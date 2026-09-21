#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preflight venue-search queries without echoing unpublished manuscript text.

The checker catches only supplied/private phrase overlap and result-shaped
values. PASS is not a guarantee that a query is anonymous or non-identifying.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.venue_query_privacy.v1"
DESTINATIONS = {"LOCAL", "PUBLIC_WEB", "EXTERNAL_AUTHENTICATED"}
PRIVATE_STATES = {"COMPLETE", "PARTIAL", "UNAVAILABLE"}


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _latin_ngrams(text: str, width: int = 6) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_-]*", text.casefold())
    return {" ".join(words[i:i + width]) for i in range(len(words) - width + 1)}


def _han_ngrams(text: str, width: int = 12) -> set[str]:
    chars = "".join(re.findall(r"[\u3400-\u9fff]", text))
    return {chars[i:i + width] for i in range(len(chars) - width + 1)}


def _private_signatures(material: dict[str, Any]) -> list[tuple[str, str]]:
    signatures: list[tuple[str, str]] = []
    for category in ("title", "abstract"):
        text = _norm(material.get(category))
        if category == "title" and len(text) >= 16:
            signatures.append((category, text))
        if category == "abstract":
            signatures.extend((category, item) for item in _latin_ngrams(text))
            signatures.extend((category, item) for item in _han_ngrams(text))
    for category in ("unique_terms", "result_phrases", "private_phrases"):
        values = material.get(category) or []
        if not isinstance(values, list):
            raise ValueError(f"private_material.{category} 必须是 list")
        for value in values:
            normalized = _norm(value)
            if len(normalized) >= 4:
                signatures.append((category, normalized))
    return signatures


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    material = spec.get("private_material")
    queries = spec.get("queries")
    if not isinstance(material, dict) or not isinstance(queries, list):
        raise ValueError("private_material/queries 类型错误")
    coverage = material.get("coverage")
    if coverage not in PRIVATE_STATES:
        raise ValueError("private_material.coverage 非法")
    approved_terms = {
        _norm(item) for item in spec.get("approved_generic_terms") or [] if _norm(item)
    }
    signatures = _private_signatures(material)
    issues: list[dict[str, str]] = []
    decisions: list[dict[str, Any]] = []

    def add(code: str, query_id: str, severity: str, message: str) -> None:
        issues.append({
            "code": code, "query_id": query_id, "severity": severity,
            "message": message,
        })

    if coverage != "COMPLETE":
        add(
            "PRIVATE_COVERAGE_INCOMPLETE", "*", "unresolved",
            "未完整登记标题、摘要、独有术语和结果短语；不能宣称已排除泄漏",
        )
    material_ready = coverage == "COMPLETE"
    if coverage == "COMPLETE":
        missing_material = [
            field for field in ("title", "abstract", "unique_terms", "result_phrases")
            if field not in material
            or (
                field in {"title", "abstract"}
                and not _norm(material.get(field))
            )
            or (
                field in {"unique_terms", "result_phrases"}
                and not isinstance(material.get(field), list)
            )
        ]
        if missing_material:
            material_ready = False
            add(
                "PRIVATE_MATERIAL_GAP", "*", "unresolved",
                f"coverage=COMPLETE 但缺必要材料类别 {missing_material}",
            )

    seen_ids: set[str] = set()
    for row in queries:
        if not isinstance(row, dict):
            raise ValueError("query 必须是 object")
        query_id = str(row.get("query_id") or "")
        destination = row.get("destination")
        text = _norm(row.get("text"))
        if not query_id or query_id in seen_ids:
            raise ValueError("query_id 缺失或重复")
        if destination not in DESTINATIONS or not text:
            raise ValueError(f"{query_id} destination/text 非法")
        seen_ids.add(query_id)
        external = destination != "LOCAL"
        if external:
            matched_categories = sorted({
                category for category, signature in signatures
                if signature and signature in text
            })
            for category in matched_categories:
                add(
                    "PRIVATE_TEXT_OVERLAP", query_id, "error",
                    f"外部查询命中未公开材料签名类别 {category}；报告故意不回显原文",
                )
            if re.search(
                r"(?:\b(?:p|q)\s*[<=>]\s*0?\.\d+)|"
                r"(?:\b\d+(?:\.\d+)?\s*%)|(?:\b\d+(?:\.\d+)?\s*±\s*\d)",
                text,
                flags=re.I,
            ):
                add(
                    "RESULT_SHAPED_VALUE", query_id, "error",
                    "外部查询含 p/q 值、百分比或均值±误差形态；改用无结果值的宽泛主题词",
                )
            purpose = str(row.get("purpose") or "")
            generic_hit = any(term in text for term in approved_terms)
            if purpose == "candidate_discovery" and not generic_hit:
                add(
                    "GENERIC_TERM_UNBOUND", query_id, "unresolved",
                    "候选发现查询未命中作者批准的宽泛领域/方法族术语",
                )
        query_errors = [
            item for item in issues
            if item["query_id"] == query_id and item["severity"] == "error"
        ]
        query_unresolved = [
            item for item in issues
            if item["query_id"] == query_id and item["severity"] == "unresolved"
        ]
        decisions.append({
            "query_id": query_id,
            "destination": destination,
            "query_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "allowed": not query_errors and not query_unresolved and material_ready,
        })

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": SCHEMA_ID,
        "status": status,
        "decisions": decisions,
        "issues": issues,
        "report_redaction": "输出仅保留 query id/hash 与命中类别，不回显私稿或查询文本。",
        "honesty": (
            "本门只检测已登记私密片段的重合和结果值形态；PASS 不证明查询不可重识别，"
            "也不替代作者对敏感/保密研究的判断。"
        ),
    }


