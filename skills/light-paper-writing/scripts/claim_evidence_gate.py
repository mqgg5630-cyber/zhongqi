#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_evidence_gate.py — paper-writing 的**claim 必有证据(诚信门)/ 过度宣称门 producer**。

蓝图 §4.3-8 的「及格线」:论文写作围绕"如何让审稿人相信值得发表"组织——**每个 claim 都有证据、
措辞强度匹配证据强度、绝不过度宣称**。本脚本把这条编排成机读 `light.findings.v1`(producer=**paper-writing**)。
门名对齐 `STAGE_GATES[8]=[claim_evidence, overclaim]`(spec §4.2):

  ① **claim_evidence(claim 无证据/诚信门)= critical**:草稿做强断言(SOTA/demonstrate/证明/显著优于…),
     但该句未登记、未绑定自己的 evidence claim ID、绑定不存在或只绑定 grade=none →
     这是 claiming benefit with no support(Boutron spin 第三型 + ACL R3"claim 须有证据或标推测"
     的反例)→ 阻断 → 被总控 `run_checkpoint --stage 8` 聚合 **exit 1**。issue 带「claim/证据/支撑」信号 →
     `reroute --stage 8` 命中 `ROUTES[8]` 建议 **8→7**(回 result-analysis 补证据;若该结论实验根本没产出
     则改 **8→6** 回 experiment-coding)。**paper-writing 是 8→7/8→6 回边发起方。**
  ② **overclaim(过度宣称)= warn**(spec §4.2 列在 warn 列):有证据档(weak+)时,正文措辞强于该档 →
     自检软化提示。**真正的 critical 措辞红线在 research-ethics 交付门**(`claim_evidence_bind` 的
     `conclusion_overclaim`),两套严重度、两语境,**非两套 lint**。
  ③ **result_card_guardrail=critical/warn**:实证 claim 必须消费 result-analysis 的 result-card
     decision/language/guardrail claim_impact；缺 result-card、REVISION_REQUIRED/UNKNOWN、guardrail FAIL/UNKNOWN、
     或 WARN 未写 limitations 都会阻断写作。
  ④ **claim_traceability=warn**:locator/source locator 缺失时提示补真实 provenance，不扩 blocking 面。
  ⑤ **contribution_consistency(贡献三处不一致)= warn**:复用同目录港来 `contribution_consistency`
     抽 abstract/intro/conclusion 贡献句比数字/强度/覆盖漂移。**跨材料/跨阶段一致性归 C2 consistency,不重造。**

这是 **v2 净新增的接线**(与 result-analysis `stat_rigor_gate`、experiment-coding `repro_gate`、research-plan
`plan_gate`、data-engineering `data_feasibility_gate`、idea 侧 `fatal_flaw_gate` 同构):**编排 _shared 措辞引擎 +
同目录港来件 → critical findings producer**,**不重造措辞档**——
  - 措辞↔证据:**直接消费 `_shared/evidence_contract`** 的 `lint_wording`(超档检测,中英双语 + 否定守卫 +
    GRADE 词表)/ `grade_evidence` / `allowed_verb_tier`。同目录 `claim_binding.py` 用
    `light.paper_claims.v1` 把当前 draft_sha256 + 每个精确 draft claim 绑定到自己的 evidence claim_id；旧稿 hash、
    未登记强断言、未知 evidence ID、或只绑定 none 档都进入 claim_evidence critical。**不再用整份证据的最高档兜底全文。**
  - 贡献一致:复用同目录港来 `contribution_consistency.check_consistency`(挂 `_shared/semantic_sim`)。
  - 证据档:消费 result-analysis emit 的 `evidence_strength.json`(light.evidence_strength.v1)。

