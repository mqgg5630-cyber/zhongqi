#!/usr/bin/env python3
"""Discover candidate publication venues from current Crossref works metadata.

This is a recall-oriented discovery helper, not a ranking engine. It preserves
the exact query, endpoint, access tier, check time, and example works. Network,
rate-limit, and service failures are UNAVAILABLE; they never become venue risk.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from typing import Callable

SCHEMA = "light.venue_discovery.v1"
BASE = "https://api.crossref.org/works"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _fetch(url: str, mailto: str = "", timeout: int = 30) -> dict:
    agent = "Light-venue-matching/2.0"
    if mailto:
        agent += f" (mailto:{mailto})"
    req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _year(item: dict):
    parts = ((item.get("published") or {}).get("date-parts") or [[]])[0]
    return parts[0] if parts else None


def discover(query: str, rows: int = 50, mailto: str = "",
             fetch: Callable[[str, str], dict] = _fetch) -> dict:
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    params = {
        "query.bibliographic": query,
        "rows": max(1, min(int(rows), 100)),
        "select": "DOI,title,container-title,ISSN,type,published,URL",
    }
    if mailto:
        params["mailto"] = mailto
    url = BASE + "?" + urllib.parse.urlencode(params)
    checked_at = now()
    source = {
        "source_id": "crossref-discovery",
        "kind": "api",
        "provider": "Crossref",
        "url": url,
        "query": query,
        "checked_at": checked_at,
        "access_tier": "free_public",
        "authority": "registration_metadata",
        "status": "AVAILABLE",
        "reason": None,
    }
    try:
        payload = fetch(url, mailto)
    except urllib.error.HTTPError as exc:
        source.update(status="UNAVAILABLE", http_status=exc.code,
                      reason=f"HTTP {exc.code}; rate/auth/service failure is not venue risk")
        return {
            "schema": SCHEMA, "generated_at": checked_at, "status": "UNAVAILABLE",
            "source": source, "candidates": [],
        }
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        source.update(status="UNAVAILABLE", reason=f"{type(exc).__name__}: {exc}")
        return {
            "schema": SCHEMA, "generated_at": checked_at, "status": "UNAVAILABLE",
            "source": source, "candidates": [],
        }

    items = ((payload.get("message") or {}).get("items") or [])
    counts: Counter = Counter()
    examples: dict = defaultdict(list)
    names: dict = {}
    issns: dict = defaultdict(set)
    for item in items:
        titles = item.get("container-title") or []
        name = str(titles[0]).strip() if titles else ""
        if not name:
            continue
        key = name.casefold()
        counts[key] += 1
        names[key] = name
        issns[key].update(str(value) for value in (item.get("ISSN") or []) if value)
        if len(examples[key]) < 3:
            examples[key].append({
                "doi": item.get("DOI"),
                "title": ((item.get("title") or [None])[0]),
                "year": _year(item),
                "url": item.get("URL"),
            })
    candidates = []
    for index, (key, count) in enumerate(
            sorted(counts.items(), key=lambda pair: (-pair[1], names[pair[0]].casefold())), 1):
        candidates.append({
            "candidate_id": f"crossref-{index:03d}",
            "name": names[key],
            "identifiers": {"issn": sorted(issns[key])},
            "discovery_count": count,
            "example_works": examples[key],
            "source_ids": [source["source_id"]],
        })
    return {
        "schema": SCHEMA,
        "generated_at": checked_at,
        "status": "AVAILABLE",
        "query": query,
        "returned_works": len(items),
        "source": source,
        "candidates": candidates,
        "boundary": (
            "Crossref container frequency is candidate discovery evidence only; "
            "it is not scope fit, quality, indexing, acceptance likelihood, or safety."
        ),
    }


def _selftest() -> int:
    def fake(url: str, mailto: str) -> dict:
        assert "query.bibliographic=reproducible+machine+learning" in url
        return {"message": {"items": [
            {"DOI": "10.1/a", "title": ["A"], "container-title": ["Journal A"],
             "ISSN": ["1234-5678"], "published": {"date-parts": [[2025]]}},
            {"DOI": "10.1/b", "title": ["B"], "container-title": ["Journal A"],
             "ISSN": ["1234-5678"], "published": {"date-parts": [[2024]]}},
            {"DOI": "10.1/c", "title": ["C"], "container-title": ["Journal B"],
             "ISSN": ["9999-0000"], "published": {"date-parts": [[2026]]}},
        ]}}

    report = discover("reproducible machine learning", fetch=fake)
    assert report["status"] == "AVAILABLE"
    assert report["candidates"][0]["name"] == "Journal A"
    assert report["candidates"][0]["discovery_count"] == 2
    assert report["source"]["query"] == "reproducible machine learning"

    def limited(url: str, mailto: str) -> dict:
        raise urllib.error.HTTPError(url, 429, "limited", {}, None)

    unavailable = discover("x", fetch=limited)
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["source"]["http_status"] == 429
    assert not unavailable["candidates"]
    assert "not venue risk" in unavailable["source"]["reason"]
    print("[selftest] PASS venue_discovery: provenance + aggregation + honest 429")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate venues from Crossref works")
    parser.add_argument("--query")
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--mailto", default="")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.query:
        parser.error("--query is required")
    try:
        report = discover(args.query, args.rows, args.mailto)
    except ValueError as exc:
        parser.error(str(exc))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
    return 0 if report["status"] == "AVAILABLE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
