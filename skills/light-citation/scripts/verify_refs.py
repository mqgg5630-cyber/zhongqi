#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify scholarly references with source-level evidence and honest states.

Core states:
  CONFIRMED          registration metadata plus an independent field source
  CONFIRMED-MISSING  DOI RA says non-existent and Crossref + DataCite return 404
  UNAVAILABLE        authoritative endpoints failed/rate-limited; never "missing"
  UNRESOLVED         registered/partly found, but two-source confirmation is incomplete

The canonical fields come from the DOI registration agency (Crossref or
DataCite). Fuzzy matching never overwrites the user's citation. Every source
value, HTTP outcome, endpoint and retrieval time remains in ``source_evidence``.
Crossref publication updates are read in the direction that applies to the
queried work: an original work has ``updated-by``; a notice points back with
``update-to``. Citation records facts and alerts; research-ethics owns the
integrity verdict and wording.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.semantic_sim import similarity as _sem_sim
    _HAS_SEM = True
except Exception:
    _HAS_SEM = False

THIS_YEAR = dt.date.today().year
TITLE_SIM_WARN = 0.60
_MAILTO = (os.environ.get("CROSSREF_MAILTO")
           or os.environ.get("OPENALEX_MAILTO") or "").strip()
_OPENALEX_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
_S2_KEY = os.environ.get("S2_API_KEY", "").strip()
_RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
_EXPLICIT_MISSING = {404, 410}
_CN_RE = re.compile(r"[\u3400-\u9fff]")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_RETRACTED_TITLE_RE = re.compile(r"^\s*retracted(?:\s*:|\s+)", re.I)
_RET_FALLBACK = {"retraction", "withdrawal", "partial_retraction", "removal"}
_CON_FALLBACK = {"correction", "corrigendum", "erratum", "expression_of_concern",
                 "clarification", "addendum"}


def _load_flag_types() -> tuple[set[str], set[str]]:
    path = (_ROOT / "skills" / "light-research-ethics" / "references"
            / "retraction_flag_types.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ret = {str(v).lower().replace("-", "_") for v in data["retraction_level"]}
        con = {str(v).lower().replace("-", "_") for v in data["concern_level"]}
        return ret | {"partial_retraction", "removal"}, con | {
            "corrigendum", "erratum", "clarification", "addendum"}
    except Exception:
        return set(_RET_FALLBACK), set(_CON_FALLBACK)


RETRACTION_TYPES, CONCERN_TYPES = _load_flag_types()

_SURNAME_PARTICLES = {
    "al", "bin", "da", "de", "del", "della", "der", "di", "dos", "du",
    "la", "le", "st", "ten", "ter", "van", "von",
}


def _display_name_author(name: str) -> dict:
    """Parse conventional given-family display names without dropping particles."""
    parts = str(name or "").split()
    start = max(0, len(parts) - 1)
    while start > 0 and parts[start - 1].lower().rstrip(".") in _SURNAME_PARTICLES:
        start -= 1
    family = " ".join(parts[start:])
    given = " ".join(parts[:start])
    return {"family": family, "given": given, "name": str(name or "")}


def _pubmed_author(name: str) -> dict:
    """Parse ESummary's ``Family Name INITIALS`` representation."""
    parts = str(name or "").split()
    if len(parts) >= 2 and re.fullmatch(r"[A-Z]{1,8}", parts[-1]):
        family, given = " ".join(parts[:-1]), parts[-1]
    else:
        family, given = str(name or ""), ""
    return {"family": family, "given": given, "name": str(name or "")}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_doi(value: str) -> str:
    value = _DOI_PREFIX_RE.sub("", (value or "").strip())
    return value.rstrip(".,;:)]}").lower()


def load_refs_spec(path: str | pathlib.Path) -> list[Any]:
    """Accept either a bare reference list or light.citation_input.v1."""
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("references"), list):
        return payload["references"]
    raise ValueError("--spec must be a JSON list or an object with references[]")


def _ua() -> str:
    return (f"light-citation/2.1 (mailto:{_MAILTO})"
            if _MAILTO else "light-citation/2.1")


