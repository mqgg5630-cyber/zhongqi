#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consistency_audit.py —— 跨材料一致性审计器 (Light / light-consistency)

读取项目 .light/ 事实源(受控术语表 / 方法名锁定 / 指标登记表 / 主张登记表)，扫描一组材料文本，
检测并定位以下不一致，输出结构化报告(产 light.findings.v1 被总控 run_checkpoint 聚合)：

  SUBSTITUTION  受控术语/方法名被同义改写或写错(大小写、连字符、近义词)
  VARIANT_CONFLICT 同一概念两种写法在材料里"共存即冲突"(无需预写 forbidden,自动发现)
  METRIC_NAME   同一指标被换名(如把 F1 写成 准确率)
  METRIC_VALUE  同一指标(同方法×数据集)在不同材料数值不一致(论文 vs PPT)
  GROSS_MISMATCH 数值同量级但超容差(30%~300%)，疑严重错填，单列告警不静默丢弃
  CONTRIBUTION_DRIFT 创新点/贡献在某材料提法偏离 .light/ 标准措辞(语义相似度,挂 _shared/semantic_sim)
  CLAIM_STRENGTH_DRIFT 主张措辞强于其证据档(result-analysis 标 weak 却写"显著/SOTA";挂 _shared/evidence_contract)
  ABBREV_FIRST_USE 缩写未遵循"首次全称(缩写)、此后用缩写"规则(消费 method_lock.first_use_rule)
  STALE_SNAPSHOT 材料/项目卡内 [snapshot date=… src=…] 三件套超期(计量>90天/许可>365天)
  COVERAGE_GAP  某规范术语/指标只在部分材料出现，在应出现的材料里缺席
  AUTHORITY_COVERAGE 事实源缺 registry/owner/provenance 时显式 warn-only，未覆盖不冒充已一致

