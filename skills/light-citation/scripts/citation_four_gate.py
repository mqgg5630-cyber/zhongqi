#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce existence → identity → publication status → claim-support ordering."""
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

SCHEMA_ID = "light.citation_four_gate.v1"
EXISTENCE = {"VERIFIED", "CONFIRMED_MISSING", "UNKNOWN", "UNAVAILABLE"}
IDENTITY = {"MATCH", "CONFLICT", "UNKNOWN"}
PUB_STATUS = {"ACTIVE", "CORRECTED", "RETRACTED", "EXPRESSION_OF_CONCERN", "UNKNOWN"}
SUPPORT = {"DIRECT", "PARTIAL", "BACKGROUND", "CONTRADICTORY", "UNRESOLVED"}
ACCESS = {"FULLTEXT", "ABSTRACT_ONLY", "METADATA_ONLY", "UNAVAILABLE"}
PURPOSES = {"DIRECT_SUPPORT", "BACKGROUND", "HISTORICAL_RECORD"}
RETRACTION_TYPES = {"retraction", "withdrawal", "partial_retraction", "removal"}
CORRECTION_TYPES = {"correction", "corrigendum", "erratum", "clarification", "addendum"}
CONCERN_TYPES = {"expression_of_concern"}
PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^replace-with|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)


def _hash(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _as_of_date(as_of: str | dt.date | dt.datetime | None = None) -> dt.date:
    if as_of is None:
        return dt.datetime.now(dt.timezone.utc).date()
    if isinstance(as_of, dt.datetime):
        return as_of.date()
    if isinstance(as_of, dt.date):
        return as_of
    text = str(as_of).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return dt.date.fromisoformat(text)


def _parse_iso_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
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


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value.strip()))


def _evidence_ok(row: dict[str, Any], *, as_of: dt.date) -> bool:
    retrieved = str(row.get("retrieved_at") or "").strip()
    parsed = _parse_iso_date(retrieved)
    return (
        bool(row.get("source"))
        and not _is_placeholder(row.get("source"))
        and bool(row.get("locator"))
        and not _is_placeholder(row.get("locator"))
        and bool(row.get("retrieved_at"))
        and not _is_placeholder(retrieved)
        and parsed is not None
        and parsed <= as_of
        and _hash(row.get("raw_sha256"))
    )


def _source_evidence(work: dict[str, Any], preferred: str | None = None) -> dict[str, Any]:
    rows = [
        row for row in work.get("source_evidence") or []
        if isinstance(row, dict) and row.get("outcome") == "FOUND"
    ]
    if preferred:
        for row in rows:
            if str(row.get("source") or "").casefold() == preferred.casefold():
                return row
    if rows:
        return rows[0]
    all_rows = [row for row in work.get("source_evidence") or [] if isinstance(row, dict)]
    return all_rows[0] if all_rows else {}


def _gate_evidence(
    work: dict[str, Any],
    *,
    state: str,
    preferred: str | None = None,
) -> dict[str, Any]:
    source = _source_evidence(work, preferred)
    retrieved_at = source.get("retrieved_at") or work.get("generated_at")
    raw_hash = source.get("normalized_payload_sha256") or source.get("raw_sha256")
    return {
        "state": state,
        "source": source.get("source") or work.get("canonical_source") or "citation-registry",
        "locator": source.get("endpoint") or source.get("locator") or f"works.{work.get('work_id')}",
        "retrieved_at": retrieved_at,
        "raw_sha256": raw_hash,
    }


