#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate an evidence-bound argument spine and reader path before prose polish."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.paper_argument.v1"
CLAIM_STATES = {"SUPPORTED", "PARTIAL", "MISSING", "CONTESTED"}
CLAIM_TYPES = {
    "RESULT", "NULL_RESULT", "MECHANISM", "CAUSAL",
    "SPECULATION", "LIMITATION", "METHOD", "POSITIONING",
}
SECTION_TYPES = {"ABSTRACT", "INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION", "CONCLUSION"}
PARAGRAPH_ROLES = {
    "CONTEXT", "GAP", "METHOD", "RESULT", "INTERPRETATION",
    "LIMITATION", "TAKEAWAY", "TRANSITION",
}
SECTION_ROLE_ALLOWLIST = {
    "ABSTRACT": {"CONTEXT", "GAP", "RESULT", "TAKEAWAY"},
    "INTRODUCTION": {"CONTEXT", "GAP", "TAKEAWAY", "TRANSITION"},
    "METHODS": {"METHOD", "TRANSITION"},
    "RESULTS": {"RESULT", "TRANSITION"},
    "DISCUSSION": {"INTERPRETATION", "LIMITATION", "TAKEAWAY", "TRANSITION"},
    "CONCLUSION": {"TAKEAWAY", "LIMITATION"},
}


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    claims_raw = spec.get("claims")
    sections = spec.get("sections")
    paragraphs = spec.get("paragraphs")
    contributions = spec.get("contributions")
    if not all(isinstance(x, list) for x in (claims_raw, sections, paragraphs, contributions)):
        raise ValueError("claims/sections/paragraphs/contributions 必须是 list")
    issues: list[dict[str, str]] = []

    def add(code: str, loc: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "loc": loc, "severity": severity, "message": message})

    claims: dict[str, dict[str, Any]] = {}
    for row in claims_raw:
        claim_id = str(row.get("claim_id") or "")
        if not claim_id or claim_id in claims:
            raise ValueError("claim_id 缺失或重复")
        if row.get("status") not in CLAIM_STATES:
            raise ValueError(f"{claim_id} status 非法")
        claims[claim_id] = row
        claim_type = row.get("claim_type")
        if claim_type not in CLAIM_TYPES:
            add("CLAIM_TYPE_GAP", f"claim:{claim_id}", "claim 缺合法 claim_type，无法区分 result/null/mechanism/causal/speculation")
        if not row.get("assertion"):
            add("CLAIM_ASSERTION_GAP", f"claim:{claim_id}", "claim 缺 assertion")
        if row.get("status") == "SUPPORTED" and not row.get("evidence_ids"):
            add("SUPPORTED_WITHOUT_EVIDENCE", f"claim:{claim_id}", "SUPPORTED claim 缺 evidence_ids")
        if row.get("status") == "MISSING":
            add("CLAIM_EVIDENCE_MISSING", f"claim:{claim_id}", "argument 中仍有 MISSING claim")
        if row.get("status") in {"PARTIAL", "CONTESTED"}:
            add(
                "CLAIM_NOT_SETTLED", f"claim:{claim_id}",
                f"claim status={row.get('status')}，须显式限制或解决", "unresolved",
            )
        if claim_type == "CAUSAL" and (
            not row.get("identification_strategy") or not row.get("causal_design_locator")
        ):
            add(
                "CAUSAL_CLAIM_DESIGN_GAP", f"claim:{claim_id}",
                "因果 claim 缺 identification_strategy/causal_design_locator；不能把相关或预测结果写成因果",
            )
        if claim_type == "MECHANISM" and not (
            row.get("mechanism_test_ids") or row.get("mechanism_test_locator")
        ):
            add(
                "MECHANISM_TEST_GAP", f"claim:{claim_id}",
                "机制 claim 缺 mechanism_test_ids/mechanism_test_locator；不能把 post-hoc 解释写成已验证机制",
            )
        if claim_type == "NULL_RESULT" and not row.get("precision_or_power_note"):
            add(
                "NULL_RESULT_PRECISION_GAP", f"claim:{claim_id}",
                "null/negative result 缺 precision_or_power_note；须说明 CI/功效/可排除的效应大小，不能只写“没效果”",
            )
        if claim_type == "SPECULATION" and not row.get("speculation_marker"):
            add(
                "SPECULATION_MARKER_GAP", f"claim:{claim_id}",
                "speculation claim 缺 speculation_marker；推测必须显式标注，不能冒充结果",
            )
        if row.get("post_hoc") and not row.get("post_hoc_disclosure"):
            add(
                "POST_HOC_DISCLOSURE_GAP", f"claim:{claim_id}",
                "post-hoc claim 缺 post_hoc_disclosure；结果后形成的解释/切片不得冒充预设贡献",
            )

    central = str(spec.get("central_claim_id") or "")
    if central not in claims:
        add("CENTRAL_CLAIM_MISSING", "argument", "central_claim_id 未登记")
    elif claims[central].get("status") != "SUPPORTED":
        add("CENTRAL_CLAIM_UNSUPPORTED", f"claim:{central}", "中心 claim 未达到 SUPPORTED")
    elif claims[central].get("claim_type") in {"SPECULATION", "LIMITATION"}:
        add(
            "CENTRAL_CLAIM_TYPE_GAP", f"claim:{central}",
            "中心 claim 不能是 SPECULATION/LIMITATION；中心贡献必须是可支撑的结果、方法或定位 claim",
        )
    if not spec.get("central_question") or not spec.get("contribution_boundary"):
        add("ARGUMENT_FRAME_GAP", "argument", "缺 central_question/contribution_boundary")

    contribution_ids: set[str] = set()
    contribution_claims: dict[str, set[str]] = {}
    for row in contributions:
        cid = str(row.get("contribution_id") or "")
        if not cid or cid in contribution_ids:
            raise ValueError("contribution_id 缺失或重复")
        contribution_ids.add(cid)
        linked = {str(x) for x in row.get("claim_ids") or []}
        contribution_claims[cid] = linked
        if not linked or not linked <= set(claims):
            add("CONTRIBUTION_BINDING_GAP", f"contribution:{cid}", "贡献未完整绑定已登记 claim")
        if not row.get("delta_from_prior") or not row.get("boundary"):
            add(
                "CONTRIBUTION_DELTA_GAP", f"contribution:{cid}",
                "贡献缺 delta_from_prior/boundary，易把领域常识包装成创新",
            )

    section_ids: set[str] = set()
    by_type: dict[str, set[str]] = {}
    next_edges: dict[str, str | None] = {}
    for row in sections:
        sid = str(row.get("section_id") or "")
        stype = row.get("type")
        if not sid or sid in section_ids or stype not in SECTION_TYPES:
            raise ValueError("section_id 重复/缺失或 type 非法")
        section_ids.add(sid)
        by_type.setdefault(stype, set()).update(str(x) for x in row.get("contribution_ids") or [])
        next_edges[sid] = row.get("next_section_id")
        if not row.get("reader_question") or not row.get("purpose"):
            add("SECTION_READER_PATH_GAP", f"section:{sid}", "section 缺 reader_question/purpose")
        bad_claims = set(map(str, row.get("claim_ids") or [])) - set(claims)
        if bad_claims:
            add("SECTION_UNKNOWN_CLAIM", f"section:{sid}", f"引用未登记 claim {sorted(bad_claims)}")
    for sid, target in next_edges.items():
        if target is not None and target not in section_ids:
            add("BROKEN_SECTION_EDGE", f"section:{sid}", f"next_section_id={target} 不存在")

    start_section_id = str(spec.get("start_section_id") or "")
    if not start_section_id or start_section_id not in section_ids:
        add("START_SECTION_GAP", "argument", "start_section_id 缺失或未登记")
    if sections and start_section_id in section_ids:
        visited: set[str] = set()
        cursor: str | None = start_section_id
        while cursor and cursor not in visited:
            visited.add(cursor)
            cursor = next_edges.get(cursor)
        if cursor in visited:
            add("SECTION_CYCLE", f"section:{cursor}", "reader path 出现循环")
        missing_sections = section_ids - visited
        if missing_sections:
            add("SECTION_DISCONNECTED", "argument", f"reader path 未覆盖 {sorted(missing_sections)}")

    promised = by_type.get("ABSTRACT", set()) | by_type.get("INTRODUCTION", set())
    closed = by_type.get("RESULTS", set()) & (
        by_type.get("DISCUSSION", set()) | by_type.get("CONCLUSION", set())
    )
    for cid in sorted(promised - closed):
        add(
            "PROMISE_NOT_CLOSED", f"contribution:{cid}",
            "摘要/引言承诺未同时在 Results 与 Discussion/Conclusion 闭合",
        )
    for cid in sorted(closed - promised):
        add(
            "UNANNOUNCED_CONTRIBUTION", f"contribution:{cid}",
            "结果中出现未在摘要/引言建立预期的贡献", "unresolved",
        )
    unknown_contrib = set().union(*by_type.values()) - contribution_ids if by_type else set()
    if unknown_contrib:
        add("SECTION_UNKNOWN_CONTRIBUTION", "argument", f"章节引用未知贡献 {sorted(unknown_contrib)}")

    paragraph_ids: set[str] = set()
    paragraph_next: dict[str, str | None] = {}
    for row in paragraphs:
        pid = str(row.get("paragraph_id") or "")
        if not pid or pid in paragraph_ids:
            raise ValueError("paragraph_id 缺失或重复")
        paragraph_ids.add(pid)
        paragraph_next[pid] = row.get("bridge_to")
        section_id = str(row.get("section_id") or "")
        claim_id = str(row.get("claim_id") or "")
        role = row.get("role")
        if section_id not in section_ids:
            add("PARAGRAPH_SECTION_GAP", f"paragraph:{pid}", "paragraph.section_id 不存在")
            section_type = None
        else:
            section_type = next((str(sec.get("type")) for sec in sections if sec.get("section_id") == section_id), None)
        if role not in PARAGRAPH_ROLES:
            add("PARAGRAPH_ROLE_GAP", f"paragraph:{pid}", "paragraph 缺合法 role（CONTEXT/GAP/METHOD/RESULT/INTERPRETATION/LIMITATION/TAKEAWAY/TRANSITION）")
        elif section_type and role not in SECTION_ROLE_ALLOWLIST.get(section_type, set()):
            add(
                "PARAGRAPH_ROLE_SECTION_MISMATCH", f"paragraph:{pid}",
                f"{section_type} section 中出现 role={role}；先写对章节职责，别用流畅 prose 掩盖结构错位",
            )
        if claim_id not in claims:
            add("PARAGRAPH_CLAIM_GAP", f"paragraph:{pid}", "paragraph 未绑定已登记 claim")
            continue
        claim_type = claims[claim_id].get("claim_type")
        if not row.get("reader_question") or not row.get("conclusion"):
            add("PARAGRAPH_CONTRACT_GAP", f"paragraph:{pid}", "缺 reader_question/conclusion")
        bound = set(map(str, row.get("evidence_ids") or []))
        allowed = set(map(str, claims[claim_id].get("evidence_ids") or []))
        if not bound or not bound <= allowed:
            add(
                "PARAGRAPH_EVIDENCE_MISMATCH", f"paragraph:{pid}",
                "paragraph evidence 缺失或超出 claim 自己的 evidence IDs",
            )
        if claims[claim_id].get("status") in {"PARTIAL", "CONTESTED"} and not row.get("limitation"):
            add("LIMITATION_GAP", f"paragraph:{pid}", "partial/contested claim 段落缺 limitation")
        if section_type == "RESULTS" and role == "INTERPRETATION":
            add(
                "RESULTS_INTERPRETATION_LEAK", f"paragraph:{pid}",
                "Results 段落承担 INTERPRETATION 角色；解释/替代解释/机制推测应移入 Discussion 或显式拆段",
            )
        if section_type == "RESULTS" and claim_type in {"SPECULATION", "LIMITATION"}:
            add(
                "RESULTS_SPECULATION_LEAK", f"paragraph:{pid}",
                f"Results 段落绑定 {claim_type} claim；推测/限制应去 Discussion/Conclusion，不能冒充实证结果",
            )
        if claim_type == "CAUSAL" and not row.get("causal_language_checked"):
            add(
                "CAUSAL_LANGUAGE_CHECK_GAP", f"paragraph:{pid}",
                "段落绑定因果 claim 但未标 causal_language_checked；须确认文本没有把非因果证据写成因果",
            )
        if claim_type == "MECHANISM" and role == "RESULT" and not row.get("mechanism_result_boundary"):
            add(
                "MECHANISM_RESULT_BOUNDARY_GAP", f"paragraph:{pid}",
                "Results 中报告机制相关结果时须写 mechanism_result_boundary，避免把探索解释写成机制结论",
            )
    for pid, target in paragraph_next.items():
        if target is not None and target not in paragraph_ids and target not in section_ids:
            add("BROKEN_PARAGRAPH_BRIDGE", f"paragraph:{pid}", f"bridge_to={target} 不存在")

    figure_map = spec.get("figure_first_map") or []
    mapped_claims = {
        str(row.get("claim_id")) for row in figure_map if isinstance(row, dict) and row.get("claim_id")
    }
    if central and central not in mapped_claims and not spec.get("figure_not_applicable_reason"):
        add(
            "CENTRAL_CLAIM_FIGURE_GAP", f"claim:{central}",
            "中心 claim 未进入 figure_first_map；若无需图应显式写 not_applicable_reason",
            "unresolved",
        )

    paragraphs_by_section: dict[str, list[dict[str, Any]]] = {}
    for row in paragraphs:
        paragraphs_by_section.setdefault(str(row.get("section_id") or ""), []).append(row)
    for section_id, rows in paragraphs_by_section.items():
        for index, row in enumerate(rows[:-1]):
            expected = str(rows[index + 1].get("paragraph_id") or "")
            if row.get("bridge_to") != expected:
                add(
                    "READER_BRIDGE_SKIP", f"paragraph:{row.get('paragraph_id')}",
                    f"同节下一段是 {expected}，bridge_to 未指向它",
                )

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.paper_argument_report.v1", "status": status,
        "issues": issues,
        "honesty": (
            "本门核登记的 argument graph 与 evidence IDs；"
            "不自动证明叙事清晰、创新重要或原始证据真实。"
        ),
    }


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "central_question": "Does the method improve robust prediction?",
        "central_claim_id": "C1",
        "start_section_id": "S0",
        "contribution_boundary": "evaluation is limited to declared datasets",
        "claims": [{
            "claim_id": "C1", "assertion": "method improves robust prediction",
            "claim_type": "RESULT", "status": "SUPPORTED", "evidence_ids": ["E1"],
        }],
        "contributions": [{
            "contribution_id": "K1", "claim_ids": ["C1"],
            "delta_from_prior": "adds uncertainty-aware training",
            "boundary": "no causal mechanism claim",
        }],
        "sections": [
            {"section_id": "S0", "type": "ABSTRACT", "reader_question": "what changed?",
             "purpose": "summary", "claim_ids": ["C1"], "contribution_ids": ["K1"],
             "next_section_id": "S1"},
            {"section_id": "S1", "type": "INTRODUCTION", "reader_question": "why needed?",
             "purpose": "motivate", "claim_ids": ["C1"], "contribution_ids": ["K1"],
             "next_section_id": "S2"},
            {"section_id": "S2", "type": "RESULTS", "reader_question": "what evidence?",
             "purpose": "show result", "claim_ids": ["C1"], "contribution_ids": ["K1"],
             "next_section_id": "S3"},
            {"section_id": "S3", "type": "CONCLUSION", "reader_question": "what follows?",
             "purpose": "close", "claim_ids": ["C1"], "contribution_ids": ["K1"],
             "next_section_id": None},
        ],
        "paragraphs": [{
            "paragraph_id": "P1", "section_id": "S2", "reader_question": "how large?",
            "role": "RESULT", "claim_id": "C1", "evidence_ids": ["E1"], "conclusion": "supports C1",
            "limitation": "declared datasets only", "bridge_to": "S3",
        }],
        "figure_first_map": [{"figure_id": "F1", "claim_id": "C1"}],
    }


