#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a source-code deposit plan for China software copyright materials.

The script inventories real project source files, estimates page mode, computes
SHA-256 hashes and performs a lightweight secret scan. It does not fabricate or
extract source material; the model/user must confirm the final selection before
formal export.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.software_copyright.source_deposit_plan.v1"
LINES_PER_PAGE = 50
SPLIT_THRESHOLD_PAGES = 60
MAX_FILE_BYTES = 900_000

CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".java", ".kt", ".go",
    ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".swift",
    ".m", ".mm", ".dart", ".scala", ".sql", ".html", ".css", ".scss", ".less",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".sh", ".ps1", ".bat",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", "vendor", "third_party", "软件著作权申请资料",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "go.sum",
}
SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("api_key_assignment", re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("connection_string", re.compile(r"(?i)\b(mysql|postgres|mongodb|redis)://[^@\s]+:[^@\s]+@")),
]


def repo_root(start: str | pathlib.Path | None = None) -> pathlib.Path:
    cur = pathlib.Path(start or __file__).resolve()
    if cur.is_file():
        cur = cur.parent
    while cur != cur.parent and not (cur / "skills").is_dir():
        cur = cur.parent
    if not (cur / "skills").is_dir():
        raise RuntimeError("Light-Skills repository root not found")
    return cur


