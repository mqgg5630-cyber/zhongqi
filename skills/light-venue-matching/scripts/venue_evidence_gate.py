#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""venue_evidence_gate.py — venue_evidence.v2 多轴证据门（stage 12 warn/decision support）。

venue matching 的关键不是“算一个总分”，而是把 scope/article type/audience/format/cost/
timeline/trust/strategy 分轴暴露。UNKNOWN、403、429、付费墙、source 过期都不能被改写成
负面证据；真正硬阻断（类型不收、硬约束超限、deadline 无 timezone/已过、身份劫持冲突）
也不能被一个高综合分盖掉。

输入 schema:
  light.venue_evidence.v2
  {
    project, as_of, author_constraints,
    decision_point: true, chosen: null,
    candidates: [{venue_id,name,axes{scope,article_type,audience,format,cost,timeline,trust,strategy}}]
  }

输出 `light.findings.v1`（producer=venue-matching）。注意：stage 12 不是 orchestrator
critical gate；本脚本的 `FAIL` 表示候选/packet 不应进入“推荐给用户选择”的 decision packet，
不是自动回炉上游，也不代表投稿动作。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA_ID = "light.venue_evidence.v2"
REPORT_SCHEMA_ID = "light.venue_evidence.report.v2"
AXES = ("scope", "article_type", "audience", "format", "cost", "timeline", "trust", "strategy")
SOURCE_STATUSES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE", "CONFLICT"}
MATCH_STATUSES = {"MATCH", "PARTIAL", "MISMATCH", "UNKNOWN", "NOT_APPLICABLE"}
TRUST_STATUSES = {"OK", "WARN", "HIGH_RISK", "UNKNOWN", "UNAVAILABLE"}
TCS_SIGNAL_IDS = {
    "CONTACT_TRANSPARENCY", "EDITORIAL_BOARD", "PEER_REVIEW", "FEES_DISCLOSED",
    "OWNERSHIP_DISCLOSED", "INDEXING_CLAIMS", "ARCHIVING_POLICY", "AUTHOR_RIGHTS",
    "RETRACTION_POLICY", "PUBLISHING_TIMELINE", "SOLICITATION", "METRICS_CLAIMS",
    "WEBSITE_IDENTITY", "ISSN_IDENTITY", "SCOPE_CLARITY", "ETHICS_POLICY",
}


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "_shared" / "__init__.py").exists():
            return parent
    raise RuntimeError("cannot locate repository root containing _shared")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402


def _status(value: Any) -> str:
    return str(value or "").strip().upper()


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finding(loc: str, issue: str, fix: str, rule: str, evidence: str = "") -> Finding:
    return Finding(loc=loc, issue=issue, fix=fix, evidence=evidence or None, rule=rule)


def _as_of(spec: dict[str, Any]) -> dt.datetime | None:
    return _parse_time(spec.get("as_of"))


def _source_findings(axis: dict[str, Any], loc: str, axis_name: str, as_of: dt.datetime | None,
                     max_age_days: int) -> tuple[list[Finding], list[Finding]]:
    blockers: list[Finding] = []
    warns: list[Finding] = []
    source_status = _status(axis.get("source_status"))
    if source_status not in SOURCE_STATUSES:
        blockers.append(_finding(
            loc,
            f"{axis_name}.source_status={source_status!r} 非法或缺失",
            "改为 VERIFIED/UNKNOWN/UNAVAILABLE/STALE/CONFLICT；查不到就显式 UNKNOWN/UNAVAILABLE",
            f"{axis_name}.bad_source_status",
        ))
        return blockers, warns
    if source_status in {"UNKNOWN", "UNAVAILABLE"}:
        warns.append(_finding(
            loc,
            f"{axis_name} 来源为 {source_status}；不能当负面证据，也不能当已核实",
            "在 decision packet 中保留 unresolved 字段；投前刷新或让用户带未知决策",
            f"{axis_name}.source_unresolved",
            str(axis.get("failure_reason") or ""),
        ))
    if source_status == "CONFLICT":
        blockers.append(_finding(
            loc,
            f"{axis_name} 来源冲突；不能用单一来源硬定",
            "保留冲突源并人工核官方/权威索引；解决前不推荐该候选为 match",
            f"{axis_name}.source_conflict",
        ))
    retrieved = _parse_time(axis.get("retrieved_at"))
    if source_status == "VERIFIED":
        if not axis.get("locator"):
            blockers.append(_finding(loc, f"{axis_name} VERIFIED 但缺 locator", "补官方/权威来源 locator", f"{axis_name}.verified_without_locator"))
        if retrieved is None:
            blockers.append(_finding(loc, f"{axis_name} VERIFIED 但 retrieved_at 缺失或无时区", "补带时区 ISO-8601 检索时间", f"{axis_name}.retrieved_at_missing"))
        elif as_of and retrieved > as_of:
            blockers.append(_finding(
                loc,
                f"{axis_name} retrieved_at 晚于 as_of，属于未来证据",
                "把 as_of 设为实际运行时间，或重新记录不晚于 as_of 的检索时间",
                f"{axis_name}.retrieved_at_future",
            ))
        elif as_of and (as_of - retrieved).days > max_age_days:
            warns.append(_finding(
                loc,
                f"{axis_name} 来源年龄 {(as_of - retrieved).days} 天，超过 refresh policy {max_age_days} 天",
                "投前刷新动态字段；过期值不得写成当前事实",
                f"{axis_name}.source_stale",
            ))
    return blockers, warns