def _selftest() -> int:
    base = {
        "private_material": {
            "coverage": "COMPLETE",
            "title": "A private title about adaptive control",
            "abstract": (
                "We introduce a distinctive adaptive controller for constrained systems. "
                "The private evaluation compares several carefully selected baselines."
            ),
            "unique_terms": ["PrivateControl-X"],
            "result_phrases": ["improves success by 17.3%"],
        },
        "approved_generic_terms": ["adaptive control", "robotics"],
        "queries": [{
            "query_id": "q-safe", "destination": "PUBLIC_WEB",
            "purpose": "candidate_discovery",
            "text": "adaptive control robotics journals aims and scope",
        }],
    }
    good = evaluate(base)
    assert good["status"] == "PASS" and good["decisions"][0]["allowed"]
    bad = json.loads(json.dumps(base))
    bad["queries"][0]["text"] = "PrivateControl-X improves success by 17.3% journal"
    report = evaluate(bad)
    codes = {x["code"] for x in report["issues"]}
    assert report["status"] == "FAIL"
    assert {"PRIVATE_TEXT_OVERLAP", "RESULT_SHAPED_VALUE"} <= codes
    assert not report["decisions"][0]["allowed"]
    assert "PrivateControl-X" not in json.dumps(report)
    partial = json.loads(json.dumps(base))
    partial["private_material"]["coverage"] = "PARTIAL"
    assert evaluate(partial)["status"] == "UNRESOLVED"
    false_complete = json.loads(json.dumps(base))
    false_complete["private_material"].pop("abstract")
    false_complete_report = evaluate(false_complete)
    assert false_complete_report["status"] == "UNRESOLVED"
    assert not false_complete_report["decisions"][0]["allowed"]
    local = json.loads(json.dumps(partial))
    local["private_material"]["coverage"] = "COMPLETE"
    local["queries"][0] = {
        "query_id": "q-local", "destination": "LOCAL",
        "purpose": "local_analysis", "text": "PrivateControl-X improves success by 17.3%",
    }
    assert evaluate(local)["status"] == "PASS"
    print("query_privacy_gate selftest PASS: 宽泛查询/私稿重合/结果值/不回显/本地例外")
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
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = evaluate(spec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
