#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用人工金标准量化文件抽取质量（light.file_reading.benchmark.v1）。

输入不是某个解析库的私有对象，而是最小元素 JSON：
{"id", "type", "text", "page_number", "coordinates", "provenance",
 "table_cells"}。本脚本只证明给定 fixture 上的抽取质量，不证明任意文件都正确。
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.file_reading.benchmark.v1"
CHANNELS = ("text", "element_types", "tables", "metadata")


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def _safe_ratio(num: float, den: float) -> float:
    return 1.0 if den == 0 and num == 0 else (num / den if den else 0.0)


def _text_metric(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any]:
    def by_page(items: list[dict[str, Any]]) -> dict[str, str]:
        out: dict[str, list[str]] = collections.defaultdict(list)
        for item in items:
            if item.get("text") not in (None, ""):
                out[str(item.get("page_number", "unknown"))].append(_norm(item["text"]))
        return {key: "\n".join(values) for key, values in out.items()}

    gp, pp = by_page(gold), by_page(pred)
    pages = sorted(gp)
    total_chars = sum(max(len(gp[p]), 1) for p in pages)
    errors = sum(_levenshtein(gp[p], pp.get(p, "")) for p in pages)
    accuracy = max(0.0, 1.0 - _safe_ratio(errors, total_chars))
    return {
        "metric": "normalized_character_accuracy",
        "value": round(accuracy, 6),
        "gold_pages": pages,
        "missing_pages": sorted(set(gp) - set(pp)),
        "extra_pages": sorted(set(pp) - set(gp)),
    }


