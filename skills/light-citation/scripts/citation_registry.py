#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build ``light.citation_registry.v1`` from author artifacts.

This is the executable resource map for citation. It inventories references
from a paper claim map, manuscript, figure/supplement text and a reference
spec; normalizes identifiers; groups versions without collapsing their
provenance; verifies DOI works; audits claim↔citation review state; and emits a
canonical registry plus BibTeX, CSL JSON, evidence and failure artifacts.

The script never treats metadata lookup as semantic support. A claim edge only
becomes ``SUPPORTS`` after a locator-backed review says so. ``related_only``,
``partial``, ``unsupported`` and unreviewed edges remain visible warnings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import urllib.parse
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import citekey_audit as cka  # noqa: E402
import verify_refs as vr  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.citation_registry.v1"
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:a-z0-9]+")
ARXIV_RE = re.compile(r"(?i)\b(?:arxiv\s*:?\s*)?(\d{4}\.\d{4,5}(?:v\d+)?)\b")
PMID_RE = re.compile(r"(?i)\bPMID\s*:?\s*(\d{6,9})\b")
ISBN_RE = re.compile(r"(?i)\bISBN(?:-1[03])?\s*:?\s*([0-9Xx][0-9Xx\-\s]{8,20})")
URL_RE = re.compile(r"https?://[^\s<>{}\[\]\"']+")
SHA_RE = re.compile(r"sha256:[0-9a-fA-F]{64}")
PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^replace-with|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: str | pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def norm_arxiv(value: str) -> str:
    match = ARXIV_RE.search(value or "")
    return match.group(1).lower() if match else ""


def norm_pmid(value: str) -> str:
    match = re.search(r"\d{6,9}", value or "")
    return match.group(0) if match else ""


def norm_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def norm_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value.rstrip(".,;:)]}"))
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    query = ("?" + parsed.query) if parsed.query else ""
    return f"https://{host}{port}{path}{query}"


def is_sha256(value: Any) -> bool:
    return bool(SHA_RE.fullmatch(str(value or "")))


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "explicit"}


def as_of_date(as_of: str | dt.date | dt.datetime | None = None) -> dt.date:
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


def parse_iso_date(value: str) -> dt.date | None:
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


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value.strip()))


def locator_ok(value: str) -> bool:
    text = str(value or "").strip()
    if not text or is_placeholder(text):
        return False
    if WINDOWS_DRIVE_RE.match(text) or text.startswith(("/", "\\", "~")):
        return False
    path_part = text.replace("\\", "/").split("#", 1)[0]
    return ".." not in path_part.split("/")


def reviewed_at_ok(value: str, *, as_of: dt.date) -> tuple[bool, str | None]:
    text = str(value or "").strip()
    if not text:
        return False, "reviewed_at"
    if is_placeholder(text):
        return False, "reviewed_at_placeholder"
    parsed = parse_iso_date(text)
    if parsed is None:
        return False, "reviewed_at_invalid"
    if parsed > as_of:
        return False, "reviewed_at_future"
    return True, None


