#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_figures2.py - figures for the NEW narrative of the midterm deck:

    数据资源 -> 三模型共识预测 -> 分阶段差异分析 -> 宏蛋白组去重与特有肽
             -> 与 AD 发病机制关联 -> 极简抑菌实验

Every figure is a *process / schematic* figure (流程示意), so no numeric result
is invented. Only the finish state (已完成 / 进行中 / 下一步) is shown, which is
exactly what the supervisor asked for.

Chinese font: run `python code/get_cjk_font.py` once.
Usage: python code/make_figures2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import make_figures as mf          # helpers: canvas / box / arrow / save / load_cjk

LIGHT, BLUE, TEAL, ORANGE = mf.LIGHT, mf.BLUE, mf.TEAL, mf.ORANGE
GREY, INK, RED = mf.GREY, mf.INK, mf.RED
DONE_F, DONE_E = LIGHT, BLUE            # 已完成
DATA_F, DATA_E = "#e8f6f1", TEAL        # 数据产出 / 已完成
NEXT_F, NEXT_E = "#fdf2e3", ORANGE      # 进行中 / 下一步


# ---------------------------------------------------------------- 总览：研究思路
def fig_roadmap():
    fig, ax = mf.canvas(12, 4.3)
    rows = [
        (0.62, [
            "① 宏基因组数据\n476 例队列",
            "② 种水平参考集\n微生物基因组",
            "③ sORF 多肽库\n微生物源短肽",
            "④ 三模型共识预测\n候选抗菌肽",
        ], DONE_F, DONE_E),
        (0.30, [
            "⑤ 分阶段差异分析\n健康 vs 各阶段",
            "⑥ 宏蛋白组去重\n表达证据过滤",
            "⑦ 特有抗菌肽\n健康特有 / 阶段特有",
            "⑧ 机制关联与简验\nAD 发病机制",
        ], NEXT_F, NEXT_E),
    ]
    x0, w, gap, h = 0.028, 0.228, 0.024, 0.24
    for y, texts, fc, ec in rows:
        for i, t in enumerate(texts):
            x = x0 + i * (w + gap)
            mf.box(ax, x, y, w, h, t, fc=fc, ec=ec, fs=16)
            if i < 3:
                mf.arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2), color=ec, lw=1.8)
    mf.arrow(ax, (0.5, 0.62), (0.5, 0.545), color=GREY, lw=1.6, ls="--")

    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="s", ls="", ms=14, mfc=DONE_F, mec=DONE_E, label="已完成（数据与预测）"),
        Line2D([], [], marker="s", ls="", ms=14, mfc=NEXT_F, mec=NEXT_E, label="已完成 / 收尾中（分析与验证）"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
              bbox_to_anchor=(0.5, 1.05), fontsize=16)
    mf.save(fig, "figA_研究思路总览.png")


# ---------------------------------------------------------------- 三模型预测
def fig_three_models():
    fig, ax = mf.canvas(11.6, 3.9)
    # 输入
    mf.box(ax, 0.01, 0.31, 0.19, 0.42,
           "非冗余多肽库\n5—50 aa\n微生物源短肽", fc=DATA_F, ec=DATA_E, fs=16)
    # 三个模型
    ys = [0.68, 0.43, 0.18]
    for y, name in zip(ys, ["Attention 模型", "LSTM 模型", "BERT 模型"]):
        mf.box(ax, 0.29, y, 0.235, 0.22, name + "\n输出抗菌肽概率", fc=LIGHT, ec=BLUE, fs=15.5)
        mf.arrow(ax, (0.20, 0.52), (0.29, y + 0.11), color=BLUE, lw=1.6, rad=0.12)
        mf.arrow(ax, (0.525, y + 0.11), (0.585, 0.52), color=BLUE, lw=1.6, rad=-0.12)
    # 共识与输出
    mf.box(ax, 0.585, 0.31, 0.215, 0.42,
           "共识判定\n三模型一致阳性\n才纳入候选集", fc=NEXT_F, ec=ORANGE, fs=16, bold=True)
    mf.arrow(ax, (0.80, 0.52), (0.845, 0.52), color=ORANGE, lw=2.0)
    mf.box(ax, 0.845, 0.31, 0.145, 0.42,
           "候选抗菌肽\n高置信度", fc=DATA_F, ec=DATA_E, fs=16, bold=True)
    ax.text(0.5, 0.02,
            "三模型独立预测 + 一致性投票：兼顾灵敏度与特异度，避免单一模型偏倚",
            ha="center", fontsize=15.5, color=GREY)
    mf.save(fig, "figB_三模型预测.png")


