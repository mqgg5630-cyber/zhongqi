#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate resume integrity, memory item governance, and failure retry discipline."""
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

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "skills" / "light-orchestrator" / "scripts"))
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402

try:
    import passport  # noqa: E402
except Exception:  # pragma: no cover - selftest requires the local repo layout
    passport = None


def _e2e_selftest_dir() -> pathlib.Path:
    root = _ROOT / ".upgrade" / "_e2e"
    root.mkdir(parents=True, exist_ok=True)
    return root

SCHEMA_ID = "light.memory_governance.v1"
PACKAGE_READY = {"RESUME_READY", "HANDOFF_READY", "SUBMIT_READY", "PUBLISH_READY"}
LAYERS = {"fact", "session_summary", "failure_attempt", "artifact_version", "tombstone", "open_question", "decision"}
STATUSES = {"active", "superseded", "deleted", "tombstone"}
SCOPES = {"session", "project", "public_product", "private_user", "external_reference"}
SENSITIVITY = {"public", "internal", "restricted", "secret"}
REVERSIBILITY = {"reversible", "tombstone_only", "hard_delete_required"}
STORAGE = {"repo", "local_only", "external_secure"}
FAILURE_STATES = {"unresolved", "resolved", "superseded", "won_t_retry"}
FORK_STATES = {"PLANNED", "RUNNING", "COMPARED", "MERGED", "ABANDONED"}
SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
SECRET_RE = re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b")
MAX_REPO_VALUE_CHARS = 1200
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?i)(?:phone|tel|mobile|手机号|电话|联系方式)\s*[:：=]?\s*\+?\d[\d\s().-]{7,}\d")
CHINA_ID_RE = re.compile(r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")
LOCAL_PATH_RE = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/]|(?:^|\s)/(?:Users|home|tmp|var/tmp)/)")
DIALOGUE_MARKER_RE = re.compile(r"(?im)^\s*(?:user|assistant|system|developer|human|ai|用户|助手|模型|系统)\s*[:：]")
FULL_CONVERSATION_HINT_RE = re.compile(r"(?i)(?:完整对话|聊天全文|raw chat|full conversation|conversation transcript)")


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and "<" not in text and "{{" not in text and text.casefold() not in {
        "unknown", "pending", "gap", "n/a",
    }


def _sha(value: Any) -> bool:
    return bool(SHA_RE.fullmatch(str(value or "")))


def _time(value: Any) -> bool:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _repo_privacy_checks(item: dict[str, Any], bag: Bag, loc: str) -> None:
    if item.get("storage") != "repo":
        return
    value = str(item.get("value") or "")
    joined = "\n".join(
        str(item.get(field) or "")
        for field in ("value", "source_locator", "artifact_path", "evidence_locator")
        if item.get(field)
    )
    if len(value) > MAX_REPO_VALUE_CHARS:
        bag.add(
            "privacy_policy", "critical", loc,
            f"repo memory item value 超过 {MAX_REPO_VALUE_CHARS} 字符，像在存原文而不是最小状态",
            "长文本放 artifact / handoff / 外部安全位置，memory item 只留摘要与 locator",
            "REPO_MEMORY_VALUE_TOO_LONG",
        )
    if FULL_CONVERSATION_HINT_RE.search(value) or len(DIALOGUE_MARKER_RE.findall(value)) >= 2:
        bag.add(
            "privacy_policy", "critical", loc,
            "repo memory item 看起来包含原始聊天/完整对话",
            "改成最小项目状态、下一步和 source locator；完整对话不进仓库台账",
            "RAW_DIALOGUE_OR_FULL_CHAT_IN_REPO",
        )
    if EMAIL_RE.search(joined):
        bag.add(
            "privacy_policy", "critical", loc,
            "repo memory item 含疑似邮箱/个人联系方式",
            "私人联系方式留在仓库外；公开台账只保留非敏感 locator",
            "EMAIL_OR_CONTACT_IN_REPO_MEMORY",
        )
    if PHONE_RE.search(joined) or CHINA_ID_RE.search(joined):
        bag.add(
            "privacy_policy", "critical", loc,
            "repo memory item 含疑似电话/身份证号等 PII",
            "PII 不进入随仓库传播的 `.light/`；只留脱敏指针",
            "PII_IN_REPO_MEMORY",
        )
    if LOCAL_PATH_RE.search(joined):
        bag.add(
            "privacy_policy", "critical", loc,
            "repo memory item 含本机绝对路径/UNC 路径",
            "改成仓库相对路径、公开 URL 或仓库外安全位置的脱敏 locator",
            "LOCAL_ABSOLUTE_PATH_IN_REPO_MEMORY",
        )


