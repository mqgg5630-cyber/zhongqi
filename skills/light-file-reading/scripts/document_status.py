#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聚合文件阅读的文档/通道/页级状态（light.file_reading.status.v1）。"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = pathlib.Path(__file__).resolve()
_ROOT = _HERE
while _ROOT != _ROOT.parent and not (_ROOT / "_shared").is_dir():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))

from _shared.status_contract import StatusIssue, StatusRecord  # noqa: E402

SCHEMA_ID = "light.file_reading.status.v1"
CHANNELS = ("text", "tables", "formulas", "figures", "layout", "annotations", "metadata")


def aggregate(channels: dict[str, dict[str, Any]],
              pages_total: int | None = None,
              requested_channels: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(channels, dict) or not channels:
        raise ValueError("channels 必须是非空 object")
    if pages_total is not None and (
        not isinstance(pages_total, int) or isinstance(pages_total, bool) or pages_total < 1
    ):
        raise ValueError("pages_total 必须是 >=1 的整数或 null")
    unknown = sorted(set(channels) - set(CHANNELS))
    if unknown:
        raise ValueError(f"未知 channel: {unknown}")
    requested = requested_channels if requested_channels is not None else list(channels)
    if not isinstance(requested, list) or not requested:
        raise ValueError("requested_channels 必须是非空 list")
    unknown_requested = sorted(set(requested) - set(CHANNELS))
    if unknown_requested:
        raise ValueError(f"requested_channels 含未知 channel: {unknown_requested}")
    missing_requested = sorted(set(requested) - set(channels))

    normalized: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    for name, value in channels.items():
        if not isinstance(value, dict):
            raise ValueError(f"channel {name} 必须是 object")
        issues = [
            StatusIssue(
                code=str(item.get("code", "")),
                message=str(item.get("message", "")),
                locator=str(item.get("locator", "")),
                retryable=bool(item.get("retryable", False)),
            )
            for item in value.get("issues", [])
        ]
        status = str(value.get("status", ""))
        record = StatusRecord(
            operation=f"file-reading:{name}",
            status=status,
            checked=[str(x) for x in value.get("checked", [])],
            unchecked=[str(x) for x in value.get("unchecked", [])],
            issues=issues,
            note=str(value.get("note", "")),
        )
        normalized[name] = record.to_dict()
        statuses.append(status)
    for name in missing_requested:
        record = StatusRecord(
            operation=f"file-reading:{name}",
            status="UNRESOLVED",
            unchecked=["all"],
            issues=[StatusIssue(
                "REQUESTED_CHANNEL_MISSING",
                f"请求读取 {name}，但没有该通道结果",
                f"channel:{name}",
                True,
            )],
        )
        normalized[name] = record.to_dict()
        statuses.append("UNRESOLVED")

    if any(x == "ERROR" for x in statuses):
        overall = "ERROR"
    elif any(x == "FAIL" for x in statuses):
        overall = "FAIL"
    elif any(x in {"PARTIAL", "UNAVAILABLE", "UNRESOLVED"} for x in statuses):
        overall = "PARTIAL"
    elif all(x == "SKIPPED" for x in statuses):
        overall = "SKIPPED"
    elif any(x == "WARN" for x in statuses):
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "schema": SCHEMA_ID,
        "status": overall,
        "pages_total": pages_total,
        "requested_channels": requested,
        "channels": normalized,
        "honesty": (
            "EXTRACTED/PASS 仅表示声明通道的抽取与覆盖完成；"
            "不自动表示 reading order、数值、图表或科学含义已正确理解。"
        ),
    }


def _selftest() -> int:
    full = aggregate({
        "text": {"status": "PASS", "checked": ["pages:1-2"]},
        "metadata": {"status": "PASS", "checked": ["document"]},
    }, 2)
    assert full["status"] == "PASS", full

    partial = aggregate({
        "text": {
            "status": "PARTIAL",
            "checked": ["page:1"],
            "unchecked": ["page:2"],
            "issues": [{
                "code": "PAGE_TIMEOUT",
                "message": "page timed out",
                "locator": "page:2",
                "retryable": True,
            }],
        },
        "tables": {
            "status": "UNRESOLVED",
            "checked": [],
            "unchecked": ["all"],
            "note": "未安装表格解析器",
        },
    }, 2)
    assert partial["status"] == "PARTIAL", partial
    assert partial["channels"]["text"]["issues"][0]["locator"] == "page:2"

    omitted = aggregate(
        {"text": {"status": "PASS", "checked": ["all"]}},
        1,
        requested_channels=["text", "figures"],
    )
    assert omitted["status"] == "PARTIAL", omitted
    assert omitted["channels"]["figures"]["status"] == "UNRESOLVED"

    failed = aggregate({
        "text": {
            "status": "ERROR",
            "checked": [],
            "unchecked": ["all"],
            "note": "文件损坏",
        }
    })
    assert failed["status"] == "ERROR", failed

    try:
        aggregate({"audio": {"status": "PASS", "checked": ["all"]}})
        raise AssertionError("未知 channel 应失败")
    except ValueError:
        pass
    print("document_status selftest PASS: full/partial/omitted/error/channel 五组通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", help="channels JSON")
    args = parser.parse_args()
    if args.input:
        payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
        print(json.dumps(
            aggregate(
                payload["channels"],
                payload.get("pages_total"),
                payload.get("requested_channels"),
            ),
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())
