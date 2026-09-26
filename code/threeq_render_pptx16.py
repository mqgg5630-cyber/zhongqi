# -*- coding: utf-8 -*-
"""PPTX renderer for the focused three-question deck.

All visible text is explicitly rendered at 16 pt or larger. Dense content is
split into short tables or separate slides instead of shrinking the font.
"""
import re
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

BLUE = RGBColor(0x10, 0x30, 0x5A)
BLUE2 = RGBColor(0x1F, 0x4E, 0x79)
GOLD = RGBColor(0xD0, 0xA6, 0x2C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1F, 0x29, 0x37)
GRAY = RGBColor(0x5B, 0x66, 0x77)
LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
LIGHT2 = RGBColor(0xE7, 0xEE, 0xF6)
EA = "Microsoft YaHei"
CITE_RE = re.compile(r"\[\[([^\]]+)\]\]")
MIN_VISIBLE_PT = 16


def resolve(text, seen):
    def rep(m):
        return "[" + "，".join(str(seen.get(k.strip(), "?")) for k in m.group(1).split(",")) + "]"
    return CITE_RE.sub(rep, str(text or ""))


def tb(slide, x, y, w, h, align=PP_ALIGN.LEFT):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    tf.paragraphs[0].alignment = align
    return tf


def run(p, text, size=18, bold=False, color=DARK, italic=False):
    size = max(MIN_VISIBLE_PT, size)
    r = p.add_run()
    r.text = str(text)
    r.font.name = EA
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    return r


def rect(slide, x, y, w, h, fill, line=None, radius=False):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                   Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
    return shape


def footer(slide, page, meta):
    rect(slide, 0.6, 6.98, 12.13, 0.025, RGBColor(0xD5, 0xDB, 0xE2))
    tf = tb(slide, 0.62, 7.05, 10.5, 0.38)
    run(tf.paragraphs[0], meta["footer_left"], size=16, color=GRAY)
    tf2 = tb(slide, 11.0, 7.05, 1.7, 0.38, PP_ALIGN.RIGHT)
    run(tf2.paragraphs[0], "第 %d 页" % page, size=16, color=GRAY)


def title(slide, text, sub=None, seen=None):
    text = resolve(text, seen or {})
    rect(slide, 0.6, 0.42, 0.14, 0.68, GOLD)
    tf = tb(slide, 0.88, 0.32, 11.8, 0.72)
    run(tf.paragraphs[0], text, size=26, bold=True, color=BLUE)
    if sub:
        tf2 = tb(slide, 0.9, 1.08, 11.8, 0.38)
        run(tf2.paragraphs[0], resolve(sub, seen or {}), size=17, color=GRAY)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text or ""


def cover(prs, meta):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, 13.333, 7.5, BLUE)
    rect(slide, 1.0, 1.25, 2.3, 0.13, GOLD)
    tf = tb(slide, 1.0, 1.65, 11.3, 1.2)
    run(tf.paragraphs[0], meta["title"], size=36, bold=True, color=WHITE)
    tf2 = tb(slide, 1.0, 2.95, 11.3, 0.75)
    run(tf2.paragraphs[0], meta["subtitle"], size=21, color=RGBColor(0xD9, 0xE2, 0xEC))
    rect(slide, 1.0, 4.0, 11.3, 0.75, RGBColor(0x1B, 0x4B, 0x84), radius=True)
    tf3 = tb(slide, 1.2, 4.16, 10.9, 0.42)
    run(tf3.paragraphs[0], meta["claim"], size=17, bold=True, color=RGBColor(0xF0, 0xD9, 0x8A))
    tf4 = tb(slide, 1.0, 5.05, 11.3, 1.4)
    for i, line in enumerate(meta["meta_lines"][:3]):
        p = tf4.paragraphs[0] if i == 0 else tf4.add_paragraph()
        p.space_after = Pt(7)
        run(p, line, size=16, color=RGBColor(0xC8, 0xD4, 0xE2))
    notes(slide, "封面：本报告只回答三问，并把 AChE-Aβ 分子动力学与 AMP-Aβ 交叉成核放到问题一的分子机制部分。")
    return slide


def section(prs, spec, meta, page):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, 13.333, 7.5, BLUE)
    tf = tb(slide, 0.95, 1.35, 11.4, 0.98)
    run(tf.paragraphs[0], spec.get("num", ""), size=44, bold=True, color=GOLD)
    rect(slide, 0.95, 2.45, 1.9, 0.11, GOLD)
    tf2 = tb(slide, 0.95, 2.78, 11.3, 1.2)
    run(tf2.paragraphs[0], spec["title"], size=34, bold=True, color=WHITE)
    tf3 = tb(slide, 0.95, 4.35, 11.4, 0.8)
    run(tf3.paragraphs[0], spec.get("sub", ""), size=20, color=RGBColor(0xD8, 0xE0, 0xEA))
    tf4 = tb(slide, 0.95, 6.55, 11.4, 0.5)
    run(tf4.paragraphs[0], meta["footer_left"], size=16, color=RGBColor(0xA8, 0xB8, 0xC9))
    notes(slide, "进入章节：" + spec["title"] + "。" + spec.get("sub", ""))
    return slide


