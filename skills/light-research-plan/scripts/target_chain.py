#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate question→estimand→endpoint→analysis→falsifier→action chains."""
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

SCHEMA_ID = "light.research_target_chain.v1"
NODE_TYPES = {
    "QUESTION", "ESTIMAND", "HYPOTHESIS", "PRIMARY_ENDPOINT",
    "EXPLORATORY_ENDPOINT", "ANALYSIS_FAMILY", "FALSIFIER", "ACTION",
}
TIMINGS = {"PRE_DATA", "POST_DATA"}
PLAN_STATES = {"PROPOSED", "AUTHORIZED", "AMENDED"}


def _hash(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _date(value: Any) -> bool:
    try:
        dt.date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _present(value: Any) -> bool:
    return value not in (None, "", [])


def _content_sha256(spec: dict[str, Any]) -> str:
    content = json.loads(json.dumps(spec))
    authorization = content.get("authorization")
    if isinstance(authorization, dict):
        authorization.pop("plan_sha256", None)
    payload = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    plan_state = spec.get("plan_state")
    if plan_state not in PLAN_STATES:
        raise ValueError("plan_state 非法")
    nodes_raw, edges = spec.get("nodes"), spec.get("edges")
    if not isinstance(nodes_raw, list) or not isinstance(edges, list):
        raise ValueError("nodes/edges 必须是 list")
    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    nodes: dict[str, dict[str, Any]] = {}
    by_type: dict[str, list[str]] = {}
    for row in nodes_raw:
        node_id = str(row.get("node_id") or "")
        node_type = row.get("type")
        if not node_id or node_id in nodes or node_type not in NODE_TYPES:
            raise ValueError("node_id 重复/缺失或 type 非法")
        nodes[node_id] = row
        by_type.setdefault(node_type, []).append(node_id)
        if not row.get("statement"):
            add("NODE_STATEMENT_GAP", f"node:{node_id}", "node 缺 statement")
        if node_type in {
            "ESTIMAND", "PRIMARY_ENDPOINT", "EXPLORATORY_ENDPOINT", "ANALYSIS_FAMILY"
        }:
            if row.get("timing") not in TIMINGS:
                add("NODE_TIMING_GAP", f"node:{node_id}", "关键节点缺 PRE_DATA/POST_DATA timing")
        if node_type == "PRIMARY_ENDPOINT" and row.get("timing") == "POST_DATA":
            add(
                "POST_DATA_PRIMARY_ENDPOINT", f"node:{node_id}",
                "数据后确定的 endpoint 不得仍称 primary；请另建 EXPLORATORY_ENDPOINT",
            )
        if node_type == "ESTIMAND":
            for field in (
                "population", "treatment_or_exposure", "outcome", "summary_measure",
                "statistical_unit", "randomization_unit", "analysis_unit",
            ):
                if not row.get(field):
                    add("ESTIMAND_GAP", f"node:{node_id}", f"estimand 缺 {field}")
            units = {
                "statistical_unit": row.get("statistical_unit"),
                "randomization_unit": row.get("randomization_unit"),
                "analysis_unit": row.get("analysis_unit"),
            }
            if all(_present(value) for value in units.values()) and len({str(value).casefold() for value in units.values()}) > 1:
                if not row.get("unit_mismatch_rationale"):
                    add(
                        "ESTIMAND_UNIT_MISMATCH",
                        f"node:{node_id}",
                        "statistical/randomization/analysis unit 不一致但缺 rationale；可能把重复测量、seed、fold 或 cluster 当独立样本",
                    )
        if node_type == "PRIMARY_ENDPOINT":
            for field in (
                "measurement_instrument", "operational_definition", "unit",
                "minimally_meaningful_effect", "missingness_policy",
            ):
                if not row.get(field):
                    add("PRIMARY_ENDPOINT_GAP", f"node:{node_id}", f"primary endpoint 缺 {field}")
        if node_type == "ANALYSIS_FAMILY":
            for field in ("method", "assumptions", "multiplicity"):
                if row.get(field) in (None, "", []):
                    add("ANALYSIS_FAMILY_GAP", f"node:{node_id}", f"analysis family 缺 {field}")
            if row.get("independence_assumption") in (None, "", []):
                add(
                    "INDEPENDENCE_ASSUMPTION_GAP",
                    f"node:{node_id}",
                    "analysis family 缺 independence_assumption；必须说明哪些观测可当独立单位",
                )
        if node_type == "FALSIFIER" and not all(
            row.get(field) for field in ("observation", "threshold")
        ):
            add("FALSIFIER_GAP", f"node:{node_id}", "falsifier 缺 observation/threshold")
        if node_type == "ACTION" and not all(
            row.get(field) for field in ("if_supported", "if_falsified")
        ):
            add("ACTION_BRANCH_GAP", f"node:{node_id}", "action 缺 supported/falsified 两分支")

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    reverse: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for row in edges:
        if not isinstance(row, dict):
            raise ValueError("edge 必须是 object")
        source, target = str(row.get("from") or ""), str(row.get("to") or "")
        if source not in nodes or target not in nodes:
            add("BROKEN_TARGET_EDGE", "edge", f"{source}->{target} 引用未知 node")
            continue
        adjacency[source].add(target)
        reverse[target].add(source)

    colors = {node_id: 0 for node_id in nodes}

    def visit(node_id: str) -> bool:
        colors[node_id] = 1
        for target in adjacency[node_id]:
            if colors[target] == 1 or (colors[target] == 0 and visit(target)):
                return True
        colors[node_id] = 2
        return False

    if any(colors[node_id] == 0 and visit(node_id) for node_id in nodes):
        add("TARGET_CHAIN_CYCLE", "chain", "目标链含循环依赖")

    required_path = (
        "QUESTION", "ESTIMAND", "HYPOTHESIS", "PRIMARY_ENDPOINT",
        "ANALYSIS_FAMILY", "FALSIFIER", "ACTION",
    )
    for left, right in zip(required_path, required_path[1:]):
        for source in by_type.get(left, []):
            targets = adjacency[source]
            if not any(nodes[target]["type"] == right for target in targets):
                add("TARGET_CHAIN_BREAK", f"node:{source}", f"{left} 未连到 {right}")
        for target in by_type.get(right, []):
            parents = reverse[target]
            if not any(nodes[parent]["type"] == left for parent in parents):
                add("TARGET_CHAIN_ORPHAN", f"node:{target}", f"{right} 缺 {left} parent")
    for node_type in required_path:
        if not by_type.get(node_type):
            add("TARGET_NODE_TYPE_MISSING", "chain", f"缺 {node_type}")

    amendments = spec.get("amendments") or []
    if plan_state == "AMENDED" and not amendments:
        add("PLAN_AMENDMENT_GAP", "plan", "AMENDED plan 缺变更账本")
    for row in amendments:
        if not isinstance(row, dict) or not all(
            row.get(field) for field in ("changed_node_id", "reason", "authorization_id", "changed_at")
        ):
            add("PLAN_AMENDMENT_PROVENANCE_GAP", "amendment", "变更缺 node/reason/auth/date")
        elif row.get("changed_node_id") not in nodes:
            add("PLAN_AMENDMENT_UNKNOWN_NODE", "amendment", "变更引用未知 node")
        elif not _date(row.get("changed_at")):
            add("PLAN_AMENDMENT_PROVENANCE_GAP", "amendment", "changed_at 不是 ISO 日期")
        elif (
            _date((spec.get("authorization") or {}).get("authorized_at"))
            and dt.date.fromisoformat(row["changed_at"])
            < dt.date.fromisoformat(spec["authorization"]["authorized_at"])
        ):
            add("PLAN_AMENDMENT_TIME_INVALID", "amendment", "变更时间早于计划授权时间")
        elif row.get("after_data") and not row.get("relabelled_exploratory"):
            add("POST_DATA_CHANGE_NOT_RELABELLED", "amendment", "数据后变更未降级 exploratory")
        elif row.get("after_data") and nodes[row["changed_node_id"]]["type"] == "PRIMARY_ENDPOINT":
            add(
                "POST_DATA_PRIMARY_MUTATION", "amendment",
                "数据后不得覆写原 primary endpoint；保留原节点并另建 EXPLORATORY_ENDPOINT",
            )

    if spec.get("comparative_study"):
        fairness = spec.get("baseline_fairness") or {}
        for field in ("data", "compute", "tuning", "evaluation_protocol"):
            if not fairness.get(field):
                add("BASELINE_FAIRNESS_GAP", "baseline_fairness", f"比较研究缺 {field} 对齐说明")

    risks = spec.get("risk_register") or []
    if not isinstance(risks, list) or not risks:
        add("RISK_REGISTER_GAP", "risk_register", "缺风险登记")
    for row in risks:
        if not isinstance(row, dict) or not all(
            row.get(field) not in (None, "", [])
            for field in ("risk_id", "likelihood", "severity", "mitigation", "owner", "trigger")
        ):
            add("RISK_ROW_GAP", "risk_register", "风险条目缺 likelihood/severity/mitigation/owner/trigger")

    authorization = spec.get("authorization") or {}
    if plan_state in {"AUTHORIZED", "AMENDED"} and not all(
        authorization.get(field)
        for field in ("actor", "authorization_id", "scope", "authorized_at")
    ):
        add("PLAN_AUTHORIZATION_GAP", "authorization", "授权计划缺 actor/id/scope/time")
    if plan_state in {"AUTHORIZED", "AMENDED"} and authorization.get("actor") != "user":
        add("PLAN_AUTHORITY_INVALID", "authorization", "研究计划冻结必须由用户授权")
    if plan_state in {"AUTHORIZED", "AMENDED"}:
        if not _hash(authorization.get("plan_sha256")):
            add("PLAN_LOCK_GAP", "authorization", "授权计划缺 plan SHA-256")
        elif authorization["plan_sha256"].casefold() != _content_sha256(spec):
            add("PLAN_LOCK_MISMATCH", "authorization", "plan SHA-256 与当前计划内容不一致")
        if authorization.get("authorized_at") and not _date(authorization.get("authorized_at")):
            add("PLAN_AUTHORIZATION_GAP", "authorization", "authorized_at 不是 ISO 日期")

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.research_target_chain_report.v1", "status": status,
        "issues": issues,
        "honesty": (
            "本门核计划链、时序、变更与风险字段；PASS 不证明效应存在、样本充分或方法在真实数据上有效。"
        ),
    }


