#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_card_gate.py — result card + analysis decision ledger 的机器门。

这个脚本补 result-analysis Round3 的真缺口：把每条结果解释必须具备的 target、analysis set、
missingness、assumption、comparison family、practical threshold，以及“哪些分析选择是结果后做的”
变成可执行契约。

输入 schema（JSON）核心字段：
  schema: light.result_card.v1
  project
  plan_lock: status/locked_at/results_available_at/locator/sha256
  result_card:
    claim_id/target_claim/target_type/estimand_or_hypothesis/metric/comparison_family/family_size/correction
    analysis_set{name,n,unit,missingness{rate,mechanism,handling,sensitivity_id}}
    provenance{source_run_ids,run_manifest_locator,run_manifest_sha256,raw_result_locator,raw_result_sha256,
               analysis_code_locator,analysis_code_sha256,computed_at,owner_skill}
    practical_threshold{metric,value,direction,justification_locator}
    assumption_checks[{assumption,status,evidence_locator}]
    guardrail_analysis{required,evidence_locator,evidence_sha256,
                       checks[{id,metric,status,observed,threshold,claim_impact,evidence_locator}]}
    effect{estimate,effect_size,ci95,p,q,direction,practical_significance}
    language{conclusion,strength,near_threshold_wording}
  decision_ledger:
    [{decision_id,timing,kind,planned,classification,affected_claim_ids,rationale,evidence_locator}]
  sensitivity:
    [{id,target_same_as_primary,changes_primary_estimand,changes_analysis_family,classification}]
  decision: CLAIM_READY|REVISION_REQUIRED|UNKNOWN

硬规则：
  - q/p/CI/效应量/实际阈值不能缺；多比较 family_size>1 必须有校正和 q；
  - q>=.05 或 CI 含 0 时，语言不得写“显著优于/证明/提升”；
  - p 或 q 在 0.045~0.055 附近时，语言必须降档并显式说明阈值敏感；
  - POST_RESULTS 的 EXCLUSION/METRIC/MODEL_CHOICE/SUBGROUP 等不得 classified=CONFIRMATORY；
  - sensitivity 与 supplementary 的分类必须由“是否同 target/是否改变 estimand/family”决定；
  - guardrail/counter-metric FAIL 或 UNKNOWN 不得 CLAIM_READY；
  - CLAIM_READY 不得覆盖任何 critical blocker。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SCHEMA_ID = "light.result_card.v1"
REPORT_SCHEMA_ID = "light.result_card.report.v1"
PLAN_STATUSES = {"FROZEN", "AMENDED", "EXPLORATORY"}
TARGET_TYPES = {"PRIMARY", "SECONDARY", "EXPLORATORY", "SENSITIVITY", "SUPPLEMENTARY"}
CORRECTIONS = {"BH", "BONFERRONI", "HOLM", "NONE", "NOT_APPLICABLE"}
ASSUMPTION_STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
GUARDRAIL_STATUSES = {"PASS", "FAIL", "WARN", "UNKNOWN", "NOT_APPLICABLE"}
LEDGER_TIMING = {"PRE_RESULTS", "POST_RESULTS"}
LEDGER_CLASSES = {"CONFIRMATORY", "SENSITIVITY", "SUPPLEMENTARY", "EXPLORATORY"}
DECISIONS = {"CLAIM_READY", "REVISION_REQUIRED", "UNKNOWN"}
POST_RESULT_CONFIRMATORY_RISK = {
    "EXCLUSION", "MODEL_CHOICE", "TRANSFORM", "OUTLIER_RULE", "SUBGROUP",
    "METRIC", "ANALYSIS_SET", "COVARIATE", "THRESHOLD",
}
STRONG_LANGUAGE = {
    "DEMONSTRATES", "PROVES", "ESTABLISHES", "SIGNIFICANTLY_IMPROVES",
    "IMPROVES", "SUPERIOR", "BETTER",
}
SAFE_NONSIG_STRENGTHS = {"NO_SIGNIFICANT_DIFFERENCE", "INCONCLUSIVE", "DESCRIPTIVE_ONLY"}
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_CLOCK_SKEW = dt.timedelta(minutes=5)
STRONG_WORD_RE = re.compile(
    r"\b(prov(e|es|ed|ing)|demonstrat(e|es|ed|ing)|significant(ly)?|superior|better|improv(e|es|ed|ing)|"
    r"outperform(s|ed|ing)?|有效|证明|显著|优于|提升|更好)\b",
    re.IGNORECASE,
)
UNCERTAIN_WORD_RE = re.compile(r"(threshold|borderline|sensitive|inconclusive|uncertain|阈值|边界|敏感|不确定|未见显著)")


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


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def _ci_contains_zero(ci: Any) -> bool | None:
    if not isinstance(ci, list) or len(ci) != 2:
        return None
    lo, hi = _num(ci[0]), _num(ci[1])
    if lo is None or hi is None:
        return None
    return min(lo, hi) <= 0 <= max(lo, hi)


def _finding(loc: str, issue: str, fix: str, rule: str, evidence: str = "") -> Finding:
    return Finding(loc=loc, issue=issue, fix=fix, evidence=evidence or None, rule=rule)


def _require_fields(obj: dict[str, Any], fields: list[str], loc: str, rule: str) -> list[Finding]:
    missing = [name for name in fields if obj.get(name) in (None, "", [], {})]
    if not missing:
        return []
    return [_finding(
        loc,
        f"缺少必填字段：{missing}；result card 不完整，claim 不能进入写作",
        "补齐 target/analysis set/missingness/assumption/family/effect/practical threshold 等字段",
        rule,
        ",".join(missing),
    )]


