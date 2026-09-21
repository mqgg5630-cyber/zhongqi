#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanically build and audit the 23-skill integration inventory."""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass
class InventoryRow:
    skill: str
    role_expected: str
    role_detected: str
    stage_expected: int | None
    stage_detected: int | None
    emits_findings_expected: bool
    emits_findings_detected: bool
    resource_maps: list[str]
    script_entries: list[str]
    selftests: list[str]
    decision_stop: str
    consumer: str


def repo_root(start: str | pathlib.Path | None = None) -> pathlib.Path:
    cur = pathlib.Path(start or __file__).resolve()
    if cur.is_file():
        cur = cur.parent
    while cur != cur.parent and not (cur / "skills").is_dir():
        cur = cur.parent
    if not (cur / "skills").is_dir():
        raise RuntimeError("Light-Skills repository root not found")
    return cur


def load_contract(root: pathlib.Path) -> dict[str, Any]:
    path = root / "skills/light-orchestrator/references/integration-contract.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def detect_stage(text: str) -> int | None:
    """Read stage ownership only from the declaration/opening contract."""
    fm = frontmatter(text)
    opening = "\n".join(text.splitlines()[:60])
    candidates = (
        re.search(r"(?mi)^\s{2}stage:\s*(\d{1,2})\b", fm),
        re.search(r"(?i)\bstage\s*[-:]?\s*(\d{1,2})\b", fm),
        re.search(r"(?i)\bstage\s*[-:]?\s*(\d{1,2})\b", opening),
        re.search(r"第\s*(\d{1,2})\s*(?:步|节点)", opening),
    )
    for hit in candidates:
        if hit and 1 <= int(hit.group(1)) <= 13:
            return int(hit.group(1))
    return None


def detect_role(skill: str, text: str, stage: int | None) -> str:
    if skill == "light-orchestrator":
        return "controller"
    if stage is not None:
        return "pipeline"
    low = text.lower()
    if (
        "engineering-off-dag" in low
        or "off-dag engineering" in low
        or ("off-dag" in low and ("engineering skill" in low or "按需工程" in text))
    ):
        return "engineering-off-dag"
    overlay = "overlay" in low or "常驻" in text
    emits_none = bool(
        re.search(r"(?mi)^\s*emits:\s*none\b", frontmatter(text))
    )
    no_findings = (
        emits_none
        or "do not emit findings" in low
        or "不产 findings" in low
    )
    if no_findings and (overlay or "off-dag local tool" in low):
        return "overlay-off-dag"
    if overlay:
        return "overlay"
    return "unknown"


def resource_maps(skill_dir: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        path for path in skill_dir.rglob("*.md")
        if "resource-map" in path.name.lower()
    )


def emits_findings(skill: str, skill_dir: pathlib.Path, skill_text: str,
                   scripts: list[str]) -> bool:
    if skill == "light-orchestrator":
        return False
    fm = frontmatter(skill_text)
    if re.search(r"(?mi)^\s*emits:\s*none\b", fm):
        return False
    if re.search(r"(?mi)^\s*emits:.*light\.findings\.v1", fm):
        return True
    script_text = "\n".join(
        (skill_dir / item).read_text(encoding="utf-8-sig", errors="replace")
        for item in scripts
    )
    return bool(re.search(
        r"\b(?:FindingsReport|GateResult)\b|_shared\.findings_schema",
        script_text,
    ))


