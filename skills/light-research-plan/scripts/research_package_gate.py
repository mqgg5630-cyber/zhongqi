#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research_package_gate.py — research-plan 的完整计划包交付门。

单个门都绿不等于一套研究方案可交给 experiment-coding：用户最终拿到的应是能冻结、能复验、能回炉的
**计划包**。本脚本检查 research-plan 标准工件是否齐、上游门报告是否真跑过、失败树/guardrail 是否
闭合、警告是否被处理/降 claim/用户授权，避免“方案文字很漂亮，但 plan_findings/target-chain/failure-tree/
prereg/checklist 缺证据”的名实落差。

输入有两种：
  1) --manifest plan_package.json（推荐）：显式声明各工件路径、handoff 授权、warning_decisions；
  2) --root .：按默认文件名寻找工件，适合草稿巡检。

最终交 experiment-coding 前必须用 --final：此时缺用户授权、存在未处理 warning、critical report fail 都会 exit 1。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import plan_lint as pl  # noqa: E402  复用实验矩阵四要素/消融/负对照 linter，不重造轮子

REPO_ROOT = pathlib.Path(__file__).resolve()
while REPO_ROOT != REPO_ROOT.parent and not (REPO_ROOT / "_shared").exists():
    REPO_ROOT = REPO_ROOT.parent

SCHEMA = "light.research_plan_package_gate.v1"
MANIFEST_SCHEMA = "light.research_plan_package.v1"
PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|TODO|TBD|待填|待定|未填写", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d(?::[0-5]\d)?(?:Z|[+-]\d{2}:\d{2})?)?$")

DEFAULT_CANDIDATES = {
    "research_plan": ("PROJECT_PLAN.md", "research-plan.md", "plans/research-plan.md"),
    "experiment_matrix": ("experiments/experiment_matrix.md", "experiment_matrix.md"),
    "target_chain_report": (".light/target_chain_report.json", "target_chain_report.json"),
    "failure_tree_report": (".light/failure_tree_report.json", "failure_tree_report.json"),
    "plan_findings": (".light/plan_findings.json", "plan_findings.json"),
    "preregistration": ("preregistration.md", ".light/preregistration.md"),
    "reproducibility_checklist": ("reproducibility-checklist.md", ".light/reproducibility-checklist.md"),
}

REQUIRED_PLAN_TERMS = {
    "estimand_or_question": ("estimand", "研究问题", "question"),
    "falsifier": ("反证", "可证伪", "falsifier"),
    "fair_baseline": ("对照公平", "baseline 公平", "fair_baseline", "等量调参"),
    "preregistration": ("预注册", "preregistration", "registry"),
    "budget": ("算力", "成本", "budget", "gpu"),
    "risk": ("风险", "risk", "plan b"),
}

REPRO_SEED_TERMS = ("PYTHONHASHSEED", "cuDNN", "DataLoader")
PREREG_STATUS_VALUES = {"DRAFT", "SUBMITTED", "REGISTERED", "EMBARGOED", "UNAVAILABLE", "LOCAL-ONLY"}


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(_read_text(path))


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _issue(severity: str, code: str, loc: str, message: str, fix: str = "") -> dict[str, str]:
    row = {"severity": severity, "code": code, "loc": loc, "message": message}
    if fix:
        row["fix"] = fix
    return row


def _has_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text))


def _valid_date(value: Any) -> bool:
    if not value or not DATE_RE.match(str(value)):
        return False
    # 只严格解析日期部分；带时间/时区时接受格式合法即可，避免 Python 版本差异。
    try:
        dt.date.fromisoformat(str(value)[:10])
        return True
    except ValueError:
        return False


def _load_manifest(root: pathlib.Path, manifest_path: pathlib.Path | None) -> dict[str, Any]:
    if manifest_path:
        manifest = _read_json(manifest_path)
        manifest.setdefault("artifacts", {})
        return manifest
    artifacts: dict[str, str] = {}
    for key, candidates in DEFAULT_CANDIDATES.items():
        for cand in candidates:
            if (root / cand).exists():
                artifacts[key] = cand
                break
    return {"schema": MANIFEST_SCHEMA, "project": root.name, "artifacts": artifacts}


