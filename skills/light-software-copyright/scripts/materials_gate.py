#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate Chinese software copyright registration material evidence.

This gate checks provenance, page/line rules, version-name consistency and
confirmation stops. It does not submit materials and does not provide legal
advice.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.software_copyright.materials.v1"
REPORT_SCHEMA = "light.software_copyright.gate_report.v1"
SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(r"(<[^>]+>|\bTBD\b|\bTODO\b|待填|待补|示例|example)", re.I)
OVERCLAIM_RE = re.compile(
    r"(包过|保过|包下证|保证登记|可直接提交|自动提交|无需审查|ready\s*to\s*submit)",
    re.I,
)
SECRET_STATUS_ALLOWED = {"PASS", "REDACTED_AND_VERIFIED"}
SOURCE_PLAN_SCHEMA = "light.software_copyright.source_deposit_plan.v1"
RIGHTS_STATUS_ALLOWED = {"VERIFIED", "PLANNED", "UNKNOWN", "UNAVAILABLE"}
THIRD_PARTY_STATUS_ALLOWED = {"PASS", "REVIEWED_WITH_EXCLUSIONS"}
CONFIRMATION_KEYS = (
    "environment",
    "source_plan",
    "application_fields",
    "business_context",
    "code_selection",
    "markdown_draft",
    "final_export",
)
APPLICATION_FIELDS = (
    "software_full_name",
    "version",
    "copyright_owner",
    "development_completion_date",
    "first_publication_status",
    "development_mode",
)


def repo_root(start: str | pathlib.Path | None = None) -> pathlib.Path:
    cur = pathlib.Path(start or __file__).resolve()
    if cur.is_file():
        cur = cur.parent
    while cur != cur.parent and not (cur / "skills").is_dir():
        cur = cur.parent
    if not (cur / "skills").is_dir():
        raise RuntimeError("Light-Skills repository root not found")
    return cur


def issue(code: str, path: str, message: str, severity: str = "ERROR") -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}


def file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(strings(item))
        return out
    return []


def scalar_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.search(value)


