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
            "⑥ 双刃剑：既抑制感染\n也经聚集与炎症促进 AD",
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
    """AChE–Aβ 复合物的动力学要点 + 候选抗菌肽的三个可能作用位点。"""
    fig, ax = mf.canvas(11.0, 5.4)

    # 左：AChE 口袋 + PAS + Aβ 停留区段
    mf.box(ax, 0.012, 0.385, 0.335, 0.595,
           "AChE 活性口袋\n催化位点 CAS 在底部", fc="#f2f4f7", ec="#9aa7b4", fs=16)
    mf.box(ax, 0.030, 0.750, 0.300, 0.180,
           "PAS 外周阴离子位点\n（Aβ 成核中心）", fc=LIGHT, ec=BLUE, fs=15.5)
    mf.box(ax, 0.040, 0.435, 0.280, 0.180,
           "Aβ 主要停留区段\nAChE 344–361", fc=PRED_F, ec=TEAL, fs=15.5)
    mf.arrow(ax, (0.18, 0.745), (0.18, 0.62), color=BLUE, lw=1.6)
    ax.text(0.012, 0.360, "Aβ 经 PAS 进入并沿酶表面铺展，停留于 344–361 区段（紧邻 PAS）",
            fontsize=15, color=GREY, va="top", ha="left")

    # 中：分子动力学结论
    mf.box(ax, 0.385, 0.385, 0.250, 0.595,
           "分子动力学模拟\n1 μs\n\n复合物保持稳定\n除 PAS 外另有多处接触\n344–361 不受\n双位点抑制剂位阻",
           fc="#eef4ef", ec=TEAL, fs=15.5)
    mf.arrow(ax, (0.35, 0.68), (0.382, 0.68), color=TEAL, lw=1.8)

    # 右：三条可检验假设
    ys = [0.765, 0.605, 0.445]
    hyps = [("H1 竞争 PAS", "减少 AChE 诱导的成核"),
            ("H2 结合 Aβ", "改变聚集路径与纤维形态"),
            ("H3 膜水平作用", "影响小胶质识别与炎症信号")]
    for y, (t, d) in zip(ys, hyps):
        mf.box(ax, 0.660, y, 0.330, 0.155, f"{t}\n{d}", fc=OPEN_F, ec=ORANGE, fs=15,
               tc="#7a4a12")
    ax.text(0.825, 0.960, "候选抗菌肽的三个可能作用位点", ha="center", fontsize=15.5,
            color="#7a4a12")
    mf.arrow(ax, (0.637, 0.68), (0.657, 0.68), color=ORANGE, lw=1.8)

    ax.text(0.5, 0.015,
            "机制结论：AChE–Aβ 复合物把抗菌肽、Aβ 聚集与胆碱能功能串成一条线；\n"
            "候选肽能否介入由对接与动力学给出优先序，再由抑菌与酶活实验验证。",
            ha="center", fontsize=15, color=GREY)
    mf.save(fig, "figM2_AChE_Aβ_机制.png")


def main() -> int:
    name = mf.load_cjk()
    mf.OUT.mkdir(parents=True, exist_ok=True)
    print(f"font: {name}")
    problems = []
    for fn in (fig_chain, fig_md_mechanism):
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