def _publication_state(work: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    updates = [
        item for item in work.get("publication_updates") or []
        if isinstance(item, dict)
    ]
    normalized = [str(item.get("type") or "").lower().replace("-", "_") for item in updates]
    if any(kind in RETRACTION_TYPES for kind in normalized):
        state = "RETRACTED"
    elif any(kind in CONCERN_TYPES for kind in normalized):
        state = "EXPRESSION_OF_CONCERN"
    elif any(kind in CORRECTION_TYPES for kind in normalized):
        state = "CORRECTED"
    elif work.get("status") == "CONFIRMED":
        state = "ACTIVE"
    else:
        state = "UNKNOWN"
    source_id = (
        ((work.get("metadata") or {}).get("identifier"))
        or next(iter((work.get("identifiers") or {}).get("doi") or []), "")
        or work.get("work_id")
    )
    relations = []
    for item in updates:
        relation = str(item.get("relation") or "")
        notice = str(item.get("notice_doi") or "")
        if relation and notice:
            relations.append({
                "relation": relation,
                "source_work_id": source_id,
                "target_work_id": notice,
            })
        elif state in {"RETRACTED", "CORRECTED", "EXPRESSION_OF_CONCERN"}:
            relations.append({
                "relation": relation or "unknown",
                "source_work_id": source_id,
                "target_work_id": notice or "UNKNOWN_NOTICE",
            })
    return state, relations


def _support_relation(edge: dict[str, Any]) -> str:
    status = str(edge.get("status") or "REVIEW_REQUIRED").upper()
    return {
        "SUPPORTS": "DIRECT",
        "PARTIAL": "PARTIAL",
        "RELATED_ONLY": "BACKGROUND",
        "UNSUPPORTED": "CONTRADICTORY",
    }.get(status, "UNRESOLVED")


def _support_access(edge: dict[str, Any]) -> str:
    access = str(edge.get("access") or "UNAVAILABLE").upper()
    return access if access in ACCESS else "UNAVAILABLE"


def registry_to_spec(registry: dict[str, Any]) -> dict[str, Any]:
    """Convert light.citation_registry.v1 into a four-gate input spec.

    The registry is the stage-10 SSOT. This adapter prevents the four-gate check
    from drifting into hand-written templates by deriving existence, identity,
    publication status, and claim-support records from the same canonical state
    that emits BibTeX/CSL/delivery artifacts.
    """
    if registry.get("schema") != "light.citation_registry.v1":
        raise ValueError("registry schema 必须为 light.citation_registry.v1")
    works = {work.get("work_id"): work for work in registry.get("works") or []}
    records: list[dict[str, Any]] = []
    for edge in registry.get("claim_edges") or []:
        if not isinstance(edge, dict):
            continue
        work = works.get(edge.get("work_id"))
        if not work:
            continue
        status = str(work.get("status") or "UNRESOLVED").upper()
        existence_state = {
            "CONFIRMED": "VERIFIED",
            "CONFIRMED-MISSING": "CONFIRMED_MISSING",
            "UNAVAILABLE": "UNAVAILABLE",
        }.get(status, "UNKNOWN")
        identity_state = (
            "CONFLICT" if work.get("is_chimeric")
            else "MATCH" if existence_state == "VERIFIED"
            else "UNKNOWN"
        )
        publication_state, relations = _publication_state(work)
        purpose = str(edge.get("claim_purpose") or "DIRECT_SUPPORT").upper()
        if purpose not in PURPOSES:
            purpose = "DIRECT_SUPPORT"
        record = {
            "record_id": f"{edge.get('edge_id') or edge.get('claim_id') or 'claim'}->{work.get('work_id')}",
            "claim_purpose": purpose,
            "existence": _gate_evidence(work, state=existence_state),
            "identity": _gate_evidence(work, state=identity_state),
            "publication_status": {
                **_gate_evidence(work, state=publication_state, preferred="Crossref"),
                "relations": relations,
            },
            "claim_support": {
                "relation": _support_relation(edge),
                "access": _support_access(edge),
                "claim_id": edge.get("claim_id"),
                "locator": edge.get("source_locator"),
                "evidence_sha256": edge.get("source_evidence_sha256"),
                "claim_text_sha256": edge.get("claim_text_sha256"),
                "reviewed_claim_sha256": edge.get("reviewed_claim_sha256"),
                "scope": edge.get("support_scope"),
            },
        }
        if publication_state in {"CORRECTED", "EXPRESSION_OF_CONCERN"}:
            record["affected_scope_reviewed"] = bool(edge.get("affected_scope_reviewed"))
            if edge.get("affected_scope_evidence_sha256"):
                record["affected_scope_evidence_sha256"] = edge.get(
                    "affected_scope_evidence_sha256")
        records.append(record)
    return {"schema": SCHEMA_ID, "records": records}


def evaluate(spec: dict[str, Any], *, as_of: str | dt.date | dt.datetime | None = None) -> dict[str, Any]:
    if spec.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    records = spec.get("records")
    if not isinstance(records, list):
        raise ValueError("records 必须是 list")
    issues: list[dict[str, str]] = []
    decisions: list[dict[str, Any]] = []
    today = _as_of_date(as_of)

    def add(code: str, rid: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "record_id": rid, "severity": severity, "message": message})

    seen: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("record 必须是 object")
        rid = str(row.get("record_id") or "")
        if not rid or rid in seen:
            raise ValueError("record_id 缺失或重复")
        seen.add(rid)
        existence = row.get("existence") or {}
        identity = row.get("identity") or {}
        publication = row.get("publication_status") or {}
        support = row.get("claim_support") or {}
        if existence.get("state") not in EXISTENCE:
            raise ValueError(f"{rid} existence.state 非法")
        if identity.get("state") not in IDENTITY:
            raise ValueError(f"{rid} identity.state 非法")
        if publication.get("state") not in PUB_STATUS:
            raise ValueError(f"{rid} publication_status.state 非法")
        if support.get("relation") not in SUPPORT or support.get("access") not in ACCESS:
            raise ValueError(f"{rid} claim_support relation/access 非法")
        purpose = row.get("claim_purpose")
        if purpose not in PURPOSES:
            raise ValueError(f"{rid} claim_purpose 非法")

        gates: list[dict[str, str]] = []
        existence_ok = existence.get("state") == "VERIFIED" and _evidence_ok(
            existence, as_of=today)
        if existence.get("state") == "CONFIRMED_MISSING":
            add("WORK_CONFIRMED_MISSING", rid, "权威检索确认查无，不能继续身份/支持关")
        elif existence.get("state") in {"UNKNOWN", "UNAVAILABLE"}:
            add("EXISTENCE_UNRESOLVED", rid, f"existence={existence.get('state')}", "unresolved")
        elif not _evidence_ok(existence, as_of=today):
            add("EXISTENCE_PROVENANCE_GAP", rid, "VERIFIED existence 缺真实 source/locator/date/raw hash，或 retrieved_at 来自未来")
        gates.append({"gate": "existence", "status": "PASS" if existence_ok else "BLOCKED"})

        identity_ok = existence_ok and identity.get("state") == "MATCH" and _evidence_ok(
            identity, as_of=today)
        if existence_ok and identity.get("state") == "CONFLICT":
            add("IDENTITY_CONFLICT", rid, "标题/作者/年份/标识符存在冲突，不得静默拼成一条")
        elif existence_ok and identity.get("state") == "UNKNOWN":
            add("IDENTITY_UNRESOLVED", rid, "身份尚未确认", "unresolved")
        elif existence_ok and identity.get("state") == "MATCH" and not _evidence_ok(
            identity, as_of=today):
            add("IDENTITY_PROVENANCE_GAP", rid, "MATCH 缺真实字段来源/locator/date/raw hash，或 retrieved_at 来自未来")
        gates.append({"gate": "identity", "status": "PASS" if identity_ok else "BLOCKED"})

        publication_ok = (
            identity_ok
            and publication.get("state") != "UNKNOWN"
            and _evidence_ok(publication, as_of=today)
        )
        if identity_ok and publication.get("state") == "UNKNOWN":
            add("PUBLICATION_STATUS_UNRESOLVED", rid, "出版更新状态 UNKNOWN", "unresolved")
        elif identity_ok and not _evidence_ok(publication, as_of=today):
            add("PUBLICATION_STATUS_PROVENANCE_GAP", rid, "出版状态缺真实有向关系来源/locator/date/raw hash，或 retrieved_at 来自未来")
        relations = publication.get("relations") or []
        if publication.get("state") in {
            "CORRECTED", "RETRACTED", "EXPRESSION_OF_CONCERN",
        } and not relations:
            add(
                "UPDATE_RELATION_MISSING", rid,
                f"{publication.get('state')} 缺 source_work→target_work 有向关系",
            )
            publication_ok = False
        for relation in relations:
            if not isinstance(relation, dict) or not all(
                relation.get(x) for x in ("relation", "source_work_id", "target_work_id")
            ):
                add("UPDATE_RELATION_GAP", rid, "更新关系缺 relation/source_work_id/target_work_id")
        gates.append({"gate": "publication_status", "status": "PASS" if publication_ok else "BLOCKED"})

        support_ok = (
            publication_ok
            and support.get("relation") != "UNRESOLVED"
            and bool(support.get("claim_id"))
            and bool(support.get("locator"))
            and _hash(support.get("evidence_sha256"))
            and _hash(support.get("claim_text_sha256"))
            and _hash(support.get("reviewed_claim_sha256"))
            and support.get("claim_text_sha256") == support.get("reviewed_claim_sha256")
        )
        if publication_ok and support.get("access") == "METADATA_ONLY":
            add("METADATA_CANNOT_SUPPORT_CLAIM", rid, "元数据不能证明 claim-support")
            support_ok = False
        if (
            publication_ok
            and support.get("access") == "ABSTRACT_ONLY"
            and support.get("relation") == "DIRECT"
            and support.get("scope") != "ABSTRACT_EXPLICIT"
        ):
            add(
                "ABSTRACT_ONLY_DIRECT_LIMIT",
                rid,
                "仅摘要可读时不得把超出摘要明确内容的关系写成全文 direct support",
                "unresolved",
            )
            support_ok = False
        if publication_ok and support.get("relation") == "UNRESOLVED":
            add("CLAIM_SUPPORT_UNRESOLVED", rid, "claim-support 尚未定位", "unresolved")
        if publication_ok and support.get("relation") != "UNRESOLVED" and not (
            support.get("claim_id") and support.get("locator") and _hash(support.get("evidence_sha256"))
        ):
            add("CLAIM_SUPPORT_PROVENANCE_GAP", rid, "支持关系缺 claim/locator/evidence hash")
            support_ok = False
        if publication_ok and support.get("relation") != "UNRESOLVED":
            claim_text_sha256 = support.get("claim_text_sha256")
            reviewed_claim_sha256 = support.get("reviewed_claim_sha256")
            if not (_hash(claim_text_sha256) and _hash(reviewed_claim_sha256)):
                add(
                    "CLAIM_SUPPORT_CLAIM_HASH_GAP",
                    rid,
                    "claim-support 审查缺当前 claim_text_sha256 或 reviewed_claim_sha256",
                )
                support_ok = False
            elif claim_text_sha256 != reviewed_claim_sha256:
                add(
                    "CLAIM_SUPPORT_STALE_CLAIM_REVIEW",
                    rid,
                    "reviewed_claim_sha256 与当前 claim_text_sha256 不一致，引用支持审查可能来自旧 claim",
                )
                support_ok = False
        gates.append({"gate": "claim_support", "status": "PASS" if support_ok else "BLOCKED"})

        allowed = support_ok
        pub_state = publication.get("state")
        relation = support.get("relation")
        if purpose == "DIRECT_SUPPORT" and relation not in {"DIRECT", "PARTIAL"}:
            add("PURPOSE_SUPPORT_MISMATCH", rid, f"{relation} 不可承担 DIRECT_SUPPORT")
            allowed = False
        if purpose == "BACKGROUND" and relation not in {"DIRECT", "PARTIAL", "BACKGROUND"}:
            add("PURPOSE_SUPPORT_MISMATCH", rid, f"{relation} 不可承担 BACKGROUND")
            allowed = False
        if pub_state == "RETRACTED" and purpose != "HISTORICAL_RECORD":
            add("RETRACTED_DEPENDENCY", rid, "已撤稿工作不能继续承担当前科学结论")
            allowed = False
        if pub_state in {"CORRECTED", "EXPRESSION_OF_CONCERN"} and not row.get("affected_scope_reviewed"):
            add(
                "UPDATE_SCOPE_UNREVIEWED", rid,
                f"{pub_state} 尚未核对受影响范围与当前 claim 的依赖",
                "unresolved",
            )
            allowed = False
        elif (
            pub_state in {"CORRECTED", "EXPRESSION_OF_CONCERN"}
            and not _hash(row.get("affected_scope_evidence_sha256"))
        ):
            add(
                "UPDATE_SCOPE_PROVENANCE_GAP", rid,
                "affected_scope_reviewed=true 但缺审查证据 SHA-256",
            )
            allowed = False
        decisions.append({
            "record_id": rid, "gates": gates, "allowed_for_declared_purpose": allowed,
        })

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    if any(not row["allowed_for_declared_purpose"] for row in decisions) and status == "PASS":
        status = "UNRESOLVED"
    return {
        "schema": "light.citation_four_gate_report.v1", "status": status,
        "decisions": decisions, "issues": issues,
        "honesty": (
            "四关只核登记证据与用途；元数据命中不证明语义支持，"
            "出版状态信号不等于科研不端裁定。"
        ),
    }


