#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_nature.py - 按 nature-paper2ppt skill 产出 H 版（Nature 汇报风）答辩 PPT。

用的 skill
----------
[mqgg5630-cyber/nature-skills](https://github.com/mqgg5630-cyber/nature-skills) —— `skills/nature-paper2ppt`
（Apache-2.0）。本脚本严格按该 skill 的流程与规则实现：

* 路由：`manifest.yaml` → `always_load`（principles / toolchain / workflow / output-and-quality）
  + 论文类型片段。本项目是"资源 / 组学 / 流程类"成果，取 `resource` 的 **workflow-to-validation** 叙事弧
  （为什么需要 → 数据与队列 → 生成与质控流程 → 主结果 → 验证与可复现 → 复用与边界 → 总结）。
* 设计规则（`references/design-and-layout.md`）：结论式标题、图上字少（正文多进备注）、
  一张图一个论点、避免"三卡片 + 结论条"式 AI 模板感、按图的形状选版式、对齐用统一参考线。
* 图与素材（`references/figure-assets.md`）：只用本项目的自制图，保留原图标注，配"来源"小字。
* 自检（`references/self-review.md` + `scripts/audit_pptx_quality.py`）：先用本脚本自带检查，
  再用 skill 的审计脚本复核，写出 `results/qa/ppt_H_qa_report.md`。
* 术语一致性：`nature-shared/core/terminology-ledger.md` → 术语表见 `docs/术语表.md`，全篇按表用词。

用法
----
    python code/make_ppt_nature.py              # 出 H 版
    python code/make_ppt_nature.py --audit      # 顺带跑 skill 的审计脚本
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = ROOT / "docs" / "ppt_outline.json"
FIGS = ROOT / "results" / "figures"
OUT = ROOT / "deliverable" / "中期答辩_H_nature风.pptx"
QA_DIR = ROOT / "results" / "qa"
AUDIT = ROOT / "build" / "nature-skills" / "skills" / "nature-paper2ppt" / "scripts" / "audit_pptx_quality.py"

# ---------------------------------------------------------------- 统一参考线
SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
LEFT = Inches(0.70)                     # 标题 / 图 / 说明统一左边界
RIGHT_IN = 12.63                        # 内容右边界（in）
CONTENT_W = Inches(RIGHT_IN) - LEFT
TITLE_TOP = Inches(0.40)
RULE_Y = Inches(1.06)                   # 标题下的细分隔线
BODY_TOP = Inches(1.30)
SOURCE_TOP = Inches(6.62)               # 图注 / 来源行基线
NOTE_TOP = Inches(7.02)                 # 页脚行

MIN_PT = 15.0

INK = RGBColor(0x11, 0x11, 0x11)
BODY = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x77, 0x77, 0x77)
RED = RGBColor(0xB0, 0x3A, 0x2E)        # 期刊红，仅作强调
TEAL = RGBColor(0x2F, 0x5D, 0x62)
ORANGE = RGBColor(0xD9, 0x8A, 0x2B)
RULE = RGBColor(0xDD, 0xDD, 0xDA)
PANEL = RGBColor(0xF7, 0xF7, 0xF5)
CN, EN = "微软雅黑", "Arial"

PROBLEMS: list[str] = []


# ---------------------------------------------------------------- 基础工具
def set_font(run, size, bold=False, color=INK):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    f.name = EN
    rPr = run._r.get_or_add_rPr()
    for tag, face in (("a:ea", CN), ("a:cs", EN)):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", face)
    if size < MIN_PT:
        PROBLEMS.append(f"font {size} pt below {MIN_PT} pt")


def tb(slide, left, top, width, height, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.03)
    tf.margin_top = tf.margin_bottom = 0
    return box, tf


def para(tf, text, size=17, bold=False, color=BODY, first=False, before=0, after=0,
         spacing=1.22, align=PP_ALIGN.LEFT):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(before)
    p.space_after = Pt(after)
    p.line_spacing = spacing
    r = p.add_run()
    r.text = text
    set_font(r, size, bold, color)
    return p


def rich(tf, parts, size=17, first=False, before=0, after=0, spacing=1.22):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_before = Pt(before)
    p.space_after = Pt(after)
    p.line_spacing = spacing
    for text, bold, color in parts:
        r = p.add_run()
        r.text = text
        set_font(r, size, bold, color)
    return p


