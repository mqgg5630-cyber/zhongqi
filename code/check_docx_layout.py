#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_docx_layout.py - 估算 .docx 的分页，确认“Ⅲ.评议情况”签字页单独成完整的一页。

本机没有 Word / LibreOffice，无法真的渲染分页，于是按文档自己的设置估算：

  * 一页可用高度 = 纸张高度 - 上下页边距（取正文那一节的 sectPr）
  * 表格行高度 = max(trHeight, 单元格文字估算高度)
    文字高度用真实 CJK 字体（PIL）按列宽换行后逐段累加，行距取 pPr 里的 spacing
  * 逐行填页：一行放不下就换到下一页（Word 对表格行的默认行为）

检查项：
  1) “Ⅲ.评议情况”那一行的段落带 <w:pageBreakBefore/> —— 签字页从新的一页开始
     （--sign-page 模式：文件本身就是签字页，改为要求表格第一行就是 Ⅲ.评议情况）
  2) 从该行到表格末尾所有行的高度之和 <= 一页可用高度 —— 签字页完整、不跨页
  3) 逐行模拟分页时，签字部分没有任何一行被拆到两页
  4) 报告估算总页数、签字页落在第几页、签字页还剩多少空间

Usage
-----
    python code/check_docx_layout.py deliverable/中期.docx
    python code/check_docx_layout.py deliverable/中期检查表_签字页.docx --sign-page
    python code/check_docx_layout.py deliverable/中期.docx --quiet
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

try:
    from PIL import ImageFont
except ImportError:                                  # pragma: no cover
    ImageFont = None

SIGN_LABEL = "Ⅲ.评议情况"
TW = 20                       # 1 pt = 20 twips
MIN_ROW = 24                  # 行高下限（空行 / 边框）
DEFAULT_SIZE_PT = 12.0
DEFAULT_LINE_MULT = 1.15


# --------------------------------------------------------------------------- #
# text metrics
# --------------------------------------------------------------------------- #
def cjk_font(px: int):
    cands = sorted(glob.glob("/tmp/fonts/*CJK*.otf"))
    if not cands or ImageFont is None:
        return None
    return ImageFont.truetype(cands[0], max(int(px), 1))


