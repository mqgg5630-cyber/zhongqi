#!/usr/bin/env python3
"""Audit analysis-plan lock, design declarations, family coverage, and provenance.

This is deliberately advisory: every finding is ``warn``/``major``.  Existing
stage-7 critical rules remain owned by stat_rigor_gate.py.  The audit answers a
different question: do we know what was planned, what the analysis unit was,
which comparisons belonged to one family, and which raw artifacts were used?
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import tempfile


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "_shared").is_dir():
            return parent
    raise RuntimeError("cannot locate repository root containing _shared")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402


SUPPORTED_SIMPLE_DESIGNS = {"independent", "paired"}
COMPLEX_DESIGNS = {
    "repeated_measures", "hierarchical", "clustered", "nested_cv",
    "repeated_cv", "time_series", "repeated_holdout",
}


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
    except ValueError:
        return None


def _finding(rule, issue, fix, evidence="", loc="analysis-plan"):
    return Finding(loc=loc, issue=issue, fix=fix, evidence=evidence, rule=rule)


def audit(spec: dict) -> dict:
    project = str(spec.get("project") or "unknown-project")
    plan = spec.get("plan") or {}
    analysis = spec.get("analysis") or {}
    coverage = spec.get("coverage") or {}
    inputs = spec.get("inputs") or []
    findings = []

    status = plan.get("status")
    if status != "frozen":
        findings.append(_finding(
            "analysis_plan.not_frozen",
            f"分析计划未标为 frozen（status={status!r}）；结果后改计划不能伪装成 a-priori",
            "记录原计划、locked_at 与变更日志；若已看结果，标 exploratory/change_after_results",
            loc=f"{project}:plan.status"))

    missing_timeline = [
        key for key in ("locked_at", "results_available_at") if not plan.get(key)
    ]
    if missing_timeline:
        findings.append(_finding(
            "analysis_plan.timeline_missing",
            f"分析计划缺少时间线字段：{missing_timeline}；仅写 status=frozen 不能证明结果前锁定",
            "记录带时区的 locked_at 与 results_available_at；若结果已可见，诚实标为探索性/敏感性分析",
            evidence=",".join(missing_timeline), loc=f"{project}:plan.timeline"))

    locked = _parse_time(plan.get("locked_at"))
    results_at = _parse_time(plan.get("results_available_at"))
    for field, parsed in (("locked_at", locked), ("results_available_at", results_at)):
        if plan.get(field) and parsed is None:
            findings.append(_finding(
                "analysis_plan.bad_timestamp",
                f"{field} 不是带时区的 ISO-8601 时间",
                "改用带时区 ISO-8601，例如 2026-07-01T09:00:00+08:00",
                evidence=str(plan.get(field)), loc=f"{project}:plan.{field}"))
    if locked and results_at and locked > results_at:
        findings.append(_finding(
            "analysis_plan.locked_after_results",
            "分析计划冻结时间晚于结果可见时间；只能按事后/探索性分析报告",
            "保留真实时间线与 change log，不得回填成 preregistered/a-priori",
            evidence=f"locked_at={plan.get('locked_at')};results_available_at={plan.get('results_available_at')}",
            loc=f"{project}:plan.locked_at"))

    required_plan = ("hypotheses", "primary_metric", "unit_of_analysis",
                     "exclusion_rules", "comparison_families")
    missing_plan = [key for key in required_plan if plan.get(key) in (None, "", [])]
    if missing_plan:
        findings.append(_finding(
            "analysis_plan.incomplete",
            f"冻结计划缺少字段：{missing_plan}",
            "在看结果前写清 hypothesis/primary metric/unit/exclusion/comparison families",
            evidence=",".join(missing_plan), loc=f"{project}:plan"))

    design = str(plan.get("design") or analysis.get("design") or "").lower()
    pair_key = analysis.get("paired_by")
    if design == "paired" and not pair_key:
        findings.append(_finding(
            "analysis_design.pair_key_missing",
            "设计声明为 paired，但未给 paired_by；同一实验单元可能被误当独立样本",
            "指定真实配对键（seed/fold/sample_id），并验证每组键唯一且交集完整",
            loc=f"{project}:analysis.paired_by"))
    if design in COMPLEX_DESIGNS:
        findings.append(_finding(
            "analysis_design.complex_requires_model",
            f"设计={design} 不能由简单独立/配对检验自动终判",
            "显式建模依赖结构（mixed model/GEE/cluster bootstrap/校正后的 CV 检验）；"
            "analyze_results 仅作描述或敏感性核验",
            evidence=f"unit={plan.get('unit_of_analysis')};paired_by={pair_key}",
            loc=f"{project}:plan.design"))
    elif design and design not in SUPPORTED_SIMPLE_DESIGNS:
        findings.append(_finding(
            "analysis_design.unknown",
            f"未知 design={design!r}，不能推断独立性",
            "改成明确设计名并说明统计单位与依赖结构",
            loc=f"{project}:plan.design"))

    if analysis.get("aggregate_only"):
        findings.append(_finding(
            "analysis_design.aggregate_only",
            "只有汇总均值，缺逐 seed/fold/sample 原始统计单位；无法验证方差与配对",
            "保留逐单位 raw results；汇总表只能作展示，不能冒充可检验样本",
            loc=f"{project}:analysis.aggregate_only"))

    families = plan.get("comparison_families") or []
    seen = set()
    for idx, family in enumerate(families):
        fid = family.get("family_id")
        loc = f"{project}:comparison_families[{idx}]"
        if not fid:
            findings.append(_finding(
                "multiplicity.family_id_missing",
                "comparison family 缺 family_id，无法证明校正覆盖的是哪一组检验",
                "为同一科学问题下的 planned comparisons 指定稳定 family_id",
                loc=loc))
        elif fid in seen:
            findings.append(_finding(
                "multiplicity.family_id_duplicate",
                f"family_id={fid!r} 重复；可能把同一家族拆开规避校正",
                "合并同一科学问题的比较，并对完整家族一次性校正",
                evidence=str(fid), loc=loc))
        seen.add(fid)
        planned = family.get("planned_comparisons")
        reported = family.get("reported_comparisons")
        if isinstance(planned, int) and isinstance(reported, int) and reported != planned:
            findings.append(_finding(
                "multiplicity.family_coverage_gap",
                f"family={fid or idx} planned={planned} 但 reported={reported}",
                "报告完整家族（含不显著结果）并对完整 p 集合重算 q",
                evidence=f"planned={planned};reported={reported}", loc=loc))
        if not family.get("correction"):
            findings.append(_finding(
                "multiplicity.correction_unspecified",
                f"family={fid or idx} 未声明 correction",
                "按分析计划声明 BH-FDR/Bonferroni/层级策略；不要看结果后换 family",
                loc=loc))

    expected = {str(x) for x in (coverage.get("expected_units") or [])}
    observed = {str(x) for x in (coverage.get("observed_units") or [])}
    if expected:
        missing_units = sorted(expected - observed)
        extra_units = sorted(observed - expected)
        if missing_units or extra_units:
            findings.append(_finding(
                "coverage.unit_mismatch",
                f"统计单位覆盖不一致：缺 {missing_units}；额外 {extra_units}",
                "解释失败/排除原因并保留 exclusion log；不得静默删掉失败 seed/fold",
                evidence=f"expected={len(expected)};observed={len(observed)}",
                loc=f"{project}:coverage"))
    elif not coverage.get("coverage_note"):
        findings.append(_finding(
            "coverage.undeclared",
            "未声明 expected/observed units 或 coverage_note，无法判断失败运行是否被静默丢弃",
            "从 run manifest 抄入预期与实得 seed/fold/sample 覆盖",
            loc=f"{project}:coverage"))

    required_input = ("path", "role", "sha256", "owner", "captured_at")
    if not inputs:
        findings.append(_finding(
            "provenance.no_inputs",
            "未声明任何输入工件；无法把 claim 追到 raw results/run manifest/config",
            "至少登记 raw_results，并记录 path/role/hash/owner/time 与 run manifest 或 commit",
            loc=f"{project}:inputs"))
    for idx, item in enumerate(inputs):
        missing = [key for key in required_input if not item.get(key)]
        if missing:
            findings.append(_finding(
                "provenance.input_gap",
                f"输入工件缺 provenance 字段：{missing}",
                "补 path/role/sha256/owner/captured_at；公开数据另补 source_url/license",
                evidence=str(item.get("path") or f"input[{idx}]"),
                loc=f"{project}:inputs[{idx}]"))
        if item.get("role") == "raw_results" and not (
                item.get("run_manifest") or item.get("commit")):
            findings.append(_finding(
                "provenance.run_locator_missing",
                "raw_results 未指向 run_manifest 或 commit，claim 不能追到真实运行",
                "补 run_manifest 路径与生成结果的 commit/config locator",
                evidence=str(item.get("path")), loc=f"{project}:inputs[{idx}]"))

    changes = analysis.get("changes_after_results") or []
    for idx, change in enumerate(changes):
        if not change.get("reason") or not change.get("declared_as"):
            findings.append(_finding(
                "analysis_plan.change_unlabeled",
                "结果后分析变更缺 reason 或 declared_as（exploratory/sensitivity）",
                "逐项记录旧值、新值、时间、原因，并明确不得称 a-priori",
                evidence=json.dumps(change, ensure_ascii=False),
                loc=f"{project}:analysis.changes_after_results[{idx}]"))

    status_name = "warn" if findings else "pass"
    gate = GateResult(
        gate="analysis_design_provenance",
        status=status_name,
        severity="major" if findings else "info",
        findings=findings,
        note=("warn-only：计划锁、统计单位、comparison family、coverage/provenance；"
              "不替代 stat_rigor_gate 的 critical 统计门"),
    )
    report = FindingsReport(
        producer="result-analysis",
        target=project,
        gates=[gate],
        summary={"warning_count": len(findings), "advisory_only": True},
    )
    return {
        "schema": "light.analysis_audit.v1",
        "project": project,
        "advisory_only": True,
        "warning_count": len(findings),
        "findings": report.to_dict(),
    }


def _good_spec(tmp: pathlib.Path) -> dict:
    return {
        "project": "audit-selftest",
        "plan": {
            "status": "frozen",
            "locked_at": "2026-07-01T09:00:00+08:00",
            "results_available_at": "2026-07-01T10:00:00+08:00",
            "hypotheses": ["H1"],
            "primary_metric": "accuracy",
            "unit_of_analysis": "seed",
            "design": "paired",
            "exclusion_rules": ["parse failure only"],
            "comparison_families": [{
                "family_id": "primary-model-comparison",
                "planned_comparisons": 2,
                "reported_comparisons": 2,
                "correction": "bh",
            }],
        },
        "analysis": {"paired_by": "seed", "aggregate_only": False},
        "coverage": {"expected_units": [1, 2, 3], "observed_units": [1, 2, 3]},
        "inputs": [{
            "path": str(tmp / "results.csv"), "role": "raw_results",
            "sha256": "abc", "owner": "selftest",
            "captured_at": "2026-07-01T10:00:00+08:00",
            "run_manifest": "run_manifest.md", "commit": "deadbeef",
        }],
    }


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        good = audit(_good_spec(pathlib.Path(td)))
        assert good["warning_count"] == 0
        assert good["findings"]["verdict"] == "pass"

        bad = _good_spec(pathlib.Path(td))
        bad["plan"]["status"] = "changed_after_results"
        bad["plan"]["locked_at"] = "2026-07-01T11:00:00+08:00"
        bad["plan"]["design"] = "nested_cv"
        bad["plan"]["comparison_families"][0]["reported_comparisons"] = 1
        bad["coverage"]["observed_units"] = [1, 2]
        bad["inputs"][0].pop("sha256")
        dirty = audit(bad)
        rules = {
            f["rule"]
            for gate in dirty["findings"]["gates"]
            for f in gate["findings"]
        }
        expected = {
            "analysis_plan.not_frozen",
            "analysis_plan.locked_after_results",
            "analysis_design.complex_requires_model",
            "multiplicity.family_coverage_gap",
            "coverage.unit_mismatch",
            "provenance.input_gap",
        }
        assert expected <= rules, (expected - rules)
        assert dirty["findings"]["verdict"] == "warn"

        hollow = _good_spec(pathlib.Path(td))
        hollow["plan"].pop("locked_at")
        hollow["plan"].pop("results_available_at")
        hollow["inputs"] = []
        hollow_result = audit(hollow)
        hollow_rules = {
            f["rule"]
            for gate in hollow_result["findings"]["gates"]
            for f in gate["findings"]
        }
        assert {"analysis_plan.timeline_missing", "provenance.no_inputs"} <= hollow_rules

        naive = _good_spec(pathlib.Path(td))
        naive["plan"]["locked_at"] = "2026-07-01T09:00:00"
        naive_result = audit(naive)
        assert any(
            f["rule"] == "analysis_plan.bad_timestamp"
            for gate in naive_result["findings"]["gates"]
            for f in gate["findings"]
        ), "无时区时间不得与带时区时间比较或冒充绝对时间"

        bom_path = pathlib.Path(td) / "bom-spec.json"
        bom_path.write_text(
            json.dumps(_good_spec(pathlib.Path(td)), ensure_ascii=False),
            encoding="utf-8-sig",
        )
        loaded = json.loads(bom_path.read_text(encoding="utf-8-sig"))
        assert audit(loaded)["warning_count"] == 0

    print("[selftest] PASS analysis_plan_audit "
          "(clean pass + advisory gaps + timeline/timezone/provenance + UTF-8 BOM; never critical)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Warn-only audit of analysis-plan lock, design, family coverage, and provenance")
    ap.add_argument("--spec", help="analysis audit JSON")
    ap.add_argument("--report", help="write light.findings.v1")
    ap.add_argument("--json-out", help="write full light.analysis_audit.v1")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec:
        ap.error("--spec is required unless --selftest")
    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8-sig"))
    result = audit(spec)
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "schema": result["schema"],
        "warning_count": result["warning_count"],
        "verdict": result["findings"]["verdict"],
        "advisory_only": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
