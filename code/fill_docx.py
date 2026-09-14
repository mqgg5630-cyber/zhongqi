#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_docx.py - write content into an existing .docx while keeping its original
layout, styles, fonts and table borders untouched.

The idea: never rebuild the document, only edit it in place. Text is always
written into the *first run* of an existing paragraph (so that run's font,
size and east-asian font are inherited), and new paragraphs are deep copies of
an existing paragraph, so numbering/indent/spacing are copied too.

Usage
-----
    python code/fill_docx.py --ops ops.json
    python code/fill_docx.py --docx sources/中期.docx --out out/filled.docx --ops ops.json

ops.json format
---------------
{
  "docx": "sources/中期.docx",          // optional if --docx given
  "out":  "out/中期报告_已填.docx",      // optional if --out given
  "ops": [
    {"op": "replace_text", "find": "____", "replace": "内容", "nth": 0, "scope": "all"},

    {"op": "set_cell", "table": 0, "row": 2, "col": 1, "text": "内容"},

    {"op": "insert_in_cell", "table": 0, "row": 2, "col": 1,
     "anchor": "（1）", "texts": ["第一段", "第二段"]},

    {"op": "set_paragraph", "index": 12, "text": "内容"},

    {"op": "insert_after", "index": 12, "texts": ["新段落1", "新段落2"]},

    {"op": "insert_after_text", "anchor": "研究内容", "texts": ["..."], "which": 0},

    {"op": "delete_paragraph", "index": 30}
  ]
}

Fields
------
find/replace : plain text match inside a single paragraph (not across runs).
nth          : 0-based; how many earlier matches to skip (default 0).
scope        : "all" (default, every paragraph) or "body" (skip table content).
index        : body element index, exactly as printed by inspect_docx.py.
which        : 0-based occurrence of the anchor text (default 0).

Every operation is reported; an op that matches nothing prints a WARN line and
the script exits with code 2 at the end, so silent mistakes are impossible.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

WARNINGS: list[str] = []

# body element numbering is frozen when the document is loaded, so that every
# {"index": n} / {"table": n} refers to the numbering printed by
# inspect_docx.py, no matter how many paragraphs earlier ops inserted.
SNAPSHOT: list = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"WARN  {msg}")


