#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Classify intake, produce hash-bound handoffs, and verify recovery freshness.

Usage:
  python lifecycle.py intake --root <project>
  python lifecycle.py handoff --root <project> --out .light/orchestrator-handoff.json
  python lifecycle.py verify-handoff --root <project> --handoff <file>
  python lifecycle.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import passport  # noqa: E402

SCHEMA_HANDOFF = "light.orchestrator.handoff.v1"
INTAKE_STATES = {"new", "resume", "partial", "dirty", "failed", "stale", "delivered"}
MAX_HANDOFF_CLOCK_SKEW = dt.timedelta(minutes=5)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def passport_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".light" / "passport.yaml"


def git_dirty(root: pathlib.Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return False, "not-a-git-worktree"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return bool(lines), f"{len(lines)} dirty path(s)"


def _stage_map(data: dict) -> dict[int, dict]:
    return {
        st["stage"]: st for st in data.get("stages") or []
        if isinstance(st, dict) and isinstance(st.get("stage"), int)
    }


def classify(root: str | pathlib.Path) -> dict:
    project_root = pathlib.Path(root).resolve()
    path = passport_path(project_root)
    dirty, dirty_note = git_dirty(project_root)
    flags: list[str] = ["dirty"] if dirty else []
    if not path.is_file():
        primary = "dirty" if dirty else "new"
        return {
            "schema": "light.orchestrator.intake.v1",
            "state": primary,
            "flags": flags + ["new"],
            "passport": str(path),
            "passport_state_hash": None,
            "next_action": (
                "preserve user changes, then propose passport initialization"
                if dirty else "propose a cropped pipeline and initialize passport after scope confirmation"),
            "blockers": [dirty_note] if dirty else [],
            "need_reverify": [],
            "known_limitations": [],
        }

    try:
        data = passport.load(str(path))
        validation = passport.validate(data)
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": "light.orchestrator.intake.v1",
            "state": "failed",
            "flags": flags + ["failed"],
            "passport": str(path),
            "passport_state_hash": None,
            "next_action": "repair or explicitly migrate the passport before any stage action",
            "blockers": [f"passport parse failure: {exc}"],
            "need_reverify": [],
            "known_limitations": [],
        }

    stages = _stage_map(data)
    statuses = {number: passport.effective_status(st) for number, st in stages.items()}
    failed = validation["verdict"] == "FAIL" or any(
        status == "gate_failed" or stages[number].get("evidence_state") == "FAILED"
        for number, status in statuses.items())
    if failed:
        flags.append("failed")
    stale = passport.stale_check(data, str(project_root))
    # "incomplete" is a normal new/partial/resume state. Only changed upstream
    # content is stale propagation; do not misclassify an unstarted stage.
    need_reverify = [
        row["stage"] for row in stale["stages"] if row["state"] == "stale"
    ]
    if need_reverify:
        flags.append("stale")
    delivered = (
        bool(stages)
        and all(status == "delivered" for status in statuses.values())
        and data.get("delivery_status") == "DELIVERED"
        and bool(data.get("delivery_authorization_id"))
    )
    if delivered:
        flags.append("delivered")
    active = [
        number for number, status in statuses.items()
        if status in {"in_progress", "needs_rework"}
    ]
    if active:
        flags.append("resume")
    elif stages and not delivered:
        flags.append("partial")
    if dirty:
        state = "dirty"
        next_action = "preserve and inspect user changes before checkpoint, migration or reroute"
    elif failed:
        state = "failed"
        next_action = (
            f"inspect blocking evidence at stage {data.get('current_stage')} and run reroute suggestion")
    elif need_reverify:
        state = "stale"
        next_action = f"reverify propagated stages {need_reverify} before continuing"
    elif delivered:
        state = "delivered"
        next_action = (
            "delivery authorization is recorded; preserve the hash-bound "
            "package or begin a new intake"
        )
    elif active:
        state = "resume"
        next_action = data.get("next_action") or f"resume stage {active[-1]}"
    elif stages:
        state = "partial"
        next_action = data.get("next_action") or "select the next dependency-ready stage"
    else:
        state = "new"
        next_action = data.get("next_action") or "append the first selected stage"
    assert state in INTAKE_STATES
    blockers = list(validation["errors"])
    if dirty:
        blockers.append(dirty_note)
    return {
        "schema": "light.orchestrator.intake.v1",
        "state": state,
        "flags": sorted(set(flags)),
        "passport": str(path),
        "passport_state_hash": data.get("state_hash"),
        "next_action": next_action,
        "blockers": blockers,
        "need_reverify": need_reverify,
        "known_limitations": data.get("known_limitations") or [],
        "validation_verdict": validation["verdict"],
        "evidence_state": data.get("evidence_state", "UNKNOWN"),
    }


