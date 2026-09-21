#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data_identity_fitness.py — 数据身份、许可/同意/DUA、split 威胁与适用性 gate。

这个脚本补 data-engineering Round3 的真缺口：把“这份数据是谁、从哪来、能不能合法用、
是否适合本研究、split 威胁是否已建模”变成可执行契约，而不是只写在 data card 里。

输入 schema（JSON）核心字段：
  schema: light.data_identity_fitness.v1
  project
  dataset: dataset_id/title/version/source_locator/source_type/snapshot_at/raw_sha256/rows/fields/unit_of_observation
  permissions: license/consent/dua/ethics_review（status=VERIFIED|NOT_APPLICABLE|UNKNOWN|RESTRICTED|PROHIBITED）
  derivation: [{step_id,input_ids,output_id,transform_locator,code_commit,input_sha256,output_sha256}]
  split_threat_model: scheme/unit/split_artifact_sha256/threats[{type,status,evidence_locator,mitigation}]
  fitness: research_question/intended_use/target_population/measurement_quality/label_quality/missingness/
           sample_power/bias_representativeness/staleness
  decision: FIT|FIT_WITH_LIMITATIONS|NOT_FIT|UNKNOWN

输出：
  - 终端 Markdown 摘要；
  - --report 写 light.findings.v1（producer=data-engineering）；
  - --json-out 写完整 light.data_identity_fitness.report.v1。

原则：
  - license/consent/DUA/ethics 未核查或禁止，不得把数据写成“可用”；
  - DERIVED 数据必须有衍生链 hash/transform/commit；
  - split threat UNKNOWN/PRESENT 均阻断 FIT（UNKNOWN=不能宣称已排除威胁）；
  - stale 可以带限制通过，但必须写影响与处理；否则阻断；
  - 这里只按声明和证据 locator 检查，不替代法务/伦理/领域专家终判。
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


