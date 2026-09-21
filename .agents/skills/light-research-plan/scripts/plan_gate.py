#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_gate.py — research-plan 的**对照公平 / 可证伪 Critical 门 producer**。

蓝图 §4.3-5 的"及格线":一个方案要"能真执行、能写进论文、能复现",最先被院士枪毙的两点是
**对照放水**(baseline 不公平,提升是假的)与**不可证伪**(假设推不翻 = 不是科学,是包装)。本脚本把
这两点编排成机读 `light.findings.v1`(producer=**research-plan**),**对照不公平 / 不可证伪 → critical
fail** → 被总控 `run_checkpoint --stage 5` 聚合 **exit 1**。门名对齐 `STAGE_GATES[5]=[fair_baseline,
falsifiable]`。**消融不隔离 / 欠功效 = warn**(spec §4.2:消融不隔离列 warn;统计功效不足偏紧)。

这是 **v2 净新增的接线**(与 data-engineering `data_feasibility_gate`、idea 侧 `fatal_flaw_gate`/
`idea_selfcheck`、lit-search `domain_map` 同构):v1 的 `plan_lint`(实验矩阵 linter)/`power_check`
(统计功效)**是纯工具/linter,零产 `light.findings.v1`**(grep 实证)——本脚本把它们 + 方案的**显式
公平性/可证伪声明**接成 critical findings producer,**不重造**矩阵 lint / 功效反推逻辑(复用同目录港来脚本)。

回炉语义(spec §5):research-plan **自身门 fail = 改方案,在 stage 5 内修复**(**无 `ROUTES[5]` 出边**);
它是 **7→5**(result-analysis 结果不支撑假设)、**13→5**(拒稿·实验)的**回炉落点**——那两条由总控
`reroute --stage 7/13` 命中 `ROUTES` 建议、`passport add-back-edge --to 5` 落账,不在本脚本。

四个 gate:
  ① fair_baseline(对照公平,**critical**):baseline 声明 `unfair`(放水/未公平调参/裁弱/少给数据算力)→
     critical;未声明对照公平性 → warn(须补,不静默放行);`warn`(没能完全调到 SOTA)→ warn;`ok` → pass。
  ② falsifiable(可证伪,**critical**):假设缺**反证条件**(falsifier:什么结果能推翻 H)→ critical;
     无任何假设 → critical;反证条件在但不可量化(无数字/不等号/p 值)→ warn。
  ③ ablation_isolation(消融隔离,**warn**):plan_lint 判某假设无消融(ABL)行 / 因果声明无负对照 → warn
     (消融不干净隔离贡献,spec §4.2 列 warn,不阻断)。
  ④ statistical_power(统计功效,**warn**):power_check 据效应量 + 种子/重复数(+ 多重比较校正)判欠功效 →
     warn(加种子/重复;非 critical,可修)。**功效依赖效应量假设**(诚实边界)。

诚实约定(名实对齐见 SKILL,铁律 2/3):
- **lint 是启发式、有边界**:plan_lint 查矩阵四要素/指标对齐/消融覆盖/负对照/多重比较,**绝不"证明了对照
  绝对公平 / 假设绝对可证伪"**——公平 / 可证伪的**终判仍需人 / 领域判断**;本脚本只聚合**声明 + 可机检信号**。
- **对照公平靠声明 + 信号,不靠脚本臆断**:fair_baseline 读方案**显式声明的公平性条件**(同数据 / 等量调参预算 /
  取最强可得 baseline),脚本不替你判"baseline 到底调够没"(GIGO);未声明 → warn 提示补,不编造"放水"。
- **功效是计划阶段反推,非结果阶段检验**:power_check 据**假设的效应量**反推所需种子/重复(+ 多重比较校正),
  d 来源须方案注明(文献 meta / 预实验),脚本对 d 极敏感。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  python plan_gate.py --spec plan_spec.json --report plan_findings.json
  python plan_gate.py --selftest