def path_problem(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return "path must be a non-empty string"
    value = raw.strip()
    win = pathlib.PureWindowsPath(value)
    posix = pathlib.PurePosixPath(value)
    if win.is_absolute() or posix.is_absolute() or win.drive:
        return "path must be project-relative, not absolute"
    if value.startswith("~") or "\x00" in value:
        return "path contains unsafe prefix or null byte"
    if ".." in win.parts or ".." in posix.parts:
        return "path must not escape with '..'"
    if PLACEHOLDER_RE.search(value):
        return "path contains placeholder text"
    return None


def parse_date(value: Any, path: str, as_of: dt.date, problems: list[dict[str, str]]) -> dt.date | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(issue("DATE_MISSING", path, "date must be YYYY-MM-DD"))
        return None
    try:
        parsed = dt.date.fromisoformat(value[:10])
    except ValueError:
        problems.append(issue("DATE_INVALID", path, "date must be YYYY-MM-DD"))
        return None
    if parsed > as_of:
        problems.append(issue("DATE_IN_FUTURE", path, f"date {parsed.isoformat()} is after as_of"))
    return parsed


def validate_file_list(items: Any, base: pathlib.Path | None, path: str) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(items, list) or not items:
        return [issue("FILE_LIST_MISSING", path, "at least one file entry is required")]
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            problems.append(issue("FILE_ENTRY_INVALID", item_path, "file entry must be an object"))
            continue
        file_id = item.get("id")
        if scalar_ok(file_id):
            if str(file_id) in seen_ids:
                problems.append(issue("FILE_ID_DUPLICATE", f"{item_path}.id", "file ids must be unique"))
            seen_ids.add(str(file_id))
        else:
            problems.append(issue("FILE_ID_MISSING", f"{item_path}.id", "file id required"))
        locator = item.get("path")
        if problem := path_problem(locator):
            problems.append(issue("FILE_PATH_INVALID", f"{item_path}.path", problem))
            continue
        sha = item.get("sha256")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            problems.append(issue("FILE_HASH_INVALID", f"{item_path}.sha256", "sha256:<64 lowercase hex> required"))
        if base is not None and isinstance(locator, str):
            resolved = (base / locator).resolve()
            try:
                resolved.relative_to(base.resolve())
            except ValueError:
                problems.append(issue("FILE_PATH_ESCAPE", f"{item_path}.path", "resolved path escapes base"))
                continue
            if not resolved.is_file():
                problems.append(issue("FILE_MISSING", f"{item_path}.path", "referenced file does not exist"))
            elif isinstance(sha, str) and SHA_RE.match(sha) and file_sha256(resolved) != sha:
                problems.append(issue("FILE_HASH_MISMATCH", f"{item_path}.sha256", "sha256 does not match file"))
    return problems


def validate_confirmations(packet: dict[str, Any], as_of: dt.date) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    confirmations = packet.get("stage_confirmations")
    if not isinstance(confirmations, dict):
        return [issue("CONFIRMATIONS_MISSING", "stage_confirmations", "confirmation gates are required")]
    for key in CONFIRMATION_KEYS:
        path = f"stage_confirmations.{key}"
        item = confirmations.get(key)
        if not isinstance(item, dict):
            problems.append(issue("CONFIRMATION_MISSING", path, "confirmation object required"))
            continue
        if item.get("confirmed") is not True:
            problems.append(issue("CONFIRMATION_NOT_TRUE", f"{path}.confirmed", "must be true before formal export"))
        parse_date(item.get("confirmed_at"), f"{path}.confirmed_at", as_of, problems)
        if not scalar_ok(item.get("basis")):
            problems.append(issue("CONFIRMATION_BASIS_MISSING", f"{path}.basis", "basis/locator for user or maintainer confirmation required"))
    return problems


def validate_source_plan(packet: dict[str, Any], base: pathlib.Path | None) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    plan = packet.get("source_plan")
    if not isinstance(plan, dict):
        return [issue("SOURCE_PLAN_MISSING", "source_plan", "source deposit plan generated from real project source is required")]
    if plan.get("schema") != SOURCE_PLAN_SCHEMA:
        problems.append(issue("SOURCE_PLAN_SCHEMA_INVALID", "source_plan.schema", f"expected {SOURCE_PLAN_SCHEMA}"))
    plan_sha = plan.get("sha256")
    if not isinstance(plan_sha, str) or not SHA_RE.match(plan_sha):
        problems.append(issue("SOURCE_PLAN_HASH_MISSING", "source_plan.sha256", "source plan sha256 required"))
    if plan.get("confirmed") is not True:
        problems.append(issue("SOURCE_PLAN_UNCONFIRMED", "source_plan.confirmed", "source plan must be confirmed before formal export"))
    if plan.get("selected_file_count") is not None and (not isinstance(plan.get("selected_file_count"), int) or plan.get("selected_file_count") <= 0):
        problems.append(issue("SOURCE_PLAN_SELECTED_COUNT_INVALID", "source_plan.selected_file_count", "selected_file_count must be positive when present"))
    if plan.get("deposit_mode") not in {"front_back_30", "all_source"}:
        problems.append(issue("SOURCE_PLAN_DEPOSIT_MODE_INVALID", "source_plan.deposit_mode", "use front_back_30 or all_source"))
    if plan.get("secret_scan_status") not in SECRET_STATUS_ALLOWED:
        problems.append(issue("SOURCE_PLAN_SECRET_STATUS_INVALID", "source_plan.secret_scan_status", "source plan secret scan must be PASS or REDACTED_AND_VERIFIED"))

    locator = plan.get("path")
    if locator is not None:
        if problem := path_problem(locator):
            problems.append(issue("SOURCE_PLAN_PATH_INVALID", "source_plan.path", problem))
        elif base is not None:
            resolved = (base / str(locator)).resolve()
            try:
                resolved.relative_to(base.resolve())
            except ValueError:
                problems.append(issue("SOURCE_PLAN_PATH_ESCAPE", "source_plan.path", "resolved path escapes base"))
            else:
                if not resolved.is_file():
                    problems.append(issue("SOURCE_PLAN_FILE_MISSING", "source_plan.path", "source plan file does not exist"))
                elif isinstance(plan_sha, str) and SHA_RE.match(plan_sha) and file_sha256(resolved) != plan_sha:
                    problems.append(issue("SOURCE_PLAN_HASH_MISMATCH", "source_plan.sha256", "sha256 does not match source plan file"))
    return problems


def validate_rights_basis(packet: dict[str, Any]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    rights = packet.get("rights_basis")
    if not isinstance(rights, dict):
        return [issue("RIGHTS_BASIS_MISSING", "rights_basis", "development mode and rights-acquisition basis must be recorded")]
    status = str(rights.get("status", "")).upper()
    if status not in RIGHTS_STATUS_ALLOWED:
        problems.append(issue("RIGHTS_STATUS_INVALID", "rights_basis.status", "use VERIFIED, PLANNED, UNKNOWN or UNAVAILABLE"))
    if status != "VERIFIED":
        problems.append(issue("RIGHTS_NOT_VERIFIED", "rights_basis.status", "rights basis must be VERIFIED before formal export PASS"))
    for field in ("development_mode", "basis"):
        if not scalar_ok(rights.get(field)):
            problems.append(issue("RIGHTS_FIELD_MISSING", f"rights_basis.{field}", "non-placeholder value required"))
    return problems


def validate_third_party_code_review(packet: dict[str, Any]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    review = packet.get("third_party_code_review")
    if not isinstance(review, dict):
        return [issue("THIRD_PARTY_REVIEW_MISSING", "third_party_code_review", "third-party/open-source/unrelated code review is required")]
    status = review.get("status")
    if status not in THIRD_PARTY_STATUS_ALLOWED:
        problems.append(issue("THIRD_PARTY_REVIEW_STATUS_INVALID", "third_party_code_review.status", "use PASS or REVIEWED_WITH_EXCLUSIONS before export"))
    if not scalar_ok(review.get("summary")):
        problems.append(issue("THIRD_PARTY_REVIEW_SUMMARY_MISSING", "third_party_code_review.summary", "review summary required"))
    if status == "REVIEWED_WITH_EXCLUSIONS":
        excluded = review.get("excluded_paths")
        if not isinstance(excluded, list) or not excluded:
            problems.append(issue("THIRD_PARTY_EXCLUSIONS_MISSING", "third_party_code_review.excluded_paths", "excluded paths required when exclusions were used"))
        else:
            for index, path in enumerate(excluded):
                if problem := path_problem(path):
                    problems.append(issue("THIRD_PARTY_EXCLUSION_PATH_INVALID", f"third_party_code_review.excluded_paths[{index}]", problem))
    return problems


def validate_code_material(code: Any) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(code, dict):
        return [issue("CODE_MATERIAL_MISSING", "code_material", "code material object required")]
    if code.get("source_type") != "REAL_PROJECT":
        problems.append(issue("CODE_NOT_REAL_PROJECT", "code_material.source_type", "code material must come from real project source"))
    if code.get("selection_confirmed") is not True:
        problems.append(issue("CODE_SELECTION_UNCONFIRMED", "code_material.selection_confirmed", "human/model selection must be confirmed before extraction"))
    if not isinstance(code.get("extraction_manifest_sha256"), str) or not SHA_RE.match(code["extraction_manifest_sha256"]):
        problems.append(issue("CODE_MANIFEST_HASH_MISSING", "code_material.extraction_manifest_sha256", "extraction manifest sha256 required"))
    if not isinstance(code.get("source_plan_sha256"), str) or not SHA_RE.match(code["source_plan_sha256"]):
        problems.append(issue("CODE_SOURCE_PLAN_HASH_MISSING", "code_material.source_plan_sha256", "source deposit plan sha256 required"))

    total_pages = code.get("total_source_pages")
    mode = code.get("deposit_mode")
    if not isinstance(total_pages, int) or total_pages <= 0:
        problems.append(issue("CODE_TOTAL_PAGES_INVALID", "code_material.total_source_pages", "positive integer required"))
        total_pages = 0
    exceptional = code.get("exceptional_deposit") is True
    if total_pages >= 60 and not exceptional:
        if mode != "front_back_30":
            problems.append(issue("CODE_DEPOSIT_MODE_INVALID", "code_material.deposit_mode", ">=60 source pages require front_back_30 unless exceptional_deposit is true"))
        if code.get("front_pages") != 30 or code.get("back_pages") != 30:
            problems.append(issue("CODE_FRONT_BACK_INVALID", "code_material", "front_pages and back_pages must both be 30"))
    if 0 < total_pages < 60:
        if mode != "all_source" or code.get("all_source_included") is not True:
            problems.append(issue("CODE_ALL_SOURCE_REQUIRED", "code_material", "<60 source pages require all source pages"))
    if code.get("full_code_pages_have_min_50_lines") is not True:
        problems.append(issue("CODE_LINE_RULE_MISSING", "code_material.full_code_pages_have_min_50_lines", "full source pages must meet the 50-line rule or document an official exception"))
    if code.get("mid_file_snippet_used") is True and not exceptional:
        problems.append(issue("CODE_MID_SNIPPET_USED", "code_material.mid_file_snippet_used", "do not fabricate arbitrary middle snippets for normal deposit"))
    return problems


def validate_document_material(document: Any) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(document, dict):
        return [issue("DOCUMENT_MATERIAL_MISSING", "document_material", "manual/document material object required")]
    total_pages = document.get("total_document_pages")
    mode = document.get("deposit_mode")
    if not isinstance(total_pages, int) or total_pages <= 0:
        problems.append(issue("DOCUMENT_TOTAL_PAGES_INVALID", "document_material.total_document_pages", "positive integer required"))
        total_pages = 0
    if total_pages >= 60:
        if mode != "front_back_30":
            problems.append(issue("DOCUMENT_DEPOSIT_MODE_INVALID", "document_material.deposit_mode", ">=60 document pages require front_back_30"))
        if document.get("front_pages") != 30 or document.get("back_pages") != 30:
            problems.append(issue("DOCUMENT_FRONT_BACK_INVALID", "document_material", "front_pages and back_pages must both be 30"))
    if 0 < total_pages < 60 and (mode != "all_document" or document.get("all_document_included") is not True):
        problems.append(issue("DOCUMENT_ALL_REQUIRED", "document_material", "<60 document pages require all pages"))
    if document.get("full_document_pages_have_min_30_lines") is not True:
        problems.append(issue("DOCUMENT_LINE_RULE_MISSING", "document_material.full_document_pages_have_min_30_lines", "full document pages must meet the 30-line rule or document an official exception"))
    if document.get("business_context_confirmed") is not True:
        problems.append(issue("BUSINESS_CONTEXT_UNCONFIRMED", "document_material.business_context_confirmed", "manual must be grounded in confirmed business/product context"))
    return problems


def validate(packet: dict[str, Any], base: pathlib.Path | None, as_of: dt.date) -> dict[str, Any]:
    problems: list[dict[str, str]] = []
    if packet.get("schema") != SCHEMA_ID:
        problems.append(issue("SCHEMA_MISMATCH", "schema", f"expected {SCHEMA_ID}"))
    if packet.get("jurisdiction") != "CN":
        problems.append(issue("JURISDICTION_UNSUPPORTED", "jurisdiction", "this gate is for China software copyright materials; use CN"))
    if packet.get("not_legal_advice_ack") is not True:
        problems.append(issue("LEGAL_ACK_MISSING", "not_legal_advice_ack", "must be true; this skill is not legal advice"))
    if OVERCLAIM_RE.search("\n".join(strings(packet))):
        problems.append(issue("OVERCLAIM", "$", "remove guarantee/auto-submit/ready-to-submit language"))
    if packet.get("submission", {}).get("submit_to_office") is True:
        problems.append(issue("SUBMISSION_OVERSTEP", "submission.submit_to_office", "Light must not submit registration materials"))

    application = packet.get("application")
    if not isinstance(application, dict):
        problems.append(issue("APPLICATION_MISSING", "application", "application fields required"))
        application = {}
    for field in APPLICATION_FIELDS:
        if not scalar_ok(application.get(field)):
            problems.append(issue("APPLICATION_FIELD_MISSING", f"application.{field}", "non-placeholder value required"))
    parse_date(application.get("development_completion_date"), "application.development_completion_date", as_of, problems)

    binding = packet.get("project_binding")
    if not isinstance(binding, dict):
        problems.append(issue("PROJECT_BINDING_MISSING", "project_binding", "project binding and source file manifest required"))
    else:
        if not scalar_ok(binding.get("source_root_name")):
            problems.append(issue("SOURCE_ROOT_NAME_MISSING", "project_binding.source_root_name", "source root name required"))
        if not isinstance(binding.get("manifest_sha256"), str) or not SHA_RE.match(binding["manifest_sha256"]):
            problems.append(issue("MANIFEST_HASH_MISSING", "project_binding.manifest_sha256", "source manifest sha256 required"))
        problems.extend(validate_file_list(binding.get("source_files"), base, "project_binding.source_files"))

    problems.extend(validate_confirmations(packet, as_of))
    problems.extend(validate_source_plan(packet, base))
    problems.extend(validate_rights_basis(packet))
    problems.extend(validate_third_party_code_review(packet))
    problems.extend(validate_code_material(packet.get("code_material")))
    problems.extend(validate_document_material(packet.get("document_material")))

    version = application.get("version")
    consistency = packet.get("version_consistency")
    if not isinstance(consistency, dict):
        problems.append(issue("VERSION_CONSISTENCY_MISSING", "version_consistency", "version consistency evidence required"))
    else:
        if consistency.get("all_materials_match_application") is not True:
            problems.append(issue("VERSION_MISMATCH_DECLARED", "version_consistency.all_materials_match_application", "all material versions must match application version"))
        materials = consistency.get("materials")
        if not isinstance(materials, list) or not materials:
            problems.append(issue("VERSION_MATERIALS_MISSING", "version_consistency.materials", "material version list required"))
        else:
            for index, item in enumerate(materials):
                if not isinstance(item, dict):
                    problems.append(issue("VERSION_MATERIAL_INVALID", f"version_consistency.materials[{index}]", "material must be object"))
                    continue
                if item.get("version") != version:
                    problems.append(issue("VERSION_MISMATCH", f"version_consistency.materials[{index}].version", "material version must match application.version"))
                if not scalar_ok(item.get("locator")):
                    problems.append(issue("VERSION_LOCATOR_MISSING", f"version_consistency.materials[{index}].locator", "version locator required"))

    secret = packet.get("secret_scan")
    if not isinstance(secret, dict) or secret.get("status") not in SECRET_STATUS_ALLOWED:
        problems.append(issue("SECRET_SCAN_NOT_CLEAN", "secret_scan.status", "status must be PASS or REDACTED_AND_VERIFIED before exporting source code"))
    if isinstance(packet.get("source_plan"), dict) and isinstance(packet.get("code_material"), dict):
        if packet["source_plan"].get("sha256") != packet["code_material"].get("source_plan_sha256"):
            problems.append(issue("SOURCE_PLAN_HASH_INCONSISTENT", "code_material.source_plan_sha256", "must match source_plan.sha256"))
    screenshot = packet.get("screenshots")
    if isinstance(screenshot, dict) and screenshot.get("required") is True:
        problems.extend(validate_file_list(screenshot.get("files"), base, "screenshots.files"))
    elif isinstance(screenshot, dict) and screenshot.get("required") is False:
        if not scalar_ok(screenshot.get("skip_reason")):
            problems.append(issue("SCREENSHOT_SKIP_REASON_MISSING", "screenshots.skip_reason", "record why screenshots are not included"))

    formal = packet.get("formal_output")
    if not isinstance(formal, dict):
        problems.append(issue("FORMAL_OUTPUT_MISSING", "formal_output", "formal output list required"))
    else:
        if formal.get("generated") is not True:
            problems.append(issue("FORMAL_OUTPUT_NOT_GENERATED", "formal_output.generated", "formal files must be generated before PASS"))
        problems.extend(validate_file_list(formal.get("files"), base, "formal_output.files"))

    return {
        "schema": REPORT_SCHEMA,
        "verdict": "FAIL" if any(row["severity"] == "ERROR" for row in problems) else "PASS",
        "checked_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of.isoformat(),
        "packet_schema": packet.get("schema"),
        "issues": problems,
    }


def run_selftest() -> int:
    root = repo_root()
    e2e_root = root / ".upgrade" / "_e2e" / "software-copyright-gate"
    e2e_root.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="selftest-", dir=e2e_root))
    try:
        src = tmp / "src"
        src.mkdir()
        app_py = src / "app.py"
        app_py.write_text("print('real project source')\n", encoding="utf-8")
        plan_file = tmp / "source-deposit-plan.json"
        plan_file.write_text('{"schema":"light.software_copyright.source_deposit_plan.v1","selected_file_count":1}\n', encoding="utf-8")
        out = tmp / "软件著作权申请资料" / "正式资料"
        out.mkdir(parents=True)
        manual = out / "LightDemo_操作手册.docx"
        code = out / "LightDemo-代码材料.docx"
        form = out / "申请表信息.txt"
        for path in (manual, code, form):
            path.write_text("placeholder binary surrogate for selftest\n", encoding="utf-8")
        packet: dict[str, Any] = {
            "schema": SCHEMA_ID,
            "jurisdiction": "CN",
            "not_legal_advice_ack": True,
            "application": {
                "software_full_name": "LightDemo 科研流程系统",
                "version": "V1.0",
                "copyright_owner": "Demo Owner",
                "development_completion_date": "2026-07-01",
                "first_publication_status": "未发表",
                "development_mode": "独立开发",
            },
            "project_binding": {
                "source_root_name": "LightDemo",
                "manifest_sha256": "sha256:" + "1" * 64,
                "source_files": [
                    {"id": "S1", "path": "src/app.py", "sha256": file_sha256(app_py)},
                ],
            },
            "source_plan": {
                "schema": SOURCE_PLAN_SCHEMA,
                "path": "source-deposit-plan.json",
                "sha256": file_sha256(plan_file),
                "confirmed": True,
                "selected_file_count": 1,
                "deposit_mode": "front_back_30",
                "secret_scan_status": "PASS",
            },
            "rights_basis": {
                "status": "VERIFIED",
                "development_mode": "独立开发",
                "basis": "User-confirmed independent development for selftest fixture.",
            },
            "third_party_code_review": {
                "status": "PASS",
                "summary": "No vendored, generated or unrelated third-party code is included in the selected source material.",
            },
            "stage_confirmations": {
                key: {"confirmed": True, "confirmed_at": "2026-07-05", "basis": f"{key} confirmed by user"}
                for key in CONFIRMATION_KEYS
            },
            "code_material": {
                "source_type": "REAL_PROJECT",
                "selection_confirmed": True,
                "extraction_manifest_sha256": "sha256:" + "2" * 64,
                "source_plan_sha256": file_sha256(plan_file),
                "total_source_pages": 75,
                "deposit_mode": "front_back_30",
                "front_pages": 30,
                "back_pages": 30,
                "full_code_pages_have_min_50_lines": True,
                "mid_file_snippet_used": False,
                "exceptional_deposit": False,
            },
            "document_material": {
                "total_document_pages": 30,
                "deposit_mode": "all_document",
                "all_document_included": True,
                "full_document_pages_have_min_30_lines": True,
                "business_context_confirmed": True,
            },
            "version_consistency": {
                "all_materials_match_application": True,
                "materials": [
                    {"locator": "申请表信息.txt", "version": "V1.0"},
                    {"locator": "LightDemo_操作手册.docx", "version": "V1.0"},
                    {"locator": "LightDemo-代码材料.docx", "version": "V1.0"},
                ],
            },
            "secret_scan": {"status": "PASS"},
            "screenshots": {"required": False, "skip_reason": "Project has no GUI; manual uses command-line workflow."},
            "submission": {"submit_to_office": False},
            "formal_output": {
                "generated": True,
                "files": [
                    {"id": "O1", "path": "软件著作权申请资料/正式资料/LightDemo_操作手册.docx", "sha256": file_sha256(manual)},
                    {"id": "O2", "path": "软件著作权申请资料/正式资料/LightDemo-代码材料.docx", "sha256": file_sha256(code)},
                    {"id": "O3", "path": "软件著作权申请资料/正式资料/申请表信息.txt", "sha256": file_sha256(form)},
                ],
            },
        }
        checks: list[tuple[bool, str]] = []
        checks.append((validate(packet, tmp, dt.date(2026, 7, 5))["verdict"] == "PASS", "valid CN materials packet passes"))

        bad_version = copy.deepcopy(packet)
        bad_version["version_consistency"]["materials"][1]["version"] = "V2.0"
        checks.append((validate(bad_version, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "version mismatch fails"))

        fake_code = copy.deepcopy(packet)
        fake_code["code_material"]["source_type"] = "AI_GENERATED"
        checks.append((validate(fake_code, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "AI/fake code source fails"))

        bad_pages = copy.deepcopy(packet)
        bad_pages["code_material"]["back_pages"] = 12
        checks.append((validate(bad_pages, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "front/back page rule fails"))

        secret_found = copy.deepcopy(packet)
        secret_found["secret_scan"]["status"] = "FOUND"
        checks.append((validate(secret_found, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "secret scan failure blocks export"))

        unverified_rights = copy.deepcopy(packet)
        unverified_rights["rights_basis"]["status"] = "UNKNOWN"
        checks.append((validate(unverified_rights, tmp, dt.date(2026, 7, 5))["verdict"] == "FAIL", "unverified rights basis blocks export"))

        ok = True
        for passed, label in checks:
            ok &= passed
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Light software copyright material packet")
    parser.add_argument("--packet", type=pathlib.Path, help="materials packet JSON")
    parser.add_argument("--base", type=pathlib.Path, help="project root for source/hash checks")
    parser.add_argument("--as-of", default=dt.date.today().isoformat(), help="validation date, YYYY-MM-DD")
    parser.add_argument("--report", type=pathlib.Path, help="optional output report JSON")
    parser.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if args.packet is None:
        parser.error("--packet is required unless --selftest is used")
    date_problems: list[dict[str, str]] = []
    as_of = parse_date(args.as_of, "--as-of", dt.date.max, date_problems) or dt.date.today()
    packet = load_json(args.packet)
    if not isinstance(packet, dict):
        raise SystemExit("packet must be a JSON object")
    report = validate(packet, args.base.resolve() if args.base else None, as_of)
    if date_problems:
        report["issues"] = date_problems + report["issues"]
        report["verdict"] = "FAIL"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
