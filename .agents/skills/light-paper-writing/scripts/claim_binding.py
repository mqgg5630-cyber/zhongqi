#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-claim draft-to-evidence binding for paper-writing.

This module deliberately does not change ``_shared/evidence_contract``. It
adds the missing writing-side join:

    current draft SHA-256 -> exact draft claim -> evidence claim_id(s) -> source locator(s)
    -> result-card decision/language/guardrail summary

The canonical artifact is ``light.paper_claims.v1``. A strong assertion that
is absent from the artifact, points to an unknown evidence ID, or binds only
``none`` evidence is an uncovered claim. A claim map whose ``draft_sha256`` does
not match the current draft is stale and fails closed. Wording checks use only
the evidence bound to that claim; the strongest unrelated evidence can never
license it. Empirical claims also have to carry the result-analysis
``result_card`` handoff so guardrail/counter-metric decisions cannot vanish
between result cards and manuscript prose.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))

from _shared import evidence_contract as ec  # noqa: E402

CLAIM_MAP_SCHEMA = "light.paper_claims.v1"
_GRADE_ORDER = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}
_PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_EMPIRICAL_CLAIM_TYPES = {"RESULT", "NULL_RESULT", "MECHANISM", "CAUSAL"}
_NON_RESULT_CARD_CLAIM_TYPES = {"METHOD", "POSITIONING", "LIMITATION", "SPECULATION"}
_READY_DECISIONS = {"CLAIM_READY"}
_BLOCKING_GUARDRAILS = {"FAIL", "UNKNOWN"}
_GUARDRAIL_STATUSES = {"PASS", "WARN", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
_GUARDRAIL_RANK = {"PASS": 0, "NOT_APPLICABLE": 0, "WARN": 1, "UNKNOWN": 2, "FAIL": 3}


def draft_sha256(text: str) -> str:
    """Return the canonical UTF-8 SHA-256 for the exact draft text under review."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_hex64(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in value)


def _as_of_date(as_of: str | dt.date | dt.datetime | None) -> dt.date:
    if as_of is None:
        return dt.date.today()
    if isinstance(as_of, dt.datetime):
        return as_of.date()
    if isinstance(as_of, dt.date):
        return as_of
    text = str(as_of).strip()
    if not text:
        return dt.date.today()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return dt.date.fromisoformat(text)


def _parse_iso_temporal(value: object) -> dt.date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            return None


def _is_placeholder(value: object) -> bool:
    return isinstance(value, str) and bool(_PLACEHOLDER_RE.search(value.strip()))


def _is_public_relative_locator(value: object) -> bool:
    """Return whether a locator is portable and safe to keep in a public artifact."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or _is_placeholder(text):
        return False
    if _WINDOWS_DRIVE_RE.match(text) or text.startswith(("/", "\\", "~")):
        return False
    path_part = text.replace("\\", "/").split("#", 1)[0]
    return ".." not in path_part.split("/")


def _temporal_findings(raw: dict, *, context: str, fields: list[str],
                       as_of: dt.date) -> list[dict]:
    findings: list[dict] = []
    for field in fields:
        value = raw.get(field)
        if value in (None, ""):
            continue
        loc = f"{context}.{field}"
        if _is_placeholder(value):
            findings.append(_problem(
                "claim_provenance.date_placeholder", "", loc,
                f"{loc} 仍是占位符，不能冒充已核验时间。",
                suggestion="写入真实 ISO 日期/时间；未核验就删除该字段或标为待核查的人读备注。"))
            continue
        parsed = _parse_iso_temporal(value)
        if parsed is None:
            findings.append(_problem(
                "claim_provenance.date_invalid", "", loc,
                f"{loc}={value!r} 不是 ISO-8601 日期/时间。",
                suggestion="使用 YYYY-MM-DD 或带时区的 ISO-8601 时间。"))
        elif parsed > as_of:
            findings.append(_problem(
                "claim_provenance.date_future", "", loc,
                f"{loc}={value!r} 晚于 as_of={as_of.isoformat()}，不能预填未来核验。",
                suggestion="改为真实发生的核验/捕获时间；未来计划写入 notes，不写入 checked_at/captured_at。"))
    return findings


def _validate_plan_provenance(claim_map: dict, *, as_of: dt.date) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []

    metadata = claim_map.get("metadata") or {}
    if isinstance(metadata, dict):
        errors.extend(_temporal_findings(metadata,
                                         context="metadata",
                                         fields=["checked_at", "created_at", "updated_at"],
                                         as_of=as_of))
    else:
        errors.append(_problem(
            "claim_provenance.metadata_invalid", "", "metadata",
            "metadata 必须是对象。"))

    venue = claim_map.get("venue") or {}
    if isinstance(venue, dict):
        errors.extend(_temporal_findings(venue, context="venue",
                                         fields=["checked_at"], as_of=as_of))
        source = venue.get("requirements_source")
        if isinstance(source, str) and _is_placeholder(source):
            warnings.append(_problem(
                "claim_provenance.venue_source_placeholder", "", "venue.requirements_source",
                "venue requirements_source 仍是占位符；不能把 venue 要求说成已核。",
                suggestion="填官方 URL/版本化本地副本；暂未核验就删除该字段并在人读备注写待核查。"))
    else:
        errors.append(_problem(
            "claim_provenance.venue_invalid", "", "venue",
            "venue 必须是对象。"))

    draft_path = claim_map.get("draft_path")
    if isinstance(draft_path, str) and draft_path.strip():
        if _is_placeholder(draft_path):
            errors.append(_problem(
                "claim_provenance.draft_path_placeholder", "", "draft_path",
                "draft_path 仍是占位符，claim map 不能证明绑定的是哪个草稿文件。",
                suggestion="写包内相对路径，如 draft/paper.md；不要留下模板占位符。"))
        elif not _is_public_relative_locator(draft_path):
            errors.append(_problem(
                "claim_provenance.draft_path_unsafe", "", "draft_path",
                "draft_path 必须是可公开交接的相对路径，不能是绝对路径、家目录或 .. 越界路径。",
                suggestion="改为交付包内相对路径；私人本机路径留在仓库外。"))

    artifacts = claim_map.get("source_artifacts")
    if artifacts in (None, ""):
        return errors, warnings
    if not isinstance(artifacts, list):
        errors.append(_problem(
            "claim_provenance.source_artifacts_invalid", "", "source_artifacts",
            "source_artifacts 必须是数组；没有上游 provenance 时应设为空数组或删除字段。"))
        return errors, warnings

    for index, artifact in enumerate(artifacts):
        loc = f"source_artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(_problem(
                "claim_provenance.source_artifact_invalid", "", loc,
                "source_artifacts 条目必须是对象。"))
            continue
        errors.extend(_temporal_findings(artifact, context=loc,
                                         fields=["captured_at", "checked_at"],
                                         as_of=as_of))
        path = artifact.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append(_problem(
                "claim_provenance.source_path_missing", "", f"{loc}.path",
                "source_artifact 缺 path，无法追到真实 evidence 工件。",
                suggestion="填交付包内相对路径；若没有真实工件，不要保留该 source_artifacts 条目。"))
        elif _is_placeholder(path):
            errors.append(_problem(
                "claim_provenance.source_path_placeholder", "", f"{loc}.path",
                "source_artifact.path 仍是占位符，不能冒充真实 evidence 工件。",
                suggestion="填真实相对路径，或删除该未落实的 source_artifacts 条目。"))
        elif not _is_public_relative_locator(path):
            errors.append(_problem(
                "claim_provenance.source_path_unsafe", "", f"{loc}.path",
                "source_artifact.path 必须是公开交接包内相对路径；绝对路径/.. 越界会泄漏或失效。",
                suggestion="改成 analysis/evidence_strength.json 这类相对路径。"))

        sha = artifact.get("sha256")
        if isinstance(sha, str) and sha.strip():
            if _is_placeholder(sha):
                errors.append(_problem(
                    "claim_provenance.source_hash_placeholder", "", f"{loc}.sha256",
                    "source_artifact.sha256 仍是占位符；哈希不可预填。",
                    suggestion="有真实文件就写 64 位 SHA-256；没有就留空，不写假值。"))
            elif not _is_hex64(sha.strip()):
                errors.append(_problem(
                    "claim_provenance.source_hash_invalid", "", f"{loc}.sha256",
                    "source_artifact.sha256 不是 64 位十六进制 SHA-256。",
                    suggestion="重新对真实 artifact 计算 SHA-256；未知时留空。"))

        for field in ("artifact_id", "run", "commit", "owner"):
            value = artifact.get(field)
            if isinstance(value, str) and value.strip() and _is_placeholder(value):
                warnings.append(_problem(
                    "claim_provenance.source_field_placeholder", "", f"{loc}.{field}",
                    f"source_artifact.{field} 仍是占位符；交付时会造成伪 provenance。",
                    suggestion="有真实值就填；没有就留空。"))
    return errors, warnings


