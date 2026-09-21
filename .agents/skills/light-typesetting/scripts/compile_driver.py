#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic LaTeX build driver for Light stage 11.

The driver records the exact command, working directory, tool versions, build
passes, PDF hash and source-located diagnostics.  Its public status contract is:

* PASS: a PDF exists and references/citations converged.
* ERROR: the manuscript or its declared backend failed.
* UNAVAILABLE: the required local toolchain/resource cannot be executed.
* UNRESOLVED: a PDF exists, but references/citations did not converge.

UNAVAILABLE exits 0 because stage 11 must not turn a missing local tool into a
manuscript critical.  It is never reported as PASS or delivered.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.typesetting_compile.v1"
STATUSES = ("PASS", "ERROR", "UNAVAILABLE", "UNRESOLVED")

_XE_TRIGGER = re.compile(
    r"\\usepackage(?:\[[^\]]*\])?\{[^}]*(fontspec|xeCJK|ctex|unicode-math|polyglossia)[^}]*\}"
    r"|\\documentclass(?:\[[^\]]*\])?\{ctex",
    re.I,
)
_LUA_TRIGGER = re.compile(
    r"\\usepackage(?:\[[^\]]*\])?\{[^}]*(luacode|luatextra|lua-ul)[^}]*\}"
    r"|\\directlua",
    re.I,
)
_BIBLATEX = re.compile(r"\\usepackage(?:\[([^\]]*)\])?\{biblatex\}", re.I)
_BIBTEX = re.compile(r"\\bibliography\s*\{", re.I)
_FILE_LINE = re.compile(
    r"(?m)^(?P<file>(?:[A-Za-z]:)?[^:\r\n]*?\.tex):(?P<line>\d+):\s*(?P<message>.+)$"
)
_L_LINE = re.compile(r"(?m)^l\.(?P<line>\d+)\s*(?P<context>.*)$")
_ROUND = re.compile(r"Run number\s+(\d+)\s+of rule\s+'([^']+)'", re.I)
_OUTPUT_PAGES = re.compile(r"Output written on .+?\((\d+)\s+pages?", re.I)
_UNRESOLVED = [
    ("undefined_citation", re.compile(r"(?:Citation|Package .* Warning: Citation).*undefined", re.I)),
    ("undefined_reference", re.compile(r"(?:Reference|Package .* Warning: Reference).*undefined", re.I)),
    ("rerun_required", re.compile(r"Rerun to get cross-references right|Label\(s\) may have changed", re.I)),
]
_ERROR_TRANSLATIONS = [
    (re.compile(r"Undefined control sequence", re.I),
     "命令未定义：核对拼写与所属宏包。"),
    (re.compile(r"Missing \$ inserted", re.I),
     "数学符号出现在文本模式：使用 $...$ 或转义特殊字符。"),
    (re.compile(r"Runaway argument|Paragraph ended before", re.I),
     "参数或环境未闭合：从首个报错行向前核对花括号和 begin/end。"),
    (re.compile(r"File [`']?([^'\r\n]+)'? not found", re.I),
     "文件或宏包缺失：核对相对路径；宏包缺失属于环境资源问题，勿改写论文掩盖。"),
    (re.compile(r"Package biblatex Error|Biber error|BibTeX error", re.I),
     "bibliography backend 失败：核对 biblatex/Biber 与传统 BibTeX 是否混用。"),
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _which(name: str) -> str | None:
    override = os.environ.get("LIGHT_TYPESETTING_PATH")
    return shutil.which(name, path=override) if override is not None else shutil.which(name)


def strip_comments(tex_text: str) -> str:
    """Remove unescaped LaTeX comments before command detection."""
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", row) for row in tex_text.splitlines())


def detect_engine(tex_text: str) -> dict[str, str]:
    tex_text = strip_comments(tex_text)
    if _XE_TRIGGER.search(tex_text):
        return {"engine": "xelatex", "reason": "fontspec/xeCJK/ctex/Unicode trigger"}
    if _LUA_TRIGGER.search(tex_text):
        return {"engine": "lualatex", "reason": "LuaTeX trigger"}
    return {"engine": "pdflatex", "reason": "no Unicode/Lua trigger"}


def detect_backend(tex_text: str) -> dict[str, Any]:
    tex_text = strip_comments(tex_text)
    biblatex = _BIBLATEX.search(tex_text)
    traditional = bool(_BIBTEX.search(tex_text))
    if biblatex and traditional:
        return {
            "backend": "conflict",
            "reason": "biblatex and traditional \\bibliography are both present",
        }
    if biblatex:
        options = biblatex.group(1) or ""
        match = re.search(r"(?:^|,)\s*backend\s*=\s*([A-Za-z0-9_-]+)", options, re.I)
        backend = match.group(1).lower() if match else "biber"
        return {"backend": backend, "reason": "biblatex package"}
    if traditional:
        return {"backend": "bibtex", "reason": "traditional \\bibliography"}
    return {"backend": "none", "reason": "no external bibliography command"}


def find_tool(preferred: str = "auto") -> tuple[str | None, str | None]:
    order = ("latexmk", "tectonic") if preferred == "auto" else (preferred,)
    for name in order:
        path = _which(name)
        if path:
            return name, path
    return None, None


def build_command(
    tool: str,
    engine: str,
    texfile: str,
    outdir: str,
    tool_path: str | None = None,
) -> list[str]:
    exe = tool_path or tool
    tex_name = pathlib.Path(texfile).name
    if tool == "latexmk":
        flag = {"pdflatex": "-pdf", "xelatex": "-pdfxe", "lualatex": "-pdflua"}[engine]
        return [
            exe, flag, "-interaction=nonstopmode", "-halt-on-error",
            "-file-line-error", f"-output-directory={outdir}", tex_name,
        ]
    return [exe, "--keep-logs", "--synctex", "--outdir", outdir, tex_name]


def _tool_version(path: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=8,
            encoding="utf-8", errors="replace",
        )
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return {
            "status": "available" if proc.returncode == 0 else "unavailable",
            "returncode": proc.returncode,
            "first_line": text.splitlines()[0] if text else "",
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _diagnostics(log_text: str, tex_path: pathlib.Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str]] = set()
    for match in _FILE_LINE.finditer(log_text):
        message = match.group("message").strip()
        if not ("error" in message.lower() or message.startswith("!") or
                any(p.search(message) for p, _ in _ERROR_TRANSLATIONS)):
            continue
        file_value = match.group("file").strip()
        line = int(match.group("line"))
        key = (file_value, line, message)
        if key not in seen:
            seen.add(key)
            results.append({
                "severity": "error", "file": file_value, "line": line,
                "message": message, "plain": translate_one(message),
            })
    if not results:
        for match in _L_LINE.finditer(log_text):
            line = int(match.group("line"))
            context = match.group("context").strip()
            window = log_text[max(0, match.start() - 500):match.end()]
            message = next(
                (row.strip("! ").strip() for row in reversed(window.splitlines())
                 if row.startswith("! ")),
                context or "LaTeX error",
            )
            key = (str(tex_path), line, message)
            if key not in seen:
                seen.add(key)
                results.append({
                    "severity": "error", "file": str(tex_path), "line": line,
                    "message": message, "plain": translate_one(message + "\n" + window),
                })
    if not results:
        first = next((row[2:].strip() for row in log_text.splitlines() if row.startswith("! ")), None)
        if first:
            results.append({
                "severity": "error", "file": str(tex_path), "line": None,
                "message": first, "plain": translate_one(first),
            })
    return results


def translate_one(text: str) -> str:
    for pattern, message in _ERROR_TRANSLATIONS:
        if pattern.search(text):
            return message
    return "从首个错误修起；后续错误通常是连锁反应。"


def _unresolved(log_text: str) -> list[dict[str, Any]]:
    out = []
    for code, pattern in _UNRESOLVED:
        matches = [m.group(0).strip() for m in pattern.finditer(log_text)]
        if matches:
            out.append({"code": code, "count": len(matches), "examples": matches[:5]})
    return out


def _base_result(tex_path: pathlib.Path, out_path: pathlib.Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "producer": "typesetting",
        "stage": 11,
        "generated_at": now(),
        "status": "ERROR",
        "manuscript": str(tex_path),
        "working_directory": str(tex_path.parent),
        "outdir": str(out_path),
        "engine": None,
        "bibliography_backend": None,
        "tool": None,
        "command": None,
        "command_shell": None,
        "returncode": None,
        "rounds": [],
        "diagnostics": [],
        "warnings": [],
        "unresolved": [],
        "pdf": None,
        "log": None,
    }


def compile_tex(
    texfile: str,
    engine: str = "auto",
    outdir: str = "build",
    timeout: int = 300,
    tool: str = "auto",
    backend: str = "auto",
) -> dict[str, Any]:
    tex_path = pathlib.Path(texfile).resolve()
    out_path = pathlib.Path(outdir)
    if not out_path.is_absolute():
        out_path = (pathlib.Path.cwd() / out_path).resolve()
    result = _base_result(tex_path, out_path)
    if not tex_path.is_file():
        result.update(status="ERROR", reason="input_missing",
                      diagnostics=[{"severity": "error", "file": str(tex_path),
                                    "line": None, "message": "manuscript not found",
                                    "plain": "输入稿件路径不存在。"}])
        return result

    text = tex_path.read_text(encoding="utf-8", errors="replace")
    detected_engine = detect_engine(text)
    selected_engine = detected_engine["engine"] if engine == "auto" else engine
    detected_backend = detect_backend(text)
    selected_backend = detected_backend["backend"] if backend == "auto" else backend
    result["engine"] = {
        "selected": selected_engine,
        "source": "detected" if engine == "auto" else "declared",
        "reason": detected_engine["reason"],
    }
    result["bibliography_backend"] = {
        "selected": selected_backend,
        "detected": detected_backend["backend"],
        "reason": detected_backend["reason"],
    }

    if (engine != "auto" and detected_engine["engine"] in ("xelatex", "lualatex")
            and selected_engine != detected_engine["engine"]):
        result.update(status="ERROR", reason="engine_incompatible_with_source")
        result["diagnostics"] = [{
            "severity": "error", "file": str(tex_path), "line": None,
            "message": (
                f"declared engine={selected_engine}, source requires "
                f"{detected_engine['engine']} ({detected_engine['reason']})"
            ),
            "plain": "profile 声明的引擎不能满足正文中的硬触发宏包/命令。",
        }]
        return result
    if detected_backend["backend"] == "conflict":
        result.update(status="ERROR", reason="bibliography_backend_conflict")
        result["diagnostics"] = [{
            "severity": "error", "file": str(tex_path), "line": None,
            "message": detected_backend["reason"],
            "plain": "不要混用 biblatex 与传统 \\bibliography；选择一套 backend。",
        }]
        return result
    if backend != "auto" and selected_backend != detected_backend["backend"]:
        result.update(status="ERROR", reason="bibliography_backend_mismatch")
        result["diagnostics"] = [{
            "severity": "error", "file": str(tex_path), "line": None,
            "message": f"declared backend={selected_backend}, source backend={detected_backend['backend']}",
            "plain": "venue/profile 声明的 bibliography backend 与正文源不一致。",
        }]
        return result

    selected_tool, selected_path = find_tool(tool)
    if not selected_tool or not selected_path:
        result.update(
            status="UNAVAILABLE", reason="compile_tool_missing",
            tool={"selected": tool, "path": None, "availability": "unavailable"},
        )
        return result

    selected_version = _tool_version(selected_path)
    if selected_version["status"] != "available":
        result.update(
            status="UNAVAILABLE", reason="compile_tool_probe_failed",
            tool={"selected": selected_tool, "path": selected_path,
                  "version": selected_version},
        )
        return result

    required = []
    if selected_tool == "latexmk":
        required.append(selected_engine)
        if selected_backend in ("bibtex", "biber"):
            required.append(selected_backend)
    required_probes = []
    for name in required:
        path = _which(name)
        probe = _tool_version(path) if path else {"status": "unavailable", "reason": "not_found"}
        required_probes.append({"name": name, "path": path, **probe})
    missing = [row["name"] for row in required_probes if row["status"] != "available"]
    result["tool"] = {
        "selected": selected_tool,
        "path": selected_path,
        "version": selected_version,
        "required_executables": required,
        "required_executable_probes": required_probes,
        "missing_executables": missing,
    }
    if missing:
        result.update(status="UNAVAILABLE", reason="required_executable_missing")
        return result
    if selected_tool == "tectonic" and selected_backend == "biber":
        result.update(status="UNAVAILABLE", reason="tectonic_biber_pipeline_not_supported")
        return result

    out_path.mkdir(parents=True, exist_ok=True)
    command = build_command(
        selected_tool, selected_engine, str(tex_path), str(out_path), selected_path
    )
    result["command"] = command
    result["command_shell"] = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    try:
        proc = subprocess.run(
            command, cwd=str(tex_path.parent), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(status="UNAVAILABLE", reason="compile_tool_timeout_or_launch_failure")
        result["diagnostics"] = [{
            "severity": "error", "file": None, "line": None,
            "message": repr(exc),
            "plain": "工具链无法在时限内启动/完成；这是环境可用性，不是稿件错误。",
        }]
        return result

    base = tex_path.stem
    log_path = out_path / f"{base}.log"
    pdf_path = out_path / f"{base}.pdf"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    combined = "\n".join((proc.stdout or "", proc.stderr or "", log_text))
    result["returncode"] = proc.returncode
    result["log"] = {
        "path": str(log_path) if log_path.is_file() else None,
        "sha256": sha256_file(log_path),
    }
    result["rounds"] = [
        {"number": int(number), "rule": rule} for number, rule in _ROUND.findall(combined)
    ]
    pages = _OUTPUT_PAGES.findall(log_text)
    result["diagnostics"] = _diagnostics(combined, tex_path)
    result["unresolved"] = _unresolved(log_text)
    result["warnings"] = [
        row.strip() for row in log_text.splitlines()
        if "Warning" in row or row.startswith(("Overfull ", "Underfull "))
    ][:100]
    if proc.returncode != 0 or not pdf_path.is_file():
        result.update(status="ERROR", reason="compiler_nonzero_or_pdf_missing")
    elif result["unresolved"]:
        result.update(status="UNRESOLVED", reason="cross_references_or_citations_not_converged")
    else:
        result.update(status="PASS", reason="compiled_and_converged")
    if pdf_path.is_file():
        result["pdf"] = {
            "path": str(pdf_path),
            "sha256": sha256_file(pdf_path),
            "bytes": pdf_path.stat().st_size,
            "pages_from_log": int(pages[-1]) if pages else None,
        }
    return result


def status_exit(status: str) -> int:
    return {"PASS": 0, "UNAVAILABLE": 0, "ERROR": 1, "UNRESOLVED": 1}.get(status, 1)


def to_markdown(result: dict[str, Any]) -> str:
    status = result["status"]
    lines = [f"# LaTeX compile — {status}", ""]
    lines.append(f"- manuscript: `{result['manuscript']}`")
    lines.append(f"- engine/backend: `{result.get('engine')}` / `{result.get('bibliography_backend')}`")
    lines.append(f"- tool: `{result.get('tool')}`")
    lines.append(f"- command: `{result.get('command_shell') or 'not run'}`")
    lines.append(f"- rounds: {result.get('rounds') or 'none recorded'}")
    lines.append(f"- PDF: `{(result.get('pdf') or {}).get('path') or 'none'}`")
    if status == "UNAVAILABLE":
        lines += ["", "> 工具链 UNAVAILABLE：未把环境缺失冒充稿件错误；exit 0，但不得标 delivered。"]
    if result.get("diagnostics"):
        lines += ["", "## Root cause"]
        for item in result["diagnostics"]:
            loc = f"{item.get('file')}:{item.get('line')}" if item.get("line") else str(item.get("file") or "tool")
            lines.append(f"- `{loc}` — {item.get('message')} → {item.get('plain')}")
    if result.get("unresolved"):
        lines += ["", "## Unresolved", f"- {json.dumps(result['unresolved'], ensure_ascii=False)}"]
    return "\n".join(lines)


def _selftest() -> int:
    assert detect_engine(r"\documentclass{ctexart}")["engine"] == "xelatex"
    assert detect_engine(r"\directlua{a}")["engine"] == "lualatex"
    assert detect_engine(r"\documentclass{article}")["engine"] == "pdflatex"
    assert detect_backend(r"\bibliography{refs}")["backend"] == "bibtex"
    assert detect_backend(r"\usepackage{biblatex}")["backend"] == "biber"
    assert detect_backend(r"\usepackage[backend=bibtex]{biblatex}")["backend"] == "bibtex"
    assert detect_backend(r"\usepackage{biblatex}\bibliography{refs}")["backend"] == "conflict"
    assert detect_backend("% \\usepackage{biblatex}\n% \\bibliography{refs}")["backend"] == "none"
    cmd = build_command("latexmk", "xelatex", "D:/x/paper.tex", "D:/x/build", "latexmk")
    assert "-pdfxe" in cmd and "-file-line-error" in cmd and cmd[-1] == "paper.tex"
    sample = "paper.tex:17: Undefined control sequence.\nl.17 \\\\bad\n"
    diag = _diagnostics(sample, pathlib.Path("paper.tex"))
    assert diag and diag[0]["line"] == 17 and "命令未定义" in diag[0]["plain"]
    unresolved = _unresolved("LaTeX Warning: Citation `missing' on page 1 undefined")
    assert unresolved and unresolved[0]["code"] == "undefined_citation"
    assert status_exit("PASS") == 0 and status_exit("UNAVAILABLE") == 0
    assert status_exit("ERROR") == 1 and status_exit("UNRESOLVED") == 1
    missing = compile_tex("Z:/definitely/not/here.tex")
    assert missing["status"] == "ERROR" and missing["reason"] == "input_missing"
    with tempfile.TemporaryDirectory() as temp:
        hard_engine = pathlib.Path(temp) / "hard-engine.tex"
        hard_engine.write_text(
            "\\documentclass{article}\\usepackage{fontspec}\\begin{document}x\\end{document}",
            encoding="utf-8",
        )
        mismatch = compile_tex(str(hard_engine), engine="pdflatex", backend="none")
        assert mismatch["status"] == "ERROR"
        assert mismatch["reason"] == "engine_incompatible_with_source"
    print("[selftest] PASS compile_driver: engine/backend/command/root-cause/status contract")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible LaTeX compile driver")
    parser.add_argument("--compile", dest="texfile")
    parser.add_argument("--detect")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "pdflatex", "xelatex", "lualatex"])
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "none", "bibtex", "biber"])
    parser.add_argument("--tool", default="auto", choices=["auto", "latexmk", "tectonic"])
    parser.add_argument("--outdir", default="build")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--json-out")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress human report; useful for locale-sensitive command gates")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest or (not args.texfile and not args.detect):
        return _selftest()
    if args.detect:
        text = pathlib.Path(args.detect).read_text(encoding="utf-8", errors="replace")
        print(json.dumps({"engine": detect_engine(text), "backend": detect_backend(text)},
                         ensure_ascii=False, indent=2))
        return 0
    result = compile_tex(
        args.texfile, engine=args.engine, backend=args.backend, tool=args.tool,
        outdir=args.outdir, timeout=args.timeout,
    )
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if not args.quiet:
        print(to_markdown(result))
    return status_exit(result["status"])


if __name__ == "__main__":
    raise SystemExit(main())
