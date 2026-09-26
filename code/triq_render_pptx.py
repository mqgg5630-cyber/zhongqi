# -*- coding: utf-8 -*-
"""三问·计算版：PPTX 渲染器（原生形状 + 原生表格 + 演讲备注 + 表格自动分页）。"""
import re
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

BLUE = RGBColor(0x10, 0x30, 0x5A)
BLUE_L = RGBColor(0x1B, 0x4B, 0x84)
GOLD = RGBColor(0xC9, 0xA2, 0x27)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1F, 0x29, 0x37)
GRAY = RGBColor(0x5B, 0x66, 0x77)
LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
EA = "微软雅黑"

CITE_RE = __import__("re").compile(r"\[\[([^\]]+)\]\]")


def _resolve(text, seen):
    def rep(m):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        return "[" + "，".join(str(seen.get(k, "?")) for k in keys) + "]"
    return CITE_RE.sub(rep, text or "")


def _tb(slide, x, y, w, h, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].alignment = align
    return tf


def _run(p, text, size=14, bold=False, color=DARK, italic=False, font=EA):
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = font
    return r


def _rect(slide, x, y, w, h, fill, line=None):
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
    sh.shadow.inherit = False
    return sh


def _footer(slide, page, meta):
    _rect(slide, 0.6, 7.05, 12.13, 0.02, RGBColor(0xD5, 0xDB, 0xE2))
    tf = _tb(slide, 0.6, 7.08, 9.0, 0.3)
    _run(tf.paragraphs[0], meta["footer_left"], size=9, color=GRAY)
    tf2 = _tb(slide, 10.0, 7.08, 2.73, 0.3, align=PP_ALIGN.RIGHT)
    _run(tf2.paragraphs[0], "第 %d 页" % page, size=9, color=GRAY)


def _title(slide, title, sub=None):
    _rect(slide, 0.6, 0.45, 0.13, 0.62, GOLD)
    tf = _tb(slide, 0.85, 0.36, 11.9, 0.8)
    p = tf.paragraphs[0]
    _run(p, title, size=25, bold=True, color=BLUE)
    if sub:
        tf2 = _tb(slide, 0.87, 1.05, 11.9, 0.35)
        _run(tf2.paragraphs[0], sub, size=12, color=GRAY)


def _notes(slide, text):
    if not text:
        return
    slide.notes_slide.notes_text_frame.text = text


