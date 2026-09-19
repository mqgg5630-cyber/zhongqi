#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mech_figures.py - 机制解释补充材料的两张图。

1. figM1_关联逻辑链.png     抗菌肽与 AD 关联的七环逻辑链（含证据强度标注）
2. figM2_AChE_Aβ_机制.png  乙酰胆碱酯酶—β-淀粉样肽复合物的分子动力学要点，
                           以及候选抗菌肽可能介入的三个位置（H1/H2/H3）

依据：Atanasova M, Dimitrov I, Ivanov S. Molecular Dynamics Simulations of
Acetylcholinesterase – Beta-Amyloid Peptide Complex. Cybernetics and Information
Technologies, 2020, 20(6): 140-154. doi:10.2478/cait-2020-0068
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_figures as mf          # noqa: E402

LIGHT, BLUE, TEAL, ORANGE = mf.LIGHT, mf.BLUE, mf.TEAL, mf.ORANGE
GREY, INK, RED = mf.GREY, mf.INK, mf.RED

DONE_F, DONE_E = "#e8f1fb", BLUE          # 已有较强证据
PRED_F, PRED_E = "#e8f6f1", TEAL          # 计算可预测
OPEN_F, OPEN_E = "#fdf2e3", ORANGE        # 本研究要回答


def fig_chain():
    """七环逻辑链：从 AD 与感染，到抗菌肽，到机制与双刃剑。"""
    fig, ax = mf.canvas(12.4, 5.2)
    rows = [
        (0.70, [
            "① AD 与感染相关\n病原体/内毒素在 AD 脑与循环中富集",
            "② 感染与炎症驱动\n抗菌肽与 Aβ 生成增加",
            "③ Aβ 本身是抗菌肽\n脑匀浆抗菌活性 AD > 对照",
        ], DONE_F, DONE_E),
        (0.40, [
            "④ 抗菌活性可计算预测\n深度学习从宏基因组挖掘候选肽",
            "⑤ AD 组特异抗菌肽\n随病程阶段变化",
            "⑥ 致病方向：促进 Aβ\n成核聚集与神经炎症",
        ], PRED_F, PRED_E),
        (0.10, [
            "⑦ 为什么 AD 更多\n炎症—Aβ—抗菌肽正反馈环",
            "机制落点：AChE–Aβ 复合物\nPAS 成核 + 344–361 区段",
            "本研究要回答的问题\n微生物源抗菌肽是否同样如此",
        ], OPEN_F, OPEN_E),
    ]
    x0, w, gap, h = 0.015, 0.315, 0.026, 0.235
    for y, texts, fc, ec in rows:
        for i, t in enumerate(texts):
            x = x0 + i * (w + gap)
            mf.box(ax, x, y, w, h, t, fc=fc, ec=ec, fs=15,
                   tc=INK if fc != OPEN_F else "#7a4a12")
            if i < 2:
                mf.arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2), color=ec, lw=1.8)
    mf.arrow(ax, (0.83, 0.70), (0.83, 0.635), color=GREY, lw=1.6, ls="--")
    mf.arrow(ax, (0.83, 0.40), (0.83, 0.335), color=GREY, lw=1.6, ls="--")

    handles = [
        Line2D([], [], marker="s", ls="", ms=13, mfc=DONE_F, mec=DONE_E,
               label="已有实验/临床证据支持"),
        Line2D([], [], marker="s", ls="", ms=13, mfc=PRED_F, mec=PRED_E,
               label="计算方法可给出候选与优先序"),
        Line2D([], [], marker="s", ls="", ms=13, mfc=OPEN_F, mec=OPEN_E,
               label="本研究拟回答 / 需要验证"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
              bbox_to_anchor=(0.5, 1.06), fontsize=15)
    mf.save(fig, "figM1_关联逻辑链.png")


def fig_md_mechanism():
    """AChE–Aβ 复合物的动力学要点 + 同一界面的实验证据 + 三个假设。

    满幅短图（12.0 × 4.35 in）：投影到幻灯片后占满正文宽度，图下再排说明文字。
    """
    fig, ax = mf.canvas_full(12.0, 4.35)

    # 第 1 列：分子动力学结论
    ax.text(0.155, 0.930, "① 分子动力学模拟（1 μs）", ha="center", fontsize=16, color=INK)
    mf.box(ax, 0.010, 0.150, 0.290, 0.740,
           "Aβ 对接进 PAS，\n复合物在 1 μs 模拟中稳定\n\n"
           "除 PAS 外另有多处接触\n\n"
           "Aβ 主要停留于 AChE 344—361：\n紧邻 PAS，且不受\n双位点抑制剂的空间位阻",
           fc=LIGHT, ec=BLUE, fs=15)

    # 第 2 列：同一界面的实验证据
    ax.text(0.505, 0.930, "② 同一界面的实验证据", ha="center", fontsize=16, color=INK)
    mf.box(ax, 0.360, 0.150, 0.290, 0.740,
           "PAS 抑制剂丙锭可阻断\nAChE 诱导的聚集，\n催化位点抑制剂无效\n\n"
           "PAS 的高负电荷密度使 Aβ\n由 α-螺旋转向 β-发夹\n\n"
           "丁酰胆碱酯酶结合可溶态 Aβ，\n反而延缓纤维形成",
           fc=PRED_F, ec=TEAL, fs=15)

    # 第 3 列：三个可检验假设
    ax.text(0.845, 0.930, "③ 三个可检验假设（致病方向）", ha="center", fontsize=16, color=INK)
    ys = [0.700, 0.480, 0.260]
    hyps = [("H1 结合 PAS 与 344—361", "促进成核与聚集"),
            ("H2 结合 Aβ 生成区", "加速纤维化 / 更毒寡聚体"),
            ("H3 膜与小胶质水平", "放大炎症信号")]
    for y, (t, d) in zip(ys, hyps):
        mf.box(ax, 0.700, y, 0.290, 0.175, f"{t}\n{d}", fc=OPEN_F, ec=ORANGE, fs=15,
               tc="#7a4a12")

    mf.arrow(ax, (0.305, 0.55), (0.355, 0.55), color=TEAL, lw=1.8)
    mf.arrow(ax, (0.655, 0.55), (0.696, 0.55), color=ORANGE, lw=1.8)
    ax.text(0.5, 0.045, "丙锭 / 位点阻断 [33]　β-发夹构象 [34]　BChE 反例 [35]　"
                        "PAS 成核与 344—361 区段 [31]",
            ha="center", fontsize=15, color=GREY)
    mf.save(fig, "figM2_AChE_Aβ_机制.png")


def fig_cross_seeding():
    """抗菌肽与 Aβ 的交叉成核：三条机制 + 对应的模拟与实验证据。"""
    fig, ax = mf.canvas_full(12.0, 4.35)

    cols = [
        (0.010, "① 结构兼容", "β-折叠拓扑相容，互为模板：\n既可能加速聚集，\n也可能把纤维导向不同形态",
         "方向由序列、电荷\n与疏水面共同决定"),
        (0.340, "② 定向成核不对称", "一方促进而反向不成立，\n可解释文献中“有的加速、\n有的抑制”",
         "同一种肽在不同浓度\n或膜环境下方向相反"),
        (0.670, "③ 表面催化", "纤维表面降低成核能垒，\n并在界面局部富集肽，\n决定新纤维的成核位置",
         "对应 PAS 等带电\n位点的成核中心"),
    ]
    for x, t, body, foot in cols:
        ax.text(x + 0.155, 0.940, t, ha="center", fontsize=16, color=INK)
        mf.box(ax, x, 0.560, 0.300, 0.330, body, fc=PRED_F, ec=TEAL, fs=15)
        mf.box(ax, x, 0.360, 0.300, 0.170, foot, fc="#f6f7f9", ec="#9aa7b4", fs=15, tc=GREY)

    ax.text(0.5, 0.300, "支撑上述机制的模拟与实验证据", ha="center", fontsize=15.5, color=INK)
    items = [
        ("AChE–Aβ\n1 μs 稳定\n344—361", "[31]"),
        ("疏水基序\n掺入生长的\n纤维", "[32]"),
        ("LL-37 与\n淀粉样肽\n封堵延伸面", "[38][39]"),
        ("多粘菌素 B–Aβ\n对接+MD\n电泳验证", "[40]"),
        ("五肽库筛选\nMM-PBSA\n破坏盐桥", "[41]"),
    ]
    w, gap = 0.192, 0.015
    for i, (t, ref) in enumerate(items):
        x = 0.010 + i * (w + gap)
        mf.box(ax, x, 0.055, w, 0.220, t, fc=LIGHT, ec=BLUE, fs=15)
        ax.text(x + w / 2, 0.018, ref, ha="center", fontsize=15, color=GREY)
    mf.save(fig, "figM3_交叉成核机制.png")


def main() -> int:
    name = mf.load_cjk()
    mf.OUT.mkdir(parents=True, exist_ok=True)
    print(f"font: {name}")
    problems = []
    for fn in (fig_chain, fig_md_mechanism, fig_cross_seeding):
        mf.OVERFLOW.clear()
        fn()
        problems += [f"{fn.__name__}: {w}" for w in mf.OVERFLOW]
    for fname, mn, eff in mf.EFFECTIVE:
        flag = "" if eff >= 14.9 else "   <-- too small"
        print(f"  {fname:<30} {mn:5.1f} pt   on slide {eff:5.1f} pt{flag}")
    if problems:
        for w in problems:
            print("  OVERFLOW", w)
        return 2
    print("labels fit their boxes; >= 15 pt on a slide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