def _plan_lock_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    plan = spec.get("plan_lock") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:plan_lock"

    if spec.get("as_of") and _parse_time(spec.get("as_of")) is None:
        findings.append(_finding(
            f"{project}:as_of",
            "as_of 不是带时区 ISO-8601；无法判断计划锁/结果/分析时间是否来自未来",
            "使用带时区时间，例如 2026-07-04T12:00:00+08:00；缺省时脚本使用当前运行时间",
            "plan_lock.as_of_bad_timestamp",
            str(spec.get("as_of")),
        ))

    findings.extend(_require_fields(
        plan, ["status", "locked_at", "results_available_at", "locator", "sha256"],
        loc, "plan_lock.required_missing"))
    status = _status(plan.get("status"))
    if status and status not in PLAN_STATUSES:
        findings.append(_finding(loc, f"plan_lock.status={status!r} 非法", "使用 FROZEN/AMENDED/EXPLORATORY", "plan_lock.bad_status"))
    if status == "EXPLORATORY":
        warn.append(_finding(
            loc,
            "plan_lock.status=EXPLORATORY；结果只能当探索性，不得写成 confirmatory",
            "所有主张降为 exploratory/descriptive，或提供真实结果前冻结计划",
            "plan_lock.exploratory",
        ))
    if plan.get("sha256") and not _is_hex64(plan.get("sha256")):
        findings.append(_finding(loc, "plan_lock.sha256 不是 64 位 SHA256", "对冻结分析计划计算 SHA256", "plan_lock.bad_hash"))
    locked = _parse_time(plan.get("locked_at"))
    results_at = _parse_time(plan.get("results_available_at"))
    if plan.get("locked_at") and locked is None:
        findings.append(_finding(loc, "locked_at 不是带时区 ISO-8601", "使用带时区时间", "plan_lock.bad_timestamp", str(plan.get("locked_at"))))
    if plan.get("results_available_at") and results_at is None:
        findings.append(_finding(loc, "results_available_at 不是带时区 ISO-8601", "使用带时区时间", "plan_lock.bad_timestamp", str(plan.get("results_available_at"))))
    if _future_time(plan.get("locked_at"), as_of):
        findings.append(_finding(
            loc,
            "locked_at 晚于 gate 的 as_of；分析计划锁定时间不能来自未来",
            "写真实计划锁定时间；尚未锁定时保持 EXPLORATORY/REVISION_REQUIRED",
            "plan_lock.future_locked_at",
            str(plan.get("locked_at")),
        ))
    if _future_time(plan.get("results_available_at"), as_of):
        findings.append(_finding(
            loc,
            "results_available_at 晚于 gate 的 as_of；结果可见时间不能来自未来",
            "写真实结果可见/交付时间；尚未得到结果时不得 CLAIM_READY",
            "plan_lock.future_results_available_at",
            str(plan.get("results_available_at")),
        ))
    if locked and results_at and locked > results_at:
        findings.append(_finding(
            loc,
            "分析计划冻结时间晚于结果可见时间；不能冒充 a-priori/confirmatory",
            "保留真实变更日志，将相关分析标为 exploratory/sensitivity",
            "plan_lock.locked_after_results",
            f"locked_at={plan.get('locked_at')};results_available_at={plan.get('results_available_at')}",
        ))

    if findings:
        return GateResult("plan_lock", "fail", "critical", findings,
                          note="计划锁缺失/时间线倒置/hash 无效 → confirmatory claim 阻断。")
    if warn:
        return GateResult("plan_lock", "warn", "major", warn,
                          note="计划为探索性或有修订；下游措辞必须降档。")
    return GateResult("plan_lock", "pass", "info", [], note="计划锁与时间线可审计。")