def _est_row_height_in(row, ncol, fs):
    """粗估一行需要的高度（英寸）：按最长单元格折行数估算。"""
    col_w_in = 12.13 / ncol
    chars_per_line = max(5, int((col_w_in * 72) / (fs * 0.92) * 0.85))  # 0.85 安全系数
    lines = 1
    for cell in row:
        txt = str(cell)
        need = 0
        for seg in txt.split("\n"):
            for part in re.split(r"[；;]", seg):
                need += max(1, -(-len(part) // chars_per_line))
        lines = max(lines, need)
    return lines * (fs * 1.32 / 72.0) + 0.04


def split_table_rows(table, seen):
    """把一张表按可用高度切成若干段，返回 [(rows_slice, fs_unused)] 列表。"""
    header = [_resolve(str(h), seen) for h in table["header"]]
    rows = [[_resolve(str(c), seen) for c in row] for row in table["rows"]]
    ncol = len(header)
    groups, cur, cur_h = [], [], 0.42
    base_fs = 12.5 if len(rows) <= 4 else 11 if len(rows) <= 6 else 10 if len(rows) <= 8 else 9 if len(rows) <= 11 else 8
    for row in rows:
        h = _est_row_height_in(row, ncol, base_fs)
        if cur and cur_h + h > 5.35:
            groups.append((cur, base_fs))
            cur, cur_h = [], 0.42
        cur.append(row); cur_h += h
    if cur:
        groups.append((cur, base_fs))
    return groups


def _table_slide(prs, title, sub, table, seen, meta, page, note=None, rows_override=None, part=None, parts=None, fs_override=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ttl = _resolve(title, seen) + (("（%d/%d）" % (part, parts)) if parts and parts > 1 else "")
    _title(slide, ttl, sub and _resolve(sub, seen))
    header = [_resolve(str(h), seen) for h in table["header"]]
    rows = rows_override if rows_override is not None else [[_resolve(str(c), seen) for c in row] for row in table["rows"]]
    ncol, nrow = len(header), len(rows) + 1
    # 字号自适应
    if fs_override:
        fs = fs_override
    elif nrow <= 5:
        fs = 12.5
    elif nrow <= 7:
        fs = 11
    elif nrow <= 9:
        fs = 10
    elif nrow <= 12:
        fs = 9
    else:
        fs = 8
    top = 1.45
    height = min(5.35, 0.34 * nrow + 0.3)
    shape = slide.shapes.add_table(nrow, ncol, Inches(0.6), Inches(top),
                                   Inches(12.13), Inches(height))
    tbl = shape.table
    for j, h in enumerate(header):
        cell = tbl.cell(0, j)
        cell.text = ""
        cell.fill.solid(); cell.fill.fore_color.rgb = BLUE
        cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        _run(p, h, size=fs, bold=True, color=WHITE)
    for i, row in enumerate(rows, 1):
        for j in range(ncol):
            cell = tbl.cell(i, j)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = LIGHT if i % 2 == 1 else WHITE
            cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
            cell.vertical_anchor = MSO_ANCHOR.TOP
            p = cell.text_frame.paragraphs[0]
            txt = row[j] if j < len(row) else ""
            if len(txt) > 260:
                txt = txt[:255] + "…"
            _run(p, txt, size=fs, color=DARK)
    _footer(slide, page, meta)
    _notes(slide, note or (title + "：逐项参数见表格；讲解时先读表头，再按行说明取值与理由。"))
    return slide


def _bullets_slide(prs, title, bullets, seen, meta, page, sub=None, note=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _title(slide, _resolve(title, seen), sub and _resolve(sub, seen))
    tf = _tb(slide, 0.75, 1.42, 11.9, 5.4)
    tf.word_wrap = True
    first = True
    n = len(bullets)
    # 自动适配：按折行估算总高度，超出可用高度就降字号
    avail = 5.4
    for fs_try in (15, 14, 13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9):
        cpl = max(10, int((11.6 * 72) / (fs_try * 0.92)))
        total = 0.0
        for lvl, text in bullets:
            t = _resolve(text, seen)
            lines = max(1, -(-len(t) // (cpl if lvl == 0 else int(cpl * 1.08))))
            total += lines * (fs_try * 1.32 / 72.0) + (0.11 if lvl == 0 else 0.07)
        if total <= avail:
            break
    fs = fs_try
    for item in bullets:
        level, text = item
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(7 if level == 0 else 4)
        p.line_spacing = 1.15
        _run(p, ("● " if level == 0 else "— ") + _resolve(text, seen),
             size=fs if level == 0 else fs - 1.5,
             bold=(level == 0), color=BLUE if level == 0 else DARK)
    _footer(slide, page, meta)
    _notes(slide, note or "要点：" + "；".join(t for _, t in bullets[:4]))
    return slide


def _cards_slide(prs, title, cards, seen, meta, page, sub=None, note=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _title(slide, _resolve(title, seen), sub and _resolve(sub, seen))
    n = len(cards)
    w = (12.13 - 0.3 * (n - 1)) / n
    for i, (ct, cb) in enumerate(cards):
        x = 0.6 + i * (w + 0.3)
        _rect(slide, x, 1.5, w, 5.1, LIGHT)
        _rect(slide, x, 1.5, w, 0.07, GOLD)
        tf = _tb(slide, x + 0.18, 1.72, w - 0.36, 0.7)
        _run(tf.paragraphs[0], _resolve(ct, seen), size=15, bold=True, color=BLUE)
        tf2 = _tb(slide, x + 0.18, 2.45, w - 0.36, 3.9)
        tf2.word_wrap = True
        _run(tf2.paragraphs[0], _resolve(cb, seen), size=12.5, color=DARK)
        tf2.paragraphs[0].line_spacing = 1.2
    _footer(slide, page, meta)
    _notes(slide, note or "；".join(c[0] for c in cards))
    return slide


def _formula_slide(prs, title, lines, seen, meta, page, sub=None, note=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _title(slide, _resolve(title, seen), sub and _resolve(sub, seen))
    _rect(slide, 1.2, 1.75, 10.9, 1.5, LIGHT)
    tf = _tb(slide, 1.4, 2.05, 10.5, 1.0, align=PP_ALIGN.CENTER)
    _run(tf.paragraphs[0], _resolve(lines[0], seen), size=20, bold=True, color=BLUE, font="Cambria")
    tf2 = _tb(slide, 0.75, 3.5, 11.9, 3.3)
    first = True
    for item in lines[1:]:
        lvl, text = item if isinstance(item, tuple) else (0, item)
        p = tf2.paragraphs[0] if first else tf2.add_paragraph()
        first = False
        p.space_after = Pt(6)
        _run(p, ("● " if lvl == 0 else "— ") + _resolve(text, seen),
             size=14 if lvl == 0 else 12.5, bold=(lvl == 0), color=BLUE if lvl == 0 else DARK)
    _footer(slide, page, meta)
    _notes(slide, note or "公式与解释：" + lines[0])
    return slide


def _section_slide(prs, num, title, sub, meta, page):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, 13.333, 7.5, BLUE)
    _rect(slide, 0.9, 2.6, 1.6, 0.11, GOLD)
    tf = _tb(slide, 0.9, 2.85, 11.5, 1.4)
    _run(tf.paragraphs[0], title, size=34, bold=True, color=WHITE)
    tf2 = _tb(slide, 0.9, 1.75, 11.5, 0.9)
    _run(tf2.paragraphs[0], num, size=44, bold=True, color=GOLD)
    tf3 = _tb(slide, 0.9, 4.35, 11.5, 0.8)
    _run(tf3.paragraphs[0], sub, size=15, color=RGBColor(0xD8, 0xE0, 0xEA))
    tf4 = _tb(slide, 0.9, 6.7, 11.5, 0.4)
    _run(tf4.paragraphs[0], meta["footer_left"], size=9, color=RGBColor(0x9A, 0xA8, 0xBA))
    _notes(slide, "进入 %s。%s" % (title, sub))
    return slide


def _cover_slide(prs, meta):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, 13.333, 7.5, BLUE)
    _rect(slide, 1.0, 1.65, 2.2, 0.12, GOLD)
    tf = _tb(slide, 1.0, 2.0, 11.3, 1.9)
    _run(tf.paragraphs[0], meta["title"], size=36, bold=True, color=WHITE)
    tf2 = _tb(slide, 1.0, 3.95, 11.3, 0.9)
    _run(tf2.paragraphs[0], meta["subtitle"], size=16, color=RGBColor(0xD9, 0xE2, 0xEC))
    tf3 = _tb(slide, 1.0, 4.85, 11.6, 2.0)
    p = tf3.paragraphs[0]
    _run(p, meta["claim"], size=12.5, color=RGBColor(0xF0, 0xD9, 0x8A))
    for line in meta["meta_lines"]:
        par = tf3.add_paragraph()
        par.space_before = Pt(4)
        _run(par, line, size=11, color=RGBColor(0xB9, 0xC6, 0xD6))
    _notes(slide, "封面。本册只回答三个问题，方法只写计算类方法：分子动力学、增强采样与自由能、量化计算、以及直接相关的组学统计与机器学习。")
    return slide


def _closing_slide(prs, meta, lines):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, 13.333, 7.5, BLUE)
    _rect(slide, 1.0, 1.9, 2.2, 0.12, GOLD)
    tf = _tb(slide, 1.0, 2.3, 11.3, 2.6)
    _run(tf.paragraphs[0], "三个问题，三条计算主线", size=30, bold=True, color=WHITE)
    for i, line in enumerate(lines):
        p = tf.add_paragraph()
        p.space_before = Pt(12)
        _run(p, line, size=15, color=RGBColor(0xDC, 0xE4, 0xEE))
    tf2 = _tb(slide, 1.0, 6.4, 11.3, 0.6)
    _run(tf2.paragraphs[0], meta["footer_left"], size=10, color=RGBColor(0x9A, 0xA8, 0xBA))
    _notes(slide, "结束页：三问对应三套计算主线，全部参数与判据见正文表格与参考文献。")
    return slide


def render_pptx(slides, tables, seen, meta, out_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    page = 0
    for spec in slides:
        t = spec["type"]
        if t == "cover":
            page += 1
            _cover_slide(prs, meta)
        elif t == "section":
            page += 1
            _section_slide(prs, spec["num"], spec["title"], spec["sub"], meta, page)
        elif t == "table":
            tbl = tables.get(spec["ref"])
            if tbl is None:
                page += 1
                _bullets_slide(prs, spec["title"], [(0, "（表格缺失：%s）" % spec["ref"])], seen, meta, page)
            else:
                groups = split_table_rows(tbl, seen)
                for gi, (rows_g, fs_g) in enumerate(groups, 1):
                    page += 1
                    _table_slide(prs, spec["title"], spec.get("sub"), tbl, seen, meta, page,
                                 spec.get("note"), rows_override=rows_g,
                                 part=gi, parts=len(groups), fs_override=fs_g)
        elif t == "bullets":
            page += 1
            _bullets_slide(prs, spec["title"], spec["bullets"], seen, meta, page, spec.get("sub"), spec.get("note"))
        elif t == "cards":
            page += 1
            _cards_slide(prs, spec["title"], spec["cards"], seen, meta, page, spec.get("sub"), spec.get("note"))
        elif t == "formula":
            page += 1
            _formula_slide(prs, spec["title"], spec["lines"], seen, meta, page, spec.get("sub"), spec.get("note"))
        elif t == "closing":
            page += 1
            _closing_slide(prs, meta, spec["lines"])
    prs.save(out_path)
    return page
