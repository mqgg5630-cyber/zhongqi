#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiment_execution_contract.py — stage 6 的 experiment spec / run status / repro level gate。

Round3 目标：把“实验准备好了/跑完了/能恢复/可复现到什么层级/远程执行是否获批”从聊天判断
变成可执行契约。它补现有 `repro_gate.py` 与 `run_artifact_check.py` 之间的空洞：

- `experiment_spec.v1`：冻结 scope/evaluator/budget/matrix/DAG；
- `run_status.v1`：区分 running/completed/failed/aborted/partial/resumable 与 OOM/timeout/preempted；
- `repro_level.v1`：same-env、clean-env、cross-platform、independent reimplementation 分层；
- `remote_execution`：远程/付费/HPC 执行必须先生成 plan，并停在用户授权门。

本脚本输出 `light.findings.v1`（producer=experiment-coding）。UNKNOWN 不冒充通过；completed 必须
是 natural_exit+exit 0+completion PASS；partial/resumable 必须有 checkpoint+resume command；
远程/付费 RUN_READY 必须 user_authorization=APPROVED。
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
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA_ID = "light.experiment_execution_contract.v1"
REPORT_SCHEMA_ID = "light.experiment_execution_contract.report.v1"
RUN_STATUSES = {"NOT_STARTED", "RUNNING", "COMPLETED", "FAILED", "ABORTED", "PARTIAL", "RESUMABLE", "UNKNOWN"}
TERMINATION_REASONS = {
    "NONE", "NATURAL_EXIT", "ERROR", "OOM", "TIMEOUT", "PREEMPTED", "USER_CANCEL", "MAX_ITERATIONS", "UNKNOWN",
}
FAILURE_CLASSES = {
    "NONE", "OOM", "TIMEOUT", "NUMERICAL", "RANDOM_FAILURE", "CACHE_CONTAMINATION",
    "ENV_MISMATCH", "DATA_MISSING", "CODE_BUG", "USER_CANCEL", "PREEMPTED", "UNKNOWN",
}
REPRO_LEVELS = {
    "SAME_ENV_REPEAT",
    "CLEAN_ENV_RERUN",
    "CROSS_PLATFORM",
    "INDEPENDENT_REIMPLEMENTATION",
}
LEVEL_ORDER = [
    "SAME_ENV_REPEAT",
    "CLEAN_ENV_RERUN",
    "CROSS_PLATFORM",
    "INDEPENDENT_REIMPLEMENTATION",
]
LEVEL_STATUS = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
AUTH_STATUSES = {"NOT_REQUIRED", "REQUESTED", "APPROVED", "DENIED", "UNKNOWN"}
DECISIONS = {"RUN_READY", "RUN_WITH_LIMITATIONS", "NOT_READY", "UNKNOWN"}
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SHA256_REF_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
PLACEHOLDER_RE = re.compile(r"^\s*(\{\{.*\}\}|TODO|TBD|待填|待定|[-—–]|n/?a|unknown|)\s*$", re.I)
MAX_CLOCK_SKEW = dt.timedelta(minutes=5)


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "_shared" / "__init__.py").exists():
            return parent
    raise RuntimeError("cannot locate repository root containing _shared")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402


def _status(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64_RE.match(value.strip()))


def _is_sha256_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_REF_RE.match(value.strip()))


def _real_text(value: Any) -> bool:
    return isinstance(value, str) and not PLACEHOLDER_RE.match(value)


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _resolve_as_of(spec: dict[str, Any]) -> dt.datetime:
    parsed = _parse_time(spec.get("as_of"))
    if parsed is not None:
        return parsed
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _future_time(value: Any, as_of: dt.datetime) -> bool:
    parsed = _parse_time(value)
    return parsed is not None and parsed > as_of + MAX_CLOCK_SKEW


def _finding(loc: str, issue: str, fix: str, rule: str, evidence: str = "") -> Finding:
    return Finding(loc=loc, issue=issue, fix=fix, evidence=evidence or None, rule=rule)


