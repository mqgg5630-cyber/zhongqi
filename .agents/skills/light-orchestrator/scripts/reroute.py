#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reroute.py —— 根因回炉路由（Light v2 总控确定性引擎之三，对齐 orchestrator-spec §5）。

某确认点 `verdict==fail` 时，总控不"重来一遍"，而是**按根因定向回炉**：用
`FindingsReport.blocking_gates()` 拿到构成阻断的 gate，**映射到根因阶段**，提出"建议回边"。

本脚本是一个**纯函数 + CLI**：
  输入  一份 verdict==fail 的 light.findings.v1 报告 + 触发阶段序号（+ 可选 passport 查配额）
  输出  [(root_cause_stage, reason, evidence_ptr, carry, action)] + 返修配额检查结果

**只产建议，绝不执行**（铁律 / spec §2.2 §5）：
  回炉是**决策点**——回哪个根因 / 带病推进 / 转已知局限，押上数月方向，属 NEVER 红线
  "绝不静默回炉"。所以本脚本只给"推荐 + 理由 + 证据 + 备选"，把执行权留给用户；
  用户拍板后由 `passport.py add-back-edge` 落账（记回边 + 置 needs_rework）。

返修配额（spec §4.3）：根因阶段已用满 MAX_REVISION_ROUNDS（2）轮返修时，**不再提议回炉**，
  改建议"转已知局限如实记录"（known_limitation），不假装能修好。跨会话从台账读已用轮次。

诚实边界：
- 触发阶段/信号未命中路由表时，**不编造**回炉目标，给 action="manual"，请人工判断（铁律 2）。
- 信号分类是关键词启发式（会漏报/误报），故只"建议"，由用户确认；不替用户拍板。

用法：
  python reroute.py --findings report.json --stage 8 [--passport .light/passport.yaml] [--json]
  python reroute.py --selftest

依赖：纯 Python stdlib + 同目录 passport.py（查配额）+ _shared（FindingsReport，规范 bootstrap）。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from dataclasses import dataclass, field
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 同目录 passport.py（查返修配额、读台账，复用不重造）──
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import passport  # noqa: E402

# ── _shared 契约：规范 bootstrap（向上走目录树找含 _shared 包的仓库根，治硬编码之脆）──
try:
    _r = pathlib.Path(__file__).resolve()
    while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
        _r = _r.parent
    if not (_r / "_shared" / "__init__.py").exists():
        raise ImportError("向上未找到 _shared 包目录（请确保脚本在 Light-Skills 树内）")
    sys.path.insert(0, str(_r))
    from _shared.findings_schema import FindingsReport, GateResult  # noqa: E402
    _HAS_FINDINGS = True
except Exception:
    _HAS_FINDINGS = False

SCHEMA_REROUTE = "light.reroute.v1"

# 13 条主线技能（序号↔技能名，对齐 spec §3.1；index 0 占位）。
STAGES = [
    None,
    "literature-search", "data-engineering", "idea-generation", "idea-critique",
    "research-plan", "experiment-coding", "result-analysis", "paper-writing",
    "figure", "citation", "typesetting", "venue-matching", "review-rebuttal",
]


def stage_name(n) -> str:
    return STAGES[n] if isinstance(n, int) and 0 < n < len(STAGES) else f"stage-{n}"


@dataclass
class Route:
    """一条根因路由规则。signals 为空 = 该触发阶段的兜底（单根因触发）。"""
    signals: tuple           # 命中 gate 名 / finding.rule / finding.issue（子串，大小写无关）即匹配
    root_cause: int          # 根因阶段序号（回炉目标）
    reason: str              # 回炉理由（中文，进 back_edge.root_cause）
    carry: str               # 回炉带什么（呈现给用户的"修这个要带的证据"）
    kind: str = "back_edge"  # back_edge | admission_hold


