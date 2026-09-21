#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate evidence-rooted idea genealogy, mechanism diversity, and cheap tests."""
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

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
from _shared.findings_schema import Finding, GateResult  # noqa: E402
from _shared.gate_runner import run_gates  # noqa: E402

SCHEMA_ID = "light.idea_genealogy.v1"
ENTRY_POINTS = {
    "DESIRED_OUTCOME", "MECHANISM_SEED", "OBSERVED_ANOMALY",
    "LITERATURE_GAP", "CONSTRAINT_CHANGE",
}
EVIDENCE_KINDS = {"USER_SEED", "LITERATURE", "OBSERVATION", "CONSTRAINT"}
EVIDENCE_STATES = {"VERIFIED", "USER_STATED", "UNKNOWN", "UNAVAILABLE"}
RESOURCE_STATES = {"AVAILABLE", "UNKNOWN", "UNAVAILABLE"}
OPPORTUNITY_PATTERNS = {
    "BRIDGE", "SYNTHESIS", "REPLACEMENT", "DECOUPLING", "COUNTEREXAMPLE",
    "MEASUREMENT", "FORMALIZATION", "TOOL_BUILDING", "NEGATIVE_RESULT",
    "MECHANISM_TEST", "OTHER_DECLARED",
}
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|<[^>]+>|replace[-_ ]?with|todo|tbd)", re.IGNORECASE)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and not _is_placeholder(text) and text not in {
        "unknown", "pending", "n/a", "gap",
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


def _locator_ok(value: Any) -> bool:
    if not _real(value):
        return False
    text = str(value).strip().casefold()
    return not (text.startswith("file:") or _local_or_escaping(value))


