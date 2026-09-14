#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_svg.py - 用「SVG 排版 + ppt-master 原生导出」再出两版风格完全不同的答辩 PPT。

为什么要有这个脚本
------------------
`make_ppt2.py` / `make_ppt_variants.py` 走的是 python-pptx 直接摆形状的路线，
版式变化空间有限（几版看起来会"像同一版"）。本脚本改走
[ppt-master](https://github.com/hugohe3/ppt-master)（54k★，MIT）的官方通路：
先按设计规范把每页写成 SVG（绝对坐标、可自由排版），再由 ppt-master 的
`svg_to_pptx.py` 导出成**原生 DrawingML** 的 pptx——文字是真实文本框、可编辑，
图片、圆角面板、色带都是原生对象。

本脚本负责四件事：
    1) 读 `docs/ppt_outline.json`（唯一内容源，与其它版本完全同一份内容）；
    2) 按风格表 `STYLES` 把每页渲染成 SVG（含字号自检：任何文字 ≥ 20 px，即幻灯片上的 15 pt）；
    3) 写 `spec_lock.md`、`notes/*.md`（演讲备注）与 `images/`；
    4) 调 ppt-master 导出 pptx 到 `deliverable/`。

用法
----
    python code/make_ppt_svg.py --style F          # 深色科技风
    python code/make_ppt_svg.py --style G          # 学术期刊风
    python code/make_ppt_svg.py                    # 两版都出

依赖 ppt-master（只在需要时下载，约 90 MB，放在 build/ 下，不入库）：
    python code/fetch_ppt_master.py
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = ROOT / "docs" / "ppt_outline.json"
FIGDIR = ROOT / "results" / "figures"
BUILD = ROOT / "build"
OUT_DIR = ROOT / "deliverable"
PM = BUILD / "ppt-master" / "skills" / "ppt-master"          # 解包后的 skill 目录
PM_EXPORT = PM / "scripts" / "svg_to_pptx.py"

W, H = 1280, 720          # SVG 画布 = 16:9
MARGIN = 72
MIN_PX = 20               # 1280 px 宽画布上，20 px ≈ 幻灯片上的 15 pt（1280/960 = 4/3）

CN = "Microsoft YaHei, Arial, sans-serif"
MONO = "Consolas, Microsoft YaHei, monospace"
SERIF = "Georgia, SimSun, serif"

# ------------------------------------------------------------------ 风格表
STYLES: dict[str, dict] = {
    "F": {
        "name": "深色科技风",
        "bg": "#070B16",
        "grid": "#16324D",
        "panel": "#0B1220",
        "panel_line": "#1E3A5F",
        "title": "#F1F5F9",
        "body": "#CBD5E1",
        "muted": "#7C8CA1",
        "accent": "#22D3EE",
        "accent2": "#F5A524",
        "chip_fill": "#0E1A2B",
        "chip_line": "#1E3A5F",
        "rule": "#1B3350",
        "kicker_family": MONO,
        "title_family": CN,
        "body_family": CN,
        "title_px": 40,
        "cover_title_px": 50,
        "band": True,           # 底部结论条：整条深色带
    },
    "G": {
        "name": "学术期刊风",
        "bg": "#FFFFFF",
        "grid": "#F1F3F5",
        "panel": "#FAFAF8",
        "panel_line": "#E3E1DC",
        "title": "#141414",
        "body": "#2B2B2B",
        "muted": "#767472",
        "accent": "#B03A2E",     # 期刊红
        "accent2": "#2F5D62",
        "chip_fill": "#FBF6F5",
        "chip_line": "#EADCD9",
        "rule": "#DEDCD7",
        "kicker_family": SERIF,
        "title_family": SERIF,
        "body_family": CN,
        "title_px": 40,
        "cover_title_px": 48,
        "band": False,          # 底部结论条：细分隔线 + 红色方点
    },
}

_font_cache: dict[int, object] = {}


