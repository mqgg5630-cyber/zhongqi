#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mech_doc.py - 生成《抗菌肽与阿尔茨海默症关联的机制解释与文献支持》。

面向"老师指出机制讲不清"的问题：把抗菌肽—AD 的关联、AD 与感染的关联、
抗菌活性预测、AD 组特有肽、促进 AD 发生、抑制感染、为什么 AD 更多、
正常人与 AD 谁更多这几个问题逐条回答，并给出以 AChE–Aβ 复合物分子动力学
为核心的机制解释与可检验假设。

产物：deliverable/抗菌肽与AD关联机制说明.docx
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "results" / "figures"
OUT = ROOT / "deliverable" / "抗菌肽与AD关联机制说明.docx"

INK = RGBColor(0x1A, 0x1A, 0x1A)
RED = RGBColor(0xB0, 0x3A, 0x2E)
GREY = RGBColor(0x55, 0x55, 0x55)

# ------------------------------------------------------------------ 风格工具
def base_style(doc: Document) -> None:
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    st.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    st.paragraph_format.line_spacing = 1.4
    st.paragraph_format.space_after = Pt(4)


def para(doc, text: str, *, size=11, bold=False, color=INK, indent=True,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=4, font="宋体"):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Pt(size * 2)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    return p


def heading(doc, text: str, *, size=14, color=INK, before=12, after=6):
    return para(doc, text, size=size, bold=True, color=color, indent=False,
                align=WD_ALIGN_PARAGRAPH.LEFT, before=before, after=after)


def bullet(doc, text: str, *, size=11, indent=True):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.35
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    return p


