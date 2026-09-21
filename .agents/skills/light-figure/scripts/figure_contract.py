#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate figure intent against an R/Python build manifest and caption facts."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.figure_delivery.v1"
BUILD_SCHEMA = "light.figure_build.v1"
PALETTES = {"qualitative", "sequential", "diverging", "none"}
VARIABLE_TYPES = {"nominal", "ordinal", "continuous", "binary"}
ENGINES = {"R", "PYTHON", "EITHER"}
EVIDENCE_BINDING_STATUSES = {"CONFIRMED", "UNRESOLVED", "MISSING"}
GUARDRAIL_STATUSES = {"PASS", "WARN", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
BLOCKING_GUARDRAILS = {"FAIL", "UNKNOWN"}
_PLACEHOLDER_RE = re.compile(
    r"(\{\{|\}\}|^<[^>]+>$|^replace-with|^(unknown|待核查|tbd|todo|n/?a|none|\?)$)",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _hash(value: Any) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _is_placeholder(value: object) -> bool:
    return isinstance(value, str) and bool(_PLACEHOLDER_RE.search(value.strip()))


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or _is_placeholder(text) or "://" in text:
        return False
    if _WINDOWS_DRIVE_RE.match(text) or text.startswith(("/", "\\", "~")):
        return False
    parts = text.replace("\\", "/").split("/")
    return ".." not in parts


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder(value)


def _e2e_tmp_root() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve()
    while root != root.parent and not (root / "_shared" / "__init__.py").exists():
        root = root.parent
    tmp = root / ".upgrade" / "_e2e"
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def evaluate(doc: dict[str, Any], *, base_dir: str | pathlib.Path | None = None) -> dict[str, Any]:
    if doc.get("schema") != SCHEMA_ID:
        raise ValueError(f"schema 必须为 {SCHEMA_ID}")
    spec, build = doc.get("spec"), doc.get("build")
    if not isinstance(spec, dict) or not isinstance(build, dict):
        raise ValueError("spec/build 类型错误")
    issues: list[dict[str, str]] = []
    artifact_base = pathlib.Path(base_dir or ".").resolve()

    def add(code: str, message: str, severity: str = "error") -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    def verify_artifact(row: dict[str, Any], label: str, *, require_path: bool) -> None:
        raw_path = row.get("path")
        declared = str(row.get("sha256") or "")
        if raw_path in (None, ""):
            if require_path:
                add("ARTIFACT_PATH_GAP", f"{label}.path 缺失；不能只写 hash 而不交付真实文件")
            return
        if not _is_safe_relative_path(raw_path):
            add(
                "ARTIFACT_PATH_UNSAFE",
                f"{label}.path 必须是交付包内相对路径，不能是占位符、绝对路径、URL 或 .. 越界路径",
            )
            return
        candidate = (artifact_base / str(raw_path)).resolve()
        try:
            candidate.relative_to(artifact_base)
        except ValueError:
            add("ARTIFACT_PATH_UNSAFE", f"{label}.path 解析后逃出交付包目录")
            return
        if not candidate.is_file():
            add("ARTIFACT_FILE_MISSING", f"{label}.path 指向的文件不存在：{raw_path}")
            return
        if _hash(declared):
            actual = _file_hash(candidate)
            if actual.lower() != declared.lower():
                add(
                    "ARTIFACT_HASH_MISMATCH",
                    f"{label}.sha256 与真实文件不一致：declared={declared[:19]}… actual={actual[:19]}…",
                )

    for field in ("figure_id", "claim_id", "reader_task", "medium"):
        if not spec.get(field):
            add("SPEC_GAP", f"spec.{field} 缺失")
    if spec.get("generation_method") not in {"PROGRAMMATIC_DATA", "PROGRAMMATIC_DIAGRAM"}:
        add(
            "NON_PROGRAMMATIC_FIGURE",
            "科研图必须由程序化数据/图解路径生成；生成式图片不可进入该 contract",
        )
    required_engine = spec.get("required_engine")
    if required_engine not in ENGINES:
        raise ValueError("required_engine 必须为 R/PYTHON/EITHER")
    engine = str(build.get("engine") or "")
    if required_engine == "R" and not engine.startswith("R/"):
        add("REQUIRED_R_NOT_USED", f"要求 R，但 build.engine={engine or 'missing'}")
    if required_engine == "PYTHON" and not engine.startswith("Python/"):
        add("REQUIRED_PYTHON_NOT_USED", f"要求 Python，但 build.engine={engine or 'missing'}")
    if build.get("degraded") and required_engine != "EITHER":
        add("ENGINE_DEGRADED", "指定引擎交付不得以 fallback 冒充完成")

    semantics = spec.get("data_semantics") or {}
    variable_type = semantics.get("variable_type")
    palette = semantics.get("palette_type")
    if variable_type not in VARIABLE_TYPES or palette not in PALETTES:
        raise ValueError("data_semantics.variable_type/palette_type 非法")
    if variable_type in {"nominal", "binary"} and palette not in {"qualitative", "none"}:
        add("PALETTE_SEMANTIC_MISMATCH", "无序类别不得使用 sequential/diverging palette")
    if variable_type in {"ordinal", "continuous"} and palette == "qualitative":
        add("PALETTE_SEMANTIC_MISMATCH", "有序/连续量不得使用 qualitative palette")
    if palette == "diverging":
        midpoint = semantics.get("midpoint")
        if not isinstance(midpoint, dict) or midpoint.get("value") is None or not midpoint.get("meaning"):
            add("DIVERGING_MIDPOINT_GAP", "diverging palette 必须有真实中点值与语义")

    size_encoding = spec.get("size_encoding")
    if isinstance(size_encoding, dict) and size_encoding.get("mark") in {"circle", "bubble"}:
        if size_encoding.get("quantity_mapping") == "radius":
            add(
                "AREA_PERCEPTION_MISMATCH",
                "圆形大小表达数量时按半径映射会造成面积非线性夸大；应按面积映射",
            )

    empirical = bool(spec.get("empirical"))
    uncertainty = spec.get("uncertainty")
    caption = spec.get("caption_facts") or {}
    evidence_binding = spec.get("evidence_binding") or {}
    if empirical:
        if caption.get("n") in (None, "", 0):
            add("CAPTION_FACT_GAP", "经验图 caption 缺正样本量/按 panel 样本量说明")
        if caption.get("analysis_set") in (None, ""):
            add("CAPTION_FACT_GAP", "经验图 caption 缺 analysis_set")
        if not isinstance(evidence_binding, dict) or not evidence_binding:
            add("EVIDENCE_BINDING_GAP", "经验图缺 evidence_binding；无法追到 result-analysis 的 result card")
        else:
            for field in (
                "result_card_id", "result_card_locator", "result_card_sha256",
                "evidence_strength_locator", "evidence_strength_sha256",
                "claim_id", "owner_skill", "binding_status",
            ):
                if evidence_binding.get(field) in (None, ""):
                    add("EVIDENCE_BINDING_GAP", f"evidence_binding.{field} 缺失")
            if evidence_binding.get("binding_status") not in EVIDENCE_BINDING_STATUSES:
                add("EVIDENCE_BINDING_STATUS_INVALID", "binding_status 必须为 CONFIRMED/UNRESOLVED/MISSING")
            elif evidence_binding.get("binding_status") != "CONFIRMED":
                add("EVIDENCE_BINDING_UNCONFIRMED", "经验图 evidence_binding 未 CONFIRMED，不能交付为论文主图")
            if evidence_binding.get("owner_skill") != "RESULT-ANALYSIS":
                add("EVIDENCE_OWNER_MISMATCH", "经验图 evidence_binding.owner_skill 必须为 RESULT-ANALYSIS")
            if evidence_binding.get("claim_id") != spec.get("claim_id"):
                add("EVIDENCE_CLAIM_MISMATCH", "figure spec.claim_id 与 evidence_binding.claim_id 不一致")
            for field in ("result_card_sha256", "evidence_strength_sha256"):
                if evidence_binding.get(field) and not _hash(evidence_binding.get(field)):
                    add("EVIDENCE_HASH_GAP", f"evidence_binding.{field} 缺真实格式 SHA-256")
        claim_context = spec.get("claim_context")
        if not isinstance(claim_context, dict) or not claim_context:
            add(
                "CLAIM_CONTEXT_GAP",
                "经验图缺 claim_context；无法证明 figure 消费了 paper-writing 的 claim plan/guardrail limitation",
            )
        else:
            if not _nonempty(claim_context.get("paper_claim_plan_locator")):
                add("CLAIM_CONTEXT_GAP", "claim_context.paper_claim_plan_locator 缺失或为占位符")
            elif not _is_safe_relative_path(claim_context.get("paper_claim_plan_locator")):
                add(
                    "CLAIM_CONTEXT_LOCATOR_UNSAFE",
                    "claim_context.paper_claim_plan_locator 必须是交付包内相对 locator",
                )
            if not _hash(claim_context.get("paper_claim_plan_sha256")):
                add("CLAIM_CONTEXT_HASH_GAP", "claim_context.paper_claim_plan_sha256 缺真实格式 SHA-256")
            if claim_context.get("claim_id") != spec.get("claim_id"):
                add("CLAIM_CONTEXT_CLAIM_MISMATCH", "claim_context.claim_id 与 spec.claim_id 不一致")
            if (
                _hash(claim_context.get("result_card_sha256"))
                and _hash(evidence_binding.get("result_card_sha256"))
                and claim_context.get("result_card_sha256") != evidence_binding.get("result_card_sha256")
            ):
                add("CLAIM_CONTEXT_RESULT_CARD_MISMATCH", "claim_context.result_card_sha256 与 evidence_binding.result_card_sha256 不一致")
            elif not _hash(claim_context.get("result_card_sha256")):
                add("CLAIM_CONTEXT_RESULT_CARD_HASH_GAP", "claim_context.result_card_sha256 缺真实格式 SHA-256")
            guardrail_status = str(claim_context.get("guardrail_status") or "").upper()
            if guardrail_status not in GUARDRAIL_STATUSES:
                add("CLAIM_CONTEXT_GUARDRAIL_STATUS_INVALID", "claim_context.guardrail_status 必须为 PASS/WARN/FAIL/UNKNOWN/NOT_APPLICABLE")
            elif guardrail_status in BLOCKING_GUARDRAILS:
                add("CLAIM_CONTEXT_GUARDRAIL_BLOCKS_FIGURE", f"guardrail_status={guardrail_status}；不得作为论文图支持 ready claim")
            if guardrail_status == "NOT_APPLICABLE" and not _nonempty(claim_context.get("not_applicable_rationale")):
                add("CLAIM_CONTEXT_GUARDRAIL_NA_RATIONALE_GAP", "guardrail_status=NOT_APPLICABLE 但缺不适用理由")
            if guardrail_status != "NOT_APPLICABLE" and not _nonempty(claim_context.get("claim_impact")):
                add("CLAIM_CONTEXT_CLAIM_IMPACT_GAP", "claim_context 缺 guardrail claim_impact；caption 无法继承写作限制")
            caption_reflects = claim_context.get("caption_reflects_claim_impact")
            if guardrail_status == "WARN":
                caption_impact = caption.get("guardrail_claim_impact")
                if caption_reflects is not True or not _nonempty(caption_impact):
                    add(
                        "CLAIM_CONTEXT_WARN_NOT_IN_CAPTION",
                        "guardrail WARN 必须在 caption_facts.guardrail_claim_impact 中显式反映 claim_impact",
                    )
    if isinstance(uncertainty, dict) and uncertainty.get("displayed"):
        for field in ("kind", "level", "method"):
            if not uncertainty.get(field):
                add("UNCERTAINTY_UNDEFINED", f"uncertainty.{field} 缺失")
        if not caption.get("uncertainty_definition"):
            add("CAPTION_FACT_GAP", "误差/区间已显示，但 caption 未定义")

    physical = spec.get("final_physical_size") or {}
    for field in ("width_mm", "height_mm", "min_font_pt"):
        if not isinstance(physical.get(field), (int, float)) or physical[field] <= 0:
            add("PHYSICAL_SIZE_GAP", f"final_physical_size.{field} 缺正数")
    if build.get("schema") != BUILD_SCHEMA:
        add("BUILD_SCHEMA_INVALID", f"build.schema 必须为 {BUILD_SCHEMA}")
    for field in (
        "engine", "engine_version", "packages", "mapping", "stat_transforms",
        "scales", "coordinates", "facets", "theme", "device", "width_mm",
        "height_mm", "inputs", "outputs",
    ):
        if build.get(field) in (None, "", [], {}):
            add("BUILD_MANIFEST_GAP", f"build.{field} 缺失")
    if str(build.get("engine_version") or "").upper() == "UNKNOWN":
        add("ENGINE_VERSION_UNRESOLVED", "未记录实际执行引擎版本", "unresolved")
    packages = build.get("packages") or {}
    if isinstance(packages, dict) and any(
        str(version or "").upper() == "UNKNOWN" for version in packages.values()
    ):
        add("PACKAGE_VERSION_UNRESOLVED", "至少一个绘图包版本 UNKNOWN", "unresolved")
    if isinstance(physical.get("width_mm"), (int, float)) and isinstance(build.get("width_mm"), (int, float)):
        tolerance = float(physical.get("tolerance_mm", 0.5))
        if abs(float(physical["width_mm"]) - float(build["width_mm"])) > tolerance:
            add("PHYSICAL_WIDTH_MISMATCH", "build width 与最终物理宽度不符")
    if isinstance(physical.get("height_mm"), (int, float)) and isinstance(build.get("height_mm"), (int, float)):
        tolerance = float(physical.get("tolerance_mm", 0.5))
        if abs(float(physical["height_mm"]) - float(build["height_mm"])) > tolerance:
            add("PHYSICAL_HEIGHT_MISMATCH", "build height 与最终物理高度不符")
    base_font = (build.get("theme") or {}).get("base_font_pt")
    min_font = physical.get("min_font_pt")
    if isinstance(base_font, (int, float)) and isinstance(min_font, (int, float)) and base_font < min_font:
        add("FONT_TOO_SMALL_AT_FINAL_SIZE", f"build base font {base_font}pt < {min_font}pt")

    inputs = build.get("inputs") or {}
    input_roles = ["data", "code"]
    if empirical:
        input_roles.append("result_card")
    for role in input_roles:
        row = inputs.get(role)
        if not isinstance(row, dict) or not _hash(row.get("sha256")):
            add("BUILD_PROVENANCE_GAP", f"build.inputs.{role} 缺真实格式 SHA-256")
        elif isinstance(row, dict):
            verify_artifact(row, f"build.inputs.{role}", require_path=False)
    result_card_input = inputs.get("result_card") if isinstance(inputs, dict) else None
    if (
        empirical
        and isinstance(evidence_binding, dict)
        and isinstance(result_card_input, dict)
        and _hash(result_card_input.get("sha256"))
        and _hash(evidence_binding.get("result_card_sha256"))
        and result_card_input.get("sha256") != evidence_binding.get("result_card_sha256")
    ):
        add("RESULT_CARD_HASH_MISMATCH", "build.inputs.result_card.sha256 与 spec.evidence_binding.result_card_sha256 不一致")
    outputs = build.get("outputs") or []
    formats = set()
    for index, row in enumerate(outputs):
        if not isinstance(row, dict) or not _hash(row.get("sha256")):
            add("OUTPUT_PROVENANCE_GAP", f"build.outputs[{index}] 缺真实格式 SHA-256")
        else:
            verify_artifact(row, f"build.outputs[{index}]", require_path=True)
            formats.add(str(row.get("format") or "").lower())
    if not formats.intersection({"pdf", "svg"}):
        add("VECTOR_OUTPUT_MISSING", "终稿缺 PDF/SVG 矢量输出")
    if not formats.intersection({"png", "jpg", "jpeg"}):
        add("RASTER_PREVIEW_MISSING", "缺真实最终尺寸位图预览")

    accessibility = spec.get("accessibility") or {}
    if palette != "none":
        if accessibility.get("cvd_review") != "VERIFIED":
            add("CVD_REVIEW_UNRESOLVED", "未提供色觉缺陷模拟/复核证据", "unresolved")
        elif not _hash(accessibility.get("cvd_evidence_sha256")):
            add("CVD_EVIDENCE_GAP", "CVD review 标 VERIFIED 但缺证据 hash", "unresolved")
        if (
            accessibility.get("grayscale_review") != "VERIFIED"
            and not accessibility.get("redundant_encoding")
        ):
            add(
                "REDUNDANT_ENCODING_UNRESOLVED",
                "灰度复核未验证且无形状/线型/直接标签冗余编码",
                "unresolved",
            )
        elif (
            accessibility.get("grayscale_review") == "VERIFIED"
            and not _hash(accessibility.get("grayscale_evidence_sha256"))
        ):
            add(
                "GRAYSCALE_EVIDENCE_GAP",
                "grayscale review 标 VERIFIED 但缺证据 hash",
                "unresolved",
            )

    status = (
        "FAIL" if any(x["severity"] == "error" for x in issues)
        else "UNRESOLVED" if issues else "PASS"
    )
    return {
        "schema": "light.figure_contract_report.v1",
        "status": status,
        "figure_id": spec.get("figure_id"),
        "issues": issues,
        "honesty": (
            "本门核声明语义、caption、物理尺寸和 build provenance；"
            "PASS 不证明数据、统计、审美或人工视觉复核正确。"
        ),
    }


def _write_fixture(base_dir: pathlib.Path, name: str, payload: bytes) -> dict[str, str]:
    path = base_dir / name
    path.write_bytes(payload)
    return {"path": name, "sha256": _file_hash(path)}


def _base(base_dir: pathlib.Path) -> dict[str, Any]:
    data = _write_fixture(base_dir, "data.csv", b"group,estimate\nA,1.0\n")
    code = _write_fixture(base_dir, "plot.R", b"pdf('F1.pdf')\nplot(1,1)\ndev.off()\n")
    result_card = _write_fixture(base_dir, "result-card.json", b'{"claim_id":"C1"}\n')
    evidence = _write_fixture(base_dir, "evidence-strength.json", b'{"claims":[]}\n')
    claim_plan = _write_fixture(base_dir, "claim-plan.json", b'{"schema":"light.paper_claims.v1"}\n')
    pdf = _write_fixture(base_dir, "F1.pdf", b"%PDF-1.4\n%fixture\n")
    png = _write_fixture(base_dir, "F1.png", b"\x89PNG\r\n\x1a\nfixture\n")
    cvd = _write_fixture(base_dir, "cvd-review.txt", b"cvd ok\n")
    gray = _write_fixture(base_dir, "grayscale-review.txt", b"gray ok\n")
    return {
        "schema": SCHEMA_ID,
        "spec": {
            "figure_id": "F1", "claim_id": "C1", "reader_task": "compare groups",
            "medium": "paper", "generation_method": "PROGRAMMATIC_DATA",
            "required_engine": "R", "empirical": True,
            "data_semantics": {"variable_type": "nominal", "palette_type": "qualitative"},
            "uncertainty": {
                "displayed": True, "kind": "confidence_interval",
                "level": "95%", "method": "bootstrap",
            },
            "caption_facts": {
                "n": 100, "analysis_set": "held-out test",
                "uncertainty_definition": "95% bootstrap CI",
            },
            "claim_context": {
                "paper_claim_plan_locator": "claim-plan.json#C1",
                "paper_claim_plan_sha256": claim_plan["sha256"],
                "claim_id": "C1",
                "result_card_sha256": result_card["sha256"],
                "guardrail_status": "PASS",
                "claim_impact": "允许主图支持该 claim，但仅限 declared datasets。",
                "caption_reflects_claim_impact": True,
            },
            "evidence_binding": {
                "result_card_id": "RC-C1",
                "result_card_locator": "result-card.json#C1",
                "result_card_sha256": result_card["sha256"],
                "evidence_strength_locator": "evidence-strength.json#C1",
                "evidence_strength_sha256": evidence["sha256"],
                "claim_id": "C1",
                "owner_skill": "RESULT-ANALYSIS",
                "binding_status": "CONFIRMED",
            },
            "final_physical_size": {
                "width_mm": 89, "height_mm": 64.1, "min_font_pt": 7,
            },
            "accessibility": {
                "cvd_review": "VERIFIED", "grayscale_review": "VERIFIED",
                "cvd_evidence_sha256": cvd["sha256"],
                "grayscale_evidence_sha256": gray["sha256"],
                "redundant_encoding": True,
            },
        },
        "build": {
            "schema": BUILD_SCHEMA, "engine": "R/ggplot2", "engine_version": "4.6.0",
            "packages": {"ggplot2": "4.0.1"}, "mapping": {"x": "group", "y": "estimate"},
            "stat_transforms": [{"name": "identity", "parameters": {}}],
            "scales": {"group": "manual_okabe_ito"},
            "coordinates": {"name": "cartesian"}, "facets": {"name": "none"},
            "theme": {"name": "publication", "base_font_pt": 8},
            "device": [{"format": "pdf", "name": "ggsave"}],
            "width_mm": 89, "height_mm": 64.1,
            "inputs": {
                "data": data,
                "code": code,
                "result_card": result_card,
            },
            "outputs": [
                {"format": "pdf", **pdf},
                {"format": "png", **png},
            ],
            "degraded": False,
        },
    }


def _selftest() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="light_fig_contract_", dir=_e2e_tmp_root()))
    try:
        base = _base(tmp)
        assert evaluate(base, base_dir=tmp)["status"] == "PASS"
        palette_bad = json.loads(json.dumps(base))
        palette_bad["spec"]["data_semantics"] = {
            "variable_type": "continuous", "palette_type": "qualitative",
        }
        assert evaluate(palette_bad, base_dir=tmp)["status"] == "FAIL"
        radius_bad = json.loads(json.dumps(base))
        radius_bad["spec"]["size_encoding"] = {
            "mark": "circle", "quantity_mapping": "radius",
        }
        assert "AREA_PERCEPTION_MISMATCH" in {
            x["code"] for x in evaluate(radius_bad, base_dir=tmp)["issues"]
        }
        fallback_bad = json.loads(json.dumps(base))
        fallback_bad["build"]["engine"] = "Python/matplotlib"
        fallback_bad["build"]["degraded"] = True
        assert evaluate(fallback_bad, base_dir=tmp)["status"] == "FAIL"
        no_evidence = json.loads(json.dumps(base))
        no_evidence["spec"]["evidence_binding"] = {}
        assert "EVIDENCE_BINDING_GAP" in {
            x["code"] for x in evaluate(no_evidence, base_dir=tmp)["issues"]
        }
        no_claim_context = json.loads(json.dumps(base))
        no_claim_context["spec"]["claim_context"] = {}
        assert "CLAIM_CONTEXT_GAP" in {
            x["code"] for x in evaluate(no_claim_context, base_dir=tmp)["issues"]
        }
        warn_not_captioned = json.loads(json.dumps(base))
        warn_not_captioned["spec"]["claim_context"]["guardrail_status"] = "WARN"
        warn_not_captioned["spec"]["claim_context"]["caption_reflects_claim_impact"] = False
        assert "CLAIM_CONTEXT_WARN_NOT_IN_CAPTION" in {
            x["code"] for x in evaluate(warn_not_captioned, base_dir=tmp)["issues"]
        }
        blocked_guardrail = json.loads(json.dumps(base))
        blocked_guardrail["spec"]["claim_context"]["guardrail_status"] = "FAIL"
        assert "CLAIM_CONTEXT_GUARDRAIL_BLOCKS_FIGURE" in {
            x["code"] for x in evaluate(blocked_guardrail, base_dir=tmp)["issues"]
        }
        claim_hash_mismatch = json.loads(json.dumps(base))
        claim_hash_mismatch["spec"]["claim_context"]["result_card_sha256"] = "sha256:" + "b" * 64
        assert "CLAIM_CONTEXT_RESULT_CARD_MISMATCH" in {
            x["code"] for x in evaluate(claim_hash_mismatch, base_dir=tmp)["issues"]
        }
        hash_mismatch = json.loads(json.dumps(base))
        hash_mismatch["build"]["inputs"]["result_card"]["sha256"] = "sha256:" + "b" * 64
        hash_codes = {x["code"] for x in evaluate(hash_mismatch, base_dir=tmp)["issues"]}
        assert "RESULT_CARD_HASH_MISMATCH" in hash_codes
        assert "ARTIFACT_HASH_MISMATCH" in hash_codes
        unresolved = json.loads(json.dumps(base))
        unresolved["spec"]["accessibility"]["cvd_review"] = "NOT_RUN"
        assert evaluate(unresolved, base_dir=tmp)["status"] == "UNRESOLVED"
        path_escape = json.loads(json.dumps(base))
        path_escape["build"]["outputs"][0]["path"] = "../F1.pdf"
        assert "ARTIFACT_PATH_UNSAFE" in {
            x["code"] for x in evaluate(path_escape, base_dir=tmp)["issues"]
        }
        missing_output = json.loads(json.dumps(base))
        missing_output["build"]["outputs"][0]["path"] = "missing.pdf"
        assert "ARTIFACT_FILE_MISSING" in {
            x["code"] for x in evaluate(missing_output, base_dir=tmp)["issues"]
        }
        no_output_path = json.loads(json.dumps(base))
        no_output_path["build"]["outputs"][0].pop("path")
        assert "ARTIFACT_PATH_GAP" in {
            x["code"] for x in evaluate(no_output_path, base_dir=tmp)["issues"]
        }
    finally:
        for path in sorted(tmp.glob("*"), reverse=True):
            path.unlink(missing_ok=True)
        tmp.rmdir()
    print("figure_contract selftest PASS: palette/midpoint/area/R strict/result-card/"
          "paper-claim-context/caption/size/CVD + packaged output paths/hash")
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
    input_path = pathlib.Path(args.input)
    report = evaluate(json.loads(input_path.read_text(encoding="utf-8-sig")),
                      base_dir=input_path.resolve().parent)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