def _require_fields(obj: dict[str, Any], fields: list[str], loc: str, rule: str) -> list[Finding]:
    missing = [name for name in fields if obj.get(name) in (None, "", [], {})]
    if not missing:
        return []
    return [_finding(
        loc,
        f"缺少必填字段：{missing}；实验执行契约不能靠口头补齐",
        "补齐字段；未知就写 UNKNOWN，不得默认为 ready/completed",
        rule,
        ",".join(missing),
    )]


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spec_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    exp = spec.get("experiment_spec") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:experiment_spec"

    if spec.get("as_of") and _parse_time(spec.get("as_of")) is None:
        findings.append(_finding(
            f"{project}:as_of",
            "as_of 不是带时区 ISO-8601；无法判断冻结/授权时间是否来自未来",
            "使用带时区时间，例如 2026-07-04T12:00:00+08:00；缺省时脚本使用当前运行时间",
            "experiment_spec.as_of_bad_timestamp",
            str(spec.get("as_of")),
        ))

    findings.extend(_require_fields(
        exp,
        ["spec_id", "frozen_at", "source_plan_locator", "plan_sha256",
         "question_id", "estimand_id", "evaluator_id", "budget", "matrix_rows", "dag_nodes"],
        loc,
        "experiment_spec.required_missing",
    ))
    if exp.get("plan_sha256") and not _is_hex64(exp.get("plan_sha256")):
        findings.append(_finding(loc, "plan_sha256 不是 64 位 SHA256", "对冻结 research-plan/target chain 计算 SHA256", "experiment_spec.bad_hash"))
    if exp.get("frozen_at") and _parse_time(exp.get("frozen_at")) is None:
        findings.append(_finding(loc, "frozen_at 不是带时区 ISO-8601", "用带时区时间记录冻结点", "experiment_spec.bad_timestamp"))
    elif _future_time(exp.get("frozen_at"), as_of):
        findings.append(_finding(
            loc,
            "frozen_at 晚于 gate 的 as_of；实验方案冻结时间不能来自未来",
            "写实际冻结 research-plan/experiment matrix 的时间；尚未冻结时不得 RUN_READY",
            "experiment_spec.future_frozen_at",
            str(exp.get("frozen_at")),
        ))

    budget = exp.get("budget") or {}
    if isinstance(budget, dict):
        for key in ("max_walltime_minutes", "max_compute_units"):
            if not _positive_number(budget.get(key)):
                findings.append(_finding(f"{loc}.budget.{key}", f"{key} 必须为正数", "补真实预算上限，防止无界运行", "budget.bad_limit"))
        cost_limit = _number(budget.get("max_cost_usd"))
        if budget.get("max_cost_usd") is not None and cost_limit is None:
            findings.append(_finding(f"{loc}.budget.max_cost_usd", "max_cost_usd 必须是数字或 null", "未知先写 null；不得用字符串冒充数值", "budget.bad_cost"))
        elif cost_limit is not None and cost_limit < 0:
            findings.append(_finding(f"{loc}.budget.max_cost_usd", "max_cost_usd 不得为负", "补真实成本上限；免费写 0", "budget.bad_cost"))

    failure_tree = exp.get("failure_tree") or {}
    requires_guardrails = True
    if not isinstance(failure_tree, dict) or not failure_tree:
        findings.append(_finding(
            f"{loc}.failure_tree",
            "缺 failure_tree handoff；实验执行端没有绑定 research-plan 的失败/无结论/guardrail 决策树",
            "先运行 research-plan failure_tree_gate.py，并在 experiment_spec.failure_tree 写 report_locator、report_sha256、status 与 warning_decisions",
            "failure_tree.missing",
        ))
        failure_tree = {}
    else:
        requires_guardrails = failure_tree.get("requires_guardrails", True) is not False
        for key in ("report_locator", "report_sha256", "status"):
            if not _real_text(failure_tree.get(key)):
                findings.append(_finding(
                    f"{loc}.failure_tree.{key}",
                    f"failure_tree 缺 {key} 或仍是模板/unknown",
                    "绑定 .light/failure_tree_report.json 的 locator、SHA256 与 PASS/WARN 状态",
                    "failure_tree.required_missing",
                ))
        if failure_tree.get("report_sha256") and not _is_sha256_ref(failure_tree.get("report_sha256")):
            findings.append(_finding(
                f"{loc}.failure_tree.report_sha256",
                "failure_tree report_sha256 不是 sha256:<64 hex> 或 64 位 hex",
                "对 failure_tree_report.json 计算 SHA256，防止执行端消费漂移报告",
                "failure_tree.bad_hash",
            ))
        ft_status = _status(failure_tree.get("status"))
        if ft_status == "FAIL":
            findings.append(_finding(
                f"{loc}.failure_tree.status",
                "failure_tree_report status=FAIL；成功/失败/无结论或 guardrail 未闭合",
                "回 research-plan 修 failure-tree，不能把未闭合计划交给实验执行",
                "failure_tree.report_failed",
            ))
        elif ft_status == "WARN":
            decisions = failure_tree.get("warning_decisions")
            if not isinstance(decisions, list) or not decisions:
                findings.append(_finding(
                    f"{loc}.failure_tree.warning_decisions",
                    "failure_tree_report status=WARN 但缺 warning_decisions",
                    "写明如何降 claim/补实验/用户授权，否则不得 RUN_READY",
                    "failure_tree.warn_without_decision",
                ))
            else:
                warn.append(_finding(
                    f"{loc}.failure_tree",
                    "failure_tree_report status=WARN；执行只能 RUN_WITH_LIMITATIONS",
                    "保留 warning_decisions，并在 result-analysis/paper-writing 降 claim",
                    "failure_tree.warn_with_decision",
                ))
        elif ft_status != "PASS":
            findings.append(_finding(
                f"{loc}.failure_tree.status",
                f"failure_tree status={ft_status!r} 非 PASS/WARN/FAIL",
                "使用 research-plan failure_tree_gate.py 的真实报告状态",
                "failure_tree.bad_status",
            ))

    rows = exp.get("matrix_rows") if isinstance(exp.get("matrix_rows"), list) else []
    row_ids: set[str] = set()
    if not rows:
        findings.append(_finding(f"{loc}.matrix_rows", "matrix_rows 为空；没有可执行实验单元", "从 research-plan experiment matrix 逐行落配置", "matrix.empty"))
    for idx, row in enumerate(rows):
        rloc = f"{loc}.matrix_rows[{idx}]"
        if not isinstance(row, dict):
            findings.append(_finding(rloc, "matrix row 必须是 object", "改成结构化 row", "matrix.bad_row"))
            continue
        findings.extend(_require_fields(
            row,
            ["row_id", "config_id", "dataset_id", "split_id", "evaluator_id", "expected_outputs"],
            rloc,
            "matrix.row_missing",
        ))
        rid = str(row.get("row_id") or "")
        if rid in row_ids:
            findings.append(_finding(rloc, f"row_id={rid!r} 重复", "每个 matrix row 需要稳定唯一 ID", "matrix.duplicate_row"))
        row_ids.add(rid)
        if not isinstance(row.get("expected_outputs"), list) or not row.get("expected_outputs"):
            findings.append(_finding(rloc, "expected_outputs 必须是非空列表", "列出 raw_metrics/predictions/test_evidence/failure 等产物", "matrix.outputs_missing"))
        refs = row.get("failure_tree_refs")
        if not isinstance(refs, dict):
            findings.append(_finding(
                f"{rloc}.failure_tree_refs",
                "matrix row 缺 failure_tree_refs；不知道本 run 该监控哪条 hypothesis/guardrail/失败动作",
                "写 hypothesis_ids、branch_action_ids，以及适用时 guardrail_ids",
                "matrix.failure_tree_refs_missing",
            ))
        else:
            for key in ("hypothesis_ids", "branch_action_ids"):
                if not isinstance(refs.get(key), list) or not refs.get(key):
                    findings.append(_finding(
                        f"{rloc}.failure_tree_refs.{key}",
                        f"failure_tree_refs.{key} 必须是非空列表",
                        "把 execution row 绑定到 research-plan failure-tree 的 hypothesis 和分支动作",
                        "matrix.failure_tree_refs_missing",
                    ))
            guardrail_ids = refs.get("guardrail_ids")
            if requires_guardrails and (not isinstance(guardrail_ids, list) or not guardrail_ids):
                findings.append(_finding(
                    f"{rloc}.failure_tree_refs.guardrail_ids",
                    "该计划要求 guardrails，但 matrix row 未绑定 guardrail_ids",
                    "列出本 run 必须计算/监控的 guardrail/counter-metric ID；无适用项需让 research-plan 改为 WARN 并授权",
                    "matrix.guardrail_refs_missing",
                ))

    nodes = exp.get("dag_nodes") if isinstance(exp.get("dag_nodes"), list) else []
    graph: dict[str, list[str]] = {}
    if not nodes:
        findings.append(_finding(f"{loc}.dag_nodes", "dag_nodes 为空；无法恢复实验执行顺序", "声明 data_prep/train/eval 等节点与依赖", "dag.empty"))
    for idx, node in enumerate(nodes):
        nloc = f"{loc}.dag_nodes[{idx}]"
        if not isinstance(node, dict):
            findings.append(_finding(nloc, "DAG node 必须是 object", "改成结构化 node", "dag.bad_node"))
            continue
        findings.extend(_require_fields(node, ["node_id", "kind", "produces"], nloc, "dag.node_missing"))
        if "depends_on" not in node:
            findings.append(_finding(
                nloc,
                "DAG node 缺 depends_on 字段；根节点也要显式写 []",
                "补 depends_on: [] 或依赖节点列表，便于恢复执行拓扑",
                "dag.depends_on_missing",
            ))
        nid = str(node.get("node_id") or "")
        deps = [str(x) for x in (node.get("depends_on") or [])]
        graph[nid] = deps
        if node.get("kind") in {"TRAIN", "EVAL"} and not node.get("command"):
            findings.append(_finding(nloc, f"{node.get('kind')} node 缺 command", "记录 argv 数组或命令 locator", "dag.command_missing"))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, stack: list[str]) -> None:
        if node_id in visiting:
            findings.append(_finding(
                f"{loc}.dag_nodes",
                f"实验 DAG 有环：{' -> '.join(stack + [node_id])}",
                "拆开依赖或修正 depends_on；有环 DAG 不能恢复/重跑",
                "dag.cycle",
            ))
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in graph.get(node_id, []):
            if dep and dep not in graph:
                findings.append(_finding(f"{loc}.dag_nodes", f"node {node_id} 依赖未知节点 {dep}", "补节点或修正 depends_on", "dag.unknown_dependency"))
            else:
                visit(dep, stack + [node_id])
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in list(graph):
        visit(node_id, [])

    if not exp.get("scope_freeze_note"):
        warn.append(_finding(
            loc,
            "缺 scope_freeze_note；实现阶段改 evaluator/budget/matrix 时读者难以判断是否越界",
            "写清允许变更与禁止变更；不可行时回 research-plan 让用户拍板",
            "scope.freeze_note_missing",
        ))

    if findings:
        return GateResult("experiment_spec", "fail", "critical", findings,
                          note="冻结 scope/evaluator/budget/matrix/DAG 不完整或有环 → 不能 RUN_READY。")
    if warn:
        return GateResult("experiment_spec", "warn", "major", warn,
                          note="实验 spec 可执行但 scope freeze 说明不足。")
    return GateResult("experiment_spec", "pass", "info", [], note="experiment spec 已冻结且 DAG 可恢复。")


