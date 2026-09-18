#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mech_doc.py - 生成《抗菌肽与 AD 关联机制说明》docx。

正文来源是 **可编辑的 md**：`docs/机制说明_正文.md`
（改完直接重跑本脚本即可；三张表与参考文献条目在 `code/mech_refs.py` 里维护）

支持的写法
----------
    ## 标题                → 一级小标题（加粗 13.5 pt，段前 12 pt）
    ### 标题               → 二级小标题（加粗 12 pt）
    结论：xxx              → 带加粗标签的正文段
    边界：xxx              → 同上
    - xxx                  → 项目符号段（悬挂缩进）
    【图1/2/3】            → 插图 + 图注（居中）
    【表：方向/阶段/动力学】 → 原生表格（数据来自 mech_refs）
    > xxx                  → 灰字提示段（斜体）

用法
----
    python code/make_mech_doc.py                     # -> deliverable/抗菌肽与AD关联机制说明.docx
    python code/make_mech_doc.py --out build/x.docx  # 换个输出位置
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mech_refs as R          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "机制说明_正文.md"
OUT = ROOT / "deliverable" / "抗菌肽与AD关联机制说明.docx"
FIGS = ROOT / "results" / "figures"

INK = RGBColor(0x11, 0x11, 0x11)
BODY = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x77, 0x77, 0x77)
RED = RGBColor(0xB0, 0x3A, 0x2E)
TEAL = RGBColor(0x2F, 0x5D, 0x62)
CN, EN = "微软雅黑", "Times New Roman"

FIGURES = {
    "【图1】": ("figM1_关联逻辑链.png",
                "图 1　抗菌肽与 AD 关联的七环逻辑链（颜色表示证据强度：蓝=已有实验/临床证据，"
                "绿=计算可给出候选与优先序，橙=本课题要回答/需验证）"),
    "【图2】": ("figM2_AChE_Aβ_机制.png",
                "图 2　AChE–Aβ 复合物的分子动力学要点、同一界面的实验证据与候选抗菌肽的三个假设"),
    "【图3】": ("figM3_交叉成核机制.png",
                "图 3　抗菌肽与 Aβ 交叉成核的三条机制，以及对应的模拟与实验证据"),
}

TABLES = {
    "方向": (["分子", "在 AD 中的方向", "标本 / 部位", "文献"],
             [(a, b, c, d) for a, b, c, d in R.DIRECTION],
             (2.05, 1.05, 4.10, 0.85)),
    "阶段": (["阶段", "分组含义", "该阶段的菌群与炎症证据"],
             [(s[0], s[1].split("：")[0], s[1].split("：", 1)[1] if "：" in s[1] else "")
              for s in R.STAGES],
             (0.85, 2.10, 5.10)),
    "动力学": (["研究 / 体系", "结论要点", "文献"],
               R.MD_TABLE,
               (2.35, 4.55, 1.15)),
}


