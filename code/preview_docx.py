#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_docx.py - 把 .docx 的分页画成图片，方便看排版（本机没有 Word）。

它只画“结构”，不追求和 Word 像素级一致：用 check_docx_layout.py 的估算高度
逐行填页，把每一页画成一张图 —— 表格行画成方框、单元格用细线分格、文字按列宽
换行写进去，页面尺寸 / 页边距按文档自己的设置。看的是：

  * 一共有几页，每一页装了哪些内容
  * 哪一行跨页（页与页之间断开）
  * 签字页是不是单独一整页

Usage
-----
    python code/preview_docx.py deliverable/中期.docx -o results/docx_preview/完整版
    python code/preview_docx.py deliverable/中期检查表_签字页.docx -o /tmp/sign --sheet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docx_layout as L                       # noqa: E402  （共用同一套估算）

DPI = 96
SCALE = 1.0
INK = (34, 34, 34)
GRID = (150, 150, 150)
ROW_BG = (248, 248, 248)
SIGN_BG = (255, 249, 240)
NOTE = (120, 120, 120)
ACCENT = (176, 64, 40)


def px(tw: float) -> float:
    return tw / L.TW * DPI / 72


def cell_texts(tc):
    out = []
    for p in tc.findall(qn("w:p")):
        txt = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        size_pt, mult, before, after = L.para_format(p)
        if txt:
            out.append((txt, size_pt, mult, before / L.TW, after / L.TW))
        else:
            out.append(("", size_pt, mult, before / L.TW, after / L.TW))
    return out


def draw_row(draw, tr, x0, y0, width, cols, cellmar, height, sign=False, max_y=None):
    """画一行：按 trHeight / 估算高度画框，单元格按 gridSpan 分格，文字逐行写。"""
    y = y0
    tcs = tr.findall(qn("w:tc"))
    span_sum = 0
    for tc in tcs:
        tcpr = tc.find(qn("w:tcPr"))
        span = 1
        if tcpr is not None and tcpr.find(qn("w:gridSpan")) is not None:
            span = int(tcpr.find(qn("w:gridSpan")).get(qn("w:val")))
        cw = width * (sum(cols[span_sum:span_sum + span]) / sum(cols))
        cx = x0 + width * (sum(cols[:span_sum]) / sum(cols))
        span_sum += span
        draw.rectangle([cx, y0, cx + cw, y0 + height],
                       fill=SIGN_BG if sign else ROW_BG, outline=GRID)
        pad = px(cellmar["left"])
        ty = y0 + 2
        for txt, size, mult, before, after in cell_texts(tc):
            ty += px(before * L.TW)
            font = L.cjk_font(size * DPI / 72)
            if not txt:
                ty += size * mult * DPI / 72
                continue
            line_h = size * mult * DPI / 72
            cur = ""
            for ch in txt:
                if not font:
                    break
                if font.getlength(cur + ch) > cw - 2 * pad and cur:
                    if ty > y0 + height - line_h * 0.2:
                        break
                    draw.text((cx + pad, ty), cur, font=font, fill=INK)
                    ty += line_h
                    cur = ch
                else:
                    cur += ch
            if cur and font:
                draw.text((cx + pad, ty), cur, font=font, fill=INK)
                ty += line_h
            ty += px(after * L.TW)


def render(path: Path, out_dir: Path, sheet: bool = False):
    doc = Document(str(path))
    out_dir.mkdir(parents=True, exist_ok=True)
    avail = L.usable_height_tw(doc)
    s = doc.sections[-1]
    pw, ph = px(s.page_width.twips), px(s.page_height.twips)
    ml, mt = px(s.left_margin.twips), px(s.top_margin.twips)
    mw = pw - px(s.left_margin.twips) - px(s.right_margin.twips)

    tbl = [el for el in doc.element.body.iterchildren() if el.tag == qn("w:tbl")][-1]
    cols, cellmar = L.table_metrics(tbl)
    trs = tbl.findall(qn("w:tr"))
    sign_row = next((i for i, tr in enumerate(trs) if L.SIGN_LABEL in L.text_of(tr)), len(trs))
    heights = [L.row_height(tr, cols, cellmar) for tr in trs]

    # 高度统一换算成像素（估算用 twips 比较，画图用像素）
    hpx = [px(h) for h in heights]
    avail_px = px(avail)
    pages, cur, used = [], [], 0.0
    for i, tr in enumerate(trs):
        h = heights[i]
        brk = L.has_page_break_before(tr)
        if (brk and cur) or (cur and used + h > avail * 0.999):
            pages.append(cur)
            cur, used = [], 0.0
        rest, part = h, 0
        while rest > avail * 0.999:        # 比一页还高：一页一页画满，剩下的标"续"
            if cur:
                pages.append(cur)
                cur, used = [], 0.0
            pages.append([(i, avail_px, part > 0)])
            rest -= avail
            part += 1
        if rest > 0:
            cur.append((i, px(rest), part > 0))
            used += rest
    if cur:
        pages.append(cur)

    files = []
    for pno, rows in enumerate(pages, 1):
        img = Image.new("RGB", (int(pw), int(ph)), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([ml, mt, ml + mw, mt + px(avail)], outline=(220, 220, 220))
        hdr = L.cjk_font(11)
        draw.text((ml, mt - 22), f"{path.name}  第 {pno} / {len(pages)} 页（估算）",
                  font=hdr, fill=NOTE)
        y = mt
        for item in rows:
            i, h = item[0], item[1]
            continuation = len(item) > 2 and item[2]
            if continuation:                          # 上一页放不下的部分
                draw_row(draw, trs[i], ml, mt, mw, cols, cellmar, h,
                         sign=i >= sign_row)
                draw.text((ml + 6, mt + 2), f"…第 {i + 1} 行续（上一页放不下）",
                          font=hdr, fill=ACCENT)
                continue
            draw_row(draw, trs[i], ml, y, mw, cols, cellmar, h, sign=i >= sign_row)
            draw.rectangle([ml - 5, y, ml - 2, y + h],
                           fill=ACCENT if i >= sign_row else (200, 200, 200))
            y += h
        if any(item[0] >= sign_row for item in rows):
            draw.text((ml, mt + px(avail) + 6),
                  "橙色底色 = 签字页（Ⅲ.评议情况：检查小组成员 / 检查意见 / 组长签字 / 单位盖章）",
                      font=hdr, fill=ACCENT)
        fp = out_dir / f"page-{pno:02d}.png"
        img.save(fp)
        files.append(fp)
        print(f"wrote {fp}  ({len(rows)} rows)")

    if sheet and files:
        ims = [Image.open(f).convert("RGB") for f in files]
        gap = 24
        w = sum(i.width for i in ims) + gap * (len(ims) - 1)
        h = max(i.height for i in ims)
        sh = Image.new("RGB", (w, h), "white")
        x = 0
        for im in ims:
            sh.paste(im, (x, 0))
            x += im.width + gap
        sp = out_dir / "全部页.png"
        sh.save(sp)
        print(f"wrote {sp}  ({len(files)} pages)")
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 .docx 的分页画成图片（估算）")
    ap.add_argument("docx")
    ap.add_argument("-o", "--out", default="results/docx_preview")
    ap.add_argument("--sheet", action="store_true", help="再拼一张全部页的图")
    args = ap.parse_args(argv)

    p = Path(args.docx)
    if not p.exists():
        print(f"[ERROR] not found: {p}", file=sys.stderr)
        return 1
    render(p, Path(args.out), sheet=args.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
