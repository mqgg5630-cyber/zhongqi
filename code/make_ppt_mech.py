#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_mech.py - 机制补充页（4 页），追加到任意由 make_ppt_nature 版式生成的 PPT 后面。

用法（在别的脚本里）：
    import make_ppt_mech as M
    M.append(prs, first_idx=17, total=20)      # 接在第 16 页之后

四页内容：
    M1 抗菌肽与 AD 关联的七环逻辑链（图 figM1）
    M2 为什么 AD 更多：炎症—Aβ—抗菌肽正反馈
    M3 机制落点：AChE–Aβ 复合物与候选肽的三个假设（图 figM2）
    M4 证据强度分级与验证路径（原生表格）

文字口径与本仓库 `deliverable/抗菌肽与AD关联机制说明.docx` 一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_ppt_nature as N          # noqa: E402

MECH_NOTES = {
    "m1": "这张图把抗菌肽与 AD 的关联拆成七环，并标出每一环的证据强度：蓝色是已有实验或临床证据，"
          "绿色是计算方法能给出候选与优先序的部分，橙色是本课题要回答或需要验证的部分。"
          "这样讲的好处是：老师问任何一环，都能说清这一环目前的证据到什么程度。",
    "m2": "为什么 AD 患者体内的抗菌肽更多？因为存在一个正反馈：菌群失衡与肠屏障通透性增加使内毒素和病原体"
          "长期刺激宿主，经 TLR4 与 NF-κB 通路升高促炎因子，而促炎因子又上调 Aβ 与抗菌肽的生成；"
          "Aβ 与抗菌肽聚集后激活小胶质细胞，产生更多炎症介质，循环自我加强。"
          "这也是抗菌保护假说的现代表述：一项有益的先天免疫反应，在长期失衡后被放大成病理过程。",
    "m3": "机制落点参照 AChE–Aβ 复合物的分子动力学研究：Aβ 对接进外周阴离子位点 PAS 后，"
          "复合物在 1 微秒模拟中保持稳定，主要停留区为 344–361 区段，该区段紧邻 PAS 但不受双位点抑制剂的位阻。"
          "由此提出三个可检验假设：H1 竞争 PAS 减少成核、H2 直接结合 Aβ 改变聚集路径、H3 在膜水平影响小胶质识别。"
          "我们用对接与动力学给出优先序，再用抑菌与酶活实验验证。",
    "m4": "这张表说明每一环的证据强度，以及本课题要补的是哪一块：宿主来源抗菌肽、Aβ 的抗菌活性、"
          "AChE 经 PAS 促进聚集，这些已有较强证据；微生物源抗菌肽在 AD 患者中增多、以及候选肽经 AChE–Aβ 界面"
          "影响成核，是本课题要回答的问题。这样既讲清了关联，也没有夸大因果。",
}


def append(prs, *, first_idx: int, total: int):
    """在现有 presentation 末尾追加 4 页机制补充页。返回最后使用的页码。"""
    N.figure_slide(prs, first_idx, total,
        headline="抗菌肽与 AD 的关联可以拆成七环，每环的证据强度不同",
        figure="figM1_关联逻辑链.png", layout="full",
        reading="① AD 与感染相关、② 感染与炎症驱动抗菌肽与 Aβ 生成、③ Aβ 本身即抗菌肽；"
                "④ 抗菌活性可计算预测、⑤ AD 组特异抗菌肽随阶段变化、⑥ 双刃剑效应；"
                "⑦ 为什么 AD 更多与 AChE–Aβ 机制落点，是本课题要回答的部分。",
        caption="抗菌肽与 AD 关联的七环逻辑链",
        note=MECH_NOTES["m1"])

    N.claim_slide(prs, first_idx + 1, total,
        headline="为什么 AD 更多：炎症—Aβ—抗菌肽构成正反馈",
        support=[
            "菌群失衡与肠屏障通透性增加，使内毒素与病原体长期刺激宿主；",
            "经 TLR4/NF-κB 升高促炎因子，促炎因子又上调 Aβ 与抗菌肽的生成；",
            "Aβ 与抗菌肽聚集、成核并激活小胶质细胞，产生更多炎症介质，循环自我加强。",
        ],
        aside=["表述口径：", "抗体外证据为主；", "区分宿主来源与", "微生物来源、局部", "与系统、阶段差异。"],
        note=MECH_NOTES["m2"])

    N.figure_slide(prs, first_idx + 2, total,
        headline="机制落点：AChE–Aβ 复合物与候选肽的三个假设",
        figure="figM2_AChE_Aβ_机制.png", layout="rail",
        reading="AChE 的 PAS 是 Aβ 聚集的成核中心；分子动力学显示复合物在 1 μs 内稳定，"
                "Aβ 主要停留于 344–361 区段，且该区段不受双位点抑制剂位阻。"
                "由此提出：H1 竞争 PAS 减少成核、H2 结合 Aβ 改变聚集路径、H3 膜水平影响炎症信号；"
                "以对接与动力学给优先序，以抑菌与酶活实验验证。",
        source="图：本项目自制（results/figures/figM2）",
        note=MECH_NOTES["m3"])

    N.table_slide(prs, first_idx + 3, total,
        headline="证据到哪一步：分级与验证路径",
        header=["要点", "证据强度", "与本课题的关系"],
        widths=(4.6, 3.4, 4.0),
        rows=[
            ("Aβ 具抗菌活性，AD 脑匀浆活性更高", "强：体外 + 人脑组织", "提供抗菌肽研究的出发点"),
            ("AD 脑内宿主抗菌肽上调", "中—强：尸检组织，样本有限", "作为宿主来源的参照系"),
            ("AChE 经 PAS 促进 Aβ 聚集", "强：体外动力学 + 位点阻断", "机制关联的参照体系"),
            ("AD 患者菌群失衡与炎症升高", "中：研究异质性大", "阶段特异性抗菌肽的合理性"),
            ("微生物源抗菌肽在 AD 增多", "待验证", "本课题要回答的问题"),
            ("候选肽经 AChE–Aβ 界面影响成核", "待验证（H1—H3）", "下一步的对接、动力学与实验"),
        ],
        note=MECH_NOTES["m4"])
    return first_idx + 3
