#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对审稿人新增实验请求是否可运行、可承诺（不执行实验）。"""
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

SCHEMA_ID = "light.rebuttal.experiment_request.v1"
TIERS = {"A_REANALYSIS", "B_MINIMAL", "C_ADAPTED", "D_NEW_DATA"}
FEASIBILITY = {"READY_NOW", "MODERATE", "HIGH_RISK", "NOT_REALISTIC", "UNKNOWN"}
ACTIONS = {"RUN", "CLARIFY", "DEFER", "ACK_LIMIT", "ADAPT_BASELINE"}
RESULT_STATES = {"NOT_RUN", "PLANNED", "RUNNING", "DONE", "FAILED"}


def _real(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and "<" not in text and "replace-with" not in text


def _iso_date(value: Any) -> bool:
    try:
        dt.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", str(value or "")))


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    policy = spec.get("venue_policy")
    requests = spec.get("requests")
    if not isinstance(policy, dict) or not isinstance(requests, list):
        raise ValueError("venue_policy/requests 类型错误")
    issues: list[dict[str, str]] = []
    decisions: list[dict[str, Any]] = []

    def add(code: str, message: str, issue_id: str, severity: str = "error") -> None:
        issues.append({"severity": severity, "code": code, "issue_id": issue_id, "message": message})

    policy_state = policy.get("state")
    if policy_state not in {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE"}:
        raise ValueError("venue_policy.state 非法")
    policy_provenance_ok = (
        policy.get("source_type") == "OFFICIAL"
        and _real(policy.get("source"))
        and _iso_date(policy.get("checked_at"))
    )
    if policy_state == "VERIFIED" and not policy_provenance_ok:
        issues.append({
            "severity": "error", "code": "VERIFIED_POLICY_PROVENANCE_GAP",
            "issue_id": "*",
            "message": "VERIFIED venue policy 缺 OFFICIAL source_type、真实 source 或 ISO checked_at",
        })
    for row in requests:
        issue_id = str(row.get("issue_id") or "")
        if not issue_id:
            raise ValueError("request.issue_id 必填")
        tier, feasibility, action = row.get("tier"), row.get("feasibility"), row.get("action")
        if tier not in TIERS or feasibility not in FEASIBILITY or action not in ACTIONS:
            raise ValueError(f"{issue_id} tier/feasibility/action 非法")
        result_status = row.get("result_status", "NOT_RUN")
        if result_status not in RESULT_STATES:
            raise ValueError(f"{issue_id} result_status 非法")
        allowed = False
        if action == "RUN":
            if policy_state != "VERIFIED":
                add("VENUE_POLICY_UNVERIFIED", "新增结果规则未 VERIFIED，不能承诺运行", issue_id)
            elif not policy_provenance_ok:
                add("VENUE_POLICY_PROVENANCE_GAP", "规则虽标 VERIFIED，但缺真实 source/checked_at", issue_id)
            elif policy.get("allows_new_results") is not True:
                add("VENUE_DISALLOWS_NEW_RESULTS", "当前权威规则不允许新增结果", issue_id)
            if feasibility not in {"READY_NOW", "MODERATE"}:
                add("FEASIBILITY_TOO_WEAK", f"feasibility={feasibility}，不得承诺 RUN", issue_id)
            if tier == "D_NEW_DATA" and not row.get("explicit_tier_d_authorization"):
                add("TIER_D_AUTH_REQUIRED", "新数据/人评/大规模 sweep 需单独用户授权", issue_id)
            for field in ("protocol_path", "budget", "authorization_id"):
                if not _real(row.get(field)):
                    add("RUN_EVIDENCE_GAP", f"RUN 缺 {field}", issue_id)
            allowed = not any(x["issue_id"] == issue_id and x["severity"] == "error" for x in issues)
        completion_evidence_ok = (
            _real(row.get("run_manifest"))
            and _sha256(row.get("result_artifact_sha256"))
        )
        if result_status == "DONE":
            if not completion_evidence_ok:
                add("DONE_WITHOUT_RUN_PROVENANCE", "DONE 缺 run_manifest/result hash", issue_id)
        elif row.get("response_claims_completion"):
            add("PLANNED_AS_DONE", "未 DONE 却准备在回复中使用完成式", issue_id)
        decisions.append({
            "issue_id": issue_id, "action": action, "allowed_to_run": allowed,
            "may_claim_done": result_status == "DONE" and completion_evidence_ok,
        })
    status = "FAIL" if any(x["severity"] == "error" for x in issues) else "PASS"
    return {
        "schema": SCHEMA_ID, "status": status, "decisions": decisions, "issues": issues,
        "honesty": "allowed_to_run 只是授权/可行性前置条件；实验完成仍须 experiment-coding 的运行证据。",
    }


def _selftest() -> int:
    good = evaluate({
        "venue_policy": {
            "state": "VERIFIED", "allows_new_results": True,
            "source_type": "OFFICIAL",
            "source": "https://official.example/rules", "checked_at": "2026-07-04",
        },
        "requests": [{
            "issue_id": "R1-A", "tier": "A_REANALYSIS", "feasibility": "READY_NOW",
            "action": "RUN", "protocol_path": "protocol.json", "budget": "1h",
            "authorization_id": "user:1", "result_status": "PLANNED",
        }],
    })
    assert good["status"] == "PASS" and good["decisions"][0]["allowed_to_run"]
    bad = evaluate({
        "venue_policy": {"state": "UNKNOWN", "allows_new_results": None},
        "requests": [{
            "issue_id": "R2-D", "tier": "D_NEW_DATA", "feasibility": "HIGH_RISK",
            "action": "RUN", "result_status": "PLANNED", "response_claims_completion": True,
        }],
    })
    codes = {x["code"] for x in bad["issues"]}
    assert bad["status"] == "FAIL"
    assert {"VENUE_POLICY_UNVERIFIED", "FEASIBILITY_TOO_WEAK", "TIER_D_AUTH_REQUIRED", "PLANNED_AS_DONE"} <= codes
    done_bad = evaluate({
        "venue_policy": {
            "state": "VERIFIED", "allows_new_results": True,
            "source_type": "OFFICIAL",
            "source": "https://official.example/rules", "checked_at": "2026-07-04",
        },
        "requests": [{
            "issue_id": "R3", "tier": "B_MINIMAL", "feasibility": "READY_NOW",
            "action": "CLARIFY", "result_status": "DONE",
        }],
    })
    assert done_bad["status"] == "FAIL"
    provenance_bad = evaluate({
        "venue_policy": {
            "state": "VERIFIED", "allows_new_results": True,
            "source_type": "OFFICIAL",
            "source": "<official-rule-url>", "checked_at": "<date>",
        },
        "requests": [{
            "issue_id": "R4", "tier": "A_REANALYSIS", "feasibility": "READY_NOW",
            "action": "RUN", "protocol_path": "protocol.json", "budget": "1h",
            "authorization_id": "user:2", "result_status": "PLANNED",
        }],
    })
    assert provenance_bad["status"] == "FAIL"
    assert not provenance_bad["decisions"][0]["allowed_to_run"]
    assert "VENUE_POLICY_PROVENANCE_GAP" in {x["code"] for x in provenance_bad["issues"]}
    print("experiment_request_gate selftest PASS: 可运行/未知规则/Tier-D/假完成")
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
