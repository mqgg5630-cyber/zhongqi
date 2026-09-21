#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""innovation_engine.py — originality typing + anti-collage gate.

This gate turns "innovation" from a vibe into auditable claims. It does not
prove that an idea is truly original; it blocks candidates that merely combine
known parts without a declared mechanism/problem delta, discriminating
prediction, boundary condition and honest claim level.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
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

SCHEMA_ID = "light.innovation_engine.v1"
REPORT_SCHEMA = "light.innovation_engine_report.v1"

ORIGINALITY_TYPES = {
    "NEW_PROBLEM",
    "NEW_MECHANISM",
    "NEW_MEASUREMENT",
    "NEW_DATA_ASSET",
    "NEW_THEORY",
    "NEW_EXPERIMENTAL_PARADIGM",
    "CROSS_DOMAIN_TRANSFER",
    "SYSTEMATIZATION",
    "ENGINEERING_INCREMENT",
    "NEGATIVE_RESULT",
    "OTHER_DECLARED",
}
STRONG_TYPES = {
    "NEW_PROBLEM",
    "NEW_MECHANISM",
    "NEW_MEASUREMENT",
    "NEW_DATA_ASSET",
    "NEW_THEORY",
    "NEW_EXPERIMENTAL_PARADIGM",
    "CROSS_DOMAIN_TRANSFER",
    "NEGATIVE_RESULT",
}
ORIGINALITY_SOURCES = {
    "OBSERVED_ANOMALY",
    "LITERATURE_CONTRADICTION",
    "MECHANISM_GAP",
    "MEASUREMENT_GAP",
    "DATASET_OPPORTUNITY",
    "CONSTRAINT_SHIFT",
    "CROSS_DOMAIN_ANALOGY",
    "FAILURE_CASE",
    "USER_INSIGHT",
    "THEORY_TENSION",
    "OTHER_DECLARED",
}
CLAIM_LEVELS = {"BREAKTHROUGH", "STRONG", "MODEST", "INCREMENTAL"}
EVIDENCE_STATES = {"VERIFIED", "USER_STATED", "UNKNOWN", "UNAVAILABLE"}
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|<[^>]+>|replace[-_ ]?with|todo|tbd)", re.IGNORECASE)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
HYPE_RE = re.compile(r"(突破|颠覆|首个|首次|revolution|breakthrough|paradigm|first-ever)", re.IGNORECASE)


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if text.casefold() in {"unknown", "pending", "todo", "tbd", "n/a", "na", "none", "-", "null"}:
        return True
    return bool(PLACEHOLDER_RE.search(text))


def _real(value: Any) -> bool:
    return not _is_placeholder(value)


def _local_or_escaping(value: Any) -> bool:
    text = str(value or "").strip()
    if WINDOWS_DRIVE_RE.match(text) or text.startswith(("\\\\", "/", "~")):
        return True
    return ".." in re.split(r"[\\/]+", text)


def _locator_ok(value: Any) -> bool:
    if not _real(value):
        return False
    text = str(value).strip().casefold()
    return not (text.startswith("file:") or _local_or_escaping(value))


