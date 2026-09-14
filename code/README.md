# code —— 分析与会话工具脚本

## 交付物生成流水线（中期报告 + 答辩 PPT）

```
deliverable/中期检查表_填写内容.md          ← 正文草稿（可直接改这个文件）
        │  build_ops.py
        ▼
build/ops_中期.json                          ← 描述"往哪个单元格写哪些段落"
        │  fill_docx.py --ops
        ▼
deliverable/中期.docx                        ← 成品（学校模板格式零改动）
        │  verify_docx.py
        ▼
格式校验：页面设置 / 表格 / 提示语 / 字体字号是否与模板一致
```

```
docs/ppt_outline.json                        ← PPT 大纲（唯一内容源，16 页逐页要素 + 演讲备注）
        │  outline_to_md.py
        ▼
docs/PPT大纲.md                              ← 人读版大纲（含配色字号规范 + 提示词模板）
```

```
results/figures/*.png                        ← 由 make_figures2.py 生成（含字号自检）
        │  make_ppt2.py           → A 版 学术蓝        deliverable/中期答辩_A_学术蓝.pptx
        │  make_ppt_variants.py   → B/C/D/E 四种风格   deliverable/中期答辩_B..E_*.pptx
        │  make_ppt_svg.py        → F/G 两版（SVG 排版 + ppt-master 原生导出）
        ▼                              deliverable/中期答辩_F_深色科技风.pptx 等
七版原生可编辑 pptx（最小 15 pt，每页带演讲备注）
        │  check_ppt.py + preview_ppt.py
        ▼
版式校验 + 逐页 PNG 预览（build/ppt_preview、results/ppt_preview）
```

### 常用命令

```bash
python code/build_ops.py                 # 草稿 md -> ops json
python code/fill_docx.py --ops build/ops_中期.json      # 填表
python code/verify_docx.py --base sources/中期.docx --filled deliverable/中期.docx \
       --cells 22:0:3 22:2:0 22:3:0 22:4:0 22:5:0 \
       --tc-skip 22:0:1 22:2:0 22:3:0 22:4:0 22:5:0 \
       --sdt-cells 13:0:0 13:1:0 13:2:0 13:3:0 13:4:0 13:5:0 13:6:0   # 格式校验（含封面）
python code/make_figures2.py             # 画图（含框内文字溢出检查 + 投影字号核算）
python code/make_ppt.py                  # 出旧版（细节版）PPT（含字号/越界/图文重叠检查）
python code/make_ppt2.py                 # 出 A 版 PPT -> deliverable/中期答辩_A_学术蓝.pptx
python code/outline_to_md.py             # PPT 大纲 json -> docs/PPT大纲.md
python code/make_ppt_variants.py         # 出 B / C / D / E 四版 PPT -> deliverable/（--style D 只出一版）
python code/fetch_ppt_master.py          # 首次：下载 ppt-master 到 build/（约 125 MB，不入库）
python code/make_ppt_svg.py              # 出 F 深色科技风 / G 学术期刊风（SVG -> 原生 DrawingML）
python code/add_notes.py "deliverable/中期答辩_A_学术蓝.pptx"   # 给 A 版补演讲备注（大纲 -> 备注区）
python code/check_ppt.py "deliverable/中期答辩_B_白底细线.pptx" # 独立版式检查
python code/preview_ppt.py "deliverable/中期答辩_A_学术蓝.pptx" -o build/prevA
```

## 各脚本用途

