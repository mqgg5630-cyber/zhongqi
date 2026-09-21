#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_lint.py — 实验矩阵四要素齐全性检查 (Light / light-research-plan)

检查实验矩阵 Markdown 表每个实验行是否齐备四要素，缺一即提示：
  1. 假设      ← "对应假设" 列非空且形如 H1/H2…
  2. 变量      ← "数据集" 与 "baseline" 列均非空（自变量/控制变量的最小落地）
  3. 指标      ← "指标" 列非空
  4. 停止条件  ← "完成判定" 列非空（用什么结果回答该假设、达到判定门槛）

对应 EXP-Bench 四要素与 SKILL「实验设计」纪律：设计与结论最易跑偏。
纯离线、只读、不产文件；--selftest 用内置样例自测。

用法：
    python scripts/plan_lint.py --file experiments/experiment_matrix.md
    python scripts/plan_lint.py --selftest
退出码：0 全齐 / 1 有缺项或无法解析（可接 CI）。
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

# ── 挂接共享契约（_shared）：规范 bootstrap（_shared/README.md，向上走目录树找仓库根，
# 治 v1 硬编码 parents[2] 之脆——v2 仓库根上移一层后必断）；缺失则降级，不静默假成功 ──
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
if str(_r) not in sys.path:
    sys.path.insert(0, str(_r))
try:
    from _shared.semantic_sim import similarity as _sem_sim, last_mode as _sem_mode
    _HAS_SEM = True
except Exception:                      # pragma: no cover - 降级路径
    _HAS_SEM = False
    def _sem_sim(a, b, mode="auto"):   # type: ignore
        return 0.0
    def _sem_mode():                   # type: ignore
        return None
try:
    from _shared.evidence_contract import _ASSERTIVE_VERBS
    _HAS_EVID = True
except Exception:                      # pragma: no cover - 降级路径
    _HAS_EVID = False
    _ASSERTIVE_VERBS = ["prove", "demonstrate", "establish", "confirm", "show",
                        "outperform", "superior", "significantly"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 列名 → 要素的别名映射（容忍模板措辞差异）
COL_ALIASES = {
    "hypothesis": ("对应假设", "假设"),
    "dataset": ("数据集", "data", "数据"),
    "baseline": ("baseline", "基线", "对照"),
    "metric": ("指标", "metric", "评价指标"),
    "stop": ("完成判定", "停止条件", "判定", "成功标准"),
    "confound": ("已控混淆", "负对照", "混淆", "negative control", "control"),
}
# 语义对齐阈值：完成判定与指标的语义相似度低于此值才判"脱节"(替代脆弱子串匹配)
SEM_ALIGN_THRESHOLD = 0.30
# 因果/贡献声明触发词：含这些的完成判定属"强断言"，应有负对照/混淆控制
CAUSAL_CLAIM_RE = re.compile(
    r"证明|归因|因果|贡献|导致|cause|because|due to|attribut|prove|demonstrat", re.I)
# 占位符（模板未填）视为缺项
PLACEHOLDER_RE = re.compile(r"^\s*(\{\{.*\}\}|[-—–]|n/?a|tbd|待定|待填|\.\.\.|…)?\s*$", re.I)
# 实验行 ID 形态：EXP-01 / ABL-02 / SEN-01 / GEN/ROB 等
EXP_ID_RE = re.compile(r"^[A-Z]{2,4}-?\d+$")
HYP_RE = re.compile(r"\bH\d+\b")
# 可量化阈值：含数字、不等号、p 值、百分比等——停止条件应可量化而非纯定性
QUANT_RE = re.compile(r"\d|[<>≥≤=]|p\s*[<>=]|%|百分", re.I)
# 纯定性词（停止条件只写这些 = 不可验收）
QUALITATIVE_ONLY = ("效果好", "有提升", "更优", "表现好", "可行", "成功", "提高", "改善",
                    "better", "improve", "good", "works")


def _is_blank(cell: str) -> bool:
    return bool(PLACEHOLDER_RE.match(cell or ""))


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def parse_tables(text: str) -> list[list[list[str]]]:
    """把 Markdown 里所有管线表解析为 [表][行][单元格]。"""
    tables, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cur.append(cells)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    return tables


def _is_separator(row: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.strip() or "") for c in row if c.strip() != "") \
        and any("-" in c for c in row)


