#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_ops.py - turn the editable draft (deliverable/中期检查表_填写内容.md) into
the ops.json that fill_docx.py applies to the school template.

Draft format
------------
    # 论文题目
    基于深度学习的……            <- one line, goes into the 论文题目 cell

    ## 1. 论文研究主要内容及工作进度
    正文段落一                    <- one paragraph per line
    !（一）小标题                 <- leading "!" = bold paragraph
    ## 2. 阶段性成果
    ## 3. 公开发表学术论文情况
    ## 4. 尚需完成的研究工作（包括内容、方案）

Blank lines are ignored. Section numbers map to the table rows of the school
form (sources/中期.docx, table index 22, column 0):
    ## 1. -> row 2    ## 2. -> row 3    ## 3. -> row 4    ## 4. -> row 5

Usage
-----
    python code/build_ops.py                       # writes build/ops_中期.json
    python code/build_ops.py --in X.md --out Y.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# section number -> (table index, row, col) in the school template
SECTION_MAP = {
    "1": (22, 2, 0),
    "2": (22, 3, 0),
    "3": (22, 4, 0),
    "4": (22, 5, 0),
}
TITLE_CELL = (22, 0, 3)      # 论文题目 fill-in cell
TEMPLATE = "sources/中期.docx"
OUTPUT = "deliverable/中期.docx"


def parse(md_path: Path):
    title = None
    sections: dict[str, list[tuple[str, bool]]] = {}
    cur = None
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("## "):
            head = line[3:].strip()
            m = re.match(r"(\d)", head)
            if not m or m.group(1) not in SECTION_MAP:
                print(f"[warn] unknown section heading: {head!r}", file=sys.stderr)
                cur = None
                continue
            cur = m.group(1)
            sections.setdefault(cur, [])
            continue
        if line.startswith("# "):
            cur = None
            continue
        if cur is None:
            # the "# 论文题目" block: first non-empty line is the title
            if title is None and not line.startswith("!") and not line.startswith("#"):
                title = line.strip()
            continue
        bold = line.startswith("!")
        text = line[1:].strip() if bold else line.strip()
        sections[cur].append((text, bold))

    ops = []
    if title:
        ops.append({
            "op": "fill_cell", "table": TITLE_CELL[0], "row": TITLE_CELL[1],
            "col": TITLE_CELL[2], "keep_before": 0, "texts": [title],
        })
    for key in ("1", "2", "3", "4"):
        items = sections.get(key) or []
        if not items:
            print(f"[warn] section {key} is empty", file=sys.stderr)
            continue
        t, r, c = SECTION_MAP[key]
        ops.append({
            "op": "fill_cell", "table": t, "row": r, "col": c,
            "keep_before": 1,                       # keep "1. 论文研究主要内容及工作进度："
            "texts": [x[0] for x in items],
            "bold": [i for i, x in enumerate(items) if x[1]],
        })
    return {"docx": TEMPLATE, "out": OUTPUT, "ops": ops}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="draft markdown -> fill_docx ops.json")
    ap.add_argument("--in", dest="src", default="deliverable/中期检查表_填写内容.md")
    ap.add_argument("--out", dest="dst", default="build/ops_中期.json")
    args = ap.parse_args(argv)

    src = Path(args.src)
    if not src.exists():
        print(f"[ERROR] not found: {src}", file=sys.stderr)
        return 1

    spec = parse(src)
    dst = Path(args.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(o["texts"]) for o in spec["ops"])
    print(f"wrote {dst}: {len(spec['ops'])} ops, {total} paragraphs")
    for o in spec["ops"]:
        print(f"  table {o['table']} r{o['row']}c{o['col']}: {len(o['texts'])} paragraphs, "
              f"{len(o.get('bold', []))} bold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