# ---------------------------------------------------------------- 分阶段差异
def fig_stage_diff():
    import numpy as np
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.4, 3.9),
                                   gridspec_kw={"width_ratios": [1.25, 1]})
    for a in (ax1, ax2):
        a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_visible(False)

    # 左：分组 × 候选肽 矩阵示意
    rng = np.random.default_rng(7)
    n_row, n_col = 9, 5
    data = rng.normal(0, 1, (n_row, n_col))
    data[2, :] += np.array([1.6, 1.3, 0.4, -1.1, -1.6])
    data[6, :] += np.array([-1.5, -0.9, 0.2, 1.2, 1.7])
    ax1.imshow(data, cmap="RdBu_r", aspect="auto", vmin=-2.5, vmax=2.5)
    ax1.set_xticks(range(n_col))
    ax1.set_xticklabels(["NC", "SCS", "SCD", "MCI", "AD"], fontsize=15)
    ax1.set_ylabel("候选抗菌肽", fontsize=15.5)
    ax1.set_title("分阶段丰度谱（流程示意）", fontsize=16, pad=10)
    ax1.tick_params(axis="x", length=0)
    ax1.set_yticks([2, 6])
    ax1.set_yticklabels(["随病程升高\n的候选肽", "随病程降低\n的候选肽"], fontsize=13.5)
    ax1.tick_params(axis="y", length=0)

    # 右：火山图示意
    x = rng.normal(0, 1, 120); y = rng.uniform(0, 5.5, 120)
    ax2.scatter(x, y, s=26, color=GREY, alpha=0.55)
    sel = (x > 1.4) | (x < -1.4)
    ax2.scatter(x[sel], y[sel], s=34, color=RED, alpha=0.9)
    ax2.axvline(1.4, color=BLUE, ls="--", lw=1.4)
    ax2.axvline(-1.4, color=BLUE, ls="--", lw=1.4)
    ax2.set_xlabel("组间差异倍数（对数）", fontsize=15)
    ax2.set_ylabel("统计显著性", fontsize=15.5)
    ax2.set_title("差异筛选（流程示意）", fontsize=16, pad=10)
    ax2.set_xticks([]); ax2.set_yticks([])
    for s in ax2.spines.values():
        s.set_visible(False)
    ax2.text(0.97, 0.05, "红色：达显著阈值的差异抗菌肽", transform=ax2.transAxes,
             ha="right", fontsize=14, color=RED,
             bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2.5))
    fig.subplots_adjust(wspace=0.15)
    mf.save(fig, "figC_分阶段差异分析.png")


# ---------------------------------------------------------------- 宏蛋白组去重
def fig_metaproteome():
    """三步式流程，避免交叉图与文字叠压。"""
    fig, ax = mf.canvas(11.6, 3.6)
    boxes = [
        (0.02, "① 候选抗菌肽\n（宏基因组预测）", LIGHT, BLUE),
        (0.355, "② 宏蛋白组证据过滤\n只保留蛋白层面\n可检出的候选肽\n排除仅序列层面预测的假阳性", DATA_F, DATA_E),
        (0.69, "③ 分组比较\n组内共有 / 组间特有\n得到健康特有\n与各阶段特有的抗菌肽", NEXT_F, NEXT_E),
    ]
    w, h = 0.29, 0.62
    for x, t, fc, ec in boxes:
        mf.box(ax, x, 0.24, w, h, t, fc=fc, ec=ec, fs=15.5)
    for x in (0.31, 0.645):
        mf.arrow(ax, (x, 0.55), (x + 0.045, 0.55), color=GREY, lw=2.0)
    ax.text(0.5, 0.155, "去重的两层含义：先在序列层面去冗余，再用宏蛋白组表达证据二次去重",
            ha="center", fontsize=15.5, color=GREY)
    ax.text(0.5, 0.03, "目的：把\"序列上可能\"收敛为\"真实存在且表达\"的抗菌肽，降低后续验证的假阳性",
            ha="center", fontsize=15, color=GREY)
    mf.save(fig, "figD_宏蛋白组去重.png")


# ---------------------------------------------------------------- 机制关联
def fig_mechanism():
    fig, ax = mf.canvas(11.8, 3.95)
    mf.box(ax, 0.31, 0.70, 0.38, 0.24,
           "分组特异的候选抗菌肽（健康特有 / 阶段特有）", fc=NEXT_F, ec=ORANGE, fs=16, bold=True)
    mf.box(ax, 0.02, 0.24, 0.30, 0.34,
           "① 与 Aβ 相互作用\n影响聚集与纤维化", fc=LIGHT, ec=BLUE, fs=15.5)
    mf.box(ax, 0.35, 0.24, 0.30, 0.34,
           "② 与 AChE（PAS）结合\n干扰 AChE–Aβ 成核", fc=LIGHT, ec=BLUE, fs=15.5)
    mf.box(ax, 0.68, 0.24, 0.30, 0.34,
           "③ 免疫与炎症通路\n肠—脑轴 / 神经炎症", fc=LIGHT, ec=BLUE, fs=15.5)
    for x in (0.17, 0.50, 0.83):
        mf.arrow(ax, (0.50, 0.70), (x, 0.58), color=GREY, lw=1.5, rad=0.10)
    ax.text(0.5, 0.075,
            "对接与分子动力学模拟验证结合稳定性（参照 AChE–Aβ 复合物模拟研究的思路）",
            ha="center", fontsize=15.5, color=GREY)
    mf.save(fig, "figE_机制关联.png")