def _sha(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


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


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    if spec.get("entry_point") not in ENTRY_POINTS:
        raise ValueError("entry_point 非法")
    today = _as_of_date(as_of if as_of is not None else spec.get("as_of"))
    evidence_raw = spec.get("source_evidence")
    candidates_raw = spec.get("candidates")
    if not isinstance(evidence_raw, list) or not isinstance(candidates_raw, list):
        raise ValueError("source_evidence/candidates 必须是 list")

    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    if not _real(spec.get("direction")):
        add("DIRECTION_GAP", "genealogy", "缺具体研究方向/目标")

    evidence: dict[str, dict[str, Any]] = {}
    for row in evidence_raw:
        if not isinstance(row, dict):
            raise ValueError("source_evidence row 必须是 object")
        evidence_id = str(row.get("evidence_id") or "")
        if (
            not evidence_id or evidence_id in evidence
            or row.get("kind") not in EVIDENCE_KINDS
            or row.get("status") not in EVIDENCE_STATES
        ):
            raise ValueError("evidence_id 重复/缺失，或 kind/status 非法")
        evidence[evidence_id] = row
        if not _locator_ok(row.get("locator")):
            add(
                "EVIDENCE_LOCATOR_GAP",
                f"evidence:{evidence_id}",
                "证据缺可公开交接 locator，或 locator 是模板/本机绝对路径/UNC/root/../逃逸/file URL",
            )
        if row["status"] == "VERIFIED" and not _sha(row.get("sha256")):
            add("VERIFIED_EVIDENCE_HASH_GAP", f"evidence:{evidence_id}", "VERIFIED 证据缺 SHA-256")
        if row["status"] == "VERIFIED":
            if _parse_iso_date(row.get("checked_at")) is None:
                add("VERIFIED_EVIDENCE_DATE_GAP", f"evidence:{evidence_id}", "VERIFIED 证据缺 checked_at")
            elif not _not_future(row.get("checked_at"), today):
                add(
                    "VERIFIED_EVIDENCE_FUTURE",
                    f"evidence:{evidence_id}",
                    f"checked_at 晚于 as_of={today.isoformat()}",
                )

    candidates: dict[str, dict[str, Any]] = {}
    adjacency: dict[str, set[str]] = {}
    eligible_ids: list[str] = []
    for row in candidates_raw:
        if not isinstance(row, dict):
            raise ValueError("candidate row 必须是 object")
        idea_id = str(row.get("idea_id") or "")
        if not idea_id or idea_id in candidates:
            raise ValueError("idea_id 重复或缺失")
        candidates[idea_id] = row
        adjacency[idea_id] = set()
        for field in (
            "title", "problem", "mechanism", "mechanism_family", "mechanism_delta",
            "assumption_delta", "research_paradigm", "evidence_type", "risk_profile",
        ):
            if not _real(row.get(field)):
                add("IDEA_FIELD_GAP", f"idea:{idea_id}", f"缺 {field}")
        if row.get("opportunity_pattern") not in OPPORTUNITY_PATTERNS:
            add("OPPORTUNITY_PATTERN_GAP", f"idea:{idea_id}", "opportunity_pattern 缺失或非法")
        elif row.get("opportunity_pattern") == "OTHER_DECLARED" and not _real(
            row.get("opportunity_pattern_detail")
        ):
            add("OPPORTUNITY_PATTERN_GAP", f"idea:{idea_id}", "OTHER_DECLARED 缺 detail")

        parent_evidence_ids = row.get("parent_evidence_ids")
        parent_ids = row.get("parent_ids")
        if not isinstance(parent_evidence_ids, list) or not isinstance(parent_ids, list):
            raise ValueError("parent_evidence_ids/parent_ids 必须是 list")
        if not parent_evidence_ids and not parent_ids:
            add("GENEALOGY_ROOT_GAP", f"idea:{idea_id}", "候选没有证据根或父候选")
        for evidence_id in parent_evidence_ids:
            if evidence_id not in evidence:
                add("UNKNOWN_PARENT_EVIDENCE", f"idea:{idea_id}", f"未知 evidence {evidence_id}")
            elif evidence[evidence_id]["status"] in {"UNKNOWN", "UNAVAILABLE"}:
                add(
                    "PARENT_EVIDENCE_UNRESOLVED", f"idea:{idea_id}",
                    f"父证据 {evidence_id} 为 {evidence[evidence_id]['status']}", "unresolved",
                )

        information_gain = row.get("information_gain") or {}
        for field in (
            "uncertainty", "observation", "decision_if_positive", "decision_if_negative"
        ):
            if not _real(information_gain.get(field)):
                add("INFORMATION_GAIN_GAP", f"idea:{idea_id}", f"information_gain 缺 {field}")
        test = row.get("discriminating_test") or {}
        for field in (
            "test", "alternative", "positive_observation", "negative_observation",
            "cost", "required_access", "kill_criterion",
        ):
            if not _real(test.get(field)):
                add("DISCRIMINATING_TEST_GAP", f"idea:{idea_id}", f"最小判别实验缺 {field}")

        resources = row.get("resources")
        if not isinstance(resources, list) or not resources:
            add("RESOURCE_LEDGER_GAP", f"idea:{idea_id}", "缺资源账")
            resources = []
        resource_unresolved = False
        for resource in resources:
            if (
                not isinstance(resource, dict)
                or not _real(resource.get("resource"))
                or resource.get("status") not in RESOURCE_STATES
                or not _real(resource.get("evidence"))
            ):
                add("RESOURCE_ROW_GAP", f"idea:{idea_id}", "资源条目缺 name/status/evidence")
                continue
            if resource["status"] != "AVAILABLE":
                resource_unresolved = True
            else:
                if not _locator_ok(resource.get("evidence_locator")):
                    add(
                        "RESOURCE_EVIDENCE_LOCATOR_GAP",
                        f"idea:{idea_id}",
                        "AVAILABLE 资源必须给可公开交接 evidence_locator；不能只写 prose evidence",
                    )
                if _parse_iso_date(resource.get("checked_at")) is None:
                    add("RESOURCE_CHECKED_AT_GAP", f"idea:{idea_id}", "AVAILABLE 资源缺 checked_at")
                elif not _not_future(resource.get("checked_at"), today):
                    add(
                        "RESOURCE_CHECKED_AT_FUTURE",
                        f"idea:{idea_id}",
                        f"资源 checked_at 晚于 as_of={today.isoformat()}",
                    )
        if row.get("eligible_to_expand") is True:
            eligible_ids.append(idea_id)
            if resource_unresolved:
                add(
                    "ELIGIBLE_WITH_RESOURCE_GAP", f"idea:{idea_id}",
                    "资源仍 UNKNOWN/UNAVAILABLE，不得标 eligible_to_expand",
                )

    for idea_id, row in candidates.items():
        for parent_id in row["parent_ids"]:
            if parent_id not in candidates:
                add("UNKNOWN_PARENT_IDEA", f"idea:{idea_id}", f"未知 parent idea {parent_id}")
            else:
                adjacency[parent_id].add(idea_id)

    colors = {idea_id: 0 for idea_id in candidates}

    def visit(idea_id: str) -> bool:
        colors[idea_id] = 1
        for child in adjacency[idea_id]:
            if colors[child] == 1 or (colors[child] == 0 and visit(child)):
                return True
        colors[idea_id] = 2
        return False

    if any(colors[idea_id] == 0 and visit(idea_id) for idea_id in candidates):
        add("GENEALOGY_CYCLE", "genealogy", "idea genealogy 含循环")
    if not eligible_ids:
        add("NO_ELIGIBLE_IDEA", "candidates", "没有可送 idea-critique 的候选")

    requirements = spec.get("diversity_requirements")
    if not isinstance(requirements, dict):
        raise ValueError("diversity_requirements 必须是 object")
    eligible = [candidates[idea_id] for idea_id in eligible_ids]
    dimensions = {
        "mechanism_families": {str(row.get("mechanism_family")) for row in eligible},
        "opportunity_patterns": {str(row.get("opportunity_pattern")) for row in eligible},
        "research_paradigms": {str(row.get("research_paradigm")) for row in eligible},
    }
    for key, actual in dimensions.items():
        requirement_key = f"min_{key}"
        minimum = requirements.get(requirement_key)
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            add("DIVERSITY_REQUIREMENT_GAP", "diversity_requirements", f"{requirement_key} 非正整数")
        elif len(actual) < minimum:
            add(
                "MECHANISM_DIVERSITY_GAP", "eligible_candidates",
                f"{key} 实际 {len(actual)} < 声明最低 {minimum}",
            )
    max_bridge = requirements.get("max_bridge_fraction")
    if not isinstance(max_bridge, (int, float)) or isinstance(max_bridge, bool) or not 0 <= max_bridge <= 1:
        add("DIVERSITY_REQUIREMENT_GAP", "diversity_requirements", "max_bridge_fraction 须在 0..1")
    elif eligible:
        bridge_count = sum(
            row.get("opportunity_pattern") in {"BRIDGE", "SYNTHESIS"} for row in eligible
        )
        if bridge_count / len(eligible) > max_bridge:
            add(
                "ANTI_BRIDGE_COLLAPSE", "eligible_candidates",
                f"bridge/synthesis 占比 {bridge_count / len(eligible):.2f} 超过声明上限 {max_bridge:.2f}",
            )

    status = (
        "FAIL" if any(issue["severity"] == "error" for issue in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.idea_genealogy_report.v1",
        "status": status,
        "eligible_ids": eligible_ids,
        "diversity": {key: sorted(value) for key, value in dimensions.items()},
        "as_of": today.isoformat(),
        "issues": issues,
        "honesty": (
            "PASS 只证明谱系、机制覆盖、资源声明与最小判别实验字段闭合；"
            "不证明 idea 新颖、重要、可行或实验能产生预期信息。候选数量不是质量证明。"
        ),
    }


def emit_findings(spec: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    def genealogy_gate(_: dict[str, Any]) -> GateResult:
        if report["status"] == "PASS":
            return GateResult(
                "idea_genealogy", "pass", "info", [],
                note="证据根、机制覆盖、资源与最小判别实验字段闭合。",
            )
        findings = [
            Finding(
                issue["loc"], issue["message"],
                "补齐谱系证据、机制差异、资源或最小判别实验后再送 idea-critique。",
                rule=issue["code"],
            )
            for issue in report["issues"]
        ]
        return GateResult(
            "idea_genealogy", "fail", "critical", findings,
            note=f"genealogy status={report['status']}；未闭合候选不得推进。",
        )

    return run_gates(
        [genealogy_gate], report, producer="idea-generation",
        target=str(spec.get("direction") or "idea-candidates"),
        summary="idea genealogy、机制多样性与最小判别实验门。",
        fresh_evidence=True,
    ).to_dict()


def _base() -> dict[str, Any]:
    h = "sha256:" + "a" * 64
    patterns = ("REPLACEMENT", "COUNTEREXAMPLE", "MEASUREMENT")
    candidates = []
    for index, pattern in enumerate(patterns, 1):
        candidates.append({
            "idea_id": f"I{index}", "title": f"candidate {index}",
            "parent_ids": [], "parent_evidence_ids": ["E1"],
            "problem": "declared problem", "mechanism": f"mechanism {index}",
            "mechanism_family": f"family-{index}", "mechanism_delta": "explicit delta",
            "assumption_delta": "explicit changed assumption",
            "opportunity_pattern": pattern, "research_paradigm": f"paradigm-{index}",
            "evidence_type": "controlled observation", "risk_profile": "declared medium",
            "information_gain": {
                "uncertainty": "which mechanism explains outcome",
                "observation": "measured contrast",
                "decision_if_positive": "advance mechanism",
                "decision_if_negative": "kill or revise mechanism",
            },
            "discriminating_test": {
                "test": "small controlled test", "alternative": "baseline explanation",
                "positive_observation": "effect exceeds declared threshold",
                "negative_observation": "effect stays below threshold",
                "cost": "one local run", "required_access": "public data",
                "kill_criterion": "negative observation",
            },
            "resources": [
                {
                    "resource": "data", "status": "AVAILABLE", "evidence": "public fixture",
                    "evidence_locator": "resource:data-card", "checked_at": "2026-07-05",
                },
                {
                    "resource": "compute", "status": "AVAILABLE", "evidence": "local CPU",
                    "evidence_locator": "resource:local-cpu", "checked_at": "2026-07-05",
                },
            ],
            "eligible_to_expand": True,
        })
    return {
        "schema": SCHEMA_ID, "direction": "generic direction", "as_of": "2026-07-05",
        "entry_point": "DESIRED_OUTCOME",
        "source_evidence": [{
            "evidence_id": "E1", "kind": "LITERATURE", "status": "VERIFIED",
            "locator": "source:1", "checked_at": "2026-07-05", "sha256": h,
        }],
        "candidates": candidates,
        "diversity_requirements": {
            "min_mechanism_families": 3, "min_opportunity_patterns": 3,
            "min_research_paradigms": 3, "max_bridge_fraction": 0.5,
        },
    }


def _selftest() -> int:
    clean = evaluate(_base(), as_of="2026-07-05")
    assert clean["status"] == "PASS"
    assert emit_findings(_base(), clean)["verdict"] == "pass"
    same = json.loads(json.dumps(_base()))
    for row in same["candidates"]:
        row["mechanism_family"] = "same"
        row["opportunity_pattern"] = "BRIDGE"
        row["research_paradigm"] = "same"
    codes = {issue["code"] for issue in evaluate(same, as_of="2026-07-05")["issues"]}
    assert {"MECHANISM_DIVERSITY_GAP", "ANTI_BRIDGE_COLLAPSE"} <= codes
    fifteen = json.loads(json.dumps(_base()))
    seed = fifteen["candidates"][0]
    fifteen["candidates"] = []
    for index in range(15):
        clone = json.loads(json.dumps(seed))
        clone["idea_id"] = f"C{index:02d}"
        clone["opportunity_pattern"] = "BRIDGE"
        clone["mechanism_family"] = "same-family"
        clone["research_paradigm"] = "same-paradigm"
        fifteen["candidates"].append(clone)
    fifteen_report = evaluate(fifteen, as_of="2026-07-05")
    assert fifteen_report["status"] == "FAIL"
    assert emit_findings(fifteen, fifteen_report)["verdict"] == "fail"
    unavailable = json.loads(json.dumps(_base()))
    unavailable["candidates"][0]["resources"][0]["status"] = "UNAVAILABLE"
    assert "ELIGIBLE_WITH_RESOURCE_GAP" in {
        issue["code"] for issue in evaluate(unavailable, as_of="2026-07-05")["issues"]
    }
    missing_resource_locator = json.loads(json.dumps(_base()))
    del missing_resource_locator["candidates"][0]["resources"][0]["evidence_locator"]
    assert "RESOURCE_EVIDENCE_LOCATOR_GAP" in {
        issue["code"] for issue in evaluate(missing_resource_locator, as_of="2026-07-05")["issues"]
    }
    future_resource = json.loads(json.dumps(_base()))
    future_resource["candidates"][0]["resources"][0]["checked_at"] = "2999-01-01"
    assert "RESOURCE_CHECKED_AT_FUTURE" in {
        issue["code"] for issue in evaluate(future_resource, as_of="2026-07-05")["issues"]
    }
    private_evidence = json.loads(json.dumps(_base()))
    private_evidence["source_evidence"][0]["locator"] = "D:\\private\\unpublished-note.md"
    assert "EVIDENCE_LOCATOR_GAP" in {
        issue["code"] for issue in evaluate(private_evidence, as_of="2026-07-05")["issues"]
    }
    future_evidence = json.loads(json.dumps(_base()))
    future_evidence["source_evidence"][0]["checked_at"] = "2999-01-01"
    assert "VERIFIED_EVIDENCE_FUTURE" in {
        issue["code"] for issue in evaluate(future_evidence, as_of="2026-07-05")["issues"]
    }
    cycle = json.loads(json.dumps(_base()))
    cycle["candidates"][0]["parent_ids"] = ["I3"]
    cycle["candidates"][2]["parent_ids"] = ["I1"]
    assert "GENEALOGY_CYCLE" in {
        issue["code"] for issue in evaluate(cycle, as_of="2026-07-05")["issues"]
    }
    print("idea_genealogy selftest PASS: roots/diversity/anti-bridge/resources/evidence-locator/dates/cycle")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--report", help="写 light.findings.v1")
    parser.add_argument("--as-of", help="ISO date/datetime; defaults to today and blocks future evidence/resource dates")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
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