def _result_card_completeness_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    as_of = art["as_of"]
    card = spec.get("result_card") or {}
    findings: list[Finding] = []
    warn: list[Finding] = []
    loc = f"{project}:result_card"

    findings.extend(_require_fields(
        card,
        ["claim_id", "target_claim", "target_type", "estimand_or_hypothesis", "metric",
         "comparison_family", "family_size", "correction", "analysis_set",
         "provenance", "practical_threshold", "assumption_checks", "effect", "language"],
        loc,
        "result_card.required_missing",
    ))
    if "guardrail_analysis" not in card:
        findings.append(_finding(
            f"{loc}.guardrail_analysis",
            "缺 guardrail_analysis；无法判断 experiment-coding 交来的 guardrail/counter-metric 是否被结果解释消费",
            "显式写 required=true/false；required=true 时绑定 guardrail evidence 和逐项状态，false 时写不适用理由",
            "guardrail_analysis.missing",
        ))
    target_type = _status(card.get("target_type"))
    if target_type and target_type not in TARGET_TYPES:
        findings.append(_finding(loc, f"target_type={target_type!r} 非法", f"改为 {sorted(TARGET_TYPES)}", "result_card.bad_target_type"))
    correction = _status(card.get("correction"))
    if correction and correction not in CORRECTIONS:
        findings.append(_finding(loc, f"correction={correction!r} 非法", f"改为 {sorted(CORRECTIONS)}", "result_card.bad_correction"))
    try:
        family_size = int(card.get("family_size", 0))
    except (TypeError, ValueError):
        family_size = 0
    if family_size <= 0:
        findings.append(_finding(loc, "family_size 必须为正整数", "声明同一 comparison family 的比较总数", "result_card.bad_family_size"))
    elif family_size > 1 and correction in {"", "NONE", "NOT_APPLICABLE"}:
        findings.append(_finding(
            f"{loc}.correction",
            f"family_size={family_size} 但 correction={correction or 'missing'}；多重比较未校正",
            "对完整 family 做 BH/Bonferroni/Holm，并以 q 为准",
            "multiplicity.correction_missing",
        ))

    analysis_set = card.get("analysis_set") or {}
    if isinstance(analysis_set, dict):
        findings.extend(_require_fields(
            analysis_set, ["name", "n", "unit", "missingness"],
            f"{loc}.analysis_set", "analysis_set.required_missing"))
        try:
            n = int(analysis_set.get("n", 0))
            if n <= 0:
                raise ValueError
        except (TypeError, ValueError):
            findings.append(_finding(f"{loc}.analysis_set.n", "analysis_set.n 必须为正整数", "补真实统计单位数", "analysis_set.bad_n"))
        missing = analysis_set.get("missingness") or {}
        if isinstance(missing, dict):
            rate = _num(missing.get("rate"))
            mechanism = _status(missing.get("mechanism"))
            if rate is None or not (0 <= rate <= 1):
                findings.append(_finding(f"{loc}.analysis_set.missingness", "missingness.rate 必须是 0~1 数值", "补缺失率", "missingness.bad_rate"))
            if mechanism in {"", "UNKNOWN"}:
                findings.append(_finding(
                    f"{loc}.analysis_set.missingness",
                    "缺失机制 UNKNOWN；缺失可能改变 target/estimand，不能直接下主结论",
                    "说明 MCAR/MAR/MNAR 假设、处理方式与敏感性分析",
                    "missingness.unknown_mechanism",
                ))
            if rate is not None and rate > 0.05 and not missing.get("sensitivity_id"):
                findings.append(_finding(
                    f"{loc}.analysis_set.missingness",
                    f"missingness.rate={rate:.3g}>5% 但没有 sensitivity_id",
                    "补缺失处理敏感性分析，或降级为探索性/限制性结论",
                    "missingness.sensitivity_missing",
                ))
            if not missing.get("handling"):
                findings.append(_finding(f"{loc}.analysis_set.missingness", "缺失处理 handling 为空", "说明 complete-case/imputation/IPW 等处理", "missingness.handling_missing"))

    provenance = card.get("provenance") or {}
    if isinstance(provenance, dict):
        findings.extend(_require_fields(
            provenance,
            [
                "source_run_ids", "run_manifest_locator", "run_manifest_sha256",
                "raw_result_locator", "raw_result_sha256", "analysis_code_locator",
                "analysis_code_sha256", "computed_at", "owner_skill",
            ],
            f"{loc}.provenance",
            "provenance.required_missing",
        ))
        if not isinstance(provenance.get("source_run_ids"), list) or not provenance.get("source_run_ids"):
            findings.append(_finding(
                f"{loc}.provenance.source_run_ids",
                "source_run_ids 必须是非空列表",
                "把 claim 绑定到 experiment-coding 的 run_id/attempt；孤立结果数字不能进写作",
                "provenance.source_runs_missing",
            ))
        for key in ("run_manifest_sha256", "raw_result_sha256", "analysis_code_sha256"):
            if provenance.get(key) and not _is_hex64(provenance.get(key)):
                findings.append(_finding(
                    f"{loc}.provenance.{key}",
                    f"{key} 不是 64 位 SHA256",
                    "对对应 artifact 计算 SHA256；UNKNOWN 不得冒充可追溯结果",
                    "provenance.bad_hash",
                ))
        if provenance.get("computed_at") and _parse_time(provenance.get("computed_at")) is None:
            findings.append(_finding(
                f"{loc}.provenance.computed_at",
                "computed_at 不是带时区 ISO-8601",
                "记录带时区的分析执行时间，供 consistency/memory-pm 回扫",
                "provenance.bad_timestamp",
            ))
        elif _future_time(provenance.get("computed_at"), as_of):
            findings.append(_finding(
                f"{loc}.provenance.computed_at",
                "computed_at 晚于 gate 的 as_of；分析计算时间不能来自未来",
                "写真实分析执行时间；尚未计算完成时不得 CLAIM_READY",
                "provenance.future_computed_at",
                str(provenance.get("computed_at")),
            ))
        computed = _parse_time(provenance.get("computed_at"))
        results_at = _parse_time((spec.get("plan_lock") or {}).get("results_available_at"))
        if computed and results_at and computed < results_at:
            findings.append(_finding(
                f"{loc}.provenance.computed_at",
                "computed_at 早于 results_available_at；分析不能在结果可见前完成",
                "修正结果可见时间/分析执行时间；若为预计算模板，不能作为真实 result card provenance",
                "provenance.computed_before_results",
                f"computed_at={provenance.get('computed_at')};results_available_at={(spec.get('plan_lock') or {}).get('results_available_at')}",
            ))
        if _status(provenance.get("owner_skill")) != "RESULT-ANALYSIS":
            findings.append(_finding(
                f"{loc}.provenance.owner_skill",
                f"owner_skill={provenance.get('owner_skill')!r}；result card 应由 result-analysis 归口",
                "写 RESULT-ANALYSIS；上游 run 只提供 raw evidence，不替本技能下统计结论",
                "provenance.owner_mismatch",
            ))
    else:
        findings.append(_finding(f"{loc}.provenance", "provenance 必须是 object", "补 run/raw/code provenance", "provenance.bad_type"))

    threshold = card.get("practical_threshold") or {}
    if isinstance(threshold, dict):
        findings.extend(_require_fields(
            threshold, ["metric", "value", "direction", "justification_locator"],
            f"{loc}.practical_threshold", "practical_threshold.required_missing"))
        if threshold.get("value") is not None and _num(threshold.get("value")) is None:
            findings.append(_finding(f"{loc}.practical_threshold.value", "practical threshold value 不是数值", "补可比较数值阈值", "practical_threshold.bad_value"))

    assumptions = card.get("assumption_checks") or []
    if isinstance(assumptions, list):
        if not assumptions:
            findings.append(_finding(f"{loc}.assumption_checks", "assumption_checks 为空", "至少列出关键模型/统计假设及证据", "assumption.empty"))
        for idx, item in enumerate(assumptions):
            aloc = f"{loc}.assumption_checks[{idx}]"
            if not isinstance(item, dict):
                findings.append(_finding(aloc, "assumption check 必须是 object", "改为结构化记录", "assumption.bad_item"))
                continue
            st = _status(item.get("status"))
            if st not in ASSUMPTION_STATUSES:
                findings.append(_finding(aloc, f"assumption status={st!r} 非法", f"改为 {sorted(ASSUMPTION_STATUSES)}", "assumption.bad_status"))
            elif st in {"FAIL", "UNKNOWN"}:
                findings.append(_finding(
                    aloc,
                    f"关键假设 {item.get('assumption', idx)!r}={st}；结果解释不能无条件通过",
                    "补诊断/稳健检验，或把 claim 降为 exploratory/limitation",
                    "assumption.not_satisfied",
                    json.dumps(item, ensure_ascii=False),
                ))
            elif st == "PASS" and not item.get("evidence_locator"):
                findings.append(_finding(aloc, "assumption PASS 但缺 evidence_locator", "补诊断图/检验/日志 locator", "assumption.pass_without_evidence"))

    guardrails = card.get("guardrail_analysis") or {}
    if isinstance(guardrails, dict) and guardrails:
        required = guardrails.get("required")
        if not isinstance(required, bool):
            findings.append(_finding(
                f"{loc}.guardrail_analysis.required",
                "guardrail_analysis.required 必须是 boolean",
                "若上游 failure-tree 要求 guardrail，写 true；确实不适用写 false + rationale",
                "guardrail.required_bad_type",
            ))
        if required is False:
            if not guardrails.get("not_applicable_rationale"):
                findings.append(_finding(
                    f"{loc}.guardrail_analysis.not_applicable_rationale",
                    "required=false 但缺 not_applicable_rationale",
                    "说明为什么本 result card 没有 guardrail/counter-metric；不能靠省略跳过",
                    "guardrail.no_rationale",
                ))
        else:
            for key in ("evidence_locator", "evidence_sha256"):
                if not guardrails.get(key):
                    findings.append(_finding(
                        f"{loc}.guardrail_analysis.{key}",
                        f"guardrail_analysis 缺 {key}",
                        "绑定 experiment-coding run bundle 中的 guardrails.json / guardrail_evidence artifact",
                        "guardrail.evidence_missing",
                    ))
            if guardrails.get("evidence_sha256") and not _is_hex64(guardrails.get("evidence_sha256")):
                findings.append(_finding(
                    f"{loc}.guardrail_analysis.evidence_sha256",
                    "guardrail evidence SHA256 不是 64 位 hex",
                    "对 guardrails.json / guardrail evidence artifact 计算 SHA256",
                    "guardrail.bad_hash",
                ))
            checks = guardrails.get("checks")
            if not isinstance(checks, list) or not checks:
                findings.append(_finding(
                    f"{loc}.guardrail_analysis.checks",
                    "required=true 但缺逐项 guardrail checks",
                    "每个 guardrail/counter-metric 写 id、metric、status、observed、threshold、claim_impact、evidence_locator",
                    "guardrail.checks_missing",
                ))
            else:
                for idx, item in enumerate(checks):
                    gloc = f"{loc}.guardrail_analysis.checks[{idx}]"
                    if not isinstance(item, dict):
                        findings.append(_finding(gloc, "guardrail check 必须是 object", "改为结构化 check", "guardrail.bad_item"))
                        continue
                    findings.extend(_require_fields(
                        item,
                        ["id", "metric", "status", "observed", "threshold", "claim_impact", "evidence_locator"],
                        gloc,
                        "guardrail.check_required_missing",
                    ))
                    st = _status(item.get("status"))
                    if st not in GUARDRAIL_STATUSES:
                        findings.append(_finding(gloc, f"guardrail status={st!r} 非法", f"改为 {sorted(GUARDRAIL_STATUSES)}", "guardrail.bad_status"))
                    elif st in {"FAIL", "UNKNOWN"}:
                        findings.append(_finding(
                            gloc,
                            f"guardrail {item.get('id', idx)!r}={st}；不能无条件 claim ready",
                            "按 failure-tree 的 kill_action/claim_impact 降 claim、回 research-plan 或报告无结论",
                            "guardrail.not_satisfied",
                            json.dumps(item, ensure_ascii=False),
                        ))
                    elif st == "WARN":
                        warn.append(_finding(
                            gloc,
                            f"guardrail {item.get('id', idx)!r}=WARN；结论必须带限制",
                            "在 language/claim impact 中写明限制，必要时转 exploratory",
                            "guardrail.warn",
                        ))
                    elif st == "PASS" and not item.get("evidence_locator"):
                        findings.append(_finding(gloc, "guardrail PASS 但缺 evidence_locator", "补 guardrails.json 或监控报告 locator", "guardrail.pass_without_evidence"))
    elif "guardrail_analysis" in card:
        findings.append(_finding(
            f"{loc}.guardrail_analysis",
            "guardrail_analysis 必须是 object",
            "写 required/evidence/checks 或 required=false + not_applicable_rationale",
            "guardrail.bad_type",
        ))

    if findings:
        return GateResult("result_card_completeness", "fail", "critical", findings,
                          note="result card 缺 target/analysis set/missingness/assumption/family/threshold 等关键字段。")
    if warn:
        return GateResult("result_card_completeness", "warn", "major", warn,
                          note="result card 基本可用但需降档/补说明。")
    return GateResult("result_card_completeness", "pass", "info", [], note="result card 核心字段完整。")


