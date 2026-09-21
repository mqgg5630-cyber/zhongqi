#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对系统设计是否已从约束走到可选择方案与 walking skeleton。

只检查设计包的证据闭包，不替用户选择架构，不声称预测真实性能。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.system_design.readiness.v1"
EVIDENCE = {"VERIFIED", "PLANNED", "UNKNOWN", "UNAVAILABLE", "FAILED"}
AUTH_SCHEMA = "light.system-design.v2.authorization"


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.casefold() not in {
        "unknown", "pending", "todo", "tbd", "n/a", "none", "user_supplied",
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


def _option_packet_digest(spec: dict[str, Any], option: dict[str, Any]) -> str:
    packet = {
        "requirements": spec.get("requirements"),
        "state_model": spec.get("state_model"),
        "fitness_functions": spec.get("fitness_functions"),
        "option": option,
    }
    canonical = json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    today = _as_of_date(as_of)
    phase = spec.get("phase")
    if phase not in {"proposal", "authorized"}:
        raise ValueError("phase 必须为 proposal/authorized")
    req = spec.get("requirements")
    options = spec.get("options")
    if not isinstance(req, dict) or not isinstance(options, list):
        raise ValueError("requirements/options 类型错误")
    issues: list[dict[str, str]] = []

    def add(code: str, message: str, severity: str = "error") -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    for field in ("problem", "users", "critical_use_cases", "constraints", "quality_attributes"):
        value = req.get(field)
        if value in (None, "", []):
            add("REQUIREMENT_GAP", f"requirements.{field} 缺失")
    constraints = req.get("constraints") or []
    constraint_ids: set[str] = set()
    for constraint in constraints:
        if not isinstance(constraint, dict):
            add("CONSTRAINT_INVALID", "每个硬约束必须是 object")
            continue
        constraint_id = str(constraint.get("id") or "")
        if not constraint_id or not constraint.get("text"):
            add("CONSTRAINT_INVALID", "硬约束必须有 id/text")
        elif constraint_id in constraint_ids:
            add("CONSTRAINT_DUPLICATE", f"硬约束 id 重复：{constraint_id}")
        else:
            constraint_ids.add(constraint_id)
    for qa in req.get("quality_attributes") or []:
        if not isinstance(qa, dict) or not all(qa.get(x) for x in ("id", "scenario", "target")):
            add("QUALITY_ATTRIBUTE_UNMEASURABLE", "质量属性必须有 id/scenario/target")
        elif qa.get("evidence_state") not in EVIDENCE:
            add("EVIDENCE_STATE_INVALID", f"质量属性 {qa.get('id')} evidence_state 非法")
    qa_ids = {str(qa.get("id")) for qa in req.get("quality_attributes") or [] if isinstance(qa, dict) and qa.get("id")}

    capacity = req.get("capacity_estimates")
    if not isinstance(capacity, list) or not capacity:
        add("CAPACITY_ESTIMATE_MISSING", "必须显式登记容量/负载估算；未知也要写 UNKNOWN，不能靠脑补规模")
    else:
        for estimate in capacity:
            if not isinstance(estimate, dict):
                add("CAPACITY_ESTIMATE_INVALID", "capacity_estimates 每项必须是 object")
                continue
            eid = estimate.get("id") or "capacity"
            has_value = any(estimate.get(key) not in (None, "", []) for key in ("value", "value_range", "target", "unknown_reason"))
            if not estimate.get("metric") or not estimate.get("unit") or not has_value:
                add("CAPACITY_ESTIMATE_INVALID", f"{eid} 必须有 metric/unit/value 或 UNKNOWN 理由")
            if estimate.get("evidence_state") not in EVIDENCE:
                add("EVIDENCE_STATE_INVALID", f"容量估算 {eid} evidence_state 非法")

    state_model = spec.get("state_model")
    if not isinstance(state_model, dict):
        add("STATE_MODEL_MISSING", "必须声明 current_state/target_state/gaps；绿地项目 current_state 可写 none")
    else:
        for field in ("current_state", "target_state", "gaps"):
            if state_model.get(field) in (None, "", []):
                add("STATE_MODEL_GAP", f"state_model.{field} 缺失")
        if state_model.get("evidence_state") not in EVIDENCE:
            add("EVIDENCE_STATE_INVALID", "state_model.evidence_state 非法")

    fitness_functions = spec.get("fitness_functions")
    fitness_ids: set[str] = set()
    if not isinstance(fitness_functions, list) or not fitness_functions:
        add("FITNESS_FUNCTION_MISSING", "必须定义可复核 fitness functions，避免架构质量只停在形容词")
    else:
        for fitness in fitness_functions:
            if not isinstance(fitness, dict):
                add("FITNESS_FUNCTION_INVALID", "fitness_functions 每项必须是 object")
                continue
            fid = str(fitness.get("id") or "")
            if not fid or fid in fitness_ids:
                add("FITNESS_FUNCTION_INVALID", f"fitness id 缺失或重复：{fid or '<empty>'}")
                continue
            fitness_ids.add(fid)
            if fitness.get("quality_attribute_id") not in qa_ids:
                add("FITNESS_QA_UNKNOWN", f"{fid} 绑定了未登记质量属性 {fitness.get('quality_attribute_id')}")
            for field in ("signal", "threshold", "verification"):
                if not fitness.get(field):
                    add("FITNESS_FUNCTION_INVALID", f"{fid}.{field} 缺失")
            if fitness.get("evidence_state") not in EVIDENCE:
                add("EVIDENCE_STATE_INVALID", f"fitness {fid} evidence_state 非法")

    if len(options) < 2:
        add("DESIGN_IT_TWICE_MISSING", "至少需要两个真正可区分的方案，不能把第一个想法当唯一答案")
    option_ids: set[str] = set()
    option_fingerprints: set[str] = set()
    option_digests: dict[str, str] = {}
    option_action_ids: dict[str, set[str]] = {}
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("option 必须是 object")
        option_id = str(option.get("id") or "")
        if not option_id or option_id in option_ids:
            raise ValueError("option.id 缺失或重复")
        option_ids.add(option_id)
        option_digests[option_id] = _option_packet_digest(spec, option)
        fingerprint = " ".join(str(option.get("summary") or "").casefold().split())
        if fingerprint and fingerprint in option_fingerprints:
            add("OPTION_NOT_DISTINCT", f"{option_id} 与另一方案 summary 相同，未形成真正备选")
        option_fingerprints.add(fingerprint)
        for field in ("summary", "tradeoffs", "rejection_conditions", "reversal_cost"):
            if option.get(field) in (None, "", []):
                add("OPTION_GAP", f"{option_id}.{field} 缺失")
        action_ids = option.get("action_ids")
        if not isinstance(action_ids, list) or not action_ids:
            add("OPTION_ACTION_IDS_MISSING", f"{option_id}.action_ids 缺失；授权无法绑定具体变更")
            option_action_ids[option_id] = set()
        else:
            normalized_actions = [str(action).strip() for action in action_ids if _real(action)]
            if len(normalized_actions) != len(action_ids) or len(set(normalized_actions)) != len(normalized_actions):
                add("OPTION_ACTION_IDS_INVALID", f"{option_id}.action_ids 必须非占位且唯一")
            option_action_ids[option_id] = set(normalized_actions)
        results = option.get("constraint_results")
        if not isinstance(results, list):
            add("CONSTRAINT_MATRIX_MISSING", f"{option_id} 缺 constraint_results")
            continue
        seen: set[str] = set()
        for result in results:
            if not isinstance(result, dict):
                add("CONSTRAINT_RESULT_INVALID", f"{option_id} 的 constraint result 必须是 object")
                continue
            cid = str(result.get("constraint_id") or "")
            status = result.get("status")
            if not cid:
                add("CONSTRAINT_RESULT_INVALID", f"{option_id} 的 constraint_id 缺失")
                continue
            if cid not in constraint_ids:
                add("CONSTRAINT_RESULT_UNKNOWN", f"{option_id} 引用了未登记约束 {cid}")
            seen.add(cid)
            if status not in {"PASS", "FAIL", "UNKNOWN", "UNAVAILABLE"}:
                add("CONSTRAINT_STATUS_INVALID", f"{option_id}/{cid} status 非法")
            if status == "FAIL":
                add("HARD_CONSTRAINT_FAILED", f"{option_id} 违反约束 {cid}")
            if status in {"UNKNOWN", "UNAVAILABLE"}:
                add("CONSTRAINT_UNRESOLVED", f"{option_id}/{cid}={status}", "warn")
            if status == "PASS" and not result.get("evidence"):
                add("CONSTRAINT_EVIDENCE_MISSING", f"{option_id}/{cid} PASS 缺 evidence")
        missing = sorted(constraint_ids - seen)
        if missing:
            add("CONSTRAINT_COVERAGE_GAP", f"{option_id} 未评估约束 {missing}")

        fitness_results = option.get("fitness_results")
        if fitness_ids:
            if not isinstance(fitness_results, list):
                add("FITNESS_MATRIX_MISSING", f"{option_id} 缺 fitness_results")
            else:
                fseen: set[str] = set()
                for result in fitness_results:
                    if not isinstance(result, dict):
                        add("FITNESS_RESULT_INVALID", f"{option_id} 的 fitness result 必须是 object")
                        continue
                    fid = str(result.get("fitness_id") or "")
                    status = result.get("status")
                    if fid not in fitness_ids:
                        add("FITNESS_RESULT_UNKNOWN", f"{option_id} 引用了未登记 fitness {fid}")
                    fseen.add(fid)
                    if status not in {"PASS", "FAIL", "UNKNOWN", "UNAVAILABLE"}:
                        add("FITNESS_STATUS_INVALID", f"{option_id}/{fid} status 非法")
                    if status == "FAIL":
                        add("HARD_FITNESS_FAILED", f"{option_id} 未满足 fitness {fid}")
                    if status in {"UNKNOWN", "UNAVAILABLE"}:
                        add("FITNESS_UNRESOLVED", f"{option_id}/{fid}={status}", "warn")
                    if status == "PASS" and not result.get("evidence"):
                        add("FITNESS_EVIDENCE_MISSING", f"{option_id}/{fid} PASS 缺 evidence")
                fmissing = sorted(fitness_ids - fseen)
                if fmissing:
                    add("FITNESS_COVERAGE_GAP", f"{option_id} 未评估 fitness {fmissing}")

        migration = option.get("migration")
        if not isinstance(migration, dict):
            add("MIGRATION_STANCE_MISSING", f"{option_id} 必须声明迁移/废弃是否适用")
        elif migration.get("applicable") is False:
            if not migration.get("not_applicable_reason"):
                add("MIGRATION_NA_REASON_MISSING", f"{option_id} migration.applicable=false 但缺理由")
        else:
            if migration.get("replacement_first") is not True:
                add("REPLACEMENT_FIRST_REQUIRED", f"{option_id} 必须先证明 replacement 可用")
            consumers = migration.get("consumer_inventory")
            if not isinstance(consumers, list) or not consumers:
                add("CONSUMER_INVENTORY_INVALID", f"{option_id} consumer_inventory 必须是非空对象数组")
            else:
                consumer_ids: set[str] = set()
                for consumer in consumers:
                    if not isinstance(consumer, dict):
                        add("CONSUMER_RECORD_INVALID", f"{option_id} consumer 必须是 object")
                        continue
                    consumer_id = str(consumer.get("id") or "")
                    if not _real(consumer_id) or consumer_id in consumer_ids:
                        add("CONSUMER_RECORD_INVALID", f"{option_id} consumer id 缺失/占位/重复")
                        continue
                    consumer_ids.add(consumer_id)
                    for field in ("interface_id", "owner", "usage_status", "evidence_state"):
                        if not _real(consumer.get(field)):
                            add("CONSUMER_RECORD_INVALID", f"{option_id}/{consumer_id}.{field} 缺失或占位")
                    if consumer.get("usage_status") not in {"ACTIVE", "INACTIVE", "UNKNOWN"}:
                        add("CONSUMER_STATUS_INVALID", f"{option_id}/{consumer_id} usage_status 非法")
                    evidence_state = consumer.get("evidence_state")
                    if evidence_state not in EVIDENCE:
                        add("EVIDENCE_STATE_INVALID", f"{option_id}/{consumer_id} consumer evidence_state 非法")
                    elif evidence_state == "FAILED":
                        add("CONSUMER_EVIDENCE_FAILED", f"{option_id}/{consumer_id} consumer evidence 已失败")
                    if evidence_state == "VERIFIED":
                        if not _real(consumer.get("evidence_locator")):
                            add("CONSUMER_EVIDENCE_MISSING", f"{option_id}/{consumer_id} VERIFIED 缺 evidence_locator")
                        checked_at = _parse_date(consumer.get("checked_at"))
                        if checked_at is None:
                            add("CONSUMER_EVIDENCE_DATE_INVALID", f"{option_id}/{consumer_id} checked_at 必须为 YYYY-MM-DD")
                        elif checked_at > today:
                            add("CONSUMER_EVIDENCE_FUTURE", f"{option_id}/{consumer_id} checked_at 不能晚于核验日")
                    elif evidence_state in {"UNKNOWN", "UNAVAILABLE", "PLANNED"}:
                        if not _real(consumer.get("measurement_plan")):
                            add("CONSUMER_USAGE_UNRESOLVED", f"{option_id}/{consumer_id} 缺 measurement_plan", "warn")
                    if consumer.get("usage_status") == "UNKNOWN" and not _real(
                        consumer.get("measurement_plan")
                    ):
                        add("CONSUMER_USAGE_UNRESOLVED", f"{option_id}/{consumer_id} usage UNKNOWN 且缺 measurement_plan", "warn")
            telemetry = migration.get("telemetry_signal")
            if not isinstance(telemetry, dict):
                add("TELEMETRY_SIGNAL_INVALID", f"{option_id} telemetry_signal 必须是 object")
            else:
                for field in ("metric", "source", "evidence_state"):
                    if not _real(telemetry.get(field)):
                        add("TELEMETRY_SIGNAL_INVALID", f"{option_id}.telemetry_signal.{field} 缺失或占位")
                if telemetry.get("evidence_state") not in EVIDENCE:
                    add("EVIDENCE_STATE_INVALID", f"{option_id} telemetry evidence_state 非法")
                elif telemetry.get("evidence_state") == "FAILED":
                    add("TELEMETRY_EVIDENCE_FAILED", f"{option_id} telemetry evidence 已失败")
                if telemetry.get("evidence_state") == "VERIFIED":
                    if not _real(telemetry.get("evidence_locator")):
                        add("TELEMETRY_EVIDENCE_MISSING", f"{option_id} VERIFIED telemetry 缺 locator")
                    checked_at = _parse_date(telemetry.get("checked_at"))
                    if checked_at is None:
                        add("TELEMETRY_DATE_INVALID", f"{option_id} telemetry.checked_at 必须为 YYYY-MM-DD")
                    elif checked_at > today:
                        add("TELEMETRY_DATE_FUTURE", f"{option_id} telemetry.checked_at 不能晚于核验日")
                elif telemetry.get("evidence_state") in {"UNKNOWN", "UNAVAILABLE", "PLANNED"}:
                    if not _real(telemetry.get("measurement_plan")):
                        add("TELEMETRY_UNRESOLVED", f"{option_id} telemetry 缺 measurement_plan", "warn")
            rollout = migration.get("rollout")
            if not isinstance(rollout, list) or not rollout:
                add("ROLLOUT_PLAN_INVALID", f"{option_id} rollout 必须是非空 phase 数组")
            else:
                rollout_ids: set[str] = set()
                for rollout_phase in rollout:
                    if not isinstance(rollout_phase, dict):
                        add("ROLLOUT_PHASE_INVALID", f"{option_id} rollout phase 必须是 object")
                        continue
                    rollout_id = str(rollout_phase.get("id") or "")
                    if not _real(rollout_id) or rollout_id in rollout_ids:
                        add("ROLLOUT_PHASE_INVALID", f"{option_id} rollout id 缺失/占位/重复")
                    rollout_ids.add(rollout_id)
                    for field in ("entry_condition", "exit_condition", "rollback_trigger"):
                        if not _real(rollout_phase.get(field)):
                            add("ROLLOUT_PHASE_INVALID", f"{option_id}/{rollout_id}.{field} 缺失或占位")
            rollback_plan = migration.get("rollback")
            if not isinstance(rollback_plan, dict) or any(
                not _real(rollback_plan.get(field))
                for field in ("trigger", "action", "verification")
            ):
                add("ROLLBACK_PLAN_INVALID", f"{option_id} rollback 必须有 trigger/action/verification")
            if migration.get("deprecates"):
                window = migration.get("compatibility_window")
                if not isinstance(window, dict) or any(
                    not _real(window.get(field))
                    for field in ("start_condition", "end_condition", "removal_condition")
                ):
                    add("DEPRECATION_WINDOW_INVALID", f"{option_id} compatibility_window 必须有 start/end/removal condition")

    recommendation = spec.get("recommendation")
    if not isinstance(recommendation, dict) or recommendation.get("option_id") not in option_ids:
        add("RECOMMENDATION_MISSING", "必须给推荐方案与理由，但推荐不等于用户选择")
    elif not recommendation.get("rationale"):
        add("RECOMMENDATION_RATIONALE_MISSING", "推荐缺 rationale")

    selection = spec.get("selection")
    if phase == "proposal":
        if selection:
            add("PREMATURE_SELECTION", "proposal 阶段不得预写用户选择")
        if spec.get("authorization"):
            add("PREMATURE_AUTHORIZATION", "proposal 阶段不得预写用户授权")
    else:
        if not isinstance(selection, dict):
            add("USER_SELECTION_MISSING", "authorized 阶段缺用户选择")
        elif selection.get("option_id") not in option_ids or not selection.get("authorization_id"):
            add("USER_SELECTION_INVALID", "selection 缺合法 option_id/authorization_id")
        selected_id = selection.get("option_id") if isinstance(selection, dict) else None
        authorization = spec.get("authorization")
        approved_actions: set[str] = set()
        if not isinstance(authorization, dict):
            add("AUTHORIZATION_MISSING", "authorized 阶段缺完整 authorization")
        else:
            if authorization.get("schema") != AUTH_SCHEMA:
                add("AUTHORIZATION_SCHEMA_GAP", f"authorization.schema 必须为 {AUTH_SCHEMA}")
            authorization_id = authorization.get("authorization_id")
            if not _real(authorization_id):
                add("AUTHORIZATION_ID_GAP", "authorization.authorization_id 缺失或占位")
            elif isinstance(selection, dict) and authorization_id != selection.get("authorization_id"):
                add("AUTHORIZATION_ID_DRIFT", "selection 与 authorization 的 authorization_id 不一致")
            if authorization.get("option_id") != selected_id:
                add("AUTHORIZATION_OPTION_DRIFT", "authorization.option_id 与用户选择不一致")
            expected_digest = option_digests.get(str(selected_id), "")
            supplied_digest = str(authorization.get("option_packet_sha256") or "")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_digest):
                add("AUTHORIZATION_DIGEST_GAP", "authorization.option_packet_sha256 必须为 64 位 SHA-256")
            elif supplied_digest.casefold() != expected_digest.casefold():
                add("AUTHORIZATION_DIGEST_STALE", "方案包已变化，现有授权摘要失效，必须重新授权")
            raw_actions = authorization.get("approved_action_ids")
            if not isinstance(raw_actions, list) or not raw_actions:
                add("AUTHORIZATION_ACTIONS_GAP", "authorization.approved_action_ids 必须列出至少一个具体动作")
            else:
                approved_actions = {str(action).strip() for action in raw_actions if _real(action)}
                if len(approved_actions) != len(raw_actions):
                    add("AUTHORIZATION_ACTIONS_INVALID", "approved_action_ids 必须非占位且唯一")
                unknown_actions = sorted(approved_actions - option_action_ids.get(str(selected_id), set()))
                if unknown_actions:
                    add("AUTHORIZATION_ACTIONS_OUT_OF_SCOPE", f"授权包含方案外动作 {unknown_actions}")
            target = authorization.get("disposable_target")
            if not _real(target):
                add("AUTHORIZATION_TARGET_GAP", "authorization.disposable_target 缺失或占位")
            else:
                target_text = str(target).strip()
                if "://" not in target_text and not pathlib.Path(target_text).is_absolute():
                    add("AUTHORIZATION_TARGET_NOT_ABSOLUTE", "disposable_target 必须是绝对路径或明确数据库 URI")
                if re.search(r"(^|[/_.:-])(prod|production|live)([/_.:-]|$)", target_text, re.I):
                    add("AUTHORIZATION_PRODUCTION_TARGET", "不得把 production/live 目标标成 disposable")
            if authorization.get("disposable_confirmed") is not True:
                add("AUTHORIZATION_DISPOSABLE_GAP", "必须显式 disposable_confirmed=true")
            if not _real(authorization.get("compatibility_choice")):
                add("AUTHORIZATION_COMPATIBILITY_GAP", "compatibility_choice 不能是 UNKNOWN/占位")
            if authorization.get("rollback_choice") != "REQUIRED":
                add("AUTHORIZATION_ROLLBACK_GAP", "系统变更授权不得豁免 rollback；rollback_choice 必须 REQUIRED")
            if not _real(authorization.get("authorized_by")):
                add("AUTHORIZATION_AUTHOR_GAP", "authorized_by 必须是用户提供的可追踪标识")
            authorized_at = _parse_date(authorization.get("authorized_at"))
            if authorized_at is None:
                add("AUTHORIZATION_DATE_GAP", "authorized_at 必须是 YYYY-MM-DD")
            elif authorized_at > today:
                add("AUTHORIZATION_DATE_FUTURE", "authorized_at 不能晚于核验日")
        skeleton = spec.get("walking_skeleton")
        required = ("entry", "core_path", "state_boundary", "observable_result",
                    "failure_probe", "verification", "action_ids")
        if not isinstance(skeleton, dict):
            add("WALKING_SKELETON_MISSING", "授权后必须定义最薄端到端 walking skeleton")
        else:
            missing = [x for x in required if not skeleton.get(x)]
            if missing:
                add("WALKING_SKELETON_GAP", f"walking skeleton 缺 {missing}")
            skeleton_actions = skeleton.get("action_ids")
            if isinstance(skeleton_actions, list):
                normalized = {str(action).strip() for action in skeleton_actions if _real(action)}
                if len(normalized) != len(skeleton_actions):
                    add("WALKING_SKELETON_ACTION_INVALID", "walking_skeleton.action_ids 必须非占位且唯一")
                unapproved = sorted(normalized - approved_actions)
                if unapproved:
                    add("WALKING_SKELETON_UNAUTHORIZED", f"walking skeleton 含未授权动作 {unapproved}")

    errors = [x for x in issues if x["severity"] == "error"]
    warnings = [x for x in issues if x["severity"] == "warn"]
    status = "FAIL" if errors else ("UNRESOLVED" if warnings else "PASS")
    return {
        "schema": SCHEMA_ID,
        "status": status,
        "phase": phase,
        "ready_for_user_decision": phase == "proposal" and status == "PASS",
        "ready_for_implementation": phase == "authorized" and status == "PASS",
        "option_packet_sha256": option_digests,
        "issues": issues,
        "honesty": "PASS 只证明设计包字段和证据闭包自洽，不证明架构在真实负载或故障下达标。",
    }