def _packet_gate(spec: dict[str, Any]) -> GateResult:
    findings: list[Finding] = []
    if _as_of(spec) is None:
        findings.append(_finding(
            "venue_packet:as_of",
            "as_of 必须是带时区的 ISO-8601 时间；否则无法判定 source age / valid-at",
            "补上本轮运行时间，例如 2026-07-04T12:00:00+08:00",
            "packet.as_of_missing_timezone",
        ))
    if spec.get("decision_point") is not True:
        findings.append(_finding(
            "venue_packet:decision_point",
            "decision_point 必须为 true；venue matching 是用户决策点",
            "保持 decision_point=true，直到用户明确选择或授权代理选择",
            "packet.decision_point_missing",
        ))
    if spec.get("chosen") not in (None, ""):
        findings.append(_finding(
            "venue_packet:chosen",
            "chosen 必须为 null；候选证据阶段不得提前选择 venue",
            "展示 decision packet 后停下问用户；选择只能来自 light.venue_user_selection.v1",
            "packet.chosen_before_user",
        ))
    if spec.get("aggregate_score") is not None:
        findings.append(_finding(
            "venue_packet:aggregate_score",
            "venue_evidence.v2 不允许用单一 aggregate_score 替代多轴决策",
            "删除总分；逐轴解释 scope/type/cost/timeline/trust/strategy",
            "packet.aggregate_score_forbidden",
        ))
    candidates = spec.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        findings.append(_finding("venue_packet:candidates", "candidates 为空", "至少给一个带证据轴的候选", "packet.no_candidates"))
    if findings:
        return GateResult("venue_decision_packet", "fail", "critical", findings,
                          note="decision packet 不能提前选择、不能用总分盖过多轴证据。")
    return GateResult("venue_decision_packet", "pass", "info", [],
                      note="packet 保持未选择状态，等待用户决策。")


