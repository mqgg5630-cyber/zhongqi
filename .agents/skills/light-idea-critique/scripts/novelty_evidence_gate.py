#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate novelty claims on held-out prior art, coverage, humans, and Pareto evidence."""
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

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
from _shared.findings_schema import Finding, GateResult  # noqa: E402
from _shared.gate_runner import run_gates  # noqa: E402

SCHEMA_ID = "light.novelty_evidence.v1"
MODES = {"TRIAGE", "FINAL_NOVELTY"}
CHANNELS = {
    "SEMANTIC", "CITATION_GRAPH", "LEXICAL_ENTITY", "HELD_OUT_PRIOR_ART",
    "HUMAN_DOMAIN", "OTHER_DECLARED",
}
RUN_STATES = {"SEARCHED", "UNAVAILABLE", "NOT_APPLICABLE"}
TARGET_RELATIONS = {"EQUIVALENT", "PARTIAL", "DIFFERENT", "UNKNOWN"}
STANCES = {"SUPPORTING", "CONTRASTING", "BACKGROUND", "UNKNOWN"}
HUMAN_STATES = {"AGREE_NOVEL", "DISAGREE_NOVEL", "SPLIT", "NOT_REVIEWED", "UNKNOWN"}
DECISIONS = {"GO", "REVISE", "NO_GO", "UNKNOWN"}
LEVELS = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
ETHICAL_LEVELS = {"LOW", "MEDIUM", "HIGH", "PROHIBITIVE", "UNKNOWN"}
FATAL_STATES = {"PRESENT", "ABSENT", "UNKNOWN"}
PARETO_FIELDS = {"NOVELTY", "VALUE", "FEASIBILITY", "TRACTABILITY", "TESTABILITY", "ETHICAL_COST"}
UNCERTAINTY_LEVELS = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
CALIBRATION_STATES = {"VALIDATED", "UNCALIBRATED", "NOT_APPLICABLE", "UNKNOWN"}
PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|<[^>]+>|replace[-_ ]?with|todo|tbd)", re.IGNORECASE)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _real(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and not _is_placeholder(text) and text not in {
        "unknown", "pending", "n/a", "gap",
    }


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.casefold()
    if lowered in {"unknown", "pending", "n/a", "na", "none", "null", "gap"}:
        return True
    return bool(PLACEHOLDER_RE.search(text))


def _locator_ok(value: Any) -> bool:
    """Return whether a public handoff locator is concrete and not a local/private path."""
    text = str(value or "").strip()
    if _is_placeholder(text):
        return False
    if WINDOWS_DRIVE_RE.match(text) or text.startswith(("\\\\", "/", "~")):
        return False
    parts = re.split(r"[\\/]+", text)
    return ".." not in parts