def _resolve_artifact(root: pathlib.Path, manifest: dict[str, Any], key: str) -> pathlib.Path | None:
    raw = (manifest.get("artifacts") or {}).get(key)
    if raw:
        path = pathlib.Path(str(raw))
        return path if path.is_absolute() else root / path
    for cand in DEFAULT_CANDIDATES.get(key, ()):
        path = root / cand
        if path.exists():
            return path
    return None


def _missing_or_text(
    root: pathlib.Path, manifest: dict[str, Any], key: str, issues: list[dict[str, str]]
) -> tuple[pathlib.Path | None, str]:
    path = _resolve_artifact(root, manifest, key)
    if not path or not path.exists():
        issues.append(_issue(
            "error", "MISSING_ARTIFACT", key,
            f"缺少 {key} 工件",
            "在 manifest.artifacts 中声明路径，或按默认文件名生成该工件。",
        ))
        return None, ""
    try:
        text = _read_text(path)
    except UnicodeDecodeError as exc:
        issues.append(_issue("error", "ARTIFACT_ENCODING", _rel(root, path), f"文件不是 UTF-8：{exc}"))
        return path, ""
    if len(text.strip()) < 80:
        issues.append(_issue("error", "ARTIFACT_TOO_SHALLOW", _rel(root, path), "工件内容过短，像空壳文件"))
    if _has_placeholder(text):
        issues.append(_issue(
            "error", "TEMPLATE_PLACEHOLDER", _rel(root, path),
            "工件仍含 {{...}}/TODO/TBD/待填 等模板占位",
            "交付前必须填真实项目事实；未知就写 UNKNOWN/UNAVAILABLE + 原因，不留模板占位。",
        ))
    return path, text


