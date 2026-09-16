#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deliverables.py —— 自循环任务的"每一轮"：重生成 docx / pptx → 自检 → 写清单。

一条命令做完一轮的 agent 侧工作（不含 push；push 交给 agent-sync.sh / agent-handsfree.sh）：

    python code/build_deliverables.py                 # 重生成 + 自检 + 写清单 + 跑闸门
    python code/build_deliverables.py --only docx     # 只重生成 docx
    python code/build_deliverables.py --no-build      # 不重生成，只自检 + 写清单（依赖缺失时用）
    python code/build_deliverables.py --keep          # 即使内容与 HEAD 一致也保留新字节（默认还原，避免无意义的二进制 churn）
    python code/build_deliverables.py --no-gate       # 跳过 code/check_all.sh（调试用）

做的事：
  1. 按 code/deliverables.tsv 里 scope=loop 的清单，跑仓库既有的生成脚本
     （build_ops.py → fill_docx.py；make_mech_doc.py；make_ppt_nature.py --mechanism；
       make_ppt_mid.py / --half）——不自造生成逻辑，复用已验收的那一套；
  2. 逐个断言 expect 列（slides= / paras>= / has= / tables>=）与 min_bytes；
  3. 与 HEAD 里的同名文件比"内容指纹"（docx/pptx 抽正文文本，md 比字节）：
     一致 → `git checkout --` 还原原字节（zip 时间戳不同不算改动）；
     不一致 → 保留新文件，记为 promoted（真的改了内容）；
  4. 跑 code/check_all.sh（模板格式零改动 / 口径一致 / PPT 版式 / .ps1 ASCII）；
  5. 写 results/status/agent_manifest.json（每个文件的 bytes + sha256 + 指标 + QA 结论）
     ——本机值守 local_check.ps1 按它逐个核对哈希，证明"产物真的回到了本机且没坏"；
  6. 由同一份 tsv 编译 results/status/success_criteria.json（agent-criteria.sh 与
     local_check.ps1 共用的机读验收标准）；
  7. 往 results/status/LOOP_LOG.md 追加一行人读记录。

退出码：0 全部通过；2 有断言/闸门失败（详情已打印并写进清单）；1 用法或环境错误。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "code" / "deliverables.tsv"
STATUS = ROOT / "results" / "status"
MANIFEST = STATUS / "agent_manifest.json"
CRITERIA = STATUS / "success_criteria.json"
LOOP_LOG = STATUS / "LOOP_LOG.md"
HANDSHAKE = STATUS / "handshake.json"

PY = sys.executable or "python3"


# --------------------------------------------------------------------- 清单
def load_tsv(path: Path = TSV) -> list[dict]:
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 5 or parts[0] == "path":
            continue
        p, kind, minb, expect, scope = parts[0], parts[1], parts[2], parts[3], parts[4]
        note = parts[5] if len(parts) > 5 else ""
        if not re.fullmatch(r"\d+", minb or ""):
            continue
        rows.append({
            "path": p, "kind": kind, "min_bytes": int(minb),
            "expect": [e for e in expect.split(";") if e], "scope": scope, "note": note,
        })
    return rows


# --------------------------------------------------------------- 生成步骤
# (标签, 命令, 产出文件) —— 全部是仓库里已验收的脚本，不改生成逻辑
def build_steps(only: str) -> list[tuple[str, list[str], list[str]]]:
    docx_steps = [
        ("ops:中期", [PY, "code/build_ops.py"], []),
        ("docx:中期", [PY, "code/fill_docx.py", "--ops", "build/ops_中期.json"],
         ["deliverable/中期.docx"]),
        ("docx:中期新", [PY, "code/fill_docx.py", "--ops", "build/ops_中期.json",
                        "--out", "deliverable/中期新.docx"],
         ["deliverable/中期新.docx"]),
        ("docx:机制说明", [PY, "code/make_mech_doc.py"],
         ["deliverable/抗菌肽与AD关联机制说明.docx"]),
        ("md:中间版草稿", [PY, "code/make_mid_content.py"], ["docs/中间版_填写内容.md"]),
        ("ops:中间版", [PY, "code/build_ops.py", "--in", "docs/中间版_填写内容.md",
                       "--out", "build/ops_中间版.json"], []),
        ("docx:中间版", [PY, "code/fill_docx.py", "--ops", "build/ops_中间版.json",
                        "--out", "中间版/中期.docx"], ["中间版/中期.docx"]),
        ("md:中间版2草稿", [PY, "code/make_mid2_content.py"], ["docs/中间版2_填写内容.md"]),
        ("ops:中间版2", [PY, "code/build_ops.py", "--in", "docs/中间版2_填写内容.md",
                        "--out", "build/ops_中间版2.json"], []),
        ("docx:中间版2", [PY, "code/fill_docx.py", "--ops", "build/ops_中间版2.json",
                         "--out", "中间版2/中期.docx"], ["中间版2/中期.docx"]),
    ]
    pptx_steps = [
        ("pptx:H(20页)", [PY, "code/make_ppt_nature.py", "--mechanism"],
         ["deliverable/中期答辩_H_nature风.pptx"]),
        ("pptx:中间版(12页)", [PY, "code/make_ppt_mid.py"],
         ["中间版/中期答辩_H_nature风.pptx"]),
        ("pptx:中间版2(12页)", [PY, "code/make_ppt_mid.py", "--half"],
         ["中间版2/中期答辩_H_nature风.pptx"]),
    ]
    if only == "docx":
        return docx_steps
    if only == "pptx":
        return pptx_steps
    return docx_steps + pptx_steps


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


