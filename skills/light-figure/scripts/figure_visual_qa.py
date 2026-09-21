#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figure_visual_qa.py — 渲染后视觉 QA 回看闭环（挂接 _shared/visual_qa 地基契约3）。

为什么有这个脚本（figure 相对全市场最大的空白机会）
------------------------------------------------
SciencePlots/cnsplots/pylustrator/同名 Claude skill 以及 figure 的静态校验脚本
（integrity_lint/figure_export）**全是"盲"代码工具/静态校验**——从不真正看一眼
渲染出来的图。但模型本就是多模态的：把图渲染成 PNG 再喂回模型自己看，能抓静态 lint 与尺寸
校验永远抓不到的——标签重叠、图例压数据、文字溢出被裁、刻度挤成一团、子图对不齐。这是 figure
能独占的顶级增量。本脚本把"渲染→看图→列问题→改"做成可执行的结构化闭环。
（PlotGen 的 Visual Feedback Agent / ReLook 的多模态 critic 印证此路;本脚本把它接进科研 DAG。）

两部分（对齐 _shared/visual_qa 的 render_then_review 协议）
--------------------------------------------------------
1. **确定性几何检测（纯计算，无需 VLM）**：从 matplotlib figure 抽出所有文本/图例的 AABB
   包围盒（标题/轴标签/刻度标签/注释/legend），喂 visual_qa.detect_geometry_issues 检测
   文本互相重叠、溢出画布（被裁）、对齐偏差。这层离线可跑、可 selftest。
2. **渲染回看协议（供 agent 执行）**：按 target_journal/column 真实栏宽渲染 PNG（复用
   figure_export.save_for_journal），连同 visual_qa_rubric() 打包成回看请求，交多模态 Opus
   逐维打分 + 列具体缺陷。无渲染器/未喂回模型时降级为仅几何检测，**明确标注"未做像素级回看"**
   （qa_report 的 pixel_review_done=False），绝不静默假成功。

结果写进 figure manifest 的 checks.visual 字段，被灵魂门 visual_honesty_gate 编排消费。出 light.visual_qa.v1。

⚠ 诚实边界：几何层抓"可计算的版面硬错"（重叠/溢出/错位）；像素级的对比度/可读性/审美须真喂回
  多模态模型才算验证，本脚本不替模型"看"，只负责把图渲染好、把检查请求结构化好。

用法（在 figure 绘图脚本里 import，或命令行驱动）：
  from figure_visual_qa import run_geometry_qa, render_for_review, build_review_request
  python figure_visual_qa.py --selftest        # 离线自测（几何检测 + 渲染 + 清理）
