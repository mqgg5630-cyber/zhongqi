# zhongqi —— 中期报告与答辩 PPT

> **本版已按导师意见重写**：不展开技术细节，只讲**研究思路**与**工作完成到哪一步**；
> 三模型（Attention / LSTM / BERT）共识预测按"已完成"呈现；分析完抗菌肽差异后用**宏蛋白组二次去重**，
> 筛选**健康人与各阶段特有的抗菌肽**，再与 **AD 发病机制**（Aβ 聚集 / AChE-PAS / 免疫炎症）建立关联，
> 并补一个**极简抑菌实验**（纸片扩散法 → MIC）作为验证。

**已交付**（可直接下载使用）：

| 文件 | 说明 |
|---|---|
| `deliverable/中期答辩.pptx` | **16 页中期答辩 PPT（A 版·学术蓝）**，16:9，全篇最小字号 **15 pt**（含图内文字按投影缩放核算） |
| `deliverable/versions/中期答辩_B_极简线框.pptx` | **另两版可编辑 PPT（B 版）**：白底细线风格，投影最干净，推荐首选 |
| `deliverable/versions/中期答辩_C_卡片色块.pptx` | **另两版可编辑 PPT（C 版）**：顶部色带 + 左侧竖条 + 卡片色块，设计感更强 |
| `docs/ppt_outline.json` | **PPT 大纲（机器可读）**：16 页逐页标题/正文/卡片/结论条/演讲备注/配图，换任何 PPT skill 都能直接喂 |
| `docs/PPT大纲.md` | **PPT 大纲（人读版）**，由上面那份 JSON 自动生成，含配色字号规范与现成提示词 |
| `docs/PPT生成Skill选择.md` | **两个高 star PPT skill 推荐**（ppt-master 54.1k★ / presenton 10.2k★）：安装、用法、怎么配合本大纲 |
| `deliverable/中期.docx` | **填好的中期检查表**，在学校空白模板上就地填写，格式与模板完全一致（已脚本校验） |
| `deliverable/中期检查表_填写内容.md` | 报告正文草稿（纯文本，最方便改；改完一键重生成 docx） |
| `results/ppt_preview/预览_第*-*页.png` | A 版 4 张版式预览图；`B版_*` / `C版_*` 为另两版预览，不用装 Office 也能核对 |
| `results/figures/figA—figG*.png` | 本版 7 张流程示意图（研究思路、三模型预测、分阶段差异、宏蛋白组去重、机制关联、抑菌实验、进度） |
| `docs/中期答辩PPT大纲.md` | **导师意见逐条落实对照表** + 逐页清单 + 7 个答辩预判问答 |

> 需要你补充：中期检查表封面（姓名、学号、研究生类型、培养单位、学科专业、研究方向、指导教师）与 PPT 封面的【姓名】【学号】【导师】。
> 填表说明要求"除签名外需打印填写"，因此未代填。

---

## 〇、三版 PPT 与通用大纲（每次都会同步）

- **三版可编辑 PPT**：A 版 `deliverable/中期答辩.pptx`（学术蓝）、B 版 `deliverable/versions/中期答辩_B_极简线框.pptx`、
  C 版 `deliverable/versions/中期答辩_C_卡片色块.pptx`。三版**内容完全一致**，都是**原生形状+文本框**（可直接改字改色、不是图片），
  全篇最小 **15 pt**，且**每页都写入了演讲备注**（口播稿）。挑一个用即可，改法见 `deliverable/versions/README.md`。
- **每次都附一份大纲**：`docs/ppt_outline.json`（机器可读，16 页逐页要素）+ `docs/PPT大纲.md`（人读版，含配色字号规范与提示词模板）。
  若想换工具重做，把这两个文件加 `results/figures/` 交给对方即可。