spec JSON 形如:
  {"project":"goat-estrus",
   "matrix":"<实验矩阵 markdown 内联>",            # 或 "matrix_file":"experiment_matrix.md"
   "hypotheses":[{"id":"H1","statement":"...","falsifier":"top-1 提升<2% 或 p>=0.05 则 H1 被推翻"}],
   "baselines":[{"name":"ResNet50","fairness":"ok:同数据同划分+等量调参预算(各200轮)+取当前SOTA"}],
   "power":{"effect_size":0.5,"n_seeds":5,"n_comparisons":3,"correction":"bh","target_power":0.8}}
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 同目录港来的纯工具/linter(复用不重造:实验矩阵四要素 lint / 统计功效反推)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import plan_lint as pl    # noqa: E402  实验矩阵四要素 + 语义弱校验 + 严谨性评分(linter,非 findings)
import power_check as pc   # noqa: E402  统计功效反推种子/重复数 + 多重比较校正

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,治硬编码 parents[N] 之脆。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    _SHARED_OK = True
except ImportError:                                                          # _shared 不可达:findings 降级
    _SHARED_OK = False


# ───────────────────────── 解析方案显式声明 ─────────────────────────
_FAIR_LEVELS = ("ok", "warn", "unfair")


def _split_level(s: str, valid: tuple, default: str = "ok") -> tuple[str, str]:
    """把 'level:note' 拆成 (level, note);level 不在 valid 则归 default、原串作 note。"""
    raw = (s or "").strip()
    if ":" in raw:
        lv, _, note = raw.partition(":")
        lv = lv.strip().lower()
        if lv in valid:
            return lv, note.strip()
    if raw.lower() in valid:
        return raw.lower(), ""
    return default, raw


def parse_baselines(raw_list: list) -> list[dict]:
    """对照声明 → [{name, level, note}];level∈{ok,warn,unfair}。"""
    out = []
    for b in raw_list or []:
        if isinstance(b, str):
            b = {"name": b, "fairness": ""}
        lv, note = _split_level(b.get("fairness", ""), _FAIR_LEVELS, default="ok")
        out.append({"name": str(b.get("name", "baseline")), "level": lv, "note": note})
    return out


def parse_hypotheses(raw_list: list) -> list[dict]:
    """假设声明 → [{id, statement, falsifier, has_falsifier, falsifier_quant}]。
    has_falsifier = 反证条件非空且非占位符;falsifier_quant = 反证条件含可量化阈值。"""
    out = []
    for h in raw_list or []:
        fid = str(h.get("id", "H?"))
        fal = (h.get("falsifier", "") or "").strip()
        has = bool(fal) and not pl.PLACEHOLDER_RE.match(fal)
        quant = bool(pl.QUANT_RE.search(fal)) if has else False
        out.append({"id": fid, "statement": str(h.get("statement", "")),
                    "falsifier": fal, "has_falsifier": has, "falsifier_quant": quant})
    return out


def run_lint(spec: dict) -> dict | None:
    """跑 plan_lint.lint(实验矩阵)。matrix 内联优先,其次 matrix_file;都无 → None(消融门跳过)。"""
    text = spec.get("matrix")
    if not text and spec.get("matrix_file"):
        text = pathlib.Path(spec["matrix_file"]).read_text(encoding="utf-8")
    if not text:
        return None
    return pl.lint(text)


def run_power(power: dict | None) -> dict | None:
    """跑 power_check.check(效应量 + 种子数 + 多重比较)。无 effect_size → None(功效门跳过)。"""
    if not power or not power.get("effect_size"):
        return None
    return pc.check(float(power["effect_size"]), n=power.get("n_seeds"),
                    target_power=float(power.get("target_power", 0.8)),
                    alpha=float(power.get("alpha", 0.05)),
                    n_comparisons=int(power.get("n_comparisons", 1)),
                    correction=power.get("correction", "none"),
                    expected_rejections=int(power.get("expected_rejections", 1)))


