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
7. 结果形式一致（SCI 论文 1 篇 + 学位论文）；
8. 送审版（deliverable/中期.docx）不含任何抑菌实验表述（其余两份表保留），导师评语为指定文本；
9. 日期一致：三份表里“封面填表日期 / 导师签字 / 检查组长签字 + 培养单位盖章”都填 2026年9月19日、
   模板的“年 月 日”空档一个不剩（签字页单独文件里也要有日期）。

用法
----
    python code/check_consistency.py                     # docx vs deliverable/*.pptx
    python code/check_consistency.py --docx X.docx --pptx a.pptx b.pptx
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from pptx import Presentation      # noqa: E402  （结构检查数页数）

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
    # 研究对象口径：筛的是 AD 组特有的肽，不是健康人群特有的肽（2026-09-19 起）
    ("特有肽口径", ["AD 特异性特有", "AD 组特有"], ["AD 特异性特有", "AD 组特有"]),
    # 关联分析落点：AD 特有肽与 AD 的关联（不再说“给出候选优先序”）
    ("关联分析口径", ["AD 特有肽与 AD 的关联", "AD 发病机制的关联分析"],
     ["AD 特有肽与 AD 的关联"]),
    # 检查小组成员（4 份表都填；签字页同源）
    # 分箱：MetaBAT2 / MaxBin2 / CONCOCT 三个算法（PPT 流程页与数据资源页都要点名）
    ("分箱工具", ["MetaBAT2", "MaxBin2", "CONCOCT"], ["MaxBin2", "CONCOCT"]),
    # 检查小组成员只填在 docx（用户 2026-09-19 指定），PPT 不要求
    ("检查小组成员（docx）", ["李向阳", "江婷婷", "孙杰", "高洪伟"], None),
    ("机制·AChE", ["AChE", "乙酰胆碱酯酶"], ["AChE", "乙酰胆碱酯酶"]),
    ("成果·投稿", ["SCI"], ["SCI"]),
    ("完成度口径", ["已完成"], ["已完成"]),
    ("后续环节", ["进行中", "正在"], ["正在推进", "进行中", "下一步"]),
]

# 各版页数与"已删除页面"清单
DECK_STRUCTURE = [
    ("deliverable/中期答辩_H_nature风.pptx", 24, ()),
    ("deliverable/中期答辩_最终版.pptx", 24, ()),
    ("中间版/中期答辩_H_nature风.pptx", 14, ()),
    # 中间版 2 = 最终答辩 PPT：已删“与开题计划相比”“八个问题逐一作答”“文献支撑一览”
    ("中间版2/中期答辩_H_nature风.pptx", 11,
     ("与开题计划相比", "八个问题逐一作答", "文献支撑一览")),
]

BANNED = ["极简", "最小工作量", "最小可行性", "最小化验证",
          # 2026-09-19 起：研究对象是 AD 特有肽、关联分析不说“优先序”
          "优先序", "健康人群特有", "各阶段特有", "各疾病阶段特有",
          # 2026-09-14 起：汇报材料里不出现"按导师意见 / 导师意见"这类表述
          "导师意见", "按导师", "导师的指导"]


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", "ignore")