- **两个高 star PPT skill 推荐**：`docs/PPT生成Skill选择.md` ——
  [ppt-master](https://github.com/hugohe3/ppt-master)（54.1k★，MIT，原生 DrawingML，跑在 AI IDE 里，可给现成 pptx 填内容）
  与 [presenton](https://github.com/presenton/presenton)（10.2k★，Apache-2.0，自托管服务 + API/MCP，导出可编辑 PPTX）。

---

## 一、报告是怎么"填"的（格式为什么保证不变）

1. 解析你的模板：`code/inspect_docx.py` 读出每个段落的样式、字体（含中文 eastAsia 字体）、字号、缩进、
   行距，以及两张表格的每一格内容，并识别出模板里的 **Word 表单域（FORMTEXT）**空白处。
2. 只做两类写操作：往**原有段落**写文字（继承该段落的缩进与行距）、按模板段落**深拷贝**出新的正文段落
   （继承宋体 12 pt、首行缩进 3 字符、1.15 倍行距）。表格的框线、列宽、页面设置、页眉页脚一个字节都没动。
3. 写完后自动校验：`code/verify_docx.py` 对比模板与成品 → 页面设置/页眉页脚一致、
   表格属性与 tblGrid 一致、**54 个非目标单元格逐字节一致**、5 个填写区域的提示语保留且段落格式/字体格式一致。
   最终输出 `RESULT: template format fully preserved`。

文档结构与我填写的位置：

| 模板栏目 | 是否已填 | 依据 |
|---|---|---|
| 论文题目（表 2 第 1 行右侧） | ✅ | 开题报告题目 |
| 1. 论文研究主要内容及工作进度 | ✅ 17 段 | 开题报告 r8 + 已完成1.docx（研究背景/4 项研究内容/8 项进度） |
| 2. 阶段性成果 | ✅ 8 段 | 已完成1.docx（数据资源、方法学、阴性结果、成果形式） |
| 3. 公开发表学术论文情况 | ✅ 1 段 | 暂无发表，写明投稿计划 |
| 4. 尚需完成的研究工作（包括内容、方案） | ✅ 16 段 | 开题模型的承诺参数 + 已完成工作的现状推演 |
| Ⅱ / Ⅲ 导师与评议部分 | ⬜ 留空 | 由导师与检查小组填写 |
| 封面信息栏 | ⬜ 留空 | 需手工填写（见上文说明） |

## 二、PPT 是怎么做的

- 16 页，逐页大纲与**答辩预判问题应答要点**见 `docs/中期答辩PPT大纲.md`；通用大纲见 `docs/PPT大纲.md` / `docs/ppt_outline.json`。
- **A / B / C 三版**分别由 `code/make_ppt2.py` 与 `code/make_ppt_variants.py` 生成（B、C 共用一个风格表 `STYLES`，改色改版式只需改几行）。
- 中文字体统一**微软雅黑**，并在 XML 中显式写入东亚字体类型，避免在别人电脑上字体回退。
- 三重自检（脚本可复跑）：
  - `code/make_figures.py`：检查图内文字是否越出方框、并折算"图片缩放到幻灯片后的最小有效字号"（8 张图 15.0—18.4 pt）；
  - `code/make_ppt.py`：逐条检查 run 字号 ≥15 pt、形状不越界、文字不压图；
  - `code/check_ppt.py`：用真实中文字体估算换行高度，独立复核无溢出。

## 三、数据口径（每个数字都能溯源）

`docs/数据台账.md` 逐条列出报告与 PPT 中每个数字的来源，例如：

- 476 例样本 / 22 582 个 MAGs / 757 个 MIMAG 高质量基因组 / 1 971 个种水平代表基因组 → 已完成1.docx
- 2.19 亿条原始 sORF → 9 139.2 万条非冗余多肽 → 已完成1.docx
- 四个队列 12 项检验 P = 0.4291—0.9786 → 已完成1.docx 表 2
- 1 085 条正样本 / 58 776 条负样本、AdamW + Focal Loss → 开题报告 4.1.1 / 3.4.2

## 四、与开题的对应关系（防止口径打架）

`docs/开题要点.md` 把开题报告逐节提炼成表格，并列出"中期 vs 开题"的逐条对照，其中一处**需要你在答辩时口头说明**：
开题计划按"轻度认知障碍 → 早期 AD → 中期 AD → 晚期 AD"分 4 阶段，实际执行改为 **NC / SCS / SCD / MCI / AD 五阶段 + 性别 × 年龄分层匹配**，
属于方法细化（多为排除增龄效应与样本量不均衡），建议答辩时说一句"依据实际队列诊断标签进一步细化分层"。

---

## 五、协作方式（拉取 / 上传）

```powershell
# ① 拿我推送的最新成果
cd E:\0zhongqi\zhongqi
.\sync.ps1

# ② 把你的新文件（结果表、PPT、图）传上来
.\upload.ps1
```

`upload.ps1` 会自动在仓库旁找到附件目录，按扩展名归位（docx/pptx/pdf/md → `sources\`，py → `code\`，xlsx/csv → `results\`）后提交推送。
首次 push 会弹 GitHub 登录窗；若提示要输**密码**，那里应填 token，或改用 GitHub Desktop 点 Push，亦可直接在 Arena 里把文件作为附件发我。

不用脚本时的等价命令：

```powershell
git fetch origin; git checkout arena/01a09d79-zhongqi; git pull --ff-only origin arena/01a09d79-zhongqi
git add -A; git commit -m "加入本地文件"; git push origin arena/01a09d79-zhongqi
```

> ⚠️ 不要 `git init` 新仓库再推这个分支：历史对不上会被拒绝；强推（`--force`）会把远端内容整支覆盖。

## 六、目录说明

```
zhongqi\
├── deliverable\            成品：中期.docx、中期答辩.pptx（A 版）、正文草稿 md
│   └── versions\           另两版可编辑 PPT（B 极简线框 / C 卡片色块）
├── sources\                你的原件：开题.docx、中期.docx（模板）、已完成1.docx、1.md
├── code\                   脚本：填表/校验/画图/出 PPT/版式检查（详见 code\README.md）
├── results\figures\        8 张插图；results\ppt_preview\ PPT 版式预览图
├── docs\                   开题要点、数据台账、PPT 大纲（json+md）、PPT skill 推荐、模板结构解析（docs\_template\）
├── sync.ps1 / upload.ps1 / push.ps1   一键拉取 / 上传 / 推送
└── build\                  中间产物（可重新生成，已 gitignore）
```

## 七、报告中待你补充的信息

| 位置 | 需要的信息 |
|---|---|
| 中期检查表封面、PPT 封面第 16 页 | 姓名、学号、研究生类型、培养单位、学科专业、研究方向、指导教师 |
| 第 2 节"阶段性成果（四）" | 是否有已投稿/在审论文（期刊、状态） |
| 第 1 节进度 | 整体进度百分比（当前写 65%）与模型完成度（当前写 35%）是否符合实际 |
| 若要在报告中写临床评分 | MMSE / MoCA 的组间分布数据（当前未写） |
