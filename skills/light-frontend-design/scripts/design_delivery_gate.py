#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate frontend delivery evidence instead of trusting self-reported READY.

Final claims require non-bypassable decisions, non-future evidence dates, project-local
token/QA/screenshot files, matching sha256 values, browser/contrast report status
agreement, and render-review metadata tied to screenshots actually reviewed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.frontend_delivery.v1"
REPORT_SCHEMA = "light.frontend_delivery_report.v1"
SCENARIOS = {"dashboard", "admin", "landing", "academic", "mobile", "custom"}
DECISION_KINDS = {
    "scenario",
    "style_direction",
    "stack",
    "color",
    "font",
    "component_library",
    "density",
    "motion",
}
DECISION_AUTHORITIES = {"user", "delegated", "inherited", "not_required"}
SOURCE_KINDS = {
    "component",
    "block",
    "template",
    "animation",
    "gradient",
    "font",
    "package",
    "inspiration",
}
SOURCE_USES = {"copy_code", "package_install", "inspiration_only", "reference_only"}
ACCESS_TIERS = {
    "public_free",
    "free_login",
    "paid",
    "institutional",
    "unknown",
    "unavailable",
}
QA_STATUSES = {"PASS", "WARN", "FAIL", "UNAVAILABLE", "NOT_RUN", "NOT_REQUIRED"}
READY_CLAIMS = {"READY", "PARTIAL_BROWSER_UNAVAILABLE", "DRAFT"}
FINAL_CLAIMS = {"READY", "PARTIAL_BROWSER_UNAVAILABLE"}
PAID_OR_RESTRICTED = {"paid", "institutional", "unavailable"}
REQUIRED_DECISIONS = {"scenario", "style_direction", "stack", "color", "font"}
REQUIRED_QA = {
    "contrast_lint",
    "ai_tell_lint",
    "audit_checklist",
    "browser_qa",
    "render_review",
}
PUBLIC_LICENSES = {
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "cc0",
    "public-domain",
    "custom-reviewed",
}


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and text not in {
        "unknown",
        "pending",
        "todo",
        "tbd",
        "n/a",
        "none",
        "-",
        "replace-with",
    } and "<" not in text and "{{" not in text


def _parse_date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def _as_of_date(value: Any = None) -> dt.date:
    if value is None or not str(value).strip():
        return dt.date.today()
    parsed = _parse_date(str(value).strip())
    if parsed is None:
        raise ValueError("--as-of must be YYYY-MM-DD")
    return parsed


