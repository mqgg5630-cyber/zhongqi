#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit declared authority, scope, change, and incident state across a project.

This is a provenance/scope gate, not a legal or ethics-committee determination.
Only an institution or other competent authority may decide approval, waiver,
exemption, amendment, incident reporting, or jurisdictional applicability.
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

_root = pathlib.Path(__file__).resolve()
while _root != _root.parent and not (_root / "_shared" / "__init__.py").exists():
    _root = _root.parent
sys.path.insert(0, str(_root))
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402

SCHEMA_ID = "light.ethics_authority_packet.v1"
STAGES = {"PLAN", "APPROVAL", "COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"}
REQUIREMENTS = {"REQUIRED", "NOT_REQUIRED_BY_AUTHORITY", "UNKNOWN"}
DECISIONS = {
    "APPROVED", "WAIVED_BY_AUTHORITY", "NOT_REQUIRED_BY_AUTHORITY",
    "PENDING", "EXPIRED", "SUSPENDED", "CLOSED", "UNKNOWN",
}
SOURCE_STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE"}
AUTHORITY_KINDS = {"INSTITUTION", "REGULATOR", "FUNDER", "VENUE"}
ACTIVITY_STATES = {"PLANNED", "ACTIVE", "COMPLETED", "PAUSED"}
CHANGE_STATES = {"PLANNED", "IMPLEMENTED", "WITHDRAWN"}
REVIEW_STATES = {"APPROVED", "NOT_REQUIRED_BY_AUTHORITY", "PENDING", "UNKNOWN"}
REPORTING_REQUIREMENTS = {"REQUIRED", "NOT_REQUIRED_BY_AUTHORITY", "UNKNOWN"}
REPORT_STATES = {"REPORTED", "OPEN", "NOT_REPORTED", "NOT_APPLICABLE"}
SCOPE_FIELDS = (
    "populations", "locations", "data_fields", "purposes", "recording_modes",
    "secondary_uses", "sharing_destinations", "cross_border_destinations",
    "public_quote_modes",
)


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _future_date(value: Any, as_of: dt.date) -> bool:
    parsed = _date(value)
    return parsed is not None and parsed > as_of


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return (
        bool(text)
        and "<" not in text
        and "replace-with" not in text
        and text not in {"unknown", "unavailable", "pending", "gap", "n/a"}
    )


def _scope_values(scope: dict[str, Any], field: str) -> set[str]:
    values = scope.get(field) or []
    if not isinstance(values, list):
        raise ValueError(f"scope.{field} 必须是 list")
    return {str(item).strip() for item in values if str(item).strip()}


