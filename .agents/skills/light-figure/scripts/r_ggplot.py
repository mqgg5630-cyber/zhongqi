#!/usr/bin/env python3
"""r_ggplot.py — R/ggplot2 出版级双路径出图 (Light / figure · Round 2 R3)

新增能力(不动 python 已验路径; figure_export/color_palettes 复用不重造):
  - find_rscript()        探测 Rscript 全路径(PATH + 常见安装位; 跨平台)
  - r_available()         探测 R + ggplot2/scales 是否真可用(跑 .R 探针, 非凭记忆)
  - r_install_advisory()  R 缺失/缺包时给用户选择门(降级/安装配置/提供 Rscript)
  - recommend_engine()    按图型 + R 可用性推荐 ggplot2 / matplotlib + 理由
  - render_ggplot()       写 .R 文件 + Rscript + ggsave 出版级出图; 真验 file.exists
  - render_fallback()     R 不可用时降级 matplotlib(复用 color_palettes+figure_export), 诚实标 degraded
  - render()              双路径总入口: 探测→推荐→路由(ggplot2 或诚实降级)

为什么存在(对标 docs/competitors/figure.md §0.C⑦, 一手核 2026-06-23):
  dazhiyang/scientific-plotting-skill(6★) 同时支持 ggplot2/plotnine, 但"python/R 选择是
  用户手填 prompt、不自动"; scipilot(530★)/davila7(28.2K★)/tvhahn(19★) 纯 python。
  **10 个真·同类绘图 skill 无一做"探测 R 可用→自动选 ggplot2→不可用诚实降级 matplotlib"**——
  本脚本补这一空白。ggplot 出版配方学 dazhiyang: 85/180mm 栏宽 + Wong 离散 + viridis 连续 +
  Times 衬线单字号 + 矢量 PDF。

按图型分流(§0.C⑦: 统计/生信/社科图 ggplot 更优雅):
  ggplot2 偏好: forest(森林图) / box(箱线+原始点) / scatter+facet(分面) / corr(相关矩阵)
  matplotlib 够用: line / bar / hist / 通用程序化图(figure_export 已验路径)

铁律(违反即重做):
  - R 一律写 .R 文件再 Rscript file.R(坑①: Windows bash 给 -e 内联代码引号/\n 被吃乱码)
  - .R 探针/自测临时文件放仓库 .upgrade/_e2e, 不落系统 Temp
  - R 脚本输出英文 + 判定看 file.exists/布尔(坑②: cat 中文 Windows 控制台 GBK 乱码)
  - selftest 真出一张图验 file.exists, 不是写完 R 代码字符串就算
  - R 不可用 → 诚实降级 matplotlib 标 degraded=True, 绝不假装出了 ggplot 图
  - 需要 ggplot2 但本机缺 R/包时, 交互场景先问用户; 非交互才自动降级并写 advisory
  - 论文数据图程序化生成, 绝不 AI 生图(永久底线)
"""
from __future__ import annotations
import os
import sys
import csv
import glob
import hashlib
import json
import shutil
import tempfile
import subprocess