def _effect_language_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    card = spec.get("result_card") or {}
    effect = card.get("effect") or {}
    language = card.get("language") or {}
    threshold = card.get("practical_threshold") or {}
    loc = f"{project}:result_card.effect_language"
    findings: list[Finding] = []
    warn: list[Finding] = []

    p = _num(effect.get("p"))
    q = _num(effect.get("q"))
    estimate = _num(effect.get("estimate"))
    effect_size = _num(effect.get("effect_size"))
    ci = effect.get("ci95")
    ci_zero = _ci_contains_zero(ci)
    text = str(language.get("conclusion") or "")
    strength = _status(language.get("strength"))
    family_size = int(card.get("family_size") or 0) if str(card.get("family_size") or "").isdigit() else 0

    for name, value in (("p", p), ("effect_size", effect_size)):
        if value is None:
            findings.append(_finding(loc, f"effect.{name} 缺失或非法；不能只靠口头判断结果强弱", "补 p/q/效应量/CI 三件套", f"effect.{name}_missing"))
    if family_size > 1 and q is None:
        findings.append(_finding(loc, "family_size>1 但 effect.q 缺失；多重比较后显著性无法判断", "补校正后 q", "effect.q_missing_for_family"))
    if ci_zero is None:
        findings.append(_finding(loc, "effect.ci95 缺失或非法；不能判断方向稳定性", "补 95% CI [lo, hi]", "effect.ci_missing"))

    sig_value = q if q is not None else p
    nonsig = sig_value is None or sig_value >= 0.05 or ci_zero is True
    if nonsig:
        if strength not in SAFE_NONSIG_STRENGTHS:
            findings.append(_finding(
                loc,
                f"结果不显著或 CI 含 0（p={p}, q={q}, ci={ci}），但 language.strength={strength!r} 不是安全非显著档",
                "改为 NO_SIGNIFICANT_DIFFERENCE/INCONCLUSIVE，并写“未见显著差异”，不得写更好/提升",
                "language.nonsignificant_overclaim",
            ))
        if STRONG_WORD_RE.search(text):
            findings.append(_finding(
                loc,
                "结论文本在非显著/CI 含 0 时使用强结论词（证明/显著/优于/提升等）",
                "改成“未见显著差异/证据不足以支持差异”，或补强证据后重跑",
                "language.nonsignificant_strong_words",
                text[:240],
            ))

    near_values = [x for x in (p, q) if x is not None and 0.045 <= x <= 0.055]
    if near_values:
        near_text = str(language.get("near_threshold_wording") or "") + " " + text
        if strength in STRONG_LANGUAGE or STRONG_WORD_RE.search(text):
            findings.append(_finding(
                loc,
                f"p/q 位于阈值附近 {near_values}，却使用强结论语言；p=0.049/0.051 不应让叙事翻面",
                "降为边界/不确定/敏感表述，并报告 effect size + CI + q，而非围绕 0.05 叙事",
                "language.threshold_instability",
            ))
        if not UNCERTAIN_WORD_RE.search(near_text):
            warn.append(_finding(
                loc,
                f"p/q 位于 0.05 附近 {near_values}，但未显式说明阈值敏感性",
                "补 near_threshold_wording，例如“结论对显著性阈值敏感，应以效应量和 CI 为主”",
                "language.near_threshold_disclosure_missing",
            ))

    practical = _status(effect.get("practical_significance"))
    tval = _num(threshold.get("value")) if isinstance(threshold, dict) else None
    direction = _status(threshold.get("direction")) if isinstance(threshold, dict) else ""
    if practical == "YES" and estimate is not None and tval is not None:
        crosses = (
            (direction in {"HIGHER_IS_BETTER", "ABOVE"} and estimate >= tval)
            or (direction in {"LOWER_IS_BETTER", "BELOW"} and estimate <= tval)
            or (direction == "ABSOLUTE" and abs(estimate) >= abs(tval))
        )
        if not crosses:
            findings.append(_finding(
                loc,
                f"practical_significance=YES 但 estimate={estimate} 未达到 practical_threshold={tval}({direction})",
                "把实际意义改为 NO/UNKNOWN，或修正阈值依据；不能把统计显著当实际重要",
                "practical_threshold.not_met",
            ))

    if findings:
        return GateResult("effect_language_stability", "fail", "critical", findings,
                          note="效应/CI/q 与结论语言不一致，或 p≈0.05 被过度叙事。")
    if warn:
        return GateResult("effect_language_stability", "warn", "major", warn,
                          note="阈值附近结果需显式披露敏感性。")
    return GateResult("effect_language_stability", "pass", "info", [],
                      note="语言强度与 p/q/CI/实际阈值一致。")


