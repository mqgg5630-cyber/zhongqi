#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_mech.py - 机制补充页，追加到由 make_ppt_nature 版式生成的 PPT 后面。

六页：
    M1 抗菌肽与 AD 的关系：七环逻辑链（图 figM1）
    M2 为什么 AD 组更多：炎症—Aβ—抗菌肽正反馈
    M3 分子机制（一）：AChE–Aβ 复合物的分子动力学要点（图 figM2）
    M4 分子机制（二）：抗菌肽与 Aβ 的交叉成核与模拟证据（图 figM3）
    M5 八个问题逐一作答 + 证据强度
    M6 文献支撑一览（代表性文献与其结论）

中间版用 which="mid" 取其中四页（M1、M3、M5、M6）。
文字口径与 `deliverable/抗菌肽与AD关联机制说明.docx` 一致，文献编号见 code/mech_refs.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_ppt_nature as N          # noqa: E402
import mech_refs as R                # noqa: E402


def _m1(prs, idx, total):
    N.figure_slide(prs, idx, total,
        headline="抗菌肽与 AD 的关联可以拆成七环，每环的证据强度不同",
        figure="figM1_关联逻辑链.png", layout="full",
        reading="① AD 与感染相关、② 感染与炎症驱动抗菌肽与 Aβ 生成、③ Aβ 本身即抗菌肽；"
                "④ 抗菌活性可计算预测、⑤ AD 组特异抗菌肽随阶段变化、⑥ 双刃剑效应；"
                "⑦ 为什么 AD 更多与分子机制落点，是本课题要回答的部分。",
        caption="抗菌肽与 AD 关联的七环逻辑链",
        note="这页把抗菌肽与 AD 的关联拆成七环，并标出每一环的证据强度：蓝色是已有实验或临床证据，"
             "绿色是计算方法能给出候选与优先序的部分，橙色是本课题要回答或需要验证的部分。"
             "老师问任何一环，都能说清这一环目前的证据到什么程度。")


def _m2(prs, idx, total):
    N.discussion_slide(prs, idx, total,
        headline="为什么 AD 组更多：炎症—Aβ—抗菌肽构成正反馈",
        pairs=[
            ("上游驱动：菌群失衡与肠屏障通透性升高",
             "AD 与前驱阶段的肠道菌群失衡、肠屏障标志物升高，使内毒素与病原体长期入血 [11][17][46]。"),
            ("放大环节：促炎因子上调 Aβ 与抗菌肽的表达",
             "LPS 经 TLR4/NF-κB 升高促炎因子，促炎因子又上调 Aβ 生成 [11][46]；"
             "TNF-α 与 Aβ 可直接诱导 CAP37 表达 [9]。"),
            ("闭环：聚集后的 Aβ 再激活小胶质细胞",
             "Aβ 与抗菌肽聚集、成核并激活小胶质细胞，释放更多炎症介质；"
             "LL-37 经 CLIC1 引起小胶质过度活化，小鼠与猴模型出现 Aβ 升高与脑萎缩 [6][7]。"),
            ("临床对应：炎症指标与抗菌肽水平同步升高",
             "血清 LL-37 高者两年内 MMSE 下降 ≥3 分的比值比为 2.11，NfL 与 pTau181 上升更快 [42]；"
             "前驱阶段的 CRP 与 LPS 已经升高 [17]。"),
        ],
        note="为什么 AD 组更多？因为存在一个正反馈：菌群失衡与肠屏障通透性增加使内毒素长期刺激宿主，"
             "经 TLR4 与 NF-κB 通路升高促炎因子，促炎因子又上调 Aβ 与抗菌肽的生成；"
             "聚集后的 Aβ 激活小胶质细胞产生更多炎症介质，循环自我加强。这也是抗菌保护假说的现代表述。")


def _m3(prs, idx, total):
    N.figure_slide(prs, idx, total,
        headline="分子机制（一）：AChE–Aβ 复合物的动力学要点",
        figure="figM2_AChE_Aβ_机制.png", layout="wide",
        reading="PAS 是 Aβ 聚集的成核中心：1 μs 模拟中复合物稳定，Aβ 主要停留于 344—361 区段，"
                "不受双位点抑制剂位阻 [31]；丙锭阻断 PAS 后聚集被抑制 [33]。",
        note="机制落点参照 AChE–Aβ 复合物的分子动力学研究：Aβ 对接进 PAS 后，复合物在 1 微秒模拟中保持稳定，"
             "主要停留区段是 344—361，该区段紧邻 PAS 但不受双位点抑制剂的位阻。"
             "同一界面的其他实验证据包括：丙锭可阻断 AChE 诱导的聚集而催化位点抑制剂无效、"
             "PAS 负电荷触发 β-发夹构象、丁酰胆碱酯酶反向延缓纤维形成。"
             "由此提出三个假设，并用对接与动力学给出优先序。")


