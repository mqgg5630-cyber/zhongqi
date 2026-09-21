#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seed_audit.py — 随机种子「覆盖度」静态机检（把复现清单落成可机检的纯工具）。

【为什么是 experiment-coding 的净新增灵魂】
research-plan 的 `reproducibility-checklist.md` 把「种子全覆盖」写成了**人工清单**
（★ 最常漏:PYTHONHASHSEED / cuDNN deterministic / DataLoader worker 种子）。v1 backend-coding
只有一个**运行期** helper `set_global_seed`(去设种子),**没有任何静态门去核查「代码到底设没设全」**。
本脚本就是补这一块:AST 扫一份/多份训练代码,按**实际 import 的框架**核查每类种子机制是否被设,
列出「缺哪几个」+ 每个缺失的严重度。这是 `repro_gate.py` 的 reproducible(可复现)critical 门的引擎。

它是**纯工具**(零接 `_shared`、零产 findings),与 v2 灵魂范式一致:findings 接线归 `repro_gate.py`
(类比 plan_gate 编排 plan_lint/power_check)。

覆盖的种子机制(对齐 reproducibility-checklist + PyTorch 官方 randomness 文档,2026-06 一手核):
  - pythonhashseed         : os.environ["PYTHONHASHSEED"]=...(★ 最常漏;影响 set/dict 跨进程顺序)
  - random_seed            : random.seed(s)(stdlib)
  - numpy_seed             : np.random.seed(s) 或 np.random.default_rng(s)(两者都认)
  - torch_seed             : torch.manual_seed(s)
  - torch_cuda_seed        : torch.cuda.manual_seed_all(s)(用 GPU 时)
  - cudnn_deterministic    : cudnn.deterministic=True + cudnn.benchmark=False,或
                             torch.use_deterministic_algorithms(True)(用 GPU 时;★ 最常漏)
  - dataloader_worker_seed : DataLoader 传 worker_init_fn= 或 generator=(多进程取数;★ 最常漏)
  - tf_seed                : tf.random.set_seed(s)

要求(required)按**实际用到的框架**推断,不无脑全要(避免 CPU-only / 不用某框架时误报):
  - 任一框架被用 → 要求 pythonhashseed。
  - random/numpy/torch/tf 各自被 import → 要求其框架种子。
  - 有 GPU/CUDA 迹象(torch.cuda.* / 'cuda' / .cuda())→ 额外要求 torch_cuda_seed + cudnn_deterministic。
  - 用了 DataLoader → 额外要求 dataloader_worker_seed。

诚实边界(名实对齐,铁律 2):
  - **静态扫描查「有没有设种子调用」,不证明「代码真可复现」**——可复现的终判是**同种子真跑两次比对**。
  - **委托式播种不误报**:代码若调 set_global_seed/seed_everything 这类 helper 而 helper 本身未纳入扫描,
    缺失项降级为 warn(提示「把 helper 一并扫描以核实」),不武断判 critical。把 helper 文件一并传入即按真覆盖判。
  - 框架「被用」按 import 推断;若随机性藏在未 import 的三方库里,本工具看不到(GIGO)。

用法:
  python seed_audit.py train.py model.py            # 扫多文件(取并集)
  python seed_audit.py train.py --json              # 输出机读 JSON
  python seed_audit.py --selftest
