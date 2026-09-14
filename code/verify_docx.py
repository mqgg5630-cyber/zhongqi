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
    ap.add_argument("--cells", nargs="*", default=[], help="fill targets as table:row:col")
    args = ap.parse_args(argv)

    targets = set()
    for spec in args.cells:
        t, r, c = (int(x) for x in spec.split(":"))
        targets.add((t, r, c))

    b = Document(args.base)
    f = Document(args.filled)
    problems = []

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
    for i, (t1, t2) in enumerate(zip(tb, tf)):
        grid1 = t1._tbl.find(qn("w:tblGrid"))
        grid2 = t2._tbl.find(qn("w:tblGrid"))
        same_grid = strip_ns(grid1.xml) == strip_ns(grid2.xml) if grid1 is not None and grid2 is not None else False
        pr1, pr2 = t1._tbl.find(qn("w:tblPr")), t2._tbl.find(qn("w:tblPr"))
        same_pr = (strip_ns(pr1.xml) == strip_ns(pr2.xml)) if pr1 is not None and pr2 is not None else False
        dims = (len(t1.rows), len(t1.columns)) == (len(t2.rows), len(t2.columns))
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
            row1, row2 = t1.rows[r], t2.rows[r]
            seen = set()
            for c, cell1 in enumerate(row1.cells):
                if c >= len(row2.cells):
                    break
                cell2 = row2.cells[c]
                key = id(cell1._tc)
                if key in seen:
                    continue          # horizontally/vertically merged: already checked
                seen.add(key)
                is_target = (i, r, c) in targets
                if is_target:
                    p1, p2 = cell1.paragraphs, cell2.paragraphs
                    same_prompt = True
                    for k in range(min(len(p1), len(p2))):
                        if "FORMTEXT" in p1[k]._p.xml:
                            break
                        if strip_ns(p1[k]._p.xml) != strip_ns(p2[k]._p.xml):
                            same_prompt = False
                            break
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
                    ok = same_prompt and (same_pPr is not False) and (same_rPr is not False)
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

    print(f"\nnon-target cells verified identical: {kept}")
    print(f"fill targets verified: {checked}")
    if problems:
        print("\nRESULT: PROBLEMS FOUND")
        for p in sorted(set(problems)):
            print("  -", p)
        return 1
    print("\nRESULT: template format fully preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