def _decision_ledger_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    ledger = spec.get("decision_ledger") or []
    findings: list[Finding] = []
    warn: list[Finding] = []
    if not isinstance(ledger, list):
        findings.append(_finding(f"{project}:decision_ledger", "decision_ledger 必须是 list", "改成结构化 ledger", "ledger.bad_type"))
        ledger = []
    if not ledger:
        warn.append(_finding(
            f"{project}:decision_ledger",
            "decision_ledger 为空；无法证明没有结果后选择/排除/换指标",
            "至少声明 no post-result changes，或逐项记录 PRE/POST decisions",
            "ledger.empty",
        ))
    for idx, item in enumerate(ledger):
        loc = f"{project}:decision_ledger[{idx}]"
        if not isinstance(item, dict):
            findings.append(_finding(loc, "ledger item 必须是 object", "改为结构化 item", "ledger.bad_item"))
            continue
        missing = [
            key for key in ("decision_id", "timing", "kind", "planned", "classification",
                            "affected_claim_ids", "rationale", "evidence_locator")
            if item.get(key) in (None, "", [], {})
        ]
        if missing:
            findings.append(_finding(loc, f"ledger item 缺字段：{missing}", "补齐 timing/kind/planned/classification/evidence", "ledger.item_missing"))
        timing = _status(item.get("timing"))
        classification = _status(item.get("classification"))
        kind = _status(item.get("kind"))
        if timing and timing not in LEDGER_TIMING:
            findings.append(_finding(loc, f"timing={timing!r} 非法", "使用 PRE_RESULTS/POST_RESULTS", "ledger.bad_timing"))
        if classification and classification not in LEDGER_CLASSES:
            findings.append(_finding(loc, f"classification={classification!r} 非法", f"使用 {sorted(LEDGER_CLASSES)}", "ledger.bad_classification"))
        if timing == "POST_RESULTS" and kind in POST_RESULT_CONFIRMATORY_RISK and classification == "CONFIRMATORY":
            findings.append(_finding(
                loc,
                f"结果后 {kind} 决策被标为 CONFIRMATORY；这是 forking paths / HARKing 风险",
                "改为 SENSITIVITY/EXPLORATORY/SUPPLEMENTARY，并在主结论中降档或回 research-plan",
                "ledger.post_result_confirmatory",
                json.dumps(item, ensure_ascii=False),
            ))
        if timing == "POST_RESULTS" and item.get("planned") is True:
            findings.append(_finding(
                loc,
                "timing=POST_RESULTS 但 planned=true；时间线自相矛盾",
                "若真是预先计划，给 plan locator；否则 planned=false 并分类为 sensitivity/exploratory",
                "ledger.post_result_planned_conflict",
            ))
        if timing == "POST_RESULTS" and not item.get("user_approved"):
            warn.append(_finding(
                loc,
                "结果后分析决策未记录 user_approved；关键方向变更需要用户/研究者拍板",
                "补 user_approved=true/false 和授权 locator，不得由 agent 静默改变主分析",
                "ledger.user_approval_missing",
            ))

    if findings:
        return GateResult("analysis_decision_ledger", "fail", "critical", findings,
                          note="结果后数据依赖决策不能冒充 confirmatory；ledger 缺失关键字段也阻断。")
    if warn:
        return GateResult("analysis_decision_ledger", "warn", "major", warn,
                          note="ledger 可用但空账/授权证据不足。")
    return GateResult("analysis_decision_ledger", "pass", "info", [],
                      note="analysis decision ledger 可追溯，未见结果后 confirmatory 伪装。")


