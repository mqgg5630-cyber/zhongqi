#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_figures.py - draw every figure used by the 中期答辩 PPT.

All data comes from the user's own results (sources/已完成1.docx, tables 1 and 2);
nothing here is invented. Chinese labels are drawn with Noto Sans CJK SC
(run code/get_cjk_font.py first).

    python code/make_figures.py            # writes results/figures/*.png
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path("results/figures")
DPI = 200

# ----------------------------------------------------------------- style
INK = "#12324f"
BLUE = "#2f6fb0"
TEAL = "#2f9e8f"
ORANGE = "#e08a2e"
RED = "#c0504d"
GREY = "#6b7c8c"
LIGHT = "#eef3f8"

plt.rcParams.update({
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
    "font.size": 15,
    "axes.edgecolor": GREY,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.titlesize": 16,
    "axes.titleweight": "bold",
    "figure.facecolor": "white",
    "axes.unicode_minus": False,
})


def load_cjk() -> str:
    cands = sorted(glob.glob("/tmp/fonts/*CJK*.otf")) + \
            sorted(glob.glob(os.path.expanduser("~/.local/share/fonts/*CJK*.otf")))
    if not cands:
        sys.exit("CJK font missing - run: python code/get_cjk_font.py")
    fp = cands[0]
    font_manager.fontManager.addfont(fp)
    name = font_manager.FontProperties(fname=fp).get_name()
    plt.rcParams["font.family"] = name
    plt.rcParams["font.sans-serif"] = [name]
    return name


# ----------------------------------------------------------------- helpers
OVERFLOW: list[str] = []
EFFECTIVE: list[tuple[str, float, float]] = []   # (file, min fig font pt, effective pt on slide)
SLIDE_CONTENT_IN = 12.09      # 13.333 in slide - 2 x 0.62 in margins
# when a matplotlib figure is placed on a slide it is scaled to the slide width,
# so text sizes must be designed at that scale (see check in main())
SLIDE_TEXT_WIDTH_IN = 12.0


def box(ax, x, y, w, h, text, fc=LIGHT, ec=BLUE, fs=12, bold=False, tc=INK, radius=0.02,
        pad_pt=8.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.005,rounding_size={radius}",
                                linewidth=1.4, edgecolor=ec, facecolor=fc, zorder=2))
    wrapped = wrap_to_width(text, w * _axes_w_pt(ax) - pad_pt, fs)   # 自动折行，避免溢出边框
    t = ax.text(x + w / 2, y + h / 2, wrapped, ha="center", va="center", fontsize=fs,
                color=tc, zorder=3, weight="bold" if bold else "normal", linespacing=1.35)
    _check_overflow(t, x, y, w, h, fs, wrapped)


_MEAS_FIG = None


def _axes_size_pt(ax):
    """(width, height) of the axes box in points.

    box() coordinates are fractions of the AXES, not of the figure, so all the
    overflow maths must use the axes box - using the figure width made the
    checker too permissive (height was never checked at all).
    """
    bb = ax.get_window_extent()
    dpi = ax.figure.dpi
    return bb.width * 72.0 / dpi, bb.height * 72.0 / dpi


def _axes_w_pt(ax) -> float:
    return _axes_size_pt(ax)[0]


def _meas_width_pt(text: str, fs: float) -> float:
    """Width of a text in points, measured with the real CJK font."""
    global _MEAS_FIG
    if _MEAS_FIG is None:
        _MEAS_FIG = plt.figure(figsize=(20, 1), dpi=72)   # 1 px == 1 pt
    t = _MEAS_FIG.text(0, 0, text, fontsize=fs)
    _MEAS_FIG.canvas.draw()
    w = t.get_window_extent(_MEAS_FIG.canvas.get_renderer()).width
    t.remove()
    return w


def wrap_to_width(text: str, width_pt: float, fs: float) -> str:
    """Greedy wrap: keep the explicit newlines, then break long lines to fit."""
    out_lines = []
    for line in text.split("\n"):
        if _meas_width_pt(line, fs) <= width_pt or len(line) <= 1:
            out_lines.append(line)
            continue
        cur = ""
        for ch in line:
            if cur and _meas_width_pt(cur + ch, fs) >= width_pt - 0.5:
                out_lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            out_lines.append(cur)
    return "\n".join(out_lines)


