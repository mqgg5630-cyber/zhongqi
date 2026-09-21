#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比较已抽取的跨材料事实绑定，覆盖术语/指标以外的通用事实。"""
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

SCHEMA_ID = "light.consistency.facts.v1"


def _normalize(value: Any, mode: str) -> Any:
    if mode == "exact":
        return str(value)
    if mode == "casefold":
        return re.sub(r"\s+", " ", str(value)).strip().casefold()
    if mode == "numeric":
        return float(value)
    if mode == "date":
        return dt.date.fromisoformat(str(value)).isoformat()
    raise ValueError(f"未知 normalization={mode}")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    facts = spec.get("facts")
    observations = spec.get("observations")
    if not isinstance(facts, list) or not isinstance(observations, list):
        raise ValueError("facts/observations 必须是 list")
    canonical: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []

    def add(code: str, message: str, fact_id: str, locator: str, severity: str) -> None:
        issues.append({
            "severity": severity, "code": code, "fact_id": fact_id,
            "locator": locator, "message": message,
        })

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "")
        if not fact_id or fact_id in canonical:
            raise ValueError("fact_id 缺失或重复")
        if fact.get("status") != "CONFIRMED" or not fact.get("source") or not fact.get("locator"):
            add("CANONICAL_UNCONFIRMED", "权威事实缺 CONFIRMED/source/locator", fact_id, "registry", "warn")
        canonical[fact_id] = fact
    seen: dict[tuple[str, str], set[Any]] = {}
    for obs in observations:
        fact_id = str(obs.get("fact_id") or "")
        locator = f"{obs.get('artifact', '?')}:{obs.get('locator', '?')}"
        if fact_id not in canonical:
            add("FACT_UNREGISTERED", "观察事实未登记权威值", fact_id or "?", locator, "warn")
            continue
        if obs.get("status") != "CONFIRMED":
            add("OBSERVATION_UNCONFIRMED", "抽取仍是候选，不能用于 PASS", fact_id, locator, "warn")
            continue
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(obs.get("artifact_sha256") or "")):
            add("ARTIFACT_HASH_MISSING", "观察缺真实格式 sha256:<64 hex>", fact_id, locator, "warn")
        fact = canonical[fact_id]
        mode = fact.get("normalization", "exact")
        try:
            expected = _normalize(fact.get("value"), mode)
            actual = _normalize(obs.get("value"), mode)
        except (ValueError, TypeError) as exc:
            add("NORMALIZATION_ERROR", str(exc), fact_id, locator, "error")
            continue
        tolerance = float(fact.get("tolerance", 0)) if mode == "numeric" else 0
        match = abs(actual - expected) <= tolerance if mode == "numeric" else actual == expected
        if not match:
            add("FACT_VALUE_MISMATCH", f"实得 {obs.get('value')!r}，权威 {fact.get('value')!r}",
                fact_id, locator, "error")
        seen.setdefault((fact_id, str(obs.get("artifact"))), set()).add(actual)
    for (fact_id, artifact), values in seen.items():
        if len(values) > 1:
            add("INTRA_ARTIFACT_CONFLICT", f"同一材料出现多个值 {sorted(map(str, values))}",
                fact_id, artifact, "error")
    for fact_id, fact in canonical.items():
        expected = set(map(str, fact.get("expected_artifacts") or []))
        observed = {
            str(x.get("artifact")) for x in observations
            if x.get("fact_id") == fact_id and x.get("status") == "CONFIRMED"
        }
        for missing in sorted(expected - observed):
            add("FACT_COVERAGE_GAP", f"预期材料 {missing} 无 confirmed observation",
                fact_id, missing, "warn")
    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "PARTIAL" if issues else "PASS"
    )
    return {
        "schema": SCHEMA_ID, "status": status, "issues": issues,
        "honesty": "本门核已抽取事实绑定；它不自动理解任意材料，候选抽取不能冒充 confirmed。",
    }


def _selftest() -> int:
    base = {
        "facts": [{
            "fact_id": "dataset.version", "value": "V2", "normalization": "casefold",
            "status": "CONFIRMED", "source": "dataset card", "locator": "L2",
            "expected_artifacts": ["paper", "slides"],
        }],
        "observations": [
            {"fact_id": "dataset.version", "value": "v2", "artifact": "paper",
             "locator": "L10", "status": "CONFIRMED", "artifact_sha256": "sha256:" + "a" * 64},
            {"fact_id": "dataset.version", "value": "V2", "artifact": "slides",
             "locator": "S3", "status": "CONFIRMED", "artifact_sha256": "sha256:" + "b" * 64},
        ],
    }
    assert evaluate(base)["status"] == "PASS"
    bad = json.loads(json.dumps(base))
    bad["observations"][1]["value"] = "V1"
    assert evaluate(bad)["status"] == "FAIL"
    partial = json.loads(json.dumps(base))
    partial["observations"][1]["status"] = "CANDIDATE"
    assert evaluate(partial)["status"] == "PARTIAL"
    numeric = {
        "facts": [{"fact_id": "n", "value": 100, "normalization": "numeric",
                   "tolerance": .1, "status": "CONFIRMED", "source": "run", "locator": "x"}],
        "observations": [{"fact_id": "n", "value": 100.05, "artifact": "paper",
                          "locator": "L1", "status": "CONFIRMED",
                          "artifact_sha256": "sha256:" + "c" * 64}],
    }
    assert evaluate(numeric)["status"] == "PASS"
    print("fact_consistency selftest PASS: 一致/冲突/候选覆盖/numeric tolerance")
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