def _check_research_plan(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> None:
    path, text = _missing_or_text(root, manifest, "research_plan", issues)
    if not path:
        return
    low = text.casefold()
    for code, terms in REQUIRED_PLAN_TERMS.items():
        if not any(term.casefold() in low for term in terms):
            issues.append(_issue(
                "error", "RESEARCH_PLAN_TERM_GAP", f"{_rel(root, path)}:{code}",
                f"研究方案缺少 {code} 相关内容",
                "方案必须覆盖 question/estimand、反证、对照公平、预注册、预算与风险，不能只写宏观路线。",
            ))


def _check_matrix(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> None:
    path, text = _missing_or_text(root, manifest, "experiment_matrix", issues)
    if not path:
        return
    lint = pl.lint(text)
    if lint.get("error") or not lint.get("ok", False):
        issues.append(_issue(
            "error", "MATRIX_LINT_FAIL", _rel(root, path),
            lint.get("error") or "实验矩阵四要素缺项",
            "运行 plan_lint.py 修齐对应假设/数据集/baseline/指标/完成判定。",
        ))
    for warning in lint.get("warnings", [])[:12]:
        issues.append(_issue(
            "warn", "MATRIX_LINT_WARNING", _rel(root, path),
            warning,
            "若暂不修复，必须在 manifest.warning_decisions 记录处理/降 claim/用户授权。",
        ))


def _check_target_chain(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> None:
    path = _resolve_artifact(root, manifest, "target_chain_report")
    if not path or not path.exists():
        issues.append(_issue(
            "error", "TARGET_CHAIN_REPORT_MISSING", "target_chain_report",
            "缺少 target_chain.py 的报告",
            "运行 target_chain.py --input target-chain.json，并把输出 JSON 路径写入 manifest。",
        ))
        return
    try:
        report = _read_json(path)
    except Exception as exc:
        issues.append(_issue("error", "TARGET_CHAIN_REPORT_INVALID", _rel(root, path), f"无法解析 JSON：{exc}"))
        return
    if report.get("schema") != "light.research_target_chain_report.v1":
        issues.append(_issue("error", "TARGET_CHAIN_SCHEMA_GAP", _rel(root, path), "target_chain report schema 不匹配"))
    if report.get("status") != "PASS":
        issues.append(_issue(
            "error", "TARGET_CHAIN_NOT_PASS", _rel(root, path),
            f"target_chain status={report.get('status')}",
            "补齐 question→estimand→endpoint→analysis→falsifier→action 链、授权、风险账与计划 hash。",
        ))


def _check_failure_tree(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> list[str]:
    path = _resolve_artifact(root, manifest, "failure_tree_report")
    if not path or not path.exists():
        issues.append(_issue(
            "error", "FAILURE_TREE_REPORT_MISSING", "failure_tree_report",
            "缺少 failure_tree_gate.py 的报告",
            "运行 failure_tree_gate.py --input failure-tree.json --json-out .light/failure_tree_report.json，并写入 manifest。",
        ))
        return []
    try:
        report = _read_json(path)
    except Exception as exc:
        issues.append(_issue("error", "FAILURE_TREE_REPORT_INVALID", _rel(root, path), f"无法解析 JSON：{exc}"))
        return []
    if report.get("schema") != "light.research_failure_tree_report.v1":
        issues.append(_issue("error", "FAILURE_TREE_SCHEMA_GAP", _rel(root, path), "failure_tree report schema 不匹配"))
    status = str(report.get("status") or "").upper()
    if status == "FAIL":
        issues.append(_issue(
            "error", "FAILURE_TREE_NOT_PASS", _rel(root, path),
            "failure_tree status=FAIL",
            "补齐 success/failure/inconclusive 分支、guardrail、stopping、amendment 与授权字段。",
        ))
    elif status == "WARN":
        issues.append(_issue(
            "warn", "FAILURE_TREE_WARN", _rel(root, path),
            "failure_tree status=WARN",
            "若暂不修复，必须在 manifest.warning_decisions 记录处理/降 claim/用户授权。",
        ))
        return ["failure_tree"]
    elif status != "PASS":
        issues.append(_issue("error", "FAILURE_TREE_STATUS_GAP", _rel(root, path), f"未知 status={status}"))
    return []


def _finding_warning_keys(findings: dict[str, Any]) -> list[str]:
    keys = []
    for gate in findings.get("gates") or []:
        status = str(gate.get("status") or "").lower()
        severity = str(gate.get("severity") or "").lower()
        if status == "warn" or severity in {"major", "minor"}:
            keys.append(str(gate.get("gate") or "unknown_gate"))
    return keys


def _check_plan_findings(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> list[str]:
    path = _resolve_artifact(root, manifest, "plan_findings")
    if not path or not path.exists():
        issues.append(_issue(
            "error", "PLAN_FINDINGS_MISSING", "plan_findings",
            "缺少 plan_gate.py 产出的 light.findings.v1",
            "运行 plan_gate.py --spec plan_spec.json --report plan_findings.json。",
        ))
        return []
    try:
        findings = _read_json(path)
    except Exception as exc:
        issues.append(_issue("error", "PLAN_FINDINGS_INVALID", _rel(root, path), f"无法解析 JSON：{exc}"))
        return []
    if findings.get("schema") != "light.findings.v1" or findings.get("producer") != "research-plan":
        issues.append(_issue(
            "error", "PLAN_FINDINGS_SCHEMA_GAP", _rel(root, path),
            "plan_findings 不是 producer=research-plan 的 light.findings.v1",
        ))
    gates = {str(g.get("gate")) for g in findings.get("gates") or []}
    if not {"fair_baseline", "falsifiable"} <= gates:
        issues.append(_issue(
            "error", "PLAN_FINDINGS_GATE_GAP", _rel(root, path),
            "plan_findings 缺 fair_baseline/falsifiable stage-5 critical 门名",
        ))
    if findings.get("verdict") == "fail":
        issues.append(_issue(
            "error", "PLAN_FINDINGS_FAIL", _rel(root, path),
            "plan_gate verdict=fail：存在对照不公平或不可证伪等 critical 问题",
            "在 stage 5 内修方案，不得交给 experiment-coding。",
        ))
    for gate in findings.get("gates") or []:
        if gate.get("status") == "warn":
            issues.append(_issue(
                "warn", "PLAN_FINDINGS_WARNING", f"{_rel(root, path)}:{gate.get('gate')}",
                str(gate.get("note") or f"{gate.get('gate')} warning"),
                "若暂不修复，必须在 manifest.warning_decisions 记录处理/降 claim/用户授权。",
            ))
    return _finding_warning_keys(findings)


def _check_prereg(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> None:
    path, text = _missing_or_text(root, manifest, "preregistration", issues)
    if not path:
        return
    up = text.upper()
    if not any(value in up for value in PREREG_STATUS_VALUES):
        issues.append(_issue(
            "error", "PREREG_STATUS_GAP", _rel(root, path),
            "预注册包缺 registration status（DRAFT/SUBMITTED/REGISTERED/EMBARGOED/UNAVAILABLE/LOCAL-ONLY）",
            "未提交就写 DRAFT 或 UNAVAILABLE；绝不把本地草稿冒充 REGISTERED。",
        ))
    for term in ("primary", "exploratory", "stopping", "guardrail"):
        if term not in text.casefold():
            issues.append(_issue("error", "PREREG_FIELD_GAP", f"{_rel(root, path)}:{term}", f"预注册包缺 {term} 字段"))


def _check_repro(root: pathlib.Path, manifest: dict[str, Any], issues: list[dict[str, str]]) -> None:
    path, text = _missing_or_text(root, manifest, "reproducibility_checklist", issues)
    if not path:
        return
    for term in REPRO_SEED_TERMS:
        if term.casefold() not in text.casefold():
            issues.append(_issue(
                "error", "REPRO_SEED_COVERAGE_GAP", f"{_rel(root, path)}:{term}",
                f"复现清单缺 {term} 种子/确定性覆盖",
                "研究方案进入编码前必须提醒 experiment-coding 固定 PYTHONHASHSEED、cuDNN 与 DataLoader worker。",
            ))


def _decision_keys(manifest: dict[str, Any]) -> set[str]:
    out = set()
    for row in manifest.get("warning_decisions") or []:
        source = str(row.get("source") or row.get("gate") or row.get("code") or "")
        if source:
            out.add(source.casefold())
    return out


def _check_warning_decisions(
    manifest: dict[str, Any], warning_gates: list[str], issues: list[dict[str, str]], final: bool
) -> None:
    decisions = manifest.get("warning_decisions") or []
    keys = _decision_keys(manifest)
    for row in decisions:
        if not all(row.get(field) for field in ("decision", "claim_impact", "authorized_by")):
            issues.append(_issue(
                "error" if final else "warn", "WARNING_DECISION_ROW_GAP", "manifest.warning_decisions",
                "warning_decisions 条目缺 decision/claim_impact/authorized_by",
                "每个未修 warning 都要写：如何处理、如何降 claim、谁授权继续。",
            ))
    for gate in warning_gates:
        if not any(gate.casefold() in key for key in keys):
            issues.append(_issue(
                "error" if final else "warn", "WARNING_DECISION_GAP", f"warning:{gate}",
                f"存在 {gate} warning，但 manifest 未记录处理/降 claim/用户授权",
                "修复 warning，或在 manifest.warning_decisions 中写明决策、claim impact 与 user 授权。",
            ))


def _check_handoff(manifest: dict[str, Any], issues: list[dict[str, str]], final: bool) -> None:
    handoff = manifest.get("handoff") or {}
    severity = "error" if final else "warn"
    if str(handoff.get("next_stage") or "").lower() not in {"experiment-coding", "light-experiment-coding", "stage-6"}:
        issues.append(_issue(
            severity, "HANDOFF_STAGE_GAP", "manifest.handoff.next_stage",
            "缺少下一站 experiment-coding/stage-6 声明",
            "最终交付前要明确交给 experiment-coding，而不是让总控自己继续乱跑。",
        ))
    if handoff.get("user_authorized") is not True:
        issues.append(_issue(
            severity, "HANDOFF_AUTHORIZATION_GAP", "manifest.handoff.user_authorized",
            "最终研究计划交接缺用户授权",
            "方案定型/预注册/进入实验编码前必须停下让用户确认。",
        ))
    if not _valid_date(handoff.get("authorized_at")):
        issues.append(_issue(
            severity, "HANDOFF_AUTHORIZATION_DATE_GAP", "manifest.handoff.authorized_at",
            "用户授权缺 ISO 日期/时间",
            "写 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS+08:00，便于 memory-pm 追踪。",
        ))
    if not handoff.get("claim_scope"):
        issues.append(_issue(
            severity, "HANDOFF_CLAIM_SCOPE_GAP", "manifest.handoff.claim_scope",
            "缺 claim_scope：不知道本计划允许宣称到什么强度",
            "写清 confirmatory/secondary/exploratory 的边界，warning 未修时必须降 claim。",
        ))


def evaluate(root: pathlib.Path, manifest_path: pathlib.Path | None = None, final: bool = False) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load_manifest(root, manifest_path)
    issues: list[dict[str, str]] = []
    if manifest.get("schema") not in (None, MANIFEST_SCHEMA):
        issues.append(_issue("error", "MANIFEST_SCHEMA_GAP", "manifest.schema", f"schema 应为 {MANIFEST_SCHEMA}"))
    _check_research_plan(root, manifest, issues)
    _check_matrix(root, manifest, issues)
    _check_target_chain(root, manifest, issues)
    failure_tree_warnings = _check_failure_tree(root, manifest, issues)
    warning_gates = _check_plan_findings(root, manifest, issues)
    _check_prereg(root, manifest, issues)
    _check_repro(root, manifest, issues)
    # 矩阵/门报告 warning 统一要求 final 包有决策；非 final 只提示，方便草稿巡检。
    matrix_warning = ["matrix_lint"] if any(x["code"] == "MATRIX_LINT_WARNING" for x in issues) else []
    _check_warning_decisions(manifest, warning_gates + matrix_warning + failure_tree_warnings, issues, final=final)
    _check_handoff(manifest, issues, final=final)

    verdict = "FAIL" if any(x["severity"] == "error" for x in issues) else "WARN" if issues else "PASS"
    return {
        "schema": SCHEMA,
        "project": manifest.get("project") or root.name,
        "mode": "final" if final else "draft",
        "verdict": verdict,
        "issues": issues,
        "artifacts": manifest.get("artifacts") or {},
        "honesty": (
            "本门只核计划包完整性、既有机器门报告、失败树/guardrail、预注册/复现字段、warning 决策与用户授权；"
            "PASS 不证明领域设计最优、因果识别成立、IRB/伦理/统计专家已批准。"
        ),
    }


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


GOOD_MATRIX = """# 实验矩阵表：demo

| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 已控混淆/负对照 | 完成判定 |
|--------|----------|--------|----------|------|-----------------|----------|
| EXP-01 | H1 | DemoSet | StrongBaseline | F1 | 同等调参预算 | F1 > baseline + 3% 且 p<0.05 |
| ABL-01 | H1 | DemoSet | 移除模块X | F1 | 随机标签负对照+同等预算 | F1 下降 > 2% 证明模块X贡献 |
"""

WARN_MATRIX = """# 实验矩阵表：demo

| 实验ID | 对应假设 | 数据集 | baseline | 指标 | 已控混淆/负对照 | 完成判定 |
|--------|----------|--------|----------|------|-----------------|----------|
| EXP-01 | H1 | DemoSet | StrongBaseline | F1 | 同等调参预算 | 效果更好 |
"""


def _good_findings(verdict: str = "pass", warn_gate: bool = False) -> dict[str, Any]:
    gates = [
        {"gate": "fair_baseline", "status": "pass", "severity": "info", "findings": [],
         "note": "对照公平性已声明"},
        {"gate": "falsifiable", "status": "pass", "severity": "info", "findings": [],
         "note": "假设均有反证条件"},
    ]
    if warn_gate:
        gates.append({"gate": "ablation_isolation", "status": "warn", "severity": "major",
                      "findings": [], "note": "消融未完全隔离"})
    return {
        "schema": "light.findings.v1",
        "producer": "research-plan",
        "target": "demo",
        "verdict": verdict,
        "gates": gates,
    }


def _make_good_package(base: pathlib.Path, *, warn: bool = False) -> pathlib.Path:
    _write(base / "PROJECT_PLAN.md", """# 研究方案：demo

## 1. 研究问题、estimand 与核心假设
Population、estimand、primary outcome 与可证伪反证条件均已声明。

## 5. 实验设计
对照公平：baseline 公平按同数据同划分与等量调参预算执行。

## 8. 风险点 & plan B
风险：样本不足；plan B：降 claim 或补数据。

## 9. 预注册与 provenance
registration status = DRAFT。

## 10. 算力 / 成本预算
GPU budget 已估算。
""")
    _write(base / "experiments" / "experiment_matrix.md", WARN_MATRIX if warn else GOOD_MATRIX)
    _write(base / ".light" / "target_chain_report.json", json.dumps({
        "schema": "light.research_target_chain_report.v1", "status": "PASS", "issues": []
    }, ensure_ascii=False, indent=2))
    _write(base / ".light" / "failure_tree_report.json", json.dumps({
        "schema": "light.research_failure_tree_report.v1",
        "status": "PASS",
        "advancement": "ALLOW",
        "issues": [],
    }, ensure_ascii=False, indent=2))
    _write(base / ".light" / "plan_findings.json", json.dumps(
        _good_findings("warn" if warn else "pass", warn_gate=warn), ensure_ascii=False, indent=2))
    _write(base / "preregistration.md", """# 预注册包：demo
registration status: DRAFT
primary confirmatory outcome: F1
exploratory: robustness
stopping: fixed N
guardrail: no quality metric below threshold
""")
    _write(base / "reproducibility-checklist.md", """# 复现清单
PYTHONHASHSEED fixed before process start.
cuDNN deterministic=True and benchmark=False.
DataLoader worker seed fixed.
""")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "project": "demo",
        "artifacts": {
            "research_plan": "PROJECT_PLAN.md",
            "experiment_matrix": "experiments/experiment_matrix.md",
            "target_chain_report": ".light/target_chain_report.json",
            "failure_tree_report": ".light/failure_tree_report.json",
            "plan_findings": ".light/plan_findings.json",
            "preregistration": "preregistration.md",
            "reproducibility_checklist": "reproducibility-checklist.md",
        },
        "handoff": {
            "next_stage": "experiment-coding",
            "user_authorized": True,
            "authorized_at": "2026-07-05T10:00:00+08:00",
            "claim_scope": "H1 confirmatory；warnings 若存在则降 claim 后推进。",
        },
    }
    if warn:
        manifest["warning_decisions"] = [
            {
                "source": "ablation_isolation",
                "decision": "先推进实现，但组件归因 claim 降为 exploratory，编码阶段补 ABL。",
                "claim_impact": "不宣称模块X已被确认贡献，只声明待验证。",
                "authorized_by": "user",
            },
            {
                "source": "matrix_lint",
                "decision": "完成判定先保留为草稿，进入编码前补量化阈值。",
                "claim_impact": "不得作为 confirmatory 判决。",
                "authorized_by": "user",
            },
        ]
    _write(base / "plan_package.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return base / "plan_package.json"


def _selftest_at(base: pathlib.Path) -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good_manifest = _make_good_package(base / "good")
    good = evaluate(base / "good", good_manifest, final=True)
    check(good["verdict"] == "PASS", f"完整 final 包应 PASS，得 {good['verdict']}:{good['issues']}")

    warn_manifest = _make_good_package(base / "warn_ack", warn=True)
    warn = evaluate(base / "warn_ack", warn_manifest, final=True)
    check(warn["verdict"] == "WARN", f"已授权处理 warning 的包应 WARN(exit 0)，得 {warn['verdict']}")

    no_decision = json.loads(_read_text(warn_manifest))
    no_decision.pop("warning_decisions")
    no_decision_path = base / "warn_ack" / "plan_package.no_decision.json"
    _write(no_decision_path, json.dumps(no_decision, ensure_ascii=False, indent=2))
    bad_warn = evaluate(base / "warn_ack", no_decision_path, final=True)
    check(bad_warn["verdict"] == "FAIL", "final 包存在 warning 但无 warning_decisions 应 FAIL")

    no_auth = json.loads(_read_text(good_manifest))
    no_auth["handoff"]["user_authorized"] = False
    no_auth_path = base / "good" / "plan_package.no_auth.json"
    _write(no_auth_path, json.dumps(no_auth, ensure_ascii=False, indent=2))
    bad_auth = evaluate(base / "good", no_auth_path, final=True)
    check(bad_auth["verdict"] == "FAIL", "final 包缺用户授权应 FAIL")

    target_bad = base / "target_bad"
    tb_manifest = _make_good_package(target_bad)
    _write(target_bad / ".light" / "target_chain_report.json", json.dumps({
        "schema": "light.research_target_chain_report.v1", "status": "FAIL",
        "issues": [{"code": "TARGET_CHAIN_BREAK"}],
    }, ensure_ascii=False, indent=2))
    tb = evaluate(target_bad, tb_manifest, final=True)
    check(tb["verdict"] == "FAIL" and any(x["code"] == "TARGET_CHAIN_NOT_PASS" for x in tb["issues"]),
          "target_chain 非 PASS 应 FAIL")

    failure_tree_bad = base / "failure_tree_bad"
    ft_manifest = _make_good_package(failure_tree_bad)
    _write(failure_tree_bad / ".light" / "failure_tree_report.json", json.dumps({
        "schema": "light.research_failure_tree_report.v1", "status": "FAIL",
        "issues": [{"code": "BRANCH_TREE_GAP"}],
    }, ensure_ascii=False, indent=2))
    ft = evaluate(failure_tree_bad, ft_manifest, final=True)
    check(
        ft["verdict"] == "FAIL" and any(x["code"] == "FAILURE_TREE_NOT_PASS" for x in ft["issues"]),
        "failure_tree 非 PASS 应 FAIL",
    )

    findings_bad = base / "findings_bad"
    fb_manifest = _make_good_package(findings_bad)
    _write(findings_bad / ".light" / "plan_findings.json", json.dumps(
        _good_findings("fail"), ensure_ascii=False, indent=2))
    fb = evaluate(findings_bad, fb_manifest, final=True)
    check(fb["verdict"] == "FAIL" and any(x["code"] == "PLAN_FINDINGS_FAIL" for x in fb["issues"]),
          "plan_findings verdict=fail 应 FAIL")

    templated = base / "templated"
    tpl_manifest = _make_good_package(templated)
    _write(templated / "PROJECT_PLAN.md", "# 研究方案：{{项目名}}\n\nTODO\n")
    tpl = evaluate(templated, tpl_manifest, final=True)
    check(tpl["verdict"] == "FAIL" and any(x["code"] == "TEMPLATE_PLACEHOLDER" for x in tpl["issues"]),
          "模板占位未填应 FAIL")

    if failures:
        print("[SELFTEST][research_package_gate] FAIL")
        for item in failures:
            print("  -", item)
        return 1
    print("[SELFTEST][research_package_gate] PASS:完整包 PASS、已授权 warning=WARN、未授权/未决策/"
          "target_chain fail/failure_tree fail/plan_findings fail/模板占位均 fail-closed")
    return 0


def _selftest() -> int:
    e2e_root = REPO_ROOT / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    base = pathlib.Path(
        tempfile.mkdtemp(prefix="research_package_gate_", dir=str(e2e_root))
    )
    try:
        return _selftest_at(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="research-plan 完整计划包交付门")
    parser.add_argument("--root", default=".", help="计划包根目录")
    parser.add_argument("--manifest", help="plan_package.json；推荐 final 交付必填")
    parser.add_argument("--final", action="store_true", help="最终交 experiment-coding 前启用硬门：缺授权/未处理 warning 即 fail")
    parser.add_argument("--json-out", help="写出完整 gate report JSON")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    report = evaluate(
        pathlib.Path(args.root),
        pathlib.Path(args.manifest) if args.manifest else None,
        final=args.final,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
