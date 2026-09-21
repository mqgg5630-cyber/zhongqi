#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate run bundles and compare a same-seed reproducibility pair.

This is a pure stdlib verifier. It does not replace ``repro_gate.py``:

- ``repro_gate`` checks static seed/leakage evidence and emits canonical findings.
- this tool checks that an executed matrix row left raw, hash-verified artifacts,
  then compares predictions and raw metrics from two same-seed runs.

It deliberately rejects summary-only handoffs. A completed run must retain
stdout, stderr, raw metrics, patient/sample-level predictions, test evidence,
config, environment, code, and input hashes. Failed/aborted runs must retain a
failure artifact instead of disappearing from coverage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "light.run_manifest.v3"
STATUS = {"completed", "failed", "aborted"}
TERMINATION_REASONS = {
    "natural_exit", "timeout", "max_iterations", "user_cancel", "error", "preempted"
}
COMPLETION_STATUS = {"NOT_EVALUATED", "PASS", "FAIL"}
SEED_ROLES = {"fixed_repro", "randomness_estimation"}
BASE_ARTIFACTS = ("stdout", "stderr", "test_evidence")
COMPLETED_ARTIFACTS = ("raw_metrics", "predictions")
SECRET_FLAGS = {
    "--api-key", "--apikey", "--token", "--access-token",
    "--password", "--secret", "--client-secret",
}
MAX_CLOCK_SKEW = dt.timedelta(minutes=5)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def load_json(path: pathlib.Path) -> dict[str, Any]:
    """Read UTF-8 JSON, accepting a Windows UTF-8 BOM."""
    with path.open(encoding="utf-8-sig") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _future_time(value: Any) -> bool:
    parsed = _parse_time(value)
    if parsed is None:
        return False
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return parsed > now + MAX_CLOCK_SKEW