def _selftest() -> int:
    assert evaluate(_base())["status"] == "PASS"
    missing = json.loads(json.dumps(_base()))
    missing["claims"][0]["evidence_ids"] = []
    assert evaluate(missing)["status"] == "FAIL"
    unclosed = json.loads(json.dumps(_base()))
    unclosed["sections"][2]["contribution_ids"] = []
    assert "PROMISE_NOT_CLOSED" in {x["code"] for x in evaluate(unclosed)["issues"]}
    mismatch = json.loads(json.dumps(_base()))
    mismatch["paragraphs"][0]["evidence_ids"] = ["E-other"]
    assert "PARAGRAPH_EVIDENCE_MISMATCH" in {x["code"] for x in evaluate(mismatch)["issues"]}
    cycle = json.loads(json.dumps(_base()))
    cycle["sections"][-1]["next_section_id"] = "S1"
    assert "SECTION_CYCLE" in {x["code"] for x in evaluate(cycle)["issues"]}
    no_start = json.loads(json.dumps(_base()))
    no_start.pop("start_section_id")
    assert "START_SECTION_GAP" in {x["code"] for x in evaluate(no_start)["issues"]}
    missing_claim = json.loads(json.dumps(_base()))
    missing_claim["claims"].append({
        "claim_id": "C2", "assertion": "unsupported extra", "claim_type": "RESULT", "status": "MISSING",
        "evidence_ids": [],
    })
    assert "CLAIM_EVIDENCE_MISSING" in {x["code"] for x in evaluate(missing_claim)["issues"]}
    causal = json.loads(json.dumps(_base()))
    causal["claims"][0]["claim_type"] = "CAUSAL"
    causal["paragraphs"][0]["causal_language_checked"] = False
    causal_issues = {x["code"] for x in evaluate(causal)["issues"]}
    assert "CAUSAL_CLAIM_DESIGN_GAP" in causal_issues
    assert "CAUSAL_LANGUAGE_CHECK_GAP" in causal_issues
    role_leak = json.loads(json.dumps(_base()))
    role_leak["paragraphs"][0]["role"] = "INTERPRETATION"
    role_issues = {x["code"] for x in evaluate(role_leak)["issues"]}
    assert "PARAGRAPH_ROLE_SECTION_MISMATCH" in role_issues
    assert "RESULTS_INTERPRETATION_LEAK" in role_issues
    null_result = json.loads(json.dumps(_base()))
    null_result["claims"][0]["claim_type"] = "NULL_RESULT"
    assert "NULL_RESULT_PRECISION_GAP" in {x["code"] for x in evaluate(null_result)["issues"]}
    print("argument_contract selftest PASS: central/evidence/contribution closure/reader path/paragraph")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("需要 --input 或 --selftest")
    report = evaluate(json.loads(pathlib.Path(args.input).read_text(encoding="utf-8-sig")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
