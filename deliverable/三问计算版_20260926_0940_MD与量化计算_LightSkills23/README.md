# 三问·计算版（MD + 量化计算）单独交付物

**文件夹**：`deliverable/三问计算版_20260926_0940_MD与量化计算_LightSkills23/`

## 只回答三个问题（不含其他内容）

| # | 问题 | 本册的计算主线 |
|---|---|---|
| ① | **抗菌肽与 Aβ 如何结合** | 全原子 MD（1-10 μs × 多重复）→ 接触频率定界面 → MM-PBSA/残基分解定自由能与热点 → 伞形采样/元动力学求 PMF → DFT/QM-MM/FMO 讲清电子本质（盐桥、π-π、β 互补、金属配位） |
| ② | **抗菌肽与肠道菌群调控如何导致 AD** | 宏基因组 AMP 挖掘（Macrel / AMPlify / LSTM+Attention+BERT 共识）→ 差异丰度（ANCOM-BC2/MaAsLin2/DESeq2）→ 共现网络（SparCC/SPIEC-EASI）→ 因果（中介分析、两样本 MR）→ 生态动力学（Lotka-Volterra 型）→ AMP-菌膜/LPS 的 MD 与 PMF → lipid A-肽的 DFT → 机器学习分类与解释 |
| ③ | **抗菌肽穿过血脑屏障如何导致 AD** | BBB 模型膜（胆固醇 30-45%、鞘脂、糖萼）MD → 跨膜 PMF + ISD 模型算 P_app → 加速采样（高温 MD/GaMD/SMD/Milestoning/MSM）→ PEPT2/LRP1/RAGE 对接与 MM-PBSA → logBB 机器学习互证 → 穿越后共聚集 MD 与 TLR4/FPR2 信号 ODE、分岔分析 |

方法学全部是计算类（**分子动力学为主，量化计算为辅**），实验内容只作为校准计算的标尺出现，不写实验操作细节。

## 两份文件

| 文件 | 说明 |
|---|---|
| `抗菌肽与AD三大问题_计算机制详解_20260926_0940_MD与QM.docx` | 主文档（约 11.2 万字节、548 段、36 张表）：阅读说明 → 总览表 → 三篇正文（问题一/二/三，每篇含命题拆解、实验锚点、逐项参数表、判据与不确定性）→ 方法总表（软件版本、机时估算、验证策略、十条陷阱）→ 附录术语表 → 参考文献（按正文首次出现顺序编号，153 条） |
| `抗菌肽与AD三大问题_计算机制详解_20260926_0940_MD与QM.pptx` | 71 页答辩/汇报版：原生可编辑形状 + 原生表格（超长表格自动分页），每页带演讲备注；封面与章节页为深蓝金配色；已通过 `code/check_ppt.py --min-pt 9`（0 警告） |

## 文献

- 共引用 **153 条**，全部围绕这三个问题（AMP-Aβ 结合、AMP 与菌群、AMP 穿越 BBB、以及三类方法学工具文献）。
- 带 **DOI / PMID / PMC** 的条目可直接检索核验原文（来自本次会话的实时文献检索）。
- 建议提交前用 DOI 批量复核一次卷期页码（`skills/light-citation` 的校验脚本）。

## 生成与复现

```bash
python3 code/make_triq_computational.py            # 时间戳取当前北京时间
TRIQ_TS=20260926_0940 python3 code/make_triq_computational.py   # 固定时间戳重生成
```

脚本模块：`code/triq_common.py`（总览/术语）、`code/triq_refs.py`（参考文献库，198 条可选）、`code/triq_q1.py`/`triq_q2.py`/`triq_q3.py`/`triq_q4.py`（正文）、`code/triq_render.py`（DOCX）、`code/triq_render_pptx.py`（PPTX）、`code/triq_slides.py`（PPT 页面规格）。

依赖：`python-docx`、`python-pptx`。

## 技能使用

Light-skills 23 项（light-literature-search 三层检索、light-paper-writing 证据门、light-citation DOI 核查、light-figure 程序化图表、light-data-engineering 数据质量门、light-consistency 跨材料一致等）＋ find-skills（3.5M）＋ docx ＋ pptx ＋ content-research-writer ＋ doc-coauthoring。