def evaluate(spec: dict[str, Any], as_of: dt.date | None = None) -> FindingsReport:
    as_of = as_of or dt.date.today()
    context = spec.get("context")
    determination = spec.get("determination")
    sources_raw = spec.get("authority_sources")
    if not isinstance(context, dict) or not isinstance(determination, dict):
        raise ValueError("context/determination 类型错误")
    if not isinstance(sources_raw, list):
        raise ValueError("authority_sources 必须是 list")
    stage = context.get("stage")
    requirement = determination.get("requirement")
    decision = determination.get("status")
    if stage not in STAGES or requirement not in REQUIREMENTS or decision not in DECISIONS:
        raise ValueError("stage/requirement/determination.status 非法")

    gates: dict[str, list[Finding]] = {
        "authority_packet": [],
        "activity_authorization": [],
        "scope_alignment": [],
        "change_control": [],
        "incident_reporting": [],
    }
    warning_gates: set[str] = set()

    def finding(gate: str, loc: str, issue: str, fix: str, rule: str,
                warning: bool = False) -> None:
        gates[gate].append(Finding(loc=loc, issue=issue, fix=fix, rule=rule))
        if warning:
            warning_gates.add(gate)

    for field in (
        "project_id", "jurisdiction", "institution", "participants",
        "data_classification", "owner", "checked_at",
    ):
        if not _real(context.get(field)):
            finding(
                "authority_packet", f"context.{field}", f"authority packet 缺真实 {field}",
                "由项目负责人补录；未知时写 UNKNOWN，不得推定", "AUTHORITY_CONTEXT_GAP",
            )
    if _date(context.get("checked_at")) is None:
        finding(
            "authority_packet", "context.checked_at", "checked_at 不是 ISO 日期",
            "写 YYYY-MM-DD，并在恢复长周期项目时重新核对", "AUTHORITY_DATE_INVALID",
        )

    if _future_date(context.get("checked_at"), as_of):
        finding(
            "authority_packet", "context.checked_at", "checked_at is in the future",
            "Use the actual authority-packet review date; future-dated context evidence is invalid.",
            "AUTHORITY_DATE_IN_FUTURE",
        )

    sources: dict[str, dict[str, Any]] = {}
    for row in sources_raw:
        if not isinstance(row, dict):
            raise ValueError("authority source 必须是 object")
        source_id = str(row.get("source_id") or "")
        if not source_id or source_id in sources:
            raise ValueError("authority source_id 缺失或重复")
        if row.get("status") not in SOURCE_STATES or row.get("kind") not in AUTHORITY_KINDS:
            raise ValueError(f"{source_id} status/kind 非法")
        sources[source_id] = row
        if row.get("status") == "VERIFIED":
            if not all(_real(row.get(field)) for field in ("source", "locator", "checked_at")):
                finding(
                    "authority_packet", f"authority_sources.{source_id}",
                    "VERIFIED authority source 缺 source/locator/checked_at",
                    "绑定机构/主管部门真实文件与定位；不能用搜索摘要代替",
                    "VERIFIED_SOURCE_PROVENANCE_GAP",
                )
            elif _date(row.get("checked_at")) is None:
                finding(
                    "authority_packet", f"authority_sources.{source_id}.checked_at",
                    "authority source 日期格式非法", "写 YYYY-MM-DD",
                    "AUTHORITY_SOURCE_DATE_INVALID",
                )

            elif _future_date(row.get("checked_at"), as_of):
                finding(
                    "authority_packet", f"authority_sources.{source_id}.checked_at",
                    "authority source checked_at is in the future",
                    "Use the actual source retrieval/review date; future-dated authority evidence is invalid.",
                    "AUTHORITY_SOURCE_DATE_IN_FUTURE",
                )

    decision_source = sources.get(str(determination.get("source_id") or ""))
    decision_source_ok = bool(
        decision_source
        and decision_source.get("status") == "VERIFIED"
        and decision_source.get("kind") in {"INSTITUTION", "REGULATOR"}
        and _real(determination.get("locator"))
    )
    if decision in {"APPROVED", "WAIVED_BY_AUTHORITY", "NOT_REQUIRED_BY_AUTHORITY"}:
        if not decision_source_ok:
            finding(
                "authority_packet", "determination",
                f"{decision} 缺机构/主管部门 VERIFIED source 与决定 locator",
                "回到有权主体的真实决定；Light 不自行宣布批准、豁免或无需审查",
                "DETERMINATION_PROVENANCE_GAP",
            )
    if requirement == "NOT_REQUIRED_BY_AUTHORITY" and decision != "NOT_REQUIRED_BY_AUTHORITY":
        finding(
            "authority_packet", "determination",
            "requirement 与 authority decision 不一致",
            "以有权主体决定为准，统一 requirement/status", "DETERMINATION_CONFLICT",
        )
    if requirement == "UNKNOWN":
        warning = stage in {"PLAN", "APPROVAL"}
        finding(
            "activity_authorization", "determination.requirement",
            "是否需要审批/认定仍 UNKNOWN",
            "暂停受影响活动并向机构确认适用路径", "AUTHORITY_REQUIREMENT_UNKNOWN",
            warning=warning,
        )
    if (
        requirement == "REQUIRED"
        and stage in {"COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"}
        and not (
            decision in {"APPROVED", "WAIVED_BY_AUTHORITY"}
            and decision_source_ok
        )
    ):
        finding(
            "activity_authorization", f"context.stage:{stage}",
            f"项目已到 {stage}，但 REQUIRED authority decision 不可验证",
            "暂停受影响工作；取得有权主体决定与 locator 后再恢复",
            "STAGE_WITHOUT_AUTHORITY",
        )

    expiry = _date(determination.get("expires_at"))
    if determination.get("expires_at") and expiry is None:
        finding(
            "authority_packet", "determination.expires_at", "expires_at 不是 ISO 日期",
            "写 YYYY-MM-DD 或删除无依据日期", "DETERMINATION_EXPIRY_INVALID",
        )
    if expiry and expiry < as_of:
        finding(
            "activity_authorization", "determination.expires_at",
            f"authority determination 已于 {expiry.isoformat()} 到期",
            "暂停受影响活动并按机构 continuing-review/renewal 路径处理",
            "DETERMINATION_EXPIRED",
        )

    activities = spec.get("activities") or []
    if not isinstance(activities, list):
        raise ValueError("activities 必须是 list")
    active_or_done = False
    for row in activities:
        if not isinstance(row, dict) or row.get("status") not in ACTIVITY_STATES:
            raise ValueError("activity/status 非法")
        activity_id = str(row.get("activity_id") or "")
        if not activity_id:
            raise ValueError("activity_id 必填")
        if row.get("status") in {"ACTIVE", "COMPLETED"}:
            active_or_done = True
            authorized = (
                requirement == "REQUIRED"
                and decision in {"APPROVED", "WAIVED_BY_AUTHORITY"}
                and decision_source_ok
                and not (expiry and expiry < as_of)
            ) or (
                requirement == "NOT_REQUIRED_BY_AUTHORITY"
                and decision == "NOT_REQUIRED_BY_AUTHORITY"
                and decision_source_ok
            )
            if not authorized:
                finding(
                    "activity_authorization", f"activity:{activity_id}",
                    f"{row.get('status')} 活动没有可验证的适用决定",
                    "暂停受影响活动；由机构确认批准/豁免/无需审查后再恢复",
                    "ACTIVITY_WITHOUT_AUTHORITY",
                )

    approved_scope = spec.get("approved_scope") or {}
    actual_scope = spec.get("actual_or_planned_scope") or {}
    if not isinstance(approved_scope, dict) or not isinstance(actual_scope, dict):
        raise ValueError("approved_scope/actual_or_planned_scope 类型错误")
    for field in SCOPE_FIELDS:
        extra = sorted(_scope_values(actual_scope, field) - _scope_values(approved_scope, field))
        if extra:
            warning = not active_or_done and stage in {"PLAN", "APPROVAL"}
            finding(
                "scope_alignment", f"scope.{field}",
                f"实际/计划范围含 {len(extra)} 个批准/认定范围外条目；值不在报告回显",
                "核对 consent/protocol/approval；需要时先走 amendment/re-consent",
                "SCOPE_DELTA_UNAUTHORIZED", warning=warning,
            )

    changes = spec.get("changes") or []
    if not isinstance(changes, list):
        raise ValueError("changes 必须是 list")
    for row in changes:
        if not isinstance(row, dict):
            raise ValueError("change 必须是 object")
        change_id = str(row.get("change_id") or "")
        state, review_state = row.get("state"), row.get("authority_status")
        if not change_id or state not in CHANGE_STATES or review_state not in REVIEW_STATES:
            raise ValueError("change_id/state/authority_status 非法")
        source = sources.get(str(row.get("source_id") or ""))
        reviewed = (
            review_state in {"APPROVED", "NOT_REQUIRED_BY_AUTHORITY"}
            and source is not None
            and source.get("status") == "VERIFIED"
            and source.get("kind") in {"INSTITUTION", "REGULATOR"}
            and _real(row.get("locator"))
        )
        if state == "IMPLEMENTED" and not reviewed:
            finding(
                "change_control", f"change:{change_id}",
                "变更已实施，但 amendment/无需审查决定不可验证",
                "暂停变更影响的活动，向有权主体补做审查并记录生效日期",
                "CHANGE_IMPLEMENTED_WITHOUT_REVIEW",
            )
        elif state == "PLANNED" and not reviewed:
            finding(
                "change_control", f"change:{change_id}",
                "计划变更尚无可验证 authority decision",
                "实施前完成 amendment/机构认定", "CHANGE_REVIEW_PENDING", warning=True,
            )

    incidents = spec.get("incidents") or []
    if not isinstance(incidents, list):
        raise ValueError("incidents 必须是 list")
    for row in incidents:
        if not isinstance(row, dict):
            raise ValueError("incident 必须是 object")
        incident_id = str(row.get("incident_id") or "")
        required, status = row.get("reporting_requirement"), row.get("status")
        if not incident_id or required not in REPORTING_REQUIREMENTS or status not in REPORT_STATES:
            raise ValueError("incident_id/reporting_requirement/status 非法")
        if required == "REQUIRED" and (
            status != "REPORTED" or not _real(row.get("report_locator"))
        ):
            finding(
                "incident_reporting", f"incident:{incident_id}",
                "需报告事件尚无 REPORTED 状态与真实 locator",
                "立即按机构时限/路径升级；脚本不替机构定义 prompt 时限",
                "INCIDENT_REPORT_GAP",
            )
        elif required == "UNKNOWN":
            finding(
                "incident_reporting", f"incident:{incident_id}",
                "事件报告义务仍 UNKNOWN",
                "暂停可能扩大风险的活动并立即咨询机构", "INCIDENT_DUTY_UNKNOWN",
            )
        elif required == "NOT_REQUIRED_BY_AUTHORITY":
            source = sources.get(str(row.get("source_id") or ""))
            if not (
                source and source.get("status") == "VERIFIED"
                and source.get("kind") in {"INSTITUTION", "REGULATOR"}
                and _real(row.get("report_locator"))
            ):
                finding(
                    "incident_reporting", f"incident:{incident_id}",
                    "NOT_REQUIRED_BY_AUTHORITY 缺有权主体来源/locator",
                    "记录机构判定；不能由研究者或 Light 自行宣布无需报告",
                    "INCIDENT_NO_REPORT_PROVENANCE_GAP",
                )

    gate_results: list[GateResult] = []
    for gate, found in gates.items():
        if found:
            only_warning = gate in warning_gates and all(
                (
                    item.rule in {"AUTHORITY_REQUIREMENT_UNKNOWN", "SCOPE_DELTA_UNAUTHORIZED",
                                  "CHANGE_REVIEW_PENDING"}
                    and (
                        item.rule != "AUTHORITY_REQUIREMENT_UNKNOWN"
                        or stage in {"PLAN", "APPROVAL"}
                    )
                )
                for item in found
            )
            gate_results.append(GateResult(
                gate=gate,
                status="warn" if only_warning else "fail",
                severity="major" if only_warning else "critical",
                findings=found,
            ))
        else:
            gate_results.append(GateResult(gate=gate, status="pass", severity="info"))
    report = FindingsReport(
        producer="research-ethics",
        target=str(context.get("project_id") or "ethics-authority-packet"),
        gates=gate_results,
        summary=(
            "核 authority provenance、活动授权、声明范围差异、变更和事件报告；"
            "不作法律/伦理委员会裁定。"
        ),
        fresh_evidence=True,
    )
    return report.finalize()


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "context": {
            "project_id": "public-data-study", "jurisdiction": "declared-jurisdiction",
            "institution": "declared-institution", "stage": "ANALYZE",
            "participants": "NONE", "data_classification": "PUBLIC_AGGREGATE",
            "owner": "project-owner", "checked_at": "2026-07-04",
        },
        "authority_sources": [{
            "source_id": "institution-decision", "kind": "INSTITUTION",
            "status": "VERIFIED", "source": "institution letter",
            "locator": "decision.pdf:1", "checked_at": "2026-07-04",
        }],
        "determination": {
            "requirement": "NOT_REQUIRED_BY_AUTHORITY",
            "status": "NOT_REQUIRED_BY_AUTHORITY",
            "source_id": "institution-decision", "locator": "decision.pdf:1",
        },
        "activities": [{
            "activity_id": "analysis", "status": "ACTIVE",
        }],
        "approved_scope": {
            "populations": [], "locations": [], "data_fields": ["public aggregate"],
            "purposes": ["declared analysis"], "recording_modes": [],
            "secondary_uses": [], "sharing_destinations": [],
            "cross_border_destinations": [], "public_quote_modes": [],
        },
        "actual_or_planned_scope": {
            "populations": [], "locations": [], "data_fields": ["public aggregate"],
            "purposes": ["declared analysis"], "recording_modes": [],
            "secondary_uses": [], "sharing_destinations": [],
            "cross_border_destinations": [], "public_quote_modes": [],
        },
        "changes": [],
        "incidents": [],
    }


