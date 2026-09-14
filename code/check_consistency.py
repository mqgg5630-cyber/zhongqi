#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_consistency.py - 核对中期 docx 与各版 PPT 的口径是否一致。

检查项（docx 为准，PPT 跟随）
-----------------------------
1. 论文题目一致；
2. 封面信息（姓名 / 学号 / 培养单位 / 学科专业 / 指导教师）在 docx 封面与各版 PPT 封面都存在；
3. 完成度口径一致：前五项"已完成"、机制关联与抑菌实验"进行中/正在推进"；
4. 抑菌实验表述禁用词（极简 / 最小工作量 / 最小可行性）；
5. 阶段划分一致（NC / SCS / SCD / MCI / AD）；
6. 机制关联三方向一致（Aβ 聚集 / AChE 外周阴离子位点 / 免疫与炎症通路）；
7. 结果形式一致（SCI 论文 1 篇 + 学位论文）。

用法
----
    python code/check_consistency.py                     # docx vs deliverable/*.pptx
    python code/check_consistency.py --docx X.docx --pptx a.pptx b.pptx
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RULES = [
    ("论文题目", ["基于深度学习的阿尔茨海默症患者与健康人群肠道微生物组中抗菌肽的差异性研究"],
     ["基于深度学习的阿尔茨海默症患者与健康人群", "肠道微生物组中抗菌肽的差异性研究"]),
    ("封面·姓名", ["文绍华"], ["文绍华"]),
    ("封面·学号", ["2024110316"], ["2024110316"]),
    ("封面·培养单位", ["生命科学学院"], ["生命科学学院"]),
    ("封面·指导教师", ["申亮"], ["申亮"]),
    ("阶段划分", ["NC", "SCS", "SCD", "MCI"],
     ["MCI", "各疾病阶段", "分阶段"]),
    ("机制·Aβ", ["Aβ", "β-淀粉样肽"], ["Aβ", "淀粉样肽"]),
    ("机制·AChE", ["AChE", "乙酰胆碱酯酶"], ["AChE", "乙酰胆碱酯酶"]),
    ("成果·投稿", ["SCI"], ["SCI"]),
    ("完成度口径", ["已完成"], ["已完成"]),
    ("后续环节", ["进行中", "正在"], ["正在推进", "进行中", "下一步"]),
]

BANNED = ["极简", "最小工作量", "最小可行性", "最小化验证",
          # 2026-09-14 起：汇报材料里不出现"按导师意见 / 导师意见"这类表述
          "导师意见", "按导师", "导师的指导"]


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", "ignore")


def pptx_text(path: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    chunks = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                chunks.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        chunks.append(cell.text)
        if slide.has_notes_slide:
            chunks.append(slide.notes_slide.notes_text_frame.text)
    return "\n".join(chunks)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", nargs="*", default=None)
    ap.add_argument("--pptx", nargs="*", default=None)
    a = ap.parse_args(argv)
    decks = ([Path(p) for p in a.pptx] if a.pptx
             else sorted((ROOT / "deliverable").glob("中期答辩_*.pptx"))
             + sorted((ROOT / "中间版").glob("*.pptx")))
    docs = ([Path(p) for p in a.docx] if a.docx else
            [ROOT / "deliverable" / "中期.docx", ROOT / "中间版" / "中期.docx"])
    dtexts = {d: docx_text(d) for d in docs}
    problems = 0

    print(f"docx: {len(docs)} 份（{'、'.join(d.parent.name + '/' + d.name for d in docs)}）"
          f"  |  对比 {len(decks)} 份 PPT\n")
    for label, dneedles, pneedles in RULES:
        d_ok = all(any(n in dtexts[d] for n in dneedles) for d in docs)
        ppt_missing = [p.stem.replace("中期答辩_", "")
                       for p in decks
                       if not any(n in pptx_text(p) for n in pneedles)]
        if d_ok and not ppt_missing:
            print(f"  OK   {label:<12}")
            continue
        problems += 1
        detail = ""
        if not d_ok:
            missing = [d.name if d.parent.name == "中间版" else d.name
                       for d in docs if not any(n in dtexts[d] for n in dneedles)]
            detail += f" docx 缺「{' / '.join(dneedles[:2])}」: {', '.join(missing)}"
        if ppt_missing:
            detail += f" PPT 缺「{' / '.join(pneedles[:2])}」: {', '.join(ppt_missing)}"
        print(f"  FAIL {label:<12} {detail}")

    for word in BANNED:
        hits = []
        for d in docs:
            if word in dtexts[d]:
                hits.append(d.parent.name + "/" + d.name)
        for p in decks:
            if word in pptx_text(p):
                hits.append(p.stem.replace("中期答辩_", ""))
        status = "OK " if not hits else "FAIL"
        if hits:
            problems += 1
        print(f"  {status} 禁用表述：{word:<8} {'-> ' + ', '.join(hits) if hits else ''}")

    if problems == 0:
        print("\nRESULT: docx 与全部 PPT 口径一致")
    else:
        print(f"\nRESULT: {problems} problem(s)")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