# 触发阶段 → 路由规则（按顺序匹配：先具体信号、后兜底）。规范回边见 spec §5 表。
ROUTES = {
    # data-engineering 数据不够 → 拦在 idea 前（2⊣3）：idea-generation 前置读 data verdict
    2: [Route(("insufficient", "sample", "power", "功效", "数据不够", "样本", "不足"), 3,
              "数据不足以支撑 idea 所需统计功效（数据可行性前置于 idea 定稿）",
              "data verdict;不够则先补数据或改 idea（2⊣3 前置门）",
              kind="admission_hold")],
    # idea-critique 撞车/无创新（fatal flaw 一票否决）→ idea-generation（4→3）
    4: [Route((), 3, "idea 撞车 / 无创新（fatal flaw 一票否决）", "具体缺口 + 最像的前作")],
    # result-analysis：不可复现/bug → experiment-coding（7→6）；不支撑假设 → research-plan（7→5）
    7: [Route(("reproduc", "repro", "bug", "seed", "种子", "复现", "不可复现"), 6,
              "结果不可复现 / 实现 bug", "失败的复现证据（命令 + 期望 vs 实得）"),
        Route(("hypothesis", "support", "假设", "支撑", "效应", "显著"), 5,
              "结果不支撑假设", "哪条假设没撑住 + 对应的效应量/CI")],
    # paper-writing claim 无证据（诚信门）→ result-analysis（8→7），实现缺口则 8→6
    8: [Route((), 7, "claim 无证据（诚信门）",
              "哪条 claim 缺哪种证据（默认 8→7；若属实现/复现缺口则改 8→6）")],
    # figure 把不显著当主图 / 图文不一致 → result-analysis（9→7）。
    # 信号制(非兜底):只有 misrepresent_evidence(把不显著当主图/图文不一致,带这些信号)才回 7;
    # 截 y 轴/双 y 轴等画法不诚实(visual_honesty,不带信号)→ 不命中 → manual = 本阶段重画修
    # (同 result-analysis p-hacking→manual 的诚实落点:画法问题在 figure 内重画,非数据回炉)。
    9: [Route(("不显著", "图文不一致", "主图", "证据", "evidence", "insignific",
               "mismatch", "misrepresent"), 7,
              "图把不显著结果当主图 / 图文不一致", "该图对应的证据强度")],
    # review-rebuttal 拒稿按根因分流（13→3 创新 / 13→5 实验 / 13→8 写作）
    13: [Route(("innov", "novel", "创新", "新颖", "contribution", "贡献"), 3,
               "拒稿·创新性", "审稿人创新性质疑原文"),
         Route(("experiment", "baseline", "ablation", "实验", "对照", "消融", "复现"), 5,
               "拒稿·实验", "审稿人实验质疑原文"),
         Route(("writing", "clarity", "presentation", "写作", "表述", "可读"), 8,
               "拒稿·写作", "审稿人表述质疑原文")],
}


@dataclass
class Suggestion:
    """一条建议回边（不执行，供用户决策）。"""
    root_cause_stage: int
    root_cause_skill: str
    reason: str
    carry: str
    evidence_ptr: str
    gate: str
    action: str                      # rework | admission_hold | known_limitation | manual
    route_kind: str = "back_edge"
    revision_rounds_used: int = 0
    revision_rounds_max: int = passport.MAX_REVISION_ROUNDS
    quota_note: str = ""

    def to_dict(self) -> dict:
        return {
            "root_cause_stage": self.root_cause_stage,
            "root_cause_skill": self.root_cause_skill,
            "reason": self.reason,
            "carry": self.carry,
            "evidence_ptr": self.evidence_ptr,
            "gate": self.gate,
            "action": self.action,
            "route_kind": self.route_kind,
            "revision_rounds_used": self.revision_rounds_used,
            "revision_rounds_max": self.revision_rounds_max,
            "quota_note": self.quota_note,
        }


@dataclass
class RerouteResult:
    """根因回炉建议结果（纯建议，decision_point=True 永真：执行权留用户）。"""
    trigger_stage: int
    verdict: str
    suggestions: List[Suggestion] = field(default_factory=list)
    decision_point: bool = True
    note: str = ("回炉是决策点：停下问用户（回哪个根因 / 带病推进并记录 / 转已知局限）。"
                 "本工具只产建议、不执行；用户拍板后由 passport add-back-edge 落账。")
    schema: str = SCHEMA_REROUTE

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "trigger_stage": self.trigger_stage,
            "trigger_skill": stage_name(self.trigger_stage),
            "verdict": self.verdict,
            "decision_point": self.decision_point,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "note": self.note,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _gate_text(g: "GateResult") -> str:
    """把一个 gate 的可匹配文本拼起来（gate 名 + 各 finding 的 rule/issue），小写。"""
    parts = [g.gate or ""]
    for f in g.findings:
        parts.append(f.rule or "")
        parts.append(f.issue or "")
    return " ".join(parts).lower()