诚实约定(名实对齐见 SKILL,铁律 2):
- **机检措辞 ≠ 证明无夸大**:lint 抓"措辞档>证据档 / 强断言无证据档"的**形态**;**逻辑薄弱、创新够不够、
  论证是否充分的终判仍需人/审稿人**。`--claim-map` 采用精确 text span + evidence claim_id，
  能证明绑定关系但不能证明科学结论为真；未提供 claim map 时，强断言 fail closed，不让无关最高档兜底。
- **claim_evidence 核"证据有无/强度"非"证据真伪"**:只核"作者给没给证据档、措辞配不配那个档",**不核结论
  对不对**(那要复现/同行)。与 SciFact(核 claim 真假)不同。
- **overclaim 在 stage 8 是 warn**(spec §4.2):critical 措辞红线是 research-ethics 交付门(`conclusion_overclaim`)。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  python claim_evidence_gate.py --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json --report claim_findings.json
  python claim_evidence_gate.py --draft draft.md            # 无证据文件:每条强断言=诚信门 critical
  python claim_evidence_gate.py --text "We achieve SOTA." --json-out out.json
  python claim_evidence_gate.py --selftest

spec(也可 --spec spec.json 一把传):
  {"project":"goat-estrus","draft":"<草稿正文或路径>","evidence":"<evidence_strength.json 路径>",
   "claim_map":"<light.paper_claims.v1 路径>"}
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

# 同目录港来的纯工具(复用不重造:贡献三处一致)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import contribution_consistency as cc      # noqa: E402
    _HAS_CC = True
except Exception:
    _HAS_CC = False
try:
    import claim_binding as cb                  # noqa: E402
    _HAS_BINDING = True
except Exception:
    _HAS_BINDING = False

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,治硬编码 parents[N] 之脆。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    from _shared import evidence_contract as ec                              # noqa: E402
    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False

_GRADE_ORDER = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}


# ───────────────────────── 证据档摘要（仅显示，不参与门判定） ─────────────────────────
def _best_grade(evidence: dict) -> str:
    """返回整份 evidence 的最强档，仅用于 CLI 摘要显示。"""
    claims = (evidence or {}).get("claims") or []
    if not claims:
        return None
    grades = []
    for c in claims:
        g = c.get("evidence_grade") or ec.grade_evidence(
            c.get("q_fdr"), c.get("effect_size"), c.get("ci95"), c.get("n"))
        grades.append(g)
    return max(grades, key=lambda g: _GRADE_ORDER.get(g, 0))

# ───────────────────────── 四个 gate 函数(接 _shared) ─────────────────────────
def _claim_evidence_gate(art: dict) -> "GateResult":
    """claim 必有自己的证据(critical):逐 claim 绑定，未登记也不放行。"""
    binding = art["binding"]
    errors = binding.get("coverage_errors") or []
    if not errors:
        n = len(binding.get("claims") or [])
        return GateResult(
            "claim_evidence", "pass", "info", [],
            note=f"逐 claim 证据覆盖通过(binding={binding.get('binding_mode')},claims={n});"
                 "每条 claim 只使用自己的 evidence_claim_ids，未登记强断言也已扫描。")
    finds = []
    for item in errors:
        finds.append(Finding(
            loc=item.get("locator") or f"{art['project']}:draft",
            issue="claim 无自己的证据支撑: " + item.get("message", ""),
            fix=item.get("suggestion") or
                "回 result-analysis(8→7)补该 claim 的证据；实验未产出则回 experiment-coding(8→6)；"
                "或删除/如实弱化。",
            evidence=("claim_id=" + str(item.get("claim_id") or "<unregistered>")
                      + ";evidence_claim_ids="
                      + ",".join(item.get("evidence_claim_ids") or [])),
            rule=item.get("code", "claim_evidence.unbacked")))
    return GateResult(
        "claim_evidence", "fail", "critical", finds,
        note="claim 无证据(critical,诚信门):逐 claim 绑定缺失/失效、draft_sha256 过期或强断言未登记。"
             "无关 claim 的 strong evidence 不能兜底；8→7/8→6 回炉仍是用户决策点。")