SCHEMA_ID = "light.data_identity_fitness.v1"
REPORT_SCHEMA_ID = "light.data_identity_fitness.report.v1"
PERMISSION_STATUSES = {"VERIFIED", "NOT_APPLICABLE", "UNKNOWN", "RESTRICTED", "PROHIBITED"}
FITNESS_STATUSES = {"PASS", "WARN", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
THREAT_STATUSES = {"MITIGATED", "PRESENT", "UNKNOWN", "NOT_APPLICABLE"}
DECISIONS = {"FIT", "FIT_WITH_LIMITATIONS", "NOT_FIT", "UNKNOWN"}
SOURCE_TYPES = {"PUBLIC", "CONTROLLED", "PRIVATE", "DERIVED", "SYNTHETIC", "FIELD_COLLECTION", "UNKNOWN"}
CORE_THREATS = {
    "TIME_CROSSOVER",
    "GROUP_OVERLAP",
    "ENTITY_OVERLAP",
    "PREPROCESSING_BEFORE_SPLIT",
    "TARGET_LEAKAGE",
    "NEAR_DUPLICATE",
    "AUGMENTATION_LEAK",
}
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
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


def _parse_dateish(value: Any) -> dt.date | None:
    if not value:
        return None
    parsed_time = _parse_time(value)
    if parsed_time is not None:
        return parsed_time.date()
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _future_dateish(value: Any, as_of: dt.datetime) -> bool:
    parsed = _parse_dateish(value)
    return parsed is not None and parsed > as_of.date()


def _finding(loc: str, issue: str, fix: str, rule: str, evidence: str = "") -> Finding:
    return Finding(loc=loc, issue=issue, fix=fix, evidence=evidence or None, rule=rule)


def _require_fields(obj: dict[str, Any], fields: list[str], loc: str, rule: str) -> list[Finding]:
    missing = [name for name in fields if obj.get(name) in (None, "", [], {})]
    if not missing:
        return []
    return [_finding(
        loc,
        f"缺少必填字段：{missing}；数据身份/适用性不能靠口头补齐",
        "补齐字段并给可核查 locator/hash；未知就写 UNKNOWN，不得默认为可用",
        rule,
        ",".join(missing),
    )]


def _permission_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    permissions = spec.get("permissions") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []

    for name in ("license", "consent", "dua", "ethics_review"):
        item = permissions.get(name)
        loc = f"{project}:permissions.{name}"
        if not isinstance(item, dict):
            findings.append(_finding(
                loc,
                f"permissions.{name} 缺失；无法判断数据能否进入研究/公开产物",
                "声明 status，并给 locator/适用范围；不适用时显式写 NOT_APPLICABLE",
                "permission.missing",
            ))
            continue
        status = _status(item.get("status"))
        if status not in PERMISSION_STATUSES:
            findings.append(_finding(
                loc,
                f"permissions.{name}.status={status!r} 非法；必须用受控取值",
                f"改为 {sorted(PERMISSION_STATUSES)} 之一",
                "permission.bad_status",
            ))
            continue
        if status == "VERIFIED":
            if not item.get("locator"):
                findings.append(_finding(
                    loc,
                    f"{name} 标为 VERIFIED 但没有 locator；核查不可复现",
                    "补条款/批准/协议 locator；若只有口头记忆，降为 UNKNOWN",
                    "permission.verified_without_locator",
                ))
            if name == "license":
                for flag in ("allows_research", "allows_derivatives", "allows_redistribution"):
                    if item.get(flag) is not True:
                        findings.append(_finding(
                            f"{loc}.{flag}",
                            f"license 已核查但 {flag} 不是 true；不能宣称可研究/衍生/再发布全链路可用",
                            "按真实条款改研究范围，或把数据限制在允许的 sink；不能公开发布就写 restricted",
                            "license.scope_not_allowed",
                            str(item.get(flag)),
                        ))
        elif status == "NOT_APPLICABLE":
            if not item.get("reason"):
                warn.append(_finding(
                    loc,
                    f"{name}=NOT_APPLICABLE 但缺 reason；读者无法知道为什么不适用",
                    "补 reason，例如 public aggregate/no human subjects/synthetic no raw subjects",
                    "permission.not_applicable_reason_missing",
                ))
        elif status in {"UNKNOWN", "RESTRICTED", "PROHIBITED"}:
            findings.append(_finding(
                loc,
                f"{name}={status}；权限链未放行，不能把数据写成可用",
                "查清条款/同意/DUA/伦理审批；若受限，只允许对应内部 sink，公开产物必须另行核验",
                "permission.unresolved_or_blocked",
                json.dumps(item, ensure_ascii=False),
            ))

    if findings:
        return GateResult("permission_chain", "fail", "critical", findings,
                          note="许可/同意/DUA/伦理任一 UNKNOWN/RESTRICTED/PROHIBITED 或 VERIFIED 无证据 → 阻断 FIT。")
    if warn:
        return GateResult("permission_chain", "warn", "major", warn,
                          note="权限链无阻断，但 NOT_APPLICABLE 缺理由等可审计性不足。")
    return GateResult("permission_chain", "pass", "info", [],
                      note="权限链声明可核查；仍不替代法务/伦理终判。")


def _identity_lineage_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    dataset = spec.get("dataset") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []

    if spec.get("as_of") and _parse_time(spec.get("as_of")) is None:
        findings.append(_finding(
            f"{project}:as_of",
            "as_of 不是带时区 ISO-8601；无法判断快照/划分时间是否来自未来",
            "使用带时区时间，例如 2026-07-04T12:00:00+08:00；缺省时脚本使用当前运行时间",
            "dataset.as_of_bad_timestamp",
            str(spec.get("as_of")),
        ))

    findings.extend(_require_fields(
        dataset,
        ["dataset_id", "title", "version", "source_locator", "source_type", "snapshot_at",
         "raw_sha256", "rows", "fields", "unit_of_observation"],
        f"{project}:dataset",
        "dataset.identity_missing",
    ))
    source_type = _status(dataset.get("source_type"))
    if source_type and source_type not in SOURCE_TYPES:
        findings.append(_finding(
            f"{project}:dataset.source_type",
            f"source_type={source_type!r} 非法",
            f"改为 {sorted(SOURCE_TYPES)} 之一；未知写 UNKNOWN",
            "dataset.bad_source_type",
        ))
    if dataset.get("raw_sha256") and not _is_hex64(dataset.get("raw_sha256")):
        findings.append(_finding(
            f"{project}:dataset.raw_sha256",
            "raw_sha256 不是 64 位十六进制；不能锁定数据快照",
            "对原始快照计算 SHA256；若无法取得原始数据，写明原因并降为 UNKNOWN",
            "dataset.bad_hash",
            str(dataset.get("raw_sha256")),
        ))
    if dataset.get("snapshot_at") and _parse_time(dataset.get("snapshot_at")) is None:
        findings.append(_finding(
            f"{project}:dataset.snapshot_at",
            "snapshot_at 不是带时区 ISO-8601；动态数据源无法复现当天状态",
            "使用带时区时间，例如 2026-07-04T12:00:00+08:00",
            "dataset.bad_timestamp",
            str(dataset.get("snapshot_at")),
        ))
    elif _future_time(dataset.get("snapshot_at"), as_of):
        findings.append(_finding(
            f"{project}:dataset.snapshot_at",
            "snapshot_at 晚于 gate 的 as_of；数据快照不能来自未来",
            "改用实际获取/冻结快照的时间；若尚未获取，保持 UNKNOWN/NOT_FIT 而不是预填时间",
            "dataset.future_snapshot",
            str(dataset.get("snapshot_at")),
        ))
    for count_field in ("rows", "fields"):
        if dataset.get(count_field) is not None:
            try:
                if int(dataset[count_field]) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                findings.append(_finding(
                    f"{project}:dataset.{count_field}",
                    f"{count_field} 必须为正整数",
                    "补真实行/字段数；未知不要写 0 冒充",
                    "dataset.bad_count",
                    str(dataset.get(count_field)),
                ))

    derivation = spec.get("derivation") or []
    if source_type == "DERIVED" and not derivation:
        findings.append(_finding(
            f"{project}:derivation",
            "source_type=DERIVED 但没有衍生链；raw→clean→split 无法追溯",
            "为每个 transform 记录 input/output/hash/脚本 locator/commit",
            "derivation.required_for_derived",
        ))
    seen_outputs: set[str] = set()
    for idx, step in enumerate(derivation):
        loc = f"{project}:derivation[{idx}]"
        if not isinstance(step, dict):
            findings.append(_finding(loc, "derivation step 必须是 object", "改成结构化 step", "derivation.bad_step"))
            continue
        findings.extend(_require_fields(
            step,
            ["step_id", "input_ids", "output_id", "transform_locator", "code_commit",
             "input_sha256", "output_sha256"],
            loc,
            "derivation.step_missing",
        ))
        for hname in ("input_sha256", "output_sha256"):
            if step.get(hname) and not _is_hex64(step.get(hname)):
                findings.append(_finding(
                    f"{loc}.{hname}",
                    f"{hname} 不是 64 位 SHA256；衍生链不可复算",
                    "补真实 SHA256；若是多输入，写 manifest_sha256",
                    "derivation.bad_hash",
                    str(step.get(hname)),
                ))
        output = str(step.get("output_id") or "")
        if output and output in seen_outputs:
            findings.append(_finding(
                f"{loc}.output_id",
                f"output_id={output!r} 重复；衍生 DAG 不可判定",
                "为每个衍生产物给稳定唯一 ID",
                "derivation.duplicate_output",
            ))
        seen_outputs.add(output)
        if step.get("pii_handling") in (None, "") and source_type in {"PRIVATE", "CONTROLLED", "FIELD_COLLECTION"}:
            warn.append(_finding(
                f"{loc}.pii_handling",
                "受控/私有/采集数据的衍生步骤未声明 pii_handling",
                "补脱敏、聚合、最小化或不涉及 PII 的证据；最终由 research-ethics 复核",
                "derivation.pii_handling_missing",
            ))

    if findings:
        return GateResult("identity_lineage", "fail", "critical", findings,
                          note="数据身份/hash/衍生链不完整 → 不得宣称该数据快照可复现。")
    if warn:
        return GateResult("identity_lineage", "warn", "major", warn,
                          note="数据身份可追溯，但 PII 处理等衍生链说明仍需补强。")
    return GateResult("identity_lineage", "pass", "info", [],
                      note="数据身份、快照 hash 与衍生链满足最低可追溯要求。")


def _split_threat_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    split = spec.get("split_threat_model") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []

    findings.extend(_require_fields(
        split,
        ["scheme", "unit", "split_artifact_sha256", "created_at", "threats"],
        f"{project}:split_threat_model",
        "split.required_missing",
    ))
    if split.get("split_artifact_sha256") and not _is_hex64(split.get("split_artifact_sha256")):
        findings.append(_finding(
            f"{project}:split_threat_model.split_artifact_sha256",
            "split_artifact_sha256 不是 64 位 SHA256；不能锁定划分",
            "对 split manifest 或 train/test ID 列表计算 SHA256",
            "split.bad_hash",
            str(split.get("split_artifact_sha256")),
        ))
    if split.get("created_at") and _parse_time(split.get("created_at")) is None:
        findings.append(_finding(
            f"{project}:split_threat_model.created_at",
            "created_at 不是带时区 ISO-8601",
            "使用带时区时间，保证先划分后分析的时间线可审计",
            "split.bad_timestamp",
            str(split.get("created_at")),
        ))
    elif _future_time(split.get("created_at"), as_of):
        findings.append(_finding(
            f"{project}:split_threat_model.created_at",
            "created_at 晚于 gate 的 as_of；split artifact 不能来自未来",
            "使用实际创建/冻结 split manifest 的时间；尚未划分时不得声明已排除 split 威胁",
            "split.future_created_at",
            str(split.get("created_at")),
        ))

    scheme = str(split.get("scheme") or "").lower()
    if scheme == "time" and not split.get("time_col"):
        findings.append(_finding(
            f"{project}:split_threat_model.time_col",
            "scheme=time 但未声明 time_col；无法排除未来预测过去",
            "声明时间列并证明按时间排序/TimeSeriesSplit",
            "split.time_col_missing",
        ))
    if scheme == "group" and not split.get("group_col"):
        findings.append(_finding(
            f"{project}:split_threat_model.group_col",
            "scheme=group 但未声明 group_col；无法排除同一实体跨 split",
            "声明 group_col 并用 GroupKFold/实体划分",
            "split.group_col_missing",
        ))
    if scheme == "entity" and not split.get("entity_col"):
        findings.append(_finding(
            f"{project}:split_threat_model.entity_col",
            "scheme=entity 但未声明 entity_col",
            "声明 entity_col，并证明同一实体不跨训练/测试",
            "split.entity_col_missing",
        ))

    threats = split.get("threats") if isinstance(split.get("threats"), list) else []
    seen: set[str] = set()
    for idx, threat in enumerate(threats):
        loc = f"{project}:split_threat_model.threats[{idx}]"
        if not isinstance(threat, dict):
            findings.append(_finding(loc, "threat 必须是 object", "改成结构化 threat", "split.bad_threat"))
            continue
        t = _status(threat.get("type"))
        st = _status(threat.get("status"))
        if not t:
            findings.append(_finding(loc, "threat.type 缺失", "补威胁类型", "split.threat_type_missing"))
            continue
        seen.add(t)
        if st not in THREAT_STATUSES:
            findings.append(_finding(
                loc,
                f"{t}.status={st!r} 非法",
                f"改为 {sorted(THREAT_STATUSES)} 之一",
                "split.threat_bad_status",
            ))
            continue
        if st == "MITIGATED":
            if not threat.get("evidence_locator") or not threat.get("mitigation"):
                findings.append(_finding(
                    loc,
                    f"{t} 标为 MITIGATED 但缺 evidence_locator/mitigation；防泄漏不可复核",
                    "补 split_leakage/safe_split/drift 等证据 locator 与实际缓解动作",
                    "split.mitigated_without_evidence",
                ))
        elif st == "PRESENT":
            findings.append(_finding(
                loc,
                f"{t}=PRESENT；已知 split 威胁存在，结果会被污染",
                "修复 split/预处理/增强流程并重跑；不能带病放行",
                "split.threat_present",
                json.dumps(threat, ensure_ascii=False),
            ))
        elif st == "UNKNOWN":
            findings.append(_finding(
                loc,
                f"{t}=UNKNOWN；未排除该类 split 威胁，不能宣称无泄漏",
                "运行或人工核验对应检查；未知保持阻断而非冒充 pass",
                "split.threat_unknown",
            ))

    missing_core = sorted(CORE_THREATS - seen)
    if missing_core:
        warn.append(_finding(
            f"{project}:split_threat_model.threats",
            f"核心 split 威胁未逐项建模：{missing_core}",
            "至少逐项标 MITIGATED/NOT_APPLICABLE/UNKNOWN；UNKNOWN 会阻断 FIT",
            "split.core_threats_missing",
            ",".join(missing_core),
        ))

    if findings:
        return GateResult("split_threat_model", "fail", "critical", findings,
                          note="split 威胁 PRESENT/UNKNOWN 或划分证据缺失 → 阻断 FIT。")
    if warn:
        return GateResult("split_threat_model", "warn", "major", warn,
                          note="未见阻断威胁，但核心 threat matrix 不完整。")
    return GateResult("split_threat_model", "pass", "info", [],
                      note="核心 split 威胁已逐项声明并有缓解/不适用证据。")


def _fitness_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    fitness = spec.get("fitness") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []

    findings.extend(_require_fields(
        fitness,
        ["research_question", "intended_use", "target_population", "measurement_quality",
         "label_quality", "missingness", "sample_power", "bias_representativeness", "staleness"],
        f"{project}:fitness",
        "fitness.required_missing",
    ))

    for axis in ("measurement_quality", "label_quality", "missingness", "sample_power",
                 "bias_representativeness"):
        item = fitness.get(axis)
        loc = f"{project}:fitness.{axis}"
        if not isinstance(item, dict):
            continue
        status = _status(item.get("status"))
        if status not in FITNESS_STATUSES:
            findings.append(_finding(
                loc,
                f"{axis}.status={status!r} 非法",
                f"改为 {sorted(FITNESS_STATUSES)} 之一",
                "fitness.bad_status",
            ))
            continue
        if status in {"FAIL", "UNKNOWN"}:
            findings.append(_finding(
                loc,
                f"{axis}={status}；数据适用性不足或未知，不能宣称支撑该研究问题",
                "补质检/标注一致性/缺失机制/功效/代表性证据；未知就先 UNKNOWN/NOT_FIT",
                "fitness.axis_blocked",
                json.dumps(item, ensure_ascii=False),
            ))
        elif status == "WARN":
            if not item.get("limitation") and not item.get("mitigation"):
                findings.append(_finding(
                    loc,
                    f"{axis}=WARN 但没有 limitation/mitigation；限制不能只藏在脑子里",
                    "写清限制、影响方向和缓解/敏感性分析",
                    "fitness.warn_without_limitation",
                ))
            else:
                warn.append(_finding(
                    loc,
                    f"{axis}=WARN；数据只能带限制使用",
                    "在 data card/result/paper 中显式带限制，不得写成无条件可用",
                    "fitness.axis_warn",
                    json.dumps(item, ensure_ascii=False),
                ))

    stale = fitness.get("staleness")
    if isinstance(stale, dict):
        st = _status(stale.get("status"))
        if st not in {"CURRENT", "STALE", "UNKNOWN", "NOT_APPLICABLE"}:
            findings.append(_finding(
                f"{project}:fitness.staleness",
                f"staleness.status={st!r} 非法",
                "改为 CURRENT/STALE/UNKNOWN/NOT_APPLICABLE",
                "staleness.bad_status",
            ))
        elif st == "UNKNOWN":
            findings.append(_finding(
                f"{project}:fitness.staleness",
                "数据 freshness/valid-at 未知；动态数据可能已过期，不能写成当前有效",
                "补 data_valid_at/freshness_policy；不知道就阻断或改写为 UNKNOWN",
                "staleness.unknown",
            ))
        if stale.get("data_valid_at") and _future_dateish(stale.get("data_valid_at"), as_of):
            findings.append(_finding(
                f"{project}:fitness.staleness.data_valid_at",
                "data_valid_at 晚于 gate 的 as_of；未来有效期不能证明当前数据可用",
                "写实际可核查的 valid-at 日期；若有效性尚未发生或未核验，保持 UNKNOWN/NOT_FIT",
                "staleness.future_data_valid_at",
                str(stale.get("data_valid_at")),
            ))
        elif st == "STALE":
            if not stale.get("impact") or not stale.get("mitigation"):
                findings.append(_finding(
                    f"{project}:fitness.staleness",
                    "数据已 stale 但缺 impact/mitigation；不能判断是否仍适合当前研究",
                    "写明过期影响、更新计划或为何仍可用于历史问题",
                    "staleness.stale_without_impact",
                ))
            else:
                warn.append(_finding(
                    f"{project}:fitness.staleness",
                    "数据已 stale；仅可带限制使用",
                    "在结论与 data card 中保留 valid-at/impact/mitigation，不得写成当前实时代表",
                    "staleness.stale_with_impact",
                    json.dumps(stale, ensure_ascii=False),
                ))

    limitations = fitness.get("limitations") or []
    if warn and not limitations:
        findings.append(_finding(
            f"{project}:fitness.limitations",
            "存在 WARN/STALE 适用性限制，但 fitness.limitations 为空",
            "把所有限制下沉到 limitations，供 result-analysis/paper-writing 消费",
            "fitness.limitations_missing",
        ))

    if findings:
        return GateResult("fitness_for_purpose", "fail", "critical", findings,
                          note="数据质量/缺失/功效/代表性/时效任一 FAIL/UNKNOWN 或限制未登记 → 阻断 FIT。")
    if warn:
        return GateResult("fitness_for_purpose", "warn", "major", warn,
                          note="数据可带限制使用；下游必须继承 limitations。")
    return GateResult("fitness_for_purpose", "pass", "info", [],
                      note="数据适用性最低证据齐全；不代表外推性已由脚本终判。")


def _decision_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    decision = _status(spec.get("decision"))
    if decision not in DECISIONS:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(
                f"{project}:decision",
                f"decision={decision!r} 非法或缺失",
                f"改为 {sorted(DECISIONS)} 之一；不要空着让下游猜",
                "decision.bad_status",
            )
        ], note="数据门必须给明确 FIT/NOT_FIT/UNKNOWN 裁定。")

    blocking_gates = [
        g for g in art["pre_decision_gates"]
        if g.status == "fail" and g.severity == "critical"
    ]
    warn_gates = [g for g in art["pre_decision_gates"] if g.status == "warn"]
    if decision in {"NOT_FIT", "UNKNOWN"}:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(
                f"{project}:decision",
                f"decision={decision}；数据门已声明不能推进或仍未知，流水线不得放行",
                "补数据/换数据/改 idea 后重跑 gate；只有 FIT 或 FIT_WITH_LIMITATIONS 才能进入下游",
                "decision.blocks_advancement",
            )
        ], note="NOT_FIT/UNKNOWN 是阻断性裁定，不是可推进状态。")
    if blocking_gates and decision in {"FIT", "FIT_WITH_LIMITATIONS"}:
        blockers = ",".join(g.gate for g in blocking_gates)
        return GateResult("declared_decision", "fail", "critical", [
            _finding(
                f"{project}:decision",
                f"存在 critical blockers({blockers}) 却声明 {decision}；名实不符",
                "把 decision 改为 NOT_FIT/UNKNOWN，或先修复 blockers 并重跑 gate",
                "decision.overrides_blockers",
                blockers,
            )
        ], note="裁定不得覆盖硬阻断。")
    if warn_gates and decision == "FIT":
        warns = ",".join(g.gate for g in warn_gates)
        return GateResult("declared_decision", "warn", "major", [
            _finding(
                f"{project}:decision",
                f"存在限制性 warn({warns}) 但声明 FIT；更诚实的是 FIT_WITH_LIMITATIONS",
                "改为 FIT_WITH_LIMITATIONS，并把 limitations 传给下游",
                "decision.should_be_limited",
                warns,
            )
        ], note="有已知限制时不应无条件 FIT。")
    if decision == "FIT_WITH_LIMITATIONS" and not warn_gates:
        limitations = (spec.get("fitness") or {}).get("limitations") or []
        if not limitations:
            return GateResult("declared_decision", "fail", "critical", [
                _finding(
                    f"{project}:decision",
                    "decision=FIT_WITH_LIMITATIONS 但 fitness.limitations 为空；限制未下沉给下游",
                    "写清限制、影响方向和下游处理要求；若没有限制则改为 FIT",
                    "decision.limited_without_limitations",
                )
            ], note="带限制放行必须把限制写成下游可消费的字段。")
        return GateResult("declared_decision", "warn", "major", [
            _finding(
                f"{project}:decision",
                "decision=FIT_WITH_LIMITATIONS；虽无前置 warn gate，但用户/领域限制需要下游继承",
                "把 fitness.limitations 传给 research-plan/result-analysis/paper-writing，不得在摘要里消失",
                "decision.explicit_limitations",
                "; ".join(map(str, limitations)),
            )
        ], note="显式限制会让整体 verdict 保持 warn，防止无条件放行。")
    return GateResult("declared_decision", "pass", "info", [],
                      note=f"decision={decision} 与前置 gate 一致。")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") not in (SCHEMA_ID, None):
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    project = str(spec.get("project") or "unknown-project")
    art = {"spec": spec, "project": project, "as_of": _resolve_as_of(spec)}
    pre = [
        _identity_lineage_gate(art),
        _permission_gate(art),
        _split_threat_gate(art),
        _fitness_gate(art),
    ]
    art["pre_decision_gates"] = pre
    gates = pre + [_decision_gate(art)]
    report = FindingsReport(
        producer="data-engineering",
        target=project,
        gates=gates,
        summary=("data identity/permission/lineage/split-threat/fitness gate: "
                 "unknown is not pass; permissions and split threats are critical blockers"),
        fresh_evidence=True,
    ).finalize()

    blocking = report.blocking_gates()
    if blocking:
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
        "blocking_gates": [g.gate for g in blocking],
        "findings": report.to_dict(),
    }


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# data-engineering 数据身份与适用性 gate：{result['project']}",
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
    lines.append("> 诚实边界：本 gate 检查声明、locator、hash、威胁模型和适用性证据是否完整；不替代法务、伦理或领域终判。")
    return "\n".join(lines)


