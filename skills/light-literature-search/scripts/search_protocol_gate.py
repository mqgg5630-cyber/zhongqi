#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit search protocol, source coverage, screening accounting, and stop claims."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.search_protocol.v1"
REVIEW_TYPES = {"EXPLORATORY", "SCOPING", "RAPID", "SYSTEMATIC"}
PROTOCOL_STATES = {"EXPLORATORY", "FROZEN", "REGISTERED", "AMENDED"}
SOURCE_STATES = {"SEARCHED", "UNAVAILABLE", "NOT_APPLICABLE"}
QUERY_STATES = {"RUN", "UNAVAILABLE", "SKIPPED"}
SCREENING_STATES = {"INCLUDED", "EXCLUDED", "UNSCREENED", "UNKNOWN"}
CHAIN_DIRECTIONS = {"FORWARD", "BACKWARD", "BOTH"}
SCOPE_DECISION_BASES = {"USER_PROVIDED", "USER_CONFIRMED", "AGENT_DEFAULT_DISCLOSED"}
SOURCE_FAMILIES = {
    "bibliographic-index", "citation-index", "discipline-database",
    "domain-index", "preprint-server", "registry", "repository",
    "library-catalog", "grey-literature", "standards-database",
    "trial-registry", "patent-database", "manual-export", "other-declared",
}


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return (
        bool(text) and "<" not in text and "replace-with" not in text
        and text not in {"unknown", "pending", "gap", "n/a"}
    )