def _type_metric(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any]:
    gc = collections.Counter(str(x.get("type", "UNKNOWN")) for x in gold)
    pc = collections.Counter(str(x.get("type", "UNKNOWN")) for x in pred)
    tp = sum(min(gc[k], pc[k]) for k in set(gc) | set(pc))
    precision = _safe_ratio(tp, sum(pc.values()))
    recall = _safe_ratio(tp, sum(gc.values()))
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    return {
        "metric": "element_type_micro_f1",
        "value": round(f1, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "gold_counts": dict(sorted(gc.items())),
        "predicted_counts": dict(sorted(pc.items())),
    }


def _table_metric(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any] | None:
    gt = [x for x in gold if x.get("table_cells") is not None]
    pt = [x for x in pred if x.get("table_cells") is not None]
    if not gt:
        return None
    if any(not x.get("id") or not isinstance(x.get("table_cells"), dict) for x in gt + pt):
        raise ValueError("表格评测要求每个表有稳定 id，table_cells 为 object")

    def triples(items: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
        return {
            (str(item["id"]), str(cell), _norm(value))
            for item in items
            for cell, value in item["table_cells"].items()
        }

    gs, ps = triples(gt), triples(pt)
    tp = len(gs & ps)
    precision = _safe_ratio(tp, len(ps))
    recall = _safe_ratio(tp, len(gs))
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    return {
        "metric": "table_cell_micro_f1",
        "value": round(f1, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "gold_tables": len(gt),
        "predicted_tables": len(pt),
    }


def _metadata_metric(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, Any] | None:
    if not fields:
        return None
    gm = {str(x["id"]): x for x in gold if x.get("id")}
    pm = {str(x["id"]): x for x in pred if x.get("id")}
    checks = 0
    matches = 0
    missing_ids: set[str] = set()
    for item_id, item in gm.items():
        for field in fields:
            if item.get(field) is None:
                continue
            checks += 1
            if item_id not in pm:
                missing_ids.add(item_id)
            elif pm[item_id].get(field) == item.get(field):
                matches += 1
    if checks == 0:
        return None
    return {
        "metric": "metadata_exact_match",
        "value": round(_safe_ratio(matches, checks), 6),
        "fields": fields,
        "checks": checks,
        "matches": matches,
        "missing_element_ids": sorted(missing_ids),
    }


def benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    gold = payload.get("gold")
    pred = payload.get("predicted")
    thresholds = payload.get("thresholds")
    if not isinstance(gold, list) or not isinstance(pred, list):
        raise ValueError("gold/predicted 必须是元素 object 列表")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds 必须显式给出；本脚本不替研究者发明合格线")
    unknown = sorted(set(thresholds) - set(CHANNELS))
    if unknown:
        raise ValueError(f"未知 threshold channel: {unknown}")
    for name, value in thresholds.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise ValueError(f"thresholds.{name} 必须在 [0,1]")

    metrics: dict[str, dict[str, Any] | None] = {
        "text": _text_metric(gold, pred),
        "element_types": _type_metric(gold, pred),
        "tables": _table_metric(gold, pred),
        "metadata": _metadata_metric(
            gold, pred, [str(x) for x in payload.get(
                "metadata_fields", ["page_number", "coordinates", "provenance"]
            )],
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    for channel, metric in metrics.items():
        if metric is None:
            results[channel] = {
                "status": "SKIPPED",
                "reason": "金标准没有该通道的可评测标注",
            }
        elif channel not in thresholds:
            results[channel] = {
                **metric,
                "status": "UNRESOLVED",
                "reason": "未声明该通道的验收阈值",
            }
        else:
            passed = metric["value"] >= thresholds[channel]
            results[channel] = {
                **metric,
                "threshold": thresholds[channel],
                "status": "PASS" if passed else "FAIL",
            }

    evaluated = [x["status"] for x in results.values() if x["status"] != "SKIPPED"]
    if any(x == "FAIL" for x in evaluated):
        overall = "FAIL"
    elif any(x == "UNRESOLVED" for x in evaluated) or not evaluated:
        overall = "PARTIAL"
    else:
        overall = "PASS"
    return {
        "schema": SCHEMA_ID,
        "status": overall,
        "fixture_id": str(payload.get("fixture_id") or "UNKNOWN"),
        "parser": payload.get("parser") or {"name": "UNKNOWN", "version": "UNKNOWN"},
        "gold_sha256": _canonical_hash(gold),
        "predicted_sha256": _canonical_hash(pred),
        "channels": results,
        "honesty": (
            "PASS 仅证明该 parser/version 在这份固定金标准 fixture 与显式阈值上达标；"
            "不外推到未评测格式、语言、版式或科学理解。"
        ),
    }


def _selftest() -> int:
    gold = [
        {"id": "p1", "type": "Title", "text": "Study A", "page_number": 1,
         "coordinates": [0, 0, 10, 2], "provenance": {"parser": "human"}},
        {"id": "t1", "type": "Table", "text": "A 1", "page_number": 1,
         "coordinates": [0, 3, 10, 8], "provenance": {"parser": "human"},
         "table_cells": {"r1c1": "A", "r1c2": "1"}},
    ]
    good = benchmark({
        "fixture_id": "selftest-good",
        "parser": {"name": "fixture", "version": "1"},
        "gold": gold,
        "predicted": json.loads(json.dumps(gold)),
        "thresholds": {"text": 1, "element_types": 1, "tables": 1, "metadata": 1},
    })
    assert good["status"] == "PASS", good
    assert good["gold_sha256"] == good["predicted_sha256"]

    bad_pred = [
        {"id": "p1", "type": "NarrativeText", "text": "wrong", "page_number": 1,
         "coordinates": None, "provenance": {"parser": "machine"}},
    ]
    bad = benchmark({
        "fixture_id": "selftest-bad",
        "gold": gold,
        "predicted": bad_pred,
        "thresholds": {"text": .9, "element_types": .9, "tables": .9, "metadata": .9},
    })
    assert bad["status"] == "FAIL", bad
    assert bad["channels"]["tables"]["recall"] == 0

    unresolved = benchmark({
        "fixture_id": "selftest-no-threshold",
        "gold": gold,
        "predicted": gold,
        "thresholds": {"text": 1},
    })
    assert unresolved["status"] == "PARTIAL", unresolved
    assert unresolved["channels"]["metadata"]["status"] == "UNRESOLVED"

    try:
        benchmark({"gold": gold, "predicted": gold, "thresholds": {"text": 1.2}})
        raise AssertionError("非法阈值应失败")
    except ValueError:
        pass
    print("extraction_benchmark selftest PASS: 达标/失败/未定阈值/坏阈值")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", help="benchmark JSON")
    parser.add_argument("--output", help="可选输出 JSON")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = benchmark(payload)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
