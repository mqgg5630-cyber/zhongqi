#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate consent scope against planned/actual research uses.

This is a provenance/scope gate, not an IRB/HREC/IACUC determination. It checks
whether declared uses of participant data/materials are backed by exact consent,
broad-consent, waiver, or authority "not required" evidence. It deliberately
does not decide whether a waiver is legally valid; it only refuses to treat
UNKNOWN, placeholders, future dates, or generic "we have consent" prose as
release-ready evidence.
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
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

_root = pathlib.Path(__file__).resolve()
while _root != _root.parent and not (_root / "_shared" / "__init__.py").exists():
    _root = _root.parent
sys.path.insert(0, str(_root))
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402

SCHEMA_ID = "light.consent_scope_packet.v1"
STAGES = {"PLAN", "APPROVAL", "COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"}
SOURCE_TYPES = {
    "CONSENT_PROCESS", "CONSENT_FORM", "ASSENT_FORM", "BROAD_CONSENT",
    "CONSENT_WAIVER", "AUTHORITY_DECISION", "PROTOCOL", "RECRUITMENT_MATERIAL",
    "DATA_MANAGEMENT_PLAN", "DEIDENTIFICATION_PLAN", "DATA_USE_AGREEMENT",
}
SOURCE_STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE", "NOT_APPLICABLE"}
USE_CATEGORIES = {
    "participation", "intervention", "survey", "interview", "recording",
    "public_quote", "biological_sample", "identifiable_data",
    "secondary_use", "future_reuse", "data_sharing", "repository_release",
    "cross_border_transfer", "model_training", "withdrawal_retention",
}
USE_STATES = {"PLANNED", "ACTIVE", "COMPLETED", "WITHDRAWN"}
REQUIREMENT_STATES = {"REQUIRED", "NOT_REQUIRED_BY_AUTHORITY", "UNKNOWN"}
BASIS_STATES = {
    "EXPLICIT_CONSENT", "BROAD_CONSENT", "ASSENT_AND_PERMISSION",
    "WAIVED_BY_AUTHORITY", "NOT_REQUIRED_BY_AUTHORITY", "UNKNOWN",
}
SCOPE_SENSITIVE_CATEGORIES = {
    "recording", "public_quote", "biological_sample", "identifiable_data",
    "secondary_use", "future_reuse", "data_sharing", "repository_release",
    "cross_border_transfer", "model_training", "withdrawal_retention",
}
AUTHORITY_BASES = {"WAIVED_BY_AUTHORITY", "NOT_REQUIRED_BY_AUTHORITY"}
CONSENT_BASES = {"EXPLICIT_CONSENT", "BROAD_CONSENT", "ASSENT_AND_PERMISSION"}


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _future_date(value: Any, as_of: dt.date) -> bool:
    parsed = _date(value)
    return parsed is not None and parsed > as_of


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return (
        bool(text)
        and "<" not in text
        and "{{" not in text
        and text.casefold() not in {
            "unknown", "unavailable", "pending", "gap", "待核查", "n/a", "none",
        }
    )


class Bag:
    def __init__(self) -> None:
        self.items: dict[str, list[tuple[str, Finding]]] = {
            "packet_context": [],
            "consent_sources": [],
            "use_coverage": [],
            "withdrawal_boundary": [],
            "attachment_consistency": [],
        }

    def add(
        self,
        gate: str,
        severity: str,
        loc: str,
        issue: str,
        fix: str,
        rule: str,
        evidence: str | None = None,
    ) -> None:
        self.items.setdefault(gate, []).append((
            severity,
            Finding(loc=loc, issue=issue, fix=fix, evidence=evidence, rule=rule),
        ))

    def gates(self) -> list[GateResult]:
        out: list[GateResult] = []
        for gate, rows in self.items.items():
            if not rows:
                out.append(GateResult(gate=gate, status="pass", severity="info"))
                continue
            severity = "critical" if any(sev == "critical" for sev, _ in rows) else "major"
            out.append(GateResult(
                gate=gate,
                status="fail" if severity == "critical" else "warn",
                severity=severity,
                findings=[finding for _, finding in rows],
            ))
        return out