def _sensitivity_classification_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    items = spec.get("sensitivity") or []
    findings: list[Finding] = []
    warn: list[Finding] = []
    if not isinstance(items, list):
        findings.append(_finding(f"{project}:sensitivity", "sensitivity 必须是 list", "改成结构化列表", "sensitivity.bad_type"))
        items = []
    for idx, item in enumerate(items):
        loc = f"{project}:sensitivity[{idx}]"
        if not isinstance(item, dict):
            findings.append(_finding(loc, "sensitivity item 必须是 object", "改为结构化 item", "sensitivity.bad_item"))
            continue
        missing = [
            key for key in ("id", "target_same_as_primary", "changes_primary_estimand",
                            "changes_analysis_family", "classification")
            if item.get(key) is None or item.get(key) == ""
        ]
        if missing:
            findings.append(_finding(loc, f"sensitivity item 缺字段：{missing}", "补分类所需字段", "sensitivity.item_missing"))
            continue
        same_target = bool(item.get("target_same_as_primary"))
        changes_estimand = bool(item.get("changes_primary_estimand"))
        changes_family = bool(item.get("changes_analysis_family"))
        declared = _status(item.get("classification"))
        expected = "SENSITIVITY" if same_target and not changes_estimand and not changes_family else "SUPPLEMENTARY"
        if declared != expected:
            findings.append(_finding(
                loc,
                f"分类不一致：声明 {declared}，但根据 same_target={same_target}, "
                f"changes_estimand={changes_estimand}, changes_family={changes_family} 应为 {expected}",
                "同 target 且不改 estimand/family 才是 sensitivity；改 target/estimand/family 就是 supplementary/exploratory",
                "sensitivity.misclassified",
                json.dumps(item, ensure_ascii=False),
            ))
        if declared == "SENSITIVITY" and item.get("reported_as_new_claim"):
            findings.append(_finding(
                loc,
                "sensitivity 被 reported_as_new_claim；敏感性分析不能膨胀成独立主贡献",
                "把它报告为稳健性/限制性证据，而不是新 confirmatory claim",
                "sensitivity.reported_as_new_claim",
            ))
        if declared == "SUPPLEMENTARY" and item.get("used_to_rescue_primary"):
            warn.append(_finding(
                loc,
                "supplementary 结果被用来 rescue primary；需明确主结果是否失败",
                "主结果不支撑时回 research-plan，不得用补充分析替换原假设",
                "supplementary.rescues_primary",
            ))
    if findings:
        return GateResult("sensitivity_vs_supplementary", "fail", "critical", findings,
                          note="sensitivity/supplementary 分类错误会让探索性结果冒充主结论。")
    if warn:
        return GateResult("sensitivity_vs_supplementary", "warn", "major", warn,
                          note="supplementary 与 primary 的叙事边界需要降档说明。")
    return GateResult("sensitivity_vs_supplementary", "pass", "info", [],
                      note="sensitivity/supplementary 分类与 target/estimand/family 一致。")


