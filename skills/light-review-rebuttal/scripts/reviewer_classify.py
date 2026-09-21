#!/usr/bin/env python3
"""Turn evidence-backed rejection-driving issues into stage-13 findings.

Only canonical issue rows with rejection_driving=true and a complete
rejection_evidence envelope may become critical. Classification labels,
overall Reject/Major decisions, or a model's severity guess alone never do.
The script emits suggestions; reroute and passport remain separate.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT_CAUSE = {
    "novelty": {"stage": 3, "skill": "idea-generation", "token": "novelty",
                "issue": "rejection-driving novelty root cause"},
    "experiment": {"stage": 5, "skill": "research-plan", "token": "experiment",
                   "issue": "rejection-driving experiment root cause"},
    "writing": {"stage": 8, "skill": "paper-writing", "token": "writing",
                "issue": "rejection-driving writing root cause"},
}
GATE = "reviewer_classify"
INPLACE_GATE = "addressable_in_rebuttal"

try:
    root = pathlib.Path(__file__).resolve()
    while root != root.parent and not (root / "_shared" / "__init__.py").is_file():
        root = root.parent
    if not (root / "_shared" / "__init__.py").is_file():
        raise ImportError("_shared not found")
    sys.path.insert(0, str(root))
    from _shared.findings_schema import Finding, FindingsReport, GateResult
except Exception as exc:  # pragma: no cover - exercised by CLI guard
    Finding = FindingsReport = GateResult = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def read_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _evidence_complete(issue: dict) -> bool:
    envelope = issue.get("rejection_evidence") or {}
    return bool(envelope.get("kind") and envelope.get("value") and envelope.get("locator"))


def build_report(matrix: dict) -> "FindingsReport":
    if matrix.get("schema") != "light.review_issue_matrix.v1":
        raise ValueError("expected light.review_issue_matrix.v1")
    issues = matrix.get("issues") or []
    target = f"review-issues@{matrix.get('venue') or 'unknown-venue'}"
    report = FindingsReport(
        producer="review-rebuttal", target=target, fresh_evidence=True,
        summary=f"stage-13 reviewer classification: {len(issues)} atomic issues",
    )
    critical = {key: [] for key in ROOT_CAUSE}
    addressable = []
    for issue in issues:
        root = str(issue.get("root_cause") or "").lower()
        eligible = (
            root in ROOT_CAUSE
            and issue.get("rejection_driving") is True
            and _evidence_complete(issue)
        )
        if eligible:
            critical[root].append(issue)
        else:
            addressable.append(issue)
    for root, rows in critical.items():
        if not rows:
            continue
        meta = ROOT_CAUSE[root]
        findings = []
        for row in rows:
            rejection = row["rejection_evidence"]
            evidence = json.dumps({
                "reviewer_raw_span": row.get("raw_span"),
                "rejection_evidence": rejection,
            }, ensure_ascii=False)
            findings.append(Finding(
                loc=str(row.get("issue_id") or "?"),
                issue=f"{meta['issue']} ({row.get('issue_id')})",
                fix=(
                    f"decision point: consider 13→{meta['stage']} ({meta['skill']}); "
                    "or rebut with evidence, downgrade the claim, request editor ruling, "
                    "or record a limitation. User must choose."
                ),
                evidence=evidence,
                rule=meta["token"],
            ))
        report.gates.append(GateResult(
            GATE, "fail", "critical", findings,
            note=(
                f"suggest 13→{meta['stage']}; rejection evidence is preserved in finding "
                "evidence; no passport mutation is performed"
            ),
        ))
    if addressable:
        findings = []
        for row in addressable:
            reason = (
                "not explicitly rejection-driving"
                if not row.get("rejection_driving")
                else "missing complete rejection_evidence or non-routable root cause"
            )
            findings.append(Finding(
                loc=str(row.get("issue_id") or "?"),
                issue=f"address in response/revision: {reason}",
                fix="follow the issue strategy and preserve planned/done truth",
                evidence=str(row.get("raw_span") or ""),
                rule="addressable",
            ))
        report.gates.append(GateResult(
            INPLACE_GATE, "warn", "minor", findings,
            note="non-blocking; labels or overall decision alone do not create critical",
        ))
    if not report.gates:
        report.gates.append(GateResult(
            GATE, "pass", "info", note="no atomic issues supplied"
        ))
    return report.finalize()


def render(report: "FindingsReport") -> str:
    blocking = [gate for gate in report.gates if gate.is_blocking()]
    lines = [
        "# Stage-13 reviewer classification",
        "",
        f"- verdict: **{report.compute_verdict()}**",
        f"- critical root-cause buckets: {len(blocking)}",
    ]
    for gate in blocking:
        token = gate.findings[0].rule
        meta = ROOT_CAUSE[token]
        lines.append(
            f"- suggestion: **13→{meta['stage']} {meta['skill']}** "
            f"({len(gate.findings)} issue(s), token `{token}`)"
        )
    if blocking:
        lines.extend([
            "",
            "> Stop here. Present the evidence and alternatives to the user. "
            "Run reroute for advice only; run add-back-edge only after the user's choice.",
        ])
    return "\n".join(lines)


def _matrix(issues: list[dict]) -> dict:
    return {
        "schema": "light.review_issue_matrix.v1",
        "venue": "Journal of Open Research Software",
        "issues": issues,
    }


def _selftest() -> int:
    assert _IMPORT_ERROR is None, _IMPORT_ERROR
    report = build_report(_matrix([
        {
            "issue_id": "N1", "root_cause": "novelty", "raw_span": "Novelty is unclear.",
            "severity": "major", "rejection_driving": False,
        },
        {
            "issue_id": "E1", "root_cause": "experiment", "raw_span": "Ablation is required.",
            "severity": "major", "rejection_driving": True,
            "rejection_evidence": {
                "kind": "meta_review", "value": "Major revision depends on the ablation",
                "locator": "meta-review:L4",
            },
        },
        {
            "issue_id": "W1", "root_cause": "writing", "raw_span": "Section 3 is unclear.",
            "severity": "major", "rejection_driving": False,
        },
    ]))
    blocking = [gate for gate in report.gates if gate.is_blocking()]
    assert report.compute_verdict() == "fail"
    assert len(blocking) == 1
    assert blocking[0].findings[0].rule == "experiment"
    assert "Ablation is required." in blocking[0].findings[0].evidence
    no_evidence = build_report(_matrix([{
        "issue_id": "N2", "root_cause": "novelty", "raw_span": "Not novel.",
        "severity": "major", "rejection_driving": True,
        "rejection_evidence": {"kind": "decision", "value": "Reject"},
    }]))
    assert no_evidence.compute_verdict() != "fail"
    rendered = render(report)
    assert "13→5" in rendered and "Stop here" in rendered
    payload = json.loads(report.to_json())
    assert payload["producer"] == "review-rebuttal"
    print("[selftest] PASS reviewer_classify: only evidenced rejection driver is critical")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="stage-13 rejection-root classifier")
    parser.add_argument("--issues")
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if _IMPORT_ERROR is not None:
        print(f"[reviewer_classify] _shared unavailable: {_IMPORT_ERROR}", file=sys.stderr)
        return 2
    if not args.issues:
        parser.error("--issues is required")
    try:
        report = build_report(read_json(pathlib.Path(args.issues)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[reviewer_classify] ERROR: {exc}", file=sys.stderr)
        return 2
    if args.out:
        pathlib.Path(args.out).write_text(report.to_json() + "\n", encoding="utf-8")
    print(report.to_json() if args.json else render(report))
    return 1 if report.compute_verdict() == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