def _inside(base: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes run directory: {relative}") from exc
    return candidate


@dataclass
class CheckResult:
    manifest: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    checked_hashes: dict[str, str] = field(default_factory=dict)
    completion_verified: bool = False
    data: dict[str, Any] = field(default_factory=dict, repr=False)

    def fail(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "ok": self.ok,
            "errors": self.errors,
            "checked_hashes": self.checked_hashes,
            "completion_verified": self.completion_verified,
        }


def _require_text(result: CheckResult, data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        result.fail(f"missing non-empty string: {key}")
        return ""
    return value


def _check_hashed_file(
    result: CheckResult,
    base: pathlib.Path,
    record: Any,
    label: str,
    *,
    required: bool = True,
) -> None:
    if record is None and not required:
        return
    if not isinstance(record, dict):
        result.fail(f"{label} must be an object with path + sha256")
        return
    relative = record.get("path")
    expected = record.get("sha256")
    if not isinstance(relative, str) or not relative:
        result.fail(f"{label}.path missing")
        return
    if not _is_sha256(expected):
        result.fail(f"{label}.sha256 must be a 64-char hexadecimal digest")
        return
    try:
        path = _inside(base, relative)
    except ValueError as exc:
        result.fail(f"{label}: {exc}")
        return
    if not path.is_file():
        result.fail(f"{label}: file not found: {relative}")
        return
    actual = sha256_file(path)
    result.checked_hashes[label] = actual
    if actual != expected:
        result.fail(f"{label}: sha256 mismatch expected={expected} actual={actual}")


def validate_manifest(path: str | pathlib.Path) -> CheckResult:
    manifest_path = pathlib.Path(path).resolve()
    result = CheckResult(str(manifest_path))
    try:
        data = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.fail(f"cannot read manifest: {exc}")
        return result
    result.data = data
    base = manifest_path.parent

    if data.get("schema") != SCHEMA:
        result.fail(f"schema must be {SCHEMA}")
    for key in ("run_id", "matrix_row", "started_at", "ended_at"):
        _require_text(result, data, key)
    started_at = _parse_time(data.get("started_at"))
    ended_at = _parse_time(data.get("ended_at"))
    if data.get("started_at") and started_at is None:
        result.fail("started_at must be timezone-aware ISO-8601")
    if data.get("ended_at") and ended_at is None:
        result.fail("ended_at must be timezone-aware ISO-8601")
    if started_at and ended_at and ended_at < started_at:
        result.fail("ended_at must be greater than or equal to started_at")
    if _future_time(data.get("started_at")):
        result.fail("started_at is in the future")
    if _future_time(data.get("ended_at")):
        result.fail("ended_at is in the future")
    status = data.get("status")
    if status not in STATUS:
        result.fail(f"status must be one of {sorted(STATUS)}")

    termination = data.get("termination")
    if not isinstance(termination, dict):
        result.fail("termination must be an object")
    else:
        reason = termination.get("reason")
        exit_code = termination.get("exit_code")
        if reason not in TERMINATION_REASONS:
            result.fail(f"termination.reason must be one of {sorted(TERMINATION_REASONS)}")
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            result.fail("termination.exit_code must be integer or null")
        if status == "completed" and not (
            reason == "natural_exit" and exit_code == 0
        ):
            result.fail("completed requires termination.reason=natural_exit and exit_code=0")
        if status == "failed" and reason != "error":
            result.fail("failed requires termination.reason=error")
        if status == "aborted" and reason not in {
            "timeout", "max_iterations", "user_cancel", "preempted"
        }:
            result.fail("aborted requires timeout/max_iterations/user_cancel/preempted")

    seed = data.get("seed")
    if not isinstance(seed, dict):
        result.fail("seed must be an object")
    else:
        if seed.get("role") not in SEED_ROLES:
            result.fail(f"seed.role must be one of {sorted(SEED_ROLES)}")
        if not isinstance(seed.get("value"), int):
            result.fail("seed.value must be an integer")

    command = data.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        result.fail("command must be a non-empty argv list")
    else:
        lowered = [item.lower() for item in command]
        if any(
            item in SECRET_FLAGS
            or any(item.startswith(f"{flag}=") for flag in SECRET_FLAGS)
            for item in lowered
        ):
            result.fail(
                "command appears to contain a secret-bearing flag; record only an env/key name"
            )

    _check_hashed_file(result, base, data.get("config"), "config")
    _check_hashed_file(result, base, data.get("environment"), "environment")

    code = data.get("code")
    if not isinstance(code, dict):
        result.fail("code must be an object")
    else:
        _require_text(result, code, "commit")
        dirty = code.get("dirty")
        if not isinstance(dirty, bool):
            result.fail("code.dirty must be boolean")
        diff_sha256 = code.get("diff_sha256")
        if dirty is True and not _is_sha256(diff_sha256):
            result.fail("dirty code requires code.diff_sha256")
        if dirty is False and diff_sha256 is not None and not _is_sha256(diff_sha256):
            result.fail("code.diff_sha256 must be null or a 64-char hexadecimal digest")
        code_files = code.get("files")
        if not isinstance(code_files, list) or not code_files:
            result.fail("code.files must retain at least one path + sha256")
        else:
            for index, record in enumerate(code_files):
                _check_hashed_file(result, base, record, f"code.files[{index}]")

    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        result.fail("inputs must retain at least one hashed input")
    else:
        for index, record in enumerate(inputs):
            label = f"inputs[{index}]"
            if not isinstance(record, dict):
                result.fail(f"{label} must be an object")
                continue
            if not isinstance(record.get("role"), str) or not record["role"]:
                result.fail(f"{label}.role missing")
            if record.get("role") == "data" and not record.get("source_revision"):
                result.fail(f"{label}.source_revision missing for data input")
            _check_hashed_file(result, base, record, label)

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        result.fail("artifacts must be an object")
        artifacts = {}
    for name in BASE_ARTIFACTS:
        _check_hashed_file(result, base, artifacts.get(name), f"artifacts.{name}")
    if status == "completed":
        for name in COMPLETED_ARTIFACTS:
            _check_hashed_file(result, base, artifacts.get(name), f"artifacts.{name}")
        if artifacts.get("failure") is not None:
            result.fail("completed run must set artifacts.failure to null")
    elif status in {"failed", "aborted"}:
        _check_hashed_file(result, base, artifacts.get("failure"), "artifacts.failure")

    completion = data.get("completion")
    if not isinstance(completion, dict):
        result.fail("completion must be an object; execution end is not task completion")
    else:
        completion_status = completion.get("status")
        oracle = completion.get("oracle")
        evidence = completion.get("evidence_artifacts")
        if completion_status not in COMPLETION_STATUS:
            result.fail(f"completion.status must be one of {sorted(COMPLETION_STATUS)}")
        if not isinstance(oracle, list) or not all(
            isinstance(x, str) and x.strip() for x in oracle
        ):
            result.fail("completion.oracle must be a list of non-empty checks")
            oracle = []
        if not isinstance(evidence, list) or not all(
            isinstance(x, str) and x.strip() for x in evidence
        ):
            result.fail("completion.evidence_artifacts must be a list of artifact names")
            evidence = []
        if completion_status in {"PASS", "FAIL"} and not oracle:
            result.fail(f"completion {completion_status} requires at least one oracle")
        if completion_status == "PASS" and not evidence:
            result.fail("completion PASS requires evidence_artifacts")
        for name in evidence:
            if name not in artifacts or artifacts.get(name) is None:
                result.fail(f"completion evidence not declared: artifacts.{name}")
        result.completion_verified = (
            completion_status == "PASS"
            and bool(oracle)
            and bool(evidence)
        )

    repro = data.get("reproducibility")
    if not isinstance(repro, dict):
        result.fail("reproducibility must be an object")
    else:
        names = repro.get("compare_artifacts")
        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(x, str) and x for x in names)
        ):
            result.fail("reproducibility.compare_artifacts must be a non-empty list")
        elif status == "completed":
            for name in names:
                if name not in artifacts:
                    result.fail(f"compare artifact not declared: artifacts.{name}")

    if not result.ok:
        result.completion_verified = False
    return result


