#!/usr/bin/env python3
"""Profile-aware project scaffold, inventory, migration, apply, and rollback.

The source project is read-only during ``intake``.  Mutation is available only
through ``apply`` with an authorization document bound to the exact plan.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
PROFILE_FILE = SKILL_ROOT / "references" / "structure-profiles.json"
sys.path.insert(0, str(HERE))
from structure_governance_gate import (  # noqa: E402
    SCHEMA_ID as GOVERNANCE_SCHEMA,
    environment_doctor,
    validate as validate_governance,
)

SCHEMA_VERSION = "light.project-structure.v2"
HASH_CHUNK = 1024 * 1024
DEFAULT_LARGE_BYTES = 10 * 1024 * 1024
SCAN_MAX_BYTES = 1024 * 1024
SKIP_DIRS = {".git", ".dvc", ".venv", "venv", "node_modules", "__pycache__"}
SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_marker", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "named_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|client_secret)"
            r"\b\s*[:=]\s*['\"]?([^'\"\s#]{8,})"
        ),
    ),
)
TEMPLATE_RESIDUAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cookiecutter_or_jinja", re.compile(r"{{\s*[^}]+?\s*}}")),
    ("copier_placeholder", re.compile(r"\[\[\s*[^]]+?\s*\]\]")),
    ("shell_project_name", re.compile(r"\$\{PROJECT_NAME\}")),
    ("angle_project_name", re.compile(r"<PROJECT_NAME>")),
    ("dunder_project_name", re.compile(r"__PROJECT_NAME__")),
    ("template_todo", re.compile(r"\bTODO_TEMPLATE\b")),
)
PLACEHOLDER_TEXT_RE = re.compile(
    r"(?:"
    r"^unknown$|^todo$|^tbd$|^none$|^n/?a$|"
    r"user[-_ ]?supplied|replace[-_ ]?me|placeholder|"
    r"<[^>]+>|\{\{[^}]+\}\}|\$\{[^}]+\}"
    r")",
    re.I,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根必须是 object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def canonical_digest(value: dict[str, Any], omit: str | None = None) -> str:
    payload = {k: v for k, v in value.items() if k != omit}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是 YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} 必须是严格 YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} 必须是严格 YYYY-MM-DD")
    return parsed


def real_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not PLACEHOLDER_TEXT_RE.search(value.strip())
    )


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(
    root: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git_context(root: Path) -> dict[str, Any]:
    if not shutil.which("git"):
        return {"available": False, "reason": "git executable unavailable"}
    top = run_git(root, "rev-parse", "--show-toplevel")
    if top.returncode:
        return {"available": False, "reason": "not a git work tree"}
    git_root = Path(top.stdout.strip()).resolve()
    try:
        scope = root.relative_to(git_root).as_posix()
    except ValueError:
        return {"available": False, "reason": "resolved root is outside git root"}
    branch = (
        run_git(git_root, "branch", "--show-current").stdout.strip()
        or "DETACHED_OR_UNBORN"
    )
    status_args = ["status", "--short", "--untracked-files=all"]
    if scope != ".":
        status_args += ["--", scope]
    status = run_git(git_root, *status_args).stdout.splitlines()
    submodules = run_git(git_root, "submodule", "status", "--recursive")
    return {
        "available": True,
        "git_root": str(git_root),
        "scope": scope,
        "branch": branch,
        "status_short": status,
        "has_uncommitted_changes": bool(status),
        "submodules": submodules.stdout.splitlines()
        if not submodules.returncode
        else [],
    }


def git_paths(ctx: dict[str, Any], mode: str) -> set[str]:
    if not ctx.get("available"):
        return set()
    git_root = Path(ctx["git_root"])
    scope = ctx["scope"]
    args = ["ls-files", "-z"]
    if mode == "tracked":
        args += ["--cached"]
    elif mode == "untracked":
        args += ["--others", "--exclude-standard"]
    elif mode == "ignored":
        args += ["--others", "--ignored", "--exclude-standard"]
    else:
        raise ValueError(mode)
    if scope != ".":
        args += ["--", scope]
    proc = run_git(git_root, *args)
    if proc.returncode:
        return set()
    result: set[str] = set()
    prefix = "" if scope == "." else scope.rstrip("/") + "/"
    for item in proc.stdout.split("\0"):
        item = item.replace("\\", "/")
        if not item:
            continue
        if prefix and item.startswith(prefix):
            item = item[len(prefix) :]
        result.add(item)
    return result


def iter_entries(root: Path) -> Iterable[Path]:
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(dirnames):
            path = current_path / name
            if name in SKIP_DIRS:
                continue
            if path.is_symlink():
                yield path
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            yield current_path / name


def is_sensitive(rel: str) -> bool:
    path = Path(rel)
    lower = path.name.lower()
    return (
        lower in SENSITIVE_NAMES
        or path.suffix.lower() in SENSITIVE_SUFFIXES
        or any(part.lower() in {"secrets", "credentials"} for part in path.parts)
    )


def redacted_fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def text_for_scan(path: Path, size: int | None) -> tuple[str | None, str | None]:
    if size is not None and size > SCAN_MAX_BYTES:
        return None, "skipped-large"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"unreadable:{exc}"
    if b"\x00" in raw[:8192]:
        return None, "binary"
    return raw.decode("utf-8", errors="replace"), None


def scan_secret_report(
    root: Path, inventory: list[dict[str, Any]]
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for item in inventory:
        rel = str(item.get("locator") or "")
        if item.get("kind") != "file" or not rel:
            continue
        if is_sensitive(rel):
            findings.append(
                {
                    "locator": rel,
                    "kind": "sensitive_path",
                    "status": "BLOCKED",
                    "redacted_fingerprint": redacted_fingerprint(rel),
                    "detail": "Path name suggests credentials or secrets; review outside the report.",
                }
            )
        text, skipped = text_for_scan(root / rel, item.get("size"))
        if text is None:
            if skipped not in {None, "binary", "skipped-large"}:
                findings.append(
                    {
                        "locator": rel,
                        "kind": "scan_unavailable",
                        "status": "BLOCKED",
                        "redacted_fingerprint": redacted_fingerprint(f"{rel}:{skipped}"),
                        "detail": "File could not be scanned; do not assume it is safe.",
                    }
                )
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    findings.append(
                        {
                            "locator": rel,
                            "line": line_no,
                            "kind": kind,
                            "status": "BLOCKED",
                            "redacted_fingerprint": redacted_fingerprint(
                                match.group(0)
                            ),
                            "detail": "Potential secret-like value found; raw value is not reported.",
                        }
                    )
    return {
        "schema": f"{SCHEMA_VERSION}.secret-scan",
        "created_at": now(),
        "performed": True,
        "raw_values_in_report": False,
        "findings": findings,
        "limitations": [
            "standard-library heuristic scan only; absence of findings is not a security guarantee",
            "large and binary files are not content-scanned",
        ],
    }


def scan_template_residuals(
    root: Path, inventory: list[dict[str, Any]]
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for item in inventory:
        rel = str(item.get("locator") or "")
        if item.get("kind") != "file" or not rel:
            continue
        text, _skipped = text_for_scan(root / rel, item.get("size"))
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in TEMPLATE_RESIDUAL_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "locator": rel,
                            "line": line_no,
                            "kind": kind,
                            "status": "OPEN",
                            "detail": "Template placeholder-like residue needs review.",
                        }
                    )
    return {
        "schema": f"{SCHEMA_VERSION}.template-residual-scan",
        "created_at": now(),
        "performed": True,
        "findings": findings,
        "limitations": [
            "heuristic placeholder scan; examples may be accepted only with an explicit decision"
        ],
    }


def normalize_words(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = [str(item) for item in value]
    elif isinstance(value, str):
        lowered = value.strip().lower().replace("-", "_")
        if lowered in {"none", "not_required", "not required"}:
            return ["not_required"]
        raw = re.split(r"[,;/|+\s]+", value)
    else:
        return []
    out: list[str] = []
    for item in raw:
        cleaned = item.strip().lower().replace(" ", "-")
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def declared_artifact_types(policy: dict[str, Any]) -> list[str]:
    """Return explicit policy types only; never infer evidence from the selection."""
    project = policy.get("project", {})
    explicit = normalize_words(project.get("artifact_types"))
    return explicit


def detect_technology_signatures(
    inventory: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    exact: dict[str, tuple[str, str]] = {
        "pyproject.toml": ("python", "python-project-marker"),
        "requirements.txt": ("python", "python-project-marker"),
        "setup.py": ("python", "python-project-marker"),
        "setup.cfg": ("python", "python-project-marker"),
        "poetry.lock": ("python", "python-lockfile"),
        "uv.lock": ("python", "python-lockfile"),
        "description": ("r", "r-package-marker"),
        "renv.lock": ("r", "r-lockfile"),
        "package.json": ("code", "javascript-project-marker"),
        "pnpm-workspace.yaml": ("code", "monorepo-marker"),
        "nx.json": ("code", "monorepo-marker"),
        "turbo.json": ("code", "monorepo-marker"),
        "lerna.json": ("code", "monorepo-marker"),
    }
    suffixes: tuple[tuple[str, str, str], ...] = (
        (".py", "python", "python-source"),
        (".r", "r", "r-source"),
        (".rmd", "r", "r-markdown"),
        (".rproj", "r", "r-project-marker"),
        (".tex", "paper", "latex-source"),
        (".bib", "paper", "bibliography"),
        (".qmd", "paper", "quarto-source"),
        (".ipynb", "code", "notebook"),
        (".js", "code", "javascript-source"),
        (".jsx", "code", "javascript-source"),
        (".ts", "code", "typescript-source"),
        (".tsx", "code", "typescript-source"),
        (".jl", "code", "julia-source"),
        (".m", "code", "matlab-or-objc-source"),
        (".csv", "data", "tabular-data"),
        (".tsv", "data", "tabular-data"),
        (".parquet", "data", "columnar-data"),
        (".feather", "data", "columnar-data"),
        (".xlsx", "data", "spreadsheet-data"),
        (".sav", "data", "statistical-data"),
        (".dta", "data", "statistical-data"),
    )
    signals: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in inventory:
        if item.get("kind") != "file":
            continue
        locator = str(item.get("locator") or "")
        name = Path(locator).name.lower()
        matches: list[tuple[str, str]] = []
        if name in exact:
            matches.append(exact[name])
        matches.extend(
            (artifact_type, indicator)
            for suffix, artifact_type, indicator in suffixes
            if name.endswith(suffix)
        )
        for artifact_type, indicator in matches:
            key = (artifact_type, locator, indicator)
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                {
                    "artifact_type": artifact_type,
                    "locator": locator,
                    "indicator": indicator,
                    "source": "observed",
                }
            )
    observed = sorted({item["artifact_type"] for item in signals})
    declared = declared_artifact_types(policy)
    effective = sorted(
        {
            item
            for item in [*observed, *declared]
            if item not in {"", "unknown", "not_required"}
        }
    )
    has_python = "python" in effective
    has_r = "r" in effective
    unsupported_code = "code" in effective and not (has_python or has_r)
    if has_python and has_r:
        recommended = "mixed-research"
        rationale = "observed/declared Python and R artifacts require a mixed profile"
    elif has_python:
        recommended = "python-research"
        rationale = "observed/declared Python artifacts support the Python minimum"
    elif has_r:
        recommended = "r-research"
        rationale = "observed/declared R artifacts support the R minimum"
    elif effective == ["paper"]:
        recommended = "paper-only"
        rationale = "only manuscript artifacts were observed or declared"
    else:
        recommended = "existing-custom"
        rationale = (
            "signals are absent, data-only, or outside the built-in Python/R/paper profiles"
            if not unsupported_code
            else "non-Python/R code requires preserving the existing custom structure"
        )
    return {
        "schema": f"{SCHEMA_VERSION}.technology-signatures",
        "created_at": now(),
        "observed_artifact_types": observed,
        "declared_artifact_types": declared,
        "effective_artifact_types": effective or ["unknown"],
        "signals": signals,
        "recommended_profile": recommended,
        "recommendation_reason": rationale,
        "limitations": [
            "filename/config signatures do not prove runtime language, architecture, or intended ownership",
            "policy declarations remain user evidence and are kept separate from observed signals",
        ],
    }


def required_tools_for(
    profile: dict[str, Any],
    policy: dict[str, Any],
    signatures: dict[str, Any] | None = None,
) -> list[str]:
    project = policy.get("project", {})
    explicit = normalize_words(
        project.get("required_tools")
        or project.get("tools")
        or project.get("local_tools")
    )
    if explicit:
        return explicit
    tools: list[str] = []
    artifact_types = set(
        (signatures or {}).get("effective_artifact_types")
        or declared_artifact_types(policy)
    )
    if "python" in artifact_types:
        tools.append("python")
    if "r" in artifact_types:
        tools.append("r")
    project_text = json.dumps(project, ensure_ascii=False).lower()
    for marker, tool in (
        ("quarto", "quarto"),
        ("latex", "latex"),
        ("tex", "latex"),
        ("dvc", "dvc"),
    ):
        if marker in project_text and tool not in tools:
            tools.append(tool)
    return tools or ["not_required"]


def build_profile_reason(
    profile: dict[str, Any],
    policy: dict[str, Any],
    signatures: dict[str, Any],
) -> dict[str, Any]:
    project = policy.get("project", {})
    selected = profile["name"]
    recommended = str(signatures["recommended_profile"])
    explicit_reason = project.get("profile_selection_reason")
    override_reason = (
        explicit_reason
        if selected != recommended and real_text(explicit_reason)
        else None
    )
    reason_source = (
        "policy.project.profile_selection_reason"
        if real_text(explicit_reason)
        else "observed-and-declared-signatures"
    )
    why_minimal = (
        explicit_reason
        if real_text(explicit_reason)
        else signatures["recommendation_reason"]
        if selected == recommended
        else "UNKNOWN"
    )
    return {
        "artifact_types": signatures["effective_artifact_types"],
        "artifact_evidence": signatures["signals"]
        + [
            {
                "artifact_type": item,
                "locator": "policy.project.artifact_types",
                "indicator": "user-declared",
                "source": "policy",
            }
            for item in signatures["declared_artifact_types"]
        ],
        "team_scale": project.get("team_scale")
        or project.get("collaborators")
        or "UNKNOWN",
        "why_minimal": why_minimal,
        "reason_source": reason_source,
        "rejected_profiles": [
            {
                "profile": name,
                "reason": (
                    "not selected by the signature recommendation rule"
                    if name != recommended
                    else "recommended but explicitly overridden"
                ),
            }
            for name in sorted(load_profiles()["profiles"])
            if name != selected
        ],
        "profile_recommendation": {
            "recommended_profile": recommended,
            "selected_matches": selected == recommended,
            "override_reason": override_reason,
        },
        "fixed_tree_imposed": False,
    }


def light_preserved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    def subset(snapshot_value: dict[str, Any], key: str) -> dict[str, str]:
        return {
            locator: digest
            for locator, digest in snapshot_value.get(key, {}).items()
            if locator == ".light" or locator.startswith(".light/")
        }

    return subset(before, "files") == subset(after, "files") and subset(
        before, "symlinks"
    ) == subset(after, "symlinks")


def governance_payload(
    *,
    profile: dict[str, Any],
    policy: dict[str, Any],
    inventory: list[dict[str, Any]],
    plan: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    template_scan: dict[str, Any],
    secret_scan: dict[str, Any],
    environment: dict[str, Any],
    signatures: dict[str, Any],
) -> dict[str, Any]:
    inventory_by_locator = {item["locator"]: item for item in inventory}
    actions: list[dict[str, Any]] = []
    for action in plan.get("actions", []):
        source = str(action.get("source") or "")
        source_item = inventory_by_locator.get(source, {})
        blockers = [str(x).lower() for x in action.get("blockers", [])]
        target_exists = any("target already exists" in item for item in blockers)
        actions.append(
            {
                "id": action.get("id"),
                "kind": action.get("kind"),
                "source": source,
                "target": action.get("target"),
                "blocked": bool(action.get("blocked")),
                "overwrite": target_exists,
                "target_exists": target_exists,
                "symlink": source_item.get("kind") == "symlink",
                "auto_apply": False,
            }
        )
    return {
        "schema": GOVERNANCE_SCHEMA,
        "mode": "intake",
        "project": {
            "selected_profile": profile["name"],
            "profile_reason": build_profile_reason(profile, policy, signatures),
        },
        "existing_project": {
            "present": True,
            "inventory_read_only": True,
            "source_unchanged": before == after,
            "untracked_preserved": before.get("git_status_short")
            == after.get("git_status_short"),
            "light_preserved": light_preserved(before, after),
        },
        "template": {
            "used": False,
            "residual_scan": template_scan,
        },
        "secret_scan": secret_scan,
        "environment_doctor": environment,
        "plan": {
            "plan_sha256": plan.get("plan_sha256"),
            "force": False,
            "actions": actions,
        },
        "authorization": {},
        "rollback": {
            "manifest_available": False,
            "verified_hashes": False,
        },
    }


def load_profiles() -> dict[str, Any]:
    data = read_json(PROFILE_FILE)
    if data.get("schema") != "light.project-structure.profiles.v1":
        raise ValueError(f"未知 profile schema: {PROFILE_FILE}")
    return data


def normalize_profile(name: str) -> dict[str, Any]:
    profiles = load_profiles()["profiles"]
    if name not in profiles:
        raise ValueError(f"未知 profile {name!r}; 可选: {', '.join(sorted(profiles))}")
    return {"name": name, **profiles[name]}


def load_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema": "light.project-structure.policy.v1", "rules": []}
    policy = read_json(path)
    if policy.get("schema") != "light.project-structure.policy.v1":
        raise ValueError("policy.schema 必须是 light.project-structure.policy.v1")
    if not isinstance(policy.get("rules", []), list):
        raise ValueError("policy.rules 必须是 array")
    return policy


def policy_for(rel: str, size: int | None, policy: dict[str, Any]) -> dict[str, Any]:
    base = {
        "owner": "UNKNOWN",
        "producer": "UNKNOWN",
        "recomputability": "UNKNOWN",
        "sensitivity": "sensitive-path" if is_sensitive(rel) else "UNKNOWN",
        "classification": "UNKNOWN",
        "git_policy": "UNKNOWN",
        "target": "UNKNOWN",
        "basis": "no matching explicit policy rule",
    }
    for index, rule in enumerate(policy.get("rules", [])):
        glob = rule.get("glob")
        if not isinstance(glob, str) or not fnmatch.fnmatchcase(rel, glob):
            continue
        max_bytes = rule.get("max_bytes")
        min_bytes = rule.get("min_bytes")
        if isinstance(max_bytes, int) and size is not None and size > max_bytes:
            continue
        if isinstance(min_bytes, int) and size is not None and size < min_bytes:
            continue
        for key in (
            "owner",
            "producer",
            "recomputability",
            "sensitivity",
            "classification",
            "git_policy",
            "target",
        ):
            if key in rule:
                base[key] = rule[key]
        base["basis"] = f"policy.rules[{index}] glob={glob}"
        break
    if rel == ".light" or rel.startswith(".light/"):
        base.update(
            {
                "owner": "memory-pm",
                "classification": "memory-ledger",
                "git_policy": "preserve",
                "target": rel,
                "basis": "cross-skill ownership: memory-pm owns .light contents",
            }
        )
    return base


def classify_state(
    rel: str,
    ctx: dict[str, Any],
    tracked: set[str],
    untracked: set[str],
    ignored: set[str],
) -> str:
    if not ctx.get("available"):
        return "git-unavailable"
    if rel in tracked:
        return "tracked"
    if rel in untracked:
        return "untracked"
    if rel in ignored:
        return "ignored"
    return "unclassified"


def safe_locator(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def build_inventory(
    root: Path, ctx: dict[str, Any], policy: dict[str, Any], large_bytes: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tracked = git_paths(ctx, "tracked")
    untracked = git_paths(ctx, "untracked")
    ignored = git_paths(ctx, "ignored")
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for path in iter_entries(root):
        rel = safe_locator(root, path)
        symlink = path.is_symlink()
        size: int | None = None
        digest = "NOT_HASHED"
        link_target: str | None = None
        if symlink:
            try:
                link_target = os.readlink(path)
            except OSError:
                link_target = "UNREADABLE"
        elif path.is_file():
            try:
                size = path.stat().st_size
                digest = hash_file(path)
            except OSError as exc:
                issues.append(
                    {"kind": "unreadable", "locator": rel, "detail": str(exc)}
                )
        else:
            continue
        applied_policy = policy_for(rel, size, policy)
        state = classify_state(rel, ctx, tracked, untracked, ignored)
        item = {
            "locator": rel,
            "kind": "symlink" if symlink else "file",
            "symlink_target": link_target,
            "sha256": digest,
            "size": size,
            "large": bool(size is not None and size >= large_bytes),
            "tracked_state": state,
            **applied_policy,
        }
        items.append(item)
        if symlink:
            issues.append(
                {
                    "kind": "symlink",
                    "locator": rel,
                    "detail": "inventory records link; automatic move is blocked",
                }
            )
        if (
            item["large"]
            and item["classification"] != "memory-ledger"
            and item["git_policy"] in {"track", "preserve", "UNKNOWN"}
        ):
            issues.append(
                {
                    "kind": "large-policy-review",
                    "locator": rel,
                    "detail": f"{size} bytes; choose Git, DVC/object storage, or retention policy",
                }
            )
        if state == "tracked" and item["git_policy"] in {
            "dvc",
            "object-storage",
            "untrack",
        }:
            issues.append(
                {
                    "kind": "tracked-policy-conflict",
                    "locator": rel,
                    "detail": f"tracked but policy requires {item['git_policy']}",
                }
            )
    return items, issues


def target_for(item: dict[str, Any]) -> str | None:
    target = item.get("target")
    if not isinstance(target, str) or target in {"", "UNKNOWN"}:
        return None
    if target.endswith("/"):
        return target + Path(item["locator"]).name
    return target


def target_stays_inside(root: Path, target: str) -> bool:
    if Path(target).is_absolute():
        return False
    candidate = (root / target).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def build_plan(
    root: Path, inventory: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = list(issues)
    seen_targets: dict[str, str] = {}
    hash_groups: dict[str, list[str]] = {}
    for item in inventory:
        if item["kind"] == "file" and item["sha256"] != "NOT_HASHED":
            hash_groups.setdefault(item["sha256"], []).append(item["locator"])
    for digest, locators in hash_groups.items():
        if len(locators) > 1:
            conflicts.append(
                {
                    "kind": "duplicate-content",
                    "sha256": digest,
                    "locators": sorted(locators),
                    "detail": "duplicate is evidence only; never auto-delete",
                }
            )
    for item in inventory:
        target = target_for(item)
        if not target or target == item["locator"]:
            continue
        action_id = f"move-{len(actions) + 1:04d}"
        action = {
            "id": action_id,
            "kind": "move",
            "source": item["locator"],
            "target": target.replace("\\", "/"),
            "before_sha256": item["sha256"],
            "tracked_state": item["tracked_state"],
            "policy_basis": item["basis"],
            "blocked": False,
            "blockers": [],
        }
        if item["kind"] == "symlink":
            action["blocked"] = True
            action["blockers"].append(
                "symlink move requires a separate explicit manual plan"
            )
        if not target_stays_inside(root, action["target"]):
            action["blocked"] = True
            action["blockers"].append(
                "target path escapes the selected project root"
            )
            conflicts.append(
                {
                    "kind": "target-escape",
                    "action_id": action_id,
                    "source": item["locator"],
                    "target": action["target"],
                    "detail": "policy target must be a relative path inside the selected root",
                }
            )
        target_path = (root / action["target"]).resolve(strict=False)
        if target_stays_inside(root, action["target"]) and (
            target_path.exists() or target_path.is_symlink()
        ):
            action["blocked"] = True
            action["blockers"].append("target already exists; overwrite is forbidden")
            conflicts.append(
                {
                    "kind": "target-exists",
                    "action_id": action_id,
                    "source": item["locator"],
                    "target": action["target"],
                }
            )
        if action["target"] in seen_targets:
            action["blocked"] = True
            action["blockers"].append(
                f"same target as {seen_targets[action['target']]}"
            )
            conflicts.append(
                {
                    "kind": "many-to-one",
                    "action_id": action_id,
                    "other_action_id": seen_targets[action["target"]],
                    "target": action["target"],
                }
            )
        seen_targets[action["target"]] = action_id
        actions.append(action)
    plan = {
        "schema": f"{SCHEMA_VERSION}.migration-plan",
        "created_at": now(),
        "root": str(root),
        "mode": "dry-run",
        "actions": actions,
        "conflicts": conflicts,
        "expected_diff": [
            {"status": "R", "from": a["source"], "to": a["target"]}
            for a in actions
            if not a["blocked"]
        ],
        "authorization_required": True,
        "authorization_contract": {
            "schema": f"{SCHEMA_VERSION}.authorization",
            "authorization_id": "<user-created stable authorization id>",
            "plan_sha256": "copy migration_plan.plan_sha256",
            "approved_action_ids": ["choose after reviewing conflicts"],
            "authorized_by": "<user-supplied identifier>",
            "authorized_at": "<YYYY-MM-DD>",
        },
    }
    plan["plan_sha256"] = canonical_digest(plan, "plan_sha256")
    return plan


def build_audit(
    profile: dict[str, Any], inventory: list[dict[str, Any]], ctx: dict[str, Any]
) -> dict[str, Any]:
    locators = {item["locator"] for item in inventory}
    missing = [
        path
        for path in profile.get("recommended", [])
        if path.rstrip("/") not in locators
        and not any(loc.startswith(path.rstrip("/") + "/") for loc in locators)
    ]
    policy_findings: list[dict[str, Any]] = []
    for item in inventory:
        if item["tracked_state"] == "tracked" and item["git_policy"] in {
            "dvc",
            "object-storage",
            "untrack",
        }:
            policy_findings.append(
                {
                    "severity": "needs-decision",
                    "locator": item["locator"],
                    "rule": "tracked-vs-storage-policy",
                    "detail": f"explicit policy says {item['git_policy']}; do not run git rm automatically",
                }
            )
    return {
        "schema": f"{SCHEMA_VERSION}.structure-audit",
        "profile": profile["name"],
        "profile_is_minimum": True,
        "missing_recommended": missing,
        "policy_findings": policy_findings,
        "git_assurance": "available" if ctx.get("available") else "unavailable",
        "limitations": [
            "directory conformance does not prove data, experiment, paper, or reproducibility quality",
            "UNKNOWN policy fields require a user or project owner decision",
        ],
    }


def profile_questions(
    profile: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    supplied = policy.get("project", {})
    fields = [
        "project_type",
        "deliverables",
        "compute_environment",
        "data_volume",
        "remote_storage",
        "collaborators",
        "ci",
        "license",
        "retention",
    ]
    values = {field: supplied.get(field, "UNKNOWN") for field in fields}
    values["structure_profile"] = profile["name"]
    return values


def intake(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve(strict=True)
    out = Path(args.out).resolve()
    if not root.is_dir():
        raise ValueError(f"root 不是目录: {root}")
    profile = normalize_profile(args.profile)
    policy = load_policy(Path(args.policy).resolve() if args.policy else None)
    ctx = git_context(root)
    before = snapshot(root)
    inventory, issues = build_inventory(root, ctx, policy, args.large_bytes)
    plan = build_plan(root, inventory, issues)
    audit = build_audit(profile, inventory, ctx)
    template_scan = scan_template_residuals(root, inventory)
    secret_scan = scan_secret_report(root, inventory)
    signatures = detect_technology_signatures(inventory, policy)
    environment = environment_doctor(
        required_tools_for(profile, policy, signatures)
    )
    project_profile = {
        "schema": f"{SCHEMA_VERSION}.project-profile",
        "created_at": now(),
        "root": str(root),
        "repo_mode": (
            "non-git"
            if not ctx.get("available")
            else "monorepo-subroot"
            if ctx.get("scope") != "."
            else "git-root"
        ),
        "requirements": profile_questions(profile, policy),
        "technology_signatures": {
            "recommended_profile": signatures["recommended_profile"],
            "effective_artifact_types": signatures["effective_artifact_types"],
            "signal_count": len(signatures["signals"]),
        },
        "git": ctx,
    }
    unknown = [
        {
            "locator": item["locator"],
            "fields": [
                key
                for key in (
                    "owner",
                    "producer",
                    "recomputability",
                    "sensitivity",
                    "classification",
                    "git_policy",
                    "target",
                )
                if item.get(key) == "UNKNOWN"
            ],
        }
        for item in inventory
        if any(
            item.get(key) == "UNKNOWN"
            for key in (
                "owner",
                "producer",
                "recomputability",
                "sensitivity",
                "classification",
                "git_policy",
                "target",
            )
        )
    ]
    rollback = {
        "schema": f"{SCHEMA_VERSION}.rollback-plan",
        "status": "not-applicable-before-apply",
        "instruction": "After apply, run rollback with the emitted applied manifest.",
        "command": "python scaffold.py rollback --manifest <applied-manifest.json>",
    }
    out.mkdir(parents=True, exist_ok=True)
    after = snapshot(root)
    governance_input = governance_payload(
        profile=profile,
        policy=policy,
        inventory=inventory,
        plan=plan,
        before=before,
        after=after,
        template_scan=template_scan,
        secret_scan=secret_scan,
        environment=environment,
        signatures=signatures,
    )
    governance_report = validate_governance(governance_input)
    governance_report["input"] = governance_input
    write_json(out / "project-profile.json", project_profile)
    write_json(
        out / "source-inventory.json",
        {
            "schema": f"{SCHEMA_VERSION}.source-inventory",
            "created_at": now(),
            "root": str(root),
            "items": inventory,
        },
    )
    write_json(out / "structure-audit.json", audit)
    write_json(out / "migration-plan.json", plan)
    write_json(out / "technology-signatures.json", signatures)
    write_json(out / "environment-doctor.json", environment)
    write_json(out / "template-residual-scan.json", template_scan)
    write_json(out / "secret-scan.json", secret_scan)
    write_json(out / "governance-report.json", governance_report)
    write_json(
        out / "conflict-unknown-report.json",
        {
            "schema": f"{SCHEMA_VERSION}.conflict-unknown",
            "conflicts": plan["conflicts"],
            "unknowns": unknown,
        },
    )
    write_json(out / "rollback-plan.json", rollback)
    write_json(
        out / "intake-integrity.json",
        {
            "schema": f"{SCHEMA_VERSION}.intake-integrity",
            "before": before,
            "after": after,
            "source_unchanged": before == after,
        },
    )
    (out / "delivery.md").write_text(
        "# Project structure intake delivery\n\n"
        "- Source project mutation: none\n"
        f"- Profile: `{profile['name']}` (minimum, not a mandatory opinion tree)\n"
        f"- Signature recommendation: `{signatures['recommended_profile']}`\n"
        f"- Profile matches recommendation: {profile['name'] == signatures['recommended_profile']}\n"
        f"- Inventory items: {len(inventory)}\n"
        f"- Planned moves: {len(plan['actions'])}\n"
        f"- Blocked moves: {sum(bool(a['blocked']) for a in plan['actions'])}\n"
        f"- Secret-scan findings: {len(secret_scan['findings'])}\n"
        f"- Template residual findings: {len(template_scan['findings'])}\n"
        f"- Environment status: {governance_report['status']}\n"
        f"- Governance report: `{out / 'governance-report.json'}`\n"
        "- Apply requires a user-authored authorization bound to `plan_sha256`.\n"
        "- Structure conformance does not prove reproducibility or research quality.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[intake] source unchanged={before == after}; evidence={out}")
    print(f"[decision] review migration-plan.json; plan_sha256={plan['plan_sha256']}")
    return 0 if before == after else 3


def snapshot(root: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    for path in iter_entries(root):
        rel = safe_locator(root, path)
        if path.is_symlink():
            try:
                symlinks[rel] = os.readlink(path)
            except OSError:
                symlinks[rel] = "UNREADABLE"
        elif path.is_file():
            try:
                files[rel] = hash_file(path)
            except OSError:
                files[rel] = "UNREADABLE"
    ctx = git_context(root)
    return {
        "files": files,
        "symlinks": symlinks,
        "git_status_short": ctx.get("status_short", []),
    }


def ensure_inside(root: Path, rel: str) -> Path:
    candidate = (root / rel).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径越界: {rel}") from exc
    return candidate


def validate_authorization(
    plan: dict[str, Any], auth: dict[str, Any], as_of: date | None = None
) -> set[str]:
    cutoff = as_of or date.today()
    if auth.get("schema") != f"{SCHEMA_VERSION}.authorization":
        raise ValueError("authorization schema 不匹配")
    if not real_text(auth.get("authorization_id")):
        raise ValueError("authorization_id 必须是非占位的稳定标识")
    if auth.get("plan_sha256") != plan.get("plan_sha256"):
        raise ValueError("authorization 未绑定当前 plan_sha256")
    approved = auth.get("approved_action_ids")
    if (
        not isinstance(approved, list)
        or not approved
        or any(not real_text(item) for item in approved)
    ):
        raise ValueError("approved_action_ids 必须是非空且无占位值的 array")
    if len(set(approved)) != len(approved):
        raise ValueError("approved_action_ids 不得重复")
    known = {
        action.get("id")
        for action in plan.get("actions", [])
        if isinstance(action, dict)
    }
    unknown = set(approved) - known
    if unknown:
        raise ValueError(f"authorization 含未知 action: {sorted(unknown)}")
    if not real_text(auth.get("authorized_by")):
        raise ValueError("authorized_by 必须是非占位的用户标识")
    authorized_at = parse_date(auth.get("authorized_at"), "authorized_at")
    if authorized_at > cutoff:
        raise ValueError(f"authorized_at 不得晚于核验日 {cutoff.isoformat()}")
    return set(approved)


def apply_plan(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).resolve(strict=True)
    auth_path = Path(args.authorization).resolve(strict=True)
    plan = read_json(plan_path)
    if plan.get("schema") != f"{SCHEMA_VERSION}.migration-plan":
        raise ValueError("不是本脚本的 migration plan")
    if canonical_digest(plan, "plan_sha256") != plan.get("plan_sha256"):
        raise ValueError("migration plan digest 已变化")
    auth = read_json(auth_path)
    approved = validate_authorization(
        plan,
        auth,
        parse_date(args.as_of, "--as-of") if args.as_of else None,
    )
    root = Path(plan["root"]).resolve(strict=True)
    known = {action["id"] for action in plan["actions"]}
    extra = approved - known
    if extra:
        raise ValueError(f"authorization 含未知 action: {sorted(extra)}")
    selected = [a for a in plan["actions"] if a["id"] in approved]
    if any(a.get("blocked") for a in selected):
        blocked = [a["id"] for a in selected if a.get("blocked")]
        raise ValueError(f"blocked action 不可授权绕过: {blocked}")
    manifest_actions: list[dict[str, Any]] = []
    created_dirs: set[str] = set()
    for action in selected:
        source = ensure_inside(root, action["source"])
        target = ensure_inside(root, action["target"])
        if source.is_symlink():
            raise ValueError(f"拒绝移动 symlink: {action['source']}")
        if not source.is_file():
            raise ValueError(f"source 不存在或非普通文件: {action['source']}")
        before_hash = hash_file(source)
        if before_hash != action["before_sha256"]:
            raise ValueError(f"source hash 已变化: {action['source']}")
        if target.exists() or target.is_symlink():
            raise ValueError(f"目标已存在，绝不覆盖: {action['target']}")
        parent = target.parent
        missing: list[Path] = []
        cursor = parent
        while cursor != root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        parent.mkdir(parents=True, exist_ok=True)
        created_dirs.update(p.relative_to(root).as_posix() for p in missing)
        source.rename(target)
        after_hash = hash_file(target)
        if after_hash != before_hash:
            raise RuntimeError(f"移动后 hash 不一致: {action['id']}")
        manifest_actions.append(
            {
                "id": action["id"],
                "source": action["source"],
                "target": action["target"],
                "before_sha256": before_hash,
                "after_sha256": after_hash,
                "source_exists_after": source.exists(),
                "target_exists_after": target.exists(),
                "tracked_state_before": action["tracked_state"],
            }
        )
    manifest = {
        "schema": f"{SCHEMA_VERSION}.applied-manifest",
        "created_at": now(),
        "root": str(root),
        "plan_sha256": plan["plan_sha256"],
        "plan_binding": {
            "locator": str(plan_path),
            "file_sha256": hash_file(plan_path),
            "plan_sha256": plan["plan_sha256"],
        },
        "authorization_sha256": canonical_digest(auth),
        "authorization_binding": {
            "locator": str(auth_path),
            "file_sha256": hash_file(auth_path),
            "canonical_sha256": canonical_digest(auth),
            "authorization_id": auth["authorization_id"],
            "plan_sha256": auth["plan_sha256"],
            "approved_action_ids": sorted(approved),
        },
        "authorization_id": auth["authorization_id"],
        "authorized_by": auth["authorized_by"],
        "authorized_at": auth["authorized_at"],
        "actions": manifest_actions,
        "created_dirs": sorted(
            created_dirs, key=lambda x: len(Path(x).parts), reverse=True
        ),
        "rollback_command": f"python {Path(__file__).name} rollback --manifest {args.manifest_out}",
    }
    write_json(Path(args.manifest_out).resolve(), manifest)
    print(
        f"[apply] applied={len(manifest_actions)}; manifest={Path(args.manifest_out).resolve()}"
    )
    return 0


def rollback(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve(strict=True)
    manifest = read_json(manifest_path)
    if manifest.get("schema") != f"{SCHEMA_VERSION}.applied-manifest":
        raise ValueError("不是本脚本的 applied manifest")
    root = Path(manifest["root"]).resolve(strict=True)
    restored: list[dict[str, Any]] = []
    for action in reversed(manifest["actions"]):
        source = ensure_inside(root, action["source"])
        target = ensure_inside(root, action["target"])
        if source.exists() or source.is_symlink():
            raise ValueError(f"rollback source 已占用，拒绝覆盖: {action['source']}")
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"rollback target 缺失或非普通文件: {action['target']}")
        digest = hash_file(target)
        if digest != action["after_sha256"]:
            raise ValueError(f"rollback target hash 已变化: {action['target']}")
        source.parent.mkdir(parents=True, exist_ok=True)
        target.rename(source)
        restored_hash = hash_file(source)
        if restored_hash != action["before_sha256"]:
            raise RuntimeError(f"rollback hash 不一致: {action['id']}")
        restored.append(
            {
                "id": action["id"],
                "restored": action["source"],
                "sha256": restored_hash,
            }
        )
    for rel in manifest.get("created_dirs", []):
        path = ensure_inside(root, rel)
        try:
            path.rmdir()
        except OSError:
            pass
    out = (
        Path(args.rollback_out).resolve()
        if args.rollback_out
        else (manifest_path.parent / "rollback-manifest.json")
    )
    write_json(
        out,
        {
            "schema": f"{SCHEMA_VERSION}.rollback-manifest",
            "created_at": now(),
            "root": str(root),
            "restored": restored,
        },
    )
    print(f"[rollback] restored={len(restored)}; manifest={out}")
    return 0


def scaffold(args: argparse.Namespace) -> int:
    root = Path(args.target).resolve()
    profile = normalize_profile(args.profile)
    if root.exists() and any(root.iterdir()):
        print(
            "错误: scaffold 仅用于空目录；没有 --force 绕过。已有项目请先 intake。",
            file=sys.stderr,
        )
        return 2
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for rel in profile.get("scaffold", []):
        path = ensure_inside(root, rel)
        if rel.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
            (path / ".gitkeep").write_text("", encoding="utf-8")
            created.append(rel + ".gitkeep")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise ValueError(f"意外冲突: {rel}")
            path.write_text("", encoding="utf-8", newline="\n")
            created.append(rel)
    provenance = {
        "schema": f"{SCHEMA_VERSION}.template-provenance",
        "created_at": now(),
        "profile": profile["name"],
        "profile_source": str(PROFILE_FILE),
        "profile_sha256": hash_file(PROFILE_FILE),
        "parameters": {"name": args.name or root.name},
        "generator": str(Path(__file__).resolve()),
        "generator_sha256": hash_file(Path(__file__).resolve()),
        "local_modifications": [],
        "update_support": "none; use Copier/Cruft for managed template updates",
    }
    write_json(root / ".project-structure-provenance.json", provenance)
    print(f"[scaffold] profile={profile['name']}; created={len(created)}; root={root}")
    return 0


def selftest() -> int:
    e2e_root = SKILL_ROOT.parents[1] / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="light_project_structure_", dir=e2e_root
    ) as tmp:
        base = Path(tmp)
        repo = base / "messy"
        repo.mkdir()
        run_git(repo, "init", "-q")
        run_git(repo, "config", "user.name", "Self Test")
        run_git(repo, "config", "user.email", "selftest@example.invalid")
        (repo / ".light").mkdir()
        (repo / ".light" / "project_card.md").write_text(
            "memory-owned\n", encoding="utf-8"
        )
        (repo / "raw").mkdir()
        (repo / "raw" / "fixture.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        (repo / "old").mkdir()
        (repo / "old" / "analysis.py").write_text("print('ok')\n", encoding="utf-8")
        (repo / "old" / "escape.py").write_text("print('bad')\n", encoding="utf-8")
        (repo / "draft.md").write_text("untracked user draft\n", encoding="utf-8")
        run_git(
            repo,
            "add",
            ".light/project_card.md",
            "raw/fixture.csv",
            "old/analysis.py",
            "old/escape.py",
        )
        run_git(repo, "commit", "-qm", "fixture")
        policy_path = base / "policy.json"
        write_json(
            policy_path,
            {
                "schema": "light.project-structure.policy.v1",
                "project": {
                    "project_type": "Python research fixture",
                    "artifact_types": ["python", "data"],
                    "required_tools": ["python"],
                },
                "rules": [
                    {
                        "glob": "raw/fixture.csv",
                        "classification": "test-fixture",
                        "git_policy": "track",
                        "recomputability": "source",
                        "sensitivity": "public",
                        "target": "raw/fixture.csv",
                    },
                    {
                        "glob": "old/escape.py",
                        "classification": "source-code",
                        "git_policy": "track",
                        "recomputability": "source",
                        "sensitivity": "public",
                        "target": "../outside.py",
                    },
                    {
                        "glob": "old/*.py",
                        "classification": "source-code",
                        "git_policy": "track",
                        "recomputability": "source",
                        "sensitivity": "public",
                        "target": "src/",
                    },
                ],
            },
        )
        out = base / "evidence"
        args = argparse.Namespace(
            root=str(repo),
            out=str(out),
            profile="python-research",
            policy=str(policy_path),
            large_bytes=20,
        )
        before = snapshot(repo)
        assert intake(args) == 0
        assert snapshot(repo) == before
        for artifact in (
            "technology-signatures.json",
            "environment-doctor.json",
            "template-residual-scan.json",
            "secret-scan.json",
            "governance-report.json",
        ):
            assert (out / artifact).is_file(), artifact
        signatures = read_json(out / "technology-signatures.json")
        assert signatures["recommended_profile"] == "python-research", signatures
        assert {"python", "data"} <= set(
            signatures["effective_artifact_types"]
        ), signatures
        assert any(
            signal["locator"] == "old/analysis.py"
            and signal["artifact_type"] == "python"
            for signal in signatures["signals"]
        ), signatures
        observed_only = detect_technology_signatures(
            [
                {"kind": "file", "locator": "analysis/model.py"},
                {"kind": "file", "locator": "analysis/report.Rmd"},
                {"kind": "file", "locator": "paper/main.tex"},
            ],
            {"schema": "light.project-structure.policy.v1", "project": {}},
        )
        assert observed_only["declared_artifact_types"] == [], observed_only
        assert observed_only["recommended_profile"] == "mixed-research", observed_only
        assert {"python", "r", "paper"} <= set(
            observed_only["effective_artifact_types"]
        ), observed_only
        governance = read_json(out / "governance-report.json")
        assert governance["status"] == "FAIL", json.dumps(
            governance, ensure_ascii=False, indent=2
        )
        assert any(
            issue["code"] == "PATH_ESCAPE_PLANNED"
            for issue in governance["issues"]
        )
        assert governance["input"]["environment_doctor"]["required_tools"] == [
            "python"
        ]
        plan = read_json(out / "migration-plan.json")
        move = next(a for a in plan["actions"] if a["source"] == "old/analysis.py")
        escape = next(a for a in plan["actions"] if a["source"] == "old/escape.py")
        assert escape["blocked"] is True
        assert any("escapes" in reason for reason in escape["blockers"])
        assert any(
            conflict["kind"] == "target-escape"
            and conflict["action_id"] == escape["id"]
            for conflict in plan["conflicts"]
        )
        auth_path = base / "authorization.json"
        write_json(
            auth_path,
            {
                "schema": f"{SCHEMA_VERSION}.authorization",
                "authorization_id": "selftest-move-authorization",
                "plan_sha256": plan["plan_sha256"],
                "approved_action_ids": [move["id"]],
                "authorized_by": "selftest",
                "authorized_at": "2026-07-05",
            },
        )
        auth = read_json(auth_path)
        for field, value in (
            ("authorization_id", "<authorization-id>"),
            ("approved_action_ids", ["move-9999"]),
            ("authorized_by", "USER_SUPPLIED"),
            ("authorized_at", "2099-01-01"),
        ):
            invalid = dict(auth)
            invalid[field] = value
            try:
                validate_authorization(
                    plan, invalid, as_of=date.fromisoformat("2026-07-05")
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid authorization accepted: {field}")
        manifest_path = out / "applied-manifest.json"
        apply_args = argparse.Namespace(
            plan=str(out / "migration-plan.json"),
            authorization=str(auth_path),
            manifest_out=str(manifest_path),
            as_of="2026-07-05",
        )
        assert apply_plan(apply_args) == 0
        assert (repo / "src" / "analysis.py").is_file()
        assert (repo / "draft.md").read_text(
            encoding="utf-8"
        ) == "untracked user draft\n"
        assert (repo / ".light" / "project_card.md").read_text(
            encoding="utf-8"
        ) == "memory-owned\n"
        rb_args = argparse.Namespace(
            manifest=str(manifest_path),
            rollback_out=str(out / "rollback-manifest.json"),
        )
        assert rollback(rb_args) == 0
        assert snapshot(repo) == before
        assert apply_plan(apply_args) == 0
        # Secret/template scans report evidence without leaking raw values.
        dirty = base / "dirty"
        dirty.mkdir()
        (dirty / "README.md").write_text(
            "{{ cookiecutter.project_name }}\n", encoding="utf-8"
        )
        (dirty / ".env").write_text(
            "TOKEN=PLACEHOLDER_TEST_VALUE\n", encoding="utf-8"
        )
        dirty_out = base / "dirty-evidence"
        dirty_args = argparse.Namespace(
            root=str(dirty),
            out=str(dirty_out),
            profile="existing-custom",
            policy=None,
            large_bytes=DEFAULT_LARGE_BYTES,
        )
        assert intake(dirty_args) == 0
        dirty_secret = read_json(dirty_out / "secret-scan.json")
        assert dirty_secret["performed"] is True
        assert dirty_secret["raw_values_in_report"] is False
        assert any(item["kind"] == "sensitive_path" for item in dirty_secret["findings"])
        assert all("value" not in item for item in dirty_secret["findings"])
        dirty_template = read_json(dirty_out / "template-residual-scan.json")
        assert any(
            item["kind"] == "cookiecutter_or_jinja"
            for item in dirty_template["findings"]
        )
        # Non-git and monorepo-subroot honest modes.
        nongit = base / "nongit"
        nongit.mkdir()
        (nongit / "x.txt").write_text("x", encoding="utf-8")
        old_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(base)
        try:
            assert git_context(nongit)["available"] is False
        finally:
            if old_ceiling is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = old_ceiling
        mono = base / "mono"
        (mono / "packages" / "p").mkdir(parents=True)
        run_git(mono, "init", "-q")
        ctx = git_context(mono / "packages" / "p")
        assert ctx["available"] and ctx["scope"] == "packages/p"
        # Symlink path is tested when the platform permits it; otherwise report skip.
        link_test = "skipped"
        try:
            os.symlink(repo / "draft.md", repo / "draft-link")
            assert any(p.is_symlink() for p in iter_entries(repo))
            link_test = "passed"
        except (OSError, NotImplementedError):
            pass
        # Greenfield profiles are minimal and refuse non-empty overwrite.
        fresh = base / "fresh"
        sc_args = argparse.Namespace(
            target=str(fresh), profile="r-research", name="fresh"
        )
        assert scaffold(sc_args) == 0
        assert scaffold(sc_args) == 2
        print(f"[selftest] PASS lifecycle; symlink={link_test}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Profile-aware project structure lifecycle (safe by default)"
    )
    ap.add_argument(
        "--selftest", action="store_true", help="run offline end-to-end self-test"
    )
    sub = ap.add_subparsers(dest="command")
    p_scaffold = sub.add_parser(
        "scaffold", help="create a profile in an empty directory"
    )
    p_scaffold.add_argument("target")
    p_scaffold.add_argument("--profile", required=True)
    p_scaffold.add_argument("--name")
    p_intake = sub.add_parser(
        "intake", help="inventory source and write a dry-run plan"
    )
    p_intake.add_argument("root")
    p_intake.add_argument("--out", required=True)
    p_intake.add_argument("--profile", required=True)
    p_intake.add_argument("--policy")
    p_intake.add_argument("--large-bytes", type=int, default=DEFAULT_LARGE_BYTES)
    p_apply = sub.add_parser(
        "apply", help="apply explicitly authorized unblocked moves"
    )
    p_apply.add_argument("--plan", required=True)
    p_apply.add_argument("--authorization", required=True)
    p_apply.add_argument("--manifest-out", required=True)
    p_apply.add_argument(
        "--as-of",
        help="authorization cutoff date (YYYY-MM-DD; default: local today)",
    )
    p_rollback = sub.add_parser("rollback", help="reverse an applied manifest")
    p_rollback.add_argument("--manifest", required=True)
    p_rollback.add_argument("--rollback-out")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.command == "scaffold":
            return scaffold(args)
        if args.command == "intake":
            return intake(args)
        if args.command == "apply":
            return apply_plan(args)
        if args.command == "rollback":
            return rollback(args)
        ap.error("choose scaffold, intake, apply, rollback, or --selftest")
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
