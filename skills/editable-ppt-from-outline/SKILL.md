---
name: editable-ppt-from-outline
description: 用一份 JSON 大纲批量生成「原生可编辑」的 PowerPoint（多套风格可选），并自动校验最小字号与版式。When the user wants editable .pptx decks from a structured outline, multiple style variants of the same deck, speaker notes in every slide, or a slide-level outline that other PPT tools (ppt-master / presenton) can consume, use this skill.
---

# 可编辑 PPT 流水线（JSON 大纲 → 多版 pptx）

## 这个 skill 解决什么

- 一份大纲，生成**任意多套风格**的 PPT，内容完全一致，只是版式/配色不同，方便挑一版；
- 输出**原生形状 + 文本框**（不是图片化），拿到后可以直接在 PowerPoint/WPS 里改字、改色、挪框；
- 硬性质量门：**全篇最小字号 ≥ 15 pt**、形状不越界、文字不压图、每页写入**演讲备注**；
- 同一份 JSON 还能导出**人读版大纲**，直接喂给 ppt-master / presenton 之类的工具重做。

## 目录与文件

| 文件 | 作用 |
|---|---|
| `docs/ppt_outline.json` | **唯一内容源**：meta + 逐页要素（含演讲备注） |
| `docs/PPT大纲.md` | 由 JSON 生成的人读版大纲（含配色规范和现成提示词） |
| `code/make_ppt2.py` | 生成 **A 版**（学术蓝）→ `deliverable/中期答辩_A_学术蓝.pptx` |
| `code/make_ppt_variants.py` | 生成 **B / C / D / E 四版**（极简线框 · 卡片色块 · 双栏杂志风 · 深色标题区）→ `deliverable/中期答辩_{B..E}_*.pptx` |
| `code/outline_to_md.py` | JSON → 人读版大纲 |
| `code/add_notes.py` | 把大纲里的 `note` 写进任意 pptx 的备注区（按页序） |
| `code/check_ppt.py` | 独立校验：最小字号 / 越界 / 图文重叠 |
| `code/preview_ppt.py` | 无 Office 环境下逐页导出 PNG，用于核版式 |
| `code/get_cjk_font.py` | 从 PyPI 取思源黑体（供 matplotlib / PIL 用） |

新项目里建议保持同样的相对路径：`code/` 放脚本、`docs/` 放 JSON、`results/figures/` 放插图。

## 大纲 JSON 结构

```jsonc
{
  "meta": {
    "title": "标题第一行", "title_line2": "标题第二行（可选）",
    "kind": "研究生论文中期检查答辩",
    "presenter": "姓名　　学号：xxxxxxxx",
    "advisor": "指导教师：xxx　　培养单位：xxx",
    "major": "学科专业：xxx",            // 可选，封面第三行
    "date": "2026 年 9 月",
    "ratio": "16:9", "font_cn": "微软雅黑", "font_en": "Arial",
    "min_font_pt": 15,
    "style_note": "内容口径说明（给大纲读者看）",
    "footer": "页脚文字",
    "figures_dir": "results/figures"
  },
  "slides": [ /* 见下 */ ]
}
```

每页按 `type` 决定版式，字段如下：

| type | 必填 | 可选 |
|---|---|---|
| `title` | `title`,`title2` | `eyebrow`,`note` |
| `toc` | `title`,`items[]` | `takeaway`,`note` |
| `figure` | `title`,`figure` | `subtitle`,`body`,`takeaway`,`note` |
| `bullets` | `title`,`bullets[]` | `subtitle`,`callout{label,text}`,`takeaway`,`note` |
| `cards` | `title`,`cards[[标签,说明,tone]]` | `subtitle`,`bullets[]`,`takeaway`,`note` |
| `cards_problems` | `title`,`cards_problems[[标签,问题,对策]]` | `subtitle`,`takeaway`,`note` |
| `steps` | `title`,`steps[[标签,说明]]` | `subtitle`,`takeaway`,`note` |
| `end` | `title` | `title2`,`note` |

约定：
- `bullets` 里用**全角空格** `　` 分隔"小标签 + 正文"，标签会自动加粗着色（例：`"背景　AD 的发生发展与……"`）；
- `figure` 只写**文件名**（如 `figA_研究思路总览.png`），脚本到 `meta.figures_dir` 下找图并按页面宽度等比缩放；
- `note` 是**演讲备注（口播稿）**，会写进 PowerPoint 的备注区；
- 页码/页脚由脚本统一加，不要写进 JSON。