"""

from __future__ import annotations
import argparse
import ast
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 识别为「全局播种 helper」的函数名(调用了它=委托播种;定义了它=覆盖在此文件内)
SEED_HELPER_NAMES = {
    "set_global_seed",
    "set_seed",
    "seed_everything",
    "set_random_seed",
    "fix_seed",
    "fix_seeds",
    "seed_all",
    "set_all_seeds",
    "make_reproducible",
    "enable_reproducibility",
    "set_determinism",
}

# 每个机制缺失时的「基准严重度」(用了对应框架/场景才会被 required)
_BASE_SEVERITY = {
    "pythonhashseed": "critical",
    "random_seed": "critical",
    "numpy_seed": "critical",
    "torch_seed": "critical",
    "torch_cuda_seed": "critical",
    "cudnn_deterministic": "critical",
    "dataloader_worker_seed": "critical",
    "tf_seed": "critical",
}
_FIX = {
    "pythonhashseed": 'os.environ["PYTHONHASHSEED"] = str(seed)(须在进程启动前设;影响 set/dict 顺序)',
    "random_seed": "random.seed(seed)",
    "numpy_seed": "np.random.seed(seed) 或 rng = np.random.default_rng(seed)",
    "torch_seed": "torch.manual_seed(seed)",
    "torch_cuda_seed": "torch.cuda.manual_seed_all(seed)",
    "cudnn_deterministic": "torch.backends.cudnn.deterministic=True + benchmark=False"
    "(或 torch.use_deterministic_algorithms(True) + 设 CUBLAS_WORKSPACE_CONFIG=:4096:2)",
    "dataloader_worker_seed": "DataLoader(..., worker_init_fn=seed_worker, "
    "generator=torch.Generator().manual_seed(seed))",
    "tf_seed": "tf.random.set_seed(seed)",
}


def _dotted(node: ast.AST) -> str:
    """把属性链 ast 还原成点名串:torch.cuda.manual_seed_all / np.random.default_rng。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _scan_one(source: str, filename: str = "<src>") -> dict:
    """扫一份源码,返回 used / hints / set-mechanisms / helper 定义与调用。"""
    out = {
        "frameworks": set(),
        "uses_dataloader": False,
        "uses_gpu": False,
        "set": set(),
        "helper_called": False,
        "helper_defined": False,
        "syntax_error": None,
        "import_aliases": {},
    }
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        out["syntax_error"] = f"{filename}:{e.lineno or 0}: {e.msg}"
        return out

    # 1) import 推断框架用了哪些
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split(".")[0]
                out["import_aliases"][a.asname or base] = base
                if base == "numpy":
                    out["frameworks"].add("numpy")
                elif base == "torch":
                    out["frameworks"].add("torch")
                elif base in ("tensorflow",):
                    out["frameworks"].add("tensorflow")
                elif base == "random":
                    out["frameworks"].add("random")
        elif isinstance(node, ast.ImportFrom):
            base = (node.module or "").split(".")[0]
            if base == "numpy":
                out["frameworks"].add("numpy")
            elif base == "torch":
                out["frameworks"].add("torch")
            elif base == "tensorflow":
                out["frameworks"].add("tensorflow")
            for a in node.names:
                if a.name == "DataLoader":
                    out["uses_dataloader"] = True

    # 2) 源码级 GPU 迹象(.cuda() / device='cuda' / "cuda")—— 启发式提示
    if re.search(
        r"\.cuda\(|['\"]cuda|cuda:\d|device\s*=\s*['\"]cuda|manual_seed_all|cudnn",
        source,
    ):
        out["uses_gpu"] = True

    # 3) 调用 / 赋值 / 下标 检测「设了哪些种子机制」
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            tail = name.split(".")[-1]
            # 框架种子调用(同时也佐证框架被用)
            if name.endswith("random.seed") and ("np" in name or "numpy" in name):
                out["set"].add("numpy_seed")
                out["frameworks"].add("numpy")
            elif tail == "default_rng":
                out["set"].add("numpy_seed")
                out["frameworks"].add("numpy")
            elif name.endswith("random.seed"):  # random.seed(...)(stdlib)
                out["set"].add("random_seed")
                out["frameworks"].add("random")
            elif tail == "manual_seed_all":
                out["set"].add("torch_cuda_seed")
                out["frameworks"].add("torch")
                out["uses_gpu"] = True
            elif tail == "manual_seed":
                out["set"].add("torch_seed")
                out["frameworks"].add("torch")
            elif tail == "use_deterministic_algorithms":
                out["set"].add("cudnn_deterministic")
                out["frameworks"].add("torch")
            elif name.endswith("random.set_seed"):  # tf.random.set_seed
                out["set"].add("tf_seed")
                out["frameworks"].add("tensorflow")
            elif tail == "DataLoader":
                out["uses_dataloader"] = True
                for kw in node.keywords:
                    if kw.arg in ("worker_init_fn", "generator"):
                        out["set"].add("dataloader_worker_seed")
            # helper 调用(委托播种)
            if tail in SEED_HELPER_NAMES:
                out["helper_called"] = True
        # cudnn.deterministic=True / cudnn.benchmark=False
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                dn = _dotted(tgt)
                if dn.endswith("cudnn.deterministic") and _is_true(node.value):
                    out.setdefault("_cudnn_det", True)
                    out["_cudnn_det"] = True
                if dn.endswith("cudnn.benchmark") and _is_false(node.value):
                    out["_cudnn_bench_off"] = True
        # os.environ["PYTHONHASHSEED"]=...
        if isinstance(node, ast.Subscript) and _dotted(node.value).endswith("environ"):
            key = _const_str(node.slice)
            if key == "PYTHONHASHSEED":
                out["set"].add("pythonhashseed")
        # helper 定义
        if isinstance(node, ast.FunctionDef) and node.name in SEED_HELPER_NAMES:
            out["helper_defined"] = True

    # cudnn 确定性:deterministic=True 且 benchmark=False(任一缺则不算齐;use_deterministic_algorithms 已单独计)
    if out.get("_cudnn_det") and out.get("_cudnn_bench_off"):
        out["set"].add("cudnn_deterministic")
    return out