# ───────────────────────── 四个 gate 函数(接 _shared) ─────────────────────────
def _fair_baseline_gate_fn(art: dict) -> "GateResult":
    """对照公平门(unfair=critical):baseline 放水 → 提升是假的 → 在 stage 5 内修复。"""
    baselines = art["baselines"]
    loc = f"{art['project']}:baselines"
    unfair = [b for b in baselines if b["level"] == "unfair"]
    warns = [b for b in baselines if b["level"] == "warn"]
    if unfair:
        detail = "；".join(f"{b['name']}={b['note'] or 'unfair'}" for b in unfair)
        return GateResult(
            "fair_baseline", "fail", "critical",
            [Finding(loc=loc,
                     issue=f"对照不公平(baseline 放水):{detail}——提升可能是对照被裁弱/未公平调参造的假象",
                     fix="给 baseline 等量调参预算 + 同数据同划分同算力 + 取当前最强可得实现,再比较",
                     evidence="；".join(b["note"] for b in unfair if b["note"]),
                     rule="fair_baseline.unfair")],
            note="对照不公平 = critical(spec §4.2):baseline 放水须先修平,否则结论不成立。")
    if not baselines:
        return GateResult(
            "fair_baseline", "warn", "major",
            [Finding(loc=loc,
                     issue="未声明任何对照/baseline 的公平性条件——无法评估对照是否公平",
                     fix="声明每个 baseline 的公平性:同数据划分 / 等量调参预算 / 取最强可得实现",
                     rule="fair_baseline.undeclared")],
            note="未声明对照公平性(warn,须补;不静默放行,也不编造放水)。")
    if warns:
        detail = "；".join(f"{b['name']}={b['note'] or 'warn'}" for b in warns)
        return GateResult(
            "fair_baseline", "warn", "major",
            [Finding(loc=loc, issue=f"对照公平性有保留项:{detail}",
                     fix="尽量调到可比;论文须如实说明对照调参预算与局限",
                     rule="fair_baseline.caveats")],
            note="对照公平含 warn 保留项(可推进,论文须 hedge)。")
    return GateResult("fair_baseline", "pass", "info", [],
                      note="对照公平性已声明(同数据/等量调参/最强可得);终判仍需人/领域复核。")


def _falsifiable_gate_fn(art: dict) -> "GateResult":
    """可证伪门(无反证条件=critical):假设推不翻 = 不是科学是包装 → 在 stage 5 内修复。"""
    hyps = art["hypotheses"]
    loc = f"{art['project']}:hypotheses"
    if not hyps:
        return GateResult(
            "falsifiable", "fail", "critical",
            [Finding(loc=loc, issue="方案无任何可证伪假设(H1/H2…)——没有能被推翻的假设 = 不是科学,是包装",
                     fix="为每条贡献写一条可证伪假设 + 反证条件(什么结果能推翻它)",
                     rule="falsifiable.no_hypothesis")],
            note="无可证伪假设 = critical(spec §4.2)。")
    no_fal = [h for h in hyps if not h["has_falsifier"]]
    if no_fal:
        detail = "；".join(f"{h['id']}:{h['statement'][:24] or '(无陈述)'}" for h in no_fal)
        return GateResult(
            "falsifiable", "fail", "critical",
            [Finding(loc=loc,
                     issue=f"假设缺反证条件(不可证伪):{detail}——没定义「什么结果能推翻 H」,实验无法证伪",
                     fix="为每条假设写明反证条件,如「若主指标提升<阈值 或 p>=0.05 则 H 被推翻」(可量化)",
                     rule="falsifiable.no_falsifier")],
            note="假设无反证条件 = 不可证伪 = critical(spec §4.2):设计须能让假设被推翻。")
    vague = [h for h in hyps if h["has_falsifier"] and not h["falsifier_quant"]]
    if vague:
        detail = "；".join(f"{h['id']}:{h['falsifier'][:24]}" for h in vague)
        return GateResult(
            "falsifiable", "warn", "major",
            [Finding(loc=loc, issue=f"反证条件不可量化(难客观证伪):{detail}",
                     fix="把反证条件写成含数字/不等号/p 值的客观门槛",
                     rule="falsifiable.vague")],
            note="反证条件在但不可量化(warn,难客观验收)。")
    return GateResult("falsifiable", "pass", "info", [],
                      note="每条假设均有可量化反证条件(可被推翻);终判仍需人/领域复核。")


