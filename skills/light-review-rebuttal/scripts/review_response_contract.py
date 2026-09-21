#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate lossless review atoms and truthful response actions.

This gate checks the stage-13 parts that are easy to over-trust in prose:
source spans, addressable-unit coverage, duplicate responses, DONE evidence,
policy/ethics authorization, reviewer context cards, and perspective-specific
self-review. It does not judge whether the scientific answer is persuasive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.review_response_contract.v1"
REPORT_SCHEMA = "light.review_response_gate.v1"

ACCESS_STATES = {"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "STALE"}
ISSUE_TYPES = {"request", "claim", "question", "misunderstanding", "editorial"}
ROOT_CAUSES = {
    "novelty", "experiment", "writing", "clarification", "citation",
    "ethics", "scope", "editorial",
}
ACTION_STATES = {"PLANNED", "IN_PROGRESS", "DONE", "DECLINED", "NOT_APPLICABLE"}
ACTION_KINDS = {
    "prose", "experiment", "analysis", "citation", "figure",
    "typesetting", "ethics", "scope", "editorial", "other",
}
EVIDENCE_KINDS = {
    "manuscript_diff", "manuscript_locator", "run_manifest",
    "result_artifact_hash", "analysis_report", "citation_registry",
    "figure_artifact", "typeset_pdf", "venue_policy", "editor_ruling",
    "ethics_approval", "limitation_record", "none",
}
VENUE_POLICY_STATES = {
    "VERIFIED_ALLOW", "VERIFIED_DISALLOW", "UNKNOWN",
    "UNAVAILABLE", "STALE", "NOT_APPLICABLE",
}
ETHICS_STATES = {"CLEAR", "UNKNOWN", "REQUIRES_REVIEW", "VIOLATES_POLICY", "NOT_APPLICABLE"}
USER_AUTH_STATES = {"APPROVED", "NOT_REQUIRED", "PENDING", "DENIED", "UNKNOWN"}
COMMITMENTS = {"COMMIT_RUN", "COMMIT_DONE", "PLAN_ONLY", "CLARIFY_ONLY", "REQUEST_RULING", "DECLINE"}
PERSPECTIVES = {"domain", "method", "statistics", "ethics", "cold_reader"}
SELF_REVIEW_STATES = {"PASS", "WARN", "FAIL", "UNKNOWN"}
COMPETENCE_STATES = {"IN_SCOPE", "PARTIAL", "OUT_OF_SCOPE", "UNKNOWN"}
CONFLICT_STATES = {"NONE", "POTENTIAL", "CONFIRMED", "UNKNOWN"}

DONE_WORDS = re.compile(
    r"\bwe (?:have )?(?:added|revised|conducted|changed|updated|corrected|run|ran)\b|"
    r"已(?:新增|添加|修改|完成|补充|运行|修订)",
    re.I,
)
FUTURE_WORDS = re.compile(r"\b(?:will|plan(?:ned)? to|to be done|todo)\b|将|计划|拟|待补|尚未", re.I)
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_hash(value: Any) -> str:
    return str(value or "").removeprefix("sha256:")


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    return bool(text) and "<" not in text and "{{" not in text and "unknown" != lowered


def _is_sha(value: Any) -> bool:
    return bool(SHA256_RE.fullmatch(str(value or "")))


def _span_text(source: str, span: dict[str, Any]) -> tuple[bool, str]:
    try:
        start = int(span.get("start"))
        end = int(span.get("end"))
    except (TypeError, ValueError):
        return False, ""
    if start < 0 or end < start or end > len(source):
        return False, ""
    return True, source[start:end]


def _add(
    findings: list[dict[str, Any]],
    code: str,
    severity: str,
    detail: str,
    loc: str | None = None,
) -> None:
    findings.append({"code": code, "severity": severity, "loc": loc, "detail": detail})


def _source_map(spec: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for source in spec.get("sources") or []:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            _add(findings, "SOURCE_ID_MISSING", "critical", "source_id is required")
            continue
        access = str(source.get("access_status") or "UNKNOWN").upper()
        if access not in ACCESS_STATES:
            _add(findings, "INVALID_ACCESS_STATUS", "critical", access, source_id)
            access = "UNKNOWN"
        raw_text = str(source.get("raw_text") or "")
        if access == "AVAILABLE" and not raw_text:
            _add(findings, "AVAILABLE_SOURCE_WITHOUT_RAW", "critical", "AVAILABLE source needs raw_text", source_id)
        if source_id in sources:
            _add(findings, "DUPLICATE_SOURCE_ID", "critical", source_id, source_id)
        sources[source_id] = raw_text
        expected = source.get("raw_sha256")
        if expected and _clean_hash(expected) != _sha_text(raw_text):
            _add(findings, "SOURCE_HASH_MISMATCH", "critical", "raw_sha256 does not match raw_text", source_id)
    return sources


def _validate_span(
    *,
    span: dict[str, Any],
    raw_text: str,
    loc: str,
    findings: list[dict[str, Any]],
    code_prefix: str,
) -> str:
    ok, actual = _span_text(raw_text, span)
    expected = str(span.get("text") or "")
    if not ok:
        _add(findings, f"{code_prefix}_SPAN_BOUNDS_INVALID", "critical", "span start/end outside raw_text", loc)
        return expected
    if expected != actual:
        _add(findings, f"{code_prefix}_SPAN_TEXT_MISMATCH", "critical", "span.text is not exact raw_text[start:end]", loc)
    digest = span.get("sha256")
    if not digest:
        _add(findings, f"{code_prefix}_SPAN_HASH_MISSING", "critical", "source span needs sha256", loc)
    elif _clean_hash(digest) != _sha_text(expected):
        _add(findings, f"{code_prefix}_SPAN_HASH_MISMATCH", "critical", "span sha256 does not match span.text", loc)
    return expected


def _coverage(
    spec: dict[str, Any],
    sources: dict[str, str],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    units: dict[str, dict[str, Any]] = {}
    for unit in spec.get("coverage_units") or []:
        unit_id = str(unit.get("unit_id") or "")
        source_id = str(unit.get("source_id") or "")
        if not unit_id:
            _add(findings, "COVERAGE_UNIT_ID_MISSING", "critical", "coverage unit needs unit_id")
            continue
        if unit_id in units:
            _add(findings, "DUPLICATE_COVERAGE_UNIT", "critical", unit_id, unit_id)
        if source_id not in sources:
            _add(findings, "COVERAGE_UNIT_UNKNOWN_SOURCE", "critical", source_id, unit_id)
        span = unit.get("span") or {}
        if not isinstance(span, dict):
            _add(findings, "COVERAGE_UNIT_SPAN_MISSING", "critical", "span object required", unit_id)
        else:
            _validate_span(
                span=span,
                raw_text=sources.get(source_id, ""),
                loc=unit_id,
                findings=findings,
                code_prefix="COVERAGE_UNIT",
            )
        units[unit_id] = unit

    atom_units: dict[str, list[str]] = {}
    unit_to_atoms: dict[str, list[str]] = {unit_id: [] for unit_id in units}
    for atom in spec.get("atoms") or []:
        issue_id = str(atom.get("issue_id") or "")
        for unit_id in [str(value) for value in atom.get("unit_ids") or []]:
            atom_units.setdefault(issue_id, []).append(unit_id)
            if unit_id not in units:
                _add(findings, "ATOM_UNKNOWN_COVERAGE_UNIT", "critical", unit_id, issue_id)
            else:
                unit_to_atoms.setdefault(unit_id, []).append(issue_id)

    for unit_id, unit in units.items():
        if unit.get("must_address", True) and not unit_to_atoms.get(unit_id):
            _add(findings, "MISSING_UNIT_COVERAGE", "critical", "addressable reviewer unit is not mapped to any atom", unit_id)
        linked = unit_to_atoms.get(unit_id) or []
        if len(set(linked)) > 1 and not unit.get("allow_split"):
            _add(findings, "DUPLICATE_UNIT_MAPPING", "critical", f"unit mapped to multiple atoms: {sorted(set(linked))}", unit_id)

    for recon in spec.get("source_reconstructions") or []:
        source_id = str(recon.get("source_id") or "")
        unit_ids = [str(value) for value in recon.get("unit_ids") or []]
        delimiter = str(recon.get("delimiter", "\n"))
        expected = recon.get("addressable_sha256")
        loc = source_id or "source_reconstruction"
        if source_id not in sources:
            _add(findings, "RECONSTRUCTION_UNKNOWN_SOURCE", "critical", source_id, loc)
            continue
        if not expected:
            _add(findings, "RECONSTRUCTION_HASH_MISSING", "critical", "addressable reconstruction needs sha256", loc)
            continue
        missing = [unit_id for unit_id in unit_ids if unit_id not in units]
        if missing:
            _add(findings, "RECONSTRUCTION_UNKNOWN_UNIT", "critical", ", ".join(missing), loc)
            continue
        text = delimiter.join(str((units[unit_id].get("span") or {}).get("text") or "") for unit_id in unit_ids)
        if _clean_hash(expected) != _sha_text(text):
            _add(findings, "RECONSTRUCTION_HASH_MISMATCH", "critical", "unit order/text does not match addressable_sha256", loc)
    return units, atom_units


def _atoms(
    spec: dict[str, Any],
    sources: dict[str, str],
    findings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    atoms: dict[str, dict[str, Any]] = {}
    for atom in spec.get("atoms") or []:
        issue_id = str(atom.get("issue_id") or "")
        if not issue_id:
            _add(findings, "ATOM_ID_MISSING", "critical", "atom needs issue_id")
            continue
        if issue_id in atoms:
            _add(findings, "DUPLICATE_ATOM_ID", "critical", issue_id, issue_id)
        source_id = str(atom.get("source_id") or "")
        if source_id not in sources:
            _add(findings, "ATOM_UNKNOWN_SOURCE", "critical", source_id, issue_id)
        span = atom.get("source_span") or {}
        if not isinstance(span, dict):
            _add(findings, "ATOM_SOURCE_SPAN_MISSING", "critical", "source_span object required", issue_id)
        else:
            _validate_span(
                span=span,
                raw_text=sources.get(source_id, ""),
                loc=issue_id,
                findings=findings,
                code_prefix="ATOM",
            )
        if str(atom.get("issue_type") or "").lower() not in ISSUE_TYPES:
            _add(findings, "INVALID_ISSUE_TYPE", "critical", str(atom.get("issue_type")), issue_id)
        if str(atom.get("root_cause") or "").lower() not in ROOT_CAUSES:
            _add(findings, "INVALID_ROOT_CAUSE", "critical", str(atom.get("root_cause")), issue_id)
        if not atom.get("interpretation"):
            _add(findings, "ATOM_INTERPRETATION_MISSING", "major", "interpretation layer should be explicit", issue_id)
        atoms[issue_id] = atom
    return atoms


def _evidence_kinds(evidence: Any, action_id: str, findings: list[dict[str, Any]]) -> set[str]:
    if not isinstance(evidence, list):
        _add(findings, "ACTION_EVIDENCE_NOT_LIST", "critical", "evidence must be a list", action_id)
        return set()
    kinds: set[str] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            _add(findings, "ACTION_EVIDENCE_ITEM_INVALID", "critical", f"evidence[{index}] must be object", action_id)
            continue
        kind = str(item.get("kind") or "")
        kinds.add(kind)
        if kind not in EVIDENCE_KINDS:
            _add(findings, "UNKNOWN_EVIDENCE_KIND", "critical", kind, action_id)
        if kind != "none" and not _real(item.get("locator") or item.get("value")):
            _add(findings, "EVIDENCE_LOCATOR_MISSING", "critical", f"{kind} needs locator/value", action_id)
        if item.get("sha256") and not _is_sha(item.get("sha256")):
            _add(findings, "EVIDENCE_HASH_INVALID", "critical", f"{kind} has invalid sha256", action_id)
    return kinds


def _commits_new_result(action: dict[str, Any], status: str, commitment: str) -> bool:
    kind = str(action.get("action_kind") or "").lower()
    return kind in {"experiment", "analysis"} and (
        status == "DONE" or commitment in {"COMMIT_RUN", "COMMIT_DONE"}
    )


def _policy(action: dict[str, Any], status: str, commitment: str, findings: list[dict[str, Any]], action_id: str) -> None:
    policy = action.get("policy_check") or {}
    if not isinstance(policy, dict):
        _add(findings, "POLICY_CHECK_INVALID", "critical", "policy_check must be object", action_id)
        return
    venue_state = str(policy.get("venue_new_material_state") or "UNKNOWN").upper()
    ethics_state = str(policy.get("ethics_state") or "UNKNOWN").upper()
    auth_state = str(policy.get("user_authorization") or "UNKNOWN").upper()
    if venue_state not in VENUE_POLICY_STATES:
        _add(findings, "INVALID_VENUE_POLICY_STATE", "critical", venue_state, action_id)
    if ethics_state not in ETHICS_STATES:
        _add(findings, "INVALID_ETHICS_STATE", "critical", ethics_state, action_id)
    if auth_state not in USER_AUTH_STATES:
        _add(findings, "INVALID_USER_AUTHORIZATION", "critical", auth_state, action_id)

    commits_new = _commits_new_result(action, status, commitment)
    if commits_new and venue_state != "VERIFIED_ALLOW":
        _add(findings, "NEW_RESULT_POLICY_NOT_VERIFIED_ALLOW", "critical", venue_state, action_id)
    if commits_new and auth_state not in {"APPROVED", "NOT_REQUIRED"}:
        _add(findings, "NEW_RESULT_AUTHORIZATION_GAP", "critical", auth_state, action_id)
    if commits_new and ethics_state in {"UNKNOWN", "REQUIRES_REVIEW"}:
        _add(findings, "ETHICS_CLEARANCE_GAP", "critical", ethics_state, action_id)
    if ethics_state == "VIOLATES_POLICY" and commitment not in {"DECLINE", "REQUEST_RULING"}:
        _add(findings, "ETHICS_POLICY_VIOLATION_ACTION", "critical", "reviewer request conflicts with policy/ethics; decline or request ruling", action_id)
    if venue_state == "VERIFIED_DISALLOW" and commitment not in {"DECLINE", "REQUEST_RULING", "CLARIFY_ONLY"}:
        _add(findings, "VENUE_POLICY_FORBIDS_ACTION", "critical", "venue policy disallows the committed action", action_id)
    if commits_new and not _real(policy.get("source")):
        _add(findings, "POLICY_SOURCE_MISSING", "critical", "committing new results needs venue/policy source", action_id)


def _actions(
    spec: dict[str, Any],
    atoms: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    action_by_issue: dict[str, list[str]] = {issue_id: [] for issue_id in atoms}
    for action in spec.get("actions") or []:
        action_id = str(action.get("action_id") or "")
        if not action_id:
            _add(findings, "ACTION_ID_MISSING", "critical", "action needs action_id")
            continue
        issue_ids = [str(value) for value in action.get("issue_ids") or []]
        if not issue_ids:
            _add(findings, "ACTION_WITHOUT_ISSUE", "critical", "action must bind issue_ids", action_id)
        for issue_id in issue_ids:
            if issue_id not in atoms:
                _add(findings, "ACTION_UNKNOWN_ISSUE", "critical", issue_id, action_id)
            else:
                action_by_issue.setdefault(issue_id, []).append(action_id)
        status = str(action.get("status") or "").upper()
        if status not in ACTION_STATES:
            _add(findings, "INVALID_ACTION_STATUS", "critical", status, action_id)
        kind = str(action.get("action_kind") or "").lower()
        if kind not in ACTION_KINDS:
            _add(findings, "INVALID_ACTION_KIND", "critical", kind, action_id)
        commitment = str(action.get("commitment") or "PLAN_ONLY").upper()
        if commitment not in COMMITMENTS:
            _add(findings, "INVALID_COMMITMENT", "critical", commitment, action_id)
        response = str(action.get("response_text") or "")
        if status in {"PLANNED", "IN_PROGRESS"} and DONE_WORDS.search(response):
            _add(findings, "PLANNED_AS_DONE", "critical", "planned/in-progress action is written as completed", action_id)
        if status == "DONE" and FUTURE_WORDS.search(response):
            _add(findings, "DONE_CONTAINS_FUTURE_LANGUAGE", "critical", "DONE action still uses future/planned language", action_id)
        if status == "DECLINED" and not _real(action.get("rationale")):
            _add(findings, "DECLINED_RATIONALE_MISSING", "major", "declined action needs rationale", action_id)
        evidence_kinds = _evidence_kinds(action.get("evidence") or [], action_id, findings)
        if status == "DONE":
            if not evidence_kinds or evidence_kinds == {"none"}:
                _add(findings, "DONE_EVIDENCE_MISSING", "critical", "DONE requires concrete evidence kind", action_id)
            if kind == "prose" and not ({"manuscript_diff", "manuscript_locator"} & evidence_kinds):
                _add(findings, "DONE_PROSE_LOCATOR_MISSING", "critical", "prose DONE needs manuscript diff/locator", action_id)
            if kind == "experiment" and not {"run_manifest", "result_artifact_hash"} <= evidence_kinds:
                _add(findings, "DONE_EXPERIMENT_PROVENANCE_GAP", "critical", "experiment DONE needs run manifest and result hash", action_id)
            if kind == "analysis" and not {"analysis_report", "result_artifact_hash"} <= evidence_kinds:
                _add(findings, "DONE_ANALYSIS_PROVENANCE_GAP", "critical", "analysis DONE needs report and result hash", action_id)
            if kind == "citation" and "citation_registry" not in evidence_kinds:
                _add(findings, "DONE_CITATION_REGISTRY_GAP", "critical", "citation DONE needs citation registry evidence", action_id)
            if kind == "figure" and "figure_artifact" not in evidence_kinds:
                _add(findings, "DONE_FIGURE_ARTIFACT_GAP", "critical", "figure DONE needs generated figure artifact", action_id)
        _policy(action, status, commitment, findings, action_id)

    for issue_id, atom in atoms.items():
        actions = action_by_issue.get(issue_id) or []
        if atom.get("response_required", True) and not actions:
            _add(findings, "ISSUE_WITHOUT_ACTION", "critical", "response-required atom has no action", issue_id)
        if len(actions) > 1 and not atom.get("allow_multiple_actions"):
            _add(findings, "DUPLICATE_ACTION_FOR_ISSUE", "critical", f"multiple actions for one issue: {actions}", issue_id)


def _self_review(spec: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    package_status = str((spec.get("package") or {}).get("status") or "DRAFT").upper()
    rows = spec.get("self_review") or []
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        perspective = str(row.get("perspective") or "").lower()
        status = str(row.get("status") or "UNKNOWN").upper()
        loc = perspective or "self_review"
        if perspective not in PERSPECTIVES:
            _add(findings, "INVALID_SELF_REVIEW_PERSPECTIVE", "critical", perspective, loc)
            continue
        if perspective in seen:
            _add(findings, "DUPLICATE_SELF_REVIEW_PERSPECTIVE", "critical", perspective, loc)
        if status not in SELF_REVIEW_STATES:
            _add(findings, "INVALID_SELF_REVIEW_STATUS", "critical", status, loc)
        if status in {"FAIL", "UNKNOWN"} and package_status in {"DRAFT_READY", "READY", "SUBMIT_READY"}:
            _add(findings, "UNRESOLVED_SELF_REVIEW_BLOCKER", "critical", f"{perspective} self-review is {status}", loc)
        if status == "WARN" and not _real(row.get("action_required")):
            _add(findings, "SELF_REVIEW_WARN_WITHOUT_ACTION", "major", "WARN needs action_required", loc)
        seen[perspective] = row
    for perspective in sorted(PERSPECTIVES - set(seen)):
        _add(findings, "MISSING_SELF_REVIEW_PERSPECTIVE", "critical", "required perspective-specific self-review missing", perspective)


def _reviewer_context(spec: dict[str, Any], sources: dict[str, str], findings: list[dict[str, Any]]) -> None:
    reviewer_ids = {
        str(source.get("reviewer_id"))
        for source in spec.get("sources") or []
        if source.get("reviewer_id")
    }
    cards: dict[str, dict[str, Any]] = {}
    for card in spec.get("reviewer_context") or []:
        reviewer_id = str(card.get("reviewer_id") or "")
        if not reviewer_id:
            _add(findings, "REVIEWER_CARD_ID_MISSING", "critical", "reviewer card needs reviewer_id")
            continue
        cards[reviewer_id] = card
        competence = card.get("competence") or {}
        conflict = card.get("conflict") or {}
        competence_state = str(competence.get("state") or "UNKNOWN").upper()
        conflict_state = str(conflict.get("state") or "UNKNOWN").upper()
        if competence_state not in COMPETENCE_STATES:
            _add(findings, "INVALID_REVIEWER_COMPETENCE", "critical", competence_state, reviewer_id)
        if conflict_state not in CONFLICT_STATES:
            _add(findings, "INVALID_REVIEWER_CONFLICT", "critical", conflict_state, reviewer_id)
        if competence_state != "UNKNOWN" and not _real(competence.get("evidence")):
            _add(findings, "REVIEWER_COMPETENCE_EVIDENCE_MISSING", "major", "competence label needs evidence", reviewer_id)
        if conflict_state in {"POTENTIAL", "CONFIRMED"} and not _real(conflict.get("evidence")):
            _add(findings, "REVIEWER_CONFLICT_EVIDENCE_MISSING", "major", "conflict label needs evidence", reviewer_id)
        if card.get("use_to_dismiss") and "editor_ruling" not in {
            str(item.get("kind") or "") for item in card.get("evidence") or [] if isinstance(item, dict)
        }:
            _add(findings, "REVIEWER_CONTEXT_USED_TO_DISMISS", "critical", "competence/conflict card cannot dismiss a comment without editor ruling", reviewer_id)
    for reviewer_id in sorted(reviewer_ids - set(cards)):
        _add(findings, "MISSING_REVIEWER_CONTEXT_CARD", "critical", "every reviewer needs competence/conflict context card", reviewer_id)
    if sources and not reviewer_ids:
        _add(findings, "NO_REVIEWER_IDS", "major", "sources should carry reviewer_id when available")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"expected {SCHEMA_ID}")
    findings: list[dict[str, Any]] = []
    sources = _source_map(spec, findings)
    _coverage(spec, sources, findings)
    atoms = _atoms(spec, sources, findings)
    _actions(spec, atoms, findings)
    _self_review(spec, findings)
    _reviewer_context(spec, sources, findings)
    critical = sum(1 for item in findings if item["severity"] == "critical")
    major = sum(1 for item in findings if item["severity"] == "major")
    return {
        "schema": REPORT_SCHEMA,
        "verdict": "FAIL" if critical else ("WARN" if major else "PASS"),
        "counts": {
            "sources": len(sources),
            "coverage_units": len(spec.get("coverage_units") or []),
            "atoms": len(atoms),
            "actions": len(spec.get("actions") or []),
            "findings": len(findings),
            "critical": critical,
            "major": major,
        },
        "findings": findings,
        "boundary": (
            "This gate verifies source-span hashes, addressable-unit coverage, duplicate "
            "actions, DONE evidence, policy/ethics authorization, reviewer context cards, "
            "and perspective-specific self-review. It does not prove the response is persuasive."
        ),
    }


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _span(raw: str, text: str) -> dict[str, Any]:
    start = raw.index(text)
    end = start + len(text)
    return {"start": start, "end": end, "text": text, "sha256": _sha_text(text)}


def _good_fixture() -> dict[str, Any]:
    raw = "The novelty is unclear. Please add an ablation. Section 3 is difficult to follow."
    u1 = _span(raw, "The novelty is unclear.")
    u2 = _span(raw, "Please add an ablation.")
    u3 = _span(raw, "Section 3 is difficult to follow.")
    recon = "\n".join([u1["text"], u2["text"], u3["text"]])
    return {
        "schema": SCHEMA_ID,
        "package": {"status": "DRAFT_READY"},
        "sources": [{
            "source_id": "r1",
            "reviewer_id": "R1",
            "access_status": "AVAILABLE",
            "raw_text": raw,
            "raw_sha256": _sha_text(raw),
        }],
        "coverage_units": [
            {"unit_id": "U1", "source_id": "r1", "span": u1, "must_address": True},
            {"unit_id": "U2", "source_id": "r1", "span": u2, "must_address": True},
            {"unit_id": "U3", "source_id": "r1", "span": u3, "must_address": True},
        ],
        "source_reconstructions": [{
            "source_id": "r1",
            "unit_ids": ["U1", "U2", "U3"],
            "delimiter": "\n",
            "addressable_sha256": _sha_text(recon),
        }],
        "atoms": [
            {
                "issue_id": "R1-N",
                "source_id": "r1",
                "unit_ids": ["U1"],
                "source_span": u1,
                "issue_type": "claim",
                "root_cause": "novelty",
                "interpretation": "Novelty framing is insufficiently explicit.",
                "response_required": True,
            },
            {
                "issue_id": "R1-E",
                "source_id": "r1",
                "unit_ids": ["U2"],
                "source_span": u2,
                "issue_type": "request",
                "root_cause": "experiment",
                "interpretation": "Reviewer requests an ablation; venue policy permits new results.",
                "response_required": True,
            },
            {
                "issue_id": "R1-W",
                "source_id": "r1",
                "unit_ids": ["U3"],
                "source_span": u3,
                "issue_type": "claim",
                "root_cause": "writing",
                "interpretation": "Section 3 needs clearer exposition.",
                "response_required": True,
            },
        ],
        "actions": [
            {
                "action_id": "A-N",
                "issue_ids": ["R1-N"],
                "status": "PLANNED",
                "action_kind": "prose",
                "commitment": "PLAN_ONLY",
                "response_text": "We will clarify the novelty framing after the writing pass.",
                "evidence": [{"kind": "none", "locator": "planned"}],
                "policy_check": {
                    "venue_new_material_state": "NOT_APPLICABLE",
                    "ethics_state": "NOT_APPLICABLE",
                    "user_authorization": "NOT_REQUIRED",
                },
            },
            {
                "action_id": "A-E",
                "issue_ids": ["R1-E"],
                "status": "DONE",
                "action_kind": "experiment",
                "commitment": "COMMIT_DONE",
                "response_text": "We have run the ablation and report it in Table 4.",
                "evidence": [
                    {"kind": "run_manifest", "locator": "runs/ablation/manifest.json"},
                    {"kind": "result_artifact_hash", "locator": "runs/ablation/results.json", "sha256": "a" * 64},
                ],
                "policy_check": {
                    "venue_new_material_state": "VERIFIED_ALLOW",
                    "ethics_state": "CLEAR",
                    "user_authorization": "APPROVED",
                    "source": "https://venue.example/revision-policy",
                },
            },
            {
                "action_id": "A-W",
                "issue_ids": ["R1-W"],
                "status": "DONE",
                "action_kind": "prose",
                "commitment": "COMMIT_DONE",
                "response_text": "We have revised Section 3 for readability.",
                "evidence": [{"kind": "manuscript_diff", "locator": "diff.md#section-3"}],
                "policy_check": {
                    "venue_new_material_state": "NOT_APPLICABLE",
                    "ethics_state": "NOT_APPLICABLE",
                    "user_authorization": "NOT_REQUIRED",
                },
            },
        ],
        "self_review": [
            {"perspective": "domain", "status": "PASS"},
            {"perspective": "method", "status": "PASS"},
            {"perspective": "statistics", "status": "PASS"},
            {"perspective": "ethics", "status": "PASS"},
            {"perspective": "cold_reader", "status": "PASS"},
        ],
        "reviewer_context": [{
            "reviewer_id": "R1",
            "competence": {"state": "IN_SCOPE", "evidence": "review discusses method details"},
            "conflict": {"state": "NONE", "evidence": "no conflict signal in review packet"},
            "use_to_dismiss": False,
            "evidence": [],
        }],
    }


def _selftest() -> int:
    good = _good_fixture()
    assert evaluate(good)["verdict"] == "PASS"

    bad = json.loads(json.dumps(good))
    bad["coverage_units"].append({
        "unit_id": "U4",
        "source_id": "r1",
        "span": _span(bad["sources"][0]["raw_text"], "Please add an ablation."),
        "must_address": True,
    })
    bad["atoms"][0]["unit_ids"] = ["U1", "U2"]
    bad["atoms"][1]["unit_ids"] = ["U2"]
    bad["actions"].append(json.loads(json.dumps(bad["actions"][0])))
    bad["actions"][-1]["action_id"] = "A-N-duplicate"
    bad["actions"][0]["response_text"] = "We have revised the novelty section."
    bad["actions"][1]["policy_check"]["venue_new_material_state"] = "UNKNOWN"
    bad["actions"][1]["policy_check"]["ethics_state"] = "VIOLATES_POLICY"
    bad["self_review"] = [row for row in bad["self_review"] if row["perspective"] != "statistics"]
    bad["reviewer_context"][0]["use_to_dismiss"] = True
    report = evaluate(bad)
    codes = {item["code"] for item in report["findings"]}
    assert report["verdict"] == "FAIL"
    assert {
        "MISSING_UNIT_COVERAGE",
        "DUPLICATE_UNIT_MAPPING",
        "DUPLICATE_ACTION_FOR_ISSUE",
        "PLANNED_AS_DONE",
        "NEW_RESULT_POLICY_NOT_VERIFIED_ALLOW",
        "ETHICS_POLICY_VIOLATION_ACTION",
        "MISSING_SELF_REVIEW_PERSPECTIVE",
        "REVIEWER_CONTEXT_USED_TO_DISMISS",
    } <= codes

    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "contract.json"
        write_json(path, good)
        assert evaluate(read_json(path))["verdict"] == "PASS"
    print("[selftest] PASS review_response_contract: atoms/actions/policy/self-review")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--input")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("--input is required unless --selftest is used")
    try:
        report = evaluate(read_json(pathlib.Path(args.input)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[review_response_contract] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