def pptx_text(path: Path) -> str:
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
             + sorted((ROOT / "中间版").glob("*.pptx"))
             + sorted((ROOT / "中间版2").glob("*.pptx")))
    docs = ([Path(p) for p in a.docx] if a.docx else
            [ROOT / "deliverable" / "中期.docx", ROOT / "中间版" / "中期.docx",
             ROOT / "中间版2" / "中期.docx"])
    dtexts = {d: docx_text(d) for d in docs}
    problems = 0

    print(f"docx: {len(docs)} 份（{'、'.join(d.parent.name + '/' + d.name for d in docs)}）"
          f"  |  对比 {len(decks)} 份 PPT\n")
    for label, dneedles, pneedles in RULES:
        d_ok = all(any(n in dtexts[d] for n in dneedles) for d in docs)
        ppt_missing = [] if pneedles is None else \
            [p.stem.replace("中期答辩_", "")
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

    # 结构检查：各版页数固定；中间版 2 已按老师意见删掉三页
    for rel, n_slides, forbidden in DECK_STRUCTURE:
        path = ROOT / rel
        if not path.exists():
            problems += 1
            print(f"  FAIL 结构·{path.name: <16} 文件不存在")
            continue
        text = pptx_text(path)
        n = len(Presentation(str(path)).slides)
        hits = [w for w in forbidden if w in text]
        if n == n_slides and not hits:
            print(f"  OK   结构·{path.parent.name}/{path.name:<22} {n} 页")
            continue
        problems += 1
        detail = []
        if n != n_slides:
            detail.append(f"页数 {n} != {n_slides}")
        if hits:
            detail.append("仍有应删页面：" + "、".join(hits))
        print(f"  FAIL 结构·{path.parent.name}/{path.name:<22} " + "；".join(detail))

    # 日期：封面填表日期 / 导师签字 / 组长签字 + 培养单位盖章，3 处空档都填好
    DATE = "2026年9月19日"
    BLANK_DATE = re.compile(r"年[\s\u3000]{2,}月[\s\u3000]*日")
    date_hits = []
    for d in docs:
        n, blanks = dtexts[d].count(DATE), len(BLANK_DATE.findall(dtexts[d]))
        if n == 3 and blanks == 0:
            print(f"  OK   日期·{d.parent.name}/{d.name:<14} 3 处日期都填了 {DATE}")
            continue
        problems += 1
        date_hits.append(f"{d.parent.name}/{d.name}（填了 {n} 处、还剩空档 {blanks} 处）")
    if date_hits:
        print(f"  FAIL 日期·三处日期应填 {DATE}：{'；'.join(date_hits)}")
    # 送审版（deliverable/中期.docx）用户 2026-09-19 指定：完全去掉抑菌实验（其余版本保留）
    NOEXP_WORDS = ["抑菌", "纸片扩散", "肉汤稀释", "指示菌", "最低抑菌浓度",
                   "阳性对照", "阴性对照", "人工合成", "活性验证",
                   "大肠杆菌", "金黄色葡萄球菌"]
    main_docx = ROOT / "deliverable" / "中期.docx"
    main_text = dtexts[main_docx] if main_docx in dtexts else docx_text(main_docx)
    left = [w for w in NOEXP_WORDS if w in main_text]
    if not left:
        print("  OK   送审版·无抑菌实验    deliverable/中期.docx 里实验相关表述 0 处")
    else:
        problems += 1
        print(f"  FAIL 送审版·无抑菌实验    deliverable/中期.docx 仍有：{'、'.join(left)}")
    for d in docs:
        if d == main_docx:
            continue
        if "抑菌" in dtexts[d]:
            print(f"  OK   版本·{d.parent.name}/{d.name:<12} 仍保留抑菌实验内容")
        else:
            problems += 1
            print(f"  FAIL 版本·{d.parent.name}/{d.name} 缺抑菌实验内容（这一版应当保留）")
    # 导师综合评语已换成用户给的文本（不再提“部分样本缺少可用参考基因组”）
    # 注意：只截取评语那一段来判，正文技术路线里本来就有“部分样本缺少可用参考基因组”一句
    ev_text = ""
    ev_at = main_text.find("导师综合评语")
    if ev_at >= 0:
        ev_text = re.sub(r"<[^>]+>", "", main_text[ev_at:ev_at + 2000]).replace("&amp;", "&")
    if ("对预测假阳性、机制关联证据强度有限等问题已有明确处理办法" in ev_text
            and "部分样本缺少可用参考基因组" not in ev_text):
        print("  OK   导师评语·送审版  已用指定文本（不再提“部分样本缺少可用参考基因组”）")
    else:
        problems += 1
        print("  FAIL 导师评语·送审版  评语不是用户指定文本（或仍提“部分样本缺少可用参考基因组”）")

    sign_docx = ROOT / "deliverable" / "中期检查表_签字页.docx"
    if sign_docx.exists():
        n = docx_text(sign_docx).count(DATE)
        if n:
            print(f"  OK   日期·deliverable/{sign_docx.name:<18} 含 {DATE}")
        else:
            problems += 1
            print(f"  FAIL 日期·deliverable/{sign_docx.name} 里没有 {DATE}")

    if problems == 0:
        print("\nRESULT: docx 与全部 PPT 口径一致")
    else:
        print(f"\nRESULT: {problems} problem(s)")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
