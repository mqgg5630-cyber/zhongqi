#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate canonical consistency objects, typed relations, coverage, and stale propagation.

This gate sits below text scanning. It prevents a registry from treating
"same-looking" facts as the same fact when unit, denominator, population,
analysis set, split, or authority owner differ.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_root = pathlib.Path(__file__).resolve()
while _root != _root.parent and not (_root / "_shared" / "__init__.py").exists():
    _root = _root.parent
sys.path.insert(0, str(_root))
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402

SCHEMA_ID = "light.consistency_registry.v1"
PACKAGE_READY = {"READY", "SUBMIT_READY", "PUBLISH_READY", "CAMERA_READY"}
OBJECT_TYPES = {"metric", "dataset_split", "claim", "term", "artifact", "figure", "result", "protocol", "value"}
PREDICATES = {
    "distinct_from", "same_as", "derived_from", "updates", "supersedes",
    "unit_conversion", "supports", "contradicts", "mentions", "owned_by",
}
CHECKER_KINDS = {"semantic", "record", "visual", "numeric", "claim", "artifact"}
COVERAGE_STATES = {"FULL", "PARTIAL", "NONE", "UNKNOWN", "MANUAL_SIGNOFF"}
CHANGE_BROADCAST = {"DONE", "NOT_REQUIRED", "PENDING", "UNKNOWN"}
BASELINE_MODES = {"FIRST_RUN", "COMPARE"}
DELTA_STATES = {"FIXED", "NEW", "PERSISTENT", "REGRESSED", "UNCHANGED"}
EXCEPTION_STATES = {"APPROVED", "PROPOSED", "REJECTED", "EXPIRED"}
SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and "<" not in text and "{{" not in text and text.casefold() not in {
        "unknown", "pending", "gap", "待核查", "n/a",
    }


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


class Bag:
    def __init__(self) -> None:
        self.rows: dict[str, list[tuple[str, Finding]]] = {
            "canonical_objects": [],
            "typed_relations": [],
            "observations": [],
            "checker_coverage": [],
            "material_inventory": [],
            "regression_baseline": [],
            "intentional_exceptions": [],
            "change_impact": [],
            "conflict_resolution": [],
        }

    def add(self, gate: str, severity: str, loc: str, issue: str, fix: str, rule: str,
            evidence: str | None = None) -> None:
        self.rows.setdefault(gate, []).append((
            severity,
            Finding(loc=loc, issue=issue, fix=fix, evidence=evidence, rule=rule),
        ))

    def gates(self) -> list[GateResult]:
        gates: list[GateResult] = []
        for gate, rows in self.rows.items():
            if not rows:
                gates.append(GateResult(gate, "pass", "info"))
                continue
            severity = "critical" if any(sev == "critical" for sev, _ in rows) else "major"
            gates.append(GateResult(
                gate=gate,
                status="fail" if severity == "critical" else "warn",
                severity=severity,
                findings=[finding for _, finding in rows],
            ))
        return gates


def _semantic_fields(row: dict[str, Any]) -> dict[str, str]:
    fields = {}
    for key in (
        "name", "method", "dataset", "value", "unit", "population",
        "analysis_set", "denominator", "numerator", "split_name",
        "split_role", "time_window", "normalization",
    ):
        if row.get(key) is not None:
            fields[key] = _norm(row.get(key))
    return fields


def _provenance_ok(row: dict[str, Any]) -> bool:
    prov = row.get("provenance") or {}
    return (
        isinstance(prov, dict)
        and str(prov.get("status") or "").upper() == "CONFIRMED"
        and _real(prov.get("source"))
        and _real(prov.get("locator"))
    )


def _relation_set(relations: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        (str(rel.get("subject") or ""), str(rel.get("predicate") or ""), str(rel.get("object") or ""))
        for rel in relations
    }


def _has_relation(relset: set[tuple[str, str, str]], a: str, pred: str, b: str) -> bool:
    return (a, pred, b) in relset or (b, pred, a) in relset


def _artifact_id(row: dict[str, Any]) -> str:
    return str(row.get("artifact") or row.get("path") or row.get("id") or "").strip()


def _section_set(row: dict[str, Any]) -> set[str]:
    return {_norm(section) for section in row.get("sections") or [] if _real(section)}