def _base() -> dict[str, Any]:
    h = "sha256:" + "d" * 64
    claim_h = "sha256:" + "c" * 64
    ev = {
        "source": "authoritative source", "locator": "record:1",
        "retrieved_at": "2026-07-04", "raw_sha256": h,
    }
    return {
        "schema": SCHEMA_ID,
        "records": [{
            "record_id": "R1", "claim_purpose": "DIRECT_SUPPORT",
            "existence": {"state": "VERIFIED", **ev},
            "identity": {"state": "MATCH", **ev},
            "publication_status": {"state": "ACTIVE", "relations": [], **ev},
            "claim_support": {
                "relation": "DIRECT", "access": "FULLTEXT", "claim_id": "C1",
                "locator": "p.3", "evidence_sha256": h,
                "claim_text_sha256": claim_h,
                "reviewed_claim_sha256": claim_h,
            },
        }],
    }


def _selftest() -> int:
    assert evaluate(_base(), as_of="2026-07-05")["status"] == "PASS"
    unavailable = json.loads(json.dumps(_base()))
    unavailable["records"][0]["existence"]["state"] = "UNAVAILABLE"
    assert evaluate(unavailable, as_of="2026-07-05")["status"] == "UNRESOLVED"
    conflict = json.loads(json.dumps(_base()))
    conflict["records"][0]["identity"]["state"] = "CONFLICT"
    assert evaluate(conflict, as_of="2026-07-05")["status"] == "FAIL"
    abstract = json.loads(json.dumps(_base()))
    abstract["records"][0]["claim_support"]["access"] = "ABSTRACT_ONLY"
    assert evaluate(abstract, as_of="2026-07-05")["status"] == "UNRESOLVED"
    retracted = json.loads(json.dumps(_base()))
    retracted["records"][0]["publication_status"]["state"] = "RETRACTED"
    retracted["records"][0]["publication_status"]["relations"] = [{
        "relation": "updated-by",
        "source_work_id": "original",
        "target_work_id": "retraction-notice",
    }]
    assert evaluate(retracted, as_of="2026-07-05")["status"] == "FAIL"
    historical = json.loads(json.dumps(retracted))
    historical["records"][0]["claim_purpose"] = "HISTORICAL_RECORD"
    assert evaluate(historical, as_of="2026-07-05")[
        "decisions"][0]["allowed_for_declared_purpose"]
    no_direction = json.loads(json.dumps(retracted))
    no_direction["records"][0]["publication_status"]["relations"] = []
    assert "UPDATE_RELATION_MISSING" in {
        x["code"] for x in evaluate(no_direction, as_of="2026-07-05")["issues"]
    }
    corrected = json.loads(json.dumps(_base()))
    corrected["records"][0]["publication_status"]["state"] = "CORRECTED"
    corrected["records"][0]["publication_status"]["relations"] = [{
        "relation": "updated-by", "source_work_id": "original",
        "target_work_id": "correction",
    }]
    corrected["records"][0]["affected_scope_reviewed"] = True
    assert "UPDATE_SCOPE_PROVENANCE_GAP" in {
        x["code"] for x in evaluate(corrected, as_of="2026-07-05")["issues"]
    }
    future = json.loads(json.dumps(_base()))
    future["records"][0]["existence"]["retrieved_at"] = "2999-01-01"
    assert "EXISTENCE_PROVENANCE_GAP" in {
        x["code"] for x in evaluate(future, as_of="2026-07-05")["issues"]
    }
    placeholder = json.loads(json.dumps(_base()))
    placeholder["records"][0]["identity"]["locator"] = "{{source locator}}"
    assert "IDENTITY_PROVENANCE_GAP" in {
        x["code"] for x in evaluate(placeholder, as_of="2026-07-05")["issues"]
    }
    stale_claim_review = json.loads(json.dumps(_base()))
    stale_claim_review["records"][0]["claim_support"][
        "reviewed_claim_sha256"] = "sha256:" + "0" * 64
    assert "CLAIM_SUPPORT_STALE_CLAIM_REVIEW" in {
        x["code"] for x in evaluate(stale_claim_review, as_of="2026-07-05")["issues"]
    }
    source_hash = "sha256:" + "e" * 64
    support_hash = "sha256:" + "f" * 64
    claim_hash = "sha256:" + "c" * 64
    registry = {
        "schema": "light.citation_registry.v1",
        "works": [{
            "work_id": "work-1",
            "status": "CONFIRMED",
            "canonical_source": "Crossref",
            "metadata": {"identifier": "10.1/example"},
            "source_evidence": [{
                "source": "Crossref",
                "endpoint": "https://api.crossref.org/works/10.1/example",
                "outcome": "FOUND",
                "retrieved_at": "2026-07-04T00:00:00+00:00",
                "normalized_payload_sha256": source_hash,
            }],
            "publication_updates": [{
                "type": "retraction",
                "notice_doi": "10.1/notice",
                "relation": "updated-by",
            }],
            "is_chimeric": False,
        }],
        "claim_edges": [{
            "edge_id": "C1->work-1",
            "claim_id": "C1",
            "work_id": "work-1",
            "status": "SUPPORTS",
            "access": "FULLTEXT",
            "source_locator": "paper.pdf:3",
            "source_evidence_sha256": support_hash,
            "claim_text_sha256": claim_hash,
            "reviewed_claim_sha256": claim_hash,
        }],
    }
    generated = registry_to_spec(registry)
    assert generated["schema"] == SCHEMA_ID and len(generated["records"]) == 1
    generated_report = evaluate(generated, as_of="2026-07-05")
    rules = {x["code"] for x in generated_report["issues"]}
    assert "RETRACTED_DEPENDENCY" in rules, generated_report
    assert generated["records"][0]["publication_status"]["relations"][0] == {
        "relation": "updated-by",
        "source_work_id": "10.1/example",
        "target_work_id": "10.1/notice",
    }
    registry["works"][0]["publication_updates"] = []
    registry["claim_edges"][0]["support_scope"] = "ABSTRACT_EXPLICIT"
    registry["claim_edges"][0]["access"] = "ABSTRACT_ONLY"
    ok_generated = registry_to_spec(registry)
    assert evaluate(ok_generated, as_of="2026-07-05")["status"] == "PASS"
    print("citation_four_gate selftest PASS: unavailable/identity/direction/access/"
          "retraction/purpose/future-date/placeholder/stale-claim-hash/registry-adapter")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--registry", help="derive four-gate records from light.citation_registry.v1")
    parser.add_argument("--as-of", help="ISO date/datetime for future retrieved_at checks")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if bool(args.input) == bool(args.registry):
        parser.error("需要且只能提供 --input 或 --registry（二选一），或 --selftest")
    payload = json.loads(pathlib.Path(args.input or args.registry).read_text(
        encoding="utf-8-sig"))
    spec = registry_to_spec(payload) if args.registry else payload
    report = evaluate(spec, as_of=args.as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