def bullets(prs, spec, seen, meta, page):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, spec["title"], spec.get("sub"), seen)
    tf = tb(slide, 0.78, 1.55, 11.8, 5.15)
    for i, item in enumerate(spec["bullets"]):
        level, text = item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10 if level == 0 else 6)
        p.line_spacing = 1.12
        p.level = 0
        marker = "● " if level == 0 else "— "
        run(p, marker + resolve(text, seen), size=19 if level == 0 else 17,
            bold=(level == 0), color=BLUE if level == 0 else DARK)
    footer(slide, page, meta)
    notes(slide, spec.get("note", "逐条解释：" + "；".join(t for _, t in spec["bullets"])))
    return slide


def estimate_lines(text, chars_per_line):
    return max(1, (len(str(text)) + chars_per_line - 1) // chars_per_line)


def table_groups(table):
    header = table["header"]
    rows = table["rows"]
    ncol = len(header)
    cpl = max(8, int(12.0 / ncol * 72 / 16 * 0.62))
    groups, cur, cur_lines = [], [], 1
    for row in rows:
        row_lines = max(1, max(estimate_lines(c, cpl) for c in row))
        # 3 rows is the safe default at 16 pt; split earlier for long cells.
        if cur and (len(cur) >= 3 or cur_lines + row_lines > 10):
            groups.append(cur)
            cur, cur_lines = [], 1
        cur.append(row)
        cur_lines += row_lines
    if cur:
        groups.append(cur)
    return groups


def table_slide(prs, spec, table, seen, meta, page, part, parts):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    suffix = "（%d/%d）" % (part, parts) if parts > 1 else ""
    title(slide, spec["title"] + suffix, spec.get("sub"), seen)
    header = [resolve(x, seen) for x in table["header"]]
    rows = [[resolve(x, seen) for x in row] for row in table["rows"]]
    ncol = len(header)
    nrow = len(rows) + 1
    top = 1.55
    height = 5.25
    shape = slide.shapes.add_table(nrow, ncol, Inches(0.6), Inches(top), Inches(12.13), Inches(height))
    tbl = shape.table
    # Keep the first column slightly wider for labels.
    if ncol >= 3:
        tbl.columns[0].width = Inches(2.05)
        rest = (12.13 - 2.05) / (ncol - 1)
        for j in range(1, ncol):
            tbl.columns[j].width = Inches(rest)
    for j, h in enumerate(header):
        cell = tbl.cell(0, j)
        cell.text = ""
        cell.fill.solid(); cell.fill.fore_color.rgb = BLUE
        cell.margin_left = Inches(0.07); cell.margin_right = Inches(0.07)
        cell.margin_top = Inches(0.05); cell.margin_bottom = Inches(0.05)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run(p, h, size=16, bold=True, color=WHITE)
    for i, row in enumerate(rows, 1):
        for j in range(ncol):
            cell = tbl.cell(i, j)
            cell.text = ""
            cell.fill.solid(); cell.fill.fore_color.rgb = LIGHT if i % 2 else WHITE
            cell.margin_left = Inches(0.07); cell.margin_right = Inches(0.07)
            cell.margin_top = Inches(0.05); cell.margin_bottom = Inches(0.05)
            cell.vertical_anchor = MSO_ANCHOR.TOP
            p = cell.text_frame.paragraphs[0]
            txt = row[j] if j < len(row) else ""
            run(p, txt, size=16, color=DARK)
    footer(slide, page, meta)
    notes(slide, spec.get("note", "读表顺序：先说明表头，再按行解释证据与边界。"))
    return slide


def closing(prs, spec, meta, page):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, 13.333, 7.5, BLUE)
    rect(slide, 1.0, 1.55, 2.3, 0.13, GOLD)
    tf = tb(slide, 1.0, 1.95, 11.3, 0.7)
    run(tf.paragraphs[0], "三问版最终结论", size=32, bold=True, color=WHITE)
    tf2 = tb(slide, 1.0, 3.0, 11.4, 2.6)
    for i, line in enumerate(spec["lines"]):
        p = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
        p.space_after = Pt(12)
        run(p, "● " + line, size=19, color=RGBColor(0xDC, 0xE4, 0xEE))
    tf3 = tb(slide, 1.0, 6.55, 11.4, 0.5)
    run(tf3.paragraphs[0], meta["footer_left"], size=16, color=RGBColor(0xA8, 0xB8, 0xC9))
    notes(slide, "结束：主路径是肠道生态和肠脑轴；AChE-Aβ、交叉成核和 BBB 是分层验证，不越级做因果结论。")
    return slide


def render(slides, tables, seen, meta, out_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    page = 0
    for spec in slides:
        typ = spec["type"]
        if typ == "cover":
            page += 1; cover(prs, meta)
        elif typ == "section":
            page += 1; section(prs, spec, meta, page)
        elif typ == "bullets":
            page += 1; bullets(prs, spec, seen, meta, page)
        elif typ == "table":
            table = tables.get(spec["ref"])
            if table is None:
                page += 1
                bullets(prs, {"title": spec["title"], "sub": "table missing", "bullets": [(0, "No table data found")]}, seen, meta, page)
            else:
                groups = table_groups(table)
                for i, rows in enumerate(groups, 1):
                    page += 1
                    part_table = dict(table)
                    part_table["rows"] = rows
                    table_slide(prs, spec, part_table, seen, meta, page, i, len(groups))
        elif typ == "closing":
            page += 1; closing(prs, spec, meta, page)
    prs.save(out_path)
    return page