def _candidate_gate(spec: dict[str, Any]) -> GateResult:
    as_of = _as_of(spec)
    constraints = spec.get("author_constraints") or {}
    max_age = int(spec.get("refresh_policy_days") or 30)
    blockers: list[Finding] = []
    warns: list[Finding] = []
    candidates = spec.get("candidates") if isinstance(spec.get("candidates"), list) else []

    for idx, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            blockers.append(_finding(f"candidates[{idx}]", "candidate 必须是 object", "改成结构化候选", "candidate.bad_type"))
            continue
        cid = cand.get("venue_id") or cand.get("name") or f"candidate[{idx}]"
        loc = f"venue:{cid}"
        axes = cand.get("axes") or {}
        missing_axes = [axis for axis in AXES if not isinstance(axes.get(axis), dict)]
        if missing_axes:
            blockers.append(_finding(
                loc,
                f"候选缺少证据轴：{missing_axes}",
                "逐轴补 scope/article_type/audience/format/cost/timeline/trust/strategy",
                "candidate.axes_missing",
                ",".join(missing_axes),
            ))
            continue
        for axis_name in AXES:
            b, w = _source_findings(axes[axis_name], f"{loc}.{axis_name}", axis_name, as_of, max_age)
            blockers.extend(b)
            warns.extend(w)

        scope = axes["scope"]
        if _status(scope.get("match")) == "MISMATCH":
            blockers.append(_finding(
                f"{loc}.scope",
                "official scope 与稿件方向不匹配",
                "不要用高名气/综合分掩盖 scope mismatch；换 venue 或让用户明知风险选择 reach",
                "scope.hard_mismatch",
            ))
        elif _status(scope.get("match")) == "UNKNOWN":
            warns.append(_finding(f"{loc}.scope", "scope match UNKNOWN", "保留未知，不写成 fit", "scope.unknown"))

        article = axes["article_type"]
        accepts = article.get("accepts")
        if accepts is False:
            blockers.append(_finding(
                f"{loc}.article_type",
                f"该 venue 不接收 article_type={spec.get('manuscript_profile', {}).get('article_type')}",
                "文章类型不收是 hard blocker；换 venue 或改稿件类型需回 stage 11/作者决策",
                "article_type.not_accepted",
            ))
        elif accepts is None:
            warns.append(_finding(f"{loc}.article_type", "article type accepts UNKNOWN", "投前核官方 author instructions", "article_type.unknown"))

        fmt = axes["format"]
        if _status(fmt.get("status")) == "FAIL":
            blockers.append(_finding(
                f"{loc}.format",
                "真实 PDF/page/profile 与 venue 格式规则不匹配",
                "返回 typesetting 修格式或排除该 venue；不能让 venue-matching 重排 PDF",
                "format.rule_fail",
                json.dumps(fmt, ensure_ascii=False),
            ))

        cost = axes["cost"]
        apc = _num(cost.get("apc_usd"))
        ceiling = _num(constraints.get("apc_ceiling_usd"))
        if ceiling is not None:
            if apc is None and constraints.get("apc_ceiling_hard") is True:
                blockers.append(_finding(
                    f"{loc}.cost",
                    "作者有硬 APC 上限，但费用 UNKNOWN/UNAVAILABLE",
                    "费用未知不能写成符合预算；刷新官方费用页或让用户带未知决策",
                    "cost.unknown_under_hard_ceiling",
                ))
            elif apc is not None and apc > ceiling:
                blockers.append(_finding(
                    f"{loc}.cost",
                    f"APC ${apc:g} 超过作者硬上限 ${ceiling:g}",
                    "排除或让用户修改约束；waiver 需有独立 VERIFIED 证据",
                    "cost.exceeds_author_ceiling",
                ))
        fee_category = _status(cost.get("fee_category"))
        if fee_category == "UNKNOWN":
            warns.append(_finding(f"{loc}.cost", "fee_category UNKNOWN", "区分 APC/page charge/no fee/waiver，不得写 free", "cost.fee_category_unknown"))

        timeline = axes["timeline"]
        deadline = timeline.get("submission_deadline")
        if deadline:
            parsed = _parse_time(deadline)
            if parsed is None:
                blockers.append(_finding(
                    f"{loc}.timeline",
                    "submission_deadline 缺 timezone 或不是 ISO-8601；deadline 无时区不可用",
                    "补官方时区，例如 2026-08-01T23:59:00-12:00",
                    "timeline.deadline_timezone_missing",
                    str(deadline),
                ))
            elif as_of and parsed < as_of:
                blockers.append(_finding(
                    f"{loc}.timeline",
                    f"deadline {deadline} 已早于 as_of={spec.get('as_of')}",
                    "排除该 CFP/venue 或刷新新一轮 deadline",
                    "timeline.deadline_passed",
                ))
        elif constraints.get("deadline_required") is True:
            blockers.append(_finding(f"{loc}.timeline", "作者硬要求 deadline，但候选 deadline UNKNOWN", "补官方 CFP/deadline；无 deadline 不能进入推荐", "timeline.deadline_required_unknown"))

        trust = axes["trust"]
        trust_status = _status(trust.get("status"))
        if trust_status not in TRUST_STATUSES:
            blockers.append(_finding(f"{loc}.trust", f"trust.status={trust_status!r} 非法", f"改为 {sorted(TRUST_STATUSES)}", "trust.bad_status"))
        if trust.get("identity_conflict") is True or trust.get("hijack_signal") is True:
            blockers.append(_finding(
                f"{loc}.trust",
                "venue 身份冲突/疑似劫持；不能进入正常 shortlist",
                "核 ISSN、官网、出版商、Retraction Watch Hijacked Journal Checker；解决前排除",
                "trust.identity_conflict",
            ))
        if trust_status == "HIGH_RISK":
            warns.append(_finding(
                f"{loc}.trust",
                "trust=HIGH_RISK；这是软预警，不是机器终判",
                "对照 TCS/DOAJ/官方索引/预警名单当前版，交用户在决策点定夺",
                "trust.high_risk_warning",
            ))
        tcs = trust.get("tcs_signals") or []
        if isinstance(tcs, list):
            ids = {_status(item.get("id")) for item in tcs if isinstance(item, dict)}
            missing = sorted(TCS_SIGNAL_IDS - ids)
            if missing:
                warns.append(_finding(
                    f"{loc}.trust.tcs_signals",
                    f"TCS/透明信号未完整结构化，缺 {len(missing)} 项",
                    "补齐 16 项透明信号；未查到写 UNKNOWN，不得沉默",
                    "trust.tcs_incomplete",
                    ",".join(missing[:8]),
                ))
            for item in tcs:
                if not isinstance(item, dict):
                    continue
                if _status(item.get("status")) == "UNKNOWN":
                    warns.append(_finding(f"{loc}.trust.tcs.{item.get('id')}", "TCS signal UNKNOWN", "保留未知，不转成负面", "trust.tcs_unknown"))

        strategy = axes["strategy"]
        if not strategy.get("because") or not strategy.get("evidence_ids"):
            blockers.append(_finding(
                f"{loc}.strategy",
                "strategy 缺 because/evidence_ids；不能只给 reach/match/safety 标签",
                "每个 tier 必须解释取舍并引用证据 ID",
                "strategy.missing_because",
            ))

    if blockers:
        return GateResult("venue_axes", "fail", "critical", blockers,
                          note="候选存在硬阻断或证据轴缺失；不能进入推荐决策包。")
    if warns:
        return GateResult("venue_axes", "warn", "major", warns,
                          note="候选可进入决策包，但 UNKNOWN/软风险/过期来源必须显式展示给用户。")
    return GateResult("venue_axes", "pass", "info", [],
                      note="候选多轴证据齐全，未见硬阻断。")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") not in (SCHEMA_ID, None):
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    project = str(spec.get("project") or "unknown-project")
    gates = [_packet_gate(spec), _candidate_gate(spec)]
    report = FindingsReport(
        producer="venue-matching",
        target=project,
        gates=gates,
        summary=("venue_evidence.v2 multi-axis gate: no aggregate score; dynamic fields keep valid-at/timezone/"
                 "UNKNOWN; hard blockers remain visible before user decision"),
        fresh_evidence=True,
    ).finalize()
    blockers = report.blocking_gates()
    return {
        "schema": REPORT_SCHEMA_ID,
        "project": project,
        "status": "FAIL" if blockers else ("WARN" if report.verdict == "warn" else "PASS"),
        "advancement": "BLOCK" if blockers else ("ALLOW_WITH_UNKNOWNS" if report.verdict == "warn" else "ALLOW"),
        "blocking_gates": [g.gate for g in blockers],
        "findings": report.to_dict(),
    }


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# venue evidence v2 gate：{result['project']}",
        "",
        f"- status: **{result['status']}**",
        f"- advancement: **{result['advancement']}**",
        "",
    ]
    if result["blocking_gates"]:
        lines.append(f"- blocking gates: {', '.join(result['blocking_gates'])}")
        lines.append("")
    lines.append("| gate | status | severity | findings |")
    lines.append("|---|---:|---:|---:|")
    for gate in result["findings"]["gates"]:
        lines.append(f"| {gate['gate']} | {gate['status']} | {gate['severity']} | {len(gate['findings'])} |")
    lines.append("")
    lines.append("> 边界：UNKNOWN/UNAVAILABLE 不等于负面证据；PASS/WARN 仍停在用户决策点，不自动选择或提交。")
    return "\n".join(lines)