def line_count(text: str, size_pt: float, box_tw: float) -> int:
    """文字按给定宽度需要几行（CJK 字体逐字换行）。"""
    if not text.strip():
        return 1
    font = cjk_font(size_pt * 96 / 72)
    if font is None:                                  # 没有字体时按字宽粗估
        per_line = max(int(box_tw / (size_pt * TW)), 1)
        return max(1, (len(text) + per_line - 1) // per_line)
    box_px = box_tw / TW * 96 / 72
    lines, cur = 1, ""
    for ch in text:
        if ch == "\n":
            lines += 1
            cur = ""
            continue
        if font.getlength(cur + ch) > box_px and cur:
            lines += 1
            cur = ch
        else:
            cur += ch
    return lines


def para_format(p_el):
    """段落字号 / 行距倍数 / 段前段后（twips）。"""
    ppr = p_el.find(qn("w:pPr"))
    spacing = ppr.find(qn("w:spacing")) if ppr is not None else None

    size_pt = None
    for r in p_el.iter(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is not None and rpr.find(qn("w:sz")) is not None:
            size_pt = float(rpr.find(qn("w:sz")).get(qn("w:val"))) / 2
            break
    if size_pt is None:                               # 空段落：取段落标记的 rPr
        rpr = ppr.find(qn("w:rPr")) if ppr is not None else None
        if rpr is not None and rpr.find(qn("w:sz")) is not None:
            size_pt = float(rpr.find(qn("w:sz")).get(qn("w:val"))) / 2
    if size_pt is None:
        size_pt = DEFAULT_SIZE_PT

    before = after = 0.0
    line_mult = DEFAULT_LINE_MULT
    if spacing is not None:
        before = float(spacing.get(qn("w:before")) or 0)
        after = float(spacing.get(qn("w:after")) or 0)
        ln = spacing.get(qn("w:line"))
        rule = spacing.get(qn("w:lineRule")) or "auto"
        if ln:
            line_mult = (float(ln) / 240.0 if rule == "auto"
                         else (float(ln) / TW) / size_pt)
    return size_pt, max(line_mult, 1.0), before, after


def para_width(p_el, avail_tw: float) -> float:
    """段落可用行宽 = 单元格宽度 - 左右缩进（首行缩进算在行内）。"""
    ppr = p_el.find(qn("w:pPr"))
    ind = ppr.find(qn("w:ind")) if ppr is not None else None
    if ind is None:
        return avail_tw
    left = float(ind.get(qn("w:left")) or 0)
    right = float(ind.get(qn("w:right")) or 0)
    first = float(ind.get(qn("w:firstLine")) or 0)
    return max(avail_tw - left - right - first, avail_tw * 0.25)


def block_height(p_el, avail_tw: float) -> float:
    """一个段落的估算高度（twips）。"""
    size_pt, line_mult, before, after = para_format(p_el)
    text = "".join(t.text or "" for t in p_el.iter(qn("w:t")))
    n = line_count(text, size_pt, para_width(p_el, avail_tw))
    return before + after + n * line_mult * size_pt * TW


# --------------------------------------------------------------------------- #
# table metrics
# --------------------------------------------------------------------------- #
def table_metrics(tbl):
    grid = tbl.find(qn("w:tblGrid"))
    cols = ([int(g.get(qn("w:w"))) for g in grid.findall(qn("w:gridCol"))]
            if grid is not None else [])
    tblpr = tbl.find(qn("w:tblPr"))
    cellmar = {"left": 108, "right": 108}
    if tblpr is not None and tblpr.find(qn("w:tblCellMar")) is not None:
        for side in ("left", "right"):
            el = tblpr.find(qn("w:tblCellMar")).find(qn("w:" + side))
            if el is not None and el.get(qn("w:type")) == "dxa":
                cellmar[side] = int(el.get(qn("w:w")))
    return cols, cellmar


def cell_text_width(tc, col_widths, cellmar) -> float:
    """单元格可用行宽 = 跨列宽度 - 左右单元格边距。"""
    tcpr = tc.find(qn("w:tcPr"))
    gutter = cellmar["left"] + cellmar["right"]
    if tcpr is not None and tcpr.find(qn("w:tcMar")) is not None:
        mar = tcpr.find(qn("w:tcMar"))
        for side in ("left", "right"):
            el = mar.find(qn("w:" + side))
            if el is not None and el.get(qn("w:type")) == "dxa":
                gutter = gutter - cellmar[side] + int(el.get(qn("w:w")))
    span = 1
    if tcpr is not None and tcpr.find(qn("w:gridSpan")) is not None:
        span = int(tcpr.find(qn("w:gridSpan")).get(qn("w:val")))
    return max(sum(col_widths[:span]) - gutter, 400)


def row_height(tr, cols, cellmar) -> float:
    trpr = tr.find(qn("w:trPr"))
    fixed = None
    if trpr is not None and trpr.find(qn("w:trHeight")) is not None:
        el = trpr.find(qn("w:trHeight"))
        val = float(el.get(qn("w:val")))
        if (el.get(qn("w:hRule")) or "atLeast") == "exact":
            return val
        fixed = val
    content = 0.0
    for tc in tr.findall(qn("w:tc")):
        w = cell_text_width(tc, cols, cellmar)
        h = sum(block_height(p, w) for p in tc.findall(qn("w:p")))
        content = max(content, h)
    return max(fixed or 0.0, content, MIN_ROW)


def has_page_break_before(tr) -> bool:
    for p in tr.iter(qn("w:p")):
        ppr = p.find(qn("w:pPr"))
        if ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None:
            return True
    return False


def text_of(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def usable_height_tw(doc) -> float:
    """一页可用高度（twips）= 纸张高度 - 上下页边距。"""
    s = doc.sections[-1]
    return float(s.page_height.twips - s.top_margin.twips - s.bottom_margin.twips)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="估算 .docx 分页，检查签字页")
    ap.add_argument("docx")
    ap.add_argument("--sign-page", action="store_true",
                    help="文件本身就是签字页：要求表格第一行是 Ⅲ.评议情况")
    ap.add_argument("--quiet", action="store_true", help="只打印结论")
    args = ap.parse_args(argv)

    path = Path(args.docx)
    if not path.exists():
        print(f"[ERROR] not found: {path}", file=sys.stderr)
        return 1
    doc = Document(str(path))
    avail = usable_height_tw(doc)
    problems: list[str] = []

    tbls = [el for el in doc.element.body.iterchildren() if el.tag == qn("w:tbl")]
    if not tbls:
        print("[ERROR] no table in the document", file=sys.stderr)
        return 1
    tbl = tbls[-1]
    cols, cellmar = table_metrics(tbl)
    trs = tbl.findall(qn("w:tr"))

    sign_row = next((i for i, tr in enumerate(trs) if SIGN_LABEL in text_of(tr)), None)
    if sign_row is None:
        print(f"[ERROR] no row with {SIGN_LABEL!r}", file=sys.stderr)
        return 1

    print(f"[layout] {path}")
    print(f"  paper {doc.sections[-1].page_width.inches:.2f}x"
          f"{doc.sections[-1].page_height.inches:.2f} in, "
          f"margins T/B {doc.sections[-1].top_margin.inches:.2f}/"
          f"{doc.sections[-1].bottom_margin.inches:.2f} in "
          f"-> 一页可用高度 {avail:.0f} twips = {avail / TW:.0f} pt")
    print(f"  table: {len(trs)} rows x {len(cols)} cols; 签字部分 = row "
          f"{sign_row}—{len(trs) - 1}")

    heights = [row_height(tr, cols, cellmar) for tr in trs]
    breaks = [has_page_break_before(tr) for tr in trs]

    # ---- 逐行填页（估算）
    page, cur, page_of, split_rows = 1, 0.0, [], []
    for i, tr in enumerate(trs):
        h = heights[i]
        if breaks[i] and cur > 0:
            page += 1
            cur = 0.0
        if h > avail:
            split_rows.append(i)
            page += 1
            cur = h % avail
        elif cur + h > avail * 0.999:
            page += 1
            cur = h
        else:
            cur += h
        page_of.append(page)

    if not args.quiet:
        print("  ── 逐行估算（p = 估算页码，pt = 估算行高）")
        for i, tr in enumerate(trs):
            head = text_of(tr).strip().replace("\n", " ")[:30]
            print(f"    r{i:>2}  p{page_of[i]:<2} {heights[i] / TW:>6.0f} pt  {head}"
                  f"{'   ← 段前分页' if breaks[i] else ''}")

    sign_rows = list(range(sign_row, len(trs)))
    sign_h = sum(heights[i] for i in sign_rows)
    sign_pages = sorted({page_of[i] for i in sign_rows})

    # ---- 检查 1：签字页从新的一页开始
    if args.sign_page:
        if trs and SIGN_LABEL in text_of(trs[0]):
            print(f"  OK   {SIGN_LABEL} 就是表格第一行（这是单独一份签字页文件）")
        else:
            problems.append("签字页文件的第一行不是 Ⅲ.评议情况")
            print(f"  FAIL 第一行是 {text_of(trs[0])[:16]!r}，不是 {SIGN_LABEL!r}")
    elif breaks[sign_row]:
        print(f"  OK   row {sign_row} [{SIGN_LABEL}] 带 <w:pageBreakBefore/>："
              f"签字页从新的一页开始")
    else:
        problems.append(f"row {sign_row} [{SIGN_LABEL}] 没有段前分页")
        print(f"  FAIL row {sign_row} [{SIGN_LABEL}] 没有段前分页，签字页不一定单独成页")

    # ---- 检查 2：签字部分装得进一页
    if sign_h <= avail:
        print(f"  OK   签字部分合计 {sign_h:.0f} twips = {sign_h / TW:.0f} pt <= "
              f"一页 {avail:.0f} twips = {avail / TW:.0f} pt"
              f"（占一页 {sign_h / avail * 100:.0f}%，余 "
              f"{(avail - sign_h) / TW:.0f} pt）")
    else:
        problems.append(f"签字部分 {sign_h / TW:.0f} pt 超过一页 {avail / TW:.0f} pt")
        print(f"  FAIL 签字部分 {sign_h / TW:.0f} pt > 一页 {avail / TW:.0f} pt，会跨页")

    # ---- 检查 3：签字部分没有被拆到两页
    if len(sign_pages) == 1 and not any(i in split_rows for i in sign_rows):
        print(f"  OK   签字部分全部落在第 {sign_pages[0]} 页（估算），没有一行被拆开")
    else:
        problems.append(f"签字部分分布在估算的第 {sign_pages} 页")
        print(f"  FAIL 签字部分分布在估算的第 {sign_pages} 页")

    if page_of[-1] == page_of[sign_row]:
        print(f"  估算总页数 {len(set(page_of))}，签字页 = 第 {page_of[sign_row]} 页（最后一页）")
    else:
        print(f"  估算总页数 {len(set(page_of))}，签字页 = 第 {page_of[sign_row]} 页")

    if problems:
        print(f"\nRESULT: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nRESULT: OK - 一页装得下整份签字页" if args.sign_page
          else "\nRESULT: OK - 签字页单独成完整一页")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
