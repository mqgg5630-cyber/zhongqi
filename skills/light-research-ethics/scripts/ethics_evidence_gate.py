#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate research-ethics evidence, AI use, contribution, and untrusted content.

This is a provenance and language-safety gate. It does not decide legality,
misconduct, authorship disputes, or IRB/IACUC outcomes; it verifies that a
package does not claim those decisions without authority evidence.
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

_root = pathlib.Path(__file__).resolve()
while _root != _root.parent and not (_root / "_shared" / "__init__.py").exists():
    _root = _root.parent
sys.path.insert(0, str(_root))
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402

SCHEMA_ID = "light.research_ethics_evidence_packet.v1"
ETHICS_SCHEMA = "light.ethics_evidence.v1"
AI_SCHEMA = "light.ai_use_ledger.v1"
CONTRIB_SCHEMA = "light.contribution_record.v1"
BOUNDARY_SCHEMA = "light.untrusted_content_boundary.v1"

PACKAGE_READY = {"READY", "SUBMIT_READY", "PUBLISH_READY", "CAMERA_READY"}
DOC_TYPES = {
    "authority_decision", "irb_approval", "iacuc_approval", "ethics_waiver",
    "consent_process", "consent_form", "consent_waiver", "assent_form",
    "data_use_agreement", "license", "redistribution_permission",
    "data_management_plan", "deidentification_plan", "risk_register",
    "protocol", "recruitment_material", "venue_policy", "funder_policy",
}
DOC_STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "STALE", "NOT_APPLICABLE"}
AUTHORITY_KINDS = {"INSTITUTION", "REGULATOR", "FUNDER", "VENUE", "RIGHTS_HOLDER"}
AI_PURPOSES = {"writing", "polishing", "coding", "data_analysis", "statistics", "literature", "figure", "image", "other"}
DISCLOSURE_LOCS = {"methods", "acknowledgment", "ai_statement", "supplement", "not_required_by_policy", "none"}
CONTRIB_TYPES = {"HUMAN", "AI_TOOL", "ORGANIZATION"}
AUTHORSHIP = {"AUTHOR", "ACKNOWLEDGMENT", "NOT_AUTHOR", "EXCLUDE", "UNKNOWN"}
BOUNDARY_STATES = {"UNTRUSTED", "SANITIZED", "REJECTED"}
SOURCE_TYPES = {"web", "paper", "pdf", "dataset", "review", "user_upload", "external_tool", "email", "portal_export", "other"}
SIGNAL_STATES = {"SIGNAL", "ALLEGATION", "CONFIRMED_BY_AUTHORITY", "RESOLVED_CLEAN", "UNRESOLVED"}
ACCUSATION = re.compile(
    r"\b(fraud|fabricat(?:e|ed|ion)|falsif(?:y|ied|ication)|plagiaris(?:m|ed)|misconduct proven)\b|"
    r"已(?:证实|确认).{0,8}(造假|篡改|抄袭|学术不端)|"
    r"(造假|篡改|抄袭|学术不端).{0,8}(坐实|已证实|已确认)",
    re.I,
)
SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