def rich(doc, parts, *, indent=True, before=0, after=4, size=11):
    """parts = [(text, bold, color|None), ...]"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Pt(size * 2)
    for text, bold, color in parts:
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        if color is not None:
            run.font.color.rgb = color
    return p


def figure(doc, name: str, caption: str, width_cm: float = 15.5) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.add_run().add_picture(str(FIGS / name), width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(10)
    run = cap.add_run(caption)
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def table(doc, header, rows, widths=None, size=9.5):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
        run.font.size = Pt(size)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.line_spacing = 1.2
            run = p.add_run(text)
            run.font.size = Pt(size)
            run.font.name = "Times New Roman"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Cm(w)
    return t


# ------------------------------------------------------------------ 正文
QA = [
    ("① 抗菌肽与 AD 有什么关联？",
     "抗菌肽是先天性免疫的效应分子；Aβ 本身即被证实具有抗菌肽活性 —— AD 脑匀浆的抗菌活性显著高于同龄对照，"
     "且该活性可被抗 Aβ 抗体免疫清除，说明其中相当部分来自 Aβ [1]。此外，AD 脑中多种宿主抗菌肽上调："
     "β-防御素-1 [2]、CAP37 [3]、LL-37 [4,5]。本课题研究的是另一类对象 —— 由肠道微生物基因组小开放阅读框"
     "编码的微生物源抗菌肽，与上述宿主来源抗菌肽互为参照系。"),
    ("② AD 与感染有什么关联？",
     "AD 脑内检出细菌内毒素（LPS）、牙龈卟啉单胞菌、螺旋体、单纯疱疹病毒 1 型等成分，AD 血浆 LPS 水平约为对照的 3 倍，"
     "并与单核/巨噬细胞活化程度正相关 [6]；AD 患者幽门螺杆菌等慢性感染的比例也更高 [6]。更上游的一环在肠道："
     "菌群失衡与肠屏障通透性增加使内毒素与细菌成分持续进入循环 [7,8]，构成对宿主免疫系统的长期刺激。"),
    ("③ 抗菌活性为什么可以预测？",
     "从序列直接预测抗菌活性已是被反复验证的方法学路线：深度学习可从人肠道宏基因组中识别出数千条抗菌肽候选序列，"
     "并经体外实验证实多数具有活性 [9]；全球微生物组规模的机器挖掘构建了迄今最大的候选抗菌肽资源库 [10]；"
     "相关方法学已有系统综述 [11]。本课题采用注意力机制、长短期记忆网络与语言模型三类结构独立预测，"
     "只保留三者一致判为阳性的序列，以降低单一模型带来的假阳性。"),
    ("④ AD 组特有的抗菌肽与 AD 如何建立关联？",
     "关联的强度来自\"阶段特异性\"：把候选抗菌肽按 NC、SCS、SCD、MCI 与 AD 五个认知阶段比较，"
     "再引入宏蛋白组表达证据二次去重，得到健康人群特有与各阶段特有的抗菌肽清单。AD 患者菌群组成与功能改变"
     "（促炎菌富集、产丁酸菌减少、α 多样性下降）已有较一致的证据 [7,8,12,13]，为该清单提供生物学合理性；"
     "清单本身则用于后续的机制关联分析与抑菌实验验证，形成\"预测—表达—功能\"的证据链。"),
    ("⑤ 抗菌肽如何\"促进 AD 发生\"？",
     "两条可分的路径。其一是聚集层面：乙酰胆碱酯酶（AChE）的外周阴离子位点（PAS）是 Aβ 聚集的成核中心 [14]，"
     "分子动力学模拟显示 Aβ 结合 PAS 后复合物在 1 μs 内保持稳定，并额外与 AChE 表面多处接触 [15]；"
     "抗菌肽可与 Aβ 共组装、改变成核与纤维生长路径，产生更具毒性的寡聚体或纤维形态。"
     "其二是炎症层面：AD 患者脑内的炎症状态并非 Aβ 单独引起，而是小胶质细胞通过模式识别受体识别"
     "LPS 与 Aβ（两者均为 TLR4/CD14 激动剂）后释放促炎因子的结果 [6]；抗菌肽 LL-37 可经 CLIC1 引起"
     "小胶质细胞过度活化、神经炎症与兴奋性毒性，在动物模型中诱导 Aβ 升高、神经纤维缠结与认知损害 [4,5]。"),
    ("⑥ 抗菌肽如何\"抑制感染\"？",
     "这是抗菌肽的生理功能：Aβ40/Aβ42 对 8 种临床相关微生物（革兰阳性、革兰阴性菌与白色念珠菌）具有与"
     "典型人抗菌肽 LL-37 相当、部分更强的抗菌活性，且反向与打乱序列的对照肽无活性，说明作用具序列特异性 [1]；"
     "在表达人 Aβ 的小鼠与线虫模型中，Aβ 表达可提高对细菌与真菌感染的抵抗力，且寡聚化是抗菌活性所必需 [16]。"
     "寡聚化同时使肽段更耐受细菌蛋白酶降解 [1] —— 这解释了为什么\"聚集\"既是功能也是代价。"),
    ("⑦ 为什么 AD 患者体内更多？",
     "因为在慢性感染的条件下，抗菌肽与 Aβ 处于一个正反馈环中：菌群失衡与屏障受损使内毒素与病原体持续刺激宿主 "
     "[7,8] → 经 TLR4/NF-κB 通路升高促炎因子，而促炎因子进一步上调 Aβ 与抗菌肽的表达 [6] → Aβ 与抗菌肽聚集、"
     "成核并激活小胶质细胞 [14,15] → 产生更多炎症介质与更多 Aβ/抗菌肽，循环自我加强。同时，AD 患者肠道内促炎菌"
     "（如 Escherichia/Shigella、Proteobacteria）富集并与 IL-1β、NLRP3 水平正相关 [12,13]，为这个环提供了持续的上游驱动。"
     "这正是\"抗菌保护假说\"的现代表述：AD 的病理改变部分源于一项有益的先天免疫反应在长期失衡后被放大 [1,16,17]。"),
    ("⑧ 正常人与 AD 患者，谁的抗菌肽更多？",
     "目前证据的方向是** AD 侧更高 **，但需要区分三个层次：(i) 来源层次 —— 已有证据主要来自宿主来源抗菌肽"
     "（β-防御素-1、CAP37、LL-37 在 AD 脑内上调 [2,3,4]）与总抗菌活性（AD 脑匀浆 > 对照 [1]），"
     "微生物源抗菌肽尚无一致结论；(ii) 部位层次 —— 局部肠腔浓度与系统循环浓度可能方向不同；"
     "(iii) 阶段层次 —— 菌群差异在 MCI 与 AD 之间并不一致 [12,13]，提示须按认知阶段比较。"
     "本课题给出的是按阶段划分的微生物源抗菌肽差异，预期方向为 AD 侧升高（依据：菌群失衡与炎症驱动），"
     "最终以本研究数据为准，不作先验断言。"),
]

HYPO = [
    ("H1 竞争 PAS",
     "候选抗菌肽与 AChE 的 PAS 结合，减少 AChE 诱导的 Aβ 成核与纤维生成。",
     "分子对接 + MD：比较候选肽存在/不存在时 Aβ 与 PAS 的结合自由能；酶活实验测 AChE 活性变化。"),
    ("H2 结合 Aβ",
     "候选抗菌肽直接与 Aβ 单体或寡聚体结合，改变聚集路径与纤维形态。",
     "共孵育 + ThT 荧光动力学、电镜/原子力显微镜观察纤维形态；MD 给出结合位点与界面残基。"),
    ("H3 膜水平作用",
     "候选抗菌肽改变膜相互作用，进而影响小胶质细胞的识别与炎症信号。",
     "脂膜模型 MD + 细胞水平炎症因子检测（必要时）；先以计算给出优先序，再择一二验证。"),
]

EVIDENCE = [
    ("Aβ 具有抗菌肽活性，AD 脑匀浆抗菌活性高于对照", "强（体外 + 人脑组织 + 抗体清除对照）", "[1]"),
    ("Aβ 表达提高对感染的抵抗力；寡聚化为活性所需", "强（小鼠、线虫、细胞模型）", "[16]"),
    ("AD 脑内 β-防御素-1 / CAP37 / LL-37 上调", "中等—强（尸检脑组织，样本量有限）", "[2,3,4]"),
    ("AD 脑与循环中存在细菌成分与内毒素，且与炎症相关", "中等—强（多实验室重复，横断面为主）", "[6]"),
    ("AChE 经 PAS 促进 Aβ 聚集；PAS 为成核中心", "强（体外动力学 + 位点阻断实验）", "[14]"),
    ("Aβ—AChE 复合物在 1 μs MD 中稳定，停留区段 344–361", "中等（单一模拟体系，需独立重复）", "[15]"),
    ("LL-37 经 CLIC1 促进小胶质活化与 AD 样病理", "中等—强（小鼠与猴模型）", "[4,5]"),
    ("AD 患者菌群失衡（促炎菌↑、产丁酸菌↓、多样性↓）", "中等（研究间异质性大，受地域与药物影响）", "[7,8,12,13]"),
    ("微生物源抗菌肽在 AD 患者中增多", "待验证（本课题要回答的问题）", "本研究"),
    ("候选抗菌肽经 AChE–Aβ 界面对成核的影响", "待验证（H1—H3）", "本研究"),
]

REFS = [
    "Soscia SJ, Kirby JE, Washicosky KJ, et al. The Alzheimer's disease-associated amyloid β-protein is an antimicrobial peptide. PLoS ONE, 2010, 5(3): e9505.",
    "Williams WM, Torres S, Siedlak SL, et al. Antimicrobial peptide β-defensin-1 expression is upregulated in Alzheimer's brain. J Neuroinflammation, 2013, 10: 127.",
    "Brock DG, Harwardt B, Gasperi R, et al. The antimicrobial protein CAP37 is upregulated in pyramidal neurons during Alzheimer's disease. Histochem Cell Biol, 2015, 144(5): 447-459.",
    "Lee M, Shi X, Barron AE, McGeer E, McGeer PL. Human antimicrobial peptide LL-37 induces glial-mediated neuroinflammation. Biochem Pharmacol, 2015, 94(2): 130-141.",
    "Chen X, Deng S, Wang M, et al. Human antimicrobial peptide LL-37 contributes to Alzheimer's disease progression. Mol Psychiatry, 2022, 27(11): 4790-4799.",
    "Zhan X, Stamova B, Sharp FR. Lipopolysaccharide associates with amyloid plaques, neurons and oligodendrocytes in Alzheimer's disease brain: a review. Front Aging Neurosci, 2018, 10: 42.",
    "Kowalski K, Mulak A. Brain-gut-microbiota axis in Alzheimer's disease. J Neurogastroenterol Motil, 2019, 25(1): 48-60.",
    "Liu S, Gao J, Zhu M, Liu K, Zhang HL. Gut microbiome and dysbiosis in Alzheimer's disease: a review. J Alzheimers Dis, 2020, 73(4): 1295-1311.",
    "Ma Y, Guo Z, Xia B, et al. Identification of antimicrobial peptides from the human gut microbiome using deep learning. Nat Biotechnol, 2022, 40(6): 921-931.",
    "Santos-Júnior CD, Torres MDT, Duan Y, et al. Discovery of antimicrobial peptides in the global microbiome with machine learning. Cell, 2024, 187(14): 3761-3778.",
    "Wan F, Wong F, Collins JJ, de la Fuente-Nunez C. Machine learning for antimicrobial peptide identification and design. Nat Rev Bioeng, 2024, 2(5): 392-407.",
    "Vogt NM, Kerby RL, Dill-McFarland KA, et al. Gut microbiome alterations in Alzheimer's disease. Sci Rep, 2017, 7: 13537.",
    "Cattaneo A, Cattane N, Galluzzi S, et al. Association of brain amyloidosis with pro-inflammatory gut bacterial taxa and peripheral inflammation markers in cognitively impaired elderly. Neurobiol Aging, 2017, 49: 60-68.",
    "Inestrosa NC, Alvarez A, Pérez CA, et al. Acetylcholinesterase accelerates assembly of amyloid-β-peptides into Alzheimer's fibrils: possible role of the peripheral site of the enzyme. Neuron, 1996, 16(4): 881-891.",
    "Atanasova M, Dimitrov I, Ivanov S. Molecular dynamics simulations of acetylcholinesterase – beta-amyloid peptide complex. Cybernetics and Information Technologies, 2020, 20(6): 140-154.",
    "Kumar DK, Choi SH, Washicosky KJ, et al. Amyloid-β peptide protects against microbial infection in mouse and worm models of Alzheimer's disease. Sci Transl Med, 2016, 8(340): 340ra72.",
    "Moir RD, Lathe R, Tanzi RE. The antimicrobial protection hypothesis of Alzheimer's disease. Alzheimers Dement, 2018, 14(12): 1602-1614.",
]


def build() -> Document:
    doc = Document()
    base_style(doc)
    for s in doc.sections:
        s.top_margin = Cm(2.4)
        s.bottom_margin = Cm(2.4)
        s.left_margin = Cm(2.6)
        s.right_margin = Cm(2.6)

    # 标题
    para(doc, "抗菌肽与阿尔茨海默症关联的机制解释与文献支持", size=17, bold=True,
         indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=2, font="黑体")
    para(doc, "中期检查补充材料", size=11, color=GREY, indent=False,
         align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    para(doc, "研究生：文绍华　　指导教师：申亮　　培养单位：生命科学学院　　"
              "2026 年 9 月", size=10, color=GREY, indent=False,
         align=WD_ALIGN_PARAGRAPH.CENTER, after=10)

    # 一、结论
    heading(doc, "一、总体结论（一句话讲清关联）")
    rich(doc, [
        ("AD 患者的肠道菌群失衡与肠屏障功能下降，使病原体及其产物（如内毒素）长期刺激宿主；"
         "抗菌肽与 β-淀粉样肽（Aβ）同属先天免疫效应分子，在此条件下被持续诱导而增多。"
         "抗菌肽一方面直接抑制微生物（抑制感染），另一方面可与 Aβ 的聚集过程及神经炎症相互促进，"
         "形成", False, None),
        ("“感染—炎症—抗菌肽/Aβ 聚集—AD 病理”的正反馈环", True, RED),
        ("——这解释了为什么 AD 患者体内的抗菌肽相关活性更高，也解释了同一分子为何既“有益”又“有害”。"
         "在分子层面，乙酰胆碱酯酶（AChE）—Aβ 复合物的分子动力学研究给出了这一环的具体落点："
         "Aβ 经 AChE 的外周阴离子位点（PAS）成核，主要停留于 344–361 区段 [15]。", False, None),
    ])
    figure(doc, "figM1_关联逻辑链.png",
           "图 1　抗菌肽与 AD 关联的七环逻辑链及其证据强度（蓝：已有实验/临床证据；"
           "绿：计算方法可给出候选与优先序；橙：本研究要回答或需验证的部分）")

    # 二、逐问回答
    heading(doc, "二、逐条回答老师提出的问题")
    for q, a in QA:
        para(doc, q, size=11.5, bold=True, indent=False, before=6, after=2)
        body = a.replace("** ", "").replace(" **", "")
        if "AD 侧更高" in body:
            head, tail = body.split("：", 1)
            rich(doc, [(head + "：", False, None), ("AD 侧更高", True, RED), (tail, False, None)])
        else:
            para(doc, body)

    # 三、机制
    heading(doc, "三、机制层：AChE–Aβ 复合物与候选抗菌肽的介入位点")
    para(doc, "本课题的机制关联分析以 Atanasova 等对 AChE–β-淀粉样肽复合物的分子动力学模拟为参照体系 [15]，"
              "并与 AChE 经 PAS 促进 Aβ 聚集的经典实验结论相互衔接 [14]。该体系的关键结论有三点：")
    bullet(doc, "Aβ 被对接至 AChE 的 PAS 后，复合物在 1 μs（1000 ns）模拟中保持稳定 [15]；")
    bullet(doc, "除 PAS 之外，Aβ 还与 AChE 表面形成多处接触，界面并非单一位点 [15]；")
    bullet(doc, "Aβ 在 AChE 表面的主要停留区为 344–361 区段。该区段紧邻 PAS，但距离足以使其不受"
                "双位点抑制剂的空间位阻影响 [15]。")
    para(doc, "把这三点与 AChE 促进 Aβ 聚集的机制放在一起，逻辑链即可闭合：AChE 的 PAS 提供成核界面，"
              "使 Aβ 由 α-螺旋向 β-折叠/β-发夹构象转变，从而降低纤维生成的能垒 [14]；"
              "而 344–361 区段构成 PAS 之外的第二个接触带。由于该接触带不被双位点抑制剂阻断，"
              "它同时意味着：能够结合 PAS 外围或 344–361 区段的分子，可以在不占据催化活性位点的前提下影响成核过程。"
              "我们的候选抗菌肽正是这样的分子 —— 它们本身具有两亲性阳离子特征，与上述界面的静电与疏水匹配度"
              "可以用分子对接与分子动力学定量评估。")
    para(doc, "因此，机制部分不直接断言“抗菌肽促进 AD”，而是提出三个可检验的介入假设，"
              "以计算给出优先序、以实验给出证据（见第四节）：若候选肽能降低 AChE 诱导的成核速率（H1），"
              "或改变 Aβ 的聚集路径与纤维形态（H2），则“抗菌肽与 AD 病理相互促进”的说法就有了分子层面的支撑；"
              "若两者皆不成立，则把结论收缩到炎症通路与膜水平作用（H3）。这样的表述既不夸大因果，也回答了"
              "“关联到底靠什么机制落地”。")
    figure(doc, "figM2_AChE_Aβ_机制.png",
           "图 2　AChE–Aβ 复合物的分子动力学要点与候选抗菌肽的三个可检验介入假设")

    # 四、假设与验证
    heading(doc, "四、三个可检验假设与验证路径")
    table(doc, ["假设", "内容", "验证方式"], HYPO, widths=[2.6, 7.0, 6.4])

    # 五、证据强度
    heading(doc, "五、证据强度分级（避免过度表述）")
    para(doc, "为使汇报口径经得起追问，下表把每一环的证据按强度分级；“待验证”一栏与本课题的研究内容直接对应。")
    table(doc, ["结论要点", "证据强度", "来源"], EVIDENCE, widths=[7.6, 6.0, 2.4])

    # 六、口径建议
    heading(doc, "六、汇报口径建议")
    bullet(doc, "讲关联时先说“同属先天免疫效应分子”，再讲“双刃剑”，最后落到 AChE–PAS 成核这一具体机制；"
                "不要一上来就下“抗菌肽导致 AD”的因果结论。")
    bullet(doc, "涉及数量差异时区分三个层次：宿主来源 vs 微生物来源、局部（肠腔）vs 系统（循环）、"
                "总体活性 vs 具体肽；本课题回答的是“微生物来源、按认知阶段划分”的差异。")
    bullet(doc, "把“AD 组更多”表述为有文献支持的预期方向（宿主抗菌肽与总活性已见升高 [1-4]），"
                "微生物源抗菌肽的结论以本项目数据为准。")
    bullet(doc, "机制部分统一表述为“线索发现”与“假设提出”，用 H1—H3 加验证路径说明下一步做什么。")

    # 参考文献
    heading(doc, "参考文献")
    for i, ref in enumerate(REFS, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.25
        run = p.add_run(f"[{i}] {ref}")
        run.font.size = Pt(9.5)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    return doc


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    from docx import Document as D
    saved = D(str(OUT))
    chars = sum(len(p.text) for p in saved.paragraphs)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  paragraphs: {len(saved.paragraphs)} | tables: {len(saved.tables)} | "
          f"inline shapes: {len(saved.inline_shapes)} | chars: {chars}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
