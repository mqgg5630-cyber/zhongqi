#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate an evidence-backed patent disclosure packet.

This is a truthfulness gate, not patentability analysis and not legal advice.
It checks whether a handoff packet is grounded in source artifacts, avoids
AI-generated patent drawings, preserves prior-art uncertainty, and refuses
"ready to file / guaranteed grant" overclaims.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.patent_disclosure.packet.v1"
REPORT_SCHEMA = "light.patent_disclosure.gate_report.v1"
SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(
    r"(<[^>]+>|\bTBD\b|\bTODO\b|\bUNKNOWN_IF_NEEDED\b|待填|待补|示例|example)",
    re.I,
)
GUARANTEE_RE = re.compile(
    r"(保证授权|必定授权|包授权|授权率|包过|稳过|可直接提交|ready\s*to\s*file|"
    r"filing[- ]ready|guaranteed\s+grant|guarantee[sd]?\s+allowance)",
    re.I,
)
AI_DRAWING_RE = re.compile(
    r"(ai[-_ ]?generated|midjourney|dall[- ]?e|stable\s+diffusion|"
    r"imagegen|nano\s+banana|生成式图片|AI\s*生图)",
    re.I,
)
ALLOWED_DIAGRAM_GENERATORS = {
    "mermaid",
    "graphviz",
    "plantuml",
    "svg",
    "manual_vector",
    "programmatic",
    "none",
}
REQUIRED_INVENTION_FIELDS = (
    "title",
    "technical_field",
    "technical_problem",
    "technical_solution",
    "technical_effect",
)
REQUIRED_SECTIONS = (
    "title",
    "technical_field",
    "background",
    "problem",
    "solution_summary",
    "technical_effects",
    "embodiments",
    "claim_support_map",
    "attorney_handoff",
)
STATUS_ALLOWED = {"VERIFIED", "PLANNED", "UNKNOWN", "UNAVAILABLE"}
RISK_TRIAGE_KEYS = (
    "public_disclosure",
    "ownership_inventorship",
    "foreign_filing_or_secrecy",
    "trade_secret_redaction",
)
QC_REVIEW_KEYS = (
    "support_map_complete",
    "terms_consistent",
    "figures_auditable",
    "overclaim_removed",
    "counsel_questions_listed",
)


def repo_root(start: str | pathlib.Path | None = None) -> pathlib.Path:
    cur = pathlib.Path(start or __file__).resolve()
    if cur.is_file():
        cur = cur.parent
    while cur != cur.parent and not (cur / "skills").is_dir():
        cur = cur.parent
    if not (cur / "skills").is_dir():
        raise RuntimeError("Light-Skills repository root not found")
    return cur