def _sha(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _parse_iso_date(value: Any) -> dt.date | None:
    try:
        text = str(value or "").strip()
        if _is_placeholder(text):
            return None
        if "T" in text:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        if " " in text:
            return dt.datetime.fromisoformat(text).date()
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


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


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema must be {SCHEMA_ID}")
    today = _as_of_date(as_of if as_of is not None else spec.get("as_of"))
    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    if not _real(spec.get("direction")):
        add("DIRECTION_GAP", "direction", "missing concrete research direction")

    evidence_rows = spec.get("evidence")
    candidates_raw = spec.get("candidates")
    if not isinstance(evidence_rows, list) or not isinstance(candidates_raw, list):
        raise ValueError("evidence and candidates must be lists")
    if not candidates_raw:
        add("NO_CANDIDATES", "candidates", "at least one candidate is required")

    evidence: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence_rows):
        if not isinstance(row, dict):
            raise ValueError("evidence rows must be objects")
        evidence_id = str(row.get("evidence_id") or "")
        if not evidence_id or evidence_id in evidence:
            raise ValueError("evidence_id missing or duplicate")
        evidence[evidence_id] = row
        if row.get("status") not in EVIDENCE_STATES:
            add("EVIDENCE_STATUS_GAP", f"evidence:{evidence_id}", "invalid evidence status")
        if row.get("status") in {"VERIFIED", "USER_STATED"} and not _locator_ok(row.get("locator")):
            add(
                "EVIDENCE_LOCATOR_GAP",
                f"evidence:{evidence_id}",
                "verified/user-stated evidence needs a public handoff locator; no local absolute, file:, ../ or placeholder locator",
            )
        if row.get("status") == "VERIFIED" and not _sha(row.get("sha256")):
            add("EVIDENCE_HASH_GAP", f"evidence:{evidence_id}", "VERIFIED evidence needs sha256 digest")
        if row.get("status") in {"VERIFIED", "USER_STATED"}:
            if _parse_iso_date(row.get("checked_at")) is None:
                add("EVIDENCE_DATE_GAP", f"evidence:{evidence_id}", "evidence needs checked_at")
            elif not _not_future(row.get("checked_at"), today):
                add("EVIDENCE_DATE_FUTURE", f"evidence:{evidence_id}", f"checked_at later than as_of={today.isoformat()}")

    passed_ids: list[str] = []
    type_histogram: dict[str, int] = {}
    source_histogram: dict[str, int] = {}
    claim_levels: dict[str, str] = {}

    for index, row in enumerate(candidates_raw):
        if not isinstance(row, dict):
            raise ValueError("candidate rows must be objects")
        idea_id = str(row.get("idea_id") or "")
        if not idea_id:
            add("IDEA_ID_GAP", f"candidates[{index}]", "candidate needs idea_id")
            continue
        title = str(row.get("title") or "")
        if not _real(title):
            add("TITLE_GAP", f"idea:{idea_id}", "candidate needs title")

        types = [str(t) for t in _list(row.get("originality_types"))]
        sources = [str(s) for s in _list(row.get("originality_sources"))]
        if not types:
            add("ORIGINALITY_TYPE_GAP", f"idea:{idea_id}", "declare at least one originality type")
        for value in types:
            if value not in ORIGINALITY_TYPES:
                add("ORIGINALITY_TYPE_GAP", f"idea:{idea_id}", f"unknown originality type {value}")
            else:
                type_histogram[value] = type_histogram.get(value, 0) + 1
        if not sources:
            add("ORIGINALITY_SOURCE_GAP", f"idea:{idea_id}", "declare at least one originality source")
        for value in sources:
            if value not in ORIGINALITY_SOURCES:
                add("ORIGINALITY_SOURCE_GAP", f"idea:{idea_id}", f"unknown originality source {value}")
            else:
                source_histogram[value] = source_histogram.get(value, 0) + 1

        claim_level = str(row.get("claim_level") or "")
        claim_levels[idea_id] = claim_level
        if claim_level not in CLAIM_LEVELS:
            add("CLAIM_LEVEL_GAP", f"idea:{idea_id}", "claim_level must be BREAKTHROUGH/STRONG/MODEST/INCREMENTAL")

        evidence_ids = [str(eid) for eid in _list(row.get("evidence_ids"))]
        if not evidence_ids:
            add("INNOVATION_EVIDENCE_GAP", f"idea:{idea_id}", "candidate needs evidence_ids linking its originality source")
        for evidence_id in evidence_ids:
            ev = evidence.get(evidence_id)
            if ev is None:
                add("UNKNOWN_EVIDENCE", f"idea:{idea_id}", f"unknown evidence_id {evidence_id}")
            elif ev.get("status") in {"UNKNOWN", "UNAVAILABLE"}:
                add("UNRESOLVED_EVIDENCE", f"idea:{idea_id}", f"evidence {evidence_id} is {ev.get('status')}", "unresolved")

        known_components = _list(row.get("known_components"))
        if len([x for x in known_components if _real(x)]) < 2 and "CROSS_DOMAIN_TRANSFER" in types:
            add("TRANSFER_COMPONENT_GAP", f"idea:{idea_id}", "cross-domain transfer needs at least source and target known components")
        anti = row.get("anti_collage") or {}
        if not isinstance(anti, dict):
            raise ValueError("anti_collage must be an object")
        for field in (
            "mechanism_or_problem_delta",
            "why_not_plain_combination",
            "non_additive_prediction",
            "competing_explanation",
            "discriminating_test",
            "kill_criterion",
            "boundary_conditions",
        ):
            if not _real(anti.get(field)):
                add("ANTI_COLLAGE_FIELD_GAP", f"idea:{idea_id}.anti_collage", f"missing {field}")

        weak_only = bool(types) and not (set(types) & STRONG_TYPES)
        if weak_only and claim_level in {"BREAKTHROUGH", "STRONG"}:
            add(
                "CLAIM_LEVEL_OVERREACH",
                f"idea:{idea_id}",
                "SYSTEMATIZATION/ENGINEERING_INCREMENT-only candidate cannot claim BREAKTHROUGH/STRONG",
            )
        if weak_only and HYPE_RE.search(title + " " + str(row.get("claim") or "")):
            add(
                "HYPE_WORDING_OVERREACH",
                f"idea:{idea_id}",
                "incremental/systematization candidate uses breakthrough/first/paradigm wording",
            )
        if "CROSS_DOMAIN_TRANSFER" in types:
            transfer = row.get("transfer") or {}
            for field in ("source_domain", "target_domain", "transferable_mechanism", "mismatch_risk"):
                if not _real(transfer.get(field)):
                    add("TRANSFER_RATIONALE_GAP", f"idea:{idea_id}.transfer", f"missing {field}")
        if {"NEW_MECHANISM", "NEW_THEORY"} & set(types):
            if not _real(row.get("differentiating_prediction")):
                add("DIFFERENTIATING_PREDICTION_GAP", f"idea:{idea_id}", "new mechanism/theory needs differentiating_prediction")
        if {"NEW_MEASUREMENT", "NEW_DATA_ASSET", "NEW_EXPERIMENTAL_PARADIGM"} & set(types):
            if not _real(row.get("validation_plan")):
                add("VALIDATION_PLAN_GAP", f"idea:{idea_id}", "measurement/data/paradigm innovation needs validation_plan")

    blocking_codes = {i["code"] for i in issues if i["severity"] == "error"}
    for row in candidates_raw:
        if not isinstance(row, dict) or not row.get("idea_id"):
            continue
        idea_id = str(row["idea_id"])
        prefix = f"idea:{idea_id}"
        if not any(str(issue["loc"]).startswith(prefix) for issue in issues if issue["severity"] == "error"):
            passed_ids.append(idea_id)

    status = "FAIL" if blocking_codes else "UNRESOLVED" if issues else "PASS"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "passed_ids": passed_ids,
        "type_histogram": dict(sorted(type_histogram.items())),
        "source_histogram": dict(sorted(source_histogram.items())),
        "claim_levels": claim_levels,
        "as_of": today.isoformat(),
        "issues": issues,
        "honesty": (
            "PASS means each candidate declares a non-collage originality source, boundary, "
            "claim level and discriminating test. It does not prove true novelty or value; "
            "idea-critique must still run prior-art and human/Pareto review."
        ),
    }


