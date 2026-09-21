#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无数据库的项目记忆条目账本（light.memory.items.v1）。

这是项目目录内的显式 JSON 文件，不是向量库或后台知识库。它提供最小的
scope / sensitivity / retention / provenance / supersession / deletion 语义。
restricted/secret 内容拒绝进入可能随仓库传播的 `.light/`。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.memory.items.v1"
KINDS = {"project_fact", "decision", "failure", "handoff", "open_question", "lesson"}
SCOPES = {"session", "project"}
SENSITIVITY = {"public", "internal", "restricted"}
RETENTION = {"session", "temporary", "project"}
MAX_VALUE_CHARS = 1200
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?i)(?:phone|tel|mobile|手机号|电话|联系方式)\s*[:：=]?\s*\+?\d[\d\s().-]{7,}\d")
CHINA_ID_RE = re.compile(r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")
LOCAL_PATH_RE = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/]|(?:^|\s)/(?:Users|home|tmp|var/tmp)/)")
DIALOGUE_MARKER_RE = re.compile(r"(?im)^\s*(?:user|assistant|system|developer|human|ai|用户|助手|模型|系统)\s*[:：]")
FULL_CONVERSATION_HINT_RE = re.compile(r"(?i)(?:完整对话|聊天全文|raw chat|full conversation|conversation transcript)")
SOURCE_PLACEHOLDERS = {"chat", "conversation", "raw_chat", "chat_history", "memory", "unknown", "pending", "todo", "tbd", "n/a", "none"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: Any, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是带时区 ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须带时区")
    return parsed


def _source_is_vague(source: str) -> bool:
    value = source.strip().casefold()
    if not value or value in SOURCE_PLACEHOLDERS:
        return True
    return any(marker in value for marker in ("<", "{{", "}}", "..."))


def _privacy_findings(item_id: str, item: dict[str, Any]) -> list[dict[str, str]]:
    """Return repository-safety findings for one memory item.

    memory_items.json is designed to travel with a project repository. It should
    contain minimal state, provenance, and next actions; not raw dialogue,
    personal contact data, local machine paths, or long pasted source material.
    """
    findings: list[dict[str, str]] = []
    value = str(item.get("value") or "")
    source = str(item.get("source") or "")
    text_for_pii = "\n".join(part for part in (value, source) if part)
    if _source_is_vague(source):
        findings.append({
            "severity": "error", "code": "SOURCE_LOCATOR_UNSAFE",
            "item_id": item_id,
            "message": "source 必须是可交接的具体 locator，不能只写 chat/conversation/unknown",
        })
    if len(value) > MAX_VALUE_CHARS:
        findings.append({
            "severity": "error", "code": "VALUE_TOO_LONG_FOR_LEDGER",
            "item_id": item_id,
            "message": f"value 超过 {MAX_VALUE_CHARS} 字符；memory item 只存最小摘要，长文本放 artifact 并记录 locator",
        })
    if item.get("contains_full_conversation") is True or FULL_CONVERSATION_HINT_RE.search(value):
        findings.append({
            "severity": "error", "code": "FULL_CONVERSATION_CAPTURED",
            "item_id": item_id,
            "message": "不得把完整对话/聊天全文写入 memory_items.json",
        })
    if len(DIALOGUE_MARKER_RE.findall(value)) >= 2:
        findings.append({
            "severity": "error", "code": "RAW_DIALOGUE_CAPTURED",
            "item_id": item_id,
            "message": "value 看起来像原始多轮对话；请改成最小项目状态 + source locator",
        })
    if EMAIL_RE.search(text_for_pii):
        findings.append({
            "severity": "error", "code": "POSSIBLE_EMAIL_IN_LEDGER",
            "item_id": item_id,
            "message": "疑似邮箱/个人联系方式不得进入随仓库传播的项目记忆",
        })
    if CHINA_ID_RE.search(text_for_pii) or PHONE_RE.search(text_for_pii):
        findings.append({
            "severity": "error", "code": "POSSIBLE_PII_IN_LEDGER",
            "item_id": item_id,
            "message": "疑似身份证号/电话号码等 PII；只保留仓库外安全位置的无敏感指针",
        })
    if LOCAL_PATH_RE.search(text_for_pii):
        findings.append({
            "severity": "error", "code": "LOCAL_ABSOLUTE_PATH_IN_LEDGER",
            "item_id": item_id,
            "message": "疑似本机绝对路径/UNC 路径；公开可传播记忆只写仓库相对路径或外部非敏感 locator",
        })
    return findings


def empty_ledger(project_id: str) -> dict[str, Any]:
    if not project_id.strip():
        raise ValueError("project_id 不得为空")
    return {
        "schema": SCHEMA_ID,
        "project_id": project_id.strip(),
        "updated_at": _now(),
        "items": [],
    }


def validate(ledger: dict[str, Any], now: dt.datetime | None = None) -> list[dict[str, str]]:
    if ledger.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    if not str(ledger.get("project_id") or "").strip():
        raise ValueError("project_id 必填")
    items = ledger.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是 list")
    now = now or dt.datetime.now(dt.timezone.utc)
    findings: list[dict[str, str]] = []
    ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] 必须是 object")
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in ids:
            raise ValueError(f"items[{index}].id 缺失或重复")
        ids.add(item_id)
        by_id[item_id] = item
        if item.get("kind") not in KINDS:
            raise ValueError(f"{item_id}.kind 非法")
        if item.get("scope") not in SCOPES:
            raise ValueError(f"{item_id}.scope 非法")
        if item.get("sensitivity") not in SENSITIVITY:
            raise ValueError(f"{item_id}.sensitivity 非法")
        if item.get("retention") not in RETENTION:
            raise ValueError(f"{item_id}.retention 非法")
        if item.get("status") not in {"active", "superseded", "deleted"}:
            raise ValueError(f"{item_id}.status 非法")
        if not str(item.get("source") or "").strip():
            raise ValueError(f"{item_id}.source 必填")
        _parse_time(item.get("created_at"), f"{item_id}.created_at")
        if item["sensitivity"] == "restricted":
            findings.append({
                "severity": "error", "code": "RESTRICTED_IN_PROJECT_LEDGER",
                "item_id": item_id,
                "message": "restricted 内容不得存入可能随仓库传播的项目记忆",
            })
        text = str(item.get("value") or "")
        if item["status"] == "deleted" and text:
            findings.append({
                "severity": "error", "code": "DELETED_VALUE_RETAINED",
                "item_id": item_id, "message": "deleted 条目仍保留 value",
            })
        if item["status"] != "deleted" and not text.strip():
            findings.append({
                "severity": "error", "code": "ACTIVE_VALUE_MISSING",
                "item_id": item_id, "message": "未删除条目缺 value",
            })
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append({
                "severity": "error", "code": "POSSIBLE_SECRET",
                "item_id": item_id, "message": "疑似密钥值；只记录 key 名或仓库外安全位置",
            })
        findings.extend(_privacy_findings(item_id, item))
        expires = item.get("expires_at")
        if item["retention"] in {"session", "temporary"} and not expires:
            findings.append({
                "severity": "error", "code": "EXPIRY_REQUIRED",
                "item_id": item_id, "message": "短期记忆必须给 expires_at",
            })
        if expires:
            expiry = _parse_time(expires, f"{item_id}.expires_at")
            if item["status"] == "active" and expiry <= now:
                findings.append({
                    "severity": "warn", "code": "EXPIRED_ACTIVE_ITEM",
                    "item_id": item_id, "message": "条目已过期但仍 active，应删除或续期",
                })
    for item_id, item in by_id.items():
        parent = item.get("supersedes")
        if parent and parent not in by_id:
            findings.append({
                "severity": "error", "code": "DANGLING_SUPERSEDES",
                "item_id": item_id, "message": f"supersedes 指向不存在条目 {parent}",
            })
        if parent and by_id[parent].get("status") != "superseded":
            findings.append({
                "severity": "error", "code": "SUPERSEDED_STATE_MISMATCH",
                "item_id": item_id, "message": f"旧条目 {parent} 未标 superseded",
            })
    return findings