def _h() -> str:
    return "a" * 64


def _good_spec() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "project": "selftest-data",
        "dataset": {
            "dataset_id": "ds-v1",
            "title": "Public sensor benchmark",
            "version": "2026-07-01",
            "source_locator": "https://example.org/dataset-card",
            "source_type": "PUBLIC",
            "snapshot_at": "2026-07-04T09:00:00+08:00",
            "raw_sha256": _h(),
            "rows": 1200,
            "fields": 24,
            "unit_of_observation": "sensor-window",
        },
        "permissions": {
            "license": {
                "status": "VERIFIED",
                "name": "CC-BY-4.0",
                "locator": "https://example.org/license",
                "allows_research": True,
                "allows_derivatives": True,
                "allows_redistribution": True,
            },
            "consent": {"status": "NOT_APPLICABLE", "reason": "public non-human aggregate"},
            "dua": {"status": "NOT_APPLICABLE", "reason": "public open dataset"},
            "ethics_review": {"status": "NOT_APPLICABLE", "reason": "no human subjects"},
        },
        "derivation": [],
        "split_threat_model": {
            "scheme": "group",
            "unit": "farm",
            "group_col": "farm_id",
            "split_artifact_sha256": _h(),
            "created_at": "2026-07-04T09:30:00+08:00",
            "threats": [
                {"type": t, "status": "MITIGATED", "evidence_locator": f"audit:{t}", "mitigation": "checked"}
                for t in sorted(CORE_THREATS)
            ],
        },
        "fitness": {
            "research_question": "Can model X detect event Y from sensor windows?",
            "intended_use": "benchmark method comparison",
            "target_population": "public benchmark farms",
            "measurement_quality": {"status": "PASS", "evidence_locator": "quality.md"},
            "label_quality": {"status": "PASS", "evidence_locator": "iaa.md"},
            "missingness": {"status": "PASS", "evidence_locator": "missingness.md"},
            "sample_power": {"status": "PASS", "evidence_locator": "power.md"},
            "bias_representativeness": {"status": "PASS", "evidence_locator": "bias.md"},
            "staleness": {"status": "CURRENT", "data_valid_at": "2026-07-01", "freshness_policy": "annual"},
            "limitations": [],
        },
        "decision": "FIT",
    }


