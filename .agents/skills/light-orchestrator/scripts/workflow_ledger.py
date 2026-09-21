#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对多任务编排、人工暂停、恢复快照与有界重试（light.workflow.ledger.v1）。

这是只读决策器，不执行任务、不替用户授权。它把 Dify/Haystack/Mastra 一类框架中的
pause/resume、snapshot compatibility、parallel join 和 retry budget 缩成 Light 的
stdlib 契约，并保持 termination != completion。
"""
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

SCHEMA_ID = "light.workflow.ledger.v1"
STATUSES = {
    "PENDING", "RUNNING", "WAITING_USER", "SUCCEEDED",
    "FAILED", "CANCELLED", "SKIPPED",
}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "SKIPPED"}
SHA_RE = re.compile(r"sha256:[0-9a-fA-F]{64}")
PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^replace-with|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _time(value: Any, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是带时区 ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须带时区")
    return parsed


def _hash(value: Any) -> bool:
    return bool(SHA_RE.fullmatch(str(value or "")))


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value.strip()))


def _safe_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or _is_placeholder(text):
        return False
    if WINDOWS_DRIVE_RE.match(text) or text.startswith(("/", "\\", "~")):
        return False
    path = text.replace("\\", "/").split("#", 1)[0]
    return ".." not in path.split("/")


def _meaningful_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder(value)


def _cycle(tasks: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> list[str] | None:
        if node in visiting:
            start = trail.index(node)
            return trail[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        for dep in tasks[node].get("depends_on", []):
            found = visit(dep, trail + [dep])
            if found:
                return found
        visiting.remove(node)
        visited.add(node)
        return None

    for task_id in tasks:
        found = visit(task_id, [task_id])
        if found:
            return found
    return None


def evaluate(payload: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    workflow_id = str(payload.get("workflow_id") or "").strip()
    workflow_digest = str(payload.get("workflow_digest") or "").strip()
    run_id = str(payload.get("run_id") or "").strip()
    if not workflow_id or not workflow_digest or not run_id:
        raise ValueError("workflow_id/workflow_digest/run_id 必填")
    if _is_placeholder(workflow_id) or _is_placeholder(run_id):
        raise ValueError("workflow_id/run_id 不能是占位符")
    if not _hash(workflow_digest):
        raise ValueError("workflow_digest 必须是 sha256:<64 hex>")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("tasks 必须是非空 list")
    now = now or dt.datetime.now(dt.timezone.utc)
    tasks: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []

    def issue(code: str, message: str, task_id: str | None = None, severity: str = "error") -> None:
        issues.append({
            "severity": severity, "code": code,
            "task_id": task_id, "message": message,
        })

    for index, task in enumerate(raw_tasks):
        if not isinstance(task, dict):
            raise ValueError(f"tasks[{index}] 必须是 object")
        task_id = str(task.get("id") or "").strip()
        if not task_id or task_id in tasks:
            raise ValueError(f"tasks[{index}].id 缺失或重复")
        if task.get("status") not in STATUSES:
            raise ValueError(f"{task_id}.status 非法")
        if not str(task.get("owner") or "").strip():
            issue("OWNER_MISSING", "任务缺 owner，无法追责或恢复上下文", task_id)
        if not str(task.get("context_scope") or "").strip():
            issue("CONTEXT_SCOPE_MISSING", "任务缺 context_scope，父子任务可能串线", task_id)
        deps = task.get("depends_on", [])
        if not isinstance(deps, list) or len(set(deps)) != len(deps):
            raise ValueError(f"{task_id}.depends_on 必须是无重复 list")
        attempts = task.get("attempts")
        max_attempts = task.get("max_attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ValueError(f"{task_id}.attempts 必须是非负整数")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValueError(f"{task_id}.max_attempts 必须是正整数")
        if attempts > max_attempts:
            issue("RETRY_BUDGET_EXCEEDED", f"attempts={attempts} > max={max_attempts}", task_id)
        if task["status"] in {"PENDING", "RUNNING"} and attempts >= max_attempts:
            issue(
                "TERMINAL_RETRY_REQUIRED",
                "重试预算已耗尽，状态必须转 FAILED/CANCELLED，不得继续 retryable",
                task_id,
            )
        if task["status"] == "SUCCEEDED":
            if task.get("completion_status") != "PASS":
                issue("COMPLETION_UNVERIFIED", "SUCCEEDED 缺 completion_status=PASS", task_id)
            artifacts = task.get("evidence_artifacts")
            artifact_hashes: list[str] = []
            if not isinstance(artifacts, list) or not artifacts:
                issue("EVIDENCE_MISSING", "SUCCEEDED 缺 evidence_artifacts", task_id)
            elif any(
                not isinstance(x, dict)
                or not _safe_path(x.get("path"))
                or not _hash(x.get("sha256"))
                for x in artifacts
            ):
                issue("EVIDENCE_INCOMPLETE", "evidence artifact 必须含安全相对 path + 真实 sha256", task_id)
            else:
                artifact_hashes = sorted(
                    {str(x["sha256"]).lower() for x in artifacts}
                )

            verification = task.get("verification")
            if not isinstance(verification, dict):
                issue(
                    "VERIFICATION_MISSING",
                    "SUCCEEDED 缺独立验证包；owner 的完成声明不能替代复核",
                    task_id,
                )
            else:
                if verification.get("status") != "PASS":
                    issue("VERIFICATION_FAILED", "verification.status 必须为 PASS", task_id)
                method = verification.get("method")
                if method not in {"machine_gate", "independent_review", "human_review"}:
                    issue(
                        "VERIFICATION_METHOD_INVALID",
                        "verification.method 必须是 machine_gate/independent_review/human_review",
                        task_id,
                    )
                verifier_id = str(verification.get("verifier_id") or "").strip()
                if not _meaningful_text(verifier_id):
                    issue("VERIFIER_MISSING", "verification 缺非占位 verifier_id", task_id)
                elif verifier_id == str(task.get("owner") or "").strip():
                    issue(
                        "SELF_VERIFICATION_FORBIDDEN",
                        "verifier_id 不能等于任务 owner；自报 PASS 不是独立验证",
                        task_id,
                    )
                checked_at = verification.get("checked_at")
                if not checked_at:
                    issue("VERIFICATION_TIME_MISSING", "verification 缺 checked_at", task_id)
                elif _time(checked_at, f"{task_id}.verification.checked_at") > now:
                    issue("VERIFICATION_FROM_FUTURE", "verification.checked_at 不能晚于核验时间", task_id)
                subjects = verification.get("subject_sha256s")
                normalized_subjects = (
                    sorted(str(x).lower() for x in subjects)
                    if isinstance(subjects, list)
                    and subjects
                    and len(set(subjects)) == len(subjects)
                    and all(_hash(x) for x in subjects)
                    else None
                )
                if normalized_subjects is None:
                    issue(
                        "VERIFICATION_SUBJECT_INVALID",
                        "verification.subject_sha256s 必须是非空、无重复的真实哈希列表",
                        task_id,
                    )
                elif artifact_hashes and normalized_subjects != artifact_hashes:
                    issue(
                        "VERIFICATION_STALE",
                        "验证包绑定的 subject_sha256s 与当前 evidence_artifacts 不一致",
                        task_id,
                    )
                report = verification.get("report")
                if (
                    not isinstance(report, dict)
                    or not _safe_path(report.get("path"))
                    or not _hash(report.get("sha256"))
                ):
                    issue(
                        "VERIFICATION_REPORT_INVALID",
                        "verification.report 必须含安全相对 path + 真实 sha256",
                        task_id,
                    )
                if method == "human_review" and not _meaningful_text(
                    verification.get("authorization_id")
                ):
                    issue(
                        "HUMAN_REVIEW_AUTH_MISSING",
                        "human_review 必须绑定 authorization_id，不能代替用户确认",
                        task_id,
                    )
        if task["status"] == "WAITING_USER":
            decision = task.get("decision")
            if not isinstance(decision, dict):
                issue("DECISION_MISSING", "WAITING_USER 缺 decision checkpoint", task_id)
            else:
                scope = decision.get("scope")
                if (
                    not _meaningful_text(decision.get("id"))
                    or not isinstance(scope, list)
                    or not scope
                    or any(not _meaningful_text(item) for item in scope)
                ):
                    issue("DECISION_SCOPE_MISSING", "decision 缺 id/scope", task_id)
                if decision.get("status") != "PROPOSED":
                    issue(
                        "WAIT_STATE_MISMATCH",
                        "WAITING_USER 只对应 PROPOSED；授权后应进入下一显式状态",
                        task_id,
                    )
                if not _meaningful_text(decision.get("question")):
                    issue(
                        "DECISION_QUESTION_MISSING",
                        "WAITING_USER 必须带给用户看的具体问题，不能只写等待状态",
                        task_id,
                    )
                options = decision.get("options")
                if not isinstance(options, list) or len(options) < 2:
                    issue("DECISION_OPTIONS_MISSING", "人工决策必须给至少两个可选项", task_id)
                else:
                    seen_options: set[str] = set()
                    for idx, option in enumerate(options):
                        if not isinstance(option, dict):
                            issue("DECISION_OPTION_INVALID", f"options[{idx}] 必须是 object", task_id)
                            continue
                        option_id = str(option.get("id") or "").strip()
                        if not _meaningful_text(option_id) or option_id in seen_options:
                            issue("DECISION_OPTION_INVALID", "option id 缺失、占位或重复", task_id)
                        seen_options.add(option_id)
                        if not _meaningful_text(option.get("label")):
                            issue("DECISION_OPTION_LABEL_MISSING", "option 缺 label", task_id)
                        if not any(
                            _meaningful_text(option.get(field))
                            for field in ("consequence", "impact", "tradeoff")
                        ):
                            issue(
                                "DECISION_OPTION_TRADEOFF_MISSING",
                                "每个用户选项必须说明 consequence/impact/tradeoff 之一",
                                task_id,
                            )
                if not decision.get("expires_at"):
                    issue("DECISION_EXPIRY_MISSING", "人工暂停缺 expires_at", task_id)
                elif _time(decision["expires_at"], f"{task_id}.decision.expires_at") <= now:
                    issue("DECISION_EXPIRED", "人工暂停已过期，必须重新确认", task_id)
        tasks[task_id] = task

    for task_id, task in tasks.items():
        for dep in task.get("depends_on", []):
            if dep not in tasks:
                issue("DEPENDENCY_MISSING", f"依赖 {dep} 不存在", task_id)
    if any(x["code"] == "DEPENDENCY_MISSING" for x in issues):
        cycle = None
    else:
        cycle = _cycle(tasks)
    if cycle:
        issue("DEPENDENCY_CYCLE", "依赖成环：" + " -> ".join(cycle))

    for task_id, task in tasks.items():
        dep_states = [tasks[x]["status"] for x in task.get("depends_on", []) if x in tasks]
        if task["status"] in {"RUNNING", "SUCCEEDED"} and any(x != "SUCCEEDED" for x in dep_states):
            issue(
                "JOIN_STARTED_EARLY",
                f"任务已{task['status']}，但依赖状态为 {dep_states}",
                task_id,
            )

    snapshot = payload.get("resume_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict):
            raise ValueError("resume_snapshot 必须是 object/null")
        if snapshot.get("workflow_digest") != workflow_digest:
            issue("SNAPSHOT_WORKFLOW_MISMATCH", "快照 workflow_digest 与当前定义不一致")
        snap_task = str(snapshot.get("task_id") or "")
        if snap_task not in tasks:
            issue("SNAPSHOT_TASK_MISSING", f"快照任务 {snap_task!r} 不在当前 workflow")
        visit = snapshot.get("visit_count")
        if not isinstance(visit, int) or isinstance(visit, bool) or visit < 0:
            issue("SNAPSHOT_VISIT_INVALID", "visit_count 必须是非负整数")
        if not snapshot.get("state_hash"):
            issue("SNAPSHOT_HASH_MISSING", "恢复快照缺 state_hash")
        elif not _hash(snapshot.get("state_hash")):
            issue("SNAPSHOT_HASH_INVALID", "恢复快照 state_hash 必须是 sha256:<64 hex>")

    runnable = sorted(
        task_id for task_id, task in tasks.items()
        if task["status"] == "PENDING"
        and task["attempts"] < task["max_attempts"]
        and all(tasks[dep]["status"] == "SUCCEEDED" for dep in task.get("depends_on", []) if dep in tasks)
        and all(dep in tasks for dep in task.get("depends_on", []))
    )
    waiting = sorted(x for x, task in tasks.items() if task["status"] == "WAITING_USER")
    failed = sorted(x for x, task in tasks.items() if task["status"] == "FAILED")
    if any(x["severity"] == "error" for x in issues):
        status = "FAIL"
    elif waiting:
        status = "UNRESOLVED"
    elif failed and not runnable:
        status = "FAIL"
    else:
        status = "PASS"
    return {
        "schema": SCHEMA_ID,
        "status": status,
        "workflow_id": workflow_id,
        "workflow_digest": workflow_digest,
        "run_id": run_id,
        "runnable_tasks": runnable,
        "waiting_user_tasks": waiting,
        "failed_tasks": failed,
        "issues": issues,
        "honesty": (
            "当 status=PASS 时，也只证明账本状态、依赖、重试预算和快照声明自洽；"
            "不执行任务、不证明产物内容正确，也不授予任何动作权限。"
        ),
    }


def _selftest() -> int:
    h_a = "sha256:" + "a" * 64
    h_b = "sha256:" + "b" * 64
    h_d = "sha256:" + "d" * 64
    h_s = "sha256:" + "c" * 64
    good = {
        "workflow_id": "wf", "workflow_digest": h_d, "run_id": "run-1",
        "tasks": [
            {
                "id": "a", "owner": "main", "context_scope": "project:a",
                "depends_on": [], "status": "SUCCEEDED", "attempts": 1, "max_attempts": 2,
                "completion_status": "PASS",
                "evidence_artifacts": [{"path": "a.json", "sha256": h_a}],
                "verification": {
                    "status": "PASS",
                    "method": "machine_gate",
                    "verifier_id": "light-checkpoint",
                    "checked_at": "2026-07-04T00:00:00+00:00",
                    "subject_sha256s": [h_a],
                    "report": {"path": "checks/a.json", "sha256": h_b},
                },
            },
            {
                "id": "b", "owner": "main", "context_scope": "project:b",
                "depends_on": ["a"], "status": "PENDING", "attempts": 0, "max_attempts": 2,
            },
        ],
        "resume_snapshot": {
            "workflow_digest": h_d, "task_id": "b",
            "visit_count": 0, "state_hash": h_s,
        },
    }
    passed = evaluate(good)
    assert passed["status"] == "PASS" and passed["runnable_tasks"] == ["b"], passed

    waiting = json.loads(json.dumps(good))
    waiting["tasks"][1].update({
        "status": "WAITING_USER",
        "decision": {
            "id": "d1", "scope": ["publish:artifact"], "status": "PROPOSED",
            "expires_at": "2026-07-05T00:00:00+00:00",
            "question": "是否发布当前交付包？",
            "options": [
                {"id": "publish", "label": "发布", "consequence": "外部可见，需接受当前限制"},
                {"id": "hold", "label": "暂缓", "consequence": "继续内部修订，不发生外部写入"},
            ],
        },
    })
    unresolved = evaluate(waiting, dt.datetime(2026, 7, 4, tzinfo=dt.timezone.utc))
    assert unresolved["status"] == "UNRESOLVED", unresolved

    hollow_wait = json.loads(json.dumps(waiting))
    hollow_wait["tasks"][1]["decision"].pop("question")
    hollow_wait["tasks"][1]["decision"]["options"] = [
        {"id": "go", "label": "继续"}
    ]
    hollow_report = evaluate(hollow_wait, dt.datetime(2026, 7, 4, tzinfo=dt.timezone.utc))
    hollow_codes = {item["code"] for item in hollow_report["issues"]}
    assert hollow_report["status"] == "FAIL"
    assert {"DECISION_QUESTION_MISSING", "DECISION_OPTIONS_MISSING"} <= hollow_codes

    bad = json.loads(json.dumps(good))
    bad["workflow_digest"] = "sha256:" + "e" * 64
    bad["tasks"][1].update({"status": "RUNNING", "attempts": 2, "max_attempts": 2})
    failed = evaluate(bad)
    codes = {x["code"] for x in failed["issues"]}
    assert failed["status"] == "FAIL"
    assert {"TERMINAL_RETRY_REQUIRED", "SNAPSHOT_WORKFLOW_MISMATCH"} <= codes

    early = json.loads(json.dumps(good))
    early["tasks"][0]["status"] = "FAILED"
    early["tasks"][1]["status"] = "SUCCEEDED"
    early["tasks"][1]["completion_status"] = "PASS"
    early["tasks"][1]["evidence_artifacts"] = [{"path": "b", "sha256": h_b}]
    early["tasks"][1]["verification"] = {
        "status": "PASS",
        "method": "independent_review",
        "verifier_id": "reviewer",
        "checked_at": "2026-07-04T00:00:00+00:00",
        "subject_sha256s": [h_b],
        "report": {"path": "checks/b.json", "sha256": h_a},
    }
    assert any(x["code"] == "JOIN_STARTED_EARLY" for x in evaluate(early)["issues"])
    placeholder_hash = json.loads(json.dumps(good))
    placeholder_hash["tasks"][0]["evidence_artifacts"][0]["sha256"] = "sha256:replace-with-artifact-hash"
    placeholder_report = evaluate(placeholder_hash)
    assert placeholder_report["status"] == "FAIL"
    assert any(item["code"] == "EVIDENCE_INCOMPLETE" for item in placeholder_report["issues"])
    self_verified = json.loads(json.dumps(good))
    self_verified["tasks"][0]["verification"]["verifier_id"] = "main"
    self_verified_report = evaluate(
        self_verified, dt.datetime(2026, 7, 5, tzinfo=dt.timezone.utc)
    )
    assert self_verified_report["status"] == "FAIL"
    assert any(
        item["code"] == "SELF_VERIFICATION_FORBIDDEN"
        for item in self_verified_report["issues"]
    )
    stale_verification = json.loads(json.dumps(good))
    stale_verification["tasks"][0]["verification"]["subject_sha256s"] = [h_b]
    stale_verification_report = evaluate(
        stale_verification, dt.datetime(2026, 7, 5, tzinfo=dt.timezone.utc)
    )
    assert stale_verification_report["status"] == "FAIL"
    assert any(
        item["code"] == "VERIFICATION_STALE"
        for item in stale_verification_report["issues"]
    )
    print(
        "workflow_ledger selftest PASS: runnable/HITL/快照/真实哈希/"
        "独立验证绑定/重试上限/提前 join"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", help="workflow ledger JSON")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    try:
        report = evaluate(payload)
    except ValueError as exc:
        report = {
            "schema": SCHEMA_ID,
            "status": "FAIL",
            "workflow_id": payload.get("workflow_id"),
            "workflow_digest": payload.get("workflow_digest"),
            "run_id": payload.get("run_id"),
            "runnable_tasks": [],
            "waiting_user_tasks": [],
            "failed_tasks": [],
            "issues": [{
                "severity": "error",
                "code": "WORKFLOW_LEDGER_SCHEMA_INVALID",
                "task_id": None,
                "message": str(exc),
            }],
            "honesty": "输入结构或占位证据无效；未执行任务，也未授权任何动作。",
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
