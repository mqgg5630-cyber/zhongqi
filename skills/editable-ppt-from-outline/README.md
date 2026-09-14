# 可编辑 PPT 流水线（skill）——使用说明

> 这份 skill 把"这份中期答辩 PPT 是怎么做出来的"沉淀成**可复用的流程**：
> **一份 JSON 大纲 → 任意多套风格的原生可编辑 pptx → 自动校验字号与版式**。
> 以后做开题、预答辩、组会汇报、项目结题，改 JSON 就能重出，不必从零排版。

## 一、它包含什么

```
skills/editable-ppt-from-outline/
├── SKILL.md                 ← 给 AI 助手看的 skill 说明（结构、流程、质量门、常见问题）
├── README.md                ← 本文件：给人的使用说明
├── outline.template.json    ← 大纲 JSON 模板（3 页示例，照抄改成自己的内容）
└── scripts/install.ps1      ← 一键把脚本装到你自己的新项目里（Windows PowerShell）
```

真正的生成代码在仓库的 `code/` 下（skill 只负责说明与安装）：

| 脚本 | 作用 |
|---|---|
| `code/make_ppt2.py` | A 版（学术蓝） |
| `code/make_ppt_variants.py` | B 版（极简线框）/ C 版（卡片色块），`STYLES` 里改配色 |
| `code/outline_to_md.py` | JSON → 人读版大纲（含提示词模板） |
| `code/add_notes.py` | 大纲里的 `note` → PowerPoint 备注区（按页序） |
| `code/check_ppt.py` | 独立校验：最小字号 ≥ 15 pt、不越界、文字不压图 |
| `code/preview_ppt.py` | 没有 Office 也能导出逐页 PNG 核版式 |
| `code/get_cjk_font.py` | 取中文字体，供 matplotlib / PIL 用 |

## 二、怎么用

### 1. 在本仓库里（最简单）

```powershell
# 只改内容：编辑 docs/ppt_outline.json
python code/outline_to_md.py                     # 更新人读版大纲
python code/make_ppt2.py                         # 出 A 版
python code/make_ppt_variants.py                 # 出 B / C 版
python code/add_notes.py deliverable/中期答辩.pptx   # A 版补演讲备注
python code/check_ppt.py deliverable/中期答辩.pptx   # 质量门：必须 OK
```

### 2. 用在新项目里（复用）

```powershell
# 在仓库里执行：把脚本装到新项目目录（会自动建 code\ docs\ results\figures\ build\）
.\skills\editable-ppt-from-outline\scripts\install.ps1 -Target C:\MyNewProject

# 然后到新项目里：
cd C:\MyNewProject
pip install python-pptx matplotlib pillow fonttools noto-cjk-sans-otc
python code/get_cjk_font.py
python code/make_ppt_variants.py --style B
python code/check_ppt.py deliverable\*.pptx
```

装好以后，新项目里只做两件事：**写 `docs/ppt_outline.json`**、**把插图放进 `results/figures/`**。

### 3. 交给别的 AI 工具做（ppt-master / presenton）

把 `docs/PPT大纲.md`（人读版）或 `docs/ppt_outline.json`（机器版）连同 `results/figures/` 一起给对方，
提示词模板在 `docs/PPT生成Skill选择.md` 里，直接复制即可。出稿后用 `python code/check_ppt.py <文件>` 复核 15 pt 底线。

## 三、大纲 JSON 怎么写

见 `outline.template.json`；要点：

- `meta`：标题（可两行）、姓名/学号、导师/单位、日期、页脚、字体、`min_font_pt`；
- `slides[]`：每页一个对象，`type` 决定版式 —— `title`（封面）/ `toc`（目录）/ `figure`（配图页）/
  `bullets`（要点页）/ `cards`（卡片页）/ `cards_problems`（问题-对策）/ `steps`（步骤）/ `end`（致谢）；
- `note` 字段写**演讲备注**（口播稿），会进 PowerPoint 备注区；
- 正文里用**全角空格** `　` 分隔"小标签 + 正文"，生成时会自动把标签加粗着色。

## 四、质量门（每次出稿都要过）

1. `python code/check_ppt.py <文件>` 输出 `RESULT: OK`；
2. 全篇最小字号 ≥ 15 pt（自动核算，含图内文字折算）；
3. 每页都有演讲备注；
4. 预览图（`results/ppt_preview/*.png`）上目视确认不挤、不越界、不压图。

## 五、备注

- `code/make_ppt2.py`（A 版）的内容是**写死在脚本里的**，改文字要改脚本；B/C 版是从 JSON 现读现画，改 JSON 即可。
  以后新建的 deck 建议**只用 JSON 路线**（`make_ppt_variants.py`）。
- 出稿不需要 Office；只有在最后交付/演示时才用 PowerPoint 或 WPS 打开（`.pptx` 是原生格式，字体已显式指定）。