# 同目录兄弟脚本可被 import(无论从哪运行)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Wong/Okabe-Ito 8 色色盲安全离散(与 color_palettes.OKABE_ITO 同源, R 侧内联)
WONG = ["#000000", "#E69F00", "#56B4E9", "#009E73",
        "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]


def _repo_root():
    root = _HERE
    while True:
        if os.path.exists(os.path.join(root, "_shared", "__init__.py")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            return os.getcwd()
        root = parent


def _e2e_tmp_dir():
    root = os.path.join(_repo_root(), ".upgrade", "_e2e")
    os.makedirs(root, exist_ok=True)
    return root


def _mkstemp_r(prefix):
    return tempfile.mkstemp(suffix=".R", prefix=prefix, dir=_e2e_tmp_dir())


def _mkdtemp(prefix):
    return tempfile.mkdtemp(prefix=prefix, dir=_e2e_tmp_dir())


# 图型→偏好引擎(R 可用时); 这些是 ggplot 语法/统计标注更优雅处
GGPLOT_FAVORED = {"forest", "box", "violin", "facet", "scatter_facet", "corr", "ridge"}
# matplotlib 已验路径够用的(无需 R)
MPL_FINE = {"line", "bar", "hist", "scatter", "heatmap"}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _manifest_relpath(path, manifest_dir):
    """Return a manifest-local relative path, or None when the file is outside."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(manifest_dir))
    except ValueError:
        return None
    if rel == os.curdir or rel.startswith(".." + os.sep) or os.path.isabs(rel):
        return None
    return rel.replace("\\", "/")


def _artifact_row(path, manifest_dir, *, include_path=True):
    row = {"sha256": _sha256(path)}
    rel = _manifest_relpath(path, manifest_dir) if include_path else None
    if rel:
        row["path"] = rel
    return row


def _r_versions(rscript, packages=("ggplot2", "scales")):
    """Return actually executed R/package versions; failure stays UNKNOWN."""
    result = {"R": "UNKNOWN", **{pkg: "UNKNOWN" for pkg in packages}}
    if not rscript:
        return result
    lines = ['cat("R=", as.character(getRversion()), "\\n", sep="")']
    for pkg in packages:
        lines.append(
            f'if (requireNamespace("{pkg}", quietly=TRUE)) '
            f'cat("PKG:{pkg}=", as.character(packageVersion("{pkg}")), "\\n", sep="")')
    fd, probe = _mkstemp_r("light_rversion_")
    os.close(fd)
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        cp = _run_rscript(rscript, probe, timeout=60)
        for line in (cp.stdout or "").splitlines():
            if line.startswith("R="):
                result["R"] = line.partition("=")[2].strip() or "UNKNOWN"
            elif line.startswith("PKG:"):
                name, _, version = line[4:].partition("=")
                if name in result:
                    result[name] = version.strip() or "UNKNOWN"
    except Exception:
        pass
    finally:
        _safe_unlink(probe)
    return result


def _semantic_build(chart_type, mapping, cols, opts):
    ct = chart_type.lower()
    stats = {
        "bar": [{"name": "identity", "parameters": {}}],
        "box": [{"name": "boxplot", "parameters": {"outliers_drawn": False}}],
        "scatter": [{"name": "identity", "parameters": {}}],
        "scatter_facet": [{"name": "identity", "parameters": {}}],
        "forest": [{"name": "identity", "parameters": {"reference": opts.get("ref", 0)}}],
    }.get(ct, [{"name": "UNKNOWN", "parameters": {}}])
    scales = {
        "x": "discrete" if ct in {"bar", "box", "forest"} else "continuous",
        "y": "continuous",
        "group": "manual_okabe_ito" if "group" in cols else "none",
    }
    return {
        "mapping": dict(mapping),
        "stat_transforms": stats,
        "scales": scales,
        "coordinates": {"name": "cartesian", "parameters": {}},
        "facets": (
            {"name": "wrap", "field": mapping.get("facet")}
            if ct == "scatter_facet" and "facet" in cols
            else {"name": "none"}
        ),
    }


def _write_build_manifest(out_base, engine, engine_version, packages, chart_type,
                          mapping, cols, opts, data_path, code_path, width_mm,
                          height_mm, files, device, degraded):
    semantic = _semantic_build(chart_type, mapping, cols, opts)
    path = out_base + ".figure-build.json"
    manifest_dir = os.path.dirname(os.path.abspath(path))
    manifest = {
        "schema": "light.figure_build.v1",
        "engine": engine,
        "engine_version": engine_version,
        "packages": packages,
        "chart_type": chart_type,
        **semantic,
        "theme": {"name": "light-publication", "base_font_pt": 8},
        "seed": opts.get("seed"),
        "device": device,
        "width_mm": round(float(width_mm), 3),
        "height_mm": round(float(height_mm), 3),
        "inputs": {
            "data": _artifact_row(data_path, manifest_dir),
            "code": (
                _artifact_row(code_path, manifest_dir)
                if code_path and os.path.isfile(code_path) else None
            ),
        },
        "outputs": [
            {
                **_artifact_row(item, manifest_dir),
                "format": os.path.splitext(item)[1].lstrip(".").lower(),
            }
            for item in files if os.path.isfile(item)
        ],
        "degraded": bool(degraded),
        "honesty": (
            "Manifest records declared build semantics and file hashes; "
            "it does not prove visual honesty or scientific validity."
        ),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path, manifest


def _deterministic_jitter(label, index, width=0.24):
    token = f"{label}\0{index}".encode("utf-8")
    unit = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") / (2**64 - 1)
    return (unit - 0.5) * width


# ---------------------------------------------------------------------------
# 1) 探测 R 环境(真跑, 非凭记忆)
# ---------------------------------------------------------------------------
def find_rscript():
    """探测 Rscript 全路径。返回路径字符串或 None。
    顺序: PATH → Windows 常见安装位(Program Files, 动态取版本号) → Unix 常见位。"""
    p = shutil.which("Rscript") or shutil.which("Rscript.exe")
    if p:
        return p
    candidates = []
    # Windows: C:\Program Files\R\R-x.y.z\bin\Rscript.exe(版本号动态)
    for base in (r"C:\Program Files\R", r"C:\Program Files (x86)\R"):
        candidates += glob.glob(os.path.join(base, "*", "bin", "Rscript.exe"))
        candidates += glob.glob(os.path.join(base, "*", "bin", "x64", "Rscript.exe"))
    # Unix 常见位
    candidates += ["/usr/bin/Rscript", "/usr/local/bin/Rscript",
                   "/opt/R/*/bin/Rscript"]
    expanded = []
    for c in candidates:
        expanded += glob.glob(c) if "*" in c else ([c] if os.path.exists(c) else [])
    # 取版本号最高的(字符串逆序近似; 够用)
    expanded = sorted(set(expanded), reverse=True)
    return expanded[0] if expanded else None


def _run_rscript(rscript, r_file, timeout=120):
    """直接 subprocess 调 Rscript file.R(不经 shell, 无 bash 引号问题)。返回 CompletedProcess。"""
    return subprocess.run([rscript, r_file], capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")


def r_available(rscript=None, packages=("ggplot2", "scales")):
    """探测 R + 指定包是否真可用(写 .R 探针跑一遍, 非凭记忆)。
    返回 dict: {ok, rscript, packages:{pkg:bool}, reason}。"""
    rscript = rscript or find_rscript()
    info = {"ok": False, "rscript": rscript, "packages": {}, "reason": None}
    if not rscript:
        info["reason"] = "Rscript 未找到(PATH/Program Files/Unix 常见位均无)"
        return info
    # 探针 .R: 输出可解析 token(坑②: 英文)
    probe_lines = ['.libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))']
    for pkg in packages:
        probe_lines.append(
            f'cat("PKG:{pkg}=", requireNamespace("{pkg}", quietly=TRUE), "\\n", sep="")')
    fd, probe = _mkstemp_r("light_rprobe_")
    os.close(fd)
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("\n".join(probe_lines) + "\n")
        try:
            cp = _run_rscript(rscript, probe, timeout=60)
        except Exception as e:  # 超时/无法执行
            info["reason"] = f"Rscript 执行失败: {e.__class__.__name__}: {e}"
            return info
        out = cp.stdout or ""
        for pkg in packages:
            info["packages"][pkg] = f"PKG:{pkg}=TRUE" in out
        info["ok"] = all(info["packages"].values())
        if not info["ok"]:
            missing = [p for p, v in info["packages"].items() if not v]
            info["reason"] = (f"R 在但缺包: {missing}"
                              f"(装: install.packages(..., lib=Sys.getenv('R_LIBS_USER')))")
    finally:
        _safe_unlink(probe)
    return info


def r_install_advisory(availability=None, chart_type=None):
    """Return a machine-readable user-choice gate for missing R/ggplot2.

    Policy:
      - interactive work: ask before installing/configuring R packages;
      - non-interactive automation: degrade to matplotlib and record this advisory;
      - required_engine=R delivery: do not accept fallback as final output.
    """
    info = dict(availability or r_available(packages=("ggplot2", "scales")))
    packages = dict(info.get("packages") or {})
    missing_packages = [pkg for pkg, ok in packages.items() if not ok]
    missing: list[str] = []
    if not info.get("rscript"):
        missing.append("Rscript")
    missing.extend(missing_packages)
    ok = bool(info.get("ok"))
    choices = []
    if not ok:
        choices = [
            {
                "id": "degrade_matplotlib",
                "label": "继续用 matplotlib 诚实降级",
                "requires_user_approval": False,
                "when": "快速继续、非交互自动流程、或该图不强制 required_engine=R",
                "effect": "输出 degraded=True，并在 manifest/routing 中保留 R 缺失原因",
            },
            {
                "id": "install_or_configure_r",
                "label": "安装/配置 R + ggplot2 + scales",
                "requires_user_approval": True,
                "when": "用户确实需要 ggplot2 风格、统计/生信/社科图优先走 R，或交付规格 required_engine=R",
                "windows_hint": "安装 R 后确保 Rscript.exe 在 PATH；包安装可在 R 中运行 install.packages(c('ggplot2','scales'))",
            },
            {
                "id": "provide_rscript_path",
                "label": "提供 Rscript.exe/Rscript 绝对路径",
                "requires_user_approval": False,
                "when": "R 已安装但不在 PATH，调用 render(..., rscript='绝对路径')",
            },
        ]
    return {
        "ok": ok,
        "chart_type": (chart_type or "").lower(),
        "reason": info.get("reason"),
        "rscript": info.get("rscript"),
        "packages": packages,
        "missing": missing,
        "requires_user_choice": not ok,
        "recommended_default": "degrade_matplotlib_unless_required_engine_r" if not ok else "use_ggplot2_when_chart_prefers_r",
        "policy": "Do not install R or R packages without explicit user approval; non-interactive runs should degrade honestly.",
        "choices": choices,
    }


# ---------------------------------------------------------------------------
# 2) 引擎推荐(按图型 + R 可用性, 诚实降级)
# ---------------------------------------------------------------------------
def recommend_engine(chart_type, r_ok=None, rscript=None):
    """按图型 + R 可用性推荐引擎。返回 {engine, reason, r_ok, degraded, chart_type}。
    - 图型偏好 ggplot2 且 R 可用 → ggplot2
    - 图型偏好 ggplot2 但 R 不可用 → matplotlib + degraded=True(诚实标"本应 ggplot, 降级")
    - 其余 → matplotlib(figure_export 已验路径够用, 不必起 R)
    """
    ct = (chart_type or "").lower()
    if r_ok is None:
        r_ok = r_available(rscript=rscript)["ok"]
    favored = ct in GGPLOT_FAVORED
    if favored and r_ok:
        return {"engine": "ggplot2", "degraded": False, "r_ok": True, "chart_type": ct,
                "reason": f"{ct} 属 ggplot 优雅图型(统计标注/分面/pointrange), R+ggplot2 可用 → 走 ggplot2"}
    if favored and not r_ok:
        return {"engine": "matplotlib", "degraded": True, "r_ok": False, "chart_type": ct,
                "reason": f"{ct} 本应走 ggplot2, 但 R/ggplot2 不可用 → 诚实降级 matplotlib(复用 figure_export 出版规格)"}
    return {"engine": "matplotlib", "degraded": False, "r_ok": r_ok, "chart_type": ct,
            "reason": f"{ct} matplotlib 已验路径够用, 无需起 R"}


# ---------------------------------------------------------------------------
# 3) 数据规整: 用户列 → 固定 canonical 列(R/mpl 两侧都按固定名取, 免动态 aes)
# ---------------------------------------------------------------------------
def _canonicalize(rows, mapping, chart_type):
    """把用户行(list[dict]) 按 mapping 重映射成固定 canonical 列, 返回 (canon_rows, cols)。
    mapping 例: {"x":"group", "y":"acc", "group":"model", "ymin":"lo", "ymax":"hi"}。
    canonical 列依图型固定: bar/box→x,y(+group, +ymin/ymax); scatter→x,y(+group,+facet);
    forest→label,est,lo,hi。"""
    ct = chart_type.lower()
    if ct in ("bar", "box", "violin"):
        need, opt = ["x", "y"], ["group", "ymin", "ymax"]
    elif ct in ("scatter", "scatter_facet"):
        need, opt = ["x", "y"], ["group", "facet"]
    elif ct == "forest":
        need, opt = ["label", "est", "lo", "hi"], ["group"]
    else:
        raise ValueError(f"暂不支持的 chart_type='{chart_type}'(支持 bar/box/scatter/forest)")
    for k in need:
        if k not in mapping:
            raise ValueError(f"chart_type={ct} 需 mapping['{k}'](指向数据列)")
    keys = need + [k for k in opt if k in mapping]
    canon = []
    for r in rows:
        cr = {}
        for k in keys:
            src = mapping[k]
            if src not in r:
                raise ValueError(f"数据行缺列 '{src}'(mapping['{k}'])")
            cr[k] = r[src]
        canon.append(cr)
    return canon, keys


def _write_csv(rows, cols, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _journal_size_mm(journal, column, custom_width_mm=None, aspect=0.72):
    """取目标刊栏宽(mm)+按宽高比给高度。复用 figure_export.JOURNAL_SPECS(不重造规格)。"""
    if custom_width_mm is not None:
        w = float(custom_width_mm)
    else:
        from figure_export import JOURNAL_SPECS
        j = (journal or "nature").lower()
        if j not in JOURNAL_SPECS:
            raise ValueError(f"未知刊 {journal}; 可选 {list(JOURNAL_SPECS)} 或给 custom_width_mm")
        spec = JOURNAL_SPECS[j]
        key = f"{column}_mm"
        if key not in spec:
            avail = [k.replace("_mm", "") for k in spec if k.endswith("_mm")]
            raise ValueError(f"{journal} 无 '{column}' 栏宽, 可选 {avail}")
        w = float(spec[key])
    return w, round(w * aspect, 1)


# ---------------------------------------------------------------------------
# 4) ggplot2 路径: 写 .R + Rscript + ggsave + 真验 file.exists
# ---------------------------------------------------------------------------
def _r_header():
    return [
        '.libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))',
        'suppressMessages({library(ggplot2); library(scales)})',
        'wong <- c("#000000","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#CC79A7")',
        # dazhiyang 配方: 衬线 Times 单字号 + 无标题 + 黑轴文字
        'theme_pub <- theme_classic(base_size=8, base_family="serif") +',
        '  theme(plot.title=element_blank(), legend.title=element_blank(),',
        '        legend.position="top", axis.text=element_text(colour="black"),',
        '        legend.key.size=unit(3,"mm"))',
    ]


def _r_plot_lines(chart_type, opts):
    """按图型生成 ggplot 表达式(canonical 列名固定)。返回 R 代码行 list。"""
    ct = chart_type.lower()
    xlab = _rstr(opts.get("xlab", ""))
    ylab = _rstr(opts.get("ylab", ""))
    has_group = bool(opts.get("group"))
    L = []
    if ct == "bar":
        L.append('df$x <- factor(df$x, levels=unique(df$x))')
        if has_group:
            L.append('df$group <- factor(df$group, levels=unique(df$group))')
            L.append('p <- ggplot(df, aes(x=x, y=y, fill=group)) +')
            L.append('  geom_col(position=position_dodge(width=0.8), width=0.7) +')
        else:
            L.append('p <- ggplot(df, aes(x=x, y=y)) +')
            L.append('  geom_col(width=0.7, fill="#0072B2") +')
        if opts.get("ymin") and opts.get("ymax"):
            pos = 'position_dodge(width=0.8)' if has_group else '"identity"'
            L.append(f'  geom_errorbar(aes(ymin=ymin, ymax=ymax), width=0.2, position={pos}) +')
        if has_group:
            L.append('  scale_fill_manual(values=wong) +')
        L.append(f'  labs(x={xlab}, y={ylab}) + theme_pub')
    elif ct == "box":
        L.append('df$x <- factor(df$x, levels=unique(df$x))')
        L.append('p <- ggplot(df, aes(x=x, y=y)) +')
        L.append('  geom_boxplot(outlier.shape=NA, width=0.6, fill="#56B4E9", alpha=0.5) +')
        # davila7: 画原始点(show individual data points)
        L.append('  geom_jitter(width=0.12, height=0, size=0.7, alpha=0.6, colour="black") +')
        L.append(f'  labs(x={xlab}, y={ylab}) + theme_pub')
    elif ct in ("scatter", "scatter_facet"):
        if has_group:
            L.append('df$group <- factor(df$group)')
            L.append('p <- ggplot(df, aes(x=x, y=y, colour=group)) +')
            L.append('  geom_point(size=1.0, alpha=0.85) +')
            L.append('  scale_colour_manual(values=wong) +')
        else:
            L.append('p <- ggplot(df, aes(x=x, y=y)) +')
            L.append('  geom_point(size=1.0, alpha=0.85, colour="#0072B2") +')
        if ct == "scatter_facet" and opts.get("facet"):
            L.append('  facet_wrap(~ facet) +')
        L.append(f'  labs(x={xlab}, y={ylab}) + theme_pub')
    elif ct == "forest":
        ref = opts.get("ref", 0)
        L.append('df$label <- factor(df$label, levels=rev(unique(df$label)))')
        L.append('p <- ggplot(df, aes(x=est, y=label)) +')
        L.append(f'  geom_vline(xintercept={ref}, linetype="dashed", colour="grey50") +')
        L.append('  geom_pointrange(aes(xmin=lo, xmax=hi), size=0.4, colour="#0072B2") +')
        L.append(f'  labs(x={xlab}, y={ylab}) + theme_pub')
    else:
        raise ValueError(f"_r_plot_lines 不支持 {chart_type}")
    return L


def _rstr(s):
    """python str → R 字符串字面量(转义双引号/反斜杠)。"""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _rpath(p):
    """Windows 路径转 R 友好(正斜杠)。"""
    return os.path.abspath(p).replace("\\", "/")


def render_ggplot(chart_type, rows, mapping, out_base, journal="nature",
                  column="single", custom_width_mm=None, opts=None, rscript=None):
    """ggplot2 出版级出图: 写 .R + Rscript + ggsave(PDF+PNG)。真验 file.exists。
    返回 {ok, engine, files, exists, rscript, stdout, stderr, r_file}。"""
    opts = dict(opts or {})
    rscript = rscript or find_rscript()
    if not rscript:
        availability = {"ok": False, "rscript": None, "packages": {}, "reason": "Rscript 未找到"}
        return {"ok": False, "engine": "ggplot2", "exists": False,
                "reason": "Rscript 未找到", "files": [],
                "r_advisory": r_install_advisory(availability, chart_type)}
    availability = r_available(rscript=rscript, packages=("ggplot2", "scales"))
    if not availability["ok"]:
        return {
            "ok": False,
            "engine": "ggplot2",
            "exists": False,
            "reason": availability["reason"],
            "packages": availability["packages"],
            "rscript": rscript,
            "files": [],
            "r_advisory": r_install_advisory(availability, chart_type),
        }
    canon, cols = _canonicalize(rows, mapping, chart_type)
    opts["group"] = "group" in cols
    opts["facet"] = ("facet" in cols) and opts.get("facet", True)
    opts["ymin"] = "ymin" in cols
    opts["ymax"] = "ymax" in cols
    w_mm, h_mm = _journal_size_mm(journal, column, custom_width_mm)

    workdir = os.path.dirname(os.path.abspath(out_base)) or "."
    os.makedirs(workdir, exist_ok=True)
    csv_path = out_base + "__data.csv"
    r_file = out_base + ".R"
    out_pdf = out_base + ".pdf"
    out_png = out_base + ".png"
    _write_csv(canon, cols, csv_path)

    lines = _r_header()
    lines.append(f'df <- read.csv({_rstr(_rpath(csv_path))}, stringsAsFactors=FALSE, '
                 'check.names=TRUE, fileEncoding="UTF-8")')
    lines += _r_plot_lines(chart_type, opts)
    lines.append(f'ggsave({_rstr(_rpath(out_pdf))}, p, width={w_mm}, height={h_mm}, units="mm", dpi=300)')
    lines.append(f'ggsave({_rstr(_rpath(out_png))}, p, width={w_mm}, height={h_mm}, units="mm", dpi=300)')
    lines.append(f'ok <- file.exists({_rstr(_rpath(out_pdf))}) && file.exists({_rstr(_rpath(out_png))})')
    lines.append('cat("RENDER_OK=", ok, "\\n", sep="")')
    with open(r_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        cp = _run_rscript(rscript, r_file, timeout=120)
    except Exception as e:
        return {"ok": False, "engine": "ggplot2", "exists": False, "files": [],
                "reason": f"Rscript 执行失败: {e.__class__.__name__}: {e}", "r_file": r_file}
    exists = os.path.exists(out_pdf) and os.path.exists(out_png) \
        and os.path.getsize(out_pdf) > 0 and os.path.getsize(out_png) > 0
    ok = exists and "RENDER_OK=TRUE" in (cp.stdout or "")
    manifest_path = None
    if ok:
        versions = _r_versions(rscript)
        manifest_path, _ = _write_build_manifest(
            out_base=out_base,
            engine="R/ggplot2",
            engine_version=versions.pop("R"),
            packages=versions,
            chart_type=chart_type,
            mapping=mapping,
            cols=cols,
            opts=opts,
            data_path=csv_path,
            code_path=r_file,
            width_mm=w_mm,
            height_mm=h_mm,
            files=[out_pdf, out_png],
            device=[{"format": "pdf", "name": "ggsave"},
                    {"format": "png", "name": "ggsave", "dpi": 300}],
            degraded=False,
        )
    return {"ok": ok, "engine": "ggplot2", "exists": exists,
            "files": [out_pdf, out_png], "rscript": rscript, "r_file": r_file,
            "data_csv": csv_path, "width_mm": w_mm, "height_mm": h_mm,
            "manifest": manifest_path,
            "stdout": (cp.stdout or "").strip(), "stderr": (cp.stderr or "").strip()}


# ---------------------------------------------------------------------------
# 5) 诚实降级: matplotlib 路径(复用 color_palettes + figure_export, 不重造)
# ---------------------------------------------------------------------------
def render_fallback(chart_type, rows, mapping, out_base, journal="nature",
                    column="single", custom_width_mm=None, opts=None):
    """R 不可用时的诚实降级: 同 spec 用 matplotlib 出版级出图。degraded=True。
    复用 color_palettes.OKABE_ITO + figure_export.save_for_journal(不重写出版规格)。"""
    opts = dict(opts or {})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from color_palettes import OKABE_ITO_LIST, apply_palette
    from figure_export import save_for_journal

    canon, cols = _canonicalize(rows, mapping, chart_type)
    data_path = out_base + "__data.csv"
    _write_csv(canon, cols, data_path)
    ct = chart_type.lower()
    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    apply_palette(OKABE_ITO_LIST, ax=ax)
    xlab, ylab = opts.get("xlab", ""), opts.get("ylab", "")

    if ct == "bar":
        cats = _uniq([r["x"] for r in canon])
        if "group" in cols:
            groups = _uniq([r["group"] for r in canon])
            n = len(groups)
            width = 0.8 / max(n, 1)
            for gi, g in enumerate(groups):
                xs = [i + (gi - (n - 1) / 2) * width for i, _ in enumerate(cats)]
                ys = [_first(canon, {"x": c, "group": g}, "y") for c in cats]
                err = None
                if "ymin" in cols and "ymax" in cols:
                    lo = [_first(canon, {"x": c, "group": g}, "ymin") for c in cats]
                    hi = [_first(canon, {"x": c, "group": g}, "ymax") for c in cats]
                    err = [
                        [y - lower for y, lower in zip(ys, lo)],
                        [upper - y for y, upper in zip(ys, hi)],
                    ]
                ax.bar(xs, ys, width=width, label=str(g),
                       color=OKABE_ITO_LIST[gi % len(OKABE_ITO_LIST)],
                       yerr=err, capsize=2)
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels([str(c) for c in cats])
            ax.legend(fontsize=6, frameon=False)
        else:
            ys = [float(r["y"]) for r in canon]
            ax.bar(range(len(canon)), ys, color="#0072B2")
            if "ymin" in cols and "ymax" in cols:
                lo = [float(r["ymin"]) for r in canon]
                hi = [float(r["ymax"]) for r in canon]
                ax.errorbar(range(len(canon)), ys,
                            yerr=[[y - lower for y, lower in zip(ys, lo)],
                                  [upper - y for y, upper in zip(ys, hi)]],
                            fmt="none", ecolor="black", capsize=2)
            ax.set_xticks(range(len(canon)))
            ax.set_xticklabels([str(r["x"]) for r in canon])
    elif ct == "box":
        cats = _uniq([r["x"] for r in canon])
        data = [[float(r["y"]) for r in canon if r["x"] == c] for c in cats]
        ax.boxplot(data, showfliers=False, positions=range(len(cats)))
        for i, c in enumerate(cats):  # davila7: 画原始点
            ys = [float(r["y"]) for r in canon if r["x"] == c]
            xs = [i + _deterministic_jitter(c, k) for k, _ in enumerate(ys)]
            ax.scatter(xs, ys, s=5, alpha=0.6, color="black", zorder=3)
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels([str(c) for c in cats])
    elif ct in ("scatter", "scatter_facet"):
        xs = [float(r["x"]) for r in canon]
        ys = [float(r["y"]) for r in canon]
        if "group" in cols:
            groups = _uniq([r["group"] for r in canon])
            for gi, g in enumerate(groups):
                gx = [float(r["x"]) for r in canon if r["group"] == g]
                gy = [float(r["y"]) for r in canon if r["group"] == g]
                ax.scatter(gx, gy, s=10, label=str(g),
                           color=OKABE_ITO_LIST[gi % len(OKABE_ITO_LIST)], alpha=0.85)
            ax.legend(fontsize=6, frameon=False)
        else:
            ax.scatter(xs, ys, s=10, color="#0072B2", alpha=0.85)
    elif ct == "forest":
        labels = [str(r["label"]) for r in canon]
        est = [float(r["est"]) for r in canon]
        lo = [float(r["lo"]) for r in canon]
        hi = [float(r["hi"]) for r in canon]
        ypos = list(range(len(labels)))[::-1]
        ax.errorbar(est, ypos, xerr=[[e - lower for e, lower in zip(est, lo)],
                                      [upper - e for upper, e in zip(hi, est)]],
                    fmt="o", color="#0072B2", capsize=2)
        ax.axvline(opts.get("ref", 0), linestyle="--", color="grey")
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels)
    else:
        plt.close(fig)
        raise ValueError(f"render_fallback 不支持 {chart_type}")

    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    written, info = save_for_journal(fig, out_base, journal=journal, column=column,
                                     custom_width_mm=custom_width_mm,
                                     formats=("pdf", "png"))
    size_in = fig.get_size_inches()
    width_mm, height_mm = float(size_in[0]) * 25.4, float(size_in[1]) * 25.4
    plt.close(fig)
    exists = all(os.path.exists(p) and os.path.getsize(p) > 0 for p in written)
    manifest_path = None
    if exists:
        recipe_path = out_base + ".matplotlib-recipe.json"
        with open(recipe_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema": "light.figure_matplotlib_recipe.v1",
                "generated_by": "light-figure/scripts/r_ggplot.py::render_fallback",
                "chart_type": chart_type,
                "mapping": mapping,
                "journal": journal,
                "column": column,
                "custom_width_mm": custom_width_mm,
                "options": opts,
                "data_csv": os.path.basename(data_path),
                "honesty": (
                    "This recipe records the fallback plotting parameters; "
                    "it is not a substitute for the data/caption/evidence contract."
                ),
            }, f, ensure_ascii=False, indent=2)
            f.write("\n")
        manifest_path, _ = _write_build_manifest(
            out_base=out_base,
            engine="Python/matplotlib",
            engine_version=sys.version.split()[0],
            packages={"matplotlib": matplotlib.__version__},
            chart_type=chart_type,
            mapping=mapping,
            cols=cols,
            opts=opts,
            data_path=data_path,
            code_path=recipe_path,
            width_mm=width_mm,
            height_mm=height_mm,
            files=written,
            device=[{"format": os.path.splitext(path)[1].lstrip("."),
                     "name": "save_for_journal"}
                    for path in written],
            degraded=True,
        )
    return {"ok": exists, "engine": "matplotlib", "degraded": True, "exists": exists,
            "files": written, "journal_info": {"width_mm": info["width_mm"]},
            "data_csv": data_path, "width_mm": width_mm, "height_mm": height_mm,
            "manifest": manifest_path,
            "note": "R/ggplot2 不可用, 已诚实降级 matplotlib(出版规格复用 figure_export)"}


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _first(rows, match, col):
    for r in rows:
        if all(r.get(k) == v for k, v in match.items()):
            return float(r[col])
    return 0.0


# ---------------------------------------------------------------------------
# 6) 双路径总入口
# ---------------------------------------------------------------------------
def render(chart_type, rows, mapping, out_base, journal="nature", column="single",
           custom_width_mm=None, opts=None, prefer="auto", rscript=None):
    """双路径总入口: 探测 R → 推荐引擎 → 路由。
    prefer: 'auto'(按图型+可用性) / 'ggplot2'(尽量 R, 不可用诚实降级) / 'matplotlib'(强制降级路径)。
    返回各 render_* 的结果 dict, 附 routing。"""
    rscript = rscript or find_rscript()
    rinfo = r_available(rscript=rscript)
    r_ok = rinfo["ok"]
    if prefer == "matplotlib":
        routing = {"engine": "matplotlib", "degraded": False, "r_ok": r_ok,
                   "reason": "调用方强制 matplotlib 路径"}
    elif prefer == "ggplot2":
        routing = recommend_engine(chart_type, r_ok=r_ok)
        routing["engine"] = "ggplot2" if r_ok else "matplotlib"
        routing["degraded"] = not r_ok
        routing["reason"] = ("调用方要 ggplot2, R 可用 → ggplot2" if r_ok else
                             "调用方要 ggplot2 但 R 不可用 → 诚实降级 matplotlib")
    else:
        routing = recommend_engine(chart_type, r_ok=r_ok)
    advisory = None
    if routing.get("degraded") and not r_ok:
        advisory = r_install_advisory(rinfo, chart_type)
        routing["r_advisory"] = advisory

    if routing["engine"] == "ggplot2":
        res = render_ggplot(chart_type, rows, mapping, out_base, journal, column,
                            custom_width_mm, opts, rscript)
        res["degraded"] = False
    else:
        res = render_fallback(chart_type, rows, mapping, out_base, journal, column,
                              custom_width_mm, opts)
    res["routing"] = routing
    if advisory:
        res["r_advisory"] = advisory
    return res


# ---------------------------------------------------------------------------
# 7) selftest(真出图验 file.exists, 不是写完 R 字符串就算)
# ---------------------------------------------------------------------------
def _safe_unlink(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _assert_manifest_paths_packaged(manifest):
    rows = []
    inputs = manifest.get("inputs") or {}
    for row in inputs.values():
        if isinstance(row, dict) and row.get("path"):
            rows.append(row)
    rows.extend(manifest.get("outputs") or [])
    for row in rows:
        path = str(row.get("path") or "")
        parts = path.replace("\\", "/").split("/")
        assert path and not os.path.isabs(path) and ".." not in parts, row


def _selftest():
    print("=" * 60)
    print("[r_ggplot selftest]")
    rs = find_rscript()
    rinfo = r_available(rscript=rs)
    print(f"  find_rscript    -> {rs}")
    print(f"  r_available     -> ok={rinfo['ok']} packages={rinfo['packages']} "
          f"reason={rinfo['reason']}")

    # --- 引擎推荐路由(不依赖 R 是否在, 用显式 r_ok 断言两支) ---
    assert recommend_engine("forest", r_ok=True)["engine"] == "ggplot2"
    assert _deterministic_jitter("A", 1) == _deterministic_jitter("A", 1)
    assert _deterministic_jitter("A", 1) != _deterministic_jitter("A", 2)
    d = recommend_engine("forest", r_ok=False)
    assert d["engine"] == "matplotlib" and d["degraded"] is True, d
    assert recommend_engine("line", r_ok=True)["engine"] == "matplotlib"
    assert recommend_engine("bar", r_ok=False)["degraded"] is False
    print("  recommend_engine-> 路由断言通过(forest+R→ggplot2 / forest-R→降级 / line→mpl)")

    tmp = _mkdtemp("light_rgg_self_")
    made = []
    try:
        # 造小数据
        bar_rows = [{"grp": g, "mdl": m, "acc": a, "lo": a - 2, "hi": a + 2}
                    for g, m, a in [("A", "ours", 88), ("A", "base", 81),
                                     ("B", "ours", 92), ("B", "base", 85)]]
        forest_rows = [{"study": s, "or": o, "l": lower, "h": upper}
                       for s, o, lower, upper in
                       [("Trial-1", 1.2, 0.9, 1.6), ("Trial-2", 0.8, 0.6, 1.1),
                        ("Trial-3", 1.5, 1.1, 2.0)]]

        # --- ggplot2 路径(R 可用才真跑, 真验 file.exists) ---
        if rinfo["ok"]:
            base_g = os.path.join(tmp, "self_forest_ggplot")
            res = render_ggplot("forest", forest_rows,
                                {"label": "study", "est": "or", "lo": "l", "hi": "h"},
                                base_g, journal="nature", column="single",
                                opts={"xlab": "Odds ratio", "ylab": "", "ref": 1})
            print(f"  render_ggplot   -> ok={res['ok']} exists={res['exists']} "
                  f"files={[os.path.basename(f) for f in res['files']]} "
                  f"stdout={res.get('stdout','')[:40]!r}")
            assert res["ok"] and res["exists"], f"ggplot 路径真出图失败: {res}"
            assert all(os.path.exists(f) and os.path.getsize(f) > 0 for f in res["files"]), res
            assert res["manifest"] and os.path.exists(res["manifest"]), res
            with open(res["manifest"], encoding="utf-8") as f:
                gg_manifest = json.load(f)
            assert gg_manifest["engine"] == "R/ggplot2"
            assert gg_manifest["mapping"]["est"] == "or"
            assert gg_manifest["inputs"]["data"]["sha256"].startswith("sha256:")
            _assert_manifest_paths_packaged(gg_manifest)
            made += res["files"] + [res.get("r_file"), res.get("data_csv")]
            made.append(res["manifest"])
            print("  [PASS] ggplot2 路径真出一张 forest 图(PDF+PNG, file.exists 验证)")
        else:
            print("  [SKIP] R/ggplot2 不可用, 跳过 ggplot2 真出图("
                  "诚实: 本机无 R 时此分支不报 PASS, 见降级分支)")

        # --- 降级路径(强制 prefer=matplotlib, 必真出图) ---
        base_f = os.path.join(tmp, "self_bar_fallback")
        rf = render_fallback("bar", bar_rows,
                             {"x": "grp", "y": "acc", "group": "mdl", "ymin": "lo", "ymax": "hi"},
                             base_f, journal="nature", column="single",
                             opts={"xlab": "Group", "ylab": "Accuracy (%)"})
        print(f"  render_fallback -> ok={rf['ok']} degraded={rf['degraded']} "
              f"files={[os.path.basename(f) for f in rf['files']]} w={rf['journal_info']['width_mm']}mm")
        assert rf["ok"] and rf["degraded"] is True, f"降级路径真出图失败: {rf}"
        assert all(os.path.exists(f) and os.path.getsize(f) > 0 for f in rf["files"]), rf
        assert rf["manifest"] and os.path.exists(rf["manifest"]), rf
        with open(rf["manifest"], encoding="utf-8") as f:
            py_manifest = json.load(f)
        assert py_manifest["engine"] == "Python/matplotlib"
        assert py_manifest["outputs"] and py_manifest["inputs"]["code"]["sha256"]
        _assert_manifest_paths_packaged(py_manifest)
        made += rf["files"] + [rf.get("data_csv"), rf.get("manifest")]
        print("  [PASS] 降级 matplotlib 路径真出一张 bar 图(误差棒+Okabe-Ito+栏宽, file.exists 验证)")

        # --- 双路径总入口: prefer=ggplot2 但模拟 R 不可用 → 必 degraded 且仍出图(不假装 ggplot) ---
        base_d = os.path.join(tmp, "self_box_degrade")
        # 用一个不存在的 rscript 模拟 R 不可用
        rr = render("box", [{"c": "X", "v": v} for v in [1, 2, 2, 3, 3, 3, 4, 5]] +
                    [{"c": "Y", "v": v} for v in [2, 3, 3, 4, 4, 5, 6, 7]],
                    {"x": "c", "y": "v"}, base_d, prefer="ggplot2", rscript="___no_such_rscript___",
                    opts={"xlab": "Cond", "ylab": "Value"})
        print(f"  render(prefer=ggplot2, R缺) -> engine={rr['engine']} degraded={rr.get('degraded')} "
              f"routing={rr['routing']['reason'][:48]!r}")
        assert rr["engine"] == "matplotlib" and rr.get("degraded") is True, \
            f"R 缺时 prefer=ggplot2 应诚实降级, 实得: {rr}"
        assert rr["exists"], f"降级仍须真出图: {rr}"
        assert rr["r_advisory"]["requires_user_choice"] is True, rr.get("r_advisory")
        assert any(c["id"] == "install_or_configure_r" and c["requires_user_approval"]
                   for c in rr["r_advisory"]["choices"]), rr["r_advisory"]
        made += rr["files"]
        print("  [PASS] R 不可用时 prefer=ggplot2 诚实降级 matplotlib + 安装需用户批准 advisory")

        print("[selftest] ALL PASS")
        return 0
    finally:
        _safe_unlink(*[m for m in made if m])
        # 清掉整个临时目录(连带 __data.csv/.R)
        try:
            for f in os.listdir(tmp):
                _safe_unlink(os.path.join(tmp, f))
            os.rmdir(tmp)
        except OSError:
            pass


def _print_detect():
    rs = find_rscript()
    info = r_available(rscript=rs)
    print(json.dumps({"rscript": rs, **info,
                      "r_advisory": r_install_advisory(info)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--selftest"
    if arg == "--selftest":
        raise SystemExit(_selftest())
    elif arg == "--detect":
        _print_detect()
    else:
        raise SystemExit("usage: python r_ggplot.py [--selftest|--detect]")
