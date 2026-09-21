#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate that idea seeds are rooted in real gap evidence, not empty intuition."""
from __future__ import annotations

import argparse
import json
import datetime as dt
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
from _shared.findings_schema import Finding, GateResult  # noqa: E402
from _shared.gate_runner import run_gates  # noqa: E402

SCHEMA_ID = "light.idea_gap_evidence.v1"
REPORT_SCHEMA = "light.idea_gap_evidence_report.v1"
GAP_TYPES = {
    "LITERATURE",
    "METHODOLOGICAL",
    "APPLICATION",
    "INTERDISCIPLINARY",
    "TEMPORAL",
    "DATA",
    "THEORY",
    "USER_CONSTRAINT",
    "OTHER_DECLARED",
}
GAP_STATES = {"SUPPORTED", "USER_STATED", "UNKNOWN", "UNAVAILABLE"}
SOURCE_STATES = {"VERIFIED", "AVAILABLE", "UNKNOWN", "UNAVAILABLE"}
CLAIM_STRENGTHS = {"SUPPORTED_GAP", "USER_STATED", "SPECULATIVE", "UNKNOWN"}
PROVOCATION_OPERATORS = {
    "gap-driven",
    "method-transfer",
    "data-driven",
    "problem-reframe",
    "combination",
    "theory-gap",
    "efficiency",
    "other-declared",
}
FACETS = {"application_domain", "purpose", "mechanism", "evaluation", "data", "theory"}
HTTP_OK = set(range(200, 400))
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|<[^>]+>|replace[-_ ]?with|todo|tbd)", re.IGNORECASE)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and not _is_placeholder(text) and text not in {
        "unknown",
        "pending",
        "todo",
        "tbd",
        "n/a",
        "none",
        "-",
        "replace-with",
    }


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.casefold()
    if lowered in {"unknown", "pending", "todo", "tbd", "n/a", "na", "none", "-", "null"}:
        return True
    return bool(PLACEHOLDER_RE.search(text))


def _local_or_escaping(value: Any) -> bool:
    text = str(value or "").strip()
    if WINDOWS_DRIVE_RE.match(text) or text.startswith(("\\\\", "/", "~")):
        return True
    parts = re.split(r"[\\/]+", text)
    return ".." in parts


def _locator_value_ok(key: str, value: Any) -> bool:
    if not _real(value):
        return False
    text = str(value).strip().casefold()
    if key in {"path", "locator", "url"} and (
        text.startswith("file:") or _local_or_escaping(value)
    ):
        return False
    return True