def file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def looks_binary(path: pathlib.Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in chunk


def material_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def priority_for(path: pathlib.Path, root: pathlib.Path) -> tuple[int, str]:
    r = rel(path, root).lower()
    name = path.name.lower()
    if name in {"main.ts", "main.js", "main.tsx", "main.jsx", "app.vue", "app.tsx", "app.py"}:
        return 0, "entry"
    if "/router/" in r or "/routes/" in r or "router." in r or "routes." in r:
        return 10, "route"
    if "/pages/" in r or "/views/" in r or "/screens/" in r or "/app/" in r:
        return 20, "page"
    if "/api/" in r or "/apis/" in r or "/services/" in r or "request." in r:
        return 30, "api-service"
    if "/store/" in r or "/stores/" in r or "/redux/" in r or "/pinia/" in r:
        return 40, "state"
    if "/components/" in r:
        return 50, "component"
    if "/utils/" in r or "/lib/" in r or "/hooks/" in r or "/composables/" in r:
        return 60, "utility"
    if "/server/" in r or "/models/" in r or "/schemas/" in r or "/workers/" in r:
        return 70, "backend-core"
    if path.suffix.lower() in {".css", ".scss", ".less"}:
        return 90, "style"
    return 80, "source"


def should_skip(path: pathlib.Path, root: pathlib.Path) -> bool:
    parts = set(path.resolve().relative_to(root.resolve()).parts)
    if parts & SKIP_DIRS:
        return True
    if path.name.lower() in SKIP_FILES:
        return True
    if path.suffix.lower() not in CODE_EXTS:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size <= 0 or size > MAX_FILE_BYTES:
        return True
    return looks_binary(path)


def iter_source_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if should_skip(path, root):
                continue
        except ValueError:
            continue
        files.append(path)
    files.sort(key=lambda p: (*priority_for(p, root), rel(p, root)))
    return files


def secret_findings(path: pathlib.Path, root: pathlib.Path, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append({"path": rel(path, root), "line": line_no, "kind": kind})
    return findings


def build_plan(root: pathlib.Path, software_name: str | None, version: str | None, max_files: int) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"project root not found: {root}")
    candidates: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        nonblank = material_lines(text)
        priority, tier = priority_for(path, root)
        item = {
            "path": rel(path, root),
            "sha256": file_sha256(path),
            "line_count": len(lines),
            "material_line_count": len(nonblank),
            "estimated_pages": math.ceil(max(1, len(nonblank)) / LINES_PER_PAGE),
            "priority": priority,
            "selection_tier": tier,
            "recommended": False,
            "model_reason": "",
        }
        candidates.append(item)
        findings.extend(secret_findings(path, root, text))
        if max_files and len(candidates) >= max_files:
            break

    recommended_lines = 0
    recommended_count = 0
    for item in candidates:
        if item["material_line_count"] <= 0:
            continue
        item["recommended"] = True
        item["model_reason"] = f"候选 {item['selection_tier']} 源码，可体现软件真实功能或运行逻辑；需用户确认。"
        recommended_lines += int(item["material_line_count"]) + 1
        recommended_count += 1
        if math.ceil(recommended_lines / LINES_PER_PAGE) >= SPLIT_THRESHOLD_PAGES:
            break

    total_lines = sum(int(item["material_line_count"]) + 1 for item in candidates if item["material_line_count"] > 0)
    recommended_pages = math.ceil(recommended_lines / LINES_PER_PAGE) if recommended_lines else 0
    all_pages = math.ceil(total_lines / LINES_PER_PAGE) if total_lines else 0
    deposit_mode = "front_back_30" if recommended_pages >= SPLIT_THRESHOLD_PAGES else "all_source"
    secret_status = "FOUND" if findings else "PASS"

    return {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "project_root_name": root.name,
        "software_name": software_name or "",
        "version": version or "",
        "line_policy": {
            "source_lines_per_page": LINES_PER_PAGE,
            "split_threshold_pages": SPLIT_THRESHOLD_PAGES,
        },
        "source_summary": {
            "candidate_file_count": len(candidates),
            "all_candidate_material_lines": total_lines,
            "all_candidate_estimated_pages": all_pages,
            "recommended_file_count": recommended_count,
            "recommended_material_lines": recommended_lines,
            "recommended_estimated_pages": recommended_pages,
            "deposit_mode": deposit_mode,
        },
        "secret_scan": {
            "status": secret_status,
            "finding_count": len(findings),
            "findings": findings[:100],
            "truncated": len(findings) > 100,
        },
        "candidate_files": candidates,
        "selection_required": True,
        "confirmation_required": True,
        "confirmed": False,
        "next_action": (
            "由模型阅读业务理解与候选源码，必要时调整 recommended/model_reason；"
            "用户确认后，将确认记录和本计划 SHA 写入 materials packet。"
        ),
    }


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_selftest() -> int:
    root = repo_root()
    e2e_root = root / ".upgrade" / "_e2e" / "software-copyright-source-plan"
    e2e_root.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="selftest-", dir=e2e_root))
    try:
        clean = tmp / "clean-project"
        (clean / "src" / "app").mkdir(parents=True)
        (clean / "src" / "app" / "page.tsx").write_text("\n".join(f"export const row{i} = {i};" for i in range(120)), encoding="utf-8")
        (clean / "src" / "services").mkdir()
        (clean / "src" / "services" / "api.ts").write_text("\n".join(f"export function api{i}() {{ return {i}; }}" for i in range(80)), encoding="utf-8")
        (clean / "node_modules").mkdir()
        (clean / "node_modules" / "ignored.js").write_text("should not be scanned\n", encoding="utf-8")

        clean_plan = build_plan(clean, "LightDemo", "V1.0", 0)
        out = tmp / "plan.json"
        write_json(out, clean_plan)

        secret = tmp / "secret-project"
        (secret / "src").mkdir(parents=True)
        (secret / "src" / "main.py").write_text('api_key = "sk-test-secret-value"\nprint(api_key)\n', encoding="utf-8")
        secret_plan = build_plan(secret, "SecretDemo", "V1.0", 0)

        checks = [
            (clean_plan["schema"] == SCHEMA, "schema emitted"),
            (clean_plan["secret_scan"]["status"] == "PASS", "clean project passes secret scan"),
            (clean_plan["source_summary"]["candidate_file_count"] == 2, "dependency/build directories skipped"),
            (clean_plan["source_summary"]["recommended_file_count"] > 0, "recommended source candidates produced"),
            (out.is_file() and out.stat().st_size > 0, "plan JSON written"),
            (secret_plan["secret_scan"]["status"] == "FOUND", "secret-like assignment is detected"),
        ]
        ok = True
        for passed, label in checks:
            ok &= passed
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Light software-copyright source deposit plan")
    parser.add_argument("--root", type=pathlib.Path, help="project root to scan")
    parser.add_argument("--out", type=pathlib.Path, help="output JSON path")
    parser.add_argument("--software-name", default="", help="confirmed or candidate software name")
    parser.add_argument("--version", default="", help="confirmed or candidate version")
    parser.add_argument("--max-files", type=int, default=0, help="limit candidate inventory for very large projects")
    parser.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.root is None:
        parser.error("--root is required unless --selftest is used")

    plan = build_plan(args.root, args.software_name, args.version, args.max_files)
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        write_json(args.out, plan)
        print(f"OK source deposit plan: {args.out}")
        print(f"sha256: {file_sha256(args.out)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
