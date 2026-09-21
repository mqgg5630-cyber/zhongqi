#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Venue-profile-driven submission preflight for LaTeX/PDF artifacts.

No venue limit is embedded here.  Page, anonymity, template, page-box and font
rules come from a user-supplied or freshly verified profile.  Static checks are
advisory outside explicitly declared objective rules; semantic anonymity and
final visual quality always require human review.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.typesetting_compliance.v1"
_UNAVAILABLE_CODES = {
    "PAGES_UNAVAILABLE", "PAGE_SIZE_UNAVAILABLE", "FONT_EMBEDDING_UNAVAILABLE",
}

_IDENTITY_CMDS = re.compile(
    r"^[^%\n]*\\(author|thanks|affil|affiliation|email|institute|address)\b",
    re.M | re.I,
)
_ACK = re.compile(r"\\(?:section|subsection)\*?\{[^}]*(acknowledg|funding|致谢|资助|基金)[^}]*\}", re.I)
_LINK = re.compile(
    r"(github\.com/[\w\-]+|gitlab\.com/[\w\-]+|[\w\-]+\.github\.io|"
    r"huggingface\.co/[\w\-]+|orcid\.org/[\d\-]+)",
    re.I,
)
_SELFREF = re.compile(r"\b(?:our|my)\s+(?:previous|prior|earlier|recent)\s+(?:work|paper|study|method)\b", re.I)
_SELFREF_ZH = re.compile(r"我们(?:之前|先前|此前|早期)的(?:工作|论文|研究|方法)")
_TODO = re.compile(r"\\todo\b|\bTODO\b|\bTBD\b|\bXXX\b|\bFIXME\b|\[占位\]|\bplaceholder\b", re.I)
_PDF_META = re.compile(rb"/(Author|Title|Subject|Creator|Keywords)\s*\(([^)]*)\)")
_DOC_CLASS = re.compile(r"\\documentclass(?:\[([^\]]*)\])?\{([^}]+)\}", re.I)
_PACKAGE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", re.I)
_FONT_ROW = re.compile(
    r"^(\S+)\s+(.+?)\s+(\S+)\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$",
    re.I,
)


def strip_comments(tex_text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", row) for row in tex_text.splitlines())


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _add(findings: list, severity: str, code: str, msg: str, **extra: Any) -> None:
    item = {"severity": severity, "code": code, "msg": msg}
    item.update({k: v for k, v in extra.items() if v is not None})
    findings.append(item)


def check_tex(text: str, double_blind: bool = False) -> list[dict[str, Any]]:
    text = strip_comments(text)
    findings: list[dict[str, Any]] = []
    if double_blind:
        for match in _IDENTITY_CMDS.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.start())
            source_line = text[start:end if end >= 0 else len(text)].strip()
            if re.search(r"anonymous|匿名|removed for review|for blind review|\\author\s*\{\s*\}", source_line, re.I):
                continue
            _add(findings, "high", "BLIND_IDENTITY",
                 f"双盲稿含未匿名身份命令：{source_line[:100]}",
                 line=_line(text, match.start()))
        ack = _ACK.search(text)
        if ack:
            _add(findings, "high", "BLIND_ACK",
                 "双盲稿含致谢/基金小节；静态命中需按 venue 规则人工确认。",
                 line=_line(text, ack.start()))
        for match in _LINK.finditer(text):
            _add(findings, "high", "BLIND_LINK",
                 f"可识别链接 `{match.group(0)}`；确认是否为匿名仓库。",
                 line=_line(text, match.start()))
        selfref = _SELFREF.search(text) or _SELFREF_ZH.search(text)
        if selfref:
            _add(findings, "med", "BLIND_SELFREF",
                 "存在第一人称自指；双盲稿应按 venue 规则改成可审匿名表述。",
                 line=_line(text, selfref.start()))
    for match in _TODO.finditer(text):
        _add(findings, "med", "RESIDUAL_TODO",
             f"残留待办/占位 `{match.group(0)}`", line=_line(text, match.start()))
    return findings


def _run_text(command: list[str], timeout: int = 20) -> tuple[int | None, str]:
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, repr(exc)