def build_handoff(root: str | pathlib.Path) -> dict:
    status = classify(root)
    return {
        "schema": SCHEMA_HANDOFF,
        "generated_at": iso_now(),
        "project_root": str(pathlib.Path(root).resolve()),
        "passport": status["passport"],
        "passport_state_hash": status["passport_state_hash"],
        "intake_state": status["state"],
        "evidence_state": status.get("evidence_state", "UNKNOWN"),
        "next_action": status["next_action"],
        "blockers": status["blockers"],
        "need_reverify": status["need_reverify"],
        "known_limitations": status["known_limitations"],
    }


def _parse_handoff_time(value: Any) -> tuple[dt.datetime | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, "handoff missing generated_at"
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "handoff generated_at must be ISO-8601"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "handoff generated_at must include timezone"
    return parsed, None


def _resolved_path(value: Any) -> pathlib.Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return pathlib.Path(value).resolve()
    except OSError:
        return None


def _handoff_field_mismatches(status: dict, handoff: dict) -> list[dict[str, Any]]:
    expected = {
        "intake_state": status["state"],
        "evidence_state": status.get("evidence_state", "UNKNOWN"),
        "next_action": status["next_action"],
        "blockers": status["blockers"],
        "need_reverify": status["need_reverify"],
        "known_limitations": status["known_limitations"],
    }
    mismatches: list[dict[str, Any]] = []
    for field, current in expected.items():
        recorded = handoff.get(field)
        if recorded != current:
            mismatches.append({
                "field": field,
                "recorded": recorded,
                "current": current,
            })
    return mismatches


def verify_handoff(root: str | pathlib.Path, handoff: dict) -> dict:
    if handoff.get("schema") != SCHEMA_HANDOFF:
        return {"verdict": "FAILED", "reason": "unsupported handoff schema"}
    current_root = pathlib.Path(root).resolve()
    recorded_root = _resolved_path(handoff.get("project_root"))
    if recorded_root is None:
        return {"verdict": "FAILED", "reason": "handoff missing project_root"}
    if recorded_root != current_root:
        return {
            "verdict": "FAILED",
            "reason": "handoff project_root does not match current root",
            "recorded_project_root": str(recorded_root),
            "current_project_root": str(current_root),
        }
    generated_at, time_error = _parse_handoff_time(handoff.get("generated_at"))
    if time_error:
        return {"verdict": "FAILED", "reason": time_error}
    now = dt.datetime.now(dt.timezone.utc).astimezone()
    if generated_at > now + MAX_HANDOFF_CLOCK_SKEW:
        return {
            "verdict": "FAILED",
            "reason": "handoff generated_at is in the future",
            "generated_at": generated_at.isoformat(),
            "current_time": now.isoformat(timespec="seconds"),
        }
    status = classify(root)
    recorded = handoff.get("passport_state_hash")
    current = status.get("passport_state_hash")
    if recorded != current:
        return {
            "verdict": "FAILED",
            "reason": "handoff is stale: passport state hash changed",
            "recorded": recorded,
            "current": current,
            "next_action": status["next_action"],
        }
    mismatches = _handoff_field_mismatches(status, handoff)
    if mismatches:
        return {
            "verdict": "FAILED",
            "reason": "handoff is stale: live intake snapshot changed",
            "mismatches": mismatches,
            "current": current,
            "next_action": status["next_action"],
        }
    return {
        "verdict": "VERIFIED",
        "reason": (
            "handoff root, timestamp, passport hash and live intake snapshot "
            "match current project"
        ),
        "current": current,
        "next_action": status["next_action"],
    }


def selftest() -> int:
    checks: list[tuple[bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="orchestrator_lifecycle_") as td:
        root = pathlib.Path(td)
        checks.append((classify(root)["state"] == "new", "new intake"))

        path = passport_path(root)
        data = {
            "schema": passport.SCHEMA_PASSPORT,
            "project": "life", "pipeline": "test",
            "created": "2026-07-03T00:00+08:00",
            "updated": "2026-07-03T00:00+08:00",
            "current_stage": 1, "state_revision": 0,
            "state_hash": "sha256:" + "0" * 64,
            "evidence_state": "PLANNED",
            "next_action": "start stage 2",
            "delivery_status": "IN_PROGRESS",
            "delivery_authorization_id": None,
            "stages": [{
                "stage": 1, "skill": "literature-search", "input": "q", "output": "map",
                "status": "delivered", "node_kind": "pipeline",
                "evidence_state": "VERIFIED",
            }],
        }
        passport.save(str(path), data)
        checks.append((classify(root)["state"] == "partial", "partial intake"))

        loaded = passport.load(str(path))
        loaded["stages"][0]["status"] = "in_progress"
        loaded["evidence_state"] = "PLANNED"
        passport.save(str(path), loaded)
        checks.append((classify(root)["state"] == "resume", "resume intake"))

        loaded = passport.load(str(path))
        loaded["stages"][0]["status"] = "gate_failed"
        loaded["stages"][0]["evidence_state"] = "FAILED"
        loaded["evidence_state"] = "FAILED"
        passport.save(str(path), loaded)
        checks.append((classify(root)["state"] == "failed", "failed intake"))

        artifact = root / "up.txt"
        artifact.write_text("v1", encoding="utf-8")
        loaded = passport.load(str(path))
        loaded["stages"][0].update({
            "status": "delivered", "evidence_state": "VERIFIED",
            "artifacts": ["up.txt"],
            "inputs_fingerprint": passport.compute_fingerprint([], str(root)),
        })
        loaded["evidence_state"] = "VERIFIED"
        loaded["delivery_status"] = "DELIVERED"
        loaded["delivery_authorization_id"] = "user-acceptance-001"
        passport.save(str(path), loaded)
        delivered_status = classify(root)
        checks.append((
            delivered_status["state"] == "delivered"
            and "authorization is recorded" in delivered_status["next_action"],
            "delivered intake",
        ))

        loaded = passport.load(str(path))
        loaded["stages"].append({
            "stage": 2, "skill": "data-engineering", "input": "map", "output": "data",
            "depends_on": [1], "status": "delivered", "node_kind": "pipeline",
            "evidence_state": "VERIFIED", "artifacts": ["up.txt"],
            "inputs_fingerprint": passport.compute_fingerprint(["up.txt"], str(root)),
        })
        loaded["current_stage"] = 2
        passport.save(str(path), loaded)
        fresh_handoff = build_handoff(root)
        checks.append((verify_handoff(root, fresh_handoff)["verdict"] == "VERIFIED",
                       "fresh live-intake handoff verifies"))
        wrong_root_handoff = dict(fresh_handoff)
        wrong_root_handoff["project_root"] = str(root / "other-project")
        checks.append((verify_handoff(root, wrong_root_handoff)["verdict"] == "FAILED",
                       "handoff rejects root mismatch"))
        future_handoff = dict(fresh_handoff)
        future_handoff["generated_at"] = "2999-01-01T00:00:00+00:00"
        checks.append((verify_handoff(root, future_handoff)["verdict"] == "FAILED",
                       "handoff rejects future timestamp"))
        artifact.write_text("v2 changed", encoding="utf-8")
        checks.append((verify_handoff(root, fresh_handoff)["verdict"] == "FAILED",
                       "artifact-only stale change invalidates handoff"))
        checks.append((classify(root)["state"] == "stale", "content-hash stale intake"))

        handoff = build_handoff(root)
        checks.append((verify_handoff(root, handoff)["verdict"] == "VERIFIED",
                       "fresh handoff verifies"))
        changed = passport.load(str(path))
        changed["next_action"] = "changed after handoff"
        passport.save(str(path), changed)
        checks.append((verify_handoff(root, handoff)["verdict"] == "FAILED",
                       "changed passport invalidates handoff"))

        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "untracked.txt").write_text("user work", encoding="utf-8")
        checks.append((classify(root)["state"] == "dirty", "dirty intake protects user work"))

    ok = True
    for passed, label in checks:
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] {label}")
    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Light orchestrator lifecycle intake and handoff")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("intake")
    p.add_argument("--root", default=".")
    p = sub.add_parser("handoff")
    p.add_argument("--root", default=".")
    p.add_argument("--out")
    p = sub.add_parser("verify-handoff")
    p.add_argument("--root", default=".")
    p.add_argument("--handoff", required=True)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.command == "intake":
        print(json.dumps(classify(args.root), ensure_ascii=False, indent=2))
        return 0
    if args.command == "handoff":
        result = build_handoff(args.root)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            pathlib.Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    if args.command == "verify-handoff":
        payload = json.loads(pathlib.Path(args.handoff).read_text(encoding="utf-8-sig"))
        result = verify_handoff(args.root, payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["verdict"] == "VERIFIED" else 1
    parser.error("choose intake, handoff, verify-handoff, or --selftest")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
