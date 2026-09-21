#!/usr/bin/env python3
"""Build the canonical stage-13 review, revision, and response package.

The workflow verifies the selected venue/context and stage-11 PDF facts, keeps
reviewer wording immutable, validates author-supplied atomic interpretations,
binds every issue to claims/evidence/actions, and emits auditable artifacts.
It formats supplied response text; it does not invent scientific content.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

INPUT_SCHEMA = "light.review_rebuttal_input.v2"
SELECTED_SCHEMA = "light.selected_venue_handoff.v1"
VENUE_CONTEXT_SCHEMA = "light.review_rebuttal_venue_context.v1"
SOURCE_EVIDENCE_SCHEMA = "light.venue_source_evidence.v1"
REGISTRY_SCHEMA = "light.review_registry.v1"
ISSUE_SCHEMA = "light.review_issue_matrix.v1"
PLAN_SCHEMA = "light.revision_plan.v1"
CHANGE_SCHEMA = "light.evidence_change_map.v1"
LEDGER_SCHEMA = "light.commitment_ledger.v1"
UNKNOWN_SCHEMA = "light.review_unknowns.v1"
FAILURE_SCHEMA = "light.review_failure.v1"
DELIVERY_SCHEMA = "light.review_rebuttal_delivery.v1"

ACCESS_STATES = {"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "STALE"}
ISSUE_TYPES = {"request", "claim", "question", "misunderstanding", "editorial"}
ROOT_CAUSES = {
    "novelty", "experiment", "writing", "clarification", "citation",
    "ethics", "scope", "editorial",
}
STRATEGIES = {
    "acknowledge_and_fix", "rebut_with_evidence", "clarify",
    "downgrade_claim", "request_editor_ruling",
}
ACTION_STATES = {"PLANNED", "IN_PROGRESS", "DONE", "DECLINED", "NOT_APPLICABLE"}
DONE_WORDS = re.compile(
    r"\bwe (?:have )?(?:added|revised|conducted|changed|updated|corrected)\b|"
    r"已(?:新增|添加|修改|完成|补充|运行|修订)",
    re.I,
)
FUTURE_WORDS = re.compile(r"\b(?:will|plan(?:ned)? to|to be done|todo)\b|将|计划|拟|待补|尚未", re.I)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _timestamp_with_tz(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _sha256_value(value: Any) -> str | None:
    text = str(value or "").strip().lower().removeprefix("sha256:")
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else None


def resolve(base: pathlib.Path, value: str | None) -> pathlib.Path | None:
    if not value:
        return None
    path = pathlib.Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _field_rules(context: dict) -> dict:
    rules = context.get("rules") or {}
    if not isinstance(rules, dict):
        raise ValueError("venue context rules must be an object")
    return rules


def _source_id_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if str(value or "").strip()}


def _rule_source_ids(rules: dict) -> set[str]:
    result: set[str] = set()
    for value in rules.values():
        if isinstance(value, dict):
            result.update(_source_id_set(value.get("source_ids") or []))
    return result


def _verify_source_evidence(
    *,
    envelope: Any,
    rules: dict,
    selected_at: dt.datetime | None,
    base: pathlib.Path,
    errors: list[str],
) -> dict:
    if not isinstance(envelope, dict):
        errors.append("selected handoff source_evidence must be an object")
        return {"status": "ERROR", "source_ids": []}
    if envelope.get("schema") != SOURCE_EVIDENCE_SCHEMA:
        errors.append("source_evidence schema mismatch")
    as_of = _date(envelope.get("as_of"))
    if as_of is None:
        errors.append("source_evidence as_of must be an ISO date")
    elif selected_at and selected_at.date() < as_of:
        errors.append("source_evidence as_of is after selected_at")
    source_ids = _source_id_set(envelope.get("source_ids") or [])
    used_source_ids = _rule_source_ids(rules)
    missing_from_envelope = sorted(used_source_ids - source_ids)
    if missing_from_envelope:
        errors.append(
            "source_evidence source_ids omit rule sources: "
            + ", ".join(missing_from_envelope)
        )
    source_path = resolve(base, envelope.get("path"))
    if not source_path or not source_path.is_file():
        errors.append("source_evidence path missing")
        return {
            "status": "ERROR",
            "path": str(source_path) if source_path else None,
            "as_of": envelope.get("as_of"),
            "source_ids": sorted(source_ids),
        }
    expected_hash = str(envelope.get("sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        errors.append("source_evidence sha256 missing or invalid")
    elif sha256(source_path) != expected_hash:
        errors.append("source_evidence artifact sha256 mismatch")
    try:
        artifact = read_json(source_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"source_evidence path unreadable: {exc}")
        return {
            "status": "ERROR",
            "path": str(source_path),
            "as_of": envelope.get("as_of"),
            "source_ids": sorted(source_ids),
        }
    if artifact.get("schema") != SOURCE_EVIDENCE_SCHEMA:
        errors.append("source_evidence artifact schema mismatch")
    if artifact.get("as_of") != envelope.get("as_of"):
        errors.append("source_evidence artifact as_of drift")
    source_by_id = {
        str(item.get("source_id")): item
        for item in artifact.get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    missing_from_artifact = sorted(source_ids - set(source_by_id))
    if missing_from_artifact:
        errors.append(
            "source_evidence artifact missing source_ids: "
            + ", ".join(missing_from_artifact)
        )
    for field_name, field in rules.items():
        if not isinstance(field, dict):
            continue
        status = str(field.get("status") or "UNKNOWN").upper()
        field_sources = _source_id_set(field.get("source_ids") or [])
        if status != "AVAILABLE":
            continue
        if not field_sources:
            errors.append(f"AVAILABLE venue field {field_name} has no source_ids")
        checked_at = _date(field.get("checked_at"))
        if checked_at is None:
            errors.append(f"AVAILABLE venue field {field_name} lacks ISO checked_at")
        elif selected_at and checked_at > selected_at.date():
            errors.append(f"venue field {field_name} checked_at is after selected_at")
        for source_id in sorted(field_sources):
            source = source_by_id.get(source_id)
            if not source:
                continue
            if str(source.get("status") or "UNKNOWN").upper() != "AVAILABLE":
                errors.append(
                    f"AVAILABLE venue field {field_name} cites non-available source {source_id}"
                )
            source_checked = _date(source.get("checked_at"))
            if source_checked is None:
                errors.append(f"source {source_id} lacks ISO checked_at")
            elif selected_at and source_checked > selected_at.date():
                errors.append(f"source {source_id} checked_at is after selected_at")
            if not str(source.get("authority") or "").strip():
                errors.append(f"source {source_id} lacks authority")
            if not (
                source.get("url")
                or source.get("query")
                or source.get("locator")
                or source.get("path")
            ):
                errors.append(f"source {source_id} lacks locator/url/query/path")
    return {
        "status": "PASS",
        "path": str(source_path.resolve()),
        "sha256": expected_hash,
        "as_of": envelope.get("as_of"),
        "source_ids": sorted(source_ids),
        "used_source_ids": sorted(used_source_ids),
    }


def consume_venue(handoff_path: pathlib.Path, context_path: pathlib.Path) -> dict:
    handoff = read_json(handoff_path)
    context = read_json(context_path)
    errors = []
    if handoff.get("schema") != SELECTED_SCHEMA:
        errors.append("selected handoff schema mismatch")
    if handoff.get("producer") != "venue-matching" or handoff.get("stage") != 12:
        errors.append("selected handoff producer/stage mismatch")
    status = handoff.get("status")
    if status not in {"SELECTED_BY_USER", "SELECTED_WITH_USER_AUTHORIZATION"}:
        errors.append("venue was not selected with user authority")
    selected_at = _timestamp_with_tz(handoff.get("selected_at"))
    if selected_at is None:
        errors.append("selected_at must be ISO-8601 with timezone")
    elif selected_at.astimezone(dt.timezone.utc) > (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    ):
        errors.append("selected_at cannot be in the future")
    selected_by = handoff.get("selected_by")
    if status == "SELECTED_BY_USER" and selected_by != "user":
        errors.append("SELECTED_BY_USER requires selected_by=user")
    if status == "SELECTED_WITH_USER_AUTHORIZATION":
        if selected_by != "agent":
            errors.append("delegated venue selection requires selected_by=agent")
        if not str(handoff.get("user_authorization") or "").strip():
            errors.append("delegated venue selection requires user_authorization")
    if handoff.get("decision_authority") != "user":
        errors.append("decision_authority must be user")
    selection_basis = str(handoff.get("selection_basis") or "").strip()
    if not selection_basis:
        errors.append("selection_basis must record the user trade-off")
    if context.get("schema") != VENUE_CONTEXT_SCHEMA:
        errors.append("review context schema mismatch")
    venue = handoff.get("venue") or {}
    chosen = handoff.get("chosen")
    if not chosen:
        errors.append("selected handoff chosen candidate is missing")
    if venue.get("candidate_id") != chosen:
        errors.append("selected handoff chosen candidate and venue candidate_id disagree")
    fit_risk = handoff.get("fit_risk") or {}
    if fit_risk.get("candidate_id") != chosen:
        errors.append("selected handoff fit_risk candidate_id disagrees with chosen")
    if context.get("venue") != venue.get("name"):
        errors.append("selected handoff and review context venue disagree")
    if context.get("venue_type") != venue.get("type"):
        errors.append("selected handoff and review context venue_type disagree")
    if context.get("rules") != venue.get("fields"):
        errors.append("review context changed venue rule envelopes")
    if context.get("fit_risk") != fit_risk:
        errors.append("review context changed fit/risk evaluation")
    if context.get("source_evidence") != handoff.get("source_evidence"):
        errors.append("review context changed source evidence envelope")
    if context.get("manuscript_profile") != handoff.get("manuscript_profile"):
        errors.append("review context changed manuscript profile")
    handoff_facts = ((handoff.get("typesetting") or {}).get("facts") or {})
    context_facts = context.get("typesetting_facts") or {}
    if handoff_facts != context_facts:
        errors.append("review context changed typesetting facts")
    rules = _field_rules(context)
    source_evidence = _verify_source_evidence(
        envelope=handoff.get("source_evidence"),
        rules=rules,
        selected_at=selected_at,
        base=handoff_path.parent,
        errors=errors,
    )
    pdf = resolve(handoff_path.parent, handoff_facts.get("pdf"))
    if not pdf or not pdf.is_file():
        errors.append("selected handoff PDF missing")
    elif sha256(pdf) != handoff_facts.get("pdf_sha256"):
        errors.append("selected handoff PDF hash mismatch")
    if handoff_facts.get("status") != "DELIVERED":
        errors.append("typesetting status is not DELIVERED")
    if handoff_facts.get("compliance_status") != "PASS":
        errors.append("typesetting compliance is not PASS")
    if int(handoff_facts.get("critical_count") or 0) != 0:
        errors.append("typesetting has critical findings")
    if errors:
        raise ValueError("; ".join(errors))
    unknown_rules = [
        {
            "field": key,
            "status": str(value.get("status") or "UNKNOWN").upper(),
            "reason": value.get("reason"),
            "source_ids": value.get("source_ids") or [],
        }
        for key, value in rules.items()
        if not isinstance(value, dict) or str(value.get("status") or "UNKNOWN").upper() != "AVAILABLE"
    ]
    return {
        "handoff_path": str(handoff_path.resolve()),
        "context_path": str(context_path.resolve()),
        "chosen": handoff.get("chosen"),
        "venue": context.get("venue"),
        "venue_type": context.get("venue_type"),
        "selection_status": handoff.get("status"),
        "decision_authority": handoff.get("decision_authority"),
        "selected_at": handoff.get("selected_at"),
        "selected_by": handoff.get("selected_by"),
        "selection_basis": selection_basis,
        "user_authorization": handoff.get("user_authorization"),
        "rules": rules,
        "fit_risk": context.get("fit_risk"),
        "source_evidence": context.get("source_evidence"),
        "source_evidence_verified": source_evidence,
        "manuscript_profile": context.get("manuscript_profile"),
        "typesetting_facts": context_facts,
        "unknown_rules": unknown_rules,
    }


def _claim_ids(claim_map: dict) -> set[str]:
    if claim_map.get("schema") != "light.paper_claims.v1":
        raise ValueError("paper claim map must be light.paper_claims.v1")
    return {str(item.get("claim_id")) for item in claim_map.get("claims") or [] if item.get("claim_id")}


def _evidence_ids(evidence: dict) -> set[str]:
    if evidence.get("schema") != "light.evidence_strength.v1":
        raise ValueError("evidence must be light.evidence_strength.v1")
    return {str(item.get("claim_id")) for item in evidence.get("claims") or [] if item.get("claim_id")}


def _citation_statuses(registry: dict | None) -> dict[str, str]:
    if not registry:
        return {}
    if registry.get("schema") != "light.citation_registry.v1":
        raise ValueError("citation registry must be light.citation_registry.v1")
    result = {}
    for item in registry.get("works") or []:
        work_id = item.get("work_id")
        verification = item.get("verification") or {}
        status = item.get("status") or verification.get("status")
        if work_id:
            result[str(work_id)] = str(status or "UNRESOLVED").upper()
    return result


def _clean_hash(value: Any) -> str:
    return str(value or "").removeprefix("sha256:")


def _atom_span(atom: dict, raw: str, issue_id: str, source_id: str, failures: list[dict]) -> tuple[str, dict | None]:
    legacy_span = str(atom.get("raw_span") or "")
    source_span = atom.get("source_span")
    normalized: dict | None = None
    if not isinstance(source_span, dict):
        failures.append({"code": "SOURCE_SPAN_V2_MISSING", "issue_id": issue_id,
                         "source_id": source_id})
        raw_span = legacy_span
    else:
        raw_span = str(source_span.get("text") or "")
        try:
            start = int(source_span.get("start"))
            end = int(source_span.get("end"))
        except (TypeError, ValueError):
            failures.append({"code": "SOURCE_SPAN_BOUNDS_INVALID", "issue_id": issue_id,
                             "source_id": source_id})
            start, end = -1, -1
        if start < 0 or end < start or end > len(raw):
            failures.append({"code": "SOURCE_SPAN_BOUNDS_INVALID", "issue_id": issue_id,
                             "source_id": source_id})
        elif raw[start:end] != raw_span:
            failures.append({"code": "SOURCE_SPAN_TEXT_MISMATCH", "issue_id": issue_id,
                             "source_id": source_id})
        expected_hash = source_span.get("sha256")
        if not expected_hash:
            failures.append({"code": "SOURCE_SPAN_HASH_MISSING", "issue_id": issue_id,
                             "source_id": source_id})
        elif _clean_hash(expected_hash) != sha256_text(raw_span):
            failures.append({"code": "SOURCE_SPAN_HASH_MISMATCH", "issue_id": issue_id,
                             "source_id": source_id})
        if legacy_span and legacy_span != raw_span:
            failures.append({"code": "RAW_SPAN_SOURCE_SPAN_DRIFT", "issue_id": issue_id,
                             "source_id": source_id})
        normalized = {
            "start": source_span.get("start"),
            "end": source_span.get("end"),
            "text": raw_span,
            "sha256": source_span.get("sha256"),
        }
    if not raw_span or raw_span not in raw:
        failures.append({"code": "RAW_SPAN_NOT_VERBATIM", "issue_id": issue_id,
                         "source_id": source_id})
    return raw_span, normalized


def _run_provenance(base: pathlib.Path, raw: dict | None) -> dict | None:
    if not raw:
        return None
    path = resolve(base, raw.get("path"))
    result = dict(raw)
    result["path"] = str(path) if path else None
    expected = _sha256_value(raw.get("sha256"))
    result["sha256_required"] = expected is None
    if path and path.is_file():
        result["exists"] = True
        actual = sha256(path)
        result["actual_sha256"] = actual
        result["verified"] = expected == actual
    else:
        result.update(exists=False, verified=False)
    return result


def normalize_reviews(
    spec: dict,
    base: pathlib.Path,
    claim_ids: set[str],
    evidence_ids: set[str],
    citation_status: dict[str, str],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    registry_items: list[dict] = []
    issues: list[dict] = []
    failures: list[dict] = []
    unknowns: list[dict] = []
    seen_issue_ids: set[str] = set()
    for index, review in enumerate(spec.get("reviews") or [], 1):
        source_id = str(review.get("source_id") or f"source-{index}")
        access = str(review.get("access_status") or "UNKNOWN").upper()
        if access not in ACCESS_STATES:
            access = "UNKNOWN"
        raw = str(review.get("raw_text") or "")
        if access != "AVAILABLE":
            unknowns.append({
                "kind": "review_source", "source_id": source_id, "status": access,
                "reason": review.get("access_reason") or "source not available",
            })
        if access == "AVAILABLE" and not raw:
            failures.append({"code": "AVAILABLE_WITHOUT_RAW_TEXT", "source_id": source_id})
        captured_at = _timestamp_with_tz(review.get("captured_at"))
        if access == "AVAILABLE" and captured_at is None:
            failures.append({"code": "REVIEW_CAPTURED_AT_INVALID", "source_id": source_id})
        elif captured_at and captured_at.astimezone(dt.timezone.utc) > (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        ):
            failures.append({"code": "REVIEW_CAPTURED_AT_FUTURE", "source_id": source_id})
        raw_sha256 = sha256_text(raw)
        expected_raw_hash = review.get("raw_sha256")
        if expected_raw_hash and _clean_hash(expected_raw_hash).lower() != raw_sha256:
            failures.append({"code": "REVIEW_RAW_HASH_MISMATCH", "source_id": source_id})
        registry_items.append({
            "source_id": source_id,
            "source_kind": review.get("source_kind"),
            "source_url": review.get("source_url"),
            "captured_at": review.get("captured_at"),
            "raw_sha256": raw_sha256,
            "access_status": access,
            "access_reason": review.get("access_reason"),
            "round": review.get("round"),
            "reviewer_id": review.get("reviewer_id"),
            "decision": review.get("decision"),
            "meta_review": review.get("meta_review"),
            "attachments": review.get("attachments") or [],
            "raw_text": raw,
            "boundary": "raw_text is immutable source evidence; atoms and drafts are interpretation layers",
        })
        if access != "AVAILABLE":
            continue
        for atom in review.get("atoms") or []:
            issue_id = str(atom.get("issue_id") or "")
            if not issue_id or issue_id in seen_issue_ids:
                failures.append({"code": "DUPLICATE_OR_MISSING_ISSUE_ID", "source_id": source_id,
                                 "issue_id": issue_id})
                continue
            seen_issue_ids.add(issue_id)
            raw_span, source_span = _atom_span(atom, raw, issue_id, source_id, failures)
            issue_type = str(atom.get("issue_type") or "").lower()
            if issue_type not in ISSUE_TYPES:
                failures.append({"code": "INVALID_ISSUE_TYPE", "issue_id": issue_id})
            root = str(atom.get("root_cause") or "").lower()
            if root not in ROOT_CAUSES:
                failures.append({"code": "INVALID_ROOT_CAUSE", "issue_id": issue_id})
            bound_claims = [str(value) for value in atom.get("claim_ids") or []]
            bad_claims = sorted(set(bound_claims) - claim_ids)
            bound_evidence = [str(value) for value in atom.get("evidence_claim_ids") or []]
            bad_evidence = sorted(set(bound_evidence) - evidence_ids)
            if bad_claims:
                failures.append({"code": "UNKNOWN_CLAIM_ID", "issue_id": issue_id,
                                 "values": bad_claims})
            if bad_evidence:
                failures.append({"code": "UNKNOWN_EVIDENCE_ID", "issue_id": issue_id,
                                 "values": bad_evidence})
            rejection_driving = bool(atom.get("rejection_driving"))
            rejection_evidence = atom.get("rejection_evidence") or {}
            if rejection_driving and not (
                rejection_evidence.get("kind")
                and rejection_evidence.get("value")
                and rejection_evidence.get("locator")
            ):
                failures.append({"code": "REJECTION_DRIVING_WITHOUT_EVIDENCE",
                                 "issue_id": issue_id})
            action = dict(atom.get("action") or {})
            strategy = str(action.get("strategy") or "")
            status = str(action.get("status") or "PLANNED").upper()
            if strategy not in STRATEGIES:
                failures.append({"code": "INVALID_STRATEGY", "issue_id": issue_id})
            if status not in ACTION_STATES:
                failures.append({"code": "INVALID_ACTION_STATUS", "issue_id": issue_id})
            response = str(action.get("response_text") or "")
            locator = action.get("change_locator")
            if status == "DONE" and not locator:
                failures.append({"code": "DONE_WITHOUT_CHANGE_LOCATOR", "issue_id": issue_id})
            if status in {"PLANNED", "IN_PROGRESS"} and DONE_WORDS.search(response):
                failures.append({"code": "PLANNED_AS_DONE", "issue_id": issue_id})
            if status == "DONE" and FUTURE_WORDS.search(response):
                failures.append({"code": "DONE_CONTAINS_FUTURE_CLAIM", "issue_id": issue_id})
            new_citations = [str(value) for value in action.get("new_citation_work_ids") or []]
            for work_id in new_citations:
                if citation_status.get(work_id) != "CONFIRMED":
                    failures.append({"code": "NEW_CITATION_NOT_CONFIRMED", "issue_id": issue_id,
                                     "work_id": work_id,
                                     "status": citation_status.get(work_id, "UNRESOLVED")})
            run_provenance = _run_provenance(base, action.get("run_provenance"))
            action_kind = str(action.get("action_kind") or "prose")
            if action_kind in {"experiment", "analysis"} and status == "DONE":
                if not run_provenance or not run_provenance.get("verified"):
                    failures.append({"code": "DONE_SCIENTIFIC_ACTION_WITHOUT_RUN_PROVENANCE",
                                     "issue_id": issue_id})
            action.update(
                status=status,
                strategy=strategy,
                response_text=response,
                run_provenance=run_provenance,
                new_citation_work_ids=new_citations,
            )
            issues.append({
                "issue_id": issue_id,
                "source_id": source_id,
                "reviewer_id": review.get("reviewer_id"),
                "round": review.get("round"),
                "raw_span": raw_span,
                "source_span": source_span,
                "issue_type": issue_type,
                "root_cause": root,
                "severity": str(atom.get("severity") or "minor").lower(),
                "rejection_driving": rejection_driving,
                "rejection_evidence": rejection_evidence if rejection_driving else None,
                "claim_ids": bound_claims,
                "evidence_claim_ids": bound_evidence,
                "interpretation": atom.get("interpretation"),
                "action": action,
            })
    return registry_items, issues, failures, unknowns


def _response_markdown(venue: dict, issues: list[dict]) -> str:
    lines = [
        f"# Response draft — {venue['venue']}",
        "",
        "> Reviewer wording below is copied verbatim from the canonical registry. "
        "Responses are author-supplied draft text; status and change locators remain visible.",
        "",
    ]
    for issue in issues:
        action = issue["action"]
        lines.extend([
            f"## {issue['issue_id']} · {issue['reviewer_id']} · round {issue['round']}",
            "",
            "> " + issue["raw_span"].replace("\n", "\n> "),
            "",
            f"**Strategy:** `{action['strategy']}`  ",
            f"**Action status:** `{action['status']}`  ",
            f"**Change locator:** {action.get('change_locator') or 'NONE'}",
            "",
            action.get("response_text") or "[AUTHOR_INPUT_NEEDED]",
            "",
        ])
    return "\n".join(lines)


def prepare(spec_path: pathlib.Path, output_dir: pathlib.Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = read_json(spec_path)
    if spec.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected {INPUT_SCHEMA}")
    base = spec_path.parent
    handoff_path = resolve(base, spec.get("venue_handoff"))
    context_path = resolve(base, spec.get("venue_context"))
    if not handoff_path or not context_path:
        raise ValueError("venue_handoff and venue_context are required")
    venue = consume_venue(handoff_path, context_path)
    claim_path = resolve(base, spec.get("paper_claims"))
    evidence_path = resolve(base, spec.get("evidence_strength"))
    citation_path = resolve(base, spec.get("citation_registry"))
    if not claim_path or not evidence_path:
        raise ValueError("paper_claims and evidence_strength are required")
    claims = read_json(claim_path)
    evidence = read_json(evidence_path)
    citations = read_json(citation_path) if citation_path and citation_path.is_file() else None
    claim_ids = _claim_ids(claims)
    evidence_ids = _evidence_ids(evidence)
    citation_status = _citation_statuses(citations)
    registry_items, issues, failures, unknowns = normalize_reviews(
        spec, base, claim_ids, evidence_ids, citation_status
    )
    unknowns = venue["unknown_rules"] + unknowns
    generated = now()
    registry = {
        "schema": REGISTRY_SCHEMA, "generated_at": generated,
        "project": spec.get("project"), "venue": venue["venue"],
        "items": registry_items,
        "boundary": "raw_text is immutable; classifications and drafts never overwrite it",
    }
    issue_matrix = {
        "schema": ISSUE_SCHEMA, "generated_at": generated,
        "project": spec.get("project"), "venue": venue["venue"],
        "issues": issues,
        "critical_policy": (
            "Only rejection_driving=true with a non-empty rejection_evidence envelope "
            "may become stage-13 critical."
        ),
    }
    revision_items = []
    changes = []
    commitments = []
    for issue in issues:
        action = issue["action"]
        revision_items.append({
            "revision_id": f"REV-{issue['issue_id']}",
            "issue_id": issue["issue_id"],
            "description": action.get("description"),
            "action_kind": action.get("action_kind") or "prose",
            "owner": action.get("owner"),
            "status": action["status"],
            "change_locator": action.get("change_locator"),
        })
        changes.append({
            "issue_id": issue["issue_id"],
            "claim_ids": issue["claim_ids"],
            "evidence_claim_ids": issue["evidence_claim_ids"],
            "strategy": action["strategy"],
            "status": action["status"],
            "change_locator": action.get("change_locator"),
            "artifact_path": action.get("artifact_path"),
            "run_provenance": action.get("run_provenance"),
            "new_citation_work_ids": action.get("new_citation_work_ids") or [],
        })
        commitments.append({
            "commitment_id": f"COM-{issue['issue_id']}",
            "issue_ids": [issue["issue_id"]],
            "text": action.get("description"),
            "action_kind": action.get("action_kind") or "prose",
            "owner": action.get("owner"),
            "status": action["status"],
            "change_locator": action.get("change_locator"),
            "artifact_path": action.get("artifact_path"),
            "run_provenance": action.get("run_provenance"),
            "rationale": action.get("rationale"),
            "response_text": action.get("response_text"),
        })
    plan = {"schema": PLAN_SCHEMA, "generated_at": generated, "items": revision_items}
    change_map = {
        "schema": CHANGE_SCHEMA, "generated_at": generated,
        "paper_claims": str(claim_path.resolve()),
        "evidence_strength": str(evidence_path.resolve()),
        "citation_registry": str(citation_path.resolve()) if citation_path else None,
        "items": changes,
    }
    ledger = {"schema": LEDGER_SCHEMA, "generated_at": generated, "items": commitments}
    unknown_artifact = {
        "schema": UNKNOWN_SCHEMA, "generated_at": generated, "items": unknowns,
        "counts": {
            state: sum(1 for item in unknowns if item.get("status") == state)
            for state in ("UNKNOWN", "UNAVAILABLE", "STALE")
        },
    }
    failure = {
        "schema": FAILURE_SCHEMA, "generated_at": generated,
        "status": "ERROR" if failures else "NONE", "items": failures,
    }
    artifacts = {
        "review_registry": str((output_dir / "review-registry.json").resolve()),
        "issue_matrix": str((output_dir / "issue-matrix.json").resolve()),
        "revision_plan": str((output_dir / "revision-plan.json").resolve()),
        "evidence_change_map": str((output_dir / "evidence-change-map.json").resolve()),
        "response_draft": str((output_dir / "response-draft.md").resolve()),
        "commitment_ledger": str((output_dir / "commitment-ledger.json").resolve()),
        "unknowns": str((output_dir / "unknowns.json").resolve()),
        "failure": str((output_dir / "failure.json").resolve()),
    }
    delivery = {
        "schema": DELIVERY_SCHEMA, "generated_at": generated,
        "status": "BLOCKED" if failures else "DRAFT_READY",
        "venue": venue,
        "artifacts": artifacts,
        "boundaries": {
            "venue": "consumed only; no venue change or rule invention",
            "manuscript": "paper-writing owns edits; this package records requested actions",
            "evidence": "result-analysis owns evidence strength",
            "citation": "citation owns new-reference verification",
            "typesetting": "typesetting owns PDF rebuild and compliance",
            "routing": "reviewer_classify/reroute advise; user chooses before add-back-edge",
        },
    }
    write_json(output_dir / "review-registry.json", registry)
    write_json(output_dir / "issue-matrix.json", issue_matrix)
    write_json(output_dir / "revision-plan.json", plan)
    write_json(output_dir / "evidence-change-map.json", change_map)
    (output_dir / "response-draft.md").write_text(
        _response_markdown(venue, issues) + "\n", encoding="utf-8"
    )
    write_json(output_dir / "commitment-ledger.json", ledger)
    write_json(output_dir / "unknowns.json", unknown_artifact)
    write_json(output_dir / "failure.json", failure)
    write_json(output_dir / "delivery.json", delivery)
    return delivery


def _fixture(root: pathlib.Path) -> pathlib.Path:
    pdf = root / "paper.pdf"
    pdf.write_bytes(b"%PDF-review-workflow-selftest")
    facts = {
        "status": "DELIVERED", "pdf": str(pdf), "pdf_sha256": sha256(pdf),
        "pages": 2, "page_size": "letter", "profile_name": "source-profile",
        "profile_source": {"kind": "official", "url": "https://example.test"},
        "compliance_status": "PASS", "critical_count": 0,
    }
    venue = {
        "candidate_id": "jors", "name": "Journal of Open Research Software",
        "type": "journal", "fields": {
            "page_limit": {"status": "AVAILABLE", "value": {"min_pages": 4, "max_pages": 6},
                           "source_ids": ["official"], "checked_at": "2026-07-03"},
            "rebuttal_length": {"status": "UNKNOWN", "value": None, "source_ids": [],
                                "reason": "no current authoritative rule found"},
        },
    }
    source_evidence_path = root / "source-evidence.json"
    write_json(source_evidence_path, {
        "schema": SOURCE_EVIDENCE_SCHEMA,
        "generated_at": now(),
        "as_of": "2026-07-03",
        "sources": [{
            "source_id": "official",
            "status": "AVAILABLE",
            "url": "https://example.test/author-guidelines",
            "checked_at": "2026-07-03",
            "access_tier": "free_public",
            "authority": "official",
        }],
    })
    fit_risk = {
        "candidate_id": "jors",
        "tier": "match",
        "fit_confidence": "MEDIUM",
        "because": "selftest source-backed venue choice",
        "evidence_source_ids": ["official"],
    }
    manuscript_profile = {"title": "P"}
    source_evidence = {
        "schema": SOURCE_EVIDENCE_SCHEMA,
        "path": str(source_evidence_path),
        "sha256": sha256(source_evidence_path),
        "as_of": "2026-07-03",
        "source_ids": ["official"],
    }
    write_json(root / "selected.json", {
        "schema": "light.selected_venue_handoff.v1", "producer": "venue-matching",
        "stage": 12, "status": "SELECTED_WITH_USER_AUTHORIZATION",
        "selected_at": "2026-07-03T12:00:00+08:00",
        "selected_by": "agent",
        "decision_authority": "user",
        "user_authorization": "User explicitly chose JORS for the selftest fixture.",
        "chosen": "jors", "venue": venue, "fit_risk": fit_risk,
        "selection_basis": "selftest selects the source-backed match venue",
        "typesetting": {"facts": facts},
        "manuscript_profile": manuscript_profile,
        "author_constraints": {},
        "source_evidence": source_evidence,
    })
    write_json(root / "context.json", {
        "schema": "light.review_rebuttal_venue_context.v1",
        "venue": venue["name"], "venue_type": "journal", "rules": venue["fields"],
        "fit_risk": fit_risk,
        "source_evidence": source_evidence,
        "manuscript_profile": manuscript_profile, "typesetting_facts": facts,
    })
    write_json(root / "claims.json", {
        "schema": "light.paper_claims.v1",
        "claims": [{"claim_id": "C1", "text": "The workflow improves traceability."}],
    })
    write_json(root / "evidence.json", {
        "schema": "light.evidence_strength.v1",
        "claims": [{"claim_id": "E1", "grade": "moderate"}],
    })
    write_json(root / "citations.json", {
        "schema": "light.citation_registry.v1",
        "works": [{"work_id": "W1", "status": "CONFIRMED"}],
    })
    run = root / "run.json"
    write_json(run, {"metric": 0.8})
    review_raw = (
        "The novelty is unclear. Please add an ablation. "
        "Section 3 is difficult to follow. Did I miss the runtime result?"
    )

    def span(text: str) -> dict:
        start = review_raw.index(text)
        return {
            "start": start,
            "end": start + len(text),
            "text": text,
            "sha256": sha256_text(text),
        }

    atoms = [
        {
            "issue_id": "R1-N", "raw_span": "The novelty is unclear.",
            "source_span": span("The novelty is unclear."),
            "issue_type": "claim", "root_cause": "novelty", "severity": "major",
            "rejection_driving": False, "claim_ids": ["C1"], "evidence_claim_ids": [],
            "action": {"strategy": "clarify", "status": "NOT_APPLICABLE",
                       "owner": "author", "description": "clarify existing novelty",
                       "response_text": "Section 2 already states the bounded contribution."},
        },
        {
            "issue_id": "R1-E", "raw_span": "Please add an ablation.",
            "source_span": span("Please add an ablation."),
            "issue_type": "request", "root_cause": "experiment", "severity": "major",
            "rejection_driving": True,
            "rejection_evidence": {
                "kind": "meta_review", "value": "Major revision: ablation is decision-driving",
                "locator": "meta-review:L4",
            },
            "claim_ids": ["C1"], "evidence_claim_ids": ["E1"],
            "action": {"strategy": "acknowledge_and_fix", "status": "PLANNED",
                       "action_kind": "experiment", "owner": "analyst",
                       "description": "run ablation", "response_text": "Ablation remains planned."},
        },
        {
            "issue_id": "R1-W", "raw_span": "Section 3 is difficult to follow.",
            "source_span": span("Section 3 is difficult to follow."),
            "issue_type": "claim", "root_cause": "writing", "severity": "major",
            "rejection_driving": False, "claim_ids": ["C1"], "evidence_claim_ids": ["E1"],
            "action": {"strategy": "acknowledge_and_fix", "status": "DONE",
                       "action_kind": "prose", "owner": "author",
                       "description": "rewrite Section 3", "change_locator": "paper.md#section-3",
                       "artifact_path": "paper.md",
                       "response_text": "We have revised Section 3 for clarity."},
        },
        {
            "issue_id": "R1-Q", "raw_span": "Did I miss the runtime result?",
            "source_span": span("Did I miss the runtime result?"),
            "issue_type": "misunderstanding", "root_cause": "clarification",
            "severity": "question", "rejection_driving": False,
            "claim_ids": ["C1"], "evidence_claim_ids": ["E1"],
            "action": {"strategy": "clarify", "status": "NOT_APPLICABLE",
                       "owner": "author", "description": "point to existing result",
                       "response_text": "Runtime is reported in Table 2; no manuscript change is claimed."},
        },
    ]
    write_json(root / "input.json", {
        "schema": INPUT_SCHEMA, "project": "selftest",
        "venue_handoff": "selected.json", "venue_context": "context.json",
        "paper_claims": "claims.json", "evidence_strength": "evidence.json",
        "citation_registry": "citations.json",
        "reviews": [{
            "source_id": "user-review", "source_kind": "user_supplied",
            "access_status": "AVAILABLE", "captured_at": now(), "round": 1,
            "reviewer_id": "R1", "raw_text": review_raw, "raw_sha256": sha256_text(review_raw),
            "decision": "Major Revision",
            "meta_review": "Ablation is decision-driving.", "atoms": atoms,
        }],
    })
    return root / "input.json"


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        spec = _fixture(root)
        delivery = prepare(spec, root / "out")
        assert delivery["status"] == "DRAFT_READY"
        issues = read_json(root / "out" / "issue-matrix.json")["issues"]
        assert len(issues) == 4
        assert sum(bool(item["rejection_driving"]) for item in issues) == 1
        assert issues[1]["action"]["status"] == "PLANNED"
        registry = read_json(root / "out" / "review-registry.json")
        assert registry["items"][0]["raw_sha256"] == sha256_text(
            "The novelty is unclear. Please add an ablation. "
            "Section 3 is difficult to follow. Did I miss the runtime result?"
        )
        unknowns = read_json(root / "out" / "unknowns.json")["items"]
        assert any(item.get("field") == "rebuttal_length" for item in unknowns)

        def expect_venue_error(label: str, mutate, needle: str) -> None:
            handoff = json.loads(json.dumps(read_json(root / "selected.json")))
            context = json.loads(json.dumps(read_json(root / "context.json")))
            mutate(handoff, context)
            handoff_path = root / f"{label}-selected.json"
            context_path = root / f"{label}-context.json"
            write_json(handoff_path, handoff)
            write_json(context_path, context)
            try:
                consume_venue(handoff_path, context_path)
            except ValueError as exc:
                assert needle in str(exc), str(exc)
            else:
                raise AssertionError(f"{label} should fail venue integrity checks")

        expect_venue_error(
            "missing-selection-basis",
            lambda handoff, _context: handoff.__setitem__("selection_basis", ""),
            "selection_basis",
        )
        expect_venue_error(
            "selection-timezone",
            lambda handoff, _context: handoff.__setitem__(
                "selected_at", "2026-07-03T12:00:00"
            ),
            "selected_at",
        )
        expect_venue_error(
            "selection-future",
            lambda handoff, _context: handoff.__setitem__(
                "selected_at", "2099-07-03T12:00:00+08:00"
            ),
            "future",
        )
        expect_venue_error(
            "rule-drift",
            lambda _handoff, context: context["rules"]["page_limit"]["value"].__setitem__(
                "max_pages", 8
            ),
            "rule envelopes",
        )
        expect_venue_error(
            "source-evidence-drift",
            lambda handoff, _context: handoff["source_evidence"].__setitem__(
                "source_ids", []
            ),
            "omit rule sources",
        )
        expect_venue_error(
            "source-evidence-hash",
            lambda handoff, context: (
                handoff["source_evidence"].__setitem__("sha256", "0" * 64),
                context["source_evidence"].__setitem__("sha256", "0" * 64),
            ),
            "sha256 mismatch",
        )

        bad = read_json(spec)
        bad["reviews"][0]["atoms"][1]["action"]["response_text"] = "We have added the ablation."
        write_json(root / "bad.json", bad)
        bad_delivery = prepare(root / "bad.json", root / "bad-out")
        failure_codes = {
            item["code"] for item in read_json(root / "bad-out" / "failure.json")["items"]
        }
        assert bad_delivery["status"] == "BLOCKED"
        assert "PLANNED_AS_DONE" in failure_codes

        bad_hash = read_json(spec)
        bad_hash["reviews"][0]["raw_sha256"] = "0" * 64
        write_json(root / "bad-hash.json", bad_hash)
        bad_hash_delivery = prepare(root / "bad-hash.json", root / "bad-hash-out")
        bad_hash_codes = {
            item["code"] for item in read_json(root / "bad-hash-out" / "failure.json")["items"]
        }
        assert bad_hash_delivery["status"] == "BLOCKED"
        assert "REVIEW_RAW_HASH_MISMATCH" in bad_hash_codes

        done_without_hash = read_json(spec)
        action = done_without_hash["reviews"][0]["atoms"][1]["action"]
        action.update({
            "status": "DONE",
            "change_locator": "paper.md#table-4",
            "run_provenance": {"path": "run.json"},
            "response_text": "We have added the ablation in Table 4.",
        })
        write_json(root / "done-without-hash.json", done_without_hash)
        done_without_hash_delivery = prepare(
            root / "done-without-hash.json",
            root / "done-without-hash-out",
        )
        done_without_hash_codes = {
            item["code"]
            for item in read_json(root / "done-without-hash-out" / "failure.json")["items"]
        }
        assert done_without_hash_delivery["status"] == "BLOCKED"
        assert "DONE_SCIENTIFIC_ACTION_WITHOUT_RUN_PROVENANCE" in done_without_hash_codes
    print("[selftest] PASS review_workflow: venue/PDF/atoms/raw-hash/run-hash/bindings/planned-done/delivery")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="canonical stage-13 review/revision/response workflow")
    parser.add_argument("--spec")
    parser.add_argument("--outdir")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec or not args.outdir:
        parser.error("--spec and --outdir are required")
    try:
        delivery = prepare(pathlib.Path(args.spec).resolve(), pathlib.Path(args.outdir).resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[review_workflow] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(delivery, ensure_ascii=False, indent=2))
    return 1 if delivery["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