def set_font(run, size, bold=False, color=BODY, italic=False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    f.name = EN
    rPr = run._r.get_or_add_rPr()
    el = rPr.find(qn("w:eastAsia"))
    if el is None:
        el = rPr.makeelement(qn("w:eastAsia"), {})
        rPr.append(el)
    el.set(qn("w:val"), CN)


def para(doc, align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=6, spacing=1.35,
         indent=None, hanging=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    p.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = spacing
    if indent is not None:
        pf.left_indent = Inches(indent)
    if hanging is not None:
        pf.first_line_indent = Inches(-hanging)
    return p


def runs_with_bold(p, text, size, color=BODY, base_bold=False):
    """把 **加粗** 语法转成 runs。"""
    for i, seg in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not seg:
            continue
        r = p.add_run(seg)
        set_font(r, size, bold=base_bold or (i % 2 == 1), color=color)


def add_rule(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(10)
    pPr = p._p.get_or_add_pPr()
    borders = pPr.makeelement(qn("w:pBdr"), {})
    bottom = borders.makeelement(qn("w:bottom"), {})
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:color"), "B03A2E")
    borders.append(bottom)
    pPr.append(borders)


def add_table(doc, header, rows, widths):
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, text in enumerate(header):
        cell = t.cell(0, c)
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(text)
        set_font(r, 9.5, bold=True, color=INK)
        shd = cell._tc.get_or_add_tcPr().makeelement(qn("w:shd"), {})
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "F2F2F0")
        cell._tc.get_or_add_tcPr().append(shd)
    for ri, row in enumerate(rows, start=1):
        for c, text in enumerate(row):
            cell = t.cell(ri, c)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(text)
            set_font(r, 9.5, color=INK if c == 0 else BODY)
    for row in t.rows:
        for c, w in enumerate(widths):
            row.cells[c].width = Inches(w)
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    lines = Path(a.src).read_text(encoding="utf-8").splitlines()
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Inches(0.85)
    sec.top_margin = sec.bottom_margin = Inches(0.8)

    n_fig = n_tab = n_q = 0
    in_comment = False
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        i += 1
        if "<!--" in line:                       # 编写说明，不进正文
            in_comment = "-->" not in line.split("<!--", 1)[1]
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if not line.strip():
            continue

        # ---- 标题区 ----
        if line.startswith("# ") and not line.startswith("## "):
            p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=4)
            r = p.add_run(line[2:].strip())
            set_font(r, 22, bold=True, color=INK)
            p2 = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=2)
            r = p2.add_run("中期检查补充材料 · 逐条回答老师提出的八个问题")
            set_font(r, 12, color=TEAL)
            p3 = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=2)
            r = p3.add_run("文绍华　2024110316　｜　指导教师：申亮　｜　生命科学学院　｜　2026 年 9 月")
            set_font(r, 10.5, color=MUTED)
            add_rule(doc)
            continue

        # ---- 提示段 ----
        if line.startswith(">"):
            p = para(doc, indent=0.0, after=8)
            runs_with_bold(p, line.lstrip("> ").strip(), 9.5, color=MUTED)
            for r in p.runs:
                r.font.italic = True
            continue

        # ---- 一级 / 二级标题 ----
        if line.startswith("### "):
            p = para(doc, before=10, after=4)
            r = p.add_run(line[4:].strip())
            set_font(r, 12.5, bold=True, color=TEAL)
            continue
        if line.startswith("## "):
            p = para(doc, before=14, after=6)
            r = p.add_run(line[3:].strip())
            set_font(r, 14, bold=True, color=INK)
            continue

        # ---- 图 ----
        if line.strip() in FIGURES:
            name, caption = FIGURES[line.strip()]
            n_fig += 1
            p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=6, after=2)
            p.add_run().add_picture(str(FIGS / name), width=Inches(6.3))
            pc = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=12)
            r = pc.add_run(caption)
            set_font(r, 9.5, color=MUTED)
            continue

        # ---- 表 ----
        m = re.match(r"【表：(方向|阶段|动力学)】", line.strip())
        if m:
            header, rows, widths = TABLES[m.group(1)]
            n_tab += 1
            add_table(doc, header, rows, widths)
            para(doc, after=10)
            continue

        # ---- 结论 / 边界 / 正文 ----
        m = re.match(r"(结论|边界|证据)：\s*(.*)", line)
        if m:
            label, rest = m.group(1), m.group(2)
            p = para(doc, before=2, after=4)
            r = p.add_run(f"{label}：")
            set_font(r, 11, bold=True,
                     color=RED if label == "边界" else (TEAL if label == "证据" else INK))
            runs_with_bold(p, rest, 11, color=BODY)
            continue
        if line.startswith("- "):
            p = para(doc, indent=0.25, hanging=0.16, after=3, spacing=1.3)
            r = p.add_run("· ")
            set_font(r, 11, color=MUTED)
            runs_with_bold(p, line[2:].strip(), 11, color=BODY)
            continue
        if re.match(r"^\d+\.\s", line):                       # 编号列表
            p = para(doc, indent=0.25, hanging=0.25, after=3, spacing=1.3)
            runs_with_bold(p, line.strip(), 11, color=BODY)
            continue
        p = para(doc, after=6)
        runs_with_bold(p, line.strip(), 11, color=BODY)

    # ---- 参考文献 ----
    p = para(doc, before=16, after=6)
    r = p.add_run("参考文献")
    set_font(r, 14, bold=True, color=INK)
    for n in sorted(R.REFS):
        p = para(doc, indent=0.30, hanging=0.30, after=2, spacing=1.18)
        r = p.add_run(f"[{n}] ")
        set_font(r, 9.5, bold=True, color=INK)
        r2 = p.add_run(R.REFS[n])
        set_font(r2, 9.5, color=BODY)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"wrote {out.relative_to(ROOT)}")
    print(f"  paragraphs: {len(doc.paragraphs)} | tables: {len(doc.tables)} | "
          f"inline shapes: {len(doc.inline_shapes)} | 文献 {len(R.REFS)} 条")
    print(f"  图 {n_fig} 张 / 表 {n_tab} 张 / 问题 {sum(1 for l in lines if l.startswith('### '))} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