def hline(slide, y, color=RULE, width_pt=1.0, left=LEFT, right=Inches(RIGHT_IN)):
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, y, right - left, Pt(width_pt))
    ln.fill.solid()
    ln.fill.fore_color.rgb = color
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def rect(slide, left, top, width, height, fill, line=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    return sh


def title(slide, text, *, size=25, second=None):
    """结论式标题 + 细分隔线；标题过长会记录为问题。"""
    if len(text) > 34:
        PROBLEMS.append(f"title too long ({len(text)}): {text}")
    _, tf = tb(slide, LEFT, TITLE_TOP, CONTENT_W, Inches(0.60))
    para(tf, text, size=size, bold=True, color=INK, first=True, spacing=1.0)
    if second:
        _, tf2 = tb(slide, LEFT, Inches(0.94), CONTENT_W, Inches(0.34))
        para(tf2, second, size=15, color=MUTED, first=True, spacing=1.0)
        hline(slide, Inches(1.30))
    else:
        hline(slide, RULE_Y)


def footer(slide, idx, total, note=None):
    _, tf = tb(slide, LEFT, NOTE_TOP, Inches(9.6), Inches(0.34))
    para(tf, note or "研究生论文中期检查 · 文绍华", size=15, color=MUTED, first=True, spacing=1.0)
    _, tf2 = tb(slide, Inches(11.0), NOTE_TOP, Inches(1.63), Inches(0.34))
    para(tf2, f"{idx} / {total}", size=15, color=MUTED, first=True, spacing=1.0,
         align=PP_ALIGN.RIGHT)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def picture(slide, name, top, height, *, left=None, width=None):
    from PIL import Image
    path = FIGS / name
    iw, ih = Image.open(path).size
    if width is None:
        width = CONTENT_W
    if left is None:
        left = LEFT
    w = float(width)
    h = w * ih / iw
    if h > float(height):                       # 以高度为准缩回来
        h = float(height)
        w = h * iw / ih
    pic = slide.shapes.add_picture(str(path), Emu(int(left)), top, Emu(int(w)), Emu(int(h)))
    return pic, Emu(int(left)), Emu(int(w)), Emu(int(h))


def bullets_block(slide, items, top, *, size=17, gap=12, width=None, x=None):
    x = x or LEFT
    width = width or CONTENT_W
    _, tf = tb(slide, x, top, width, Inches(4.4))
    for k, text in enumerate(items):
        if isinstance(text, tuple):
            tag, rest = text
            rich(tf, [(tag, True, TEAL), ("　" + rest, False, BODY)], size=size,
                 first=(k == 0), before=(0 if k == 0 else gap), spacing=1.24)
        else:
            para(tf, text, size=size, first=(k == 0), before=(0 if k == 0 else gap),
                 spacing=1.24)


# ---------------------------------------------------------------- 各页版式
def cover(prs, s, total, meta):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.10), RED)
    _, tf = tb(slide, LEFT, Inches(0.95), CONTENT_W, Inches(0.4))
    para(tf, s.get("eyebrow", ""), size=16, color=RED, first=True, spacing=1.0)
    _, tf = tb(slide, LEFT, Inches(1.62), CONTENT_W, Inches(2.2))
    para(tf, s["title"], size=34, bold=True, color=INK, first=True, spacing=1.16)
    para(tf, s.get("title2", ""), size=34, bold=True, color=INK, spacing=1.16)
    hline(slide, Inches(4.16), RED, 2.4, left=LEFT, right=LEFT + Inches(2.1))
    _, tf = tb(slide, LEFT, Inches(4.42), Inches(8.6), Inches(1.9))
    for k, line in enumerate([meta["presenter"], meta["advisor"], meta["major"],
                              f"汇报日期：{meta['date']}"]):
        para(tf, line, size=16, color=BODY, first=(k == 0), before=0 if k == 0 else 8,
             spacing=1.15)
    _, tf = tb(slide, Inches(9.6), Inches(4.42), Inches(3.03), Inches(1.2))
    para(tf, "研究思路 · 已完成工作 · 下一步计划", size=15, color=MUTED, first=True,
         align=PP_ALIGN.RIGHT, spacing=1.2)
    footer(slide, 1, total, "研究生论文中期检查")
    notes(slide, "各位老师好，我汇报的题目是《基于深度学习的阿尔茨海默症患者与健康人群肠道微生物组中抗菌肽的差异性研究》。"
                 "本次中期检查重点说明研究思路，以及每一项工作完成到哪一步。")
    return slide