def iter_body(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield "p", Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield "tbl", Table(child, doc)


def body_elements(doc, live: bool = False):
    """Same numbering as inspect_docx.py.

    Returns the frozen SNAPSHOT taken at load time, so that an index printed by
    inspect_docx.py keeps pointing at the same paragraph even after earlier ops
    inserted or deleted paragraphs. Pass live=True for a fresh walk.
    """
    if live or not SNAPSHOT:
        return list(iter_body(doc))
    return SNAPSHOT


def all_paragraphs(doc, scope: str = "all"):
    """Every paragraph, in document order; scope='body' skips table cells."""
    for kind, obj in body_elements(doc):
        if kind == "p":
            yield obj
        elif scope == "all":
            for row in obj.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        yield p


def set_paragraph_text(p: Paragraph, text: str) -> None:
    """Overwrite a paragraph's text, keeping the formatting of its first run."""
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    for r in runs[1:]:
        r._element.getparent().remove(r._element)
    runs[0].text = text


def insert_paragraphs_after(anchor_el, texts, base_p: Paragraph, parent):
    """Deep-copy base_p for every text and insert right after anchor_el."""
    cur = anchor_el
    created = []
    for t in texts:
        new_el = copy.deepcopy(base_p._p)
        cur.addnext(new_el)
        np = Paragraph(new_el, parent)
        set_paragraph_text(np, t)
        cur = new_el
        created.append(np)
    return created


def find_paragraph_by_text(doc, needle: str, which: int = 0, scope: str = "all"):
    hits = [p for p in all_paragraphs(doc, scope) if needle in p.text]
    if len(hits) <= which:
        return None
    return hits[which]


def get_cell(doc, t_idx: int, r: int, c: int):
    els = body_elements(doc)
    if t_idx >= len(els) or els[t_idx][0] != "tbl":
        return None
    tbl = els[t_idx][1]
    if r >= len(tbl.rows) or c >= len(tbl.columns):
        return None
    return tbl.cell(r, c)


# ------------------------------------------------------------------ operations

def op_replace_text(doc, op):
    find, repl = op["find"], op["replace"]
    nth = int(op.get("nth", 0))
    scope = op.get("scope", "all")
    pattern = re.compile(re.escape(find))
    done = 0
    for p in all_paragraphs(doc, scope):
        if pattern.search(p.text):
            if done < nth:
                done += 1
                continue
            new_text = p.text[: p.text.find(find)] + repl + p.text[p.text.find(find) + len(find):]
            set_paragraph_text(p, new_text)
            print(f"OK    replace_text  {find!r} -> {repl[:24]!r}  (nth={nth})")
            return
    warn(f"replace_text: {find!r} (nth={nth}) not found")


def op_set_cell(doc, op):
    cell = get_cell(doc, op["table"], op["row"], op["col"])
    if cell is None:
        warn(f"set_cell: table {op['table']} r{op['row']}c{op['col']} does not exist")
        return
    texts = [op["text"]] if isinstance(op.get("text"), str) else list(op.get("text") or [])
    if not texts:
        warn(f"set_cell: empty text for table {op['table']} r{op['row']}c{op['col']}")
        return
    paras = cell.paragraphs
    if not paras:
        cell.add_paragraph(texts[0])
        paras = cell.paragraphs
    set_paragraph_text(paras[0], texts[0])
    for extra in texts[1:]:
        new_el = copy.deepcopy(paras[0]._p)
        paras[-1]._p.addnext(new_el)
        np = Paragraph(new_el, cell)
        set_paragraph_text(np, extra)
        paras = cell.paragraphs
    for p in cell.paragraphs[1 + len(texts) - 1:]:
        p._element.getparent().remove(p._element)
    print(f"OK    set_cell      table {op['table']} r{op['row']}c{op['col']} "
          f"<- {texts[0][:24]!r}{' ...' if len(texts) > 1 else ''}")


def op_insert_in_cell(doc, op):
    cell = get_cell(doc, op["table"], op["row"], op["col"])
    if cell is None:
        warn(f"insert_in_cell: table {op['table']} r{op['row']}c{op['col']} does not exist")
        return
    texts = list(op["texts"])
    anchor_txt = op.get("anchor")
    paras = cell.paragraphs
    if anchor_txt:
        base = next((p for p in paras if anchor_txt in p.text), None)
        if base is None:
            warn(f"insert_in_cell: anchor {anchor_txt!r} not found in cell")
            return
    else:
        base = paras[-1]
    insert_paragraphs_after(base._p, texts, base, cell)
    print(f"OK    insert_in_cell table {op['table']} r{op['row']}c{op['col']} "
          f"+{len(texts)} paragraphs")


def op_set_paragraph(doc, op):
    els = body_elements(doc)
    idx = op["index"]
    if idx >= len(els) or els[idx][0] != "p":
        warn(f"set_paragraph: body element {idx} is not a paragraph")
        return
    set_paragraph_text(els[idx][1], op["text"])
    print(f"OK    set_paragraph body[{idx}] <- {op['text'][:24]!r}")


def op_insert_after(doc, op):
    els = body_elements(doc)
    idx = op["index"]
    if idx >= len(els) or els[idx][0] != "p":
        warn(f"insert_after: body element {idx} is not a paragraph")
        return
    base = els[idx][1]
    if base._p.getparent() is None:
        warn(f"insert_after: body element {idx} was already removed")
        return
    insert_paragraphs_after(base._p, list(op["texts"]), base, base._parent)
    print(f"OK    insert_after  body[{idx}] +{len(op['texts'])} paragraphs")


def op_insert_after_text(doc, op):
    base = find_paragraph_by_text(doc, op["anchor"], int(op.get("which", 0)), op.get("scope", "all"))
    if base is None:
        warn(f"insert_after_text: anchor {op['anchor']!r} not found")
        return
    insert_paragraphs_after(base._p, list(op["texts"]), base, base._parent)
    print(f"OK    insert_after_text {op['anchor'][:20]!r} +{len(op['texts'])} paragraphs")


def op_delete_paragraph(doc, op):
    els = body_elements(doc)
    idx = op["index"]
    if idx >= len(els) or els[idx][0] != "p":
        warn(f"delete_paragraph: body element {idx} is not a paragraph")
        return
    el = els[idx][1]._element
    if el.getparent() is None:
        warn(f"delete_paragraph: body element {idx} was already removed")
        return
    el.getparent().remove(el)
    print(f"OK    delete_paragraph body[{idx}]")



def _clean_run(rpr_el, text: str, bold: bool = False):
    """Build a <w:r> with a copy of rpr_el (or none) and the given text."""
    r = OxmlElement("w:r")
    if rpr_el is not None:
        rpr = copy.deepcopy(rpr_el)
        if bold:
            b = rpr.find(qn("w:b"))
            if b is None:
                b = OxmlElement("w:b")
                rpr.insert(0, b)
        r.append(rpr)
    elif bold:
        rpr = OxmlElement("w:rPr")
        rpr.append(OxmlElement("w:b"))
        r.append(rpr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _rpr_of_text_run(p_el):
    """rPr of the first run of a paragraph that actually holds text (skips
    form-field runs such as fldChar / instrText)."""
    fallback = None
    for r in p_el.findall(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if r.find(qn("w:t")) is not None:
            return rpr
        if fallback is None:
            fallback = rpr
    return fallback


class _RawCell:
    """Minimal stand-in for docx.table._Cell, built from a <w:tc> element that
    python-docx cannot reach (cells wrapped in a content control <w:sdt>)."""

    def __init__(self, tc):
        self._tc = tc

    @property
    def paragraphs(self):
        return [Paragraph(p, None) for p in self._tc.findall(qn("w:p"))]


def get_row_children(doc, t_idx: int, r: int, tag: str):
    """Children of a raw table row: tag='w:tc' or 'w:sdt'."""
    els = body_elements(doc)
    if t_idx >= len(els) or els[t_idx][0] != "tbl":
        return None
    trs = els[t_idx][1]._tbl.findall(qn("w:tr"))
    if r >= len(trs):
        return None
    return trs[r].findall(qn(tag))


def op_fill_cell(doc, op):
    cell = get_cell(doc, op["table"], op["row"], op["col"])
    if cell is None:
        warn(f"fill_cell: table {op['table']} r{op['row']}c{op['col']} does not exist")
        return
    _apply_fill(cell, f"table {op['table']} r{op['row']}c{op['col']}", op)


def op_fill_tc(doc, op):
    """fill_cell by RAW row index and RAW <w:tc> index - needed for tables whose
    rows mix plain cells with content-control cells (python-docx's grid mapping
    is wrong there)."""
    tcs = get_row_children(doc, op["table"], op["row"], "w:tc")
    if tcs is None or op["col"] >= len(tcs):
        warn(f"fill_tc: table {op['table']} r{op['row']} cell#{op['col']} does not exist")
        return
    _apply_fill(_RawCell(tcs[op["col"]]),
                f"table {op['table']} r{op['row']} tc#{op['col']} (raw)", op)


def get_row_sdts(doc, t_idx: int, r: int):
    """Every <w:sdt> inside a table row, in document order - covers both the
    row-level content controls (cover table rows 0/1/3/4/6) and the ones nested
    inside a plain cell (rows 2/5)."""
    els = body_elements(doc)
    if t_idx >= len(els) or els[t_idx][0] != "tbl":
        return None
    trs = els[t_idx][1]._tbl.findall(qn("w:tr"))
    if r >= len(trs):
        return None
    return list(trs[r].iter(qn("w:sdt")))


def op_fill_sdt(doc, op):
    """Write into a Word content-control cell (<w:sdt>, possibly nested in <w:tc>)."""
    sdts = get_row_sdts(doc, op["table"], op["row"])
    nth = int(op.get("nth", 0))
    if sdts is None or nth >= len(sdts):
        warn(f"fill_sdt: table {op['table']} r{op['row']} sdt#{nth} does not exist")
        return
    sdt = sdts[nth]
    content = sdt.find(qn("w:sdtContent"))
    # the control either wraps a whole table cell (row-level sdt) or sits inside
    # a normal cell and wraps only the paragraph (dropdown / plain-text control)
    ps = list(content.iter(qn("w:p"))) if content is not None else []
    if not ps:
        warn(f"fill_sdt: table {op['table']} r{op['row']} sdt#{nth} has no paragraph")
        return
    # drop the "showing placeholder" flag so Word treats our text as content
    for flag in sdt.findall(qn("w:sdtPr") + "/" + qn("w:showingPlcHdr")):
        flag.getparent().remove(flag)
    text = op["text"]
    runs = ps[0].findall(qn("w:r"))
    text_runs = [r for r in runs if r.find(qn("w:t")) is not None]
    if not text_runs:
        warn(f"fill_sdt: table {op['table']} r{op['row']} sdt#{nth} has no text run")
        return
    keep = text_runs[0]
    for extra in text_runs[1:]:
        extra.getparent().remove(extra)
    for t in keep.findall(qn("w:t")):
        keep.remove(t)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    keep.append(t)
    print(f"OK    fill_sdt      table {op['table']} r{op['row']} sdt#{nth} <- {text!r}")


def _apply_fill(cell, label: str, op):
    """Replace everything after the first `keep_before` paragraphs of a cell with
    `texts`, keeping the template's paragraph format (indent / line spacing) and
    run format (font / size) - including Word form fields being removed cleanly."""
    texts = list(op["texts"])
    keep = int(op.get("keep_before", 1))
    bold_idx = set(int(i) for i in op.get("bold", []))

    orig = list(cell.paragraphs)
    if keep > len(orig):
        warn(f"fill_cell: keep_before={keep} > {len(orig)} paragraphs")
        return

    # template paragraph = first placeholder paragraph after the kept ones
    tmpl = None
    for p in orig[keep:]:
        if "FORMTEXT" in p._p.xml or p.text.strip("\u2002 ").strip() == "":
            tmpl = p
            break
    if tmpl is None:
        tmpl = orig[keep] if len(orig) > keep else orig[-1]

    normal_rpr = _rpr_of_text_run(tmpl._p)
    bold_rpr = _rpr_of_text_run(orig[0]._p) if orig else normal_rpr
    if bold_rpr is None or bold_rpr.find(qn("w:b")) is None:
        bold_rpr = None  # heading is not bold -> keep normal format

    anchor = orig[keep - 1]._p if keep > 0 else tmpl._p.getprevious()
    created = []
    for i, text in enumerate(texts):
        new_p = copy.deepcopy(tmpl._p)
        for r in new_p.findall(qn("w:r")):
            new_p.remove(r)
        for extra in (qn("w:bookmarkStart"), qn("w:bookmarkEnd")):
            for el in new_p.findall(extra):
                new_p.remove(el)
        use_bold = i in bold_idx and bold_rpr is not None
        new_p.append(_clean_run(bold_rpr if use_bold else normal_rpr, text, bold=use_bold))
        if anchor is not None:
            anchor.addnext(new_p)
        else:
            cell._tc.insert(0, new_p) if False else None
        anchor = new_p
        created.append(new_p)

    for p in orig[keep:]:
        p._p.getparent().remove(p._p)

    print(f"OK    fill_cell     {label} "
          f"+{len(texts)} paragraphs ({len(bold_idx)} bold)")


HANDLERS = {
    "replace_text": op_replace_text,
    "set_cell": op_set_cell,
    "fill_cell": op_fill_cell,
    "fill_tc": op_fill_tc,
    "fill_sdt": op_fill_sdt,
    "insert_in_cell": op_insert_in_cell,
    "set_paragraph": op_set_paragraph,
    "insert_after": op_insert_after,
    "insert_after_text": op_insert_after_text,
    "delete_paragraph": op_delete_paragraph,
}


def apply_ops(doc, ops) -> int:
    failed = 0
    for i, op in enumerate(ops):
        name = op.get("op")
        handler = HANDLERS.get(name)
        if handler is None:
            warn(f"op #{i}: unknown op {name!r}")
            failed += 1
            continue
        before = len(WARNINGS)
        handler(doc, op)
        if len(WARNINGS) > before:
            failed += 1
    return failed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="fill a .docx in place, keeping its formatting")
    ap.add_argument("--ops", required=True, help="ops json file")
    ap.add_argument("--docx", help="override input docx")
    ap.add_argument("--out", help="override output docx")
    args = ap.parse_args(argv)

    spec = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    src = Path(args.docx or spec["docx"])
    dst = Path(args.out or spec["out"])
    if not src.exists():
        print(f"[ERROR] not found: {src}", file=sys.stderr)
        return 1

    doc = Document(str(src))
    SNAPSHOT.clear()
    SNAPSHOT.extend(iter_body(doc))          # freeze body numbering here
    failed = apply_ops(doc, spec["ops"])

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))
    print(f"\nsaved -> {dst}  ({len(spec['ops'])} ops, {failed} failed)")
    if failed:
        print("some operations did not apply - fix the ops file and rerun", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