def issue(code: str, path: str, message: str, severity: str = "ERROR") -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(all_strings(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(all_strings(item))
        return out
    return []


def scalar_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.search(value)


def path_problem(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return "path must be a non-empty string"
    value = raw.strip()
    win = pathlib.PureWindowsPath(value)
    posix = pathlib.PurePosixPath(value)
    if win.is_absolute() or posix.is_absolute() or win.drive:
        return "path must be repository/project relative, not absolute"
    if value.startswith("~") or "\x00" in value:
        return "path contains unsafe prefix or null byte"
    if ".." in win.parts or ".." in posix.parts:
        return "path must not escape with '..'"
    if PLACEHOLDER_RE.search(value):
        return "path contains placeholder text"
    return None


def parse_date(value: Any, path: str, as_of: dt.date, problems: list[dict[str, str]]) -> dt.date | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(issue("DATE_MISSING", path, "date must be YYYY-MM-DD"))
        return None
    try:
        parsed = dt.date.fromisoformat(value[:10])
    except ValueError:
        problems.append(issue("DATE_INVALID", path, "date must be YYYY-MM-DD"))
        return None
    if parsed > as_of:
        problems.append(issue("DATE_IN_FUTURE", path, f"date {parsed.isoformat()} is after as_of"))
    return parsed


def validate_artifacts(packet: dict[str, Any], base: pathlib.Path | None) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    problems: list[dict[str, str]] = []
    artifacts = packet.get("source_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return {}, [issue("SOURCE_ARTIFACTS_MISSING", "source_artifacts", "at least one real source artifact is required")]

    by_id: dict[str, dict[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        path = f"source_artifacts[{index}]"
        if not isinstance(artifact, dict):
            problems.append(issue("ARTIFACT_INVALID", path, "artifact must be an object"))
            continue
        artifact_id = artifact.get("id")
        if not scalar_ok(artifact_id):
            problems.append(issue("ARTIFACT_ID_MISSING", f"{path}.id", "artifact id is required"))
        elif artifact_id in by_id:
            problems.append(issue("ARTIFACT_ID_DUPLICATE", f"{path}.id", "artifact ids must be unique"))
        else:
            by_id[str(artifact_id)] = artifact

        locator = artifact.get("path")
        if problem := path_problem(locator):
            problems.append(issue("ARTIFACT_PATH_INVALID", f"{path}.path", problem))
            continue

        sha = artifact.get("sha256")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            problems.append(issue("ARTIFACT_HASH_INVALID", f"{path}.sha256", "sha256:<64 lowercase hex> required"))
        if base is not None and isinstance(locator, str):
            resolved = (base / locator).resolve()
            try:
                resolved.relative_to(base.resolve())
            except ValueError:
                problems.append(issue("ARTIFACT_PATH_ESCAPE", f"{path}.path", "resolved path escapes base"))
                continue
            if not resolved.is_file():
                problems.append(issue("ARTIFACT_MISSING", f"{path}.path", "source artifact file does not exist"))
            elif isinstance(sha, str) and SHA_RE.match(sha) and file_sha256(resolved) != sha:
                problems.append(issue("ARTIFACT_HASH_MISMATCH", f"{path}.sha256", "sha256 does not match source artifact"))
    return by_id, problems


def has_artifact_support(value: Any, artifact_ids: set[str]) -> bool:
    refs = value.get("support_artifact_ids") if isinstance(value, dict) else None
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not refs:
        return False
    return all(isinstance(ref, str) and ref in artifact_ids for ref in refs)


def validate_status_record(value: Any, path: str, problems: list[dict[str, str]]) -> str:
    if not isinstance(value, dict):
        problems.append(issue("STATUS_RECORD_MISSING", path, "status record object required"))
        return ""
    status = str(value.get("status", "")).upper()
    if status not in STATUS_ALLOWED:
        problems.append(issue("STATUS_INVALID", f"{path}.status", "use VERIFIED, PLANNED, UNKNOWN or UNAVAILABLE"))
    if not scalar_ok(value.get("summary")):
        problems.append(issue("STATUS_SUMMARY_MISSING", f"{path}.summary", "non-placeholder summary required"))
    return status


def validate_risk_triage(packet: dict[str, Any], as_of: dt.date) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    triage = packet.get("risk_triage")
    if not isinstance(triage, dict):
        return [issue("RISK_TRIAGE_MISSING", "risk_triage", "public disclosure, ownership, secrecy and redaction triage are required")]
    for key in RISK_TRIAGE_KEYS:
        path = f"risk_triage.{key}"
        item = triage.get(key)
        status = validate_status_record(item, path, problems)
        if isinstance(item, dict):
            if item.get("date"):
                parse_date(item.get("date"), f"{path}.date", as_of, problems)
            if status in {"PLANNED", "UNKNOWN"} and not scalar_ok(item.get("next_check")):
                problems.append(issue("RISK_NEXT_CHECK_MISSING", f"{path}.next_check", "planned/unknown risk facts require a next check"))
    return problems


def validate_inventor_known_prior_art(packet: dict[str, Any]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    known = packet.get("inventor_known_prior_art")
    if not isinstance(known, dict):
        return [issue("KNOWN_PRIOR_ART_MISSING", "inventor_known_prior_art", "separate inventor-known prior art from public search results")]
    status = validate_status_record(known, "inventor_known_prior_art", problems)
    items = known.get("items")
    if status == "VERIFIED":
        if not isinstance(items, list):
            problems.append(issue("KNOWN_PRIOR_ART_ITEMS_INVALID", "inventor_known_prior_art.items", "items list required when verified; use [] if none known"))
        else:
            for index, item in enumerate(items):
                path = f"inventor_known_prior_art.items[{index}]"
                if not isinstance(item, dict):
                    problems.append(issue("KNOWN_PRIOR_ART_ITEM_INVALID", path, "item must be an object"))
                    continue
                for field in ("title", "source_or_person", "relationship"):
                    if not scalar_ok(item.get(field)):
                        problems.append(issue("KNOWN_PRIOR_ART_FIELD_MISSING", f"{path}.{field}", "non-placeholder text required"))
    elif not scalar_ok(known.get("next_check")):
        problems.append(issue("KNOWN_PRIOR_ART_NEXT_CHECK_MISSING", "inventor_known_prior_art.next_check", "non-verified inventor-known prior art requires next check"))
    return problems


def validate_prior_art(packet: dict[str, Any], as_of: dt.date) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    prior_art = packet.get("prior_art")
    if not isinstance(prior_art, dict):
        return [issue("PRIOR_ART_MISSING", "prior_art", "prior-art status must be explicit")]
    status = str(prior_art.get("search_status", "")).upper()
    if status not in STATUS_ALLOWED:
        problems.append(issue("PRIOR_ART_STATUS_INVALID", "prior_art.search_status", "use VERIFIED, PLANNED, UNKNOWN or UNAVAILABLE"))
    if status == "VERIFIED":
        parse_date(prior_art.get("checked_at"), "prior_art.checked_at", as_of, problems)
        queries = prior_art.get("queries")
        results = prior_art.get("nearest_results")
        searched_sources = prior_art.get("searched_sources")
        if not isinstance(queries, list) or not queries:
            problems.append(issue("PRIOR_ART_QUERIES_MISSING", "prior_art.queries", "verified search requires recorded queries"))
        if not isinstance(searched_sources, list) or not searched_sources:
            problems.append(issue("PRIOR_ART_SOURCES_MISSING", "prior_art.searched_sources", "verified search requires source/query coverage records"))
        else:
            source_types: set[str] = set()
            for index, source in enumerate(searched_sources):
                path = f"prior_art.searched_sources[{index}]"
                if not isinstance(source, dict):
                    problems.append(issue("PRIOR_ART_SOURCE_INVALID", path, "source record must be an object"))
                    continue
                source_type = str(source.get("source_type", "")).strip().lower()
                source_types.add(source_type)
                for field in ("source_name", "source_type", "query"):
                    if not scalar_ok(source.get(field)):
                        problems.append(issue("PRIOR_ART_SOURCE_FIELD_MISSING", f"{path}.{field}", "non-placeholder text required"))
                if "checked_at" in source:
                    parse_date(source.get("checked_at"), f"{path}.checked_at", as_of, problems)
                if "result_count" in source and not isinstance(source.get("result_count"), int):
                    problems.append(issue("PRIOR_ART_SOURCE_COUNT_INVALID", f"{path}.result_count", "result_count must be an integer when present"))
            if "patent_database" not in source_types:
                problems.append(issue("PRIOR_ART_PATENT_SOURCE_MISSING", "prior_art.searched_sources", "include at least one patent_database search or lower search_status"))
            if "non_patent_literature" not in source_types and not scalar_ok(prior_art.get("npl_not_searched_reason")):
                problems.append(issue("PRIOR_ART_NPL_REASON_MISSING", "prior_art.npl_not_searched_reason", "record why non-patent literature was not searched"))
        if not isinstance(results, list) or not results:
            problems.append(issue("PRIOR_ART_RESULTS_MISSING", "prior_art.nearest_results", "verified search requires recorded nearest results"))
        else:
            for index, result in enumerate(results):
                path = f"prior_art.nearest_results[{index}]"
                if not isinstance(result, dict):
                    problems.append(issue("PRIOR_ART_RESULT_INVALID", path, "result must be an object"))
                    continue
                for field in ("title", "locator", "relationship"):
                    if not scalar_ok(result.get(field)):
                        problems.append(issue("PRIOR_ART_RESULT_FIELD_MISSING", f"{path}.{field}", "non-placeholder text required"))
    elif not scalar_ok(prior_art.get("reason")):
        problems.append(issue("PRIOR_ART_REASON_MISSING", "prior_art.reason", "non-verified search requires a reason and next step"))
    return problems


def validate_claim_strategy(packet: dict[str, Any], artifact_ids: set[str]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    strategy = packet.get("claim_strategy")
    if not isinstance(strategy, dict):
        return [issue("CLAIM_STRATEGY_MISSING", "claim_strategy", "claim ladder and enablement support summary are required")]
    for field in ("broadest_defensible_point", "enablement_support_summary"):
        if not scalar_ok(strategy.get(field)):
            problems.append(issue("CLAIM_STRATEGY_FIELD_MISSING", f"claim_strategy.{field}", "non-placeholder text required"))
    if not has_artifact_support(strategy, artifact_ids):
        problems.append(issue("CLAIM_STRATEGY_SUPPORT_MISSING", "claim_strategy.support_artifact_ids", "claim strategy must cite source_artifact ids"))
    fallback = strategy.get("fallback_positions")
    if not isinstance(fallback, list) or not fallback:
        problems.append(issue("FALLBACK_POSITIONS_MISSING", "claim_strategy.fallback_positions", "at least one narrower fallback position is required"))
    else:
        for index, item in enumerate(fallback):
            path = f"claim_strategy.fallback_positions[{index}]"
            if not isinstance(item, dict):
                problems.append(issue("FALLBACK_POSITION_INVALID", path, "fallback position must be an object"))
                continue
            for field in ("description", "why_narrower"):
                if not scalar_ok(item.get(field)):
                    problems.append(issue("FALLBACK_POSITION_FIELD_MISSING", f"{path}.{field}", "non-placeholder text required"))
            if not has_artifact_support(item, artifact_ids):
                problems.append(issue("FALLBACK_POSITION_SUPPORT_MISSING", path, "fallback position must cite source_artifact ids"))
    return problems


def validate_qc_review(packet: dict[str, Any], require_all_true: bool) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    qc = packet.get("qc_review")
    if not isinstance(qc, dict):
        return [issue("QC_REVIEW_MISSING", "qc_review", "self-review gate record is required")]
    for key in QC_REVIEW_KEYS:
        if key not in qc:
            problems.append(issue("QC_FIELD_MISSING", f"qc_review.{key}", "QC boolean required"))
        elif require_all_true and qc.get(key) is not True:
            problems.append(issue("QC_FIELD_NOT_TRUE", f"qc_review.{key}", "must be true before READY_FOR_ATTORNEY_REVIEW"))
    if not scalar_ok(qc.get("review_summary")):
        problems.append(issue("QC_SUMMARY_MISSING", "qc_review.review_summary", "review summary required"))
    return problems


def validate(packet: dict[str, Any], base: pathlib.Path | None, as_of: dt.date) -> dict[str, Any]:
    problems: list[dict[str, str]] = []

    if packet.get("schema") != SCHEMA_ID:
        problems.append(issue("SCHEMA_MISMATCH", "schema", f"expected {SCHEMA_ID}"))
    if packet.get("not_legal_advice_ack") is not True:
        problems.append(issue("LEGAL_ACK_MISSING", "not_legal_advice_ack", "must be true; this skill is not legal advice"))

    joined_text = "\n".join(all_strings(packet))
    if GUARANTEE_RE.search(joined_text):
        problems.append(issue("OVERCLAIM_GUARANTEE", "$", "remove filing/grant/registration guarantees or ready-to-file language"))

    submission = packet.get("submission") if isinstance(packet.get("submission"), dict) else {}
    if submission.get("office_submit_ready") is True or submission.get("submit_to_office") is True:
        problems.append(issue("SUBMISSION_OVERSTEP", "submission", "Light may prepare an attorney handoff, not certify or submit filing"))

    artifacts, artifact_issues = validate_artifacts(packet, base)
    problems.extend(artifact_issues)
    artifact_ids = set(artifacts)
    final_delivery = packet.get("final_delivery") if isinstance(packet.get("final_delivery"), dict) else {}
    delivery_status = final_delivery.get("status")

    problems.extend(validate_risk_triage(packet, as_of))
    problems.extend(validate_inventor_known_prior_art(packet))

    invention = packet.get("invention")
    if not isinstance(invention, dict):
        problems.append(issue("INVENTION_MISSING", "invention", "invention object is required"))
    else:
        for field in REQUIRED_INVENTION_FIELDS:
            if not scalar_ok(invention.get(field)):
                problems.append(issue("INVENTION_FIELD_MISSING", f"invention.{field}", "non-placeholder text required"))
        features = invention.get("distinguishing_features")
        if not isinstance(features, list) or not features:
            problems.append(issue("FEATURES_MISSING", "invention.distinguishing_features", "at least one distinguishing feature is required"))
        else:
            for index, feature in enumerate(features):
                path = f"invention.distinguishing_features[{index}]"
                if not isinstance(feature, dict) or not scalar_ok(feature.get("description")):
                    problems.append(issue("FEATURE_TEXT_MISSING", f"{path}.description", "feature description required"))
                    continue
                if not has_artifact_support(feature, artifact_ids):
                    problems.append(issue("FEATURE_SUPPORT_MISSING", path, "feature must cite existing source_artifact ids"))

    problems.extend(validate_prior_art(packet, as_of))
    problems.extend(validate_claim_strategy(packet, artifact_ids))

    claims = packet.get("draft_claims")
    if not isinstance(claims, list) or not claims:
        problems.append(issue("CLAIMS_MISSING", "draft_claims", "draft patent points or claims are required for attorney review"))
    else:
        for claim_index, claim in enumerate(claims):
            claim_path = f"draft_claims[{claim_index}]"
            if not isinstance(claim, dict) or not scalar_ok(claim.get("text")):
                problems.append(issue("CLAIM_TEXT_MISSING", f"{claim_path}.text", "claim/patent-point text required"))
                continue
            elements = claim.get("elements")
            if not isinstance(elements, list) or not elements:
                problems.append(issue("CLAIM_ELEMENTS_MISSING", f"{claim_path}.elements", "claim elements are required"))
                continue
            for element_index, element in enumerate(elements):
                path = f"{claim_path}.elements[{element_index}]"
                if not isinstance(element, dict) or not scalar_ok(element.get("text")):
                    problems.append(issue("CLAIM_ELEMENT_TEXT_MISSING", f"{path}.text", "claim element text required"))
                    continue
                if not has_artifact_support(element, artifact_ids):
                    problems.append(issue("CLAIM_ELEMENT_SUPPORT_MISSING", path, "claim element must cite source_artifact ids"))

    sections = packet.get("disclosure_sections")
    if not isinstance(sections, dict):
        problems.append(issue("SECTIONS_MISSING", "disclosure_sections", "section map is required"))
    else:
        for section in REQUIRED_SECTIONS:
            if not scalar_ok(sections.get(section)):
                problems.append(issue("SECTION_MISSING", f"disclosure_sections.{section}", "non-placeholder section text required"))

    for index, diagram in enumerate(as_list(packet.get("diagrams"))):
        if not isinstance(diagram, dict):
            problems.append(issue("DIAGRAM_INVALID", f"diagrams[{index}]", "diagram must be an object"))
            continue
        generator = str(diagram.get("generator", "")).strip().lower()
        text = "\n".join(all_strings(diagram))
        if diagram.get("ai_generated") is True or AI_DRAWING_RE.search(text):
            problems.append(issue("AI_DRAWING_FORBIDDEN", f"diagrams[{index}]", "patent figures must be programmatic/vector/manual, not AI-generated bitmap"))
        if generator not in ALLOWED_DIAGRAM_GENERATORS:
            problems.append(issue("DIAGRAM_GENERATOR_INVALID", f"diagrams[{index}].generator", "use Mermaid/Graphviz/PlantUML/SVG/programmatic/manual_vector or none"))
        if generator != "none":
            if not scalar_ok(diagram.get("source_locator")):
                problems.append(issue("DIAGRAM_SOURCE_MISSING", f"diagrams[{index}].source_locator", "diagram source locator required"))
            if not isinstance(diagram.get("source_sha256"), str) or not SHA_RE.match(diagram["source_sha256"]):
                problems.append(issue("DIAGRAM_HASH_MISSING", f"diagrams[{index}].source_sha256", "diagram source sha256 required"))

    allowed_status = {"DRAFT", "READY_FOR_ATTORNEY_REVIEW", "NEEDS_USER_INPUT"}
    if delivery_status not in allowed_status:
        problems.append(issue("DELIVERY_STATUS_INVALID", "final_delivery.status", "allowed: DRAFT, READY_FOR_ATTORNEY_REVIEW, NEEDS_USER_INPUT"))
    problems.extend(validate_qc_review(packet, delivery_status == "READY_FOR_ATTORNEY_REVIEW"))
    if delivery_status == "READY_FOR_ATTORNEY_REVIEW":
        if final_delivery.get("attorney_review_required") is not True:
            problems.append(issue("ATTORNEY_REVIEW_FLAG_MISSING", "final_delivery.attorney_review_required", "must be true before any filing use"))
        if not scalar_ok(final_delivery.get("open_questions_for_counsel")):
            problems.append(issue("COUNSEL_QUESTIONS_MISSING", "final_delivery.open_questions_for_counsel", "record open legal/prosecution questions"))

    return {
        "schema": REPORT_SCHEMA,
        "verdict": "FAIL" if any(row["severity"] == "ERROR" for row in problems) else "PASS",
        "checked_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of.isoformat(),
        "packet_schema": packet.get("schema"),
        "issues": problems,
    }


def run_selftest() -> int:
    root = repo_root()
    e2e_root = root / ".upgrade" / "_e2e" / "patent-disclosure-gate"
    e2e_root.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="selftest-", dir=e2e_root))
    try:
        evidence_dir = tmp / "evidence"
        evidence_dir.mkdir()
        design = evidence_dir / "design.md"
        design.write_text(
            "# Invention notes\nA scheduler groups jobs by tenant quota and retry budget.\n",
            encoding="utf-8",
        )
        diagram = evidence_dir / "architecture.mmd"
        diagram.write_text("flowchart LR\nA[tenant queue] --> B[quota scheduler]\n", encoding="utf-8")
        packet: dict[str, Any] = {
            "schema": SCHEMA_ID,
            "not_legal_advice_ack": True,
            "source_artifacts": [
                {"id": "A1", "path": "evidence/design.md", "sha256": file_sha256(design)},
            ],
            "risk_triage": {
                "public_disclosure": {
                    "status": "VERIFIED",
                    "summary": "No public demo, publication, sale or repository release before the validation date.",
                },
                "ownership_inventorship": {
                    "status": "VERIFIED",
                    "summary": "Inventorship and applicant facts are recorded for attorney review.",
                },
                "foreign_filing_or_secrecy": {
                    "status": "PLANNED",
                    "summary": "Foreign filing and secrecy review must be checked by counsel before filing.",
                    "next_check": "Ask counsel to review secrecy and foreign filing route.",
                },
                "trade_secret_redaction": {
                    "status": "VERIFIED",
                    "summary": "No third-party confidential content is included in the handoff packet.",
                },
            },
            "invention": {
                "title": "Tenant quota aware retry scheduler",
                "technical_field": "distributed job scheduling",
                "technical_problem": "burst retries starve lower-volume tenants",
                "technical_solution": "combine tenant quota, retry budget and queue aging into one scheduling score",
                "technical_effect": "reduces starvation while preserving bounded retry throughput",
                "distinguishing_features": [
                    {"description": "retry budget enters the dispatch score", "support_artifact_ids": ["A1"]},
                ],
            },
            "inventor_known_prior_art": {
                "status": "VERIFIED",
                "summary": "Inventors reported one known quota scheduler family and no known retry-budget scheduler.",
                "items": [
                    {
                        "title": "Internal quota scheduler baseline",
                        "source_or_person": "inventor interview notes",
                        "relationship": "background; lacks retry-budget dispatch scoring",
                    }
                ],
            },
            "prior_art": {
                "search_status": "VERIFIED",
                "checked_at": "2026-07-05",
                "queries": ["tenant quota retry scheduler patent"],
                "searched_sources": [
                    {
                        "source_name": "Google Patents",
                        "source_type": "patent_database",
                        "query": "tenant quota retry scheduler",
                        "checked_at": "2026-07-05",
                        "result_count": 8,
                    }
                ],
                "npl_not_searched_reason": "Selftest fixture exercises the non-patent-literature limitation path.",
                "nearest_results": [
                    {
                        "title": "Quota based scheduling",
                        "locator": "https://patents.google.com/patent/CN100000000A/en",
                        "relationship": "background only; does not combine retry budget",
                    }
                ],
            },
            "claim_strategy": {
                "broadest_defensible_point": "Dispatch scoring that combines tenant quota, retry budget and queue aging.",
                "enablement_support_summary": "A1 describes the score inputs, dispatch tick and retry budget update path.",
                "support_artifact_ids": ["A1"],
                "fallback_positions": [
                    {
                        "description": "Limit the score to retry budget plus tenant quota, excluding optional queue aging.",
                        "why_narrower": "Keeps the retry-budget contribution if queue aging is found in prior art.",
                        "support_artifact_ids": ["A1"],
                    }
                ],
            },
            "draft_claims": [
                {
                    "text": "A scheduling method using tenant quota and retry budget.",
                    "elements": [
                        {"text": "computing a dispatch score from retry budget", "support_artifact_ids": ["A1"]},
                    ],
                }
            ],
            "disclosure_sections": {
                "title": "Tenant quota aware retry scheduler",
                "technical_field": "Distributed scheduling",
                "background": "Existing queues may starve small tenants during retry storms.",
                "problem": "Retry bursts consume capacity unfairly.",
                "solution_summary": "Use a composite score using quota, retry budget and aging.",
                "technical_effects": "Bounded retries and improved fairness.",
                "embodiments": "Embodiment 1 computes a score every dispatch tick.",
                "claim_support_map": "Claim element 1 is supported by A1.",
                "attorney_handoff": "Please review scope, novelty and jurisdiction strategy.",
            },
            "diagrams": [
                {
                    "generator": "mermaid",
                    "source_locator": "evidence/architecture.mmd",
                    "source_sha256": file_sha256(diagram),
                    "ai_generated": False,
                }
            ],
            "submission": {"office_submit_ready": False, "submit_to_office": False},
            "qc_review": {
                "support_map_complete": True,
                "terms_consistent": True,
                "figures_auditable": True,
                "overclaim_removed": True,
                "counsel_questions_listed": True,
                "review_summary": "All claim elements map to A1, diagram source is auditable, and counsel questions remain explicit.",
            },
            "final_delivery": {
                "status": "READY_FOR_ATTORNEY_REVIEW",
                "attorney_review_required": True,
                "open_questions_for_counsel": "Check claim breadth against the cited nearest results.",
            },
        }
        checks: list[tuple[bool, str]] = []
        checks.append((validate(packet, tmp, dt.date(2026, 7, 5))["verdict"] == "PASS", "valid packet passes"))

        overclaim = copy.deepcopy(packet)
        overclaim["notes"] = "该方案保证授权，可直接提交。"
        checks.append((validate(overclaim, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "guarantee language fails"))

        bad_diagram = copy.deepcopy(packet)
        bad_diagram["diagrams"][0]["ai_generated"] = True
        checks.append((validate(bad_diagram, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "AI drawing fails"))

        bad_hash = copy.deepcopy(packet)
        bad_hash["source_artifacts"][0]["sha256"] = "sha256:" + "0" * 64
        checks.append((validate(bad_hash, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "hash mismatch fails"))

        submit = copy.deepcopy(packet)
        submit["submission"]["office_submit_ready"] = True
        checks.append((validate(submit, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "filing overstep fails"))

        ok = True
        for passed, label in checks:
            ok &= passed
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Light patent disclosure packet")
    parser.add_argument("--packet", type=pathlib.Path, help="packet JSON file")
    parser.add_argument("--base", type=pathlib.Path, help="project root for source/hash checks")
    parser.add_argument("--as-of", default=dt.date.today().isoformat(), help="validation date, YYYY-MM-DD")
    parser.add_argument("--report", type=pathlib.Path, help="optional output report JSON")
    parser.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.packet is None:
        parser.error("--packet is required unless --selftest is used")

    problems: list[dict[str, str]] = []
    as_of = parse_date(args.as_of, "--as-of", dt.date.max, problems) or dt.date.today()
    packet = load_json(args.packet)
    if not isinstance(packet, dict):
        raise SystemExit("packet must be a JSON object")
    base = args.base.resolve() if args.base else None
    report = validate(packet, base, as_of)
    if problems:
        report["issues"] = problems + report["issues"]
        report["verdict"] = "FAIL"

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