def _match_route(trigger_stage: int, gate: "GateResult") -> Optional[Route]:
    """在触发阶段的路由规则里，先按信号命中、再退回兜底（signals 为空）。"""
    routes = ROUTES.get(trigger_stage)
    if not routes:
        return None
    text = _gate_text(gate)
    for r in routes:
        if r.signals and any(s.lower() in text for s in r.signals):
            return r
    for r in routes:
        if not r.signals:
            return r
    return None


def _evidence_ptr(producer: str, gate: "GateResult") -> str:
    """从阻断 gate 构造证据指针：producer:gate@首个 finding 定位（无则 gate 名）。
    这是"指向这次具体输出"的可核指针，供 add-back-edge 落账（总控可再叠 @ts）。"""
    loc = ""
    if gate.findings:
        locs = [f.loc for f in gate.findings if f.loc]
        loc = ",".join(locs[:3])
    head = f"{producer}:{gate.gate}" if producer else gate.gate
    return f"{head}@{loc}" if loc else f"{head}"


def suggest_reroute(report: "FindingsReport", trigger_stage: int,
                    passport_data: Optional[dict] = None) -> RerouteResult:
    """根因回炉路由（纯函数）：fail 报告 → 建议回边 + 配额检查。不执行任何回炉。

    - 只在 verdict==fail 时产建议（非 fail 直接返回空建议）。
    - 每个阻断 gate 映射到根因阶段；命不中路由表则 action="manual"（不编造目标）。
    - 根因阶段已用满返修配额 → action="known_limitation"（转已知局限），不再提议回炉。
    """
    verdict = report.compute_verdict()
    result = RerouteResult(trigger_stage=trigger_stage, verdict=verdict)
    if verdict != "fail":
        return result  # 无阻断,无需回炉

    seen = set()  # 去重:同一根因阶段只建议一次(取第一个命中的 gate 作证据)
    for g in report.blocking_gates():
        route = _match_route(trigger_stage, g)
        ev = _evidence_ptr(report.producer, g)
        if route is None:
            key = ("manual", g.gate)
            if key in seen:
                continue
            seen.add(key)
            result.suggestions.append(Suggestion(
                root_cause_stage=-1, root_cause_skill="(待人工判断)",
                reason=f"触发阶段 {trigger_stage}({stage_name(trigger_stage)}) / 信号未命中"
                       f"路由表，无法自动定位根因",
                carry="请人工判断回炉目标（不编造）",
                evidence_ptr=ev, gate=g.gate, action="manual"))
            continue
        if route.root_cause in seen:
            continue
        seen.add(route.root_cause)
        used = (passport.revision_rounds_used(passport_data, route.root_cause)
                if passport_data else 0)
        if route.kind == "admission_hold":
            action = "admission_hold"
            qnote = ("2⊣3 是进入 stage 3 前的 admission hold，不是回边；"
                     "不得调用 add-back-edge。补数据或由用户改 idea 后重跑 stage 2。")
        elif used >= passport.MAX_REVISION_ROUNDS:
            action = "known_limitation"
            qnote = (f"根因阶段 {route.root_cause}({stage_name(route.root_cause)}) 已用满 "
                     f"{used}/{passport.MAX_REVISION_ROUNDS} 轮返修配额：建议转已知局限如实记录，"
                     f"不再回炉（spec §4.3）")
        else:
            action = "rework"
            qnote = f"返修配额 {used}/{passport.MAX_REVISION_ROUNDS}，可回炉"
        result.suggestions.append(Suggestion(
            root_cause_stage=route.root_cause,
            root_cause_skill=stage_name(route.root_cause),
            reason=route.reason, carry=route.carry,
            evidence_ptr=ev, gate=g.gate, action=action,
            route_kind=route.kind,
            revision_rounds_used=used, quota_note=qnote))
    return result