def _run_status_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    exp = spec.get("experiment_spec") or {}
    run = spec.get("run_status") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:run_status"

    findings.extend(_require_fields(
        run,
        ["run_id", "matrix_row_id", "attempt", "status", "termination",
         "failure_class", "resources", "completion", "resume_semantics"],
        loc,
        "run_status.required_missing",
    ))
    status = _status(run.get("status"))
    failure_class = _status(run.get("failure_class"))
    if status and status not in RUN_STATUSES:
        findings.append(_finding(loc, f"run status={status!r} 非法", f"改为 {sorted(RUN_STATUSES)}", "run_status.bad_status"))
    if failure_class and failure_class not in FAILURE_CLASSES:
        findings.append(_finding(loc, f"failure_class={failure_class!r} 非法", f"改为 {sorted(FAILURE_CLASSES)}", "failure.bad_class"))
    attempt = run.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
        findings.append(_finding(loc, "attempt 必须是正整数", "每次重跑/恢复都用单调 attempt 记录，禁止覆盖旧 run", "run.attempt_bad"))
    row_ids = {
        str(row.get("row_id"))
        for row in (exp.get("matrix_rows") or [])
        if isinstance(row, dict) and row.get("row_id")
    }
    matrix_row_id = str(run.get("matrix_row_id") or "")
    if row_ids and matrix_row_id and matrix_row_id not in row_ids:
        findings.append(_finding(
            loc,
            f"run.matrix_row_id={matrix_row_id!r} 不在冻结 matrix_rows 中",
            "把 run 绑定到冻结 matrix row；新实验必须先修订 research-plan/experiment matrix",
            "run.matrix_row_unknown",
        ))

    termination = run.get("termination") or {}
    if isinstance(termination, dict):
        reason = _status(termination.get("reason"))
        exit_code = termination.get("exit_code")
        if reason and reason not in TERMINATION_REASONS:
            findings.append(_finding(f"{loc}.termination", f"termination.reason={reason!r} 非法", f"改为 {sorted(TERMINATION_REASONS)}", "termination.bad_reason"))
        if status == "COMPLETED" and not (reason == "NATURAL_EXIT" and exit_code == 0):
            findings.append(_finding(
                loc,
                f"status=COMPLETED 但 termination={reason}/exit_code={exit_code}；执行结束不等于任务完成",
                "只有 natural_exit + exit 0 + completion PASS 才能 completed；timeout/OOM/max_iter 必须 aborted/failed/partial",
                "run.completed_bad_termination",
            ))
        if reason in {"OOM", "TIMEOUT", "PREEMPTED", "MAX_ITERATIONS", "USER_CANCEL"} and status == "COMPLETED":
            findings.append(_finding(
                loc,
                f"{reason} 不能写成 COMPLETED",
                "按 ABORTED/PARTIAL/RESUMABLE/FAILED 记录，并保留 failure artifact",
                "run.failure_reason_marked_completed",
            ))

    completion = run.get("completion") or {}
    if isinstance(completion, dict):
        cstatus = _status(completion.get("status"))
        if status == "COMPLETED" and cstatus != "PASS":
            findings.append(_finding(
                f"{loc}.completion",
                f"status=COMPLETED 但 completion.status={cstatus!r} 不是 PASS",
                "completion oracle 通过前不能写 completed",
                "completion.not_pass_for_completed",
            ))
        if cstatus == "PASS" and not completion.get("evidence_artifacts"):
            findings.append(_finding(f"{loc}.completion", "completion PASS 缺 evidence_artifacts", "列出 raw_metrics/predictions/test_evidence 等证据", "completion.evidence_missing"))
        failure_tree = exp.get("failure_tree") if isinstance(exp, dict) else {}
        requires_guardrails = not isinstance(failure_tree, dict) or failure_tree.get("requires_guardrails", True) is not False
        if status == "COMPLETED" and cstatus == "PASS" and requires_guardrails:
            evidence = completion.get("evidence_artifacts") or []
            guardrail_evidence = completion.get("guardrail_evidence_artifacts") or []
            has_guardrail_evidence = (
                isinstance(guardrail_evidence, list) and bool(guardrail_evidence)
            ) or any("guardrail" in str(item).casefold() for item in evidence)
            if not has_guardrail_evidence:
                findings.append(_finding(
                    f"{loc}.completion.guardrail_evidence_artifacts",
                    "completed run 缺 guardrail evidence；执行端可能丢掉 research-plan 的守护指标/kill criterion",
                    "保存 guardrail_evidence_artifacts，或在 failure_tree 中声明 requires_guardrails=false 并走 warning/授权",
                    "completion.guardrail_evidence_missing",
                ))

    checkpoint = run.get("checkpoint") or {}
    resume = run.get("resume_semantics") or {}
    if status in {"PARTIAL", "RESUMABLE"}:
        if not isinstance(checkpoint, dict) or _status(checkpoint.get("status")) != "PARTIAL":
            findings.append(_finding(f"{loc}.checkpoint", f"status={status} 但 checkpoint.status 不是 PARTIAL", "登记 checkpoint locator/SHA/resume command", "resume.checkpoint_missing"))
        else:
            if not checkpoint.get("locator") or not _is_hex64(checkpoint.get("sha256")):
                findings.append(_finding(f"{loc}.checkpoint", "partial/resumable 缺 checkpoint locator 或有效 SHA256", "补 checkpoint 文件/目录 manifest 与 SHA256", "resume.checkpoint_hash_missing"))
            if not checkpoint.get("resume_command"):
                findings.append(_finding(f"{loc}.checkpoint", "partial/resumable 缺 resume_command", "补可重启 argv；不能只写“继续跑”", "resume.command_missing"))
        if not isinstance(resume, dict) or resume.get("safe_to_resume") is not True:
            findings.append(_finding(f"{loc}.resume_semantics", "partial/resumable 未声明 safe_to_resume=true", "说明恢复是否污染指标、是否需要 clean env/cache", "resume.safety_missing"))
    if status in {"FAILED", "ABORTED", "PARTIAL", "RESUMABLE"} and failure_class in {"", "NONE", "UNKNOWN"}:
        findings.append(_finding(loc, f"status={status} 但 failure_class={failure_class or 'missing'}", "分类 OOM/TIMEOUT/PREEMPTED/CODE_BUG/ENV_MISMATCH 等，供回炉定位", "failure.class_missing"))

    resources = run.get("resources") or {}
    if isinstance(resources, dict):
        for key in ("walltime_minutes", "cpu_hours", "gpu_hours", "memory_peak_gb", "storage_gb"):
            if resources.get(key) is None:
                warn.append(_finding(f"{loc}.resources.{key}", f"resources.{key} 缺失", "补资源/成本，供预算与复现实验估算", "resources.metric_missing"))
        cost_value = _number(resources.get("cost_usd"))
        if resources.get("cost_usd") is not None and cost_value is None:
            findings.append(_finding(
                f"{loc}.resources.cost_usd",
                "cost_usd 必须是数字或 null",
                "未知写 null 并保留 budget/coverage 缺口；不得用字符串 UNKNOWN 让脚本崩溃",
                "resources.bad_cost",
            ))
        elif cost_value is not None and cost_value < 0:
            findings.append(_finding(f"{loc}.resources.cost_usd", "cost_usd 不得为负", "免费写 0，未知写 null", "resources.bad_cost"))
        budget = exp.get("budget") if isinstance(exp, dict) else {}
        if isinstance(budget, dict):
            walltime_used = _number(resources.get("walltime_minutes"))
            walltime_limit = _number(budget.get("max_walltime_minutes"))
            if walltime_used is not None and walltime_limit is not None and walltime_used > walltime_limit:
                findings.append(_finding(
                    f"{loc}.resources.walltime_minutes",
                    f"walltime {walltime_used:g}min 超过冻结预算 {walltime_limit:g}min",
                    "停止扩大运行；回 research-plan/用户处修订预算或解释 overrun",
                    "budget.walltime_exceeded",
                ))
            cost_limit = _number(budget.get("max_cost_usd"))
            if cost_value is not None and cost_limit is not None and cost_value > cost_limit:
                findings.append(_finding(
                    f"{loc}.resources.cost_usd",
                    f"cost ${cost_value:g} 超过冻结预算 ${cost_limit:g}",
                    "停止付费扩跑；补预算授权或降级实验",
                    "budget.cost_exceeded",
                ))
            compute_used = _number(resources.get("compute_units_used"))
            compute_limit = _number(budget.get("max_compute_units"))
            if compute_used is not None and compute_limit is not None and compute_used > compute_limit:
                findings.append(_finding(
                    f"{loc}.resources.compute_units_used",
                    f"compute_units {compute_used:g} 超过冻结预算 {compute_limit:g}",
                    "补预算修订或减少运行；不得把超预算 run 标作 ready",
                    "budget.compute_exceeded",
                ))

    if findings:
        return GateResult("run_status", "fail", "critical", findings,
                          note="run status/termination/completion/resume/failure class 不一致 → 不能交给 result-analysis。")
    if warn:
        return GateResult("run_status", "warn", "major", warn,
                          note="运行可解释但资源/成本记录不足。")
    return GateResult("run_status", "pass", "info", [], note="run status、失败分类和 resume semantics 一致。")