def _real(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and "<" not in text and "{{" not in text and text.casefold() not in {
        "unknown", "unavailable", "pending", "gap", "待核查", "n/a",
    }


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _iso_date(value: Any) -> bool:
    return _date(value) is not None


def _future_date(value: Any) -> bool:
    parsed = _date(value)
    return parsed is not None and parsed > dt.date.today()


def _sha(value: Any) -> bool:
    return bool(SHA_RE.fullmatch(str(value or "")))


class FindingBag:
    def __init__(self) -> None:
        self.items: dict[str, list[tuple[str, Finding]]] = {
            "ethics_evidence": [],
            "ai_use_ledger": [],
            "contribution_record": [],
            "untrusted_content_boundary": [],
            "signal_language": [],
        }

    def add(self, gate: str, severity: str, loc: str, issue: str, fix: str, rule: str,
            evidence: str | None = None) -> None:
        self.items.setdefault(gate, []).append((
            severity,
            Finding(loc=loc, issue=issue, fix=fix, evidence=evidence, rule=rule),
        ))

    def gates(self) -> list[GateResult]:
        out: list[GateResult] = []
        for gate, rows in self.items.items():
            if not rows:
                out.append(GateResult(gate=gate, status="pass", severity="info"))
                continue
            severity = "critical" if any(sev == "critical" for sev, _ in rows) else "major"
            status = "fail" if severity == "critical" else "warn"
            out.append(GateResult(
                gate=gate,
                status=status,
                severity=severity,
                findings=[finding for _, finding in rows],
            ))
        return out


def _read_docs(ethics: dict[str, Any], bag: FindingBag) -> dict[str, list[dict[str, Any]]]:
    docs_by_type: dict[str, list[dict[str, Any]]] = {}
    docs = ethics.get("documents") or []
    if not isinstance(docs, list):
        raise ValueError("ethics_evidence.documents 必须是 list")
    for doc in docs:
        if not isinstance(doc, dict):
            raise ValueError("ethics document 必须是 object")
        doc_id = str(doc.get("doc_id") or "")
        doc_type = str(doc.get("type") or "")
        state = str(doc.get("status") or "UNKNOWN").upper()
        loc = doc_id or doc_type or "document"
        if not doc_id:
            bag.add("ethics_evidence", "critical", loc, "伦理证据文件缺 doc_id", "给每个证据稳定 ID", "DOC_ID_MISSING")
        if doc_type not in DOC_TYPES:
            bag.add("ethics_evidence", "critical", loc, f"未知 document type: {doc_type}", "使用受控 type 或扩展脚本", "DOC_TYPE_INVALID")
        if state not in DOC_STATES:
            bag.add("ethics_evidence", "critical", loc, f"非法 document status: {state}", "使用 VERIFIED/UNKNOWN/UNAVAILABLE/STALE/NOT_APPLICABLE", "DOC_STATUS_INVALID")
        if state == "VERIFIED":
            missing = [field for field in ("source", "locator", "checked_at") if not _real(doc.get(field))]
            if missing:
                bag.add("ethics_evidence", "critical", loc, f"VERIFIED 文件缺 {','.join(missing)}", "绑定真实来源、定位和核查日期", "VERIFIED_DOC_PROVENANCE_GAP")
            if doc.get("checked_at") and not _iso_date(doc.get("checked_at")):
                bag.add("ethics_evidence", "critical", loc, "checked_at 不是 ISO 日期", "写 YYYY-MM-DD", "DOC_DATE_INVALID")
            if _future_date(doc.get("checked_at")):
                bag.add(
                    "ethics_evidence", "critical", loc,
                    "checked_at is in the future",
                    "Use the actual verification date; future-dated evidence cannot be VERIFIED.",
                    "DOC_DATE_IN_FUTURE",
                )
            if doc.get("sha256") and not _sha(doc.get("sha256")):
                bag.add("ethics_evidence", "critical", loc, "sha256 格式非法", "写 64 位 SHA-256", "DOC_HASH_INVALID")
            if doc.get("authority_kind") and doc.get("authority_kind") not in AUTHORITY_KINDS:
                bag.add("ethics_evidence", "critical", loc, "authority_kind 非法", "使用机构/监管/资助/场地/权利人等受控值", "AUTHORITY_KIND_INVALID")
        docs_by_type.setdefault(doc_type, []).append(doc)
    return docs_by_type


def _verified(docs_by_type: dict[str, list[dict[str, Any]]], *types: str) -> bool:
    for doc_type in types:
        for doc in docs_by_type.get(doc_type, []):
            if (
                doc.get("status") == "VERIFIED"
                and _real(doc.get("source"))
                and _real(doc.get("locator"))
                and _iso_date(doc.get("checked_at"))
            ):
                return True
    return False


def _require_doc(
    bag: FindingBag,
    docs_by_type: dict[str, list[dict[str, Any]]],
    loc: str,
    reason: str,
    *types: str,
) -> None:
    if not _verified(docs_by_type, *types):
        bag.add(
            "ethics_evidence", "critical", loc,
            f"{reason} 需要 VERIFIED {'/'.join(types)}",
            "补充有权主体/权利人的真实文件 locator；UNKNOWN/STALE/UNAVAILABLE 不得放行",
            "REQUIRED_ETHICS_EVIDENCE_MISSING",
        )


def _ethics(spec: dict[str, Any], bag: FindingBag, ready: bool) -> None:
    ethics = spec.get("ethics_evidence") or {}
    if ethics.get("schema") != ETHICS_SCHEMA:
        bag.add("ethics_evidence", "critical", "ethics_evidence.schema", "schema 不匹配", f"使用 {ETHICS_SCHEMA}", "ETHICS_SCHEMA_INVALID")
        return
    context = ethics.get("context") or {}
    requirements = ethics.get("requirements") or {}
    if not isinstance(context, dict) or not isinstance(requirements, dict):
        raise ValueError("ethics_evidence.context/requirements 必须是 object")
    docs_by_type = _read_docs(ethics, bag)
    participants = str(context.get("participants") or "UNKNOWN").upper()
    data_class = str(context.get("data_classification") or "UNKNOWN").upper()
    if ready:
        for field in ("project_id", "jurisdiction", "institution", "owner", "checked_at"):
            if not _real(context.get(field)):
                bag.add("ethics_evidence", "critical", f"context.{field}", f"package-ready 缺 {field}", "补录或降级为非 ready", "ETHICS_CONTEXT_GAP")
        if context.get("checked_at") and not _iso_date(context.get("checked_at")):
            bag.add("ethics_evidence", "critical", "context.checked_at", "checked_at 不是 ISO 日期", "写 YYYY-MM-DD", "ETHICS_CONTEXT_DATE_INVALID")
        if _future_date(context.get("checked_at")):
            bag.add(
                "ethics_evidence", "critical", "context.checked_at",
                "checked_at is in the future",
                "Use the actual ethics packet review date; future-dated readiness evidence is invalid.",
                "ETHICS_CONTEXT_DATE_IN_FUTURE",
            )
    if participants in {"HUMAN", "BOTH"} and requirements.get("irb") == "REQUIRED":
        _require_doc(bag, docs_by_type, "requirements.irb", "涉人且 IRB/伦理审查为 REQUIRED", "authority_decision", "irb_approval", "ethics_waiver")
    if participants in {"ANIMAL", "BOTH"} and requirements.get("iacuc") == "REQUIRED":
        _require_doc(bag, docs_by_type, "requirements.iacuc", "涉动物且 IACUC/动物伦理为 REQUIRED", "authority_decision", "iacuc_approval")
    consent = requirements.get("consent") or {}
    if isinstance(consent, dict) and consent.get("required") is True:
        if not (_verified(docs_by_type, "consent_process") and _verified(docs_by_type, "consent_form")) and not _verified(docs_by_type, "consent_waiver"):
            bag.add(
                "ethics_evidence", "critical", "requirements.consent",
                "知情同意需要 process+form 或 authority waiver 的 VERIFIED 证据",
                "补充 consent 过程/文件，或机构 waiver；不能用口头描述替代",
                "CONSENT_EVIDENCE_MISSING",
            )
    if requirements.get("dua") == "REQUIRED" or data_class in {"IDENTIFIABLE", "SENSITIVE", "CONTROLLED", "THIRD_PARTY"}:
        _require_doc(bag, docs_by_type, "requirements.dua", "受控/可识别/第三方数据", "data_use_agreement")
    if requirements.get("license") == "REQUIRED" or requirements.get("redistribution") == "REQUIRED":
        _require_doc(bag, docs_by_type, "requirements.license", "外部数据/代码/材料许可或再分发", "license", "redistribution_permission")
    if requirements.get("data_release") == "REQUIRED":
        _require_doc(bag, docs_by_type, "requirements.data_release", "数据/代码/补充材料发布", "data_management_plan", "deidentification_plan")
    if ready and not _verified(docs_by_type, "risk_register"):
        bag.add("ethics_evidence", "major", "risk_register", "package-ready 未见 risk register", "补充风险、缓解和 owner；若确不适用写 authority 证据", "RISK_REGISTER_MISSING")


def _ai(spec: dict[str, Any], bag: FindingBag, ready: bool) -> None:
    ledger = spec.get("ai_use_ledger") or {}
    if ledger.get("schema") != AI_SCHEMA:
        bag.add("ai_use_ledger", "critical", "ai_use_ledger.schema", "schema 不匹配", f"使用 {AI_SCHEMA}", "AI_SCHEMA_INVALID")
        return
    policy = ledger.get("venue_policy") or {}
    policy_state = str(policy.get("status") or "UNKNOWN").upper()
    if ready and policy_state != "VERIFIED":
        bag.add("ai_use_ledger", "critical", "venue_policy", "交付前目标 venue/funder AI 政策未 VERIFIED", "联网或由用户提供当天官方政策 locator；未知不得放行", "AI_POLICY_UNVERIFIED")
    if policy_state == "VERIFIED" and not (_real(policy.get("source")) and _real(policy.get("locator")) and _iso_date(policy.get("checked_at"))):
        bag.add("ai_use_ledger", "critical", "venue_policy", "VERIFIED AI policy 缺 source/locator/checked_at", "绑定目标 venue/funder 官方政策", "AI_POLICY_PROVENANCE_GAP")
    if policy_state == "VERIFIED" and _future_date(policy.get("checked_at")):
        bag.add(
            "ai_use_ledger", "critical", "venue_policy",
            "AI policy checked_at is in the future",
            "Use the actual policy retrieval/review date; future-dated policy evidence is not VERIFIED.",
            "AI_POLICY_DATE_IN_FUTURE",
        )
    uses = ledger.get("uses") or []
    if not isinstance(uses, list):
        raise ValueError("ai_use_ledger.uses 必须是 list")
    for use in uses:
        use_id = str(use.get("use_id") or "ai-use")
        purpose = str(use.get("purpose") or "other")
        if purpose not in AI_PURPOSES:
            bag.add("ai_use_ledger", "critical", use_id, f"未知 AI purpose: {purpose}", "使用受控 purpose", "AI_PURPOSE_INVALID")
        if use.get("listed_as_author") is True:
            bag.add("ai_use_ledger", "critical", use_id, "AI 工具不得列作者", "移出作者列表，按 venue 政策披露用途", "AI_LISTED_AS_AUTHOR")
        if use.get("generated_scientific_figure") is True:
            bag.add("ai_use_ledger", "critical", use_id, "论文数据图/科学图不得 AI 生图", "用程序化绘图并保留代码、数据和 seed", "AI_GENERATED_SCIENTIFIC_FIGURE")
        if use.get("human_reviewed") is not True:
            bag.add("ai_use_ledger", "critical", use_id, "AI 输出缺人工复核确认", "作者逐项复核事实、代码、引用、偏差和版权", "AI_HUMAN_REVIEW_GAP")
        disclosure = str(use.get("disclosure_location") or "none")
        if disclosure not in DISCLOSURE_LOCS:
            bag.add("ai_use_ledger", "critical", use_id, "disclosure_location 非法", "使用受控披露位置", "AI_DISCLOSURE_LOCATION_INVALID")
        if ready and purpose in {"data_analysis", "statistics", "figure", "image", "coding"} and disclosure not in {"methods", "ai_statement", "supplement"}:
            bag.add("ai_use_ledger", "critical", use_id, "分析/代码/作图类 AI 使用未进入方法或补充披露", "按目标政策写入 methods/AI statement/supplement", "AI_METHODS_DISCLOSURE_GAP")
        if ready and purpose in {"writing", "polishing", "literature"} and disclosure == "none" and policy.get("requires_disclosure") is not False:
            bag.add("ai_use_ledger", "major", use_id, "写作/文献类 AI 使用未披露且无政策豁免", "按目标政策写致谢/AI statement；或绑定 not_required_by_policy", "AI_DISCLOSURE_GAP")
        if use.get("prohibited_by_policy") is True and use.get("status") not in {"REMOVED", "NOT_USED"}:
            bag.add("ai_use_ledger", "critical", use_id, "AI 用途被目标政策禁止但仍保留", "移除该用途并记录替代路径", "AI_POLICY_PROHIBITED_USE")


def _contrib(spec: dict[str, Any], bag: FindingBag, ready: bool) -> None:
    record = spec.get("contribution_record") or {}
    if record.get("schema") != CONTRIB_SCHEMA:
        bag.add("contribution_record", "critical", "contribution_record.schema", "schema 不匹配", f"使用 {CONTRIB_SCHEMA}", "CONTRIB_SCHEMA_INVALID")
        return
    contributors = record.get("contributors") or []
    if not isinstance(contributors, list) or not contributors:
        bag.add("contribution_record", "critical", "contributors", "贡献记录为空", "列出人类作者、致谢对象、组织和 AI 工具", "CONTRIBUTORS_MISSING")
        return
    for person in contributors:
        cid = str(person.get("contributor_id") or person.get("name") or "contributor")
        ctype = str(person.get("type") or "HUMAN").upper()
        decision = str(person.get("authorship_decision") or "UNKNOWN").upper()
        if ctype not in CONTRIB_TYPES:
            bag.add("contribution_record", "critical", cid, f"贡献者 type 非法: {ctype}", "使用 HUMAN/AI_TOOL/ORGANIZATION", "CONTRIB_TYPE_INVALID")
        if decision not in AUTHORSHIP:
            bag.add("contribution_record", "critical", cid, f"authorship_decision 非法: {decision}", "使用 AUTHOR/ACKNOWLEDGMENT/NOT_AUTHOR/EXCLUDE/UNKNOWN", "AUTHORSHIP_DECISION_INVALID")
        if ctype == "AI_TOOL" and decision == "AUTHOR":
            bag.add("contribution_record", "critical", cid, "AI 工具不得作为作者", "改为 AI use ledger 披露，不进入作者资格", "AI_AUTHORSHIP_FORBIDDEN")
        icmje = person.get("icmje") or {}
        if decision == "AUTHOR":
            missing = [key for key in ("substantial_contribution", "drafting_or_review", "final_approval", "accountable") if icmje.get(key) is not True]
            if missing:
                bag.add("contribution_record", "critical", cid, f"作者缺 ICMJE 条件: {','.join(missing)}", "缺一则不能署名；改致谢或补足真实贡献/批准/责任", "ICMJE_AUTHORSHIP_GAP")
            if ready and not _real(person.get("final_approval_locator")):
                bag.add("contribution_record", "critical", cid, "作者缺 final approval locator", "收集终稿批准记录；不能由模型代签", "FINAL_APPROVAL_LOCATOR_MISSING")
        if decision == "AUTHOR" and str(person.get("authorship_basis") or "").upper() == "CREDIT_ONLY":
            bag.add("contribution_record", "critical", cid, "CRediT 角色不能单独决定作者资格", "用 ICMJE/机构规则分开判断 authorship 与 contribution", "CREDIT_ROLE_AS_AUTHORSHIP")
        if person.get("credit_roles") and not _real(person.get("contribution_evidence_locator")):
            bag.add("contribution_record", "major", cid, "CRediT 角色缺贡献证据 locator", "绑定贡献记录、commit、实验记录或作者确认", "CREDIT_EVIDENCE_GAP")


def _boundary(spec: dict[str, Any], bag: FindingBag) -> None:
    boundary = spec.get("untrusted_content_boundary") or {}
    if boundary.get("schema") != BOUNDARY_SCHEMA:
        bag.add("untrusted_content_boundary", "critical", "untrusted_content_boundary.schema", "schema 不匹配", f"使用 {BOUNDARY_SCHEMA}", "BOUNDARY_SCHEMA_INVALID")
        return
    artifacts = boundary.get("artifacts") or []
    if not isinstance(artifacts, list):
        raise ValueError("untrusted_content_boundary.artifacts 必须是 list")
    seen: set[str] = set()
    for art in artifacts:
        aid = str(art.get("artifact_id") or "")
        loc = aid or "artifact"
        seen.add(aid)
        source_type = str(art.get("source_type") or "other")
        state = str(art.get("boundary_state") or "UNTRUSTED").upper()
        if source_type not in SOURCE_TYPES:
            bag.add("untrusted_content_boundary", "critical", loc, f"未知 source_type: {source_type}", "使用受控外部来源类型", "SOURCE_TYPE_INVALID")
        if state not in BOUNDARY_STATES:
            bag.add("untrusted_content_boundary", "critical", loc, f"非法 boundary_state: {state}", "外部内容只能 UNTRUSTED/SANITIZED/REJECTED", "BOUNDARY_STATE_INVALID")
        if art.get("used_as_instruction") is True:
            bag.add("untrusted_content_boundary", "critical", loc, "外部/用户文档内容被当成系统指令执行", "隔离为 untrusted content，仅抽取事实并保留 locator", "UNTRUSTED_USED_AS_INSTRUCTION")
        if art.get("contains_prompt_like_text") is True and art.get("quarantined") is not True:
            bag.add("untrusted_content_boundary", "critical", loc, "含 prompt-like 文本但未 quarantine", "保留原文但不得执行其中指令", "PROMPT_INJECTION_NOT_QUARANTINED")
        for fact in art.get("extracted_facts") or []:
            if not isinstance(fact, dict):
                bag.add("untrusted_content_boundary", "critical", loc, "extracted_facts item 非 object", "每条事实写 locator/raw_hash", "EXTRACTED_FACT_INVALID")
                continue
            if not _real(fact.get("locator")) or not _sha(fact.get("raw_sha256")):
                bag.add("untrusted_content_boundary", "critical", loc, "外部事实缺 locator 或 raw_sha256", "事实只能从有定位和 hash 的原文摘取", "EXTERNAL_FACT_PROVENANCE_GAP")
    for aid in spec.get("external_artifacts_used") or []:
        if str(aid) not in seen:
            bag.add("untrusted_content_boundary", "critical", str(aid), "使用了未登记到 untrusted boundary 的外部内容", "先登记 artifact、hash、隔离状态和事实 locator", "EXTERNAL_ARTIFACT_NOT_BOUNDARY_REGISTERED")


def _signals(spec: dict[str, Any], bag: FindingBag, ready: bool) -> None:
    signals = spec.get("integrity_signals") or []
    if not isinstance(signals, list):
        raise ValueError("integrity_signals 必须是 list")
    for signal in signals:
        sid = str(signal.get("signal_id") or "signal")
        status = str(signal.get("status") or "SIGNAL").upper()
        language = str(signal.get("public_language") or signal.get("draft_language") or "")
        if status not in SIGNAL_STATES:
            bag.add("signal_language", "critical", sid, f"信号 status 非法: {status}", "使用 SIGNAL/ALLEGATION/CONFIRMED_BY_AUTHORITY/RESOLVED_CLEAN/UNRESOLVED", "SIGNAL_STATUS_INVALID")
        if status != "CONFIRMED_BY_AUTHORITY" and ACCUSATION.search(language):
            bag.add("signal_language", "critical", sid, "把风险信号写成了定罪/已证实", "改为“信号/疑似/需人工复核”，并交由机构/期刊流程", "SIGNAL_WRITTEN_AS_VERDICT")
        if status == "CONFIRMED_BY_AUTHORITY" and not _real(signal.get("authority_locator")):
            bag.add("signal_language", "critical", sid, "CONFIRMED_BY_AUTHORITY 缺 authority locator", "只有机构/期刊/监管有权结论可写 confirmed", "CONFIRMED_SIGNAL_NO_AUTHORITY")
        if ready and status in {"SIGNAL", "ALLEGATION", "UNRESOLVED"}:
            if not _real(signal.get("evidence_locator")) or not _real(signal.get("escalation_owner")):
                bag.add("signal_language", "critical", sid, "未闭环风险信号缺 evidence_locator/escalation_owner", "绑定证据、owner 和升级路径；不能静默提交", "SIGNAL_ESCALATION_GAP")


def evaluate(spec: dict[str, Any]) -> FindingsReport:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    ready = str((spec.get("package") or {}).get("status") or "DRAFT").upper() in PACKAGE_READY
    bag = FindingBag()
    _ethics(spec, bag, ready)
    _ai(spec, bag, ready)
    _contrib(spec, bag, ready)
    _boundary(spec, bag)
    _signals(spec, bag, ready)
    return FindingsReport(
        producer="research-ethics",
        target=str((spec.get("package") or {}).get("target") or "ethics-evidence-packet"),
        gates=bag.gates(),
        summary=(
            "核 ethics_evidence、ai_use_ledger、contribution_record、untrusted-content "
            "boundary 与 allegation/status/evidence/escalation 语言；不作机构裁定。"
        ),
        fresh_evidence=True,
    ).finalize()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("input must be JSON object")
    return value


def _good() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "package": {"status": "SUBMIT_READY", "target": "paper.md"},
        "ethics_evidence": {
            "schema": ETHICS_SCHEMA,
            "context": {
                "project_id": "public-study", "jurisdiction": "declared",
                "institution": "declared institution", "owner": "project owner",
                "participants": "HUMAN", "data_classification": "IDENTIFIABLE",
                "checked_at": "2026-07-04",
            },
            "requirements": {
                "irb": "REQUIRED", "consent": {"required": True},
                "dua": "REQUIRED", "license": "NOT_REQUIRED", "data_release": "REQUIRED",
            },
            "documents": [
                {"doc_id": "irb", "type": "irb_approval", "status": "VERIFIED", "source": "institution IRB", "locator": "irb.pdf:1", "checked_at": "2026-07-04", "authority_kind": "INSTITUTION"},
                {"doc_id": "consent-process", "type": "consent_process", "status": "VERIFIED", "source": "protocol", "locator": "protocol.pdf:4", "checked_at": "2026-07-04"},
                {"doc_id": "consent-form", "type": "consent_form", "status": "VERIFIED", "source": "consent.pdf", "locator": "consent.pdf:1", "checked_at": "2026-07-04"},
                {"doc_id": "dua", "type": "data_use_agreement", "status": "VERIFIED", "source": "dua.pdf", "locator": "dua.pdf:1", "checked_at": "2026-07-04"},
                {"doc_id": "dmp", "type": "data_management_plan", "status": "VERIFIED", "source": "dmp.md", "locator": "dmp.md:1", "checked_at": "2026-07-04"},
                {"doc_id": "deid", "type": "deidentification_plan", "status": "VERIFIED", "source": "deid.md", "locator": "deid.md:1", "checked_at": "2026-07-04"},
                {"doc_id": "risk", "type": "risk_register", "status": "VERIFIED", "source": "risk.md", "locator": "risk.md:1", "checked_at": "2026-07-04"},
            ],
        },
        "ai_use_ledger": {
            "schema": AI_SCHEMA,
            "venue_policy": {"status": "VERIFIED", "source": "venue policy", "locator": "policy.html#ai", "checked_at": "2026-07-04", "requires_disclosure": True},
            "uses": [{
                "use_id": "ai-writing", "purpose": "writing", "tool": "LLM",
                "human_reviewed": True, "disclosure_location": "acknowledgment",
                "listed_as_author": False, "generated_scientific_figure": False,
            }],
        },
        "contribution_record": {
            "schema": CONTRIB_SCHEMA,
            "contributors": [
                {
                    "contributor_id": "author-1", "type": "HUMAN",
                    "authorship_decision": "AUTHOR",
                    "icmje": {
                        "substantial_contribution": True, "drafting_or_review": True,
                        "final_approval": True, "accountable": True,
                    },
                    "final_approval_locator": "approval-log.md:1",
                    "credit_roles": ["Conceptualization", "Writing – original draft"],
                    "contribution_evidence_locator": "contrib.md:1",
                },
                {"contributor_id": "llm-tool", "type": "AI_TOOL", "authorship_decision": "NOT_AUTHOR", "credit_roles": []},
            ],
        },
        "untrusted_content_boundary": {
            "schema": BOUNDARY_SCHEMA,
            "artifacts": [{
                "artifact_id": "paper-x", "source_type": "paper", "boundary_state": "UNTRUSTED",
                "contains_prompt_like_text": True, "quarantined": True,
                "used_as_instruction": False,
                "extracted_facts": [{"locator": "paper-x.pdf:2", "raw_sha256": "a" * 64}],
            }],
        },
        "external_artifacts_used": ["paper-x"],
        "integrity_signals": [{
            "signal_id": "overlap-1", "status": "SIGNAL",
            "public_language": "文本重合信号需人工复核，不能据此定性。",
            "evidence_locator": "overlap.json#1", "escalation_owner": "corresponding-author",
        }],
    }