def _min_font(fig) -> float:
    sizes = []
    for t in fig.findobj(match=lambda o: hasattr(o, "get_fontsize")):
        try:
            sizes.append(float(t.get_fontsize()))
        except Exception:
            pass
    for ax in fig.axes:
        for t in [ax.title, ax.xaxis.label, ax.yaxis.label] + \
                 list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            try:
                sizes.append(float(t.get_fontsize()))
            except Exception:
                pass
        lg = ax.get_legend()
        if lg is not None:
            for t in lg.get_texts():
                sizes.append(float(t.get_fontsize()))
    return min(sizes) if sizes else 0.0


def save(fig, name: str):
    """Save a figure and record what its smallest font becomes on the slide."""
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    from PIL import Image
    with Image.open(path) as im:
        w_in = im.size[0] / DPI
    scale = SLIDE_CONTENT_IN / w_in
    mn = _min_font(fig)
    eff = mn * scale
    EFFECTIVE.append((name, mn, eff))
    if eff < 14.9:
        OVERFLOW.append(f"{name}: smallest figure font {mn:.1f} pt -> {eff:.1f} pt on the slide")
    plt.close(fig)


def _check_overflow(text_artist, x, y, w, h, fs, text):
    """Warn when a label does not fit its box, measured with the real CJK font."""
    try:
        fig = text_artist.figure
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        bbox = text_artist.get_window_extent(renderer=r)
        ax_w_pt, ax_h_pt = _axes_size_pt(text_artist.axes)
        box_w_pt = w * ax_w_pt
        box_h_pt = h * ax_h_pt
        # get_window_extent returns display pixels -> convert to points
        tw = bbox.width * 72.0 / fig.dpi
        th = bbox.height * 72.0 / fig.dpi
        if tw > box_w_pt - 4 or th > box_h_pt - 3:
            OVERFLOW.append(f"{text.splitlines()[0][:16]!r}: text {tw:.0f}x{th:.0f} pt "
                            f"vs box {box_w_pt:.0f}x{box_h_pt:.0f} pt ({fs} pt font)")
    except Exception as exc:                     # measurement must never break the build
        OVERFLOW.append(f"measure failed: {exc}")


def arrow(ax, p1, p2, color=BLUE, style="-|>", lw=1.8, rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=16,
                                 linewidth=lw, color=color, zorder=1,
                                 connectionstyle=f"arc3,rad={rad}", linestyle=ls))


def canvas(w=13.33, h=7.5):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def canvas_full(w=12.0, h=4.35):
    """满幅画布：坐标轴铺满整张图，box 的比例直接等于图内的英寸比例。"""
    fig, ax = plt.subplots(figsize=(w, h))
    fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# ----------------------------------------------------------------- 1. pipeline
def fig_pipeline():
    """三阶段 × 四列的技术路线。画布 12 in 宽，正文 16 pt：
    投影到 11 in 的幻灯片后实际字号约 15 pt，满足最小字号要求。"""
    fig, ax = canvas(12, 4.0)

    rows = [
        (0.655, [
            "476 例粪便样本\n双端鸟枪法测序",
            "质控与去宿主\nfastp + KneadData",
            "从头组装\nMEGAHIT",
            "多算法联合分箱\nMetaBAT2 · MaxBin2\n· CONCOCT",
        ], LIGHT, BLUE),
        (0.345, [
            "分箱提纯 metaWRAP\n（≥50% / ≤10%）",
            "22 582 个 MAGs\nMIMAG 高质量 757 个",
            "种水平去冗余 dRep\n(95% ANI) 1 971 个",
            "sORF 预测与去冗余\ngetorf 5—50 aa\n9 139.2 万条",
        ], "#e8f6f1", TEAL),
        (0.035, [
            "DeepMetaAMP 训练\nESM-2 + Transformer",
            "全量推理\n筛选候选抗菌肽",
            "丰度定量\nCoverM + CLR 变换",
            "四队列差异分析\nKruskal-Wallis /\nMann-Whitney U",
        ], "#fdf2e3", ORANGE),
    ]
    x0, w, gap = 0.028, 0.228, 0.024
    h = 0.245
    for y, texts, fc, ec in rows:
        for i, t in enumerate(texts):
            x = x0 + i * (w + gap)
            box(ax, x, y, w, h, t, fc=fc, ec=ec, fs=16)
            if i < 3:
                arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2), color=ec, lw=1.8)
        if y != 0.035:
            arrow(ax, (0.5, y), (0.5, y - 0.075), color=GREY, lw=1.6, ls="--")

    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="s", ls="", ms=14, mfc=LIGHT, mec=BLUE, label="数据基础（已完成）"),
        Line2D([], [], marker="s", ls="", ms=14, mfc="#e8f6f1", mec=TEAL, label="多肽库构建（已完成）"),
        Line2D([], [], marker="s", ls="", ms=14, mfc="#fdf2e3", mec=ORANGE, label="模型与差异分析（进行中）"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
              bbox_to_anchor=(0.5, 1.06), fontsize=16)
    save(fig, "fig1_技术路线.png")