def _record_sha(data: dict[str, Any], section: str, key: str = "") -> str:
    record: Any = data.get(section)
    if key and isinstance(record, dict):
        record = record.get(key)
    return record.get("sha256", "") if isinstance(record, dict) else ""


def _identity(data: dict[str, Any]) -> dict[str, Any]:
    code = data.get("code") if isinstance(data.get("code"), dict) else {}
    code_files = code.get("files") if isinstance(code.get("files"), list) else []
    inputs = data.get("inputs") if isinstance(data.get("inputs"), list) else []
    return {
        "matrix_row": data.get("matrix_row"),
        "seed": data.get("seed"),
        "config_sha256": _record_sha(data, "config"),
        "environment_sha256": _record_sha(data, "environment"),
        "code_commit": code.get("commit"),
        "code_dirty": code.get("dirty"),
        "code_diff_sha256": code.get("diff_sha256"),
        "code_files": sorted(
            (x.get("path"), x.get("sha256")) for x in code_files if isinstance(x, dict)
        ),
        "inputs": sorted(
            (x.get("role"), x.get("source_revision"), x.get("sha256"))
            for x in inputs
            if isinstance(x, dict)
        ),
    }


def compare_manifests(
    first: str | pathlib.Path,
    second: str | pathlib.Path,
) -> dict[str, Any]:
    left = validate_manifest(first)
    right = validate_manifest(second)
    errors = [f"first: {x}" for x in left.errors] + [
        f"second: {x}" for x in right.errors
    ]
    compared: dict[str, dict[str, Any]] = {}
    if not errors:
        if (
            left.data.get("status") != "completed"
            or right.data.get("status") != "completed"
        ):
            errors.append("same-seed comparison requires two completed runs")
        seed_left = left.data.get("seed", {})
        seed_right = right.data.get("seed", {})
        if seed_left != seed_right or seed_left.get("role") != "fixed_repro":
            errors.append(
                "runs must share seed role=fixed_repro and the same integer value"
            )
        if _identity(left.data) != _identity(right.data):
            errors.append("run identity differs (matrix/config/environment/code/input)")

        names = left.data.get("reproducibility", {}).get("compare_artifacts", [])
        if names != right.data.get("reproducibility", {}).get("compare_artifacts", []):
            errors.append("compare_artifacts lists differ")
        else:
            for name in names:
                lsha = _record_sha(left.data, "artifacts", name)
                rsha = _record_sha(right.data, "artifacts", name)
                match = bool(lsha) and lsha == rsha
                compared[name] = {"first": lsha, "second": rsha, "match": match}
                if not match:
                    errors.append(f"artifact mismatch: {name}")

    return {
        "schema": "light.repro_comparison.v1",
        "first": str(pathlib.Path(first).resolve()),
        "second": str(pathlib.Path(second).resolve()),
        "same_seed_exact": not errors,
        "compared_artifacts": compared,
        "errors": errors,
    }