def _environment_cache_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    env = spec.get("environment") or {}
    cache = spec.get("cache") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:environment"

    findings.extend(_require_fields(
        env,
        ["code_commit", "dirty", "env_lock_sha256", "package_lock_sha256",
         "python", "os", "random_seed"],
        loc,
        "environment.required_missing",
    ))
    for key in ("env_lock_sha256", "package_lock_sha256"):
        if env.get(key) and not _is_hex64(env.get(key)):
            findings.append(_finding(f"{loc}.{key}", f"{key} 不是 64 位 SHA256", "对 lock/环境导出计算 SHA256", "environment.bad_hash"))
    if env.get("dirty") is True and not _is_hex64(env.get("diff_sha256")):
        findings.append(_finding(loc, "dirty=true 但 diff_sha256 缺失/非法", "记录未提交 diff 的 SHA256；否则不可复现", "environment.dirty_without_diff_hash"))
    if env.get("random_seed") is None:
        findings.append(_finding(loc, "random_seed 缺失；同 seed 复现无锚点", "记录固定 seed 与 seed role", "environment.seed_missing"))

    enabled = bool(cache.get("enabled"))
    if enabled:
        for key in ("cache_policy", "cache_manifest_sha256", "isolation_strategy"):
            if not cache.get(key):
                findings.append(_finding(f"{project}:cache.{key}", f"cache.enabled=true 但 {key} 缺失", "缓存必须有 manifest/hash/隔离策略，防污染", "cache.required_missing"))
        if cache.get("cache_manifest_sha256") and not _is_hex64(cache.get("cache_manifest_sha256")):
            findings.append(_finding(f"{project}:cache.cache_manifest_sha256", "cache manifest hash 非法", "对缓存 manifest 计算 SHA256", "cache.bad_hash"))
        if _status(cache.get("contamination_check")) in {"", "UNKNOWN", "FAIL"}:
            findings.append(_finding(
                f"{project}:cache.contamination_check",
                f"cache contamination_check={cache.get('contamination_check')!r}；无法排除缓存污染",
                "清缓存重跑或记录 cache key/input hash；缓存污染是结果虚高常见根因",
                "cache.contamination_unresolved",
            ))
    else:
        warn.append(_finding(f"{project}:cache", "cache 未启用或未声明；若实际用了缓存，必须补 manifest", "不用缓存写 enabled=false；用了就登记", "cache.declaration_missing"))

    if findings:
        return GateResult("environment_cache", "fail", "critical", findings,
                          note="环境/dirty diff/cache 证据不足会破坏复现实验。")
    if warn:
        return GateResult("environment_cache", "warn", "major", warn,
                          note="环境可追溯，但 cache 声明需要确认。")
    return GateResult("environment_cache", "pass", "info", [], note="环境锁、dirty 状态和 cache 证据可追溯。")