def _objects(spec: dict[str, Any], bag: Bag) -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}
    for row in spec.get("objects") or []:
        oid = str(row.get("id") or "")
        if not oid:
            bag.add("canonical_objects", "critical", "object", "canonical object 缺 id", "给每个语义对象稳定 ID", "OBJECT_ID_MISSING")
            continue
        if oid in objects:
            bag.add("canonical_objects", "critical", oid, "canonical object id 重复", "拆分或合并前先人工裁定", "DUPLICATE_OBJECT_ID")
        if row.get("type") not in OBJECT_TYPES:
            bag.add("canonical_objects", "critical", oid, f"未知 object type: {row.get('type')}", "使用受控 object type", "OBJECT_TYPE_INVALID")
        if not _real(row.get("owner_skill")):
            bag.add("canonical_objects", "major", oid, "canonical object 缺 owner_skill", "声明事实源所有者，用于冲突解决", "OWNER_SKILL_MISSING")
        if not _provenance_ok(row):
            bag.add("canonical_objects", "major", oid, "canonical object 缺 confirmed provenance", "补 source+locator；候选不得当 canonical", "OBJECT_PROVENANCE_GAP")
        objects[oid] = row
    return objects


def _relations(spec: dict[str, Any], objects: dict[str, dict[str, Any]], bag: Bag) -> list[dict[str, Any]]:
    relations = spec.get("relations") or []
    if not isinstance(relations, list):
        raise ValueError("relations 必须是 list")
    for rel in relations:
        rid = str(rel.get("relation_id") or f"{rel.get('subject')}:{rel.get('predicate')}:{rel.get('object')}")
        subject, obj, pred = str(rel.get("subject") or ""), str(rel.get("object") or ""), str(rel.get("predicate") or "")
        if subject not in objects or obj not in objects:
            bag.add("typed_relations", "critical", rid, "typed relation 指向未知 object", "先登记 subject/object，再建立关系", "RELATION_UNKNOWN_OBJECT")
        if pred not in PREDICATES:
            bag.add("typed_relations", "critical", rid, f"未知 predicate: {pred}", "使用受控 typed relation", "RELATION_PREDICATE_INVALID")
        if pred in {"same_as", "unit_conversion"} and not _real(rel.get("evidence_locator")):
            bag.add("typed_relations", "critical", rid, f"{pred} 缺 evidence_locator", "等价/换算关系必须有证据", "RELATION_EVIDENCE_GAP")
    return relations


def _collisions(objects: dict[str, dict[str, Any]], relset: set[tuple[str, str, str]], bag: Bag) -> None:
    metrics = [row for row in objects.values() if row.get("type") == "metric"]
    for i, left in enumerate(metrics):
        for right in metrics[i + 1:]:
            left_id, right_id = str(left["id"]), str(right["id"])
            same_label = (
                _norm(left.get("name")) == _norm(right.get("name"))
                and _norm(left.get("method")) == _norm(right.get("method"))
                and _norm(left.get("dataset")) == _norm(right.get("dataset"))
            )
            if not same_label:
                continue
            different = [
                key for key in ("unit", "population", "analysis_set", "denominator", "numerator", "normalization")
                if _norm(left.get(key)) != _norm(right.get(key))
            ]
            if different and not _has_relation(relset, left_id, "distinct_from", right_id):
                bag.add(
                    "canonical_objects", "critical", f"{left_id}|{right_id}",
                    f"同名指标语义字段不同但未声明 distinct_from: {','.join(different)}",
                    "拆成不同 canonical ID 并登记 distinct_from；不要按名字自动合并",
                    "SAME_NAME_SEMANTIC_COLLISION",
                    evidence=json.dumps({"left": _semantic_fields(left), "right": _semantic_fields(right)}, ensure_ascii=False),
                )
            same_value = _norm(left.get("value")) == _norm(right.get("value")) and _real(left.get("value"))
            if same_value and _norm(left.get("unit")) != _norm(right.get("unit")) and not _has_relation(relset, left_id, "unit_conversion", right_id):
                bag.add(
                    "canonical_objects", "critical", f"{left_id}|{right_id}",
                    "同名同值但单位不同，且无 unit_conversion 证据",
                    "明确单位和换算关系；同值不同单位不能自动视为一致",
                    "SAME_VALUE_DIFFERENT_UNIT",
                )