def _font(px: int, family: str = CN):
    """取一个等宽对齐的度量字体（中文用思源黑体，英文/数字也够用）。"""
    from PIL import ImageFont
    key = px
    if key not in _font_cache:
        cands = sorted(Path("/tmp/fonts").glob("*CJK*.otf"))
        _font_cache[key] = (ImageFont.truetype(str(cands[0]), px) if cands
                            else ImageFont.load_default())
    return _font_cache[key]


def text_w(s: str, px: int) -> float:
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return d.textlength(s, font=_font(px))


def wrap(s: str, width_px: float, px: int) -> list[str]:
    """按像素宽度折行（中英文都按字符切，中文不必分词）。"""
    words, out, cur = [], [], ""
    for ch in s:
        if text_w(cur + ch, px) > width_px and cur:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out or [""]


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, *, px, fill, family=CN, weight="normal", anchor="start", ls=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight != "normal" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{px}"'
            f'{w}{a}{l} fill="{fill}">{esc(s)}</text>')


def block(x, y, s, *, px, fill, width, lh=1.5, family=CN, weight="normal", max_lines=None):
    """按宽度折行并输出多行 <text>；返回 (xml, next_y)。"""
    lines = wrap(s, width, px)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
    out = [t(x, y + i * px * lh, ln, px=px, fill=fill, family=family, weight=weight)
           for i, ln in enumerate(lines)]
    return "\n  ".join(out), y + len(lines) * px * lh


def rect(x, y, w, h, fill, *, stroke=None, sw=1, rx=None, op=None):
    s = f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}"'
    if rx:
        s += f' rx="{rx}"'
    s += f' fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    if op is not None:
        s += f' fill-opacity="{op}"'
    return s + "/>"


def line(x1, y1, x2, y2, color, sw=1):
    return (f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"'
            f' stroke="{color}" stroke-width="{sw}"/>')


# ------------------------------------------------------------------ 页面骨架
def frame(st: dict, kicker: str, idx: int, total: int, grid: bool = True) -> list[str]:
    """背景 + 页眉（kicker / 标题用）——标题由各版式函数自己画。"""
    out = [rect(0, 0, W, H, st["bg"])]
    if grid and st.get("grid"):
        g = []
        for x in range(0, W + 1, 320):
            g.append(f"M{x} 0V{H}")
        for y in range(0, H + 1, 180):
            g.append(f"M0 {y}H{W}")
        out.append(f'<g stroke="{st["grid"]}" stroke-width="1" opacity="0.55" '
                   f'fill="none"><path d="{"".join(g)}" fill="none"/></g>')
    if kicker:
        out.append(t(MARGIN, 74, kicker, px=21, fill=st["accent"],
                     family=st["kicker_family"], weight="bold", ls=2))
    out.append(t(W - MARGIN, 74, f"{idx:02d} / {total}", px=21, fill=st["muted"],
                 anchor="end", family=MONO))
    return out


def heading(st: dict, title: str, subtitle: str | None, top: int = 118) -> tuple[list, int]:
    """标题 + 副标题 + 分隔线，返回 (元素, 内容起始 y)。"""
    out, y = [], top
    px = st["title_px"]
    lines = wrap(title, W - 2 * MARGIN - 70, px)
    if len(lines) > 2:                      # 太长就缩到刚好两行
        px = int(px * 0.86)
        lines = wrap(title, W - 2 * MARGIN - 70, px)
    for i, ln in enumerate(lines):
        out.append(t(MARGIN, y + i * px * 1.22, ln, px=px, fill=st["title"],
                     family=st["title_family"], weight="bold"))
    y += (len(lines) - 1) * px * 1.22
    if subtitle:
        sub_px = 22
        out.append(t(MARGIN, y + 34, subtitle, px=sub_px, fill=st["accent2"],
                     family=st["kicker_family"]))
        y += 34
    y += 20
    out.append(line(MARGIN, y, W - MARGIN, y, st["rule"], 1.5))
    return out, y + 34