def _axis(match: str = "MATCH") -> dict[str, Any]:
    return {
        "source_status": "VERIFIED",
        "locator": "https://venue.example/rules",
        "retrieved_at": "2026-07-04T09:00:00+08:00",
        "match": match,
    }


def _good_spec() -> dict[str, Any]:
    axes = {
        "scope": _axis("MATCH"),
        "article_type": {**_axis("MATCH"), "accepts": True},
        "audience": _axis("MATCH"),
        "format": {**_axis("MATCH"), "status": "PASS"},
        "cost": {**_axis("MATCH"), "apc_usd": 1200, "fee_category": "APC", "waiver_status": "UNKNOWN"},
        "timeline": {**_axis("MATCH"), "submission_deadline": "2026-08-01T23:59:00-12:00"},
        "trust": {
            **_axis("MATCH"),
            "status": "OK",
            "identity_conflict": False,
            "hijack_signal": False,
            "tcs_signals": [
                {"id": sid, "status": "ABSENT", "evidence_locator": f"tcs:{sid}"}
                for sid in sorted(TCS_SIGNAL_IDS)
            ],
        },
        "strategy": {**_axis("MATCH"), "tier": "match", "because": "scope/type/cost/timeline fit", "evidence_ids": ["scope", "cost"]},
    }
    return {
        "schema": SCHEMA_ID,
        "project": "selftest-venue",
        "as_of": "2026-07-04T12:00:00+08:00",
        "refresh_policy_days": 30,
        "decision_point": True,
        "chosen": None,
        "author_constraints": {"apc_ceiling_usd": 1500, "apc_ceiling_hard": True, "deadline_required": True},
        "manuscript_profile": {"article_type": "research-article", "pages": 12},
        "candidates": [{"venue_id": "V1", "name": "Good Venue", "axes": axes}],
    }