def _sha(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _locator(source: dict[str, Any]) -> bool:
    return any(
        _locator_value_ok(key, source.get(key))
        for key in ("doi", "url", "path", "query", "locator")
    )


def _parse_iso_date(value: Any) -> dt.date | None:
    try:
        text = str(value).strip()
        if _is_placeholder(text):
            return None
        if "T" in text:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        if " " in text:
            return dt.datetime.fromisoformat(text).date()
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _checked_at(value: Any) -> bool:
    return _parse_iso_date(value) is not None


def _as_of_date(value: Any = None) -> dt.date:
    if value is None or str(value).strip() == "":
        return dt.date.today()
    parsed = _parse_iso_date(value)
    if parsed is None:
        raise ValueError("--as-of/spec.as_of must be an ISO date or datetime")
    return parsed


def _not_future(value: Any, as_of: dt.date) -> bool:
    parsed = _parse_iso_date(value)
    return parsed is not None and parsed <= as_of


def _negative_search_ok(row: dict[str, Any]) -> bool:
    if not _real(row.get("query")) or not _real(row.get("corpus")):
        return False
    if not _checked_at(row.get("checked_at")):
        return False
    if row.get("status") not in {"ZERO_HIT", "NO_EQUIVALENT", "SCREENED"}:
        return False
    result_count = row.get("result_count")
    if not isinstance(result_count, int) or isinstance(result_count, bool) or result_count < 0:
        return False
    http_status = row.get("http_status")
    if http_status is not None and http_status not in HTTP_OK:
        return False
    return True


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema must be {SCHEMA_ID}")
    today = _as_of_date(as_of if as_of is not None else spec.get("as_of"))
    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append(
            {"code": code, "loc": loc, "severity": severity, "message": message}
        )

    if not _real(spec.get("direction")):
        add("DIRECTION_GAP", "direction", "missing concrete research direction")

    sources_raw = spec.get("evidence_sources")
    gaps_raw = spec.get("gap_claims")
    links_raw = spec.get("candidate_links")
    if not isinstance(sources_raw, list) or not isinstance(gaps_raw, list):
        raise ValueError("evidence_sources and gap_claims must be lists")
    if not isinstance(links_raw, list):
        raise ValueError("candidate_links must be a list")
    if not gaps_raw:
        add("NO_GAP_CLAIMS", "gap_claims", "at least one gap claim is required")
    if not links_raw:
        add(
            "NO_CANDIDATE_LINKS",
            "candidate_links",
            "at least one candidate must be linked to gap evidence",
        )

    sources: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(sources_raw):
        if not isinstance(row, dict):
            raise ValueError("evidence_sources rows must be objects")
        source_id = str(row.get("source_id") or "")
        if not source_id or source_id in sources:
            raise ValueError("source_id missing or duplicate")
        sources[source_id] = row
        if row.get("status") not in SOURCE_STATES:
            add("SOURCE_STATUS_GAP", f"source:{source_id}", "invalid source status")
        if row.get("status") in {"VERIFIED", "AVAILABLE"} and not _locator(row):
            add(
                "SOURCE_LOCATOR_GAP",
                f"source:{source_id}",
                "verified/available source needs a real doi/url/path/query/locator; local absolute, UNC/root, ../, or template locators are invalid",
            )
        for locator_key in ("url", "path", "locator"):
            locator_value = row.get(locator_key)
            if str(locator_value or "").strip() and not _locator_value_ok(locator_key, locator_value):
                add(
                    "SOURCE_LOCATOR_PRIVATE_OR_PLACEHOLDER",
                    f"source:{source_id}.{locator_key}",
                    f"{locator_key} must not be a template, local absolute path, UNC/root path, or ../ escape",
                )
        if row.get("status") == "VERIFIED" and not _sha(row.get("sha256")):
            add(
                "SOURCE_HASH_GAP",
                f"source:{source_id}",
                "verified source needs sha256: digest",
            )
        if row.get("status") in {"VERIFIED", "AVAILABLE"} and not _checked_at(
            row.get("checked_at")
        ):
            add(
                "SOURCE_CHECKED_AT_GAP",
                f"source:{source_id}",
                "verified/available source needs checked_at date",
            )
        elif row.get("status") in {"VERIFIED", "AVAILABLE"} and not _not_future(
            row.get("checked_at"), today
        ):
            add(
                "SOURCE_CHECKED_AT_FUTURE",
                f"source:{source_id}",
                f"checked_at is later than as_of={today.isoformat()}",
            )
        if not _real(row.get("title")) and not _real(row.get("claim")):
            add(
                "SOURCE_DESCRIPTION_GAP",
                f"evidence_sources[{index}]",
                "source needs a title or claim so users can inspect the root",
            )

    gaps: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(gaps_raw):
        if not isinstance(row, dict):
            raise ValueError("gap_claims rows must be objects")
        gap_id = str(row.get("gap_id") or "")
        if not gap_id or gap_id in gaps:
            raise ValueError("gap_id missing or duplicate")
        gaps[gap_id] = row
        if row.get("gap_type") not in GAP_TYPES:
            add("GAP_TYPE_GAP", f"gap:{gap_id}", "invalid or missing gap_type")
        if row.get("status") not in GAP_STATES:
            add("GAP_STATUS_GAP", f"gap:{gap_id}", "invalid or missing status")
        if not _real(row.get("claim")):
            add("GAP_CLAIM_GAP", f"gap:{gap_id}", "gap claim is empty or placeholder")
        if row.get("gap_type") == "OTHER_DECLARED" and not _real(
            row.get("gap_type_detail")
        ):
            add("GAP_TYPE_DETAIL_GAP", f"gap:{gap_id}", "OTHER_DECLARED needs detail")

        source_ids = row.get("source_ids")
        if not isinstance(source_ids, list):
            raise ValueError("gap_claims.source_ids must be lists")
        if row.get("status") == "SUPPORTED" and not source_ids:
            add("SUPPORTED_GAP_SOURCE_GAP", f"gap:{gap_id}", "SUPPORTED gap needs sources")
        for source_id in source_ids:
            source = sources.get(str(source_id))
            if source is None:
                add("UNKNOWN_GAP_SOURCE", f"gap:{gap_id}", f"unknown source {source_id}")
            elif source.get("status") in {"UNKNOWN", "UNAVAILABLE"}:
                add(
                    "UNRESOLVED_GAP_SOURCE",
                    f"gap:{gap_id}",
                    f"source {source_id} is {source.get('status')}",
                    "unresolved",
                )

        negative = row.get("negative_searches")
        if negative is None:
            negative = []
        if not isinstance(negative, list):
            raise ValueError("gap_claims.negative_searches must be lists when present")
        if row.get("claims_no_prior_work") is True and not negative:
            add(
                "NEGATIVE_SEARCH_GAP",
                f"gap:{gap_id}",
                "no-prior-work claim needs negative searches with corpus/query/date",
            )
        for n_index, search in enumerate(negative):
            if not isinstance(search, dict) or not _negative_search_ok(search):
                add(
                    "NEGATIVE_SEARCH_ROW_GAP",
                    f"gap:{gap_id}.negative_searches[{n_index}]",
                    "negative search needs query, corpus, checked_at, status, result_count, and valid http_status",
                )
            elif not _not_future(search.get("checked_at"), today):
                add(
                    "NEGATIVE_SEARCH_CHECKED_AT_FUTURE",
                    f"gap:{gap_id}.negative_searches[{n_index}]",
                    f"negative search checked_at is later than as_of={today.isoformat()}",
                )

    linked_candidates: set[str] = set()
    linked_gaps: set[str] = set()
    for index, row in enumerate(links_raw):
        if not isinstance(row, dict):
            raise ValueError("candidate_links rows must be objects")
        idea_id = str(row.get("idea_id") or "")
        gap_ids = row.get("gap_ids")
        if not idea_id:
            add("IDEA_ID_GAP", f"candidate_links[{index}]", "candidate link needs idea_id")
            continue
        linked_candidates.add(idea_id)
        if not isinstance(gap_ids, list) or not gap_ids:
            add("CANDIDATE_GAP_LINK_GAP", f"idea:{idea_id}", "candidate needs at least one gap_id")
            gap_ids = []
        if row.get("claim_strength") not in CLAIM_STRENGTHS:
            add("CLAIM_STRENGTH_GAP", f"idea:{idea_id}", "invalid claim_strength")
        if row.get("provocation_operator") not in PROVOCATION_OPERATORS:
            add(
                "PROVOCATION_OPERATOR_GAP",
                f"idea:{idea_id}",
                "candidate needs one known provocation operator",
            )
        facets = row.get("facets")
        if not isinstance(facets, list) or not facets:
            add("FACET_GAP", f"idea:{idea_id}", "candidate needs affected facet list")
            facets = []
        for facet in facets:
            if facet not in FACETS:
                add("FACET_GAP", f"idea:{idea_id}", f"unknown facet {facet}")
        for gap_id in gap_ids:
            gap = gaps.get(str(gap_id))
            if gap is None:
                add("UNKNOWN_CANDIDATE_GAP", f"idea:{idea_id}", f"unknown gap {gap_id}")
                continue
            linked_gaps.add(str(gap_id))
            if (
                row.get("eligible_to_expand") is True
                and row.get("claim_strength") == "SUPPORTED_GAP"
                and gap.get("status") != "SUPPORTED"
            ):
                add(
                    "ELIGIBLE_WITH_UNRESOLVED_GAP",
                    f"idea:{idea_id}",
                    f"eligible supported candidate links to {gap.get('status')} gap {gap_id}",
                )

    if gaps and not linked_candidates:
        add("NO_CANDIDATE_LINKS", "candidate_links", "no candidates linked to gap evidence")
    unused_supported = [
        gap_id
        for gap_id, row in gaps.items()
        if row.get("status") == "SUPPORTED" and gap_id not in linked_gaps
    ]
    if unused_supported:
        add(
            "UNUSED_SUPPORTED_GAP",
            "gap_claims",
            f"supported gaps not used by any candidate: {', '.join(sorted(unused_supported))}",
            "unresolved",
        )

    gap_type_counts = {
        gap_type: sum(1 for row in gaps.values() if row.get("gap_type") == gap_type)
        for gap_type in sorted(GAP_TYPES)
    }
    status = (
        "FAIL"
        if any(issue["severity"] == "error" for issue in issues)
        else "UNRESOLVED"
        if issues
        else "PASS"
    )
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "direction": spec.get("direction"),
        "n_sources": len(sources),
        "n_gap_claims": len(gaps),
        "n_candidate_links": len(linked_candidates),
        "gap_type_counts": gap_type_counts,
        "as_of": today.isoformat(),
        "issues": issues,
        "honesty": (
            "PASS only proves candidate seeds are linked to declared gap evidence and "
            "negative-search records when no-prior-work is claimed; it does not prove "
            "the idea is novel, important, feasible, or publication-worthy."
        ),
    }


