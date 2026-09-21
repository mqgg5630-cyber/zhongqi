#!/usr/bin/env python3
"""Assess a response against a current, source-backed venue rule envelope.

No venue preset is embedded. If the selected venue context has no current
authoritative response limit, the result is UNKNOWN rather than a borrowed
limit from another venue.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata

LIMIT_FIELDS = (
    "rebuttal_length", "response_length", "revision_response_limit",
    "author_response_limit",
)


def read_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def is_cjk(character: str) -> bool:
    try:
        name = unicodedata.name(character)
    except ValueError:
        return False
    return "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name


def strip_markup(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"^#{1,6}\s*", "", text, flags=re.M)


def count(text: str) -> dict:
    body = strip_markup(text)
    cjk = sum(1 for character in body if is_cjk(character))
    latin_body = "".join(" " if is_cjk(character) else character for character in body)
    latin = len([token for token in re.split(r"\s+", latin_body) if token])
    return {"words": latin + cjk, "latin_words": latin, "cjk_characters": cjk,
            "characters": len(body)}


def rule_from_context(context: dict) -> tuple[str, dict | None, str | None]:
    if context.get("schema") != "light.review_rebuttal_venue_context.v1":
        raise ValueError("context must be light.review_rebuttal_venue_context.v1")
    rules = context.get("rules") or {}
    for field in LIMIT_FIELDS:
        envelope = rules.get(field)
        if isinstance(envelope, dict):
            status = str(envelope.get("status") or "UNKNOWN").upper()
            return status, envelope, field
    return "UNKNOWN", None, None


def assess(text: str, status: str, envelope: dict | None, field: str | None) -> dict:
    totals = count(text)
    result = {
        "schema": "light.rebuttal_budget.v2",
        "rule_field": field,
        "rule_status": status,
        "rule": envelope,
        "counts": totals,
    }
    if status != "AVAILABLE" or not envelope:
        result.update(
            verdict=status if status in {"UNKNOWN", "UNAVAILABLE", "STALE"} else "UNKNOWN",
            reason=(envelope or {}).get("reason") or
                   "no current authoritative response limit in selected venue context",
        )
        return result
    value = envelope.get("value")
    if not isinstance(value, dict):
        result.update(verdict="UNKNOWN", reason="AVAILABLE limit must be an object")
        return result
    checks = []
    for key, count_key in (
        ("max_words", "words"), ("max_characters", "characters"), ("max_pages", None)
    ):
        maximum = value.get(key)
        if maximum is None:
            continue
        if key == "max_pages":
            result.update(verdict="UNKNOWN",
                          reason="page limit requires rendered artifact inspection; text count cannot prove it")
            return result
        if not isinstance(maximum, (int, float)):
            result.update(verdict="UNKNOWN", reason=f"{key} is not numeric")
            return result
        checks.append((count_key, totals[count_key], maximum))
    if not checks:
        result.update(verdict="UNKNOWN", reason="rule has no supported word/character limit")
        return result
    over = [
        {"metric": metric, "actual": actual, "maximum": maximum}
        for metric, actual, maximum in checks if actual > maximum
    ]
    result["checks"] = [
        {"metric": metric, "actual": actual, "maximum": maximum}
        for metric, actual, maximum in checks
    ]
    result["verdict"] = "FAIL" if over else "PASS"
    result["over"] = over
    return result


def _selftest() -> int:
    context = {
        "schema": "light.review_rebuttal_venue_context.v1",
        "rules": {"rebuttal_length": {
            "status": "AVAILABLE", "value": {"max_characters": 10},
            "source_ids": ["official"], "checked_at": "2026-07-03",
        }},
    }
    status, envelope, field = rule_from_context(context)
    assert assess("short", status, envelope, field)["verdict"] == "PASS"
    assert assess("this is too long", status, envelope, field)["verdict"] == "FAIL"
    unknown = {
        "schema": "light.review_rebuttal_venue_context.v1",
        "rules": {"rebuttal_length": {
            "status": "UNKNOWN", "value": None,
            "reason": "no current authoritative rule found",
        }},
    }
    status, envelope, field = rule_from_context(unknown)
    assert assess("any text", status, envelope, field)["verdict"] == "UNKNOWN"
    print("[selftest] PASS rebuttal_budget: current rule pass/fail + UNKNOWN no borrowing")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="source-backed response budget")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--context")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.file or not args.context:
        parser.error("FILE and --context are required")
    try:
        text = pathlib.Path(args.file).read_text(encoding="utf-8")
        context = read_json(pathlib.Path(args.context))
        status, envelope, field = rule_from_context(context)
        result = assess(text, status, envelope, field)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[rebuttal_budget] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["verdict"] == "FAIL":
        return 1
    if result["verdict"] == "UNAVAILABLE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
