# 八版答辩 PPT 怎么挑、怎么改

八版**文字内容与口径一致**（同一份 `docs/ppt_outline.json` + `docs/术语表.md`，16 页，含演讲备注），差别在版式、配色与叙事组织。
都是**原生可编辑 pptx**（真实形状 + 文本框 + 原生表格，不是图片），全篇最小字号 **15 pt**。

## 三组、八版

- **A—E**：同一套排版的换肤（python-pptx 直排）；
- **F / G**：换了一条生产线 —— 排版先用矢量（SVG）画好，再由
  [ppt-master](https://github.com/hugohe3/ppt-master)（54k★，MIT）的原生导出通路编译成 DrawingML；
- **H**：按 [nature-skills](https://github.com/mqgg5630-cyber/nature-skills) 的 `nature-paper2ppt`（Apache-2.0）
  重新组织内容与版式：论文汇报的叙事弧（概述 → 队列 → 流程 → 证据 → 验证与边界 → 总结）、
  结论式标题、图上字少、原生对照表、每页留足留白。

| 版本 | 文件 | 风格 | 适合场合 |
|---|---|---|---|
| **H nature 风** | `中期答辩_H_nature风.pptx` | 白底 + 期刊红细线 + 衬线感排版、原生对照表、留白多 | **论文汇报/答辩首选**：最像"学术报告"，评审看着最舒服 |
| **F 深色科技风** | `中期答辩_F_深色科技风.pptx` | 近黑底 + 青色强调 + 网格底纹 + 深色结论条 | **推荐首选**：大教室投影最抓眼，AI/组学主题很贴 |
| **G 学术期刊风** | `中期答辩_G_学术期刊风.pptx` | 白底纸面 + 期刊红 + 细线分隔 + 衬线标题 | **推荐次选**：稳妥、像论文抽印本，打印和评审都友好 |
| C 卡片色块 | `中期答辩_C_卡片色块.pptx` | 顶部色带 + 左侧竖条 + 卡片底色块 | 想要设计感、页面更饱满 |
| D 双栏杂志风 | `中期答辩_D_双栏杂志风.pptx` | 正文两栏 + 砖红编号 + 右上角页码 | 内容多、想要高信息密度 |
| A 学术蓝 | `中期答辩_A_学术蓝.pptx` | 深蓝 + 青绿标签块、圆角色块 | 最常见的"工作汇报"观感 |
| B 白底细线 | `中期答辩_B_白底细线.pptx` | 白底细线卡片、短下划线标题 | 投影仪偏亮、要打印纸质稿时最稳 |
| E 深色标题区 | `中期答辩_E_深色标题区.pptx` | 深色标题带 + 深色结论条 + 橙色强调 | 只要标题区强调、正文保持浅底 |

**一眼对比图**：`../results/ppt_preview/三版新风格对比_封面与第10页.png`（F / G / H）、
`../results/ppt_preview/四版主推对比_封面与第10页.png`（A / B / F / G）；
逐页预览：`../results/ppt_preview/A版_第1页起.png` … `G版_第13页起.png`，每版 4 张（每张 4 页）。

## 挑选建议

1. 学位论文中期/预答辩、正式评审场合 → **H nature 风**（最贴论文汇报的规范）。
2. 报告厅投影、老师坐得远、想有记忆点 → **F 深色科技风**。
3. 评审偏保守、或要交纸质稿 → **G 学术期刊风**。
4. 只想"不出错" → B（白底细线）或 A（学术蓝）。
5. 定下来后**只用一版**，别混着讲；八版内容口径完全一致，可随时换。

## 怎么改

| 需求 | A—E 版 | F / G 版 |
|---|---|---|
| 改几个字 | PowerPoint 里直接改文本框 | 同左（原生文本框，可改） |
| 改配色 | 改 `code/make_ppt_variants.py` 顶部 `STYLES[k]["accent"]` 等，重跑生成 | 改 `code/make_ppt_svg.py` 顶部 `STYLES[style]` 里的十六进制色，重跑生成 |
| 换字体 | 改 `code/make_ppt.py` 的 `CN_FONT` | 改 `code/make_ppt_svg.py` 的 `CN` / `SERIF` / `MONO` 常量 |
| 改内容 | 改 `docs/ppt_outline.json`（A—E 与 F/G 共用） | H 版内容写在 `code/make_ppt_nature.py` 的 `build()` 里，改字改这里 |
| 加减页 / 改顺序 | 改 `docs/ppt_outline.json`，重出 | 同左 |

重出命令（在仓库根目录）：

```powershell
python code/make_figures2.py                                   # 图（改了图内文字才需要）

# A—E 版（python-pptx 路线）
python code/make_ppt2.py                                       # A 版
python code/add_notes.py "deliverable/中期答辩_A_学术蓝.pptx"   # A 版补演讲备注
python code/make_ppt_variants.py                               # B / C / D / E

# F / G 版（SVG + ppt-master 原生导出路线）
python code/fetch_ppt_master.py                                # 首次：下载 ppt-master 到 build\（约 125 MB，不入库）
python code/make_ppt_svg.py                                    # 出 F / G；--style F 只出一版

# H 版（nature-skills 路线）
python code/fetch_nature_skills.py                             # 首次：下载 nature-skills 到 build\
python code/make_ppt_nature.py --audit                         # 出 H 版并跑 skill 自带审计

# 通用
python code/check_consistency.py                               # docx 与八版 PPT 口径核对
python code/check_ppt.py "deliverable/中期答辩_F_深色科技风.pptx"  # 版式自检（≥15 pt、不越界）
python code/preview_ppt.py "deliverable/中期答辩_F_深色科技风.pptx" -o build/prevF
```

## 内容口径（八版共用的硬约束）

- 全篇最小字号 **15 pt**（含图片缩放到页面后的折算字号）。
- 只讲**研究思路**与**完成到哪一步**，不展开技术细节（进度页保留百分比）。
- 抑菌实验统一表述为**"候选抗菌肽抑菌实验验证"**（纸片扩散法初筛 → 微量肉汤稀释法测 MIC，设阳性/阴性对照），
  **不使用"极简""最小工作量""最小可行性"等说法**。
- 用词以 `docs/术语表.md` 为准；跑 `python code/check_consistency.py` 可一次性核对 docx 与八版 PPT。