def emit_findings(spec: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    def gate(_: dict[str, Any]) -> GateResult:
        if report["status"] == "PASS":
            return GateResult(
                "idea_gap_evidence",
                "pass",
                "info",
                [],
                note="gap evidence, negative searches, and candidate links are structurally closed.",
            )
        findings = [
            Finding(
                issue["loc"],
                issue["message"],
                "Root the candidate in literature-search/domain-map evidence, add checked sources or mark UNKNOWN instead of claiming support.",
                rule=issue["code"],
            )
            for issue in report["issues"]
        ]
        severity = "critical" if report["status"] == "FAIL" else "major"
        return GateResult(
            "idea_gap_evidence",
            "fail" if report["status"] == "FAIL" else "warn",
            severity,
            findings,
            note=f"gap evidence status={report['status']}; unsupported seeds must not be packaged as evidence-rooted ideas.",
        )

    return run_gates(
        [gate],
        report,
        producer="idea-generation",
        target=str(spec.get("direction") or "idea-seeds"),
        summary="idea gap evidence and candidate seed grounding gate.",
        fresh_evidence=True,
    ).to_dict()


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "direction": "contrastive learning for animal behavior monitoring",
        "evidence_sources": [
            {
                "source_id": "S1",
                "status": "VERIFIED",
                "title": "Recent supervised accelerometer estrus detector",
                "doi": "10.0000/example",
                "checked_at": "2026-07-05",
                "sha256": "sha256:" + "a" * 64,
            }
        ],
        "gap_claims": [
            {
                "gap_id": "G1",
                "gap_type": "METHODOLOGICAL",
                "status": "SUPPORTED",
                "claim": "Existing estrus detectors rely on dense supervised labels.",
                "source_ids": ["S1"],
                "claims_no_prior_work": True,
                "negative_searches": [
                    {
                        "query": "self-supervised contrastive goat estrus accelerometer",
                        "corpus": "OpenAlex",
                        "checked_at": "2026-07-05",
                        "status": "NO_EQUIVALENT",
                        "result_count": 12,
                        "http_status": 200,
                    }
                ],
            }
        ],
        "candidate_links": [
            {
                "idea_id": "I1",
                "gap_ids": ["G1"],
                "claim_strength": "SUPPORTED_GAP",
                "provocation_operator": "method-transfer",
                "facets": ["mechanism", "data"],
                "eligible_to_expand": True,
            }
        ],
    }


