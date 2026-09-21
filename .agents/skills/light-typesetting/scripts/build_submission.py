#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a provenance-preserving stage-11 submission bundle.

This orchestrator snapshots declared manuscript/figure/citation inputs, runs a
deterministic preflight, invokes compile_driver, evaluates the supplied venue
profile, and emits canonical build/delivery/failure artifacts.  It never
re-verifies citation authenticity and never invents venue limits.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import compile_driver as cd  # noqa: E402
import submission_check as sc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve()
while ROOT != ROOT.parent and not (ROOT / "_shared" / "__init__.py").exists():
    ROOT = ROOT.parent
CITATION_SCRIPTS = ROOT / "skills" / "light-citation" / "scripts"
if CITATION_SCRIPTS.is_dir():
    sys.path.insert(0, str(CITATION_SCRIPTS))
try:
    import citekey_audit as cka  # noqa: E402
except ImportError:
    cka = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

INPUT_SCHEMA = "light.typesetting_input.v1"
MANIFEST_SCHEMA = "light.typesetting_build.v1"
DELIVERY_SCHEMA = "light.typesetting_delivery.v1"
PROFILE_SCHEMA = "light.typesetting_venue_profile.v1"
CITATION_DELIVERY_SCHEMA = "light.citation_delivery.v1"
FIGURE_DELIVERY_SCHEMA = "light.figure_delivery.v1"
FIGURE_BUILD_SCHEMA = "light.figure_build.v1"
_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_GRAPHIC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]+)\}")
_LABEL = re.compile(r"\\label\s*\{([^}]+)\}")
_REF = re.compile(r"\\(?:ref|pageref|autoref|cref|Cref)\s*\{([^}]+)\}")
_PACKAGE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", re.I)
_DOC_CLASS = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", re.I)
_SHA = re.compile(r"(?:sha256:)?[0-9a-fA-F]{64}")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file_prefixed(path: pathlib.Path) -> str | None:
    digest = sha256_file(path)
    return "sha256:" + digest if digest else None