def _declared_decision_gate(art: dict[str, Any]) -> GateResult:
    spec = art["spec"]
    project = art["project"]
    decision = _status(spec.get("decision"))
    if decision not in DECISIONS:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(f"{project}:decision", f"decision={decision!r} 非法或缺失", f"改为 {sorted(DECISIONS)}", "decision.bad_status")
        ], note="result-analysis 必须明确 claim 是否 ready。")
    blockers = [
        g for g in art["pre_decision_gates"]
        if g.status == "fail" and g.severity == "critical"
    ]
    warners = [g for g in art["pre_decision_gates"] if g.status == "warn"]
    if decision in {"REVISION_REQUIRED", "UNKNOWN"}:
        return GateResult("declared_decision", "fail", "critical", [
            _finding(
                f"{project}:decision",
                f"decision={decision}；result card 已声明需修订或仍未知，不能交给写作/投稿",
                "修复统计/证据/ledger/provenance 后再改为 CLAIM_READY；未知保持阻断",
                "decision.blocks_advancement",
            )
        ], note="REVISION_REQUIRED/UNKNOWN 是阻断性裁定，不是可推进状态。")
    if blockers and decision == "CLAIM_READY":
        names = ",".join(g.gate for g in blockers)
        return GateResult("declared_decision", "fail", "critical", [
            _finding(f"{project}:decision", f"存在 critical blockers({names}) 却声明 CLAIM_READY", "改为 REVISION_REQUIRED/UNKNOWN，或先修复 blockers", "decision.overrides_blockers", names)
        ], note="CLAIM_READY 不得覆盖硬阻断。")
    if warners and decision == "CLAIM_READY":
        names = ",".join(g.gate for g in warners)
        return GateResult("declared_decision", "warn", "major", [
            _finding(f"{project}:decision", f"存在 warn({names}) 但声明 CLAIM_READY；需带限制 ready", "在 conclusion 中显式写限制，或改 REVISION_REQUIRED", "decision.ready_with_warnings", names)
        ], note="有 warn 时需要限制性 ready。")
    return GateResult("declared_decision", "pass", "info", [], note=f"decision={decision} 与前置 gate 一致。")


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") not in (SCHEMA_ID, None):
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    project = str(spec.get("project") or "unknown-project")
    art = {"spec": spec, "project": project, "as_of": _resolve_as_of(spec)}
    pre = [
        _plan_lock_gate(art),
        _result_card_completeness_gate(art),
        _effect_language_gate(art),
        _decision_ledger_gate(art),
        _sensitivity_classification_gate(art),
    ]
    art["pre_decision_gates"] = pre
    gates = pre + [_declared_decision_gate(art)]
    report = FindingsReport(
        producer="result-analysis",
        target=project,
        gates=gates,
        summary=("result card + analysis decision ledger gate: target/analysis set/missingness/"
                 "assumptions/family/practical threshold + language stability + forking paths ledger"),
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
        f"# result-analysis result card gate：{result['project']}",
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
    lines.append("> 诚实边界：本 gate 检查结果解释是否与统计证据/计划/决策账本一致；不替代领域机制与因果终判。")
    return "\n".join(lines)


def _h() -> str:
    return "b" * 64


def _good_spec() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "project": "selftest-result",
        "plan_lock": {
            "status": "FROZEN",
            "locked_at": "2026-07-01T09:00:00+08:00",
            "results_available_at": "2026-07-01T10:00:00+08:00",
            "locator": "analysis-plan.md",
            "sha256": _h(),
        },
        "result_card": {
            "claim_id": "C1",
            "target_claim": "Method A improves accuracy over baseline on the planned test set",
            "target_type": "PRIMARY",
            "estimand_or_hypothesis": "H1: paired mean accuracy difference > 0",
            "metric": "accuracy",
            "comparison_family": "primary-model-comparison",
            "family_size": 2,
            "correction": "BH",
            "analysis_set": {
                "name": "planned-test-seeds",
                "n": 40,
                "unit": "seed",
                "missingness": {
                    "rate": 0.0,
                    "mechanism": "NOT_APPLICABLE",
                    "handling": "no missing planned units",
                },
            },
            "provenance": {
                "source_run_ids": ["EXP-01-seed42-a", "EXP-01-seed42-b"],
                "run_manifest_locator": "runs/EXP-01/manifest.json",
                "run_manifest_sha256": _h(),
                "raw_result_locator": "runs/EXP-01/raw_metrics.csv",
                "raw_result_sha256": _h(),
                "analysis_code_locator": "scripts/analyze_results.py",
                "analysis_code_sha256": _h(),
                "computed_at": "2026-07-04T12:00:00+08:00",
                "owner_skill": "RESULT-ANALYSIS",
            },
            "practical_threshold": {
                "metric": "accuracy_diff",
                "value": 0.02,
                "direction": "HIGHER_IS_BETTER",
                "justification_locator": "analysis-plan.md#threshold",
            },
            "assumption_checks": [
                {"assumption": "paired seeds", "status": "PASS", "evidence_locator": "run_manifest.md#seeds"},
                {"assumption": "no leakage", "status": "PASS", "evidence_locator": "leak_findings.json"},
            ],
            "guardrail_analysis": {
                "required": True,
                "evidence_locator": "runs/EXP-01/guardrails.json",
                "evidence_sha256": _h(),
                "checks": [
                    {
                        "id": "G1",
                        "metric": "minority subgroup accuracy",
                        "status": "PASS",
                        "observed": 0.82,
                        "threshold": 0.75,
                        "claim_impact": "允许主 claim，但需说明 subgroup guardrail 已过",
                        "evidence_locator": "runs/EXP-01/guardrails.json#G1",
                    }
                ],
            },
            "effect": {
                "estimate": 0.04,
                "effect_size": 0.7,
                "ci95": [0.015, 0.065],
                "p": 0.003,
                "q": 0.006,
                "direction": "positive",
                "practical_significance": "YES",
            },
            "language": {
                "conclusion": "Method A improves accuracy on the planned test set with a practically meaningful effect.",
                "strength": "IMPROVES",
            },
        },
        "decision_ledger": [
            {
                "decision_id": "D1",
                "timing": "PRE_RESULTS",
                "kind": "METRIC",
                "planned": True,
                "classification": "CONFIRMATORY",
                "affected_claim_ids": ["C1"],
                "rationale": "primary metric locked in analysis plan",
                "evidence_locator": "analysis-plan.md#metric",
            }
        ],
        "sensitivity": [
            {
                "id": "S1",
                "target_same_as_primary": True,
                "changes_primary_estimand": False,
                "changes_analysis_family": False,
                "classification": "SENSITIVITY",
            }
        ],
        "decision": "CLAIM_READY",
    }