def find_experiment_table(tables: list[list[list[str]]]) -> tuple[list[str], list[list[str]]] | None:
    """找含"对应假设/假设"列且有实验 ID 行的表，返回 (表头, 数据行)。"""
    for tbl in tables:
        if len(tbl) < 2:
            continue
        header = tbl[0]
        norm_header = [_norm(h) for h in header]
        has_hyp = any(any(a in nh for a in (_norm(x) for x in COL_ALIASES["hypothesis"]))
                      for nh in norm_header)
        if not has_hyp:
            continue
        rows = [r for r in tbl[1:] if not _is_separator(r)]
        # 至少一行首列像实验 ID
        if any(EXP_ID_RE.match((r[0] or "").strip()) for r in rows if r):
            return header, rows
    return None


def _col_index(header: list[str], element: str) -> int | None:
    for i, h in enumerate(header):
        nh = _norm(h)
        if any(_norm(alias) in nh for alias in COL_ALIASES[element]):
            return i
    return None


def _metric_aligned(stop_val: str, metric_val: str) -> bool:
    """判定完成判定是否与指标对齐，分三层、各层诚实标注能力边界：
      1) 词面 token 直接命中（最强信号）
      2) token 缩写/前缀匹配（acc⊂accuracy、mAP⊂mAP@0.5——治常见缩写漏报，纯字符串、不夸张）
      3) 共享 semantic_sim 语义档（仅当注入 embedding/LLM scorer 才真能跨同义/跨语言；
         离线档对 acc↔accuracy 这类缩写、mAP↔平均精度这类跨语言同义**力有不逮**，故只作补充信号）
    """
    low_stop = stop_val.lower()
    stop_tokens = re.findall(r"[a-z]+[\-\d@\.]*|[一-鿿]{2,}", low_stop)
    mtokens = re.findall(r"[A-Za-z]+[\-\d@\.]*|[一-鿿]{2,}", metric_val.lower())
    mtokens = [t for t in mtokens if len(t) >= 2 or any(ch.isdigit() for ch in t)]
    if not mtokens:
        return True                      # 指标无可比 token，不判脱节
    # 层1：词面直接命中
    if any(t in low_stop for t in mtokens):
        return True
    # 层2：缩写/前缀双向匹配（acc 是 accuracy 的前缀；长度≥3 防误命中 f/r 这种单字母）
    for mt in mtokens:
        core = re.sub(r"[\-\d@\.]", "", mt)
        if len(core) < 3:
            continue
        for st in stop_tokens:
            score = re.sub(r"[\-\d@\.]", "", st)
            if len(score) < 3:
                continue
            if core.startswith(score) or score.startswith(core):
                return True
    # 层3：语义档（embedding/LLM 注入时才有真同义判别力，离线档仅补充）
    if _HAS_SEM:
        return _sem_sim(metric_val, stop_val, mode="auto") >= SEM_ALIGN_THRESHOLD
    return False