def _selftest() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good = evaluate(_good_spec())
    check(good["status"] == "PASS", f"good spec 应 PASS，得 {good['status']}")
    check(good["findings"]["producer"] == "venue-matching", "producer 应 venue-matching")

    agg = _good_spec()
    agg["aggregate_score"] = 0.92
    r2 = evaluate(agg)
    check(r2["status"] == "FAIL" and "venue_decision_packet" in r2["blocking_gates"],
          "aggregate_score 应阻断")

    chosen = _good_spec()
    chosen["chosen"] = "V1"
    r3 = evaluate(chosen)
    check(r3["status"] == "FAIL", "用户选择前 chosen 不得非空")

    no_as_of = _good_spec()
    no_as_of["as_of"] = "2026-07-04T12:00:00"
    r3b = evaluate(no_as_of)
    check(r3b["status"] == "FAIL" and "venue_decision_packet" in r3b["blocking_gates"],
          "as_of 无时区应阻断，否则 source age 无法判定")

    type_bad = _good_spec()
    type_bad["candidates"][0]["axes"]["article_type"]["accepts"] = False
    r4 = evaluate(type_bad)
    check(r4["status"] == "FAIL" and "venue_axes" in r4["blocking_gates"],
          "article type 不收应阻断")

    tz_bad = _good_spec()
    tz_bad["candidates"][0]["axes"]["timeline"]["submission_deadline"] = "2026-08-01T23:59:00"
    r5 = evaluate(tz_bad)
    check(r5["status"] == "FAIL", "deadline 无 timezone 应阻断")

    cost_unknown = _good_spec()
    cost_unknown["candidates"][0]["axes"]["cost"]["source_status"] = "UNAVAILABLE"
    cost_unknown["candidates"][0]["axes"]["cost"].pop("apc_usd")
    r6 = evaluate(cost_unknown)
    check(r6["status"] == "FAIL", "硬 APC 上限下费用未知应阻断")

    doaj_fail = _good_spec()
    doaj_fail["candidates"][0]["axes"]["trust"]["tcs_signals"] = []
    doaj_fail["candidates"][0]["axes"]["trust"]["source_status"] = "UNAVAILABLE"
    r7 = evaluate(doaj_fail)
    check(r7["status"] == "WARN" and r7["advancement"] == "ALLOW_WITH_UNKNOWNS",
          "trust source unavailable/TCS incomplete 应 warn，不当负面证据")

    hijack = _good_spec()
    hijack["candidates"][0]["axes"]["trust"]["identity_conflict"] = True
    r8 = evaluate(hijack)
    check(r8["status"] == "FAIL", "identity conflict/hijack 应阻断")

    stale = _good_spec()
    stale["candidates"][0]["axes"]["cost"]["retrieved_at"] = "2026-05-01T09:00:00+08:00"
    r9 = evaluate(stale)
    check(r9["status"] == "WARN", "动态费用来源过期应 warn")

    future = _good_spec()
    future["candidates"][0]["axes"]["cost"]["retrieved_at"] = "2026-07-05T09:00:00+08:00"
    r10 = evaluate(future)
    check(r10["status"] == "FAIL", "retrieved_at 晚于 as_of 的未来证据应阻断")

    check("venue evidence v2 gate" in to_markdown(good), "markdown 应含标题")

    if failures:
        print("[SELFTEST][venue_evidence_gate] FAIL:")
        for failure in failures:
            print("  -", failure)
        return 1
    print("[SELFTEST][venue_evidence_gate] OK: pass / aggregate forbidden / chosen forbidden / "
          "as_of timezone / article type / deadline timezone / cost unknown / "
          "unavailable not adverse / hijack / stale/future source")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate venue_evidence.v2 multi-axis decision packet")
    parser.add_argument("--spec", help="light.venue_evidence.v2 JSON")
    parser.add_argument("--report", help="write light.findings.v1")
    parser.add_argument("--json-out", help="write full report")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec:
        parser.error("--spec is required unless --selftest")
    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8-sig"))
    result = evaluate(spec)
    print(to_markdown(result))
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
