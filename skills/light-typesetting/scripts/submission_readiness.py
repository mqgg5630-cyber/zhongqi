#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Derive submission readiness from separate build, visual, metadata, and profile evidence."""
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

SCHEMA_ID = "light.submission_readiness_input.v1"
REPORT_SCHEMA = "light.submission_readiness_report.v1"
STATES = (
    "INVENTORIED", "SOURCE_BUILDABLE", "TECHNICALLY_CHECKED",
    "VISUALLY_CHECKED", "METADATA_MATCHED", "VENUE_READY", "USER_APPROVED",
)
PROFILE_STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE"}
CLAIM_KINDS = {"AVAILABLE", "FUNCTIONAL", "REUSABLE", "REPRODUCED", "REPLICATED"}
RELATIONSHIPS = {"AUTHOR_TEAM", "INDEPENDENT_TEAM", "FORMAL_REVIEW_BODY"}


def _hash(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _hash_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _same_hash(left: Any, right: Any) -> bool:
    return _hash(left) and _hash(right) and _hash_text(left) == _hash_text(right)


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def evaluate(spec: dict[str, Any], as_of: dt.date | None = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    as_of = as_of or dt.date.today()
    requested = spec.get("requested_state", "VENUE_READY")
    if requested not in STATES:
        raise ValueError("requested_state 非法")
    evidence = spec.get("evidence")
    profile = spec.get("venue_profile")
    if not isinstance(evidence, dict) or not isinstance(profile, dict):
        raise ValueError("evidence/venue_profile 类型错误")
    issues: list[dict[str, str]] = []
    checks: dict[str, dict[str, Any]] = {}

    def add(code: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    def state(name: str, passed: bool, reason: str) -> None:
        checks[name] = {"status": "PASS" if passed else "BLOCKED", "reason": reason}

    inventory = evidence.get("inventory") or {}
    inventory_ok = (
        inventory.get("status") == "PASS"
        and _hash(inventory.get("manifest_sha256"))
        and _int(inventory.get("file_count"), 0) > 0
    )
    if not inventory_ok:
        add("INVENTORY_EVIDENCE_GAP", "INVENTORIED 缺 PASS/file_count/manifest SHA-256")
    state("INVENTORIED", inventory_ok, "source inventory with manifest hash")

    compile_row = evidence.get("compile") or {}
    compile_pdf_sha256 = compile_row.get("pdf_sha256")
    compile_page_count = _int(compile_row.get("page_count"), 0)
    compile_ok = (
        inventory_ok
        and compile_row.get("status") == "PASS"
        and _int(compile_row.get("exit_code")) == 0
        and _hash(compile_pdf_sha256)
        and compile_page_count > 0
        and _int(compile_row.get("unresolved_references")) == 0
        and _int(compile_row.get("unresolved_citations")) == 0
    )
    if compile_row.get("status") == "PASS" and (
        _int(compile_row.get("unresolved_references")) > 0
        or _int(compile_row.get("unresolved_citations")) > 0
    ):
        add("PASS_WITH_UNRESOLVED_REFS", "exit 0 但仍有 unresolved refs/citations")
    if not compile_ok:
        add("SOURCE_BUILD_EVIDENCE_GAP", "SOURCE_BUILDABLE 证据不闭合")
    if compile_row.get("status") == "PASS" and compile_page_count <= 0:
        add("COMPILE_PAGE_COUNT_GAP", "compile PASS 必须记录 PDF page_count")
    state(
        "SOURCE_BUILDABLE",
        compile_ok,
        "compile PASS + PDF hash/page count + zero unresolved references",
    )

    technical = evidence.get("technical") or {}
    technical_ok = (
        compile_ok
        and technical.get("status") == "PASS"
        and bool(technical.get("checks"))
        and _hash(technical.get("log_sha256"))
        and bool(technical.get("tool_versions"))
    )
    if not technical_ok:
        add("TECHNICAL_EVIDENCE_GAP", "技术检查缺 checks/log hash/tool versions")
    state("TECHNICALLY_CHECKED", technical_ok, "lint/preflight evidence is separate from compile")

    visual = evidence.get("visual") or {}
    page_count = _int(visual.get("page_count"), 0)
    pages = visual.get("pages") or []
    visual_pdf_match = _same_hash(visual.get("source_pdf_sha256"), compile_pdf_sha256)
    indexed = {
        int(row.get("page")) for row in pages
        if isinstance(row, dict)
        and type(row.get("page")) is int
        and 1 <= int(row.get("page")) <= page_count
        and _hash(row.get("render_sha256"))
        and row.get("review_status") == "PASS"
        and bool(row.get("render_tool"))
        and bool(row.get("reviewer") or row.get("reviewer_id"))
        and _date(row.get("reviewed_at")) is not None
        and _date(row.get("reviewed_at")) <= as_of
    }
    visual_ok = (
        technical_ok and visual.get("status") == "PASS"
        and visual_pdf_match
        and page_count > 0 and len(pages) == page_count
        and page_count == compile_page_count
        and indexed == set(range(1, page_count + 1))
    )
    if visual.get("status") == "PASS" and not visual_pdf_match:
        add("VISUAL_PDF_HASH_MISMATCH", "visual.source_pdf_sha256 必须等于 compile.pdf_sha256")
    if visual.get("status") == "PASS" and page_count != compile_page_count:
        add("PAGE_COUNT_MISMATCH", "visual.page_count 必须等于 compile.page_count")
    if not visual_ok:
        add(
            "PAGE_RENDER_COVERAGE_GAP",
            "VISUALLY_CHECKED 要求同一 PDF、逐页 render hash、reviewer/reviewed_at/tool 与 PASS",
        )
    state("VISUALLY_CHECKED", visual_ok, "every PDF page has rendered and reviewed evidence")

    metadata = evidence.get("metadata") or {}
    metadata_pdf_match = _same_hash(metadata.get("source_pdf_sha256"), compile_pdf_sha256)
    metadata_ok = (
        visual_ok
        and metadata.get("status") == "PASS"
        and _hash(metadata.get("report_sha256"))
        and metadata_pdf_match
        and not metadata.get("identity_leak")
        and metadata.get("manuscript_identity_match") is True
    )
    if metadata.get("status") == "PASS" and not metadata_pdf_match:
        add("METADATA_PDF_HASH_MISMATCH", "metadata.source_pdf_sha256 必须等于 compile.pdf_sha256")
    if metadata.get("identity_leak"):
        add("METADATA_IDENTITY_LEAK", "PDF metadata/filename/embedded property 泄露身份")
    if not metadata_ok:
        add("METADATA_EVIDENCE_GAP", "METADATA_MATCHED 证据不闭合")
    state("METADATA_MATCHED", metadata_ok, "identity/title/anonymity metadata checked")

    source = profile.get("source") or {}
    profile_state = source.get("status")
    if profile_state not in PROFILE_STATES:
        raise ValueError("venue_profile.source.status 非法")
    checked_at = _date(source.get("checked_at"))
    max_age = _int(profile.get("max_age_days"), 0)
    profile_current = (
        profile_state == "VERIFIED"
        and source.get("kind") == "OFFICIAL"
        and bool(source.get("url") or source.get("locator"))
        and checked_at is not None
        and max_age > 0
        and (as_of - checked_at).days <= max_age
        and (as_of - checked_at).days >= 0
    )
    if profile_state == "VERIFIED" and not profile_current:
        add(
            "VENUE_PROFILE_STALE_OR_UNPROVEN",
            "VERIFIED profile 缺官方来源、有效日期，或超过 max_age_days",
            "unresolved",
        )
    elif profile_state != "VERIFIED":
        add("VENUE_PROFILE_UNVERIFIED", f"profile source={profile_state}", "unresolved")
    manuscript_type = spec.get("manuscript_article_type")
    profile_type = profile.get("article_type")
    article_match = bool(manuscript_type and profile_type and manuscript_type == profile_type)
    if not article_match:
        add(
            "ARTICLE_TYPE_MISMATCH",
            "manuscript article_type 与 profile 不一致或缺失",
        )
    compliance = evidence.get("compliance") or {}
    compliance_pdf_match = _same_hash(compliance.get("source_pdf_sha256"), compile_pdf_sha256)
    compliance_profile_match = (
        compliance.get("venue") == profile.get("venue")
        and compliance.get("article_type") == profile.get("article_type")
    )
    compliance_ok = (
        compliance.get("status") == "PASS"
        and _int(compliance.get("critical_count")) == 0
        and _hash(compliance.get("report_sha256"))
        and compliance_pdf_match
        and compliance_profile_match
    )
    if compliance.get("status") == "PASS" and not compliance_pdf_match:
        add("COMPLIANCE_PDF_HASH_MISMATCH", "compliance.source_pdf_sha256 必须等于 compile.pdf_sha256")
    if compliance.get("status") == "PASS" and not compliance_profile_match:
        add("COMPLIANCE_PROFILE_MISMATCH", "compliance 必须绑定同一 venue 与 article_type")
    if not compliance_ok:
        add("COMPLIANCE_EVIDENCE_GAP", "venue compliance 缺 PASS/zero critical/report hash/PDF/profile binding")
    venue_ok = metadata_ok and profile_current and article_match and compliance_ok
    state("VENUE_READY", venue_ok, "fresh official article-type profile + compliance")

    selection = spec.get("user_approval") or {}
    approved_at = _date(selection.get("approved_at"))
    user_ok = (
        venue_ok
        and selection.get("actor") == "user"
        and bool(selection.get("authorization_id"))
        and selection.get("scope") == "submission_package"
        and _same_hash(selection.get("pdf_sha256"), compile_pdf_sha256)
        and approved_at is not None
        and approved_at <= as_of
    )
    if requested == "USER_APPROVED" and not user_ok:
        add("USER_APPROVAL_GAP", "最终提交包缺用户本人、授权 id、submission_package scope、PDF hash 或有效日期")
    state("USER_APPROVED", user_ok, "direct user authorization; never portal submission")

    for row in spec.get("artifact_claims") or []:
        if not isinstance(row, dict):
            raise ValueError("artifact_claim 必须是 object")
        kind = row.get("kind")
        relationship = row.get("evaluator_relationship")
        if kind not in CLAIM_KINDS or relationship not in RELATIONSHIPS:
            raise ValueError("artifact kind/evaluator_relationship 非法")
        if row.get("status") not in {"NOT_CLAIMED", "PLANNED", "VERIFIED"}:
            raise ValueError("artifact claim status 非法")
        if row.get("status") == "VERIFIED" and not _hash(row.get("evidence_sha256")):
            add("ARTIFACT_CLAIM_PROVENANCE_GAP", f"{kind} 缺 evidence SHA-256")
        if kind in {"REPRODUCED", "REPLICATED"} and relationship == "AUTHOR_TEAM":
            add("FALSE_INDEPENDENCE_CLAIM", f"{kind} 不能由作者团队自验升级")
        if kind == "REPLICATED" and row.get("uses_author_artifacts") is not False:
            add("REPLICATION_USES_AUTHOR_ARTIFACTS", "REPLICATED 必须不依赖作者 artifacts")
        if kind in {"FUNCTIONAL", "REUSABLE"} and row.get("execution_status") != "PASS":
            add("ARTIFACT_NOT_EXERCISED", f"{kind} 缺真实 execution PASS")

    reached_index = -1
    for index, name in enumerate(STATES):
        if checks[name]["status"] == "PASS" and index == reached_index + 1:
            reached_index = index
        else:
            break
    achieved = STATES[reached_index] if reached_index >= 0 else None
    requested_ok = reached_index >= STATES.index(requested)
    if not requested_ok and not any(x["severity"] == "error" for x in issues):
        add("REQUESTED_STATE_UNRESOLVED", f"未达到 requested_state={requested}", "unresolved")
    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues or not requested_ok else "PASS"
    )
    return {
        "schema": REPORT_SCHEMA, "status": status, "requested_state": requested,
        "achieved_state": achieved, "states": checks, "issues": issues,
        "artifact_boundary": (
            "Available/Functional/Reusable/Reproduced/Replicated 分开；"
            "本报告记录证据，不授予 ACM 或其他机构 badge。"
        ),
        "pdf_evidence_boundary": "visual/metadata/compliance/user approval must bind to compile.pdf_sha256.",
        "submission_boundary": "USER_APPROVED 仍不表示已向 portal 提交。",
    }


def _base() -> dict[str, Any]:
    h = "sha256:" + "b" * 64
    return {
        "schema": SCHEMA_ID, "requested_state": "VENUE_READY",
        "manuscript_article_type": "research-article",
        "venue_profile": {
            "venue": "Example Venue", "article_type": "research-article",
            "max_age_days": 7,
            "source": {
                "status": "VERIFIED", "kind": "OFFICIAL",
                "url": "https://official.example/authors", "checked_at": "2026-07-04",
            },
        },
        "evidence": {
            "inventory": {"status": "PASS", "file_count": 5, "manifest_sha256": h},
            "compile": {
                "status": "PASS", "exit_code": 0, "pdf_sha256": h,
                "page_count": 2, "unresolved_references": 0, "unresolved_citations": 0,
            },
            "technical": {
                "status": "PASS", "checks": ["preflight", "lint"],
                "log_sha256": h, "tool_versions": {"latex": "actual-version"},
            },
            "visual": {
                "status": "PASS", "source_pdf_sha256": h, "page_count": 2,
                "pages": [
                    {
                        "page": 1, "render_sha256": h, "render_tool": "pdftoppm",
                        "review_status": "PASS", "reviewer_id": "local-reviewer",
                        "reviewed_at": "2026-07-04",
                    },
                    {
                        "page": 2, "render_sha256": h, "render_tool": "pdftoppm",
                        "review_status": "PASS", "reviewer_id": "local-reviewer",
                        "reviewed_at": "2026-07-04",
                    },
                ],
            },
            "metadata": {
                "status": "PASS", "source_pdf_sha256": h, "report_sha256": h,
                "identity_leak": False, "manuscript_identity_match": True,
            },
            "compliance": {
                "status": "PASS", "source_pdf_sha256": h, "venue": "Example Venue",
                "article_type": "research-article", "critical_count": 0,
                "report_sha256": h,
            },
        },
        "artifact_claims": [],
    }


def _selftest() -> int:
    assert evaluate(_base(), dt.date(2026, 7, 4))["status"] == "PASS"
    refs = json.loads(json.dumps(_base()))
    refs["evidence"]["compile"]["unresolved_references"] = 1
    assert "PASS_WITH_UNRESOLVED_REFS" in {
        x["code"] for x in evaluate(refs, dt.date(2026, 7, 4))["issues"]
    }
    stale = json.loads(json.dumps(_base()))
    stale["venue_profile"]["source"]["checked_at"] = "2026-06-01"
    assert evaluate(stale, dt.date(2026, 7, 4))["status"] == "UNRESOLVED"
    leak = json.loads(json.dumps(_base()))
    leak["evidence"]["metadata"]["identity_leak"] = True
    assert evaluate(leak, dt.date(2026, 7, 4))["status"] == "FAIL"
    mismatched_pdf = json.loads(json.dumps(_base()))
    mismatched_pdf["evidence"]["visual"]["source_pdf_sha256"] = "sha256:" + "d" * 64
    assert "VISUAL_PDF_HASH_MISMATCH" in {
        x["code"] for x in evaluate(mismatched_pdf, dt.date(2026, 7, 4))["issues"]
    }
    missing_page_review = json.loads(json.dumps(_base()))
    del missing_page_review["evidence"]["visual"]["pages"][0]["reviewed_at"]
    assert "PAGE_RENDER_COVERAGE_GAP" in {
        x["code"] for x in evaluate(missing_page_review, dt.date(2026, 7, 4))["issues"]
    }
    wrong_profile = json.loads(json.dumps(_base()))
    wrong_profile["evidence"]["compliance"]["article_type"] = "short-paper"
    assert "COMPLIANCE_PROFILE_MISMATCH" in {
        x["code"] for x in evaluate(wrong_profile, dt.date(2026, 7, 4))["issues"]
    }
    false_replication = json.loads(json.dumps(_base()))
    false_replication["artifact_claims"] = [{
        "kind": "REPLICATED", "status": "VERIFIED",
        "evidence_sha256": "sha256:" + "c" * 64,
        "evaluator_relationship": "AUTHOR_TEAM",
        "uses_author_artifacts": True,
    }]
    assert "FALSE_INDEPENDENCE_CLAIM" in {
        x["code"] for x in evaluate(false_replication, dt.date(2026, 7, 4))["issues"]
    }
    print("submission_readiness selftest PASS: 状态链/refs/逐页/profile/article/badge independence")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--as-of")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    as_of = _date(args.as_of) if args.as_of else dt.date.today()
    if args.as_of and as_of is None:
        parser.error("--as-of 必须为 YYYY-MM-DD")
    report = evaluate(
        json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig")),
        as_of,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        pathlib.Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