def make_inventory(root: pathlib.Path,
                   contract: dict[str, Any]) -> list[InventoryRow]:
    rows: list[InventoryRow] = []
    for skill, expected in sorted(contract["skills"].items()):
        skill_dir = root / "skills" / skill
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            rows.append(InventoryRow(
                skill, expected["role"], "missing", expected["stage"], None,
                expected["emits_findings"], False, [], [], [],
                expected["decision_stop"], expected["consumer"],
            ))
            continue
        skill_text = skill_path.read_text(encoding="utf-8-sig")
        maps = resource_maps(skill_dir)
        scripts = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file() and path.suffix in {".py", ".R"}
        )
        selftests = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file() and path.suffix in {".py", ".R"}
            and "--selftest" in path.read_text(
                encoding="utf-8-sig", errors="replace"
            )
        )
        stage = detect_stage(skill_text)
        rows.append(InventoryRow(
            skill=skill,
            role_expected=expected["role"],
            role_detected=detect_role(skill, skill_text, stage),
            stage_expected=expected["stage"],
            stage_detected=stage,
            emits_findings_expected=expected["emits_findings"],
            emits_findings_detected=emits_findings(
                skill, skill_dir, skill_text, scripts
            ),
            resource_maps=[
                path.relative_to(root).as_posix() for path in maps
            ],
            script_entries=scripts,
            selftests=selftests,
            decision_stop=expected["decision_stop"],
            consumer=expected["consumer"],
        ))
    return rows


def import_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def live_wiring(root: pathlib.Path) -> tuple[dict[int, list[str]],
                                                list[dict[str, Any]]]:
    scripts = root / "skills/light-orchestrator/scripts"
    checkpoint = import_module(
        scripts / "run_checkpoint.py", "_light_checkpoint_audit"
    )
    reroute = import_module(scripts / "reroute.py", "_light_reroute_audit")
    gates = {int(key): list(value)
             for key, value in checkpoint.STAGE_GATES.items()}
    routes = [
        {
            "from": int(source),
            "to": int(rule.root_cause),
            "kind": getattr(rule, "kind", "back_edge"),
        }
        for source, rules in reroute.ROUTES.items()
        for rule in rules
    ]
    return gates, routes