def _is_true(v: ast.AST) -> bool:
    return isinstance(v, ast.Constant) and v.value is True


def _is_false(v: ast.AST) -> bool:
    return isinstance(v, ast.Constant) and v.value is False


def _const_str(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _merge(parts: list[dict]) -> dict:
    """多文件取并集:框架/迹象 OR 起来,set-mechanisms / helper 标志 OR 起来。"""
    m = {
        "frameworks": set(),
        "uses_dataloader": False,
        "uses_gpu": False,
        "set": set(),
        "helper_called": False,
        "helper_defined": False,
        "syntax_errors": [],
    }
    for p in parts:
        if p.get("syntax_error"):
            m["syntax_errors"].append(p["syntax_error"])
        m["frameworks"] |= p["frameworks"]
        m["uses_dataloader"] |= p["uses_dataloader"]
        m["uses_gpu"] |= p["uses_gpu"]
        m["set"] |= p["set"]
        m["helper_called"] |= p["helper_called"]
        m["helper_defined"] |= p["helper_defined"]
    return m


def required_mechanisms(m: dict) -> list[str]:
    """按实际用到的框架 / 场景推断「应当设」的种子机制。"""
    fw = m["frameworks"]
    req = []
    if fw:  # 用了任一框架 → PYTHONHASHSEED 永远要
        req.append("pythonhashseed")
    if "random" in fw:
        req.append("random_seed")
    if "numpy" in fw:
        req.append("numpy_seed")
    if "torch" in fw:
        req.append("torch_seed")
        if m["uses_gpu"]:
            req += ["torch_cuda_seed", "cudnn_deterministic"]
    if "tensorflow" in fw:
        req.append("tf_seed")
    if m["uses_dataloader"]:
        req.append("dataloader_worker_seed")
    return req


def audit(sources: list[tuple[str, str]]) -> dict:
    """对若干 (filename, source) 做种子覆盖度审计。返回机读结论。"""
    parts = [_scan_one(src, fn) for fn, src in sources]
    m = _merge(parts)
    req = required_mechanisms(m)
    have = m["set"]
    # 委托式播种:调了 helper 但 helper 定义不在扫描集 → 缺失项降级 warn(不武断 critical)
    delegated = m["helper_called"] and not m["helper_defined"]
    missing = []
    for mech in req:
        if mech in have:
            continue
        sev = _BASE_SEVERITY[mech]
        if delegated:
            sev = "warn"
        missing.append({"mechanism": mech, "severity": sev, "fix": _FIX[mech]})
    has_randomness = bool(m["frameworks"])
    ok = has_randomness and not missing
    return {
        "frameworks": sorted(m["frameworks"]),
        "uses_dataloader": m["uses_dataloader"],
        "uses_gpu": m["uses_gpu"],
        "required": req,
        "set": sorted(have),
        "missing": missing,
        "missing_critical": [
            x["mechanism"] for x in missing if x["severity"] == "critical"
        ],
        "delegated_to_unscanned_helper": delegated,
        "has_randomness": has_randomness,
        "syntax_errors": m["syntax_errors"],
        "ok": ok,
    }


def audit_files(paths: list[str]) -> dict:
    sources = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                sources.append((p, f.read()))
        except OSError as e:
            sources.append((p, f"# READ-ERROR {e}\n"))
    return audit(sources)


def to_markdown(rep: dict) -> str:
    L = ["# 随机种子覆盖度审计", ""]
    if not rep["has_randomness"]:
        L.append(
            "ℹ 未检出 random/numpy/torch/tensorflow 用法——无随机性需固定(或随机性藏在未 import 的三方库,GIGO)。"
        )
        return "\n".join(L)
    L.append(
        f"- 用到框架:{', '.join(rep['frameworks'])}"
        f"  |  DataLoader={rep['uses_dataloader']}  GPU迹象={rep['uses_gpu']}"
    )
    L.append(f"- 应设:{', '.join(rep['required'])}")
    L.append(f"- 已设:{', '.join(rep['set']) or '(无)'}")
    if rep["delegated_to_unscanned_helper"]:
        L.append(
            "- ⚠ 检出 set_global_seed 类 helper 调用但未纳入扫描——缺失项降级为 warn"
            "(把 helper 文件一并传入以按真覆盖判定)。"
        )
    if rep["missing"]:
        L.append("")
        L.append("| 缺失机制 | 严重度 | 修复 |")
        L.append("| --- | --- | --- |")
        for x in rep["missing"]:
            L.append(f"| {x['mechanism']} | **{x['severity']}** | {x['fix']} |")
    else:
        L.append("- ✅ 已覆盖全部应设种子机制(静态层面;终判仍需同种子真跑两次比对)。")
    if rep["syntax_errors"]:
        L.append("")
        L.append("> 语法错误(未能解析,如实报):" + "；".join(rep["syntax_errors"]))
    L.append("")
    L.append(
        "> 静态扫描:查「有没有设种子」,不证明「真可复现」——可复现终判 = 同种子真跑两次结果一致。"
    )
    return "\n".join(L)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
_FULL = """
import os, random
import numpy as np
import torch
from torch.utils.data import DataLoader

def seed_worker(wid):
    s = torch.initial_seed() % 2**32
    np.random.seed(s); random.seed(s)

def main(seed=42):
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    g = torch.Generator(); g.manual_seed(seed)
    dl = DataLoader([1, 2, 3], worker_init_fn=seed_worker, generator=g)
    return dl
"""

_MISSING = """
import os, random
import numpy as np
import torch
from torch.utils.data import DataLoader

def main(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)         # 用了 GPU
    dl = DataLoader([1, 2, 3])               # 漏 worker_init_fn/generator
    return dl
    # 漏 PYTHONHASHSEED、漏 cudnn deterministic
"""

_DELEGATED_CALL = """
import torch, numpy as np, random
from mylib.repro import set_global_seed
def main():
    set_global_seed(42)          # 委托 helper(未纳入扫描)
    return torch.nn.Linear(3, 3)
"""

_HELPER_DEF = """
import os, random
import numpy as np
import torch
def set_global_seed(seed=42):
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
"""

_NO_RANDOM = """
import json
def load(p):
    with open(p) as f:
        return json.load(f)
"""


def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 全覆盖 → ok,无缺失
    r1 = audit([("full.py", _FULL)])
    check(
        r1["ok"] and not r1["missing"], f"全覆盖应 ok 无缺失,得 missing={r1['missing']}"
    )
    check("dataloader_worker_seed" in r1["set"], "应识别 worker_init_fn/generator")
    check(
        "cudnn_deterministic" in r1["set"], "应识别 cudnn deterministic+benchmark off"
    )
    check("pythonhashseed" in r1["set"], "应识别 PYTHONHASHSEED")

    # 2. 种子不全(漏 PYTHONHASHSEED + cuDNN + DataLoader worker)→ 多个 critical
    r2 = audit([("bad.py", _MISSING)])
    miss = set(r2["missing_critical"])
    check("pythonhashseed" in miss, f"应抓漏 PYTHONHASHSEED critical,得 {miss}")
    check(
        "cudnn_deterministic" in miss, f"应抓漏 cuDNN deterministic critical,得 {miss}"
    )
    check(
        "dataloader_worker_seed" in miss, f"应抓漏 DataLoader worker critical,得 {miss}"
    )
    check(not r2["ok"], "种子不全应 ok=False")
    check(r2["uses_gpu"], "manual_seed_all 应判 uses_gpu")

    # 3. 委托 helper 未纳入扫描 → 缺失降级 warn(不武断 critical)
    r3 = audit([("train.py", _DELEGATED_CALL)])
    check(r3["delegated_to_unscanned_helper"], "应检出委托未扫描 helper")
    check(
        r3["missing"] and all(x["severity"] == "warn" for x in r3["missing"]),
        f"委托式缺失应全 warn,得 {r3['missing']}",
    )
    check(not r3["missing_critical"], "委托式不应有 critical")

    # 4. helper 一并纳入扫描 → 按真覆盖(helper 设了 hashseed/random/numpy/torch)
    r4 = audit([("train.py", _DELEGATED_CALL), ("repro.py", _HELPER_DEF)])
    check(not r4["delegated_to_unscanned_helper"], "helper 已纳入,不应再判委托")
    check(
        "pythonhashseed" in r4["set"] and "torch_seed" in r4["set"],
        "应吸收 helper 内设的种子机制",
    )
    # train.py 无 GPU 迹象、无 DataLoader → 不要求 cuda/worker;helper 覆盖基础四项 → ok
    check(r4["ok"], f"helper 纳入后应 ok,得 missing={r4['missing']}")

    # 5. 无随机性 → 跳过(不误判缺种子)
    r5 = audit([("io.py", _NO_RANDOM)])
    check(not r5["has_randomness"] and not r5["missing"], "无随机性不应报缺种子")
    check(not r5["ok"], "无随机性 ok=False(无可复现可言,非通过)")

    # 6. 语法错误如实报
    r6 = audit([("syntax.py", "def f(:\n")])
    check(r6["syntax_errors"], "语法错误应如实报")

    # 7. markdown 不崩
    check("种子覆盖度" in to_markdown(r2), "markdown 应含标题")

    if failures:
        print("[SELFTEST][seed_audit] FAIL:")
        for x in failures:
            print("  -", x)
        return 1
    print(
        "[SELFTEST][seed_audit] OK:全覆盖 ok / 漏 PYTHONHASHSEED+cuDNN+worker critical / "
        "委托 helper 降级 warn / helper 纳入按真覆盖 / 无随机性跳过 / 语法错如实报 全通过。"
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="随机种子覆盖度静态机检(纯工具;findings 接线归 repro_gate)"
    )
    ap.add_argument(
        "paths",
        nargs="*",
        help="要扫的 .py 文件(多文件取并集;把 set_global_seed helper 一并传入)",
    )
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    if not args.paths:
        ap.error("提供 .py 文件路径,或 --selftest")
    rep = audit_files(args.paths)
    print(
        json.dumps(rep, ensure_ascii=False, indent=2) if args.json else to_markdown(rep)
    )
    # 有 critical 缺失 → 退出码 1(便于单独当 CI 门)
    sys.exit(1 if rep["missing_critical"] else 0)


if __name__ == "__main__":
    main()