# ----------------------------------------------------------------- 2. yield
def fig_yield():
    fig, ax = plt.subplots(figsize=(11, 5.2))
    labels = ["测序样本", "组装基因组\n(MAGs)", "MIMAG 高质量\n基因组", "种水平代表\n基因组", "非冗余多肽"]
    vals = [476, 22582, 757, 1971, 91392612]
    disp = ["476", "22 582", "757", "1 971", "9 139.2 万"]
    colors = [GREY, BLUE, TEAL, "#3f8fbf", ORANGE]
    x = range(len(vals))
    bars = ax.bar(x, vals, color=colors, width=0.62, zorder=3)
    ax.set_yscale("log")
    ax.set_ylabel("数量（对数坐标）", fontsize=13)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=14.5)
    ax.grid(axis="y", ls=":", color="#c9d6e2", zorder=0)
    ax.set_title("本阶段产出规模：476 例样本 → 9 139.2 万条非冗余多肽", pad=14)
    for i, (b, d) in enumerate(zip(bars, disp)):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.35, d,
                ha="center", fontsize=15, weight="bold", color=INK)
    ax.set_ylim(200, 6e8)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "fig2_产出规模.png")


# ----------------------------------------------------------------- 3. cohort design
def fig_cohort():
    fig, ax = canvas(11, 4.25)
    ax.text(0.5, 0.955, "队列分层设计：以最短板为约束的严格匹配", ha="center",
            fontsize=20, weight="bold")

    box(ax, 0.19, 0.70, 0.62, 0.17,
        "全队列 476 例受试者\n5 个诊断阶段 × 2 种性别 × 3 个年龄段 = 30 个分层单元",
        fc=LIGHT, ec=BLUE, fs=15.5, bold=True)

    box(ax, 0.03, 0.36, 0.44, 0.24,
        "匹配亚队列 265 例\n各阶段均 53 例　每组 35 女 / 18 男\n组间平均年龄最大差 1.8 岁",
        fc="#e8f6f1", ec=TEAL, fs=14.5)
    box(ax, 0.53, 0.36, 0.44, 0.24,
        "全样本队列 476 例\nNC 61 / SCS 78 / SCD 89 / MCI 114 / AD 117\n保留真实世界临床异质性",
        fc=LIGHT, ec=BLUE, fs=14.5)
    arrow(ax, (0.34, 0.70), (0.25, 0.60), color=TEAL, lw=1.8)
    arrow(ax, (0.66, 0.70), (0.75, 0.60), color=BLUE, lw=1.8)
    ax.text(0.135, 0.655, "分层抽样", color=TEAL, fontsize=14.5)
    ax.text(0.77, 0.655, "全量纳入", color=BLUE, fontsize=14.5)

    q = [
        (0.03, "队列一\n匹配 265 例\n五阶段比较", TEAL),
        (0.275, "队列二\n匹配 265 例\nNC 对 AD", TEAL),
        (0.52, "队列三\n全 476 例\n五阶段比较", BLUE),
        (0.765, "队列四\n全 476 例\nNC 对 AD", BLUE),
    ]
    for x, t, c in q:
        box(ax, x, 0.055, 0.20, 0.21, t, fc="white", ec=c, fs=13.5)
    arrow(ax, (0.25, 0.36), (0.13, 0.26), color=GREY, lw=1.2, ls="--")
    arrow(ax, (0.25, 0.36), (0.375, 0.26), color=GREY, lw=1.2, ls="--")
    arrow(ax, (0.75, 0.36), (0.62, 0.26), color=GREY, lw=1.2, ls="--")
    arrow(ax, (0.75, 0.36), (0.865, 0.26), color=GREY, lw=1.2, ls="--")
    ax.text(0.5, -0.035, "主要结局：单位基因组 sORF 数（sORF_per_MAG）　次要结局：sORF 总数　"
                         "偏倚诊断：代表基因组数",
            ha="center", fontsize=13.5, color=GREY)
    save(fig, "fig3_队列设计.png")