def sha256_file(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def extract_identifiers(text: str) -> dict[str, list[str]]:
    dois = sorted({vr.normalize_doi(m.group(0)) for m in DOI_RE.finditer(text or "")})
    arxiv = sorted({norm_arxiv(m.group(0)) for m in ARXIV_RE.finditer(text or "")
                    if norm_arxiv(m.group(0))})
    pmids = sorted({norm_pmid(m.group(0)) for m in PMID_RE.finditer(text or "")})
    isbns = sorted({norm_isbn(m.group(1)) for m in ISBN_RE.finditer(text or "")
                    if 10 <= len(norm_isbn(m.group(1))) <= 13})
    urls = sorted({norm_url(m.group(0)) for m in URL_RE.finditer(text or "")
                   if norm_url(m.group(0))})
    return {"doi": dois, "arxiv": arxiv, "pmid": pmids, "isbn": isbns, "url": urls}


def normalize_bundle(raw: Any) -> dict:
    item = raw if isinstance(raw, dict) else {"raw": str(raw)}
    blob = " ".join(str(item.get(k) or "") for k in (
        "raw", "doi", "DOI", "arxiv", "arxiv_id", "pmid", "isbn", "url"))
    found = extract_identifiers(blob)
    doi = vr.normalize_doi(item.get("doi") or item.get("DOI") or "")
    arxiv = norm_arxiv(item.get("arxiv") or item.get("arxiv_id") or "")
    pmid = norm_pmid(str(item.get("pmid") or ""))
    isbn = norm_isbn(str(item.get("isbn") or ""))
    url = norm_url(str(item.get("url") or ""))
    return {
        "doi": doi or (found["doi"][0] if found["doi"] else ""),
        "arxiv": arxiv or (found["arxiv"][0] if found["arxiv"] else ""),
        "pmid": pmid or (found["pmid"][0] if found["pmid"] else ""),
        "isbn": isbn or (found["isbn"][0] if found["isbn"] else ""),
        "url": url or (found["url"][0] if found["url"] else ""),
        "citekey": str(item.get("citekey") or item.get("key") or "").strip(),
    }


def inventory_row(raw: Any, *, source_kind: str, path: str, locator: str,
                  claim: dict | None = None) -> dict:
    item = raw if isinstance(raw, dict) else {"raw": str(raw)}
    identifiers = normalize_bundle(item)
    claim_text = str((claim or {}).get("text") or "")
    payload = {
        "inventory_id": "",
        "raw": item,
        "identifiers": identifiers,
        "provenance": {
            "source_kind": source_kind,
            "path": path,
            "locator": locator,
            "claim_id": (claim or {}).get("claim_id"),
            "claim_locator": (claim or {}).get("locator"),
            "claim_text": claim_text or None,
            "claim_text_sha256": (
                sha256_text(claim_text) if claim_text and not is_placeholder(claim_text)
                else None
            ),
            "captured_at": now(),
        },
    }
    digest = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    payload["inventory_id"] = f"inv-{digest}"
    return payload


def _scan_text(path: str, source_kind: str) -> list[dict]:
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    rows = []
    for line_no, line in enumerate(text.splitlines(), 1):
        ids = extract_identifiers(line)
        for kind, values in ids.items():
            for value in values:
                rows.append(inventory_row(
                    {kind: value, "raw": line.strip()},
                    source_kind=source_kind, path=str(pathlib.Path(path)),
                    locator=f"L{line_no}"))
    for key in sorted(cka.extract_cited_keys(text)):
        rows.append(inventory_row(
            {"citekey": key, "raw": key}, source_kind=source_kind,
            path=str(pathlib.Path(path)), locator="inline-citation"))
    return rows


def collect_inventory(*, claim_map_path: str | None = None,
                      draft_paths: list[str] | None = None,
                      figure_paths: list[str] | None = None,
                      supplement_paths: list[str] | None = None,
                      refs_spec_path: str | None = None) -> list[dict]:
    rows: list[dict] = []
    if claim_map_path:
        claim_map = load_json(claim_map_path)
        for claim in claim_map.get("claims") or []:
            for index, candidate in enumerate(claim.get("citation_candidates") or [], 1):
                rows.append(inventory_row(
                    candidate, source_kind="paper-claim-map", path=claim_map_path,
                    locator=f"claims[{claim.get('claim_id')}].citation_candidates[{index}]",
                    claim=claim))
    for path in draft_paths or []:
        rows.extend(_scan_text(path, "manuscript"))
    for path in figure_paths or []:
        rows.extend(_scan_text(path, "figure-or-table"))
    for path in supplement_paths or []:
        rows.extend(_scan_text(path, "supplement"))
    if refs_spec_path:
        spec = load_json(refs_spec_path)
        refs = spec.get("references") if isinstance(spec, dict) else spec
        for index, ref in enumerate(refs or [], 1):
            rows.append(inventory_row(
                ref, source_kind="reference-spec", path=refs_spec_path,
                locator=f"references[{index}]"))
    # Preserve every provenance row; only remove byte-identical repeats.
    unique = {}
    for row in rows:
        unique[row["inventory_id"]] = row
    return list(unique.values())


def identity_key(ids: dict) -> str:
    for key in ("doi", "arxiv", "pmid", "isbn", "url", "citekey"):
        if ids.get(key):
            return f"{key}:{ids[key].lower()}"
    return "unidentified:" + hashlib.sha256(
        json.dumps(ids, sort_keys=True).encode()).hexdigest()[:12]


def group_works(inventory: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    alias_to_key: dict[str, str] = {}
    for row in inventory:
        ids = row["identifiers"]
        aliases = [f"{k}:{v.lower()}" for k, v in ids.items() if v]
        key = next((alias_to_key[a] for a in aliases if a in alias_to_key), identity_key(ids))
        work = groups.setdefault(key, {
            "work_id": "", "canonical_identity": key, "identifiers": {
                "doi": [], "arxiv": [], "pmid": [], "isbn": [], "url": []},
            "citekeys": [], "inventory_ids": [], "versions": [],
        })
        for kind in work["identifiers"]:
            value = ids.get(kind)
            if value and value not in work["identifiers"][kind]:
                work["identifiers"][kind].append(value)
                work["versions"].append({"identifier_type": kind, "identifier": value,
                                         "inventory_id": row["inventory_id"]})
                alias_to_key[f"{kind}:{value.lower()}"] = key
        if ids.get("citekey") and ids["citekey"] not in work["citekeys"]:
            work["citekeys"].append(ids["citekey"])
            alias_to_key[f"citekey:{ids['citekey'].lower()}"] = key
        work["inventory_ids"].append(row["inventory_id"])
    for key, work in groups.items():
        work["work_id"] = "work-" + hashlib.sha256(key.encode()).hexdigest()[:12]
    return list(groups.values())


def _claimed_for(work: dict, inventory_by_id: dict[str, dict]) -> dict:
    claimed: dict[str, Any] = {}
    for inv_id in work["inventory_ids"]:
        raw = inventory_by_id[inv_id].get("raw") or {}
        if not isinstance(raw, dict):
            continue
        for key in ("title", "first_author", "authors", "year"):
            if raw.get(key) not in (None, "", []) and key not in claimed:
                claimed[key] = raw[key]
    return claimed


def _attach_verification(works: list[dict], inventory: list[dict], *,
                         online: bool, verification_report: dict | None = None,
                         self_authors: list[str] | None = None) -> None:
    by_doi = {}
    if verification_report:
        for item in verification_report.get("items") or []:
            by_doi[vr.normalize_doi(item.get("doi") or "")] = item
    inv_by_id = {row["inventory_id"]: row for row in inventory}
    for work in works:
        dois = work["identifiers"]["doi"]
        if not dois:
            work.update({
                "status": "UNRESOLVED", "canonical_source": None, "metadata": {},
                "source_evidence": [], "field_conflicts": [],
                "publication_updates": [], "is_chimeric": False,
                "mismatch_fields": [],
            })
            continue
        doi = dois[0]
        if doi in by_doi:
            rec = by_doi[doi]
        elif online:
            rec = vr.verify_one(doi, self_authors or [],
                                claimed=_claimed_for(work, inv_by_id))
        else:
            rec = {
                "status": "UNRESOLVED", "canonical_source": None,
                "metadata": {"identifier": doi}, "source_evidence": [],
                "field_conflicts": [], "publication_updates": [],
                "is_chimeric": False, "mismatch_fields": [],
                "errors": [], "warnings": ["offline registry build; verification not run"],
            }
        for key in ("status", "canonical_source", "metadata", "source_evidence",
                    "field_conflicts", "publication_updates", "is_chimeric",
                    "mismatch_fields", "errors", "warnings", "http"):
            work[key] = rec.get(key, [] if key.endswith("s") else None)


def _claim_edges(works: list[dict], inventory: list[dict],
                 *, as_of: str | dt.date | dt.datetime | None = None) -> list[dict]:
    inv_to_work = {inv: work["work_id"] for work in works for inv in work["inventory_ids"]}
    review_as_of = as_of_date(as_of)
    edges = []
    for row in inventory:
        prov = row["provenance"]
        if not prov.get("claim_id"):
            continue
        raw = row.get("raw") or {}
        raw = raw if isinstance(raw, dict) else {}
        verdict = str(raw.get("support_verdict") or "").strip().lower()
        locator = str(raw.get("source_locator") or raw.get("locator") or "").strip()
        excerpt = str(raw.get("source_excerpt") or "").strip()
        evidence_sha256 = str(
            raw.get("source_evidence_sha256") or raw.get("evidence_sha256") or ""
        ).strip()
        access = str(raw.get("access") or "UNAVAILABLE").strip().upper()
        reviewer = str(raw.get("reviewer") or "").strip()
        reviewed_at = str(raw.get("reviewed_at") or "").strip()
        locator_valid = locator_ok(locator)
        reviewed_time_ok, reviewed_time_missing = reviewed_at_ok(
            reviewed_at, as_of=review_as_of)
        support_scope = str(raw.get("support_scope") or raw.get("scope") or "").strip().upper()
        abstract_claim_explicit = (
            truthy(raw.get("abstract_claim_explicit"))
            or support_scope == "ABSTRACT_EXPLICIT"
        )
        claim_text = str(prov.get("claim_text") or "")
        claim_text_sha256 = (
            sha256_text(claim_text)
            if claim_text.strip() and not is_placeholder(claim_text)
            else ""
        )
        reviewed_claim_sha256 = str(
            raw.get("reviewed_claim_sha256") or raw.get("claim_text_sha256") or ""
        ).strip()
        claim_review_bound = (
            is_sha256(claim_text_sha256)
            and is_sha256(reviewed_claim_sha256)
            and reviewed_claim_sha256 == claim_text_sha256
        )
        requested_status = "REVIEW_REQUIRED"
        if verdict in {"supports", "fully_supported"}:
            requested_status = "SUPPORTS"
        elif verdict in {"partial", "partially_supported"}:
            requested_status = "PARTIAL"
        elif verdict in {"unsupported", "not_supported"}:
            requested_status = "UNSUPPORTED"
        elif verdict in {"related_only", "related"}:
            requested_status = "RELATED_ONLY"

        review_complete = (
            locator_valid
            and is_sha256(evidence_sha256)
            and bool(reviewer)
            and reviewed_time_ok
            and claim_review_bound
            and access not in {"", "METADATA_ONLY", "UNAVAILABLE"}
            and not (
                requested_status == "SUPPORTS"
                and access == "ABSTRACT_ONLY"
                and not abstract_claim_explicit
            )
        )
        if requested_status == "SUPPORTS" and review_complete:
            status = "SUPPORTS"
        elif requested_status in {"PARTIAL", "UNSUPPORTED", "RELATED_ONLY"} and review_complete:
            status = requested_status
        else:
            status = "REVIEW_REQUIRED"
        missing_review_fields = []
        if not locator:
            missing_review_fields.append("source_locator")
        elif not locator_valid:
            missing_review_fields.append("source_locator_valid")
        if not is_sha256(evidence_sha256):
            missing_review_fields.append("source_evidence_sha256")
        if not reviewer:
            missing_review_fields.append("reviewer")
        if reviewed_time_missing:
            missing_review_fields.append(reviewed_time_missing)
        if not claim_text_sha256:
            missing_review_fields.append("claim_text")
        if not is_sha256(reviewed_claim_sha256):
            missing_review_fields.append("reviewed_claim_sha256")
        elif reviewed_claim_sha256 != claim_text_sha256:
            missing_review_fields.append("reviewed_claim_sha256_mismatch")
        if access in {"", "METADATA_ONLY", "UNAVAILABLE"}:
            missing_review_fields.append("fulltext_or_abstract_access")
        if (
            requested_status == "SUPPORTS"
            and access == "ABSTRACT_ONLY"
            and not abstract_claim_explicit
        ):
            missing_review_fields.append("abstract_claim_explicit")
        edges.append({
            "edge_id": f"{prov['claim_id']}->{inv_to_work[row['inventory_id']]}",
            "claim_id": prov["claim_id"],
            "claim_text": prov.get("claim_text"),
            "claim_text_sha256": claim_text_sha256 or None,
            "reviewed_claim_sha256": reviewed_claim_sha256 or None,
            "claim_locator": prov.get("claim_locator"),
            "work_id": inv_to_work[row["inventory_id"]],
            "citekey": row["identifiers"].get("citekey"),
            "status": status,
            "requested_status": requested_status,
            "source_locator": locator or None,
            "source_excerpt": excerpt or None,
            "source_evidence_sha256": evidence_sha256 or None,
            "access": access,
            "reviewer": reviewer or None,
            "reviewed_at": reviewed_at or None,
            "support_scope": support_scope or None,
            "abstract_claim_explicit": abstract_claim_explicit,
            "review_provenance_complete": review_complete,
            "missing_review_fields": missing_review_fields,
            "review_note": raw.get("review_note"),
            "rule": ("semantic support is independent of metadata confirmation; "
                     "SUPPORTS requires a real locator, source evidence hash, reviewer, "
                     "non-future reviewed_at, reviewed_claim_sha256 matching the current "
                     "claim_text_sha256, and non-metadata access; ABSTRACT_ONLY SUPPORTS "
                     "also requires abstract_claim_explicit/support_scope=ABSTRACT_EXPLICIT"),
        })
    return edges


def _safe_word(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    return words[0] if words else "work"


def _citekey(work: dict, used: set[str]) -> str:
    preferred = next(iter(work.get("citekeys") or []), "")
    meta = work.get("metadata") or {}
    authors = meta.get("authors") or []
    family = (authors[0].get("family") if authors else "") or "anon"
    base = re.sub(r"[^a-z0-9]", "", family.lower())
    base += str(meta.get("year") or "nd") + _safe_word(meta.get("title") or "")
    key = preferred or base or work["work_id"]
    suffix, candidate = 0, key
    while candidate in used:
        suffix += 1
        candidate = key + chr(96 + min(suffix, 26))
    used.add(candidate)
    return candidate


def _bibtex(works: list[dict]) -> str:
    used = set()
    entries = []
    for work in works:
        if work.get("status") != "CONFIRMED" or work.get("is_chimeric"):
            continue
        meta = work.get("metadata") or {}
        key = _citekey(work, used)
        work["canonical_citekey"] = key
        author = " and ".join(
            ", ".join(v for v in (a.get("family"), a.get("given")) if v)
            for a in meta.get("authors") or [])
        fields = [
            ("title", meta.get("title")), ("author", author),
            ("year", meta.get("year")), ("journal", meta.get("venue")),
            ("doi", meta.get("identifier")),
            ("url", f"https://doi.org/{meta.get('identifier')}"
             if meta.get("identifier") else None),
        ]
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields
                          if value not in (None, ""))
        entries.append(f"@article{{{key},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def _csl(works: list[dict]) -> list[dict]:
    rows = []
    for work in works:
        if work.get("status") != "CONFIRMED" or work.get("is_chimeric"):
            continue
        meta = work.get("metadata") or {}
        rows.append({
            "id": work.get("canonical_citekey"),
            "type": meta.get("type") or "article-journal",
            "title": meta.get("title"),
            "author": [{"family": a.get("family"), "given": a.get("given")}
                       for a in meta.get("authors") or []],
            "issued": {"date-parts": [[meta.get("year")]]} if meta.get("year") else {},
            "container-title": meta.get("venue"),
            "DOI": meta.get("identifier"),
            "URL": (f"https://doi.org/{meta.get('identifier')}"
                    if meta.get("identifier") else None),
        })
    return rows


def build_registry(*, inventory: list[dict], online: bool = False,
                   verification_report: dict | None = None,
                   self_authors: list[str] | None = None,
                   project: str = "unnamed",
                   as_of: str | dt.date | dt.datetime | None = None) -> dict:
    works = group_works(inventory)
    _attach_verification(works, inventory, online=online,
                         verification_report=verification_report,
                         self_authors=self_authors)
    claim_edges = _claim_edges(works, inventory, as_of=as_of)
    return {
        "schema": SCHEMA,
        "project": project,
        "generated_at": now(),
        "inventory": inventory,
        "works": works,
        "claim_edges": claim_edges,
        "summary": {
            "inventory_count": len(inventory),
            "work_count": len(works),
            "status_counts": {state: sum(w.get("status") == state for w in works)
                              for state in ("CONFIRMED", "CONFIRMED-MISSING",
                                            "UNAVAILABLE", "UNRESOLVED")},
            "chimeric_count": sum(bool(w.get("is_chimeric")) for w in works),
            "claim_edge_counts": {state: sum(e["status"] == state for e in claim_edges)
                                  for state in ("SUPPORTS", "PARTIAL", "UNSUPPORTED",
                                                "RELATED_ONLY", "REVIEW_REQUIRED")},
        },
    }


def write_outputs(registry: dict, out_dir: str | pathlib.Path,
                  draft_paths: list[str] | None = None) -> dict:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bib = _bibtex(registry["works"])
    csl = _csl(registry["works"])
    evidence = [{
        "work_id": work["work_id"], "status": work.get("status"),
        "source_evidence": work.get("source_evidence"),
        "field_conflicts": work.get("field_conflicts"),
        "publication_updates": work.get("publication_updates"),
    } for work in registry["works"]]
    failures = [{
        "work_id": work["work_id"], "status": work.get("status"),
        "identifiers": work["identifiers"], "is_chimeric": work.get("is_chimeric"),
        "mismatch_fields": work.get("mismatch_fields"),
        "errors": work.get("errors"), "warnings": work.get("warnings"),
    } for work in registry["works"]
        if work.get("status") != "CONFIRMED" or work.get("is_chimeric")]
    review = [edge for edge in registry["claim_edges"] if edge["status"] != "SUPPORTS"]

    (out / "references.bib").write_text(bib, encoding="utf-8")
    (out / "references.csl.json").write_text(
        json.dumps(csl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "citation-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "citation-failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "claim-citation-review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit = None
    if draft_paths:
        text = "\n".join(pathlib.Path(path).read_text(
            encoding="utf-8", errors="replace") for path in draft_paths)
        audit = cka.audit(text, bib)
        (out / "citekey-audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry["deliverables"] = {
        "registry": "citation-registry.json", "bibtex": "references.bib",
        "csl": "references.csl.json", "evidence": "citation-evidence.json",
        "failures": "citation-failures.json",
        "claim_review": "claim-citation-review.json",
        "citekey_audit": "citekey-audit.json" if audit is not None else None,
    }
    (out / "citation-registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    deliverable_hashes = {
        role: sha256_file(out / name)
        for role, name in registry["deliverables"].items()
        if name and (out / name).is_file()
    }
    if failures:
        delivery_status = "ERROR"
    elif audit is not None and not audit.get("ok"):
        delivery_status = "ERROR"
    elif review:
        delivery_status = "REVIEW_REQUIRED"
    else:
        delivery_status = "DELIVERED"
    delivery = {
        "schema": "light.citation_delivery.v1",
        "producer": "citation", "stage": 10, "generated_at": now(),
        "status": delivery_status,
        "deliverables": registry["deliverables"],
        "deliverable_hashes": deliverable_hashes,
        "typesetting_contract": {
            "consume": ["references.bib", "citekey-audit.json"],
            "truth_boundary": "typesetting checks citekeys/compilation; citation owns authenticity",
        },
    }
    (out / "delivery.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out_dir": str(out), "citekey_audit": audit, "failures": len(failures),
            "review_required": len(review)}


def _selftest() -> int:
    print("### citation_registry offline selftest")
    old_verify = vr.verify_one

    def fake_verify(doi, self_authors=None, claimed=None):
        return {
            "doi": doi, "status": "CONFIRMED", "canonical_source": "Crossref",
            "metadata": {"title": "A Dataset Paper",
                         "authors": [{"family": "Smith", "given": "Ann"}],
                         "year": 2024, "venue": "Data Journal",
                         "identifier": doi, "type": "article-journal"},
            "source_evidence": [
                {"source": "Crossref", "outcome": "FOUND", "fields": {"title": "A Dataset Paper"}},
                {"source": "PubMed", "outcome": "FOUND", "fields": {"title": "A Dataset Paper"}}],
            "field_conflicts": [], "publication_updates": [], "is_chimeric": False,
            "mismatch_fields": [], "errors": [], "warnings": [], "http": {},
        }

    try:
        vr.verify_one = fake_verify
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            h = "sha256:" + "c" * 64
            claim_text = "The intervention cures disease."
            claim_text_sha = sha256_text(claim_text)
            claim = {
                "schema": "light.paper_claims.v1",
                "claims": [{
                    "claim_id": "C1", "text": claim_text,
                    "locator": "draft.md:L1",
                    "citation_candidates": [{
                        "doi": "https://doi.org/10.1234/ABC",
                        "citekey": "smith2024dataset",
                        "support_verdict": "related_only",
                        "source_locator": "abstract",
                        "source_excerpt": "This paper releases a dataset.",
                        "source_evidence_sha256": h,
                        "reviewed_claim_sha256": claim_text_sha,
                        "access": "ABSTRACT_ONLY",
                        "reviewer": "selftest-reviewer",
                        "reviewed_at": "2026-07-04T00:00:00+00:00"
                    }]
                }]
            }
            refs = [{"doi": "10.1234/abc", "title": "A Dataset Paper",
                     "citekey": "smith2024dataset", "arxiv": "2401.12345"}]
            draft = "The intervention cures disease \\cite{smith2024dataset}.\n"
            (root / "claims.json").write_text(json.dumps(claim), encoding="utf-8")
            (root / "refs.json").write_text(json.dumps(refs), encoding="utf-8")
            (root / "draft.tex").write_text(draft, encoding="utf-8")
            inventory = collect_inventory(
                claim_map_path=str(root / "claims.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            registry = build_registry(inventory=inventory, online=True, project="selftest")
            result = write_outputs(registry, root / "out",
                                   draft_paths=[str(root / "draft.tex")])
            assert registry["summary"]["work_count"] == 1, registry["works"]
            # The refs-spec maps the draft citekey to the DOI; DOI+arXiv remain
            # distinct version identifiers inside one work.
            doi_work = next(w for w in registry["works"] if w["identifiers"]["doi"])
            assert doi_work["identifiers"]["arxiv"] == ["2401.12345"], doi_work
            assert registry["claim_edges"][0]["status"] == "RELATED_ONLY"
            broken_review = json.loads(json.dumps(claim))
            broken_review["claims"][0]["citation_candidates"][0]["support_verdict"] = "supports"
            broken_review["claims"][0]["citation_candidates"][0]["source_evidence_sha256"] = ""
            (root / "claims-broken.json").write_text(json.dumps(broken_review), encoding="utf-8")
            broken_inventory = collect_inventory(
                claim_map_path=str(root / "claims-broken.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            broken_registry = build_registry(inventory=broken_inventory, online=True, project="selftest")
            assert broken_registry["claim_edges"][0]["status"] == "REVIEW_REQUIRED"
            assert "source_evidence_sha256" in broken_registry["claim_edges"][0]["missing_review_fields"]
            abstract_support = json.loads(json.dumps(claim))
            abstract_support["claims"][0]["citation_candidates"][0]["support_verdict"] = "supports"
            abstract_support["claims"][0]["citation_candidates"][0]["access"] = "ABSTRACT_ONLY"
            (root / "claims-abstract.json").write_text(
                json.dumps(abstract_support), encoding="utf-8")
            abstract_inventory = collect_inventory(
                claim_map_path=str(root / "claims-abstract.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            abstract_registry = build_registry(
                inventory=abstract_inventory, online=True, project="selftest")
            assert abstract_registry["claim_edges"][0]["status"] == "REVIEW_REQUIRED"
            assert "abstract_claim_explicit" in abstract_registry[
                "claim_edges"][0]["missing_review_fields"]
            abstract_support["claims"][0]["citation_candidates"][0][
                "support_scope"] = "ABSTRACT_EXPLICIT"
            abstract_support["claims"][0]["citation_candidates"][0][
                "abstract_claim_explicit"] = True
            (root / "claims-abstract-ok.json").write_text(
                json.dumps(abstract_support), encoding="utf-8")
            abstract_ok_inventory = collect_inventory(
                claim_map_path=str(root / "claims-abstract-ok.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            abstract_ok_registry = build_registry(
                inventory=abstract_ok_inventory, online=True, project="selftest",
                as_of="2026-07-05")
            assert abstract_ok_registry["claim_edges"][0]["status"] == "SUPPORTS"
            stale_review = json.loads(json.dumps(abstract_support))
            stale_review["claims"][0]["citation_candidates"][0][
                "reviewed_claim_sha256"] = "sha256:" + "0" * 64
            stale_review["claims"][0]["citation_candidates"][0][
                "support_scope"] = "ABSTRACT_EXPLICIT"
            stale_review["claims"][0]["citation_candidates"][0][
                "abstract_claim_explicit"] = True
            (root / "claims-stale-review.json").write_text(
                json.dumps(stale_review), encoding="utf-8")
            stale_inventory = collect_inventory(
                claim_map_path=str(root / "claims-stale-review.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            stale_registry = build_registry(
                inventory=stale_inventory, online=True, project="selftest",
                as_of="2026-07-05")
            assert stale_registry["claim_edges"][0]["status"] == "REVIEW_REQUIRED"
            assert "reviewed_claim_sha256_mismatch" in stale_registry[
                "claim_edges"][0]["missing_review_fields"]
            future_review = json.loads(json.dumps(claim))
            future_review["claims"][0]["citation_candidates"][0]["support_verdict"] = "supports"
            future_review["claims"][0]["citation_candidates"][0]["support_scope"] = "ABSTRACT_EXPLICIT"
            future_review["claims"][0]["citation_candidates"][0]["abstract_claim_explicit"] = True
            future_review["claims"][0]["citation_candidates"][0][
                "reviewed_at"] = "2999-01-01T00:00:00+00:00"
            (root / "claims-future-review.json").write_text(
                json.dumps(future_review), encoding="utf-8")
            future_inventory = collect_inventory(
                claim_map_path=str(root / "claims-future-review.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            future_registry = build_registry(
                inventory=future_inventory, online=True, project="selftest",
                as_of="2026-07-05")
            assert future_registry["claim_edges"][0]["status"] == "REVIEW_REQUIRED"
            assert "reviewed_at_future" in future_registry[
                "claim_edges"][0]["missing_review_fields"]
            placeholder_locator = json.loads(json.dumps(abstract_support))
            placeholder_locator["claims"][0]["citation_candidates"][0][
                "source_locator"] = "{{PDF p.7}}"
            placeholder_locator["claims"][0]["citation_candidates"][0][
                "support_scope"] = "ABSTRACT_EXPLICIT"
            placeholder_locator["claims"][0]["citation_candidates"][0][
                "abstract_claim_explicit"] = True
            (root / "claims-placeholder-locator.json").write_text(
                json.dumps(placeholder_locator), encoding="utf-8")
            placeholder_inventory = collect_inventory(
                claim_map_path=str(root / "claims-placeholder-locator.json"),
                draft_paths=[str(root / "draft.tex")],
                refs_spec_path=str(root / "refs.json"))
            placeholder_registry = build_registry(
                inventory=placeholder_inventory, online=True, project="selftest",
                as_of="2026-07-05")
            assert placeholder_registry["claim_edges"][0]["status"] == "REVIEW_REQUIRED"
            assert "source_locator_valid" in placeholder_registry[
                "claim_edges"][0]["missing_review_fields"]
            assert result["citekey_audit"]["missing_keys"] == []
            assert (root / "out" / "citation-registry.json").exists()
            assert (root / "out" / "references.bib").exists()
    finally:
        vr.verify_one = old_verify
    print("[selftest] PASS inventory provenance / DOI normalization / version grouping / "
          "claim-edge review / abstract-only support guard / "
          "stale-claim-hash guard / future-reviewed_at+placeholder-locator guard / "
          "registry+BibTeX+CSL+evidence+failure delivery")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build canonical citation registry and delivery")
    parser.add_argument("--claim-map")
    parser.add_argument("--draft", action="append", default=[])
    parser.add_argument("--figure", action="append", default=[])
    parser.add_argument("--supplement", action="append", default=[])
    parser.add_argument("--refs-spec")
    parser.add_argument("--verification-report")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--self-author", action="append", default=[])
    parser.add_argument("--project", default="unnamed")
    parser.add_argument("--out-dir", default="citation-delivery")
    parser.add_argument("--as-of", help="ISO date/datetime for reviewed_at future checks")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not any((args.claim_map, args.draft, args.figure, args.supplement, args.refs_spec)):
        parser.error("provide at least one author artifact")
    inventory = collect_inventory(
        claim_map_path=args.claim_map, draft_paths=args.draft,
        figure_paths=args.figure, supplement_paths=args.supplement,
        refs_spec_path=args.refs_spec)
    verification = load_json(args.verification_report) if args.verification_report else None
    registry = build_registry(
        inventory=inventory, online=args.online,
        verification_report=verification, self_authors=args.self_author,
        project=args.project, as_of=args.as_of)
    result = write_outputs(registry, args.out_dir, draft_paths=args.draft)
    print(json.dumps({
        "schema": registry["schema"], "summary": registry["summary"],
        "delivery": result,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
