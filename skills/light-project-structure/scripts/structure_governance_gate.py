#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project-structure governance gate.

Validate that a scaffold/intake/migration/rollback delivery is honest about
profile choice, existing-project safety, template provenance, residual
placeholders, secret handling, environment checks, authorization, and rollback.

This script is deliberately a local report, not light.findings.v1: project
structure remains an off-DAG overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from datetime import date
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.project_structure.governance.v1"
REPORT_SCHEMA = "light.project_structure.governance.v1.report"
DOCTOR_SCHEMA = "light.project_structure.environment_doctor.v1"
PROFILES = {"python-research", "r-research", "mixed-research", "paper-only", "existing-custom"}
MODES = {"scaffold", "intake", "apply", "rollback"}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.I)
SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.I)
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
FORBIDDEN_APPLY_KINDS = {"delete", "overwrite", "git_rm_cached", "dvc_init", "config_rewrite"}
PLACEHOLDER_TEXT_RE = re.compile(
    r"(?:"
    r"^unknown$|^todo$|^tbd$|^none$|^n/?a$|"
    r"user[-_ ]?supplied|replace[-_ ]?me|placeholder|"
    r"<[^>]+>|\{\{[^}]+\}\}|\$\{[^}]+\}"
    r")",
    re.I,
)


def _issue(
    severity: str,
    code: str,
    locator: str,
    message: str,
    suggestion: str = "",
) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "locator": locator,
        "message": message,
        "suggestion": suggestion,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA_RE.match(value))


def _real_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not PLACEHOLDER_TEXT_RE.search(value.strip())
    )


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path_in_light(path: Any) -> bool:
    if not isinstance(path, str):
        return False
    normalized = path.replace("\\", "/").strip("/")
    return normalized == ".light" or normalized.startswith(".light/")


def _path_escape(path: Any) -> bool:
    if not isinstance(path, str):
        return False
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return False
    if normalized.startswith("/") or normalized.startswith("//"):
        return True
    if WINDOWS_ABSOLUTE_RE.match(normalized):
        return True
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return ".." in parts


def _env_check(checks: dict[str, Any], tool: str) -> dict[str, Any]:
    if tool in {"r", "rscript"}:
        return _as_dict(checks.get("r") or checks.get("rscript"))
    return _as_dict(checks.get(tool))