def _write_file(path: pathlib.Path, text: str) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"path": path.name, "sha256": sha256_file(path)}


def _make_manifest(
    run: pathlib.Path, run_id: str, prediction: str = "p\n0.2\n"
) -> pathlib.Path:
    config = _write_file(run / "config.json", '{"seed":42}\n')
    environment = _write_file(run / "environment.json", '{"python":"3.11"}\n')
    code_file = _write_file(run / "train.py", "print('train')\n")
    data_file = _write_file(run / "data.csv", "id,y\n1,0\n")
    artifacts = {
        "stdout": _write_file(run / "stdout.log", "ok\n"),
        "stderr": _write_file(run / "stderr.log", ""),
        "raw_metrics": _write_file(run / "raw_metrics.jsonl", '{"brier":0.04}\n'),
        "predictions": _write_file(run / "predictions.csv", prediction),
        "test_evidence": _write_file(run / "test_evidence.json", '{"passed":true}\n'),
        "failure": None,
    }
    manifest = {
        "schema": SCHEMA,
        "run_id": run_id,
        "matrix_row": "EXP-01",
        "status": "completed",
        "termination": {
            "reason": "natural_exit",
            "exit_code": 0,
            "signal": None,
        },
        "seed": {"role": "fixed_repro", "value": 42},
        "command": ["python", "train.py", "--seed", "42"],
        "started_at": "2026-07-02T10:00:00+08:00",
        "ended_at": "2026-07-02T10:01:00+08:00",
        "config": config,
        "environment": environment,
        "code": {"commit": "abc123", "dirty": False, "files": [code_file]},
        "inputs": [{**data_file, "role": "data", "source_revision": "rev-1"}],
        "artifacts": artifacts,
        "completion": {
            "status": "PASS",
            "oracle": ["test evidence reports pass", "required raw artifacts exist"],
            "evidence_artifacts": ["test_evidence", "raw_metrics", "predictions"],
        },
        "reproducibility": {
            "pair_id": "EXP-01-seed42",
            "comparison_role": "first",
            "compare_artifacts": ["predictions", "raw_metrics"],
        },
        "notes": [],
    }
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _selftest() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="run_artifact_check_") as tmp:
        root = pathlib.Path(tmp)
        first = _make_manifest(root / "run-a", "EXP-01-seed42-a")
        second = _make_manifest(root / "run-b", "EXP-01-seed42-b")
        good = validate_manifest(first)
        if not good.ok:
            failures.append(f"valid bundle rejected: {good.errors}")
        if not good.completion_verified:
            failures.append("valid bundle completion oracle was not verified")
        exact = compare_manifests(first, second)
        if not exact["same_seed_exact"]:
            failures.append(f"identical pair rejected: {exact['errors']}")

        changed = _make_manifest(
            root / "run-c", "EXP-01-seed42-c", prediction="p\n0.3\n"
        )
        mismatch = compare_manifests(first, changed)
        if (
            mismatch["same_seed_exact"]
            or "artifact mismatch: predictions" not in mismatch["errors"]
        ):
            failures.append("prediction mismatch was not rejected")

        dirty_path = _make_manifest(root / "run-d", "EXP-01-seed42-d")
        dirty_data = load_json(dirty_path)
        dirty_data["code"]["dirty"] = True
        dirty_path.write_text(json.dumps(dirty_data, indent=2), encoding="utf-8")
        dirty = validate_manifest(dirty_path)
        if dirty.ok or "dirty code requires code.diff_sha256" not in dirty.errors:
            failures.append("dirty run without diff SHA256 was not rejected")

        secret_path = _make_manifest(root / "run-secret", "EXP-01-seed42-secret")
        secret_data = load_json(secret_path)
        secret_data["command"] += ["--api-key", "do-not-store-this"]
        secret_path.write_text(json.dumps(secret_data, indent=2), encoding="utf-8")
        secret = validate_manifest(secret_path)
        if secret.ok or not any("secret-bearing flag" in x for x in secret.errors):
            failures.append("secret-bearing command flag was not rejected")

        future_time_path = _make_manifest(
            root / "run-future-time", "EXP-01-seed42-future-time"
        )
        future_time_data = load_json(future_time_path)
        future_time_data["started_at"] = "2999-01-01T00:00:00+00:00"
        future_time_data["ended_at"] = "2999-01-01T00:01:00+00:00"
        future_time_path.write_text(
            json.dumps(future_time_data, indent=2), encoding="utf-8"
        )
        future_time = validate_manifest(future_time_path)
        if future_time.ok or not any("future" in x for x in future_time.errors):
            failures.append("future started_at/ended_at was not rejected")

        reversed_time_path = _make_manifest(
            root / "run-reversed-time", "EXP-01-seed42-reversed-time"
        )
        reversed_time_data = load_json(reversed_time_path)
        reversed_time_data["started_at"] = "2026-07-02T10:02:00+08:00"
        reversed_time_data["ended_at"] = "2026-07-02T10:01:00+08:00"
        reversed_time_path.write_text(
            json.dumps(reversed_time_data, indent=2), encoding="utf-8"
        )
        reversed_time = validate_manifest(reversed_time_path)
        if (
            reversed_time.ok
            or "ended_at must be greater than or equal to started_at"
            not in reversed_time.errors
        ):
            failures.append("ended_at before started_at was not rejected")

        unbounded_path = _make_manifest(root / "run-e", "EXP-01-seed42-e")
        unbounded_data = load_json(unbounded_path)
        unbounded_data["status"] = "aborted"
        unbounded_data["termination"] = {
            "reason": "max_iterations", "exit_code": None, "signal": None
        }
        unbounded_data["completion"] = {
            "status": "NOT_EVALUATED", "oracle": [], "evidence_artifacts": []
        }
        unbounded_data["artifacts"]["failure"] = _write_file(
            unbounded_path.parent / "failure.json",
            '{"reason":"max_iterations"}\n',
        )
        unbounded_path.write_text(
            json.dumps(unbounded_data, indent=2), encoding="utf-8"
        )
        unbounded = validate_manifest(unbounded_path)
        if not unbounded.ok or unbounded.completion_verified:
            failures.append(
                "max-iteration abort should be valid execution evidence but not completion"
            )

        broken_data = load_json(first)
        pathlib.Path(
            root / "run-a" / broken_data["artifacts"]["raw_metrics"]["path"]
        ).write_text('{"brier":0.99}\n', encoding="utf-8")
        broken = validate_manifest(first)
        if broken.ok or not any("sha256 mismatch" in x for x in broken.errors):
            failures.append("tampered artifact hash was not rejected")

    if failures:
        print("[SELFTEST][run_artifact_check] FAIL:")
        for failure in failures:
            print("  -", failure)
        return 1
    print(
        "[SELFTEST][run_artifact_check] OK: valid bundle / same-seed exact pair / "
        "prediction mismatch / dirty diff / max-iterations not completed / "
        "secret flag / future or reversed timestamps / tampered hash / temp cleanup checked"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="核验逐 run 原始工件，并比较同 seed 两次真复现"
    )
    parser.add_argument("--manifest", help="验证一个 light.run_manifest.v3")
    parser.add_argument("--compare", nargs=2, metavar=("FIRST", "SECOND"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if bool(args.manifest) == bool(args.compare):
        parser.error("exactly one of --manifest or --compare is required")
    if args.manifest:
        result: dict[str, Any] = validate_manifest(args.manifest).to_dict()
        ok = result["ok"]
    else:
        result = compare_manifests(*args.compare)
        ok = result["same_seed_exact"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if ok else "FAIL")
        for error in result.get("errors", []):
            print("-", error)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
