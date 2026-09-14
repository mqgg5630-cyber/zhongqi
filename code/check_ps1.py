#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ps1.py - sanity check the .ps1 helper scripts before shipping them to a
Windows PowerShell 5.1 user.

Windows PowerShell 5.1 reads a .ps1 file as ANSI (GBK on a Chinese Windows) when
it has no UTF-8 BOM. A UTF-8 Chinese comment then decodes to garbage that can
swallow a closing quote and break the parser - exactly the error users see as
"InvalidArgument" / "字符串缺少终止符".

This checker flags:
  1. any non-ASCII byte in a .ps1 file                (must be avoided)
  2. a UTF-8 BOM                                       (fine, but reported)
  3. unbalanced double quotes per file                 (unterminated string)
  4. unbalanced braces / parentheses                   (unterminated block)

Usage:
    python code/check_ps1.py *.ps1
"""

from __future__ import annotations

import sys
from pathlib import Path


def scan(text: str):
    """Return (issues, stats): very small PowerShell lexer good enough for our scripts."""
    issues = []
    braces = parens = 0
    in_string = False
    line = 1
    i = 0
    in_block_comment = False
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            if in_string:
                issues.append((line, "unterminated double-quoted string (line ends inside a string)"))
                in_string = False
            line += 1
            i += 1
            continue
        if in_block_comment:
            if text.startswith("#>", i):
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if not in_string:
            if text.startswith("<#", i):
                in_block_comment = True
                i += 2
                continue
            if ch == "#":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if ch == "'":
                # single-quoted string: '' is an escaped quote
                i += 1
                while i < n:
                    if text[i] == "'":
                        if i + 1 < n and text[i + 1] == "'":
                            i += 2
                            continue
                        break
                    if text[i] == "\n":
                        line += 1
                    i += 1
                i += 1
                continue
        if ch == "`":                       # backtick escapes the next char
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
            i += 1
            continue
        if in_string:
            i += 1
            continue
        if ch == "{":
            braces += 1
        elif ch == "}":
            braces -= 1
            if braces < 0:
                issues.append((line, "closing brace with no opener"))
                braces = 0
        elif ch == "(":
            parens += 1
        elif ch == ")":
            parens -= 1
            if parens < 0:
                issues.append((line, "closing parenthesis with no opener"))
                parens = 0
        i += 1

    if in_string:
        issues.append((line, "unterminated double-quoted string at end of file"))
    if braces:
        issues.append((line, f"unbalanced curly braces (balance {braces:+d})"))
    if parens:
        issues.append((line, f"unbalanced parentheses (balance {parens:+d})"))
    return issues


def check(path: Path) -> list:
    raw = path.read_bytes()
    issues = []
    if raw.startswith(b"\xef\xbb\xbf"):
        print(f"note  {path}: has UTF-8 BOM (ok for PS 5.1, but not required)")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as e:
        bad = raw[e.start:e.start + 12]
        issues.append((0, f"NON-ASCII bytes at offset {e.start} ({bad!r}) - "
                          f"PowerShell 5.1 will decode this as GBK and may break"))
        text = raw.decode("utf-8", errors="replace")
    # normalise line endings so the lexer sees \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    issues.extend(scan(text))
    return issues


def main(argv) -> int:
    files = [Path(a) for a in (argv or sys.argv[1:])]
    if not files:
        files = sorted(Path(".").glob("*.ps1"))
    bad = 0
    for f in files:
        issues = check(f)
        if issues:
            bad += 1
            print(f"FAIL  {f}")
            for ln, msg in issues:
                print(f"        line {ln}: {msg}")
        else:
            print(f"OK    {f}")
    print(f"\n{len(files) - bad}/{len(files)} file(s) passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(None))