def _hash(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _date_value(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> bool:
    return _date_value(value) is not None


def _future(value: Any, as_of: dt.date) -> bool:
    parsed = _date_value(value)
    return parsed is not None and parsed > as_of


def _norm(value: Any) -> str:
    return re.sub(r"\s+", "-", str(value or "").strip().casefold())


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and value >= 0


def _content_sha256(spec: dict[str, Any]) -> str:
    content = {key: value for key, value in spec.items() if key != "protocol_lock"}
    payload = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def evaluate(spec: dict[str, Any], as_of: dt.date | None = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    as_of = as_of or dt.date.today()
    review_type = spec.get("review_type")
    protocol_state = spec.get("protocol_state")
    if review_type not in REVIEW_TYPES or protocol_state not in PROTOCOL_STATES:
        raise ValueError("review_type/protocol_state 非法")
    issues: list[dict[str, str]] = []

    def add(code: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    if protocol_state in {"FROZEN", "REGISTERED", "AMENDED"}:
        protocol_lock = spec.get("protocol_lock") or {}
        if not _hash(protocol_lock.get("protocol_sha256")):
            add("PROTOCOL_LOCK_GAP", "冻结/注册/修订协议缺 protocol SHA-256")
        elif protocol_lock["protocol_sha256"].casefold() != _content_sha256(spec):
            add("PROTOCOL_LOCK_MISMATCH", "protocol SHA-256 与当前协议内容不一致")
        if not _date(protocol_lock.get("frozen_at")):
            add("PROTOCOL_LOCK_GAP", "冻结/注册/修订协议缺 ISO frozen_at")
        elif _future(protocol_lock.get("frozen_at"), as_of):
            add("FUTURE_PROTOCOL_DATE", "protocol_lock.frozen_at 晚于 as_of")
    if protocol_state == "REGISTERED":
        registration = spec.get("registration") or {}
        if not all(_real(registration.get(field)) for field in ("registry", "record_id", "url")):
            add("REGISTRATION_PROVENANCE_GAP", "REGISTERED 协议缺 registry/record_id/url")

    question = spec.get("question") or {}
    for field in ("research_question", "concepts", "scope_boundary"):
        if question.get(field) in (None, "", []):
            add("QUESTION_FRAME_GAP", f"question.{field} 缺失")
    eligibility = spec.get("eligibility") or {}
    for field in ("include", "exclude", "date_range", "languages", "document_types"):
        if eligibility.get(field) in (None, "", []):
            add("ELIGIBILITY_GAP", f"eligibility.{field} 缺失")

    scope_decision = spec.get("scope_decision")
    if not isinstance(scope_decision, dict):
        add("SCOPE_DECISION_GAP", "缺 scope_decision；无法证明范围/时间窗/语种来自用户或已向用户披露")
    else:
        basis = scope_decision.get("basis")
        if basis not in SCOPE_DECISION_BASES:
            add("SCOPE_DECISION_GAP", "scope_decision.basis 必须是 USER_PROVIDED/USER_CONFIRMED/AGENT_DEFAULT_DISCLOSED")
        if review_type == "SYSTEMATIC" and basis == "AGENT_DEFAULT_DISCLOSED":
            add(
                "SCOPE_DECISION_NOT_USER_AUTHORIZED",
                "SYSTEMATIC 检索范围必须由用户提供或确认，不能由 agent 默认值直接冻结",
            )
        if not _real(scope_decision.get("decision_id")):
            add("SCOPE_DECISION_GAP", "scope_decision 缺真实 decision_id")
        decided_at = scope_decision.get("decided_at")
        if not _date(decided_at):
            add("SCOPE_DECISION_GAP", "scope_decision.decided_at 必须是 ISO 日期")
        elif _future(decided_at, as_of):
            add("FUTURE_SCOPE_DECISION", "scope_decision.decided_at 晚于 as_of")
        if not (
            _real(scope_decision.get("evidence_locator"))
            and _hash(scope_decision.get("evidence_sha256"))
        ):
            add(
                "SCOPE_DECISION_EVIDENCE_GAP",
                "scope decision 必须绑定用户原话/确认记录的 locator 与 SHA-256",
            )
        selection = scope_decision.get("selection")
        if not isinstance(selection, dict):
            add("SCOPE_DECISION_GAP", "scope_decision.selection 必须是 object")
        else:
            expected = {
                "review_type": review_type,
                "research_question": question.get("research_question"),
                "scope_boundary": question.get("scope_boundary"),
                "date_range": eligibility.get("date_range"),
                "languages": eligibility.get("languages"),
                "document_types": eligibility.get("document_types"),
            }
            if any(selection.get(key) != value for key, value in expected.items()):
                add(
                    "SCOPE_DECISION_MISMATCH",
                    "scope_decision.selection 与当前 question/eligibility/review_type 不一致；问完后范围发生漂移",
                )

    sources = spec.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources 必须是 list")
    searched_families: set[str] = set()
    searched_source_ids: set[str] = set()
    source_ids: set[str] = set()
    source_result_counts: dict[str, int] = {}
    source_result_total = 0
    unavailable = 0
    for row in sources:
        if not isinstance(row, dict):
            raise ValueError("source 必须是 object")
        source_id = str(row.get("source_id") or "")
        state = row.get("status")
        if not source_id or source_id in source_ids or state not in SOURCE_STATES:
            raise ValueError("source_id 重复/缺失或 status 非法")
        source_ids.add(source_id)
        family = _norm(row.get("family"))
        if not _real(row.get("family")) or not _real(row.get("reason")):
            add("SOURCE_DECLARATION_GAP", f"{source_id} 缺 family/reason")
        elif family not in SOURCE_FAMILIES:
            add("SOURCE_FAMILY_INVALID", f"{source_id} family 不在受控枚举中")
        elif family == "other-declared" and not _real(row.get("family_detail")):
            add("SOURCE_FAMILY_INVALID", f"{source_id} other-declared 缺 family_detail")
        if state == "SEARCHED":
            searched_source_ids.add(source_id)
            if family in SOURCE_FAMILIES:
                searched_families.add(family)
            for field in ("query", "searched_at", "endpoint", "raw_locator"):
                if not _real(row.get(field)):
                    add("SEARCH_PROVENANCE_GAP", f"{source_id} SEARCHED 缺 {field}")
            if _real(row.get("searched_at")) and not _date(row.get("searched_at")):
                add("SEARCH_PROVENANCE_GAP", f"{source_id} searched_at 不是 ISO 日期")
            elif _future(row.get("searched_at"), as_of):
                add("FUTURE_SEARCH_DATE", f"{source_id} searched_at 晚于 as_of")
            if not _hash(row.get("raw_sha256")):
                add("SEARCH_PROVENANCE_GAP", f"{source_id} SEARCHED 缺 raw SHA-256")
            if not isinstance(row.get("result_count"), int) or row["result_count"] < 0:
                add("SEARCH_COUNT_INVALID", f"{source_id} result_count 非非负整数")
            else:
                source_result_total += row["result_count"]
                source_result_counts[source_id] = row["result_count"]
        elif state == "UNAVAILABLE":
            unavailable += 1
            if not _real(row.get("failure")):
                add("UNAVAILABLE_REASON_GAP", f"{source_id} UNAVAILABLE 缺 failure")

    query_ledger = spec.get("query_ledger")
    query_result_counts: dict[str, int] = {}
    if query_ledger in (None, []):
        if review_type in {"SYSTEMATIC", "RAPID"}:
            add("QUERY_LEDGER_GAP", "SYSTEMATIC/RAPID 缺 query_ledger，无法审计检索式、用途与原始响应")
    elif not isinstance(query_ledger, list):
        raise ValueError("query_ledger 必须是 list")
    else:
        query_ids: set[str] = set()
        for row in query_ledger:
            if not isinstance(row, dict):
                raise ValueError("query_ledger item 必须是 object")
            query_id = str(row.get("query_id") or "")
            source_id = str(row.get("source_id") or "")
            run_status = row.get("run_status")
            if not query_id or query_id in query_ids:
                add("QUERY_LEDGER_INVALID", "query_id 缺失或重复")
                continue
            query_ids.add(query_id)
            if source_id not in source_ids or run_status not in QUERY_STATES:
                add("QUERY_LEDGER_INVALID", f"{query_id} source_id/run_status 非法")
                continue
            for field in ("purpose", "query", "eligibility_link"):
                if not _real(row.get(field)):
                    add("QUERY_LEDGER_GAP", f"{query_id} 缺 {field}")
            if run_status == "RUN":
                if source_id not in searched_source_ids:
                    add("QUERY_SOURCE_STATE_MISMATCH", f"{query_id} RUN 但 source {source_id} 不是 SEARCHED")
                for field in ("searched_at", "endpoint", "raw_locator"):
                    if not _real(row.get(field)):
                        add("QUERY_RUN_PROVENANCE_GAP", f"{query_id} RUN 缺 {field}")
                if _real(row.get("searched_at")) and not _date(row.get("searched_at")):
                    add("QUERY_RUN_PROVENANCE_GAP", f"{query_id} searched_at 不是 ISO 日期")
                elif _future(row.get("searched_at"), as_of):
                    add("FUTURE_QUERY_DATE", f"{query_id} searched_at 晚于 as_of")
                if not _hash(row.get("raw_sha256")):
                    add("QUERY_RUN_PROVENANCE_GAP", f"{query_id} RUN 缺 raw SHA-256")
                if not _non_negative_int(row.get("result_count")):
                    add("QUERY_COUNT_INVALID", f"{query_id} result_count 非非负整数")
                else:
                    query_result_counts[source_id] = (
                        query_result_counts.get(source_id, 0) + row["result_count"]
                    )
            elif run_status == "UNAVAILABLE":
                if not _real(row.get("failure")):
                    add("QUERY_UNAVAILABLE_REASON_GAP", f"{query_id} UNAVAILABLE 缺 failure")
            elif not _real(row.get("skip_reason")):
                add("QUERY_SKIP_REASON_GAP", f"{query_id} SKIPPED 缺 skip_reason")
        for source_id in searched_source_ids:
            if source_id not in query_result_counts:
                add("SOURCE_WITHOUT_QUERY_LEDGER", f"{source_id} SEARCHED 但没有 RUN query ledger")
            elif query_result_counts[source_id] != source_result_counts.get(source_id, 0):
                add(
                    "QUERY_SOURCE_COUNT_MISMATCH",
                    f"{source_id} query_ledger result_count 之和不等于 source.result_count",
                )

    if review_type in {"SYSTEMATIC", "RAPID"} and len(searched_families) < 2:
        add(
            "SOURCE_FAMILY_COVERAGE_GAP",
            "SYSTEMATIC/RAPID 至少需要两个独立 source family，或降级 review_type",
        )
    if not searched_families:
        add("NO_SOURCE_SEARCHED", "没有任何 SEARCHED source")

    coverage_audit = spec.get("coverage_audit")
    if coverage_audit in (None, {}):
        if review_type in {"SYSTEMATIC", "RAPID"}:
            add("COVERAGE_AUDIT_GAP", "SYSTEMATIC/RAPID 缺 coverage_audit")
        coverage_audit = {}
    elif not isinstance(coverage_audit, dict):
        raise ValueError("coverage_audit 必须是 object")

    known_items = coverage_audit.get("known_items")
    if known_items is None:
        if review_type in {"SYSTEMATIC", "RAPID"}:
            add("KNOWN_ITEM_AUDIT_GAP", "SYSTEMATIC/RAPID 缺 known_items 召回校验")
    elif not isinstance(known_items, list):
        raise ValueError("known_items 必须是 list")
    else:
        if not known_items and review_type in {"SYSTEMATIC", "RAPID"}:
            if not _real(coverage_audit.get("no_known_items_rationale")):
                add("KNOWN_ITEM_AUDIT_GAP", "没有 known_items 时必须说明 no_known_items_rationale")
        for row in known_items:
            if not isinstance(row, dict):
                raise ValueError("known_items item 必须是 object")
            item_id = str(row.get("item_id") or "")
            has_identity = any(_real(row.get(field)) for field in ("doi", "title", "citation"))
            if not _real(item_id) or not has_identity or not _real(row.get("expected_reason")):
                add("KNOWN_ITEM_PROVENANCE_GAP", "known item 缺 item_id/identity/expected_reason")
            if row.get("must_retrieve", True) and row.get("retrieved") is not True:
                add("KNOWN_ITEM_MISSED", f"{item_id or '<unknown>'} 是应召回 known item 但未检出")
            if row.get("retrieved") is True:
                evidence_source_ids = row.get("evidence_source_ids")
                if not isinstance(evidence_source_ids, list) or not evidence_source_ids:
                    add("KNOWN_ITEM_EVIDENCE_GAP", f"{item_id} retrieved 但缺 evidence_source_ids")
                else:
                    for source_id in evidence_source_ids:
                        if source_id not in searched_source_ids:
                            add("KNOWN_ITEM_EVIDENCE_GAP", f"{item_id} evidence source 未被 SEARCHED: {source_id}")
                if not _real(row.get("locator")):
                    add("KNOWN_ITEM_EVIDENCE_GAP", f"{item_id} retrieved 但缺 locator")

    citation_chaining = coverage_audit.get("citation_chaining") or []
    if not isinstance(citation_chaining, list):
        raise ValueError("citation_chaining 必须是 list")
    if not citation_chaining and review_type == "SYSTEMATIC":
        if not _real(coverage_audit.get("no_citation_chaining_rationale")):
            add("CITATION_CHAINING_GAP", "SYSTEMATIC 缺 citation_chaining 或 no_citation_chaining_rationale")
    for row in citation_chaining:
        if not isinstance(row, dict):
            raise ValueError("citation_chaining item 必须是 object")
        seed_status = str(row.get("seed_screening_status") or "").upper()
        direction = str(row.get("direction") or "").upper()
        seed_id = str(row.get("seed_item_id") or "")
        if not _real(seed_id) or seed_status not in SCREENING_STATES or direction not in CHAIN_DIRECTIONS:
            add("CITATION_CHAINING_INVALID", "citation_chaining 缺 seed/status/direction")
        if not _non_negative_int(row.get("round")) or row.get("round") == 0:
            add("CITATION_CHAINING_INVALID", f"{seed_id or '<unknown>'} round 必须是正整数")
        if not _non_negative_int(row.get("new_records")):
            add("CITATION_CHAINING_INVALID", f"{seed_id or '<unknown>'} new_records 非非负整数")
        if not _hash(row.get("raw_sha256")):
            add("CITATION_CHAINING_PROVENANCE_GAP", f"{seed_id or '<unknown>'} 缺 raw SHA-256")
        if not _real(row.get("raw_locator")):
            add("CITATION_CHAINING_PROVENANCE_GAP", f"{seed_id or '<unknown>'} 缺 raw_locator")
        if seed_status in SCREENING_STATES and seed_status != "INCLUDED":
            if not _real(row.get("exploratory_override")):
                add(
                    "SNOWBALL_FROM_NONINCLUDED_SEED",
                    f"{seed_id or '<unknown>'} 不是 INCLUDED seed；系统检索不得把 excluded/unscreened 节点当扩展根",
                )

    if review_type in {"SYSTEMATIC", "RAPID"}:
        summary = coverage_audit.get("summary") or {}
        if not isinstance(summary, dict):
            raise ValueError("coverage_audit.summary 必须是 object")
        for field in (
            "source_coverage_basis", "known_item_recall_basis",
            "citation_yield_basis", "unavailable_impact",
        ):
            if not _real(summary.get(field)):
                add("COVERAGE_SUMMARY_GAP", f"coverage_audit.summary 缺 {field}")

    accounting = spec.get("accounting") or {}
    identified = accounting.get("identified")
    duplicates = accounting.get("duplicates_removed")
    screened = accounting.get("screened")
    excluded = accounting.get("screen_excluded")
    included = accounting.get("included")
    values = (identified, duplicates, screened, excluded, included)
    if not all(isinstance(x, int) and x >= 0 for x in values):
        add("ACCOUNTING_INVALID", "identified/dedup/screen/excluded/included 必须是非负整数")
    else:
        if identified != source_result_total:
            add("SOURCE_ACCOUNTING_MISMATCH", "各 SEARCHED source 的 result_count 之和不等于 identified")
        if identified - duplicates != screened:
            add("ACCOUNTING_MISMATCH", "identified - duplicates_removed != screened")
        if screened - excluded < included:
            add("ACCOUNTING_MISMATCH", "included 超过筛选后剩余记录")
    reasons = accounting.get("exclusion_reasons") or {}
    reasons_valid = (
        isinstance(reasons, dict)
        and all(_real(key) and isinstance(value, int) and value >= 0
                for key, value in reasons.items())
    )
    if not reasons_valid or (
        isinstance(excluded, int) and sum(reasons.values()) != excluded
    ):
        add("EXCLUSION_REASON_MISMATCH", "排除原因计数未与 screen_excluded 勾稽")
    if not _real(accounting.get("dedup_method")):
        add("DEDUP_METHOD_GAP", "缺 dedup_method")

    stop = spec.get("stop_rule") or {}
    for field in ("rule", "max_rounds", "rounds_completed"):
        if stop.get(field) in (None, ""):
            add("STOP_RULE_GAP", f"stop_rule.{field} 缺失")
    max_rounds = stop.get("max_rounds")
    rounds = stop.get("rounds_completed")
    if isinstance(max_rounds, int) and isinstance(rounds, int):
        if max_rounds <= 0 or rounds < 0:
            add("STOP_RULE_INVALID", "max_rounds 必须大于 0，rounds_completed 不得为负")
        elif rounds > max_rounds:
            add("STOP_BUDGET_BREACH", "rounds_completed 超过 max_rounds")
        if stop.get("stopped") and not _real(stop.get("observed_basis")):
            add("STOP_EVIDENCE_GAP", "声明 stopped 但缺 observed_basis")
        if stop.get("stopped") and (
            not _real(stop.get("observed_locator"))
            or not _hash(stop.get("observed_sha256"))
        ):
            add("STOP_EVIDENCE_GAP", "声明 stopped 必须绑定 observed_locator 与 observed_sha256")
    else:
        add("STOP_RULE_INVALID", "max_rounds/rounds_completed 必须是整数")
    if str(spec.get("coverage_claim") or "").upper() in {"EXHAUSTIVE", "COMPLETE"}:
        add("EXHAUSTIVE_CLAIM_FORBIDDEN", "检索不能仅凭当前协议宣称 exhaustive/complete")
    if unavailable:
        add(
            "SOURCE_UNAVAILABLE_VISIBLE",
            f"{unavailable} 个计划来源不可用；覆盖结论必须保留该缺口",
            "unresolved",
        )

    amendments = spec.get("amendments") or []
    if protocol_state == "AMENDED" and not amendments:
        add("AMENDMENT_LEDGER_GAP", "protocol_state=AMENDED 但无 amendment ledger")
    for row in amendments:
        if not isinstance(row, dict) or not all(
            _real(row.get(field)) for field in ("changed_at", "reason", "authorization_id")
        ):
            add("AMENDMENT_PROVENANCE_GAP", "amendment 缺 date/reason/authorization")
        elif not _date(row.get("changed_at")):
            add("AMENDMENT_PROVENANCE_GAP", "amendment changed_at 不是 ISO 日期")
        elif _future(row.get("changed_at"), as_of):
            add("FUTURE_AMENDMENT_DATE", "amendment changed_at 晚于 as_of")

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.search_protocol_report.v1", "status": status,
        "searched_source_families": sorted(searched_families),
        "query_count": len(query_ledger) if isinstance(query_ledger, list) else 0,
        "known_items_checked": len(known_items) if isinstance(known_items, list) else 0,
        "issues": issues,
        "honesty": (
            "PASS 证明协议字段、来源证据与计数闭合；不证明召回穷尽、全文判断正确或研究空白真实。"
        ),
    }


def _base() -> dict[str, Any]:
    h = "sha256:" + "e" * 64
    spec = {
        "schema": SCHEMA_ID, "review_type": "SYSTEMATIC", "protocol_state": "FROZEN",
        "question": {
            "research_question": "What methods address X?", "concepts": ["X", "method"],
            "scope_boundary": "declared domain",
        },
        "eligibility": {
            "include": ["empirical studies"], "exclude": ["editorials"],
            "date_range": "2000-2026", "languages": ["English"],
            "document_types": ["article", "preprint"],
        },
        "scope_decision": {
            "decision_id": "scope-selftest-001",
            "basis": "USER_CONFIRMED",
            "decided_at": "2026-07-01",
            "evidence_locator": "decisions/scope-selftest-001.json",
            "evidence_sha256": h,
            "selection": {
                "review_type": "SYSTEMATIC",
                "research_question": "What methods address X?",
                "scope_boundary": "declared domain",
                "date_range": "2000-2026",
                "languages": ["English"],
                "document_types": ["article", "preprint"],
            },
        },
        "sources": [
            {"source_id": "s1", "family": "bibliographic-index", "status": "SEARCHED",
             "reason": "broad discovery", "query": "exact query 1", "searched_at": "2026-07-04",
             "endpoint": "https://example.invalid/api1", "raw_locator": "raw/s1.json",
             "raw_sha256": h, "result_count": 8},
            {"source_id": "s2", "family": "domain-index", "status": "SEARCHED",
             "reason": "domain coverage", "query": "exact query 2", "searched_at": "2026-07-04",
             "endpoint": "https://example.invalid/api2", "raw_locator": "raw/s2.json",
             "raw_sha256": h, "result_count": 7},
        ],
        "query_ledger": [
            {"query_id": "q1", "source_id": "s1", "purpose": "broad discovery",
             "query": "exact query 1", "eligibility_link": "maps concept X and method",
             "run_status": "RUN", "searched_at": "2026-07-04",
             "endpoint": "https://example.invalid/api1", "raw_locator": "raw/q1.json",
             "raw_sha256": h, "result_count": 8},
            {"query_id": "q2", "source_id": "s2", "purpose": "domain-index recall",
             "query": "exact query 2", "eligibility_link": "domain-specific vocabulary",
             "run_status": "RUN", "searched_at": "2026-07-04",
             "endpoint": "https://example.invalid/api2", "raw_locator": "raw/q2.json",
             "raw_sha256": h, "result_count": 7},
        ],
        "coverage_audit": {
            "known_items": [
                {"item_id": "k1", "doi": "10.0000/example",
                 "expected_reason": "known seminal or seed work in scope", "must_retrieve": True,
                 "retrieved": True, "evidence_source_ids": ["s1"],
                 "locator": "domain_map.json#/records/0"}
            ],
            "citation_chaining": [
                {"seed_item_id": "k1", "seed_screening_status": "INCLUDED",
                 "direction": "BACKWARD", "round": 1, "new_records": 0,
                 "raw_locator": "raw/chaining-k1-backward.json", "raw_sha256": h}
            ],
            "summary": {
                "source_coverage_basis": "two independent source families searched",
                "known_item_recall_basis": "known in-scope seed k1 retrieved from s1",
                "citation_yield_basis": "backward chaining over included seed yielded no new records",
                "unavailable_impact": "no planned source unavailable",
            },
        },
        "accounting": {
            "identified": 15, "duplicates_removed": 3, "screened": 12,
            "screen_excluded": 7, "included": 5,
            "exclusion_reasons": {"out_of_scope": 5, "wrong_type": 2},
            "dedup_method": "normalized DOI then title/year",
        },
        "stop_rule": {
            "rule": "two rounds with no new eligible concept family",
            "max_rounds": 5, "rounds_completed": 3, "stopped": True,
            "observed_basis": "rounds 2-3 added no new eligible concept family",
            "observed_locator": "raw/stop-rounds-2-3.json", "observed_sha256": h,
        },
        "coverage_claim": "SYSTEMATIC_PROTOCOL_COVERAGE",
        "amendments": [],
    }
    spec["protocol_lock"] = {
        "protocol_sha256": _content_sha256(spec), "frozen_at": "2026-07-01"
    }
    return spec


def _selftest() -> int:
    assert evaluate(_base(), dt.date(2026, 7, 5))["status"] == "PASS"
    missing_scope_decision = json.loads(json.dumps(_base()))
    missing_scope_decision.pop("scope_decision")
    assert "SCOPE_DECISION_GAP" in {
        x["code"] for x in evaluate(missing_scope_decision, dt.date(2026, 7, 5))["issues"]
    }
    agent_default_systematic = json.loads(json.dumps(_base()))
    agent_default_systematic["scope_decision"]["basis"] = "AGENT_DEFAULT_DISCLOSED"
    assert "SCOPE_DECISION_NOT_USER_AUTHORIZED" in {
        x["code"] for x in evaluate(agent_default_systematic, dt.date(2026, 7, 5))["issues"]
    }
    drifted_scope_decision = json.loads(json.dumps(_base()))
    drifted_scope_decision["scope_decision"]["selection"]["date_range"] = "2020-2026"
    assert "SCOPE_DECISION_MISMATCH" in {
        x["code"] for x in evaluate(drifted_scope_decision, dt.date(2026, 7, 5))["issues"]
    }
    future_scope_decision = json.loads(json.dumps(_base()))
    future_scope_decision["scope_decision"]["decided_at"] = "2026-07-06"
    assert "FUTURE_SCOPE_DECISION" in {
        x["code"] for x in evaluate(future_scope_decision, dt.date(2026, 7, 5))["issues"]
    }
    one_source = json.loads(json.dumps(_base()))
    one_source["sources"] = one_source["sources"][:1]
    assert "SOURCE_FAMILY_COVERAGE_GAP" in {
        x["code"] for x in evaluate(one_source, dt.date(2026, 7, 5))["issues"]
    }
    bad_family = json.loads(json.dumps(_base()))
    bad_family["sources"][1]["family"] = "Bibliographic Index "
    assert "SOURCE_FAMILY_COVERAGE_GAP" in {
        x["code"] for x in evaluate(bad_family, dt.date(2026, 7, 5))["issues"]
    }
    bad_count = json.loads(json.dumps(_base()))
    bad_count["accounting"]["screened"] = 11
    assert evaluate(bad_count, dt.date(2026, 7, 5))["status"] == "FAIL"
    bad_reasons = json.loads(json.dumps(_base()))
    bad_reasons["accounting"]["exclusion_reasons"]["wrong_type"] = "2"
    assert "EXCLUSION_REASON_MISMATCH" in {
        x["code"] for x in evaluate(bad_reasons, dt.date(2026, 7, 5))["issues"]
    }
    unlocked = json.loads(json.dumps(_base()))
    unlocked.pop("protocol_lock")
    assert "PROTOCOL_LOCK_GAP" in {
        x["code"] for x in evaluate(unlocked, dt.date(2026, 7, 5))["issues"]
    }
    stale_lock = json.loads(json.dumps(_base()))
    stale_lock["question"]["research_question"] = "changed after freeze"
    assert "PROTOCOL_LOCK_MISMATCH" in {
        x["code"] for x in evaluate(stale_lock, dt.date(2026, 7, 5))["issues"]
    }
    future_search = json.loads(json.dumps(_base()))
    future_search["sources"][0]["searched_at"] = "2026-07-06"
    assert "FUTURE_SEARCH_DATE" in {
        x["code"] for x in evaluate(future_search, dt.date(2026, 7, 5))["issues"]
    }
    missing_raw_locator = json.loads(json.dumps(_base()))
    del missing_raw_locator["query_ledger"][0]["raw_locator"]
    assert "QUERY_RUN_PROVENANCE_GAP" in {
        x["code"] for x in evaluate(missing_raw_locator, dt.date(2026, 7, 5))["issues"]
    }
    bad_source_total = json.loads(json.dumps(_base()))
    bad_source_total["sources"][0]["result_count"] = 9
    assert "SOURCE_ACCOUNTING_MISMATCH" in {
        x["code"] for x in evaluate(bad_source_total, dt.date(2026, 7, 5))["issues"]
    }
    query_count_mismatch = json.loads(json.dumps(_base()))
    query_count_mismatch["query_ledger"][0]["result_count"] = 9
    assert "QUERY_SOURCE_COUNT_MISMATCH" in {
        x["code"] for x in evaluate(query_count_mismatch, dt.date(2026, 7, 5))["issues"]
    }
    zero_budget = json.loads(json.dumps(_base()))
    zero_budget["stop_rule"]["max_rounds"] = 0
    assert "STOP_RULE_INVALID" in {
        x["code"] for x in evaluate(zero_budget, dt.date(2026, 7, 5))["issues"]
    }
    missing_stop_evidence = json.loads(json.dumps(_base()))
    del missing_stop_evidence["stop_rule"]["observed_sha256"]
    assert "STOP_EVIDENCE_GAP" in {
        x["code"] for x in evaluate(missing_stop_evidence, dt.date(2026, 7, 5))["issues"]
    }
    missed_known = json.loads(json.dumps(_base()))
    missed_known["coverage_audit"]["known_items"][0]["retrieved"] = False
    assert "KNOWN_ITEM_MISSED" in {
        x["code"] for x in evaluate(missed_known, dt.date(2026, 7, 5))["issues"]
    }
    bad_chain = json.loads(json.dumps(_base()))
    bad_chain["coverage_audit"]["citation_chaining"][0]["seed_screening_status"] = "EXCLUDED"
    assert "SNOWBALL_FROM_NONINCLUDED_SEED" in {
        x["code"] for x in evaluate(bad_chain, dt.date(2026, 7, 5))["issues"]
    }
    unavailable = json.loads(json.dumps(_base()))
    unavailable["sources"][1] = {
        "source_id": "s2", "family": "domain-index", "status": "UNAVAILABLE",
        "reason": "domain coverage", "failure": "HTTP 429",
    }
    assert evaluate(unavailable, dt.date(2026, 7, 5))["status"] == "FAIL"
    exhaustive = json.loads(json.dumps(_base()))
    exhaustive["coverage_claim"] = "EXHAUSTIVE"
    assert "EXHAUSTIVE_CLAIM_FORBIDDEN" in {
        x["code"] for x in evaluate(exhaustive, dt.date(2026, 7, 5))["issues"]
    }
    print(
        "search_protocol_gate selftest PASS: "
        "scope-decision/multi-source/query-ledger/known-item/chaining/"
        "accounting/stop/unavailable/no-exhaustive"
    )
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
    as_of = _date_value(args.as_of) if args.as_of else dt.date.today()
    if args.as_of and as_of is None:
        parser.error("--as-of 必须为 YYYY-MM-DD")
    report = evaluate(
        json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig")),
        as_of,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