def _observations(spec: dict[str, Any], objects: dict[str, dict[str, Any]], bag: Bag) -> None:
    seen_values: dict[tuple[str, str], set[str]] = {}
    for obs in spec.get("observations") or []:
        obs_id = str(obs.get("obs_id") or "observation")
        oid = str(obs.get("object_id") or "")
        if oid not in objects:
            bag.add("observations", "critical", obs_id, "observation 指向未知 object", "先登记 canonical object", "OBS_UNKNOWN_OBJECT")
            continue
        if str(obs.get("status") or "").upper() != "CONFIRMED":
            bag.add("observations", "major", obs_id, "observation 不是 CONFIRMED", "候选抽取只能 partial，不能支撑 PASS", "OBS_UNCONFIRMED")
            continue
        if not re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", str(obs.get("artifact_sha256") or "")):
            bag.add("observations", "major", obs_id, "observation 缺 artifact_sha256", "绑定材料版本 hash，防止旧材料冒充已扫", "OBS_HASH_MISSING")
        obj = objects[oid]
        obj_fields = _semantic_fields(obj)
        obs_fields = _semantic_fields(obs)
        for key in ("value", "unit", "population", "analysis_set", "denominator", "numerator", "split_name", "split_role", "time_window", "normalization"):
            if key in obj_fields and key in obs_fields and obj_fields[key] != obs_fields[key]:
                rule = "SPLIT_ROLE_CONFLICT" if key in {"split_name", "split_role"} else "OBJECT_OBSERVATION_DRIFT"
                bag.add(
                    "observations", "critical", obs_id,
                    f"observation {key} 与 canonical 不一致：{obs.get(key)!r} vs {obj.get(key)!r}",
                    "回到事实源所有者裁定；不要自动选择最像的值",
                    rule,
                    evidence=json.dumps({"object": obj_fields, "observation": obs_fields}, ensure_ascii=False),
                )
        seen_values.setdefault((oid, str(obs.get("artifact") or "")), set()).add(json.dumps(obs_fields, sort_keys=True, ensure_ascii=False))
    for (oid, artifact), values in seen_values.items():
        if len(values) > 1:
            bag.add("observations", "critical", f"{artifact}:{oid}", "同一材料内同一 canonical object 出现多个语义值", "定位并人工裁定哪个值有效", "INTRA_ARTIFACT_SEMANTIC_CONFLICT")