class Bag:
    def __init__(self) -> None:
        self.rows: dict[str, list[tuple[str, Finding]]] = {
            "resume_integrity": [],
            "memory_items": [],
            "artifact_versions": [],
            "failure_index": [],
            "fork_comparisons": [],
            "privacy_policy": [],
        }

    def add(self, gate: str, severity: str, loc: str, issue: str, fix: str, rule: str,
            evidence: str | None = None) -> None:
        self.rows.setdefault(gate, []).append((
            severity,
            Finding(loc=loc, issue=issue, fix=fix, evidence=evidence, rule=rule),
        ))

    def gates(self) -> list[GateResult]:
        out: list[GateResult] = []
        for gate, rows in self.rows.items():
            if not rows:
                out.append(GateResult(gate, "pass", "info"))
                continue
            severity = "critical" if any(sev == "critical" for sev, _ in rows) else "major"
            out.append(GateResult(
                gate=gate,
                status="fail" if severity == "critical" else "warn",
                severity=severity,
                findings=[finding for _, finding in rows],
            ))
        return out


def _resume(spec: dict[str, Any], bag: Bag, ready: bool, base: pathlib.Path) -> None:
    resume = spec.get("resume") or {}
    passport_info = resume.get("passport") or {}
    handoff = resume.get("handoff") or {}
    computed_hash = None
    passport_path = passport_info.get("path")
    if passport_path and passport is not None:
        path = pathlib.Path(passport_path)
        if not path.is_absolute():
            path = (base / path).resolve()
        if path.is_file():
            try:
                data = passport.load(str(path))
                computed_hash = passport.compute_state_hash(data)
                recorded = data.get("state_hash")
                if recorded and recorded != computed_hash:
                    bag.add("resume_integrity", "critical", str(path), "passport state_hash 与当前内容不一致", "重新运行 passport save/validate；篡改不能静默续跑", "PASSPORT_STATE_HASH_MISMATCH", f"recorded={recorded}; computed={computed_hash}")
                expected_stage = passport_info.get("expected_current_stage")
                if expected_stage is not None and data.get("current_stage") != expected_stage:
                    bag.add("resume_integrity", "critical", "resume.passport.expected_current_stage", "resume 期望阶段与 passport current_stage 冲突", "以 passport 为准并修正 handoff/resume 摘要", "RESUME_STAGE_CONFLICT")
            except Exception as exc:  # noqa: BLE001
                bag.add("resume_integrity", "critical", str(path), f"passport 读取/哈希计算失败:{exc}", "先修复 passport.yaml", "PASSPORT_READ_FAILED")
        elif ready:
            bag.add("resume_integrity", "critical", str(path), "resume 指向的 passport 不存在", "提供正确 .light/passport.yaml", "PASSPORT_MISSING")
    elif ready:
        bag.add("resume_integrity", "major", "resume.passport.path", "未给 passport path，无法重算 state hash", "handoff/resume-ready 前应绑定 passport path", "PASSPORT_PATH_MISSING")
    if handoff:
        expected = handoff.get("state_hash")
        if expected and computed_hash and expected != computed_hash:
            bag.add("resume_integrity", "critical", "resume.handoff.state_hash", "handoff state_hash 与当前 passport 内容不一致", "重读当前 passport，标记旧 handoff stale，生成新 handoff", "HANDOFF_HASH_STALE")
        if handoff.get("artifact_path") and handoff.get("artifact_sha256") and not _sha(handoff.get("artifact_sha256")):
            bag.add("resume_integrity", "critical", "resume.handoff.artifact_sha256", "handoff artifact hash 格式非法", "写 sha256:<64 hex> 或 64 hex", "HANDOFF_HASH_INVALID")
    summary = resume.get("summary") or {}
    if summary:
        if computed_hash and summary.get("passport_state_hash") and summary.get("passport_state_hash") != computed_hash:
            bag.add("resume_integrity", "critical", "resume.summary.passport_state_hash", "resume summary 引用旧 state hash", "resume report 必须展示并重算当前 hash", "RESUME_SUMMARY_HASH_STALE")
        if summary.get("source") == "chat_history_only" and ready:
            bag.add("resume_integrity", "critical", "resume.summary.source", "resume 只来自聊天历史而非 .light/passport", "用 pm.py resume 从 .light 确定性生成", "RESUME_NOT_LEDGER_BOUND")


