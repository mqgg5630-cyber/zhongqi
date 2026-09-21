#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选择最简单充分的 Light 执行模式；只给计划，不启动 agent 或外部动作。"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.execution_mode.v1"
HIGH_IMPACT_FLAGS = {
    "remote_execution", "paid_resource", "external_write", "will_publish",
    "will_submit", "deletes_or_overwrites", "modifies_user_work",
    "affects_people", "legal_or_ethics_sensitive", "uses_private_data",
}
HIGH_IMPACT_ACTION_WORDS = {
    "push", "publish", "submit", "delete", "overwrite", "deploy",
    "remote", "paid", "spend", "charge", "email", "message",
}
DECISION_CHECKPOINT_SCHEMA = "light.decision_checkpoint.v1"


def _decision_authorized(spec: dict[str, Any]) -> bool:
    checkpoint = spec.get("decision_checkpoint")
    if not isinstance(checkpoint, dict):
        return False
    return (
        checkpoint.get("schema") == DECISION_CHECKPOINT_SCHEMA
        and checkpoint.get("status") == "PASS"
        and checkpoint.get("allowed") is True
        and bool(str(checkpoint.get("authorization_id") or "").strip())
    )


def _cost_trigger(spec: dict[str, Any], key: str) -> str | None:
    if key not in spec or spec[key] in (None, ""):
        return None
    value = spec[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} 必须是数字")
    return f"{key}>0" if value > 0 else None


