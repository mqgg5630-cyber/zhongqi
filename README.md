# zhongqi —— 中期报告与答辩 PPT

> **本版内容口径**：不展开技术细节，只讲**研究思路**与**工作完成到哪一步**；
> 三模型（Attention / LSTM / BERT）共识预测按"已完成"呈现；分析完抗菌肽差异后用**宏蛋白组二次去重**，
> 筛出 **AD 特异性特有的抗菌肽**（AD 组有、对照组没有），再与 **AD 发病机制**（Aβ 聚集 / AChE-PAS / 免疫炎症）建立关联，
> 最后用**抑菌实验验证**（纸片扩散法初筛 → 微量肉汤稀释法测 MIC）对候选肽做活性验证。

**已交付**（可直接下载使用）：

| 文件 | 说明 |
|---|---|
| `deliverable/中期答辩_最终版.pptx` | **最终版（H 版·nature 风，24 页）**：18 页主体（含**宏基因组流程页**与**分阶段分组页**）+ 6 页机制补充页；与 `中期答辩_H_nature风.pptx` 同源同版式，改名只为好认 |
| `deliverable/中期答辩_H_nature风.pptx` | **24 页中期答辩 PPT（H 版·nature 风）**——按 [nature-skills](https://github.com/mqgg5630-cyber/nature-skills) 的 `nature-paper2ppt` 生成：论文汇报叙事弧、结论式标题、原生对照表、留白多；**论文汇报/答辩首选** |
| `deliverable/中期答辩_F_深色科技风.pptx` | **16 页中期答辩 PPT（F 版·深色科技风）**——近黑底 + 青色强调 + 网格底纹 + 深色结论条，**推荐首选**；由 ppt-master 原生导出（DrawingML） |
| `deliverable/中期答辩_G_学术期刊风.pptx` | **G 版·学术期刊风**——白底纸面 + 期刊红 + 细线分隔 + 衬线标题，**推荐次选**；同为 ppt-master 原生导出 |
| `deliverable/中期答辩_A_学术蓝.pptx` | A 版·学术蓝（深蓝 + 青绿标签块，常见工作汇报观感） |
| `deliverable/中期答辩_B_白底细线.pptx` | B 版·白底细线（白底细线卡片，投影与打印最稳） |
| `deliverable/中期答辩_C_卡片色块.pptx` | C 版·卡片色块（顶部色带 + 左侧竖条 + 卡片底色块） |
| `deliverable/中期答辩_D_双栏杂志风.pptx` | D 版·双栏杂志风（正文两栏 + 细分隔线 + 右上角页码） |
| `deliverable/中期答辩_E_深色标题区.pptx` | E 版·深色标题区（深色标题带 + 深色结论条） |
| `results/ppt_preview/三版新风格对比_封面与第10页.png` | **F / G / H 一眼对比图**（封面 + 第 10 页），不用装 Office 也能挑版本 |
| `results/qa/ppt_H_qa_report.md` | H 版的 QA 报告（生成状态 / 自检与修正 / 口径一致性核对，按 nature skill 要求填写） |
| `deliverable/PPT版本选择.md` | 八版怎么挑、怎么改（含换色/加减页、三条生产线的重出命令） |
| `results/docx_preview/完整版/page-10.png` | 签字页那一页的版面图（第 10 页；`完整版/全部页.png` 为 10 页全图） |
| `docs/ppt_outline.json` | **PPT 大纲（机器可读）**：16 页逐页标题/正文/卡片/结论条/演讲备注/配图，换任何 PPT skill 都能直接喂 |
| `docs/PPT大纲.md` | **PPT 大纲（人读版）**，由上面那份 JSON 自动生成，含配色字号规范与现成提示词 |
| `docs/PPT生成Skill选择.md` | **两个高 star PPT skill 推荐**（ppt-master 54.1k★ / presenton 10.2k★）：安装、用法、怎么配合本大纲 |
| `deliverable/中期.docx` | **填好的中期检查表**（含封面：文绍华 / 2024110316 / 生命科学学院 / 生物学 / 指导教师 申亮；含 Ⅱ.导师指导情况；检查小组成员已按学院给的名单填好：组长 李向阳（教授），组员 江婷婷（副教授）、孙杰（教授）、高洪伟（教授），专业均为生物化学与分子生物学，单位均为鲁东大学生命科学学院），在学校空白模板上就地填写，格式与模板完全一致（脚本逐格校验通过） |
| `deliverable/中期新.docx` | 同一内容的第二个文件名（"两版中期"用），与 `中期.docx` 由同一脚本生成、内容一致 |
| `deliverable/中期检查表_签字页.docx` | **只有签字页的一页文件**（Ⅲ.评议情况：检查小组成员 → 中期检查意见 → 是否同意参加预答辩 / 检查组长签字 / 培养单位盖章 2026年9月19日）：从填好的 `deliverable/中期.docx` 原样裁出，10 行逐行与整份表一致，A4 一页；明天打印这一页去签字（检查小组签字与单位盖章同页）；导师评语与导师签字在**上一页**，正文改完后把签好的这页直接替换 / 装订到最后 |
| `deliverable/抗菌肽与AD关联机制说明.docx` | **机制解释补充材料**（老师指出机制没说清后新增）：逐条回答 8 个问题 + **按致病方向**验证候选肽能否推动 AD（AChE–Aβ 分子动力学 + 交叉成核机制）+ 三个可检验假设 + 证据强度分级 + **60 条参考文献**；正文源 `docs/机制说明_正文.md`，由 `code/make_mech_doc.py` 生成 |
| `deliverable/中期答辩_最终版.pptx` | **最终版 PPT（H 版）**：3 张机制图、24 页（含流程页、分组页与 6 页机制页），与 `中期答辩_H_nature风.pptx` 同源同版式 |
| `中间版/` | **提交给老师用的中间版 1**：内容砍一半（docx 正文 52%、PPT 14 页 / 完整版 24 页），**进度口径同完整版**；文件名与完整版一致；完整版不放这里、也不改动 |
| `中间版2/` | **中间版 2（与中间版平行）**：内容同样减半，**进度也减半** —— 只把数据与预测（4/8）算作中期已完成，其余列入下一阶段计划 |
| `deliverable/中期检查表_填写内容.md` | 报告正文草稿（纯文本，最方便改；改完一键重生成 docx；正文约 8 000 字） |
| `results/ppt_preview/A版_*-*页.png` … `E版_*` | 五个版本各 4 张版式预览图（A/B/C/D/E），不用装 Office 也能核对 |
| `results/figures/figA—figG*.png` | 本版 7 张流程示意图（研究思路、三模型预测、分阶段差异、宏蛋白组去重、机制关联、抑菌实验、进度） |
| `docs/中期答辩PPT大纲.md` | **汇报重点与落实方式对照表** + 逐页清单 + 7 个答辩预判问答 |

> 封面信息已从 `sources/开题.docx`（封面表）读取并填入：**文绍华 / 2024110316 / 学术学位硕士研究生 / 生命科学学院 /
> 生物学 / 生物化学与分子生物学 / 指导教师 申亮** —— 中期检查表封面 7 栏 + 八版 PPT 封面全部同步填入，无占位符。
> 表中"除签名外需打印填写"指的是本表**用打印稿提交**，如学院要求手写，把封面 7 栏改成手写即可，正文内容不受影响。

---

## 本地同步（先看这一页）

**进文件夹 `E:\0zhongqi\zhongqi`（仓库根目录），双击 `sync.cmd` 就是一键同步。**
拿不准该用哪一个文件夹、交付物在哪，**双击 `where.cmd`**（列出本机所有克隆的路径 / 分支 / 下载目录）；如果这个文件夹已经被别的分支占了，**双击 `reclone.cmd`** 另拉一个干净文件夹
（默认 `..\zhongqi-arena`）即可，旧文件夹原样不动。
完整速查（含首次准备、下载交付物、故障对照）见 `docs/本地同步怎么用.md`，
脚本说明见 `skills/git-sync/README.md`。

## 〇、八版 PPT 与通用大纲（每次都会同步）

- **八版可编辑 PPT（都在 `deliverable\` 根目录，文件名以"中期答辩_"开头）**，分三条生产线：
  - **A—E 版**（学术蓝 / 白底细线 / 卡片色块 / 双栏杂志风 / 深色标题区）由 `code\make_ppt2.py`、`code\make_ppt_variants.py` 用 python-pptx 直接摆形状生成；
  - **F 深色科技风 / G 学术期刊风**由 `code\make_ppt_svg.py` 把每页写成 SVG，再经
    [ppt-master](https://github.com/hugohe3/ppt-master)（54k★，MIT，**已实际用于出稿**）的原生导出通路编译成 pptx ——
    版式与配色和 A—E 完全不同，是真正"换了风格"的两版；
  - **H nature 风**由 `code\make_ppt_nature.py` 按
    [nature-skills](https://github.com/mqgg5630-cyber/nature-skills) 的 `nature-paper2ppt`（Apache-2.0）生成：
    论文汇报叙事弧（概述 → 队列 → 流程 → 证据 → 验证与边界 → 总结）、结论式标题、原生可编辑对照表。
    该 skill 自带的审计脚本 `audit_pptx_quality.py` 对八版 PPT 全部跑过，H 版 findings = 0（详见 `results\qa\`）。
  八版**内容口径完全一致**（同一份 `docs/ppt_outline.json` + `docs/术语表.md`），都是**原生形状 + 文本框 + 原生表格**
  （可直接改字改色、不是图片），全篇最小 **15 pt**，且**每页都写入了演讲备注**（口播稿）。
  挑一版用即可，改法见 `deliverable/PPT版本选择.md`；口径核对见 `code/check_consistency.py`。
- **每次都附一份大纲**：`docs/ppt_outline.json`（机器可读，16 页逐页要素）+ `docs/PPT大纲.md`（人读版，含配色字号规范与提示词模板）。
  若想换工具重做，把这两个文件加 `results/figures/` 交给对方即可。
- **两个高 star PPT skill 推荐**：`docs/PPT生成Skill选择.md` ——
  [ppt-master](https://github.com/hugohe3/ppt-master)（54.1k★，原生 DrawingML，跑在 AI IDE 里，可给现成 pptx 填内容）
  与 [presenton](https://github.com/presenton/presenton)（10.2k★，Apache-2.0，自托管服务 + API/MCP，导出可编辑 PPTX）。

---

## 一、报告是怎么"填"的（格式为什么保证不变）

1. 解析你的模板：`code/inspect_docx.py` 读出每个段落的样式、字体（含中文 eastAsia 字体）、字号、缩进、
   行距，以及两张表格的每一格内容，并识别出模板里的 **Word 表单域（FORMTEXT）**空白处。
2. 只做两类写操作：往**原有段落**写文字（继承该段落的缩进与行距）、按模板段落**深拷贝**出新的正文段落
   （继承宋体 12 pt、首行缩进 3 字符、1.15 倍行距）。表格的框线、列宽、页面设置、页眉页脚一个字节都没动。
3. 写完后自动校验：`code/verify_docx.py` 对比模板与成品 → 页面设置/页眉页脚一致、
   表格属性与 tblGrid 一致、**54 个非目标单元格逐字节一致**、填写区域的提示语保留且段落格式/字体格式一致。
   最终输出 `RESULT: template format fully preserved`。

文档结构与我填写的位置：

| 模板栏目 | 是否已填 | 依据 |
|---|---|---|
| 论文题目（表 2 第 1 行右侧） | ✅ | 开题报告题目 |
| 封面信息栏（7 栏） | ✅ 已填 | `sources/开题.docx` 封面表（姓名/学号/研究生类型/培养单位/学科专业/研究方向/指导教师） |
| 1. 论文研究主要内容及工作进度 | ✅ 38 段（6 个小标题） | 开题报告 + 已完成1.docx：选题背景与意义、国内外现状与切入点、研究目标、8 项研究内容、技术路线与实施要点、8 项进度与完成情况 |
| 2. 阶段性成果 | ✅ 17 段（5 个小标题） | 数据资源与分析流程、预测结果、差异与特有肽、机制关联与实验方案、成果形式与阶段性结论 |
| 3. 公开发表学术论文情况 | ✅ 4 段 | 暂无发表，写明投稿计划与学位论文安排 |
| 4. 尚需完成的研究工作（包括内容、方案） | ✅ 21 段（5 个小标题） | 机制关联、抑菌实验验证、整理与投稿、问题与对策、后续安排 |
| Ⅱ.导师指导情况 — 1. 论文指导情况 | ✅ 1 段 | 按开题以来的实际指导过程撰写（选题与框架、方案路线、学术规范、进度督促），文字为草稿，供导师修改 |
| Ⅱ.导师指导情况 — 2. 导师综合评语 | ✅ 1 段 | 就科研情况与已完成工作给出总体评价并明确同意参加预答辩；文字为草稿，**正式文本由导师撰写并签字** |
| 2. 导师综合评语 — 导师签字 | ✅ 已填日期 | 评语正文由脚本写入（草稿，供导师改），末尾“导师签字： 2026年9月19日”已填日期、手写签名留给导师现场签；这一行在**正文末页**（Ⅱ.导师指导情况那一页），签字页从下面的 Ⅲ.评议情况另起一页 |
| Ⅲ.评议情况 — 检查小组成员 / 组长签字 / 单位盖章 | ✅ 已填 / ⬜ 待签 | 成员已按学院名单填好：组长 李向阳（教授），组员 江婷婷（副教授）、孙杰（教授）、高洪伟（教授），专业均为生物化学与分子生物学，单位均为鲁东大学生命科学学院；模板备用的第 15 行留空。签名与盖章现场办，日期已填 2026年9月19日 |
| Ⅲ.评议情况 — 中期检查意见 / 是否同意预答辩 | ⬜ 留空 | 由检查小组现场填写；自动加的一行由 `code/fill_docx.py` 的 `clone_row` 复制原行生成，行高与框线一致 |

## 二、PPT 是怎么做的

- 16 页，逐页大纲与**答辩预判问题应答要点**见 `docs/中期答辩PPT大纲.md`；通用大纲见 `docs/PPT大纲.md` / `docs/ppt_outline.json`。
- **签字页单独成完整一页**：分页加在 `Ⅲ.评议情况` 那一行（`code/fill_docx.py` 的 `page_break_before_row`，由 `code/build_ops.py` 自动带上），于是检查小组成员 / 检查意见 / 是否同意预答辩 / 组长签字 / 培养单位盖章整体落在**最后一页**、不会被拆页；**`2. 导师综合评语`（末尾“导师签字”）留在上一页**（用户 2026-09-19 指定“移回上一页”）。另出 `deliverable/中期检查表_签字页.docx`（10 行）供明天单独打印签字。分页用 `code/check_docx_layout.py` 估算核对（含“签字部分同页”检查）、`code/preview_docx.py` 出图（无需装 Office）。
- **所有日期统一填 2026年9月19日**：封面填表日期、导师签字、检查组长签字 / 培养单位盖章 3 处空档一次填好（`code/fill_docx.py` 的 `fill_date_blanks`）。模板里这 3 处在 Word 内容控件（`w:sdt`）里，python-docx 看不到，所以按 XML 只替换 `w:t` 里的文字，字体 / 字号 / 颜色等格式一字不动（`code/verify_docx.py` 会核对这点）。
- **机制补充页**（最终版/H 版第 18—23 页 = 六页；中间版 1 第 10—13 页 = 四页；中间版 2 第 9—10 页 = 两页，`code/make_ppt_mech.py`）：七环逻辑链、炎症—Aβ—抗菌肽正反馈、**动力学如何检验 AD 特有肽与 AD 的关联**（H1 结合 PAS/344—361 → 促进成核）、交叉成核，以及完整版与中间版 1 保留的八问作答表、文献一览表；插在结束页之前。
- **研究对象统一为“AD 特异性特有抗菌肽”**（AD 组特有、对照不出现）：流程页第 ⑨/⑩ 步、去重页、机制页与 docx 口径一致；关联分析的落点写成“AD 特有肽与 AD 的关联”，不再使用“候选排序”一类的说法。
- **新增流程页（第 5 页）与分组页（第 6 页）**：宏基因组流程用原生可编辑方框 + 箭头，12 步全部点名工具（fastp / KneadData / MEGAHIT / MetaBAT2 / MaxBin2 / CONCOCT / metaWRAP / dRep / EMBOSS getorf / Attention-LSTM-BERT / CoverM / Kruskal-Wallis / Mann-Whitney U）；分组页写清 5 阶段 × 2 性别 × 3 年龄段的匹配方式，并写明最终选择人数（265 例匹配亚队列、各阶段 53 例、每组 35 女 / 18 男、平均年龄差 ≤1.8 岁）。
- **不再出现来源小字**：正文与备注里没有"图：本项目自制（results/figures/…）"一类说明，图意直接写在图注里。
- **结束页在最后一页**：最终版/H 版 24 页、中间版 1 14 页、中间版 2 11 页，"谢谢各位老师，请批评指正"都在最后一页；机制页插在结束页之前。
- **中间版 2（最终答辩 PPT）按老师意见做减法**：删掉“与开题计划相比”页、“八个问题逐一作答”页与“文献支撑一览”页（这些内容留在《抗菌肽与AD关联机制说明》docx 里），机制页只留七环逻辑链与 AChE–Aβ 动力学两页，共 11 页。
- **A 版**由 `code/make_ppt2.py` 生成；**B / C / D / E 四版**由 `code/make_ppt_variants.py` 生成
  （共用一个 `STYLES` 风格表，改配色、改版式只需要改几行；`--style D` 可只出某一版）。
- **F / G 两版**走另一条线：`code/make_ppt_svg.py` 把同一份大纲渲染成 16 页 SVG（严格遵守 ppt-master 的
  SVG 书写规范：绝对坐标、`fill="none"`、字号 ≥ 20 px），再调 ppt-master 的 `scripts/svg_to_pptx.py`
  导出为原生 DrawingML；ppt-master 本体按需下载（`code/fetch_ppt_master.py`，约 125 MB，放在 `build/` 下不入库）。
- 中文字体统一**微软雅黑**，并在 XML 中显式写入东亚字体类型，避免在别人电脑上字体回退。
- 三重自检（脚本可复跑）：
  - `code/make_figures2.py`：检查图内文字是否越出方框、并折算"图片缩放到幻灯片后的最小有效字号"（7 张图均 ≥15 pt）；
  - `code/make_ppt2.py`：逐条检查 run 字号 ≥15 pt、形状不越界、文字不压图；
  - `code/check_ppt.py`：用真实中文字体估算换行高度，独立复核八版 PPT 无溢出。

## 二·五、docx 与 PPT 的口径核对

`code\check_consistency.py` 以 **docx 中期检查表为准**，逐条核对 8 份 PPT 的：论文题目、封面 5 项信息、
阶段划分（NC / SCS / SCD / MCI / AD）、机制关联的三个方向（Aβ / AChE / 免疫炎症通路）、成果形式（SCI 论文 + 学位论文）、
完成度口径，以及禁用表述（极简 / 最小工作量 / 最小可行性）。输出 `RESULT: docx 与全部 PPT 口径一致` 即通过。
用词标准见 `docs\术语表.md`。

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

## 五、协作方式（取 / 传 / 下载 / 打包）

> 在 `E:\0zhongqi\zhongqi` 里**双击 `sync.cmd`** 即一键同步；速查页见 `docs/本地同步怎么用.md`。

唯一需要记的两条（也可双击 `sync.cmd` / 直接用 `upload.ps1`）：

```powershell
cd E:\0zhongqi\zhongqi
.\sync.ps1        # ① 拿我推送的最新成果（本地有改动会自动 stash）
.\upload.ps1      # ② 把你的新文件传上来（按扩展名归位后自动 commit + push）
```

另外几个按需用：

```powershell
.\download.ps1 -List          # 看有哪些下载集合
.\download.ps1 -Set final     # ③ 把 deliverable\ 中间版\ 中间版2\ 复制到本机（robocopy 镜像）
.\pack.ps1 -Set final         # ④ 打成 _export\<日期>_final.zip，方便直接交材料
.\doctor.ps1                  # ⑤ "哪里不对劲"先跑它：分支/远端/落后领先/未提交/stash 一次看清
.\bootstrap.ps1               # ⑥ 换电脑或重装后的首次准备（执行策略 + 身份 + 切分支 + 首拉）
```

`upload.ps1` 会自动在仓库旁找到附件目录，按扩展名归位（docx/pptx/pdf/md → `sources\`，py → `code\`，xlsx/csv → `results\`）后提交推送。
首次 push 会弹 GitHub 登录窗；若提示要输**密码**，那里应填 token，或改用 GitHub Desktop 点 Push，亦可直接在 Arena 里把文件作为附件发我。

**这套脚本本身已沉淀成 skill**：`skills\git-sync\`（`SKILL.md` 给 Agent 看，`README.md` 给你看，
`sync.config.json` 是唯一的配置 —— 分支名、下载集合、扩展名归位规则都改这里）。
换项目时用 `skills\git-sync\scripts\install.ps1 -Target <新仓库>` 一键装好。

不用脚本时的等价命令：

```powershell
git fetch origin; git checkout arena/01a09d79-zhongqi; git pull --ff-only origin arena/01a09d79-zhongqi
git add -A; git commit -m "加入本地文件"; git push origin arena/01a09d79-zhongqi
```

> ⚠️ 不要 `git init` 新仓库再推这个分支：历史对不上会被拒绝；强推（`--force`）会把远端内容整支覆盖。

## 六、目录说明

```
zhongqi\
├── deliverable\            成品（完整版）：中期.docx / 中期新.docx、八版中期答辩 PPT（A—H）、正文草稿 md、PPT版本选择.md
├── 中间版\                 中间版 1：中期.docx（正文减半，进度同完整版）、中期答辩_H_nature风.pptx（14 页）
├── 中间版2\                中间版 2：中期.docx（正文减半 + 进度减半）、中期答辩_H_nature风.pptx（11 页）
├── sources\                你的原件：开题.docx、中期.docx（模板）、已完成1.docx、1.md
├── code\                   脚本：填表/校验/画图/出 PPT/版式检查（详见 code\README.md）
├── results\figures\        7 张插图；results\ppt_preview\ 八版各 4 张版式预览 + 对比图；results\qa\ 审计与 QA 报告
├── docs\                   开题要点、数据台账、PPT 大纲（json+md）、PPT skill 推荐、模板结构解析（docs\_template\）
├── skills\                 可复用 skill：可编辑 PPT 流水线、本地 git 同步脚本
├── sync.ps1 / upload.ps1 / push.ps1   一键拉取 / 上传 / 推送
├── download.ps1 / pack.ps1            一键下载交付物 / 打包成 zip
├── doctor.ps1 / bootstrap.ps1         体检排障 / 换机首次准备
└── build\                  中间产物（可重新生成，已 gitignore）
```

## 七、可复用的 skill（以后做别的汇报直接用）

| skill | 内容 | 文件 |
|---|---|---|
| **可编辑 PPT 流水线** | 一份 JSON 大纲 → 多条路线的原生可编辑 PPT（python-pptx 直排 A—E；SVG + ppt-master 原生导出 F/G；nature-skills 出 H）+ 自动校验（≥15 pt、不越界）+ 演讲备注；含大纲模板与"装到新项目"脚本 | `skills/editable-ppt-from-outline/`（`SKILL.md` / `README.md` / `outline.template.json` / `scripts/install.ps1`） |
| **本地 ↔ Agent 双向同步** | 取 / 传 / 下载 / 打包 / 体检 / 首次准备 七个 `.ps1` + 唯一配置 `sync.config.json` + 助手侧 `agent-sync.sh`（分支守卫、提交前自检、发散自愈）与 `agent-recover.sh`（沙箱 `.git` 重置后恢复历史）；含 PowerShell 5.1 的中文坑与 ASCII 自动校验 | `skills/git-sync/`（SKILL.md + README.md + scripts/） |

用法（在本仓库）：

```powershell
# 新项目复用：把生成脚本装过去（自动建 code\ docs\ results\figures\）
.\skills\editable-ppt-from-outline\scripts\install.ps1 -Target C:\MyNewProject
```

## 八、报告中待你补充的信息

| 位置 | 需要的信息 |
|---|---|
| ~~封面信息~~ | ✅ 已从 `sources/开题.docx` 填入（中期检查表 + 八版 PPT） |
| 第 2 节"阶段性成果（五）" | 是否有已投稿/在审论文（期刊、状态） |
| 第 1 节进度 | 进度口径是否需要写具体百分比（当前正文按"已完成/进行中"描述，PPT 进度页保留百分比） |
| 若要在报告中写临床评分 | MMSE / MoCA 的组间分布数据（当前未写） |