def _base() -> dict[str, Any]:
    nodes = [
        {"node_id": "Q1", "type": "QUESTION", "statement": "Does X improve Y?"},
        {"node_id": "E1", "type": "ESTIMAND", "statement": "mean effect",
         "timing": "PRE_DATA", "population": "declared population",
         "treatment_or_exposure": "X", "outcome": "Y", "summary_measure": "mean difference",
         "statistical_unit": "participant", "randomization_unit": "participant",
         "analysis_unit": "participant"},
        {"node_id": "H1", "type": "HYPOTHESIS", "statement": "X improves Y"},
        {"node_id": "P1", "type": "PRIMARY_ENDPOINT", "statement": "held-out Y",
         "timing": "PRE_DATA", "measurement_instrument": "validated assay",
         "operational_definition": "mean held-out Y over the declared assessment window",
         "unit": "score points", "minimally_meaningful_effect": ">= 2 score points",
         "missingness_policy": "predeclared exclusion plus sensitivity analysis"},
        {"node_id": "A1", "type": "ANALYSIS_FAMILY", "statement": "primary model",
         "timing": "PRE_DATA", "method": "declared test", "assumptions": ["independence"],
         "multiplicity": "one primary endpoint",
         "independence_assumption": "one participant contributes one independent primary endpoint"},
        {"node_id": "F1", "type": "FALSIFIER", "statement": "no practical benefit",
         "observation": "upper CI below practical threshold", "threshold": "delta"},
        {"node_id": "D1", "type": "ACTION", "statement": "decision",
         "if_supported": "advance", "if_falsified": "revise or stop"},
    ]
    edges = [{"from": nodes[i]["node_id"], "to": nodes[i + 1]["node_id"]}
             for i in range(len(nodes) - 1)]
    spec = {
        "schema": SCHEMA_ID, "plan_state": "AUTHORIZED",
        "nodes": nodes, "edges": edges, "amendments": [],
        "risk_register": [{
            "risk_id": "R1", "likelihood": "medium", "severity": "high",
            "mitigation": "pilot", "owner": "PI", "trigger": "missingness > threshold",
        }],
        "authorization": {
            "actor": "user", "authorization_id": "user-msg:1", "scope": "target-chain-v1",
            "authorized_at": "2026-07-01",
        },
    }
    spec["authorization"]["plan_sha256"] = _content_sha256(spec)
    return spec