def _items(spec: dict[str, Any], bag: Bag, ready: bool) -> dict[str, dict[str, Any]]:
    items = spec.get("memory_items") or []
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        raise ValueError("memory_items 必须是 list")
    for item in items:
        item_id = str(item.get("id") or "")
        loc = item_id or "memory_item"
        if not item_id:
            bag.add("memory_items", "critical", loc, "memory item 缺 id", "给条目稳定 ID", "MEMORY_ITEM_ID_MISSING")
            continue
        if item_id in by_id:
            bag.add("memory_items", "critical", loc, "memory item id 重复", "合并或重命名条目", "MEMORY_ITEM_DUPLICATE")
        by_id[item_id] = item
        for field, allowed, rule in (
            ("layer", LAYERS, "MEMORY_LAYER_INVALID"),
            ("status", STATUSES, "MEMORY_STATUS_INVALID"),
            ("scope", SCOPES, "MEMORY_SCOPE_INVALID"),
            ("sensitivity", SENSITIVITY, "MEMORY_SENSITIVITY_INVALID"),
            ("reversibility", REVERSIBILITY, "MEMORY_REVERSIBILITY_INVALID"),
            ("storage", STORAGE, "MEMORY_STORAGE_INVALID"),
        ):
            if item.get(field) not in allowed:
                bag.add("memory_items", "critical", loc, f"{field} 非法: {item.get(field)}", f"使用受控 {field}", rule)
        if item.get("storage") == "repo" and item.get("sensitivity") in {"restricted", "secret"}:
            bag.add("privacy_policy", "critical", loc, "受限/密钥级内容不得进入随仓库传播的 .light", "仅保存仓库外安全位置的非敏感指针", "RESTRICTED_OR_SECRET_IN_REPO_LEDGER")
        if item.get("storage") == "repo" and item.get("scope") == "private_user":
            bag.add("privacy_policy", "critical", loc, "private_user scope 不得写入公开产品仓库台账", "保留在用户私有记忆或仓库外", "PRIVATE_SCOPE_IN_PUBLIC_REPO")
        value = str(item.get("value") or "")
        if SECRET_RE.search(value):
            bag.add("privacy_policy", "critical", loc, "疑似密钥/令牌值进入 memory item", "只记录变量名或外部安全位置，不记录值", "SECRET_VALUE_IN_MEMORY")
        if item.get("contains_full_conversation") is True:
            bag.add("privacy_policy", "critical", loc, "memory item 含完整对话文本", "默认只存最小项目摘要、证据 locator 和下一步", "FULL_CONVERSATION_CAPTURED")
        _repo_privacy_checks(item, bag, loc)
        if item.get("status") in {"deleted", "tombstone"} and value:
            bag.add("memory_items", "critical", loc, "deleted/tombstone 条目仍保留 value", "清空 value，仅留 tombstone 元数据", "TOMBSTONE_VALUE_RETAINED")
        if item.get("retention_until") and not _time(item.get("retention_until")):
            bag.add("memory_items", "critical", loc, "retention_until 不是带时区 ISO-8601", "写带时区时间或删除该字段", "RETENTION_TIME_INVALID")
        if ready and item.get("status") == "active" and item.get("layer") == "session_summary" and not item.get("source_locator"):
            bag.add("memory_items", "major", loc, "active session_summary 缺 source_locator", "绑定 handoff/resume/report locator，避免聊天记忆漂移", "SESSION_SUMMARY_LOCATOR_MISSING")
        if item.get("supersedes") and item.get("supersedes") not in by_id:
            # Second pass below catches forward refs; keep here only for empty strings.
            pass
    for item_id, item in by_id.items():
        parent = item.get("supersedes")
        if parent and parent not in by_id:
            bag.add("memory_items", "critical", item_id, f"supersedes 指向不存在条目 {parent}", "保留完整替代链或移除错误指针", "DANGLING_SUPERSEDES")
        if parent and by_id[parent].get("status") != "superseded":
            bag.add("memory_items", "critical", item_id, f"被 supersede 的旧条目 {parent} 未标 superseded", "旧条目标 superseded，新条目写 supersedes", "SUPERSEDED_STATE_MISMATCH")
    return by_id