def _is_late(stage: str, use_state: str) -> bool:
    return stage in {"COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"} or use_state in {
        "ACTIVE", "COMPLETED",
    }


def _source_ok(
    source: dict[str, Any] | None,
    allowed_types: set[str],
    as_of: dt.date,
) -> bool:
    return bool(
        source
        and source.get("status") == "VERIFIED"
        and source.get("type") in allowed_types
        and _real(source.get("source"))
        and _real(source.get("locator"))
        and _date(source.get("checked_at")) is not None
        and not _future_date(source.get("checked_at"), as_of)
    )


def _validate_context(spec: dict[str, Any], bag: Bag, as_of: dt.date) -> tuple[dict[str, Any], str]:
    context = spec.get("context")
    if not isinstance(context, dict):
        raise ValueError("context 必须是 object")
    stage = str(context.get("stage") or "UNKNOWN").upper()
    if stage not in STAGES:
        raise ValueError("context.stage 非法")
    for field in ("project_id", "jurisdiction", "institution", "owner", "checked_at"):
        if not _real(context.get(field)):
            bag.add(
                "packet_context", "critical", f"context.{field}",
                f"consent scope packet 缺真实 {field}",
                "补录真实项目、法域、机构、owner 与核验日期；未知时不要写成 VERIFIED",
                "CONSENT_CONTEXT_GAP",
            )
    if _date(context.get("checked_at")) is None:
        bag.add(
            "packet_context", "critical", "context.checked_at",
            "checked_at 不是 ISO 日期", "写 YYYY-MM-DD", "CONSENT_CONTEXT_DATE_INVALID",
        )
    elif _future_date(context.get("checked_at"), as_of):
        bag.add(
            "packet_context", "critical", "context.checked_at",
            "checked_at is in the future",
            "Use the actual consent-scope review date; future-dated evidence is invalid.",
            "CONSENT_CONTEXT_DATE_IN_FUTURE",
        )
    return context, stage


def _read_sources(spec: dict[str, Any], bag: Bag, as_of: dt.date) -> dict[str, dict[str, Any]]:
    sources_raw = spec.get("consent_sources")
    if not isinstance(sources_raw, list):
        raise ValueError("consent_sources 必须是 list")
    sources: dict[str, dict[str, Any]] = {}
    for row in sources_raw:
        if not isinstance(row, dict):
            raise ValueError("consent source 必须是 object")
        sid = str(row.get("source_id") or "")
        if not sid or sid in sources:
            raise ValueError("consent source_id 缺失或重复")
        stype = str(row.get("type") or "")
        state = str(row.get("status") or "UNKNOWN").upper()
        if stype not in SOURCE_TYPES:
            bag.add(
                "consent_sources", "critical", f"consent_sources.{sid}",
                f"未知 consent source type: {stype}",
                "使用受控 source type；不要把普通说明当 consent/authority 文件",
                "CONSENT_SOURCE_TYPE_INVALID",
            )
        if state not in SOURCE_STATES:
            bag.add(
                "consent_sources", "critical", f"consent_sources.{sid}",
                f"非法 consent source status: {state}",
                "使用 VERIFIED/UNKNOWN/UNAVAILABLE/STALE/NOT_APPLICABLE",
                "CONSENT_SOURCE_STATUS_INVALID",
            )
        normalized = dict(row)
        normalized["status"] = state
        sources[sid] = normalized
        if state == "VERIFIED":
            missing = [
                field for field in ("source", "locator", "checked_at")
                if not _real(row.get(field))
            ]
            if missing:
                bag.add(
                    "consent_sources", "critical", f"consent_sources.{sid}",
                    f"VERIFIED consent source 缺 {','.join(missing)}",
                    "绑定真实文件/网页/portal export 的 locator 与取得日期",
                    "VERIFIED_CONSENT_SOURCE_PROVENANCE_GAP",
                )
            elif _date(row.get("checked_at")) is None:
                bag.add(
                    "consent_sources", "critical", f"consent_sources.{sid}.checked_at",
                    "consent source checked_at 不是 ISO 日期", "写 YYYY-MM-DD",
                    "CONSENT_SOURCE_DATE_INVALID",
                )
            elif _future_date(row.get("checked_at"), as_of):
                bag.add(
                    "consent_sources", "critical", f"consent_sources.{sid}.checked_at",
                    "consent source checked_at is in the future",
                    "Use the actual source retrieval/review date.",
                    "CONSENT_SOURCE_DATE_IN_FUTURE",
                )
    return sources