def audit(root: pathlib.Path, contract: dict[str, Any],
          rows: list[InventoryRow]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if len(rows) != 23:
        errors.append(f"inventory must contain 23 skills, got {len(rows)}")

    stages = {row.stage_detected for row in rows
              if row.role_expected == "pipeline"}
    if stages != set(range(1, 14)):
        errors.append(f"pipeline stage set mismatch: {sorted(stages)}")

    for row in rows:
        if row.role_detected != row.role_expected:
            errors.append(
                f"{row.skill}: role expected={row.role_expected} "
                f"detected={row.role_detected}"
            )
        if row.stage_detected != row.stage_expected:
            errors.append(
                f"{row.skill}: stage expected={row.stage_expected} "
                f"detected={row.stage_detected}"
            )
        if row.emits_findings_detected != row.emits_findings_expected:
            errors.append(
                f"{row.skill}: emits_findings "
                f"expected={row.emits_findings_expected} "
                f"detected={row.emits_findings_detected}"
            )

    gates, routes = live_wiring(root)
    expected_gates = {
        int(key): value for key, value in contract["stage_gates"].items()
    }
    if gates != expected_gates:
        errors.append(f"STAGE_GATES mismatch: live={gates} "
                      f"expected={expected_gates}")

    def normalize(values):
        return sorted(
            values, key=lambda row: (row["from"], row["to"], row["kind"])
        )
    if normalize(routes) != normalize(contract["routes"]):
        errors.append(f"ROUTES mismatch: live={normalize(routes)} "
                      f"expected={normalize(contract['routes'])}")
    for route in routes:
        if route["kind"] == "back_edge" and route["to"] >= route["from"]:
            errors.append(f"illegal back-edge {route['from']}->{route['to']}")
        if route["kind"] == "admission_hold" and route["to"] <= route["from"]:
            errors.append(f"invalid admission hold: {route}")

    forbidden = {
        "light-frontend-design", "light-system-design",
        "light-patent-disclosure", "light-software-copyright",
        "light-project-structure", "light-file-reading",
    }
    skill_by_stage = {
        row.stage_expected: row.skill
        for row in rows if row.stage_expected is not None
    }
    wired = {skill_by_stage.get(stage) for stage in gates}
    if forbidden & wired:
        errors.append(
            f"off-DAG skills in STAGE_GATES: {sorted(forbidden & wired)}"
        )

    for row in rows:
        if row.role_expected not in {"engineering-off-dag", "overlay-off-dag"}:
            continue
        script_dir = root / "skills" / row.skill / "scripts"
        for path in script_dir.glob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            if re.search(
                r"FindingsReport|GateResult|_shared\.findings_schema|"
                r"_shared\.gate_runner",
                text,
            ):
                errors.append(
                    f"{row.skill} illegally attaches findings: {path.name}"
                )

    for row in rows:
        if row.emits_findings_expected and not row.consumer.strip():
            errors.append(f"{row.skill}: findings producer has no consumer")

    return {
        "schema": "light.integration-audit.v1",
        "verdict": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "skills": [asdict(row) for row in rows],
        "stage_gates": gates,
        "routes": routes,
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Light 23-skill integration inventory",
        "",
        f"- schema: `{report['schema']}`",
        f"- verdict: **{report['verdict']}**",
        f"- skills: {len(report['skills'])}",
        "",
        "| skill | role | stage | findings | consumer | decision stop | "
        "scripts | selftests |",
        "|---|---|---:|---|---|---|---:|---:|",
    ]
    for row in report["skills"]:
        stage = row["stage_detected"]
        lines.append(
            f"| {row['skill']} | {row['role_detected']} | "
            f"{stage if stage is not None else '—'} | "
            f"{'yes' if row['emits_findings_detected'] else 'no'} | "
            f"{row['consumer']} | {row['decision_stop']} | "
            f"{len(row['script_entries'])} | {len(row['selftests'])} |"
        )
    lines.extend(["", "## STAGE_GATES", ""])
    for stage, gates in sorted(
        report["stage_gates"].items(), key=lambda item: int(item[0])
    ):
        lines.append(f"- stage {stage}: `{', '.join(gates)}`")
    lines.extend(["", "## Routes", ""])
    for route in sorted(
        report["routes"], key=lambda row: (row["from"], row["to"])
    ):
        lines.append(
            f"- {route['from']}→{route['to']}: `{route['kind']}`"
        )
    lines.extend(["", "## Audit", ""])
    for error in report["errors"]:
        lines.append(f"- ERROR: {error}")
    for warning in report["warnings"]:
        lines.append(f"- WARN: {warning}")
    if not report["errors"] and not report["warnings"]:
        lines.append(
            "- PASS: role, stage, producer/consumer, gate and route wiring agree."
        )
    return "\n".join(lines) + "\n"


def selftest() -> int:
    root = repo_root()
    contract = load_contract(root)
    rows = make_inventory(root, contract)
    report = audit(root, contract, rows)
    checks = [
        (len(rows) == 23, "extract exactly 23 skills"),
        (
            {row.stage_detected for row in rows
             if row.role_expected == "pipeline"} == set(range(1, 14)),
            "extract stages 1-13",
        ),
        (
            not any(
                row.skill == "light-system-design"
                and row.emits_findings_detected for row in rows
            ),
            "system-design emits no findings",
        ),
        (
            all(
                row.stage_detected is None for row in rows
                if "off-dag" in row.role_expected
            ),
            "off-DAG roles have no stage",
        ),
        (report["verdict"] == "PASS", "live integration contract passes"),
    ]
    ok = True
    for passed, label in checks:
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] {label}")
    with tempfile.TemporaryDirectory(prefix="integration_audit_") as tmp:
        path = pathlib.Path(tmp) / "x.json"
        path.write_text(
            "\ufeff" + json.dumps({"schema": "x"}), encoding="utf-8"
        )
        passed = json.loads(
            path.read_text(encoding="utf-8-sig")
        )["schema"] == "x"
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] UTF-8 BOM input")
    if not ok:
        for item in report["errors"]:
            print("   ERROR", item)
        for item in report["warnings"]:
            print("   WARN", item)
    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="extract and audit the Light 23-skill integration inventory"
    )
    parser.add_argument("--root", help="Light-Skills repository root")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--markdown", action="store_true", help="emit Markdown")
    parser.add_argument("--out", help="write output to this path")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    root = repo_root(args.root)
    contract = load_contract(root)
    report = audit(root, contract, make_inventory(root, contract))
    content = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.json else markdown(report)
    )
    if args.out:
        pathlib.Path(args.out).write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