def _overclaim_gate(art: dict) -> "GateResult":
    """过度宣称(warn):只用每条 claim 自己绑定的证据档。"""
    binding = art["binding"]
    hits = binding.get("overclaims") or []
    if not hits:
        return GateResult("overclaim", "pass", "info", [],
                          note="已绑定 claim 的措辞未超过各自证据档；不使用全文最高档。")
    finds = []
    for v in hits:
        finds.append(Finding(
            loc=v.get("locator", "draft"),
            issue=v.get("message", "过度宣称"),
            fix=v.get("suggestion", "降级措辞或补更强证据") + "；交付前由 research-ethics 硬门复核",
            evidence=("claim_id=" + str(v.get("claim_id") or "")
                      + ";evidence_claim_ids=" + ",".join(v.get("evidence_claim_ids") or [])),
            rule=v.get("code", "overclaim.wording_exceeds_evidence")))
    return GateResult("overclaim", "warn", "major", finds,
                      note="过度宣称(warn,spec §4.2 不阻断):措辞强于证据档。写作时软化;**critical 措辞红线"
                           "是 research-ethics 交付门**(conclusion_overclaim)——共用同一 evidence_contract.lint_wording,"
                           "两语境、非两套。")


def _result_card_guardrail_gate(art: dict) -> "GateResult":
    """结果卡/guardrail 交接门:防止 result-analysis 的限制在写作阶段丢失。"""
    binding = art["binding"]
    errors = binding.get("result_card_errors") or []
    warnings = binding.get("guardrail_warnings") or []
    if errors:
        finds = [
            Finding(
                loc=item.get("locator", "claim-map"),
                issue=item.get("message", ""),
                fix=item.get("suggestion", "补 result-card locator/hash/decision/guardrail claim_impact 后重跑。"),
                evidence=("claim_id=" + str(item.get("claim_id") or "")
                          + ";evidence_claim_ids="
                          + ",".join(item.get("evidence_claim_ids") or [])),
                rule=item.get("code", "result_card.guardrail"))
            for item in errors
        ]
        return GateResult(
            "result_card_guardrail", "fail", "critical", finds,
            note="result-card/guardrail 交接失败(critical):实证 claim 必须带固定版本 result card，"
                 "且 decision=CLAIM_READY；guardrail FAIL/UNKNOWN 或 WARN 未限制 claim 不得进入论文写作。")
    if warnings:
        finds = [
            Finding(
                loc=item.get("locator", "claim-map"),
                issue=item.get("message", ""),
                fix=item.get("suggestion", "保留限制性措辞并在 Discussion/Limitations 呼应 guardrail。"),
                evidence=("claim_id=" + str(item.get("claim_id") or "")
                          + ";evidence_claim_ids="
                          + ",".join(item.get("evidence_claim_ids") or [])),
                rule=item.get("code", "result_card.guardrail_limited_claim"))
            for item in warnings
        ]
        return GateResult(
            "result_card_guardrail", "warn", "major", finds,
            note="guardrail WARN 已进入 claim plan：只允许限制性 claim；交付前仍需人工确认措辞与局限。")
    return GateResult(
        "result_card_guardrail", "pass", "info", [],
        note="已消费 result-card decision/language/guardrail 摘要；guardrail/counter-metric 未在写作阶段丢失。")


def _claim_traceability_gate(art: dict) -> "GateResult":
    """来源定位缺失只 warn；它不扩 stage-8 blocking 面。"""
    warnings = art["binding"].get("traceability_warnings") or []
    if not warnings:
        return GateResult(
            "claim_traceability", "pass", "info", [],
            note="claim 的 draft locator/source locator 齐全；run provenance 仍以真实上游工件为准。")
    finds = [
        Finding(
            loc=item.get("locator", "claim-map"),
            issue=item.get("message", ""),
            fix="补真实 source locator（artifact/path + claim_id/field；有则再加 run/commit/hash），"
                "不得凭空制造 provenance。",
            evidence="claim_id=" + str(item.get("claim_id") or ""),
            rule=item.get("code", "claim_traceability.missing"))
        for item in warnings
    ]
    return GateResult(
        "claim_traceability", "warn", "minor", finds,
        note="来源定位不完整(warn，不扩大 blocking 面)：evidence_strength 缺完整 run provenance 时，"
             "由 light.paper_claims.v1 的 source_locators 保留真实指针。")