def _selftest() -> int:
    good = evaluate(_base(), as_of="2026-07-05")
    assert good["status"] == "PASS", json.dumps(good, ensure_ascii=False, indent=2)
    assert emit_findings(_base(), good)["verdict"] == "pass"

    bad = json.loads(json.dumps(_base()))
    bad["gap_claims"][0]["source_ids"] = ["MISSING"]
    bad["gap_claims"][0]["negative_searches"] = []
    bad["candidate_links"][0]["gap_ids"] = []
    report = evaluate(bad, as_of="2026-07-05")
    assert report["status"] == "FAIL", json.dumps(report, ensure_ascii=False, indent=2)
    codes = {issue["code"] for issue in report["issues"]}
    expected = {
        "UNKNOWN_GAP_SOURCE",
        "NEGATIVE_SEARCH_GAP",
        "CANDIDATE_GAP_LINK_GAP",
    }
    assert expected <= codes, (expected, codes)
    assert emit_findings(bad, report)["verdict"] == "fail"

    unresolved = json.loads(json.dumps(_base()))
    unresolved["gap_claims"].append(
        {
            "gap_id": "G2",
            "gap_type": "TEMPORAL",
            "status": "SUPPORTED",
            "claim": "New sensor hardware changed the feasible measurement window.",
            "source_ids": ["S1"],
        }
    )
    unresolved_report = evaluate(unresolved, as_of="2026-07-05")
    assert unresolved_report["status"] == "UNRESOLVED", json.dumps(
        unresolved_report, ensure_ascii=False, indent=2
    )
    assert "UNUSED_SUPPORTED_GAP" in {
        issue["code"] for issue in unresolved_report["issues"]
    }

    unknown = json.loads(json.dumps(_base()))
    unknown["gap_claims"][0]["status"] = "UNKNOWN"
    unknown["candidate_links"][0]["eligible_to_expand"] = True
    assert "ELIGIBLE_WITH_UNRESOLVED_GAP" in {
        issue["code"] for issue in evaluate(unknown, as_of="2026-07-05")["issues"]
    }
    future_source = json.loads(json.dumps(_base()))
    future_source["evidence_sources"][0]["checked_at"] = "2999-01-01"
    assert "SOURCE_CHECKED_AT_FUTURE" in {
        issue["code"] for issue in evaluate(future_source, as_of="2026-07-05")["issues"]
    }

    future_negative = json.loads(json.dumps(_base()))
    future_negative["gap_claims"][0]["negative_searches"][0]["checked_at"] = "2999-01-01"
    assert "NEGATIVE_SEARCH_CHECKED_AT_FUTURE" in {
        issue["code"] for issue in evaluate(future_negative, as_of="2026-07-05")["issues"]
    }

    private_path = json.loads(json.dumps(_base()))
    private_path["evidence_sources"][0]["path"] = "D:\\private\\unpublished-note.pdf"
    assert "SOURCE_LOCATOR_PRIVATE_OR_PLACEHOLDER" in {
        issue["code"] for issue in evaluate(private_path, as_of="2026-07-05")["issues"]
    }

    file_url = json.loads(json.dumps(_base()))
    file_url["evidence_sources"][0]["url"] = "file:///D:/private/unpublished-note.pdf"
    assert "SOURCE_LOCATOR_PRIVATE_OR_PLACEHOLDER" in {
        issue["code"] for issue in evaluate(file_url, as_of="2026-07-05")["issues"]
    }

    escaping_path = json.loads(json.dumps(_base()))
    escaping_path["evidence_sources"][0].pop("doi", None)
    escaping_path["evidence_sources"][0]["path"] = "../private/source.pdf"
    path_codes = {
        issue["code"] for issue in evaluate(escaping_path, as_of="2026-07-05")["issues"]
    }
    assert "SOURCE_LOCATOR_GAP" in path_codes and "SOURCE_LOCATOR_PRIVATE_OR_PLACEHOLDER" in path_codes
    print("gap_evidence_gate selftest PASS: sources/gaps/negative-searches/links + future/private-locator guards")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--report", help="write light.findings.v1")
    parser.add_argument("--as-of", help="ISO date/datetime; defaults to today and blocks future evidence dates")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("need --input or --selftest")
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = evaluate(spec, as_of=args.as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(emit_findings(spec, report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