"""

from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)  # figure_export 同目录

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,
# 治 v1 硬编码 `../../_shared` 之脆(v2 _shared 在仓库根、嵌套深度已变)。
# 本脚本是 _shared/visual_qa 的正当消费者:抽 matplotlib AABB 喂其几何引擎,**不重造检测**。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.visual_qa import (
        detect_geometry_issues,
        visual_qa_rubric,  # noqa: E402
        qa_report,
    )

    _HAS_VQA = True
except ImportError:
    _HAS_VQA = False

try:
    import matplotlib  # noqa: E402

    matplotlib.use("Agg")
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _e2e_selftest_dir() -> pathlib.Path:
    root = _ROOT / ".upgrade" / "_e2e"
    root.mkdir(parents=True, exist_ok=True)
    return root


def extract_aabbs(fig) -> tuple:
    """从 matplotlib figure 抽出文本/图例元素的 AABB（像素坐标，原点左上）+ 画布尺寸。

    只取文本类元素（标题/轴标签/刻度标签/注释/legend）做重叠/溢出检测——不取 axes 矩形
    （axes 本就包含自己的刻度标签，纳入会假阳）。返回 (shapes, (W,H))。
    """
    if not _HAS_MPL:
        raise RuntimeError(
            "matplotlib 不可用，无法从 figure 抽 AABB（传 shapes 走纯几何路径）"
        )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox = fig.get_window_extent(renderer)
    W, H = bbox.width, bbox.height

    shapes = []
    idx = [0]

    def _add(artist, kind, label):
        try:
            if not artist.get_visible():
                return
        except Exception:
            pass
        try:
            ext = artist.get_window_extent(renderer)
        except Exception:
            return
        if ext.width <= 0 or ext.height <= 0:
            return
        # display 坐标原点在左下；转左上：y_top = H - ext.y1
        shapes.append(
            {
                "id": f"{kind}{idx[0]}",
                "kind": kind,
                "text": label,
                "x": float(ext.x0),
                "y": float(H - ext.y1),
                "w": float(ext.width),
                "h": float(ext.height),
            }
        )
        idx[0] += 1

    for ax in fig.axes:
        if ax.get_title():
            _add(ax.title, "title", ax.get_title())
        if ax.xaxis.label.get_text():
            _add(ax.xaxis.label, "xlabel", ax.xaxis.label.get_text())
        if ax.yaxis.label.get_text():
            _add(ax.yaxis.label, "ylabel", ax.yaxis.label.get_text())
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            if t.get_text():
                _add(t, "tick", t.get_text())
        for t in ax.texts:
            if t.get_text():
                _add(t, "annot", t.get_text())
        leg = ax.get_legend()
        if leg is not None:
            _add(leg, "legend", "legend")
    for t in fig.texts:
        if t.get_text():
            _add(t, "figtext", t.get_text())
    return shapes, (W, H)


def run_geometry_qa(fig=None, shapes=None, canvas_wh=None, vlm_findings=None) -> dict:
    """跑几何检测（从 fig 抽 AABB 或直接收 shapes）+ 合并 VLM 回看 → light.visual_qa.v1。"""
    if not _HAS_VQA:
        return {
            "schema": "light.visual_qa.v1",
            "verdict": "skip",
            "error": "_shared/visual_qa 不可用，无法做几何检测",
        }
    if shapes is None:
        if fig is None:
            raise ValueError("须传 fig 或 shapes 之一")
        shapes, canvas_wh = extract_aabbs(fig)
    geom = detect_geometry_issues(shapes, canvas_wh)
    # 降噪：同轴刻度标签本就该共享基线(x 刻度同 y、y 刻度同 x)，它们之间的 misalignment
    # 是"有意对齐"非缺陷，过滤掉避免淹没真问题；重叠/溢出/跨类错位仍保留。
    kind = {s.get("id"): s.get("kind") for s in shapes}
    geom = [
        g
        for g in geom
        if not (
            g.get("type") == "misalignment"
            and all(kind.get(e) == "tick" for e in g.get("elements", []))
        )
    ]
    rep = qa_report(geom, vlm_findings=vlm_findings)
    rep["n_elements"] = len(shapes)
    return rep


def render_for_review(
    fig, out_basename, journal="nature", column="single", custom_width_mm=None
) -> dict:
    """按目标刊真实栏宽渲染 PNG，供回看。返回 {png, info}。复用 figure_export.save_for_journal。"""
    if not _HAS_MPL:
        raise RuntimeError("matplotlib 不可用，无法渲染")
    import figure_export as fe  # 同目录

    written, info = fe.save_for_journal(
        fig,
        out_basename,
        journal=journal,
        column=column,
        formats=("png",),
        custom_width_mm=custom_width_mm,
    )
    png = next((p for p in written if str(p).lower().endswith(".png")), None)
    return {"png": str(png) if png else None, "info": info}


def build_review_request(png_path: str, journal: str = "", column: str = "") -> dict:
    """打包"渲染回看"请求：PNG + rubric + 指令，交多模态 Opus 逐维打分列缺陷。

    这是 render_then_review 协议的 (b) 步——脚本本身不"看"图，负责把请求结构化好；
    agent 拿到后须把 png 连同 rubric 喂回多模态 Opus，再把返回的 issues 作 vlm_findings
    回灌 run_geometry_qa()，得到含像素级回看的完整 light.visual_qa.v1。
    """
    return {
        "task": "figure_visual_review",
        "png": png_path,
        "render_spec": {"journal": journal, "column": column},
        "rubric": visual_qa_rubric() if _HAS_VQA else None,
        "instruction": (
            "按上面真实栏宽渲染图，逐维打分(1-5)并列出具体缺陷：标签是否重叠/被裁、"
            "图例是否压住数据、刻度文字是否挤、子图是否对齐、缩印到该栏宽后是否仍可读。"
            "每条缺陷含 type(overlap/clipped/illegible/misaligned/low_contrast)、"
            "loc、severity(critical/important/minor)。把返回的 issues 作 vlm_findings 回灌。"
        ),
        "note": "未喂回多模态模型前，视觉品味/对比度/可读性未经验证（仅几何层已查）。",
    }


def _selftest() -> int:
    print("### figure_visual_qa 离线自测", file=sys.stderr)
    assert _HAS_VQA, "visual_qa 契约不可用"

    # --- 纯几何路径（不依赖 matplotlib）：溢出画布应被检出 ---
    overflow_shapes = [{"id": "T1", "x": 80, "y": 80, "w": 40, "h": 40}]  # 超右下
    rep_of = run_geometry_qa(shapes=overflow_shapes, canvas_wh=(100, 100))
    assert rep_of["verdict"] == "fail", rep_of
    assert any(i["type"] == "overflow_canvas" for i in rep_of["issues"]), rep_of[
        "issues"
    ]
    # 未喂回模型 → 诚实标注未做像素回看
    assert rep_of["pixel_review_done"] is False and rep_of["pixel_review_note"], rep_of
    print("[1] 纯几何:溢出检出+诚实标注未像素回看 ... OK", file=sys.stderr)

    # --- VLM 回灌：把多模态返回的 issues 作 vlm_findings 合并 ---
    rep_vlm = run_geometry_qa(
        shapes=[{"id": "ok", "x": 10, "y": 10, "w": 20, "h": 20}],
        canvas_wh=(100, 100),
        vlm_findings=[
            {
                "type": "low_contrast",
                "severity": "important",
                "loc": "图例",
                "issue": "图例文字对比不足",
            }
        ],
    )
    assert rep_vlm["pixel_review_done"] is True and rep_vlm["verdict"] == "warn", (
        rep_vlm
    )
    print("[2] VLM 回灌:像素回看标记+verdict合并 ... OK", file=sys.stderr)

    # --- build_review_request 结构 ---
    req = build_review_request("/x/fig.png", "nature", "single")
    assert req["png"] == "/x/fig.png" and req["rubric"] and "instruction" in req, req
    print("[3] 回看请求打包(png+rubric+指令) ... OK", file=sys.stderr)

    # --- matplotlib 路径：抽 AABB + 渲染（写临时目录，跑完清理，零 git 残留）---
    if _HAS_MPL:
        import matplotlib.pyplot as plt
        import tempfile
        import shutil

        # 故意制造两个大字号文本重叠
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])
        ax.text(0.5, 0.5, "AAAAAA", fontsize=44, transform=ax.transAxes)
        ax.text(0.5, 0.5, "BBBBBB", fontsize=44, transform=ax.transAxes)  # 与上重叠
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        shapes, cwh = extract_aabbs(fig)
        rep_geom = run_geometry_qa(fig=fig)
        print(
            f"[mpl] 抽出 {len(shapes)} 元素, issues={[i['type'] for i in rep_geom['issues']]}",
            file=sys.stderr,
        )
        assert len(shapes) >= 3, shapes  # 至少 xlabel/ylabel + 两注释 + 刻度
        assert any(i["type"] == "overlap" for i in rep_geom["issues"]), rep_geom[
            "issues"
        ]
        # 渲染到仓库 .upgrade/_e2e 临时目录（gitignored），用完删
        tmp = tempfile.mkdtemp(prefix="light_vqa_", dir=str(_e2e_selftest_dir()))
        try:
            out = render_for_review(
                fig, os.path.join(tmp, "fig"), journal="nature", column="single"
            )
            assert out["png"] and os.path.exists(out["png"]), out
            assert out["info"]["width_mm"] == 89, out["info"]  # nature single=89mm
            print(
                f"[4] 抽AABB检出重叠 + 渲染{out['info']['width_mm']}mm PNG ... OK",
                file=sys.stderr,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            plt.close(fig)
        # 干净图不应误报重叠
        fig2, ax2 = plt.subplots(figsize=(4, 3))
        ax2.plot([0, 1, 2], [1, 3, 2])
        ax2.set_xlabel("time")
        ax2.set_ylabel("value")
        rep_clean = run_geometry_qa(fig=fig2)
        assert not any(i["type"] == "overlap" for i in rep_clean["issues"]), rep_clean[
            "issues"
        ]
        plt.close(fig2)
        print("[5] 干净图无重叠误报 ... OK", file=sys.stderr)
    else:
        print(
            "[4-5] matplotlib 不可用，跳过渲染/抽AABB测试（已诚实标注）",
            file=sys.stderr,
        )

    print("[selftest] PASS figure_visual_qa offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="渲染后视觉 QA 回看闭环（挂 _shared/visual_qa）"
    )
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument(
        "--shapes", help="JSON: {shapes:[{id,x,y,w,h}], canvas_wh:[W,H]} 纯几何检测"
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.selftest or not args.shapes:
        return _selftest()
    with open(args.shapes, encoding="utf-8") as f:
        d = json.load(f)
    rep = run_geometry_qa(
        shapes=d["shapes"], canvas_wh=tuple(d.get("canvas_wh", [0, 0]))
    )
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 1 if rep.get("verdict") == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