def _ablation_gate_fn(art: dict) -> "GateResult":
    """消融隔离门(warn):每假设是否有消融(ABL)隔离贡献 + 因果声明是否有负对照(spec §4.2 列 warn)。"""
    lint = art["lint"]
    loc = f"{art['project']}:experiment_matrix"
    if lint is None:
        return GateResult("ablation_isolation", "skip", "info", [],
                          note="未提供实验矩阵(matrix/matrix_file):消融隔离检查跳过。")
    if lint.get("error"):
        return GateResult("ablation_isolation", "warn", "minor",
                          [Finding(loc=loc, issue=f"实验矩阵无法解析:{lint['error']}",
                                   fix="按 experiment_matrix.md 模板填(含「对应假设」列 + EXP-/ABL- 行)",
                                   rule="ablation_isolation.unparsable")],
                          note="实验矩阵未解析(warn)。")
    bd = lint.get("rigor_breakdown", {})
    issues = []
    if not bd.get("ablation_coverage", True):
        miss = [w for w in lint.get("warnings", []) if "消融" in w]
        issues.append(Finding(loc=loc,
                              issue="有假设无消融(ABL)实验隔离贡献:" + ("；".join(miss[:3]) or "见 plan_lint"),
                              fix="每条创新假设配 ≥1 消融行,逐个移除创新组件证明其贡献来源",
                              rule="ablation_isolation.no_ablation"))
    if not bd.get("confound_coverage", True):
        conf = [w for w in lint.get("warnings", []) if "负对照" in w or "混淆" in w]
        issues.append(Finding(loc=loc,
                              issue="因果/贡献声明缺负对照/混淆控制:" + ("；".join(conf[:3]) or "见 plan_lint"),
                              fix="做因果/贡献声明的行配负对照(如随机标签)+ 同等调参预算,排除替代解释",
                              rule="ablation_isolation.no_control"))
    if issues:
        return GateResult("ablation_isolation", "warn", "major", issues,
                          note="消融不隔离贡献(warn,spec §4.2 不阻断;但归因不干净是顶会审稿质疑点)。")
    return GateResult("ablation_isolation", "pass", "info", [],
                      note=f"消融覆盖 + 负对照齐(plan_lint 严谨性 {lint.get('rigor_score','?')}/100)。")