def _base() -> dict[str, Any]:
    return {
        "phase": "proposal",
        "requirements": {
            "problem": "ingest files", "users": ["researcher"],
            "critical_use_cases": ["upload and inspect"],
            "constraints": [{"id": "local", "text": "local-only"}],
            "quality_attributes": [{
                "id": "latency", "scenario": "single upload", "target": "<2s",
                "evidence_state": "PLANNED",
            }],
            "capacity_estimates": [{
                "id": "upload-qps", "metric": "peak upload requests", "value_range": "1-20",
                "unit": "requests/minute", "evidence_state": "PLANNED",
                "assumption": "early single-lab use; revisit before public launch",
            }],
        },
        "state_model": {
            "current_state": "greenfield/no deployed system",
            "target_state": "one deployable with explicit parse/report boundary",
            "gaps": ["no load evidence yet"],
            "evidence_state": "PLANNED",
        },
        "fitness_functions": [{
            "id": "ff-upload-latency",
            "quality_attribute_id": "latency",
            "signal": "p95 upload-to-report latency",
            "threshold": "<2s for declared capacity range",
            "verification": "walking skeleton e2e timing probe",
            "evidence_state": "PLANNED",
        }],
        "options": [
            {
                "id": "modular", "summary": "modular monolith",
                "tradeoffs": ["simple deploy"], "rejection_conditions": ["independent scaling required"],
                "reversal_cost": "moderate",
                "action_ids": ["create-module-boundaries", "create-api-contract"],
                "constraint_results": [{"constraint_id": "local", "status": "PASS", "evidence": "local process"}],
                "fitness_results": [{"fitness_id": "ff-upload-latency", "status": "PASS", "evidence": "single process avoids network hop"}],
                "migration": {"applicable": False, "not_applicable_reason": "greenfield with no existing consumers"},
            },
            {
                "id": "services", "summary": "two services",
                "tradeoffs": ["operational cost"], "rejection_conditions": ["single operator"],
                "reversal_cost": "hard",
                "action_ids": ["create-service-a", "create-service-b", "create-service-contract"],
                "constraint_results": [{"constraint_id": "local", "status": "PASS", "evidence": "local network"}],
                "fitness_results": [{"fitness_id": "ff-upload-latency", "status": "PASS", "evidence": "same-host call path remains within declared timing probe scope"}],
                "migration": {"applicable": False, "not_applicable_reason": "greenfield with no existing consumers"},
            },
        ],
        "recommendation": {"option_id": "modular", "rationale": "lowest justified complexity"},
    }