def _basis_allowed_types(basis: str) -> set[str]:
    if basis == "BROAD_CONSENT":
        return {"BROAD_CONSENT", "CONSENT_FORM", "AUTHORITY_DECISION"}
    if basis == "ASSENT_AND_PERMISSION":
        return {"ASSENT_FORM", "CONSENT_FORM", "CONSENT_PROCESS"}
    if basis == "EXPLICIT_CONSENT":
        return {"CONSENT_FORM", "CONSENT_PROCESS"}
    return {"AUTHORITY_DECISION", "CONSENT_WAIVER"}


def _check_uses(
    spec: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    bag: Bag,
    stage: str,
    as_of: dt.date,
) -> bool:
    uses = spec.get("planned_or_actual_uses")
    if not isinstance(uses, list) or not uses:
        bag.add(
            "use_coverage", "critical", "planned_or_actual_uses",
            "未列出任何计划/实际 consent-sensitive use",
            "逐项列出参与、记录、公开引文、二次使用、共享、发布、跨境、模型训练等用途",
            "USES_MISSING",
        )
        return False
    saw_human_consent_use = False
    for use in uses:
        if not isinstance(use, dict):
            raise ValueError("planned_or_actual_uses item 必须是 object")
        use_id = str(use.get("use_id") or "")
        category = str(use.get("category") or "")
        state = str(use.get("status") or "PLANNED").upper()
        requirement = str(use.get("requires_consent") or "UNKNOWN").upper()
        basis = str(use.get("consent_basis") or "UNKNOWN").upper()
        loc = f"use:{use_id or category or 'unknown'}"
        if not use_id:
            raise ValueError("use_id 必填")
        if category not in USE_CATEGORIES or state not in USE_STATES:
            raise ValueError(f"{use_id} category/status 非法")
        if requirement not in REQUIREMENT_STATES or basis not in BASIS_STATES:
            raise ValueError(f"{use_id} requires_consent/consent_basis 非法")
        late = _is_late(stage, state)
        if requirement == "UNKNOWN":
            bag.add(
                "use_coverage", "critical" if late else "major", loc,
                "该用途是否需要 consent/waiver/authority determination 仍 UNKNOWN",
                "实施前找机构/IRB/HREC/数据治理 owner 确认；不要由 Light 自行判免审",
                "USE_CONSENT_REQUIREMENT_UNKNOWN",
            )
        if requirement == "REQUIRED" and basis == "UNKNOWN":
            bag.add(
                "use_coverage", "critical" if late else "major", loc,
                "需要 consent 的用途缺 consent_basis",
                "绑定 explicit/broad/assent+permission/waiver 的真实来源与 locator",
                "USE_CONSENT_BASIS_MISSING",
            )
        if requirement == "NOT_REQUIRED_BY_AUTHORITY" and basis != "NOT_REQUIRED_BY_AUTHORITY":
            bag.add(
                "use_coverage", "critical", loc,
                "requires_consent 与 consent_basis 不一致",
                "只有有权主体 source 可支持 NOT_REQUIRED_BY_AUTHORITY",
                "USE_REQUIREMENT_BASIS_CONFLICT",
            )
        if basis in CONSENT_BASES | AUTHORITY_BASES:
            sid = str(use.get("source_id") or "")
            source = sources.get(sid)
            if not _source_ok(source, _basis_allowed_types(basis), as_of):
                bag.add(
                    "use_coverage", "critical", loc,
                    f"{basis} 缺匹配类型的 VERIFIED source",
                    "source_id 必须指向 consent/broad-consent/waiver/authority 文件，且有真实 locator/checked_at",
                    "USE_BASIS_SOURCE_UNVERIFIED",
                )
            if not _real(use.get("locator")):
                bag.add(
                    "use_coverage", "critical", loc,
                    "用途缺指向 consent/authority 原文的 locator",
                    "locator 应精确到 consent 表、批准函、waiver 或 authority decision 的段落/页码",
                    "USE_SCOPE_LOCATOR_MISSING",
                )
        if requirement == "REQUIRED" or basis in CONSENT_BASES:
            saw_human_consent_use = True
        if category in SCOPE_SENSITIVE_CATEGORIES and basis in CONSENT_BASES:
            if not _real(use.get("specific_scope_locator")):
                bag.add(
                    "use_coverage", "critical", loc,
                    f"{category} 需要单独范围定位，不能被通用 consent 兜底",
                    "补 exact locator：录音/录像、公开引文、二次使用、共享、发布、跨境或模型训练的具体同意范围",
                    "SENSITIVE_USE_SCOPE_LOCATOR_MISSING",
                )
        if category in {"public_quote", "recording"} and use.get("deductive_disclosure_risk") is True:
            if not _real(use.get("mitigation_locator")):
                bag.add(
                    "use_coverage", "critical", loc,
                    "存在可搜索原话/影像/声音/小社区再识别风险但缺 mitigation locator",
                    "记录脱敏、改写、member check、额外同意或禁止公开的具体处理依据",
                    "DEDUCTIVE_DISCLOSURE_MITIGATION_MISSING",
                )
        if category in {"data_sharing", "repository_release", "cross_border_transfer", "model_training"}:
            if not _real(use.get("withdrawal_boundary_locator")):
                bag.add(
                    "use_coverage", "critical" if late else "major", loc,
                    "共享/发布/跨境/模型训练用途缺退出后数据边界 locator",
                    "说明参与者退出后已收集/已共享数据如何保留、撤回或不可撤回；绑定 consent/DMP/authority locator",
                    "WITHDRAWAL_BOUNDARY_LOCATOR_MISSING",
                )
    return saw_human_consent_use


