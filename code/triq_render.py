# -*- coding: utf-8 -*-
"""三问·计算版：DOCX 渲染器（含自动引文编号）。"""
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BLUE = RGBColor(0x10, 0x30, 0x5A)
BLUE_HEX = "10305A"
GOLD_HEX = "C9A227"
GRAY = RGBColor(0x55, 0x55, 0x55)
DARK = RGBColor(0x1F, 0x29, 0x37)

CITE_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _set_font(run, size=11, bold=False, italic=False, color=DARK, ea="宋体", ascii_font="Times New Roman"):
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color
    run.font.name = ascii_font
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), ascii_font)
    rFonts.set(qn('w:hAnsi'), ascii_font)
    rFonts.set(qn('w:eastAsia'), ea)


def _shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    tcPr.append(shd)


def _para(doc, text, size=11, bold=False, italic=False, color=DARK, ea="宋体",
          align=None, space_before=0, space_after=6, indent_chars=0, line=1.35, runs=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if indent_chars:
        pf.first_line_indent = Pt(size * indent_chars)
    if align is not None:
        p.alignment = align
    if runs is None:
        runs = [(text, bold, italic, color, ea, size)]
    for t, b, i, c, f, s in runs:
        r = p.add_run(t)
        _set_font(r, size=s, bold=b, italic=i, color=c, ea=f)
    return p


def assign_numbers(blocks):
    """按出现顺序给引用编号，返回 (order_list, warning_set)。"""
    order, seen, missing = [], {}, set()
    def scan(text):
        for m in CITE_RE.finditer(text or ""):
            for key in [k.strip() for k in m.group(1).split(",") if k.strip()]:
                if key not in seen:
                    seen[key] = len(order) + 1
                    order.append(key)
    for kind, payload in blocks:
        if kind in ("h1", "h2", "h3", "p", "b", "b2", "note", "quote"):
            scan(payload)
        elif kind == "table":
            scan(payload.get("title", ""))
            for row in payload.get("rows", []):
                for c in row:
                    scan(str(c))
        elif kind == "kv":
            for k, v in payload:
                scan(k); scan(v)
    return seen, order


def resolve(text, seen, missing):
    def rep(m):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        nums = []
        for k in keys:
            if k in seen:
                nums.append(str(seen[k]))
            else:
                missing.add(k)
                nums.append("?")
        return "[" + "，".join(nums) + "]"
    return CITE_RE.sub(rep, text or "")


def add_table(doc, spec, seen, missing):
    _para(doc, resolve(spec.get("title", ""), seen, missing), size=10.5, bold=True,
          color=BLUE, ea="微软雅黑", space_before=8, space_after=4)
    header = spec["header"]
    rows = spec["rows"]
    t = doc.add_table(rows=1, cols=len(header))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for j, h in enumerate(header):
        hdr[j].text = ""
        p = hdr[j].paragraphs[0]
        r = p.add_run(str(h))
        _set_font(r, size=9.5, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), ea="微软雅黑")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(hdr[j], BLUE_HEX)
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j, val in enumerate(row):
            cells[j].text = ""
            p = cells[j].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            r = p.add_run(resolve(str(val), seen, missing))
            _set_font(r, size=9.5, ea="宋体")
            if i % 2 == 1:
                _shade(cells[j], "F2F5F9")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_kv(doc, pairs, seen, missing):
    t = doc.add_table(rows=0, cols=2)
    t.style = 'Table Grid'
    for k, v in pairs:
        cells = t.add_row().cells
        cells[0].text = ""
        r = cells[0].paragraphs[0].add_run(resolve(str(k), seen, missing))
        _set_font(r, size=9.5, bold=True, ea="微软雅黑", color=BLUE)
        _shade(cells[0], "F2F5F9")
        cells[1].text = ""
        r2 = cells[1].paragraphs[0].add_run(resolve(str(v), seen, missing))
        _set_font(r2, size=9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def render_docx(blocks, refs_map, out_path, meta):
    seen, order = assign_numbers(blocks)
    missing = set()
    doc = Document()
    st = doc.styles['Normal']
    st.font.size = Pt(11)
    st.font.name = "Times New Roman"
    st.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    sec = doc.sections[0]
    sec.top_margin = Cm(2.2); sec.bottom_margin = Cm(2.2)
    sec.left_margin = Cm(2.4); sec.right_margin = Cm(2.4)

    # ---- 封面 ----
    _para(doc, meta["title"], size=24, bold=True, color=BLUE, ea="微软雅黑",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_before=90, space_after=10, line=1.2)
    _para(doc, meta["subtitle"], size=13, bold=False, color=GRAY, ea="微软雅黑",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=24)
    _para(doc, meta["claim"], size=12, bold=True, color=DARK, ea="微软雅黑",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=30)
    for line in meta["meta_lines"]:
        _para(doc, line, size=10.5, color=GRAY, ea="微软雅黑",
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=3)
    doc.add_page_break()

    # ---- 目录（手工，两级）----
    _para(doc, "目　录", size=16, bold=True, color=BLUE, ea="微软雅黑",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)
    for kind, payload in blocks:
        if kind == "h1":
            _para(doc, resolve(payload, seen, missing), size=11.5, bold=True, color=BLUE,
                  ea="微软雅黑", space_after=2)
        elif kind == "h2":
            _para(doc, "　　" + resolve(payload, seen, missing), size=10.5, color=GRAY,
                  ea="微软雅黑", space_after=1)
    for key, num in sorted(seen.items(), key=lambda kv: kv[1]):
        pass
    _para(doc, "参考文献　（共 %d 条，按正文首次出现顺序编号）" % len(order), size=11.5,
          bold=True, color=BLUE, ea="微软雅黑", space_before=6)
    doc.add_page_break()

    # ---- 正文 ----
    for kind, payload in blocks:
        if kind == "h1":
            _para(doc, resolve(payload, seen, missing), size=17, bold=True, color=BLUE,
                  ea="微软雅黑", space_before=16, space_after=8, line=1.2)
        elif kind == "h2":
            _para(doc, resolve(payload, seen, missing), size=13.5, bold=True, color=BLUE,
                  ea="微软雅黑", space_before=12, space_after=5, line=1.2)
        elif kind == "h3":
            _para(doc, resolve(payload, seen, missing), size=11.5, bold=True, color=DARK,
                  ea="微软雅黑", space_before=8, space_after=4)
        elif kind == "p":
            _para(doc, resolve(payload, seen, missing), size=11, indent_chars=2, line=1.4)
        elif kind == "b":
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            r = p.add_run(resolve(payload, seen, missing))
            _set_font(r, size=10.5)
        elif kind == "b2":
            p = doc.add_paragraph(style='List Bullet 2')
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(resolve(payload, seen, missing))
            _set_font(r, size=10)
        elif kind == "note":
            _para(doc, "▶ " + resolve(payload, seen, missing), size=10, italic=True,
                  color=GRAY, ea="楷体", indent_chars=1, space_before=2, space_after=6)
        elif kind == "quote":
            _para(doc, resolve(payload, seen, missing), size=11, italic=True, color=BLUE,
                  ea="Cambria", align=WD_ALIGN_PARAGRAPH.CENTER, space_before=6, space_after=6)
        elif kind == "table":
            add_table(doc, payload, seen, missing)
        elif kind == "kv":
            add_kv(doc, payload, seen, missing)

    # ---- 参考文献 ----
    doc.add_page_break()
    _para(doc, "参考文献", size=17, bold=True, color=BLUE, ea="微软雅黑", space_after=8)
    _para(doc, "（编号与正文方括号一致；带 DOI/PMID/PMC 的条目可直接检索核验原文。"
               "本次共引用 %d 条。）" % len(order), size=10, italic=True, color=GRAY,
          ea="楷体", space_after=8)
    for i, key in enumerate(order, 1):
        text = refs_map.get(key, "【缺失文献：%s】" % key)
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(3)
        pf.line_spacing = 1.25
        pf.left_indent = Cm(0.9)
        pf.first_line_indent = Cm(-0.9)
        r = p.add_run("[%d] " % i)
        _set_font(r, size=9.5, bold=True, color=BLUE)
        r2 = p.add_run(text)
        _set_font(r2, size=9.5)

    doc.save(out_path)
    return {"citations": len(order), "missing": sorted(missing), "used_keys": order}