def _repro_level_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    repro = spec.get("reproducibility") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:reproducibility"

    requested = _status(repro.get("requested_level"))
    if requested not in REPRO_LEVELS:
        findings.append(_finding(loc, f"requested_level={requested!r} 非法或缺失", f"改为 {sorted(REPRO_LEVELS)}", "repro.bad_requested_level"))
        requested_index = -1
    else:
        requested_index = LEVEL_ORDER.index(requested)
    levels = repro.get("levels") or {}
    if not isinstance(levels, dict):
        findings.append(_finding(loc, "reproducibility.levels 必须是 object", "逐级记录 PASS/FAIL/UNKNOWN", "repro.levels_bad_type"))
        levels = {}
    for idx, level in enumerate(LEVEL_ORDER):
        status = _status(levels.get(level))
        if status not in LEVEL_STATUS:
            findings.append(_finding(f"{loc}.levels.{level}", f"{level}={status!r} 非法/缺失", f"改为 {sorted(LEVEL_STATUS)}", "repro.level_bad_status"))
            continue
        if requested_index >= idx and status != "PASS":
            findings.append(_finding(
                f"{loc}.levels.{level}",
                f"请求 {requested}，但 {level}={status}；不能宣称达到请求复现层级",
                "补对应层级证据，或把 requested_level 降到已验证层级",
                "repro.requested_level_not_met",
            ))
        elif requested_index < idx and status == "UNKNOWN":
            warn.append(_finding(
                f"{loc}.levels.{level}",
                f"{level}=UNKNOWN；未验证更高复现层级",
                "如不宣称该层级可保持 UNKNOWN，但下游不得写跨平台/独立复现",
                "repro.higher_level_unknown",
            ))

    evidence = repro.get("evidence") or {}
    if requested in REPRO_LEVELS:
        key = requested.lower()
        if not evidence.get(key):
            findings.append(_finding(
                f"{loc}.evidence.{key}",
                f"requested_level={requested} 但缺对应 evidence locator",
                "写入同 seed 对比报告、clean env 重跑、跨平台报告或独立实现 locator",
                "repro.evidence_missing",
            ))

    same_seed_runs = repro.get("same_seed_runs") or []
    if same_seed_runs:
        for idx, pair in enumerate(same_seed_runs):
            ploc = f"{loc}.same_seed_runs[{idx}]"
            if not isinstance(pair, dict):
                findings.append(_finding(ploc, "same_seed run pair 必须是 object", "改成结构化 pair", "repro.pair_bad_type"))
                continue
            if pair.get("same_seed_exact") is not True:
                findings.append(_finding(ploc, "同 seed 两次 artifacts 不完全一致", "用 run_artifact_check.py --compare 定位 predictions/raw_metrics 差异", "repro.same_seed_mismatch"))
            if not pair.get("comparison_locator"):
                findings.append(_finding(ploc, "same_seed pair 缺 comparison_locator", "补 run_artifact_check --compare 输出", "repro.comparison_locator_missing"))

    if findings:
        return GateResult("repro_level", "fail", "critical", findings,
                          note="请求复现层级未由证据支撑，或 same-seed pair 不一致。")
    if warn:
        return GateResult("repro_level", "warn", "major", warn,
                          note="已满足请求层级，但更高层级未验证；不得过度宣称。")
    return GateResult("repro_level", "pass", "info", [], note="请求复现层级由证据支撑。")


def _remote_execution_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    exp = spec.get("experiment_spec") or {}
    remote = spec.get("remote_execution") or {}
    decision = _status(spec.get("decision"))
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:remote_execution"
    required = bool(remote.get("required"))
    paid = bool(remote.get("paid"))
    cost = remote.get("estimated_cost_usd")
    cost_value = _number(cost)
    cost_positive = cost_value is not None and cost_value > 0

    if required or paid or cost_positive:
        findings.extend(_require_fields(
            remote,
            ["provider", "plan_locator", "estimated_cost_usd", "cancel_command",
             "data_egress", "secrets_policy", "user_authorization"],
            loc,
            "remote.required_missing",
        ))
        auth = remote.get("user_authorization") or {}
        auth_status = _status(auth.get("status")) if isinstance(auth, dict) else "UNKNOWN"
        if auth_status not in AUTH_STATUSES:
            findings.append(_finding(loc, f"user_authorization.status={auth_status!r} 非法", f"改为 {sorted(AUTH_STATUSES)}", "remote.auth_bad_status"))
        if decision == "RUN_READY" and auth_status != "APPROVED":
            findings.append(_finding(
                loc,
                f"远程/付费执行未获 APPROVED（当前 {auth_status}）却声明 RUN_READY",
                "先把 plan/cost/cancel/data egress/secrets policy 给用户审批；未批前 NOT_READY/UNKNOWN",
                "remote.approval_required",
            ))
        if auth_status == "APPROVED":
            if not auth.get("approved_at") or _parse_time(auth.get("approved_at")) is None:
                findings.append(_finding(loc, "authorization APPROVED 但 approved_at 缺失或无时区", "补带时区批准时间", "remote.approved_at_missing"))
            elif _future_time(auth.get("approved_at"), as_of):
                findings.append(_finding(
                    loc,
                    "authorization approved_at 晚于 gate 的 as_of；远程/付费授权不能来自未来",
                    "写用户实际批准时间；尚未批准时保持 REQUESTED/NOT_READY",
                    "remote.future_approved_at",
                    str(auth.get("approved_at")),
                ))
            if not auth.get("scope"):
                findings.append(_finding(loc, "authorization APPROVED 但 scope 缺失", "写明批准的 provider/cost/data/run 范围", "remote.approval_scope_missing"))
        if cost is not None and cost_value is None:
            findings.append(_finding(
                loc,
                "estimated_cost_usd 必须是数字或 null",
                "未知成本不得 RUN_READY；补真实估算或把 decision 改为 NOT_READY/UNKNOWN",
                "remote.bad_estimated_cost",
            ))
        if cost_positive and not remote.get("budget_impact"):
            warn.append(_finding(loc, "estimated_cost_usd>0 但缺 budget_impact", "写明成本由谁承担、超预算如何停机", "remote.budget_impact_missing"))
        budget = exp.get("budget") if isinstance(exp, dict) else {}
        if isinstance(budget, dict):
            cost_limit = _number(budget.get("max_cost_usd"))
            if cost_limit is not None and cost_value is not None and cost_value > cost_limit:
                if not remote.get("budget_override_locator"):
                    findings.append(_finding(
                        loc,
                        f"estimated_cost_usd=${cost_value:g} 超过冻结预算 ${cost_limit:g}，但缺预算覆盖授权",
                        "补 budget_override_locator 或把 decision 改为 NOT_READY；不得静默扩付费预算",
                        "remote.cost_over_budget",
                    ))
    else:
        auth = remote.get("user_authorization") if isinstance(remote, dict) else None
        if auth and _status(auth.get("status")) not in {"NOT_REQUIRED", "APPROVED"}:
            warn.append(_finding(loc, "remote_execution 不需要但授权状态不是 NOT_REQUIRED/APPROVED", "统一状态，避免下游误以为待审批", "remote.unneeded_auth_state"))

    if findings:
        return GateResult("remote_execution_authorization", "fail", "critical", findings,
                          note="远程/付费/HPC 执行必须先有 plan + cost + cancel + data/secrets policy + 用户批准。")
    if warn:
        return GateResult("remote_execution_authorization", "warn", "major", warn,
                          note="远程执行授权通过/不需要，但预算影响说明不足。")
    return GateResult("remote_execution_authorization", "pass", "info", [],
                      note="远程/付费执行授权状态与 decision 一致。")