def _check_withdrawal(
    spec: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    bag: Bag,
    stage: str,
    saw_human_consent_use: bool,
    as_of: dt.date,
) -> None:
    policy = spec.get("withdrawal_policy") or {}
    if not isinstance(policy, dict):
        raise ValueError("withdrawal_policy 必须是 object")
    if not saw_human_consent_use:
        return
    state = str(policy.get("status") or "UNKNOWN").upper()
    if state not in SOURCE_STATES:
        raise ValueError("withdrawal_policy.status 非法")
    late = stage in {"COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"}
    sid = str(policy.get("source_id") or "")
    ok = _source_ok(
        sources.get(sid),
        {"CONSENT_FORM", "CONSENT_PROCESS", "BROAD_CONSENT", "AUTHORITY_DECISION"},
        as_of,
    )
    if state != "VERIFIED" or not ok or not _real(policy.get("locator")):
        bag.add(
            "withdrawal_boundary", "critical" if late else "major",
            "withdrawal_policy",
            "知情同意/参与者用途缺 VERIFIED 退出边界说明",
            "说明可随时退出、已收集数据是否保留分析、已共享数据是否可撤回；绑定 consent/process/authority locator",
            "WITHDRAWAL_POLICY_UNVERIFIED",
        )
    if policy.get("retains_collected_data_after_withdrawal") is True:
        if not _real(policy.get("participant_explanation_locator")):
            bag.add(
                "withdrawal_boundary", "critical", "withdrawal_policy",
                "保留退出前已收集数据但缺给参与者的解释 locator",
                "按机构/法规要求在 consent 中解释退出后已收集数据的处理边界",
                "WITHDRAWAL_RETENTION_EXPLANATION_MISSING",
            )


