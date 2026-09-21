#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate research-plan success/failure/inconclusive branches and guardrails.

Research plans often over-specify "what counts as success" and under-specify
"what makes us stop, downgrade, or admit no conclusion".  This gate turns that
reviewer question into a machine-checkable contract:

  - every hypothesis has success / failure / inconclusive branches;
  - every branch has a quantitative condition, action kind, and claim impact;
  - inconclusive/failure branches cannot keep a confirmatory claim alive;
  - guardrails or an explicit not-applicable rationale are declared;
  - post-data amendments are append-only / exploratory-only and authorized.

PASS means the decision tree is structurally auditable.  It does not prove that
thresholds, guardrails, or actions are scientifically optimal.
"""
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
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.research_failure_tree.v1"
REPORT_SCHEMA = "light.research_failure_tree_report.v1"

BRANCHES = ("success", "failure", "inconclusive")
ACTION_KINDS = {
    "PROCEED_CONFIRMATORY",
    "PROCEED_SECONDARY",
    "MARK_EXPLORATORY",
    "DOWNGRADE_CLAIM",
    "COLLECT_MORE_DATA",
    "REPLAN",
    "STOP_NO_GO",
    "REPORT_INCONCLUSIVE",
}
SUCCESS_ACTIONS = {"PROCEED_CONFIRMATORY", "PROCEED_SECONDARY"}
NON_SUCCESS_ACTIONS = {
    "MARK_EXPLORATORY",
    "DOWNGRADE_CLAIM",
    "COLLECT_MORE_DATA",
    "REPLAN",
    "STOP_NO_GO",
    "REPORT_INCONCLUSIVE",
}
GUARDRAIL_DIRECTIONS = {"<", "<=", ">", ">=", "outside_range", "inside_range"}
POST_DATA_POLICIES = {"EXPLORATORY_ONLY", "NEW_VERSION_ONLY"}
PLAN_STATES = {"DRAFT", "AUTHORIZED", "AMENDED"}

PLACEHOLDER_RE = re.compile(r"^\s*(\{\{.*\}\}|TODO|TBD|待填|待定|[-—–]|n/?a|unknown|)\s*$", re.I)
QUANT_RE = re.compile(r"\d|[<>≥≤=]|p\s*[<>=]|%|percent|百分|CI|置信区间", re.I)
SHA_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def _real(value: Any) -> bool:
    if value in (None, [], {}):
        return False
    if isinstance(value, str):
        return not PLACEHOLDER_RE.match(value)
    return True


def _quantified(value: Any) -> bool:
    return _real(value) and bool(QUANT_RE.search(str(value)))


def _date_not_future(value: Any, today: dt.date) -> bool:
    try:
        parsed = dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return False
    return parsed <= today


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA_RE.fullmatch(value))


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    today = dt.date.fromisoformat(str(as_of)) if as_of else dt.date.today()
    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    if spec.get("plan_state") not in PLAN_STATES:
        add("PLAN_STATE_GAP", "plan_state", "plan_state 必须是 DRAFT/AUTHORIZED/AMENDED")
    if not _real(spec.get("project")):
        add("PROJECT_GAP", "project", "缺 project")

    hypotheses = spec.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        add("HYPOTHESIS_TREE_GAP", "hypotheses", "缺 hypothesis failure tree")
        hypotheses = []
    seen: set[str] = set()
    for index, row in enumerate(hypotheses):
        loc = f"hypotheses[{index}]"
        if not isinstance(row, dict):
            add("HYPOTHESIS_ROW_GAP", loc, "hypothesis row 必须是 object")
            continue
        hid = str(row.get("id") or "")
        if not hid or hid in seen:
            add("HYPOTHESIS_ID_GAP", loc, "hypothesis id 缺失或重复")
        seen.add(hid)
        if not _real(row.get("claim")):
            add("HYPOTHESIS_CLAIM_GAP", loc, "hypothesis 缺 claim")
        endpoint = row.get("primary_endpoint")
        if not isinstance(endpoint, dict) or not all(
            _real(endpoint.get(field)) for field in ("metric", "unit", "timepoint")
        ):
            add("PRIMARY_ENDPOINT_BRANCH_GAP", loc, "failure tree 缺 primary_endpoint metric/unit/timepoint")

        branches = row.get("branches")
        if not isinstance(branches, dict):
            add("BRANCH_TREE_GAP", f"{loc}.branches", "缺 success/failure/inconclusive 三分支")
            continue
        branch_actions: dict[str, str] = {}
        for branch in BRANCHES:
            branch_loc = f"{loc}.branches.{branch}"
            branch_spec = branches.get(branch)
            if not isinstance(branch_spec, dict):
                add("BRANCH_TREE_GAP", branch_loc, f"缺 {branch} branch")
                continue
            if not _quantified(branch_spec.get("condition")):
                add(
                    "BRANCH_CONDITION_GAP", f"{branch_loc}.condition",
                    f"{branch} branch 缺可量化 condition",
                )
            action_kind = branch_spec.get("action_kind")
            if action_kind not in ACTION_KINDS:
                add("BRANCH_ACTION_GAP", f"{branch_loc}.action_kind", f"{branch} action_kind 非法")
            else:
                branch_actions[branch] = str(action_kind)
            if not _real(branch_spec.get("claim_impact")):
                add("BRANCH_CLAIM_IMPACT_GAP", f"{branch_loc}.claim_impact", f"{branch} 缺 claim_impact")
            if branch != "success" and action_kind in SUCCESS_ACTIONS:
                add(
                    "NON_SUCCESS_OVERCLAIM",
                    f"{branch_loc}.action_kind",
                    f"{branch} branch 不能继续 confirmatory/secondary 成功动作",
                )
            if branch == "success" and action_kind in NON_SUCCESS_ACTIONS:
                add("SUCCESS_ACTION_MISMATCH", f"{branch_loc}.action_kind", "success branch 却使用失败/无结论动作")
        if (
            branch_actions.get("failure") == branch_actions.get("success")
            or branch_actions.get("inconclusive") == branch_actions.get("success")
        ):
            add(
                "BRANCH_ACTION_COLLAPSE", f"{loc}.branches",
                "failure/inconclusive 与 success 动作相同；方案只会报喜，不能证伪或降 claim",
            )

    guardrails = spec.get("guardrails")
    rationale = spec.get("guardrail_not_applicable_rationale")
    if not isinstance(guardrails, list) or not guardrails:
        if _real(rationale):
            add("GUARDRAIL_JUSTIFIED_ABSENCE", "guardrails", "无 guardrail，但给出适用性理由；需人工复核", "warn")
            guardrails = []
        else:
            add("GUARDRAIL_GAP", "guardrails", "缺 guardrail/counter-metric/kill criterion，且无不适用理由")
            guardrails = []
    for index, row in enumerate(guardrails):
        loc = f"guardrails[{index}]"
        if not isinstance(row, dict):
            add("GUARDRAIL_ROW_GAP", loc, "guardrail row 必须是 object")
            continue
        for field in ("id", "metric", "threshold", "monitored_during", "kill_action", "claim_impact"):
            if not _real(row.get(field)):
                add("GUARDRAIL_FIELD_GAP", f"{loc}.{field}", f"guardrail 缺 {field}")
        if row.get("direction") not in GUARDRAIL_DIRECTIONS:
            add("GUARDRAIL_DIRECTION_GAP", f"{loc}.direction", "direction 必须是 < <= > >= outside_range inside_range")
        if str(row.get("kill_action") or "").strip().casefold() in {"ignore", "none", "无", "不处理"}:
            add("GUARDRAIL_KILL_ACTION_GAP", f"{loc}.kill_action", "guardrail 触发后不能写忽略/不处理")

    stopping = spec.get("stopping")
    if not isinstance(stopping, dict):
        add("STOPPING_TREE_GAP", "stopping", "缺 stopping object")
    else:
        if not _real(stopping.get("rule")) or not _quantified(stopping.get("limit")):
            add("STOPPING_RULE_GAP", "stopping", "stopping 缺 rule 或可量化 limit")
        if not _real(stopping.get("action_on_exhaustion")):
            add("STOPPING_ACTION_GAP", "stopping.action_on_exhaustion", "资源/样本/时间耗尽时缺默认动作")

    amendment = spec.get("amendment_policy")
    if not isinstance(amendment, dict):
        add("AMENDMENT_POLICY_GAP", "amendment_policy", "缺 amendment_policy")
    else:
        if amendment.get("post_data_changes") not in POST_DATA_POLICIES:
            add("POST_DATA_POLICY_GAP", "amendment_policy.post_data_changes", "数据后变更必须 EXPLORATORY_ONLY 或 NEW_VERSION_ONLY")
        if amendment.get("authorization_required") is not True:
            add("AMENDMENT_AUTH_GAP", "amendment_policy.authorization_required", "计划变更必须要求用户/PI 授权")
        if not _real(amendment.get("deviation_log")):
            add("DEVIATION_LOG_GAP", "amendment_policy.deviation_log", "缺 deviation_log locator/path")

    authorization = spec.get("authorization") or {}
    if spec.get("plan_state") in {"AUTHORIZED", "AMENDED"}:
        for field in ("actor", "authorization_id", "authorized_at", "plan_sha256"):
            if not _real(authorization.get(field)):
                add("AUTHORIZATION_GAP", f"authorization.{field}", f"授权态缺 {field}")
        if _real(authorization.get("authorized_at")) and not _date_not_future(authorization["authorized_at"], today):
            add("AUTHORIZATION_DATE_INVALID", "authorization.authorized_at", "authorized_at 非 ISO 日期或来自未来")
        if _real(authorization.get("plan_sha256")) and not _sha(authorization["plan_sha256"]):
            add("AUTHORIZATION_HASH_GAP", "authorization.plan_sha256", "授权 plan_sha256 必须是 sha256:<64 hex>")

    status = "FAIL" if any(item["severity"] == "error" for item in issues) else "WARN" if issues else "PASS"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "advancement": "BLOCK" if status == "FAIL" else "ALLOW_WITH_DECISION" if status == "WARN" else "ALLOW",
        "project": spec.get("project"),
        "issues": issues,
        "honesty": (
            "PASS 只表示成功/失败/无结论分支、guardrail、stopping 与 amendment policy 结构闭合；"
            "不证明阈值科学最优、伦理合规或领域专家已批准。"
        ),
    }


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "project": "demo",
        "plan_state": "AUTHORIZED",
        "hypotheses": [{
            "id": "H1",
            "claim": "method improves F1 over strong baseline",
            "primary_endpoint": {"metric": "F1", "unit": "percentage point", "timepoint": "test set freeze v1"},
            "branches": {
                "success": {
                    "condition": "F1 improvement >= 3 percentage points and q < 0.05",
                    "action_kind": "PROCEED_CONFIRMATORY",
                    "claim_impact": "允许写 confirmatory improvement claim",
                },
                "failure": {
                    "condition": "F1 improvement < 1 percentage point or q >= 0.05",
                    "action_kind": "REPLAN",
                    "claim_impact": "不得写 superiority；回 research-plan 重设假设或设计",
                },
                "inconclusive": {
                    "condition": "95% CI crosses SESOI [-1, 3] percentage points",
                    "action_kind": "REPORT_INCONCLUSIVE",
                    "claim_impact": "只能写精度不足/无结论，不写支持",
                },
            },
        }],
        "guardrails": [{
            "id": "G1",
            "metric": "minority subgroup F1",
            "direction": ">=",
            "threshold": "0.70",
            "monitored_during": "primary evaluation",
            "kill_action": "降级 claim 并补 subgroup analysis；若低于 0.60 则 STOP_NO_GO",
            "claim_impact": "guardrail 未过不得宣称普遍有效",
        }],
        "stopping": {
            "rule": "fixed-N with budget cap",
            "limit": "N=240 independent subjects or GPU budget=80h",
            "action_on_exhaustion": "若未达到 precision，报告 inconclusive 或降 claim",
        },
        "amendment_policy": {
            "post_data_changes": "EXPLORATORY_ONLY",
            "authorization_required": True,
            "deviation_log": ".light/deviations.md",
        },
        "authorization": {
            "actor": "user",
            "authorization_id": "auth-001",
            "authorized_at": "2026-07-05",
            "plan_sha256": "sha256:" + "a" * 64,
        },
    }


def _selftest() -> int:
    good = evaluate(_base(), as_of="2026-07-05")
    assert good["status"] == "PASS", good
    missing_branch = json.loads(json.dumps(_base()))
    missing_branch["hypotheses"][0]["branches"].pop("failure")
    assert "BRANCH_TREE_GAP" in {i["code"] for i in evaluate(missing_branch, as_of="2026-07-05")["issues"]}
    overclaim = json.loads(json.dumps(_base()))
    overclaim["hypotheses"][0]["branches"]["inconclusive"]["action_kind"] = "PROCEED_CONFIRMATORY"
    assert "NON_SUCCESS_OVERCLAIM" in {i["code"] for i in evaluate(overclaim, as_of="2026-07-05")["issues"]}
    no_guardrail = json.loads(json.dumps(_base()))
    no_guardrail["guardrails"] = []
    assert "GUARDRAIL_GAP" in {i["code"] for i in evaluate(no_guardrail, as_of="2026-07-05")["issues"]}
    justified = json.loads(json.dumps(_base()))
    justified["guardrails"] = []
    justified["guardrail_not_applicable_rationale"] = "pure archival descriptive plan; no intervention or system output"
    assert evaluate(justified, as_of="2026-07-05")["status"] == "WARN"
    future_auth = json.loads(json.dumps(_base()))
    future_auth["authorization"]["authorized_at"] = "2999-01-01"
    assert "AUTHORIZATION_DATE_INVALID" in {
        i["code"] for i in evaluate(future_auth, as_of="2026-07-05")["issues"]
    }
    bad_hash = json.loads(json.dumps(_base()))
    bad_hash["authorization"]["plan_sha256"] = "sha256:not-a-real-hash"
    assert "AUTHORIZATION_HASH_GAP" in {i["code"] for i in evaluate(bad_hash, as_of="2026-07-05")["issues"]}
    print("failure_tree_gate selftest PASS: branch/guardrail/stopping/amendment/auth fail-closed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="research-plan failure tree / guardrail gate")
    parser.add_argument("--input", help="failure-tree JSON")
    parser.add_argument("--as-of", help="YYYY-MM-DD；测试/复核时固定当前日")
    parser.add_argument("--json-out", help="写报告 JSON")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("--input required unless --selftest")
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = evaluate(spec, as_of=args.as_of)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        pathlib.Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
