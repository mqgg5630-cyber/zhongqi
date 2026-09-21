#!/usr/bin/env python3
"""Read-only system intake and architecture-package evidence verification.

This tool intentionally does not generate architecture choices or apply SQL.
It makes two fragile mechanics deterministic:

* inventory an existing source root without changing it; and
* reject unsupported VERIFIED claims in a package manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

INTAKE_SCHEMA = "light.system-design.v2.intake"
PACKAGE_SCHEMA = "light.system-design.v2.package"
AUTH_SCHEMA = "light.system-design.v2.authorization"
STATES = {"VERIFIED", "PLANNED", "UNKNOWN", "UNAVAILABLE", "FAILED"}
REQUIREMENTS = (
    "users",
    "business_goal",
    "core_use_cases",
    "data_classification",
    "load_range",
    "latency_target",
    "availability_target",
    "durability_target",
    "consistency_target",
    "team_operations_capability",
    "budget",
    "deployment_environment",
    "compliance",
    "migration_window",
)
CURRENT_STATE = (
    "components",
    "interfaces",
    "stores",
    "dependencies",
    "write_paths",
    "trust_boundaries",
    "failure_modes",
    "deployments",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.casefold() not in {
        "unknown",
        "pending",
        "todo",
        "tbd",
        "n/a",
        "none",
        "user_supplied",
    } and "<" not in text and "{{" not in text


def _looks_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[0-9a-fA-F]{64}", value.strip())
    )


def _action_set(value: Any, label: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} needs non-empty action_ids")
        return set()
    normalized = [str(action).strip() for action in value if _real(action)]
    if len(normalized) != len(value) or len(set(normalized)) != len(normalized):
        errors.append(f"{label} action_ids must be real and unique")
        return set(normalized)
    return set(normalized)


def _package_locator(
    package_dir: Path, locator: Any, label: str, errors: list[str]
) -> Path | None:
    if not isinstance(locator, str) or not locator.strip():
        errors.append(f"{label} needs a non-empty locator")
        return None
    raw = Path(locator).expanduser()
    path = raw.resolve() if raw.is_absolute() else (package_dir / raw).resolve()
    if not _is_within(path, package_dir):
        errors.append(f"{label} locator escapes package directory: {locator}")
        return None
    return path


def _artifact_kind(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in {".sql", ".sqlite", ".sqlite3", ".db"}:
        return "schema-or-store-signal"
    if name in {"openapi.yaml", "openapi.yml", "openapi.json"}:
        return "api-contract-signal"
    if suffix in {".yaml", ".yml", ".json", ".toml", ".ini", ".env"}:
        return "configuration-signal"
    if name in {"dockerfile", "compose.yaml", "compose.yml"} or suffix in {
        ".tf",
        ".hcl",
    }:
        return "deployment-signal"
    if name in {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "pom.xml",
        "build.gradle",
        "cargo.toml",
        "go.mod",
    }:
        return "dependency-signal"
    if suffix in {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".cs",
        ".rb",
        ".php",
    }:
        return "code-signal"
    if suffix in {".md", ".rst", ".txt"}:
        return "documentation-signal"
    return "other"


def _snapshot(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            rows.append(
                {
                    "locator": path.relative_to(root).as_posix(),
                    "kind": "symlink",
                    "target": os.readlink(path),
                }
            )
        elif path.is_file():
            rows.append(
                {
                    "locator": path.relative_to(root).as_posix(),
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "artifact_kind_signal": _artifact_kind(path),
                }
            )
    return rows


def _json_read(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_declared(items: Any, category: str) -> list[dict[str, Any]] | str:
    if items in (None, "UNKNOWN"):
        return "UNKNOWN"
    if not isinstance(items, list):
        raise ValueError(f"current_state.{category} must be an array")
    normalized = []
    for index, raw in enumerate(items):
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict):
            raise ValueError(f"current_state.{category}[{index}] must be an object")
        item = dict(raw)
        item.setdefault("name", "UNKNOWN")
        item.setdefault("owner", "UNKNOWN")
        item.setdefault("fact_status", "declared")
        item.setdefault("source_locator", "UNKNOWN")
        item.setdefault("freshness", "UNKNOWN")
        normalized.append(item)
    return normalized


def _unknown_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if value == "UNKNOWN":
        found.append(prefix or "$")
    elif isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else key
            found.extend(_unknown_paths(child, name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_unknown_paths(child, f"{prefix}[{index}]"))
    return found


def run_intake(root_arg: str, manifest_arg: str, out_arg: str) -> dict[str, Any]:
    root = Path(root_arg).expanduser().resolve()
    manifest_path = Path(manifest_arg).expanduser().resolve()
    out = Path(out_arg).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    if not manifest_path.is_file():
        raise ValueError(f"manifest is not a file: {manifest_path}")
    if _is_within(out, root):
        raise ValueError("evidence --out must be outside the source root")
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"evidence directory must be absent or empty: {out}")

    manifest = _json_read(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema") != INTAKE_SCHEMA:
        raise ValueError(f"manifest schema must be {INTAKE_SCHEMA}")

    requirements = dict(manifest.get("requirements") or {})
    for key in REQUIREMENTS:
        requirements.setdefault(key, "UNKNOWN")
    current = dict(manifest.get("current_state") or {})
    declared = {
        key: _normalize_declared(current.get(key, "UNKNOWN"), key)
        for key in CURRENT_STATE
    }

    before = _snapshot(root)
    profile = {
        "schema": "light.system-design.v2.profile",
        "source_root": str(root),
        "mode": manifest.get("mode", "UNKNOWN"),
        "requirements": requirements,
        "known_constraints": manifest.get("known_constraints", "UNKNOWN"),
        "existing_clients": manifest.get("existing_clients", "UNKNOWN"),
        "fact_sources": manifest.get("fact_sources", "UNKNOWN"),
    }
    inventory = {
        "schema": "light.system-design.v2.source-inventory",
        "source_root": str(root),
        "files": before,
    }
    current_inventory = {
        "schema": "light.system-design.v2.current-state",
        **declared,
        "limitation": (
            "Declared items are not independently proven by filename scanning; "
            "fact_status/source_locator/freshness must carry that distinction."
        ),
    }
    unknowns = sorted(set(_unknown_paths(profile) + _unknown_paths(current_inventory)))
    risks: list[dict[str, str]] = []
    if declared["trust_boundaries"] in ("UNKNOWN", []):
        risks.append(
            {
                "code": "TRUST-BOUNDARY-UNKNOWN",
                "state": "UNKNOWN",
                "message": "No trust boundary was declared; do not infer one.",
            }
        )
    existing_clients = manifest.get("existing_clients", "UNKNOWN")
    if existing_clients == "UNKNOWN":
        risks.append(
            {
                "code": "EXISTING-CLIENTS-UNKNOWN",
                "state": "UNKNOWN",
                "message": "Existing-client inventory is UNKNOWN; compatibility is not cleared.",
            }
        )
    elif existing_clients and requirements["migration_window"] == "UNKNOWN":
        risks.append(
            {
                "code": "CLIENT-WINDOW-UNKNOWN",
                "state": "UNKNOWN",
                "message": "Existing clients are declared but migration window is UNKNOWN.",
            }
        )
    if requirements["data_classification"] == "UNKNOWN":
        risks.append(
            {
                "code": "DATA-CLASSIFICATION-UNKNOWN",
                "state": "UNKNOWN",
                "message": "Data classification is UNKNOWN; no privacy clearance is implied.",
            }
        )

    after = _snapshot(root)
    unchanged = before == after
    if not unchanged:
        raise RuntimeError("source snapshot changed during read-only intake")

    out.mkdir(parents=True, exist_ok=True)
    _json_write(out / "system-profile.json", profile)
    _json_write(out / "source-inventory.json", inventory)
    _json_write(out / "current-state-inventory.json", current_inventory)
    _json_write(
        out / "risk-unknown-report.json",
        {
            "schema": "light.system-design.v2.risk-unknown",
            "unknown_paths": unknowns,
            "risks": risks,
        },
    )
    integrity = {
        "schema": "light.system-design.v2.intake-integrity",
        "source_root": str(root),
        "evidence_root": str(out),
        "source_unchanged": unchanged,
        "before_snapshot_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "after_snapshot_sha256": hashlib.sha256(
            json.dumps(after, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "file_count": sum(1 for row in before if row["kind"] == "file"),
    }
    _json_write(out / "intake-integrity.json", integrity)
    (out / "delivery.md").write_text(
        "\n".join(
            [
                "# System intake delivery",
                "",
                f"- Source root: `{root}`",
                f"- Source unchanged: `{str(unchanged).lower()}`",
                f"- Files inventoried: {integrity['file_count']}",
                f"- Explicit unknown fields: {len(unknowns)}",
                f"- Risk/decision signals: {len(risks)}",
                "",
                "This is a read-only inventory, not authorization to rewrite "
                "schema, API, deployment, or configuration.",
                "Next: review current state and present architecture options "
                "before requesting a user decision.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return integrity


def verify_package(package_arg: str) -> dict[str, Any]:
    package_path = Path(package_arg).expanduser().resolve()
    package_dir = package_path.parent
    package = _json_read(package_path)
    errors: list[str] = []
    if not isinstance(package, dict) or package.get("schema") != PACKAGE_SCHEMA:
        errors.append(f"package schema must be {PACKAGE_SCHEMA}")
        package = package if isinstance(package, dict) else {}

    approved_actions: set[str] = set()
    binding = package.get("authorization_binding")
    if not isinstance(binding, dict):
        errors.append("authorization_binding is required for architecture package verification")
    else:
        for field in ("authorization_id", "option_id"):
            if not _real(binding.get(field)):
                errors.append(f"authorization_binding.{field} is required")
        if not _looks_sha256(binding.get("option_packet_sha256")):
            errors.append("authorization_binding.option_packet_sha256 must be a 64-hex SHA-256")
        approved_actions = _action_set(
            binding.get("approved_action_ids"),
            "authorization_binding.approved_action_ids",
            errors,
        )
        auth_expected = binding.get("authorization_sha256")
        if not _looks_sha256(auth_expected):
            errors.append("authorization_binding.authorization_sha256 must be a 64-hex SHA-256")
        auth_path = _package_locator(
            package_dir,
            binding.get("authorization_locator"),
            "authorization_binding",
            errors,
        )
        if auth_path is not None:
            if not auth_path.is_file():
                errors.append(f"authorization_binding missing: {auth_path}")
            elif _looks_sha256(auth_expected):
                actual = _sha256(auth_path)
                if actual != str(auth_expected).strip().casefold():
                    errors.append("authorization_binding hash mismatch")
                if auth_path.suffix.lower() == ".json":
                    auth = _json_read(auth_path)
                    if not isinstance(auth, dict) or auth.get("schema") != AUTH_SCHEMA:
                        errors.append(f"authorization file schema must be {AUTH_SCHEMA}")
                    else:
                        for field in ("authorization_id", "option_id", "option_packet_sha256"):
                            if str(auth.get(field) or "").strip() != str(binding.get(field) or "").strip():
                                errors.append(f"authorization_binding.{field} drifts from authorization file")
                        auth_actions = set(str(x).strip() for x in auth.get("approved_action_ids", []) if _real(x))
                        if auth_actions != approved_actions:
                            errors.append("authorization_binding.approved_action_ids drift from authorization file")

    implemented_actions = _action_set(
        package.get("implemented_action_ids"), "implemented_action_ids", errors
    )
    if approved_actions:
        out_of_scope = sorted(implemented_actions - approved_actions)
        if out_of_scope:
            errors.append(f"implemented_action_ids include unauthorized actions: {out_of_scope}")

    source_binding = package.get("source_intake_binding")
    if isinstance(source_binding, dict):
        expected = source_binding.get("sha256")
        if not _looks_sha256(expected):
            errors.append("source_intake_binding.sha256 must be a 64-hex SHA-256")
        intake_path = _package_locator(
            package_dir, source_binding.get("locator"), "source_intake_binding", errors
        )
        if intake_path is not None:
            if not intake_path.is_file():
                errors.append(f"source_intake_binding missing: {intake_path}")
            elif _looks_sha256(expected):
                if _sha256(intake_path) != str(expected).strip().casefold():
                    errors.append("source_intake_binding hash mismatch")
                intake = _json_read(intake_path)
                if not isinstance(intake, dict) or intake.get("schema") != "light.system-design.v2.intake-integrity":
                    errors.append("source_intake_binding must point to intake-integrity.json")
                else:
                    if intake.get("source_unchanged") is not True:
                        errors.append("source_intake_binding source_unchanged is not true")
                    if source_binding.get("source_root") and str(source_binding.get("source_root")) != str(intake.get("source_root")):
                        errors.append("source_intake_binding.source_root drifts from intake artifact")
                    supplied_snapshot = source_binding.get("before_snapshot_sha256")
                    if supplied_snapshot:
                        if not _looks_sha256(supplied_snapshot):
                            errors.append("source_intake_binding.before_snapshot_sha256 must be a 64-hex SHA-256")
                        elif str(supplied_snapshot).casefold() != str(intake.get("before_snapshot_sha256") or "").casefold():
                            errors.append("source_intake_binding.before_snapshot_sha256 drifts from intake artifact")
    elif not _real(package.get("source_intake_not_applicable_reason")):
        errors.append("source_intake_binding or source_intake_not_applicable_reason is required")

    for index, artifact in enumerate(package.get("artifacts", [])):
        if not isinstance(artifact, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        artifact_actions = _action_set(
            artifact.get("action_ids"), f"artifacts[{index}]", errors
        )
        if implemented_actions:
            out_of_scope = sorted(artifact_actions - implemented_actions)
            if out_of_scope:
                errors.append(f"artifacts[{index}] action_ids outside implemented scope: {out_of_scope}")
        locator = artifact.get("locator")
        expected = artifact.get("sha256")
        if not locator or not expected:
            errors.append(f"artifacts[{index}] needs locator and sha256")
            continue
        path = _package_locator(package_dir, locator, f"artifacts[{index}]", errors)
        if path is None:
            continue
        if not path.is_file():
            errors.append(f"artifacts[{index}] missing: {path}")
        elif _sha256(path) != expected:
            errors.append(f"artifacts[{index}] hash mismatch: {path}")

    required = {"command", "cwd", "returncode", "locator", "sha256", "timestamp"}
    counts = {state: 0 for state in sorted(STATES)}
    covered_actions: set[str] = set()
    for index, check in enumerate(package.get("verifications", [])):
        if not isinstance(check, dict):
            errors.append(f"verifications[{index}] must be an object")
            continue
        check_actions = _action_set(
            check.get("action_ids"), f"verifications[{index}]", errors
        )
        if implemented_actions:
            out_of_scope = sorted(check_actions - implemented_actions)
            if out_of_scope:
                errors.append(f"verifications[{index}] action_ids outside implemented scope: {out_of_scope}")
            covered_actions.update(check_actions)
        state = check.get("state")
        if state not in STATES:
            errors.append(f"verifications[{index}] invalid state: {state}")
            continue
        counts[state] += 1
        if state != "VERIFIED":
            continue
        missing = sorted(key for key in required if check.get(key) in (None, ""))
        if missing:
            errors.append(
                f"verifications[{index}] VERIFIED missing evidence: {missing}"
            )
            continue
        if check.get("returncode") != 0:
            errors.append(f"verifications[{index}] VERIFIED returncode is not 0")
        locator = _package_locator(
            package_dir, check["locator"], f"verifications[{index}]", errors
        )
        if locator is None:
            continue
        if not locator.is_file():
            errors.append(f"verifications[{index}] evidence missing: {locator}")
        elif _sha256(locator) != check["sha256"]:
            errors.append(f"verifications[{index}] evidence hash mismatch: {locator}")

    if implemented_actions:
        uncovered = sorted(implemented_actions - covered_actions)
        if uncovered:
            errors.append(f"implemented actions lack verification coverage: {uncovered}")

    return {
        "schema": "light.system-design.v2.package-verification",
        "package": str(package_path),
        "valid": not errors,
        "state_counts": counts,
        "errors": errors,
    }


def _selftest() -> int:
    repo_root = Path(__file__).resolve()
    while repo_root != repo_root.parent and not (
        repo_root / "skills" / "light-system-design"
    ).exists():
        repo_root = repo_root.parent
    e2e_root = repo_root / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    base = Path(
        tempfile.mkdtemp(prefix="light-system-design-lifecycle-", dir=e2e_root)
    )
    try:
        source = base / "service"
        evidence = base / "evidence"
        source.mkdir()
        (source / "schema.sql").write_text(
            "CREATE TABLE experiment(id INTEGER PRIMARY KEY);\n", encoding="utf-8"
        )
        (source / "openapi.yaml").write_text(
            "openapi: 3.1.0\ninfo: {title: x, version: '1'}\npaths: {}\n",
            encoding="utf-8",
        )
        manifest = base / "intake.json"
        _json_write(
            manifest,
            {
                "schema": INTAKE_SCHEMA,
                "mode": "existing",
                "requirements": {"business_goal": "track experiments"},
                "current_state": {
                    "components": [
                        {
                            "name": "api",
                            "source_locator": "openapi.yaml",
                            "freshness": "2026-07-03",
                        }
                    ]
                },
                "existing_clients": ["legacy-cli"],
            },
        )
        before = _snapshot(source)
        result = run_intake(str(source), str(manifest), str(evidence))
        assert result["source_unchanged"] is True
        assert before == _snapshot(source)
        report = _json_read(evidence / "risk-unknown-report.json")
        codes = {risk["code"] for risk in report["risks"]}
        assert "CLIENT-WINDOW-UNKNOWN" in codes
        assert "DATA-CLASSIFICATION-UNKNOWN" in codes
        current_state = _json_read(evidence / "current-state-inventory.json")
        assert current_state["interfaces"] == "UNKNOWN"
        assert "interfaces" in report["unknown_paths"]

        sparse_source = base / "sparse-service"
        sparse_source.mkdir()
        (sparse_source / "app.py").write_text("print('ok')\n", encoding="utf-8")
        sparse_manifest = base / "sparse-intake.json"
        _json_write(sparse_manifest, {"schema": INTAKE_SCHEMA, "mode": "existing"})
        sparse_evidence = base / "sparse-evidence"
        run_intake(str(sparse_source), str(sparse_manifest), str(sparse_evidence))
        sparse_report = _json_read(sparse_evidence / "risk-unknown-report.json")
        assert "requirements.core_use_cases" in sparse_report["unknown_paths"]
        assert "components" in sparse_report["unknown_paths"]
        assert "EXISTING-CLIENTS-UNKNOWN" in {
            risk["code"] for risk in sparse_report["risks"]
        }

        log = base / "verify.log"
        log.write_text("ok\n", encoding="utf-8")
        authorization = base / "authorization.json"
        _json_write(
            authorization,
            {
                "schema": AUTH_SCHEMA,
                "authorization_id": "auth-20260705-1",
                "option_id": "modular",
                "option_packet_sha256": "a" * 64,
                "approved_action_ids": [
                    "create-module-boundaries",
                    "create-api-contract",
                ],
                "disposable_target": str(base / "sandbox"),
                "disposable_confirmed": True,
                "compatibility_choice": "no existing consumers",
                "rollback_choice": "REQUIRED",
                "authorized_by": "user-message-42",
                "authorized_at": "2026-07-05",
            },
        )
        intake_integrity = evidence / "intake-integrity.json"
        package = base / "package.json"
        package_payload = {
            "schema": PACKAGE_SCHEMA,
            "authorization_binding": {
                "authorization_locator": "authorization.json",
                "authorization_sha256": _sha256(authorization),
                "authorization_id": "auth-20260705-1",
                "option_id": "modular",
                "option_packet_sha256": "a" * 64,
                "approved_action_ids": [
                    "create-module-boundaries",
                    "create-api-contract",
                ],
            },
            "implemented_action_ids": ["create-module-boundaries"],
            "source_intake_binding": {
                "locator": "evidence/intake-integrity.json",
                "sha256": _sha256(intake_integrity),
                "source_root": str(source.resolve()),
                "before_snapshot_sha256": result["before_snapshot_sha256"],
            },
            "artifacts": [
                {
                    "locator": "verify.log",
                    "sha256": _sha256(log),
                    "action_ids": ["create-module-boundaries"],
                }
            ],
            "verifications": [
                {
                    "name": "sample",
                    "state": "VERIFIED",
                    "command": "sample --check",
                    "cwd": str(base),
                    "returncode": 0,
                    "locator": "verify.log",
                    "sha256": _sha256(log),
                    "timestamp": "2026-07-03T00:00:00Z",
                    "action_ids": ["create-module-boundaries"],
                },
                {
                    "name": "load",
                    "state": "PLANNED",
                    "action_ids": ["create-module-boundaries"],
                },
            ],
        }
        _json_write(package, package_payload)
        verified = verify_package(str(package))
        assert verified["valid"] is True, verified

        escaped = _json_read(package)
        escaped["artifacts"].append(
            {
                "locator": "../outside.log",
                "sha256": "0" * 64,
                "action_ids": ["create-module-boundaries"],
            }
        )
        _json_write(package, escaped)
        escape_rejected = verify_package(str(package))
        assert escape_rejected["valid"] is False
        assert "escapes package directory" in "\n".join(escape_rejected["errors"])

        _json_write(package, json.loads(json.dumps(package_payload)))
        bad = _json_read(package)
        bad["verifications"][0].pop("command")
        _json_write(package, bad)
        rejected = verify_package(str(package))
        assert rejected["valid"] is False
        assert "missing evidence" in "\n".join(rejected["errors"])
        missing_binding = json.loads(json.dumps(package_payload))
        missing_binding.pop("authorization_binding")
        _json_write(package, missing_binding)
        missing_binding_result = verify_package(str(package))
        assert missing_binding_result["valid"] is False
        assert "authorization_binding is required" in "\n".join(
            missing_binding_result["errors"]
        )

        scope_bad = json.loads(json.dumps(package_payload))
        scope_bad["implemented_action_ids"].append("drop-production")
        _json_write(package, scope_bad)
        scope_result = verify_package(str(package))
        assert scope_result["valid"] is False
        assert "unauthorized actions" in "\n".join(scope_result["errors"])

        intake_stale = json.loads(json.dumps(package_payload))
        intake_stale["source_intake_binding"]["sha256"] = "0" * 64
        _json_write(package, intake_stale)
        intake_result = verify_package(str(package))
        assert intake_result["valid"] is False
        assert "source_intake_binding hash mismatch" in "\n".join(
            intake_result["errors"]
        )
        print("[selftest] PASS architecture_lifecycle")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only system intake and package evidence verification"
    )
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    intake = sub.add_parser("intake")
    intake.add_argument("root")
    intake.add_argument("--manifest", required=True)
    intake.add_argument("--out", required=True)
    verify = sub.add_parser("verify-package")
    verify.add_argument("--package", required=True)
    verify.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()
    try:
        if args.command == "intake":
            print(json.dumps(run_intake(args.root, args.manifest, args.out), indent=2))
            return 0
        if args.command == "verify-package":
            report = verify_package(args.package)
            print(
                json.dumps(report, ensure_ascii=False, indent=2)
                if args.json
                else (
                    "PASS package evidence"
                    if report["valid"]
                    else "FAIL package evidence\n- " + "\n- ".join(report["errors"])
                )
            )
            return 0 if report["valid"] else 1
        parser.error("choose intake or verify-package, or use --selftest")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