def _check_attachment_matrix(spec: dict[str, Any], bag: Bag, stage: str) -> None:
    matrix = spec.get("attachment_matrix") or []
    if not isinstance(matrix, list):
        raise ValueError("attachment_matrix 必须是 list")
    late = stage in {"COLLECT", "ANALYZE", "PUBLISH", "POST_PUBLICATION"}
    for row in matrix:
        if not isinstance(row, dict):
            raise ValueError("attachment_matrix item 必须是 object")
        mid = str(row.get("matrix_id") or "attachment")
        state = str(row.get("status") or "UNKNOWN").upper()
        if state not in {"CONSISTENT", "INCONSISTENT", "UNKNOWN"}:
            raise ValueError("attachment_matrix.status 非法")
        loc = f"attachment_matrix:{mid}"
        if state == "INCONSISTENT":
            bag.add(
                "attachment_consistency", "critical", loc,
                "protocol/consent/recruitment/DMP 附件声明不一致",
                "先修正附件并取得必要 amendment/approval；不能靠投稿声明掩盖范围冲突",
                "CONSENT_ATTACHMENT_INCONSISTENT",
            )
        elif state == "UNKNOWN":
            bag.add(
                "attachment_consistency", "critical" if late else "major", loc,
                "跨附件一致性尚未核验",
                "至少核 protocol、consent、recruitment、DMP 与实际用途是否一致并记录 locator",
                "CONSENT_ATTACHMENT_CONSISTENCY_UNKNOWN",
            )
        if state == "CONSISTENT":
            for field in ("protocol_locator", "consent_locator"):
                if not _real(row.get(field)):
                    bag.add(
                        "attachment_consistency", "critical", f"{loc}.{field}",
                        f"CONSISTENT 记录缺 {field}",
                        "一致性结论必须绑定原始附件定位，不接受口头承诺",
                        "CONSENT_ATTACHMENT_LOCATOR_MISSING",
                    )


def evaluate(spec: dict[str, Any], as_of: dt.date | None = None) -> FindingsReport:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    as_of = as_of or dt.date.today()
    bag = Bag()
    context, stage = _validate_context(spec, bag, as_of)
    sources = _read_sources(spec, bag, as_of)
    saw_human = _check_uses(spec, sources, bag, stage, as_of)
    _check_withdrawal(spec, sources, bag, stage, saw_human, as_of)
    _check_attachment_matrix(spec, bag, stage)
    return FindingsReport(
        producer="research-ethics",
        target=str(context.get("project_id") or "consent-scope-packet"),
        gates=bag.gates(),
        summary=(
            "核 consent/broad-consent/waiver/authority locator 是否覆盖实际用途、"
            "敏感用途范围、退出边界与跨附件一致性；不作机构裁定。"
        ),
        fresh_evidence=True,
    ).finalize()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("input must be JSON object")
    return value


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "context": {
            "project_id": "interview-study",
            "jurisdiction": "declared-jurisdiction",
            "institution": "declared-institution",
            "stage": "COLLECT",
            "owner": "pi-or-owner",
            "checked_at": "2026-07-05",
        },
        "consent_sources": [
            {
                "source_id": "consent-form",
                "type": "CONSENT_FORM",
                "status": "VERIFIED",
                "source": "participant consent form v3",
                "locator": "consent-v3.pdf:2-4",
                "checked_at": "2026-07-05",
            },
            {
                "source_id": "consent-process",
                "type": "CONSENT_PROCESS",
                "status": "VERIFIED",
                "source": "protocol consent process",
                "locator": "protocol.pdf:5",
                "checked_at": "2026-07-05",
            },
        ],
        "planned_or_actual_uses": [
            {
                "use_id": "audio-recording",
                "category": "recording",
                "status": "ACTIVE",
                "requires_consent": "REQUIRED",
                "consent_basis": "EXPLICIT_CONSENT",
                "source_id": "consent-form",
                "locator": "consent-v3.pdf:recording",
                "specific_scope_locator": "consent-v3.pdf:recording",
                "deductive_disclosure_risk": True,
                "mitigation_locator": "protocol.pdf:deidentification",
            },
            {
                "use_id": "coded-data-analysis",
                "category": "identifiable_data",
                "status": "ACTIVE",
                "requires_consent": "REQUIRED",
                "consent_basis": "EXPLICIT_CONSENT",
                "source_id": "consent-form",
                "locator": "consent-v3.pdf:data-use",
                "specific_scope_locator": "consent-v3.pdf:data-use",
            },
        ],
        "withdrawal_policy": {
            "status": "VERIFIED",
            "source_id": "consent-form",
            "locator": "consent-v3.pdf:withdrawal",
            "retains_collected_data_after_withdrawal": True,
            "participant_explanation_locator": "consent-v3.pdf:withdrawal-retention",
        },
        "attachment_matrix": [
            {
                "matrix_id": "core-attachments",
                "status": "CONSISTENT",
                "protocol_locator": "protocol.pdf:5-8",
                "consent_locator": "consent-v3.pdf:2-4",
                "dmp_locator": "dmp.md:participant-data",
            }
        ],
    }


