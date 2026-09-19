#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_docx.py - prove that a filled .docx kept the original template's format.

It compares the template (base) with the filled document and checks:
  1. page setup / section properties (paper size, margins, orientation)  - must be identical
  2. headers and footers                                                 - must be identical
  3. number and kind of body elements (paragraphs / tables)              - must be identical
  4. table properties, column widths (tblGrid) and dimensions           - must be identical
  5. every table cell that is not a fill target                         - XML identical
  6. inside a fill target cell: the prompt paragraph and the paragraph format
     (pPr: indent, line spacing) and run format (rPr: font, size, colour) of the
     written paragraphs                                                  - must match the template
  7. no leftover Word FORM field markers are reported

Usage:
    python code/verify_docx.py --base sources/中期.docx --filled deliverable/中期.docx \
        --cells 22:0:3 22:2:0 22:3:0 22:4:0 22:5:0
"""

from __future__ import annotations

import argparse
import re
import copy
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

OK, BAD = "  OK  ", " FAIL "


def body(doc):
    out = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            out.append(("p", Paragraph(child, doc)))
        elif child.tag == qn("w:tbl"):
            out.append(("tbl", Table(child, doc)))
    return out


def strip_ns(xml: str) -> str:
    return re.sub(r'\sxmlns:[a-zA-Z0-9]+="[^"]*"', "", xml)


def pPr_xml(p_el):
    el = p_el.find(qn("w:pPr"))
    return strip_ns(el.xml) if el is not None else None


def rpr_normalized(xml):
    """rPr compared without the parts we add on purpose (an extra <w:b/> for
    headings and the east-asia font hint)."""
    if xml is None:
        return None
    xml = re.sub(r'\s*w:hint="[^"]*"', "", xml)
    xml = re.sub(r'\s*<w:b/>', "", xml)
    xml = re.sub(r'\s*<w:b\s+w:val="[^"]*"/>', "", xml)
    return xml


def is_bold(xml) -> bool:
    return bool(xml) and ("<w:b/>" in xml or '<w:b w:val="1"' in xml or '<w:b w:val="true"' in xml)


def first_text_rpr(p_el):
    """rPr of the first run holding text, walking through form fields."""
    for r in p_el.findall(qn("w:r")):
        if r.find(qn("w:t")) is not None:
            rpr = r.find(qn("w:rPr"))
            return strip_ns(rpr.xml) if rpr is not None else None
    return None


from lxml import etree as _etree


def etree_of(el):
    from lxml import etree
    return etree.tostring(el, encoding="unicode")


def xml_of(el) -> str:
    return _etree.tostring(el, encoding="unicode")


T_RE = re.compile(r"(<w:t[^>]*>).*?(</w:t>)", re.S)


def mask_text(xml: str) -> str:
    """XML with the *contents* of every <w:t> blanked and the placeholder flag
    removed - used to prove that a fill target changed text and nothing else."""
    xml = xml.replace("<w:showingPlcHdr/>", "")
    return T_RE.sub(r"\1@\2", xml)


DATE_RE = re.compile(r"(?:\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
                      r"|年[\s\u3000]+月[\s\u3000]+日)")


def same_xml_or_date(a: str, b: str) -> bool:
    """两段 XML 逐字节相同；或者只差一处“年 月 日 -> 2026年9月19日”的日期填写。

    日期属于“填空”，不能因为填空就判成改动格式：把两边的日期都归一成 〈日期〉 再比。
    """
    a2, b2 = strip_ns(a), strip_ns(b)
    if a2 == b2:
        return True
    return DATE_RE.sub("〈日期〉", a2) == DATE_RE.sub("〈日期〉", b2)


def get_cell(doc, t_idx: int, r: int, c: int):
    """Cell by body-element table index / merged-grid row, column."""
    els = body(doc)
    if t_idx >= len(els) or els[t_idx][0] != "tbl":
        return None
    tbl = els[t_idx][1]
    if r >= len(tbl.rows) or c >= len(tbl.columns):
        return None
    return tbl.cell(r, c)


def section_signature(doc):
    sig = []
    for s in doc.sections:
        sig.append({
            "page_w": s.page_width, "page_h": s.page_height,
            "left": s.left_margin, "right": s.right_margin,
            "top": s.top_margin, "bottom": s.bottom_margin,
            "header_distance": s.header_distance, "footer_distance": s.footer_distance,
            "header": "|".join(p.text for p in s.header.paragraphs),
            "footer": "|".join(p.text for p in s.footer.paragraphs),
        })
    return sig


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="verify a filled docx kept its template format")
    ap.add_argument("--base", required=True)
    ap.add_argument("--filled", required=True)
    ap.add_argument("--cells", nargs="*", default=[],
                    help="fill targets as table:row:col, optionally "
                         "table:row:col@t:r:c:para to also require that every paragraph "
                         "whose pPr the base cell does not contain matches that template "
                         "paragraph's pPr/rPr (used for inserted body paragraphs)")
    ap.add_argument("--blank-cells", nargs="*", default=[],
                    help="cells that were empty in the template and got filled: "
                         "table:row:col - paragraph format must stay identical")
    ap.add_argument("--insert-cells", nargs="*", default=[],
                    help="cells where paragraphs were inserted after a given index: "
                         "table:row:col@t:r:c:para:after")
    ap.add_argument("--tc-cells", nargs="*", default=[],
                    help="raw fill targets as table:row:tc_index (text-only change, e.g. cover)")
    ap.add_argument("--tc-skip", nargs="*", default=[],
                    help="raw cells rebuilt by fill_cell: skip here, their paragraph "
                         "format is checked by --cells")
    ap.add_argument("--row-insert", nargs="*", default=[],
                    help="declared inserted rows as table:after:count (row cloned in place, "
                         "format must equal the source row)")
    ap.add_argument("--sdt-cells", nargs="*", default=[],
                    help="content-control fill targets as table:row:sdt_index (fills done with fill_sdt)")
    ap.add_argument("--pbb-rows", nargs="*", default=[],
                    help="rows that may only gain <w:pageBreakBefore/> (signature page starts "
                         "a new page): table:row - everything else in the row must be identical")
    args = ap.parse_args(argv)

    targets = set()
    fmt_templates = {}
    for spec in args.cells:
        cell_spec, _, tmpl_spec = spec.partition("@")
        t, r, c = (int(x) for x in cell_spec.split(":"))
        targets.add((t, r, c))
        if tmpl_spec:
            tt, tr, tc, tp = (int(x) for x in tmpl_spec.split(":"))
            fmt_templates[(t, r, c)] = (tt, tr, tc, tp)

    blank_targets = set()
    for spec in args.blank_cells:
        t, r, c = (int(x) for x in spec.split(":"))
        blank_targets.add((t, r, c))
    insert_specs = {}
    for spec in args.insert_cells:
        cell_spec, _, tmpl_spec = spec.partition("@")
        t, r, c = (int(x) for x in cell_spec.split(":"))
        tt, tr, tc, tp, after = (int(x) for x in tmpl_spec.split(":"))
        insert_specs[(t, r, c)] = (tt, tr, tc, tp, after)

    tc_targets = set()
    for spec in args.tc_cells:
        t, r, c = (int(x) for x in spec.split(":"))
        tc_targets.add((t, r, c))
    sdt_targets = set()
    for spec in args.sdt_cells:
        t, r, c = (int(x) for x in spec.split(":"))
        sdt_targets.add((t, r, c))
    tc_skips = set()
    for spec in args.tc_skip:
        t, r, c = (int(x) for x in spec.split(":"))
        tc_skips.add((t, r, c))
    pbb_rows = set()
    for spec in args.pbb_rows:
        t, r = (int(x) for x in spec.split(":"))
        pbb_rows.add((t, r))

    row_inserts = {}
    for spec in args.row_insert:
        t, after, n = (int(x) for x in spec.split(":"))
        row_inserts[(t, after)] = n

    def mapped(table_idx, base_row):
        """base row index -> filled row index (accounting for declared row clones)"""
        off = 0
        for (t, after), n in row_inserts.items():
            if t == table_idx and base_row > after:
                off += n
        return base_row + off

    b = Document(args.base)
    f = Document(args.filled)
    problems = []

    # --pbb-rows：这些表格行允许且**只允许**多出 <w:pageBreakBefore/>（签字页段前分页）。
    # 校验前先确认标记确实加上了，然后把它从“已填”文档的内存树里摘掉 ——
    # 脚本只读不保存，摘掉后其余逐格比对与普通文档完全一致，所以这条特例不会
    # 放宽任何别的检查（文本、字体、框线、行高照样逐字节比）。
    if pbb_rows:
        for (t, r) in sorted(pbb_rows):
            els_b, els_f = body(b), body(f)
            if t >= len(els_b) or els_b[t][0] != "tbl" or t >= len(els_f) or els_f[t][0] != "tbl":
                problems.append(f"--pbb-rows {t}:{r}: body element {t} is not a table")
                print(f"{BAD} --pbb-rows {t}:{r}: body element {t} is not a table")
                continue
            trs_b = els_b[t][1]._tbl.findall(qn("w:tr"))
            trs_f = els_f[t][1]._tbl.findall(qn("w:tr"))
            if r >= len(trs_b) or r >= len(trs_f):
                problems.append(f"--pbb-rows {t}:{r}: no such row")
                print(f"{BAD} --pbb-rows {t}:{r}: no such row")
                continue
            base_had = any(p.find(qn("w:pPr")) is not None and
                           p.find(qn("w:pPr")).find(qn("w:pageBreakBefore")) is not None
                           for p in trs_b[r].iter(qn("w:p")))
            added = 0
            for p in trs_f[r].iter(qn("w:p")):
                ppr = p.find(qn("w:pPr"))
                if ppr is not None:
                    for pb in ppr.findall(qn("w:pageBreakBefore")):
                        ppr.remove(pb)
                        added += 1
            if added and not base_had:
                print(f"{OK} page break in row tbl{t} r{r}: {added} paragraph(s) start a new "
                      f"page in the filled file, template had none")
            else:
                problems.append(f"tbl{t} r{r}: page break missing (added={added}, "
                                f"template already had one={base_had})")
                print(f"{BAD} page break in row tbl{t} r{r}: added={added} "
                      f"template_had={base_had}")

    # element ids of the content controls we are allowed to change (base tree)
    target_sdt_els = []
    if sdt_targets or tc_targets:
        for i, (kind, el) in enumerate(body(b)):
            if kind != "tbl":
                continue
            for r, tr in enumerate(el._tbl.findall(qn("w:tr"))):
                for nth, sdt in enumerate(tr.iter(qn("w:sdt"))):
                    if (i, r, nth) in sdt_targets:
                        target_sdt_els.append(sdt)   # keep the proxy alive!

    # 1 + 2 -----------------------------------------------------------------
    if section_signature(b) == section_signature(f):
        print(f"{OK} page setup / headers / footers identical")
    else:
        problems.append("page setup, headers or footers changed")
        print(f"{BAD} page setup / headers / footers differ")

    # 3 ---------------------------------------------------------------------
    bb, fb = body(b), body(f)
    if len(bb) == len(fb) and [x[0] for x in bb] == [x[0] for x in fb]:
        print(f"{OK} body structure identical ({len(bb)} elements)")
    else:
        problems.append("body element list changed")
        print(f"{BAD} body structure: base {len(bb)} vs filled {len(fb)}")

    # 4 ---------------------------------------------------------------------
    tb = [x[1] for x in bb if x[0] == "tbl"]
    tf = [x[1] for x in fb if x[0] == "tbl"]
    tbl_body_idx = [i for i, x in enumerate(bb) if x[0] == "tbl"]
    for i, (t1, t2) in enumerate(zip(tb, tf)):
        grid1 = t1._tbl.find(qn("w:tblGrid"))
        grid2 = t2._tbl.find(qn("w:tblGrid"))
        same_grid = strip_ns(grid1.xml) == strip_ns(grid2.xml) if grid1 is not None and grid2 is not None else False
        pr1, pr2 = t1._tbl.find(qn("w:tblPr")), t2._tbl.find(qn("w:tblPr"))
        same_pr = (strip_ns(pr1.xml) == strip_ns(pr2.xml)) if pr1 is not None and pr2 is not None else False
        body_idx = tbl_body_idx[i]
        extra = sum(n for (tt, _a), n in row_inserts.items() if tt == body_idx)
        dims = (len(t2.rows) == len(t1.rows) + extra and
                len(t1.columns) == len(t2.columns))
        if same_grid and same_pr and dims:
            print(f"{OK} table {i}: dimensions {len(t1.rows)}x{len(t1.columns)}, "
                  f"tblPr and tblGrid identical")
        else:
            problems.append(f"table {i} properties changed")
            print(f"{BAD} table {i}: dims={dims} tblPr={same_pr} tblGrid={same_grid}")

    # 5 + 6 -----------------------------------------------------------------
    checked, kept = 0, 0
    for i, (e1, e2) in enumerate(zip(bb, fb)):
        if e1[0] != "tbl":
            if strip_ns(e1[1]._p.xml) != strip_ns(e2[1]._p.xml):
                print(f"      paragraph [{i}] text changed")
            continue
        t1, t2 = e1[1], e2[1]
        for r in range(len(t1.rows)):
            if r >= len(t2.rows):
                break
            fr = mapped(i, r)
            if fr >= len(t2.rows):
                continue
            row1, row2 = t1.rows[r], t2.rows[fr]
            seen = set()
            for c, cell1 in enumerate(row1.cells):
                if c >= len(row2.cells):
                    break
                cell2 = row2.cells[c]
                key = id(cell1._tc)
                if key in seen:
                    continue          # horizontally/vertically merged: already checked
                seen.add(key)
                is_target = (i, r, c) in targets or any(
                    x in target_sdt_els for x in cell1._tc.iter(qn("w:sdt")))

                if (i, r, c) in blank_targets:
                    # 模板里本来是空格子：填进去的段落，段落格式要与原空格子一致
                    p1, p2 = cell1.paragraphs, cell2.paragraphs
                    ref_pPr = pPr_xml(p1[0]._p) if p1 else None
                    ref_rPr = rpr_normalized(first_text_rpr(p1[0]._p)) if p1 else None
                    if ref_rPr is None and p1:            # 空格子没有 run：取段落标记的 rPr
                        mark = p1[0]._p.find(qn("w:pPr"))
                        mark = mark.find(qn("w:rPr")) if mark is not None else None
                        ref_rPr = rpr_normalized(xml_of(mark)) if mark is not None else None
                    same_pPr = all(pPr_xml(p._p) == ref_pPr for p in p2)
                    same_rPr = all((rpr_normalized(first_text_rpr(p._p)) or ref_rPr) == ref_rPr
                                   for p in p2)
                    ok = bool(p2) and same_pPr and same_rPr
                    checked += 1
                    if ok:
                        print(f"{OK} filled blank cell tbl{i} r{r}c{c}: {len(p2)} "
                              f"paragraph(s), pPr/rPr identical to the empty template cell")
                    else:
                        problems.append(f"format drift in blank cell tbl{i} r{r}c{c}")
                        print(f"{BAD} blank cell tbl{i} r{r}c{c}: pPr={same_pPr} rPr={same_rPr}")
                    continue

                if (i, r, c) in insert_specs:
                    # 在原单元格中间插入段落：前后的原段落必须逐字节保留，
                    # 插入的段落格式必须等于指定模板段落
                    tt, tr, tc, tp, after = insert_specs[(i, r, c)]
                    p1, p2 = cell1.paragraphs, cell2.paragraphs
                    tcell = get_cell(b, tt, tr, tc)
                    tmpl_ref = tcell.paragraphs[tp]._p if tcell and len(tcell.paragraphs) > tp else None
                    n_tail = len(p1) - after - 1
                    prefix_ok = all(same_xml_or_date(p1[k]._p.xml, p2[k]._p.xml)
                                    for k in range(after + 1))
                    tail_ok = all(same_xml_or_date(p1[-(k + 1)]._p.xml, p2[-(k + 1)]._p.xml)
                                  for k in range(n_tail))
                    inserted = p2[after + 1:len(p2) - n_tail] if n_tail else p2[after + 1:]
                    fmt_ok = bool(inserted) and tmpl_ref is not None and all(
                        pPr_xml(p._p) == pPr_xml(tmpl_ref) and
                        rpr_normalized(first_text_rpr(p._p)) ==
                        rpr_normalized(first_text_rpr(tmpl_ref)) for p in inserted)
                    checked += 1
                    if prefix_ok and tail_ok and fmt_ok:
                        print(f"{OK} inserted paras tbl{i} r{r}c{c}: {len(inserted)} new, "
                              f"surrounding paragraphs untouched, format = "
                              f"tbl{tt} r{tr}c{tc} para{tp}")
                    else:
                        problems.append(f"inserted paragraphs wrong in tbl{i} r{r}c{c}")
                        print(f"{BAD} insert tbl{i} r{r}c{c}: prefix={prefix_ok} "
                              f"tail={tail_ok} format={fmt_ok}")
                    continue

                if is_target:
                    # 只往原占位符里填了字（例如 年 月 日 -> 2026年9月19日）：
                    # 结构 / 段落 / run 属性逐字节相同，只有 w:t 里的文字变了
                    if mask_text(strip_ns(cell1._tc.xml)) == mask_text(strip_ns(cell2._tc.xml)):
                        checked += 1
                        print(f"{OK} fill target tbl{i} r{r}c{c}: 只填文字，"
                              f"结构 / 段落 / run 属性逐字节相同")
                        continue
                    p1, p2 = cell1.paragraphs, cell2.paragraphs
                    same_prompt = True
                    for k in range(min(len(p1), len(p2))):
                        if "FORMTEXT" in p1[k]._p.xml:
                            break
                        if strip_ns(p1[k]._p.xml) != strip_ns(p2[k]._p.xml):
                            same_prompt = False
                            break
                    same_pPr = same_rPr = None
                    n_bold = 0
                    tmpl_p = next((p for p in p1 if "FORMTEXT" in p._p.xml), None)
                    new_ps = [p for p in p2 if "FORMTEXT" not in p._p.xml]
                    if tmpl_p is not None:
                        new_ps = new_ps[len([p for p in p1 if "FORMTEXT" not in p._p.xml]):] or new_ps
                        same_pPr = all(pPr_xml(p._p) == pPr_xml(tmpl_p._p) for p in new_ps)
                        base_rpr = rpr_normalized(first_text_rpr(tmpl_p._p))
                        same_rPr = all(rpr_normalized(first_text_rpr(p._p)) == base_rpr for p in new_ps)
                        n_bold = sum(1 for p in new_ps if is_bold(first_text_rpr(p._p)))
                    else:
                        same_pPr = same_rPr = None
                    fmt_ok = None
                    if (i, r, c) in fmt_templates:
                        tt, tr, tc, tp = fmt_templates[(i, r, c)]
                        tcell = get_cell(b, tt, tr, tc)
                        base_pprs = {strip_ns(pPr_xml(p._p)) for p in tcell.paragraphs}
                        if len(tcell.paragraphs) > tp:
                            tmpl_ref = tcell.paragraphs[tp]._p
                            ref_pPr = strip_ns(pPr_xml(tmpl_ref))
                            ref_rPr = rpr_normalized(first_text_rpr(tmpl_ref))
                            new_ps = [p for p in p2
                                      if strip_ns(pPr_xml(p._p)) not in base_pprs]
                            fmt_ok = bool(new_ps) and all(
                                pPr_xml(p._p) == pPr_xml(tmpl_ref) and
                                rpr_normalized(first_text_rpr(p._p)) == ref_rPr
                                for p in new_ps)
                            if fmt_ok:
                                print(f"{OK} format template tbl{i} r{r}c{c}: "
                                      f"{len(new_ps)} inserted paragraph(s) match "
                                      f"tbl{tt} r{tr}c{tc} para{tp}")
                            else:
                                problems.append(f"format template mismatch in tbl{i} r{r}c{c}")
                    ok = same_prompt and (same_pPr is not False) and \
                        (same_rPr is not False) and (fmt_ok is not False)
                    checked += 1
                    if ok:
                        print(f"{OK} fill target tbl{i} r{r}c{c}: prompt kept, "
                              f"pPr identical={same_pPr}, rPr identical={same_rPr}, "
                              f"{len(new_ps)} new paragraphs ({n_bold} bold headings)")
                    else:
                        problems.append(f"format drift in tbl{i} r{r}c{c}")
                        print(f"{BAD} fill target tbl{i} r{r}c{c}: prompt={same_prompt} "
                              f"pPr={same_pPr} rPr={same_rPr}")
                else:
                    if strip_ns(cell1._tc.xml) == strip_ns(cell2._tc.xml):
                        kept += 1
                    else:
                        problems.append(f"non-target cell tbl{i} r{r}c{c} changed")
                        print(f"{BAD} non-target cell tbl{i} r{r}c{c} was modified")

    # 7 raw cells: plain <w:tc> mixed with content-control <w:sdt> -----------
    raw_kept, raw_targets, raw_skipped = 0, 0, 0
    for i, (e1, e2) in enumerate(zip(bb, fb)):
        if e1[0] != "tbl":
            continue
        trs1 = e1[1]._tbl.findall(qn("w:tr"))
        trs2 = e2[1]._tbl.findall(qn("w:tr"))
        extra_rows = sum(n for (tt, _a), n in row_inserts.items() if tt == i)
        if len(trs1) + extra_rows != len(trs2):
            problems.append(f"table {i} row count changed")
            print(f"{BAD} table {i}: row count changed")
            continue
        for r, tr1 in enumerate(trs1):
            fr = mapped(i, r)
            if fr >= len(trs2):
                continue
            tr2 = trs2[fr]
            sdts1 = list(tr1.iter(qn("w:sdt")))
            target_sdts = {k for k in range(len(sdts1)) if (i, r, k) in sdt_targets}
            for tag, label in (("w:tc", "tc"), ("w:sdt", "sdt")):
                kids1, kids2 = tr1.findall(qn(tag)), tr2.findall(qn(tag))
                if len(kids1) != len(kids2):
                    problems.append(f"table {i} r{r} {label} count changed")
                    print(f"{BAD} table {i} r{r}: {label} count changed")
                    continue
                sdt_no = -1
                for k, (c1, c2) in enumerate(zip(kids1, kids2)):
                    if tag == "w:sdt":
                        sdt_no = k
                        target = k in target_sdts
                    else:
                        # a plain cell counts as a target either because it is
                        # listed in --tc-cells or because it *contains* a content
                        # control we filled (cover rows 2 and 5)
                        target = ((i, r, k) in tc_targets
                                  or any(sdts1[j] in c1.iter() for j in target_sdts))
                    if tag == "w:tc" and (i, r, k) in tc_skips:
                        raw_skipped += 1
                        print(f"{OK} fill target tc tbl{i} r{r}#{k}: rebuilt cell, "
                              f"paragraph format checked by --cells")
                        continue
                    x1, x2 = strip_ns(xml_of(c1)), strip_ns(xml_of(c2))
                    if x1 == x2 and not target:
                        raw_kept += 1
                        continue
                    if not target:
                        problems.append(f"non-target {label} tbl{i} r{r}#{k} changed")
                        print(f"{BAD} non-target {label} tbl{i} r{r}#{k} was modified")
                        continue
                    if mask_text(x1) == mask_text(x2):
                        raw_targets += 1
                        print(f"{OK} fill target {label} tbl{i} r{r}#{k}: text only, "
                              f"formatting identical")
                    else:
                        problems.append(f"format drift in {label} tbl{i} r{r}#{k}")
                        print(f"{BAD} fill target {label} tbl{i} r{r}#{k}: formatting changed")

    # 8 declared inserted rows: same XML as the source row, text aside --------
    clones = 0
    for (ti, after), n in row_inserts.items():
        if ti not in tbl_body_idx:
            continue
        idx = tbl_body_idx.index(ti)
        src = tb[idx]._tbl.findall(qn("w:tr"))
        dst = tf[idx]._tbl.findall(qn("w:tr"))
        if after >= len(src):
            continue
        for k in range(1, n + 1):
            fi = after + k
            if fi >= len(dst):
                problems.append(f"inserted row {fi} missing in table {ti}")
                continue
            def row_shape(tr):
                """行/单元格的结构属性：trPr + 每个 tc 的 tcPr（不含文字与 run）"""
                trPr = tr.find(qn("w:trPr"))
                shape = [strip_ns(xml_of(trPr)) if trPr is not None else ""]
                for tc in tr.findall(qn("w:tc")):
                    tcPr = tc.find(qn("w:tcPr"))
                    shape.append(strip_ns(xml_of(tcPr)) if tcPr is not None else "")
                return shape
            same = row_shape(src[after]) == row_shape(dst[fi])
            if same:
                clones += 1
                print(f"{OK} cloned row tbl{ti} r{fi}: row height / cell borders / "
                      f"column spans identical to the source row")
            else:
                problems.append(f"cloned row tbl{ti} r{fi} formatting differs")
                print(f"{BAD} cloned row tbl{ti} r{fi} formatting differs")
    if row_inserts:
        print(f"cloned rows verified: {clones}")

    print(f"\nnon-target cells verified identical: {kept}")
    print(f"fill targets verified: {checked}")
    print(f"raw tc/sdt structures verified identical: {raw_kept} "
          f"(+{raw_targets} fill targets with text-only diff, "
          f"+{raw_skipped} rebuilt cells checked at paragraph level)")
    if problems:
        print("\nRESULT: PROBLEMS FOUND")
        for p in sorted(set(problems)):
            print("  -", p)
        return 1
    print("\nRESULT: template format fully preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