# ----------------------------------------------------------------- 度量
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def docx_text(path: Path) -> str:
    """正文全文（含 w:sdt 内容控件里的封面栏目）——直接读 XML，不需要 python-docx。

    python-docx 的 doc.paragraphs / cell.text 看不到 w:sdt 包着的单元格
    （中期检查表封面 7 栏正是这种），用它会误判"封面没填"。
    """
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    import html as _html
    return "".join(_html.unescape(t)
                   for t in re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S))


def docx_metrics(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        media = [n for n in z.namelist() if n.startswith("word/media/")]
    text = docx_text(path)
    return {"paragraphs": len(re.findall(r"<w:p[ >/]", xml)),
            "tables": len(re.findall(r"<w:tbl[ >/]", xml)),
            "sdt_controls": len(re.findall(r"<w:sdt[ >/]", xml)),
            "media_files": len(media),
            "chars": len(text)}


def pptx_metrics(path: Path) -> dict:
    from pptx import Presentation
    pr = Presentation(str(path))
    texts, runs = [], 0
    for s in pr.slides:
        for sh in s.shapes:
            if sh.has_text_frame:
                texts.append(sh.text_frame.text)
                runs += len(sh.text_frame.paragraphs)
        if s.has_notes_slide and s.notes_slide.notes_text_frame is not None:
            texts.append(s.notes_slide.notes_text_frame.text)
    return {"slides": len(pr.slides._sldIdLst), "shapes_with_text_runs": runs,
            "text": "\n".join(texts)}


def zip_parts(path: Path) -> dict:
    """不依赖 python-docx/pptx 的兜底度量（本机没装依赖也能核对结构）。"""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    return {
        "parts": len(names),
        "slides": len([n for n in names
                       if n.startswith("ppt/slides/slide") and n.endswith(".xml")]),
        "has_document_xml": "word/document.xml" in names,
        "has_presentation_xml": "ppt/presentation.xml" in names,
    }


def content_sig(path: Path, kind: str) -> str:
    """内容指纹：docx/pptx 抽正文文本（忽略 zip 时间戳），md 直接比字节。"""
    if not path.exists():
        return ""
    if kind == "docx":
        try:
            return "docx:" + hashlib.md5(docx_text(path).encode("utf-8")).hexdigest()
        except Exception:
            return "zip:" + hashlib.md5(b"".join(
                sorted(zipfile.ZipFile(path).namelist()))).hexdigest()
    if kind == "pptx":
        try:
            m = pptx_metrics(path)
            return "pptx:%d:%s" % (m["slides"],
                                   hashlib.md5(m["text"].encode("utf-8")).hexdigest())
        except Exception:
            return "zip:" + hashlib.md5(b"".join(
                sorted(zipfile.ZipFile(path).namelist()))).hexdigest()
    return "bytes:" + sha256(path)


def head_bytes(rel: str) -> bytes | None:
    proc = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(ROOT),
                          capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def head_sig(rel: str, kind: str) -> str:
    raw = head_bytes(rel)
    if raw is None:
        return ""
    tmp = ROOT / "build" / "_head_cmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(raw)
    try:
        return content_sig(tmp, kind)
    finally:
        tmp.unlink(missing_ok=True)


# ----------------------------------------------------------------- 断言
def check_expect(rel: str, row: dict, text: str | None, metrics: dict) -> list[str]:
    fails: list[str] = []
    size = (ROOT / rel).stat().st_size
    if size < row["min_bytes"]:
        fails.append(f"太小 {size} B < {row['min_bytes']} B")
    for e in row["expect"]:
        if e.startswith("slides="):
            want = int(e.split("=", 1)[1])
            got = metrics.get("slides")
            if got != want:
                fails.append(f"slides={got}，应为 {want}")
        elif e.startswith("paras>="):
            want = int(e.split(">=", 1)[1])
            got = metrics.get("paragraphs")
            if got is None:
                got = len([l for l in (text or "").splitlines() if l.strip()])
            if got < want:
                fails.append(f"paras={got} < {want}")
        elif e.startswith("tables>="):
            want = int(e.split(">=", 1)[1])
            got = metrics.get("tables", 0)
            if got < want:
                fails.append(f"tables={got} < {want}")
        elif e.startswith("has="):
            needle = e.split("=", 1)[1]
            if needle not in (text or ""):
                fails.append(f"正文里找不到 {needle!r}")
        else:
            fails.append(f"无法解析的断言：{e}")
    return fails


# ------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="regenerate + verify the loop deliverables")
    ap.add_argument("--only", choices=["all", "docx", "pptx"], default="all")
    ap.add_argument("--no-build", action="store_true", help="不重生成，只自检 + 写清单")
    ap.add_argument("--no-gate", action="store_true", help="跳过 code/check_all.sh")
    ap.add_argument("--keep", action="store_true",
                    help="内容与 HEAD 一致时也保留新字节（默认还原原文件）")
    ap.add_argument("--round", default="", help="轮次标签（默认取 handshake.round+1）")
    ap.add_argument("--manifest", default=str(MANIFEST))
    a = ap.parse_args(argv)

    rows = load_tsv()
    loop_rows = [r for r in rows if r["scope"] in ("loop", "source")]
    all_rows = rows

    # 轮次标签：handshake 里当前轮 + 1（agent-check.sh --request 会把远端轮次 +1）
    rnd = a.round
    if not rnd:
        cur = 0
        if HANDSHAKE.exists():
            try:
                cur = int(json.loads(HANDSHAKE.read_text(encoding="utf-8-sig")).get("round") or 0)
            except Exception:
                cur = 0
        rnd = str(cur + 1)

    print(f"== build_deliverables  round {rnd}  only={a.only} "
          f"build={'no' if a.no_build else 'yes'} gate={'no' if a.no_gate else 'yes'}")

    steps_log: list[dict] = []
    build_ok = True
    if not a.no_build:
        for label, cmd, outs in build_steps(a.only):
            code, out = run(cmd)
            tail = " | ".join([l for l in out.splitlines() if l.strip()][-2:])[:300]
            steps_log.append({"step": label, "cmd": " ".join(cmd),
                              "exit": code, "tail": tail})
            mark = "OK " if code == 0 else "FAIL"
            print(f"  [{mark}] {label}: {tail or '(no output)'}")
            if code != 0:
                build_ok = False
    else:
        print("  [SKIP] --no-build：不重生成，直接自检现有文件")

    # ------------------------------------------------ 逐文件度量 + 断言 + 复现性
    files: list[dict] = []
    fails: list[str] = []
    promoted: list[str] = []
    restored: list[str] = []

    for row in all_rows:
        rel, kind = row["path"], row["kind"]
        p = ROOT / rel
        rec: dict = {"path": rel, "kind": kind, "scope": row["scope"],
                     "min_bytes": row["min_bytes"], "note": row["note"]}
        if kind == "manifest":
            # the manifest lists itself - a self-hash can never match, so it is
            # only reported (the local side skips it the same way)
            rec["status"] = "self-reference"
            rec["bytes"] = p.stat().st_size if p.exists() else 0
            files.append(rec)
            continue
        if not p.exists():
            rec["status"] = "missing"
            fails.append(f"缺席：{rel}")
            files.append(rec)
            continue
            rec["status"] = "missing"
            fails.append(f"缺席：{rel}")
            files.append(rec)
            continue

        # 度量：能用 python-docx / python-pptx 就抽正文；缺依赖退回 zip 结构；
        # 打不开 = 文件坏了，直接判失败
        text, metrics = None, {}
        try:
            if kind == "docx":
                text = docx_text(p)
                metrics = docx_metrics(p)
            elif kind == "pptx":
                metrics = pptx_metrics(p)
                text = metrics.pop("text", "")
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
                metrics = {"paragraphs": len([l for l in text.splitlines() if l.strip()])}
        except ModuleNotFoundError as exc:
            rec["deps_missing"] = str(exc)
            if kind in ("docx", "pptx"):
                try:
                    metrics = zip_parts(p)
                except Exception as exc2:
                    fails.append(f"打不开 {rel}: {exc2}")
                    rec["status"] = "corrupt"
                    files.append(rec)
                    continue
        except Exception as exc:
            fails.append(f"打不开 {rel}: {exc}")
            rec["status"] = "corrupt"
            files.append(rec)
            continue

        ef = check_expect(rel, row, text, metrics)
        for m in ef:
            fails.append(f"{rel}: {m}")
        rec.update({"bytes": p.stat().st_size, "sha256": sha256(p),
                    "metrics": metrics, "assert_fails": ef,
                    "status": "ok" if not ef else "assert-failed"})

        # 复现性：与 HEAD 比内容指纹（只对这一轮真正重新生成过的文件有意义）
        if kind in ("docx", "pptx", "md") and row["scope"] == "loop" and not a.no_build:
            hs = head_sig(rel, kind)
            ws = content_sig(p, kind)
            if not hs:
                rec["reproducibility"] = "new-file"
                promoted.append(rel)
            elif hs == ws:
                rec["reproducibility"] = "identical-to-HEAD"
                if not a.keep:
                    subprocess.run(["git", "checkout", "--", rel], cwd=str(ROOT),
                                   capture_output=True)
                    rec["bytes"] = p.stat().st_size
                    rec["sha256"] = sha256(p)
                    restored.append(rel)
            else:
                rec["reproducibility"] = "content-changed"
                promoted.append(rel)
        files.append(rec)

    # ---------------------------------------------------------------- 闸门
    gate = {"ran": False, "exit": None, "tail": ""}
    if not a.no_gate:
        code, out = run(["bash", "code/check_all.sh"])
        gate = {"ran": True, "exit": code,
                "tail": "\n".join(out.splitlines()[-25:])}
        print(f"  [{'OK ' if code == 0 else 'FAIL'}] 闸门 code/check_all.sh (exit {code})")
        if code != 0:
            fails.append(f"code/check_all.sh 失败 (exit {code})")
            print("\n".join("      " + l for l in out.splitlines()[-20:]))

    # ---------------------------------------------------------------- 清单
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True).stdout.strip()
    verdict = "pass" if (build_ok and not fails) else "fail"
    manifest = {
        "round": rnd,
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "branch": branch,
        "base_commit": head,
        "generator": "code/build_deliverables.py",
        "toolchain": {"python": sys.version.split()[0],
                      "python_docx": _mod_ver("docx"), "python_pptx": _mod_ver("pptx")},
        "only": a.only,
        "rebuilt": not a.no_build,
        "verdict": verdict,
        "steps": steps_log,
        "qa": {"gate_exit": gate["exit"], "gate_tail": gate["tail"],
               "assert_fails": fails,
               "promoted": promoted, "restored_identical": restored},
        "files": files,
        "_read_me": "本机值守 code/local_check.ps1 会逐个核对 files[].sha256 —— "
                    "哈希对上就说明这一轮的 docx/pptx 完整地回到了本机。",
    }
    man_path = Path(a.manifest)
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    # ------------------------------------------- success_criteria.json（同一份 tsv 编译）
    crit = {
        "description": "自循环验收标准（由 code/deliverables.tsv 编译，勿手改；改 tsv 后重跑 build_deliverables.py）",
        "require_files": [r["path"] for r in loop_rows] +
                         [r["path"] for r in rows if r["scope"] == "fixed"],
        "min_bytes": {r["path"]: r["min_bytes"] for r in rows},
        "require_contains": {"results/status/agent_manifest.json": '"verdict": "pass"'},
    }
    CRITERIA.parent.mkdir(parents=True, exist_ok=True)
    CRITERIA.write_text(json.dumps(crit, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    # ---------------------------------------------------------------- 轮次日志
    LOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = (f"| {rnd} | {manifest['generated_at_utc']} | agent | {verdict} | "
            f"重生成 {len(steps_log)} 步 / 内容变更 {len(promoted)} 个 / "
            f"与 HEAD 一致 {len(restored)} 个 | "
            f"{'; '.join(fails[:3]) if fails else '断言与闸门全部通过'} |\n")
    if not LOOP_LOG.exists():
        LOOP_LOG.write_text(
            "# 自循环轮次日志（docx / pptx）\n\n"
            "agent 侧每轮由 `code/build_deliverables.py` 追加一行；本机侧的结论见 "
            "`results/status/check_r*_*.txt` 与 `handshake.json`。\n\n"
            "| 轮次 | 时间(UTC) | 侧 | 结论 | 摘要 | 备注 |\n"
            "|---|---|---|---|---|---|\n", encoding="utf-8")
    with LOOP_LOG.open("a", encoding="utf-8") as f:
        f.write(line)

    print("")
    print(f"== 清单：{man_path.relative_to(ROOT)}  (files={len(files)})")
    print(f"== 验收标准：{CRITERIA.relative_to(ROOT)}")
    print(f"== 内容变更（promoted）：{promoted or '无'}")
    print(f"== 与 HEAD 一致（已还原原字节）：{len(restored)} 个")
    if fails:
        print(f"== 失败 {len(fails)} 条：")
        for m in fails[:20]:
            print("   - " + m)
        return 2
    print("== RESULT: 本轮 docx/pptx 重生成 + 自检全部通过")
    return 0


def _mod_ver(name: str) -> str:
    try:
        mod = __import__(name)
        return getattr(mod, "__version__", "installed")
    except Exception:
        return "missing"


if __name__ == "__main__":
    raise SystemExit(main())
