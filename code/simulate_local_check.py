#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""simulate_local_check.py —— 在沙箱里**预演本机核验**（code/check_deliverables.ps1 的
纯 python 双胞胎），这样每一轮在请本机核验之前，就能先证明"本机那一关会过"。

为什么要有它：本机核验是闭环的最后一关，但沙箱里没有 Windows / PowerShell / Office。
把同一套判据（在场 → 体积 → sha256 → OOXML 包结构 → 页数/段落数复核）在沙箱里先跑一遍，
就能把"清单写错了 / 忘了还原字节 / 文件被截断"这类问题挡在 push 之前，
不至于浪费一轮本机往返（本机值守 2 分钟一轮）。

**不**预演的部分（只有真本机才有意义）：
  - `auth.ps1 -Verify`（免点击推送）
  - 计划任务 `git-sync-watch-*` 的形态（零窗口）
  - `-Com`：真 Word / PowerPoint 打开

用法：
    python code/simulate_local_check.py                 # 预演，逐个文件打印
    python code/simulate_local_check.py --json          # 机读输出
    python code/simulate_local_check.py --manifest P    # 指定清单

退出码：0 = 本机那一关会过；2 = 有文件对不上（详情已打印）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "results" / "status" / "agent_manifest.json"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check_file(rec: dict) -> tuple[str, str]:
    """返回 (状态, 详情)；状态 ∈ ok / skip / fail:<原因>"""
    rel = rec.get("path", "")
    kind = rec.get("kind", "")
    p = ROOT / rel
    if kind == "manifest":
        return ("skip", "self-reference, not hash-checked")
    if not p.exists():
        return ("fail:missing", "文件不在")

    raw = p.read_bytes()
    size = len(raw)
    minb = int(rec.get("min_bytes") or 0)
    if size < minb:
        return ("fail:too-small", f"{size} B < {minb} B")

    got = sha256_bytes(raw)
    want = str(rec.get("sha256") or "").lower()
    eol = ""
    if want and got != want:
        want_lf = str(rec.get("sha256_lf") or "").lower()
        got_lf = sha256_bytes(raw.replace(b"\r\n", b"\n"))
        if want_lf and got_lf == want_lf:
            eol = "（CRLF→LF 归一化后一致，core.autocrlf 造成的行尾差异）"
            got = got_lf
        else:
            return ("fail:sha256", f"本机 {got[:16]}… ≠ agent {want[:16]}…（旧的/被截断的副本）")

    detail = f"sha256 {got[:12]}{eol}"
    metrics = rec.get("metrics") or {}

    if kind in ("docx", "pptx"):
        if not zipfile.is_zipfile(p):
            return ("fail:package", "不是合法的 zip/OOXML 包")
        with zipfile.ZipFile(p) as z:
            bad = z.testzip()
            if bad:
                return ("fail:package", f"包内损坏的成员：{bad}")
            names = z.namelist()
            need = "word/document.xml" if kind == "docx" else "ppt/presentation.xml"
            if need not in names:
                return ("fail:package", f"缺 {need}")
            if kind == "pptx":
                slides = len([n for n in names
                              if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)])
                detail += f" slides={slides}"
                if metrics.get("slides") and slides != int(metrics["slides"]):
                    return ("fail:slides", f"这里数到 {slides} 页，清单写的是 {metrics['slides']} 页")
            else:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
                paras = len(re.findall(r"<w:p[ >/]", xml))
                tbls = len(re.findall(r"<w:tbl[ >/]", xml))
                detail += f" paragraphs={paras} tables={tbls}"
                if metrics.get("paragraphs") and paras != int(metrics["paragraphs"]):
                    return ("fail:paragraphs",
                            f"这里数到 {paras} 段，清单写的是 {metrics['paragraphs']} 段")
                if metrics.get("tables") and tbls != int(metrics["tables"]):
                    return ("fail:tables",
                            f"这里数到 {tbls} 张表，清单写的是 {metrics['tables']} 张")
    elif kind in ("md", "manifest"):
        detail += f" lines={len(raw.decode('utf-8', 'replace').splitlines())}"

    return ("ok", detail)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="dry-run the local deliverable check in the sandbox")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    man_path = Path(a.manifest)
    if not man_path.exists():
        print(f"[WARN] 没有清单 {man_path} —— 先跑 python code/build_deliverables.py")
        return 0
    man = json.loads(man_path.read_text(encoding="utf-8-sig"))

    results = []
    bad = 0
    for rec in man.get("files", []):
        state, detail = check_file(rec)
        results.append({"path": rec.get("path"), "kind": rec.get("kind"),
                        "state": state, "detail": detail})
        if state.startswith("fail"):
            bad += 1

    if str(man.get("verdict")) != "pass":
        print(f"[FAIL] agent 自己把这一轮标成了 {man.get('verdict')!r} —— 不该请本机核验")
        bad += 1

    if a.json:
        print(json.dumps({"manifest": str(man_path), "round": man.get("round"),
                          "would_pass": bad == 0, "failed": bad,
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        print(f"== 预演本机核验（清单 round {man.get('round')}，"
              f"agent 建于 {man.get('generated_at_utc')}）")
        for r in results:
            mark = "OK  " if r["state"] == "ok" else ("SKIP" if r["state"] == "skip" else "FAIL")
            print(f"   [{mark}] {r['path']}\n          {r['detail']}"
                  if r["state"].startswith("fail") else
                  f"   [{mark}] {str(r['path']).ljust(46)} {r['detail']}")
        print(f"== 结论：{'本机那一关会过' if bad == 0 else f'{bad} 项对不上，先修再请本机'}")
        print("== 未预演（只有真本机有意义）：auth.ps1 -Verify / 计划任务零窗口形态 / -Com 真 Office 打开")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