def takeaway(st: dict, text: str) -> list[str]:
    """底部结论条（两种风格不同做法，但都在 y=640..700 之间）。"""
    top, height = 640, 60
    out = []
    if st["band"]:
        out.append(rect(0, top, W, height, st["panel"]))
        out.append(rect(0, top, 8, height, st["accent"]))
        x = MARGIN
    else:
        out.append(line(MARGIN, top, W - MARGIN, top, st["rule"], 1.5))
        out.append(rect(MARGIN, top + 22, 14, 14, st["accent"]))
        x = MARGIN + 30
    px = 22
    lines = wrap(text, W - x - MARGIN, px)
    y = top + 37 if len(lines) == 1 else top + 28
    for i, ln in enumerate(lines[:2]):
        out.append(t(x, y + i * px * 1.35, ln, px=px,
                     fill=st["title"] if st["band"] else st["body"],
                     family=st["body_family"], weight="bold"))
    return out


def figure_page(st, s, idx, total, content_top):
    """配图页：图在上，图注说明在下（说明太短也不小于 20 px）。"""
    out, names = [], s.get("figure")
    body = s.get("body")
    img = FIGDIR / names
    top = content_top - 6
    avail_h = (600 - top)
    panel_h = avail_h if not body else avail_h * 0.80
    out.append(rect(MARGIN - 8, top, W - 2 * MARGIN + 16, panel_h, st["panel"],
                    stroke=st["panel_line"], sw=1, rx=10))
    # 图片等比缩放放进面板
    from PIL import Image
    iw, ih = Image.open(img).size
    pad = 14
    maxw, maxh = W - 2 * MARGIN - pad * 2, panel_h - pad * 2
    scale = min(maxw / iw, maxh / ih)
    dw, dh = iw * scale, ih * scale
    x = (W - dw) / 2
    y = top + (panel_h - dh) / 2
    rel = f"../images/{img.name}"
    out.append(f'<image href="{rel}" x="{x:.0f}" y="{y:.0f}" '
               f'width="{dw:.0f}" height="{dh:.0f}"/>')
    if body:
        xml, _ = block(MARGIN, top + panel_h + 46, body, px=22, fill=st["body"],
                       width=W - 2 * MARGIN, lh=1.42, family=st["body_family"])
        out.append(xml)
    return out


def bullets_page(st, s, idx, total, content_top):
    out = []
    bullets = s.get("bullets", [])
    callout = s.get("callout")
    bottom = 610 if not callout else 470
    y = content_top + 6
    for b in bullets:
        tag, _, rest = b.partition("　")
        if rest:
            out.append(rect(MARGIN, y - 14, 10, 10, st["accent"]))
            out.append(t(MARGIN + 24, y, tag, px=22, fill=st["accent2"],
                         family=st["body_family"], weight="bold"))
            xml, ny = block(MARGIN + 24 + text_w(tag, 22) + 16, y, rest, px=22,
                            fill=st["body"], width=W - 2 * MARGIN - 24 - text_w(tag, 22) - 16,
                            lh=1.42, family=st["body_family"])
        else:
            out.append(rect(MARGIN, y - 14, 10, 10, st["accent"]))
            xml, ny = block(MARGIN + 24, y, b, px=22, fill=st["body"],
                            width=W - 2 * MARGIN - 24, lh=1.42, family=st["body_family"])
        out.append(xml)
        y = ny + 22
        if y > bottom:
            break
    if callout:
        top = 500
        out.append(rect(MARGIN, top, W - 2 * MARGIN, 120, st["chip_fill"],
                        stroke=st["chip_line"], sw=1, rx=10))
        out.append(rect(MARGIN, top, 6, 120, st["accent"]))
        out.append(t(MARGIN + 26, top + 40, callout["label"], px=21, fill=st["accent2"],
                     family=st["body_family"], weight="bold"))
        xml, _ = block(MARGIN + 26, top + 76, callout["text"], px=22, fill=st["body"],
                       width=W - 2 * MARGIN - 52, lh=1.35, family=st["body_family"])
        out.append(xml)
    return out