def _decision_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    decision = _status(spec.get("decision"))
    if decision not in DECISIONS:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(f"{project}:decision", f"decision={decision!r} 非法或缺失", f"改为 {sorted(DECISIONS)}", "decision.bad_status")
        ], note="必须明确 RUN_READY/NOT_READY/UNKNOWN。")
    blockers = [g for g in art["pre_decision_gates"] if g.status == "fail" and g.severity == "critical"]
    warners = [g for g in art["pre_decision_gates"] if g.status == "warn"]
    if decision in {"NOT_READY", "UNKNOWN"}:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(
                f"{project}:decision",
                f"decision={decision}；执行契约已声明未准备好或仍未知，流水线不得进入 result-analysis",
                "修复执行契约/补授权/重跑实验后再改为 RUN_READY 或 RUN_WITH_LIMITATIONS",
                "decision.blocks_advancement",
            )
        ], note="NOT_READY/UNKNOWN 是阻断性裁定，不是可推进状态。")
    if blockers and decision in {"RUN_READY", "RUN_WITH_LIMITATIONS"}:
        names = ",".join(g.gate for g in blockers)
        return GateResult("declared_decision", "fail", "critical", [
            _finding(f"{project}:decision", f"存在 critical blockers({names}) 却声明 {decision}", "改为 NOT_READY/UNKNOWN，或先修复 blockers", "decision.overrides_blockers", names)
        ], note="RUN_READY 不得覆盖硬阻断。")
    if warners and decision == "RUN_READY":
        names = ",".join(g.gate for g in warners)
        return GateResult("declared_decision", "warn", "major", [
            _finding(f"{project}:decision", f"存在 warn({names}) 但声明 RUN_READY", "改为 RUN_WITH_LIMITATIONS，或补齐限制证据", "decision.should_be_limited", names)
        ], note="有 warn 时应限制性 ready。")
    return GateResult("declared_decision", "pass", "info", [], note=f"decision={decision} 与前置 gate 一致。")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") not in (SCHEMA_ID, None):
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    project = str(spec.get("project") or "unknown-project")
    art = {"spec": spec, "project": project, "as_of": _resolve_as_of(spec)}
    pre = [
        _spec_gate(art),
        _run_status_gate(art),
        _environment_cache_gate(art),
        _repro_level_gate(art),
        _remote_execution_gate(art),
    ]
    art["pre_decision_gates"] = pre
    gates = pre + [_decision_gate(art)]
    report = FindingsReport(
        producer="experiment-coding",
        target=project,
        gates=gates,
        summary=("experiment execution contract: frozen scope/evaluator/budget/DAG + run status/"
                 "failure/resume + environment/cache + repro level + remote authorization"),
        fresh_evidence=True,
    ).finalize()
    blockers = report.blocking_gates()
    if blockers:
        status = "FAIL"
        advancement = "BLOCK"
    elif report.verdict == "warn":
        status = "WARN"
        advancement = "ALLOW_WITH_LIMITATIONS"
    else:
        status = "PASS"
        advancement = "ALLOW"
    return {
        "schema": REPORT_SCHEMA_ID,
        "project": project,
        "status": status,
        "advancement": advancement,
        "decision": _status(spec.get("decision")),
        "blocking_gates": [g.gate for g in blockers],
        "findings": report.to_dict(),
    }


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# experiment-coding execution contract：{result['project']}",
        "",
        f"- status: **{result['status']}**",
        f"- advancement: **{result['advancement']}**",
        f"- declared decision: `{result['decision']}`",
        "",
    ]
    if result["blocking_gates"]:
        lines.append(f"- blocking gates: {', '.join(result['blocking_gates'])}")
        lines.append("")
    lines.append("| gate | status | severity | findings |")
    lines.append("|---|---:|---:|---:|")
    for gate in result["findings"]["gates"]:
        lines.append(f"| {gate['gate']} | {gate['status']} | {gate['severity']} | {len(gate['findings'])} |")
    lines.append("")
    lines.append("> 诚实边界：PASS 只说明执行契约闭合；不证明科学假设成立、跨硬件 bitwise 复现或远程平台可无限制使用。")
    return "\n".join(lines)


def _h(char: str = "c") -> str:
    return char * 64