| 脚本 | 作用 |
|---|---|
| `inspect_docx.py` | 解析 docx 结构：段落样式、字体（含东亚字体）、字号、缩进、表格逐格内容、Word 表单域，输出 txt + json |
| `fill_docx.py` | 就地填 docx：`replace_text` / `set_cell` / `fill_cell` / `fill_tc`（按原始行/格定位）/ `fill_sdt`（Word 内容控件，封面用）/ `insert_in_cell` / `set_paragraph` / `insert_after` / `insert_after_text` / `delete_paragraph`，全部基于模板原有段落格式 |
| `verify_docx.py` | 校验成品是否保持模板格式（页面设置、页眉页脚、表格属性、非目标单元格逐字节一致、目标单元格段落/字体格式一致）；新增 `--sdt-cells` / `--tc-cells` / `--tc-skip` 三个参数，覆盖封面内容控件与"整格重建"的正文格 |
| `build_ops.py` | 把 `deliverable/中期检查表_填写内容.md` 编译成 `fill_docx.py` 的 ops；`# 封面信息` 段 → 封面表（body 序号 13）7 栏，`## n.` 段 → 正文单元格 |
| `make_figures.py` | 生成 fig1—fig8（**细节版**，供学位论文用）；含折行与溢出测量工具函数；自检：文本是否超出方框、缩放到幻灯片后最小有效字号是否 ≥15 pt |
| `make_figures2.py` | 生成 figA—figG（**思路版**，中期答辩用：研究思路、三模型预测、分阶段差异、宏蛋白组去重、机制关联、抑菌实验验证、进度） |
| `make_ppt.py` | 生成第一版 16 页答辩 PPT（细节版）；自检：每个 run ≥15 pt、形状不越界、文字不压图 |
| `make_ppt2.py` | 生成 **A 版**答辩 PPT（按导师意见：只讲思路与完成度，三模型预测与宏蛋白组去重按已完成呈现） |
| `make_ppt_variants.py` | 由 `docs/ppt_outline.json` 生成 **B 白底细线 / C 卡片色块 / D 双栏杂志风 / E 深色标题区** 四版 PPT，可选 `--style D`；版式差异集中在文件顶部 `STYLES` 风格表（`header_style` / `takeaway_style` / `body_style`）与 `header()` / `takeaway()` / `bullets_two_col()` / `cards_row()` |
| `outline_to_md.py` | 把 `docs/ppt_outline.json` 转成 `docs/PPT大纲.md`（人读版 + 提示词模板），供 ppt-master / presenton 等工具使用 |
| `make_ppt_svg.py` | 把 `docs/ppt_outline.json` 渲染成 16 页 SVG（遵守 ppt-master 的 SVG 规范：绝对坐标、`fill="none"`、字号 ≥ 20 px），再调 ppt-master 的 `svg_to_pptx.py` 导出 **F 深色科技风 / G 学术期刊风** 两版原生 DrawingML pptx；风格表 `STYLES` 与版式函数（`cover()` / `figure_page()` / `toc_page()`…）都在文件里 |
| `fetch_ppt_master.py` | 按需下载 ppt-master（54k★，MIT）到 `build/ppt-master/` 供 `make_ppt_svg.py` 调用；不在仓库里存 125 MB 的第三方源码 |
| `add_notes.py` | 把大纲里的演讲备注（口播稿）按页序写进任意 pptx（A 版补备注即用它），七版备注口径一致 |
| `check_ppt.py` | 独立的 PPT 版式检查（用真实 CJK 字体估算换行高度） |
| `preview_ppt.py` | 无 PowerPoint 环境下的逐页 PNG 预览（用于核版式）；支持读取 `p:bg` 幻灯片背景色，深色版式不会预览成白底 |
| `get_cjk_font.py` | 从 PyPI 的 `noto-cjk-sans-otc` 抽出思源黑体 SC 单字体，供 matplotlib/PIL 使用 |
| `check_ps1.py` | 校验 .ps1 脚本为纯 ASCII（避免 Windows PowerShell 5.1 按 GBK 解码导致的解析错误） |
| `1.py` | 你的原始脚本：全队列 476 样本 MAGs 成果校验与统计（bash/SLURM 流程） |

## 依赖

```bash
pip install python-docx python-pptx matplotlib numpy pillow fonttools noto-cjk-sans-otc
python code/get_cjk_font.py     # 抽出 /tmp/fonts/NotoSansCJKsc-Regular.otf
```

## 注意

- `build/` 目录是中间产物（ops json、PPT 预览图），可随时重新生成，不纳入版本管理。
- 表格/文档中的中文数字使用半角空格分组（如 `22 582`），与已完成1.docx 的写法保持一致。