def cards_page(st, s, idx, total, content_top):
    """左侧要点 + 右侧卡片（卡片页）。"""
    out = []
    bullets = s.get("bullets", [])
    cards = s.get("cards", [])
    y = content_top + 10
    for b in bullets:
        xml, ny = block(MARGIN, y, "· " + b, px=21, fill=st["body"],
                        width=620, lh=1.4, family=st["body_family"])
        out.append(xml)
        y = ny + 16
    cy = content_top + 6
    ch = 96
    for label, desc, tone in cards:
        col = st["accent"] if tone == "A" else st["accent2"]
        out.append(rect(760, cy, 448, ch, st["chip_fill"], stroke=st["chip_line"],
                        sw=1, rx=8))
        out.append(rect(760, cy, 6, ch, col))
        out.append(t(786, cy + 40, label, px=22, fill=col, family=st["body_family"],
                     weight="bold"))
        xml, _ = block(786, cy + 72, desc, px=20, fill=st["body"], width=400, lh=1.25,
                       family=st["body_family"], max_lines=2)
        out.append(xml)
        cy += ch + 14
    return out


def steps_page(st, s, idx, total, content_top):
    out = []
    y = content_top + 12
    steps = s.get("steps", [])
    row_gap = (600 - y - 90 * len(steps)) / max(1, len(steps) - 1) if len(steps) > 1 else 0
    for k, (tag, text) in enumerate(steps):
        out.append(rect(MARGIN, y, 6, 74, st["accent"] if k % 2 == 0 else st["accent2"]))
        out.append(t(MARGIN + 26, y + 32, tag, px=23, fill=st["title"],
                     family=st["body_family"], weight="bold"))
        xml, _ = block(MARGIN + 26, y + 66, text, px=21, fill=st["body"],
                       width=W - 2 * MARGIN - 40, lh=1.35, family=st["body_family"])
        out.append(xml)
        y += 74 + max(18, row_gap)
    return out


def problems_page(st, s, idx, total, content_top):
    out = []
    y = content_top + 8
    for label, problem, answer in s.get("cards_problems", []):
        out.append(rect(MARGIN, y, W - 2 * MARGIN, 118, st["chip_fill"],
                        stroke=st["chip_line"], sw=1, rx=8))
        out.append(rect(MARGIN, y, 6, 118, st["accent"]))
        out.append(t(MARGIN + 26, y + 36, label, px=20, fill=st["accent"],
                     family=st["kicker_family"], weight="bold"))
        out.append(t(MARGIN + 26 + text_w(label, 20) + 18, y + 36, problem, px=23,
                     fill=st["title"], family=st["body_family"], weight="bold"))
        xml, _ = block(MARGIN + 26, y + 76, answer, px=21, fill=st["body"],
                       width=W - 2 * MARGIN - 60, lh=1.3, family=st["body_family"],
                       max_lines=2)
        out.append(xml)
        y += 134
    return out


def numbered_bullets_page(st, s, idx, total, content_top):
    out = []
    y = content_top + 14
    for k, b in enumerate(s.get("bullets", []), 1):
        out.append(t(MARGIN, y, f"{k:02d}", px=26, fill=st["accent"],
                     family=st["kicker_family"], weight="bold"))
        xml, ny = block(MARGIN + 62, y, b, px=22, fill=st["body"],
                        width=W - 2 * MARGIN - 62, lh=1.4, family=st["body_family"])
        out.append(xml)
        y = ny + 24
        if k < len(s.get("bullets", [])):
            out.append(line(MARGIN, y - 14, W - MARGIN, y - 14, st["rule"], 1))
    return out


def toc_page(st, s, idx, total, content_top):
    out = []
    items = s.get("items", [])
    col_w = (W - 2 * MARGIN - 60) / 2
    for k, item in enumerate(items):
        col, row = divmod(k, 3)
        x = MARGIN + col * (col_w + 60)
        y = content_top + 26 + row * 92
        out.append(t(x, y, f"{k + 1:02d}", px=30, fill=st["accent"],
                     family=st["kicker_family"], weight="bold"))
        xml, _ = block(x + 66, y, item, px=23, fill=st["body"], width=col_w - 66,
                       lh=1.3, family=st["body_family"], max_lines=2)
        out.append(xml)
        out.append(line(x, y + 46, x + col_w, y + 46, st["rule"], 1))
    return out


