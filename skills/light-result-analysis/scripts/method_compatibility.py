#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在运行分析/解释方法前核对其声明能力与研究数据条件。

该门不判断方法“好不好”，只阻止已知不兼容，并把缺失条件保留为 UNRESOLVED。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.analysis.compatibility.v1"
ACCESS_LEVELS = {"predictions", "probabilities", "gradients", "internal_states", "training_data"}
DEPENDENCE = {
    "independent", "paired", "clustered", "hierarchical", "time_series",
    "spatial", "repeated_measures", "unknown", "*",
}


def _strings(value: Any, name: str, allow_empty: bool = False) -> set[str]:
    if value is None and allow_empty:
        return set()
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{name} 必须是{'可空' if allow_empty else '非空'}字符串列表")
    out = {str(x).strip() for x in value if str(x).strip()}
    if len(out) != len(value):
        raise ValueError(f"{name} 含空值或重复值")
    return out


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    method = spec.get("method")
    case = spec.get("case")
    if not isinstance(method, dict) or not isinstance(case, dict):
        raise ValueError("method/case 必须是 object")
    method_id = str(method.get("id") or "").strip()
    if not method_id:
        raise ValueError("method.id 必填")

    scopes = _strings(method.get("domain_scope"), "method.domain_scope")
    modalities = _strings(method.get("input_modalities"), "method.input_modalities")
    tasks = _strings(method.get("task_types"), "method.task_types")
    required_access = _strings(method.get("requires_access", []), "method.requires_access", True)
    unknown_access = sorted(required_access - ACCESS_LEVELS)
    if unknown_access:
        raise ValueError(f"未知 access capability: {unknown_access}")
    supported_dependence = _strings(
        method.get("supported_dependence"), "method.supported_dependence"
    )
    if supported_dependence - DEPENDENCE:
        raise ValueError("method.supported_dependence 含未知结构")

    labels = method.get("labels")
    if labels not in {"required", "optional"}:
        raise ValueError("method.labels 必须为 required/optional")
    if case.get("has_labels") is not None and not isinstance(case.get("has_labels"), bool):
        raise ValueError("case.has_labels 必须为 bool/null")

    missing_case = [
        name for name in ("domain", "input_modality", "task_type", "dependence")
        if not str(case.get(name) or "").strip()
    ]
    issues: list[dict[str, str]] = []
    if missing_case:
        issues.append({
            "code": "CASE_CONDITION_UNKNOWN",
            "message": f"研究条件缺失：{missing_case}",
            "fix": "先从数据与研究设计确认条件，不得猜测后放行",
        })
    dependence = str(case.get("dependence") or "unknown")
    if dependence not in DEPENDENCE:
        raise ValueError(f"未知 case.dependence={dependence!r}")

    available_access = _strings(
        case.get("available_access", []), "case.available_access", True
    )
    if available_access - ACCESS_LEVELS:
        raise ValueError("case.available_access 含未知能力")

    known_incompatibilities: list[tuple[bool, str, str]] = [
        (
            bool(case.get("domain")) and "*" not in scopes and str(case["domain"]) not in scopes,
            "DOMAIN_SCOPE_MISMATCH",
            f"domain={case.get('domain')} 不在 method.domain_scope={sorted(scopes)}",
        ),
        (
            bool(case.get("input_modality"))
            and "*" not in modalities
            and str(case["input_modality"]) not in modalities,
            "MODALITY_MISMATCH",
            f"input_modality={case.get('input_modality')} 不受支持",
        ),
        (
            bool(case.get("task_type"))
            and "*" not in tasks
            and str(case["task_type"]) not in tasks,
            "TASK_MISMATCH",
            f"task_type={case.get('task_type')} 不受支持",
        ),
        (
            dependence != "unknown"
            and "*" not in supported_dependence
            and dependence not in supported_dependence,
            "DEPENDENCE_MISMATCH",
            f"dependence={dependence} 不受支持",
        ),
        (
            not required_access.issubset(available_access),
            "ACCESS_MISSING",
            f"缺少访问能力：{sorted(required_access - available_access)}",
        ),
        (
            method.get("labels") == "required" and case.get("has_labels") is False,
            "LABELS_MISSING",
            "方法要求标签，但研究数据明确无标签",
        ),
    ]
    for hit, code, message in known_incompatibilities:
        if hit:
            issues.append({
                "code": code,
                "message": message,
                "fix": "换兼容方法，或取得真实所需输入；不得用代理值冒充",
            })

    hard = [x for x in issues if x["code"] != "CASE_CONDITION_UNKNOWN"]
    if hard:
        status = "FAIL"
    elif issues or dependence == "unknown" or case.get("has_labels") is None:
        status = "UNRESOLVED"
    else:
        status = "PASS"
    return {
        "schema": SCHEMA_ID,
        "status": status,
        "method_id": method_id,
        "compatible": True if status == "PASS" else (False if status == "FAIL" else None),
        "issues": issues,
        "checked": {
            "domain_scope": sorted(scopes),
            "input_modalities": sorted(modalities),
            "task_types": sorted(tasks),
            "requires_access": sorted(required_access),
            "supported_dependence": sorted(supported_dependence),
        },
        "honesty": (
            "PASS 只表示声明条件兼容，不证明统计识别、实现正确、结果可信或因果有效；"
            "这些仍须由分析计划、统计门、负对照和敏感性分析验证。"
        ),
    }


def _method() -> dict[str, Any]:
    return {
        "id": "selftest-explainer",
        "domain_scope": ["*"],
        "input_modalities": ["tabular"],
        "task_types": ["classification"],
        "requires_access": ["predictions", "probabilities"],
        "supported_dependence": ["independent", "paired"],
        "labels": "optional",
    }


def _selftest() -> int:
    good = evaluate({
        "method": _method(),
        "case": {
            "domain": "ecology", "input_modality": "tabular",
            "task_type": "classification", "dependence": "paired",
            "available_access": ["predictions", "probabilities"], "has_labels": True,
        },
    })
    assert good["status"] == "PASS", good

    incompatible = evaluate({
        "method": _method(),
        "case": {
            "domain": "ecology", "input_modality": "image",
            "task_type": "classification", "dependence": "clustered",
            "available_access": ["predictions"], "has_labels": True,
        },
    })
    assert incompatible["status"] == "FAIL", incompatible
    codes = {x["code"] for x in incompatible["issues"]}
    assert {"MODALITY_MISMATCH", "DEPENDENCE_MISMATCH", "ACCESS_MISSING"} <= codes

    unresolved = evaluate({
        "method": _method(),
        "case": {
            "domain": "ecology", "input_modality": "tabular",
            "task_type": "classification", "dependence": "unknown",
            "available_access": ["predictions", "probabilities"],
        },
    })
    assert unresolved["status"] == "UNRESOLVED", unresolved
    print("method_compatibility selftest PASS: 兼容/不兼容/条件未知")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", help="compatibility JSON")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = evaluate(spec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