def _contribution_consistency_gate(art: dict) -> "GateResult":
    """贡献三处不一致(warn):复用同目录港来 contribution_consistency(单稿内自检;跨材料归 C2)。"""
    draft = art["draft"]
    if not _HAS_CC:
        return GateResult("contribution_consistency", "skip", "info", [],
                          note="同目录 contribution_consistency 不可用:贡献三处一致门跳过。")
    rep = cc.check_consistency(draft)
    if not rep.get("sections_found"):
        return GateResult("contribution_consistency", "skip", "info", [],
                          note="未识别到 abstract/introduction/conclusion 标题:贡献三处一致门跳过"
                               "(给带这三节标题的完整草稿)。")
    issues = rep.get("issues") or []
    if not issues:
        return GateResult("contribution_consistency", "pass", "info", [],
                          note=f"abstract/intro/conclusion 贡献句数字/强度/覆盖一致(章节 {rep['sections_found']})。")
    finds = []
    for i in issues:
        finds.append(Finding(
            loc=i.get("loc", "draft"), issue=i.get("msg", ""),
            evidence=i.get("text", ""), rule=i.get("code", "contribution_drift")))
    sev = "major" if rep.get("by_severity", {}).get("major") else "minor"
    return GateResult("contribution_consistency", "warn", sev, finds,
                      note="贡献三处不一致(warn,spec §4.2 不阻断):abstract/intro/conclusion 贡献句漂移。"
                           "单稿内自检;**跨材料/跨阶段术语·指标·创新点一致性归 C2 consistency 常驻**,不重造。"
                           "启发式抽贡献句会漏/误报,不替代人读三处对齐。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装逐 claim 证据/措辞/来源 + 贡献一致性四门。"""
    project = str(spec.get("project", "unnamed"))
    draft = spec.get("draft") or ""
    evidence = spec.get("evidence")          # dict | None(已 load)
    claim_map = spec.get("claim_map")        # dict | None(已 load)
    binding = (cb.evaluate_bindings(draft, evidence, claim_map)
               if _HAS_BINDING and _SHARED_OK else {
                   "binding_mode": "unavailable", "claims": [],
                   "coverage_errors": [{
                       "code": "claim_binding.unavailable",
                       "claim_id": "",
                       "locator": f"{project}:claim-map",
                       "message": "claim_binding 模块不可用，不能证明逐 claim 证据覆盖。",
                       "evidence_claim_ids": [],
                       "suggestion": "修复本技能安装/导入后重跑；不得降级为全局最高证据档。",
                   }],
                   "overclaims": [],
                   "traceability_warnings": [],
                   "result_card_errors": [],
                   "guardrail_warnings": []})
    art = {"project": project, "draft": draft, "evidence": evidence,
           "claim_map": claim_map, "binding": binding,
           "best_grade": _best_grade(evidence) if _SHARED_OK else None}

    report = None
    if _SHARED_OK:
        report = run_gates(
            [_claim_evidence_gate, _overclaim_gate, _claim_traceability_gate,
             _result_card_guardrail_gate, _contribution_consistency_gate],
            art, producer="paper-writing", target=project,
            summary="paper-writing 写作门:claim 无证据(critical,诚信门→8→7)+ 过度宣称(warn,硬红线在 "
                    "research-ethics)+ result-card/guardrail 交接(critical)+ 贡献三处一致(warn,跨材料归 C2)"
                    "→ claim 无证据/guardrail 阻断 → run_checkpoint --stage 8 exit 1;"
                    "本技能是 8→7/8→6 回炉发起方。",
            fresh_evidence=True)

    return {"project": project, "best_grade": art["best_grade"],
            "has_evidence": evidence is not None,
            "binding_mode": binding.get("binding_mode"),
            "claim_count": len(binding.get("claims") or []),
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# paper-writing 写作门(claim 必有证据/过度宣称):{result['project']}", ""]
    lines.append(f"- 证据档:{'有 evidence_strength.json,全局最强档(仅信息)=' + str(result.get('best_grade')) if result.get('has_evidence') else '无 evidence_strength.json'}")
    lines.append(f"- claim 绑定:{result.get('binding_mode')}，登记 {result.get('claim_count', 0)} 条；"
                 "门判定只用逐 claim 绑定，不用全局最高档。")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=paper-writing);"
                  f"run_checkpoint --stage 8 聚合,claim 无证据→critical fail→exit 1;"
                  f"本技能是 8→7(claim 无证据回 result-analysis)/8→6(实现缺口回 experiment-coding)回炉发起方。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}  {g.get('note', '')[:60]}")
            for x in g.get("findings", [])[:4]:
                lines.append(f">       · {x['loc']}: {x['issue'][:80]}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    def claim_map(draft_text, *rows):
        return {
            "schema": cb.CLAIM_MAP_SCHEMA,
            "draft_sha256": cb.draft_sha256(draft_text),
            "claims": list(rows),
        }

    def result_card(status="PASS", decision="CLAIM_READY"):
        return {
            "claim_id": "c1",
            "locator": "analysis/result-card-c1.json",
            "sha256": "b" * 64,
            "decision": decision,
            "language_strength": "IMPROVES",
            "guardrail_summary": {
                "required": True,
                "status": status,
                "claim_impact": "允许主 claim，但需保留适用范围。",
                "evidence_locator": "analysis/guardrails.json#c1",
            },
        }

    def row(claim_id, text, evidence_id=None, line=1, *, rc=None, limitations=None):
        out = {
            "claim_id": claim_id,
            "text": text,
            "locator": f"draft.md:L{line}",
            "claim_type": "RESULT",
            "evidence_claim_ids": [evidence_id] if evidence_id else [],
            "source_locators": ([f"evidence_strength.json#{evidence_id}"]
                                if evidence_id else []),
        }
        if evidence_id:
            out["result_card"] = result_card() if rc is None else rc
        if limitations is not None:
            out["limitations"] = limitations
        return out

    # 1. claim 无证据(无 evidence 文件)+ 强断言 → claim_evidence critical(诚信门)→ 整体 fail
    r1 = build({"project": "p1",
                "draft": "We demonstrate state-of-the-art results and prove our method is superior."})
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f1["producer"] == "paper-writing", f"producer 应 paper-writing,得 {f1['producer']}")
        names = {g["gate"] for g in f1["gates"]}
        check({"claim_evidence", "overclaim", "result_card_guardrail"} <= names,
              f"门名应含 claim_evidence/overclaim/result_card_guardrail,得 {names}")
        ce = next(g for g in f1["gates"] if g["gate"] == "claim_evidence")
        check(ce["status"] == "fail" and ce["severity"] == "critical",
              "无证据 + 强断言应 claim_evidence critical")
        check(f1["verdict"] == "fail", f"claim 无证据应整体 fail,得 {f1['verdict']}")
        # 诚信门 issue 带 8→7 路由信号(claim/证据/支撑)
        blob = " ".join(x["issue"] + x.get("rule", "") for x in ce["findings"])
        check(any(s in blob for s in ("claim", "证据", "支撑")),
              f"claim_evidence issue 应带 8→7 路由信号(claim/证据/支撑),得:{blob[:80]}")
        # overclaim 门不抢 critical；逐 claim 绑定缺失由 claim_evidence 处理
        oc = next(g for g in f1["gates"] if g["gate"] == "overclaim")
        check(oc["status"] == "pass", f"无绑定可比时 overclaim 应 pass,得 {oc['status']}")

    # 2. claim 无证据(evidence 在档但全 none)+ 强断言 → claim_evidence critical
    ev_none = ec.build_evidence_json([
        {"claim_id": "c1", "text": "ours vs base", "q_fdr": 0.3, "effect_size": 0.1,
         "ci95": [-0.2, 0.4], "n": 50}]) if _SHARED_OK else None
    text2 = "Our method significantly outperforms all baselines."
    r2 = build({"project": "p2", "draft": text2, "evidence": ev_none,
                "claim_map": claim_map(text2, row("C2", text2, "c1"))})
    if _SHARED_OK:
        f2 = r2["findings"]
        ce2 = next(g for g in f2["gates"] if g["gate"] == "claim_evidence")
        check(ce2["status"] == "fail" and ce2["severity"] == "critical",
              "全 none 证据 + 强断言应 claim_evidence critical")
        check("c1" in " ".join(x.get("evidence", "") for x in ce2["findings"]),
              "证据应保留逐 claim evidence ID")

    # 3. 过度宣称(weak 证据 + 强措辞)→ overclaim warn(非 critical),claim_evidence pass
    ev_weak = ec.build_evidence_json([
        {"claim_id": "c1", "text": "ours vs base", "q_fdr": 0.03, "effect_size": 0.2,
         "ci95": [0.05, 0.4], "n": 200}]) if _SHARED_OK else None
    text3 = "Our method demonstrates a significant improvement, may help in practice."
    r3 = build({"project": "p3", "draft": text3, "evidence": ev_weak,
                "claim_map": claim_map(text3, row("C3", text3, "c1"))})
    if _SHARED_OK:
        f3 = r3["findings"]
        ce3 = next(g for g in f3["gates"] if g["gate"] == "claim_evidence")
        check(ce3["status"] == "pass", f"有 weak 证据档时 claim_evidence 应 pass,得 {ce3['status']}")
        oc3 = next(g for g in f3["gates"] if g["gate"] == "overclaim")
        check(oc3["status"] == "warn" and oc3["severity"] != "critical",
              f"weak 证据 + 强措辞应 overclaim warn 非 critical,得 {oc3['status']}/{oc3['severity']}")
        check(f3["verdict"] == "warn", f"仅过度宣称应整体 warn(不阻断),得 {f3['verdict']}")
        check(any(x["rule"] == "overclaim.wording_exceeds_evidence" for x in oc3["findings"]),
              "应命中 overclaim.wording_exceeds_evidence 规则")

    # 4. 干净:strong 证据 + 强措辞合规 → claim_evidence pass + overclaim pass → 整体非 fail
    ev_strong = ec.build_evidence_json([
        {"claim_id": "c1", "text": "ours vs base", "q_fdr": 0.001, "effect_size": 0.9,
         "ci95": [0.4, 1.3], "n": 120}]) if _SHARED_OK else None
    text4 = "We demonstrate a clear and reliable improvement."
    r4 = build({"project": "p4", "draft": text4, "evidence": ev_strong,
                "claim_map": claim_map(text4, row("C4", text4, "c1"))})
    if _SHARED_OK:
        f4 = r4["findings"]
        check(f4["verdict"] != "fail", f"strong 证据 + 合规措辞不应 fail,得 {f4['verdict']}")
        ce4 = next(g for g in f4["gates"] if g["gate"] == "claim_evidence")
        check(ce4["status"] == "pass", "strong 证据应 claim_evidence pass")

    # 5. 诚实 hedge 草稿(无证据但不做强断言)→ claim_evidence pass
    r5 = build({"project": "p5",
                "draft": "Our results may suggest a modest gain; we observed no significant difference on B."})
    if _SHARED_OK:
        ce5 = next(g for g in r5["findings"]["gates"] if g["gate"] == "claim_evidence")
        check(ce5["status"] == "pass", f"无证据但诚实 hedge 应 claim_evidence pass,得 {ce5['status']}")
        check(r5["findings"]["verdict"] != "fail", "诚实 hedge 草稿不应 fail")

    # 6. 贡献三处不一致 → contribution_consistency warn
    drift_draft = (
        "# Abstract\nWe propose a tracking method that improves accuracy by 3.1 points.\n"
        "We also propose a calibration module reducing error by 12 percent.\n"
        "# Introduction\nWe propose a tracking method for dense scenes.\n"
        "# Conclusion\nWe proposed a tracking method that may suggest improvements.\n")
    r6_rows = [
        row("C6a", "We propose a tracking method that improves accuracy by 3.1 points.", "c1", 2),
        row("C6b", "We also propose a calibration module reducing error by 12 percent.", "c1", 3),
        row("C6c", "We propose a tracking method for dense scenes.", "c1", 5),
        row("C6d", "We proposed a tracking method that may suggest improvements.", "c1", 7),
    ]
    r6 = build({"project": "p6", "draft": drift_draft, "evidence": ev_strong,
                "claim_map": claim_map(drift_draft, *r6_rows)})
    if _SHARED_OK and _HAS_CC:
        ccg = next(g for g in r6["findings"]["gates"] if g["gate"] == "contribution_consistency")
        check(ccg["status"] == "warn", f"贡献漂移应 contribution_consistency warn,得 {ccg['status']}")

    # 7. findings 往返 + 阻断 gate
    if _SHARED_OK:
        rep = FindingsReport.from_json(json.dumps(r1["findings"], ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1,
              "findings 应可往返且有阻断 gate")
        check(rep.producer == "paper-writing", "往返后 producer 仍 paper-writing")

    # 8. 中文草稿:无证据 + 强断言(证明/显著优于)→ claim_evidence critical
    r8 = build({"project": "p8", "draft": "本文首次证明该方法显著优于现有方案,全面超越基线。"})
    if _SHARED_OK:
        ce8 = next(g for g in r8["findings"]["gates"] if g["gate"] == "claim_evidence")
        check(ce8["status"] == "fail" and ce8["severity"] == "critical",
              "中文无证据强断言应 claim_evidence critical")

    # 9. 回归：A 有 strong，B 完全未登记；A 不能给 B 兜底
    text_a = "Claim A demonstrates a reliable improvement."
    text_b = "Claim B significantly outperforms every baseline."
    r9 = build({
        "project": "p9", "draft": text_a + "\n" + text_b,
        "evidence": ev_strong,
        "claim_map": claim_map(text_a + "\n" + text_b, row("C-A", text_a, "c1", 1)),
    })
    if _SHARED_OK:
        ce9 = next(g for g in r9["findings"]["gates"] if g["gate"] == "claim_evidence")
        check(ce9["status"] == "fail" and
              any(x["rule"] == "claim_binding.unregistered_assertion"
                  for x in ce9["findings"]),
              "strong evidence A 不得放过未登记的强断言 B")

    # 10. result-card/guardrail 交接:缺失、FAIL、WARN 无 limitation 均阻断；WARN+limitation 为 warn
    r10 = build({"project": "p10", "draft": text4, "evidence": ev_strong,
                 "claim_map": claim_map(text4, {
                     "claim_id": "C10", "text": text4, "locator": "draft.md:L1",
                     "claim_type": "RESULT",
                     "evidence_claim_ids": ["c1"],
                     "source_locators": ["evidence_strength.json#c1"],
                 })})
    if _SHARED_OK:
        rc10 = next(g for g in r10["findings"]["gates"] if g["gate"] == "result_card_guardrail")
        check(rc10["status"] == "fail" and rc10["severity"] == "critical",
              "缺 result-card handoff 应 result_card_guardrail critical")
    r11 = build({"project": "p11", "draft": text4, "evidence": ev_strong,
                 "claim_map": claim_map(text4, row("C11", text4, "c1", rc=result_card("FAIL")))})
    if _SHARED_OK:
        rc11 = next(g for g in r11["findings"]["gates"] if g["gate"] == "result_card_guardrail")
        check(rc11["status"] == "fail", "guardrail FAIL 应阻断写作")
    r12 = build({"project": "p12", "draft": text4, "evidence": ev_strong,
                 "claim_map": claim_map(text4, row("C12", text4, "c1", rc=result_card("WARN"),
                                                   limitations=["guardrail limits scope"]))})
    if _SHARED_OK:
        rc12 = next(g for g in r12["findings"]["gates"] if g["gate"] == "result_card_guardrail")
        check(rc12["status"] == "warn", f"guardrail WARN + limitations 应为 warn,得 {rc12['status']}")

    # 13. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 14. markdown 不崩
    check("写作门" in to_markdown(r1), "markdown 应含写作门标题")

    if failures:
        print("[SELFTEST][claim_evidence_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][claim_evidence_gate] OK:逐 claim 绑定 / strong A 不兜底未登记 B / "
          "无证据强断言 critical(诚信门,8→7 信号) / 全 none 证据 critical / "
          "过度宣称 warn(非 critical) / result-card guardrail critical / "
          "strong 合规 pass / 诚实 hedge pass / 贡献漂移 warn / "
          "中文强断言 critical / guardrail WARN 限制推进 / findings(paper-writing) 往返"
          + ("" if _SHARED_OK else "(_shared 不可达,走诚实降级)") + "。")
    return 0


def _load_draft(spec_draft: str) -> str:
    """draft 字段:是存在的文件路径 → 读文件;否则当作内联正文。"""
    if spec_draft and os.path.exists(spec_draft):
        with open(spec_draft, encoding="utf-8", errors="replace") as f:
            return f.read()
    return spec_draft or ""


def main() -> None:
    ap = argparse.ArgumentParser(
        description="paper-writing claim 必有证据/过度宣称 Critical 门 producer"
                    "(claim 无证据→critical→stage 8 exit 1;8→7/8→6 回炉发起方)")
    ap.add_argument("--spec", help="spec JSON(project/draft/evidence 一把传)")
    ap.add_argument("--draft", help="草稿 md 路径(或内联文本见 --text)")
    ap.add_argument("--text", help="内联草稿正文")
    ap.add_argument("--evidence", help="result-analysis 的 evidence_strength.json 路径")
    ap.add_argument("--claim-map", help="light.paper_claims.v1 路径（强断言逐条绑定自己的 evidence claim_id）")
    ap.add_argument("--project", default="unnamed")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整写作门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        spec["draft"] = _load_draft(spec.get("draft", ""))
        ev_path = spec.get("evidence")
        spec["evidence"] = ec.load(ev_path) if (ev_path and _SHARED_OK and os.path.exists(ev_path)) else None
        claim_map_path = spec.get("claim_map")
        spec["claim_map"] = (cb.load_claim_map(claim_map_path)
                             if (claim_map_path and _HAS_BINDING
                                 and os.path.exists(claim_map_path)) else None)
    else:
        if args.text is not None:
            draft = args.text
        elif args.draft:
            draft = _load_draft(args.draft)
        else:
            ap.error("需要 --spec 或 --draft/--text(或 --selftest)")
        evidence = None
        if args.evidence and _SHARED_OK and os.path.exists(args.evidence):
            evidence = ec.load(args.evidence)
        claim_map = None
        if args.claim_map and _HAS_BINDING and os.path.exists(args.claim_map):
            claim_map = cb.load_claim_map(args.claim_map)
        spec = {"project": args.project, "draft": draft, "evidence": evidence,
                "claim_map": claim_map}

    result = build(spec)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整写作门 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
