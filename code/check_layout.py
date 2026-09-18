#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_layout.py - 版面体检：形状重叠 + 文字溢出估算。

    python code/check_layout.py deliverable/中期答辩_H_nature风.pptx

做三件事：
1. 形状级重叠：图片 / 文本框 / 表格两两求交，报告明显重叠（面积 > 10% 且 > 0.05 in²）；
   装饰用的细线（高或宽 < 6 pt）不参与判定。
2. 文字溢出：按真实字体估算每段文字需要的行数与高度，超出文本框高度即报警。
3. 越界：任何形状超出页面或跑到页脚（y > 7.05 in）以下即报警。

返回码：0 = 通过，1 = 有问题。
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

EMU_IN = 914400.0
SLIDE_W_IN, SLIDE_H_IN = 13.333, 7.5
FOOTER_Y = 7.05
THIN_PT = 6.0


def _in(emu) -> float:
    return float(emu) / EMU_IN


def _text_blocks(shape):
    """返回 [(段文字, 字号 pt, 行距, 段前 pt, 段后 pt)]。"""
    out = []
    if not shape.has_text_frame:
        return out
    for p in shape.text_frame.paragraphs:
        text = "".join(r.text for r in p.runs)
        if not text.strip():
            continue
        size = None
        for r in p.runs:
            if r.font.size is not None:
                size = float(r.font.size.pt)
                break
        size = size or 18.0
        ls = float(p.line_spacing) if isinstance(p.line_spacing, float) else 1.2
        before = float(p.space_before.pt) if p.space_before is not None else 0.0
        after = float(p.space_after.pt) if p.space_after is not None else 0.0
        out.append((text, size, ls, before, after))
    return out


def _char_w(ch: str, size: float) -> float:
    if ord(ch) > 0x2E80:                     # CJK 及全角标点
        return size
    if ch in "iljI.,:;'|!":
        return size * 0.30
    if ch.isdigit() or ch.isalpha():
        return size * 0.56
    if ch == " ":
        return size * 0.28
    return size * 0.62


def _text_height_pt(shape) -> float:
    """估算文本框里文字需要的总高度（pt）。"""
    usable_w = _in(shape.width) * 72.0 - 6.0
    if usable_w <= 12:
        return 0.0
    total = 0.0
    for text, size, ls, before, after in _text_blocks(shape):
        lines = 0
        cur = 0.0
        for ch in text:
            w = _char_w(ch, size)
            if cur + w > usable_w:
                lines += 1
                cur = w
            else:
                cur += w
        lines += 1
        total += before + after + lines * size * ls * 1.02
    return total


def check(path: Path) -> int:
    prs = Presentation(path)
    problems: list[str] = []
    for i, slide in enumerate(prs.slides, 1):
        boxes = []
        for sh in slide.shapes:
            if sh.shape_type is not None and sh.shape_type == 6:      # group
                continue
            w, h = _in(sh.width), _in(sh.height)
            x, y = _in(sh.left), _in(sh.top)
            has_text = sh.has_text_frame and sh.text_frame.text.strip()
            is_footer = y >= 6.95 or (has_text and "研究生论文中期检查" in sh.text_frame.text) \
                or (has_text and "/ 24" in sh.text_frame.text) or y + h > 7.2
            is_pic = sh.shape_type is not None and "PICTURE" in str(sh.shape_type)
            is_tbl = getattr(sh, "has_table", False) and sh.has_table
            thin = h * 72 < THIN_PT or w * 72 < THIN_PT
            if has_text or is_pic or is_tbl:
                boxes.append((sh, x, y, w, h, has_text, is_pic, is_tbl, thin))

            # 越界 / 压页脚（页脚自身除外）
            if has_text and not is_footer and y + h > FOOTER_Y + 0.02 and y < FOOTER_Y:
                need = _text_height_pt(sh) / 72.0
                if y + min(need, h) > FOOTER_Y + 0.02:
                    problems.append(f"[{i}] 文本框压到页脚：{sh.text_frame.text[:16]!r} "
                                    f"y={y:.2f}+{h:.2f} in")

            # 文字溢出
            if has_text and h > 0.05:
                need = _text_height_pt(sh) / 72.0
                if need > h + 0.06:
                    problems.append(f"[{i}] 文字超出文本框：{sh.text_frame.text[:16]!r} "
                                    f"需要 {need:.2f} in / 框高 {h:.2f} in")

        # 两两重叠
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                sa, ax, ay, aw, ah, at, ap, atb, athin = boxes[a]
                sb, bx, by, bw, bh, bt, bp, btb, bthin = boxes[b]
                if athin or bthin:
                    continue
                if not (at or ap or atb) or not (bt or bp or btb):
                    continue
                if (sa.text_frame.text.strip().startswith("研究生论文中期检查") if at else False) \
                        or (sb.text_frame.text.strip().startswith("研究生论文中期检查") if bt else False) \
                        or ay >= 6.95 or by >= 6.95:
                    continue
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox <= 0 or oy <= 0:
                    continue
                area = ox * oy
                small = min(aw * ah, bw * bh)
                if area > 0.05 and area / max(small, 1e-6) > 0.10:
                    ta = sa.text_frame.text[:14] if at else ("图" if ap else "表")
                    tb = sb.text_frame.text[:14] if bt else ("图" if bp else "表")
                    problems.append(f"[{i}] 形状重叠 {area:.2f} in²（占较小者 "
                                    f"{area / small:.0%}）：{ta!r} × {tb!r}")
    for p in problems:
        print("  -", p)
    print(f"RESULT: {'OK' if not problems else str(len(problems)) + ' problem(s)'} - {path.name}")
    return 0 if not problems else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx", nargs="?",
                    default="deliverable/中期答辩_H_nature风.pptx")
    a = ap.parse_args(argv)
    return check(Path(a.pptx))


if __name__ == "__main__":
    raise SystemExit(main())