def lint(text: str) -> dict:
    tables = parse_tables(text)
    found = find_experiment_table(tables)
    if not found:
        return {"ok": False, "error": "未找到实验矩阵表（需含「对应假设」列且有 EXP-/ABL- 等实验行）"}
    header, rows = found
    idx = {el: _col_index(header, el) for el in COL_ALIASES}
    # confound 列为可选（新增能力），不计入硬性缺列
    missing_cols = [el for el, i in idx.items() if i is None and el != "confound"]
    findings = []
    warnings = []           # 语义弱校验（不翻 ok 退出码，但提示"绿了可能仍错"）
    hyp_to_exps = {}        # 假设 → 该假设下的实验 ID 列表（覆盖度检查）
    n_hypothesis_tests = 0  # 多重比较族大小 K：完成判定里做显著性检验的行数
    checked = 0
    for r in rows:
        if not r or not EXP_ID_RE.match((r[0] or "").strip()):
            continue
        checked += 1
        exp_id = r[0].strip()
        gaps = []
        # 假设
        i = idx["hypothesis"]
        hyp_val = r[i] if (i is not None and i < len(r)) else ""
        if i is None or i >= len(r) or _is_blank(r[i]) or not HYP_RE.search(r[i]):
            gaps.append("假设(对应假设列空或非 H#)")
        else:
            for h in HYP_RE.findall(hyp_val):
                hyp_to_exps.setdefault(h, []).append(exp_id)
        # 变量：数据集 + baseline 都要有
        for el, label in (("dataset", "数据集"), ("baseline", "baseline")):
            j = idx[el]
            if j is None or j >= len(r) or _is_blank(r[j]):
                gaps.append(f"变量({label}空)")
        # 指标
        k = idx["metric"]
        metric_val = r[k] if (k is not None and k < len(r)) else ""
        if k is None or k >= len(r) or _is_blank(r[k]):
            gaps.append("指标(空)")
        # 停止条件
        m = idx["stop"]
        stop_val = r[m] if (m is not None and m < len(r)) else ""
        if m is None or m >= len(r) or _is_blank(r[m]):
            gaps.append("停止条件(完成判定空)")
        else:
            # 多重比较族计数：完成判定含 p 值/显著性检验 → 计入 K
            if re.search(r"p\s*[<>=]|显著|significan|q\s*[<>=]|fdr", stop_val, re.I):
                n_hypothesis_tests += 1
            # 语义弱校验1：停止条件应可量化（含数字/不等号/p值），纯定性词给 warning
            if not QUANT_RE.search(stop_val):
                warnings.append(f"{exp_id}: 完成判定「{stop_val[:30]}」无可量化阈值（数字/不等号/p值），"
                                f"难以客观验收——EXP-Bench 最忌结论判定不可量化")
            elif any(q in stop_val.lower() for q in QUALITATIVE_ONLY) and not QUANT_RE.search(stop_val):
                warnings.append(f"{exp_id}: 完成判定含定性词且无量化门槛")
            # 语义弱校验2：完成判定是否与该行指标对齐（语义相似度，替脆弱子串匹配）
            if metric_val and not _is_blank(metric_val):
                aligned = _metric_aligned(stop_val, metric_val)
                if not aligned:
                    backend = f"[{_sem_mode() or 'literal'}]" if _HAS_SEM else "[literal]"
                    warnings.append(f"{exp_id}: 完成判定与指标「{metric_val[:20]}」语义不对齐 {backend}，"
                                    f"判定与指标可能脱节（绿了但判定对错存疑）")
            # 语义弱校验4（新增，借 Popper/co-scientist）：因果/贡献声明须有负对照/混淆控制
            if CAUSAL_CLAIM_RE.search(stop_val):
                ci = idx["confound"]
                conf_val = r[ci] if (ci is not None and ci < len(r)) else ""
                if ci is None or _is_blank(conf_val):
                    warnings.append(f"{exp_id}: 完成判定做因果/贡献声明「{stop_val[:24]}」但「已控混淆/负对照」列空——"
                                    f"缺负对照难排除替代解释（借 Popper 严格 Type-I：声明因果须配负对照）")
        if gaps:
            findings.append({"exp_id": exp_id, "gaps": gaps})

    # 语义弱校验3：假设-实验覆盖度——每个假设最好有 ≥1 主实验(EXP) + ≥1 消融(ABL)
    coverage_warnings = []
    for h, exps in sorted(hyp_to_exps.items()):
        prefixes = {re.match(r"^[A-Z]+", e).group(0) for e in exps if re.match(r"^[A-Z]+", e)}
        if "ABL" not in prefixes:
            coverage_warnings.append(f"假设 {h} 无消融实验(ABL-)，仅靠 {sorted(set(exps))} 验证——"
                                     f"缺消融难归因增益来自创新点本身")
    warnings.extend(coverage_warnings)

    # 多重比较感知（与 result-analysis 显著性校正口径对齐）：K>1 但 power 未按校正后 alpha 反推时 warn。
    power_under_correction_ok = True
    if n_hypothesis_tests > 1:
        power_under_correction_ok = False
        warnings.append(
            f"多重比较族 K={n_hypothesis_tests}（{n_hypothesis_tests} 行做显著性检验）："
            f"种子/重复数应在校正后 α 上反推，否则 result-analysis 做 BH-FDR 后整盘静默欠功效。"
            f"跑 `python scripts/power_check.py --effect <d> --n-comparisons {n_hypothesis_tests} "
            f"--correction bh` 取校正后 min_n。")

    # 严谨性评分卡：经验扣分制（**非 ARA 那种六维语义认知评审，是计数扣分；诚实降级**）。
    # 每个硬缺项行扣 15、每条语义 warning 扣 5，封底 0。仅作可审计的相对严谨度起点，非真值。
    rigor = 100
    rigor -= 15 * len(findings)
    rigor -= 5 * len(warnings)
    rigor = max(0, rigor)
    rigor_breakdown = {
        "form_complete": len(findings) == 0,              # 四要素齐全
        "quantifiable_verdicts": not any("无可量化阈值" in w for w in warnings),
        "verdict_metric_aligned": not any("脱节" in w for w in warnings),
        "ablation_coverage": not any("无消融实验" in w for w in warnings),
        "confound_coverage": not any("已控混淆/负对照" in w for w in warnings),
        "power_under_correction": power_under_correction_ok,
        "n_hard_gaps": len(findings),
        "n_semantic_warnings": len(warnings),
        "scoring": "计数扣分制(非真值/非语义认知评审)",
    }

    return {"ok": len(findings) == 0 and not missing_cols,
            "rigor_score": rigor, "rigor_breakdown": rigor_breakdown,
            "checked_rows": checked, "missing_columns": missing_cols,
            "n_hypothesis_tests": n_hypothesis_tests,
            "sem_backend": (_sem_mode() if _HAS_SEM else None),
            "findings": findings, "warnings": warnings,
            "hypotheses": {h: sorted(set(e)) for h, e in hyp_to_exps.items()}}