def resolve_tool(name: str) -> str | None:
    """Prefer a real executable over a broken PATH wrapper on Windows."""
    candidates: list[str] = []
    first = shutil.which(name)
    if first:
        candidates.append(first)
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["where.exe", name], capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode == 0:
                candidates.extend(row.strip() for row in proc.stdout.splitlines() if row.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
        candidates.sort(key=lambda value: pathlib.Path(value).suffix.lower() != ".exe")
    for candidate in dict.fromkeys(candidates):
        if pathlib.Path(candidate).is_file():
            return candidate
    return None


def inspect_pdf(path: str) -> dict[str, Any]:
    pdf = pathlib.Path(path)
    result: dict[str, Any] = {
        "path": str(pdf.resolve()), "exists": pdf.is_file(), "backend": None,
        "pages": None, "page_size": None, "metadata": {}, "fonts": [],
        "pdfinfo_tool": None, "pdffonts_tool": None,
    }
    if not pdf.is_file():
        result["error"] = "PDF missing"
        return result
    pdfinfo = resolve_tool("pdfinfo")
    result["pdfinfo_tool"] = pdfinfo
    if pdfinfo:
        code, text = _run_text([pdfinfo, str(pdf)])
        if code == 0:
            result["backend"] = "pdfinfo"
            for row in text.splitlines():
                if ":" not in row:
                    continue
                key, value = row.split(":", 1)
                key, value = key.strip(), value.strip()
                if key == "Pages" and value.isdigit():
                    result["pages"] = int(value)
                elif key == "Page size":
                    result["page_size"] = value
                elif key in {"Author", "Title", "Subject", "Creator", "Producer", "Keywords"} and value:
                    result["metadata"][key] = value
    pdffonts = resolve_tool("pdffonts")
    result["pdffonts_tool"] = pdffonts
    if pdffonts:
        code, text = _run_text([pdffonts, str(pdf)])
        if code == 0:
            rows = [row for row in text.splitlines() if row.strip()]
            for row in rows[2:]:
                match = _FONT_ROW.match(row)
                if match:
                    result["fonts"].append({
                        "name": match.group(1), "type": match.group(2),
                        "encoding": match.group(3),
                        "embedded": match.group(4).lower() == "yes",
                        "subset": match.group(5).lower() == "yes",
                        "unicode": match.group(6).lower() == "yes",
                    })
    if result["pages"] is None or not result["metadata"]:
        raw = pdf.read_bytes()
        if result["pages"] is None:
            count = len(re.findall(rb"/Type\s*/Page\b(?!s)", raw))
            result["pages"] = count or None
        for match in _PDF_META.finditer(raw):
            key = match.group(1).decode("latin-1")
            value = match.group(2).decode("latin-1", "replace").strip()
            if value:
                result["metadata"].setdefault(key, value)
        result["backend"] = result["backend"] or "raw-fallback"
    return result


def check_pdf_metadata(path: str, double_blind: bool = False) -> list[dict[str, Any]]:
    info = inspect_pdf(path)
    findings: list[dict[str, Any]] = []
    if not info["exists"]:
        _add(findings, "info", "PDF_UNREADABLE", "PDF 不存在或不可读。")
        return findings
    author = info["metadata"].get("Author")
    if author:
        _add(
            findings, "high" if double_blind else "med", "PDF_AUTHOR_META",
            f"PDF metadata Author=`{author[:80]}`"
            + ("；双盲 profile 要求清空。" if double_blind else "；确认是否应公开。"),
        )
    if not info["metadata"]:
        _add(findings, "info", "PDF_META_NONE",
             "未发现可读 PDF metadata；仍需人工/venue analyzer 复核。")
    return findings


def check_pages(path: str, max_pages: int) -> list[dict[str, Any]]:
    info = inspect_pdf(path)
    pages = info.get("pages")
    if pages is None:
        return [{"severity": "med", "code": "PAGES_UNAVAILABLE", "msg": "无法可靠取得 PDF 页数。"}]
    if pages > max_pages:
        return [{"severity": "high", "code": "PAGES_OVER",
                 "msg": f"PDF {pages} 页 > profile 上限 {max_pages} 页。", "actual": pages,
                 "expected": max_pages}]
    return [{"severity": "info", "code": "PAGES_OK",
             "msg": f"PDF {pages} 页 ≤ profile 上限 {max_pages} 页。", "actual": pages,
             "expected": max_pages}]


def check_profile(tex_text: str, pdf_path: str | None, profile: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    tex_text = strip_comments(tex_text)
    expected_class = profile.get("required_documentclass")
    match = _DOC_CLASS.search(tex_text)
    actual_class = match.group(2).strip() if match else None
    if expected_class and actual_class != expected_class:
        _add(findings, "high", "TEMPLATE_CLASS",
             f"documentclass=`{actual_class}`，profile 要求 `{expected_class}`。")
    required_packages = set(profile.get("required_packages") or [])
    actual_packages: set[str] = set()
    for pkg_match in _PACKAGE.finditer(tex_text):
        actual_packages.update(part.strip() for part in pkg_match.group(1).split(","))
    for package in sorted(required_packages - actual_packages):
        _add(findings, "high", "REQUIRED_PACKAGE",
             f"profile 要求宏包 `{package}`，正文未加载。")
    if pdf_path:
        info = inspect_pdf(pdf_path)
        expected_size = profile.get("expected_page_size")
        if expected_size and info.get("page_size") and expected_size.lower() not in info["page_size"].lower():
            _add(findings, "high", "PAGE_SIZE",
                 f"PDF page size `{info['page_size']}` 与 profile `{expected_size}` 不符。")
        elif expected_size and not info.get("page_size"):
            _add(findings, "med", "PAGE_SIZE_UNAVAILABLE",
                 "profile 要求核 page size，但本地 PDF 工具未返回可判值。")
        if profile.get("require_embedded_fonts"):
            if not info.get("fonts"):
                _add(findings, "med", "FONT_EMBEDDING_UNAVAILABLE",
                     "pdffonts 不可用或未解析到字体；不能声称字体嵌入已核。")
            for font in info.get("fonts") or []:
                if not font["embedded"]:
                    _add(findings, "high", "FONT_NOT_EMBEDDED",
                         f"字体 `{font['name']}` 未嵌入 PDF。")
    return findings


def audit(tex_path: str | None, pdf_path: str | None, profile: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    tex_text = ""
    if tex_path:
        tex_text = pathlib.Path(tex_path).read_text(encoding="utf-8", errors="replace")
        findings.extend(check_tex(tex_text, bool(profile.get("double_blind"))))
    if pdf_path:
        findings.extend(check_pdf_metadata(pdf_path, bool(profile.get("double_blind"))))
        max_pages = int(profile.get("max_pages") or 0)
        if max_pages > 0:
            findings.extend(check_pages(pdf_path, max_pages))
    if tex_path:
        findings.extend(check_profile(tex_text, pdf_path, profile))
    critical_count = sum(item["severity"] == "high" for item in findings)
    unavailable_count = sum(item["code"] in _UNAVAILABLE_CODES for item in findings)
    status = "ERROR" if critical_count else "UNAVAILABLE" if unavailable_count else "PASS"
    return {
        "schema": SCHEMA, "producer": "typesetting",
        "status": status,
        "profile": profile, "tex": tex_path, "pdf": pdf_path,
        "pdf_inspection": inspect_pdf(pdf_path) if pdf_path else None,
        "findings": findings,
        "critical_count": critical_count,
        "unavailable_count": unavailable_count,
        "boundary": (
            "Static checks cannot prove semantic anonymity, authoritative venue interpretation, "
            "or final visual quality; review the current official instructions and rendered PDF."
        ),
    }


def render(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "PASS: 未命中 profile 声明的静态雷区；仍需权威规范与视觉人工复核。"
    order = {"high": 0, "med": 1, "info": 2}
    lines = ["# Submission compliance", ""]
    for item in sorted(findings, key=lambda row: order.get(row["severity"], 9)):
        loc = f" line {item['line']}" if item.get("line") else ""
        lines.append(f"- [{item['severity']}] {item['code']}{loc}: {item['msg']}")
    return "\n".join(lines)


def _selftest() -> int:
    bad = (
        "\\documentclass{article}\n\\usepackage{graphicx}\n"
        "\\author{Zhang Wei}\\section{Acknowledgements} Funded.\n"
        "See our previous work. github.com/zhang/repo TODO\n"
    )
    findings = check_tex(bad, True)
    codes = {item["code"] for item in findings}
    assert {"BLIND_IDENTITY", "BLIND_ACK", "BLIND_LINK", "BLIND_SELFREF", "RESIDUAL_TODO"} <= codes
    assert not check_tex("% \\author{Visible Name}\n% TODO\n", True)
    profile_findings = check_profile(
        bad, None, {"required_documentclass": "IEEEtran", "required_packages": ["booktabs"]}
    )
    assert {item["code"] for item in profile_findings} == {"TEMPLATE_CLASS", "REQUIRED_PACKAGE"}
    font_row = _FONT_ROW.match(
        "ABCDEF+CMR10 Type 1 Builtin yes yes yes 12 0"
    )
    assert font_row and font_row.group(4).lower() == "yes"
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        fake = pathlib.Path(temp) / "fake.pdf"
        fake.write_bytes(b"%PDF-1.5\n/Author (Zhang Wei)\n/Type /Page\n/Type /Page\n")
        assert any(item["code"] == "PDF_AUTHOR_META" for item in check_pdf_metadata(str(fake), True))
        assert any(item["code"] == "PAGES_OVER" for item in check_pages(str(fake), 1))
    print("[selftest] PASS submission_check: profile/anonymity/pages/metadata")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Venue-profile submission checker")
    parser.add_argument("--tex")
    parser.add_argument("--pdf")
    parser.add_argument("--profile", help="JSON venue/profile; no limits are embedded")
    parser.add_argument("--double-blind", action="store_true")
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--report")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest or not (args.tex or args.pdf):
        return _selftest()
    profile: dict[str, Any] = {}
    if args.profile:
        profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
        if profile.get("schema") == "light.typesetting_venue_profile.v1":
            profile = profile.get("rules") or {}
    if args.double_blind:
        profile["double_blind"] = True
    if args.max_pages:
        profile["max_pages"] = args.max_pages
    result = audit(args.tex, args.pdf, profile)
    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result["findings"]))
    return 1 if result["critical_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