def _sha(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _file_sha(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _project_file(root: pathlib.Path | None, locator: Any) -> tuple[pathlib.Path | None, str | None]:
    if root is None:
        return None, "project root unavailable"
    text = str(locator or "").strip()
    if not _real(text):
        return None, "locator is missing or placeholder"
    candidate = pathlib.Path(text)
    if candidate.is_absolute():
        return None, "locator must be project-relative, not an absolute local path"
    base = root.resolve()
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return None, "locator escapes the project root"
    return resolved, None


def _screenshot_entry(value: Any) -> tuple[Any, Any]:
    if isinstance(value, dict):
        return (
            value.get("locator") or value.get("path") or value.get("screenshot"),
            value.get("sha256") or value.get("screenshot_sha256"),
        )
    return value, None


def _json_file(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _license_ok(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in PUBLIC_LICENSES or (
        "mit" in text and "commons clause" in text
    )


def evaluate(
    spec: dict[str, Any],
    *,
    root: pathlib.Path | None = None,
    as_of: Any = None,
) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema must be {SCHEMA_ID}")
    issues: list[dict[str, str]] = []
    today = _as_of_date(as_of)
    evidence_root = root.resolve() if root is not None else None

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append(
            {"code": code, "loc": loc, "severity": severity, "message": message}
        )

    delivery_claim = spec.get("delivery_claim")
    if delivery_claim not in READY_CLAIMS:
        add("DELIVERY_CLAIM_GAP", "delivery_claim", "invalid delivery_claim")
    if delivery_claim in FINAL_CLAIMS and evidence_root is None:
        add(
            "EVIDENCE_ROOT_GAP",
            "project_root",
            "final delivery claims need a project root so artifacts can be verified",
        )
    scenario = spec.get("scenario")
    if scenario not in SCENARIOS:
        add("SCENARIO_GAP", "scenario", "scenario must be a known UI scenario")

    decisions_raw = spec.get("decisions")
    sources_raw = spec.get("sources")
    qa_raw = spec.get("qa")
    token_raw = spec.get("token_system")
    if not isinstance(decisions_raw, list):
        raise ValueError("decisions must be a list")
    if not isinstance(sources_raw, list):
        raise ValueError("sources must be a list")
    if not isinstance(qa_raw, dict):
        raise ValueError("qa must be an object")
    if not isinstance(token_raw, dict):
        raise ValueError("token_system must be an object")

    decisions_by_kind: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(decisions_raw):
        if not isinstance(row, dict):
            raise ValueError("decision rows must be objects")
        kind = str(row.get("kind") or "")
        decisions_by_kind.setdefault(kind, []).append(row)
        loc = f"decisions[{index}]"
        if kind not in DECISION_KINDS:
            add("DECISION_KIND_GAP", loc, "unknown decision kind")
        if row.get("authority") not in DECISION_AUTHORITIES:
            add("DECISION_AUTHORITY_GAP", loc, "decision authority must be user/delegated/inherited/not_required")
        if not _real(row.get("selected")) and row.get("authority") != "not_required":
            add("DECISION_SELECTED_GAP", loc, "decision needs selected value")
        if row.get("authority") == "user":
            options = row.get("options_presented")
            real_options = (
                [str(option).strip() for option in options if _real(option)]
                if isinstance(options, list)
                else []
            )
            if len(real_options) < 2 or len({option.casefold() for option in real_options}) < 2:
                add(
                    "USER_DECISION_OPTIONS_GAP",
                    loc,
                    "user decision needs at least two distinct, non-placeholder options",
                )
            elif str(row.get("selected") or "").strip() not in real_options:
                add(
                    "USER_DECISION_SELECTION_DRIFT",
                    loc,
                    "selected value must be one of the options actually presented",
                )
            decided_at = _parse_date(row.get("decided_at"))
            if decided_at is None:
                add("DECISION_DATE_GAP", loc, "user decision needs decided_at date")
            elif decided_at > today:
                add(
                    "DECISION_DATE_FUTURE",
                    loc,
                    f"decided_at {decided_at.isoformat()} is later than as_of {today.isoformat()}",
                )
        elif row.get("authority") == "delegated":
            if not _real(row.get("user_authorization")):
                add(
                    "DELEGATED_DECISION_AUTH_GAP",
                    loc,
                    "delegated design decision needs explicit user_authorization",
                )
        elif row.get("authority") == "inherited":
            if not _real(row.get("source_locator")):
                add("INHERITED_DECISION_SOURCE_GAP", loc, "inherited decision needs source_locator")
        elif row.get("authority") not in {"not_required", "user", "delegated", "inherited"}:
            add(
                "AGENT_DECISION_RISK",
                loc,
                "agent-picked direction/stack/color/font is not an accepted authority",
            )
        if kind == "scenario" and row.get("selected") != scenario:
            add("SCENARIO_DECISION_DRIFT", loc, "scenario decision and top-level scenario differ")

    missing_decisions = sorted(REQUIRED_DECISIONS - set(decisions_by_kind))
    if missing_decisions:
        add(
            "REQUIRED_DECISION_MISSING",
            "decisions",
            f"missing required design decisions: {', '.join(missing_decisions)}",
        )
    for kind in sorted(REQUIRED_DECISIONS):
        for row in decisions_by_kind.get(kind, []):
            if row.get("authority") == "not_required":
                add(
                    "REQUIRED_DECISION_AUTHORITY_GAP",
                    f"decisions.{kind}",
                    f"{kind} is required and cannot be marked not_required",
                )
    if scenario in {"dashboard", "admin", "academic", "mobile"} and "density" not in decisions_by_kind:
        add("DENSITY_DECISION_MISSING", "decisions", f"{scenario} needs density decision")
    if any(
        row.get("selected") in {"gsap", "motion", "scroll-animation", "webgl"}
        for row in decisions_by_kind.get("motion", [])
    ):
        motion_decision = decisions_by_kind.get("motion", [{}])[0]
        if not _real(motion_decision.get("reduced_motion_strategy")):
            add("REDUCED_MOTION_GAP", "decisions.motion", "motion decision needs reduced_motion_strategy")

    source_ids: set[str] = set()
    for index, row in enumerate(sources_raw):
        if not isinstance(row, dict):
            raise ValueError("source rows must be objects")
        sid = str(row.get("source_id") or "")
        loc = f"sources[{index}]"
        if not sid or sid in source_ids:
            raise ValueError("source_id missing or duplicate")
        source_ids.add(sid)
        if row.get("kind") not in SOURCE_KINDS:
            add("SOURCE_KIND_GAP", loc, "unknown source kind")
        if row.get("use") not in SOURCE_USES:
            add("SOURCE_USE_GAP", loc, "unknown source use")
        if row.get("access_tier") not in ACCESS_TIERS:
            add("SOURCE_ACCESS_GAP", loc, "unknown access_tier")
        if not _real(row.get("locator")) and not _real(row.get("package")):
            add("SOURCE_LOCATOR_GAP", loc, "source needs locator or package")
        last_checked = _parse_date(row.get("last_checked"))
        if last_checked is None:
            add("SOURCE_LAST_CHECKED_GAP", loc, "source needs last_checked date")
        elif last_checked > today:
            add(
                "SOURCE_LAST_CHECKED_FUTURE",
                loc,
                f"last_checked {last_checked.isoformat()} is later than as_of {today.isoformat()}",
            )
        use = row.get("use")
        if use in {"copy_code", "package_install"}:
            if not _license_ok(row.get("license")):
                add("SOURCE_LICENSE_GAP", loc, "copied/installed source needs reviewed reusable license")
            if row.get("access_tier") in PAID_OR_RESTRICTED and not _real(
                row.get("user_authorization")
            ):
                add("RESTRICTED_SOURCE_AUTH_GAP", loc, "paid/restricted source needs user authorization")
            if use == "package_install" and not _real(row.get("version_checked")):
                add("PACKAGE_VERSION_GAP", loc, "package install needs version_checked")
        if use == "inspiration_only" and row.get("copied_code") is True:
            add("INSPIRATION_CODE_COPY_DRIFT", loc, "inspiration_only source cannot copy code")

    if token_raw.get("single_token_source") is not True:
        add("TOKEN_SINGLE_SOURCE_GAP", "token_system.single_token_source", "one project must have one token source")
    if not _real(token_raw.get("token_source_locator")):
        add("TOKEN_SOURCE_LOCATOR_GAP", "token_system.token_source_locator", "token source locator required")
    token_hash = token_raw.get("token_source_sha256")
    if token_hash and not _sha(token_hash):
        add("TOKEN_SOURCE_HASH_GAP", "token_system.token_source_sha256", "token source hash must be sha256:")
    if delivery_claim in FINAL_CLAIMS and not _sha(token_hash):
        add(
            "TOKEN_SOURCE_HASH_REQUIRED",
            "token_system.token_source_sha256",
            "final delivery needs the verified token source sha256",
        )
    token_path, token_path_error = _project_file(evidence_root, token_raw.get("token_source_locator"))
    if delivery_claim in FINAL_CLAIMS and token_path_error:
        add("TOKEN_SOURCE_PATH_GAP", "token_system.token_source_locator", token_path_error)
    elif delivery_claim in FINAL_CLAIMS and token_path is not None:
        if not token_path.is_file():
            add("TOKEN_SOURCE_MISSING", "token_system.token_source_locator", "token source file does not exist")
        elif token_path.stat().st_size == 0:
            add("TOKEN_SOURCE_EMPTY", "token_system.token_source_locator", "token source file is empty")
        elif _sha(token_hash) and _file_sha(token_path).casefold() != str(token_hash).casefold():
            add("TOKEN_SOURCE_HASH_MISMATCH", "token_system.token_source_sha256", "token source sha256 does not match the file")
    if token_raw.get("foreign_hardcoded_colors_remaining") is True:
        add("FOREIGN_COLOR_DRIFT", "token_system", "borrowed hardcoded colors still remain")
    if token_raw.get("second_design_system_present") is True:
        add("SECOND_DESIGN_SYSTEM", "token_system", "one project must not mix multiple design systems")

    for gate in sorted(REQUIRED_QA):
        row = qa_raw.get(gate)
        if not isinstance(row, dict):
            add("QA_GATE_MISSING", f"qa.{gate}", "required QA gate missing")
            continue
        status = row.get("status")
        if status not in QA_STATUSES:
            add("QA_STATUS_GAP", f"qa.{gate}", "invalid QA status")
            continue
        if status == "FAIL":
            add("QA_FAIL", f"qa.{gate}", f"{gate} failed")
        if status == "NOT_RUN":
            add("QA_NOT_RUN", f"qa.{gate}", f"{gate} was not run")
        if status == "UNAVAILABLE":
            severity = (
                "unresolved"
                if delivery_claim == "PARTIAL_BROWSER_UNAVAILABLE" and gate == "browser_qa"
                else "error"
            )
            add("QA_UNAVAILABLE", f"qa.{gate}", f"{gate} unavailable", severity)
        if delivery_claim in FINAL_CLAIMS:
            if delivery_claim == "PARTIAL_BROWSER_UNAVAILABLE" and gate == "browser_qa":
                allowed = {"UNAVAILABLE"}
            elif gate in {"contrast_lint", "ai_tell_lint", "audit_checklist"}:
                allowed = {"PASS"}
            else:
                allowed = {"PASS", "WARN"}
            if status not in allowed:
                add(
                    "FINAL_QA_STATUS_GAP",
                    f"qa.{gate}",
                    f"{delivery_claim} requires {gate} status in {sorted(allowed)}",
                )
        if status == "WARN" and not _real(row.get("warning_summary")):
            add("QA_WARNING_SUMMARY_GAP", f"qa.{gate}", "WARN needs a concrete warning_summary")
        if status in {"PASS", "WARN", "FAIL"} and not _real(row.get("artifact")):
            add("QA_ARTIFACT_GAP", f"qa.{gate}", "QA result needs artifact locator")
        artifact_hash = row.get("artifact_sha256")
        if artifact_hash and not _sha(artifact_hash):
            add("QA_ARTIFACT_HASH_GAP", f"qa.{gate}", "artifact_sha256 must be sha256:")
        if delivery_claim in FINAL_CLAIMS and status in {"PASS", "WARN"} and not _sha(artifact_hash):
            add(
                "QA_ARTIFACT_HASH_REQUIRED",
                f"qa.{gate}",
                "final QA evidence needs artifact_sha256",
            )
        if status in {"PASS", "WARN", "FAIL"} and _real(row.get("artifact")):
            artifact_path, artifact_error = _project_file(evidence_root, row.get("artifact"))
            if delivery_claim in FINAL_CLAIMS and artifact_error:
                add("QA_ARTIFACT_PATH_GAP", f"qa.{gate}", artifact_error)
            elif artifact_path is not None:
                if not artifact_path.is_file():
                    add("QA_ARTIFACT_MISSING", f"qa.{gate}", "QA artifact file does not exist")
                elif artifact_path.stat().st_size == 0:
                    add("QA_ARTIFACT_EMPTY", f"qa.{gate}", "QA artifact file is empty")
                else:
                    if _sha(artifact_hash) and _file_sha(artifact_path).casefold() != str(artifact_hash).casefold():
                        add("QA_ARTIFACT_HASH_MISMATCH", f"qa.{gate}", "artifact sha256 does not match the file")
                    if gate == "browser_qa":
                        browser_report = _json_file(artifact_path)
                        if not browser_report or browser_report.get("schema") != "light.frontend.browser_qa.v1":
                            add("BROWSER_QA_SCHEMA_GAP", f"qa.{gate}", "artifact is not a browser_qa report")
                        else:
                            actual = browser_report.get("status")
                            if actual != status:
                                add(
                                    "BROWSER_QA_STATUS_DRIFT",
                                    f"qa.{gate}",
                                    f"declared {status}, artifact reports {actual}",
                                )
                            coverage = browser_report.get("coverage")
                            if not isinstance(coverage, dict) or coverage.get("real_chromium") is not True:
                                add("BROWSER_QA_RUNTIME_GAP", f"qa.{gate}", "artifact does not prove real Chromium execution")
                            viewports = browser_report.get("viewports")
                            names = {
                                item.get("viewport")
                                for item in viewports
                                if isinstance(item, dict)
                            } if isinstance(viewports, list) else set()
                            if names != {"mobile", "tablet", "desktop"}:
                                add("BROWSER_QA_VIEWPORT_GAP", f"qa.{gate}", "artifact must contain mobile/tablet/desktop results")
                            elif evidence_root is not None:
                                for item in viewports:
                                    screenshot, screenshot_error = _project_file(evidence_root, item.get("screenshot"))
                                    expected_screenshot_hash = item.get("screenshot_sha256")
                                    if screenshot_error or screenshot is None or not screenshot.is_file() or screenshot.stat().st_size == 0:
                                        add(
                                            "BROWSER_QA_SCREENSHOT_GAP",
                                            f"qa.{gate}.{item.get('viewport')}",
                                            screenshot_error or "screenshot file is missing or empty",
                                        )
                                    if not _sha(expected_screenshot_hash):
                                        add(
                                            "BROWSER_QA_SCREENSHOT_HASH_REQUIRED",
                                            f"qa.{gate}.{item.get('viewport')}",
                                            "browser QA screenshot needs screenshot_sha256",
                                        )
                                    elif screenshot is not None and screenshot.is_file() and _file_sha(screenshot).casefold() != str(expected_screenshot_hash).casefold():
                                        add(
                                            "BROWSER_QA_SCREENSHOT_HASH_MISMATCH",
                                            f"qa.{gate}.{item.get('viewport')}",
                                            "screenshot_sha256 does not match the screenshot file",
                                        )
                            if browser_report.get("runtime_errors"):
                                add("BROWSER_QA_RUNTIME_ERROR", f"qa.{gate}", "browser report contains runtime_errors")
                    elif gate == "contrast_lint":
                        contrast_report = _json_file(artifact_path)
                        if not contrast_report or contrast_report.get("schema") != "light.visual_qa.v1":
                            add("CONTRAST_QA_SCHEMA_GAP", f"qa.{gate}", "artifact must be light.visual_qa.v1 JSON")
                        else:
                            actual = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(
                                str(contrast_report.get("verdict") or "").casefold()
                            )
                            if actual != status:
                                add(
                                    "CONTRAST_QA_STATUS_DRIFT",
                                    f"qa.{gate}",
                                    f"declared {status}, artifact reports {actual or 'unknown'}",
                                )
                    elif gate == "ai_tell_lint":
                        text = artifact_path.read_text(encoding="utf-8-sig", errors="replace")
                        actual = "PASS" if text.lstrip().startswith("CLEAN:") else "FAIL"
                        if actual != status:
                            add("AI_TELL_STATUS_DRIFT", f"qa.{gate}", f"declared {status}, artifact implies {actual}")
                    elif gate == "audit_checklist":
                        text = artifact_path.read_text(encoding="utf-8-sig", errors="replace")
                        actual = "FAIL" if "[FAIL]" in text else (
                            "PASS" if re.search(r"---\s*(\d+)/\1 rules passed\s*---", text) else None
                        )
                        if actual != status:
                            add(
                                "AUDIT_CHECKLIST_STATUS_DRIFT",
                                f"qa.{gate}",
                                f"declared {status}, artifact implies {actual or 'unknown'}",
                            )

        if gate == "render_review" and delivery_claim in FINAL_CLAIMS:
            reviewed_at = _parse_date(row.get("reviewed_at"))
            if reviewed_at is None:
                add("RENDER_REVIEW_DATE_GAP", f"qa.{gate}", "render review needs reviewed_at YYYY-MM-DD")
            elif reviewed_at > today:
                add("RENDER_REVIEW_DATE_FUTURE", f"qa.{gate}", "render review date cannot be in the future")
            if not _real(row.get("summary")):
                add("RENDER_REVIEW_SUMMARY_GAP", f"qa.{gate}", "render review needs a concrete summary")
            screenshots = row.get("screenshots")
            if not isinstance(screenshots, list) or not screenshots:
                add("RENDER_REVIEW_SCREENSHOT_GAP", f"qa.{gate}", "render review needs reviewed screenshot locators")
            elif evidence_root is not None:
                for index, screenshot_entry in enumerate(screenshots):
                    screenshot_locator, screenshot_hash = _screenshot_entry(screenshot_entry)
                    screenshot, screenshot_error = _project_file(evidence_root, screenshot_locator)
                    if screenshot_error or screenshot is None or not screenshot.is_file() or screenshot.stat().st_size == 0:
                        add(
                            "RENDER_REVIEW_SCREENSHOT_GAP",
                            f"qa.{gate}.screenshots[{index}]",
                            screenshot_error or "reviewed screenshot is missing or empty",
                        )
                    if not _sha(screenshot_hash):
                        add(
                            "RENDER_REVIEW_SCREENSHOT_HASH_REQUIRED",
                            f"qa.{gate}.screenshots[{index}]",
                            "render-reviewed screenshot needs sha256",
                        )
                    elif screenshot is not None and screenshot.is_file() and _file_sha(screenshot).casefold() != str(screenshot_hash).casefold():
                        add(
                            "RENDER_REVIEW_SCREENSHOT_HASH_MISMATCH",
                            f"qa.{gate}.screenshots[{index}]",
                            "render-review screenshot sha256 does not match the file",
                        )
            critical_count = row.get("critical_count")
            if not isinstance(critical_count, int) or isinstance(critical_count, bool) or critical_count < 0:
                add("RENDER_REVIEW_CRITICAL_COUNT_GAP", f"qa.{gate}", "critical_count must be a non-negative integer")
            elif critical_count > 0:
                add("RENDER_REVIEW_CRITICAL_OPEN", f"qa.{gate}", "critical visual findings remain open")

    render = qa_raw.get("render_review") if isinstance(qa_raw.get("render_review"), dict) else {}
    if delivery_claim == "READY":
        browser = qa_raw.get("browser_qa", {})
        if browser.get("status") not in {"PASS", "WARN"}:
            add("READY_WITHOUT_BROWSER_QA", "qa.browser_qa", "READY delivery needs real browser QA PASS/WARN")
        if render.get("status") not in {"PASS", "WARN"}:
            add("READY_WITHOUT_RENDER_REVIEW", "qa.render_review", "READY delivery needs render-then-look review")

    critical = [item for item in issues if item["severity"] == "error"]
    if critical:
        status = "FAIL"
    elif issues:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "delivery_claim": delivery_claim,
        "scenario": scenario,
        "source_count": len(source_ids),
        "decision_kinds": sorted(k for k in decisions_by_kind if k),
        "issues": issues,
        "honesty": (
            "PASS means the frontend delivery has auditable user/inherited decisions, "
            "source provenance, token ownership, and QA artifacts. It does not prove "
            "the design is award-winning, only that it is not being overclaimed."
        ),
    }


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "delivery_claim": "READY",
        "scenario": "dashboard",
        "decisions": [
            {
                "kind": "scenario",
                "authority": "user",
                "selected": "dashboard",
                "options_presented": ["dashboard", "landing"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "style_direction",
                "authority": "user",
                "selected": "industrial-minimal",
                "options_presented": ["industrial-minimal", "soft-pastel"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "stack",
                "authority": "user",
                "selected": "Vite + React",
                "options_presented": ["Vite + React", "Next App Router"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "color",
                "authority": "user",
                "selected": "slate + amber",
                "options_presented": ["slate + amber", "indigo + lime"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "font",
                "authority": "user",
                "selected": "Atkinson/Fraunces",
                "options_presented": ["Atkinson/Fraunces", "IBM Plex/Instrument Serif"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "density",
                "authority": "user",
                "selected": "high-density",
                "options_presented": ["high-density", "presentation"],
                "decided_at": "2026-07-05",
            },
            {
                "kind": "motion",
                "authority": "not_required",
                "selected": "none",
            },
        ],
        "sources": [
            {
                "source_id": "S1",
                "name": "HyperUI metric card",
                "kind": "component",
                "use": "copy_code",
                "locator": "https://www.hyperui.dev/components/marketing/cards",
                "access_tier": "public_free",
                "license": "MIT",
                "last_checked": "2026-07-05",
            },
            {
                "source_id": "S2",
                "name": "Awwwards dashboard inspiration",
                "kind": "inspiration",
                "use": "inspiration_only",
                "locator": "https://www.awwwards.com/websites/",
                "access_tier": "public_free",
                "license": "unknown",
                "last_checked": "2026-07-05",
                "copied_code": False,
            },
        ],
        "token_system": {
            "single_token_source": True,
            "token_source_locator": "src/styles/tokens.css",
            "token_source_sha256": "",
            "foreign_hardcoded_colors_remaining": False,
            "second_design_system_present": False,
        },
        "qa": {
            "contrast_lint": {"status": "PASS", "artifact": "qa/contrast.json", "artifact_sha256": ""},
            "ai_tell_lint": {"status": "PASS", "artifact": "qa/ai-tell.txt", "artifact_sha256": ""},
            "audit_checklist": {"status": "PASS", "artifact": "qa/audit.txt", "artifact_sha256": ""},
            "browser_qa": {
                "status": "WARN",
                "artifact": "qa/browser.json",
                "artifact_sha256": "",
                "warning_summary": "focus indicator heuristic needs human confirmation",
            },
            "render_review": {
                "status": "PASS",
                "artifact": "qa/render-review.md",
                "artifact_sha256": "",
                "reviewed_at": "2026-07-05",
                "summary": "three viewport screenshots reviewed; no critical visual defects",
                "screenshots": [
                    "qa/screenshots/mobile.png",
                    "qa/screenshots/tablet.png",
                    "qa/screenshots/desktop.png",
                ],
                "critical_count": 0,
            },
        },
    }


def _materialize_evidence(spec: dict[str, Any], root: pathlib.Path) -> None:
    token = root / spec["token_system"]["token_source_locator"]
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(":root{--color-bg:#fff;--color-fg:#111;}\n", encoding="utf-8")
    spec["token_system"]["token_source_sha256"] = _file_sha(token)

    screenshots: dict[str, str] = {}
    screenshot_hashes: dict[str, str] = {}
    for viewport in ("mobile", "tablet", "desktop"):
        path = root / "qa" / "screenshots" / f"{viewport}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"selftest-{viewport}-png".encode())
        screenshots[viewport] = path.relative_to(root).as_posix()
        screenshot_hashes[viewport] = _file_sha(path)
    spec["qa"]["render_review"]["screenshots"] = [
        {"locator": screenshots[viewport], "sha256": screenshot_hashes[viewport]}
        for viewport in ("mobile", "tablet", "desktop")
    ]

    artifacts: dict[str, str] = {
        "contrast_lint": json.dumps(
            {
                "schema": "light.visual_qa.v1",
                "verdict": "pass",
                "pixel_review_done": False,
                "counts": {"critical": 0, "important": 0, "total": 0},
                "issues": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "ai_tell_lint": "CLEAN: no AI-tells found.\n",
        "audit_checklist": "\n".join(
            [f"[PASS] R{i}: selftest" for i in range(1, 8)]
            + ["--- 7/7 rules passed ---", ""]
        ),
        "browser_qa": json.dumps(
            {
                "schema": "light.frontend.browser_qa.v1",
                "status": "WARN",
                "target": "selftest",
                "viewports": [
                    {
                        "viewport": viewport,
                        "status": "WARN" if viewport == "mobile" else "PASS",
                        "screenshot": screenshots[viewport],
                        "screenshot_sha256": screenshot_hashes[viewport],
                    }
                    for viewport in ("mobile", "tablet", "desktop")
                ],
                "runtime_errors": [],
                "coverage": {"real_chromium": True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        "render_review": "# Render review\n\n三视口截图已回看，无 critical。\n",
    }
    for gate, content in artifacts.items():
        path = root / spec["qa"][gate]["artifact"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        spec["qa"][gate]["artifact_sha256"] = _file_sha(path)


def _selftest() -> int:
    repo_root = pathlib.Path(__file__).resolve()
    while repo_root != repo_root.parent and not (repo_root / "_shared" / "__init__.py").exists():
        repo_root = repo_root.parent
    e2e_root = repo_root / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="frontend_delivery_", dir=e2e_root) as td:
        root = pathlib.Path(td)
        base = _base()
        _materialize_evidence(base, root)
        good = evaluate(base, root=root, as_of="2026-07-05")
        assert good["status"] == "PASS", json.dumps(good, ensure_ascii=False, indent=2)

        bad = json.loads(json.dumps(base))
        bad["decisions"][1]["authority"] = "agent"
        bad["decisions"][2]["options_presented"] = ["Vite + React"]
        bad["sources"][0]["license"] = "unknown"
        bad["sources"].append(
            {
                "source_id": "S3",
                "name": "Paid hero prompt",
                "kind": "template",
                "use": "copy_code",
                "locator": "https://example.invalid/paid",
                "access_tier": "paid",
                "license": "unknown",
                "last_checked": "2026-07-05",
            }
        )
        bad["token_system"]["single_token_source"] = False
        bad["token_system"]["foreign_hardcoded_colors_remaining"] = True
        bad["qa"]["contrast_lint"]["status"] = "FAIL"
        bad["qa"]["browser_qa"]["status"] = "UNAVAILABLE"
        bad["qa"]["render_review"]["status"] = "NOT_RUN"
        report = evaluate(bad, root=root, as_of="2026-07-05")
        assert report["status"] == "FAIL", json.dumps(report, ensure_ascii=False, indent=2)
        codes = {issue["code"] for issue in report["issues"]}
        expected = {
            "DECISION_AUTHORITY_GAP",
            "USER_DECISION_OPTIONS_GAP",
            "SOURCE_LICENSE_GAP",
            "RESTRICTED_SOURCE_AUTH_GAP",
            "TOKEN_SINGLE_SOURCE_GAP",
            "FOREIGN_COLOR_DRIFT",
            "QA_FAIL",
            "QA_UNAVAILABLE",
            "QA_NOT_RUN",
            "READY_WITHOUT_BROWSER_QA",
            "READY_WITHOUT_RENDER_REVIEW",
        }
        assert expected <= codes, (expected, codes)

        truth_gap = json.loads(json.dumps(base))
        truth_gap["decisions"][1]["authority"] = "not_required"
        truth_gap["sources"][0]["last_checked"] = "2999-01-01"
        truth_gap["qa"]["audit_checklist"]["status"] = "NOT_REQUIRED"
        truth_gap["qa"]["ai_tell_lint"]["artifact"] = "../outside.txt"
        truth_gap["qa"]["browser_qa"]["status"] = "PASS"
        truth_gap["qa"]["render_review"]["reviewed_at"] = "2999-01-01"
        truth_gap["token_system"]["token_source_sha256"] = "sha256:" + "0" * 64
        truth_report = evaluate(truth_gap, root=root, as_of="2026-07-05")
        truth_codes = {issue["code"] for issue in truth_report["issues"]}
        truth_expected = {
            "REQUIRED_DECISION_AUTHORITY_GAP",
            "SOURCE_LAST_CHECKED_FUTURE",
            "FINAL_QA_STATUS_GAP",
            "QA_ARTIFACT_PATH_GAP",
            "BROWSER_QA_STATUS_DRIFT",
            "RENDER_REVIEW_DATE_FUTURE",
            "TOKEN_SOURCE_HASH_MISMATCH",
        }
        assert truth_expected <= truth_codes, (truth_expected, truth_codes)

        screenshot_gap = json.loads(json.dumps(base))
        browser_report_path = root / "qa" / "browser.json"
        browser_report = json.loads(browser_report_path.read_text(encoding="utf-8"))
        browser_report["viewports"][0]["screenshot_sha256"] = "sha256:" + "0" * 64
        bad_browser_path = root / "qa" / "browser-bad-screenshot.json"
        bad_browser_path.write_text(json.dumps(browser_report, ensure_ascii=False, indent=2), encoding="utf-8")
        screenshot_gap["qa"]["browser_qa"]["artifact"] = bad_browser_path.relative_to(root).as_posix()
        screenshot_gap["qa"]["browser_qa"]["artifact_sha256"] = _file_sha(bad_browser_path)
        screenshot_gap["qa"]["render_review"]["screenshots"][0]["sha256"] = "sha256:" + "0" * 64
        screenshot_report = evaluate(screenshot_gap, root=root, as_of="2026-07-05")
        screenshot_codes = {issue["code"] for issue in screenshot_report["issues"]}
        assert "BROWSER_QA_SCREENSHOT_HASH_MISMATCH" in screenshot_codes, screenshot_codes
        assert "RENDER_REVIEW_SCREENSHOT_HASH_MISMATCH" in screenshot_codes, screenshot_codes

        partial = json.loads(json.dumps(base))
        partial["delivery_claim"] = "PARTIAL_BROWSER_UNAVAILABLE"
        partial["qa"]["browser_qa"] = {
            "status": "UNAVAILABLE",
            "reason": "playwright unavailable in CI",
        }
        partial_report = evaluate(partial, root=root, as_of="2026-07-05")
        assert partial_report["status"] == "PARTIAL", json.dumps(
            partial_report, ensure_ascii=False, indent=2
        )
        assert "QA_UNAVAILABLE" in {issue["code"] for issue in partial_report["issues"]}
    print("design_delivery_gate selftest PASS: decisions/dates/sources/tokens/artifact-hash/screenshot-hash/browser/render")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--root", help="project root for verifying token, QA artifacts, and screenshots")
    parser.add_argument("--as-of", help="YYYY-MM-DD; defaults to today and blocks future evidence dates")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("need --input or --selftest")
    input_path = pathlib.Path(args.input).resolve()
    spec = json.loads(input_path.read_text(encoding="utf-8-sig"))
    root = pathlib.Path(args.root).resolve() if args.root else input_path.parent
    report = evaluate(spec, root=root, as_of=args.as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