def _print_report(rep: dict) -> None:
    if rep.get("error"):
        print(f"[plan_lint] 解析失败: {rep['error']}")
        return
    print(f"[plan_lint] 检查 {rep['checked_rows']} 个实验行")
    if rep["missing_columns"]:
        print(f"  ⚠ 表头缺列: {', '.join(rep['missing_columns'])}（无法核对对应要素）")
    if rep["findings"]:
        for f in rep["findings"]:
            print(f"  ✗ {f['exp_id']}: 缺 {', '.join(f['gaps'])}")
    else:
        print("  ✓ 所有实验行四要素齐全（假设/变量/指标/停止条件）")
    # 语义弱校验（warning：不影响退出码，但提示"形式齐全≠语义正确"）
    if rep.get("warnings"):
        print(f"  —— 语义弱校验 {len(rep['warnings'])} 条 warning（形式齐全≠语义正确，人工核） ——")
        for w in rep["warnings"]:
            print(f"  ⚠ {w}")
    # 严谨性评分卡（计数扣分制，非 ARA 语义评审）
    if "rigor_score" in rep:
        b = rep["rigor_breakdown"]
        print(f"  —— 严谨性评分 {rep['rigor_score']}/100（计数扣分制，可审计；非真值/非语义认知评审） ——")
        print(f"     四要素齐全={b['form_complete']} 判定可量化={b['quantifiable_verdicts']} "
              f"判定指标对齐={b['verdict_metric_aligned']} 有消融覆盖={b['ablation_coverage']}")
        print(f"     已控混淆/负对照={b['confound_coverage']} 多重比较已校正={b['power_under_correction']}"
              f"  (指标对齐档={rep.get('sem_backend') or 'literal'})")
        if rep.get("n_hypothesis_tests", 0) > 1:
            print(f"     多重比较族 K={rep['n_hypothesis_tests']} → 功效须按校正后 α 反推")