def cover(st, s, idx, total):
    out = [rect(0, 0, W, H, st["bg"])]
    if st["band"]:      # 深色版：右侧竖向示意块
        out.append(rect(0, 0, W, 8, st["accent"]))
        out.append(rect(W - 300, 120, 220, 12, st["accent"]))
        out.append(rect(W - 300, 150, 150, 12, st["accent2"]))
    else:               # 期刊版：双细线
        out.append(line(MARGIN, 96, W - MARGIN, 96, st["title"], 3))
        out.append(line(MARGIN, 104, W - MARGIN, 104, st["rule"], 1))
    out.append(t(MARGIN, 150, s.get("eyebrow", ""), px=22, fill=st["accent"],
                 family=st["kicker_family"], weight="bold", ls=2))
    px = st["cover_title_px"]
    lines = (wrap(s["title"], W - 2 * MARGIN - 130, px)
             + wrap(s.get("title2", ""), W - 2 * MARGIN - 130, px))
    for i, ln in enumerate([x for x in lines if x]):
        out.append(t(MARGIN, 246 + i * px * 1.26, ln, px=px, fill=st["title"],
                     family=st["title_family"], weight="bold"))
    y = 246 + len([x for x in lines if x]) * px * 1.26 + 30
    out.append(line(MARGIN, y, MARGIN + 220, y, st["accent"], 3))
    metas = [s.get("presenter", ""), s.get("advisor", ""), s.get("major", ""),
             s.get("date", "")]
    for i, m in enumerate([x for x in metas if x]):
        out.append(t(MARGIN, y + 62 + i * 42, m, px=22, fill=st["body"],
                     family=st["body_family"]))
    out.append(t(W - MARGIN, H - 56, f"{idx:02d} / {total}", px=21, fill=st["muted"],
                 anchor="end", family=MONO))
    return out


def end_page(st, s, idx, total):
    out = [rect(0, 0, W, H, st["bg"])]
    if st["band"]:
        out.append(rect(0, 0, W, 8, st["accent"]))
    else:
        out.append(line(MARGIN, 96, W - MARGIN, 96, st["title"], 3))
    out.append(t(MARGIN, 300, s.get("title", ""), px=46, fill=st["title"],
                 family=st["title_family"], weight="bold"))
    if s.get("title2"):
        out.append(t(MARGIN, 372, s["title2"], px=32, fill=st["accent"],
                     family=st["title_family"], weight="bold"))
    out.append(line(MARGIN, 430, MARGIN + 220, 430, st["accent"], 3))
    return out


