#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 light.decision.v1 转成总控可执行/停问判定；本脚本不执行被授权动作。"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))

from _shared.decision_contract import validate  # noqa: E402

SCHEMA_ID = "light.decision_checkpoint.v1"


def check(data: dict[str, Any]) -> dict[str, Any]:
    validate(data)
    status = data["status"]
    allowed = status == "AUTHORIZED"
    if allowed:
        checkpoint_status = "PASS"
        ask = None
        reason = (
            f"已获 {data['authority_required']} 授权；"
            f"仅允许 scope={data['scope']}，授权={data['authorization']['id']}"
        )
    elif status == "PROPOSED":
        checkpoint_status = "UNRESOLVED"
        ask = data["question"]
        reason = "关键取舍尚未拍板，必须停下询问"
    else:
        checkpoint_status = "FAIL"
        ask = None
        reason = f"决策状态为 {status}，不得执行"
    return {
        "schema": SCHEMA_ID,
        "status": checkpoint_status,
        "allowed": allowed,
        "decision_id": data["decision_id"],
        "selected": data.get("selected"),
        "scope": list(data["scope"]),
        "authorization_id": (
            data["authorization"]["id"] if data.get("authorization") else None
        ),
        "ask": ask,
        "reason": reason,
        "does_not_execute": True,
    }


def _fixture(status: str = "PROPOSED") -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": "light.decision.v1",
        "decision_id": "D-remote",
        "question": "是否启动远程付费实验？",
        "status": status,
        "risk": "high",
        "reversible": False,
        "authority_required": "user",
        "scope": ["remote-job:exp-7"],
        "options": [
            {"id": "run", "label": "启动", "evidence": ["预算卡"], "risks": ["费用"]},
            {"id": "hold", "label": "暂缓", "evidence": [], "risks": ["延期"]},
        ],
        "recommendation": "hold",
        "selected": None,
        "authorization": None,
    }
    if status == "AUTHORIZED":
        data["selected"] = "run"
        data["authorization"] = {
            "id": "AUTH-remote-7",
            "actor": "user",
            "at": "2026-07-04T12:00:00+08:00",
        }
    return data


def _selftest() -> int:
    proposed = check(_fixture())
    assert proposed["status"] == "UNRESOLVED"
    assert proposed["ask"] == "是否启动远程付费实验？"
    authorized = check(_fixture("AUTHORIZED"))
    assert authorized["allowed"] is True
    assert authorized["authorization_id"] == "AUTH-remote-7"
    for terminal in ("REJECTED", "REVOKED", "EXPIRED"):
        denied = check(_fixture(terminal))
        assert denied["status"] == "FAIL" and denied["allowed"] is False
    print("decision_checkpoint selftest PASS: ask/authorize/reject/revoke/expire")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--input")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.input:
        with open(args.input, encoding="utf-8-sig") as handle:
            result = check(json.load(handle))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["allowed"] else 2
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())