def _selftest() -> int:
    good = """
# 实验矩阵

| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 随机种子 | 状态 | 完成判定 |
|--------|----------|--------------|----------------|------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 | 0,1,2 | 未开始 | top-1 > baseline 且 p<0.05 |
"""
    rep = lint(good)
    assert rep["ok"], rep
    assert rep["checked_rows"] == 1 and not rep["findings"], rep

    bad = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 状态 | 完成判定 |
|--------|----------|--------------|----------------|------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 | 未开始 | top-1 > baseline 且 p<0.05 |
| EXP-02 | {{假设}} | {{数据集}} | ResNet50 | top-1 | 未开始 | {{判定门槛}} |
| ABL-01 | H2 | CIFAR | 移除X | acc | 未开始 | — |
"""
    rep2 = lint(bad)
    assert not rep2["ok"], rep2
    assert rep2["checked_rows"] == 3, rep2
    ids = {f["exp_id"] for f in rep2["findings"]}
    assert ids == {"EXP-02", "ABL-01"}, rep2
    exp02 = next(f for f in rep2["findings"] if f["exp_id"] == "EXP-02")
    assert any("假设" in g for g in exp02["gaps"]), exp02
    assert any("数据集" in g for g in exp02["gaps"]), exp02
    assert any("停止条件" in g for g in exp02["gaps"]), exp02
    abl = next(f for f in rep2["findings"] if f["exp_id"] == "ABL-01")
    assert any("停止条件" in g for g in abl["gaps"]), abl

    # 无实验表 → 报错而非崩
    rep3 = lint("# 没有表格\n普通文字。")
    assert not rep3["ok"] and rep3.get("error"), rep3

    # 语义弱校验：完成判定不可量化 + 判定与指标脱节 + 假设无消融
    sem = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 acc | 效果比 baseline 好 |
| EXP-02 | H2 | CIFAR | VGG | F1 | top-1 > 0.9 |
"""
    rs = lint(sem)
    # 四要素齐全(形式) → ok=True，但应有语义 warning
    assert rs["ok"], rs
    # EXP-01 完成判定"效果比baseline好"无量化阈值
    assert any("EXP-01" in w and "无可量化阈值" in w for w in rs["warnings"]), rs["warnings"]
    # EXP-02 指标是 F1 但判定写 top-1（脱节）
    assert any("EXP-02" in w and "脱节" in w for w in rs["warnings"]), rs["warnings"]
    # H1/H2 都无 ABL 消融 → 覆盖度 warning
    assert any("H1" in w and "消融" in w for w in rs["warnings"]), rs["warnings"]

    # 有消融时不报覆盖度 warning
    with_abl = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 | top-1 > baseline 且 p<0.05 |