def _power_gate_fn(art: dict) -> "GateResult":
    """统计功效门(warn):据效应量 + 种子/重复数 + 多重比较校正判欠功效(非 critical,可加种子修)。"""
    rep = art["power"]
    loc = f"{art['project']}:statistical_power"
    if rep is None:
        return GateResult("statistical_power", "skip", "info", [],
                          note="未提供功效参数(power.effect_size):统计功效检查跳过。")
    if "adequate" not in rep:    # 只反推 min_n、没给 n_seeds
        return GateResult("statistical_power", "warn", "minor",
                          [Finding(loc=loc,
                                   issue=f"未声明每组种子/重复数(n_seeds):达 power {rep['target_power']} "
                                         f"需每组 ≥{rep['min_n_for_target']} 次(d={rep['effect_size']})",
                                   fix=f"实验矩阵种子数填 ≥{rep['min_n_for_target']}(power_check 反推值,别用默认5)",
                                   rule="statistical_power.unspecified")],
                          note="未声明重复数(warn):按 power_check 反推值填种子数。")
    if not rep["adequate"]:
        return GateResult(
            "statistical_power", "warn", "major",
            [Finding(loc=loc,
                     issue=f"欠功效:每组 {rep['n']} 次对 d={rep['effect_size']} 仅 power={rep['actual_power']}"
                           f"(<目标 {rep['target_power']};{rep.get('correction','none')} 校正后 "
                           f"α={rep.get('alpha_adjusted')})",
                     fix=f"种子/重复数加到 ≥{rep['min_n_for_target']}/组,或论文如实标算力受限的功效局限",
                     evidence=rep.get("verdict", ""), rule="statistical_power.underpowered")],
            note="欠功效(warn,可加种子修;非 critical)。功效依赖效应量 d 假设(诚实边界)。")
    return GateResult("statistical_power", "pass", "info", [],
                      note=f"每组 {rep['n']} 次达 power={rep['actual_power']}≥{rep['target_power']}(功效充足)。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装对照公平/可证伪 critical findings:港来矩阵 lint + 功效 + 显式声明 → 四 gate。"""
    project = str(spec.get("project", "unnamed"))
    lint = run_lint(spec)
    baselines = parse_baselines(spec.get("baselines"))
    hyps = parse_hypotheses(spec.get("hypotheses"))
    power = run_power(spec.get("power"))
    art = {"project": project, "lint": lint, "baselines": baselines,
           "hypotheses": hyps, "power": power}

    report = None
    if _SHARED_OK:
        report = run_gates(
            [_fair_baseline_gate_fn, _falsifiable_gate_fn,
             _ablation_gate_fn, _power_gate_fn],
            art, producer="research-plan", target=project,
            summary="research-plan 方案门:对照公平 + 可证伪(critical)+ 消融隔离 + 统计功效(warn)→ "
                    "对照不公平/不可证伪 → run_checkpoint --stage 5 exit 1(在 stage 5 内修复,无出边);"
                    "research-plan 是 7→5/13→5 回炉落点。",
            fresh_evidence=True)
    return {"project": project, "lint": lint, "baselines": baselines,
            "hypotheses": hyps, "power": power,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# research-plan 方案门(对照公平/可证伪):{result['project']}", ""]
    # baselines
    lines += ["## 对照公平 (fair_baseline, critical)", ""]
    if result["baselines"]:
        for b in result["baselines"]:
            lines.append(f"- {b['name']}:**{b['level']}** — {b['note'] or '(无说明)'}")
    else:
        lines.append("- (未声明任何对照公平性条件 → warn 须补)")
    # hypotheses
    lines += ["", "## 可证伪 (falsifiable, critical)", ""]
    if result["hypotheses"]:
        for h in result["hypotheses"]:
            tag = "✓有反证条件" if h["has_falsifier"] else "✗缺反证条件"
            q = "(可量化)" if h["falsifier_quant"] else ("(不可量化)" if h["has_falsifier"] else "")
            lines.append(f"- {h['id']}:{tag}{q} — {h['falsifier'][:48] or h['statement'][:48]}")
    else:
        lines.append("- (无可证伪假设 → critical)")
    # lint / power summary
    if result.get("lint") and not result["lint"].get("error"):
        L = result["lint"]
        lines += ["", f"## 消融隔离 (ablation_isolation, warn) — plan_lint 严谨性 "
                  f"{L.get('rigor_score','?')}/100",
                  f"- 消融覆盖={L['rigor_breakdown'].get('ablation_coverage')} "
                  f"负对照={L['rigor_breakdown'].get('confound_coverage')} "
                  f"多重比较族 K={L.get('n_hypothesis_tests')}"]
    if result.get("power"):
        p = result["power"]
        lines += ["", "## 统计功效 (statistical_power, warn)",
                  f"- {p.get('verdict','')}"]
    # findings
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=research-plan);"
                  f"run_checkpoint --stage 5 聚合,对照不公平/不可证伪→critical fail→exit 1"
                  f"(在 stage 5 内修复;research-plan 是 7→5/13→5 回炉落点)。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
# 复用的离线实验矩阵 fixture(plan_lint 可解析)
_MATRIX_WITH_ABL = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 已控混淆/负对照 | 完成判定 |
|--------|----------|--------|----------|------|-----------------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 | 同等调参预算 | top-1 > baseline 且 p<0.05 |
| ABL-01 | H1 | ImageNet | 移除模块X | top-1 | 随机标签负对照+同等调参预算 | top-1 下降 > 2% 证明模块X贡献 |
"""
_MATRIX_NO_ABL = """
| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 完成判定 |
|--------|----------|--------|----------|------|----------|
| EXP-01 | H1 | ImageNet | ResNet50 | top-1 | top-1 > baseline 且 p<0.05 |
| EXP-02 | H2 | CIFAR | VGG | top-1 | top-1 > baseline 且 p<0.05 |
"""
_FAIR_BL = [{"name": "ResNet50", "fairness": "ok:同数据同划分+等量调参预算(各200轮Optuna)+取当前SOTA实现"}]
_GOOD_HYP = [{"id": "H1", "statement": "模块X提升识别",
              "falsifier": "若 top-1 提升 < 2% 或 p >= 0.05 则 H1 被推翻"}]


def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 对照放水 → fair_baseline critical → verdict fail
    spec_unfair = {"project": "p1", "matrix": _MATRIX_WITH_ABL, "hypotheses": _GOOD_HYP,
                   "baselines": [{"name": "ResNet50",
                                  "fairness": "unfair:baseline 用默认超参未调,我方调了200轮"}],
                   "power": {"effect_size": 0.8, "n_seeds": 30}}
    r1 = build(spec_unfair)
    if _SHARED_OK:
        f = r1["findings"]
        check(f and f["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f["producer"] == "research-plan", f"producer 应为 research-plan,得 {f and f['producer']}")
        check(f["verdict"] == "fail", f"对照放水应整体 fail(critical),得 {f and f['verdict']}")
        fb = next(g for g in f["gates"] if g["gate"] == "fair_baseline")
        check(fb["status"] == "fail" and fb["severity"] == "critical", "对照放水应 critical fail")
        # 门名对齐 STAGE_GATES[5]=[fair_baseline,falsifiable]
        names = {g["gate"] for g in f["gates"]}
        check({"fair_baseline", "falsifiable"} <= names,
              f"门名应含 STAGE_GATES[5] 的 fair_baseline/falsifiable,得 {names}")
        rep = FindingsReport.from_json(json.dumps(f, ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1,
              "findings 应可往返且有阻断 gate")

    # 2. 不可证伪(假设缺反证条件)→ falsifiable critical → verdict fail
    spec_unfals = {"project": "p2", "matrix": _MATRIX_WITH_ABL, "baselines": _FAIR_BL,
                   "hypotheses": [{"id": "H1", "statement": "我的方法更好", "falsifier": ""}],
                   "power": {"effect_size": 0.8, "n_seeds": 30}}
    r2 = build(spec_unfals)
    if _SHARED_OK:
        f2 = r2["findings"]
        check(f2["verdict"] == "fail", f"不可证伪应整体 fail,得 {f2['verdict']}")
        fa = next(g for g in f2["gates"] if g["gate"] == "falsifiable")
        check(fa["status"] == "fail" and fa["severity"] == "critical",
              "假设缺反证条件应 critical fail")
        fb2 = next(g for g in f2["gates"] if g["gate"] == "fair_baseline")
        check(fb2["status"] == "pass", "公平 baseline 时对照门应 pass(与可证伪门独立)")

    # 3. 消融不隔离(矩阵无 ABL)→ ablation_isolation warn,整体 warn(无 critical)
    spec_noabl = {"project": "p3", "matrix": _MATRIX_NO_ABL, "baselines": _FAIR_BL,
                  "hypotheses": [{"id": "H1", "statement": "x", "falsifier": "top-1<2% 或 p>=0.05 推翻"},
                                 {"id": "H2", "statement": "y", "falsifier": "F1<3% 或 p>=0.05 推翻"}],
                  "power": {"effect_size": 0.8, "n_seeds": 30}}
    r3 = build(spec_noabl)
    if _SHARED_OK:
        f3 = r3["findings"]
        ab = next(g for g in f3["gates"] if g["gate"] == "ablation_isolation")
        check(ab["status"] == "warn" and ab["severity"] != "critical",
              f"无消融应 warn 非 critical,得 {ab['status']}/{ab['severity']}")
        check(f3["verdict"] == "warn", f"仅消融 warn 时整体应 warn(不阻断),得 {f3['verdict']}")

    # 4. 欠功效(d=0.5, n=5)→ statistical_power warn
    spec_pow = {"project": "p4", "matrix": _MATRIX_WITH_ABL, "baselines": _FAIR_BL,
                "hypotheses": _GOOD_HYP, "power": {"effect_size": 0.5, "n_seeds": 5}}
    r4 = build(spec_pow)
    check(r4["power"]["adequate"] is False, "d=0.5 n=5 应欠功效")
    if _SHARED_OK:
        f4 = r4["findings"]
        sp = next(g for g in f4["gates"] if g["gate"] == "statistical_power")
        check(sp["status"] == "warn" and sp["severity"] != "critical",
              f"欠功效应 warn 非 critical,得 {sp['status']}/{sp['severity']}")

    # 5. 全 ok → pass
    spec_ok = {"project": "p5", "matrix": _MATRIX_WITH_ABL, "baselines": _FAIR_BL,
               "hypotheses": _GOOD_HYP, "power": {"effect_size": 0.8, "n_seeds": 30}}
    r5 = build(spec_ok)
    if _SHARED_OK:
        f5 = r5["findings"]
        check(f5["verdict"] == "pass", f"公平+可证伪+有消融+功效足应 pass,得 {f5['verdict']}")

    # 6. 无 matrix / 无 power → 对应门 skip(不静默当 pass)
    r6 = build({"project": "p6", "baselines": _FAIR_BL, "hypotheses": _GOOD_HYP})
    if _SHARED_OK:
        ab6 = next(g for g in r6["findings"]["gates"] if g["gate"] == "ablation_isolation")
        sp6 = next(g for g in r6["findings"]["gates"] if g["gate"] == "statistical_power")
        check(ab6["status"] == "skip", f"无矩阵 → 消融门 skip,得 {ab6['status']}")
        check(sp6["status"] == "skip", f"无功效参数 → 功效门 skip,得 {sp6['status']}")

    # 7. 未声明 baseline → fair_baseline warn(须补,不静默放行也不编造放水)
    r7 = build({"project": "p7", "matrix": _MATRIX_WITH_ABL, "hypotheses": _GOOD_HYP})
    if _SHARED_OK:
        fb7 = next(g for g in r7["findings"]["gates"] if g["gate"] == "fair_baseline")
        check(fb7["status"] == "warn" and fb7["severity"] != "critical",
              f"未声明对照应 warn 非 critical,得 {fb7['status']}/{fb7['severity']}")

    # 8. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应诚实为 None")

    # 9. markdown 不崩 + 含方案门标题
    check("方案门" in to_markdown(r1), "markdown 应含方案门标题")

    if failures:
        print("[SELFTEST][plan_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][plan_gate] OK:对照放水 critical + 不可证伪 critical + 消融不隔离 warn + "
          "欠功效 warn + 全 ok pass + 无矩阵/功效 skip + 未声明对照 warn + findings(research-plan) 全通过"
          + ("" if _SHARED_OK else "(_shared 不可达,findings 走诚实降级路径)") + "。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="research-plan 对照公平/可证伪 Critical 门 producer(不公平/不可证伪→critical→stage 5 内修复)")
    ap.add_argument("--spec", help="方案 spec JSON(project/matrix(_file)/hypotheses/baselines/power)")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整方案门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.spec:
        ap.error("需要 --spec plan_spec.json(或 --selftest)")

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    result = build(spec)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整方案门 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    # critical fail → 退出码 1(与 run_checkpoint 同口径,便于单独跑也能确定性阻断)
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