# ----------------------------------------------------------------- 4. sORF per MAG
QUEUE1 = [("NC", 51, 113306.7, 39216.8), ("SCS", 50, 113214.0, 46391.6),
          ("SCD", 52, 104693.8, 40532.0), ("MCI", 51, 108738.2, 35670.7),
          ("AD", 51, 114555.0, 51117.8)]
QUEUE3 = [("NC", 61, 114529.3, 44832.6), ("SCS", 78, 110000.2, 41944.1),
          ("SCD", 89, 108545.9, 41447.3), ("MCI", 114, 114283.5, 48208.6),
          ("AD", 117, 111582.5, 45370.1)]


def fig_sORF():
    """主要结局指标：两个队列各自的误差棒图，组间差异标注在各自面板内。"""
    panels = [
        (QUEUE1, "队列一：匹配 265 例（各 53 例）", "Kruskal-Wallis P = 0.7344"),
        (QUEUE3, "队列三：全 476 例", "Kruskal-Wallis P = 0.8359"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.55), sharey=True)
    for ax, (data, title, sub) in zip(axes, panels):
        labels = [d[0] for d in data]
        means = [d[2] for d in data]
        sds = [d[3] for d in data]
        ns = [d[1] for d in data]
        xs = list(range(len(data)))
        ax.errorbar(xs, means, yerr=sds, fmt="o", ms=9, lw=2.2, capsize=7,
                    color=BLUE, ecolor=GREY, zorder=3)
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{l}\n(n={n})" for l, n in zip(labels, ns)], fontsize=15)
        ax.set_title(f"{title}\n{sub}", fontsize=16.5, pad=10)
        ax.grid(axis="y", ls=":", color="#c9d6e2", zorder=0)
        ax.set_ylim(45000, 178000)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("组间相对差异 9.4%" if ax is axes[0] else "组间相对差异 5.5%",
                      fontsize=15.5, color=GREY, labelpad=8)
    axes[0].set_ylabel("单位基因组 sORF 数（均值 ± 标准差）", fontsize=15.5)
    axes[0].tick_params(axis="y", labelsize=14.5)
    save(fig, "fig4_sORF数量.png")