def _sha(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _parse_iso_date(value: Any) -> dt.date | None:
    try:
        text = str(value).strip()
        if _is_placeholder(text):
            return None
        if "T" in text:
            text = text.replace("Z", "+00:00")
            return dt.datetime.fromisoformat(text).date()
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> bool:
    return _parse_iso_date(value) is not None


def _as_of_date(value: Any = None) -> dt.date:
    if value is None or str(value).strip() == "":
        return dt.date.today()
    parsed = _parse_iso_date(value)
    if parsed is None:
        raise ValueError("--as-of/spec.as_of 必须是 ISO 日期或时间")
    return parsed


def _date_not_future(value: Any, as_of: dt.date) -> bool:
    parsed = _parse_iso_date(value)
    return parsed is not None and parsed <= as_of


def evaluate(spec: dict[str, Any], *, as_of: Any = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    today = _as_of_date(as_of if as_of is not None else spec.get("as_of"))
    protocol = spec.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("mode") not in MODES:
        raise ValueError("protocol/mode 非法")
    runs_raw = spec.get("evidence_runs")
    collisions = spec.get("collisions")
    if not isinstance(runs_raw, list) or not isinstance(collisions, list):
        raise ValueError("evidence_runs/collisions 必须是 list")

    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    def check_evidence_refs(
        values: Any,
        loc: str,
        code: str,
        label: str,
        *,
        require_captured_at: bool = False,
    ) -> bool:
        """Validate handoff-safe evidence refs.

        Final novelty decisions must not rely on mutable prose locators alone.
        A ref is an object with locator + SHA-256; captured_at is mandatory for
        human judgments because reviewer notes are time-bound observations.
        """
        ok = True
        if not isinstance(values, list) or not values:
            add(code, loc, f"{label} 缺 evidence refs")
            return False
        for index, ref in enumerate(values):
            ref_loc = f"{loc}[{index}]"
            if not isinstance(ref, dict):
                add(code, ref_loc, f"{label} evidence 必须是 object(locator+sha256)，字符串 locator 不足以防证据漂移")
                ok = False
                continue
            if not _locator_ok(ref.get("locator")):
                add(code, f"{ref_loc}.locator", f"{label} evidence locator 非真实公开定位符，或是模板/本机路径/越界路径")
                ok = False
            if not _sha(ref.get("sha256")):
                add(code, f"{ref_loc}.sha256", f"{label} evidence 缺 sha256:<64 hex>，无法绑定当时看到的证据内容")
                ok = False
            captured_at = ref.get("captured_at")
            if require_captured_at:
                if not _date_not_future(captured_at, today):
                    add(code, f"{ref_loc}.captured_at", f"{label} evidence 缺非未来 captured_at")
                    ok = False
            elif captured_at is not None and not _date_not_future(captured_at, today):
                add(code, f"{ref_loc}.captured_at", f"{label} evidence captured_at 非 ISO 日期或来自未来")
                ok = False
        return ok

    if not _real(spec.get("idea_id")):
        add("IDEA_ID_GAP", "idea", "缺待审候选 idea_id")

    required_channels = protocol.get("required_channels")
    if not isinstance(required_channels, list) or not required_channels:
        add("REQUIRED_CHANNELS_GAP", "protocol", "缺 required_channels")
        required_channels = []
    elif any(channel not in CHANNELS for channel in required_channels):
        raise ValueError("required_channels 含非法 channel")
    if protocol.get("mode") == "FINAL_NOVELTY":
        minimum = {"SEMANTIC", "CITATION_GRAPH", "LEXICAL_ENTITY", "HELD_OUT_PRIOR_ART"}
        if not minimum <= set(required_channels):
            add("FINAL_CHANNEL_COVERAGE_GAP", "protocol", "最终新颖性判断缺四路机器证据")
    boundedness = protocol.get("source_boundedness")
    if boundedness not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        add("SOURCE_BOUNDEDNESS_GAP", "protocol", "source_boundedness 缺失或非法")
    elif boundedness in {"HIGH", "UNKNOWN"}:
        add(
            "NOVELTY_MIRAGE_RISK", "protocol",
            f"source_boundedness={boundedness}，不能据窄检索视图判 novel", "unresolved",
        )

    runs: dict[str, dict[str, Any]] = {}
    searched_channels: set[str] = set()
    held_out = False
    result_total = 0
    for row in runs_raw:
        if not isinstance(row, dict):
            raise ValueError("evidence run 必须是 object")
        run_id = str(row.get("run_id") or "")
        if (
            not run_id or run_id in runs or row.get("channel") not in CHANNELS
            or row.get("status") not in RUN_STATES
        ):
            raise ValueError("run_id 重复/缺失，或 channel/status 非法")
        runs[run_id] = row
        if row["status"] == "SEARCHED":
            searched_channels.add(row["channel"])
            if not _locator_ok(row.get("locator")):
                add(
                    "RUN_LOCATOR_INVALID", f"run:{run_id}",
                    "SEARCHED run 的 locator 必须是真实公开定位符，不能是模板、本机绝对路径或 ../ 越界路径",
                )
            if not _real(row.get("retrieved_at")):
                add("RUN_PROVENANCE_GAP", f"run:{run_id}", "SEARCHED run 缺 retrieved_at")
            elif not _date(row.get("retrieved_at")):
                add("RUN_PROVENANCE_GAP", f"run:{run_id}", "retrieved_at 不是 ISO 日期")
            elif not _date_not_future(row.get("retrieved_at"), today):
                add(
                    "RUN_RETRIEVED_AT_FUTURE", f"run:{run_id}",
                    f"retrieved_at 晚于 as_of={today.isoformat()}，不能用未来查新证据支撑判决",
                )
            if not _sha(row.get("raw_sha256")):
                add("RUN_PROVENANCE_GAP", f"run:{run_id}", "SEARCHED run 缺 raw SHA-256")
            if not isinstance(row.get("result_count"), int) or isinstance(
                row.get("result_count"), bool
            ) or row["result_count"] < 0:
                add("RUN_COUNT_INVALID", f"run:{run_id}", "result_count 必须是非负整数")
            else:
                result_total += row["result_count"]
        elif row["status"] == "UNAVAILABLE":
            if not _real(row.get("failure")):
                add("RUN_UNAVAILABLE_REASON_GAP", f"run:{run_id}", "UNAVAILABLE 缺 failure")
            add(
                "REQUIRED_SOURCE_UNAVAILABLE", f"run:{run_id}",
                f"{row['channel']} unavailable；不得改写为未发现前作", "unresolved",
            )
        if row["channel"] == "HELD_OUT_PRIOR_ART" and row["status"] == "SEARCHED":
            if row.get("generator_visible") is False:
                held_out = True
            else:
                add("HELD_OUT_LEAKAGE", f"run:{run_id}", "held-out prior art 对 generator 可见")

    for channel in required_channels:
        if channel not in searched_channels:
            add(
                "REQUIRED_CHANNEL_UNRESOLVED", "coverage",
                f"required channel {channel} 未成功检索", "unresolved",
            )
    if protocol.get("mode") == "FINAL_NOVELTY" and not held_out:
        add("HELD_OUT_PRIOR_ART_GAP", "coverage", "最终判断缺与 generator 隔离的 held-out prior art")
    if protocol.get("mode") == "FINAL_NOVELTY" and result_total == 0:
        add("NO_PRIOR_ART_RESULTS", "coverage", "最终判断的成功检索合计 0 条，不能据此判 novel")
    if protocol.get("mode") == "FINAL_NOVELTY" and not collisions:
        add("NEAREST_PRIOR_ART_GAP", "collisions", "最终判断缺最近前作 target/background 分解")

    target_collision = False
    unknown_collision = False
    for index, row in enumerate(collisions):
        if not isinstance(row, dict):
            raise ValueError("collision 必须是 object")
        loc = f"collision:{index}"
        if (
            not _real(row.get("prior_art_id"))
            or row.get("target_relation") not in TARGET_RELATIONS
            or row.get("stance") not in STANCES
            or not _locator_ok(row.get("locator"))
        ):
            add(
                "COLLISION_EVIDENCE_GAP", loc,
                "collision 缺 prior-art/relation/stance/真实 locator，或 locator 是模板/本机路径/越界路径",
            )
        source_run_ids = row.get("source_run_ids")
        if not isinstance(source_run_ids, list) or not source_run_ids:
            add("COLLISION_SOURCE_GAP", loc, "collision 缺 source_run_ids")
        elif any(run_id not in runs for run_id in source_run_ids):
            add("COLLISION_SOURCE_GAP", loc, "collision 引用未知 run")
        if row.get("target_relation") in {"PARTIAL", "DIFFERENT"} and not _real(
            row.get("mechanism_delta")
        ):
            add("MECHANISM_DELTA_GAP", loc, "非等价 target 缺 mechanism_delta")
        if row.get("target_relation") == "EQUIVALENT" and row.get("stance") == "SUPPORTING":
            target_collision = True
            add("TARGET_COLLISION", loc, "target 等价且同向，不能宣称 novel")
        if row.get("target_relation") == "UNKNOWN" or row.get("stance") == "UNKNOWN":
            unknown_collision = True
            add("COLLISION_UNRESOLVED", loc, "target/stance 未判定", "unresolved")

    judge_signals = spec.get("judge_signals")
    if not isinstance(judge_signals, list):
        raise ValueError("judge_signals 必须是 list")
    judge_unresolved = False
    judge_calibration_status = "NOT_USED"
    if judge_signals:
        judge_calibration = spec.get("judge_calibration")
        if not isinstance(judge_calibration, dict):
            add("JUDGE_CALIBRATION_GAP", "judge_calibration", "使用 judge_signals 时必须声明 judge_calibration")
            judge_unresolved = True
        else:
            judge_calibration_status = str(judge_calibration.get("status") or "")
            if judge_calibration_status not in CALIBRATION_STATES:
                add("JUDGE_CALIBRATION_GAP", "judge_calibration", "judge_calibration.status 非法")
                judge_unresolved = True
            elif judge_calibration_status != "VALIDATED":
                add(
                    "JUDGE_UNCALIBRATED", "judge_calibration",
                    f"judge_calibration.status={judge_calibration_status}；模型 judge 只能作未校准 signal",
                    "unresolved",
                )
                judge_unresolved = True
            else:
                for field in ("benchmark_id", "applicability", "retrieved_at"):
                    if not _real(judge_calibration.get(field)):
                        add("JUDGE_CALIBRATION_GAP", "judge_calibration", f"VALIDATED calibration 缺 {field}")
                        judge_unresolved = True
                if _real(judge_calibration.get("retrieved_at")) and not _date(
                    judge_calibration.get("retrieved_at")
                ):
                    add("JUDGE_CALIBRATION_GAP", "judge_calibration", "retrieved_at 不是 ISO 日期")
                    judge_unresolved = True
                elif not _date_not_future(judge_calibration.get("retrieved_at"), today):
                    add(
                        "JUDGE_CALIBRATION_FUTURE", "judge_calibration",
                        f"judge calibration retrieved_at 晚于 as_of={today.isoformat()}",
                        "unresolved",
                    )
                    judge_unresolved = True
                if not _sha(judge_calibration.get("raw_sha256")):
                    add("JUDGE_CALIBRATION_GAP", "judge_calibration", "VALIDATED calibration 缺 raw SHA-256")
                    judge_unresolved = True
                sample_size = judge_calibration.get("sample_size")
                if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
                    add("JUDGE_CALIBRATION_GAP", "judge_calibration", "sample_size 必须是正整数")
                    judge_unresolved = True
    judge_ids: set[str] = set()
    groups: dict[str, list[str]] = {}
    for row in judge_signals:
        if not isinstance(row, dict):
            raise ValueError("judge signal 必须是 object")
        judge_id = str(row.get("judge_id") or "")
        group = str(row.get("independence_group") or "")
        evidence_run_ids = row.get("evidence_run_ids")
        uncertainty = str(row.get("uncertainty") or "").upper()
        if (
            not judge_id or judge_id in judge_ids or not group
            or not _real(row.get("verdict")) or uncertainty not in UNCERTAINTY_LEVELS
            or not isinstance(evidence_run_ids, list) or not evidence_run_ids
            or any(run_id not in runs for run_id in evidence_run_ids)
            or not _locator_ok(row.get("rationale_locator")) or not _sha(row.get("raw_sha256"))
        ):
            add(
                "JUDGE_SIGNAL_GAP", "judge_signals",
                "judge 缺 id/group/verdict/uncertainty/evidence runs/真实 rationale locator/raw hash，或 id 重复",
            )
            continue
        judge_ids.add(judge_id)
        groups.setdefault(group, []).append(str(row["verdict"]))
        if uncertainty in {"HIGH", "UNKNOWN"}:
            add(
                "JUDGE_UNCERTAINTY_UNRESOLVED", f"judge:{judge_id}",
                f"judge uncertainty={uncertainty}；不得用高不确定 judge signal 支撑 GO",
                "unresolved",
            )
            judge_unresolved = True
    judge_verdicts = {verdict for verdicts in groups.values() for verdict in verdicts}
    if len(judge_verdicts) > 1:
        add("JUDGE_DISAGREEMENT", "judge_signals", "judge signals 分歧，不能多数表决抹平", "unresolved")
        judge_unresolved = True
    if len(judge_ids) > 1 and len(groups) == 1:
        add(
            "JUDGE_PSEUDOREPLICATION", "judge_signals",
            "多个 judge 来自同一 independence_group，只能算一个独立信号，不能包装成专家共识",
            "unresolved",
        )
        judge_unresolved = True

    human = spec.get("human_domain_verdict")
    if not isinstance(human, dict) or human.get("status") not in HUMAN_STATES:
        raise ValueError("human_domain_verdict/status 非法")
    human_status = human["status"]
    reviewer_count = human.get("reviewer_count")
    if not isinstance(reviewer_count, int) or isinstance(reviewer_count, bool) or reviewer_count < 0:
        add("HUMAN_VERDICT_GAP", "human", "reviewer_count 必须是非负整数")
    if human_status in {"AGREE_NOVEL", "DISAGREE_NOVEL", "SPLIT"}:
        check_evidence_refs(
            human.get("locators"), "human.locators", "HUMAN_VERDICT_GAP",
            "human domain verdict", require_captured_at=True,
        )
    if human_status in {"NOT_REVIEWED", "UNKNOWN", "SPLIT"}:
        add("HUMAN_VERDICT_UNRESOLVED", "human", f"human verdict={human_status}", "unresolved")
    elif human_status == "DISAGREE_NOVEL":
        add("HUMAN_NOVELTY_CONFLICT", "human", "领域判断不支持 novel", "unresolved")

    pareto = spec.get("pareto")
    if not isinstance(pareto, dict):
        raise ValueError("pareto 必须是 object")
    pareto_unknown = False
    for field in PARETO_FIELDS:
        row = pareto.get(field)
        allowed = ETHICAL_LEVELS if field == "ETHICAL_COST" else LEVELS
        if not isinstance(row, dict) or row.get("level") not in allowed:
            add("PARETO_EVIDENCE_GAP", f"pareto:{field}", "缺 level/evidence")
            continue
        check_evidence_refs(
            row.get("evidence"), f"pareto:{field}.evidence",
            "PARETO_EVIDENCE_GAP", f"pareto {field}",
        )
        if row["level"] == "UNKNOWN":
            pareto_unknown = True
            add("PARETO_UNRESOLVED", f"pareto:{field}", f"{field}=UNKNOWN", "unresolved")

    fatal_flaws = spec.get("fatal_flaws")
    if not isinstance(fatal_flaws, list) or not fatal_flaws:
        add("FATAL_FLAW_AUDIT_GAP", "fatal_flaws", "缺 fatal flaw 审计")
        fatal_flaws = []
    fatal_present = False
    fatal_unknown = False
    for index, row in enumerate(fatal_flaws):
        if not isinstance(row, dict) or row.get("status") not in FATAL_STATES:
            add("FATAL_FLAW_AUDIT_GAP", f"fatal:{index}", "fatal flaw status 非法")
            continue
        fatal_description_ok = _real(row.get("description"))
        fatal_evidence_ok = check_evidence_refs(
            row.get("evidence"), f"fatal:{index}.evidence",
            "FATAL_FLAW_EVIDENCE_GAP", "fatal flaw",
        )
        if not fatal_description_ok or not fatal_evidence_ok:
            add("FATAL_FLAW_EVIDENCE_GAP", f"fatal:{index}", "fatal flaw 缺描述/证据")
        fatal_present |= row["status"] == "PRESENT"
        fatal_unknown |= row["status"] == "UNKNOWN"
    if fatal_present:
        add("FATAL_FLAW_PRESENT", "fatal_flaws", "存在有证据的 fatal flaw")
    if fatal_unknown:
        add("FATAL_FLAW_UNKNOWN", "fatal_flaws", "fatal flaw 尚未排除", "unresolved")

    decision = spec.get("decision")
    if not isinstance(decision, dict) or decision.get("verdict") not in DECISIONS:
        raise ValueError("decision/verdict 非法")
    decision_rationale_ok = _real(decision.get("rationale"))
    decision_evidence_ok = check_evidence_refs(
        decision.get("evidence"), "decision.evidence",
        "DECISION_PROVENANCE_GAP", "decision",
    )
    if not decision_rationale_ok or not decision_evidence_ok:
        add("DECISION_PROVENANCE_GAP", "decision", "decision 缺 rationale/evidence")
    hard_block = (
        target_collision or fatal_present
        or (pareto.get("ETHICAL_COST") or {}).get("level") == "PROHIBITIVE"
    )
    unresolved = (
        unknown_collision or pareto_unknown or fatal_unknown
        or human_status != "AGREE_NOVEL"
        or boundedness in {"HIGH", "UNKNOWN"}
        or any(channel not in searched_channels for channel in required_channels)
        or len(judge_verdicts) > 1
        or judge_unresolved
    )
    verdict = decision["verdict"]
    if hard_block and verdict != "NO_GO":
        add("DECISION_OVERRIDES_HARD_BLOCK", "decision", "hard blocker 存在时必须 NO_GO")
    if hard_block:
        add("ADVANCEMENT_BLOCKED", "decision", "证据要求阻止该候选推进")
    elif unresolved and verdict == "GO":
        add("GO_WITH_UNRESOLVED_EVIDENCE", "decision", "证据未决时不得 GO")
    elif protocol.get("mode") == "FINAL_NOVELTY" and not unresolved and verdict != "GO":
        add(
            "DECISION_EVIDENCE_MISMATCH", "decision",
            "证据链满足最终审查但 decision 未说明为何不 GO", "unresolved",
        )

    status = (
        "FAIL" if hard_block or any(issue["severity"] == "error" for issue in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.novelty_evidence_report.v1",
        "status": status,
        "advancement": "BLOCK" if status != "PASS" else "ALLOW",
        "searched_channels": sorted(searched_channels),
        "judge_independence_groups": len(groups),
        "judge_calibration_status": judge_calibration_status,
        "as_of": today.isoformat(),
        "issues": issues,
        "honesty": (
            "PASS 只表示声明的检索视图、held-out 隔离、人类判断与 Pareto 证据闭合；"
            "不证明客观新颖性、未来价值或成功概率。多个 LLM 的一致不等于多个独立专家。"
        ),
    }


def emit_findings(spec: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    def novelty_gate(_: dict[str, Any]) -> GateResult:
        if report["status"] == "PASS":
            return GateResult(
                "novelty_evidence", "pass", "info", [],
                note="held-out、覆盖、人类判断与 Pareto 证据字段闭合。",
            )
        findings = [
            Finding(
                issue["loc"], issue["message"],
                "补检索/held-out/领域判断或据 hard blocker 回 idea-generation 重提。",
                rule=issue["code"],
            )
            for issue in report["issues"]
        ]
        return GateResult(
            "novelty_evidence", "fail", "critical", findings,
            note=f"novelty evidence status={report['status']}；UNKNOWN 也阻止 stage 4 推进。",
        )

    return run_gates(
        [novelty_gate], report, producer="idea-critique",
        target=str(spec.get("idea_id") or "idea"),
        summary="新颖性 held-out、覆盖、人类判断与 Pareto 证据门。",
        fresh_evidence=True,
    ).to_dict()


def _base() -> dict[str, Any]:
    h = "sha256:" + "b" * 64
    def ref(locator: str, fill: str = "c", captured_at: str = "2026-07-04") -> dict[str, str]:
        return {
            "locator": locator,
            "sha256": "sha256:" + fill * 64,
            "captured_at": captured_at,
        }

    channels = ("SEMANTIC", "CITATION_GRAPH", "LEXICAL_ENTITY", "HELD_OUT_PRIOR_ART")
    runs = []
    for index, channel in enumerate(channels, 1):
        runs.append({
            "run_id": f"R{index}", "channel": channel, "status": "SEARCHED",
            "locator": f"run:{index}", "retrieved_at": "2026-07-04",
            "raw_sha256": h, "result_count": 10,
            "generator_visible": False if channel == "HELD_OUT_PRIOR_ART" else True,
        })
    pareto = {}
    for field in PARETO_FIELDS:
        pareto[field] = {
            "level": "LOW" if field == "ETHICAL_COST" else "HIGH",
            "evidence": [ref(f"assessment:{field.lower()}")],
        }
    return {
        "schema": SCHEMA_ID,
        "idea_id": "I1",
        "protocol": {
            "mode": "FINAL_NOVELTY", "required_channels": list(channels),
            "source_boundedness": "LOW",
        },
        "evidence_runs": runs,
        "collisions": [{
            "prior_art_id": "P1", "source_run_ids": ["R1", "R4"],
            "target_relation": "DIFFERENT", "stance": "BACKGROUND",
            "mechanism_delta": "different intervention mechanism", "locator": "paper:P1",
        }],
        "judge_calibration": {
            "status": "VALIDATED",
            "benchmark_id": "local-idea-review-calibration-demo",
            "sample_size": 12,
            "applicability": "same novelty evidence protocol and adjacent domain family",
            "retrieved_at": "2026-07-04",
            "raw_sha256": h,
        },
        "judge_signals": [
            {
                "judge_id": "J1", "independence_group": "model-family-a",
                "verdict": "novel", "uncertainty": "MEDIUM", "evidence_run_ids": ["R1", "R4"],
                "rationale_locator": "judge:J1", "raw_sha256": h,
            },
            {
                "judge_id": "J2", "independence_group": "model-family-b",
                "verdict": "novel", "uncertainty": "MEDIUM", "evidence_run_ids": ["R1", "R4"],
                "rationale_locator": "judge:J2", "raw_sha256": h,
            },
        ],
        "human_domain_verdict": {
            "status": "AGREE_NOVEL", "reviewer_count": 1, "locators": [ref("review:H1", "d")],
        },
        "pareto": pareto,
        "fatal_flaws": [{
            "status": "ABSENT", "description": "no fatal flaw found in declared review",
            "evidence": [ref("review:F1", "e")],
        }],
        "decision": {
            "verdict": "GO", "rationale": "all declared gates passed",
            "evidence": [ref("review:H1", "d"), ref("review:F1", "e")],
        },
    }


def _selftest() -> int:
    clean = evaluate(_base(), as_of="2026-07-05")
    assert clean["status"] == "PASS"
    assert emit_findings(_base(), clean)["verdict"] == "pass"
    collision = json.loads(json.dumps(_base()))
    collision["collisions"][0]["target_relation"] = "EQUIVALENT"
    collision["collisions"][0]["stance"] = "SUPPORTING"
    collision["decision"]["verdict"] = "NO_GO"
    report = evaluate(collision, as_of="2026-07-05")
    assert report["status"] == "FAIL"
    assert "TARGET_COLLISION" in {issue["code"] for issue in report["issues"]}
    unavailable = json.loads(json.dumps(_base()))
    unavailable["evidence_runs"][1] = {
        "run_id": "R2", "channel": "CITATION_GRAPH", "status": "UNAVAILABLE",
        "failure": "HTTP 429",
    }
    unavailable["decision"]["verdict"] = "UNKNOWN"
    unavailable_report = evaluate(unavailable, as_of="2026-07-05")
    assert unavailable_report["status"] == "UNRESOLVED"
    assert emit_findings(unavailable, unavailable_report)["verdict"] == "fail"
    leaked = json.loads(json.dumps(_base()))
    leaked["evidence_runs"][3]["generator_visible"] = True
    assert "HELD_OUT_LEAKAGE" in {
        issue["code"] for issue in evaluate(leaked, as_of="2026-07-05")["issues"]
    }
    split = json.loads(json.dumps(_base()))
    split["human_domain_verdict"]["status"] = "SPLIT"
    split["decision"]["verdict"] = "UNKNOWN"
    assert evaluate(split, as_of="2026-07-05")["status"] == "UNRESOLVED"
    uncalibrated = json.loads(json.dumps(_base()))
    uncalibrated["judge_calibration"]["status"] = "UNCALIBRATED"
    uncalibrated["decision"]["verdict"] = "UNKNOWN"
    assert "JUDGE_UNCALIBRATED" in {
        issue["code"] for issue in evaluate(uncalibrated, as_of="2026-07-05")["issues"]
    }
    uncertain = json.loads(json.dumps(_base()))
    uncertain["judge_signals"][0]["uncertainty"] = "HIGH"
    uncertain["decision"]["verdict"] = "UNKNOWN"
    assert "JUDGE_UNCERTAINTY_UNRESOLVED" in {
        issue["code"] for issue in evaluate(uncertain, as_of="2026-07-05")["issues"]
    }
    pseudo = json.loads(json.dumps(_base()))
    pseudo["judge_signals"][1]["independence_group"] = "model-family-a"
    pseudo["decision"]["verdict"] = "UNKNOWN"
    assert "JUDGE_PSEUDOREPLICATION" in {
        issue["code"] for issue in evaluate(pseudo, as_of="2026-07-05")["issues"]
    }
    override = json.loads(json.dumps(collision))
    override["decision"]["verdict"] = "GO"
    assert "DECISION_OVERRIDES_HARD_BLOCK" in {
        issue["code"] for issue in evaluate(override, as_of="2026-07-05")["issues"]
    }
    future_run = json.loads(json.dumps(_base()))
    future_run["evidence_runs"][0]["retrieved_at"] = "2999-01-01"
    future_run["decision"]["verdict"] = "UNKNOWN"
    assert "RUN_RETRIEVED_AT_FUTURE" in {
        issue["code"] for issue in evaluate(future_run, as_of="2026-07-05")["issues"]
    }
    placeholder_locator = json.loads(json.dumps(_base()))
    placeholder_locator["evidence_runs"][0]["locator"] = "{{semantic-search-run}}"
    placeholder_locator["decision"]["verdict"] = "UNKNOWN"
    assert "RUN_LOCATOR_INVALID" in {
        issue["code"] for issue in evaluate(placeholder_locator, as_of="2026-07-05")["issues"]
    }
    escaping_locator = json.loads(json.dumps(_base()))
    escaping_locator["decision"]["evidence"] = ["../private/review.md"]
    escaping_locator["decision"]["verdict"] = "UNKNOWN"
    assert "DECISION_PROVENANCE_GAP" in {
        issue["code"] for issue in evaluate(escaping_locator, as_of="2026-07-05")["issues"]
    }
    mutable_human = json.loads(json.dumps(_base()))
    mutable_human["human_domain_verdict"]["locators"] = ["review:H1"]
    mutable_human["decision"]["verdict"] = "UNKNOWN"
    assert "HUMAN_VERDICT_GAP" in {
        issue["code"] for issue in evaluate(mutable_human, as_of="2026-07-05")["issues"]
    }
    future_human = json.loads(json.dumps(_base()))
    future_human["human_domain_verdict"]["locators"][0]["captured_at"] = "2999-01-01"
    future_human["decision"]["verdict"] = "UNKNOWN"
    assert "HUMAN_VERDICT_GAP" in {
        issue["code"] for issue in evaluate(future_human, as_of="2026-07-05")["issues"]
    }
    mutable_pareto = json.loads(json.dumps(_base()))
    mutable_pareto["pareto"]["VALUE"]["evidence"][0].pop("sha256")
    mutable_pareto["decision"]["verdict"] = "UNKNOWN"
    assert "PARETO_EVIDENCE_GAP" in {
        issue["code"] for issue in evaluate(mutable_pareto, as_of="2026-07-05")["issues"]
    }
    future_calibration = json.loads(json.dumps(_base()))
    future_calibration["judge_calibration"]["retrieved_at"] = "2999-01-01"
    future_calibration["decision"]["verdict"] = "UNKNOWN"
    assert "JUDGE_CALIBRATION_FUTURE" in {
        issue["code"] for issue in evaluate(future_calibration, as_of="2026-07-05")["issues"]
    }
    print(
        "novelty_evidence_gate selftest PASS: held-out/coverage/collision/human/Pareto/"
        "judge-calibration + hashed evidence refs + future-date/placeholder-locator guards"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--report", help="写 light.findings.v1")
    parser.add_argument("--as-of", help="ISO 日期/时间；默认取系统今日，用于阻断未来 retrieved_at")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    spec = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig"))
    report = evaluate(spec, as_of=args.as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(emit_findings(spec, report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