def render(res: RerouteResult) -> str:
    """人读渲染：建议回边表 + 决策点提示。"""
    L = [f"# 根因回炉建议 — 触发阶段 {res.trigger_stage}"
         f"（{stage_name(res.trigger_stage)}）", ""]
    if res.verdict != "fail":
        L.append(f"- 整体裁定：**{res.verdict}**，无阻断 → 无需回炉。")
        return "\n".join(L)
    if not res.suggestions:
        L.append("- verdict=fail 但无可路由的阻断 gate（异常，请核对报告）。")
        return "\n".join(L)
    L.append("- 整体裁定：**⛔ fail** → 以下为**建议回边**（决策点，停下问用户，不自动回）：")
    L.append("")
    L.append("| 根因阶段 | 回炉动作 | 理由 | 回炉带什么 | 证据指针 | 配额 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for s in res.suggestions:
        act = {"rework": "↩ 建议回炉", "admission_hold": "⏸ 阻止进入下一阶段",
               "known_limitation": "📌 转已知局限",
               "manual": "❓ 人工判断"}.get(s.action, s.action)
        tgt = (f"{s.root_cause_stage} {s.root_cause_skill}"
               if s.root_cause_stage > 0 else s.root_cause_skill)
        L.append(f"| {tgt} | {act} | {s.reason} | {s.carry} | `{s.evidence_ptr}` | "
                 f"{s.revision_rounds_used}/{s.revision_rounds_max} |")
    L.append("")
    has_kl = any(s.action == "known_limitation" for s in res.suggestions)
    if has_kl:
        L.append("> 📌 有根因阶段返修配额已耗尽：**不再提议回炉**，建议转已知局限如实记录"
                 "（spec §4.3，不假装修好）。")
    if any(s.action == "admission_hold" for s in res.suggestions):
        L.append("> ⏸ admission hold 只阻止进入下游；它不是 back-edge，禁止写 "
                 "`passport add-back-edge`。")
    L.append(f"> 🧑 {res.note}")
    if any(s.action == "rework" for s in res.suggestions):
        L.append("> 用户确认真实回炉后落账：`python passport.py add-back-edge --to <根因> "
                 "--from <触发> --root-cause \"<理由>\" --evidence-ptr <指针> "
                 "--authorization-id <用户授权记录>`")
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def _mk_report(producer, target, gate, status, severity, findings):
    """合成一份单 gate 的 FindingsReport。"""
    from _shared.findings_schema import Finding, GateResult as GR, FindingsReport as FR
    grs = [GR(gate, status, severity,
              [Finding(loc, iss, fix, rule=rule) for (loc, iss, fix, rule) in findings])]
    return FR(producer=producer, target=target, gates=grs).finalize()


def _selftest() -> int:
    assert _HAS_FINDINGS, "_shared/findings_schema 必须可导入（规范 bootstrap 失败？）"
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")

    # 1. stage 8 claim 无证据 → 建议回 7（result-analysis），action=rework，带证据指针
    rep = _mk_report("paper-writing", "draft.md", "claim_evidence", "fail", "critical",
                     [("draft.md:42", "claim 'SOTA' 无实验支撑", "补证据或降级措辞",
                       "claim_evidence")])
    res = suggest_reroute(rep, trigger_stage=8)
    s = res.suggestions[0]
    check(res.verdict == "fail" and res.decision_point is True, "fail 报告 → decision_point=True")
    check(s.root_cause_stage == 7 and s.root_cause_skill == "result-analysis",
          f"claim 无证据 → 回 7 result-analysis（得 {s.root_cause_stage}）")
    check(s.action == "rework", "配额未耗尽 → action=rework")
    check("draft.md:42" in s.evidence_ptr and "claim_evidence" in s.evidence_ptr,
          f"证据指针含定位+gate（得 {s.evidence_ptr}）")

    # 2. 配额耗尽 → 转已知局限（不再回炉）
    pp = {"schema": passport.SCHEMA_PASSPORT, "project": "p", "pipeline": "A",
          "created": "x", "updated": "x", "current_stage": 7,
          "stages": [{"stage": 7, "skill": "result-analysis", "input": "i", "output": "o",
                      "artifacts": ["res.md"], "revision_rounds": 2}]}
    res2 = suggest_reroute(rep, trigger_stage=8, passport_data=pp)
    s2 = res2.suggestions[0]
    check(s2.action == "known_limitation",
          f"根因阶段返修满 2 轮 → known_limitation（得 {s2.action}）")
    check("转已知局限" in s2.quota_note and s2.revision_rounds_used == 2,
          "配额备注说明转已知局限 + used=2")
    check("转已知局限" in render(res2), "render 提示转已知局限")

    # 2b. stage 2 数据不足是 admission hold，不是非法 2→3 "回边"
    rep_hold = _mk_report("data-engineering", "data.json", "data_feasibility",
                          "fail", "critical",
                          [("data:sample", "insufficient sample power / 样本不足",
                            "补数据或改 idea", "sample_power")])
    hold = suggest_reroute(rep_hold, trigger_stage=2).suggestions[0]
    check(hold.action == "admission_hold" and hold.route_kind == "admission_hold"
          and hold.root_cause_stage == 3,
          "2⊣3 → admission_hold（不伪造成 back-edge）")

    # 3. stage 4 撞车/无创新 → 回 3（idea-generation）
    rep3 = _mk_report("idea-critique", "ideas.md", "semantic_sim", "fail", "critical",
                      [("idea:2", "与 Smith2023 高度撞车（near-duplicate）", "换角度或找新缺口",
                        "collision")])
    res3 = suggest_reroute(rep3, trigger_stage=4)
    check(res3.suggestions[0].root_cause_stage == 3,
          f"撞车 → 回 3 idea-generation（得 {res3.suggestions[0].root_cause_stage}）")

    # 4. stage 13 拒稿按根因分流：创新→3 / 实验→5 / 写作→8
    rep_inv = _mk_report("review-rebuttal", "reviews.md", "reviewer_classify", "fail",
                         "critical", [("r1", "审稿人质疑 novelty / 创新性不足", "回 idea",
                                       "innovation")])
    rep_exp = _mk_report("review-rebuttal", "reviews.md", "reviewer_classify", "fail",
                         "critical", [("r2", "baseline 不公平 / 实验质疑", "补实验", "experiment")])
    rep_wri = _mk_report("review-rebuttal", "reviews.md", "reviewer_classify", "fail",
                         "critical", [("r3", "presentation / 写作表述不清", "改写", "writing")])
    check(suggest_reroute(rep_inv, 13).suggestions[0].root_cause_stage == 3, "拒稿·创新→3")
    check(suggest_reroute(rep_exp, 13).suggestions[0].root_cause_stage == 5, "拒稿·实验→5")
    check(suggest_reroute(rep_wri, 13).suggestions[0].root_cause_stage == 8, "拒稿·写作→8")

    # 5. stage 7：不可复现→6；不支撑假设→5（同阶段双信号分流）
    rep_repro = _mk_report("result-analysis", "res.md", "reproducible", "fail", "critical",
                           [("run.py", "种子未固定，复现失败", "固定种子重跑", "reproducible")])
    rep_hyp = _mk_report("result-analysis", "res.md", "stat_validity", "fail", "critical",
                         [("res.md:7", "主假设 H1 未被结果支撑", "回方案", "hypothesis_support")])
    check(suggest_reroute(rep_repro, 7).suggestions[0].root_cause_stage == 6, "不可复现→6")
    check(suggest_reroute(rep_hyp, 7).suggestions[0].root_cause_stage == 5, "不支撑假设→5")

    # 5a. stage 3 没有自指 route；未命中时 manual，绝不生成 3→3。
    rep_stage3 = _mk_report("idea-generation", "ideas.md", "frame_lock",
                            "fail", "critical",
                            [("idea:1", "frame lock", "人工复核", "frame_lock")])
    s3 = suggest_reroute(rep_stage3, 3).suggestions[0]
    check(s3.action == "manual" and s3.root_cause_stage == -1,
          "stage 3 无 3→3 自指 route")

    # 5b. stage 9（figure 信号制,非兜底）:把不显著当主图(带信号)→9→7;截/双轴画法不诚实(不带信号)→manual
    rep_misrep = _mk_report("figure", "F1", "misrepresent_evidence", "fail", "critical",
                            [("F1", "把不显著结果当主图:主图绑定 claim 证据档=none(图文不一致)",
                              "回 result-analysis 核证据强度",
                              "misrepresent_evidence.insignificant_as_main")])
    rep_vishon = _mk_report("figure", "plot.py", "visual_honesty", "fail", "critical",
                            [("plot:L4", "视觉不诚实:y 轴截断(起点非 0 且无断轴标注)——夸大组间高度差",
                              "本阶段重画零基线/断轴标注", "visual_honesty.axis_truncate")])
    s_misrep = suggest_reroute(rep_misrep, 9).suggestions[0]
    check(s_misrep.root_cause_stage == 7 and s_misrep.action == "rework",
          f"figure 把不显著当主图(带信号)→ 9→7 result-analysis（得 {s_misrep.root_cause_stage}）")
    s_vishon = suggest_reroute(rep_vishon, 9).suggestions[0]
    check(s_vishon.action == "manual" and s_vishon.root_cause_stage == -1,
          f"figure 截 y 轴(画法不诚实,不带信号)→ manual 本阶段重画（得 {s_vishon.action}）")

    # 6. 不可路由（信号/阶段未命中）→ action=manual，不编造目标（铁律 2）
    rep_unk = _mk_report("venue-matching", "venue.md", "mystery_gate", "fail", "critical",
                         [("x", "未知阻断", "?", "mystery")])
    res_unk = suggest_reroute(rep_unk, trigger_stage=12)
    check(res_unk.suggestions[0].action == "manual"
          and res_unk.suggestions[0].root_cause_stage == -1,
          "未命中路由 → manual（不编造回炉目标）")

    # 7. 非 fail 报告 → 无建议（reroute 只对 fail 动作）
    rep_ok = _mk_report("paper-writing", "draft.md", "style", "warn", "minor",
                        [("draft.md:3", "措辞偏口语", "改正式", "style")])
    res_ok = suggest_reroute(rep_ok, trigger_stage=8)
    check(res_ok.verdict == "warn" and not res_ok.suggestions, "warn 报告 → 无回炉建议")

    # 8. JSON 可序列化 + schema 正确
    d = json.loads(res.to_json())
    check(d["schema"] == SCHEMA_REROUTE and d["decision_point"] is True
          and d["suggestions"][0]["root_cause_stage"] == 7, "结果 JSON 可序列化且字段正确")

    # 9. 决策点恒真:never 自动执行(本脚本无任何写台账/回炉副作用)
    check(all(suggest_reroute(r, ts).decision_point
              for (r, ts) in [(rep, 8), (rep3, 4), (rep_repro, 7)]),
          "所有建议 decision_point 恒为 True（只建议不执行）")

    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="根因回炉路由：fail 报告 → 建议回边 + 配额检查（只建议不执行）")
    ap.add_argument("--findings", help="一份 light.findings.v1 报告文件（verdict 通常为 fail）")
    ap.add_argument("--stage", type=int, help="触发阶段序号（门 fail 处）")
    ap.add_argument("--passport", help="passport 台账路径（查根因阶段返修配额，可选）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON（默认人读 md）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not _HAS_FINDINGS:
        print("[reroute] 致命：_shared/findings_schema 不可导入，无法解析报告。"
              "请确保脚本在 Light-Skills 树内（规范 bootstrap）。", file=sys.stderr)
        return 2
    if not args.findings or args.stage is None:
        ap.error("需要 --findings FILE 与 --stage N（或 --selftest）")

    with open(args.findings, encoding="utf-8") as fh:
        report = FindingsReport.from_dict(json.load(fh))
    passport_data = None
    if args.passport and os.path.exists(args.passport):
        passport_data = passport.load(args.passport)

    res = suggest_reroute(report, args.stage, passport_data)
    print(res.to_json() if args.json else render(res))
    # 建议性脚本:始终 exit 0(确定性阻断由 run_checkpoint 负责,回炉决策由用户负责)。
    return 0


if __name__ == "__main__":
    sys.exit(main())