def _artifacts(items: dict[str, dict[str, Any]], bag: Bag, ready: bool) -> None:
    for item_id, item in items.items():
        if item.get("layer") != "artifact_version":
            continue
        if not _real(item.get("artifact_path")):
            bag.add("artifact_versions", "critical", item_id, "artifact_version 缺 artifact_path", "绑定实际产物路径", "ARTIFACT_PATH_MISSING")
        if not _sha(item.get("artifact_sha256")):
            bag.add("artifact_versions", "critical", item_id, "artifact_version 缺真实 SHA-256", "绑定 sha256:<64 hex>", "ARTIFACT_HASH_MISSING")
        if ready and item.get("status") == "active" and item.get("superseded_by"):
            bag.add("artifact_versions", "critical", item_id, "active artifact_version 却声明 superseded_by", "更新状态为 superseded 或移除 superseded_by", "ARTIFACT_VERSION_STATE_CONFLICT")


def _failures(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    index = spec.get("failure_index") or []
    attempts = spec.get("attempts") or []
    failures_by_sig: dict[str, list[dict[str, Any]]] = {}
    for failure in index:
        fid = str(failure.get("failure_id") or "failure")
        state = str(failure.get("status") or "unresolved")
        if state not in FAILURE_STATES:
            bag.add("failure_index", "critical", fid, f"failure status 非法: {state}", "使用 unresolved/resolved/superseded/won_t_retry", "FAILURE_STATUS_INVALID")
        sig = str(failure.get("signature") or "")
        if not sig:
            bag.add("failure_index", "critical", fid, "failure 缺 signature", "用 root-cause + artifact + error code 形成稳定签名", "FAILURE_SIGNATURE_MISSING")
        failures_by_sig.setdefault(sig, []).append(failure)
        if state == "resolved" and not _real(failure.get("resolution_locator")):
            bag.add("failure_index", "major", fid, "resolved failure 缺 resolution_locator", "绑定修复记录/commit/test locator", "FAILURE_RESOLUTION_LOCATOR_MISSING")
    unresolved = {
        sig: rows for sig, rows in failures_by_sig.items()
        if sig and any(str(row.get("status") or "") == "unresolved" for row in rows)
    }
    for attempt in attempts:
        aid = str(attempt.get("attempt_id") or "attempt")
        sig = str(attempt.get("failure_signature") or "")
        if sig in unresolved and not _real(attempt.get("new_mitigation")) and attempt.get("user_override") is not True:
            bag.add("failure_index", "critical", aid, "计划重复旧失败但无新 mitigation 或用户 override", "先读 failure index，改变策略或让用户确认带病重试", "REPEATED_FAILURE_WITHOUT_MITIGATION")
        if ready and attempt.get("repeats_previous") is True and not _real(attempt.get("difference_from_previous")):
            bag.add("failure_index", "critical", aid, "重试标记 repeats_previous 但未说明差异", "写明新数据/新参数/新证据/新假设", "RETRY_DIFFERENCE_MISSING")


def _forks(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    forks = spec.get("fork_comparisons") or []
    if not isinstance(forks, list):
        raise ValueError("fork_comparisons 必须是 list")
    seen_forks: set[str] = set()
    for fork in forks:
        fork_id = str(fork.get("fork_id") or "")
        loc = fork_id or "fork_comparison"
        if not fork_id:
            bag.add("fork_comparisons", "critical", loc, "fork comparison 缺 fork_id", "给比较稳定 ID", "FORK_ID_MISSING")
        elif fork_id in seen_forks:
            bag.add("fork_comparisons", "critical", loc, "fork_id 重复", "合并或重命名比较", "FORK_ID_DUPLICATE")
        seen_forks.add(fork_id)
        if fork.get("status") not in FORK_STATES:
            bag.add("fork_comparisons", "critical", loc, f"fork status 非法: {fork.get('status')}", "使用 PLANNED/RUNNING/COMPARED/MERGED/ABANDONED", "FORK_STATUS_INVALID")
        for field, rule in (
            ("parent_session_id", "FORK_PARENT_MISSING"),
            ("divergence_reason", "FORK_DIVERGENCE_REASON_MISSING"),
        ):
            if not _real(fork.get(field)):
                bag.add("fork_comparisons", "critical", f"{loc}.{field}", f"{field} 缺失或占位", "记录分叉共同祖先和分叉理由", rule)
        if not _sha(fork.get("base_artifact_sha256")):
            bag.add("fork_comparisons", "critical", f"{loc}.base_artifact_sha256", "fork 缺共同祖先 artifact SHA-256", "绑定分叉前共同 artifact 内容哈希", "FORK_BASE_HASH_MISSING")
        criteria = fork.get("comparison_criteria") or []
        if not isinstance(criteria, list) or not criteria or any(not _real(value) for value in criteria):
            bag.add("fork_comparisons", "critical", f"{loc}.comparison_criteria", "比较准则缺失或含占位", "分叉前冻结可判定的比较准则", "FORK_CRITERIA_MISSING")
        branches = fork.get("branches") or []
        if not isinstance(branches, list) or len(branches) < 2:
            bag.add("fork_comparisons", "critical", f"{loc}.branches", "fork comparison 少于两条分支", "至少记录两个可比较分支", "FORK_BRANCHES_INSUFFICIENT")
            branches = []
        seen_branches: set[str] = set()
        for branch in branches:
            branch_id = str(branch.get("branch_id") or "")
            branch_loc = f"{loc}.branches.{branch_id or 'branch'}"
            if not branch_id or branch_id in seen_branches:
                bag.add("fork_comparisons", "critical", branch_loc, "branch_id 缺失或重复", "给每条分支唯一 ID", "FORK_BRANCH_ID_INVALID")
            seen_branches.add(branch_id)
            if not _sha(branch.get("input_sha256")):
                bag.add("fork_comparisons", "critical", f"{branch_loc}.input_sha256", "分支缺输入 SHA-256", "绑定实际分支输入，暴露不可比输入", "FORK_BRANCH_INPUT_HASH_MISSING")
            if fork.get("status") in {"COMPARED", "MERGED"}:
                if not _real(branch.get("outcome_locator")):
                    bag.add("fork_comparisons", "critical", f"{branch_loc}.outcome_locator", "已比较分支缺结果 locator", "绑定结果 artifact/run/report", "FORK_OUTCOME_MISSING")
                if not _sha(branch.get("outcome_sha256")):
                    bag.add("fork_comparisons", "critical", f"{branch_loc}.outcome_sha256", "已比较分支缺结果 SHA-256", "绑定结果内容哈希", "FORK_OUTCOME_HASH_MISSING")
        decision = fork.get("merge_decision") or {}
        if fork.get("status") == "MERGED":
            selected = str(decision.get("selected_branch_id") or "")
            if selected not in seen_branches:
                bag.add("fork_comparisons", "critical", f"{loc}.merge_decision.selected_branch_id", "merge 选择指向不存在分支", "选择已登记 branch_id", "FORK_SELECTED_BRANCH_INVALID")
            for field, rule in (
                ("rationale", "FORK_MERGE_RATIONALE_MISSING"),
                ("evidence_locator", "FORK_MERGE_EVIDENCE_MISSING"),
                ("user_decision_locator", "FORK_USER_DECISION_MISSING"),
            ):
                if not _real(decision.get(field)):
                    bag.add("fork_comparisons", "critical", f"{loc}.merge_decision.{field}", f"MERGED 缺 {field}", "保留证据、理由和用户最终选择", rule)
        if ready and fork.get("comparison_claim") and fork.get("status") not in {"COMPARED", "MERGED"}:
            bag.add("fork_comparisons", "critical", f"{loc}.comparison_claim", "尚未完成比较却输出路线优劣 claim", "先完成两分支证据或移除比较结论", "FORK_PREMATURE_COMPARISON_CLAIM")


def _policy(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    policy = spec.get("repository_policy") or {}
    if ready and policy.get("public_product") is not True:
        bag.add("privacy_policy", "major", "repository_policy.public_product", "未声明这是公开产品仓库", "公开技能包默认 public_product=true", "PUBLIC_PRODUCT_POLICY_MISSING")
    if policy.get("default_capture") not in {"minimal_summary_only", "explicit_user_approved"}:
        bag.add("privacy_policy", "critical", "repository_policy.default_capture", "default_capture 过宽或未声明", "默认只采集最小项目摘要；完整对话不进仓库", "DEFAULT_CAPTURE_POLICY_UNSAFE")
    if policy.get("full_conversation_allowed") is True:
        bag.add("privacy_policy", "critical", "repository_policy.full_conversation_allowed", "仓库台账允许完整对话采集", "改为 false；只存必要项目状态与 locator", "FULL_CONVERSATION_POLICY_ALLOWED")


def evaluate(spec: dict[str, Any], base: pathlib.Path | None = None) -> FindingsReport:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    base = base or pathlib.Path.cwd()
    ready = str((spec.get("package") or {}).get("status") or "DRAFT") in PACKAGE_READY
    bag = Bag()
    _resume(spec, bag, ready, base)
    items = _items(spec, bag, ready)
    _artifacts(items, bag, ready)
    _failures(spec, bag, ready)
    _forks(spec, bag, ready)
    _policy(spec, bag, ready)
    return FindingsReport(
        producer="memory-pm",
        target=str((spec.get("package") or {}).get("target") or "memory-governance"),
        gates=bag.gates(),
        summary=(
            "核 resume hash、memory item scope/sensitivity/reversibility、artifact version、"
            "failure index、fork comparison 与仓库采集策略；不存完整聊天内容。"
        ),
        fresh_evidence=True,
    ).finalize()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("input must be JSON object")
    return value


def _selftest() -> int:
    import tempfile
    import shutil

    if passport is None:
        raise AssertionError("passport import failed")
    root = pathlib.Path(tempfile.mkdtemp(prefix="memory_gov_", dir=str(_e2e_selftest_dir())))
    try:
        pp = root / ".light" / "passport.yaml"
        data = {
            "schema": "light.passport.v3", "project": "memory-gov", "pipeline": "A",
            "created": "2026-07-04T00:00", "updated": "2026-07-04T00:00",
            "current_stage": 8, "state_revision": 0, "state_hash": "sha256:" + "0" * 64,
            "evidence_state": "OBSERVED", "next_action": "continue",
            "delivery_status": "IN_PROGRESS", "delivery_authorization_id": None,
            "stages": [{"stage": 8, "skill": "paper-writing", "status": "in_progress"}],
        }
        passport.save(str(pp), data)
        computed = passport.compute_state_hash(passport.load(str(pp)))
        good = {
            "schema": SCHEMA_ID,
            "package": {"status": "RESUME_READY", "target": "selftest"},
            "repository_policy": {
                "public_product": True,
                "default_capture": "minimal_summary_only",
                "full_conversation_allowed": False,
            },
            "resume": {
                "passport": {"path": str(pp), "expected_current_stage": 8},
                "handoff": {"state_hash": computed, "artifact_sha256": "a" * 64},
                "summary": {"passport_state_hash": computed, "source": "pm.py resume"},
            },
            "memory_items": [
                {
                    "id": "sum-1", "layer": "session_summary", "status": "active",
                    "scope": "project", "sensitivity": "internal", "reversibility": "reversible",
                    "storage": "repo", "value": "stage 8 in progress", "source_locator": "handoff:S01",
                },
                {
                    "id": "art-1", "layer": "artifact_version", "status": "active",
                    "scope": "project", "sensitivity": "public", "reversibility": "reversible",
                    "storage": "repo", "value": "paper draft", "artifact_path": "paper.md",
                    "artifact_sha256": "sha256:" + "b" * 64,
                },
            ],
            "failure_index": [{
                "failure_id": "fail-1", "signature": "ruff:E501:paper", "status": "resolved",
                "resolution_locator": "commit:abc",
            }],
            "attempts": [],
            "fork_comparisons": [{
                "fork_id": "fork-1",
                "status": "MERGED",
                "parent_session_id": "S01",
                "base_artifact_sha256": "sha256:" + "c" * 64,
                "divergence_reason": "compare two analysis strategies",
                "comparison_criteria": ["held-out error", "runtime"],
                "branches": [
                    {
                        "branch_id": "robust",
                        "input_sha256": "sha256:" + "d" * 64,
                        "outcome_locator": "runs/robust.json",
                        "outcome_sha256": "sha256:" + "e" * 64,
                    },
                    {
                        "branch_id": "simple",
                        "input_sha256": "sha256:" + "d" * 64,
                        "outcome_locator": "runs/simple.json",
                        "outcome_sha256": "sha256:" + "f" * 64,
                    },
                ],
                "merge_decision": {
                    "selected_branch_id": "robust",
                    "rationale": "lower held-out error within runtime budget",
                    "evidence_locator": "reports/fork-1.md",
                    "user_decision_locator": "decision_log.md#fork-1",
                },
            }],
        }
        assert evaluate(good, root).verdict == "pass"
        bad = json.loads(json.dumps(good))
        bad["resume"]["handoff"]["state_hash"] = "sha256:" + "1" * 64
        bad["resume"]["summary"]["source"] = "chat_history_only"
        bad["repository_policy"]["default_capture"] = "full_conversation"
        bad["repository_policy"]["full_conversation_allowed"] = True
        bad["memory_items"][0].update({
            "scope": "private_user", "sensitivity": "restricted",
            "contains_full_conversation": True,
            "value": "token=abc123456789xyz",
        })
        bad["memory_items"].append({
            "id": "repo-privacy",
            "layer": "session_summary",
            "status": "active",
            "scope": "project",
            "sensitivity": "internal",
            "reversibility": "reversible",
            "storage": "repo",
            "source_locator": "handoff:S01#raw",
            "value": (
                "用户: 继续\n助手: 好的。联系人 light@example.com；"
                "原始文件 D:\\Users\\Light\\secret\\raw.xlsx。" + "x" * (MAX_REPO_VALUE_CHARS + 1)
            ),
        })
        bad["memory_items"][1]["artifact_sha256"] = "bad"
        bad["memory_items"].append({
            "id": "old", "layer": "fact", "status": "active", "scope": "project",
            "sensitivity": "internal", "reversibility": "reversible", "storage": "repo",
            "value": "old fact",
        })
        bad["memory_items"].append({
            "id": "new", "layer": "fact", "status": "active", "scope": "project",
            "sensitivity": "internal", "reversibility": "reversible", "storage": "repo",
            "value": "new fact", "supersedes": "old",
        })
        bad["failure_index"] = [{"failure_id": "fail-2", "signature": "same-error", "status": "unresolved"}]
        bad["attempts"] = [{"attempt_id": "retry-1", "failure_signature": "same-error", "repeats_previous": True}]
        bad["fork_comparisons"][0].update({
            "status": "MERGED",
            "base_artifact_sha256": "unknown",
            "comparison_criteria": [],
            "comparison_claim": "robust is better",
        })
        bad["fork_comparisons"][0]["branches"][1].update({
            "branch_id": "robust",
            "outcome_locator": None,
            "outcome_sha256": "unknown",
        })
        bad["fork_comparisons"][0]["merge_decision"] = {
            "selected_branch_id": "missing",
            "rationale": None,
            "evidence_locator": None,
            "user_decision_locator": None,
        }
        report = evaluate(bad, root)
        assert report.verdict == "fail", report.to_json()
        rules = {finding.rule for gate in report.gates for finding in gate.findings}
        assert {
            "HANDOFF_HASH_STALE", "RESUME_NOT_LEDGER_BOUND", "RESTRICTED_OR_SECRET_IN_REPO_LEDGER",
            "PRIVATE_SCOPE_IN_PUBLIC_REPO", "SECRET_VALUE_IN_MEMORY", "FULL_CONVERSATION_CAPTURED",
            "ARTIFACT_HASH_MISSING", "SUPERSEDED_STATE_MISMATCH", "REPEATED_FAILURE_WITHOUT_MITIGATION",
            "RETRY_DIFFERENCE_MISSING", "DEFAULT_CAPTURE_POLICY_UNSAFE", "FULL_CONVERSATION_POLICY_ALLOWED",
            "FORK_BASE_HASH_MISSING", "FORK_CRITERIA_MISSING", "FORK_BRANCH_ID_INVALID",
            "FORK_OUTCOME_MISSING", "FORK_OUTCOME_HASH_MISSING", "FORK_SELECTED_BRANCH_INVALID",
            "FORK_MERGE_RATIONALE_MISSING", "FORK_MERGE_EVIDENCE_MISSING", "FORK_USER_DECISION_MISSING",
            "REPO_MEMORY_VALUE_TOO_LONG", "RAW_DIALOGUE_OR_FULL_CHAT_IN_REPO",
            "EMAIL_OR_CONTACT_IN_REPO_MEMORY", "LOCAL_ABSOLUTE_PATH_IN_REPO_MEMORY",
        } <= rules
        print("memory_governance_gate selftest PASS: resume/items/artifacts/failures/forks/policy")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--input")
    parser.add_argument("--base", default=".")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    report = evaluate(read_json(pathlib.Path(args.input)), pathlib.Path(args.base).resolve())
    print(report.to_json())
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