def _rules(report: FindingsReport) -> set[str]:
    return {finding.rule for gate in report.gates for finding in gate.findings}


def _selftest() -> int:
    good = evaluate(_base(), dt.date(2026, 7, 5))
    assert good.verdict == "pass", good.to_json()

    bad = json.loads(json.dumps(_base()))
    bad["context"]["checked_at"] = "2999-01-01"
    bad["consent_sources"][0]["checked_at"] = "2999-01-01"
    bad["planned_or_actual_uses"] = [
        {
            "use_id": "new-video",
            "category": "recording",
            "status": "ACTIVE",
            "requires_consent": "REQUIRED",
            "consent_basis": "UNKNOWN",
            "deductive_disclosure_risk": True,
        },
        {
            "use_id": "public-quote",
            "category": "public_quote",
            "status": "ACTIVE",
            "requires_consent": "REQUIRED",
            "consent_basis": "EXPLICIT_CONSENT",
            "source_id": "consent-form",
            "locator": "consent-v3.pdf:quotes",
            "deductive_disclosure_risk": True,
        },
        {
            "use_id": "repository",
            "category": "repository_release",
            "status": "PLANNED",
            "requires_consent": "REQUIRED",
            "consent_basis": "EXPLICIT_CONSENT",
            "source_id": "consent-form",
            "locator": "consent-v3.pdf:sharing",
            "specific_scope_locator": "consent-v3.pdf:sharing",
        },
    ]
    bad["withdrawal_policy"] = {"status": "UNKNOWN"}
    bad["attachment_matrix"] = [{"matrix_id": "core", "status": "INCONSISTENT"}]
    bad_report = evaluate(bad, dt.date(2026, 7, 5))
    bad_rules = _rules(bad_report)
    assert bad_report.verdict == "fail", bad_report.to_json()
    assert {
        "CONSENT_CONTEXT_DATE_IN_FUTURE",
        "CONSENT_SOURCE_DATE_IN_FUTURE",
        "USE_CONSENT_BASIS_MISSING",
        "USE_BASIS_SOURCE_UNVERIFIED",
        "SENSITIVE_USE_SCOPE_LOCATOR_MISSING",
        "DEDUCTIVE_DISCLOSURE_MITIGATION_MISSING",
        "WITHDRAWAL_BOUNDARY_LOCATOR_MISSING",
        "WITHDRAWAL_POLICY_UNVERIFIED",
        "CONSENT_ATTACHMENT_INCONSISTENT",
    } <= bad_rules

    planned = json.loads(json.dumps(_base()))
    planned["context"]["stage"] = "PLAN"
    planned["planned_or_actual_uses"] = [{
        "use_id": "future-sharing",
        "category": "data_sharing",
        "status": "PLANNED",
        "requires_consent": "UNKNOWN",
        "consent_basis": "UNKNOWN",
    }]
    planned["withdrawal_policy"] = {}
    planned["attachment_matrix"] = [{"matrix_id": "plan", "status": "UNKNOWN"}]
    planned_report = evaluate(planned, dt.date(2026, 7, 5))
    assert planned_report.verdict == "warn", planned_report.to_json()

    not_required_bad = json.loads(json.dumps(_base()))
    not_required_bad["planned_or_actual_uses"][0].update({
        "requires_consent": "NOT_REQUIRED_BY_AUTHORITY",
        "consent_basis": "EXPLICIT_CONSENT",
    })
    nr_report = evaluate(not_required_bad, dt.date(2026, 7, 5))
    assert "USE_REQUIREMENT_BASIS_CONFLICT" in _rules(nr_report)

    print("consent_scope_gate selftest PASS: scope/basis/source/withdrawal/attachment gates")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--input")
    parser.add_argument("--as-of")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    as_of = _date(args.as_of) if args.as_of else dt.date.today()
    if args.as_of and as_of is None:
        parser.error("--as-of 必须是 YYYY-MM-DD")
    report = evaluate(read_json(pathlib.Path(args.input)), as_of)
    print(report.to_json())
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