def emit_findings(spec: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    def innovation_gate(_: dict[str, Any]) -> GateResult:
        if report["status"] == "PASS":
            return GateResult(
                "innovation_engine", "pass", "info", [],
                note="原创来源分型、反拼接字段、claim 强度与判别实验字段闭合。",
            )
        findings = [
            Finding(
                issue["loc"],
                issue["message"],
                "补齐原创来源/反拼接解释/边界/判别实验；若只是工程增量，降级 claim_level 与措辞。",
                rule=issue["code"],
            )
            for issue in report["issues"]
        ]
        return GateResult(
            "innovation_engine", "fail", "critical", findings,
            note=f"innovation status={report['status']}；拼接式或过度宣称候选不得送 idea-critique。",
        )

    return run_gates(
        [innovation_gate],
        report,
        producer="idea-generation",
        target=str(spec.get("direction") or "idea-candidates"),
        summary="originality typing + anti-collage innovation gate.",
        fresh_evidence=True,
    ).to_dict()


def _base() -> dict[str, Any]:
    h = "sha256:" + "a" * 64
    return {
        "schema": SCHEMA_ID,
        "direction": "cross-domain physiological behavior monitoring",
        "as_of": "2026-07-05",
        "evidence": [
            {
                "evidence_id": "E1",
                "status": "VERIFIED",
                "locator": "fixture:prior-work-example",
                "checked_at": "2026-07-05",
                "sha256": h,
                "note": "prior work reports label scarcity and domain shift",
            }
        ],
        "candidates": [
            {
                "idea_id": "I1",
                "title": "Mechanism-aware self-supervised event detector",
                "claim": "Use circadian phase constraints to distinguish behavior events from activity bursts.",
                "originality_types": ["NEW_MECHANISM", "CROSS_DOMAIN_TRANSFER"],
                "originality_sources": ["MECHANISM_GAP", "CROSS_DOMAIN_ANALOGY"],
                "claim_level": "STRONG",
                "evidence_ids": ["E1"],
                "known_components": ["self-supervised contrastive learning", "circadian phase model"],
                "anti_collage": {
                    "mechanism_or_problem_delta": "The target shifts from activity recognition to mechanism-constrained event discrimination.",
                    "why_not_plain_combination": "The phase constraint changes the negative-pair definition and predicts different failure modes.",
                    "non_additive_prediction": "Performance should improve specifically near confounded high-activity windows, not uniformly.",
                    "competing_explanation": "A larger encoder may explain gains without the mechanism.",
                    "discriminating_test": "Ablate phase-aware negatives under matched parameter count.",
                    "kill_criterion": "No interaction between phase windows and event discrimination after ablation.",
                    "boundary_conditions": "Only applies when circadian phase is measured or inferable.",
                },
                "transfer": {
                    "source_domain": "chronobiology",
                    "target_domain": "animal behavior sensing",
                    "transferable_mechanism": "phase-dependent confounding structure",
                    "mismatch_risk": "phase signals may be weaker in noisy barn environments",
                },
                "differentiating_prediction": "The method reduces false positives during predictable activity bursts more than during random bursts.",
            }
        ],
    }


def _selftest() -> int:
    good = evaluate(_base(), as_of="2026-07-05")
    assert good["status"] == "PASS", json.dumps(good, ensure_ascii=False, indent=2)
    assert emit_findings(_base(), good)["verdict"] == "pass"

    collage = json.loads(json.dumps(_base()))
    c = collage["candidates"][0]
    c["title"] = "Breakthrough first-ever Transformer plus graph model"
    c["originality_types"] = ["ENGINEERING_INCREMENT"]
    c["originality_sources"] = ["USER_INSIGHT"]
    c["claim_level"] = "BREAKTHROUGH"
    c["anti_collage"]["why_not_plain_combination"] = ""
    report = evaluate(collage, as_of="2026-07-05")
    codes = {issue["code"] for issue in report["issues"]}
    assert report["status"] == "FAIL", json.dumps(report, ensure_ascii=False, indent=2)
    assert {"ANTI_COLLAGE_FIELD_GAP", "CLAIM_LEVEL_OVERREACH", "HYPE_WORDING_OVERREACH"} <= codes
    assert emit_findings(collage, report)["verdict"] == "fail"

    transfer_gap = json.loads(json.dumps(_base()))
    del transfer_gap["candidates"][0]["transfer"]["mismatch_risk"]
    assert "TRANSFER_RATIONALE_GAP" in {
        issue["code"] for issue in evaluate(transfer_gap, as_of="2026-07-05")["issues"]
    }

    measurement_gap = json.loads(json.dumps(_base()))
    m = measurement_gap["candidates"][0]
    m["originality_types"] = ["NEW_MEASUREMENT"]
    m["validation_plan"] = ""
    assert "VALIDATION_PLAN_GAP" in {
        issue["code"] for issue in evaluate(measurement_gap, as_of="2026-07-05")["issues"]
    }

    private_evidence = json.loads(json.dumps(_base()))
    private_evidence["evidence"][0]["locator"] = "D:\\private\\note.md"
    assert "EVIDENCE_LOCATOR_GAP" in {
        issue["code"] for issue in evaluate(private_evidence, as_of="2026-07-05")["issues"]
    }

    future = json.loads(json.dumps(_base()))
    future["evidence"][0]["checked_at"] = "2999-01-01"
    assert "EVIDENCE_DATE_FUTURE" in {
        issue["code"] for issue in evaluate(future, as_of="2026-07-05")["issues"]
    }
    print("innovation_engine selftest PASS: originality typing / anti-collage / claim-level / transfer / evidence guards")
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