# ---------------------------------------------------------------- 极简抑菌实验
def fig_antibacterial():
    fig, ax = mf.canvas(11.8, 3.6)
    steps = [
        ("候选肽\n3—5 条\n人工合成", LIGHT, BLUE),
        ("指示菌\n大肠杆菌\n金黄色葡萄球菌", DATA_F, DATA_E),
        ("纸片扩散法\n抑菌圈初筛", NEXT_F, NEXT_E),
        ("微量肉汤稀释法\nMIC 测定", NEXT_F, NEXT_E),
        ("结论\n活性与剂量关系", LIGHT, BLUE),
    ]
    x0, w, gap, h = 0.0, 0.185, 0.019, 0.38
    for i, (t, fc, ec) in enumerate(steps):
        x = x0 + i * (w + gap)
        mf.box(ax, x, 0.36, w, h, t, fc=fc, ec=ec, fs=14.5)
        if i < len(steps) - 1:
            mf.arrow(ax, (x + w, 0.57), (x + w + gap, 0.57), color=ec, lw=1.8)
    ax.text(0.5, 0.19,
            "方案极简：常规微生物实验室即可完成，用于对候选肽做最小可行性验证",
            ha="center", fontsize=15.5, color=GREY)
    ax.text(0.5, 0.045,
            "设阳性对照（已知抗菌肽）与阴性对照（溶剂），每组 3 重复",
            ha="center", fontsize=15, color=GREY)
    mf.save(fig, "figF_抑菌实验方案.png")


# ---------------------------------------------------------------- 进度甘特（更新）
def fig_progress2():
    tasks = [
        ("数据获取与资源构建", 0, 3, 100),
        ("三模型共识预测", 3, 2, 100),
        ("分阶段差异分析", 5, 2, 100),
        ("宏蛋白组去重与特有肽", 6, 2, 100),
        ("机制关联分析", 8, 1, 100),
        ("极简抑菌实验验证", 8, 2, 45),
        ("论文撰写与预答辩", 9, 4, 30),
    ]
    fig, ax = plt.subplots(figsize=(11, 3.75))
    for i, (name, start, dur, pct) in enumerate(tasks):
        y = len(tasks) - 1 - i
        ax.barh(y, dur, left=start, height=0.55, color="#dde7f0", edgecolor="#c2d2e0", zorder=2)
        ax.barh(y, dur * pct / 100, left=start, height=0.55,
                color=TEAL if pct >= 100 else ORANGE, zorder=3)
        ax.text(start + dur + 0.15, y, f"{pct}%", va="center", fontsize=15,
                color=TEAL if pct >= 100 else ORANGE, weight="bold")
    ax.set_yticks(range(len(tasks))[::-1])
    ax.set_yticklabels([t[0] for t in tasks], fontsize=15)
    ax.set_xlim(0, 15.4)
    ax.set_xticks(range(0, 15, 2))
    ax.set_xticklabels(["26.1", "26.3", "26.5", "26.7", "26.9", "26.11", "27.1", "27.3"],
                       fontsize=14.5)
    ax.set_xlabel("时间（2026 年 1 月 — 2027 年 4 月）", fontsize=15)
    ax.axvline(9.0, color=RED, ls="--", lw=1.6)
    ax.text(9.15, len(tasks) - 0.45, "中期检查", color=RED, fontsize=15, weight="bold")
    ax.grid(axis="x", ls=":", color="#c9d6e2", zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    mf.save(fig, "figG_进度甘特.png")


def main() -> int:
    name = mf.load_cjk()
    mf.OUT.mkdir(parents=True, exist_ok=True)
    print(f"font: {name}")
    problems = []
    for fn in (fig_roadmap, fig_three_models, fig_stage_diff, fig_metaproteome,
               fig_mechanism, fig_antibacterial, fig_progress2):
        mf.OVERFLOW.clear()
        fn()
        problems += [f"{fn.__name__}: {w}" for w in mf.OVERFLOW]
        print(f"  drawn {fn.__name__}")
    print("\nfigure                min font   on slide")
    for fname, mn, eff in mf.EFFECTIVE:
        flag = "" if eff >= 14.9 else "   <-- too small"
        print(f"  {fname:<28} {mn:5.1f} pt   {eff:5.1f} pt{flag}")
    if problems:
        print(f"\n{len(problems)} label(s) do not fit their box:")
        for w in problems:
            print("  OVERFLOW", w)
        return 2
    print("all labels fit their boxes and are >= 15 pt on the slide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