def _m4(prs, idx, total):
    N.figure_slide(prs, idx, total,
        headline="分子机制（二）：抗菌肽与 Aβ 的交叉成核，方向由界面决定",
        figure="figM3_交叉成核机制.png", layout="wide",
        reading="抗菌肽与 Aβ 结构兼容，可交叉成核，方向由界面与浓度决定 [36][37]；"
                "LL-37 以疏水作用封堵纤维延伸面 [38]，五肽库筛选可破坏 D23—K28 盐桥 [41]。",
        note="这页说明分子机制为什么能解释得通：抗菌肽与 Aβ 结构兼容，可以交叉成核，方向取决于界面与浓度。"
             "支撑这一机制的模拟证据已经比较完整：AChE–Aβ 的 1 微秒模拟、AChE 疏水基序掺入纤维、"
             "LL-37 与淀粉样肽的离散动力学、抗菌肽类分子与 Aβ 的对接加动力学并用实验验证、"
             "以及五肽库筛选破坏 D23–K28 盐桥。这些结果说明用对接与动力学研究候选肽与 Aβ/AChE 的界面是可行的。")


def _m5(prs, idx, total):
    questions = [
        ("① 抗菌肽与 AD 的关联", "Aβ 本身即抗菌肽，宿主抗菌肽在 AD 中上调", "强",
         "[1][2][8][9]"),
        ("② AD 与感染的关联", "AD 脑细菌读段与内毒素升高，多类病原体检出", "中—强",
         "[11][12][13][14]"),
        ("③ 抗菌活性可预测", "宏基因组 + 深度学习挖掘已有完整先例", "强",
         "[21][22][24]"),
        ("④ AD 组特有肽", "菌群随认知阶段梯度变化，阶段特有肽有依据", "中",
         "[26][28][30]"),
        ("⑤ 促进还是抑制", "两者同时成立：低浓度抗菌，长期过量致病", "中—强",
         "[1][3][6][20]"),
        ("⑥ 抑制感染证据", "小鼠抗感染更强；纤维网捕获病原体", "强",
         "[1][3][4]"),
        ("⑦ 为什么 AD 更多", "LPS–TLR4/NF-κB 上调 Aβ 与抗菌肽，形成正反馈", "中—强",
         "[9][11][46]"),
        ("⑧ 谁更多（对照）", "总体 AD 更高，乳铁蛋白等反而下降", "中",
         "[42][43][44]"),
    ]
    rows = [(q, a, s, r) for q, a, s, r in questions]
    N.table_slide(prs, idx, total,
        headline="八个问题逐一作答：结论方向与证据强度",
        header=["问题", "本课题的回答要点", "证据强度", "代表文献"],
        widths=(3.05, 5.60, 1.55, 1.73),
        rows=rows,
        note="这张表把老师提出的八个问题逐条列出，并给出答案要点与证据强度。"
             "需要说明的是：关联类结论的证据强度较高，方向类结论（谁更多、促进还是抑制）"
             "存在例外与条件依赖，因此标注为中；微生物源抗菌肽在 AD 中的变化属于待验证部分，"
             "正是本课题要补的一环。")


def _m6(prs, idx, total):
    rows = [
        ("Soscia 等 2010", "Aβ 对 8 种微生物有活性，AD 脑匀浆活性更高", "PLoS ONE [1]"),
        ("Kumar 等 2016", "表达 Aβ 的小鼠抗感染更强，寡聚化为活性必需", "Sci Transl Med [3]"),
        ("Eimer 等 2018", "Aβ 结合病毒糖蛋白并成纤维网捕获病毒", "Neuron [4]"),
        ("Chen 等 2022", "LL-37 经 CLIC1 引起小胶质活化与 AD 样病理", "Mol Psychiatry [6]"),
        ("Zhan 等 2018", "AD 脑与血中 LPS 升高，LPS 与斑块共定位", "Front Aging Neurosci [11]"),
        ("Emery 等 2017", "AD 脑细菌读段为对照的 5—10 倍", "Front Aging Neurosci [12]"),
        ("Ma 等 2022", "宏基因组 + 深度学习挖掘抗菌肽并有体外验证", "Nat Biotechnol [21]"),
        ("Atanasova 等 2020", "AChE–Aβ 复合物 1 μs 稳定，停留区段 344—361",
         "Cybernetics & Inf Tech [31]"),
        ("Zheng 等 2026", "交叉成核三机制与病原—淀粉样正反馈环", "Research [36]"),
        ("LB 等 2023", "血清 LL-37 高者认知下降更快（OR 2.11）", "J Alzheimers Dis [42]"),
    ]
    N.table_slide(prs, idx, total,
        headline="文献支撑一览：每一环都有可溯源的原始研究",
        header=["代表文献", "本课题引用它的哪条结论", "出处与编号"],
        widths=(2.95, 6.15, 2.83),
        row_h=0.46, rows=rows,
        note="机制说明文档《抗菌肽与AD关联机制说明》共整理 46 条文献，覆盖 AD 与感染、"
             "宿主抗菌肽在 AD 中的变化、抗菌肽预测方法、菌群分期、AChE–Aβ 与交叉成核的分子模拟，"
             "以及作为反例的乳铁蛋白下降证据。这里列出其中十条代表性文献及其结论。")


PAGES = {"m1": _m1, "m2": _m2, "m3": _m3, "m4": _m4, "m5": _m5, "m6": _m6}
MID_KEYS = ["m1", "m3", "m5", "m6"]


def append(prs, *, first_idx: int, total: int, which: str = "full") -> int:
    """在 presentation 末尾追加机制页，返回最后一页的页码。"""
    keys = list(PAGES) if which == "full" else MID_KEYS
    idx = first_idx
    for k in keys:
        PAGES[k](prs, idx, total)
        idx += 1
    return idx - 1