def _good_spec() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "project": "selftest-experiment",
        "experiment_spec": {
            "spec_id": "EXP-SPEC-1",
            "frozen_at": "2026-07-04T10:00:00+08:00",
            "source_plan_locator": "target-chain.json",
            "plan_sha256": _h(),
            "failure_tree": {
                "report_locator": ".light/failure_tree_report.json",
                "report_sha256": _h("f"),
                "status": "PASS",
                "requires_guardrails": True,
            },
            "question_id": "Q1",
            "estimand_id": "E1",
            "evaluator_id": "primary-evaluator",
            "scope_freeze_note": "Only bug fixes allowed; metric/evaluator changes require research-plan amendment.",
            "budget": {"max_walltime_minutes": 120, "max_compute_units": 2, "max_cost_usd": 0},
            "matrix_rows": [
                {
                    "row_id": "EXP-01",
                    "config_id": "cfg-a",
                    "dataset_id": "ds-v1",
                    "split_id": "split-v1",
                    "evaluator_id": "primary-evaluator",
                    "expected_outputs": ["raw_metrics", "predictions", "test_evidence"],
                    "failure_tree_refs": {
                        "hypothesis_ids": ["H1"],
                        "branch_action_ids": ["H1.success", "H1.failure", "H1.inconclusive"],
                        "guardrail_ids": ["G1"],
                    },
                }
            ],
            "dag_nodes": [
                {"node_id": "prep", "kind": "DATA_PREP", "depends_on": [], "produces": ["curated"]},
                {"node_id": "train", "kind": "TRAIN", "depends_on": ["prep"], "command": ["python", "train.py"], "produces": ["model"]},
                {"node_id": "eval", "kind": "EVAL", "depends_on": ["train"], "command": ["python", "eval.py"], "produces": ["raw_metrics", "predictions"]},
            ],
        },
        "run_status": {
            "run_id": "EXP-01-seed42-a",
            "matrix_row_id": "EXP-01",
            "attempt": 1,
            "status": "COMPLETED",
            "termination": {"reason": "NATURAL_EXIT", "exit_code": 0},
            "failure_class": "NONE",
            "completion": {
                "status": "PASS",
                "evidence_artifacts": ["raw_metrics", "predictions", "test_evidence", "guardrail_evidence"],
                "guardrail_evidence_artifacts": ["guardrails.json"],
            },
            "checkpoint": {"status": "NONE"},
            "resume_semantics": {"safe_to_resume": False, "reason": "completed"},
            "resources": {
                "walltime_minutes": 5,
                "cpu_hours": 0.2,
                "gpu_hours": 0,
                "compute_units_used": 1,
                "memory_peak_gb": 1.1,
                "storage_gb": 0.02,
                "cost_usd": 0,
            },
        },
        "environment": {
            "code_commit": "abc123",
            "dirty": False,
            "env_lock_sha256": _h("d"),
            "package_lock_sha256": _h("e"),
            "python": "3.11.9",
            "os": "Windows",
            "random_seed": 42,
        },
        "cache": {"enabled": False},
        "reproducibility": {
            "requested_level": "SAME_ENV_REPEAT",
            "levels": {
                "SAME_ENV_REPEAT": "PASS",
                "CLEAN_ENV_RERUN": "UNKNOWN",
                "CROSS_PLATFORM": "UNKNOWN",
                "INDEPENDENT_REIMPLEMENTATION": "UNKNOWN",
            },
            "evidence": {"same_env_repeat": "run_artifact_compare.json"},
            "same_seed_runs": [{"same_seed_exact": True, "comparison_locator": "run_artifact_compare.json"}],
        },
        "remote_execution": {"required": False, "paid": False, "user_authorization": {"status": "NOT_REQUIRED"}},
        "decision": "RUN_WITH_LIMITATIONS",
    }