def normalize_sha256(value: Any) -> str | None:
    text = str(value or "").strip()
    if not _SHA.fullmatch(text):
        return None
    return text.lower() if text.startswith("sha256:") else "sha256:" + text.lower()


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(base: pathlib.Path, value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def resolve_declared_child(base: pathlib.Path, value: Any) -> pathlib.Path | None:
    raw = pathlib.Path(str(value or ""))
    if not str(value or "").strip() or raw.is_absolute():
        return None
    root = base.resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def provenance(path: pathlib.Path, role: str, declared_source: Any = None) -> dict[str, Any]:
    return {
        "role": role,
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
        "declared_source": declared_source,
    }


def check(status: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"status": status, "code": code, "message": message}
    item.update({key: value for key, value in extra.items() if value is not None})
    return item


def _copy_file(source: pathlib.Path, root: pathlib.Path, target: str) -> pathlib.Path:
    destination = (root / target).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"target escapes source snapshot: {target}") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _profile(spec: dict[str, Any], base: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = spec.get("venue_profile")
    if isinstance(raw, str):
        path = resolve(base, raw)
        data = json.loads(path.read_text(encoding="utf-8"))
        prov = provenance(path, "venue_profile", data.get("source"))
    elif isinstance(raw, dict):
        data = raw
        prov = {
            "role": "venue_profile", "path": None, "exists": True,
            "sha256": hashlib.sha256(
                json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "declared_source": data.get("source"),
        }
    else:
        data = {"schema": PROFILE_SCHEMA, "name": "unspecified", "source": None, "rules": {}}
        prov = {"role": "venue_profile", "path": None, "exists": False,
                "sha256": None, "declared_source": None}
    if data.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"venue profile schema must be {PROFILE_SCHEMA}")
    return data, prov


def snapshot_inputs(
    spec: dict[str, Any], spec_base: pathlib.Path, source_root: pathlib.Path
) -> dict[str, Any]:
    manuscript = spec.get("manuscript") or {}
    manuscript_path = resolve(spec_base, manuscript["path"])
    entry_target = manuscript.get("target") or manuscript_path.name
    inputs = [provenance(manuscript_path, "paper-writing.manuscript", manuscript.get("source"))]
    if not manuscript_path.is_file():
        return {"entrypoint": source_root / entry_target, "inputs": inputs,
                "errors": [check("ERROR", "MANUSCRIPT_MISSING", str(manuscript_path))]}
    entrypoint = _copy_file(manuscript_path, source_root, entry_target)
    errors = []
    for row in manuscript.get("source_files") or []:
        data = {"path": row} if isinstance(row, str) else row
        source = resolve(spec_base, data["path"])
        inputs.append(provenance(source, "paper-writing.source_file", data.get("source")))
        if source.is_file():
            _copy_file(source, source_root, data.get("target") or source.name)
        else:
            errors.append(check("ERROR", "SOURCE_FILE_MISSING", str(source)))
    figure_rows = []
    for index, row in enumerate(spec.get("figures") or [], 1):
        figure_id = row.get("id") or f"F{index}"
        source = resolve(spec_base, row["path"])
        target = row.get("target") or f"figures/{source.name}"
        manifest_value = row.get("source_manifest")
        manifest_source = resolve(spec_base, manifest_value) if manifest_value else None
        inputs.append(provenance(source, f"figure.{figure_id}", manifest_value))
        manifest_snapshot = None
        manifest_data = None
        if manifest_source:
            inputs.append(provenance(manifest_source, f"figure.{figure_id}.manifest", None))
            if manifest_source.is_file():
                manifest_snapshot = _copy_file(
                    manifest_source, source_root,
                    f"provenance/figures/{figure_id}-{manifest_source.name}",
                )
                try:
                    manifest_data = json.loads(manifest_source.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(check(
                        "ERROR", "FIGURE_MANIFEST_JSON",
                        f"{manifest_source}: {exc}", figure_id=figure_id,
                    ))
            else:
                errors.append(check(
                    "ERROR", "FIGURE_MANIFEST_MISSING", str(manifest_source),
                    figure_id=figure_id,
                ))
        else:
            errors.append(check(
                "ERROR", "FIGURE_MANIFEST_UNDECLARED",
                "each figure row must name the figure delivery/build manifest",
                figure_id=figure_id,
            ))
        if source.is_file():
            copied = _copy_file(source, source_root, target)
            figure_rows.append({
                "id": figure_id, "source": str(source),
                "target": str(copied), "target_relative": target,
                "sha256": sha256_file(copied),
                "sha256_prefixed": sha256_file_prefixed(copied),
                "declared_dimensions": row.get("dimensions"),
                "source_manifest": str(manifest_source) if manifest_source else None,
                "source_manifest_snapshot": str(manifest_snapshot) if manifest_snapshot else None,
                "source_manifest_schema": (
                    manifest_data.get("schema") if isinstance(manifest_data, dict) else None
                ),
                "source_manifest_data": manifest_data,
            })
        else:
            errors.append(check("ERROR", "FIGURE_MISSING", str(source), figure_id=figure_id))

    citation = spec.get("citation") or {}
    delivery_path = resolve(spec_base, citation["delivery"])
    inputs.append(provenance(delivery_path, "citation.delivery", None))
    citation_data = None
    citation_audit = None
    bib_target = citation.get("bib_target") or "references.bib"
    bib_source = None
    citation_delivery_snapshot = None
    citation_delivery_dir = delivery_path.parent
    citation_sidecar_snapshots: dict[str, str] = {}
    if not delivery_path.is_file():
        errors.append(check("ERROR", "CITATION_DELIVERY_MISSING", str(delivery_path)))
    else:
        citation_delivery_snapshot = _copy_file(
            delivery_path, source_root, "provenance/citation/delivery.json"
        )
        citation_data = json.loads(delivery_path.read_text(encoding="utf-8"))
        if citation_data.get("schema") != CITATION_DELIVERY_SCHEMA:
            errors.append(check("ERROR", "CITATION_DELIVERY_SCHEMA",
                                f"got {citation_data.get('schema')}"))
        deliverables = citation_data.get("deliverables") or {}
        bib_name = deliverables.get("bibtex")
        audit_name = deliverables.get("citekey_audit")
        if bib_name:
            bib_source = resolve_declared_child(delivery_path.parent, bib_name)
            if bib_source is None:
                errors.append(check(
                    "ERROR", "CITATION_DELIVERABLE_ESCAPES",
                    f"bibtex: {bib_name}", file=str(delivery_path),
                ))
            else:
                inputs.append(provenance(bib_source, "citation.references_bib", delivery_path.name))
                if bib_source.is_file():
                    _copy_file(bib_source, source_root, bib_target)
                else:
                    errors.append(check("ERROR", "REFERENCES_BIB_MISSING", str(bib_source)))
        else:
            errors.append(check("ERROR", "REFERENCES_BIB_UNDECLARED", "delivery lacks bibtex"))
        if audit_name:
            audit_path = resolve_declared_child(delivery_path.parent, audit_name)
            if audit_path is None:
                errors.append(check(
                    "ERROR", "CITATION_DELIVERABLE_ESCAPES",
                    f"citekey_audit: {audit_name}", file=str(delivery_path),
                ))
            else:
                inputs.append(provenance(audit_path, "citation.citekey_audit", delivery_path.name))
                if audit_path.is_file():
                    citation_audit = json.loads(audit_path.read_text(encoding="utf-8"))
                    citation_sidecar_snapshots["citekey_audit"] = str(_copy_file(
                        audit_path, source_root, "provenance/citation/citekey-audit.json"
                    ))
                else:
                    errors.append(check("ERROR", "CITEKEY_AUDIT_MISSING", str(audit_path)))
        else:
            errors.append(check("ERROR", "CITEKEY_AUDIT_UNDECLARED", "delivery lacks citekey audit"))
        for role in ("failures", "claim_review"):
            sidecar_name = deliverables.get(role)
            if not sidecar_name:
                continue
            sidecar_path = resolve_declared_child(delivery_path.parent, sidecar_name)
            if sidecar_path is None:
                errors.append(check(
                    "ERROR", "CITATION_DELIVERABLE_ESCAPES",
                    f"{role}: {sidecar_name}", file=str(delivery_path),
                ))
                continue
            inputs.append(provenance(sidecar_path, f"citation.{role}", delivery_path.name))
            if sidecar_path.is_file():
                citation_sidecar_snapshots[role] = str(_copy_file(
                    sidecar_path,
                    source_root,
                    f"provenance/citation/{role}-{sidecar_path.name}",
                ))
    return {
        "entrypoint": entrypoint, "inputs": inputs, "errors": errors,
        "figures": figure_rows, "citation_delivery": citation_data,
        "citation_delivery_path": str(delivery_path),
        "citation_delivery_dir": str(citation_delivery_dir),
        "citation_delivery_snapshot": str(citation_delivery_snapshot) if citation_delivery_snapshot else None,
        "citation_sidecar_snapshots": citation_sidecar_snapshots,
        "citation_audit": citation_audit, "bib_source": bib_source,
        "bib_target": source_root / bib_target,
    }


def _tex_closure(entrypoint: pathlib.Path) -> tuple[list[pathlib.Path], list[dict[str, Any]]]:
    queue = [entrypoint]
    seen: set[pathlib.Path] = set()
    files: list[pathlib.Path] = []
    checks: list[dict[str, Any]] = []
    while queue:
        path = queue.pop(0).resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            checks.append(check("ERROR", "TEX_INCLUDE_MISSING", str(path)))
            continue
        files.append(path)
        text = cd.strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for raw in _INPUT.findall(text):
            child = pathlib.Path(raw)
            if not child.suffix:
                child = child.with_suffix(".tex")
            queue.append((path.parent / child).resolve())
    return files, checks


def _graphic_exists(base: pathlib.Path, raw: str) -> pathlib.Path | None:
    candidate = (base / raw).resolve()
    if candidate.is_file():
        return candidate
    if candidate.suffix:
        return None
    for suffix in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
        trial = candidate.with_suffix(suffix)
        if trial.is_file():
            return trial
    return None


def _measure_figure(path: pathlib.Path) -> dict[str, Any]:
    """Read physical asset dimensions without judging figure scientific quality."""
    result: dict[str, Any] = {
        "path": str(path), "width_mm": None, "height_mm": None,
        "dpi_x": None, "dpi_y": None, "method": None,
    }
    if path.suffix.lower() == ".pdf":
        pdfinfo = sc.resolve_tool("pdfinfo")
        if not pdfinfo:
            result["method"] = "pdfinfo unavailable"
            return result
        try:
            proc = subprocess.run(
                [pdfinfo, str(path)], capture_output=True, text=True,
                timeout=15, encoding="utf-8", errors="replace",
            )
        except (OSError, subprocess.TimeoutExpired):
            result["method"] = "pdfinfo failed"
            return result
        match = re.search(
            r"^Page size:\s*([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
            proc.stdout or "", re.MULTILINE | re.IGNORECASE,
        )
        if match:
            result.update({
                "width_mm": round(float(match.group(1)) * 25.4 / 72.0, 2),
                "height_mm": round(float(match.group(2)) * 25.4 / 72.0, 2),
                "method": "pdfinfo MediaBox",
            })
        else:
            result["method"] = "pdfinfo no page size"
        return result
    try:
        from PIL import Image
        with Image.open(path) as image:
            dpi = image.info.get("dpi") or (None, None)
            dpi_x = float(dpi[0]) if dpi and dpi[0] else None
            dpi_y = float(dpi[1]) if len(dpi) > 1 and dpi[1] else dpi_x
            result.update({
                "pixels": {"width": image.width, "height": image.height},
                "dpi_x": round(dpi_x, 2) if dpi_x else None,
                "dpi_y": round(dpi_y, 2) if dpi_y else None,
                "width_mm": round(image.width / dpi_x * 25.4, 2) if dpi_x else None,
                "height_mm": round(image.height / dpi_y * 25.4, 2) if dpi_y else None,
                "method": "Pillow",
            })
    except (ImportError, OSError, ValueError):
        result["method"] = "raster metadata unavailable"
    return result


def _dimension_checks(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []
    for row in snapshot.get("figures") or []:
        measurement = _measure_figure(pathlib.Path(row["target"]))
        measurement["id"] = row["id"]
        measurement["declared"] = row.get("declared_dimensions")
        measurements.append(measurement)
        declared = row.get("declared_dimensions") or {}
        for key in ("width_mm", "height_mm"):
            expected = declared.get(key)
            actual = measurement.get(key)
            if expected is None:
                continue
            if actual is None:
                checks.append(check(
                    "SKIP", "FIGURE_DIMENSION_UNVERIFIED",
                    f"{row['id']} {key}: declared={expected}, measurement unavailable",
                    file=row["target"],
                ))
                continue
            tolerance = max(1.0, abs(float(expected)) * 0.02)
            if abs(float(actual) - float(expected)) > tolerance:
                checks.append(check(
                    "ERROR", "FIGURE_DIMENSION_MISMATCH",
                    f"{row['id']} {key}: declared={expected} mm, actual={actual} mm",
                    file=row["target"],
                ))
        expected_dpi = declared.get("dpi")
        actual_dpi = measurement.get("dpi_x")
        suffix = pathlib.Path(row["target"]).suffix.lower()
        if expected_dpi is not None and actual_dpi is None and suffix not in (".pdf", ".svg", ".eps"):
            checks.append(check(
                "SKIP", "FIGURE_DPI_UNVERIFIED",
                f"{row['id']}: declared={expected_dpi}, raster DPI metadata unavailable",
                file=row["target"],
            ))
        elif expected_dpi is not None and actual_dpi is not None and abs(float(actual_dpi) - float(expected_dpi)) > 1:
            checks.append(check(
                "ERROR", "FIGURE_DPI_MISMATCH",
                f"{row['id']}: declared={expected_dpi}, actual={actual_dpi}",
                file=row["target"],
            ))
    return checks, measurements


def _figure_manifest_outputs(doc: dict[str, Any]) -> list[dict[str, Any]]:
    schema = doc.get("schema")
    if schema == FIGURE_DELIVERY_SCHEMA:
        build = doc.get("build") or {}
        return build.get("outputs") or []
    if schema == FIGURE_BUILD_SCHEMA:
        return doc.get("outputs") or []
    return []


def _figure_manifest_checks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for row in snapshot.get("figures") or []:
        figure_id = row.get("id")
        doc = row.get("source_manifest_data")
        actual_hash = normalize_sha256(row.get("sha256_prefixed"))
        if not isinstance(doc, dict):
            continue
        schema = doc.get("schema")
        if schema not in {FIGURE_DELIVERY_SCHEMA, FIGURE_BUILD_SCHEMA}:
            checks.append(check(
                "ERROR", "FIGURE_MANIFEST_SCHEMA",
                f"{figure_id}: got {schema}; expected figure delivery/build schema",
                file=row.get("source_manifest"),
            ))
            continue
        outputs = _figure_manifest_outputs(doc)
        output_hashes = [
            normalize_sha256(item.get("sha256"))
            for item in outputs if isinstance(item, dict)
        ]
        output_hashes = [value for value in output_hashes if value]
        if not output_hashes:
            checks.append(check(
                "ERROR", "FIGURE_OUTPUT_HASH_UNDECLARED",
                f"{figure_id}: source manifest does not declare output SHA-256",
                file=row.get("source_manifest"),
            ))
        elif actual_hash not in output_hashes:
            checks.append(check(
                "ERROR", "FIGURE_OUTPUT_HASH_MISMATCH",
                f"{figure_id}: embedded file hash is absent from source manifest outputs",
                file=row.get("target"),
                actual_sha256=actual_hash,
                declared_sha256=output_hashes,
            ))
        if schema != FIGURE_DELIVERY_SCHEMA:
            continue
        spec = doc.get("spec") or {}
        build = doc.get("build") or {}
        spec_figure_id = spec.get("figure_id")
        if spec_figure_id != figure_id:
            checks.append(check(
                "ERROR", "FIGURE_ID_MISMATCH",
                f"typesetting row id={figure_id}; figure delivery spec.figure_id={spec_figure_id}",
                file=row.get("source_manifest"),
            ))
        if not spec.get("empirical"):
            continue
        evidence = spec.get("evidence_binding") or {}
        if evidence.get("binding_status") != "CONFIRMED":
            checks.append(check(
                "ERROR", "FIGURE_EVIDENCE_UNCONFIRMED",
                f"{figure_id}: empirical figure evidence_binding is not CONFIRMED",
                file=row.get("source_manifest"),
            ))
        if evidence.get("owner_skill") != "RESULT-ANALYSIS":
            checks.append(check(
                "ERROR", "FIGURE_EVIDENCE_OWNER",
                f"{figure_id}: evidence owner must be RESULT-ANALYSIS",
                file=row.get("source_manifest"),
            ))
        if evidence.get("claim_id") != spec.get("claim_id"):
            checks.append(check(
                "ERROR", "FIGURE_EVIDENCE_CLAIM",
                f"{figure_id}: evidence claim_id does not match figure claim_id",
                file=row.get("source_manifest"),
            ))
        for field in ("result_card_sha256", "evidence_strength_sha256"):
            if not normalize_sha256(evidence.get(field)):
                checks.append(check(
                    "ERROR", "FIGURE_EVIDENCE_HASH",
                    f"{figure_id}: evidence_binding.{field} is missing a real SHA-256",
                    file=row.get("source_manifest"),
                ))
        result_card_hash = normalize_sha256(
            ((build.get("inputs") or {}).get("result_card") or {}).get("sha256")
        )
        evidence_result_hash = normalize_sha256(evidence.get("result_card_sha256"))
        if result_card_hash and evidence_result_hash and result_card_hash != evidence_result_hash:
            checks.append(check(
                "ERROR", "FIGURE_RESULT_CARD_HASH_MISMATCH",
                f"{figure_id}: build.inputs.result_card.sha256 != evidence_binding.result_card_sha256",
                file=row.get("source_manifest"),
            ))
    return checks


def _read_json_list(path: pathlib.Path) -> list[Any] | None:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else None


def _citation_delivery_checks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    delivery = snapshot.get("citation_delivery")
    if not isinstance(delivery, dict):
        return checks
    delivery_path = snapshot.get("citation_delivery_path")
    if delivery.get("producer") != "citation":
        checks.append(check(
            "ERROR", "CITATION_DELIVERY_PRODUCER",
            f"citation delivery producer must be citation, got {delivery.get('producer')}",
            file=delivery_path,
        ))
    if delivery.get("status") != "DELIVERED":
        checks.append(check(
            "ERROR", "CITATION_DELIVERY_STATUS",
            f"citation delivery must be DELIVERED before typesetting, got {delivery.get('status')}",
            file=delivery_path,
        ))
    deliverables = delivery.get("deliverables") or {}
    declared_hashes = delivery.get("deliverable_hashes") or {}
    if not isinstance(deliverables, dict) or not isinstance(declared_hashes, dict):
        checks.append(check(
            "ERROR", "CITATION_DELIVERY_CONTRACT",
            "citation delivery must declare deliverables and deliverable_hashes",
            file=delivery_path,
        ))
        return checks
    citation_dir = pathlib.Path(snapshot.get("citation_delivery_dir") or ".")
    required_roles = ("bibtex", "citekey_audit", "failures", "claim_review")
    for role in required_roles:
        name = deliverables.get(role)
        if not name:
            checks.append(check(
                "ERROR", "CITATION_DELIVERABLE_UNDECLARED",
                f"citation delivery lacks {role}",
                file=delivery_path,
            ))
            continue
        path = resolve_declared_child(citation_dir, name)
        if path is None:
            checks.append(check(
                "ERROR", "CITATION_DELIVERABLE_ESCAPES",
                f"{role}: declared path must stay inside the citation delivery directory",
                file=delivery_path,
            ))
            continue
        if not path.is_file():
            checks.append(check(
                "ERROR", "CITATION_DELIVERABLE_MISSING",
                f"{role}: {path}",
                file=delivery_path,
            ))
            continue
        actual = sha256_file_prefixed(path)
        declared = normalize_sha256(declared_hashes.get(role))
        if not declared:
            checks.append(check(
                "ERROR", "CITATION_DELIVERABLE_HASH_UNDECLARED",
                f"{role}: citation delivery lacks a real SHA-256",
                file=delivery_path,
            ))
        elif declared != actual:
            checks.append(check(
                "ERROR", "CITATION_DELIVERABLE_HASH_MISMATCH",
                f"{role}: citation delivery hash does not match the file on disk",
                file=str(path),
                declared_sha256=declared,
                actual_sha256=actual,
            ))
    consume = set((delivery.get("typesetting_contract") or {}).get("consume") or [])
    expected = {deliverables.get("bibtex"), deliverables.get("citekey_audit")}
    if not expected.issubset(consume):
        checks.append(check(
            "ERROR", "CITATION_TYPESETTING_CONTRACT",
            "typesetting_contract.consume must include the BibTeX and citekey audit deliverables",
            file=delivery_path,
        ))
    failures_name = deliverables.get("failures")
    if failures_name:
        failures_path = resolve_declared_child(citation_dir, failures_name)
        if failures_path is not None and failures_path.is_file():
            try:
                failures = _read_json_list(failures_path)
                if failures is None:
                    checks.append(check(
                        "ERROR", "CITATION_FAILURES_SCHEMA",
                        "citation failures deliverable must be a JSON list",
                        file=str(failures_path),
                    ))
                elif failures:
                    checks.append(check(
                        "ERROR", "CITATION_FAILURES_PRESENT",
                        f"citation delivery contains {len(failures)} unresolved/failed work rows",
                        file=str(failures_path),
                    ))
            except json.JSONDecodeError as exc:
                checks.append(check(
                    "ERROR", "CITATION_FAILURES_JSON",
                    f"{failures_path}: {exc}", file=str(failures_path),
                ))
    review_name = deliverables.get("claim_review")
    if review_name:
        review_path = resolve_declared_child(citation_dir, review_name)
        if review_path is not None and review_path.is_file():
            try:
                review = _read_json_list(review_path)
                if review is None:
                    checks.append(check(
                        "ERROR", "CITATION_CLAIM_REVIEW_SCHEMA",
                        "claim review deliverable must be a JSON list",
                        file=str(review_path),
                    ))
                elif review:
                    checks.append(check(
                        "ERROR", "CITATION_CLAIM_REVIEW_OPEN",
                        f"citation delivery contains {len(review)} non-supporting or unreviewed claim edges",
                        file=str(review_path),
                    ))
            except json.JSONDecodeError as exc:
                checks.append(check(
                    "ERROR", "CITATION_CLAIM_REVIEW_JSON",
                    f"{review_path}: {exc}", file=str(review_path),
                ))
    return checks


def preflight(snapshot: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    checks = list(snapshot.get("errors") or [])
    entrypoint: pathlib.Path = snapshot["entrypoint"]
    tex_files, include_checks = _tex_closure(entrypoint)
    checks.extend(include_checks)
    combined = ""
    labels: list[str] = []
    refs: list[str] = []
    packages: set[str] = set()
    graphics = []
    for path in tex_files:
        text = cd.strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        combined += "\n" + text
        labels.extend(_LABEL.findall(text))
        refs.extend(_REF.findall(text))
        for match in _PACKAGE.finditer(text):
            packages.update(part.strip() for part in match.group(1).split(","))
        for raw in _GRAPHIC.findall(text):
            resolved = _graphic_exists(path.parent, raw)
            graphics.append({"declared": raw, "resolved": str(resolved) if resolved else None,
                             "from": str(path)})
            if not resolved:
                checks.append(check("ERROR", "GRAPHIC_PATH_MISSING", raw, file=str(path)))
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    missing_refs = sorted(set(refs) - set(labels))
    if duplicate_labels:
        checks.append(check("ERROR", "DUPLICATE_LABEL", ", ".join(duplicate_labels)))
    if missing_refs:
        checks.append(check("ERROR", "MISSING_LABEL", ", ".join(missing_refs)))

    detected_engine = cd.detect_engine(combined)
    detected_backend = cd.detect_backend(combined)
    rules = profile.get("rules") or {}
    requested_engine = rules.get("engine", "auto")
    requested_backend = rules.get("bibliography_backend", "auto")
    if (requested_engine != "auto" and detected_engine["engine"] in ("xelatex", "lualatex")
            and requested_engine != detected_engine["engine"]):
        checks.append(check(
            "ERROR", "ENGINE_MISMATCH",
            f"profile={requested_engine}, source requires {detected_engine['engine']}: "
            f"{detected_engine['reason']}",
            file=str(entrypoint),
        ))
    if detected_backend["backend"] == "conflict":
        checks.append(check("ERROR", "BIB_BACKEND_CONFLICT", detected_backend["reason"]))
    if requested_backend != "auto" and requested_backend != detected_backend["backend"]:
        checks.append(check(
            "ERROR", "BIB_BACKEND_MISMATCH",
            f"profile={requested_backend}, source={detected_backend['backend']}",
            file=str(entrypoint),
        ))

    bib_path: pathlib.Path = snapshot.get("bib_target")
    live_audit = None
    if entrypoint.is_file() and bib_path and bib_path.is_file():
        if cka is None:
            checks.append(check("UNAVAILABLE", "CITEKEY_AUDITOR_UNAVAILABLE",
                                "light-citation citekey_audit import failed"))
        else:
            live_audit = cka.audit(combined, bib_path.read_text(encoding="utf-8", errors="replace"))
            if live_audit.get("missing_keys"):
                checks.append(check("ERROR", "CITEKEY_MISSING",
                                    ", ".join(live_audit["missing_keys"]), file=str(entrypoint)))
            if live_audit.get("duplicate_bib_keys"):
                checks.append(check("ERROR", "CITEKEY_DUPLICATE",
                                    ", ".join(live_audit["duplicate_bib_keys"]), file=str(bib_path)))
    supplied_audit = snapshot.get("citation_audit")
    if supplied_audit is None:
        checks.append(check("ERROR", "CITEKEY_AUDIT_NOT_CONSUMED",
                            "citation delivery did not provide a readable audit"))
    else:
        checks.append(check(
            "PASS" if supplied_audit.get("ok") else "ERROR",
            "CITATION_DELIVERY_AUDIT",
            f"consumed citation citekey-audit ok={supplied_audit.get('ok')}",
        ))

    kpsewhich = shutil.which("kpsewhich")
    package_probe = []
    if kpsewhich:
        for package in sorted(packages):
            try:
                proc = subprocess.run(
                    [kpsewhich, f"{package}.sty"], capture_output=True, text=True,
                    timeout=10, encoding="utf-8", errors="replace",
                )
                found = proc.returncode == 0 and bool((proc.stdout or "").strip())
                package_probe.append({"package": package, "available": found})
                if not found:
                    checks.append(check("UNAVAILABLE", "LATEX_PACKAGE_UNAVAILABLE", package))
            except subprocess.TimeoutExpired:
                checks.append(check("UNAVAILABLE", "PACKAGE_PROBE_TIMEOUT", package))
    else:
        checks.append(check("SKIP", "PACKAGE_PROBE_UNAVAILABLE",
                            "kpsewhich not found; compile remains the authoritative check"))

    doc = _DOC_CLASS.search(combined)
    required_class = rules.get("required_documentclass")
    actual_class = doc.group(1) if doc else None
    if required_class and required_class != actual_class:
        checks.append(check("ERROR", "TEMPLATE_CLASS",
                            f"profile={required_class}, source={actual_class}"))
    required_packages = set(rules.get("required_packages") or [])
    for package in sorted(required_packages - packages):
        checks.append(check("ERROR", "REQUIRED_PACKAGE", package))

    figure_checks, figure_measurements = _dimension_checks(snapshot)
    checks.extend(figure_checks)
    checks.extend(_figure_manifest_checks(snapshot))
    checks.extend(_citation_delivery_checks(snapshot))

    status = "PASS"
    if any(item["status"] == "ERROR" for item in checks):
        status = "ERROR"
    elif any(item["status"] == "UNAVAILABLE" for item in checks):
        status = "UNAVAILABLE"
    return {
        "status": status, "checks": checks, "tex_files": [str(path) for path in tex_files],
        "graphics": graphics, "labels": sorted(set(labels)), "refs": sorted(set(refs)),
        "figure_measurements": figure_measurements,
        "packages": sorted(packages), "package_probe": package_probe,
        "engine": {"detected": detected_engine, "requested": requested_engine},
        "bibliography_backend": {"detected": detected_backend, "requested": requested_backend},
        "citation_delivery_audit": supplied_audit, "live_citekey_audit": live_audit,
    }


def build(spec_path: str, outdir: str | None = None, preflight_only: bool = False) -> dict[str, Any]:
    spec_file = pathlib.Path(spec_path).resolve()
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    if spec.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"input schema must be {INPUT_SCHEMA}")
    output = pathlib.Path(outdir or spec.get("output_dir") or "typesetting-build")
    if not output.is_absolute():
        output = (spec_file.parent / output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            f"output_dir must be new or empty to prevent stale build reuse: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    source_root = output / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    profile, profile_prov = _profile(spec, spec_file.parent)
    snapshot = snapshot_inputs(spec, spec_file.parent, source_root)
    inputs = [provenance(spec_file, "typesetting.input_spec", None), profile_prov] + snapshot["inputs"]
    pf = preflight(snapshot, profile)

    compile_out = output / "compile"
    rules = profile.get("rules") or {}
    if pf["status"] == "ERROR":
        compile_result = {
            "schema": cd.SCHEMA, "producer": "typesetting", "stage": 11,
            "generated_at": now(), "status": "ERROR",
            "reason": "preflight_blocked", "manuscript": str(snapshot["entrypoint"]),
            "diagnostics": [item for item in pf["checks"] if item["status"] == "ERROR"],
            "pdf": None, "log": None,
        }
    elif pf["status"] == "UNAVAILABLE":
        compile_result = {
            "schema": cd.SCHEMA, "producer": "typesetting", "stage": 11,
            "generated_at": now(), "status": "UNAVAILABLE",
            "reason": "preflight_resource_unavailable", "manuscript": str(snapshot["entrypoint"]),
            "diagnostics": [item for item in pf["checks"] if item["status"] == "UNAVAILABLE"],
            "pdf": None, "log": None,
        }
    elif preflight_only:
        compile_result = {
            "schema": cd.SCHEMA, "producer": "typesetting", "stage": 11,
            "generated_at": now(), "status": "UNAVAILABLE",
            "reason": "preflight_only_not_compiled", "manuscript": str(snapshot["entrypoint"]),
            "diagnostics": [], "pdf": None, "log": None,
        }
    else:
        compile_result = cd.compile_tex(
            str(snapshot["entrypoint"]),
            engine=rules.get("engine", "auto"),
            backend=rules.get("bibliography_backend", "auto"),
            tool=rules.get("compile_tool", "auto"),
            outdir=str(compile_out),
            timeout=int(rules.get("compile_timeout_seconds") or 300),
        )
    write_json(output / "compile-report.json", compile_result)

    pdf_path = (compile_result.get("pdf") or {}).get("path")
    compliance = sc.audit(
        str(snapshot["entrypoint"]) if snapshot["entrypoint"].is_file() else None,
        pdf_path,
        rules,
    )
    write_json(output / "compliance-report.json", compliance)
    critical = compliance["critical_count"]
    compliance_unavailable = compliance.get("status") == "UNAVAILABLE"
    delivered = (
        compile_result["status"] == "PASS"
        and critical == 0
        and not compliance_unavailable
    )
    overall = (
        "DELIVERED" if delivered else
        "FAILED" if pf["status"] == "ERROR"
                    or compile_result["status"] in ("ERROR", "UNRESOLVED")
                    or compliance.get("status") == "ERROR" else
        "UNAVAILABLE"
    )
    failure_path = None
    if not delivered:
        failure = {
            "schema": "light.typesetting_failure.v1", "producer": "typesetting",
            "stage": 11, "generated_at": now(), "status": overall,
            "compile_status": compile_result["status"],
            "compile_reason": compile_result.get("reason"),
            "compliance_status": compliance.get("status"),
            "preflight_blockers": [item for item in pf["checks"]
                                   if item["status"] in ("ERROR", "UNAVAILABLE")],
            "desk_reject_critical": [item for item in compliance["findings"]
                                     if item["severity"] == "high"],
            "repair_scope": "stage 11 only; ROUTES has no key 11",
        }
        failure_path = output / "failure.json"
        write_json(failure_path, failure)

    pdf_info = compliance.get("pdf_inspection") or {}
    venue_handoff = {
        "schema": "light.typesetting_venue_handoff.v1",
        "producer": "typesetting", "consumer": "venue-matching", "stage": 11,
        "status": overall, "pdf": pdf_path,
        "pdf_sha256": (compile_result.get("pdf") or {}).get("sha256"),
        "pages": pdf_info.get("pages"),
        "page_size": pdf_info.get("page_size"),
        "profile_name": profile.get("name"),
        "profile_source": profile.get("source"),
        "compliance_report": str(output / "compliance-report.json"),
        "compliance_status": compliance.get("status"),
        "critical_count": critical,
        "boundary": compliance["boundary"],
    }
    write_json(output / "venue-handoff.json", venue_handoff)

    artifacts = {
        "source_snapshot": str(source_root),
        "compile_report": str(output / "compile-report.json"),
        "compile_log": (compile_result.get("log") or {}).get("path"),
        "compliance_report": str(output / "compliance-report.json"),
        "pdf": pdf_path,
        "failure": str(failure_path) if failure_path else None,
        "venue_handoff": str(output / "venue-handoff.json"),
    }
    manifest = {
        "schema": MANIFEST_SCHEMA, "producer": "typesetting", "stage": 11,
        "project": spec.get("project") or "unnamed", "generated_at": now(),
        "input_spec": str(spec_file), "inputs": inputs, "profile": profile,
        "snapshot": {
            "entrypoint": str(snapshot["entrypoint"]),
            "figures": snapshot.get("figures") or [],
            "citation_contract": (snapshot.get("citation_delivery") or {}).get("typesetting_contract"),
            "citation_delivery_status": (snapshot.get("citation_delivery") or {}).get("status"),
            "citation_delivery_hashes": (snapshot.get("citation_delivery") or {}).get("deliverable_hashes"),
            "citation_delivery_snapshot": snapshot.get("citation_delivery_snapshot"),
            "citation_sidecar_snapshots": snapshot.get("citation_sidecar_snapshots") or {},
        },
        "preflight": pf, "compile": compile_result, "compliance": compliance,
        "status": overall, "artifacts": artifacts,
    }
    write_json(output / "build-manifest.json", manifest)
    delivery = {
        "schema": DELIVERY_SCHEMA, "producer": "typesetting", "stage": 11,
        "generated_at": now(), "project": manifest["project"], "status": overall,
        "build_manifest": str(output / "build-manifest.json"),
        "compile_report": artifacts["compile_report"],
        "compile_log": artifacts["compile_log"],
        "compliance_report": artifacts["compliance_report"],
        "pdf": artifacts["pdf"], "failure": artifacts["failure"],
        "venue_handoff": artifacts["venue_handoff"],
        "consumer_contract": {
            "venue-matching": ["pdf", "pages", "page_size", "compliance_report",
                               "profile_name", "profile_source"],
        },
    }
    write_json(output / "delivery.json", delivery)
    return {
        "status": overall, "exit_code": 0 if delivered or overall == "UNAVAILABLE" else 1,
        "output_dir": str(output), "manifest": manifest, "delivery": delivery,
    }


def render(result: dict[str, Any]) -> str:
    manifest = result["manifest"]
    compile_result = manifest["compile"]
    return "\n".join([
        f"# Typesetting build — {result['status']}",
        "",
        f"- preflight: `{manifest['preflight']['status']}`",
        f"- compile: `{compile_result['status']}` ({compile_result.get('reason')})",
        f"- command: `{compile_result.get('command_shell') or 'not run'}`",
        f"- PDF: `{manifest['artifacts']['pdf'] or 'none'}`",
        f"- compliance critical: `{manifest['compliance']['critical_count']}`",
        f"- delivery: `{result['delivery']['build_manifest']}`",
    ])


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        (root / "paper.tex").write_text(
            "\\documentclass{article}\\usepackage{graphicx}\\usepackage{fontspec}\\begin{document}"
            "\\includegraphics{figures/result.pdf}\\includegraphics{missing}"
            "\\cite{x}\\bibliography{references}\\end{document}",
            encoding="utf-8",
        )
        figure_dir = root / "figure-delivery"
        figure_dir.mkdir()
        figure_path = figure_dir / "result.pdf"
        figure_path.write_bytes(b"%PDF-1.4\n% selftest figure bytes\n")
        figure_hash = sha256_file_prefixed(figure_path)
        evidence_hash = "sha256:" + "a" * 64
        figure_delivery = {
            "schema": FIGURE_DELIVERY_SCHEMA,
            "spec": {
                "figure_id": "F1", "claim_id": "C1", "reader_task": "selftest",
                "medium": "paper", "generation_method": "PROGRAMMATIC_DATA",
                "required_engine": "R", "empirical": True,
                "data_semantics": {"variable_type": "nominal", "palette_type": "qualitative"},
                "uncertainty": {"displayed": False},
                "caption_facts": {"n": 1, "analysis_set": "selftest"},
                "evidence_binding": {
                    "result_card_id": "RC1",
                    "result_card_locator": "result-card.json#C1",
                    "result_card_sha256": evidence_hash,
                    "evidence_strength_locator": "evidence-strength.json#C1",
                    "evidence_strength_sha256": evidence_hash,
                    "claim_id": "C1",
                    "owner_skill": "RESULT-ANALYSIS",
                    "binding_status": "CONFIRMED",
                },
            },
            "build": {
                "schema": FIGURE_BUILD_SCHEMA,
                "engine": "R/ggplot2",
                "inputs": {"result_card": {"sha256": evidence_hash}},
                "outputs": [{"format": "pdf", "path": str(figure_path), "sha256": figure_hash}],
            },
        }
        write_json(figure_dir / "manifest.json", figure_delivery)
        bad_figure_delivery = json.loads(json.dumps(figure_delivery))
        bad_figure_delivery["build"]["outputs"][0]["sha256"] = "sha256:" + "b" * 64
        write_json(figure_dir / "manifest-bad.json", bad_figure_delivery)
        delivery_dir = root / "citation"
        delivery_dir.mkdir()
        (delivery_dir / "references.bib").write_text("@article{x,title={X}}\n", encoding="utf-8")
        write_json(delivery_dir / "citekey-audit.json", {
            "n_cited": 1, "n_bib": 1, "missing_keys": [], "uncited_keys": [],
            "duplicate_bib_keys": [], "naming_violations": [], "ok": True,
        })
        write_json(delivery_dir / "citation-failures.json", [])
        write_json(delivery_dir / "claim-citation-review.json", [])
        citation_deliverables = {
            "bibtex": "references.bib",
            "citekey_audit": "citekey-audit.json",
            "failures": "citation-failures.json",
            "claim_review": "claim-citation-review.json",
        }
        citation_hashes = {
            role: sha256_file_prefixed(delivery_dir / name)
            for role, name in citation_deliverables.items()
        }
        write_json(delivery_dir / "delivery.json", {
            "schema": CITATION_DELIVERY_SCHEMA,
            "producer": "citation",
            "status": "DELIVERED",
            "deliverables": citation_deliverables,
            "deliverable_hashes": citation_hashes,
            "typesetting_contract": {"consume": ["references.bib", "citekey-audit.json"]},
        })
        bad_hashes = dict(citation_hashes)
        bad_hashes["bibtex"] = "sha256:" + "c" * 64
        write_json(delivery_dir / "delivery-bad-hash.json", {
            "schema": CITATION_DELIVERY_SCHEMA,
            "producer": "citation",
            "status": "DELIVERED",
            "deliverables": citation_deliverables,
            "deliverable_hashes": bad_hashes,
            "typesetting_contract": {"consume": ["references.bib", "citekey-audit.json"]},
        })
        spec = {
            "schema": INPUT_SCHEMA, "project": "selftest",
            "manuscript": {"path": "paper.tex"},
            "figures": [{
                "id": "F1",
                "path": "figure-delivery/result.pdf",
                "target": "figures/result.pdf",
                "source_manifest": "figure-delivery/manifest.json",
            }],
            "citation": {"delivery": "citation/delivery.json"},
            "venue_profile": {
                "schema": PROFILE_SCHEMA, "name": "selftest",
                "source": {"kind": "user_input", "checked_at": "2026-07-03"},
                "rules": {"engine": "pdflatex", "bibliography_backend": "biber"},
            },
            "output_dir": "out",
        }
        write_json(root / "spec.json", spec)
        result = build(str(root / "spec.json"), preflight_only=True)
        codes = {item["code"] for item in result["manifest"]["preflight"]["checks"]}
        assert "GRAPHIC_PATH_MISSING" in codes
        assert "ENGINE_MISMATCH" in codes
        assert "BIB_BACKEND_MISMATCH" in codes
        assert "FIGURE_OUTPUT_HASH_MISMATCH" not in codes
        assert result["manifest"]["snapshot"]["figures"][0]["source_manifest_schema"] == FIGURE_DELIVERY_SCHEMA
        assert result["manifest"]["snapshot"]["citation_contract"]["consume"]
        assert result["manifest"]["snapshot"]["citation_delivery_status"] == "DELIVERED"
        sidecars = result["manifest"]["snapshot"]["citation_sidecar_snapshots"]
        assert {"citekey_audit", "failures", "claim_review"}.issubset(sidecars), sidecars
        assert all(pathlib.Path(path).is_file() for path in sidecars.values()), sidecars
        input_roles = {row["role"] for row in result["manifest"]["inputs"]}
        assert {"citation.failures", "citation.claim_review"}.issubset(input_roles), input_roles
        assert result["status"] == "FAILED" and result["exit_code"] == 1
        bad_spec = json.loads(json.dumps(spec))
        bad_spec["figures"][0]["source_manifest"] = "figure-delivery/manifest-bad.json"
        bad_spec["output_dir"] = "out-bad-figure"
        write_json(root / "spec-bad-figure.json", bad_spec)
        bad_result = build(str(root / "spec-bad-figure.json"), preflight_only=True)
        bad_codes = {item["code"] for item in bad_result["manifest"]["preflight"]["checks"]}
        assert "FIGURE_OUTPUT_HASH_MISMATCH" in bad_codes
        bad_citation_spec = json.loads(json.dumps(spec))
        bad_citation_spec["citation"]["delivery"] = "citation/delivery-bad-hash.json"
        bad_citation_spec["output_dir"] = "out-bad-citation"
        write_json(root / "spec-bad-citation.json", bad_citation_spec)
        bad_citation = build(str(root / "spec-bad-citation.json"), preflight_only=True)
        bad_citation_codes = {item["code"] for item in bad_citation["manifest"]["preflight"]["checks"]}
        assert "CITATION_DELIVERABLE_HASH_MISMATCH" in bad_citation_codes
        escape_delivery = json.loads((delivery_dir / "delivery.json").read_text(encoding="utf-8"))
        escape_delivery["deliverables"]["bibtex"] = "../outside.bib"
        write_json(delivery_dir / "delivery-escape.json", escape_delivery)
        escape_spec = json.loads(json.dumps(spec))
        escape_spec["citation"]["delivery"] = "citation/delivery-escape.json"
        escape_spec["output_dir"] = "out-escape-citation"
        write_json(root / "spec-escape-citation.json", escape_spec)
        escape_result = build(str(root / "spec-escape-citation.json"), preflight_only=True)
        escape_codes = {item["code"] for item in escape_result["manifest"]["preflight"]["checks"]}
        assert "CITATION_DELIVERABLE_ESCAPES" in escape_codes
        try:
            build(str(root / "spec.json"), preflight_only=True)
            raise AssertionError("non-empty output directory must be rejected")
        except ValueError as exc:
            assert "new or empty" in str(exc)
    print("[selftest] PASS build_submission: snapshot/provenance/handoff hashes/citation/profile/preflight")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canonical stage-11 submission bundle")
    parser.add_argument("--spec")
    parser.add_argument("--outdir")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec:
        parser.error("--spec is required")
    try:
        result = build(args.spec, args.outdir, args.preflight_only)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[build_submission] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["delivery"], ensure_ascii=False, indent=2) if args.json else render(result))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