| ABL-01 | H1 | ImageNet | 移除X | top-1 | top-1 下降 > 2% 证明X有效 |
"""
    rab = lint(with_abl)
    assert not any("消融" in w for w in rab["warnings"]), rab["warnings"]

    # 严谨性评分卡：齐全+对齐+有消融 → 高分；缺项/多 warning → 低分
    assert rab["rigor_score"] >= 85, rab["rigor_score"]          # with_abl 基本干净
    assert rab["rigor_breakdown"]["ablation_coverage"], rab
    assert rs["rigor_score"] < rab["rigor_score"], (rs["rigor_score"], rab["rigor_score"])  # sem 有 warning 应更低
    assert rep2["rigor_score"] < 100, rep2["rigor_score"]        # bad 有硬缺项

    # —— 新增校验1：缩写/前缀对齐治同义词漏报（层2）+ 语义档可用时留痕 ——
    # 指标 accuracy，完成判定写 acc：词面"accuracy"不在判定里，但 acc⊂accuracy 前缀匹配应对齐
    syn = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | classification accuracy | acc 提升 > 2 个百分点 |
| ABL-01 | H1 | ImageNet | 移除X | classification accuracy | acc 下降 > 2% |
"""
    rsyn = lint(syn)
    # 缩写前缀匹配应消除 accuracy↔acc 误报（不依赖 embedding）
    assert not any("脱节" in w for w in rsyn["warnings"]), \
        ("acc⊂accuracy 前缀匹配应消除误报", rsyn["warnings"])
    assert rsyn["ok"], rsyn
    # 真脱节仍要报：指标 F1 但判定只提 top-1（无前缀/词面/缩写关系）
    mis = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | F1 score | top-1 > 0.9 |
"""
    rmis = lint(mis)
    assert any("脱节" in w for w in rmis["warnings"]), rmis["warnings"]

    # —— 新增校验2：因果/贡献声明无负对照 → confound warning（借 Popper）——
    causal = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| ABL-01 | H1 | ImageNet | 移除模块X | top-1 | top-1 下降 > 2% 证明模块X的贡献 |
"""
    rc = lint(causal)
    assert any("已控混淆/负对照" in w for w in rc["warnings"]), rc["warnings"]
    assert not rc["rigor_breakdown"]["confound_coverage"], rc["rigor_breakdown"]
    # 补上"已控混淆"列后不再 warn
    causal_ok = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 已控混淆/负对照 | 完成判定 |
|--------|----------|--------|----------|------|-----------------|----------|
| ABL-01 | H1 | ImageNet | 移除模块X | top-1 | 随机标签负对照+同等调参预算 | top-1 下降 > 2% 证明模块X的贡献 |
"""
    rco = lint(causal_ok)
    assert not any("已控混淆/负对照" in w for w in rco["warnings"]), rco["warnings"]
    assert rco["rigor_breakdown"]["confound_coverage"], rco["rigor_breakdown"]

    # —— 新增校验3：多重比较族计数 K + 未校正 warning（top_idea 1）——
    multi = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | A | B1 | top-1 | top-1 > baseline 且 p<0.05 |
| EXP-02 | H1 | A | B2 | top-1 | top-1 > baseline 且 p<0.05 |
| EXP-03 | H2 | A | B3 | top-1 | top-1 > baseline 且 p<0.05 |
"""
    rmul = lint(multi)
    assert rmul["n_hypothesis_tests"] == 3, rmul["n_hypothesis_tests"]
    assert any("多重比较族 K=3" in w for w in rmul["warnings"]), rmul["warnings"]
    assert not rmul["rigor_breakdown"]["power_under_correction"], rmul["rigor_breakdown"]
    # 单一检验不触发
    assert rab["n_hypothesis_tests"] <= 1, rab["n_hypothesis_tests"]
    assert rab["rigor_breakdown"]["power_under_correction"], rab["rigor_breakdown"]

    print("[selftest] PASS plan_lint（齐全/缺项/无表 + 语义弱校验 + 覆盖度 + 严谨性评分 "
          "+ 语义对齐 + 负对照覆盖 + 多重比较族计数）")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="实验矩阵四要素齐全性检查")
    ap.add_argument("--file", help="实验矩阵 Markdown 路径")
    ap.add_argument("--selftest", action="store_true", help="离线样例自测")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    if not args.file:
        ap.error("需 --file <实验矩阵.md> 或 --selftest")
    with open(args.file, encoding="utf-8") as f:
        rep = lint(f.read())
    _print_report(rep)
    sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