## 标准流程

```bash
# 1) 改内容：只改 docs/ppt_outline.json
# 2) 生成人读版大纲（给别的工具/人看）
python code/outline_to_md.py
# 3) 出 PPT：A 版 + B/C/D/E 四版
python code/make_ppt2.py
python code/make_ppt_variants.py            # 或 --style D 只出一版；--style all 出四版
# 4) 补/更新演讲备注（A 版由 make_ppt2 出图后执行一次即可）
python code/add_notes.py "deliverable/中期答辩_A_学术蓝.pptx"
# 5) 质量门：必须全绿
python code/check_ppt.py "deliverable/中期答辩_A_学术蓝.pptx"
python code/check_ppt.py "deliverable/中期答辩_B_极简线框.pptx"
# 6) 目视核对（无需 Office）：4 页一张联系图
python code/preview_ppt.py "deliverable/中期答辩_A_学术蓝.pptx" -o build/prevA
```

`make_ppt2.py` / `make_ppt_variants.py` 自己也会打印 `slides / runs / smallest font` 并做一遍自检；`check_ppt.py` 是**独立**复查（用真实中文字体估算换行高度），两者都要过。

## 换风格、换配色

- B / C / D / E 四版共用 `code/make_ppt_variants.py` 顶部的 `STYLES` 字典：
  `accent` 主色、`accent2` 强调色、`card_fill` 卡片底色、`card_line` 描边、`card_bar` 卡片左侧色条、
  `header_style`（`rule` 短下划线 / `band` 浅色标题带 / `plain` 细分隔线 + 右上角页码 / `darkband` 深色标题带）、
  `takeaway_style`（`rule` 左侧竖线 / `band` 浅底结论条 / `line` 方形点 + 细线 / `dark` 深色结论条）、
  `body_style`（`auto` 单栏 / `twocol` 双栏，见 `bullets_two_col()` 与 `cards_row()`）；
- 想再加一版：在 `STYLES` 里加一个键（如 `"F"`），运行 `python code/make_ppt_variants.py --style F`；
- 字体、页边距、标题位置等常量集中在 `code/make_ppt.py` 顶部（`MARGIN`、`CONTENT_W`、`TITLE_TOP`、`CONTENT_TOP`、`TAKEAWAY_TOP`、`FOOTER_TOP`）。

## 质量门（出稿前逐条确认）

1. `check_ppt.py` 输出 `RESULT: OK`；最小字号 ≥ `meta.min_font_pt`；
2. 图片按宽度缩放后，**图内最小字号折算到幻灯片上仍 ≥ 15 pt**（画图脚本 `make_figures2.py` 会打印这个折算值）；
3. 每页都有演讲备注（`add_notes.py` 会报"写入 N 页"）；
4. 预览图上确认：标题不换行挤、卡片文字不出框、结论条不被遮挡。

## 常见问题

| 现象 | 处理 |
|---|---|
| `check_ppt.py` 报某页字号 < 15 pt | 调小该页正文条数，或把内容拆到两页；不要靠缩小字号解决 |
| 文字压到图片 | `place_figure()` 传 `max_h`/`left`，或把整页改成 `figure` 版式（图居中 + 下方 2 行说明） |
| 卡片/结论条文字溢出 | 缩短文案；`make_ppt_variants.py` 的卡片高度按行数固定，超过 2 行需改 `card_h` |
| 中文字体在别人电脑上变了 | 脚本已把 `a:ea`/`a:cs` 显式写进 XML（微软雅黑 + Arial）；换字体请同时改 `FONT_CN`/`FONT_EN` |
| 换 JSON 后 B—E 版没变 | 四版都是从 JSON 现读现画，重跑 `make_ppt_variants.py` 即可；**A 版内容写死在 `make_ppt2.py`，改文字要同步改脚本** |
| 想用别的工具重做 | 把 `docs/PPT大纲.md`（或 `ppt_outline.json`）连同 `results/figures/` 给 ppt-master / presenton，提示词模板见 `docs/PPT生成Skill选择.md` |