def _get_json(url: str, timeout: int = 30, headers: dict | None = None):
    """Return ``(HTTP status, JSON-or-None)``; status 0 means transport/parse failure."""
    req_headers = {"User-Agent": _ua(), "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            body = None
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return 0, None


def _outcome(code: int, found: bool = False, explicit_missing: bool = False) -> str:
    if found:
        return "FOUND"
    if explicit_missing or code in _EXPLICIT_MISSING:
        return "NOT_FOUND"
    if code == 0 or code in _RETRYABLE or code in {401, 403}:
        return "UNAVAILABLE"
    return "UNRESOLVED"


def _evidence(source: str, endpoint: str, code: int, fields: dict | None = None,
              *, explicit_missing: bool = False, note: str = "") -> dict:
    fields = fields or {}
    normalized_payload = {
        "http_status": code,
        "fields": fields,
        "note": note,
    }
    return {
        "source": source,
        "endpoint": endpoint,
        "http_status": code,
        "outcome": _outcome(code, bool(fields), explicit_missing),
        "retrieved_at": _now(),
        "fields": fields,
        "note": note,
        "normalized_payload_sha256": "sha256:" + hashlib.sha256(
            json.dumps(
                normalized_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def _date_year(obj: dict, *keys: str) -> int | None:
    for key in keys:
        parts = (obj.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def _crossref_fields(message: dict) -> dict:
    authors = []
    for author in message.get("author") or []:
        family = (author.get("family") or author.get("name") or "").strip()
        given = (author.get("given") or "").strip()
        authors.append({"family": family, "given": given,
                        "name": " ".join(v for v in (given, family) if v)})
    return {
        "title": ((message.get("title") or [""])[0] or "").strip(),
        "authors": authors,
        "year": _date_year(message, "published-print", "published-online", "issued"),
        "venue": ((message.get("container-title") or [""])[0] or "").strip(),
        "identifier": normalize_doi(message.get("DOI") or ""),
        "type": message.get("type"),
        "publisher": message.get("publisher"),
        "cited_by_count": message.get("is-referenced-by-count"),
    }


def _datacite_fields(payload: dict) -> dict:
    attrs = (payload.get("data") or {}).get("attributes") or {}
    authors = []
    for creator in attrs.get("creators") or []:
        authors.append({
            "family": (creator.get("familyName") or creator.get("name") or "").strip(),
            "given": (creator.get("givenName") or "").strip(),
            "name": (creator.get("name") or "").strip(),
        })
    container = attrs.get("container") or {}
    publisher = attrs.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    return {
        "title": (((attrs.get("titles") or [{}])[0].get("title")) or "").strip(),
        "authors": authors,
        "year": attrs.get("publicationYear"),
        "venue": (container.get("title") or publisher or "").strip(),
        "identifier": normalize_doi(attrs.get("doi") or ""),
        "type": ((attrs.get("types") or {}).get("resourceTypeGeneral")
                 or (attrs.get("types") or {}).get("resourceType")),
        "publisher": publisher,
        "version": attrs.get("version"),
        "related_identifiers": attrs.get("relatedIdentifiers") or [],
        "state": attrs.get("state"),
    }


def _s2_fields(payload: dict) -> dict:
    return {
        "title": (payload.get("title") or "").strip(),
        "authors": [_display_name_author(a.get("name") or "")
                    for a in payload.get("authors") or []],
        "year": payload.get("year"),
        "venue": (payload.get("venue") or "").strip(),
        "identifier": normalize_doi((payload.get("externalIds") or {}).get("DOI") or ""),
        "type": payload.get("publicationTypes"),
    }


def _openalex_fields(payload: dict) -> dict:
    source = ((payload.get("primary_location") or {}).get("source") or {})
    return {
        "title": (payload.get("title") or "").strip(),
        "authors": [
            _display_name_author((a.get("author") or {}).get("display_name") or "")
            for a in payload.get("authorships") or []
        ],
        "year": payload.get("publication_year"),
        "venue": (source.get("display_name") or "").strip(),
        "identifier": normalize_doi(payload.get("doi") or ""),
        "type": payload.get("type"),
        "version": (payload.get("primary_location") or {}).get("version"),
        "is_oa": (payload.get("open_access") or {}).get("is_oa"),
        "oa_status": (payload.get("open_access") or {}).get("oa_status"),
        "is_in_doaj": source.get("is_in_doaj"),
        "cited_by_count": payload.get("cited_by_count"),
    }


def _query_pubmed(doi: str) -> tuple[int, dict | None, str]:
    search = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
              + urllib.parse.urlencode({"db": "pubmed", "term": f"{doi}[doi]",
                                        "retmode": "json", "retmax": "3"}))
    code, result = _get_json(search)
    if code != 200 or not result:
        return code, None, search
    ids = ((result.get("esearchresult") or {}).get("idlist") or [])
    if not ids:
        return 404, None, search
    summary = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
               + urllib.parse.urlencode({"db": "pubmed", "id": ids[0],
                                         "retmode": "json"}))
    code2, data = _get_json(summary)
    if code2 != 200 or not data:
        return code2, None, summary
    doc = (data.get("result") or {}).get(ids[0]) or {}
    article_ids = {item.get("idtype"): item.get("value")
                   for item in doc.get("articleids") or []}
    fields = {
        "title": (doc.get("title") or "").rstrip("."),
        "authors": [_pubmed_author(a.get("name", ""))
                    for a in doc.get("authors") or []],
        "year": int(doc.get("pubdate", "")[:4]) if doc.get("pubdate", "")[:4].isdigit() else None,
        "venue": doc.get("fulljournalname") or doc.get("source") or "",
        "identifier": normalize_doi(article_ids.get("doi") or doi),
        "pmid": ids[0],
        "type": doc.get("pubtype") or [],
    }
    return code2, fields, summary


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", str(value or "").lower())


def _title_match(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if _HAS_SEM:
        return _sem_sim(a, b, mode="offline")
    aw = {_norm_text(w) for w in a.split() if _norm_text(w)}
    bw = {_norm_text(w) for w in b.split() if _norm_text(w)}
    return len(aw & bw) / len(aw | bw) if aw and bw else 0.0


def _family_names(authors: list[dict] | list[str]) -> list[str]:
    out = []
    for author in authors or []:
        raw = author if isinstance(author, str) else (
            author.get("family") or author.get("name") or "")
        folded = unicodedata.normalize("NFKD", raw).encode(
            "ascii", "ignore").decode("ascii") or raw
        norm = re.sub(r"[^a-z\u3400-\u9fff]", "", folded.lower())
        if norm:
            out.append(norm)
    return out


def author_set_diff(claimed_authors, real_authors) -> dict:
    claimed = _family_names(claimed_authors or [])
    real = _family_names(real_authors or [])
    cs, rs = set(claimed), set(real)
    common = cs & rs
    reordered = ([a for a in claimed if a in common] != [a for a in real if a in common]
                 if len(common) >= 2 else False)
    added, removed = sorted(cs - rs), sorted(rs - cs)
    verdict = ("author_addition" if added else "author_deletion" if removed
               else "reordered" if reordered else "match")
    return {
        "added": added, "removed": removed, "reordered": reordered,
        "jaccard": round(len(common) / len(cs | rs), 3) if cs | rs else 1.0,
        "verdict": verdict,
    }


def _field_conflicts(evidence: list[dict]) -> list[dict]:
    found = [e for e in evidence if e["outcome"] == "FOUND"]
    conflicts = []
    for field in ("title", "authors", "year", "venue", "identifier"):
        values = []
        for item in found:
            value = item["fields"].get(field)
            if value in (None, "", []):
                continue
            values.append({"source": item["source"], "value": value})
        if len(values) < 2:
            continue
        if field == "title":
            conflict = any(_title_match(values[0]["value"], v["value"]) < TITLE_SIM_WARN
                           for v in values[1:])
        elif field == "authors":
            base = set(_family_names(values[0]["value"]))
            conflict = any(set(_family_names(v["value"])) != base for v in values[1:])
        elif field == "year":
            conflict = any(abs(int(values[0]["value"]) - int(v["value"])) > 1
                           for v in values[1:] if str(v["value"]).isdigit())
        else:
            conflict = any(_norm_text(v["value"]) != _norm_text(values[0]["value"])
                           for v in values[1:])
        if conflict:
            conflicts.append({"field": field, "values": values})
    return conflicts


def _publication_updates(message: dict) -> list[dict]:
    value = message.get("updated-by")
    relations = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
    updates = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        kind = (relation.get("type") or "").lower().replace("-", "_")
        if kind in RETRACTION_TYPES | CONCERN_TYPES:
            updates.append({
                "type": kind,
                "notice_doi": normalize_doi(relation.get("DOI") or ""),
                "label": relation.get("label"),
                "source": relation.get("source"),
                "relation": "updated-by",
                "applies_to_queried_work": True,
            })
    return updates


def verify_one(doi: str, self_authors=None, claimed=None) -> dict:
    self_authors = [re.sub(r"[^a-z\u3400-\u9fff]", "", s.lower())
                    for s in (self_authors or []) if s]
    claimed = claimed or {}
    doi = normalize_doi(doi)
    evidence: list[dict] = []

    ra_url = "https://doi.org/ra/" + urllib.parse.quote(doi, safe="/")
    ra_code, ra_data = _get_json(ra_url)
    ra_name, ra_missing = "", False
    if ra_code == 200 and isinstance(ra_data, list) and ra_data:
        ra_name = str(ra_data[0].get("RA") or "")
        ra_missing = "does not exist" in str(ra_data[0].get("status") or "").lower()
    ra_fields = {"registration_agency": ra_name} if ra_name else {}
    evidence.append(_evidence("DOI Registration Agency", ra_url, ra_code, ra_fields,
                              explicit_missing=ra_missing,
                              note=(ra_data[0].get("status", "") if isinstance(ra_data, list)
                                    and ra_data else "")))

    cr_endpoint = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    cr_url = cr_endpoint
    if _MAILTO:
        cr_url += "?mailto=" + urllib.parse.quote(_MAILTO, safe="")
    cr_code, cr_payload = _get_json(cr_url)
    cr_message = (cr_payload or {}).get("message") if isinstance(cr_payload, dict) else None
    cr_fields = _crossref_fields(cr_message) if isinstance(cr_message, dict) else {}
    evidence.append(_evidence(
        "Crossref", cr_endpoint, cr_code, cr_fields,
        note="polite-pool contact configured" if _MAILTO else "",
    ))

    dc_url = "https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="")
    dc_code, dc_payload = _get_json(dc_url)
    dc_fields = (_datacite_fields(dc_payload) if dc_code == 200
                 and isinstance(dc_payload, dict) else {})
    evidence.append(_evidence("DataCite", dc_url, dc_code, dc_fields))

    pm_code, pm_fields, pm_url = _query_pubmed(doi)
    evidence.append(_evidence("PubMed", pm_url, pm_code, pm_fields or {}))

    s2_url = ("https://api.semanticscholar.org/graph/v1/paper/DOI%3A"
              + urllib.parse.quote(doi, safe="")
              + "?fields=title,authors,year,venue,externalIds,publicationTypes")
    s2_headers = {"x-api-key": _S2_KEY} if _S2_KEY else None
    s2_code, s2_payload = _get_json(s2_url, headers=s2_headers)
    s2_fields = _s2_fields(s2_payload) if s2_code == 200 and isinstance(s2_payload, dict) else {}
    evidence.append(_evidence("Semantic Scholar", s2_url, s2_code, s2_fields))

    oa_fields = {}
    oa_code = 403
    oa_endpoint = ("https://api.openalex.org/works/https://doi.org/"
                   + urllib.parse.quote(doi, safe=""))
    oa_url = oa_endpoint
    if _OPENALEX_KEY:
        oa_url += "?" + urllib.parse.urlencode({"api_key": _OPENALEX_KEY})
        oa_code, oa_payload = _get_json(oa_url)
        oa_fields = (_openalex_fields(oa_payload) if oa_code == 200
                     and isinstance(oa_payload, dict) else {})
        evidence.append(_evidence(
            "OpenAlex", oa_endpoint, oa_code, oa_fields,
            note="API key configured; value intentionally not persisted",
        ))
    else:
        evidence.append(_evidence(
            "OpenAlex", oa_endpoint, 0, {},
            note="free API key not configured; optional enhancement, never core dependency",
        ))

    primary_source = ""
    primary = {}
    if ra_name.lower() == "crossref" and cr_fields:
        primary_source, primary = "Crossref", cr_fields
    elif ra_name.lower() == "datacite" and dc_fields:
        primary_source, primary = "DataCite", dc_fields
    elif cr_fields:
        primary_source, primary = "Crossref", cr_fields
    elif dc_fields:
        primary_source, primary = "DataCite", dc_fields

    secondary_found = [e for e in evidence if e["source"] in {
        "PubMed", "Semantic Scholar", "OpenAlex"} and e["outcome"] == "FOUND"]
    missing = (ra_missing and cr_code in _EXPLICIT_MISSING
               and dc_code in _EXPLICIT_MISSING)
    authoritative_unavailable = any(e["outcome"] == "UNAVAILABLE" for e in evidence
                                    if e["source"] in {
                                        "DOI Registration Agency", "Crossref", "DataCite"})
    if missing:
        status = "CONFIRMED-MISSING"
    elif primary and secondary_found:
        status = "CONFIRMED"
    elif primary or ra_name:
        status = "UNRESOLVED"
    elif authoritative_unavailable:
        status = "UNAVAILABLE"
    else:
        status = "UNRESOLVED"

    updates = _publication_updates(cr_message or {})
    title = primary.get("title")
    authors = primary.get("authors") or []
    year = primary.get("year")
    venue = primary.get("venue")
    conflicts = _field_conflicts(evidence)

    mismatch_fields = []
    claimed_title_sim = None
    if claimed.get("title") and title:
        claimed_title_sim = round(_title_match(str(claimed["title"]), title), 3)
        if claimed_title_sim < TITLE_SIM_WARN:
            mismatch_fields.append("title")
    claimed_authors = claimed.get("authors") or (
        [claimed.get("first_author")] if claimed.get("first_author") else [])
    author_diff = author_set_diff(claimed_authors, authors) if claimed_authors and authors else {}
    if author_diff and author_diff["verdict"] != "match":
        mismatch_fields.append("authors")
    if claimed.get("year") and year:
        try:
            if abs(int(claimed["year"]) - int(year)) > 1:
                mismatch_fields.append("year")
        except (TypeError, ValueError):
            mismatch_fields.append("year")

    title_matches = claimed_title_sim is None or claimed_title_sim >= TITLE_SIM_WARN
    is_chimeric = (
        len(set(mismatch_fields) & {"title", "authors", "year"}) >= 2
        or (title_matches and author_diff.get("verdict") == "author_addition")
    )
    errors, warnings = [], []
    if missing:
        errors.append({"severity": "high", "msg":
                       "DOI Registration Agency 明确不存在，且 Crossref/DataCite 均 404"})
    if is_chimeric:
        errors.append({"severity": "high", "msg":
                       "疑似嵌合引用：真实标识符与声称的 title/authors/year 多字段冲突",
                       "mismatch_fields": sorted(set(mismatch_fields))})
    if status in {"UNAVAILABLE", "UNRESOLVED"}:
        warnings.append(f"{status}: 尚未取得注册源 + 第二独立字段源的一致确认")
    if mismatch_fields and not is_chimeric:
        warnings.append("所引元数据与注册源不一致：" + ",".join(sorted(set(mismatch_fields))))
    for conflict in conflicts:
        warnings.append(f"逐源字段冲突:{conflict['field']}（保留各源值，不自动覆盖）")
    for update in updates:
        warnings.append(
            f"Crossref updated-by:{update['type']} → {update['notice_doi'] or 'notice unknown'};"
            "事实警报交 research-ethics 终判")
    if _RETRACTED_TITLE_RE.match(title or "") and not any(
            u["type"] in RETRACTION_TYPES for u in updates):
        updates.append({
            "type": "retraction", "notice_doi": "", "label": "title prefix",
            "source": "crossref-title", "relation": "title",
            "applies_to_queried_work": True,
        })

    real_families = set(_family_names(authors))
    is_self_cite = any(name in real_families for name in self_authors)
    is_cn = bool(_CN_RE.search((title or "") + " "
                               + " ".join(a.get("name", "") for a in authors)))
    cited_by = primary.get("cited_by_count")
    if cited_by is None and oa_fields:
        cited_by = oa_fields.get("cited_by_count")

    return {
        "doi": doi,
        "status": status,
        "canonical_source": primary_source or None,
        "metadata": {
            "title": title, "authors": authors, "year": year, "venue": venue,
            "identifier": primary.get("identifier") or doi, "type": primary.get("type"),
            "publisher": primary.get("publisher"), "version": primary.get("version"),
        },
        "source_evidence": evidence,
        "field_conflicts": conflicts,
        "mismatch_fields": sorted(set(mismatch_fields)),
        "publication_updates": updates,
        "title": title, "authors": authors, "year": year, "venue": venue,
        "cited_by_count": cited_by,
        "found_crossref": bool(cr_fields),
        "found_datacite": bool(dc_fields),
        "found_pubmed": bool(pm_fields),
        "found_semanticscholar": bool(s2_fields),
        "found_openalex": bool(oa_fields),
        "http": {
            "doi_ra": ra_code, "crossref": cr_code, "datacite": dc_code,
            "pubmed": pm_code, "semanticscholar": s2_code, "openalex": oa_code,
        },
        "claimed_title_sim": claimed_title_sim,
        "author_set_diff": author_diff,
        "is_chimeric": is_chimeric,
        "is_retracted": any(u["type"] in RETRACTION_TYPES for u in updates),
        "retraction_flags": updates,
        "is_self_cite": is_self_cite,
        "is_cn": is_cn,
        "is_oa": oa_fields.get("is_oa"),
        "oa_status": oa_fields.get("oa_status"),
        "is_in_doaj": oa_fields.get("is_in_doaj"),
        "oa_type": oa_fields.get("type"),
        "version": oa_fields.get("version") or primary.get("version"),
        "unverified_offline": status in {"UNAVAILABLE", "UNRESOLVED"},
        "errors": errors,
        "warnings": warnings,
    }


def build_report(refs, self_authors=None):
    items = []
    for raw in refs:
        if isinstance(raw, str):
            doi, claimed = raw, {}
        else:
            doi = raw.get("doi") or raw.get("DOI") or ""
            claimed = {k: raw[k] for k in ("title", "first_author", "authors", "year")
                       if raw.get(k) not in (None, "", [])}
        if normalize_doi(doi):
            items.append(verify_one(doi, self_authors, claimed=claimed))
    counts = {state: sum(1 for item in items if item["status"] == state)
              for state in ("CONFIRMED", "CONFIRMED-MISSING", "UNAVAILABLE", "UNRESOLVED")}
    n = len(items)
    return {
        "schema": "light.citation_verification.v2",
        "summary": {
            "total": n,
            "status_counts": counts,
            "verified_ok": counts["CONFIRMED"],
            "high_severity_errors": sum(len(item["errors"]) for item in items),
            "unverified_offline_count": counts["UNAVAILABLE"] + counts["UNRESOLVED"],
            "cn_count": sum(1 for item in items if item["is_cn"]),
            "self_citation_rate": round(
                sum(1 for item in items if item["is_self_cite"]) / n, 3) if n else 0,
            "recent_2y_count": sum(
                1 for item in items if (item.get("year") or 0) >= THIS_YEAR - 2),
            "preprint_count": sum(
                1 for item in items if item.get("oa_type") == "preprint"),
            "retracted_signal_count": sum(
                1 for item in items if item.get("publication_updates")),
            "checked_at": _now(),
            "state_rule": (
                "CONFIRMED requires registration metadata plus an independent field source; "
                "CONFIRMED-MISSING requires DOI RA explicit non-existence and "
                "Crossref+DataCite 404; failures/rate limits never mean missing."
            ),
        },
        "items": items,
    }


def _selftest() -> int:
    print("### verify_refs offline selftest")
    global _get_json, _query_pubmed, _MAILTO, _OPENALEX_KEY
    old_get, old_pubmed = _get_json, _query_pubmed
    old_mailto, old_openalex_key = _MAILTO, _OPENALEX_KEY

    def fake_get(url, timeout=30, headers=None):
        if "missing" in url:
            if "doi.org/ra" in url:
                return 200, [{"DOI": "10.0/missing", "status": "DOI does not exist"}]
            return 404, None
        if "unavailable" in url:
            return 503, None
        if "doi.org/ra" in url:
            return 200, [{"DOI": "10.0/ok", "RA": "Crossref"}]
        if "api.crossref.org" in url:
            return 200, {"message": {
                "DOI": "10.0/ok", "title": ["A Real Study"],
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Journal"], "type": "journal-article",
                "author": [{"family": "Smith", "given": "Ann"}],
                "updated-by": {"type": "retraction", "DOI": "10.0/notice",
                               "source": "retraction-watch"},
                "update-to": {"type": "retraction", "DOI": "10.0/other-original"},
            }}
        if "api.datacite.org" in url:
            return 404, None
        if "semanticscholar" in url:
            return 200, {"title": "A Real Study", "year": 2024, "venue": "Journal",
                         "authors": [{"name": "Ann Smith"}],
                         "externalIds": {"DOI": "10.0/ok"}}
        return 403, None

    def fake_pubmed(doi):
        return 404, None, "https://pubmed.test"

    try:
        _get_json, _query_pubmed = fake_get, fake_pubmed
        _MAILTO = "private@example.invalid"
        _OPENALEX_KEY = "private-openalex-key"
        ok = verify_one("10.0/ok", self_authors=["Smith"],
                        claimed={"title": "Wrong Topic", "authors": ["Jones"],
                                 "year": 1999})
        missing = verify_one("10.0/missing", self_authors=["Smith"])
        unavailable = verify_one("10.0/unavailable", self_authors=["Smith"])
    finally:
        _get_json, _query_pubmed = old_get, old_pubmed
        _MAILTO, _OPENALEX_KEY = old_mailto, old_openalex_key

    assert ok["status"] == "CONFIRMED" and ok["is_self_cite"], ok
    assert ok["is_chimeric"] and set(ok["mismatch_fields"]) == {
        "title", "authors", "year"}, ok
    assert ok["publication_updates"][0]["relation"] == "updated-by", ok
    serialized_evidence = json.dumps(ok["source_evidence"], ensure_ascii=False)
    assert "private@example.invalid" not in serialized_evidence, serialized_evidence
    assert "private-openalex-key" not in serialized_evidence, serialized_evidence
    assert all(item.get("normalized_payload_sha256")
               for item in ok["source_evidence"]), ok["source_evidence"]
    assert all(u.get("notice_doi") != "10.0/other-original"
               for u in ok["publication_updates"]), "must ignore inverse update-to"
    assert missing["status"] == "CONFIRMED-MISSING", missing
    assert unavailable["status"] == "UNAVAILABLE" and not unavailable["errors"], unavailable
    assert author_set_diff(["Smith", "Jones"], ["Smith", "Brown"])["verdict"] == "author_addition"
    compound = [
        _pubmed_author("van der Walt SJ"),
        _pubmed_author("Del Río JF"),
        _display_name_author("Stefan van der Walt"),
        _display_name_author("Juan Del Río"),
    ]
    assert [a["family"] for a in compound] == [
        "van der Walt", "Del Río", "van der Walt", "Del Río"], compound
    assert _family_names(compound[:2]) == _family_names(compound[2:]), compound
    with tempfile.TemporaryDirectory() as temp:
        spec_path = pathlib.Path(temp) / "spec.json"
        spec_path.write_text(json.dumps({
            "schema": "light.citation_input.v1",
            "references": [{"doi": "10.0/ok"}],
        }), encoding="utf-8")
        assert load_refs_spec(spec_path) == [{"doi": "10.0/ok"}]
    report = {
        "summary": {
            state: sum(item["status"] == state for item in (ok, missing, unavailable))
            for state in ("CONFIRMED", "CONFIRMED-MISSING", "UNAVAILABLE")
        }
    }
    assert report["summary"]["CONFIRMED-MISSING"] == 1
    print("[selftest] PASS: two-source confirmation / explicit missing / 5xx unavailable / "
          "chimeric metadata / updated-by direction / compound-surname parsing / "
          "normalized payload hash / credential redaction / wrapped spec input / "
          "self-author failure-safe")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Multi-source scholarly reference verification with source-level evidence")
    parser.add_argument("dois", nargs="*")
    parser.add_argument("--file", help="one DOI per line")
    parser.add_argument("--spec", help="JSON list with doi/title/authors/year")
    parser.add_argument("--self-author", action="append", default=[])
    parser.add_argument("--mailto", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--s2-api-key", default="")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()

    global _MAILTO, _OPENALEX_KEY, _S2_KEY
    if args.mailto:
        _MAILTO = args.mailto.strip()
    if args.openalex_api_key:
        _OPENALEX_KEY = args.openalex_api_key.strip()
    if args.s2_api_key:
        _S2_KEY = args.s2_api_key.strip()

    refs: list[Any] = list(args.dois)
    if args.file:
        refs.extend(line.strip() for line in pathlib.Path(args.file).read_text(
            encoding="utf-8").splitlines() if line.strip() and not line.startswith("#"))
    if args.spec:
        refs.extend(load_refs_spec(args.spec))
    if not refs:
        parser.error("provide DOI(s), --file, or --spec")
    report = build_report(refs, args.self_author)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"report -> {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