def _selftest() -> int:
    good = evaluate(_good())
    assert good.verdict == "pass", good.to_json()
    bad = _good()
    bad = json.loads(json.dumps(bad))
    bad["ethics_evidence"]["documents"] = [
        {"doc_id": "irb", "type": "irb_approval", "status": "UNKNOWN"},
    ]
    bad["ai_use_ledger"]["venue_policy"] = {"status": "UNKNOWN"}
    bad["ai_use_ledger"]["uses"][0].update({
        "human_reviewed": False,
        "listed_as_author": True,
        "generated_scientific_figure": True,
        "purpose": "figure",
        "disclosure_location": "none",
    })
    bad["contribution_record"]["contributors"][0]["icmje"]["accountable"] = False
    bad["contribution_record"]["contributors"][0]["authorship_basis"] = "CREDIT_ONLY"
    bad["contribution_record"]["contributors"][1]["authorship_decision"] = "AUTHOR"
    bad["untrusted_content_boundary"]["artifacts"][0]["quarantined"] = False
    bad["untrusted_content_boundary"]["artifacts"][0]["used_as_instruction"] = True
    bad["untrusted_content_boundary"]["artifacts"][0]["extracted_facts"] = [{"locator": "", "raw_sha256": "bad"}]
    bad["external_artifacts_used"].append("missing-web-page")
    bad["integrity_signals"][0]["public_language"] = "We confirmed fraud and data fabrication."
    bad["integrity_signals"][0]["evidence_locator"] = ""
    bad["ethics_evidence"]["context"]["checked_at"] = "2999-01-01"
    bad["ethics_evidence"]["documents"].append({
        "doc_id": "future-license",
        "type": "license",
        "status": "VERIFIED",
        "source": "rights holder",
        "locator": "license.pdf:1",
        "checked_at": "2999-01-01",
    })
    report = evaluate(bad)
    assert report.verdict == "fail", report.to_json()
    rules = {finding.rule for gate in report.gates for finding in gate.findings}
    assert {
        "REQUIRED_ETHICS_EVIDENCE_MISSING", "CONSENT_EVIDENCE_MISSING",
        "AI_POLICY_UNVERIFIED", "AI_LISTED_AS_AUTHOR", "AI_GENERATED_SCIENTIFIC_FIGURE",
        "AI_HUMAN_REVIEW_GAP", "ICMJE_AUTHORSHIP_GAP", "CREDIT_ROLE_AS_AUTHORSHIP",
        "AI_AUTHORSHIP_FORBIDDEN", "UNTRUSTED_USED_AS_INSTRUCTION",
        "PROMPT_INJECTION_NOT_QUARANTINED", "EXTERNAL_FACT_PROVENANCE_GAP",
        "EXTERNAL_ARTIFACT_NOT_BOUNDARY_REGISTERED", "SIGNAL_WRITTEN_AS_VERDICT",
        "SIGNAL_ESCALATION_GAP", "DOC_DATE_IN_FUTURE",
        "ETHICS_CONTEXT_DATE_IN_FUTURE",
    } <= rules
    future_policy = _good()
    future_policy["ai_use_ledger"]["venue_policy"]["checked_at"] = "2999-01-01"
    future_report = evaluate(future_policy)
    future_rules = {
        finding.rule for gate in future_report.gates for finding in gate.findings
    }
    assert "AI_POLICY_DATE_IN_FUTURE" in future_rules
    print("ethics_evidence_gate selftest PASS: evidence/AI/contribution/boundary/signal language")
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
