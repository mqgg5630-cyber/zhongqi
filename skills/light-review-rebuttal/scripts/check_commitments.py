#!/usr/bin/env python3
"""Validate the canonical commitment ledger against issue and change maps."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile

LEDGER_SCHEMA = "light.commitment_ledger.v1"
ISSUE_SCHEMA = "light.review_issue_matrix.v1"
CHANGE_SCHEMA = "light.evidence_change_map.v1"
STATES = {"PLANNED", "IN_PROGRESS", "DONE", "DECLINED", "NOT_APPLICABLE"}
DONE_WORDS = re.compile(
    r"\bwe (?:have )?(?:added|revised|conducted|changed|updated|corrected)\b|"
    r"已(?:新增|添加|修改|完成|补充|运行|修订)", re.I,
)
FUTURE_WORDS = re.compile(r"\b(?:will|plan(?:ned)? to|todo|to be done)\b|将|计划|拟|待补|尚未", re.I)


def read_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(ledger: dict, issues: dict, changes: dict) -> dict:
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError(f"ledger must be {LEDGER_SCHEMA}")
    if issues.get("schema") != ISSUE_SCHEMA:
        raise ValueError(f"issues must be {ISSUE_SCHEMA}")
    if changes.get("schema") != CHANGE_SCHEMA:
        raise ValueError(f"change map must be {CHANGE_SCHEMA}")
    issue_ids = {str(row.get("issue_id")) for row in issues.get("issues") or []}
    change_by_issue = {
        str(row.get("issue_id")): row for row in changes.get("items") or []
        if row.get("issue_id")
    }
    covered: set[str] = set()
    findings = []
    for item in ledger.get("items") or []:
        commitment_id = str(item.get("commitment_id") or "?")
        item_issues = {str(value) for value in item.get("issue_ids") or []}
        covered.update(item_issues)
        unknown = sorted(item_issues - issue_ids)
        if unknown:
            findings.append({
                "code": "UNKNOWN_ISSUE_REFERENCE", "severity": "critical",
                "commitment_id": commitment_id, "detail": unknown,
            })
        status = str(item.get("status") or "").upper()
        if status not in STATES:
            findings.append({
                "code": "INVALID_STATUS", "severity": "critical",
                "commitment_id": commitment_id, "detail": status,
            })
            continue
        response = str(item.get("response_text") or "")
        if status in {"PLANNED", "IN_PROGRESS"} and DONE_WORDS.search(response):
            findings.append({
                "code": "PLANNED_AS_DONE", "severity": "critical",
                "commitment_id": commitment_id,
                "detail": "planned/in-progress action is written as completed",
            })
        if status == "DONE":
            if not item.get("change_locator"):
                findings.append({
                    "code": "DONE_NO_LOCATOR", "severity": "critical",
                    "commitment_id": commitment_id,
                    "detail": "DONE requires a concrete change locator",
                })
            if FUTURE_WORDS.search(response):
                findings.append({
                    "code": "DONE_CONTAINS_FUTURE", "severity": "critical",
                    "commitment_id": commitment_id,
                    "detail": "DONE response still uses future/planned language",
                })
            for issue_id in item_issues:
                change = change_by_issue.get(issue_id)
                if not change or change.get("status") != "DONE":
                    findings.append({
                        "code": "LEDGER_CHANGE_MAP_DRIFT", "severity": "critical",
                        "commitment_id": commitment_id, "detail": issue_id,
                    })
            if item.get("action_kind") in {"experiment", "analysis"}:
                run = item.get("run_provenance") or {}
                path_value = run.get("path")
                path = pathlib.Path(path_value) if path_value else None
                valid = bool(path and path.is_file())
                if valid and run.get("sha256"):
                    valid = sha256(path) == run.get("sha256")
                if not valid:
                    findings.append({
                        "code": "DONE_SCIENTIFIC_ACTION_NO_PROVENANCE",
                        "severity": "critical", "commitment_id": commitment_id,
                        "detail": path_value,
                    })
        if status == "DECLINED" and not item.get("rationale"):
            findings.append({
                "code": "DECLINED_NO_RATIONALE", "severity": "major",
                "commitment_id": commitment_id,
                "detail": "declined action needs evidence/scope rationale",
            })
    missing = sorted(issue_ids - covered)
    for issue_id in missing:
        findings.append({
            "code": "MISSING_ISSUE_COVERAGE", "severity": "critical",
            "commitment_id": None, "detail": issue_id,
        })
    critical = sum(1 for item in findings if item["severity"] == "critical")
    return {
        "schema": "light.commitment_check.v2",
        "verdict": "FAIL" if critical else ("WARN" if findings else "PASS"),
        "counts": {"issues": len(issue_ids), "commitments": len(ledger.get("items") or []),
                   "findings": len(findings), "critical": critical},
        "findings": findings,
        "boundary": (
            "This verifies coverage, state truth, locators, map consistency, and run "
            "provenance. It does not judge whether a scientific change is adequate."
        ),
    }


def _selftest() -> int:
    with tempfile.TemporaryDirectory():
        issues = {
            "schema": ISSUE_SCHEMA,
            "issues": [{"issue_id": "R1"}, {"issue_id": "R2"}],
        }
        changes = {
            "schema": CHANGE_SCHEMA,
            "items": [
                {"issue_id": "R1", "status": "PLANNED"},
                {"issue_id": "R2", "status": "DONE", "change_locator": "paper.md#sec-3"},
            ],
        }
        bad = {
            "schema": LEDGER_SCHEMA,
            "items": [{
                "commitment_id": "C1", "issue_ids": ["R1"], "status": "PLANNED",
                "response_text": "We have added the experiment.", "action_kind": "experiment",
            }],
        }
        report = check(bad, issues, changes)
        codes = {item["code"] for item in report["findings"]}
        assert report["verdict"] == "FAIL"
        assert {"PLANNED_AS_DONE", "MISSING_ISSUE_COVERAGE"} <= codes
        clean = {
            "schema": LEDGER_SCHEMA,
            "items": [
                {
                    "commitment_id": "C1", "issue_ids": ["R1"], "status": "PLANNED",
                    "response_text": "The experiment remains planned.",
                    "action_kind": "experiment",
                },
                {
                    "commitment_id": "C2", "issue_ids": ["R2"], "status": "DONE",
                    "response_text": "We have revised Section 3.",
                    "change_locator": "paper.md#sec-3", "action_kind": "prose",
                },
            ],
        }
        assert check(clean, issues, changes)["verdict"] == "PASS"
    print("[selftest] PASS check_commitments: coverage + planned/done + locator + map")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="canonical commitment-ledger gate")
    parser.add_argument("--ledger")
    parser.add_argument("--issues")
    parser.add_argument("--change-map")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.ledger or not args.issues or not args.change_map:
        parser.error("--ledger, --issues, and --change-map are required")
    try:
        report = check(
            read_json(pathlib.Path(args.ledger)),
            read_json(pathlib.Path(args.issues)),
            read_json(pathlib.Path(args.change_map)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[check_commitments] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