def _selftest() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good = evaluate(_good_spec())
    check(good["status"] == "WARN" and good["advancement"] == "ALLOW_WITH_LIMITATIONS",
          f"good spec 有 higher repro UNKNOWN/cache declaration warn，应限制通过，得 {good['status']}")
    check(good["findings"]["schema"] == "light.findings.v1", "应产 light.findings.v1")
    check(good["findings"]["producer"] == "experiment-coding", "producer 应 experiment-coding")

    no_failure_tree = _good_spec()
    no_failure_tree["experiment_spec"].pop("failure_tree")
    rft0 = evaluate(no_failure_tree)
    check(rft0["status"] == "FAIL" and "experiment_spec" in rft0["blocking_gates"],
          "缺 failure_tree handoff 应阻断 RUN_READY/RUN_WITH_LIMITATIONS")

    warn_failure_tree = _good_spec()
    warn_failure_tree["experiment_spec"]["failure_tree"]["status"] = "WARN"
    rft1 = evaluate(warn_failure_tree)
    rules_ft1 = {
        finding["rule"]
        for gate in rft1["findings"]["gates"]
        for finding in gate["findings"]
    }
    check("failure_tree.warn_without_decision" in rules_ft1,
          "failure_tree WARN 但无 warning_decisions 应阻断")

    missing_guardrail_refs = _good_spec()
    missing_guardrail_refs["experiment_spec"]["matrix_rows"][0]["failure_tree_refs"]["guardrail_ids"] = []
    rft2 = evaluate(missing_guardrail_refs)
    check(rft2["status"] == "FAIL" and "experiment_spec" in rft2["blocking_gates"],
          "requires_guardrails=true 时 matrix row 缺 guardrail_ids 应阻断")

    missing_guardrail_evidence = _good_spec()
    missing_guardrail_evidence["run_status"]["completion"]["evidence_artifacts"] = ["raw_metrics", "predictions", "test_evidence"]
    missing_guardrail_evidence["run_status"]["completion"]["guardrail_evidence_artifacts"] = []
    rft3 = evaluate(missing_guardrail_evidence)
    check(rft3["status"] == "FAIL" and "run_status" in rft3["blocking_gates"],
          "completed run 缺 guardrail evidence 应阻断")

    completed_timeout = _good_spec()
    completed_timeout["run_status"]["termination"] = {"reason": "TIMEOUT", "exit_code": None}
    completed_timeout["run_status"]["failure_class"] = "TIMEOUT"
    completed_timeout["decision"] = "RUN_READY"
    r2 = evaluate(completed_timeout)
    check(r2["status"] == "FAIL" and "run_status" in r2["blocking_gates"],
          "TIMEOUT 不能标 COMPLETED")

    partial = _good_spec()
    partial["run_status"]["status"] = "RESUMABLE"
    partial["run_status"]["termination"] = {"reason": "PREEMPTED", "exit_code": None}
    partial["run_status"]["failure_class"] = "PREEMPTED"
    partial["run_status"]["completion"] = {"status": "NOT_EVALUATED", "evidence_artifacts": []}
    partial["run_status"]["checkpoint"] = {"status": "PARTIAL", "locator": "ckpt.pt"}
    partial["run_status"]["resume_semantics"] = {"safe_to_resume": False}
    r3 = evaluate(partial)
    check(r3["status"] == "FAIL" and "run_status" in r3["blocking_gates"],
          "RESUMABLE 缺 checkpoint SHA/resume command/safe_to_resume 应阻断")

    remote = _good_spec()
    remote["remote_execution"] = {
        "required": True,
        "paid": True,
        "provider": "hpc-cluster",
        "plan_locator": "remote-plan.md",
        "estimated_cost_usd": 25,
        "cancel_command": "scancel <jobid>",
        "data_egress": "none",
        "secrets_policy": "no secrets in command",
        "user_authorization": {"status": "REQUESTED"},
    }
    remote["decision"] = "RUN_READY"
    r4 = evaluate(remote)
    check(r4["status"] == "FAIL" and "remote_execution_authorization" in r4["blocking_gates"],
          "远程/付费执行未 APPROVED 不能 RUN_READY")

    repro = _good_spec()
    repro["reproducibility"]["requested_level"] = "CLEAN_ENV_RERUN"
    repro["reproducibility"]["levels"]["CLEAN_ENV_RERUN"] = "UNKNOWN"
    repro["decision"] = "RUN_READY"
    r5 = evaluate(repro)
    check(r5["status"] == "FAIL" and "repro_level" in r5["blocking_gates"],
          "请求 CLEAN_ENV_RERUN 但未知应阻断")

    cache = _good_spec()
    cache["cache"] = {"enabled": True, "cache_policy": "reuse-if-input-hash-match", "contamination_check": "UNKNOWN"}
    r6 = evaluate(cache)
    check(r6["status"] == "FAIL" and "environment_cache" in r6["blocking_gates"],
          "cache enabled 但无 manifest/污染检查未知应阻断")

    cycle = _good_spec()
    cycle["experiment_spec"]["dag_nodes"][0]["depends_on"] = ["eval"]
    r7 = evaluate(cycle)
    check(r7["status"] == "FAIL" and "experiment_spec" in r7["blocking_gates"],
          "DAG 有环应阻断")

    dirty = _good_spec()
    dirty["environment"]["dirty"] = True
    dirty["environment"]["diff_sha256"] = ""
    r8 = evaluate(dirty)
    check(r8["status"] == "FAIL" and "environment_cache" in r8["blocking_gates"],
          "dirty code 无 diff hash 应阻断")

    row_drift = _good_spec()
    row_drift["run_status"]["matrix_row_id"] = "EXP-NEW"
    r9 = evaluate(row_drift)
    check(r9["status"] == "FAIL" and "run_status" in r9["blocking_gates"],
          "run 绑定到未冻结 matrix row 应阻断")

    over_budget = _good_spec()
    over_budget["run_status"]["resources"]["walltime_minutes"] = 121
    over_budget["run_status"]["resources"]["compute_units_used"] = 3
    over_budget["run_status"]["resources"]["cost_usd"] = 1
    r10 = evaluate(over_budget)
    check(r10["status"] == "FAIL" and "run_status" in r10["blocking_gates"],
          "实际资源/成本超过冻结预算应阻断")

    remote_over_budget = _good_spec()
    remote_over_budget["remote_execution"] = {
        "required": True,
        "paid": True,
        "provider": "hpc-cluster",
        "plan_locator": "remote-plan.md",
        "estimated_cost_usd": 25,
        "cancel_command": "scancel <jobid>",
        "data_egress": "none",
        "secrets_policy": "no secrets in command",
        "budget_impact": "would exceed frozen zero-cost budget",
        "user_authorization": {
            "status": "APPROVED",
            "approved_at": "2026-07-04T10:10:00+08:00",
            "scope": "remote dry run only",
        },
    }
    remote_over_budget["decision"] = "RUN_READY"
    r11 = evaluate(remote_over_budget)
    check(r11["status"] == "FAIL" and "remote_execution_authorization" in r11["blocking_gates"],
          "远程预计成本超过冻结预算且无 budget_override_locator 应阻断")

    bad_cost_string = _good_spec()
    bad_cost_string["run_status"]["resources"]["cost_usd"] = "UNKNOWN"
    bad_cost_string["remote_execution"]["estimated_cost_usd"] = "UNKNOWN"
    bad_cost_string["remote_execution"]["required"] = True
    bad_cost_string["remote_execution"]["paid"] = True
    r12 = evaluate(bad_cost_string)
    check(r12["status"] == "FAIL" and {
        "run_status", "remote_execution_authorization",
    } <= set(r12["blocking_gates"]), "字符串 UNKNOWN 成本应转为结构化 finding 而不是崩溃")

    future = _good_spec()
    future["as_of"] = "2026-07-04T10:00:00+08:00"
    future["experiment_spec"]["frozen_at"] = "2999-01-01T00:00:00+00:00"
    future["remote_execution"] = {
        "required": True,
        "paid": False,
        "provider": "hpc-cluster",
        "plan_locator": "remote-plan.md",
        "estimated_cost_usd": 0,
        "cancel_command": "scancel <jobid>",
        "data_egress": "none",
        "secrets_policy": "no secrets in command",
        "user_authorization": {
            "status": "APPROVED",
            "approved_at": "2999-01-01T00:00:00+00:00",
            "scope": "single dry run",
        },
    }
    future["decision"] = "RUN_READY"
    r13 = evaluate(future)
    rules = {
        finding["rule"]
        for gate in r13["findings"]["gates"]
        for finding in gate["findings"]
    }
    check({
        "experiment_spec.future_frozen_at",
        "remote.future_approved_at",
    } <= rules, "未来 frozen_at/approved_at 应阻断")

    not_ready = _good_spec()
    not_ready["decision"] = "NOT_READY"
    r14 = evaluate(not_ready)
    check(r14["status"] == "FAIL" and "declared_decision" in r14["blocking_gates"],
          "decision=NOT_READY 应阻断推进")

    check("execution contract" in to_markdown(good), "markdown 应含标题")

    if failures:
        print("[SELFTEST][experiment_execution_contract] FAIL:")
        for failure in failures:
            print("  -", failure)
        return 1
    print("[SELFTEST][experiment_execution_contract] OK: clean limited / timeout completed / "
          "resumable checkpoint / remote approval / repro level / cache / DAG cycle / dirty diff / "
          "failure-tree handoff / guardrail refs+evidence / matrix row drift / budget overrun / "
          "bad cost string / future dates / declared decision all checked")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate experiment execution contract")
    parser.add_argument("--spec", help="light.experiment_execution_contract.v1 JSON")
    parser.add_argument("--report", help="write light.findings.v1")
    parser.add_argument("--json-out", help="write full report")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec:
        parser.error("--spec is required unless --selftest")
    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8-sig"))
    result = evaluate(spec)
    print(to_markdown(result))
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