def _selftest() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good = evaluate(_good_spec())
    check(good["status"] == "PASS", f"good spec 应 PASS，得 {good['status']}")
    check(good["findings"]["schema"] == "light.findings.v1", "应产 light.findings.v1")
    check(good["findings"]["producer"] == "data-engineering", "producer 应为 data-engineering")

    unknown_license = _good_spec()
    unknown_license["permissions"]["license"] = {"status": "UNKNOWN"}
    unknown_license["decision"] = "FIT"
    r2 = evaluate(unknown_license)
    check(r2["status"] == "FAIL" and "permission_chain" in r2["blocking_gates"],
          "license UNKNOWN 应阻断")
    dec_gate = next(g for g in r2["findings"]["gates"] if g["gate"] == "declared_decision")
    check(dec_gate["status"] == "fail", "存在 blocker 却声明 FIT 应 decision fail")

    leaky = _good_spec()
    leaky["split_threat_model"]["threats"][0]["status"] = "PRESENT"
    r3 = evaluate(leaky)
    check(r3["status"] == "FAIL" and "split_threat_model" in r3["blocking_gates"],
          "PRESENT split threat 应阻断")

    derived = _good_spec()
    derived["dataset"]["source_type"] = "DERIVED"
    derived["derivation"] = []
    r4 = evaluate(derived)
    check(r4["status"] == "FAIL" and "identity_lineage" in r4["blocking_gates"],
          "DERIVED 无衍生链应阻断")

    stale = _good_spec()
    stale["fitness"]["staleness"] = {
        "status": "STALE",
        "data_valid_at": "2024-01-01",
        "freshness_policy": "annual",
        "impact": "Only historical claims, not current prevalence",
        "mitigation": "state valid-at and rerun if current claims are needed",
    }
    stale["fitness"]["limitations"] = ["Historical snapshot only"]
    stale["decision"] = "FIT_WITH_LIMITATIONS"
    r5 = evaluate(stale)
    check(r5["status"] == "WARN" and r5["advancement"] == "ALLOW_WITH_LIMITATIONS",
          f"stale with impact 应 warn 可带限制通过，得 {r5['status']}/{r5['advancement']}")

    pbad = _good_spec()
    pbad["permissions"]["license"]["allows_derivatives"] = False
    r6 = evaluate(pbad)
    check(r6["status"] == "FAIL", "license 不允许衍生应阻断")

    bad_time = _good_spec()
    bad_time["dataset"]["snapshot_at"] = "2026-07-04 09:00"
    r7 = evaluate(bad_time)
    check(r7["status"] == "FAIL", "无时区 snapshot_at 应阻断")

    future = _good_spec()
    future["as_of"] = "2026-07-04T10:00:00+08:00"
    future["dataset"]["snapshot_at"] = "2999-01-01T00:00:00+00:00"
    future["split_threat_model"]["created_at"] = "2999-01-01T00:00:00+00:00"
    future["fitness"]["staleness"]["data_valid_at"] = "2999-01-01"
    r8 = evaluate(future)
    rules = {
        finding["rule"]
        for gate in r8["findings"]["gates"]
        for finding in gate["findings"]
    }
    check(
        {
            "dataset.future_snapshot",
            "split.future_created_at",
            "staleness.future_data_valid_at",
        } <= rules,
        "未来 snapshot/split/data_valid_at 应全部阻断",
    )

    not_fit = _good_spec()
    not_fit["decision"] = "NOT_FIT"
    r9 = evaluate(not_fit)
    check(r9["status"] == "FAIL" and "declared_decision" in r9["blocking_gates"],
          "decision=NOT_FIT 应阻断推进")

    limited_missing = _good_spec()
    limited_missing["decision"] = "FIT_WITH_LIMITATIONS"
    r10 = evaluate(limited_missing)
    check(r10["status"] == "FAIL" and "declared_decision" in r10["blocking_gates"],
          "FIT_WITH_LIMITATIONS 无 limitations 应 fail")

    limited = _good_spec()
    limited["decision"] = "FIT_WITH_LIMITATIONS"
    limited["fitness"]["limitations"] = ["external validity limited to public benchmark farms"]
    r11 = evaluate(limited)
    check(r11["status"] == "WARN" and r11["advancement"] == "ALLOW_WITH_LIMITATIONS",
          "显式 FIT_WITH_LIMITATIONS 应 warn 并带限制放行")

    check("数据身份与适用性 gate" in to_markdown(good), "markdown 应含标题")

    if failures:
        print("[SELFTEST][data_identity_fitness] FAIL:")
        for item in failures:
            print("  -", item)
        return 1
    print("[SELFTEST][data_identity_fitness] OK: clean pass / unknown permission / split threat / "
          "derived lineage / stale limitations / license scope / timezone / future dates / "
          "declared decision all checked")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate data identity, permissions, lineage, split threats, and fitness")
    parser.add_argument("--spec", help="light.data_identity_fitness.v1 JSON")
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