def load_claim_map(path: str | pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _grade(claim: dict) -> str:
    return claim.get("evidence_grade") or ec.grade_evidence(
        claim.get("q_fdr"), claim.get("effect_size"), claim.get("ci95"), claim.get("n"))


def _best_grade(claims: list[dict]) -> str | None:
    if not claims:
        return None
    return max((_grade(claim) for claim in claims),
               key=lambda grade: _GRADE_ORDER.get(grade, 0))


def wording_hits(text: str, grade: str) -> list[dict]:
    """Return de-duplicated real wording hits for one text span and grade."""
    hits, seen = [], set()
    for violation in ec.lint_wording(text, {"evidence_grade": grade}):
        matched = violation.get("matched")
        if not matched:
            continue
        key = (violation.get("loc"), str(matched).casefold())
        if key not in seen:
            seen.add(key)
            hits.append(violation)
    return hits


def _problem(code: str, claim_id: str, locator: str, message: str,
             *, matched: str = "", evidence_ids: list[str] | None = None,
             suggestion: str = "") -> dict:
    return {
        "code": code,
        "claim_id": claim_id,
        "locator": locator,
        "message": message,
        "matched": matched,
        "evidence_claim_ids": evidence_ids or [],
        "suggestion": suggestion,
    }


def _result_card_required(raw: dict, evidence_ids: list[str]) -> bool:
    """Return whether this manuscript claim must carry a result-card handoff."""
    if not evidence_ids:
        return False
    claim_type = str(raw.get("claim_type") or "").strip().upper()
    if claim_type in _NON_RESULT_CARD_CLAIM_TYPES:
        return False
    if claim_type and claim_type not in _EMPIRICAL_CLAIM_TYPES:
        return False
    status = str(raw.get("status") or "").strip().upper()
    return status not in {"GAP", "SPECULATIVE", "MISSING"}


def _first_result_card_ref(raw: dict) -> dict | None:
    """Accept a single ``result_card`` object or the first ``result_card_refs`` item."""
    ref = raw.get("result_card") or raw.get("result_card_ref")
    if ref is None and isinstance(raw.get("result_card_refs"), list) and raw["result_card_refs"]:
        ref = raw["result_card_refs"][0]
    return ref if isinstance(ref, dict) else None


def _guardrail_status_from_checks(checks: object) -> str:
    if not isinstance(checks, list):
        return ""
    statuses: list[str] = []
    for check in checks:
        if isinstance(check, dict):
            status = str(check.get("status") or "").strip().upper()
            if status:
                statuses.append(status)
    if not statuses:
        return ""
    return max(statuses, key=lambda item: _GUARDRAIL_RANK.get(item, -1))


def _has_limitation(raw: dict) -> bool:
    limitations = raw.get("limitations")
    if isinstance(limitations, list):
        return any(str(item).strip() and not _is_placeholder(str(item)) for item in limitations)
    if isinstance(limitations, str):
        return bool(limitations.strip() and not _is_placeholder(limitations))
    return False


def _validate_result_card_ref(raw: dict, *, claim_id: str, locator: str,
                              evidence_ids: list[str]) -> tuple[list[dict], list[dict], dict | None]:
    """Validate result-analysis result-card handoff for one empirical manuscript claim.

    The claim map stores a compact, hash-bound summary instead of duplicating the
    whole result card. The goal is to prove paper-writing saw the upstream
    decision, language strength, and guardrail/counter-metric claim impact before
    prose was strengthened.
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    if not _result_card_required(raw, evidence_ids):
        return errors, warnings, None

    loc = locator or f"claim:{claim_id or '<missing>'}"
    ref = _first_result_card_ref(raw)
    if ref is None:
        errors.append(_problem(
            "result_card.missing", claim_id, loc,
            "实证 claim 已绑定 evidence_strength，但缺 result_card 摘要；"
            "写作阶段无法证明已消费 guardrail/counter-metric 与 CLAIM_READY 决策。",
            evidence_ids=evidence_ids,
            suggestion="从 result-analysis 的 light.result_card.v1 抄入 locator、sha256、decision、"
                       "language_strength 与 guardrail_summary；不要只靠 evidence_strength 写强结论。"))
        return errors, warnings, None

    ref_locator = str(ref.get("locator") or ref.get("path") or "").strip()
    ref_sha = str(ref.get("sha256") or ref.get("result_card_sha256") or "").strip()
    decision = str(ref.get("decision") or "").strip().upper()
    language_strength = str(ref.get("language_strength") or ref.get("strength") or "").strip().upper()
    result_claim_id = str(ref.get("claim_id") or ref.get("result_claim_id") or "").strip()
    summary = {
        "claim_id": result_claim_id,
        "locator": ref_locator,
        "sha256": ref_sha,
        "decision": decision,
        "language_strength": language_strength,
        "guardrail": None,
    }

    if not ref_locator:
        errors.append(_problem(
            "result_card.locator_missing", claim_id, loc,
            "result_card 缺 locator，无法复核 guardrail/decision 来源。",
            evidence_ids=evidence_ids,
            suggestion="填公开交接包内相对路径，如 analysis/result-card-C1.json。"))
    elif _is_placeholder(ref_locator) or not _is_public_relative_locator(ref_locator):
        errors.append(_problem(
            "result_card.locator_unsafe", claim_id, ref_locator,
            "result_card locator 必须是公开交接包内相对路径/锚点，不能是占位符、绝对路径或 .. 越界。",
            evidence_ids=evidence_ids,
            suggestion="改为 result-analysis 输出包内相对 locator。"))
    if not ref_sha:
        errors.append(_problem(
            "result_card.hash_missing", claim_id, ref_locator or loc,
            "result_card 缺 SHA-256，无法证明写作消费的是固定版本的结果卡。",
            evidence_ids=evidence_ids,
            suggestion="对真实 result-card JSON 计算 64 位 SHA-256；未知时先不要写强 claim。"))
    elif _is_placeholder(ref_sha) or not _is_hex64(ref_sha):
        errors.append(_problem(
            "result_card.hash_invalid", claim_id, ref_locator or loc,
            "result_card SHA-256 不是真实 64 位十六进制值。",
            evidence_ids=evidence_ids,
            suggestion="重新对 result-card artifact 计算 SHA-256；不要写 unknown/模板值。"))
    if not decision:
        errors.append(_problem(
            "result_card.decision_missing", claim_id, ref_locator or loc,
            "result_card 缺 decision，无法确认 result-analysis 是否允许进入写作。",
            evidence_ids=evidence_ids,
            suggestion="只接受 upstream decision=CLAIM_READY；REVISION_REQUIRED/UNKNOWN 不得写成 ready claim。"))
    elif decision not in _READY_DECISIONS:
        errors.append(_problem(
            "result_card.not_ready", claim_id, ref_locator or loc,
            f"result_card decision={decision!r}，不是 CLAIM_READY；不得把未完成/需修订结论写进论文。",
            evidence_ids=evidence_ids,
            suggestion="回 result-analysis 修复 result card，或把 claim 改成 gap/limitation/null result。"))
    if not language_strength or _is_placeholder(language_strength):
        errors.append(_problem(
            "result_card.language_strength_missing", claim_id, ref_locator or loc,
            "result_card 缺 language_strength，写作无法继承上游对结论强度的限制。",
            evidence_ids=evidence_ids,
            suggestion="填 result_card.language.strength；若为 INCONCLUSIVE/NO_EFFECT，正文不得写强收益。"))

    guard = ref.get("guardrail_summary") or ref.get("guardrail")
    if not isinstance(guard, dict):
        errors.append(_problem(
            "result_card.guardrail_missing", claim_id, ref_locator or loc,
            "result_card 摘要缺 guardrail_summary；guardrail/counter-metric 的 claim_impact 可能在写作阶段丢失。",
            evidence_ids=evidence_ids,
            suggestion="从 result_card.guardrail_analysis 汇总 required/status/claim_impact/evidence_locator。"))
        return errors, warnings, summary

    required = guard.get("required")
    if not isinstance(required, bool):
        errors.append(_problem(
            "result_card.guardrail_required_invalid", claim_id, ref_locator or loc,
            "guardrail_summary.required 必须是 boolean；不能用空字符串或 prose 模糊带过。",
            evidence_ids=evidence_ids,
            suggestion="按 result_card.guardrail_analysis.required 填 true/false。"))
        guard_status = ""
    elif required is False:
        rationale = str(guard.get("not_applicable_rationale") or guard.get("rationale") or "").strip()
        guard_status = "NOT_APPLICABLE"
        if not rationale or _is_placeholder(rationale):
            errors.append(_problem(
                "result_card.guardrail_na_rationale_missing", claim_id, ref_locator or loc,
                "guardrail_summary.required=false 但缺不适用理由；不能让 guardrail 静默消失。",
                evidence_ids=evidence_ids,
                suggestion="写明为何该 claim 无适用 guardrail/counter-metric，并保留 result-card locator/hash。"))
    else:
        guard_status = str(guard.get("status") or guard.get("aggregate_status") or "").strip().upper()
        if not guard_status:
            guard_status = _guardrail_status_from_checks(guard.get("checks"))
        if guard_status not in _GUARDRAIL_STATUSES:
            errors.append(_problem(
                "result_card.guardrail_status_invalid", claim_id, ref_locator or loc,
                "guardrail_summary.status 必须为 PASS/WARN/FAIL/UNKNOWN（或由 checks 汇总）。",
                evidence_ids=evidence_ids,
                suggestion="从 result_card.guardrail_analysis.checks 汇总最严重状态。"))
        claim_impact = str(guard.get("claim_impact") or "").strip()
        if not claim_impact or _is_placeholder(claim_impact):
            errors.append(_problem(
                "result_card.guardrail_claim_impact_missing", claim_id, ref_locator or loc,
                "guardrail_summary 缺 claim_impact；论文写作无法知道要降 claim、报局限还是回炉。",
                evidence_ids=evidence_ids,
                suggestion="填 result_card.guardrail_analysis.checks[].claim_impact 的合并结论。"))
        if guard_status in _BLOCKING_GUARDRAILS:
            errors.append(_problem(
                "result_card.guardrail_blocks_claim", claim_id, ref_locator or loc,
                f"guardrail status={guard_status}；FAIL/UNKNOWN 不得进入 CLAIM_READY 写作。",
                evidence_ids=evidence_ids,
                suggestion="回 result-analysis/research-plan 处理 guardrail；或把正文改为无结论/局限，不能写强收益。"))
        elif guard_status == "WARN":
            if not _has_limitation(raw):
                errors.append(_problem(
                    "result_card.guardrail_warn_without_limitation", claim_id, ref_locator or loc,
                    "guardrail status=WARN 但 claim 缺 limitations；限制性 ready 被写作阶段吞掉。",
                    evidence_ids=evidence_ids,
                    suggestion="在 claim.limitations 和正文中显式写 guardrail 的 claim_impact，再保留有限措辞。"))
            else:
                warnings.append(_problem(
                    "result_card.guardrail_limited_claim", claim_id, ref_locator or loc,
                    "guardrail status=WARN；claim 只能限制性推进，正文必须显式继承 claim_impact。",
                    evidence_ids=evidence_ids,
                    suggestion="在摘要/结果/结论中保持有限措辞，并在 Discussion/Limitations 呼应该 guardrail。"))
    summary["guardrail"] = {
        "required": required,
        "status": guard_status,
        "claim_impact": str(guard.get("claim_impact") or ""),
    }
    return errors, warnings, summary


def evaluate_bindings(draft: str, evidence: dict | None,
                      claim_map: dict | None,
                      *, as_of: str | dt.date | dt.datetime | None = None) -> dict:
    """Evaluate exact-span claim coverage, bound wording, and provenance.

    ``coverage_errors`` are integrity failures for the stage-8
    ``claim_evidence`` gate. ``overclaims`` and ``traceability_warnings`` are
    writing-stage warnings.
    """
    today = _as_of_date(as_of)
    coverage_errors: list[dict] = []
    result_card_errors: list[dict] = []
    overclaims: list[dict] = []
    traceability_warnings: list[dict] = []
    guardrail_warnings: list[dict] = []
    rows: list[dict] = []

    evidence_claims = (evidence or {}).get("claims") or []
    evidence_index = {
        str(claim.get("claim_id")): claim
        for claim in evidence_claims
        if claim.get("claim_id") not in (None, "")
    }

    if claim_map is None:
        for hit in wording_hits(draft, "none"):
            coverage_errors.append(_problem(
                "claim_binding.map_missing", "", hit.get("loc", "draft"),
                "草稿含强断言，但未提供 light.paper_claims.v1；无法证明该断言绑定了自己的证据。",
                matched=hit.get("matched", ""),
                suggestion="建立 claim/argument plan，逐条填 claim_id、精确 text、locator、"
                           "evidence_claim_ids 与 source_locators。"))
        return {
            "schema": CLAIM_MAP_SCHEMA,
            "binding_mode": "missing",
            "claims": rows,
            "coverage_errors": coverage_errors,
            "result_card_errors": result_card_errors,
            "overclaims": overclaims,
            "traceability_warnings": traceability_warnings,
            "guardrail_warnings": guardrail_warnings,
            "uncovered_strong_assertions": len(coverage_errors),
        }

    if claim_map.get("schema") != CLAIM_MAP_SCHEMA:
        coverage_errors.append(_problem(
            "claim_binding.schema_invalid", "", "claim-map",
            f"claim map schema 应为 {CLAIM_MAP_SCHEMA}，实为 {claim_map.get('schema')!r}。"))
        return {
            "schema": CLAIM_MAP_SCHEMA,
            "binding_mode": "invalid",
            "claims": rows,
            "coverage_errors": coverage_errors,
            "result_card_errors": result_card_errors,
            "overclaims": overclaims,
            "traceability_warnings": traceability_warnings,
            "guardrail_warnings": guardrail_warnings,
            "uncovered_strong_assertions": len(wording_hits(draft, "none")),
        }

    actual_draft_sha = draft_sha256(draft)
    declared_draft_sha = str(claim_map.get("draft_sha256") or "").strip()
    if not declared_draft_sha:
        coverage_errors.append(_problem(
            "claim_binding.draft_hash_missing", "", "claim-map",
            "claim map 缺 draft_sha256；无法证明 claim 绑定对应当前草稿，而不是旧稿。",
            suggestion="对当前 draft 正文按 UTF-8 计算 SHA-256，写入 light.paper_claims.v1 的 draft_sha256。"))
    elif not _is_hex64(declared_draft_sha):
        coverage_errors.append(_problem(
            "claim_binding.draft_hash_invalid", "", "claim-map",
            "draft_sha256 不是 64 位十六进制 SHA-256。",
            suggestion="重新计算当前 draft 的 SHA-256；不要写 UNKNOWN 或占位符。"))
    elif declared_draft_sha.lower() != actual_draft_sha:
        coverage_errors.append(_problem(
            "claim_binding.draft_hash_mismatch", "", "claim-map",
            f"claim map 指向的 draft_sha256={declared_draft_sha[:12]}…，当前草稿为 {actual_draft_sha[:12]}…；"
            "修稿后旧 claim map 已失效。",
            suggestion="重新抽取/复核 claim text、locator、evidence_claim_ids 和 source_locators，再更新 draft_sha256。"))

    provenance_errors, provenance_warnings = _validate_plan_provenance(
        claim_map, as_of=today)
    coverage_errors.extend(provenance_errors)
    traceability_warnings.extend(provenance_warnings)

    declared = claim_map.get("claims")
    if not isinstance(declared, list):
        coverage_errors.append(_problem(
            "claim_binding.claims_invalid", "", "claim-map",
            "claim map 的 claims 必须是数组。"))
        declared = []

    masked = list(draft)
    seen_claim_ids: set[str] = set()

    for number, raw in enumerate(declared, 1):
        if not isinstance(raw, dict):
            coverage_errors.append(_problem(
                "claim_binding.entry_invalid", f"entry-{number}", "claim-map",
                "claim entry 必须是对象。"))
            continue

        claim_id = str(raw.get("claim_id") or "").strip()
        text = str(raw.get("text") or "")
        locator = str(raw.get("locator") or "").strip()
        evidence_ids = raw.get("evidence_claim_ids") or []
        source_locators = raw.get("source_locators") or []

        coverage_errors.extend(_temporal_findings(raw, context=f"claims[{number - 1}]",
                                                  fields=["updated_at"], as_of=today))

        if not isinstance(evidence_ids, list):
            evidence_ids = []
            coverage_errors.append(_problem(
                "claim_binding.evidence_ids_invalid", claim_id or f"entry-{number}",
                locator or "claim-map", "evidence_claim_ids 必须是数组。"))
        evidence_ids = [str(item).strip() for item in evidence_ids if str(item).strip()]

        if not claim_id:
            coverage_errors.append(_problem(
                "claim_binding.claim_id_missing", f"entry-{number}",
                locator or "claim-map", "claim entry 缺 claim_id。"))
        elif claim_id in seen_claim_ids:
            coverage_errors.append(_problem(
                "claim_binding.claim_id_duplicate", claim_id,
                locator or "claim-map", f"claim_id {claim_id!r} 重复，绑定不唯一。"))
        seen_claim_ids.add(claim_id)

        if not text:
            coverage_errors.append(_problem(
                "claim_binding.text_missing", claim_id or f"entry-{number}",
                locator or "claim-map", "claim entry 缺精确 draft text，无法做覆盖核验。"))
            continue

        occurrences = draft.count(text)
        if occurrences != 1:
            coverage_errors.append(_problem(
                "claim_binding.text_not_unique", claim_id or f"entry-{number}",
                locator or "claim-map",
                f"claim text 在草稿中出现 {occurrences} 次；必须恰好出现一次，避免宽泛/陈旧绑定。"))
        else:
            start = draft.index(text)
            for pos in range(start, start + len(text)):
                if masked[pos] != "\n":
                    masked[pos] = " "

        if not locator:
            traceability_warnings.append(_problem(
                "claim_traceability.draft_locator_missing", claim_id,
                "claim-map", "claim 缺草稿 locator；修稿后难以复核落点。"))
        elif _is_placeholder(locator):
            coverage_errors.append(_problem(
                "claim_provenance.claim_locator_placeholder", claim_id,
                "claim-map", "claim locator 仍是占位符，无法定位草稿中的真实断言。",
                suggestion="填 draft.md:L12 或 section/paragraph anchor。"))
        elif not _is_public_relative_locator(locator):
            coverage_errors.append(_problem(
                "claim_provenance.claim_locator_unsafe", claim_id,
                locator, "claim locator 必须是公开交接包内相对 locator，不能是绝对路径或 .. 越界。",
                suggestion="改为 draft.md:L12 或 section/paragraph anchor；私人本机路径留在仓库外。"))
        if not isinstance(source_locators, list):
            coverage_errors.append(_problem(
                "claim_provenance.source_locators_invalid", claim_id,
                locator or "claim-map", "source_locators 必须是数组。"))
            source_locators = []
        else:
            for source_index, source_locator in enumerate(source_locators):
                source_text = str(source_locator or "").strip()
                source_loc = f"{locator or 'claim-map'}.source_locators[{source_index}]"
                if not source_text or _is_placeholder(source_text):
                    coverage_errors.append(_problem(
                        "claim_provenance.source_locator_placeholder", claim_id,
                        source_loc, "source_locator 为空或仍是占位符，不能冒充真实证据来源。",
                        evidence_ids=evidence_ids,
                        suggestion="填 analysis/evidence_strength.json#claim-id 这类真实 locator；未知则先别写强 claim。"))
                elif not _is_public_relative_locator(source_text):
                    coverage_errors.append(_problem(
                        "claim_provenance.source_locator_unsafe", claim_id,
                        source_text,
                        "source_locator 必须是公开交接包内相对路径/锚点，不能是绝对路径或 .. 越界。",
                        evidence_ids=evidence_ids,
                        suggestion="改为包内相对 locator；私人本机路径不得进入公开 claim map。"))
        if evidence_ids and not source_locators:
            traceability_warnings.append(_problem(
                "claim_traceability.source_locator_missing", claim_id,
                locator or "claim-map",
                "claim 已绑定 evidence_claim_ids，但缺 source_locators；"
                "evidence_strength.json 不含完整 run provenance 时将失去真实来源。",
                evidence_ids=evidence_ids))

        unknown_ids = [item for item in evidence_ids if item not in evidence_index]
        if unknown_ids:
            coverage_errors.append(_problem(
                "claim_binding.evidence_id_unknown", claim_id,
                locator or "claim-map",
                "claim 指向 evidence_strength.json 中不存在的 evidence claim_id："
                + ", ".join(unknown_ids),
                evidence_ids=evidence_ids,
                suggestion="回 result-analysis 核对 claim_id，或删除虚假绑定并标 GAP。"))

        rc_errors, rc_warnings, result_card_summary = _validate_result_card_ref(
            raw, claim_id=claim_id, locator=locator, evidence_ids=evidence_ids)
        result_card_errors.extend(rc_errors)
        guardrail_warnings.extend(rc_warnings)

        bound = [evidence_index[item] for item in evidence_ids if item in evidence_index]
        best = _best_grade(bound)
        strong_hits = wording_hits(text, "none")
        if strong_hits and (not evidence_ids or not bound or best == "none"):
            why = ("未绑定 evidence_claim_ids" if not evidence_ids else
                   "绑定 ID 不存在" if not bound else "绑定证据档全部为 none")
            for hit in strong_hits:
                coverage_errors.append(_problem(
                    "claim_evidence.unbacked", claim_id,
                    locator or hit.get("loc", "draft"),
                    f"claim 措辞『{hit.get('matched')}』无自己的证据支撑（{why}）。",
                    matched=hit.get("matched", ""),
                    evidence_ids=evidence_ids,
                    suggestion="回 result-analysis(8→7)补该 claim 的证据；若实验未产出则"
                               "回 experiment-coding(8→6)；或删除/如实弱化断言。"))
        elif best not in (None, "none"):
            for hit in wording_hits(text, best):
                overclaims.append(_problem(
                    "overclaim.wording_exceeds_evidence", claim_id,
                    locator or hit.get("loc", "draft"),
                    f"claim 措辞『{hit.get('matched')}』强于它绑定的证据档『{best}』。",
                    matched=hit.get("matched", ""),
                    evidence_ids=evidence_ids,
                    suggestion=hit.get("suggestion", "降级措辞或补更强证据。")))

        rows.append({
            "claim_id": claim_id,
            "text": text,
            "locator": locator,
            "evidence_claim_ids": evidence_ids,
            "source_locators": source_locators if isinstance(source_locators, list) else [],
            "result_card": result_card_summary,
            "bound_evidence_grade": best,
            "post_hoc": bool(raw.get("post_hoc", False)),
            "status": raw.get("status", ""),
        })

    uncovered = wording_hits("".join(masked), "none")
    for hit in uncovered:
        coverage_errors.append(_problem(
            "claim_binding.unregistered_assertion", "",
            hit.get("loc", "draft"),
            f"草稿强断言『{hit.get('matched')}』未落入任何 claim text；"
            "不能由别的 claim 的最高证据档兜底。",
            matched=hit.get("matched", ""),
            suggestion="把该句作为独立 claim 登记并绑定自己的 evidence_claim_ids，"
                       "或删除/弱化。"))

    return {
        "schema": CLAIM_MAP_SCHEMA,
        "binding_mode": "per-claim",
        "draft_sha256": actual_draft_sha,
        "draft_hash_verified": (
            bool(declared_draft_sha)
            and _is_hex64(declared_draft_sha)
            and declared_draft_sha.lower() == actual_draft_sha
        ),
        "claims": rows,
        "coverage_errors": coverage_errors,
        "result_card_errors": result_card_errors,
        "overclaims": overclaims,
        "traceability_warnings": traceability_warnings,
        "guardrail_warnings": guardrail_warnings,
        "uncovered_strong_assertions": len(uncovered),
    }


def _selftest() -> int:
    evidence = ec.build_evidence_json([
        {"claim_id": "A", "text": "A vs baseline", "q_fdr": 0.001,
         "effect_size": 0.9, "ci95": [0.4, 1.3], "n": 120},
        {"claim_id": "B", "text": "B vs baseline", "q_fdr": 0.3,
         "effect_size": 0.1, "ci95": [-0.2, 0.4], "n": 120},
        {"claim_id": "W", "text": "W vs baseline", "q_fdr": 0.03,
         "effect_size": 0.2, "ci95": [0.05, 0.4], "n": 200},
    ])
    a = "Claim A demonstrates a reliable improvement."
    b = "Claim B significantly outperforms every baseline."
    draft = a + "\n" + b

    def cmap_for(text: str, rows: list[dict]) -> dict:
        return {
            "schema": CLAIM_MAP_SCHEMA,
            "draft_sha256": draft_sha256(text),
            "claims": rows,
        }

    def rc(status: str = "PASS", decision: str = "CLAIM_READY") -> dict:
        return {
            "claim_id": "A",
            "locator": "analysis/result-card-A.json",
            "sha256": "a" * 64,
            "decision": decision,
            "language_strength": "IMPROVES",
            "guardrail_summary": {
                "required": True,
                "status": status,
                "claim_impact": "允许主 claim，但需报告 guardrail 状态与适用范围。",
                "evidence_locator": "analysis/guardrails.json#A",
            },
        }

    base = {
        "schema": CLAIM_MAP_SCHEMA,
        "draft_sha256": draft_sha256(a),
        "claims": [{
            "claim_id": "C-A", "text": a, "locator": "draft.md:L1",
            "claim_type": "RESULT",
            "evidence_claim_ids": ["A"],
            "source_locators": ["analysis/evidence_strength.json#A"],
            "result_card": rc(),
        }],
    }

    mixed = evaluate_bindings(draft, evidence, base)
    assert any(item["code"] == "claim_binding.draft_hash_mismatch"
               for item in mixed["coverage_errors"]), mixed
    assert any(item["code"] == "claim_binding.unregistered_assertion"
               for item in mixed["coverage_errors"]), mixed

    mapped_none = cmap_for(draft, [
        json.loads(json.dumps(base["claims"][0])),
        {
            "claim_id": "C-B", "text": b, "locator": "draft.md:L2",
            "claim_type": "RESULT",
            "evidence_claim_ids": ["B"],
            "source_locators": ["analysis/evidence_strength.json#B"],
            "result_card": rc(),
        },
    ])
    none_result = evaluate_bindings(draft, evidence, mapped_none)
    assert any(item["claim_id"] == "C-B" and item["code"] == "claim_evidence.unbacked"
               for item in none_result["coverage_errors"]), none_result

    weak_text = "Claim W demonstrates a significant improvement."
    weak_map = cmap_for(weak_text, [{
            "claim_id": "C-W", "text": weak_text, "locator": "draft.md:L1",
            "claim_type": "RESULT",
            "evidence_claim_ids": ["W"],
            "source_locators": ["analysis/evidence_strength.json#W"],
            "result_card": rc(),
        }])
    weak_result = evaluate_bindings(weak_text, evidence, weak_map)
    assert not weak_result["coverage_errors"], weak_result
    assert not weak_result["result_card_errors"], weak_result
    assert weak_result["overclaims"], weak_result

    clean = evaluate_bindings(a, evidence, base)
    assert not clean["coverage_errors"] and not clean["result_card_errors"] and not clean["overclaims"], clean

    no_card = json.loads(json.dumps(base))
    del no_card["claims"][0]["result_card"]
    no_card_result = evaluate_bindings(a, evidence, no_card)
    assert any(item["code"] == "result_card.missing"
               for item in no_card_result["result_card_errors"]), no_card_result

    guardrail_fail = json.loads(json.dumps(base))
    guardrail_fail["claims"][0]["result_card"]["guardrail_summary"]["status"] = "FAIL"
    fail_result = evaluate_bindings(a, evidence, guardrail_fail)
    assert any(item["code"] == "result_card.guardrail_blocks_claim"
               for item in fail_result["result_card_errors"]), fail_result

    guardrail_warn = json.loads(json.dumps(base))
    guardrail_warn["claims"][0]["result_card"]["guardrail_summary"]["status"] = "WARN"
    warn_result = evaluate_bindings(a, evidence, guardrail_warn)
    assert any(item["code"] == "result_card.guardrail_warn_without_limitation"
               for item in warn_result["result_card_errors"]), warn_result
    guardrail_warn["claims"][0]["limitations"] = ["Guardrail warn limits the scope."]
    warn_limited = evaluate_bindings(a, evidence, guardrail_warn)
    assert not warn_limited["result_card_errors"], warn_limited
    assert any(item["code"] == "result_card.guardrail_limited_claim"
               for item in warn_limited["guardrail_warnings"]), warn_limited

    missing_provenance = json.loads(json.dumps(base))
    missing_provenance["claims"][0]["source_locators"] = []
    trace = evaluate_bindings(a, evidence, missing_provenance)
    assert any(item["code"] == "claim_traceability.source_locator_missing"
               for item in trace["traceability_warnings"]), trace

    no_map = evaluate_bindings(a, evidence, None)
    assert any(item["code"] == "claim_binding.map_missing"
               for item in no_map["coverage_errors"]), no_map

    stale = json.loads(json.dumps(base))
    stale["draft_sha256"] = "0" * 64
    stale_result = evaluate_bindings(a, evidence, stale)
    assert any(item["code"] == "claim_binding.draft_hash_mismatch"
               for item in stale_result["coverage_errors"]), stale_result

    forged = json.loads(json.dumps(base))
    forged["venue"] = {"checked_at": "2999-01-01", "requirements_source": "{{official URL}}"}
    forged["draft_path"] = r"D:\private\draft.md"
    forged["source_artifacts"] = [{
        "artifact_id": "{{analysis-evidence}}",
        "path": "../private/evidence_strength.json",
        "sha256": "not-a-real-hash",
        "run": "{{run manifest}}",
        "commit": "",
        "owner": "",
        "captured_at": "{{ISO-8601}}",
    }]
    forged["claims"][0]["locator"] = r"C:\private\draft.md:L1"
    forged["claims"][0]["source_locators"] = ["{{analysis_out/evidence_strength.json#A}}"]
    forged["claims"][0]["updated_at"] = "2999-01-02"
    forged_result = evaluate_bindings(a, evidence, forged, as_of="2026-01-02")
    forged_codes = {item["code"] for item in forged_result["coverage_errors"]}
    assert {
        "claim_provenance.date_future",
        "claim_provenance.draft_path_unsafe",
        "claim_provenance.source_path_unsafe",
        "claim_provenance.source_hash_invalid",
        "claim_provenance.date_placeholder",
        "claim_provenance.claim_locator_unsafe",
        "claim_provenance.source_locator_placeholder",
    } <= forged_codes, forged_result
    assert any(
        item["code"] == "claim_provenance.date_future"
        and item["locator"] == "claims[0].updated_at"
        for item in forged_result["coverage_errors"]
    ), forged_result

    print("[selftest] PASS claim_binding: per-claim coverage / result-card guardrail handoff / "
          "unrelated strong evidence cannot shield an unbound claim / stale draft hash critical / "
          "none binding critical / weak overclaim warn / provenance warn / "
          "future-or-forged provenance critical")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit per-claim draft/evidence bindings.")
    parser.add_argument("--draft")
    parser.add_argument("--evidence")
    parser.add_argument("--claim-map")
    parser.add_argument("--as-of", help="ISO 日期；用于复现实验或阻断未来 checked_at/captured_at")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not (args.draft and args.claim_map):
        parser.error("需要 --draft 和 --claim-map（--evidence 可选）")
    draft = pathlib.Path(args.draft).read_text(encoding="utf-8")
    evidence = ec.load(args.evidence) if args.evidence else None
    claim_map = load_claim_map(args.claim_map)
    report = evaluate_bindings(draft, evidence, claim_map, as_of=args.as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if (report["coverage_errors"] or report["result_card_errors"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