def add_item(ledger: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    value = str(item.get("value") or "")
    if item.get("sensitivity", "internal") == "restricted":
        raise ValueError("restricted 内容拒绝进入 .light；请存仓库外安全位置，仅留无敏感值指针")
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        raise ValueError("疑似密钥值，拒绝写入；只记录 key 名或仓库外安全位置")
    new = {
        "id": str(item.get("id") or "").strip(),
        "kind": item.get("kind"),
        "scope": item.get("scope", "project"),
        "sensitivity": item.get("sensitivity", "internal"),
        "retention": item.get("retention", "project"),
        "source": str(item.get("source") or "").strip(),
        "created_at": item.get("created_at") or _now(),
        "expires_at": item.get("expires_at"),
        "status": "active",
        "supersedes": item.get("supersedes"),
        "value": value,
    }
    parent = new.get("supersedes")
    if parent:
        matches = [x for x in ledger.get("items", []) if x.get("id") == parent]
        if len(matches) != 1:
            raise ValueError(f"supersedes={parent} 不存在或不唯一")
        if matches[0].get("status") != "active":
            raise ValueError("只能替代 active 条目")
        matches[0]["status"] = "superseded"
        matches[0]["superseded_at"] = new["created_at"]
    ledger.setdefault("items", []).append(new)
    ledger["updated_at"] = _now()
    errors = [x for x in validate(ledger) if x["severity"] == "error"]
    if errors:
        ledger["items"].pop()
        if parent:
            matches[0]["status"] = "active"
            matches[0].pop("superseded_at", None)
        raise ValueError("; ".join(x["message"] for x in errors))
    return ledger


def delete_item(
    ledger: dict[str, Any], item_id: str, reason: str, deleted_at: str | None = None
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("删除必须记录 reason")
    matches = [x for x in ledger.get("items", []) if x.get("id") == item_id]
    if len(matches) != 1:
        raise ValueError(f"找不到唯一条目 {item_id}")
    item = matches[0]
    if item.get("status") == "deleted":
        return ledger
    item["status"] = "deleted"
    item["value"] = ""
    item["deleted_at"] = deleted_at or _now()
    item["deletion_reason"] = reason.strip()
    ledger["updated_at"] = _now()
    return ledger


def _load(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _atomic_write(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _selftest() -> int:
    ledger = empty_ledger("selftest")
    add_item(ledger, {
        "id": "fact-1", "kind": "project_fact", "scope": "project",
        "sensitivity": "internal", "retention": "project",
        "source": "experiment/run-1", "value": "baseline 已运行；指标见 artifact hash",
        "created_at": "2026-07-04T08:00:00+00:00",
    })
    add_item(ledger, {
        "id": "fact-2", "kind": "project_fact", "scope": "project",
        "sensitivity": "internal", "retention": "project",
        "source": "experiment/run-2", "value": "baseline 已重跑；指标见新 artifact hash",
        "supersedes": "fact-1", "created_at": "2026-07-04T09:00:00+00:00",
    })
    assert ledger["items"][0]["status"] == "superseded"
    delete_item(ledger, "fact-2", "用户要求忘记该条目", "2026-07-04T10:00:00+00:00")
    assert ledger["items"][1]["status"] == "deleted" and not ledger["items"][1]["value"]
    assert not [x for x in validate(
        ledger, dt.datetime(2026, 7, 4, 11, tzinfo=dt.timezone.utc)
    ) if x["severity"] == "error"]

    try:
        add_item(ledger, {
            "id": "secret", "kind": "project_fact", "scope": "project",
            "sensitivity": "internal", "retention": "project",
            "source": "chat", "value": "api_key=top-secret-value",
        })
        raise AssertionError("密钥应拒绝")
    except ValueError:
        pass
    try:
        add_item(ledger, {
            "id": "restricted", "kind": "project_fact", "scope": "project",
            "sensitivity": "restricted", "retention": "project",
            "source": "chat", "value": "私人内容",
        })
        raise AssertionError("restricted 应拒绝")
    except ValueError:
        pass

    def assert_privacy_rule(item: dict[str, Any], code: str) -> None:
        probe = empty_ledger("privacy")
        candidate = dict(item)
        candidate.setdefault("kind", "project_fact")
        candidate.setdefault("scope", "project")
        candidate.setdefault("sensitivity", "internal")
        candidate.setdefault("retention", "project")
        candidate.setdefault("source", "handoff:S01#fact")
        candidate.setdefault("created_at", "2026-07-04T08:00:00+00:00")
        candidate.setdefault("status", "active")
        direct = dict(probe)
        direct["items"] = [candidate]
        assert any(x["code"] == code for x in validate(direct)), validate(direct)
        try:
            add_item(probe, candidate)
            raise AssertionError(f"{code} 应拒绝写入")
        except ValueError:
            pass

    assert_privacy_rule({
        "id": "vague-source", "source": "chat", "value": "模型说项目做到 stage 3",
    }, "SOURCE_LOCATOR_UNSAFE")
    assert_privacy_rule({
        "id": "email", "value": "联系作者 light@example.com 获取未公开数据",
    }, "POSSIBLE_EMAIL_IN_LEDGER")
    assert_privacy_rule({
        "id": "local-path", "value": "原始文件在 D:\\Users\\Light\\secret\\raw.xlsx",
    }, "LOCAL_ABSOLUTE_PATH_IN_LEDGER")
    assert_privacy_rule({
        "id": "raw-dialogue", "value": "用户: 继续\n助手: 好的，我接着做",
    }, "RAW_DIALOGUE_CAPTURED")
    assert_privacy_rule({
        "id": "raw-chat", "contains_full_conversation": True,
        "value": "full conversation transcript stored here",
    }, "FULL_CONVERSATION_CAPTURED")
    assert_privacy_rule({
        "id": "too-long", "value": "x" * (MAX_VALUE_CHARS + 1),
    }, "VALUE_TOO_LONG_FOR_LEDGER")

    expiring = empty_ledger("expiry")
    add_item(expiring, {
        "id": "tmp", "kind": "handoff", "scope": "session",
        "sensitivity": "internal", "retention": "session", "source": "session:S1",
        "value": "临时上下文", "expires_at": "2026-07-04T09:00:00+00:00",
        "created_at": "2026-07-04T08:00:00+00:00",
    })
    findings = validate(expiring, dt.datetime(2026, 7, 4, 10, tzinfo=dt.timezone.utc))
    assert any(x["code"] == "EXPIRED_ACTIVE_ITEM" for x in findings)
    print("memory_items selftest PASS: 替代链/删除/密钥拒绝/restricted拒绝/PII与原始对话拒绝/过期审计")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init")
    init.add_argument("--file", required=True)
    init.add_argument("--project", required=True)
    add = sub.add_parser("add")
    add.add_argument("--file", required=True)
    add.add_argument("--item", required=True, help="单条 item JSON 文件")
    delete = sub.add_parser("delete")
    delete.add_argument("--file", required=True)
    delete.add_argument("--id", required=True)
    delete.add_argument("--reason", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--file", required=True)
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if args.command == "init":
        _atomic_write(pathlib.Path(args.file), empty_ledger(args.project))
        return 0
    if args.command == "add":
        path = pathlib.Path(args.file)
        ledger = _load(path)
        item = _load(pathlib.Path(args.item))
        _atomic_write(path, add_item(ledger, item))
        return 0
    if args.command == "delete":
        path = pathlib.Path(args.file)
        _atomic_write(path, delete_item(_load(path), args.id, args.reason))
        return 0
    if args.command == "audit":
        findings = validate(_load(pathlib.Path(args.file)))
        report = {
            "schema": SCHEMA_ID,
            "status": "FAIL" if any(x["severity"] == "error" for x in findings)
            else ("WARN" if findings else "PASS"),
            "findings": findings,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["status"] == "FAIL" else 0
    parser.error("需要子命令或 --selftest")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