def _selftest() -> int:
    proposal = evaluate(_base(), as_of="2026-07-05")
    assert proposal["status"] == "PASS" and proposal["ready_for_user_decision"]
    migration_ready = _base()
    migration_ready["options"][0]["migration"] = {
        "applicable": True,
        "replacement_first": True,
        "consumer_inventory": [{
            "id": "client-web",
            "interface_id": "old-upload-api",
            "owner": "web-team",
            "usage_status": "ACTIVE",
            "evidence_state": "VERIFIED",
            "evidence_locator": "evidence/consumer-usage.json",
            "checked_at": "2026-07-05",
        }],
        "telemetry_signal": {
            "metric": "requests to old-upload-api",
            "source": "gateway access log",
            "evidence_state": "VERIFIED",
            "evidence_locator": "evidence/old-api-traffic.json",
            "checked_at": "2026-07-05",
        },
        "rollout": [{
            "id": "canary",
            "entry_condition": "replacement contract tests pass",
            "exit_condition": "declared canary checks pass",
            "rollback_trigger": "error budget exceeded",
        }],
        "rollback": {
            "trigger": "canary failure",
            "action": "route client-web to old-upload-api",
            "verification": "old path smoke test",
        },
        "deprecates": ["old-upload-api"],
        "compatibility_window": {
            "start_condition": "replacement available",
            "end_condition": "all registered consumers inactive on old path",
            "removal_condition": "zero verified usage and rollback rehearsal pass",
        },
    }
    assert evaluate(migration_ready, as_of="2026-07-05")["status"] == "PASS"
    authorized = _base()
    authorized["phase"] = "authorized"
    digest = _option_packet_digest(authorized, authorized["options"][0])
    authorized["selection"] = {"option_id": "modular", "authorization_id": "auth-20260705-1"}
    authorized["authorization"] = {
        "schema": AUTH_SCHEMA,
        "authorization_id": "auth-20260705-1",
        "option_id": "modular",
        "option_packet_sha256": digest,
        "approved_action_ids": ["create-module-boundaries", "create-api-contract"],
        "disposable_target": "D:/work/system-design-sandbox",
        "disposable_confirmed": True,
        "compatibility_choice": "no existing consumers",
        "rollback_choice": "REQUIRED",
        "authorized_by": "user-message-42",
        "authorized_at": "2026-07-05",
    }
    authorized["walking_skeleton"] = {
        "entry": "upload", "core_path": "parse", "state_boundary": "filesystem",
        "observable_result": "report", "failure_probe": "corrupt input",
        "verification": "e2e test",
        "action_ids": ["create-module-boundaries", "create-api-contract"],
    }
    assert evaluate(authorized, as_of="2026-07-05")["ready_for_implementation"]
    bad = _base()
    bad["options"] = bad["options"][:1]
    assert evaluate(bad, as_of="2026-07-05")["status"] == "FAIL"
    missing_evidence = _base()
    missing_evidence["requirements"].pop("capacity_estimates")
    missing_evidence.pop("state_model")
    missing_evidence["fitness_functions"][0]["threshold"] = ""
    missing_evidence["options"][0]["fitness_results"] = []
    missing_evidence["options"][0]["migration"] = {"applicable": True, "deprecates": ["old-api"]}
    codes = {x["code"] for x in evaluate(missing_evidence, as_of="2026-07-05")["issues"]}
    assert {
        "CAPACITY_ESTIMATE_MISSING", "STATE_MODEL_MISSING", "FITNESS_FUNCTION_INVALID",
        "FITNESS_COVERAGE_GAP", "REPLACEMENT_FIRST_REQUIRED",
        "CONSUMER_INVENTORY_INVALID", "TELEMETRY_SIGNAL_INVALID",
        "ROLLOUT_PLAN_INVALID", "ROLLBACK_PLAN_INVALID", "DEPRECATION_WINDOW_INVALID",
    } <= codes
    future_consumer = json.loads(json.dumps(migration_ready))
    future_consumer["options"][0]["migration"]["consumer_inventory"][0][
        "checked_at"
    ] = "2999-01-01"
    future_consumer["options"][0]["migration"]["telemetry_signal"][
        "evidence_locator"
    ] = "<telemetry>"
    future_codes = {
        x["code"]
        for x in evaluate(future_consumer, as_of="2026-07-05")["issues"]
    }
    assert {
        "CONSUMER_EVIDENCE_FUTURE",
        "TELEMETRY_EVIDENCE_MISSING",
    } <= future_codes
    duplicate = _base()
    duplicate["options"][1]["summary"] = duplicate["options"][0]["summary"].upper()
    assert "OPTION_NOT_DISTINCT" in {x["code"] for x in evaluate(duplicate, as_of="2026-07-05")["issues"]}
    unknown = _base()
    unknown["options"][0]["constraint_results"][0]["status"] = "UNKNOWN"
    unknown["options"][0]["constraint_results"][0].pop("evidence")
    assert evaluate(unknown, as_of="2026-07-05")["status"] == "UNRESOLVED"

    stale = json.loads(json.dumps(authorized))
    stale["options"][0]["summary"] = "changed modular monolith"
    stale_codes = {x["code"] for x in evaluate(stale, as_of="2026-07-05")["issues"]}
    assert "AUTHORIZATION_DIGEST_STALE" in stale_codes

    scope_bad = json.loads(json.dumps(authorized))
    scope_bad["authorization"]["approved_action_ids"].append("drop-production")
    scope_bad["authorization"]["disposable_target"] = "postgres://production/main"
    scope_bad["authorization"]["authorized_at"] = "2999-01-01"
    scope_bad["walking_skeleton"]["action_ids"].append("unapproved-action")
    scope_codes = {x["code"] for x in evaluate(scope_bad, as_of="2026-07-05")["issues"]}
    assert {
        "AUTHORIZATION_ACTIONS_OUT_OF_SCOPE",
        "AUTHORIZATION_PRODUCTION_TARGET",
        "AUTHORIZATION_DATE_FUTURE",
        "WALKING_SKELETON_UNAUTHORIZED",
    } <= scope_codes
    print("design_readiness selftest PASS: proposal/digest-bound-authorization/actions/skeleton")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--as-of", help="YYYY-MM-DD; defaults to today and blocks future authorization dates")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    report = evaluate(
        json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig")),
        as_of=args.as_of,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