def _selftest() -> int:
    assert evaluate(_base())["status"] == "PASS"
    post = json.loads(json.dumps(_base()))
    post["nodes"][3]["timing"] = "POST_DATA"
    assert "POST_DATA_PRIMARY_ENDPOINT" in {x["code"] for x in evaluate(post)["issues"]}
    broken = json.loads(json.dumps(_base()))
    broken["edges"] = broken["edges"][:-1]
    assert "TARGET_CHAIN_BREAK" in {x["code"] for x in evaluate(broken)["issues"]}
    cycle = json.loads(json.dumps(_base()))
    cycle["edges"].append({"from": "D1", "to": "Q1"})
    assert "TARGET_CHAIN_CYCLE" in {x["code"] for x in evaluate(cycle)["issues"]}
    no_falsifier = json.loads(json.dumps(_base()))
    no_falsifier["nodes"][5].pop("threshold")
    assert "FALSIFIER_GAP" in {x["code"] for x in evaluate(no_falsifier)["issues"]}
    weak_endpoint = json.loads(json.dumps(_base()))
    weak_endpoint["nodes"][3].pop("measurement_instrument")
    weak_endpoint["nodes"][4].pop("independence_assumption")
    codes = {x["code"] for x in evaluate(weak_endpoint)["issues"]}
    assert {"PRIMARY_ENDPOINT_GAP", "INDEPENDENCE_ASSUMPTION_GAP"} <= codes
    unit_mismatch = json.loads(json.dumps(_base()))
    unit_mismatch["nodes"][1]["analysis_unit"] = "seed"
    assert "ESTIMAND_UNIT_MISMATCH" in {x["code"] for x in evaluate(unit_mismatch)["issues"]}
    unit_mismatch["nodes"][1]["unit_mismatch_rationale"] = "seed-level variance is descriptive only; primary inference remains participant-level"
    assert "ESTIMAND_UNIT_MISMATCH" not in {x["code"] for x in evaluate(unit_mismatch)["issues"]}
    amended = json.loads(json.dumps(_base()))
    amended["plan_state"] = "AMENDED"
    amended["amendments"] = [{
        "changed_node_id": "P1", "reason": "observed result", "authorization_id": "user-msg:2",
        "changed_at": "2026-07-04", "after_data": True, "relabelled_exploratory": False,
    }]
    assert "POST_DATA_CHANGE_NOT_RELABELLED" in {x["code"] for x in evaluate(amended)["issues"]}
    unlocked = json.loads(json.dumps(_base()))
    unlocked["authorization"].pop("plan_sha256")
    assert "PLAN_LOCK_GAP" in {x["code"] for x in evaluate(unlocked)["issues"]}
    stale_lock = json.loads(json.dumps(_base()))
    stale_lock["nodes"][0]["statement"] = "changed after authorization"
    assert "PLAN_LOCK_MISMATCH" in {x["code"] for x in evaluate(stale_lock)["issues"]}
    unfair = json.loads(json.dumps(_base()))
    unfair["comparative_study"] = True
    assert "BASELINE_FAIRNESS_GAP" in {x["code"] for x in evaluate(unfair)["issues"]}
    print("target_chain selftest PASS: full chain/post-data endpoint/falsifier/amendment/risk/auth")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    report = evaluate(json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