def _selftest() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good = evaluate(_good_spec())
    check(good["status"] == "PASS", f"good spec 应 PASS，得 {good['status']}")
    check(good["findings"]["schema"] == "light.findings.v1", "应产 light.findings.v1")
    check(good["findings"]["producer"] == "result-analysis", "producer 应 result-analysis")

    nonsig = _good_spec()
    nonsig["result_card"]["effect"]["p"] = 0.051
    nonsig["result_card"]["effect"]["q"] = 0.061
    nonsig["result_card"]["effect"]["ci95"] = [-0.01, 0.05]
    nonsig["result_card"]["language"]["conclusion"] = "Method A significantly improves accuracy."
    nonsig["result_card"]["language"]["strength"] = "IMPROVES"
    r2 = evaluate(nonsig)
    check(r2["status"] == "FAIL" and "effect_language_stability" in r2["blocking_gates"],
          "非显著/CI 含 0 强语言应阻断")

    near = _good_spec()
    near["result_card"]["effect"]["p"] = 0.049
    near["result_card"]["effect"]["q"] = 0.049
    near["result_card"]["language"]["strength"] = "IMPROVES"
    near["result_card"]["language"]["conclusion"] = "Method A significantly improves accuracy."
    r3 = evaluate(near)
    check(r3["status"] == "FAIL", "p=0.049 强叙事应阻断阈值不稳定")

    post = _good_spec()
    post["decision_ledger"].append({
        "decision_id": "D2",
        "timing": "POST_RESULTS",
        "kind": "EXCLUSION",
        "planned": False,
        "classification": "CONFIRMATORY",
        "affected_claim_ids": ["C1"],
        "rationale": "remove outlier after seeing result",
        "evidence_locator": "notebook.ipynb#cell-9",
    })
    r4 = evaluate(post)
    check(r4["status"] == "FAIL" and "analysis_decision_ledger" in r4["blocking_gates"],
          "结果后 exclusion 标 confirmatory 应阻断")

    mis = _good_spec()
    mis["sensitivity"][0]["changes_primary_estimand"] = True
    mis["sensitivity"][0]["classification"] = "SENSITIVITY"
    r5 = evaluate(mis)
    check(r5["status"] == "FAIL" and "sensitivity_vs_supplementary" in r5["blocking_gates"],
          "改变 estimand 却标 sensitivity 应阻断")

    miss = _good_spec()
    miss["result_card"]["analysis_set"]["missingness"] = {
        "rate": 0.12,
        "mechanism": "UNKNOWN",
        "handling": "complete-case",
    }
    r6 = evaluate(miss)
    check(r6["status"] == "FAIL" and "result_card_completeness" in r6["blocking_gates"],
          "missingness UNKNOWN 且高缺失无 sensitivity 应阻断")

    no_corr = _good_spec()
    no_corr["result_card"]["family_size"] = 5
    no_corr["result_card"]["correction"] = "NONE"
    no_corr["result_card"]["effect"]["q"] = None
    r7 = evaluate(no_corr)
    check(r7["status"] == "FAIL", "多比较无 correction/q 应阻断")

    no_provenance = _good_spec()
    no_provenance["result_card"]["provenance"]["raw_result_sha256"] = ""
    no_provenance["result_card"]["provenance"]["owner_skill"] = "EXPERIMENT-CODING"
    r7b = evaluate(no_provenance)
    check(r7b["status"] == "FAIL" and "result_card_completeness" in r7b["blocking_gates"],
          "缺 raw result hash 或 owner_skill 错误应阻断")

    guardrail_fail = _good_spec()
    guardrail_fail["result_card"]["guardrail_analysis"]["checks"][0]["status"] = "FAIL"
    guardrail_fail["result_card"]["guardrail_analysis"]["checks"][0]["observed"] = 0.61
    r7c = evaluate(guardrail_fail)
    check(r7c["status"] == "FAIL" and "result_card_completeness" in r7c["blocking_gates"],
          "guardrail FAIL 应阻断 claim ready")

    guardrail_missing = _good_spec()
    guardrail_missing["result_card"]["guardrail_analysis"] = {
        "required": False,
    }
    r7d = evaluate(guardrail_missing)
    check(r7d["status"] == "FAIL" and "result_card_completeness" in r7d["blocking_gates"],
          "guardrail required=false 但无 rationale 应阻断")

    plan_after = _good_spec()
    plan_after["plan_lock"]["locked_at"] = "2026-07-01T12:00:00+08:00"
    r8 = evaluate(plan_after)
    check(r8["status"] == "FAIL" and "plan_lock" in r8["blocking_gates"],
          "计划晚于结果应阻断 confirmatory claim")

    future = _good_spec()
    future["as_of"] = "2026-07-04T10:00:00+08:00"
    future["plan_lock"]["locked_at"] = "2999-01-01T00:00:00+00:00"
    future["plan_lock"]["results_available_at"] = "2999-01-02T00:00:00+00:00"
    future["result_card"]["provenance"]["computed_at"] = "2999-01-03T00:00:00+00:00"
    r9 = evaluate(future)
    rules = {
        finding["rule"]
        for gate in r9["findings"]["gates"]
        for finding in gate["findings"]
    }
    check({
        "plan_lock.future_locked_at",
        "plan_lock.future_results_available_at",
        "provenance.future_computed_at",
    } <= rules, "未来 locked/results/computed 时间应阻断")

    computed_before = _good_spec()
    computed_before["result_card"]["provenance"]["computed_at"] = "2026-07-01T09:30:00+08:00"
    r10 = evaluate(computed_before)
    check(
        r10["status"] == "FAIL"
        and "result_card_completeness" in r10["blocking_gates"],
        "computed_at 早于 results_available_at 应阻断",
    )

    revision_required = _good_spec()
    revision_required["decision"] = "REVISION_REQUIRED"
    r11 = evaluate(revision_required)
    check(
        r11["status"] == "FAIL"
        and "declared_decision" in r11["blocking_gates"],
        "decision=REVISION_REQUIRED 应阻断推进",
    )

    check("result card gate" in to_markdown(good), "markdown 应含标题")

    if failures:
        print("[SELFTEST][result_card_gate] FAIL:")
        for item in failures:
            print("  -", item)
        return 1
    print("[SELFTEST][result_card_gate] OK: clean pass / p=.051 non-sig / p=.049 threshold / "
          "post-result ledger / sensitivity classification / missingness / multiplicity / provenance / guardrail / "
          "plan lock / future dates / declared decision")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate result card and analysis decision ledger")
    parser.add_argument("--spec", help="light.result_card.v1 JSON")
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