# ----------------------------------------------------------------- 5. p values
def fig_pvalues():
    rows = [
        ("队列一（265例）五阶段 · sORF 总数", 0.5689, "KW"),
        ("队列一（265例）五阶段 · 单位基因组", 0.7344, "KW"),
        ("队列一（265例）五阶段 · 基因组数", 0.5591, "KW"),
        ("队列二（265例）NC-AD · sORF 总数", 0.9786, "MWU"),
        ("队列二（265例）NC-AD · 单位基因组", 0.6204, "MWU"),
        ("队列二（265例）NC-AD · 基因组数", 0.8895, "MWU"),
        ("队列三（476例）五阶段 · sORF 总数", 0.6860, "KW"),
        ("队列三（476例）五阶段 · 单位基因组", 0.8359, "KW"),
        ("队列三（476例）五阶段 · 基因组数", 0.5585, "KW"),
        ("队列四（476例）NC-AD · sORF 总数", 0.7662, "MWU"),
        ("队列四（476例）NC-AD · 单位基因组", 0.4291, "MWU"),
        ("队列四（476例）NC-AD · 基因组数", 0.4590, "MWU"),
    ]
    fig, ax = plt.subplots(figsize=(9.6, 5.6))
    ys = list(range(len(rows)))[::-1]
    ps = [r[1] for r in rows]
    ax.scatter(ps, ys, s=90, color=[GREY, ORANGE, GREY] * 0 + [BLUE if p > 0.05 else RED for p in ps],
               zorder=3, edgecolor="white", linewidth=1.2)
    for y, p in zip(ys, ps):
        ax.text(p + 0.012, y, f"{p:.4f}", va="center", fontsize=15, color=INK)
    ax.axvline(0.05, color=RED, ls="--", lw=1.6, zorder=1)
    ax.text(0.055, 0.02, "显著性阈值 P = 0.05\n（所有点均在阈值右侧）", color=RED, fontsize=15,
            va="bottom", linespacing=1.4)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=15)
    ax.set_xlim(0, 1.14)
    ax.set_xlabel("双尾 P 值", fontsize=15.5)
    ax.set_title("四个队列 12 项检验：P 值介于 0.4291—0.9786，均无统计学意义", pad=16, fontsize=17)
    ax.grid(axis="x", ls=":", color="#c9d6e2", zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save(fig, "fig5_P值.png")


# ----------------------------------------------------------------- 6. progress
def fig_progress():
    tasks = [
        ("数据获取与质控去宿主", 0, 3, 100),
        ("组装、联合分箱与评估", 3, 3, 100),
        ("sORF 预测与多肽库", 5, 2, 100),
        ("队列分层设计", 7, 1, 100),
        ("数量层面统计分析", 7, 2, 100),
        ("DeepMetaAMP 训练", 8, 3, 35),
        ("全量推理与候选筛选", 10, 2, 0),
        ("差异分析与论文撰写", 12, 3, 0),
    ]
    fig, ax = plt.subplots(figsize=(11, 3.75))
    for i, (name, start, dur, pct) in enumerate(tasks):
        y = len(tasks) - 1 - i
        ax.barh(y, dur, left=start, height=0.55, color="#dde7f0", edgecolor="#c2d2e0", zorder=2)
        if pct:
            ax.barh(y, dur * pct / 100, left=start, height=0.55,
                    color=TEAL if pct == 100 else ORANGE, zorder=3)
            ax.text(start + dur + 0.15, y, f"{pct}%", va="center", fontsize=15,
                    color=TEAL if pct == 100 else ORANGE, weight="bold")
        else:
            ax.text(start + dur + 0.15, y, "待开展", va="center", fontsize=15, color=GREY)
    ax.set_yticks(range(len(tasks))[::-1])
    ax.set_yticklabels([t[0] for t in tasks], fontsize=15)
    ax.set_xlim(0, 16.6)
    ax.set_xticks(range(0, 18, 3))
    ax.set_xticklabels(["26.1", "26.4", "26.7", "26.10", "27.1", "27.4"], fontsize=15)
    ax.set_xlabel("时间（2026 年 1 月 — 2027 年 4 月）", fontsize=15)
    ax.axvline(8.6, color=RED, ls="--", lw=1.6)
    ax.text(8.75, len(tasks) - 0.45, "中期检查", color=RED, fontsize=15, weight="bold")
    ax.grid(axis="x", ls=":", color="#c9d6e2", zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save(fig, "fig6_进度甘特.png")


# ----------------------------------------------------------------- 7. model
def fig_model():
    fig, ax = canvas(11.8, 3.55)


    box(ax, 0.015, 0.42, 0.16, 0.25, "输入序列\n5—50 aa\n非冗余多肽库", fc=LIGHT, ec=BLUE, fs=14)
    box(ax, 0.205, 0.42, 0.16, 0.25, "ESM-2\n蛋白质语言模型\n提取序列表征", fc="#e8f6f1", ec=TEAL, fs=14)
    box(ax, 0.395, 0.42, 0.17, 0.25, "Transformer /\nBiLSTM 编码器\n捕获长程依赖", fc="#e8f6f1", ec=TEAL, fs=14)
    box(ax, 0.595, 0.42, 0.16, 0.25, "注意力池化\n聚焦关键氨基酸\n位点", fc="#e8f6f1", ec=TEAL, fs=14)
    box(ax, 0.785, 0.42, 0.20, 0.25, "分类头（Focal Loss）\n抗菌肽 / 非抗菌肽\n阈值由验证集确定", fc="#fdf2e3", ec=ORANGE, fs=14)
    for a, b in [(0.175, 0.205), (0.365, 0.395), (0.565, 0.595), (0.755, 0.785)]:
        arrow(ax, (a, 0.545), (b, 0.545))

    box(ax, 0.015, 0.03, 0.315, 0.30,
        "训练集\n正样本 1 085 条\n负样本 58 776 条\n（c_AMPs-prediction / non-AMPs）",
        fc=LIGHT, ec=BLUE, fs=13.5)
    box(ax, 0.35, 0.03, 0.30, 0.30,
        "训练策略\n优化器 AdamW\n损失函数 Focal Loss\n按 40% 一致性划分\n避免同源序列泄漏",
        fc=LIGHT, ec=BLUE, fs=13.5)
    box(ax, 0.67, 0.03, 0.315, 0.30,
        "评价指标\nAUC / F1 / Precision@k / MCC\n以 AMPSphere 序列构建\n外部独立测试集",
        fc=LIGHT, ec=BLUE, fs=13.5)
    save(fig, "fig7_模型结构.png")


# ----------------------------------------------------------------- 8. next steps
def fig_next():
    tasks = [
        ("DeepMetaAMP 训练与调优", 0, 3, "模型权重与性能报告"),
        ("全量多肽推理与候选筛选", 2, 3, "候选抗菌肽清单"),
        ("丰度定量与四队列差异分析", 4, 3, "差异抗菌肽列表与图"),
        ("分阶段趋势与临床关联", 6, 2, "趋势与相关性结果"),
        ("可解释性与体外验证", 7, 3, "关键基序与 MIC 数据"),
        ("论文撰写与预答辩准备", 9, 4, "SCI 论文与学位论文"),
    ]
    fig, ax = plt.subplots(figsize=(11, 3.7))
    colors = [ORANGE, "#e8a75e", TEAL, "#4fb3a4", BLUE, "#5a8fc4"]
    for i, (name, start, dur, deliver) in enumerate(tasks):
        y = len(tasks) - 1 - i
        ax.barh(y, dur, left=start, height=0.5, color=colors[i], zorder=3)
        ax.text(start + dur + 0.2, y, deliver, va="center", fontsize=15, color=GREY)
    ax.set_yticks(range(len(tasks))[::-1])
    ax.set_yticklabels([t[0] for t in tasks], fontsize=15)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 14, 2))
    ax.set_xticklabels(["26.9", "26.11", "27.1", "27.3", "27.5", "27.7", "27.9"], fontsize=15)
    ax.set_xlabel("时间（2026 年 9 月 — 2027 年 7 月）", fontsize=15)
    ax.grid(axis="x", ls=":", color="#c9d6e2", zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save(fig, "fig8_下一步计划.png")


def main() -> int:
    name = load_cjk()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"font: {name}")
    for fn in (fig_pipeline, fig_yield, fig_cohort, fig_sORF, fig_pvalues,
               fig_progress, fig_model, fig_next):
        fn()
        print("  drawn", fn.__name__)
    print(f"\n{len(list(OUT.glob('*.png')))} figures -> {OUT}")
    print("\nfigure                min font   on slide")
    for name, mn, eff in EFFECTIVE:
        flag = "" if eff >= 14.9 else "   <-- too small"
        print(f"  {name:<28} {mn:5.1f} pt   {eff:5.1f} pt{flag}")
    if OVERFLOW:
        print(f"\n{len(OVERFLOW)} label(s) do not fit their box:")
        for w in OVERFLOW:
            print("  OVERFLOW", w)
        return 2
    print("all labels fit their boxes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
