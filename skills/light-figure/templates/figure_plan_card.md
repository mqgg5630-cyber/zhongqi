<!--
图表规划卡模板（单张图/表一张卡）。
用途：把"这张图讲什么故事、放哪节、绑哪条 claim"（叙事层）与"图型/尺寸/栏宽键/配色/无障碍"（规格层）一次定死，交绘制照卡执行。
两层设计：叙事层先定（为什么画）、规格层再定（怎么画对）。栏宽键取值与同技能 scripts/figure_export.py 的 JOURNAL_SPECS 唯一真相源对齐。
v2 增量：新增 claim_id（精确图↔claim 绑定，供 visual_honesty_gate 的"把不显著当主图"门精确匹配证据档；只写 claim 文本则降级为语义匹配）。
-->

# 图表规划卡 · {{figure_id}}

> 一张卡 = 一张图或表。上层叙事先定，下层规格再定；规格层缺 target_journal/column 时绘制会打回本环节补，不自行猜栏宽。

## 上层 · 叙事（这张图为什么存在）

| 字段 | 内容 |
|------|------|
| **figure_id** | `F#` 命名图、`T#` 命名表（与论文模板 `[图位 F1]`/`[表位 T1]` 占位对齐） |
| **claim_id** | 这张图支撑的 claim 在 result-analysis `evidence_strength.json` 里的 `claim_id`（精确绑定；留空则按"绑定 claim"文本语义匹配证据档） |
| **绑定 claim** | 这张图支撑论文的哪一条 claim（一条，写清）；删掉它论文会缺哪一块 |
| **讲什么故事** | 一句话：读者看完这张图应得到什么结论 |
| **放哪节** | 正文哪一节 / 附录 / graphical abstract；`where_to_place_in_paper` |
| **优先级** | 必做（支撑核心贡献）/ 可做（增强）/ 可删（冗余或弱）。⚠ **主图(必做)绑定的 claim 证据档须为 weak+；绑到 grade=none(不显著) = 把不显著当主图,会被 visual_honesty_gate 拦并回炉 9→7** |
| **组图归属** | 若属某组图，写明 panel 角色（overview / deviation / relationship），并说明本 panel 回答的**唯一科学问题**（遮住它会丢什么独有信息——防冗余检验） |

## 下层 · 规格（怎么把它画对）

| 字段 | 内容 |
|------|------|
| **figure_type** | 图型（用清晰唯一名，如 `跨数据集主结果对比(分组柱+误差棒)`；选型可借 `recommend_chart.py`） |
| **purpose** | 图的作用 |
| **data_required** | 需要哪些数据（数值来源 result-analysis 的 `claim_evidence_table.md`；不足回 result-analysis / data-engineering 取，**禁手填臆测**） |
| **layout** | 布局（单图 / GridSpec 几行几列 / 跨格） |
| **color_scheme** | 配色约束：离散用 Okabe-Ito（≤8 类）/ 连续用 viridis·cividis；同论文统一调色板；**忌 jet/rainbow**（非感知均匀+色盲不安全；`color_palettes.py` 取安全色） |
| **annotation_style** | 标注：panel 标号 a/b/c、**误差棒类型(SD/SEM/CI)+样本量 n**、显著性标记、单位入括号 |
| **caption_style** | caption 能否脱离正文独立读懂；统计标注与 result-analysis 口径一致 |
| **possible_code_tool** | 建议工具（matplotlib/seaborn/ggplot2/TikZ/Graphviz/Inkscape…）。**论文数据图一律程序化生成,绝不 AI 生图** |
| **replication_notes** | 复现要点（数据指针 + 随机种子 + 生成脚本路径） |
| **target_journal** | 目标期刊键，取 figure_export.py `JOURNAL_SPECS` 之一：`nature`/`science`/`cell`/`plos`/`ieee`/`elsevier`/`mdpi`；表外刊（如中文刊）填 `custom` 并补 `custom_width_mm`（数据须有来源：目标刊作者指南或实测，禁止臆测） |
| **column** | 栏宽档位，须为该刊在 `JOURNAL_SPECS` 实有的键：`single`/`double`/`full`(仅 science/mdpi)/`onehalf`(仅 plos/elsevier)；`custom` 时省略，以 `custom_width_mm` 为准 |
| **尺寸/格式** | 由 `target_journal`+`column` 锁定物理栏宽 mm、最小字号、首选格式；绘制时 `save_for_journal(fig, base, journal=target_journal, column=column)` |
| **caption_draft** | caption 初稿 |
| **output_formats** | 矢量(PDF/EPS/SVG) + 位图(TIFF/PNG)，按刊首选格式 |
| **source_card（必填）** | 图的数据/模式来源指针：数据来源如 `result-analysis:claim_evidence_table.md / Table 2`；图型若为复用模式可记其来源，全新模式标 `new_canonical_candidate` |

## 无障碍 / 投稿前自检（交卡前过一遍）

- [ ] 配色色盲安全：Okabe-Ito 或 viridis 系；颜色之外加冗余编码（线型/marker）；忌 jet/rainbow。
- [ ] 灰度可辨：黑白打印仍能区分各系列。
- [ ] 字号：最终印刷尺寸下达目标刊下限（缩放后仍 ≥ 下限，用 `check_scaled_fonts` 复核）。
- [ ] 坐标轴标签含单位；误差棒注明类型与 n；显著性标记齐全。
- [ ] 物理尺寸 = 目标栏宽（`check_figure_size` 复核，勿被 bbox tight 静默裁剪）。
- [ ] 去 chart junk；**不误导（y 轴不偷偷截断、慎用双 y 轴、不用 jet/rainbow）**——过 `visual_honesty_gate`。
- [ ] **主图绑定的 claim 证据档 weak+**（不把不显著结果当主图）。
- [ ] 组图：每个 panel 回答唯一科学问题，无冗余（过 `audit_figure_set`）。

---

**交接**：本卡交绘制执行——读 `source_card` 照卡画、读 `target_journal/column` 锁栏宽、导出后跑 `check_figure_size`/`check_scaled_fonts`，交付前过 `visual_honesty_gate`（截/双轴诚实 + 把不显著当主图）。项目级风格/图号/caption/导出路径登记到项目 `.light/` 的 figure manifest（memory-pm 归属）。