def _checkers(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    checkers = spec.get("checkers") or []
    kinds_seen: set[str] = set()
    for checker in checkers:
        cid = str(checker.get("checker_id") or "checker")
        kind = str(checker.get("kind") or "")
        state = str((checker.get("coverage") or {}).get("state") or "UNKNOWN").upper()
        kinds_seen.add(kind)
        if kind not in CHECKER_KINDS:
            bag.add("checker_coverage", "critical", cid, f"未知 checker kind: {kind}", "使用 semantic/record/visual/numeric/claim/artifact", "CHECKER_KIND_INVALID")
        if state not in COVERAGE_STATES:
            bag.add("checker_coverage", "critical", cid, f"非法 coverage state: {state}", "使用 FULL/PARTIAL/NONE/UNKNOWN/MANUAL_SIGNOFF", "COVERAGE_STATE_INVALID")
        if ready and state in {"NONE", "UNKNOWN"}:
            bag.add("checker_coverage", "critical", cid, f"{kind} checker coverage={state}", "交付前必须声明覆盖边界；未覆盖不能说已一致", "CHECKER_COVERAGE_GAP")
        if state in {"PARTIAL", "MANUAL_SIGNOFF"} and not _real((checker.get("coverage") or {}).get("locator")):
            bag.add("checker_coverage", "major", cid, f"{state} coverage 缺 locator", "绑定 coverage report 或人工签字 locator", "COVERAGE_LOCATOR_MISSING")
        if kind == "visual" and checker.get("mode") == "scripted_pixel_check":
            bag.add("checker_coverage", "major", cid, "visual scripted check 声明需谨慎", "若无真实取色/版式脚本，改为 MANUAL_SIGNOFF 并给签字 locator", "VISUAL_COVERAGE_BOUNDARY")
    if ready:
        for required in {"semantic", "record", "visual"} - kinds_seen:
            bag.add("checker_coverage", "critical", required, f"缺 {required} checker coverage 声明", "明确哪些一致性面已查/未查/人工签字", "REQUIRED_CHECKER_MISSING")


def _material_inventory(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    inventories = spec.get("material_inventory") or []
    if not isinstance(inventories, list):
        raise ValueError("material_inventory 必须是 list")
    if ready and not inventories:
        bag.add(
            "material_inventory", "critical", "material_inventory",
            "交付前缺材料清单，不能声称跨材料全查",
            "登记 required_artifacts/scanned_artifacts、hash、section 覆盖和扫描报告 locator",
            "MATERIAL_INVENTORY_MISSING",
        )
        return
    for inv in inventories:
        iid = str(inv.get("inventory_id") or "material_inventory")
        required = inv.get("required_artifacts") or []
        scanned = inv.get("scanned_artifacts") or []
        if not _real(inv.get("inventory_locator")):
            bag.add("material_inventory", "major", iid, "材料清单缺 inventory_locator", "绑定材料清单来源，避免临时口头清单", "MATERIAL_INVENTORY_LOCATOR_MISSING")
        if ready and not required:
            bag.add("material_inventory", "critical", iid, "SUBMIT_READY 但 required_artifacts 为空", "列出论文/PPT/软著/代码/补充材料等应查材料", "REQUIRED_ARTIFACTS_MISSING")

        complete = True
        scanned_by_artifact: dict[str, dict[str, Any]] = {}
        for row in scanned:
            artifact = _artifact_id(row)
            if not artifact:
                complete = False
                bag.add("material_inventory", "critical", iid, "scanned_artifacts 存在空 artifact", "给每份已扫材料稳定路径/ID", "SCANNED_ARTIFACT_ID_MISSING")
                continue
            if artifact in scanned_by_artifact:
                bag.add("material_inventory", "major", artifact, "同一材料重复登记扫描结果", "合并为单条并保留最新 hash/locator", "DUPLICATE_SCANNED_ARTIFACT")
            scanned_by_artifact[artifact] = row
            if not SHA_RE.fullmatch(str(row.get("artifact_sha256") or "")):
                complete = False
                bag.add("material_inventory", "major", artifact, "已扫材料缺合法 artifact_sha256", "绑定本次扫描使用的材料版本 hash", "MATERIAL_HASH_MISSING")
            if not _real(row.get("scan_locator")):
                complete = False
                bag.add("material_inventory", "major", artifact, "已扫材料缺 scan_locator", "绑定扫描报告或 findings locator", "MATERIAL_SCAN_LOCATOR_MISSING")

        for row in required:
            artifact = _artifact_id(row)
            if not artifact:
                complete = False
                bag.add("material_inventory", "critical", iid, "required_artifacts 存在空 artifact", "给每份应查材料稳定路径/ID", "REQUIRED_ARTIFACT_ID_MISSING")
                continue
            scanned_row = scanned_by_artifact.get(artifact)
            if scanned_row is None:
                complete = False
                severity = "critical" if ready else "major"
                bag.add("material_inventory", severity, artifact, "应查材料未进入 scanned_artifacts", "先补扫该材料；缺材料时不能声称全查", "MATERIAL_NOT_SCANNED")
                continue
            missing_sections = sorted(_section_set(row) - _section_set(scanned_row))
            if missing_sections:
                complete = False
                severity = "critical" if ready else "major"
                bag.add(
                    "material_inventory", severity, artifact,
                    f"材料未扫描必需 section: {', '.join(missing_sections)}",
                    "按 title/abstract/methods/results/figures/tables/supplement 等材料结构补扫",
                    "MATERIAL_SECTION_MISSING",
                )
        if str(inv.get("coverage_claim") or "").upper() in {"FULL", "ALL"} and not complete:
            bag.add("material_inventory", "critical", iid, "coverage_claim=FULL 但清单/section/hash/locator 不完整", "改为 PARTIAL 或补齐证据后再声称全查", "PREMATURE_FULL_COVERAGE_CLAIM")


def _baseline(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    baseline = spec.get("regression_baseline") or {}
    if not isinstance(baseline, dict):
        raise ValueError("regression_baseline 必须是 object")
    mode = str(baseline.get("mode") or "").upper()
    if ready and mode not in BASELINE_MODES:
        bag.add("regression_baseline", "critical", "regression_baseline", "缺 FIRST_RUN/COMPARE 基线模式", "首轮写 FIRST_RUN；复扫写 COMPARE 并给 baseline/current run locator", "BASELINE_MODE_MISSING")
    if mode and mode not in BASELINE_MODES:
        bag.add("regression_baseline", "critical", "regression_baseline", f"非法 baseline mode: {mode}", "使用 FIRST_RUN/COMPARE", "BASELINE_MODE_INVALID")
    if mode in BASELINE_MODES and not _real(baseline.get("current_run_locator")):
        bag.add("regression_baseline", "major", "regression_baseline", "缺 current_run_locator", "绑定本轮扫描报告或 findings 文件", "CURRENT_RUN_LOCATOR_MISSING")
    if mode == "COMPARE" and not _real(baseline.get("baseline_run_locator")):
        bag.add("regression_baseline", "critical", "regression_baseline", "COMPARE 模式缺 baseline_run_locator", "绑定上一轮基线报告，才能区分 Fixed/New/Persistent/Regressed", "BASELINE_RUN_LOCATOR_MISSING")

    deltas = spec.get("baseline_deltas") or []
    if not isinstance(deltas, list):
        raise ValueError("baseline_deltas 必须是 list")
    if ready and mode == "COMPARE" and not deltas:
        bag.add("regression_baseline", "critical", "baseline_deltas", "COMPARE 模式缺 baseline_deltas", "逐条标 Fixed/New/Persistent/Regressed/Unchanged", "BASELINE_DELTAS_MISSING")
    for delta in deltas:
        did = str(delta.get("delta_id") or "baseline_delta")
        state = str(delta.get("state") or "").upper()
        if state not in DELTA_STATES:
            bag.add("regression_baseline", "critical", did, f"非法 delta state: {state}", "使用 Fixed/New/Persistent/Regressed/Unchanged", "BASELINE_DELTA_STATE_INVALID")
        if not _real(delta.get("finding_key")):
            bag.add("regression_baseline", "major", did, "baseline delta 缺 finding_key", "用 kind+artifact+locator 或稳定 finding hash 绑定同一问题", "BASELINE_FINDING_KEY_MISSING")
        if state in {"FIXED", "PERSISTENT", "REGRESSED"} and not _real(delta.get("baseline_locator")):
            bag.add("regression_baseline", "major", did, f"{state} 缺 baseline_locator", "绑定上一轮该 finding 的证据位置", "BASELINE_DELTA_BASE_LOCATOR_MISSING")
        if state in {"NEW", "PERSISTENT", "REGRESSED"} and not _real(delta.get("current_locator")):
            bag.add("regression_baseline", "major", did, f"{state} 缺 current_locator", "绑定本轮该 finding 的证据位置", "BASELINE_DELTA_CURRENT_LOCATOR_MISSING")
        if state in {"NEW", "REGRESSED"} and ready and not _real(delta.get("owner_decision_locator")):
            bag.add("regression_baseline", "critical", did, f"{state} finding 缺 owner_decision_locator", "新增/回归问题不能静默放行；记录修复、例外或带病推进裁定", "BASELINE_NEW_OR_REGRESSED_UNACKED")
        if state == "PERSISTENT" and ready and not _real(delta.get("known_issue_locator")):
            bag.add("regression_baseline", "critical", did, "Persistent finding 缺 known_issue_locator", "持久问题必须进入 known issue/例外登记，不能每轮当新发现糊过去", "PERSISTENT_FINDING_UNTRACKED")


def _exceptions(spec: dict[str, Any], bag: Bag, ready: bool) -> set[str]:
    exceptions = spec.get("exceptions") or []
    if not isinstance(exceptions, list):
        raise ValueError("exceptions 必须是 list")
    approved: set[str] = set()
    for exc in exceptions:
        eid = str(exc.get("exception_id") or "")
        if not eid:
            bag.add("intentional_exceptions", "critical", "exception", "exception 缺 exception_id", "给每个有意例外稳定 ID", "EXCEPTION_ID_MISSING")
            continue
        status = str(exc.get("status") or "").upper()
        if status not in EXCEPTION_STATES:
            bag.add("intentional_exceptions", "critical", eid, f"非法 exception status: {status}", "使用 APPROVED/PROPOSED/REJECTED/EXPIRED", "EXCEPTION_STATUS_INVALID")
        if status == "APPROVED":
            approved.add(eid)
            scope = exc.get("scope") or {}
            if not _real(exc.get("rationale")):
                bag.add("intentional_exceptions", "critical", eid, "APPROVED exception 缺 rationale", "解释为什么该不一致是有意保留而非漏修", "EXCEPTION_RATIONALE_MISSING")
            if not _real(exc.get("owner_decision_locator")):
                bag.add("intentional_exceptions", "critical", eid, "APPROVED exception 缺 owner_decision_locator", "绑定作者/事实源 owner 裁定记录", "EXCEPTION_DECISION_LOCATOR_MISSING")
            if not isinstance(scope, dict) or not scope.get("artifacts"):
                bag.add("intentional_exceptions", "critical", eid, "APPROVED exception 缺 scope.artifacts", "限定例外适用材料/范围，禁止全仓模糊豁免", "EXCEPTION_SCOPE_MISSING")
            if not _real(exc.get("evidence_locator")):
                bag.add("intentional_exceptions", "major", eid, "APPROVED exception 缺 evidence_locator", "绑定被豁免冲突的原始证据位置", "EXCEPTION_EVIDENCE_LOCATOR_MISSING")
        elif ready and status in {"PROPOSED", "EXPIRED"}:
            bag.add("intentional_exceptions", "critical", eid, f"{status} exception 不能支撑交付放行", "交付前必须 APPROVED 或改为修复/阻断", "EXCEPTION_NOT_APPROVED")
    return approved


def _changes(spec: dict[str, Any], bag: Bag, ready: bool) -> None:
    for change in spec.get("changes") or []:
        cid = str(change.get("change_id") or "change")
        fields = change.get("changed_fields") or []
        if not fields:
            continue
        impact = change.get("impact_graph") or {}
        stale = change.get("stale_marks") or []
        broadcast = str(change.get("broadcast_status") or "UNKNOWN").upper()
        if ready and not (impact.get("objects") or impact.get("artifacts") or impact.get("checkers")):
            bag.add("change_impact", "critical", cid, "canonical 变更缺 impact graph", "列出受影响 objects/artifacts/checkers 并全量回扫", "CHANGE_IMPACT_GRAPH_MISSING")
        if ready and not stale:
            bag.add("change_impact", "critical", cid, "canonical 变更未产生 stale marks", "定义一改，下游材料必须标 stale 直到重扫", "STALE_PROPAGATION_MISSING")
        if broadcast not in CHANGE_BROADCAST:
            bag.add("change_impact", "critical", cid, f"broadcast_status 非法: {broadcast}", "使用 DONE/NOT_REQUIRED/PENDING/UNKNOWN", "CHANGE_BROADCAST_INVALID")
        if ready and broadcast not in {"DONE", "NOT_REQUIRED"}:
            bag.add("change_impact", "critical", cid, "变更广播未完成", "memory-pm 记录广播、owner 和重扫结果", "CHANGE_BROADCAST_NOT_DONE")


def _conflicts(spec: dict[str, Any], bag: Bag, ready: bool, approved_exceptions: set[str]) -> None:
    for conflict in spec.get("conflicts") or []:
        cid = str(conflict.get("conflict_id") or "conflict")
        if conflict.get("auto_resolved_by_similarity") is True:
            bag.add("conflict_resolution", "critical", cid, "冲突被相似度/最近值自动解决", "必须由事实源所有者人工裁定，不自动选择最像值", "AUTO_RESOLVED_BY_SIMILARITY")
        status = str(conflict.get("status") or "UNRESOLVED").upper()
        if ready and status in {"UNRESOLVED", "UNKNOWN"}:
            bag.add("conflict_resolution", "critical", cid, "交付前仍有未解决冲突", "记录 owner decision、source locator 和修复/例外范围", "UNRESOLVED_CONFLICT")
        if status == "RESOLVED" and not _real(conflict.get("decision_locator")):
            bag.add("conflict_resolution", "critical", cid, "RESOLVED conflict 缺 decision_locator", "绑定用户/owner 裁定记录", "CONFLICT_DECISION_LOCATOR_MISSING")
        if status == "EXCEPTION":
            exception_id = str(conflict.get("exception_id") or "")
            if exception_id not in approved_exceptions:
                bag.add("conflict_resolution", "critical", cid, "conflict 引用的 exception 未批准或不存在", "先在 exceptions[] 登记 APPROVED exception 并绑定 owner 裁定", "CONFLICT_EXCEPTION_NOT_APPROVED")


def evaluate(spec: dict[str, Any]) -> FindingsReport:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    ready = str((spec.get("package") or {}).get("status") or "DRAFT").upper() in PACKAGE_READY
    bag = Bag()
    objects = _objects(spec, bag)
    relations = _relations(spec, objects, bag)
    relset = _relation_set(relations)
    _collisions(objects, relset, bag)
    _observations(spec, objects, bag)
    _checkers(spec, bag, ready)
    _material_inventory(spec, bag, ready)
    _baseline(spec, bag, ready)
    approved_exceptions = _exceptions(spec, bag, ready)
    _changes(spec, bag, ready)
    _conflicts(spec, bag, ready, approved_exceptions)
    return FindingsReport(
        producer="consistency",
        target=str((spec.get("package") or {}).get("target") or "consistency-registry"),
        gates=bag.gates(),
        summary=(
            "核 canonical registry、typed relations、semantic observations、checker coverage、"
            "material inventory、baseline deltas、intentional exceptions、change impact/stale propagation；"
            "不自动选择最像值。"
        ),
        fresh_evidence=True,
    ).finalize()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("input must be JSON object")
    return value


def _good() -> dict[str, Any]:
    prov = {"status": "CONFIRMED", "source": "results.csv", "locator": "Results!B2"}
    return {
        "schema": SCHEMA_ID,
        "package": {"status": "SUBMIT_READY", "target": "paper+slides+code"},
        "objects": [
            {"id": "metric.f1.test", "type": "metric", "name": "F1", "method": "DCA-Net", "dataset": "D", "value": 87.6, "unit": "%", "population": "all", "analysis_set": "test", "denominator": "test instances", "numerator": "correct positive matches", "normalization": "percent", "owner_skill": "result-analysis", "provenance": prov},
            {"id": "metric.f1.validation", "type": "metric", "name": "F1", "method": "DCA-Net", "dataset": "D", "value": 86.1, "unit": "%", "population": "all", "analysis_set": "validation", "denominator": "validation instances", "numerator": "correct positive matches", "normalization": "percent", "owner_skill": "result-analysis", "provenance": prov},
            {"id": "split.test", "type": "dataset_split", "name": "test split", "dataset": "D", "split_name": "test", "split_role": "held-out test", "owner_skill": "data-engineering", "provenance": {"status": "CONFIRMED", "source": "data-card.md", "locator": "L4"}},
        ],
        "relations": [
            {"relation_id": "r1", "subject": "metric.f1.test", "predicate": "distinct_from", "object": "metric.f1.validation", "evidence_locator": "analysis-plan.md:12"},
        ],
        "observations": [
            {"obs_id": "paper-f1", "object_id": "metric.f1.test", "artifact": "paper.md", "locator": "L20", "artifact_sha256": "sha256:" + "a" * 64, "status": "CONFIRMED", "value": 87.6, "unit": "%", "analysis_set": "test", "denominator": "test instances"},
            {"obs_id": "code-split", "object_id": "split.test", "artifact": "config.yaml", "locator": "L8", "artifact_sha256": "sha256:" + "b" * 64, "status": "CONFIRMED", "split_name": "test", "split_role": "held-out test"},
        ],
        "checkers": [
            {"checker_id": "semantic-text", "kind": "semantic", "coverage": {"state": "FULL", "object_types": ["term", "claim", "metric"], "artifacts": ["paper.md", "slides.md"]}},
            {"checker_id": "record-values", "kind": "record", "coverage": {"state": "FULL", "object_types": ["metric", "dataset_split"], "artifacts": ["paper.md", "config.yaml"]}},
            {"checker_id": "visual-manual", "kind": "visual", "mode": "manual", "coverage": {"state": "MANUAL_SIGNOFF", "locator": "review-log.md:visual"}},
        ],
        "material_inventory": [{
            "inventory_id": "submit-set",
            "inventory_locator": "passport.yaml:artifacts",
            "coverage_claim": "FULL",
            "required_artifacts": [
                {"artifact": "paper.md", "sections": ["title", "abstract", "methods", "results", "figures", "tables"]},
                {"artifact": "slides.md", "sections": ["title", "methods", "results"]},
                {"artifact": "config.yaml", "sections": ["settings"]},
            ],
            "scanned_artifacts": [
                {"artifact": "paper.md", "artifact_sha256": "sha256:" + "c" * 64, "sections": ["title", "abstract", "methods", "results", "figures", "tables"], "scan_locator": "cons.findings.json:paper"},
                {"artifact": "slides.md", "artifact_sha256": "sha256:" + "d" * 64, "sections": ["title", "methods", "results"], "scan_locator": "cons.findings.json:slides"},
                {"artifact": "config.yaml", "artifact_sha256": "sha256:" + "e" * 64, "sections": ["settings"], "scan_locator": "cons.findings.json:config"},
            ],
        }],
        "regression_baseline": {
            "mode": "COMPARE",
            "baseline_run_locator": "consistency-runs/001.json",
            "current_run_locator": "consistency-runs/002.json",
        },
        "baseline_deltas": [
            {"delta_id": "fix-old-slide-value", "finding_key": "METRIC_VALUE:slides.md:L20", "state": "FIXED", "baseline_locator": "consistency-runs/001.json:METRIC_VALUE:slides.md:L20"},
            {"delta_id": "same-clean-paper", "finding_key": "paper.md:all", "state": "UNCHANGED"},
        ],
        "exceptions": [{
            "exception_id": "ex-short-slide-label",
            "status": "APPROVED",
            "rationale": "PPT 首页保留短标签，正文和论文使用 canonical 全称。",
            "owner_decision_locator": "decision-log.md:12",
            "evidence_locator": "slides.md:1",
            "scope": {"artifacts": ["slides.md"], "until": "camera-ready"},
        }],
        "changes": [{
            "change_id": "chg-f1", "object_id": "metric.f1.test", "changed_fields": ["value"],
            "impact_graph": {"objects": ["metric.f1.test"], "artifacts": ["paper.md", "slides.md"], "checkers": ["record-values"]},
            "stale_marks": [{"artifact": "slides.md", "reason": "metric changed"}],
            "broadcast_status": "DONE",
        }],
        "conflicts": [
            {"conflict_id": "c-old", "status": "RESOLVED", "decision_locator": "decision-log.md:3"},
            {"conflict_id": "c-intentional-short-label", "status": "EXCEPTION", "exception_id": "ex-short-slide-label"},
        ],
    }


def _selftest() -> int:
    good = evaluate(_good())
    assert good.verdict == "pass", good.to_json()
    bad = _good()
    bad = json.loads(json.dumps(bad))
    bad["relations"] = []
    bad["objects"][1]["value"] = 87.6
    bad["objects"][1]["unit"] = "fraction"
    bad["observations"][0]["unit"] = "fraction"
    bad["observations"][1]["split_role"] = "validation"
    bad["checkers"] = [bad["checkers"][0], {"checker_id": "record-values", "kind": "record", "coverage": {"state": "UNKNOWN"}}]
    bad["material_inventory"][0]["required_artifacts"].append({"artifact": "supplement.pdf", "sections": ["methods", "tables"]})
    bad["material_inventory"][0]["scanned_artifacts"] = [
        {"artifact": "paper.md", "artifact_sha256": "not-a-hash", "sections": ["title"], "scan_locator": ""},
        {"artifact": "slides.md", "artifact_sha256": "sha256:" + "d" * 64, "sections": ["title"], "scan_locator": "cons.findings.json:slides"},
    ]
    bad["regression_baseline"] = {"mode": "COMPARE", "current_run_locator": ""}
    bad["baseline_deltas"] = [
        {"delta_id": "regressed-term", "finding_key": "", "state": "REGRESSED", "baseline_locator": "", "current_locator": "", "owner_decision_locator": ""},
        {"delta_id": "persistent-metric", "finding_key": "METRIC_VALUE:slides.md:L20", "state": "PERSISTENT", "baseline_locator": "old.json:1", "current_locator": "new.json:1"},
    ]
    bad["exceptions"] = [{"exception_id": "ex-short-slide-label", "status": "PROPOSED"}]
    bad["changes"][0]["impact_graph"] = {}
    bad["changes"][0]["stale_marks"] = []
    bad["changes"][0]["broadcast_status"] = "PENDING"
    bad["conflicts"] = [
        {"conflict_id": "c1", "status": "UNRESOLVED", "auto_resolved_by_similarity": True},
        {"conflict_id": "c2", "status": "EXCEPTION", "exception_id": "ex-short-slide-label"},
    ]
    report = evaluate(bad)
    assert report.verdict == "fail", report.to_json()
    rules = {finding.rule for gate in report.gates for finding in gate.findings}
    assert {
        "SAME_NAME_SEMANTIC_COLLISION", "SAME_VALUE_DIFFERENT_UNIT",
        "OBJECT_OBSERVATION_DRIFT", "SPLIT_ROLE_CONFLICT", "CHECKER_COVERAGE_GAP",
        "REQUIRED_CHECKER_MISSING", "MATERIAL_HASH_MISSING", "MATERIAL_SECTION_MISSING",
        "MATERIAL_NOT_SCANNED", "PREMATURE_FULL_COVERAGE_CLAIM",
        "BASELINE_RUN_LOCATOR_MISSING", "BASELINE_NEW_OR_REGRESSED_UNACKED",
        "PERSISTENT_FINDING_UNTRACKED", "EXCEPTION_NOT_APPROVED",
        "CONFLICT_EXCEPTION_NOT_APPROVED", "CHANGE_IMPACT_GRAPH_MISSING",
        "STALE_PROPAGATION_MISSING", "CHANGE_BROADCAST_NOT_DONE",
        "AUTO_RESOLVED_BY_SIMILARITY", "UNRESOLVED_CONFLICT",
    } <= rules
    print("consistency_registry_gate selftest PASS: semantic objects/coverage/materials/baseline/exceptions/impact/stale")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--input")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    report = evaluate(read_json(pathlib.Path(args.input)))
    print(report.to_json())
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
