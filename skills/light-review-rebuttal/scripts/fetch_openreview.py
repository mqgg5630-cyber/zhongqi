#!/usr/bin/env python3
"""Capture public OpenReview reviews/decisions without rewriting source text.

AVAILABLE captures retain the raw content object, invitation, signatures,
timestamps, URL, and capture time. Network/auth/rate failures emit an
UNAVAILABLE capture artifact and return 3; they never become negative evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

API_V2 = "https://api2.openreview.net"
CAPTURE_SCHEMA = "light.openreview_capture.v1"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_json(base: str, path: str, params: dict, timeout: int = 30) -> tuple[int, dict]:
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "light-review-rebuttal/2.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.getcode()), json.loads(response.read().decode("utf-8"))


def get_json_url(url: str, timeout: int = 30) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "light-review-rebuttal/2.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.getcode()), json.loads(response.read().decode("utf-8"))


def api_kind(base: str) -> str:
    return "OpenReview API v2" if "api2.openreview.net" in base else "OpenReview API v1"


def content_value(note: dict, field: str):
    value = (note.get("content") or {}).get(field)
    return value.get("value") if isinstance(value, dict) else value


def note_type(note: dict) -> str:
    invitations = note.get("invitations") or (
        [note.get("invitation")] if note.get("invitation") else []
    )
    for invitation in invitations:
        if "/-/" in invitation:
            return invitation.rsplit("/-/", 1)[-1]
    return "Unknown"


def raw_text(note: dict) -> str:
    fields = (
        "summary", "strengths", "weaknesses", "questions", "comment",
        "metareview", "meta_review", "decision", "recommendation",
    )
    blocks = []
    for field in fields:
        value = content_value(note, field)
        if value not in (None, "", []):
            blocks.append(f"[{field}]\n{value}")
    if blocks:
        return "\n\n".join(blocks)
    return json.dumps(note.get("content") or {}, ensure_ascii=False, sort_keys=True)


def normalize_note(note: dict, forum: str, captured_at: str) -> dict:
    return {
        "note_id": note.get("id"),
        "forum": note.get("forum") or forum,
        "note_type": note_type(note),
        "invitations": note.get("invitations") or (
            [note.get("invitation")] if note.get("invitation") else []
        ),
        "signatures": note.get("signatures") or [],
        "tcdate": note.get("tcdate"),
        "tmdate": note.get("tmdate"),
        "captured_at": captured_at,
        "access_status": "AVAILABLE",
        "raw_text": raw_text(note),
        "raw_content": note.get("content") or {},
    }


def capture_forum(base: str, forum: str, timeout: int = 30) -> dict:
    captured_at = now()
    code, obj = get_json(base, "/notes", {"forum": forum, "details": "directReplies"}, timeout)
    if code != 200:
        raise RuntimeError(f"HTTP {code}")
    notes = obj.get("notes") or []
    records = [normalize_note(note, forum, captured_at) for note in notes]
    counts = Counter(item["note_type"] for item in records)
    return {
        "schema": CAPTURE_SCHEMA,
        "captured_at": captured_at,
        "source": {
            "kind": api_kind(base),
            "base_url": base,
            "query": {"forum": forum, "details": "directReplies"},
            "http_status": code,
            "access_status": "AVAILABLE",
            "access_tier": "free_public",
        },
        "forum": forum,
        "records": records,
        "counts": dict(sorted(counts.items())),
        "boundary": "Public read-only capture; raw_text/raw_content are source evidence.",
    }


def capture_peerread(url: str, timeout: int = 30) -> dict:
    """Capture a fixed public PeerRead snapshot derived from OpenReview."""
    captured_at = now()
    code, obj = get_json_url(url, timeout)
    if code != 200:
        raise RuntimeError(f"HTTP {code}")
    records = []
    seen_records: set[str] = set()
    duplicate_records = 0
    for index, review in enumerate(obj.get("reviews") or [], 1):
        fingerprint = json.dumps(review, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen_records:
            duplicate_records += 1
            continue
        seen_records.add(fingerprint)
        comments = review.get("comments")
        title = str(review.get("TITLE") or "")
        other = str(review.get("OTHER_KEYS") or "")
        records.append({
            "note_id": f"{obj.get('id') or 'unknown'}-review-{index}",
            "forum": str(obj.get("id") or ""),
            "note_type": (
                "Decision"
                if "final decision" in title.lower()
                else "Meta_Review"
                if review.get("IS_META_REVIEW")
                else "Review"
            ),
            "invitations": [],
            "signatures": [other] if other else [],
            "tcdate": review.get("DATE"),
            "tmdate": None,
            "captured_at": captured_at,
            "access_status": "AVAILABLE",
            "raw_text": "" if comments is None else str(comments),
            "raw_content": review,
        })
    counts = Counter(item["note_type"] for item in records)
    return {
        "schema": CAPTURE_SCHEMA,
        "captured_at": captured_at,
        "source": {
            "kind": "PeerRead public OpenReview snapshot",
            "url": url,
            "http_status": code,
            "access_status": "AVAILABLE",
            "access_tier": "free_public",
        },
        "forum": str(obj.get("id") or ""),
        "paper": {
            "conference": obj.get("conference"),
            "title": obj.get("title"),
            "accepted": obj.get("accepted"),
        },
        "source_record_count": len(obj.get("reviews") or []),
        "duplicate_records_removed": duplicate_records,
        "records": records,
        "counts": dict(sorted(counts.items())),
        "boundary": (
            "PeerRead is a fixed public snapshot, not a live OpenReview view; "
            "raw_text/raw_content are source evidence."
        ),
    }


def unavailable(base: str, forum: str, exc: Exception, kind: str | None = None) -> dict:
    status = getattr(exc, "code", None)
    reason = f"{type(exc).__name__}: {exc}"
    return {
        "schema": CAPTURE_SCHEMA,
        "captured_at": now(),
        "source": {
            "kind": kind or api_kind(base),
            "base_url": base,
            "query": {"forum": forum, "details": "directReplies"},
            "http_status": status,
            "access_status": "UNAVAILABLE",
            "access_tier": "free_public",
            "reason": reason,
        },
        "forum": forum,
        "records": [],
        "counts": {},
        "boundary": (
            "UNAVAILABLE means transport/rate/auth/service failure; it is not evidence "
            "that reviews, decisions, or comments do not exist."
        ),
    }


def _selftest() -> int:
    global get_json_url
    note = {
        "id": "N1", "forum": "F1",
        "invitations": ["V/Submission1/-/Official_Review"],
        "signatures": ["V/Submission1/Reviewer_ABC"],
        "content": {
            "summary": {"value": "Summary verbatim."},
            "weaknesses": {"value": "Major novelty concern."},
            "rating": {"value": "2: Reject"},
        },
    }
    item = normalize_note(note, "F1", "2026-07-03T00:00:00+08:00")
    assert item["note_type"] == "Official_Review"
    assert item["raw_text"] == "[summary]\nSummary verbatim.\n\n[weaknesses]\nMajor novelty concern."
    assert item["raw_content"]["rating"]["value"] == "2: Reject"
    denied = unavailable(API_V2, "F1", urllib.error.HTTPError(
        "https://example.test", 429, "Too Many Requests", {}, None
    ))
    assert denied["source"]["access_status"] == "UNAVAILABLE"
    assert denied["source"]["http_status"] == 429
    assert denied["records"] == []
    assert api_kind("https://api.openreview.net") == "OpenReview API v1"
    assert api_kind(API_V2) == "OpenReview API v2"
    old_get_json_url = get_json_url
    duplicate = {
        "TITLE": "ICLR committee final decision",
        "OTHER_KEYS": "ICLR PCs",
        "DATE": "01 Jan 2017",
        "comments": "Not ready for publication.",
        "IS_META_REVIEW": False,
    }
    def fake_get_json_url(url: str, timeout: int = 30) -> tuple[int, dict]:
        return (
            200,
            {
                "id": "F1",
                "conference": "ICLR",
                "title": "P",
                "accepted": False,
                "reviews": [duplicate, dict(duplicate)],
            },
        )

    try:
        get_json_url = fake_get_json_url
        snapshot = capture_peerread("https://example.test/fixed.json")
    finally:
        get_json_url = old_get_json_url
    assert snapshot["source_record_count"] == 2
    assert snapshot["duplicate_records_removed"] == 1
    assert snapshot["counts"] == {"Decision": 1}
    print(
        "[selftest] PASS fetch_openreview: verbatim capture + provenance + "
        "honest 429 + snapshot duplicate accounting"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="capture public OpenReview forum data")
    parser.add_argument("--forum")
    parser.add_argument(
        "--peerread-url",
        help="fixed public PeerRead JSON snapshot derived from OpenReview",
    )
    parser.add_argument("--base-url", default=API_V2)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if bool(args.forum) == bool(args.peerread_url):
        parser.error("provide exactly one of --forum or --peerread-url")
    try:
        if args.peerread_url:
            report = capture_peerread(args.peerread_url, args.timeout)
        else:
            report = capture_forum(args.base_url, args.forum, args.timeout)
        exit_code = 0
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        if args.peerread_url:
            report = unavailable(
                args.peerread_url,
                "UNKNOWN",
                exc,
                kind="PeerRead public OpenReview snapshot",
            )
            report["source"]["url"] = args.peerread_url
        else:
            report = unavailable(args.base_url, args.forum, exc)
        exit_code = 3
    if args.out:
        write_json(pathlib.Path(args.out), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
