#!/usr/bin/env python3
"""Canonical stage-12 venue evidence, decision, and selected-handoff workflow.

Prepare mode consumes a delivered typesetting venue-handoff without rebuilding
the PDF, validates per-field evidence/status, and emits a decision packet whose
chosen field is always null. Choose mode requires a direct user choice or an
explicitly delegated selection artifact before it can emit the selected-venue
handoff.
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

INPUT_SCHEMA = "light.venue_input.v2"
REGISTRY_SCHEMA = "light.venue_candidate_registry.v2"
EVIDENCE_SCHEMA = "light.venue_source_evidence.v1"
FIT_SCHEMA = "light.venue_fit_risk.v2"
UNKNOWN_SCHEMA = "light.venue_unknowns.v1"
DECISION_SCHEMA = "light.venue_decision_packet.v2"
DELIVERY_SCHEMA = "light.venue_delivery.v2"
SELECTION_SCHEMA = "light.venue_user_selection.v1"
SELECTED_SCHEMA = "light.selected_venue_handoff.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^replace-with|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
BOUND_ARTIFACTS = {
    "candidate_registry": ("candidate-registry.json", REGISTRY_SCHEMA),
    "source_evidence": ("source-evidence.json", EVIDENCE_SCHEMA),
    "fit_risk_report": ("fit-risk-report.json", FIT_SCHEMA),
    "unknowns": ("unknowns.json", UNKNOWN_SCHEMA),
}

FIELD_STATES = {"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "STALE"}
SOURCE_STATES = {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}
VOLATILE_FIELDS = {
    "acceptance_rate", "review_time", "apc", "oa", "indexing", "quartile",
    "cfp_deadline", "submission_deadline",
}
OFFICIAL_AUTHORITIES = {
    "official", "publisher", "venue", "journal", "conference", "conference_organizer", "cfp"
}
INDEX_AUTHORITIES = {"index", "registry"}
FIELD_AUTHORITY_POLICY = {
    "scope_keywords": OFFICIAL_AUTHORITIES,
    "scope_match": OFFICIAL_AUTHORITIES,
    "article_types": OFFICIAL_AUTHORITIES,
    "article_type_fit": OFFICIAL_AUTHORITIES,
    "page_limit": OFFICIAL_AUTHORITIES,
    "apc": OFFICIAL_AUTHORITIES,
    "oa": OFFICIAL_AUTHORITIES,
    "cfp_deadline": OFFICIAL_AUTHORITIES,
    "submission_deadline": OFFICIAL_AUTHORITIES,
    "acceptance_rate": OFFICIAL_AUTHORITIES,
    "review_time": OFFICIAL_AUTHORITIES,
    "indexing": INDEX_AUTHORITIES,
    "quartile": INDEX_AUTHORITIES,
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value.strip()))


def normalize_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1]
    return text if SHA256_RE.fullmatch(text) else ""


def safe_relative_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or is_placeholder(text):
        return False
    if pathlib.Path(text).is_absolute() or WINDOWS_DRIVE_RE.match(text):
        return False
    path = text.replace("\\", "/").split("#", 1)[0]
    return ".." not in path.split("/")


def write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(base: pathlib.Path, value: str | None) -> pathlib.Path | None:
    if not value:
        return None
    path = pathlib.Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def validate_claims_delivery(base: pathlib.Path, manuscript: dict[str, Any]) -> dict[str, Any]:
    binding = manuscript.get("claims_delivery")
    if not isinstance(binding, dict):
        raise ValueError(
            "manuscript_profile.claims_delivery must bind the current paper-writing "
            "claim/profile artifact"
        )
    raw_path = str(binding.get("path") or "").strip()
    if not safe_relative_path(raw_path):
        raise ValueError("manuscript_profile.claims_delivery.path must be a safe relative path")
    expected_hash = normalize_sha256(binding.get("sha256"))
    if not expected_hash:
        raise ValueError("manuscript_profile.claims_delivery.sha256 must be a real SHA-256")
    expected_schema = str(binding.get("schema") or "").strip()
    if not expected_schema:
        raise ValueError("manuscript_profile.claims_delivery.schema is required")
    artifact_path = (base / raw_path).resolve()
    if not artifact_path.is_file():
        raise ValueError("manuscript_profile.claims_delivery.path does not exist")
    if sha256(artifact_path) != expected_hash:
        raise ValueError("manuscript_profile.claims_delivery sha256 mismatch")
    if artifact_path.suffix.lower() == ".json":
        artifact = read_json(artifact_path)
        if artifact.get("schema") != expected_schema:
            raise ValueError("manuscript_profile.claims_delivery schema mismatch")
    return {
        "path": raw_path,
        "sha256": expected_hash,
        "schema": expected_schema,
        "role": binding.get("role") or "paper-writing-claim-profile",
        "boundary": (
            "venue-matching may read paper type/claim/evidence profile, but must not "
            "rewrite claims or strengthen the manuscript to fit a venue"
        ),
    }


def read_bound_artifact(
    decision_path: pathlib.Path,
    decision: dict,
    role: str,
) -> tuple[dict, pathlib.Path, dict]:
    filename, expected_schema = BOUND_ARTIFACTS[role]
    bindings = decision.get("artifact_bindings")
    binding = bindings.get(role) if isinstance(bindings, dict) else None
    if not isinstance(binding, dict):
        raise ValueError(f"decision packet lacks artifact binding for {role}")
    raw_path = binding.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{role} binding path is missing")
    if pathlib.Path(raw_path).is_absolute():
        raise ValueError(f"{role} binding path must be relative to the decision packet")
    artifact_path = (decision_path.parent / raw_path).resolve()
    decision_dir = decision_path.parent.resolve()
    if artifact_path.parent != decision_dir or artifact_path.name != filename:
        raise ValueError(f"{role} binding must target {filename} beside the decision packet")
    legacy_path = resolve(decision_dir, decision.get(role))
    if legacy_path != artifact_path:
        raise ValueError(f"{role} legacy path disagrees with artifact binding")
    expected_hash = str(binding.get("sha256") or "").lower()
    if not SHA256_RE.fullmatch(expected_hash):
        raise ValueError(f"{role} binding sha256 is missing or invalid")
    if not artifact_path.is_file():
        raise ValueError(f"{role} bound artifact is missing")
    if sha256(artifact_path) != expected_hash:
        raise ValueError(f"{role} bound artifact sha256 mismatch")
    artifact = read_json(artifact_path)
    if binding.get("schema") != expected_schema or artifact.get("schema") != expected_schema:
        raise ValueError(f"{role} bound artifact schema mismatch")
    return artifact, artifact_path, binding


def consume_typesetting_handoff(path: pathlib.Path) -> dict:
    handoff = read_json(path)
    issues = []
    expected = {
        "schema": "light.typesetting_venue_handoff.v1",
        "producer": "typesetting",
        "consumer": "venue-matching",
        "status": "DELIVERED",
        "compliance_status": "PASS",
        "critical_count": 0,
    }
    for key, value in expected.items():
        if handoff.get(key) != value:
            issues.append(f"{key}: expected {value!r}, got {handoff.get(key)!r}")
    base = path.parent
    pdf = resolve(base, handoff.get("pdf"))
    compliance_path = resolve(base, handoff.get("compliance_report"))
    if not pdf or not pdf.is_file():
        issues.append("PDF missing")
    elif handoff.get("pdf_sha256") != sha256(pdf):
        issues.append("PDF sha256 mismatch")
    compliance = None
    if not compliance_path or not compliance_path.is_file():
        issues.append("compliance report missing")
    else:
        compliance = read_json(compliance_path)
        if compliance.get("status") != "PASS":
            issues.append(f"compliance report status={compliance.get('status')!r}, not PASS")
        if int(compliance.get("critical_count") or 0) != 0:
            issues.append("compliance report has critical findings")
        inspection = compliance.get("pdf_inspection") or {}
        if inspection.get("pages") is not None and inspection.get("pages") != handoff.get("pages"):
            issues.append("handoff pages disagree with compliance report")
        if inspection.get("page_size") is not None and inspection.get("page_size") != handoff.get("page_size"):
            issues.append("handoff page_size disagrees with compliance report")
    build_manifest_path = base / "build-manifest.json"
    build_manifest = read_json(build_manifest_path) if build_manifest_path.is_file() else None
    upstream = []
    if build_manifest:
        for item in build_manifest.get("inputs") or []:
            upstream.append({
                "role": item.get("role"),
                "producer": item.get("producer"),
                "original_path": item.get("original_path") or item.get("path"),
                "sha256": item.get("sha256"),
                "source": item.get("source"),
            })
    return {
        "schema": handoff.get("schema"),
        "path": str(path.resolve()),
        "verification_status": "PASS" if not issues else "ERROR",
        "issues": issues,
        "facts": {
            "status": handoff.get("status"),
            "pdf": str(pdf) if pdf else None,
            "pdf_sha256": handoff.get("pdf_sha256"),
            "pages": handoff.get("pages"),
            "page_size": handoff.get("page_size"),
            "profile_name": handoff.get("profile_name"),
            "profile_source": handoff.get("profile_source"),
            "compliance_status": handoff.get("compliance_status"),
            "critical_count": handoff.get("critical_count"),
            "compliance_report": str(compliance_path) if compliance_path else None,
            "boundary": handoff.get("boundary"),
        },
        "upstream_provenance": upstream,
        "boundary": (
            "venue-matching verifies identity/hash and consumes stage-11 facts; "
            "it does not compile, reformat, reinterpret UNAVAILABLE, or redo compliance."
        ),
    }


def _date(value: str | None):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


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


def _source_locator(source: dict[str, Any]) -> str:
    return str(
        source.get("url")
        or source.get("query")
        or source.get("locator")
        or source.get("path")
        or ""
    ).strip()


def normalize_source(raw: Any, as_of: dt.date) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("every source must be an object")
    source_id = raw.get("source_id")
    if not source_id:
        raise ValueError("every source needs a source_id")
    normalized = dict(raw)
    status = str(normalized.get("status") or "UNKNOWN").upper()
    if status not in SOURCE_STATES:
        raise ValueError(f"source {source_id}: invalid status {status}")
    normalized["status"] = status
    if status == "AVAILABLE":
        problems = []
        if not _source_locator(normalized):
            problems.append("locator/url/query/path")
        if _date(normalized.get("checked_at")) is None:
            problems.append("checked_at")
        if not normalized.get("access_tier"):
            problems.append("access_tier")
        if not normalized.get("authority"):
            problems.append("authority")
        if problems:
            normalized["status"] = "UNKNOWN"
            normalized["reason"] = (
                "AVAILABLE source lacks audit fields: " + ", ".join(problems)
            )
        elif _date(normalized.get("checked_at")) and _date(normalized.get("checked_at")) > as_of:
            normalized["status"] = "UNKNOWN"
            normalized["reason"] = "source checked_at is after the workflow as_of date"
    elif not normalized.get("reason"):
        normalized["reason"] = f"{status.lower()} source without supplied reason"
    return normalized


def _bad_authority_sources(name: str, source_ids: list[str], sources: dict) -> list[str]:
    allowed = FIELD_AUTHORITY_POLICY.get(name)
    if not allowed:
        return []
    bad = []
    for source_id in source_ids:
        authority = str((sources.get(source_id) or {}).get("authority") or "").strip().lower()
        if authority not in allowed:
            bad.append(f"{source_id}:{authority or 'missing'}")
    return bad


def normalize_field(name: str, raw: Any, sources: dict, as_of: dt.date,
                    unknowns: list, candidate_id: str) -> dict:
    if not isinstance(raw, dict):
        raw = {"status": "UNKNOWN", "value": None, "reason": "field envelope missing"}
    status = str(raw.get("status") or "UNKNOWN").upper()
    if status not in FIELD_STATES:
        status = "UNKNOWN"
        raw["reason"] = "invalid field status"
    value = raw.get("value")
    source_ids = list(raw.get("source_ids") or [])
    reason = raw.get("reason")
    checked_at = raw.get("checked_at")
    if status == "AVAILABLE":
        bad_sources = [
            source_id for source_id in source_ids
            if source_id not in sources or sources[source_id].get("status") != "AVAILABLE"
        ]
        bad_authorities = _bad_authority_sources(name, source_ids, sources)
        if value is None or not source_ids or bad_sources:
            status = "UNKNOWN"
            value = None
            reason = (
                "AVAILABLE requires a value and AVAILABLE source_ids"
                + (f"; bad={bad_sources}" if bad_sources else "")
            )
        elif bad_authorities:
            status = "UNKNOWN"
            value = None
            reason = (
                f"field {name} requires authoritative sources; bad_authorities={bad_authorities}"
            )
        elif name in VOLATILE_FIELDS and _date(checked_at) != as_of:
            status = "STALE"
            reason = f"volatile field must be checked on {as_of.isoformat()}"
    elif status in {"UNKNOWN", "UNAVAILABLE", "STALE"}:
        value = None
        reason = reason or f"{status.lower()} without supplied reason"
    result = {
        "status": status,
        "value": value,
        "source_ids": source_ids,
        "checked_at": checked_at,
        "reason": reason,
    }
    if status != "AVAILABLE":
        unknowns.append({
            "candidate_id": candidate_id,
            "field": name,
            "status": status,
            "reason": reason,
            "source_ids": source_ids,
        })
    return result


def _terms(value: Any) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9.+-]{1,}", str(value).casefold())
        if token not in {"and", "the", "with", "from", "for", "into", "using"}
    }


def _field(candidate: dict, name: str):
    return ((candidate.get("fields") or {}).get(name) or {})


def _available_value(candidate: dict, name: str):
    field = _field(candidate, name)
    return field.get("value") if field.get("status") == "AVAILABLE" else None


def evaluate(candidate: dict, manuscript: dict, constraints: dict, pdf_facts: dict,
             as_of: dt.date) -> dict:
    evidence = []
    warnings = []
    exclusions = []
    score_parts = []
    manuscript_terms = _terms(
        [manuscript.get("research_direction"), manuscript.get("title"),
         manuscript.get("abstract")] + list(manuscript.get("keywords") or [])
    )
    scope_terms = _terms(_available_value(candidate, "scope_keywords") or [])
    overlap = sorted(manuscript_terms & scope_terms)
    declared_scope_fit = _available_value(candidate, "scope_match")
    if declared_scope_fit:
        scope_fit = str(declared_scope_fit).upper()
        score_parts.append({
            "factor": "scope", "value": scope_fit, "weight": 30,
            "because": _field(candidate, "scope_match").get("reason")
                       or f"source-backed manual scope comparison; overlap={overlap}",
        })
        evidence.extend(_field(candidate, "scope_match").get("source_ids") or [])
    elif scope_terms:
        scope_fit = "HIGH" if len(overlap) >= 3 else ("MEDIUM" if overlap else "LOW")
        score_parts.append({"factor": "scope", "value": scope_fit, "weight": 30,
                            "because": f"official/current scope keyword overlap={overlap}"})
        evidence.extend(_field(candidate, "scope_keywords").get("source_ids") or [])
    else:
        scope_fit = "UNKNOWN"
        warnings.append("scope evidence unavailable; do not infer fit from venue prestige")
    if scope_fit == "LOW" and declared_scope_fit:
        exclusions.append("SCOPE_MISMATCH")

    article_type = str(manuscript.get("article_type") or "").casefold()
    accepted = _available_value(candidate, "article_types")
    declared_article_fit = _available_value(candidate, "article_type_fit")
    if declared_article_fit:
        article_fit = str(declared_article_fit).upper() == "PASS"
        score_parts.append({
            "factor": "article_type", "value": "PASS" if article_fit else "FAIL",
            "weight": 20,
            "because": _field(candidate, "article_type_fit").get("reason")
                       or f"source-backed comparison for paper type={article_type}",
        })
        evidence.extend(_field(candidate, "article_type_fit").get("source_ids") or [])
        if not article_fit:
            exclusions.append("ARTICLE_TYPE_MISMATCH")
    elif accepted:
        accepted_cf = [str(item).casefold() for item in accepted]
        article_fit = any(article_type in item or item in article_type for item in accepted_cf)
        score_parts.append({"factor": "article_type", "value": "PASS" if article_fit else "FAIL",
                            "weight": 20, "because": f"paper={article_type}; venue={accepted}"})
        evidence.extend(_field(candidate, "article_types").get("source_ids") or [])
        if not article_fit:
            exclusions.append("ARTICLE_TYPE_MISMATCH")
    else:
        article_fit = None
        warnings.append("accepted article types unknown")

    page_limit = _available_value(candidate, "page_limit")
    pages = pdf_facts.get("pages")
    page_min = None
    page_max = None
    if isinstance(page_limit, (int, float)):
        page_max = page_limit
    elif isinstance(page_limit, dict):
        page_min = page_limit.get("min_pages")
        page_max = page_limit.get("max_pages")
    numeric_bounds = all(
        value is None or isinstance(value, (int, float))
        for value in (page_min, page_max)
    )
    if isinstance(pages, (int, float)) and numeric_bounds and (
        page_min is not None or page_max is not None
    ):
        below_min = page_min is not None and pages < page_min
        above_max = page_max is not None and pages > page_max
        page_fit = not below_min and not above_max
        bounds = (
            f"official range={page_min}-{page_max}"
            if page_min is not None and page_max is not None
            else f"official {'min' if page_min is not None else 'max'}="
                 f"{page_min if page_min is not None else page_max}"
        )
        score_parts.append({
            "factor": "page_limit",
            "value": "PASS" if page_fit else "FAIL",
            "weight": 10,
            "because": f"real PDF pages={pages}; {bounds}",
        })
        evidence.extend(_field(candidate, "page_limit").get("source_ids") or [])
        if above_max:
            exclusions.append("PAGE_LIMIT_MISMATCH")
        elif below_min:
            warnings.append(
                f"real PDF has {pages} pages, below official minimum {page_min}; "
                "candidate remains available only if the author expands the manuscript"
            )
    else:
        page_fit = None

    method_fit = _available_value(candidate, "method_fit")
    if method_fit:
        score_parts.append({"factor": "method_data", "value": method_fit, "weight": 15,
                            "because": _field(candidate, "method_fit").get("reason")})
        evidence.extend(_field(candidate, "method_fit").get("source_ids") or [])
        if str(method_fit).upper() == "LOW":
            warnings.append("method/data scale is weak for this venue")

    apc_field = _field(candidate, "apc")
    apc = _available_value(candidate, "apc")
    budget = ((constraints.get("apc_budget") or {}).get("max_usd"))
    budget_hard = bool((constraints.get("apc_budget") or {}).get("hard"))
    apc_amount = apc
    apc_currency = "USD"
    if isinstance(apc, dict):
        apc_amount = apc.get("amount")
        apc_currency = str(apc.get("currency") or "UNKNOWN").upper()
    if apc is None:
        warnings.append("APC unavailable/unknown; this is not evidence of zero fee")
    else:
        score_parts.append({
            "factor": "apc",
            "value": apc,
            "weight": 0,
            "because": apc_field.get("reason") or "current sourced APC",
        })
        evidence.extend(apc_field.get("source_ids") or [])
        if isinstance(apc_amount, (int, float)) and isinstance(budget, (int, float)):
            if apc_currency == "USD" and apc_amount > budget:
                message = f"APC {apc_amount} USD exceeds budget {budget} USD"
                (exclusions if budget_hard else warnings).append(
                    "APC_BUDGET_MISMATCH" if budget_hard else message
                )
            elif apc_currency != "USD":
                warnings.append(
                    f"APC is {apc_amount} {apc_currency}; USD budget cannot be compared "
                    "without a current sourced exchange rate"
                )

    oa_field = _field(candidate, "oa")
    oa_value = _available_value(candidate, "oa")
    oa = str(oa_value or "").casefold()
    if oa_value is not None:
        score_parts.append({
            "factor": "oa",
            "value": oa_value,
            "weight": 0,
            "because": oa_field.get("reason") or "current sourced OA model",
        })
        evidence.extend(oa_field.get("source_ids") or [])
    elif constraints.get("oa_required"):
        warnings.append("OA model unavailable/unknown while author requires OA")
    if constraints.get("oa_required") and oa and oa not in {"full", "gold", "diamond", "yes"}:
        exclusions.append("OA_REQUIREMENT_MISMATCH")

    review_field = _field(candidate, "review_time")
    review_time = _available_value(candidate, "review_time")
    review_preference = constraints.get("review_speed")
    speed_requested = (
        isinstance(review_preference, dict) and
        review_preference.get("max_first_decision_days") is not None
    ) or (
        isinstance(review_preference, str) and
        review_preference.strip().casefold() not in {"", "no preference"}
    )
    if review_time is not None:
        score_parts.append({
            "factor": "review_time",
            "value": review_time,
            "weight": 0,
            "because": review_field.get("reason") or "current sourced review timing",
        })
        evidence.extend(review_field.get("source_ids") or [])
        if isinstance(review_preference, dict) and isinstance(review_time, dict):
            maximum = review_preference.get("max_first_decision_days")
            actual = review_time.get("first_decision_days")
            if isinstance(maximum, (int, float)) and isinstance(actual, (int, float)) and actual > maximum:
                message = f"first-decision days {actual} exceed preference {maximum}"
                if review_preference.get("hard"):
                    exclusions.append("REVIEW_TIME_MISMATCH")
                else:
                    warnings.append(message)
    elif speed_requested:
        warnings.append("review time unavailable/unknown; author speed preference cannot be verified")

    cfp_field = _field(candidate, "cfp_deadline")
    cfp_deadline = _available_value(candidate, "cfp_deadline")
    if cfp_deadline is not None:
        score_parts.append({
            "factor": "cfp_deadline",
            "value": cfp_deadline,
            "weight": 0,
            "because": cfp_field.get("reason") or "current official CFP deadline",
        })
        evidence.extend(cfp_field.get("source_ids") or [])
        deadline_date = _date(cfp_deadline)
        ready_date = _date(constraints.get("earliest_ready_date"))
        if deadline_date is None:
            warnings.append("CFP deadline value is not an ISO date; manual verification required")
        elif deadline_date < as_of:
            exclusions.append("CFP_CLOSED")
        elif ready_date and deadline_date < ready_date:
            exclusions.append("CFP_BEFORE_AUTHOR_READY")

    indexing = _available_value(candidate, "indexing")
    required_indexes = {str(item).casefold() for item in constraints.get("required_indexing") or []}
    if indexing is not None:
        score_parts.append({
            "factor": "indexing",
            "value": indexing,
            "weight": 0,
            "because": _field(candidate, "indexing").get("reason")
                       or "current authoritative index lookup",
        })
        evidence.extend(_field(candidate, "indexing").get("source_ids") or [])
    elif required_indexes:
        warnings.append("required indexing unavailable/unknown; do not infer non-indexing")
    if required_indexes and indexing:
        actual = {str(item).casefold() for item in (indexing if isinstance(indexing, list) else [indexing])}
        if not required_indexes.issubset(actual):
            exclusions.append("INDEXING_REQUIREMENT_MISMATCH")

    unacceptable = {str(item).casefold() for item in constraints.get("unacceptable") or []}
    haystack = " ".join([
        str(candidate.get("name") or ""), str(candidate.get("publisher") or "")
    ]).casefold()
    if any(item and item in haystack for item in unacceptable):
        exclusions.append("AUTHOR_UNACCEPTABLE_ITEM")

    for signal in candidate.get("risk_signals") or []:
        status = str(signal.get("status") or "WARN").upper()
        because = signal.get("because") or signal.get("code") or "risk signal"
        warnings.append(f"{status}: {because}; human multi-source verdict required")
        evidence.extend(signal.get("source_ids") or [])

    bar = str(_available_value(candidate, "selectivity") or "UNKNOWN").upper()
    strength = str(manuscript.get("paper_strength") or "UNKNOWN").upper()
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    if bar in order and strength in order:
        delta = order[bar] - order[strength]
        tier = "reach" if delta > 0 else ("safety" if delta < 0 else "match")
    else:
        tier = "match"
        warnings.append("selectivity/paper-strength relation unknown; provisional match tier")
    if exclusions:
        tier = "excluded"
    available_factors = len(score_parts)
    confidence = "HIGH" if available_factors >= 5 else ("MEDIUM" if available_factors >= 3 else "LOW")
    return {
        "candidate_id": candidate["candidate_id"],
        "name": candidate.get("name"),
        "tier": tier,
        "fit_confidence": confidence,
        "scope_fit": scope_fit,
        "article_type_fit": article_fit,
        "page_fit": page_fit,
        "score_parts": score_parts,
        "risk_warnings": warnings,
        "hard_exclusions": sorted(set(exclusions)),
        "evidence_source_ids": sorted(set(evidence)),
        "acceptance_likelihood": {
            "status": (
                "AVAILABLE" if _field(candidate, "acceptance_rate").get("status") == "AVAILABLE"
                else "UNKNOWN"
            ),
            "value": _available_value(candidate, "acceptance_rate"),
            "boundary": "No official current source means UNKNOWN; fit is not acceptance probability.",
        },
        "because": (
            f"tier={tier}; scope={scope_fit}; real_pdf_pages={pages}; "
            f"factors={available_factors}; exclusions={sorted(set(exclusions)) or 'none'}; "
            f"warnings={len(warnings)}"
        ),
    }


def prepare(spec_path: pathlib.Path, output_dir: pathlib.Path, as_of: dt.date) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = read_json(spec_path)
    if spec.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected {INPUT_SCHEMA}")
    handoff_path = resolve(spec_path.parent, spec.get("typesetting_handoff"))
    if not handoff_path or not handoff_path.is_file():
        raise ValueError("typesetting_handoff is missing")
    typesetting = consume_typesetting_handoff(handoff_path)
    if typesetting["verification_status"] != "PASS":
        raise ValueError("typesetting handoff is not a verified DELIVERED/PASS artifact: "
                         + "; ".join(typesetting["issues"]))
    sources_list = spec.get("sources") or []
    sources = {}
    for source in sources_list:
        normalized = normalize_source(source, as_of)
        source_id = normalized.get("source_id")
        if not source_id or source_id in sources:
            raise ValueError("every source needs a unique source_id")
        sources[source_id] = normalized

    unknowns = []
    candidates = []
    seen = set()
    for raw in spec.get("candidates") or []:
        candidate_id = raw.get("candidate_id")
        if not candidate_id or candidate_id in seen:
            raise ValueError("every candidate needs a unique candidate_id")
        seen.add(candidate_id)
        candidate = {
            "candidate_id": candidate_id,
            "name": raw.get("name"),
            "type": raw.get("type"),
            "publisher": raw.get("publisher"),
            "identifiers": raw.get("identifiers") or {},
            "discovery": raw.get("discovery") or {},
            "risk_signals": raw.get("risk_signals") or [],
            "fields": {},
        }
        for name, value in (raw.get("fields") or {}).items():
            candidate["fields"][name] = normalize_field(
                name, value, sources, as_of, unknowns, candidate_id
            )
        candidates.append(candidate)
    manuscript = dict(spec.get("manuscript_profile") or {})
    manuscript["claims_delivery"] = validate_claims_delivery(spec_path.parent, manuscript)
    constraints = spec.get("author_constraints") or {}
    evaluations = [
        evaluate(candidate, manuscript, constraints, typesetting["facts"], as_of)
        for candidate in candidates
    ]
    priority = {"reach": 0, "match": 1, "safety": 2, "excluded": 3}
    evaluations.sort(key=lambda row: (priority[row["tier"]], row["name"] or ""))
    tiers = {"reach": [], "match": [], "safety": [], "excluded": []}
    for row in evaluations:
        tiers[row["tier"]].append(row["candidate_id"])
    order = [
        {
            "position": index,
            "candidate_id": row["candidate_id"],
            "tier": row["tier"],
            "because": row["because"],
            "evidence_source_ids": row["evidence_source_ids"],
        }
        for index, row in enumerate(
            [row for row in evaluations if row["tier"] != "excluded"], 1
        )
    ]
    generated = now()
    evidence_artifact = {
        "schema": EVIDENCE_SCHEMA,
        "generated_at": generated,
        "as_of": as_of.isoformat(),
        "sources": list(sources.values()),
        "boundary": (
            "UNAVAILABLE/UNKNOWN/403/429/5xx/login/key/subscription is missing evidence, "
            "not non-indexing, non-DOAJ status, or venue risk."
        ),
    }
    registry = {
        "schema": REGISTRY_SCHEMA,
        "generated_at": generated,
        "project": spec.get("project"),
        "typesetting": typesetting,
        "manuscript_profile": manuscript,
        "author_constraints": constraints,
        "candidates": candidates,
    }
    fit_report = {
        "schema": FIT_SCHEMA,
        "generated_at": generated,
        "evaluations": evaluations,
        "boundary": (
            "Soft risk signals remain warnings. Predatory/hijacked status needs "
            "multi-source evidence and a human verdict; this report never auto-condemns."
        ),
    }
    unknown_artifact = {
        "schema": UNKNOWN_SCHEMA,
        "generated_at": generated,
        "items": unknowns,
        "counts": {
            status: sum(1 for item in unknowns if item["status"] == status)
            for status in ("UNKNOWN", "UNAVAILABLE", "STALE")
        },
    }
    artifact_objects = {
        "candidate_registry": registry,
        "source_evidence": evidence_artifact,
        "fit_risk_report": fit_report,
        "unknowns": unknown_artifact,
    }
    for role, artifact in artifact_objects.items():
        filename, _ = BOUND_ARTIFACTS[role]
        write_json(output_dir / filename, artifact)
    artifact_bindings = {
        role: {
            "path": filename,
            "sha256": sha256(output_dir / filename),
            "schema": expected_schema,
        }
        for role, (filename, expected_schema) in BOUND_ARTIFACTS.items()
    }
    decision = {
        "schema": DECISION_SCHEMA,
        "generated_at": generated,
        "status": "AWAITING_USER_DECISION",
        "stage": 12,
        "stage_contract": {
            "decision_point": True,
            "confirmation_checkpoint": False,
            "in_STAGE_GATES": False,
            "has_ROUTE_out_edge": False,
            "findings_severity": "none; optional legacy risk producer is warn-only",
        },
        "decision_point": True,
        "chosen": None,
        "tiers": tiers,
        "transfer_order": order,
        "question": (
            "Choose one candidate after reviewing reach/match/safety trade-offs, "
            "evidence, unknowns, and risk warnings. No selection or submission is automatic."
        ),
        "candidate_registry": artifact_bindings["candidate_registry"]["path"],
        "source_evidence": artifact_bindings["source_evidence"]["path"],
        "fit_risk_report": artifact_bindings["fit_risk_report"]["path"],
        "unknowns": artifact_bindings["unknowns"]["path"],
        "artifact_bindings": artifact_bindings,
    }
    write_json(output_dir / "decision-packet.json", decision)
    decision_sha256 = sha256(output_dir / "decision-packet.json")
    delivery = {
        "schema": DELIVERY_SCHEMA,
        "generated_at": generated,
        "status": "AWAITING_USER_DECISION",
        "decision_point": True,
        "chosen": None,
        "decision_sha256": decision_sha256,
        "artifacts": {
            "candidate_registry": artifact_bindings["candidate_registry"],
            "source_evidence": artifact_bindings["source_evidence"],
            "fit_risk_report": artifact_bindings["fit_risk_report"],
            "unknowns": artifact_bindings["unknowns"],
            "decision_packet": str((output_dir / "decision-packet.json").resolve()),
            "decision_packet_sha256": decision_sha256,
            "selected_venue_handoff": None,
        },
    }
    write_json(output_dir / "delivery.json", delivery)
    return delivery


def choose(decision_path: pathlib.Path, selection_path: pathlib.Path,
           output_dir: pathlib.Path) -> dict:
    decision = read_json(decision_path)
    selection = read_json(selection_path)
    if decision.get("schema") != DECISION_SCHEMA or decision.get("chosen") is not None:
        raise ValueError("decision packet must be unchosen light.venue_decision_packet.v2")
    actor = selection.get("actor")
    if selection.get("schema") != SELECTION_SCHEMA or actor not in {
        "user", "agent_with_user_authorization"
    }:
        raise ValueError(
            "selection must use actor=user or actor=agent_with_user_authorization"
        )
    if selection.get("decision_authority") != "user":
        raise ValueError("selection decision_authority must be user")
    if actor == "agent_with_user_authorization" and not (
        selection.get("user_authorization") and
        selection.get("decision_authority") == "user"
    ):
        raise ValueError(
            "delegated selection requires decision_authority=user and verbatim user_authorization"
        )
    decision_digest = str(selection.get("decision_sha256") or "").lower()
    if not SHA256_RE.fullmatch(decision_digest):
        raise ValueError("selection decision_sha256 must bind the reviewed decision packet")
    if decision_digest != sha256(decision_path):
        raise ValueError("selection decision_sha256 does not match the current decision packet")
    selected_at = selection.get("selected_at")
    selected_ts = _timestamp_with_tz(selected_at)
    if selected_ts is None:
        raise ValueError("selection selected_at must be ISO-8601 with timezone")
    decision_ts = _timestamp_with_tz(decision.get("generated_at"))
    if decision_ts is None:
        raise ValueError("decision packet generated_at must be ISO-8601 with timezone")
    if selected_ts < decision_ts:
        raise ValueError("selection selected_at cannot predate the decision packet")
    because = str(selection.get("because") or "").strip()
    if not because:
        raise ValueError("selection because must record the user's stated trade-off")
    candidate_id = selection.get("candidate_id")
    selectable_ids = {
        candidate_id_
        for tier, values in (decision.get("tiers") or {}).items()
        if tier != "excluded"
        for candidate_id_ in values
    }
    if candidate_id not in selectable_ids:
        raise ValueError("selected candidate_id is not a selectable candidate in the decision packet")
    registry, registry_path, registry_binding = read_bound_artifact(
        decision_path, decision, "candidate_registry"
    )
    evidence, evidence_path, evidence_binding = read_bound_artifact(
        decision_path, decision, "source_evidence"
    )
    fit, fit_path, fit_binding = read_bound_artifact(
        decision_path, decision, "fit_risk_report"
    )
    read_bound_artifact(decision_path, decision, "unknowns")
    candidate = next(item for item in registry["candidates"] if item["candidate_id"] == candidate_id)
    evaluation = next(item for item in fit["evaluations"] if item["candidate_id"] == candidate_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    delegated = actor == "agent_with_user_authorization"
    handoff = {
        "schema": SELECTED_SCHEMA,
        "producer": "venue-matching",
        "stage": 12,
        "status": "SELECTED_WITH_USER_AUTHORIZATION" if delegated else "SELECTED_BY_USER",
        "selected_at": selected_at,
        "selected_by": "agent" if delegated else "user",
        "decision_authority": "user",
        "decision_binding": {
            "path": str(decision_path.resolve()),
            "sha256": decision_digest,
            "schema": DECISION_SCHEMA,
        },
        "user_authorization": selection.get("user_authorization") if delegated else None,
        "chosen": candidate_id,
        "venue": candidate,
        "fit_risk": evaluation,
        "selection_basis": because,
        "typesetting": registry["typesetting"],
        "manuscript_profile": registry["manuscript_profile"],
        "author_constraints": registry["author_constraints"],
        "source_evidence": {
            "schema": evidence.get("schema"),
            "path": str(evidence_path),
            "sha256": evidence_binding["sha256"],
            "as_of": evidence.get("as_of"),
            "source_ids": sorted({
                source_id
                for field in (candidate.get("fields") or {}).values()
                for source_id in field.get("source_ids") or []
            }),
        },
        "artifact_bindings": {
            "candidate_registry": {
                **registry_binding,
                "path": str(registry_path),
            },
            "fit_risk_report": {
                **fit_binding,
                "path": str(fit_path),
            },
        },
        "consumers": {
            "review-rebuttal": [
                "venue.name", "venue.fields", "fit_risk", "source_evidence",
                "manuscript_profile", "typesetting.facts",
            ],
            "author_submission_plan": [
                "venue.fields", "author_constraints", "source_evidence", "typesetting.facts",
            ],
        },
        "boundary": (
            "Selection records a direct user choice or an agent choice made under explicit "
            "user authorization; it does not submit the manuscript."
        ),
    }
    unknown_rules = [
        name for name, field in (candidate.get("fields") or {}).items()
        if field.get("status") != "AVAILABLE"
    ]
    plan = {
        "schema": "light.author_submission_plan.v1",
        "generated_at": now(),
        "chosen": candidate_id,
        "venue_name": candidate.get("name"),
        "pdf": registry["typesetting"]["facts"],
        "verified_rules": {
            name: field for name, field in (candidate.get("fields") or {}).items()
            if field.get("status") == "AVAILABLE"
        },
        "must_recheck": unknown_rules,
        "steps": [
            "Recheck volatile venue fields against their authoritative source on submission day.",
            "Resolve every UNKNOWN/UNAVAILABLE rule before portal upload.",
            "Use the delivered PDF unchanged unless the selected venue requires a new stage-11 profile/build.",
            "Prepare cover letter, declarations, supplemental files, and portal metadata.",
            "Stop before submission; the author performs the irreversible submit action.",
        ],
        "provenance": handoff["source_evidence"],
    }
    review_context = {
        "schema": "light.review_rebuttal_venue_context.v1",
        "venue": candidate.get("name"),
        "venue_type": candidate.get("type"),
        "rules": candidate.get("fields"),
        "fit_risk": evaluation,
        "source_evidence": handoff["source_evidence"],
        "manuscript_profile": registry["manuscript_profile"],
        "typesetting_facts": registry["typesetting"]["facts"],
    }
    write_json(output_dir / "selected-venue-handoff.json", handoff)
    write_json(output_dir / "author-submission-plan.json", plan)
    write_json(output_dir / "review-rebuttal-context.json", review_context)
    return handoff


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        build = root / "build"
        build.mkdir()
        pdf = build / "paper.pdf"
        pdf.write_bytes(b"%PDF-selftest")
        compliance = {
            "schema": "light.typesetting_compliance.v1",
            "status": "PASS",
            "critical_count": 0,
            "pdf_inspection": {"pages": 2, "page_size": "letter"},
        }
        write_json(build / "compliance-report.json", compliance)
        write_json(build / "build-manifest.json", {
            "inputs": [
                {"role": "manuscript", "producer": "paper-writing", "sha256": "paper"},
                {"role": "citation", "producer": "citation", "sha256": "citation"},
                {"role": "figure", "producer": "figure", "sha256": "figure"},
            ]
        })
        write_json(build / "venue-handoff.json", {
            "schema": "light.typesetting_venue_handoff.v1",
            "producer": "typesetting", "consumer": "venue-matching", "stage": 11,
            "status": "DELIVERED", "pdf": str(pdf), "pdf_sha256": sha256(pdf),
            "pages": 2, "page_size": "letter", "profile_name": "selftest",
            "profile_source": {"kind": "user_input", "checked_at": "2026-07-03"},
            "compliance_report": str(build / "compliance-report.json"),
            "compliance_status": "PASS", "critical_count": 0, "boundary": "test",
        })
        write_json(root / "claims.json", {
            "schema": "light.paper_claims.v1",
            "claims": [{
                "claim_id": "C1",
                "text": "The paper studies reproducible machine learning software.",
                "claim_type": "POSITIONING",
            }],
        })
        checked = "2026-07-03"
        sources = [
            {"source_id": "official", "kind": "official_guidelines", "url": "https://example.test",
             "checked_at": checked, "access_tier": "free_public", "authority": "official",
             "status": "AVAILABLE"},
            {"source_id": "limited", "kind": "index", "url": "https://example.test/limited",
             "checked_at": checked, "access_tier": "institution_restricted",
             "authority": "index", "status": "UNAVAILABLE", "reason": "login required"},
            {"source_id": "blog", "kind": "web_page", "url": "https://blog.example.test",
             "checked_at": checked, "access_tier": "free_public", "authority": "blog",
             "status": "AVAILABLE"},
            {"source_id": "nolocator", "kind": "official_guidelines",
             "checked_at": checked, "access_tier": "free_public", "authority": "official",
             "status": "AVAILABLE"},
        ]
        def available(value, reason=None):
            return {
                "status": "AVAILABLE",
                "value": value,
                "source_ids": ["official"],
                "checked_at": checked,
                "reason": reason,
            }
        candidates = [
            {"candidate_id": "warn-ok", "name": "Warning Journal", "type": "journal",
             "fields": {
                 "scope_keywords": available(["machine learning", "reproducibility", "software"]),
                 "article_types": available(["research article"]),
                 "page_limit": available({"min_pages": 3, "max_pages": 4}),
                 "method_fit": available("HIGH", "method is explicitly in scope"),
                 "selectivity": available("MEDIUM"),
                 "apc": {"status": "UNAVAILABLE", "value": None, "source_ids": ["limited"],
                         "checked_at": checked, "reason": "login required"},
                 "acceptance_rate": {"status": "UNKNOWN", "value": None, "source_ids": [],
                                     "checked_at": checked, "reason": "no official public figure"},
             },
             "risk_signals": [{"code": "SOLICITATION", "status": "WARN",
                               "because": "unsolicited email only", "source_ids": ["official"]}]},
            {"candidate_id": "wrong-type", "name": "Review Only", "type": "journal",
             "fields": {
                 "scope_keywords": available(["machine learning"]),
                 "article_types": available(["review"]),
                 "cfp_deadline": available("2026-06-01"),
                 "selectivity": available("LOW"),
             }},
            {"candidate_id": "bad-authority", "name": "Blog Sourced", "type": "journal",
             "fields": {
                 "article_types": {
                     "status": "AVAILABLE", "value": ["research article"],
                     "source_ids": ["blog"], "checked_at": checked,
                     "reason": "blog says it accepts research articles",
                 },
                 "scope_keywords": available(["machine learning", "software"]),
             }},
            {"candidate_id": "bad-source", "name": "No Locator Source", "type": "journal",
             "fields": {
                 "scope_keywords": {
                     "status": "AVAILABLE", "value": ["machine learning"],
                     "source_ids": ["nolocator"], "checked_at": checked,
                     "reason": "source lacks a URL or locator",
                 },
             }},
        ]
        spec = {
            "schema": INPUT_SCHEMA, "project": "selftest",
            "typesetting_handoff": str(build / "venue-handoff.json"),
            "manuscript_profile": {
                "title": "Reproducible machine learning software",
                "research_direction": "machine learning reproducibility",
                "keywords": ["software"], "article_type": "research article",
                "paper_strength": "MEDIUM",
                "claims_delivery": {
                    "path": "claims.json",
                    "sha256": sha256(root / "claims.json"),
                    "schema": "light.paper_claims.v1",
                },
            },
            "author_constraints": {
                "apc_budget": {"max_usd": 1000, "hard": True},
                "review_speed": {"max_first_decision_days": 60, "hard": False},
                "required_indexing": [], "unacceptable": [],
            },
            "sources": sources, "candidates": candidates,
        }
        write_json(root / "input.json", spec)
        missing_claims = json.loads(json.dumps(spec))
        missing_claims["manuscript_profile"]["claims_delivery"] = None
        write_json(root / "input-missing-claims.json", missing_claims)
        try:
            prepare(root / "input-missing-claims.json", root / "missing-claims",
                    dt.date(2026, 7, 3))
            raise AssertionError("missing paper-writing claims delivery must fail")
        except ValueError as exc:
            assert "claims_delivery" in str(exc)
        bad_claims_hash = json.loads(json.dumps(spec))
        bad_claims_hash["manuscript_profile"]["claims_delivery"]["sha256"] = "0" * 64
        write_json(root / "input-bad-claims-hash.json", bad_claims_hash)
        try:
            prepare(root / "input-bad-claims-hash.json", root / "bad-claims-hash",
                    dt.date(2026, 7, 3))
            raise AssertionError("tampered claims delivery hash must fail")
        except ValueError as exc:
            assert "claims_delivery" in str(exc) and "sha256" in str(exc)
        delivery = prepare(root / "input.json", root / "prepared", dt.date(2026, 7, 3))
        assert delivery["status"] == "AWAITING_USER_DECISION"
        assert delivery["chosen"] is None and delivery["decision_point"] is True
        decision = read_json(root / "prepared" / "decision-packet.json")
        decision_ts = decision["generated_at"]
        assert decision["chosen"] is None
        registry = read_json(root / "prepared" / "candidate-registry.json")
        assert registry["manuscript_profile"]["claims_delivery"]["sha256"] == sha256(root / "claims.json")
        fit = read_json(root / "prepared" / "fit-risk-report.json")["evaluations"]
        warn = next(item for item in fit if item["candidate_id"] == "warn-ok")
        wrong = next(item for item in fit if item["candidate_id"] == "wrong-type")
        assert warn["tier"] != "excluded" and warn["risk_warnings"]
        assert warn["page_fit"] is False
        assert any("below official minimum 3" in item for item in warn["risk_warnings"])
        assert any("review time unavailable/unknown" in item for item in warn["risk_warnings"])
        assert warn["acceptance_likelihood"]["status"] == "UNKNOWN"
        assert wrong["tier"] == "excluded" and "ARTICLE_TYPE_MISMATCH" in wrong["hard_exclusions"]
        assert "CFP_CLOSED" in wrong["hard_exclusions"]
        unknowns = read_json(root / "prepared" / "unknowns.json")["items"]
        assert any(item["field"] == "apc" and item["status"] == "UNAVAILABLE" for item in unknowns)
        assert not any(item["field"] == "apc" and "risk" in item["reason"].casefold() for item in unknowns)
        assert any(
            item["candidate_id"] == "bad-authority"
            and item["field"] == "article_types"
            and "bad_authorities" in item["reason"]
            for item in unknowns
        )
        assert any(
            item["candidate_id"] == "bad-source"
            and item["field"] == "scope_keywords"
            and "bad=['nolocator']" in item["reason"]
            for item in unknowns
        )
        bad_selection = {
            "schema": SELECTION_SCHEMA, "actor": "agent", "candidate_id": "warn-ok"
        }
        write_json(root / "bad-selection.json", bad_selection)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "bad-selection.json", root / "selected")
            raise AssertionError("agent selection must fail")
        except ValueError as exc:
            assert "actor=user" in str(exc)
        bad_delegation = {
            "schema": SELECTION_SCHEMA, "actor": "agent_with_user_authorization",
            "decision_authority": "user", "candidate_id": "warn-ok",
            "selected_at": decision_ts, "because": "delegated test",
        }
        write_json(root / "bad-delegation.json", bad_delegation)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "bad-delegation.json", root / "bad-delegated")
            raise AssertionError("delegated selection without user authorization must fail")
        except ValueError as exc:
            assert "user_authorization" in str(exc)
        unbound_selection = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "warn-ok", "selected_at": decision_ts,
            "because": "selection without reviewed packet digest",
        }
        write_json(root / "unbound-selection.json", unbound_selection)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "unbound-selection.json", root / "unbound")
            raise AssertionError("selection without decision digest must fail")
        except ValueError as exc:
            assert "decision_sha256" in str(exc)
        excluded_selection = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "wrong-type", "selected_at": decision_ts,
            "because": "try excluded candidate",
            "decision_sha256": delivery["decision_sha256"],
        }
        write_json(root / "excluded-selection.json", excluded_selection)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "excluded-selection.json", root / "excluded")
            raise AssertionError("excluded candidate must not be selectable")
        except ValueError as exc:
            assert "selectable candidate" in str(exc)
        bad_time = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "warn-ok", "selected_at": "2026-07-03T12:00:00",
            "because": "missing timezone",
            "decision_sha256": delivery["decision_sha256"],
        }
        write_json(root / "bad-time-selection.json", bad_time)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "bad-time-selection.json", root / "bad-time")
            raise AssertionError("selection without timezone must fail")
        except ValueError as exc:
            assert "timezone" in str(exc)
        past_selection = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "warn-ok",
            "selected_at": (
                dt.datetime.fromisoformat(decision_ts) - dt.timedelta(seconds=1)
            ).isoformat(),
            "because": "backdated selection",
            "decision_sha256": delivery["decision_sha256"],
        }
        write_json(root / "past-selection.json", past_selection)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "past-selection.json", root / "past")
            raise AssertionError("selection before decision packet must fail")
        except ValueError as exc:
            assert "predate" in str(exc)
        bad_because = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "warn-ok", "selected_at": decision_ts,
            "because": "",
            "decision_sha256": delivery["decision_sha256"],
        }
        write_json(root / "bad-because-selection.json", bad_because)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "bad-because-selection.json", root / "bad-because")
            raise AssertionError("selection without because must fail")
        except ValueError as exc:
            assert "trade-off" in str(exc)
        good_selection = {
            "schema": SELECTION_SCHEMA, "actor": "user", "decision_authority": "user",
            "candidate_id": "warn-ok",
            "selected_at": decision_ts, "because": "selftest explicit choice",
            "decision_sha256": delivery["decision_sha256"],
        }
        write_json(root / "selection.json", good_selection)
        registry_path = root / "prepared" / "candidate-registry.json"
        original_registry = registry_path.read_bytes()
        tampered_registry = read_json(registry_path)
        tampered_registry["candidates"][0]["name"] = "Tampered Venue"
        write_json(registry_path, tampered_registry)
        try:
            choose(root / "prepared" / "decision-packet.json",
                   root / "selection.json", root / "tampered-artifact")
            raise AssertionError("tampered decision artifact must fail")
        except ValueError as exc:
            assert "sha256 mismatch" in str(exc)
        registry_path.write_bytes(original_registry)
        decision_path = root / "prepared" / "decision-packet.json"
        original_decision = decision_path.read_bytes()
        decision_path.write_bytes(original_decision + b" ")
        try:
            choose(decision_path, root / "selection.json", root / "tampered-decision")
            raise AssertionError("tampered decision packet must fail")
        except ValueError as exc:
            assert "decision_sha256" in str(exc)
        decision_path.write_bytes(original_decision)
        selected = choose(root / "prepared" / "decision-packet.json",
                          root / "selection.json", root / "selected")
        assert selected["chosen"] == "warn-ok" and selected["selected_by"] == "user"
        assert (root / "selected" / "author-submission-plan.json").is_file()
        assert (root / "selected" / "review-rebuttal-context.json").is_file()
    print("[selftest] PASS venue_workflow: handoff/hash/provenance/status/"
          "decision+artifact binding/user choice")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical venue-matching stage-12 workflow")
    sub = parser.add_subparsers(dest="command")
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--input", required=True)
    prepare_parser.add_argument("--out-dir", required=True)
    prepare_parser.add_argument("--as-of", default=dt.date.today().isoformat())
    choose_parser = sub.add_parser("choose")
    choose_parser.add_argument("--decision", required=True)
    choose_parser.add_argument("--selection", required=True)
    choose_parser.add_argument("--out-dir", required=True)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    try:
        if args.command == "prepare":
            result = prepare(pathlib.Path(args.input).resolve(),
                             pathlib.Path(args.out_dir).resolve(),
                             dt.date.fromisoformat(args.as_of))
        elif args.command == "choose":
            result = choose(pathlib.Path(args.decision).resolve(),
                            pathlib.Path(args.selection).resolve(),
                            pathlib.Path(args.out_dir).resolve())
        else:
            parser.error("choose a command or use --selftest")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[venue_workflow] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
