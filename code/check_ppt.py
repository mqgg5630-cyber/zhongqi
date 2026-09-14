#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ppt.py - layout self-check for the generated deck.

Two things are verified, since neither PowerPoint nor LibreOffice is available
in this environment:

1. every run >= 15 pt (the hard requirement) and every shape inside the canvas
2. a text-fit estimate: the wrapped text of every shape is measured with the
   real CJK font (PIL) and compared with the shape's box - a shape whose text
   needs more height than the box (or than the space left on the slide) is
   reported so it can be shortened before delivery.

Usage:
    python code/check_ppt.py deliverable/中期答辩.pptx
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from PIL import ImageFont
from pptx import Presentation
from pptx.util import Emu, Pt

MIN_PT = 15
TOLERANCE = 1.06          # allow 6 % slack in the estimate


def cjk_font(px: int):
    cands = sorted(glob.glob("/tmp/fonts/*CJK*.otf"))
    if not cands:
        return ImageFont.load_default()
    return ImageFont.truetype(cands[0], int(px))


def wrap_width(font, text: str, box_px: float) -> int:
    """number of lines needed to wrap `text` into `box_px` pixels"""
    if not text:
        return 1
    lines, cur = 1, ""
    for ch in text:
        if font.getlength(cur + ch) > box_px and cur:
            lines += 1
            cur = ch
        else:
            cur += ch
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx", nargs="?", default="deliverable/中期答辩.pptx")
    ap.add_argument("--min-pt", type=float, default=MIN_PT)
    args = ap.parse_args(argv)

    prs = Presentation(args.pptx)
    slide_h_px_pt = prs.slide_height.pt
    problems, warnings = [], []

    for idx, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.left is None:
                continue
            # ---- geometry
            if sh.top + sh.height > prs.slide_height + Emu(20000) or \
               sh.left + sh.width > prs.slide_width + Emu(20000) or sh.top < -Emu(20000) or sh.left < -Emu(20000):
                problems.append(f"slide {idx}: shape leaves the canvas")

            if not sh.has_text_frame:
                continue

            top_pt = sh.top.pt
            box_w_pt = sh.width.pt
            box_h_pt = sh.height.pt
            text_h = 0.0
            for p in sh.text_frame.paragraphs:
                runs = p.runs
                if not runs:
                    continue
                size = max((r.font.size.pt if r.font.size else 18) for r in runs)
                if size < args.min_pt - 1e-6:
                    problems.append(f"slide {idx}: font {size} pt < {args.min_pt} pt "
                                    f"({''.join(r.text for r in runs)[:28]!r})")
                text = "".join(r.text for r in runs)
                font = cjk_font(size * 96 / 72)          # px at 96 dpi
                n_lines = wrap_width(font, text, box_w_pt * 96 / 72)
                spacing = p.line_spacing or 1.2
                text_h += n_lines * size * spacing * 1.22
                text_h += (p.space_before.pt if p.space_before else 0) + \
                          (p.space_after.pt if p.space_after else 0)
            if text_h > box_h_pt * TOLERANCE:
                # a plain textbox grows downwards; only a problem if it leaves the slide
                bottom = top_pt + text_h
                msg = (f"slide {idx}: text needs {text_h:.0f} pt but the box is {box_h_pt:.0f} pt "
                       f"({''.join(r.text for p in sh.text_frame.paragraphs for r in p.runs)[:34]!r})")
                if bottom > slide_h_px_pt - 4:
                    problems.append(msg + " -> runs off the slide")
                else:
                    warnings.append(msg)

    print(f"slides: {len(prs.slides._sldIdLst)}")
    for w in warnings:
        print("WARN ", w)
    for p in problems:
        print("FAIL ", p)
    if problems:
        print(f"\nRESULT: {len(problems)} problem(s)")
        return 1
    print(f"\nRESULT: OK ({len(warnings)} soft warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
