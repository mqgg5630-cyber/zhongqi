#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consistency_delta.py — 对比两次 consistency findings，防止“修了旧冲突又冒新冲突”。

consistency_audit.py 能告诉你当前材料有没有冲突；交付前还需要知道：

- 旧问题是否真的 FIXED；
- 新问题是否 NEW；
- 旧问题是否 PERSISTENT；
- 已登记解决过的问题是否 REGRESSED。

本脚本消费两份 `light.findings.v1`（producer=consistency）和可选 resolved ledger / owner decisions。
`--final` 模式下，NEW/PERSISTENT/REGRESSED 若没有 owner 决策（修复、延期、批准例外、降 claim），exit 1。
它不改任何材料，只产可审计 delta。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.consistency_delta.v1"
FINGERPRINT_VERSION = "gate-rule-loc.v2"


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def fingerprint(row: dict[str, Any]) -> str:
    # Finding prose is deliberately excluded: scanners may improve wording
    # between runs without changing the underlying gate/rule/location identity.
    payload = "|".join(_norm(row.get(key)) for key in ("gate", "rule", "loc"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def report_digest(report: dict[str, Any]) -> str:
    payload = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _issue(severity: str, code: str, loc: str, message: str, fix: str = "") -> dict[str, str]:
    row = {"severity": severity, "code": code, "loc": loc, "message": message}
    if fix:
        row["fix"] = fix
    return row


def extract(report: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    if report.get("schema") != "light.findings.v1":
        raise ValueError(f"{label}: schema 不是 light.findings.v1")
    if report.get("producer") not in (None, "consistency"):
        raise ValueError(f"{label}: producer 不是 consistency")
    out: dict[str, dict[str, Any]] = {}
    for gate in report.get("gates") or []:
        gate_name = str(gate.get("gate") or "unknown_gate")
        gate_status = str(gate.get("status") or "")
        gate_severity = str(gate.get("severity") or "")
        for finding in gate.get("findings") or []:
            row = {
                "gate": gate_name,
                "status": gate_status,
                "severity": gate_severity,
                "loc": str(finding.get("loc") or ""),
                "issue": str(finding.get("issue") or ""),
                "fix": str(finding.get("fix") or ""),
                "rule": str(finding.get("rule") or gate_name),
                "evidence": str(finding.get("evidence") or ""),
            }
            row["fingerprint"] = fingerprint(row)
            if row["fingerprint"] in out:
                previous = out[row["fingerprint"]]
                raise ValueError(
                    f"{label}: duplicate stable finding identity for "
                    f"{gate_name}/{row['rule']}/{row['loc']}; "
                    f"make loc specific enough to distinguish findings "
                    f"({previous['issue']!r} vs {row['issue']!r})"
                )
            out[row["fingerprint"]] = row
    return out


def _load_decisions(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    if not raw:
        return decisions
    rows = raw.get("decisions") if isinstance(raw, dict) else None
    if rows is None and isinstance(raw, dict):
        rows = raw.get("items")
    for row in rows or []:
        fp = str(row.get("fingerprint") or "")
        if fp:
            decisions[fp] = row
    return decisions


def _load_resolved(raw: dict[str, Any] | None) -> set[str]:
    if not raw:
        return set()
    rows = raw.get("resolved") if isinstance(raw, dict) else None
    if rows is None and isinstance(raw, dict):
        rows = raw.get("items")
    out = set()
    for row in rows or []:
        fp = row if isinstance(row, str) else row.get("fingerprint")
        if fp:
            out.add(str(fp))
    return out


def _decision_ok(decision: dict[str, Any] | None) -> bool:
    if not decision:
        return False
    required = ("owner", "decision", "rationale", "locator")
    return all(str(decision.get(field) or "").strip() for field in required)


def evaluate(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    decisions_raw: dict[str, Any] | None = None,
    resolved_raw: dict[str, Any] | None = None,
    final: bool = False,
) -> dict[str, Any]:
    before = extract(before_report, "before")
    after = extract(after_report, "after")
    decisions = _load_decisions(decisions_raw)
    resolved = _load_resolved(resolved_raw)

    fixed = sorted(set(before) - set(after))
    active = sorted(set(after))
    persistent = sorted(set(before) & set(after))
    after_only = sorted(set(after) - set(before))
    regressed = sorted(fp for fp in after_only if fp in resolved)
    new = sorted(fp for fp in after_only if fp not in resolved)

    items = []
    for state, fps in (
        ("FIXED", fixed),
        ("PERSISTENT", persistent),
        ("NEW", new),
        ("REGRESSED", regressed),
    ):
        for fp in fps:
            source = before.get(fp) if state == "FIXED" else after.get(fp)
            row = {
                "state": state,
                "fingerprint": fp,
                "gate": source.get("gate"),
                "severity": source.get("severity"),
                "loc": source.get("loc"),
                "issue": source.get("issue"),
                "rule": source.get("rule"),
                "decision": decisions.get(fp),
            }
            items.append(row)

    issues: list[dict[str, str]] = []
    for row in items:
        if row["state"] not in {"NEW", "PERSISTENT", "REGRESSED"}:
            continue
        if not _decision_ok(row.get("decision")):
            severity = "error" if final else "warn"
            issues.append(_issue(
                severity,
                f"{row['state']}_WITHOUT_OWNER_DECISION",
                str(row["loc"]),
                f"{row['state']} 一致性问题缺 owner 决策：{row['issue']}",
                "修复后重扫，或登记 owner/rationale/locator/decision；不得用零 finding 或口头说明冒充解决。",
            ))

    verdict = "FAIL" if any(x["severity"] == "error" for x in issues) else "WARN" if active or issues else "PASS"
    return {
        "schema": SCHEMA,
        "fingerprint_version": FINGERPRINT_VERSION,
        "inputs": {
            "before_sha256": report_digest(before_report),
            "after_sha256": report_digest(after_report),
        },
        "mode": "final" if final else "draft",
        "verdict": verdict,
        "counts": {
            "before": len(before),
            "after": len(after),
            "fixed": len(fixed),
            "new": len(new),
            "persistent": len(persistent),
            "regressed": len(regressed),
        },
        "items": items,
        "issues": issues,
        "honesty": (
            "本门只比较两次 consistency findings 的稳定指纹；它不证明未扫描材料一致，也不替用户裁定哪个事实为真。"
        ),
    }


def _report(findings: list[dict[str, Any]], verdict: str = "fail") -> dict[str, Any]:
    gates = {}
    for row in findings:
        gate = row.get("gate", "METRIC_VALUE")
        gates.setdefault(gate, []).append({
            "loc": row.get("loc", "paper.md:1"),
            "issue": row.get("issue", "F1 mismatch"),
            "fix": row.get("fix", "ask owner"),
            "rule": row.get("rule", gate),
        })
    return {
        "schema": "light.findings.v1",
        "producer": "consistency",
        "target": "demo",
        "verdict": verdict,
        "gates": [
            {"gate": gate, "status": "fail", "severity": "critical", "findings": rows}
            for gate, rows in gates.items()
        ],
    }


def _selftest() -> int:
    before = _report([
        {"gate": "METRIC_VALUE", "loc": "paper.md:10", "issue": "F1=81 与权威 87.6 不符", "rule": "METRIC_VALUE"},
        {"gate": "SUBSTITUTION", "loc": "slides.md:2", "issue": "DCANet 应为 DCA-Net", "rule": "SUBSTITUTION"},
    ])
    after = _report([
        {"gate": "SUBSTITUTION", "loc": "slides.md:2", "issue": "DCANet 应为 DCA-Net", "rule": "SUBSTITUTION"},
        {"gate": "CLAIM_STRENGTH_DRIFT", "loc": "abstract.md:3", "issue": "弱证据却写显著提升", "rule": "CLAIM_STRENGTH_DRIFT"},
        {"gate": "METRIC_VALUE", "loc": "ppt.md:8", "issue": "Accuracy=0.91 与权威 0.87 不符", "rule": "METRIC_VALUE"},
    ])
    after_rows = extract(after, "after")
    regressed_fp = next(
        fp for fp, row in after_rows.items()
        if row["loc"] == "ppt.md:8"
    )
    fail = evaluate(before, after, final=True, resolved_raw={"resolved": [regressed_fp]})
    assert fail["verdict"] == "FAIL"
    assert fail["counts"] == {
        "before": 2, "after": 3, "fixed": 1, "new": 1, "persistent": 1, "regressed": 1,
    }
    assert {item["state"] for item in fail["items"]} == {"FIXED", "PERSISTENT", "NEW", "REGRESSED"}
    decisions = {
        "decisions": [
            {"fingerprint": item["fingerprint"], "owner": "user", "decision": "fix before submission",
             "rationale": "hard conflict", "locator": "user-msg:1"}
            for item in fail["items"]
            if item["state"] in {"PERSISTENT", "NEW", "REGRESSED"}
        ]
    }
    warn = evaluate(before, after, decisions_raw=decisions, resolved_raw={"resolved": [regressed_fp]}, final=True)
    assert warn["verdict"] == "WARN"
    clean = evaluate(after, _report([], verdict="pass"), final=True)
    assert clean["verdict"] == "PASS"
    wording_before = _report([
        {"gate": "METRIC_VALUE", "loc": "paper.md:C1", "issue": "F1=81 mismatch",
         "rule": "METRIC_VALUE"},
    ])
    wording_after = _report([
        {"gate": "METRIC_VALUE", "loc": "paper.md:C1",
         "issue": "Metric F1 differs from the canonical value",
         "rule": "METRIC_VALUE"},
    ])
    wording_delta = evaluate(wording_before, wording_after)
    assert wording_delta["counts"]["persistent"] == 1
    assert wording_delta["counts"]["new"] == 0
    duplicate = _report([
        {"gate": "METRIC_VALUE", "loc": "paper.md:C1", "issue": "first",
         "rule": "METRIC_VALUE"},
        {"gate": "METRIC_VALUE", "loc": "paper.md:C1", "issue": "second",
         "rule": "METRIC_VALUE"},
    ])
    try:
        evaluate(duplicate, wording_after)
        raise AssertionError("duplicate stable finding identity must fail")
    except ValueError as exc:
        assert "duplicate stable finding identity" in str(exc)
    assert wording_delta["inputs"]["before_sha256"].startswith("sha256:")
    print("consistency_delta selftest PASS: stable wording-independent identity + "
          "input digests + duplicate guard + fixed/new/persistent/regressed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="对比两次 consistency findings 的 delta")
    parser.add_argument("--before", help="旧 light.findings.v1")
    parser.add_argument("--after", help="新 light.findings.v1")
    parser.add_argument("--decisions", help="owner decisions JSON，可选")
    parser.add_argument("--resolved-ledger", help="已解决 fingerprint ledger，可选；若 after 再出现则 REGRESSED")
    parser.add_argument("--final", action="store_true", help="NEW/PERSISTENT/REGRESSED 缺 owner 决策时 exit 1")
    parser.add_argument("--json-out", help="写出 delta report")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.before or not args.after:
        parser.error("需要 --before 与 --after，或 --selftest")
    report = evaluate(
        _read_json(pathlib.Path(args.before)),
        _read_json(pathlib.Path(args.after)),
        decisions_raw=_read_json(pathlib.Path(args.decisions)) if args.decisions else None,
        resolved_raw=_read_json(pathlib.Path(args.resolved_ledger)) if args.resolved_ledger else None,
        final=args.final,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