def _validate_profile(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    project = _as_dict(payload.get("project"))
    selected = str(project.get("selected_profile") or "")
    if selected not in PROFILES:
        issues.append(_issue(
            "critical",
            "UNKNOWN_PROFILE",
            "project.selected_profile",
            f"未知 profile={selected!r}；必须从 structure-profiles.json 的最小 profile 选择。",
        ))
    reason = _as_dict(project.get("profile_reason"))
    artifact_types = [str(x).lower() for x in _as_list(reason.get("artifact_types"))]
    required = [
        "artifact_types",
        "artifact_evidence",
        "team_scale",
        "why_minimal",
        "reason_source",
        "rejected_profiles",
        "profile_recommendation",
    ]
    missing = [key for key in required if key not in reason]
    if missing:
        issues.append(_issue(
            "major",
            "PROFILE_REASON_INCOMPLETE",
            "project.profile_reason",
            f"profile 选择理由缺少字段：{', '.join(missing)}。",
            "按 artifact 类型、团队规模、交付物和被拒 profile 说明为什么是最小足够结构。",
        ))
    evidence = [
        _as_dict(item)
        for item in _as_list(reason.get("artifact_evidence"))
    ]
    evidenced_types = {
        str(item.get("artifact_type") or "").lower()
        for item in evidence
        if _real_text(item.get("locator"))
        and item.get("source") in {"observed", "policy"}
    }
    missing_evidence = {
        item
        for item in artifact_types
        if item not in {"unknown", "not_required"} and item not in evidenced_types
    }
    if missing_evidence:
        issues.append(_issue(
            "critical",
            "ARTIFACT_TYPE_EVIDENCE_MISSING",
            "project.profile_reason.artifact_evidence",
            f"artifact types 缺少 observed/policy 定位证据：{sorted(missing_evidence)}。",
        ))
    recommendation = _as_dict(reason.get("profile_recommendation"))
    recommended = str(recommendation.get("recommended_profile") or "")
    if recommended and recommended not in PROFILES:
        issues.append(_issue(
            "critical",
            "PROFILE_RECOMMENDATION_INVALID",
            "project.profile_reason.profile_recommendation.recommended_profile",
            f"推荐 profile={recommended!r} 不在已知 profile 中。",
        ))
    if (
        recommended in PROFILES
        and selected != recommended
        and not _real_text(recommendation.get("override_reason"))
    ):
        issues.append(_issue(
            "critical",
            "PROFILE_SELECTION_UNJUSTIFIED",
            "project.profile_reason.profile_recommendation",
            f"所选 {selected!r} 与证据推荐 {recommended!r} 不一致，且没有用户 override reason。",
        ))
    if reason.get("fixed_tree_imposed") is True:
        issues.append(_issue(
            "critical",
            "FIXED_TREE_IMPOSED",
            "project.profile_reason.fixed_tree_imposed",
            "不得把固定 23 目录或数据科学目录强套到所有学科/已有仓库。",
        ))
    if "r" in artifact_types and selected == "python-research":
        issues.append(_issue(
            "critical",
            "PROFILE_MISMATCH_R_PROJECT",
            "project.selected_profile",
            "artifact_types 含 R，但选择 python-research 且无混合/R profile。",
            "选 r-research/mixed-research，或把 R 需求降为 UNKNOWN 并解释。",
        ))
    required_profile_types = {
        "python-research": {"python"},
        "r-research": {"r"},
        "mixed-research": {"python", "r"},
        "paper-only": {"paper"},
    }.get(selected, set())
    profile_types_missing = required_profile_types - set(artifact_types)
    if profile_types_missing:
        issues.append(_issue(
            "critical",
            "PROFILE_LANGUAGE_EVIDENCE_MISSING",
            "project.profile_reason.artifact_types",
            f"所选 {selected!r} 缺少对应 artifact evidence：{sorted(profile_types_missing)}。",
            "从项目文件获得 observed signal，或由用户在 policy.project.artifact_types 明确声明。",
        ))
    if "python" in artifact_types and selected == "r-research":
        issues.append(_issue(
            "critical",
            "PROFILE_MISMATCH_PYTHON_PROJECT",
            "project.selected_profile",
            "artifact_types 含 Python，但选择 r-research 且无 mixed/custom override。",
        ))
    if (
        {"code", "python", "r", "data"} & set(artifact_types)
        and selected == "paper-only"
    ):
        issues.append(_issue(
            "critical",
            "PAPER_ONLY_WITH_CODE",
            "project.selected_profile",
            "paper-only profile 不应吞掉真实代码或数据交付物。",
        ))


def _validate_existing_safety(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    mode = str(payload.get("mode") or "")
    existing = _as_dict(payload.get("existing_project"))
    is_existing = existing.get("present") is True
    if is_existing and mode == "scaffold":
        issues.append(_issue(
            "critical",
            "SCAFFOLD_ON_EXISTING_PROJECT",
            "mode",
            "已有项目不能直接 scaffold；必须先只读 intake，再让用户看 plan。",
        ))
    if is_existing and existing.get("inventory_read_only") is not True:
        issues.append(_issue(
            "critical",
            "INTAKE_NOT_READ_ONLY",
            "existing_project.inventory_read_only",
            "已有项目盘点必须只读；inventory 不是移动授权。",
        ))
    if is_existing and existing.get("source_unchanged") is not True and mode in {"intake", "scaffold"}:
        issues.append(_issue(
            "critical",
            "SOURCE_MUTATED_DURING_INTAKE",
            "existing_project.source_unchanged",
            "intake/scaffold 阶段发生源目录变化。",
        ))
    if existing.get("untracked_preserved") is False:
        issues.append(_issue(
            "critical",
            "UNTRACKED_NOT_PRESERVED",
            "existing_project.untracked_preserved",
            "未跟踪草稿必须保留；不得整理时顺手丢弃。",
        ))
    if existing.get("light_preserved") is False:
        issues.append(_issue(
            "critical",
            "LIGHT_NOT_PRESERVED",
            "existing_project.light_preserved",
            ".light/ 属 memory-pm，project-structure 必须字节级保留。",
        ))


def _validate_template(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    template = _as_dict(payload.get("template"))
    mode = str(payload.get("mode") or "")
    if mode == "scaffold" or template.get("used") is True or template.get("update_requested") is True:
        provenance = _as_dict(template.get("provenance"))
        required = ("source_locator", "source_sha256", "generator_sha256", "parameters_sha256")
        missing = [key for key in required if not provenance.get(key)]
        if missing:
            issues.append(_issue(
                "major",
                "TEMPLATE_PROVENANCE_MISSING",
                "template.provenance",
                f"模板/脚手架交付缺少 provenance 字段：{', '.join(missing)}。",
            ))
        for key in ("source_sha256", "generator_sha256", "parameters_sha256"):
            if provenance.get(key) and not _is_sha(provenance.get(key)):
                issues.append(_issue(
                    "major",
                    "BAD_TEMPLATE_HASH",
                    f"template.provenance.{key}",
                    f"{key} 不是 SHA-256。",
                ))
        scan = _as_dict(template.get("residual_scan"))
        if scan.get("performed") is not True:
            issues.append(_issue(
                "critical",
                "TEMPLATE_RESIDUAL_SCAN_MISSING",
                "template.residual_scan",
                "模板生成后必须扫描 cookiecutter/copier/Jinja 占位符与 TODO_TEMPLATE 残留。",
            ))
        for idx, finding in enumerate(_as_list(scan.get("findings"))):
            obj = _as_dict(finding)
            if str(obj.get("status") or "OPEN").upper() not in {"RESOLVED", "ACCEPTED"}:
                issues.append(_issue(
                    "critical",
                    "TEMPLATE_RESIDUAL_OPEN",
                    f"template.residual_scan.findings[{idx}]",
                    "模板占位符/残留未解决，不能交付为可用项目结构。",
                    "替换、删除或显式保留为示例文件并标 ACCEPTED。",
                ))
        if template.get("update_claim") == "merge-guaranteed":
            issues.append(_issue(
                "critical",
                "TEMPLATE_UPDATE_OVERCLAIM",
                "template.update_claim",
                "Copier/Cruft drift detection 不等于安全自动合并保证。",
            ))


def _validate_secret_scan(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    scan = _as_dict(payload.get("secret_scan"))
    if scan.get("performed") is not True:
        issues.append(_issue(
            "critical",
            "SECRET_SCAN_MISSING",
            "secret_scan.performed",
            "结构整理/脚手架交付前必须做 secret scan；.env ignore 不是秘密不会提交的证明。",
        ))
        return
    if scan.get("raw_values_in_report") is True:
        issues.append(_issue(
            "critical",
            "SECRET_VALUE_REPORTED",
            "secret_scan.raw_values_in_report",
            "secret scan 报告不得回显真实 secret 值。",
        ))
    for idx, finding in enumerate(_as_list(scan.get("findings"))):
        obj = _as_dict(finding)
        if "value" in obj or "raw_value" in obj:
            issues.append(_issue(
                "critical",
                "SECRET_VALUE_FIELD_PRESENT",
                f"secret_scan.findings[{idx}]",
                "finding 中不得包含 value/raw_value；只保留 kind、locator、redacted fingerprint。",
            ))
        status = str(obj.get("status") or "OPEN").upper()
        if status not in {"BLOCKED", "EXTERNALIZED", "ACCEPTED_NON_SECRET", "RESOLVED"}:
            issues.append(_issue(
                "critical",
                "SECRET_FINDING_OPEN",
                f"secret_scan.findings[{idx}]",
                f"secret finding status={status} 未被处理。",
            ))


def _validate_environment(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    env = _as_dict(payload.get("environment_doctor"))
    required_tools = [str(x).lower() for x in _as_list(env.get("required_tools"))]
    checks = _as_dict(env.get("checks"))
    if not required_tools:
        issues.append(_issue(
            "major",
            "ENV_REQUIREMENTS_MISSING",
            "environment_doctor.required_tools",
            "必须声明本项目需要哪些工具；没有证据就写 UNKNOWN/NOT_REQUIRED。",
        ))
        return
    for tool in required_tools:
        check = _env_check(checks, tool)
        if not check:
            issues.append(_issue(
                "major",
                "ENV_CHECK_MISSING",
                f"environment_doctor.checks.{tool}",
                f"缺少 {tool} 环境检查结果。",
            ))
            continue
        status = str(check.get("status") or "").upper()
        if status not in {"AVAILABLE", "UNAVAILABLE", "NOT_REQUIRED", "UNKNOWN"}:
            issues.append(_issue(
                "major",
                "BAD_ENV_STATUS",
                f"environment_doctor.checks.{tool}.status",
                f"非法环境状态 {status!r}。",
            ))
        if status == "UNAVAILABLE" and check.get("required") is True:
            issues.append(_issue(
                "critical",
                "REQUIRED_TOOL_UNAVAILABLE",
                f"environment_doctor.checks.{tool}",
                f"必需工具 {tool} 不可用，不能宣称结构已可运行。",
            ))
    if "r" in required_tools and "rscript" not in checks and "r" not in checks:
        issues.append(_issue(
            "critical",
            "R_ENV_CHECK_MISSING",
            "environment_doctor.checks",
            "R/Rscript 被列为需求时必须有环境检查；不能只建 R/ 目录。",
        ))


def _validate_plan(
    payload: dict[str, Any],
    issues: list[dict[str, str]],
    as_of: date,
) -> None:
    plan = _as_dict(payload.get("plan"))
    actions = _as_list(plan.get("actions"))
    mode = str(payload.get("mode") or "")
    if plan.get("force") is True:
        issues.append(_issue("critical", "FORCE_BYPASS_PRESENT", "plan.force", "生命周期没有 --force 绕过。"))
    if mode in {"intake", "apply"}:
        if not isinstance(plan.get("plan_sha256"), str) or not HEX64_RE.match(plan["plan_sha256"]):
            issues.append(_issue(
                "major",
                "PLAN_DIGEST_MISSING",
                "plan.plan_sha256",
                "intake/apply 必须展示 migration plan SHA-256。",
            ))
    seen: set[str] = set()
    blocked: set[str] = set()
    for idx, action in enumerate(actions):
        obj = _as_dict(action)
        aid = str(obj.get("id") or "")
        if not aid:
            issues.append(_issue("major", "ACTION_ID_MISSING", f"plan.actions[{idx}]", "每个 action 必须有稳定 id。"))
        elif aid in seen:
            issues.append(_issue("critical", "DUPLICATE_ACTION_ID", f"plan.actions[{idx}]", f"重复 action id {aid}。"))
        seen.add(aid)
        kind = str(obj.get("kind") or "")
        if kind in FORBIDDEN_APPLY_KINDS and obj.get("status") in {"approved", "applied"}:
            issues.append(_issue(
                "critical",
                "FORBIDDEN_ACTION_APPLIED",
                f"plan.actions[{idx}]",
                f"{kind} 必须作为单独用户决策/手工步骤，不能由 project-structure apply。",
            ))
        if obj.get("blocked") is True:
            blocked.add(aid)
        if obj.get("overwrite") is True or obj.get("target_exists") is True:
            issues.append(_issue(
                "critical",
                "OVERWRITE_RISK",
                f"plan.actions[{idx}]",
                "目标已存在/overwrite 风险不能自动通过。",
            ))
        if obj.get("symlink") is True and obj.get("auto_apply") is True:
            issues.append(_issue(
                "critical",
                "SYMLINK_AUTO_MOVE",
                f"plan.actions[{idx}]",
                "symlink 只能盘点和人工计划，不得自动移动。",
            ))
        if _path_in_light(obj.get("source")) or _path_in_light(obj.get("target")):
            issues.append(_issue(
                "critical",
                "LIGHT_MOVE_PLANNED",
                f"plan.actions[{idx}]",
                ".light/ 内容归 memory-pm；project-structure 不得移动、改写或删除。",
            ))

        if _path_escape(obj.get("source")) or _path_escape(obj.get("target")):
            issues.append(_issue(
                "critical",
                "PATH_ESCAPE_PLANNED",
                f"plan.actions[{idx}]",
                "action source/target 必须是所选项目根内的相对路径；不得含 ..、绝对路径、盘符路径或 UNC 路径。",
            ))

    auth = _as_dict(payload.get("authorization"))
    if mode == "apply":
        if auth.get("schema") != "light.project-structure.v2.authorization":
            issues.append(_issue(
                "critical",
                "AUTHORIZATION_SCHEMA_INVALID",
                "authorization.schema",
                "apply 授权必须使用 light.project-structure.v2.authorization。",
            ))
        if not _real_text(auth.get("authorization_id")):
            issues.append(_issue(
                "critical",
                "AUTHORIZATION_ID_INVALID",
                "authorization.authorization_id",
                "authorization_id 必须是非占位的稳定标识。",
            ))
        if auth.get("plan_sha256") != plan.get("plan_sha256"):
            issues.append(_issue(
                "critical",
                "AUTHORIZATION_PLAN_MISMATCH",
                "authorization.plan_sha256",
                "授权必须绑定当前 plan_sha256；plan 变化需重新授权。",
            ))
        approved_list = _as_list(auth.get("approved_action_ids"))
        approved = {str(x) for x in approved_list if _real_text(x)}
        if not approved:
            issues.append(_issue("critical", "APPROVED_ACTIONS_MISSING", "authorization.approved_action_ids", "apply 必须有明确 action id 授权。"))
        if len(approved) != len(approved_list):
            issues.append(_issue(
                "critical",
                "APPROVED_ACTIONS_INVALID",
                "authorization.approved_action_ids",
                "approved_action_ids 不得包含重复、空值或模板占位。",
            ))
        unknown = approved - seen
        if unknown:
            issues.append(_issue(
                "critical",
                "UNKNOWN_ACTION_AUTHORIZED",
                "authorization.approved_action_ids",
                f"授权包含当前 plan 中不存在的 action：{sorted(unknown)}。",
            ))
        if approved & blocked:
            issues.append(_issue(
                "critical",
                "BLOCKED_ACTION_AUTHORIZED",
                "authorization.approved_action_ids",
                f"授权包含 blocked action：{sorted(approved & blocked)}。",
            ))
        if not _real_text(auth.get("authorized_by")):
            issues.append(_issue(
                "critical",
                "AUTHORIZED_BY_INVALID",
                "authorization.authorized_by",
                "authorized_by 必须是非占位的用户标识。",
            ))
        authorized_at = _parse_date(auth.get("authorized_at"))
        if authorized_at is None:
            issues.append(_issue(
                "critical",
                "AUTHORIZED_AT_INVALID",
                "authorization.authorized_at",
                "authorized_at 必须是严格 YYYY-MM-DD。",
            ))
        elif authorized_at > as_of:
            issues.append(_issue(
                "critical",
                "AUTHORIZED_AT_FUTURE",
                "authorization.authorized_at",
                f"authorized_at 不得晚于核验日 {as_of.isoformat()}。",
            ))


def _validate_rollback(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    mode = str(payload.get("mode") or "")
    rollback = _as_dict(payload.get("rollback"))
    if mode in {"apply", "rollback"}:
        if rollback.get("manifest_available") is not True:
            issues.append(_issue(
                "critical",
                "ROLLBACK_MANIFEST_MISSING",
                "rollback.manifest_available",
                "apply/rollback 交付必须有 rollback manifest 或 rollback plan。",
            ))
        if rollback.get("verified_hashes") is False:
            issues.append(_issue(
                "critical",
                "ROLLBACK_HASH_UNVERIFIED",
                "rollback.verified_hashes",
                "rollback 必须核 before/after hash；不能只说可以恢复。",
            ))


def _validate_applied_manifest(payload: dict[str, Any], issues: list[dict[str, str]]) -> None:
    if str(payload.get("mode") or "") != "apply":
        return
    applied = _as_dict(payload.get("applied_manifest"))
    plan = _as_dict(payload.get("plan"))
    auth = _as_dict(payload.get("authorization"))
    if not applied:
        issues.append(_issue(
            "critical",
            "APPLIED_MANIFEST_BINDING_MISSING",
            "applied_manifest",
            "apply 交付必须展示 applied-manifest 的 plan/auth 文件绑定，而不是只说已移动。",
        ))
        return
    if applied.get("plan_sha256") != plan.get("plan_sha256"):
        issues.append(_issue(
            "critical",
            "APPLIED_PLAN_DIGEST_MISMATCH",
            "applied_manifest.plan_sha256",
            "applied manifest 必须绑定当前 plan_sha256。",
        ))
    plan_binding = _as_dict(applied.get("plan_binding"))
    if (
        not _real_text(plan_binding.get("locator"))
        or not _is_sha(plan_binding.get("file_sha256"))
        or plan_binding.get("plan_sha256") != plan.get("plan_sha256")
    ):
        issues.append(_issue(
            "critical",
            "APPLIED_PLAN_FILE_BINDING_INVALID",
            "applied_manifest.plan_binding",
            "applied manifest 必须记录 plan 文件 locator、文件 SHA-256 与 plan_sha256。",
        ))
    auth_binding = _as_dict(applied.get("authorization_binding"))
    if (
        not _real_text(auth_binding.get("locator"))
        or not _is_sha(auth_binding.get("file_sha256"))
        or not _is_sha(auth_binding.get("canonical_sha256"))
        or auth_binding.get("authorization_id") != auth.get("authorization_id")
        or auth_binding.get("plan_sha256") != auth.get("plan_sha256")
    ):
        issues.append(_issue(
            "critical",
            "APPLIED_AUTH_FILE_BINDING_INVALID",
            "applied_manifest.authorization_binding",
            "applied manifest 必须记录 authorization 文件 locator、文件 SHA-256、canonical SHA-256、authorization_id 与 plan_sha256。",
        ))
    approved = {str(x) for x in _as_list(auth.get("approved_action_ids")) if _real_text(x)}
    bound_actions = {str(x) for x in _as_list(auth_binding.get("approved_action_ids")) if _real_text(x)}
    if approved and bound_actions != approved:
        issues.append(_issue(
            "critical",
            "APPLIED_AUTH_ACTIONS_DRIFT",
            "applied_manifest.authorization_binding.approved_action_ids",
            "applied manifest 记录的 approved action IDs 必须与授权一致。",
        ))
    applied_actions = {
        str(_as_dict(action).get("id"))
        for action in _as_list(applied.get("actions"))
        if _real_text(_as_dict(action).get("id"))
    }
    if not applied_actions:
        issues.append(_issue(
            "critical",
            "APPLIED_ACTIONS_MISSING",
            "applied_manifest.actions",
            "applied manifest 必须列出已执行 action IDs。",
        ))
    elif approved and not applied_actions <= approved:
        issues.append(_issue(
            "critical",
            "APPLIED_ACTIONS_UNAUTHORIZED",
            "applied_manifest.actions",
            f"applied manifest 含未授权 action：{sorted(applied_actions - approved)}。",
        ))


def validate(
    payload: dict[str, Any], as_of: date | None = None
) -> dict[str, Any]:
    cutoff = as_of or date.today()
    issues: list[dict[str, str]] = []
    if payload.get("schema") != SCHEMA_ID:
        issues.append(_issue("critical", "BAD_SCHEMA", "schema", f"schema 必须是 {SCHEMA_ID}。"))
    mode = str(payload.get("mode") or "")
    if mode not in MODES:
        issues.append(_issue("critical", "BAD_MODE", "mode", f"mode 必须是 {sorted(MODES)} 之一。"))

    _validate_profile(payload, issues)
    _validate_existing_safety(payload, issues)
    _validate_template(payload, issues)
    _validate_secret_scan(payload, issues)
    _validate_environment(payload, issues)
    _validate_plan(payload, issues, cutoff)
    _validate_rollback(payload, issues)
    _validate_applied_manifest(payload, issues)

    if any(x["severity"] == "critical" for x in issues):
        status = "FAIL"
    elif issues:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "mode": mode,
        "issue_count": len(issues),
        "issues": issues,
        "input_sha256": _canonical_sha256(payload),
        "honesty": (
            "PASS 只说明结构生命周期证据自洽；不证明数据血缘、许可、实验可复现、统计有效或论文质量。"
        ),
    }


def _windows_rscript_candidates() -> list[str]:
    roots = [
        pathlib.Path("C:/Program Files/R"),
        pathlib.Path("D:/Program Files/R"),
        pathlib.Path("D:/R"),
        pathlib.Path.home() / "AppData/Local/Programs/R",
    ]
    out: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for version_dir in sorted(root.glob("R-*"), reverse=True):
            out.extend([
                str(version_dir / "bin" / "x64" / "Rscript.exe"),
                str(version_dir / "bin" / "Rscript.exe"),
            ])
    return out


def environment_doctor(tools: list[str]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    required_tools: list[str] = []
    for raw in tools:
        tool = str(raw).strip()
        if not tool:
            continue
        key = tool.lower()
        if key in {"none", "not_required", "not-required", "not required"}:
            key = "not_required"
            if key not in required_tools:
                required_tools.append(key)
            checks[key] = {
                "status": "NOT_REQUIRED",
                "path": None,
                "required": False,
            }
            continue
        if key not in required_tools:
            required_tools.append(key)
        candidates = {
            "python": [sys.executable],
            "r": ["Rscript", "R", *_windows_rscript_candidates()],
            "rscript": ["Rscript", "R", *_windows_rscript_candidates()],
        }.get(key, [tool])
        found = None
        for candidate in candidates:
            if os.path.isabs(candidate) and pathlib.Path(candidate).exists():
                found = candidate
                break
            located = shutil.which(candidate)
            if located:
                found = located
                break
        checks[key] = {
            "status": "AVAILABLE" if found else "UNAVAILABLE",
            "path": found or None,
            "required": True,
        }
    return {
        "schema": DOCTOR_SCHEMA,
        "required_tools": required_tools or ["not_required"],
        "checks": checks,
        "honesty": "工具可执行仅证明当前机器能找到入口，不证明项目环境已完整可复现。",
    }


def _good_packet() -> dict[str, Any]:
    sha = "a" * 64
    return {
        "schema": SCHEMA_ID,
        "mode": "intake",
        "project": {
            "selected_profile": "mixed-research",
            "profile_reason": {
                "artifact_types": ["python", "r", "paper", "data"],
                "artifact_evidence": [
                    {
                        "artifact_type": "python",
                        "locator": "pyproject.toml",
                        "source": "observed",
                    },
                    {
                        "artifact_type": "r",
                        "locator": "DESCRIPTION",
                        "source": "observed",
                    },
                    {
                        "artifact_type": "paper",
                        "locator": "paper/main.tex",
                        "source": "observed",
                    },
                    {
                        "artifact_type": "data",
                        "locator": "data/observations.csv",
                        "source": "observed",
                    },
                ],
                "team_scale": "small-team",
                "why_minimal": "mixed Python/R analysis with manuscript output; no monorepo package split yet",
                "reason_source": "observed-and-declared-signatures",
                "rejected_profiles": ["python-research", "r-research", "paper-only"],
                "profile_recommendation": {
                    "recommended_profile": "mixed-research",
                    "selected_matches": True,
                    "override_reason": None,
                },
                "fixed_tree_imposed": False,
            },
        },
        "existing_project": {
            "present": True,
            "inventory_read_only": True,
            "source_unchanged": True,
            "untracked_preserved": True,
            "light_preserved": True,
        },
        "template": {
            "used": False,
            "residual_scan": {"performed": True, "findings": []},
        },
        "secret_scan": {
            "performed": True,
            "raw_values_in_report": False,
            "findings": [],
        },
        "environment_doctor": {
            "required_tools": ["python", "r"],
            "checks": {
                "python": {"status": "AVAILABLE", "required": True},
                "rscript": {"status": "AVAILABLE", "required": True},
            },
        },
        "plan": {
            "plan_sha256": sha,
            "force": False,
            "actions": [{
                "id": "move-0001",
                "kind": "move",
                "source": "old/analysis.py",
                "target": "src/analysis.py",
                "blocked": False,
                "overwrite": False,
                "symlink": False,
            }],
        },
    }


def _good_apply_packet() -> dict[str, Any]:
    packet = json.loads(json.dumps(_good_packet()))
    packet["mode"] = "apply"
    packet["authorization"] = {
        "schema": "light.project-structure.v2.authorization",
        "authorization_id": "auth-move-0001",
        "plan_sha256": packet["plan"]["plan_sha256"],
        "approved_action_ids": ["move-0001"],
        "authorized_by": "project-owner",
        "authorized_at": "2026-07-05",
    }
    packet["rollback"] = {
        "manifest_available": True,
        "verified_hashes": True,
    }
    packet["applied_manifest"] = {
        "plan_sha256": packet["plan"]["plan_sha256"],
        "plan_binding": {
            "locator": "evidence/migration-plan.json",
            "file_sha256": "a" * 64,
            "plan_sha256": packet["plan"]["plan_sha256"],
        },
        "authorization_binding": {
            "locator": "evidence/authorization.json",
            "file_sha256": "b" * 64,
            "canonical_sha256": "sha256:" + "c" * 64,
            "authorization_id": "auth-move-0001",
            "plan_sha256": packet["plan"]["plan_sha256"],
            "approved_action_ids": ["move-0001"],
        },
        "actions": [{"id": "move-0001"}],
    }
    return packet


def _bad_packet() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "mode": "scaffold",
        "project": {
            "selected_profile": "python-research",
            "profile_reason": {
                "artifact_types": ["r", "paper", "data"],
                "team_scale": "UNKNOWN",
                "fixed_tree_imposed": True,
            },
        },
        "existing_project": {
            "present": True,
            "inventory_read_only": False,
            "source_unchanged": False,
            "untracked_preserved": False,
            "light_preserved": False,
        },
        "template": {
            "used": True,
            "update_claim": "merge-guaranteed",
            "provenance": {"source_locator": "template"},
            "residual_scan": {
                "performed": True,
                "findings": [{"locator": "README.md", "pattern": "{{ cookiecutter.project_name }}", "status": "OPEN"}],
            },
        },
        "secret_scan": {
            "performed": True,
            "raw_values_in_report": True,
            "findings": [{"locator": ".env", "kind": "api_key", "raw_value": "REDACTED-IN-BAD-FIXTURE", "status": "OPEN"}],
        },
        "environment_doctor": {
            "required_tools": ["python", "r"],
            "checks": {
                "python": {"status": "AVAILABLE", "required": True},
                "rscript": {"status": "UNAVAILABLE", "required": True},
            },
        },
        "plan": {
            "plan_sha256": "not-a-digest",
            "force": True,
            "actions": [
                {"id": "move-0001", "kind": "move", "source": ".light/passport.yaml", "target": "archive/passport.yaml"},
                {"id": "move-0001", "kind": "delete", "source": "data/raw.csv", "status": "approved"},
                {"id": "move-0002", "kind": "move", "source": "link", "target": "new/link", "symlink": True, "auto_apply": True},
                {"id": "move-0003", "kind": "move", "source": "a.txt", "target": "b.txt", "overwrite": True, "blocked": True},
                {"id": "move-0004", "kind": "move", "source": "old/escape.py", "target": "../outside.py"},
            ],
        },
        "authorization": {
            "plan_sha256": "different",
            "approved_action_ids": ["move-0003"],
            "authorized_by": "",
        },
        "rollback": {
            "manifest_available": False,
            "verified_hashes": False,
        },
    }


def _selftest() -> int:
    good = validate(_good_packet())
    assert good["status"] == "PASS", json.dumps(good, ensure_ascii=False, indent=2)
    bad_profile = _good_packet()
    bad_profile["project"]["selected_profile"] = "python-research"
    bad_profile["project"]["profile_reason"]["artifact_evidence"] = []
    bad_profile_report = validate(bad_profile)
    bad_profile_codes = {item["code"] for item in bad_profile_report["issues"]}
    assert {
        "ARTIFACT_TYPE_EVIDENCE_MISSING",
        "PROFILE_SELECTION_UNJUSTIFIED",
        "PROFILE_MISMATCH_R_PROJECT",
    } <= bad_profile_codes, bad_profile_report
    missing_language = _good_packet()
    missing_language["project"]["profile_reason"]["artifact_types"] = [
        "python",
        "paper",
        "data",
    ]
    missing_language["project"]["profile_reason"]["artifact_evidence"] = [
        item
        for item in missing_language["project"]["profile_reason"][
            "artifact_evidence"
        ]
        if item["artifact_type"] != "r"
    ]
    missing_language_report = validate(missing_language)
    assert any(
        item["code"] == "PROFILE_LANGUAGE_EVIDENCE_MISSING"
        for item in missing_language_report["issues"]
    ), missing_language_report
    cutoff = date.fromisoformat("2026-07-05")
    good_apply = validate(_good_apply_packet(), as_of=cutoff)
    assert good_apply["status"] == "PASS", json.dumps(
        good_apply, ensure_ascii=False, indent=2
    )
    bad_authorization = _good_apply_packet()
    bad_authorization["authorization"].update({
        "authorization_id": "<authorization-id>",
        "approved_action_ids": ["move-9999"],
        "authorized_by": "USER_SUPPLIED",
        "authorized_at": "2099-01-01",
    })
    bad_auth_report = validate(bad_authorization, as_of=cutoff)
    bad_auth_codes = {item["code"] for item in bad_auth_report["issues"]}
    assert {
        "AUTHORIZATION_ID_INVALID",
        "UNKNOWN_ACTION_AUTHORIZED",
        "AUTHORIZED_BY_INVALID",
        "AUTHORIZED_AT_FUTURE",
        "APPLIED_AUTH_FILE_BINDING_INVALID",
        "APPLIED_AUTH_ACTIONS_DRIFT",
    } <= bad_auth_codes, bad_auth_report
    bad_applied = _good_apply_packet()
    bad_applied["applied_manifest"]["plan_binding"]["file_sha256"] = "not-a-sha"
    bad_applied["applied_manifest"]["authorization_binding"][
        "approved_action_ids"
    ] = ["move-9999"]
    bad_applied["applied_manifest"]["actions"] = [{"id": "move-9999"}]
    bad_applied_report = validate(bad_applied, as_of=cutoff)
    bad_applied_codes = {item["code"] for item in bad_applied_report["issues"]}
    assert {
        "APPLIED_PLAN_FILE_BINDING_INVALID",
        "APPLIED_AUTH_ACTIONS_DRIFT",
        "APPLIED_ACTIONS_UNAUTHORIZED",
    } <= bad_applied_codes, bad_applied_report
    bad = validate(_bad_packet())
    assert bad["status"] == "FAIL", json.dumps(bad, ensure_ascii=False, indent=2)
    codes = {item["code"] for item in bad["issues"]}
    expected = {
        "SCAFFOLD_ON_EXISTING_PROJECT",
        "FIXED_TREE_IMPOSED",
        "PROFILE_MISMATCH_R_PROJECT",
        "TEMPLATE_RESIDUAL_OPEN",
        "SECRET_VALUE_REPORTED",
        "SECRET_VALUE_FIELD_PRESENT",
        "REQUIRED_TOOL_UNAVAILABLE",
        "FORCE_BYPASS_PRESENT",
        "LIGHT_MOVE_PLANNED",
        "DUPLICATE_ACTION_ID",
        "FORBIDDEN_ACTION_APPLIED",
        "SYMLINK_AUTO_MOVE",
        "PATH_ESCAPE_PLANNED",
    }
    missing = expected - codes
    assert not missing, (missing, codes)
    doctor = environment_doctor(["python"])
    assert doctor["checks"]["python"]["status"] == "AVAILABLE", doctor
    print("structure_governance_gate selftest PASS: profile/template/secrets/env/plan/rollback")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", help="governance JSON")
    parser.add_argument("--output", help="可选输出 JSON")
    parser.add_argument("--doctor", nargs="+", help="emit environment doctor for required tools")
    parser.add_argument(
        "--as-of",
        help="authorization cutoff date (YYYY-MM-DD; default: local today)",
    )
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if args.doctor:
        report = environment_doctor(args.doctor)
    else:
        if not args.input:
            parser.error("需要 --input、--doctor 或 --selftest")
        payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
        cutoff = _parse_date(args.as_of) if args.as_of else None
        if args.as_of and cutoff is None:
            parser.error("--as-of 必须是严格 YYYY-MM-DD")
        report = validate(payload, as_of=cutoff)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status", "PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