每条发现带定位(material:line)与修正建议。报告末尾做完整性自检(条数核对)。
作用域感知(scope-aware):```围栏代码块 / `行内代码` 内的命中按需跳过,避免代码里
的 finetune 被当正文 SUBSTITUTION 误命中(对标 Vale 的 scope=text)。

跨技能反哺(挂接 _shared 共享契约,规范 bootstrap,不重造轮子)：
  - evidence_contract.py(light.evidence_strength.v1)：CLAIM_STRENGTH_DRIFT 用其
    grade_evidence/allowed_verb_tier/lint_wording 做"证据档→允许措辞档"机械映射。
  - semantic_sim.py：CONTRIBUTION_DRIFT 用其 similarity() 替旧的裸 token-Jaccard,
    词序无关、能识别倒装,治"一字对齐"措辞夸大。缺失时诚实降级回 Jaccard 并标注。

用法（事实源在项目 .light/，去本地知识库）：
  python consistency_audit.py --source .light/consistency --materials paper.md ppt.md [--json out.json]
  python consistency_audit.py --source .light/terminology.md --materials *.md   # Markdown 表(覆盖缺口档)
  python consistency_audit.py --source .light/consistency --materials *.md --report cons.findings.json
      └ 产 light.findings.v1 → 交总控:run_checkpoint --findings cons.findings.json(跨阶段一致性门,exit 1 阻断)
  python consistency_audit.py --selftest # 合成自测(X-1..X-9 + R2 authority + F-1..F-5)
  python consistency_audit.py            # 无参数 -> 同 --selftest

依赖：PyYAML(已确认环境可用)；无网络、无外部数据。
_shared 契约:semantic_sim/evidence_contract 为可选增强;findings_schema/gate_runner 产机读门。
  缺失时相关检测/产门降级且显式标注,绝不静默假成功。
"""
import argparse
import datetime
import glob
import json
import os
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

try:
    import yaml
except ImportError:
    sys.stderr.write("需要 PyYAML: pip install pyyaml\n")
    sys.exit(2)

# ── 挂接 _shared 共享契约:规范 bootstrap(向上走目录树找含 _shared 包的仓库根)──────
# 治 v1 硬编码 ../../_shared / parents[N] 之脆:v2 的 _shared 在仓库根、与 skills/ 平级,
# 脚本嵌套深度也变了,硬编码必断。规范 bootstrap 不依赖深度,三 harness / 全局安装 /
# 任意嵌套都可靠(见 _shared/README.md)。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
if str(_r) not in sys.path:
    sys.path.insert(0, str(_r))
try:
    from _shared import evidence_contract as _evc
    HAVE_EVIDENCE = True
except Exception:                      # 降级:无证据契约则 CLAIM_STRENGTH_DRIFT 跳过并标注
    _evc = None
    HAVE_EVIDENCE = False
try:
    from _shared import semantic_sim as _sem
    HAVE_SEMSIM = True
except Exception:                      # 降级:无语义契约则 CONTRIBUTION_DRIFT 回退裸 Jaccard
    _sem = None
    HAVE_SEMSIM = False
# findings 契约:把内部 dict findings 接成 light.findings.v1,被总控 run_checkpoint 聚合。
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport
    from _shared.gate_runner import run_gates
    HAVE_FINDINGS = True
except Exception:                      # 降级:无 findings 契约则只能出内部报告,不能产机读门
    HAVE_FINDINGS = False

NUM_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)")

# 数值比对的相对偏差分带(X-2)：
#   reldiff <= SCOPE_REL          -> 视为该指标取值，进入按 decimals 的精确比对
#   SCOPE_REL < reldiff <= GROSS_REL -> 疑似严重错填，单列 GROSS_MISMATCH 告警(不再静默丢弃)
#   reldiff > GROSS_REL           -> 数量级无关(年份/计数等)，丢弃
SCOPE_REL = 0.30
GROSS_REL = 3.0

# 创新点漂移检测阈值(X-5)：
#   coverage(材料行覆盖 canonical 关键 token 的比例) >= ADDR_MIN -> 认定该材料在表述此贡献
#   该行与 canonical 的 Jaccard < DRIFT_SIM            -> 提法偏离，报 CONTRIBUTION_DRIFT
ADDR_MIN = 0.25
DRIFT_SIM = 0.55


def _forbidden_literals(forbidden):
    """规范化 forbidden 列表(X-1)：

    字符串 = 需实际匹配的禁用写法；
    映射 {text:..., placeholder: true} = 说明性占位(如"本文方法"在正式名出现后仍这么写)，
        语义需人工判断、不能 literal 匹配，故由 schema 显式标记跳过——
        取代旧的 bad.startswith("本文方法") 字符串 hack，使其余 forbidden 项真正生效。
    返回需实际匹配的禁用写法字符串列表。
    """
    out = []
    for item in forbidden or []:
        if isinstance(item, dict):
            if item.get("placeholder"):
                continue
            txt = item.get("text")
            if txt:
                out.append(txt)
        elif isinstance(item, str) and item.strip():
            out.append(item)
    return out


def _normalize_value(num, auth, unit):
    """单位归一化(X-2)：% 指标的分数写法(0-1)与百分数(0-100)互转，使 0.876 与 87.6 可比。

    仅对 unit=='%' 生效：权威值为百分数而抽取值像分数则放大 100 倍，反之缩小。
    其它单位(ms/M/无)原样返回。
    """
    if unit == "%" and auth:
        if 0 < num <= 1.0 and abs(auth) > 1.0:
            return num * 100.0
        if 0 < abs(auth) <= 1.0 and num > 1.0:
            return num / 100.0
    return num


_SOURCE_FILES = (
    "glossary.yaml", "method_lock.yaml", "metric_registry.yaml", "claims_registry.yaml")


def _confirmed_provenance(value):
    """canonical 事实必须能回到已确认的 source + locator；占位符不算覆盖。"""
    if not isinstance(value, dict):
        return False
    source = str(value.get("source") or "").strip()
    locator = str(value.get("locator") or "").strip()
    status = str(value.get("status") or "").strip().lower()
    placeholder = (not source or not locator or "<" in source or "<" in locator
                   or "示例事实源" in source or "需替换" in locator)
    return not placeholder and status == "confirmed"


def _source_provenance_gaps(docs):
    """返回缺已确认 provenance 的 canonical/record 条目（只诊断，不修改事实源）。"""
    gaps = []
    glossary = docs.get("glossary.yaml") or {}
    for item in glossary.get("terms", []):
        if not _confirmed_provenance(item.get("provenance")):
            gaps.append(f"glossary.term:{item.get('id') or item.get('canonical')}")
    for item in glossary.get("contributions", []):
        if not _confirmed_provenance(item.get("provenance")):
            gaps.append(f"glossary.contribution:{item.get('id') or item.get('canonical')}")

    methods = docs.get("method_lock.yaml") or {}
    for item in methods.get("methods", []):
        if not _confirmed_provenance(item.get("provenance")):
            gaps.append(f"method:{item.get('id') or item.get('canonical')}")

    metrics = docs.get("metric_registry.yaml") or {}
    for item in metrics.get("metrics", []):
        if not _confirmed_provenance(item.get("provenance")):
            gaps.append(f"metric:{item.get('id') or item.get('canonical')}")
        for idx, record in enumerate(item.get("records", []), 1):
            if not _confirmed_provenance(record.get("provenance")):
                gaps.append(
                    f"metric-record:{item.get('id') or item.get('canonical')}#{idx}")

    claims = docs.get("claims_registry.yaml") or {}
    for item in claims.get("claims", []):
        if not _confirmed_provenance(item.get("provenance")):
            gaps.append(f"claim:{item.get('claim_id') or item.get('text')}")
    return gaps


def load_source(db_dir):
    """加载 .light/ 四份 schema；缺文件不伪装全覆盖，由 AUTHORITY_COVERAGE 显式报告。"""
    docs = {}

    def _load(name):
        p = os.path.join(db_dir, name)
        if not os.path.exists(p):
            docs[name] = {}
            return {}
        with open(p, encoding="utf-8") as f:
            docs[name] = yaml.safe_load(f) or {}
            return docs[name]
    glossary = _load("glossary.yaml")
    methods = _load("method_lock.yaml")
    metrics = _load("metric_registry.yaml")
    claims = _load("claims_registry.yaml")
    present = [name for name in _SOURCE_FILES
               if os.path.exists(os.path.join(db_dir, name))]
    missing = [name for name in _SOURCE_FILES if name not in present]
    missing_headers = []
    for name in present:
        authority = (docs.get(name) or {}).get("authority")
        if not isinstance(authority, dict) or not authority.get("owner") or not authority.get("updated_at"):
            missing_headers.append(name)
    return {
        "glossary": glossary.get("terms", []),
        "methods": methods.get("methods", []),
        "metrics": metrics.get("metrics", []),
        "contributions": glossary.get("contributions", []),
        "claims": claims.get("claims", []),
        "_source_meta": {
            "mode": "yaml",
            "path": os.path.abspath(db_dir),
            "present_files": present,
            "missing_files": missing,
            "missing_authority_headers": missing_headers,
            "provenance_gaps": _source_provenance_gaps(docs),
        },
    }


def load_source_markdown(path):
    """解析真实 .light/ 项目的 terminology.md(Markdown 表)为 source 结构。

    .light/ 项目按 light-memory-pm 约定把受控术语存为 Markdown 表:
        | 类别 | 标准叫法 | 缩写 | 英文 | 备注 |
    本加载器把 方法/数据集→methods+glossary，指标→metrics+glossary，其余→glossary。
    诚实限制:Markdown 表无 forbidden/confusable/权威数值列，故只支撑
    COVERAGE_GAP(覆盖缺口)检测;SUBSTITUTION/METRIC_VALUE 需 YAML schema 才完整。
    """
    glossary, methods, metrics = [], [], []
    contributions = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    n = 0
    for ln in lines:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        cat, canon = cells[0], cells[1]
        if cat in ("类别", "") or set(canon) <= {"-", "—", " "} or canon == "标准叫法":
            continue  # 表头 / 分隔行 / 空
        if cat.startswith("创新点"):  # X-5：创新点行作贡献单一事实源(只读)
            if canon:
                contributions.append({"id": cat, "canonical": canon})
            continue
        abbr = cells[2].strip() if len(cells) > 2 else ""
        en = cells[3].strip() if len(cells) > 3 else ""
        aliases = [a for a in (abbr, en) if a and set(a) > {"-", "—"}]
        n += 1
        item = {"id": f"md.{n}", "canonical": canon, "aliases": aliases,
                "forbidden": [], "case_lock": False, "zh": canon, "en": en}
        glossary.append(item)
        if cat == "指标":
            metrics.append({"id": f"md.metric.{n}", "canonical": canon,
                            "aliases": aliases, "confusable": [], "unit": "",
                            "decimals": 1, "records": []})
        elif cat in ("方法", "数据集"):
            methods.append({"id": f"md.method.{n}", "canonical": canon, "forbidden": []})
    return {"glossary": glossary, "methods": methods, "metrics": metrics,
            "contributions": contributions, "claims": [],
            "_source_meta": {
                "mode": "markdown",
                "path": os.path.abspath(path),
                "present_files": [os.path.basename(path)],
                "missing_files": list(_SOURCE_FILES),
                "missing_authority_headers": [],
                "provenance_gaps": [],
            }}


def load_source_auto(path):
    """.light/ 来源自适应:目录含三份 yaml 走 schema 模式;否则找 terminology.md 走 Markdown 模式。"""
    if os.path.isfile(path) and path.endswith(".md"):
        return load_source_markdown(path)
    if os.path.isdir(path):
        if os.path.exists(os.path.join(path, "glossary.yaml")):
            return load_source(path)
        term = os.path.join(path, "terminology.md")
        if os.path.exists(term):
            return load_source_markdown(term)
    raise FileNotFoundError(
        f".light/ 事实源无法识别:{path}(需含 glossary.yaml 等 schema 的目录,或 terminology.md)")


def read_material(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    return {"name": os.path.basename(path), "lines": lines,
            "code_flags": _code_block_flags(lines)}


def _code_block_flags(lines):
    """标出每行是否处于 ```/~~~ 围栏代码块内(scope-aware,对标 Vale scope=text)。
    返回与 lines 等长的 bool 列表:True=代码块内,SUBSTITUTION/VARIANT 等文本类检测跳过。"""
    flags, in_block = [], False
    fence = re.compile(r"^\s*(```|~~~)")
    for ln in lines:
        if fence.match(ln):
            flags.append(True)        # 围栏行本身也算块内(不在正文)
            in_block = not in_block
            continue
        flags.append(in_block)
    return flags


def _strip_inline_code(line):
    """挖空 `行内代码` 跨度为等长空格(保留列坐标),使行内 code 里的 finetune 不误命中。"""
    return re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)


def _finding(kind, severity, material, line_no, line_text, detail, suggestion):
    return {
        "kind": kind, "severity": severity,
        "location": f"{material}:{line_no}",
        "line": line_text.strip(),
        "detail": detail, "suggestion": suggestion,
    }


def _word_present(text, token, case_lock):
    """词在文本中是否出现。含中文则按子串匹配；纯 ASCII 用词边界，避免 'AP' 命中 'mAP'。"""
    if re.search(r"[^\x00-\x7f]", token):
        hay = text if case_lock else text.lower()
        ndl = token if case_lock else token.lower()
        return ndl in hay
    flags = 0 if case_lock else re.IGNORECASE
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])", text, flags) is not None


# ---------------------------------------------------------------------------
# 检测 1：受控术语 / 方法名 的禁用写法 (SUBSTITUTION)
# ---------------------------------------------------------------------------
def audit_substitution(materials, source):
    findings = []
    entries = []
    for t in source["glossary"]:
        entries.append(("term", t.get("canonical"), _forbidden_literals(t.get("forbidden", [])), t.get("case_lock", False)))
    for m in source["methods"]:
        entries.append(("method", m.get("canonical"), _forbidden_literals(m.get("forbidden", [])), True))
    for mat in materials:
        flags = mat.get("code_flags") or [False] * len(mat["lines"])
        for i, line in enumerate(mat["lines"], 1):
            if flags[i - 1]:
                continue                       # scope-aware: 代码块内不查正文术语
            scan = _strip_inline_code(line)    # 行内 `code` 挖空
            for kind, canon, forbidden, case_lock in entries:
                for bad in forbidden:
                    if _word_present(scan, bad, case_lock):
                        findings.append(_finding(
                            "SUBSTITUTION", "error", mat["name"], i, line,
                            f"出现禁用写法 '{bad}'（{kind} 规范名应为 '{canon}'）",
                            f"将 '{bad}' 改为规范写法 '{canon}'"))
    return findings


# ---------------------------------------------------------------------------
# 检测 2：指标换名 (METRIC_NAME) —— 把易混名(confusable)当成该指标在用
# ---------------------------------------------------------------------------
def audit_metric_name(materials, source):
    findings = []
    for mat in materials:
        for i, line in enumerate(mat["lines"], 1):
            for met in source["metrics"]:
                canon = met.get("canonical")
                for conf in met.get("confusable", []):
                    # 仅当该行同时带数字时才疑似"用错名报指标值"，降低误报
                    if _word_present(line, conf, case_lock=False) and NUM_RE.search(line):
                        findings.append(_finding(
                            "METRIC_NAME", "warn", mat["name"], i, line,
                            f"疑似用易混名 '{conf}' 指代指标 '{canon}'（二者语义不同）",
                            f"若确指 '{canon}' 则改名；若确是 '{conf}' 则它未登记，需在 .light/ 术语表注册"))
    return findings


# ---------------------------------------------------------------------------
# 检测 3：指标数值冲突 (METRIC_VALUE)
#   思路：对每个指标的权威 records(method×dataset→value)，在材料中找"同时提到
#   该指标名 + 该方法名"的行，抽取数字，与权威值比对；并跨材料比对同一(指标,方法)
#   出现的不同数值。
# ---------------------------------------------------------------------------
def _extract_numbers(line):
    return [float(x) for x in NUM_RE.findall(line)]


def _positions(line, token, case_lock):
    """返回 token 在行内所有出现的起始下标(词边界规则同 _word_present)。"""
    if re.search(r"[^\x00-\x7f]", token):
        hay = line if case_lock else line.lower()
        ndl = token if case_lock else token.lower()
        return [m.start() for m in re.finditer(re.escape(ndl), hay)]
    flags = 0 if case_lock else re.IGNORECASE
    pat = r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])"
    return [m.start() for m in re.finditer(pat, line, flags)]


def audit_metric_value(materials, source):
    """位置感知：一行内可并列多指标/多方法，按"就近"把每个数字配给
    最近的指标名与最近的方法名，避免 F1 与 mAP 的数字互相串位。"""
    findings = []
    observed = {}  # (mid, canon, method, dec, auth) -> [(value, material, line_no, line)]
    metrics = []
    for met in source["metrics"]:
        metrics.append({
            "mid": met["id"], "canon": met["canonical"],
            "names": [met["canonical"]] + met.get("aliases", []),
            "dec": met.get("decimals", 1),
            "unit": met.get("unit", ""),
            "rec": {r["method"]: r["value"] for r in met.get("records", [])},
        })
    all_methods = sorted({m for met in metrics for m in met["rec"]}, key=len, reverse=True)

    for mat in materials:
        for i, line in enumerate(mat["lines"], 1):
            # 1) 收集本行所有"指标名出现位置" -> (pos, metric)
            mpos = []
            for met in metrics:
                for n in met["names"]:
                    for p in _positions(line, n, case_lock=False):
                        mpos.append((p, p + len(n), met))
            if not mpos:
                continue
            # 2) 收集方法名位置
            methpos = [(p, mname) for mname in all_methods
                       for p in _positions(line, mname, case_lock=True)]
            if not methpos:
                continue
            # 3) 把"命名实体"片段从行内挖空再取数字：避免实体内嵌数字被误读为指标值
            #    (mAP@0.5 的 0.5、YOLOv8 的 8、CrowdScene-2k 的 2)。
            #    挖空范围 = 指标名 + 方法名 + 受控术语/数据集名(含别名)，但保留位置坐标。
            mask_spans = [(s, e) for s, e, _ in mpos]
            mask_spans += [(p, p + len(mn)) for p, mn in methpos]
            for term in source.get("glossary", []):
                for nm in [term.get("canonical")] + term.get("aliases", []):
                    if nm and re.search(r"\d", nm):  # 仅含数字的实体才需挖空
                        for p in _positions(line, nm, term.get("case_lock", False)):
                            mask_spans.append((p, p + len(nm)))
            masked = list(line)
            for s, e in mask_spans:
                for k in range(s, e):
                    masked[k] = " "
            masked = "".join(masked)
            for m in NUM_RE.finditer(masked):
                num, npos = float(m.group(1)), m.start()
                # 数字归属：最近(优先在其左侧)的指标名
                met = min(mpos, key=lambda mp: (npos < mp[0], abs(npos - mp[0])))[2]
                # 方法归属：优先取数字左侧最近的方法名(主语通常在指标/数值之前；
                # 句尾的"优于基线 YOLOv8"虽文本更近，但不是该数值的归属方)。
                left = [mp for mp in methpos if mp[0] <= npos]
                cand = left if left else methpos
                owner = min(cand, key=lambda mp: abs(npos - mp[0]))[1]
                auth = met["rec"].get(owner)
                if auth is None:
                    continue  # 该方法无此指标记录，与本数字无关
                # 单位归一化(X-2)：% 指标的分数/百分数互转，使 0.876 与 87.6 可比
                num_n = _normalize_value(num, auth, met["unit"])
                reldiff = abs(num_n - auth) / abs(auth) if auth else 0.0
                if reldiff > GROSS_REL:
                    continue  # 数量级无关(年份/计数等)，丢弃
                if reldiff > SCOPE_REL:
                    # 中间带：疑似严重错填，单列 GROSS_MISMATCH(不再静默丢弃)
                    findings.append(_finding(
                        "GROSS_MISMATCH", "error", mat["name"], i, line,
                        f"{owner} 的 {met['canon']} 标为 {num:g}，与 .light/ 权威值 "
                        f"{auth:g} 相差 {reldiff*100:.0f}%(疑严重错填或张冠李戴)",
                        f"核对该数值是否填错指标/方法；确属 {met['canon']} 则订正为 {auth:g}"))
                    continue
                observed.setdefault(
                    (met["mid"], met["canon"], owner, met["dec"], auth), []
                ).append((num_n, mat["name"], i, line))
    return findings, observed


def evaluate_value_conflicts(observed):
    """对每个(指标,方法)：标记与权威值不符、以及跨材料互相矛盾的数值。"""
    findings = []
    for (mid, canon, method, dec, auth), obs in observed.items():
        seen_vals = {}
        for claimed, mat, ln, line in obs:
            seen_vals.setdefault(round(claimed, dec), []).append((mat, ln, line))
            if abs(claimed - auth) > (0.5 * 10 ** (-dec)):  # 超出约定精度的容差即冲突
                findings.append(_finding(
                    "METRIC_VALUE", "error", mat, ln, line,
                    f"{method} 的 {canon} 标为 {claimed:.{dec}f}，与 .light/ 权威值 {auth:.{dec}f} 不符",
                    f"核对实验记录后统一为权威值 {auth:.{dec}f}，并更新 .light/ 或材料"))
        if len(seen_vals) > 1:  # 跨材料出现多个不同数值
            spread = ", ".join(f"{v}@{loc[0][0]}" for v, loc in seen_vals.items())
            first = obs[0]
            findings.append(_finding(
                "METRIC_VALUE", "error", first[1], first[2], first[3],
                f"{method} 的 {canon} 在不同材料数值不一致：{spread}",
                f"以 .light/ 权威值 {auth:.{dec}f} 为准，逐处统一"))
    return findings


# ---------------------------------------------------------------------------
# 检测 4：覆盖缺口 (COVERAGE_GAP) —— 规范术语/指标只在部分材料出现
# ---------------------------------------------------------------------------
def audit_coverage(materials, source):
    findings = []
    # must_cover(贡献级)术语/指标缺席报 WARN；普通术语缺席降 INFO(X-4 降噪)
    targets = [("术语", t["canonical"], t.get("aliases", []), t.get("case_lock", False),
                bool(t.get("must_cover", False)))
               for t in source["glossary"]]
    targets += [("指标", m["canonical"], m.get("aliases", []), False,
                 bool(m.get("must_cover", False)))
                for m in source["metrics"]]
    mat_names = [m["name"] for m in materials]
    for kind, canon, aliases, cl, must in targets:
        present = []
        for mat in materials:
            text = "\n".join(mat["lines"])
            if any(_word_present(text, n, cl) for n in [canon] + aliases):
                present.append(mat["name"])
        if present and len(present) < len(mat_names):
            missing = [n for n in mat_names if n not in present]
            sev = "warn" if must else "info"
            tier = "贡献级(must_cover)" if must else "一般术语"
            findings.append(_finding(
                "COVERAGE_GAP", sev, missing[0], 0, "",
                f"{tier}{kind} '{canon}' 出现在 {present}，但在 {missing} 缺席",
                f"确认 {missing} 是否应包含 '{canon}'；若应包含则补齐措辞"))
    return findings


# ---------------------------------------------------------------------------
# 检测 5：创新点/贡献提法漂移 (CONTRIBUTION_DRIFT) —— X-5
#   背景：.light/ terminology.md 已有"创新点1/2/3"行(只读，由 memory-pm 维护)，是 3 条贡献的
#   单一事实源。SKILL 反复承诺"创新点跨论文/PPT/软著一字对齐"却零脚本实现——本检测补缺。
#   做法：对每条创新点 canonical，抽关键 token；在每份材料里找"覆盖足够 token 的行"
#   (认定该材料在表述此贡献)，再用句级 Jaccard 相似度判断提法是否偏离 canonical。
# ---------------------------------------------------------------------------
# 中文停用词 + 标点，降低 token 噪声
_STOP = set("的了与和及对在为是用做以并把被让使其之于而且或等这那一二三四五六"
            "七八九十个项条点级与都也很更最就还把对从向到上下里中外前后左右")
_TOKEN_SPLIT = re.compile(r"[\s，。、；：（）()【】\[\]\"“”‘’,.;:!?！？/\\|—\-_+=<>]+")


def _tokens(text):
    """中英混合分词:ASCII 词整体保留(小写)，中文按二元/一元切，去停用词与短噪声。"""
    toks = set()
    for seg in _TOKEN_SPLIT.split(text):
        if not seg:
            continue
        if re.fullmatch(r"[\x00-\x7f]+", seg):  # 纯 ASCII 词
            s = seg.lower()
            if len(s) >= 2 and s not in _STOP:
                toks.add(s)
            continue
        # 含中文:逐字 + 相邻二元(二元更能锁定术语，如"级联""传播")
        chars = [c for c in seg if c.strip()]
        for c in chars:
            if c not in _STOP and not re.match(r"[\x00-\x7f]", c):
                toks.add(c)
        for a, b in zip(chars, chars[1:]):
            bg = a + b
            if a not in _STOP and b not in _STOP:
                toks.add(bg)
    return toks


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni else 0.0


def _sentence_sim(a, b):
    """句级相似度:挂接 _shared/semantic_sim(词序无关、识别倒装、中文按字)。
    缺失契约时诚实降级回裸 token-Jaccard 并由调用方标注。"""
    if HAVE_SEMSIM:
        return _sem.similarity(a, b, mode="offline")
    return _jaccard(_tokens(a), _tokens(b))


def audit_contribution(materials, source):
    """创新点提法漂移检测。source["contributions"] = [{id, canonical}]。

    每条贡献:
      - 抽 canonical 关键 token,对每份材料逐行算覆盖率,取覆盖率最高行为"代表句";
      - 覆盖率 >= ADDR_MIN 视为该材料在表述此贡献;
      - 代表句与 canonical 的【句级相似度】< DRIFT_SIM -> 提法偏离,报 CONTRIBUTION_DRIFT。

    相似度挂接 _shared/semantic_sim(替旧裸 Jaccard):词序无关、能识别倒装,
    不再把"同词不同序"误判为一致——这是审查指出的"一字对齐"措辞夸大的真实兑现。
    """
    findings = []
    contribs = source.get("contributions", [])
    sim_note = "" if HAVE_SEMSIM else "(semantic_sim 缺失,已降级裸 Jaccard)"
    for c in contribs:
        canon = c.get("canonical", "")
        ctoks = _tokens(canon)
        if not ctoks:
            continue
        for mat in materials:
            best = (0.0, 0, "", 0.0)  # (coverage, line_no, line, sim)
            for i, line in enumerate(mat["lines"], 1):
                ltoks = _tokens(line)
                if not ltoks:
                    continue
                cover = len(ltoks & ctoks) / len(ctoks)
                if cover > best[0]:
                    best = (cover, i, line, _sentence_sim(line, canon))
            cover, ln, line, sim = best
            if cover >= ADDR_MIN and sim < DRIFT_SIM:
                findings.append(_finding(
                    "CONTRIBUTION_DRIFT", "warn", mat["name"], ln, line,
                    f"贡献 '{c.get('id', '?')}' 在此处提法偏离 .light/ 标准措辞"
                    f"(覆盖 {cover*100:.0f}% / 语义相似 {sim*100:.0f}%{sim_note})：标准为「{canon}」",
                    f"按 .light/ 创新点统一措辞改写，使 {mat['name']} 与论文/软著对齐"))
    return findings


# ---------------------------------------------------------------------------
# 检测 6：主张措辞强于证据 (CLAIM_STRENGTH_DRIFT) —— top_idea #1,跨技能反哺 result-analysis→ethics→writing
#   挂接 _shared/evidence_contract(light.evidence_strength.v1):
#   result-analysis 为每条主张标证据档(strong/moderate/weak/none),本检测扫所有材料,
#   若某主张所在行用了"高于其证据档"的措辞(weak 证据却写 demonstrate/significantly/
#   显著/SOTA),报 ERROR。这是裸模型与 Vale/Acrolinx/Xbench 都没有的科研专属维度。
# ---------------------------------------------------------------------------
def _claim_keywords_hit(line, keywords):
    """该行是否在表述某主张:命中 >=2 个关键词,或命中 >=1 且其中含主方法/指标名。"""
    low = line.lower()
    hits = 0
    for kw in keywords or []:
        k = kw.lower()
        if re.search(r"[^\x00-\x7f]", kw):       # 中文子串
            if k in low:
                hits += 1
        elif re.search(r"(?<![A-Za-z0-9_])" + re.escape(k) + r"(?![A-Za-z0-9_])", low):
            hits += 1
    return hits >= 2


# 中文强断言短语(英文动词表无法覆盖中文材料,显式列;按证据档收紧)
_ZH_STRONG = ["显著", "大幅", "证明", "确立", "达到 sota", "达到sota", "最优", "首次实现", "完全超越"]


def audit_claim_strength(materials, source):
    findings = []
    claims = source.get("claims", [])
    if not claims:
        return findings
    if not HAVE_EVIDENCE:
        # 诚实降级:契约缺失则只用本地中文短语表兜底(英文动词档无法机械映射)
        for mat in materials:
            flags = mat.get("code_flags") or [False] * len(mat["lines"])
            for i, line in enumerate(mat["lines"], 1):
                if flags[i - 1]:
                    continue
                for c in claims:
                    if c.get("evidence_grade") in ("weak", "none") and _claim_keywords_hit(line, c.get("keywords")):
                        for ph in c.get("forbidden_zh", []):
                            if ph and ph in line:
                                findings.append(_finding(
                                    "CLAIM_STRENGTH_DRIFT", "error", mat["name"], i, line,
                                    f"主张 '{c.get('claim_id')}' 证据档为 '{c.get('evidence_grade')}',"
                                    f"却用强措辞 '{ph}'(evidence_contract 缺失,仅中文短语兜底)",
                                    f"降级措辞:{c.get('evidence_grade')} 档应 hedge(可能/初步),勿用 '{ph}'"))
        return findings
    # 正常路径:用 evidence_contract 的 grade→措辞档做机械映射
    for mat in materials:
        flags = mat.get("code_flags") or [False] * len(mat["lines"])
        for i, line in enumerate(mat["lines"], 1):
            if flags[i - 1]:
                continue
            for c in claims:
                if not _claim_keywords_hit(line, c.get("keywords")):
                    continue
                grade = c.get("evidence_grade") or _evc.grade_evidence(
                    c.get("q_fdr"), c.get("effect_size"), c.get("ci95"), c.get("n"))
                # 英文措辞:走契约 lint_wording(动词档机械映射)
                for v in _evc.lint_wording(line, {"evidence_grade": grade}):
                    if v.get("matched") is None:
                        continue              # whole-line hedge 缺失对单行材料噪声大,跳过
                    findings.append(_finding(
                        "CLAIM_STRENGTH_DRIFT", "error", mat["name"], i, line,
                        f"主张 '{c.get('claim_id')}' 证据档 '{grade}',措辞 '{v['matched']}' 超档"
                        f"({v['issue']})",
                        v["suggestion"]))
                # 中文措辞:契约动词表覆盖不到,用 registry 的 forbidden_zh 补
                if grade in ("weak", "none"):
                    for ph in c.get("forbidden_zh", []):
                        if ph and ph in line:
                            findings.append(_finding(
                                "CLAIM_STRENGTH_DRIFT", "error", mat["name"], i, line,
                                f"主张 '{c.get('claim_id')}' 证据档 '{grade}',却用强措辞 '{ph}'",
                                f"{grade} 档须 hedge(可能/初步/有待验证),勿用 '{ph}'"))
    return findings


# ---------------------------------------------------------------------------
# 检测 7：共存即冲突 (VARIANT_CONFLICT) —— missing_mechanism(Vale/Xbench 有)
#   无需预写 forbidden 表:对每个 canonical,在材料里自动发现"仅大小写/连字符/空格
#   不同"的变体写法。若变体与 canonical 同时出现且未登记为 alias,即报不一致。
#   解决审查指出的"完全依赖人工把禁用写法穷举进 .light/ 术语表,漏写即漏检"。
# ---------------------------------------------------------------------------
def _variant_key(s):
    """归一键:小写 + 去连字符/空格/下划线。'DCA-Net'/'DCA Net'/'dcanet' → 同键。"""
    return re.sub(r"[-_\s]", "", s.lower())


def audit_variant_conflict(materials, source):
    findings = []
    # 登记的"精确写法"(canonical + aliases/abbr/full)不算冲突;forbidden 由 SUBSTITUTION
    # 负责,此处排除以聚焦"未预写、自动发现"的近形变体(VARIANT_CONFLICT 的存在意义)。
    entries = []
    for t in source.get("glossary", []):
        canon = t.get("canonical")
        if canon:
            surfaces = set([canon] + list(t.get("aliases", [])))
            forb = set(_forbidden_literals(t.get("forbidden", [])))
            entries.append((canon, surfaces, forb))
    for m in source.get("methods", []):
        canon = m.get("canonical")
        if canon:
            surfaces = set(x for x in [canon, m.get("abbr"), m.get("full")] if x)
            forb = set(_forbidden_literals(m.get("forbidden", [])))
            entries.append((canon, surfaces, forb))
    ckey = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_ ]*[A-Za-z0-9]|[A-Za-z0-9]")
    for canon, surfaces, forb in entries:
        target = _variant_key(canon)
        variants = {}  # surface -> (material, line_no, line)
        for mat in materials:
            flags = mat.get("code_flags") or [False] * len(mat["lines"])
            for i, line in enumerate(mat["lines"], 1):
                if flags[i - 1]:
                    continue
                scan = _strip_inline_code(line)
                for mt in ckey.finditer(scan):
                    surf = mt.group(0).strip()
                    if not surf or _variant_key(surf) != target:
                        continue
                    if surf in surfaces:
                        continue            # 精确命中登记写法
                    if surf in forb or any(surf == fb for fb in forb):
                        continue            # 已在 forbidden,归 SUBSTITUTION 报
                    if surf not in variants:
                        variants[surf] = (mat["name"], i, line)
        # 只有当确实出现"非登记的近形变体"才报(共存即冲突)
        for surf, (mn, ln, line) in variants.items():
            findings.append(_finding(
                "VARIANT_CONFLICT", "warn", mn, ln, line,
                f"出现 '{canon}' 的未登记近形变体 '{surf}'(仅大小写/连字符/空格不同),共存即不一致",
                f"统一为规范写法 '{canon}',或把 '{surf}' 登记为 alias/forbidden"))
    return findings


# ---------------------------------------------------------------------------
# 检测 8：缩写首次全称规则 (ABBREV_FIRST_USE) —— missing_mechanism + 兑现 first_use_rule
#   method_lock 写了 first_use_rule 字段但旧脚本根本没消费。学术惯例:缩写首次出现
#   应写"全称(缩写)",此后用缩写。本检测对每份材料逐一核查每个含 full≠abbr 的方法。
# ---------------------------------------------------------------------------
def audit_abbrev_first_use(materials, source):
    findings = []
    methods = [m for m in source.get("methods", [])
               if m.get("abbr") and m.get("full") and m["abbr"] != m["full"]
               and m["abbr"] != m.get("canonical")]   # canonical 本身即缩写(方法名)的不查
    for m in methods:
        abbr, full = m["abbr"], m["full"]
        for mat in materials:
            flags = mat.get("code_flags") or [False] * len(mat["lines"])
            first_abbr = None      # (line_no, line)
            full_before = False
            paren_ok = False
            for i, line in enumerate(mat["lines"], 1):
                if flags[i - 1]:
                    continue
                scan = _strip_inline_code(line)
                has_full = _word_present(scan, full, case_lock=False)
                has_abbr = _word_present(scan, abbr, case_lock=True)
                if has_full:
                    full_before = True
                    # 同行 "全称(缩写)" 形式即合规首次定义
                    if re.search(re.escape(full) + r"\s*[（(]\s*" + re.escape(abbr) + r"\s*[）)]", scan):
                        paren_ok = True
                if has_abbr and first_abbr is None:
                    first_abbr = (i, line)
                    break
            if first_abbr and not full_before and not paren_ok:
                # 缩写先于任何全称定义出现 → 违反 first_use_rule
                ln, line = first_abbr
                findings.append(_finding(
                    "ABBREV_FIRST_USE", "warn", mat["name"], ln, line,
                    f"缩写 '{abbr}' 首次出现前未给全称定义(规则:{m.get('first_use_rule', '首次写全称(缩写)')})",
                    f"首次改为 '{full}（{abbr}）',此后再用 '{abbr}'"))
    return findings


# ---------------------------------------------------------------------------
# 检测 9：B-fact 快照新鲜度 (STALE_SNAPSHOT) —— top_idea #2,补 SKILL 维度⑦功能名不副实
#   解析材料/卡内 [snapshot date=YYYY-MM-DD ... src=...] 三件套,按 kind 阈值算超期:
#     metric(计量) > 90 天 / license(许可) > 365 天 / doi 永不过期。
#   旧 SKILL 白纸黑字说"consistency_audit.py 可顺带标记"却零实现——本检测兑现。
# ---------------------------------------------------------------------------
_SNAP_RE = re.compile(
    r"\[snapshot\s+date=(\d{4}-\d{2}-\d{2})(?:\s+kind=([a-zA-Z]+))?[^\]]*?src=([^\]]+)\]")
_STALE_DAYS = {"metric": 90, "license": 365, "doi": None, "default": 180}


def _infer_kind(src, kind):
    if kind:
        return kind.lower()
    s = src.lower()
    if "doi" in s or "10." in s:
        return "doi"
    if "license" in s or "许可" in s or "ccby" in s or "cc-by" in s:
        return "license"
    if any(w in s for w in ("if", "影响因子", "citescore", "计量", "metric", "jcr")):
        return "metric"
    return "default"


def audit_snapshot_freshness(materials, source, today=None):
    findings = []
    if today is None:
        today = datetime.date.today()
    elif isinstance(today, str):
        today = datetime.date.fromisoformat(today)
    for mat in materials:
        for i, line in enumerate(mat["lines"], 1):
            for mt in _SNAP_RE.finditer(line):
                date_s, kind_s, src = mt.group(1), mt.group(2), mt.group(3).strip()
                try:
                    snap = datetime.date.fromisoformat(date_s)
                except ValueError:
                    continue
                kind = _infer_kind(src, kind_s)
                limit = _STALE_DAYS.get(kind, _STALE_DAYS["default"])
                if limit is None:
                    continue              # doi 等不过期
                age = (today - snap).days
                if age > limit:
                    findings.append(_finding(
                        "STALE_SNAPSHOT", "warn", mat["name"], i, line,
                        f"快照 [{kind}] 取于 {date_s},距今 {age} 天 > 阈值 {limit} 天(src={src})",
                        f"重新核对 {src} 并更新 [snapshot date=…] 为最新值"))
    return findings


def audit_authority_coverage(source):
    """事实源覆盖诊断（warn-only）：缺 schema/provenance ≠ 已一致。"""
    meta = source.get("_source_meta") or {}
    if not meta:
        return []
    findings = []
    loc = meta.get("path") or ".light/consistency"
    mode = meta.get("mode")
    if mode == "markdown":
        findings.append(_finding(
            "AUTHORITY_COVERAGE", "warn", loc, 0, "",
            "当前事实源为 Markdown 覆盖档：可做术语/贡献覆盖与近形变体检查，"
            "但没有 forbidden/confusable、指标权威 records、claim 证据档，"
            "不能据此宣称数值与主张已核",
            "由 memory-pm 在人工确认后建立 .light/consistency 四份 YAML；"
            "未建立前保留“部分覆盖”结论"))
        return findings

    missing = meta.get("missing_files") or []
    if missing:
        findings.append(_finding(
            "AUTHORITY_COVERAGE", "warn", loc, 0, "",
            f"YAML 事实源缺 {missing}；对应检测面未覆盖，不等于已一致",
            "由 memory-pm 补齐缺失 registry，或明确记录该检查面不适用及理由"))
    missing_headers = meta.get("missing_authority_headers") or []
    if missing_headers:
        findings.append(_finding(
            "AUTHORITY_COVERAGE", "warn", loc, 0, "",
            f"{missing_headers} 缺 authority.owner / authority.updated_at，"
            "无法确认维护责任人与更新时间",
            "由 memory-pm 补 owner 与绝对日期；consistency 只报告，不代写"))
    gaps = meta.get("provenance_gaps") or []
    if gaps:
        sample = ", ".join(gaps[:6]) + (" …" if len(gaps) > 6 else "")
        findings.append(_finding(
            "AUTHORITY_COVERAGE", "warn", loc, 0, "",
            f"{len(gaps)} 个 canonical/record/claim 缺 status=confirmed 的 source+locator"
            f"（样例：{sample}）；这些值可参与扫描，但权威链尚不完整",
            "回到原论文/实验表/协议定位，人工确认后由 memory-pm 写入 provenance；"
            "harvest 候选不得直接升 canonical"))
    return findings


def run_audit(materials, source, today=None):
    # 补 code_flags(scope-aware):合成材料/外部构造的 dict 可能没带,这里兜底计算
    for mat in materials:
        if "code_flags" not in mat:
            mat["code_flags"] = _code_block_flags(mat["lines"])
    findings = []
    findings += audit_substitution(materials, source)
    findings += audit_variant_conflict(materials, source)        # VARIANT_CONFLICT(共存即冲突)
    findings += audit_metric_name(materials, source)
    gross, observed = audit_metric_value(materials, source)
    findings += gross  # GROSS_MISMATCH(X-2)：超阈值单列告警，不再静默丢弃
    findings += evaluate_value_conflicts(observed)
    findings += audit_coverage(materials, source)
    findings += audit_contribution(materials, source)  # CONTRIBUTION_DRIFT(X-5,挂 semantic_sim)
    findings += audit_claim_strength(materials, source)          # CLAIM_STRENGTH_DRIFT(挂 evidence_contract)
    findings += audit_abbrev_first_use(materials, source)        # ABBREV_FIRST_USE(兑现 first_use_rule)
    findings += audit_snapshot_freshness(materials, source, today)  # STALE_SNAPSHOT(维度⑦兑现)
    findings += audit_authority_coverage(source)                 # AUTHORITY_COVERAGE(warn-only,不伪装覆盖)
    # 去重：同一(类型,位置,问题)只保留一条(如 DCANet 同时命中术语表与方法锁)。
    seen, deduped = set(), []
    for f in findings:
        key = (f["kind"], f["location"], f.get("suggestion"), f["detail"]
               if f["kind"] != "SUBSTITUTION" else f.get("suggestion"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    findings = deduped
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["kind"], f["location"]))
    return findings


def render_report(findings, materials):
    out = []
    out.append("=" * 64)
    out.append("跨材料一致性审计报告 (light-consistency)")
    out.append(f"材料数：{len(materials)}　发现总数：{len(findings)}")
    out.append("=" * 64)
    by_kind = {}
    for f in findings:
        by_kind.setdefault(f["kind"], []).append(f)
    labels = {"SUBSTITUTION": "受控术语/方法名替换", "VARIANT_CONFLICT": "共存即冲突(近形变体)",
              "METRIC_NAME": "指标换名", "METRIC_VALUE": "指标数值冲突",
              "GROSS_MISMATCH": "指标数值严重偏离", "COVERAGE_GAP": "覆盖缺口",
              "CONTRIBUTION_DRIFT": "创新点提法漂移", "CLAIM_STRENGTH_DRIFT": "措辞强于证据",
              "ABBREV_FIRST_USE": "缩写首次全称规则", "STALE_SNAPSHOT": "快照超期",
              "AUTHORITY_COVERAGE": "权威源覆盖/溯源缺口"}
    n = 0
    for kind in ["SUBSTITUTION", "VARIANT_CONFLICT", "METRIC_NAME", "METRIC_VALUE",
                 "GROSS_MISMATCH", "CLAIM_STRENGTH_DRIFT", "CONTRIBUTION_DRIFT",
                 "ABBREV_FIRST_USE", "STALE_SNAPSHOT", "AUTHORITY_COVERAGE", "COVERAGE_GAP"]:
        items = by_kind.get(kind, [])
        out.append(f"\n## [{kind}] {labels[kind]}　({len(items)} 条)")
        if not items:
            out.append("  （无）")
        for f in items:
            n += 1
            tag = {"error": "ERROR", "warn": "WARN ", "info": "INFO "}.get(f["severity"], "WARN ")
            loc = f["location"] if not f["location"].endswith(":0") else f["location"][:-2] + ":(全篇)"
            out.append(f"  {n:>3}. [{tag}] {loc}")
            out.append(f"       现状：{f['line'] or '(跨材料/全篇)'}")
            out.append(f"       问题：{f['detail']}")
            out.append(f"       建议：{f['suggestion']}")
    out.append("\n" + "=" * 64)
    out.append(f"完整性自检：累计输出 {n} 条 == 发现总数 {len(findings)} -> "
               + ("通过" if n == len(findings) else "不一致(请检查)"))
    out.append("=" * 64)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 接 _shared/findings_schema:内部 dict findings → light.findings.v1(机读门)
#   被总控 run_checkpoint --findings 聚合为【跨阶段一致性门】(orchestrator-spec §4.2 末行)。
#   硬冲突(SUBSTITUTION/METRIC_VALUE/GROSS_MISMATCH/CLAIM_STRENGTH_DRIFT = 内部 error)
#     → gate fail/critical → verdict=fail → run_checkpoint exit 1 确定性阻断;
#   软漂移(VARIANT/METRIC_NAME/CONTRIBUTION_DRIFT/ABBREV/STALE = warn) → warn/major;
#   覆盖缺口(info) → warn/minor(可按 severity 过滤,不阻断)。
# ---------------------------------------------------------------------------
_INTERNAL_TO_GATE = {
    "error": ("fail", "critical"),     # 硬冲突:阻断
    "warn":  ("warn", "major"),        # 软漂移:警示不阻断
    "info":  ("warn", "minor"),        # 覆盖缺口:最低警示
}
_SEV_RANK = {"error": 2, "warn": 1, "info": 0}


def _gate_fns_from_internal(internal):
    """内部 findings 按 kind 分组,每组→一个 gate 闭包(供 run_gates 执行,不重复跑 audit)。
    闭包返回预构造 GateResult(gate 名=kind,status/severity 由该 kind 最严重项定)。"""
    by_kind = {}
    for f in internal:
        by_kind.setdefault(f["kind"], []).append(f)
    fns = []
    for kind in sorted(by_kind):
        items = by_kind[kind]
        worst = max(items, key=lambda x: _SEV_RANK.get(x["severity"], 0))["severity"]
        status, gsev = _INTERNAL_TO_GATE.get(worst, ("warn", "minor"))
        fs = [Finding(loc=(it["location"] or kind), issue=it["detail"],
                      fix=it["suggestion"], evidence=(it["line"] or None),
                      rule=f"consistency.{kind}")
              for it in items]
        n_err = sum(1 for it in items if it["severity"] == "error")
        gr = GateResult(gate=kind, status=status, severity=gsev, findings=fs,
                        note=f"{len(fs)} 处 {kind}({n_err} 硬冲突)")

        def _gate(_artifact, _gr=gr):
            return _gr
        _gate.__name__ = f"gate_{kind}"
        fns.append(_gate)
    return fns


def report_from_internal(internal, producer="consistency", target="cross-material"):
    """已算出的内部 findings → light.findings.v1(经 _shared/gate_runner 聚合)。"""
    if not HAVE_FINDINGS:
        raise RuntimeError(
            "_shared/findings_schema 不可导入,无法产 light.findings.v1(检查 _shared 路径)")
    fns = _gate_fns_from_internal(internal)
    if not fns:
        fns = [lambda _a: GateResult("consistency", "pass", "info", [],
                                     note="未发现跨材料不一致")]
    return run_gates(fns, artifact=None, producer=producer, target=target,
                     summary="跨材料一致性审计(术语/指标/创新点/措辞)", fresh_evidence=True)


def audit_to_report(materials, source, today=None,
                    producer="consistency", target="cross-material"):
    """raw 材料+事实源 → light.findings.v1。run_audit 抛异常不静默:交 run_gates 兜成
    critical fail(对齐 gate_runner 诚实纪律),绝不假成功。"""
    if not HAVE_FINDINGS:
        raise RuntimeError(
            "_shared/findings_schema 不可导入,无法产 light.findings.v1(检查 _shared 路径)")
    try:
        internal = run_audit(materials, source, today=today)
    except Exception:
        def _boom(_a):
            return run_audit(materials, source, today=today)  # 复跑触发同一异常,交 run_gates 捕获
        return run_gates([_boom], artifact=None, producer=producer, target=target,
                         summary="跨材料一致性审计(审计抛异常)", fresh_evidence=True)
    return report_from_internal(internal, producer=producer, target=target)


# ---------------------------------------------------------------------------
# 合成自测：无参数运行时，用内置事实源 + 内置材料跑一遍，验证全部检测类型都能命中
# ---------------------------------------------------------------------------
SYNTH_SOURCE = {
    "_source_meta": {
        "mode": "yaml", "path": ".light/consistency",
        "present_files": ["glossary.yaml", "method_lock.yaml", "metric_registry.yaml"],
        "missing_files": ["claims_registry.yaml"],
        "missing_authority_headers": ["metric_registry.yaml"],
        "provenance_gaps": ["metric-record:f1#1"],
    },
    "glossary": [
        # forbidden 混用 字符串 与 dict 形式(X-1)：dict{text} 也须生效
        {"id": "t1", "canonical": "DCA-Net",
         "forbidden": ["DCANet", {"text": "DCA网络"}], "case_lock": True,
         "must_cover": False},
        {"id": "t2", "canonical": "fine-tune", "forbidden": ["finetune"],
         "case_lock": True, "must_cover": True},  # must_cover -> 缺席报 WARN(X-4)
    ],
    "methods": [
        # placeholder:true 项须被跳过(X-1)，否则"本文方法"会误命中正文；
        # 真实禁用写法"我们的网络"仍须生效。
        {"id": "m1", "canonical": "DCA-Net", "abbr": "DCA-Net", "full": "Dual-Cross Attention Network",
         "forbidden": ["我们的网络",
                       {"text": "本文方法(在正式名出现后仍这么写)", "placeholder": True}]},
        # X-8: abbr≠full 的模块,缩写首次出现前无全称定义 -> ABBREV_FIRST_USE
        {"id": "m2", "canonical": "CCA 模块", "abbr": "CCA", "full": "Cross-Channel Attention",
         "forbidden": [], "first_use_rule": "首次写 CCA(Cross-Channel Attention)"},
    ],
    "metrics": [
        {"id": "f1", "canonical": "F1", "aliases": ["F1-score"],
         "confusable": ["准确率"], "unit": "%", "decimals": 1, "higher_is_better": True,
         "records": [{"method": "DCA-Net", "dataset": "D", "value": 87.6}]},
    ],
    # 创新点单一事实源(X-5)：取自 .light/ terminology.md 的"创新点N"行(此处为合成等价物)
    "contributions": [
        {"id": "创新点1",
         "canonical": "级联误差传播抑制：检测跟踪行为四级流水线的不确定性传播建模"},
    ],
    # 主张-证据登记(X-6)：c_weak 证据弱,材料里用强措辞即 CLAIM_STRENGTH_DRIFT
    "claims": [
        {"claim_id": "c_weak", "text": "SFP reduces miss rate",
         "keywords": ["SFP", "漏检", "召回"], "evidence_grade": "weak",
         "forbidden_zh": ["显著", "大幅", "SOTA"]},
    ],
}
SYNTH_MATERIALS = [
    {"name": "paper.txt", "lines": [
        "我们提出 DCA-Net 用于检测。",
        "DCA-Net 的 F1 达到 87.6%。",
        "训练阶段对骨干网络做 fine-tune。",
        "本文的级联误差传播抑制对检测跟踪行为四级流水线的不确定性传播建模。",
        "venue 影响因子见 [snapshot date=2020-01-01 kind=metric src=JCR-IF]。",  # X-9: STALE
        "SFP 模块对小目标漏检有一定缓解作用。",                                  # claim c_weak,合规
    ]},
    {"name": "ppt.txt", "lines": [
        "本页介绍 DCANet 架构。",                 # SUBSTITUTION: DCANet
        "DCA-Net 的 F1 为 85.2%。",                # METRIC_VALUE: 与权威 87.6 冲突(小偏差)
        "我们的网络准确率 85.2% 领先。",            # SUBSTITUTION(我们的网络)+METRIC_NAME(准确率)
        "采用 finetune 策略。",                    # SUBSTITUTION: finetune
        "DCA-Net 的 F1 是 50.0%。",                # GROSS_MISMATCH: 偏差 43% (X-2)
        "DCA-Net 的 F1 写作 0.876。",              # 单位归一化后==87.6，不应误报(X-2)
        "这里做了流水线的误差处理。",               # 覆盖不足，不应误报为漂移
        "本页讲多级流水线误差传播的处理思路与系统稳健性提升方案。",  # CONTRIBUTION_DRIFT(X-5)
        "SFP 模块显著降低小目标漏检率。",           # X-6: weak 证据用"显著" -> CLAIM_STRENGTH_DRIFT
        "DCA Net 与基线对比。",                     # X-7: 'DCA Net' 未登记近形变体 -> VARIANT_CONFLICT
        "CCA 模块用于通道建模。",                   # X-8: 缩写 CCA 首次出现无全称 -> ABBREV_FIRST_USE
        "代码示例如下：",
        "```python",
        "model = finetune(net)  # 代码块内 finetune 不应误报(scope-aware)",
        "```",
    ]},
    # fine-tune(must_cover) 仅出现在 paper -> COVERAGE_GAP/WARN
]


def selftest():
    print(">>> 运行内置合成自测\n")
    findings = run_audit(SYNTH_MATERIALS, SYNTH_SOURCE, today="2026-06-15")
    print(render_report(findings, SYNTH_MATERIALS))
    kinds = {f["kind"] for f in findings}
    expect = {"SUBSTITUTION", "METRIC_NAME", "METRIC_VALUE", "GROSS_MISMATCH",
              "CONTRIBUTION_DRIFT", "COVERAGE_GAP", "CLAIM_STRENGTH_DRIFT",
              "VARIANT_CONFLICT", "ABBREV_FIRST_USE", "STALE_SNAPSHOT",
              "AUTHORITY_COVERAGE"}
    missing = expect - kinds
    ok = not missing
    checks = []
    # X-1: placeholder 跳过 = 没有任何 detail 含"本文方法"的误报
    no_placeholder = not any("本文方法" in f["detail"] for f in findings)
    checks.append(("X-1 placeholder 占位被跳过", no_placeholder))
    # X-2: GROSS_MISMATCH 恰好命中 50.0 那行，且 0.876 行未被误报
    gm = [f for f in findings if f["kind"] == "GROSS_MISMATCH"]
    gm_ok = len(gm) == 1 and "50" in gm[0]["line"]
    norm_ok = not any("0.876" in f["line"] for f in findings)
    checks.append(("X-2 GROSS_MISMATCH 单列且未静默丢弃", gm_ok))
    checks.append(("X-2 单位归一化 0.876==87.6 不误报", norm_ok))
    # X-4: must_cover(fine-tune)缺席报 WARN
    cov = [f for f in findings if f["kind"] == "COVERAGE_GAP"]
    cov_warn = any(f["severity"] == "warn" and "fine-tune" in f["detail"] for f in cov)
    checks.append(("X-4 must_cover 缺席报 WARN", cov_warn))
    # X-5: 创新点漂移命中 ppt 的偏离句
    drift = [f for f in findings if f["kind"] == "CONTRIBUTION_DRIFT"]
    drift_ok = any(f["location"].startswith("ppt.txt") for f in drift)
    checks.append(("X-5 创新点漂移命中 PPT 偏离句(挂 semantic_sim)", drift_ok))
    # X-6: CLAIM_STRENGTH_DRIFT 命中"SFP 模块显著..."且不误报 paper 的合规句
    csd = [f for f in findings if f["kind"] == "CLAIM_STRENGTH_DRIFT"]
    csd_ok = any("显著" in f["line"] for f in csd) and not any(
        "一定缓解" in f["line"] for f in csd)
    checks.append(("X-6 措辞强于证据(挂 evidence_contract):弱证据'显著'报错、合规句不误报", csd_ok))
    # X-7: VARIANT_CONFLICT 自动发现 'DCA Net'(未预写 forbidden)
    vc = [f for f in findings if f["kind"] == "VARIANT_CONFLICT"]
    vc_ok = any("DCA Net" in f["detail"] for f in vc)
    checks.append(("X-7 共存即冲突:自动发现未登记变体 'DCA Net'", vc_ok))
    # X-8: ABBREV_FIRST_USE 命中 CCA(首次无全称),且 DCA-Net(abbr==full)不误报
    ab = [f for f in findings if f["kind"] == "ABBREV_FIRST_USE"]
    ab_ok = any("CCA" in f["detail"] for f in ab)
    checks.append(("X-8 缩写首次全称规则:CCA 报错(消费 first_use_rule)", ab_ok))
    # X-9: STALE_SNAPSHOT 命中 2020 的计量快照(距 2026-06-15 远超 90 天)
    ss = [f for f in findings if f["kind"] == "STALE_SNAPSHOT"]
    ss_ok = any("2020-01-01" in f["line"] for f in ss)
    checks.append(("X-9 快照超期:计量快照 >90 天报 WARN(维度⑦兑现)", ss_ok))
    # R2：事实源缺文件/owner/provenance 必须显式 warn，且不能扩大 critical 阻断面
    ac = [f for f in findings if f["kind"] == "AUTHORITY_COVERAGE"]
    ac_ok = (len(ac) == 3 and all(f["severity"] == "warn" for f in ac)
             and any("claims_registry.yaml" in f["detail"] for f in ac)
             and any("source+locator" in f["detail"] for f in ac))
    checks.append(("R2 AUTHORITY_COVERAGE:缺 schema/owner/provenance 显式 warn-only", ac_ok))
    md_ac = audit_authority_coverage({
        "_source_meta": {"mode": "markdown", "path": ".light/terminology.md"}})
    checks.append(("R2 Markdown-only 明示部分覆盖",
                   len(md_ac) == 1 and "Markdown 覆盖档" in md_ac[0]["detail"]))
    checks.append(("R2 provenance 占位符不算 confirmed",
                   not _confirmed_provenance({
                       "status": "confirmed", "source": "示例事实源",
                       "locator": "需替换为真实页码"})))
    # scope-aware: 代码块内 finetune 未被 SUBSTITUTION 误报
    scope_ok = not any(f["kind"] == "SUBSTITUTION" and "model = finetune" in f["line"]
                       for f in findings)
    checks.append(("scope-aware 代码块内 finetune 不误命中", scope_ok))
    # 契约挂接留痕
    print(f"\n[契约挂接] evidence_contract={'已挂' if HAVE_EVIDENCE else '缺失(降级)'} "
          f"semantic_sim={'已挂' if HAVE_SEMSIM else '缺失(降级)'}")

    # findings 接线断言:内部 findings → light.findings.v1,被总控 run_checkpoint 聚合
    if HAVE_FINDINGS:
        rep = report_from_internal(findings, target="selftest")
        checks.append(("F-1 产 light.findings.v1(producer=consistency)",
                       rep.schema == "light.findings.v1" and rep.producer == "consistency"))
        # 合成材料含 SUBSTITUTION/METRIC_VALUE 等硬冲突(error) → verdict 必 fail(总控 exit 1 阻断)
        checks.append(("F-2 含硬冲突 → verdict=fail(被总控确定性阻断)", rep.verdict == "fail"))
        checks.append(("F-3 至少一个 blocking gate(critical fail)",
                       any(g.is_blocking() for g in rep.gates)))
        checks.append(("F-4 light.findings.v1 JSON 往返保真",
                       FindingsReport.from_json(rep.to_json()).verdict == "fail"))
        checks.append(("F-5 每个检测 kind 映成一个 gate",
                       {g.gate for g in rep.gates} >= expect))
        ac_rep = report_from_internal(ac, target="authority-only")
        checks.append(("F-6 AUTHORITY_COVERAGE 单独只到 verdict=warn",
                       ac_rep.verdict == "warn"
                       and not any(g.is_blocking() for g in ac_rep.gates)))
    else:
        checks.append(("F-0 _shared/findings_schema 可导入(产机读门必需)", False))

    print("\n[自测断言] 全部检测类型均触发：",
          "通过" if ok else f"缺失 {missing}")
    for name, passed in checks:
        print(f"  - {name}：{'通过' if passed else '失败'}")
        ok = ok and passed
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="跨材料一致性审计器")
    ap.add_argument("--source", help=".light/ 事实源:含 glossary.yaml 等 schema 的目录,"
                                     "或项目 terminology.md(Markdown 表,覆盖缺口档)")
    ap.add_argument("--materials", nargs="*", help="材料文本文件(支持 glob)")
    ap.add_argument("--json", help="把内部 dict findings 写入该 JSON 文件(调试/人读)")
    ap.add_argument("--report", help="把 light.findings.v1 报告写到该文件"
                                     "(供总控 run_checkpoint --findings 聚合为跨阶段一致性门)")
    ap.add_argument("--report-target", help="findings 报告里的 target 名(默认 cross-material)")
    ap.add_argument("--today", help="基准日期 YYYY-MM-DD(STALE_SNAPSHOT 用,缺省取今天)")
    ap.add_argument("--selftest", action="store_true", help="run built-in offline synthetic self-test")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.source or not args.materials:
        return selftest()

    source = load_source_auto(args.source)
    paths = []
    for pat in args.materials:
        paths += glob.glob(pat) or [pat]
    materials = [read_material(p) for p in paths if os.path.isfile(p)]
    if not materials:
        sys.stderr.write("未找到任何材料文件\n")
        return 2

    findings = run_audit(materials, source, today=args.today)
    print(render_report(findings, materials))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(findings, f, ensure_ascii=False, indent=2)
        print(f"\n[已写出内部 JSON] {args.json}")
    if args.report:
        rep = report_from_internal(findings, target=(args.report_target or "cross-material"))
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(rep.to_json())
        print(f"\n[已写出 light.findings.v1] {args.report}"
              f"（verdict={rep.verdict}；交 run_checkpoint --findings 聚合）")
    errors = sum(1 for f in findings if f["severity"] == "error")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