def _selftest() -> int:
    good = evaluate(_base(), dt.date(2026, 7, 4))
    assert good.verdict == "pass"
    bad = json.loads(json.dumps(_base()))
    bad["determination"] = {"requirement": "REQUIRED", "status": "PENDING"}
    bad["actual_or_planned_scope"]["data_fields"].append("new identifiable field")
    bad["changes"] = [{
        "change_id": "chg-1", "state": "IMPLEMENTED", "authority_status": "PENDING",
    }]
    bad["incidents"] = [{
        "incident_id": "inc-1", "reporting_requirement": "REQUIRED",
        "status": "NOT_REPORTED",
    }]
    report = evaluate(bad, dt.date(2026, 7, 4))
    assert report.verdict == "fail"
    rules = {
        finding.rule for gate in report.gates for finding in gate.findings
    }
    assert {
        "STAGE_WITHOUT_AUTHORITY", "ACTIVITY_WITHOUT_AUTHORITY", "SCOPE_DELTA_UNAUTHORIZED",
        "CHANGE_IMPLEMENTED_WITHOUT_REVIEW", "INCIDENT_REPORT_GAP",
    } <= rules
    no_activities = json.loads(json.dumps(_base()))
    no_activities["determination"] = {"requirement": "REQUIRED", "status": "PENDING"}
    no_activities["activities"] = []
    no_activity_report = evaluate(no_activities, dt.date(2026, 7, 4))
    assert "STAGE_WITHOUT_AUTHORITY" in {
        finding.rule for gate in no_activity_report.gates for finding in gate.findings
    }
    planned = json.loads(json.dumps(_base()))
    planned["context"]["stage"] = "PLAN"
    planned["activities"][0]["status"] = "PLANNED"
    planned["determination"] = {"requirement": "UNKNOWN", "status": "UNKNOWN"}
    assert evaluate(planned, dt.date(2026, 7, 4)).verdict == "warn"
    future = json.loads(json.dumps(_base()))
    future["context"]["checked_at"] = "2999-01-01"
    future["authority_sources"][0]["checked_at"] = "2999-01-01"
    future_report = evaluate(future, dt.date(2026, 7, 4))
    future_rules = {
        finding.rule for gate in future_report.gates for finding in gate.findings
    }
    assert {
        "AUTHORITY_DATE_IN_FUTURE",
        "AUTHORITY_SOURCE_DATE_IN_FUTURE",
    } <= future_rules
    print("authority_lifecycle_gate selftest PASS: 已认定/未授权活动/范围差异/变更/事件")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    as_of = _date(args.as_of) if args.as_of else dt.date.today()
    if args.as_of and as_of is None:
        parser.error("--as-of 必须是 YYYY-MM-DD")
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    report = evaluate(spec, as_of)
    print(report.to_json())
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