def claim_slide(prs, idx, total, *, headline, support, aside, note):
    """claim-led：一句主张 + 两条支撑 + 右侧窄栏，不用卡片。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=26)
    _, tf = tb(slide, LEFT, Inches(1.62), Inches(7.9), Inches(3.4))
    for k, line in enumerate(support):
        para(tf, line, size=18, color=BODY, first=(k == 0), before=0 if k == 0 else 14,
             spacing=1.34)
    ln = rect(slide, Inches(9.0), Inches(1.62), Pt(1.0), Inches(3.3), RULE)
    _, tf = tb(slide, Inches(9.35), Inches(1.62), Inches(3.28), Inches(3.4))
    for k, line in enumerate(aside):
        para(tf, line, size=16, color=MUTED, first=(k == 0), before=0 if k == 0 else 12,
             spacing=1.3)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def figure_slide(prs, idx, total, *, headline, figure, reading, note,
                 layout="full", caption=None, source=None):
    """figure-dominant / process-wide / rail：按图的形状选择版式。

    说明行一律放在图片下沿之下（按图片实际高度计算），避免与图片重叠。
    图下不再排“来源”小字（source 参数保留只为兼容旧调用，不绘制）。
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    if layout == "full":
        pic, _, w, h = picture(slide, figure, BODY_TOP, Inches(4.12))
        if float(w) < float(CONTENT_W) - Inches(0.30):      # 未占满宽度时水平居中
            shift = int((float(CONTENT_W) - float(w)) / 2)
            pic.left = Emu(int(float(pic.left)) + shift)
        bottom_in = (float(BODY_TOP) + float(h)) / 914400.0
        y = min(bottom_in + 0.16, 5.55)
        _, tf = tb(slide, LEFT, Inches(y), CONTENT_W, Inches(0.95))
        para(tf, reading, size=17, color=BODY, first=True, spacing=1.3)
    elif layout == "rail":
        pic, _, w, h = picture(slide, figure, BODY_TOP, Inches(4.60), left=LEFT,
                               width=Inches(8.60))
        x = Inches(9.35)
        _, tf = tb(slide, x, BODY_TOP, Inches(3.28), Inches(4.9))
        para(tf, "解读", size=16, bold=True, color=TEAL, first=True, spacing=1.1)
        para(tf, reading, size=16, color=BODY, before=8, spacing=1.3)
    elif layout == "wide":
        pic, _, w, h = picture(slide, figure, BODY_TOP, Inches(4.30))
        if float(w) < float(CONTENT_W) - Inches(0.30):
            shift = int((float(CONTENT_W) - float(w)) / 2)
            pic.left = Emu(int(float(pic.left)) + shift)
        bottom_in = (float(BODY_TOP) + float(h)) / 914400.0
        _, tf = tb(slide, LEFT, Inches(bottom_in + 0.14), CONTENT_W,
                   Inches(max(0.4, 6.42 - bottom_in)))
        para(tf, reading, size=16, color=BODY, first=True, spacing=1.24)
    else:                                   # "band"：图 + 底部说明带
        pic, _, w, h = picture(slide, figure, BODY_TOP, Inches(4.45))
        rect(slide, LEFT, Inches(5.96), CONTENT_W, Inches(0.52), PANEL)
        _, tf = tb(slide, Inches(0.86), Inches(5.96), Inches(11.5), Inches(0.52),
                   anchor=MSO_ANCHOR.MIDDLE)
        para(tf, reading, size=16, color=BODY, first=True, spacing=1.1)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def metrics_slide(prs, idx, total, *, headline, lead, stages, note):
    """资源概览：一句导语 + 阶段条带（不排成等宽卡片）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    _, tf = tb(slide, LEFT, Inches(1.56), Inches(11.4), Inches(1.2))
    para(tf, lead, size=19, color=BODY, first=True, spacing=1.32)
    x = float(LEFT)
    gap = 0.24
    w = (float(CONTENT_W) - Inches(gap) * (len(stages) - 1)) / len(stages)
    for k, (label, desc) in enumerate(stages):
        cx = Emu(int(float(LEFT) + k * (w + Inches(gap))))
        bar = rect(slide, cx, Inches(3.30), Emu(int(w)), Pt(3),
                   TEAL if k < len(stages) - 1 else RED)
        _, tf = tb(slide, cx, Inches(3.52), Emu(int(w)), Inches(1.1))
        para(tf, label, size=18, bold=True, color=INK, first=True, spacing=1.1)
        para(tf, desc, size=15, color=MUTED, before=4, spacing=1.2)
    hline(slide, Inches(4.86))
    _, tf = tb(slide, LEFT, Inches(5.10), Inches(11.4), Inches(1.1))
    para(tf, "分析口径：全部样本使用同一套处理流程与参数，分组信息与测序数据一一对应。",
         size=16, color=BODY, first=True, spacing=1.3)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def flow_slide(prs, idx, total, *, headline, lead, steps, note):
    """流程页：原生可编辑方框 + 箭头，蛇形两行（①→⑥ 后接下行 ⑦→⑫）。

    steps: [(序号, 标题, 说明, 状态)]，状态 "done" / "doing"。
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    _, tf = tb(slide, LEFT, Inches(1.12), CONTENT_W, Inches(0.30))
    para(tf, lead, size=15, color=MUTED, first=True, spacing=1.0)

    n_col = 6
    gap = 0.15
    w = (float(CONTENT_W) - Inches(gap) * (n_col - 1)) / n_col
    h = Inches(1.68)
    top1, top2 = Inches(1.46), Inches(3.44)
    for row, (top, flip) in enumerate(((top1, False), (top2, True))):
        for c in range(n_col):
            num, label, desc, status = steps[row * n_col + c]
            x = Emu(int(float(LEFT) + c * (w + Inches(gap))))
            card = rect(slide, x, top, Emu(int(w)), h, PANEL)
            rect(slide, x, top, Emu(int(w)), Pt(3), TEAL if status == "done" else ORANGE)
            tf = card.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = Inches(0.10)
            tf.margin_top = Inches(0.10)
            tf.margin_bottom = Inches(0.06)
            rich(tf, [(num + " ", True, TEAL if status == "done" else RED),
                      (label, True, INK)], size=15, first=True, spacing=1.12)
            para(tf, desc, size=15, color=BODY, before=4, spacing=1.16)
            if c < n_col - 1:                     # 行内箭头：第一行向右、第二行向左
                ax_ = Emu(int(float(x) + float(w) + 0.035 * 914400))
                aw = Emu(int((gap - 0.07) * 914400))
                arrow = slide.shapes.add_shape(
                    MSO_SHAPE.LEFT_ARROW if flip else MSO_SHAPE.RIGHT_ARROW,
                    ax_, Emu(int(float(top) + float(h) / 2 - 0.055 * 914400)),
                    aw, Emu(int(0.11 * 914400)))
                arrow.fill.solid()
                arrow.fill.fore_color.rgb = MUTED
                arrow.line.fill.background()
                arrow.shadow.inherit = False
        if not flip:                              # 第一行末列转第二行
            x6 = float(LEFT) + (n_col - 1) * (w + Inches(gap))
            down = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW,
                Emu(int(x6 + w / 2 - 0.06 * 914400)), Emu(int(float(top) + float(h) + 0.03 * 914400)),
                Emu(int(0.12 * 914400)), Emu(int(0.22 * 914400)))
            down.fill.solid()
            down.fill.fore_color.rgb = MUTED
            down.line.fill.background()
            down.shadow.inherit = False

    _, tf = tb(slide, LEFT, Inches(5.30), Inches(4.0), Inches(0.30))
    rich(tf, [("■ ", True, TEAL), ("已完成　", False, BODY),
              ("■ ", True, ORANGE), ("正在推进", False, BODY)], size=15, first=True, spacing=1.0)
    _ = tf
    rect(slide, LEFT, Inches(5.72), CONTENT_W, Inches(0.62), PANEL)
    _, tf = tb(slide, Inches(0.88), Inches(5.72), Inches(11.6), Inches(0.62),
               anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "全流程使用同一套参考集与参数，样本的分组信息与测序数据一一对应；"
             "青色标注的步骤已完成，橙色标注的正在推进。", size=15, color=BODY, first=True, spacing=1.12)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def stage_slide(prs, idx, total, *, headline, lead, facts, stages, note):
    """分组页：上排关键规模，下排五个认知阶段的分组构成。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    _, tf = tb(slide, LEFT, Inches(1.30), CONTENT_W, Inches(0.60))
    para(tf, lead, size=17, color=BODY, first=True, spacing=1.24)

    fw = float(CONTENT_W) / len(facts)
    for k, (big, small) in enumerate(facts):
        x = Emu(int(float(LEFT) + k * fw))
        _, tf = tb(slide, x, Inches(1.94), Emu(int(fw - 0.20 * 914400)), Inches(0.46))
        para(tf, big, size=24, bold=True, color=TEAL, first=True, spacing=1.0)
        _, tf = tb(slide, x, Inches(2.42), Emu(int(fw - 0.20 * 914400)), Inches(0.52))
        para(tf, small, size=15, color=MUTED, first=True, spacing=1.0)
    hline(slide, Inches(3.00))

    sw = float(CONTENT_W) / len(stages)
    for k, (code, label, n, feat, color) in enumerate(stages):
        x = Emu(int(float(LEFT) + k * sw))
        rect(slide, x, Inches(3.16), Emu(int(sw - 0.24 * 914400)), Pt(3), color)
        _, tf = tb(slide, x, Inches(3.28), Emu(int(sw - 0.20 * 914400)), Inches(0.34))
        para(tf, code, size=18, bold=True, color=INK, first=True, spacing=1.0)
        _, tf = tb(slide, x, Inches(3.62), Emu(int(sw - 0.20 * 914400)), Inches(1.20))
        para(tf, label, size=16, color=BODY, first=True, spacing=1.14)
        para(tf, n, size=15, color=TEAL, before=3, spacing=1.14)
        para(tf, feat, size=15, color=MUTED, before=3, spacing=1.14)
    hline(slide, Inches(4.90))
    _, tf = tb(slide, LEFT, Inches(5.06), CONTENT_W, Inches(1.30))
    para(tf, "分层方式：5 个阶段 × 2 个性别 × 3 个年龄段（60—69、70—79、≥80 岁）= 30 个分层单元；"
             "每个单元内按年龄与性别匹配，最终选出 265 例匹配亚队列——各阶段 53 例、每组 35 女 / 18 男，"
             "组间平均年龄最大差 1.8 岁，保证阶段之间的差异不来自年龄与性别构成。",
         size=16, color=BODY, first=True, spacing=1.26)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def table_slide(prs, idx, total, *, headline, rows, note, header=None, widths=None,
                row_h=0.52, size=15):
    """对照表：原生可编辑表格（nature skill 建议显式数值用原生表）。

    header / widths 可自定义（机制补充页用它排“证据强度分级”）。
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    head = list(header) if header else ["环节", "开题计划", "现阶段结果"]
    n_col = len(head)
    n_rows = len(rows) + 1
    shape = slide.shapes.add_table(n_rows, n_col, LEFT, BODY_TOP + Inches(0.05),
                                   CONTENT_W, Inches(row_h) * n_rows)
    for r in range(n_rows):
        table_h = shape.table
        table_h.rows[r].height = Inches(row_h)
    table = shape.table
    if widths:
        for i, w in enumerate(widths):
            table.columns[i].width = Inches(w)
    elif n_col == 3:
        table.columns[0].width = Inches(2.0)
        table.columns[1].width = Inches(4.6)
        table.columns[2].width = CONTENT_W - Inches(6.6)
    for c, text in enumerate(head):
        cell = table.cell(0, c)
        cell.text = ""
        para(cell.text_frame, text, size=size, bold=True, color=INK, first=True, spacing=1.05)
        cell.fill.solid()
        cell.fill.fore_color.rgb = PANEL
        cell.margin_top = cell.margin_bottom = Inches(0.03)
    for r, row in enumerate(rows, start=1):
        for col, text in enumerate(row):
            cell = table.cell(r, col)
            cell.text = ""
            para(cell.text_frame, text, size=size,
                 color=INK if col == 0 else BODY, first=True, spacing=1.05)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def discussion_slide(prs, idx, total, *, headline, pairs, note):
    """问题与对策：开放排版，编号 + 细线，不做卡片。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    y0, y_end = 1.58, 6.30
    pitch = min(1.62, (y_end - y0) / max(len(pairs), 1))
    y = y0
    for k, (q, a) in enumerate(pairs, 1):
        _, tf = tb(slide, LEFT, Inches(y), Inches(0.6), Inches(0.5))
        para(tf, f"{k:02d}", size=20, bold=True, color=RED, first=True, spacing=1.0)
        _, tf = tb(slide, LEFT + Inches(0.62), Inches(y), Inches(11.3),
                   Inches(pitch - 0.12))
        para(tf, q, size=18, bold=True, color=INK, first=True, spacing=1.08)
        para(tf, a, size=16, color=BODY, before=3, spacing=1.20)
        y += pitch
        if k < len(pairs):
            hline(slide, Inches(y - 0.30))
    footer(slide, idx, total)
    notes(slide, note)
    return slide


def closing(prs, idx, total, *, headline, lines, note, thanks=False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title(slide, headline, size=25)
    _, tf = tb(slide, LEFT, Inches(1.62), Inches(11.4), Inches(3.6))
    for k, line in enumerate(lines):
        para(tf, line, size=18, color=BODY, first=(k == 0), before=0 if k == 0 else 14,
             spacing=1.34)
    if thanks:
        hline(slide, Inches(5.30), RED, 2.4, left=LEFT, right=LEFT + Inches(2.1))
        _, tf = tb(slide, LEFT, Inches(5.56), Inches(11.4), Inches(0.8))
        para(tf, "谢谢各位老师，请批评指正。", size=20, bold=True, color=INK, first=True,
             spacing=1.1)
    footer(slide, idx, total)
    notes(slide, note)
    return slide



# ---------------------------------------------------------------- 标准内容页
FLOW_STEPS = [
    ("①", "测序与质控", "fastp 质控\nKneadData 去宿主", "done"),
    ("②", "组装与分箱", "MEGAHIT 组装\nMetaBAT2 分箱\nCONCOCT 分箱", "done"),
    ("③", "参考基因组集", "metaWRAP 提纯\ndRep 去冗余", "done"),
    ("④", "sORF 预测", "EMBOSS getorf\n长度 5—50 aa", "done"),
    ("⑤", "去冗余建库", "序列级精确去冗余\n非冗余短肽库", "done"),
    ("⑥", "共识预测", "Attention / LSTM\n/ BERT 一致阳性", "done"),
    ("⑦", "阶段差异分析", "CoverM 定量\nCLR 变换\nKruskal-Wallis", "done"),
    ("⑧", "表达证据去重", "宏蛋白组二次去重\n剔除无表达序列", "done"),
    ("⑨", "特有抗菌肽", "健康人群特有肽\n各阶段特有肽", "done"),
    ("⑩", "机制关联分析", "分子对接 + 动力学\n给出候选优先序", "doing"),
    ("⑪", "抑菌实验验证", "纸片扩散法筛查\n微量肉汤稀释法 MIC", "doing"),
    ("⑫", "整理与撰写", "学位论文与投稿\n结果汇总", "doing"),
]

STAGE_FACTS = [("265 例", "匹配亚队列 · 各阶段 53 例"),
               ("53 例", "每阶段样本量 · 每组 35 女 / 18 男"),
               ("3 个年龄段", "60—69 · 70—79 · ≥80 岁"),
               ("68.2—70.0 岁", "各阶段平均年龄 · 组间差 ≤1.8 岁")]

STAGE_ROWS = [("NC", "认知正常（对照）", "53 例 ｜ 35 女 / 18 男", "平均 68.4 岁 · 多样性最高", TEAL),
              ("SCS", "主观认知下降", "53 例 ｜ 35 女 / 18 男", "平均 68.2 岁 · 组成偏移", TEAL),
              ("SCD", "可疑认知障碍", "53 例 ｜ 35 女 / 18 男", "平均 69.1 岁 · 屏障标志↑", ORANGE),
              ("MCI", "轻度认知障碍", "53 例 ｜ 35 女 / 18 男", "平均 68.8 岁 · 失衡最明显", ORANGE),
              ("AD", "阿尔茨海默症", "53 例 ｜ 35 女 / 18 男", "平均 70.0 岁 · 变化幅度最大", RED)]


def std_flow_slide(prs, idx, total, progress="full"):
    """标准流程页；progress="half" 时只把前四步记为已完成（中间版 2 用）。"""
    cut = 4 if progress == "half" else 9      # 完整版：前九步已完成，后三步推进中
    steps = [(n, l, d, "done" if k < cut else "doing")
             for k, (n, l, d, _st) in enumerate(FLOW_STEPS)]
    if progress == "half":
        note = ("这页说明整体流程：从测序数据到候选抗菌肽清单，共十二步。"
                "工具链是 fastp 与 KneadData 质控去宿主、MEGAHIT 组装、MetaBAT2 / MaxBin2 / CONCOCT "
                "联合分箱、metaWRAP 提纯、dRep 去冗余、EMBOSS getorf 预测 sORF、三模型一致阳性判定、"
                "CoverM 定量与 Kruskal-Wallis / Mann-Whitney U 检验。"
                "目前前四步已完成，其余内容安排在下一阶段推进。")
    else:
        note = ("这页说明整体流程：从测序数据到候选抗菌肽清单，共十二步，输入输出都可追溯。"
                "工具链是 fastp 与 KneadData 做质控去宿主，MEGAHIT 组装，MetaBAT2、MaxBin2 与 CONCOCT "
                "多算法联合分箱后 metaWRAP 提纯，dRep 按 95% ANI 去冗余得到参考基因组集，"
                "EMBOSS getorf 预测 sORF 并做序列级去冗余，Attention / LSTM / BERT 三模型一致阳性才纳入候选，"
                "CoverM 定量并做 CLR 变换，用 Kruskal-Wallis 与 Mann-Whitney U 做组间检验，"
                "再用宏蛋白组表达证据二次去重。前九步已经在中期前完成，最后三步正在推进——"
                "机制关联分析、抑菌实验验证与结果整理。")
    flow_slide(prs, idx, total,
        headline="宏基因组分析流程：从测序数据到候选抗菌肽清单",
        lead="流程按“数据 → 序列 → 预测 → 统计 → 功能”顺序推进，每一步的输入输出都可追溯。",
        steps=steps, note=note)


def std_stage_slide(prs, idx, total, headline=None):
    stage_slide(prs, idx, total,
        headline=headline or "分阶段组的划分：阶段、性别、年龄三层匹配后再比较",
        lead="队列按认知功能分为五个阶段，并在每个阶段内按性别与年龄段匹配，"
             "保证阶段之间可直接比较。",
        facts=STAGE_FACTS,
        stages=STAGE_ROWS,
        note="分组方式是这页的重点：五个认知阶段，每阶段内再按性别与三个年龄段分层，共三十个分层单元；"
             "每个单元内按年龄与性别匹配，最终选出 265 例匹配亚队列——各阶段 53 例、每组 35 女 / 18 男，"
             "组间平均年龄最大差 1.8 岁，这样阶段之间的差异不会来自年龄与性别构成。")


# ---------------------------------------------------------------- 逐页内容
def final_closing(prs, total: int) -> None:
    """H 版最后一页（谢谢页）：放在机制补充页之后，保证它是整份 PPT 的最后一页。"""
    closing(prs, total, total,
        headline="主要分析已完成，剩余工作风险可控",
        lines=[
            "确认事实：数据资源、短肽库、三模型共识预测、分阶段差异分析与特有抗菌肽筛选均已完成。",
            "待完成：机制关联分析的结论整理、候选抗菌肽的抑菌实验验证，以及学位论文与投稿论文撰写。",
            "进度安排：按开题计划推进，后续不依赖新的数据生产。",
        ],
        note="总结一下：主体分析工作已经在中期完成，剩余是机制关联的结论整理、抑菌实验验证和论文撰写，"
             "整体风险可控。我的汇报到此结束，请各位老师批评指正。",
        thanks=True)


def build(outline: dict, total: int = 24, *, with_final: bool = True) -> Presentation:
    meta = outline["meta"]
    S = {s["n"]: s for s in outline["slides"]}
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

    cover(prs, S[1], total, meta)

    claim_slide(prs, 2, total,
        headline="肠—脑轴把 AD 与肠道微生物组联系起来，但缺少落到分子层面的对象",
        support=[
            "AD 患者与健康人群的肠道微生物组在组成与功能上存在差异，菌群失衡可通过免疫与代谢途径影响中枢炎症状态。",
            "微生物基因组的小开放阅读框可编码抗菌肽，直接存在于肠腔，是连接微生物刺激与神经炎症的候选效应分子。",
            "现有抗菌肽研究多基于通用训练集与宿主来源序列，缺少面向 AD 人群、并按认知阶段分层比较的工作。",
        ],
        aside=["两个约束条件：",
               "① 计算预测必须有多模型与表达层面的相互印证；",
               "② 验证手段要在常规实验室条件下可完成。"],
        note="研究背景分三点：AD 与肠道微生物组的关系已有较多证据；微生物基因组编码的抗菌肽是可能的效应分子；"
             "现有研究缺少面向 AD 人群并按认知阶段分层的分析。由此提出本次研究的切入点。")

    claim_slide(prs, 3, total,
        headline="研究按“数据—预测—统计—功能”四层推进，主体分析已完成",
        support=[
            "数据与序列层：全队列宏基因组数据统一处理，构建微生物源短肽库并保留来源可追溯信息。",
            "预测层：三类深度学习模型独立预测，取一致阳性序列构成候选抗菌肽集合。",
            "统计与表达层：按认知阶段比较差异，并以宏蛋白组表达证据二次去重，筛选健康人群特有与各阶段特有抗菌肽。",
            "功能层：对特有抗菌肽开展发病机制关联分析与抑菌实验验证。",
        ],
        aside=["当前状态：",
               "前四层中的前三层已完成，功能层正在实施；",
               "整体进度与开题计划一致。"],
        note="整体研究分四层：数据与序列、预测、统计与表达、功能。前三层已完成，第四层正在进行，"
             "这也是本次中期检查要重点汇报的完成度。")

    metrics_slide(prs, 4, total,
        headline="队列按认知功能分阶段，样本与元数据一一对应",
        lead="以公开宏基因组队列为对象，按认知功能与临床诊断把样本分为五个阶段，用于比较候选抗菌肽在病程中的变化。",
        stages=[("NC", "认知正常对照"), ("SCS", "主观认知下降"), ("SCD", "可疑认知障碍"),
                ("MCI", "轻度认知障碍"), ("AD", "阿尔茨海默症")],
        note="队列按认知功能分五个阶段：NC、SCS、SCD、MCI 与 AD，样本的临床分组信息与测序数据一一对应，"
             "为后续的分阶段差异分析提供可比的基础。")

    std_flow_slide(prs, 5, total)

    std_stage_slide(prs, 6, total)

    figure_slide(prs, 7, total,
        headline="研究路线：前五项已完成，后两项正在推进",
        figure="figA_研究思路总览.png", layout="full",
        reading="数据资源与参考集、短肽库、三模型共识预测、分阶段差异分析、宏蛋白组二次去重五项已完成；"
                "机制关联分析与抑菌实验验证两项正在推进。",
        caption="研究技术路线与完成状态",
        note="这一页是整体路线：前五项，也就是数据、短肽库、预测、分阶段差异和宏蛋白组去重，已经全部完成；"
             "后两项机制关联分析和抑菌实验验证正在推进。")

    figure_slide(prs, 8, total,
        headline="三模型一致阳性的序列才纳入候选集合",
        figure="figB_三模型预测.png", layout="rail",
        reading="Attention、LSTM、BERT 三个模型相互独立地给出抗菌肽概率；只有三者一致判为阳性的序列才进入候选集合，"
                "以此降低单一模型的偏倚。该步骤已完成，候选名单已产出。",
        note="预测环节采用 Attention、LSTM、BERT 三个模型分别预测，只有三者一致判为阳性的序列才纳入候选集合。"
             "这样处理的目的是降低单一模型带来的假阳性，提高候选集合的可信度；这一步已经完成。")

    figure_slide(prs, 9, total,
        headline="分阶段比较给出随病程变化的候选抗菌肽",
        figure="figC_分阶段差异分析.png", layout="band",
        reading="按认知阶段分组比较候选抗菌肽的丰度与组成差异，筛选随病程变化明显的候选抗菌肽。",
        note="差异分析按认知阶段分组，比较各阶段与健康人群之间候选抗菌肽的丰度与组成差异，"
             "得到一批随病程变化明显的候选抗菌肽，作为后续筛选的输入。这一步也已完成。")

    figure_slide(prs, 10, total,
        headline="宏蛋白组表达证据二次去重后，得到健康人与各阶段特有抗菌肽",
        figure="figD_宏蛋白组去重.png", layout="full",
        reading="序列层面去冗余解决重复；宏蛋白组表达证据解决“有预测、无表达”的假阳性。"
                "二次去重后按组内共有、组间特比较，得到健康人群特有与各疾病阶段特有的抗菌肽清单。",
        note="在序列去冗余的基础上，引入宏蛋白组的表达证据做二次去重，只保留在蛋白层面真实存在、可检出的抗菌肽；"
             "再按组内共有、组间特比较，得到健康人群特有与各疾病阶段特有的抗菌肽清单。这一步已完成。")

    figure_slide(prs, 11, total,
        headline="机制关联从 Aβ、AChE 与炎症通路三个方向展开",
        figure="figE_机制关联.png", layout="rail",
        reading="借鉴乙酰胆碱酯酶—β-淀粉样肽复合物分子模拟研究的思路，按致病方向考察：候选肽是否"
                "促进 Aβ 成核与聚集、是否经 AChE 外周阴离子位点推动成核、是否经免疫与炎症通路放大"
                "神经炎症；输出优先序，定位为线索发现。",
        note="机制关联参照乙酰胆碱酯酶—β-淀粉样肽复合物分子模拟研究的思路，方向按致病方向设定："
             "微生物来源的淀粉样蛋白与内毒素已有先例——FapC 与 CsgA 种子加速 Aβ 纤维化并在动物模型中"
             "加重病理，LPS 缩短成核滞后期并诱导斑块与 p-tau，LL-37 与 Aβ 形成异源团簇、生成更毒的聚集体。"
             "因此分析的是候选肽是否促进 Aβ 成核与聚集、是否经 AChE 外周阴离子位点推动成核、"
             "是否经免疫与炎症通路放大神经炎症，而不是去证明它抑制 AD；结论定位为线索发现与优先序。")

    figure_slide(prs, 12, total,
        headline="抑菌实验验证给出候选抗菌肽活性的直接证据",
        figure="figF_抑菌实验方案.png", layout="band",
        reading="人工合成代表性候选肽，以大肠杆菌与金黄色葡萄球菌为指示菌，纸片扩散法初筛，微量肉汤稀释法测最低抑菌浓度。",
        note="抑菌实验验证选取有代表性的候选抗菌肽进行人工合成，以大肠杆菌与金黄色葡萄球菌作为指示菌，"
             "先用纸片扩散法观察抑菌圈做初筛，再用微量肉汤稀释法测定最低抑菌浓度，"
             "并设置阳性对照与阴性对照。这些方法在常规微生物实验室即可完成。")

    figure_slide(prs, 13, total,
        headline="进度与开题计划一致：主体分析完成，进入验证与撰写阶段",
        figure="figG_进度甘特.png", layout="full",
        reading="数据资源、短肽库、三模型共识预测、分阶段差异分析与宏蛋白组二次去重均已完成；"
                "机制关联分析与抑菌实验验证正在推进，论文撰写同步进行。",
        note="进度上，前五项已经全部完成，当前集中在机制关联分析与抑菌实验验证两件事上，"
             "论文撰写同步推进，整体进度与开题安排一致。")

    table_slide(prs, 14, total,
        headline="与开题计划相比，研究方向未变，预测与去重环节做了调整",
        rows=[
            ("数据准备", "使用公开宏基因组数据", "已完成全队列数据处理与参考集构建"),
            ("候选肽挖掘", "提取 sORF 并预测抗菌肽", "已完成短肽库构建与三模型共识预测"),
            ("差异分析", "按病程阶段比较", "已完成分阶段差异分析，新增宏蛋白组二次去重"),
            ("模型方案", "拟构建 DeepMetaAMP", "改用 Attention / LSTM / BERT 三模型协同预测"),
            ("机制与验证", "功能与可视化分析", "正在开展机制关联分析与抑菌实验验证"),
        ],
        note="这张表把开题计划与现阶段结果逐条对照：数据准备、候选肽挖掘、差异分析三项已完成；"
             "模型方案由自建模型改为三个已发表模型协同预测；机制与验证环节正在实施。研究方向没有变，"
             "调整都发生在方法层面。")

    discussion_slide(prs, 15, total,
        headline="三个已识别问题都有对应处理办法",
        pairs=[
            ("预测结果的假阳性风险",
             "以三模型共识判定提高候选集合可信度，再用宏蛋白组表达证据二次去重，最后以抑菌实验验证活性。"),
            ("部分样本缺少可用的参考基因组",
             "在丰度分析阶段改用全量基因组回填，恢复样本覆盖，并在结果中说明数据处理口径。"),
            ("机制关联的证据强度有限",
             "以分子对接与分子动力学模拟、文献比对为主，把结论定位为线索发现，不夸大因果性。"),
        ],
        note="目前识别出三个问题：预测假阳性、部分样本缺少参考基因组、机制关联证据强度有限。"
             "三者都有对应处理办法，不影响整体进度。")

    closing(prs, 16, total,
        headline="后续安排集中在机制关联、实验验证与论文撰写",
        lines=[
            "机制关联分析：完成特有抗菌肽与 Aβ 聚集、AChE 结合及炎症通路的关联分析，形成候选肽清单。",
            "抑菌实验验证：完成候选抗菌肽的合成与抑菌实验，获得抑菌活性初筛结果。",
            "结果整理与论文撰写：汇总候选抗菌肽、特有肽与验证结果，完成学位论文与投稿论文准备。",
        ],
        note="后续收尾分三块：机制关联分析、抑菌实验验证，以及结果整理与论文撰写。"
             "这些工作以已完成的数据与分析流程为基础，不再涉及大规模数据生产。")

    closing(prs, 17, total,
        headline="预期成果与现阶段的边界",
        lines=[
            "预期成果：一套可复用的分析流程、健康人与各阶段特有的候选抗菌肽清单、机制关联与抑菌活性结果，"
            "以及以第一作者投稿的 SCI 论文与学位论文。",
            "现阶段的边界：机制关联属于计算预测与文献比对，尚不能给出因果关系；抑菌实验只针对代表性候选肽，"
            "覆盖范围有限；阶段划分依据队列既有临床标签，未纳入新的评分数据。",
            "这两点会在论文中明确说明，并在后续实验中逐步补充。",
        ],
        note="预期成果包括可复用的分析流程、特有抗菌肽清单、机制关联与抑菌活性结果，以及投稿论文与学位论文。"
             "同时说明现阶段的边界：机制关联是计算预测、抑菌实验只覆盖代表性候选肽、阶段划分依据队列既有标签，"
             "这些限定会在论文中写清楚。")

    if with_final:
        final_closing(prs, total)

    return prs


def audit(path: Path) -> int:
    """本仓库自检 + skill 自带审计脚本，结果写进 results/qa/。"""
    rc = 0
    QA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[self-check] {path.name}")
    r = subprocess.run([sys.executable, str(ROOT / "code" / "check_ppt.py"), str(path)],
                       capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-2] if r.stdout.strip() else r.stderr[-400:])
    if "RESULT: OK" not in r.stdout:
        rc = 1
    if AUDIT.exists():
        rep = QA_DIR / "ppt_H_audit.md"
        r2 = subprocess.run([sys.executable, str(AUDIT), str(path), "--report", str(rep),
                             "--json", str(QA_DIR / "ppt_H_audit.json"), "--fail-on", "none"],
                            capture_output=True, text=True)
        print(r2.stdout.strip()[-600:] or r2.stderr[-600:])
    else:
        print("（未找到 nature-skills 审计脚本：先跑 python code/fetch_nature_skills.py）")
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--outline", default=str(OUTLINE))
    ap.add_argument("--mechanism", action="store_true",
                    help="在 18 页之后追加 6 页机制补充页（共 24 页）")
    a = ap.parse_args(argv)

    # 1) 术语一致性：全篇只允许术语表里的写法
    text = OUTLINE.read_text(encoding="utf-8")
    for banned in ("极简", "最小工作量", "最小可行性"):
        if banned in text:
            PROBLEMS.append(f"term not allowed: {banned}")

    outline = json.loads(text)
    total = 24 if a.mechanism else 18
    prs = build(outline, total, with_final=not a.mechanism)
    if a.mechanism:
        import make_ppt_mech as MECH
        MECH.append(prs, first_idx=18, total=24, which="full")   # 机制页插在谢谢页之前
        final_closing(prs, total)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    slides = len(prs.slides._sldIdLst)
    runs = sum(len(p.runs) for s in prs.slides for sh in s.shapes if sh.has_text_frame
               for p in sh.text_frame.paragraphs)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"slides: {slides} | runs: {runs}")
    if PROBLEMS:
        print("PROBLEMS:")
        for p in PROBLEMS:
            print("  -", p)
        return 1
    if a.audit:
        return audit(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