# ------------------------------------------------------------------ 主流程
def render(style_key: str, outline: dict) -> Path:
    st = STYLES[style_key]
    slides = outline["slides"]
    meta = outline["meta"]
    total = len(slides)
    proj = BUILD / f"svgproj_{style_key}"
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "svg_output").mkdir(parents=True)
    (proj / "notes").mkdir()
    (proj / "images").mkdir()
    for png in FIGDIR.glob("*.png"):
        shutil.copy(png, proj / "images" / png.name)

    for s in slides:
        n, kind = s["n"], s["type"]
        idx = n
        if kind == "title":
            body = cover(st, {**meta, "eyebrow": s.get("eyebrow", "")}, idx, total)
            body[0] = rect(0, 0, W, H, st["bg"])
        elif kind == "end":
            body = end_page(st, s, idx, total)
        else:
            dark = st is STYLES["F"]
            kicker = f"// {idx:02d} / {s.get('subtitle', '')}" if dark else ""
            head = frame(st, kicker, idx, total)
            h, y = heading(st, s["title"], None if dark else s.get("subtitle"))
            head += h
            if s.get("cards_problems"):          # 大纲里 type=cards 但内容是问题-对策
                head += problems_page(st, s, idx, total, y)
            else:
                fn = {"toc": toc_page, "figure": figure_page, "bullets": bullets_page,
                      "cards": cards_page, "steps": steps_page}[kind]
                head += fn(st, s, idx, total, y)
            if s.get("takeaway"):
                head += takeaway(st, s["takeaway"])
            body = head
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
               f'width="{W}" height="{H}" font-family="{CN}">\n  '
               + "\n  ".join(body) + "\n</svg>\n")
        (proj / "svg_output" / f"{n:02d}_{kind}.svg").write_text(svg, encoding="utf-8")
        note = s.get("note")
        if note:
            (proj / "notes" / f"{n:02d}_{kind}.md").write_text(note + "\n", encoding="utf-8")

    # spec_lock：ppt-master 的导出契约文件
    (proj / "spec_lock.md").write_text(f"""<!-- ppt-master-schema: spec-lock/v1 -->
# Execution Lock

## canvas
- viewBox: 0 0 {W} {H}
- format: PPT 16:9

## communication
- primary_language: zh-Hans-CN
- audience: 学位论文中期检查评委会（导师与检查小组）
- objective: 讲清研究思路与各项工作完成到哪一步，并说明后续安排
- core_message: 主体分析工作已完成，机制关联分析与抑菌实验验证正在推进

## mode
- mode: custom
- mode_behavior: 按研究逻辑展开——思路、已完成工作、下一步计划、进度与对策，结论先行的同时保留证据来源。

## visual_style
- visual_style: custom
- visual_style_behavior: {st['name']}：{'深色画布 + 青色强调 + 单色网格底纹，结论条为深色整条色带' if style_key == 'F' else '白底纸面 + 期刊红强调 + 细线分隔，标题用衬线体，结论条为细线与方点'}。

## colors
- primary: {st['accent']}
- accent: {st['accent2']}
- background: {st['bg']}
- surface: {st['panel']}
- secondary_text: {st['muted']}
- divider: {st['rule']}

## typography
- font_family: {CN}
- title_family: {st['title_family']}
- body_family: {st['body_family']}
- body: 22
- title: {st['title_px']}

## icons
- library: none
- inventory: none

## page_rhythm
""" + "\n".join(f"- P{n:02d}: {'breathing' if n in (1, 2, total) else 'dense'}"
                 for n in range(1, total + 1)) + """

## pptx_structure
- mode: flat

## forbidden
- `mask`, `<style>`, `class`, external CSS, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`
- HTML named entities in text; write typography as raw Unicode and escape XML reserved characters
- 任何一页文字不得小于 15 pt (user)
""", encoding="utf-8")

    # 自检：所有 <text> 的 font-size 必须 >= MIN_PX
    bad = []
    for f in sorted((proj / "svg_output").glob("*.svg")):
        for m in re.finditer(r'font-size="([\d.]+)"', f.read_text(encoding="utf-8")):
            if float(m.group(1)) < MIN_PX:
                bad.append((f.name, m.group(1)))
    if bad:
        raise SystemExit(f"SVG 字号自检未通过（<{MIN_PX}px）: {bad}")

    out = OUT_DIR / f"中期答辩_{style_key}_{st['name']}.pptx"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(PM_EXPORT), str(proj), "-q",
           "--enable-dangerous-nonconforming-svg-export", "-o", str(out)]
    print("  ", " ".join(str(c) for c in cmd[:4]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()
    print("\n".join(tail[-4:]) if tail else r.stderr[-800:])
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"ppt-master 导出失败：\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    print(f"  -> {out.relative_to(ROOT)}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", choices=list(STYLES) + ["all"], default="all")
    ap.add_argument("--outline", default=str(OUTLINE))
    a = ap.parse_args(argv)
    if not PM_EXPORT.exists():
        raise SystemExit(f"没找到 ppt-master：{PM_EXPORT}\n先运行：python code/fetch_ppt_master.py")
    outline = json.loads(Path(a.outline).read_text(encoding="utf-8"))
    keys = list(STYLES) if a.style == "all" else [a.style]
    for k in keys:
        print(f"\n=== 风格 {k}（{STYLES[k]['name']}）")
        render(k, outline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
