#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""outline_to_md.py - docs/ppt_outline.json -> docs/PPT大纲.md

The JSON is the single source of truth for the deck content: this script turns it
into a human-readable outline that can be pasted into any other PPT tool
(ppt-master / Presenton / PptxGenJS skill / 手工排版), and the same JSON drives
code/make_ppt_variants.py.

Usage: python code/outline_to_md.py
"""

from __future__ import annotations

import json
from pathlib import Path

SRC = Path("docs/ppt_outline.json")
DST = Path("docs/PPT大纲.md")

TYPE_LABEL = {
    "title": "封面",
    "toc": "目录",
    "bullets": "要点页",
    "cards": "卡片页",
    "figure": "图示页",
    "steps": "步骤/对照页",
    "end": "结束页",
}

LAYOUT_HINT = {
    "title": "大标题 + 副标题居中，细横线分隔，下方两行汇报人信息",
    "toc": "左侧大号编号 01–06 + 右侧一行式标题；底部结论条",
    "bullets": "顶部标题；正文为带菱形标记的段落；可选右侧强调框（callout）",
    "cards": "左侧要点列表 + 右侧 4 张标签卡（大标签 + 说明），或 3 张问题卡上下排列",
    "figure": "顶部标题；整幅流程图居中；图下 2–3 行说明；底部结论条",
    "steps": "顶部标题；1–5 条编号步骤，每条含小标题 + 一句说明",
    "end": "大字致谢居中 + 汇报人信息",
}


KEY_LABEL = {"eyebrow": "页眉小字", "subtitle": "小标题"}


def block_lines(slide: dict) -> list[str]:
    out = []
    for key in ("eyebrow", "subtitle"):
        if slide.get(key):
            out.append(f"- **{KEY_LABEL[key]}**：{slide[key]}")
    if slide.get("title2"):
        out.append(f"- **副标题**：{slide['title2']}")
    for b in slide.get("bullets", []) or []:
        out.append(f"- 正文要点：{b}")
    for tag, text, *_ in slide.get("steps", []) or []:
        out.append(f"- 步骤：**{tag}** — {text}")
    for c in slide.get("cards", []) or []:
        out.append(f"- 标签卡：**{c[0]}**｜{c[1]}")
    for tag, prob, fix in slide.get("cards_problems", []) or []:
        out.append(f"- 问题卡：**{tag}｜{prob}** — {fix}")
    if slide.get("callout"):
        co = slide["callout"]
        out.append(f"- 强调框：**{co['label']}** — {co['text']}")
    if slide.get("body"):
        out.append(f"- 图下说明：{slide['body']}")
    if slide.get("figure"):
        out.append(f"- 配图：`results/figures/{slide['figure']}`（示意图，可直接替换）")
    if slide.get("takeaway"):
        out.append(f"- 底部结论条：**{slide['takeaway']}**")
    if slide.get("note"):
        out.append(f"- 演讲备注（口播稿）：{slide['note']}")
    return out


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    m = data["meta"]
    slides = data["slides"]

    L: list[str] = []
    L.append("# 中期答辩 PPT 大纲")
    L.append("")
    L.append("> 本文件由 `docs/ppt_outline.json` 自动生成（`python code/outline_to_md.py`）。")
    L.append("> JSON 是唯一的内容源：三版 PPT 与这份大纲都从它生成，改文字只需改 JSON。")
    L.append("")
    L.append("## 一、总览")
    L.append("")
    L.append("| 项目 | 内容 |")
    L.append("|---|---|")
    L.append(f"| 题目 | {m['title']} |")
    L.append(f"| 类型 | {m['kind']} |")
    L.append(f"| 页数 | {len(slides)} 页 |")
    L.append(f"| 版式比例 | {m['ratio']} |")
    L.append(f"| 中文字体 | {m['font_cn']}（西文 {m['font_en']}） |")
    L.append(f"| 最小字号 | {m['min_font_pt']} pt（含图内文字） |")
    L.append(f"| 汇报人 | {m['presenter']} |")
    L.append(f"| 指导教师 | {m['advisor']} |")
    L.append(f"| 汇报日期 | {m['date']} |")
    L.append(f"| 页脚 | {m['footer']} |")
    L.append("")
    L.append(f"**内容口径**：{m['style_note']}")
    L.append("")
    L.append("**配色与字号规范（三版通用）**")
    L.append("")
    L.append("| 用途 | 色值 | 字号 |")
    L.append("|---|---|---|")
    L.append("| 主色（标题、强调） | 深蓝 #12324F / #2F6FB0 | 标题 26–28 pt |")
    L.append("| 完成态 | 青绿 #2F9E8F（填充 #E8F6F1） | 正文 16–18 pt |")
    L.append("| 进行中/待办 | 橙 #E08A2E（填充 #FDF2E3） | 正文 16–18 pt |")
    L.append("| 说明文字 | 灰 #6B7C8C | ≥15 pt |")
    L.append("| 结论条 | 底 #ECF7F4 + 边 #2F9E8F | 17 pt 加粗 |")
    L.append("")
    L.append("## 二、逐页大纲")
    L.append("")
    for s in slides:
        L.append(f"### 第 {s['n']} 页　{s.get('title','')}"
                 + (f"　{s['title2']}" if s.get("title2") else ""))
        L.append("")
        L.append(f"类型：**{TYPE_LABEL.get(s['type'], s['type'])}**　版式：{LAYOUT_HINT.get(s['type'], '')}")
        L.append("")
        L.extend(block_lines(s))
        L.append("")
    L.append("## 三、配图清单")
    L.append("")
    L.append("| 文件 | 用途 | 页 |")
    L.append("|---|---|---|")
    for s in slides:
        if s.get("figure"):
            L.append(f"| `results/figures/{s['figure']}` | 示意图 | 第 {s['n']} 页 |")
    L.append("")
    L.append("> 配图由 `python code/make_figures2.py` 生成，可直接替换为你自己的图；")
    L.append("> 若替换，注意图片中最小字号在图缩小到幻灯片宽度后仍需 ≥15 pt。")
    L.append("")
    L.append("## 四、给其他 PPT 工具的提示词模板")
    L.append("")
    L.append("把下面这段连同本文件一起交给生成工具（ppt-master / Presenton / PptxGenJS skill 均可）：")
    L.append("")
    L.append("```text")
    L.append("请按 docs/ppt_outline.json（或 docs/PPT大纲.md）生成一份 16 页学术答辩 PPT，要求：")
    L.append("1. 16:9，中文字体微软雅黑、西文 Arial，全文最小字号不低于 15 pt；")
    L.append("2. 内容严格按大纲，不要自行增删要点，不要加入大纲之外的数字；")
    L.append("3. 每页保留大纲给出的「演讲备注」，写入 PowerPoint 的备注区；")
    L.append("4. 需要插入图片的页面，使用 results/figures/ 下同名 PNG，按页面宽度等比缩放居中；")
    L.append("5. 输出必须为原生可编辑的 .pptx（真实文本框与形状，不要图片化）；")
    L.append("6. 风格：学术简洁，主色深蓝 #12324F / #2F6FB0，完成态用青绿 #2F9E8F，进行中用橙 #E08A2E，底部结论条底色 #ECF7F4。")
    L.append("```")
    L.append("")
    DST.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DST} ({len(L)} lines, {len(slides)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
