#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mid2_figures.py - 中间版 2（进度半程）专用图。

完整版与中间版 1 的图都在 `results/figures/`，本脚本只额外画一张：
`figA_研究思路总览_半程.png` —— 与完整版同一张路线图，但只把前四项标为
"已完成（数据与预测）"，后四项标为"下一阶段（分析与验证）"，直观呈现半程进度。
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
GREY = mf.GREY
DONE_F, DONE_E = LIGHT, BLUE            # 已完成
NEXT_F, NEXT_E = "#f2f4f7", "#9aa7b4"   # 下一阶段（灰）


def fig_roadmap_half():
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
            "⑧ 机制关联与验证\nAD 发病机制",
        ], NEXT_F, NEXT_E),
    ]
    x0, w, gap, h = 0.028, 0.228, 0.024, 0.24
    for y, texts, fc, ec in rows:
        for i, t in enumerate(texts):
            x = x0 + i * (w + gap)
            mf.box(ax, x, y, w, h, t, fc=fc, ec=ec, fs=16,
                   tc=mf.INK if fc == DONE_F else "#5b6672")
            if i < 3:
                mf.arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2), color=ec, lw=1.8)
    mf.arrow(ax, (0.5, 0.62), (0.5, 0.545), color=GREY, lw=1.6, ls="--")

    handles = [
        Line2D([], [], marker="s", ls="", ms=14, mfc=DONE_F, mec=DONE_E,
               label="已完成（数据与预测，4/8）"),
        Line2D([], [], marker="s", ls="", ms=14, mfc=NEXT_F, mec=NEXT_E,
               label="下一阶段（分析与验证，4/8）"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
              bbox_to_anchor=(0.5, 1.05), fontsize=16)
    mf.save(fig, "figA_研究思路总览_半程.png")


def main() -> int:
    name = mf.load_cjk()
    mf.OUT.mkdir(parents=True, exist_ok=True)
    print(f"font: {name}")
    mf.OVERFLOW.clear()
    mf.EFFECTIVE.clear()
    fig_roadmap_half()
    for fname, mn, eff in mf.EFFECTIVE:
        flag = "" if eff >= 14.9 else "   <-- too small"
        print(f"  {fname:<34} {mn:5.1f} pt   on slide {eff:5.1f} pt{flag}")
    if mf.OVERFLOW:
        for w in mf.OVERFLOW:
            print("  OVERFLOW", w)
        return 2
    print("all labels fit their boxes and are >= 15 pt on the slide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