def _high_impact_triggers(spec: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    for key in sorted(HIGH_IMPACT_FLAGS):
        if key not in spec:
            continue
        if not isinstance(spec[key], bool):
            raise ValueError(f"{key} 必须是 JSON boolean")
        if spec[key]:
            triggers.append(key)
    risk = str(spec.get("risk") or spec.get("risk_level") or "").strip().lower()
    if risk == "high":
        triggers.append("risk=high")
    if "reversible" in spec:
        if not isinstance(spec["reversible"], bool):
            raise ValueError("reversible 必须是 JSON boolean")
        if spec["reversible"] is False:
            triggers.append("reversible=false")
    for key in ("cost_usd", "estimated_cost_usd", "budget_spend_usd"):
        trigger = _cost_trigger(spec, key)
        if trigger:
            triggers.append(trigger)
    action_text = " ".join(
        str(spec.get(key) or "").lower()
        for key in ("action", "action_kind", "operation", "side_effect")
    )
    for word in sorted(HIGH_IMPACT_ACTION_WORDS):
        if word in action_text:
            triggers.append(f"action:{word}")
    return sorted(set(triggers))


def choose(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("task profile 必须是 JSON object")
    required = (
        "complexity", "path_predictable", "subtasks_independent",
        "clear_evaluator", "requirements_complete", "user_decision_needed",
    )
    missing = [key for key in required if key not in spec]
    if missing:
        return {
            "schema": SCHEMA_ID,
            "status": "UNRESOLVED",
            "mode": None,
            "ask": f"请先确认：{missing[0]}",
            "reason": f"缺少会改变执行方式的字段：{missing}",
        }

    complexity = str(spec["complexity"])
    if complexity not in {"simple", "complex"}:
        raise ValueError("complexity 必须是 simple 或 complex")
    boolean_fields = required[1:]
    bad_booleans = [key for key in boolean_fields if not isinstance(spec[key], bool)]
    if bad_booleans:
        raise ValueError(f"这些字段必须是 JSON boolean：{bad_booleans}")
    high_impact = _high_impact_triggers(spec)
    if not spec["requirements_complete"]:
        return {
            "schema": SCHEMA_ID,
            "status": "UNRESOLVED",
            "mode": None,
            "ask": spec.get("requirements_question") or "哪项交付要求仍未确定？",
            "reason": "需求不完整，继续编排会放大返工",
            "risk_triggers": high_impact,
        }
    if high_impact and not _decision_authorized(spec):
        return {
            "schema": SCHEMA_ID,
            "status": "UNRESOLVED",
            "mode": None,
            "ask": (
                spec.get("decision_question")
                or "该动作命中高风险/不可逆触发器；请先生成 light.decision.v1 并通过 decision_checkpoint.py。"
            ),
            "reason": "高风险、付费、远程、发布、投稿、删除、覆盖或不可逆动作不能靠执行模式自动放行",
            "risk_triggers": high_impact,
            "requires_decision_checkpoint": True,
        }
    if spec["user_decision_needed"]:
        return {
            "schema": SCHEMA_ID,
            "status": "UNRESOLVED",
            "mode": None,
            "ask": spec.get("decision_question") or "请确认会改变执行路线的关键取舍。",
            "reason": "存在必须由用户拍板的战略选择",
            "risk_triggers": high_impact,
            "requires_decision_checkpoint": False,
        }
    predictable = spec["path_predictable"]
    independent = spec["subtasks_independent"]
    evaluator = spec["clear_evaluator"]
    categories = int(spec.get("distinct_categories", 1))
    if categories < 1:
        raise ValueError("distinct_categories 必须 >=1")
    dynamic = bool(spec.get("dynamic_decomposition", False))
    budget_parallel = bool(spec.get("budget_allows_parallel", False))
    iterative = bool(spec.get("iterative_improvement", False))
    if evaluator and iterative and int(spec.get("max_iterations", 0)) < 1:
        return {
            "schema": SCHEMA_ID,
            "status": "UNRESOLVED",
            "mode": None,
            "ask": "请确认 evaluator loop 的最大修订轮数或成本上限。",
            "reason": "有评价器但没有停止预算，可能形成无界循环",
        }

    if complexity == "simple":
        mode, reason = "direct", "任务简单，单线执行可直接验证"
    elif evaluator and iterative:
        mode, reason = "evaluator_loop", "有清晰评价器且迭代产生可测改进"
    elif independent and categories > 1 and budget_parallel:
        mode, reason = "parallel", "多个独立子任务且额外成本已纳入预算"
    elif dynamic and not predictable:
        mode, reason = "orchestrated", "子任务无法预先固定，需要动态分解"
    elif categories > 1:
        mode, reason = "routed", "输入类别可区分，适合路由到专门流程"
    else:
        mode, reason = "fixed_workflow", "步骤可预定义，固定流程更可预测"

    return {
        "schema": SCHEMA_ID,
        "status": "PASS",
        "mode": mode,
        "reason": reason,
        "human_checkpoints": list(spec.get("human_checkpoints", [])),
        "stop_condition": spec.get("stop_condition") or "artifact + end-state + verification",
        "does_not_execute": True,
        "risk_triggers": high_impact,
        "requires_decision_checkpoint": False,
    }


def _selftest() -> int:
    base = {
        "complexity": "simple",
        "path_predictable": True,
        "subtasks_independent": False,
        "clear_evaluator": True,
        "requirements_complete": True,
        "user_decision_needed": False,
    }
    assert choose(base)["mode"] == "direct"
    parallel = dict(base, complexity="complex", subtasks_independent=True,
                    distinct_categories=3, budget_allows_parallel=True,
                    clear_evaluator=False)
    assert choose(parallel)["mode"] == "parallel"
    coupled = dict(parallel, subtasks_independent=False, path_predictable=False,
                   dynamic_decomposition=True)
    assert choose(coupled)["mode"] == "orchestrated"
    fixed = dict(base, complexity="complex", clear_evaluator=False)
    assert choose(fixed)["mode"] == "fixed_workflow"
    unresolved = choose({"complexity": "complex"})
    assert unresolved["status"] == "UNRESOLVED" and unresolved["mode"] is None
    evaluated = dict(base, complexity="complex", iterative_improvement=True,
                     max_iterations=3)
    assert choose(evaluated)["mode"] == "evaluator_loop"
    unbounded = dict(base, complexity="complex", iterative_improvement=True)
    assert choose(unbounded)["status"] == "UNRESOLVED"
    strategic = dict(base, user_decision_needed=True,
                     decision_question="请选择速度或精度优先。")
    assert choose(strategic)["ask"] == "请选择速度或精度优先。"
    remote_paid = dict(base, remote_execution=True, estimated_cost_usd=3.5)
    blocked = choose(remote_paid)
    assert blocked["status"] == "UNRESOLVED"
    assert blocked["requires_decision_checkpoint"] is True
    assert {"remote_execution", "estimated_cost_usd>0"} <= set(blocked["risk_triggers"])
    authorized_remote = dict(remote_paid, decision_checkpoint={
        "schema": DECISION_CHECKPOINT_SCHEMA,
        "status": "PASS",
        "allowed": True,
        "authorization_id": "AUTH-remote",
    })
    assert choose(authorized_remote)["mode"] == "direct"
    irreversible = dict(base, reversible=False, user_decision_needed=False)
    assert choose(irreversible)["status"] == "UNRESOLVED"
    publish = dict(base, action_kind="submit manuscript")
    assert "action:submit" in choose(publish)["risk_triggers"]
    print("execution_mode selftest PASS: execution modes + authorization triggers")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    args = parser.parse_args()
    if args.input:
        with open(args.input, encoding="utf-8-sig") as handle:
            result = choose(json.load(handle))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())
