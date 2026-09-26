# 候选抗菌肽与 AD 病理关联解释版

生成时间：2026-09-26 10:25 北京时间

## 这版解决什么问题

这不是把 Aβ 结合文献再讲一遍，而是解释：论文中用深度学习从 AD 患者与健康人群肠道微生物组筛出的候选抗菌肽，如何与 AD 病理建立有证据边界的关联。

主线是：

`476 样本/宏基因组 -> 微生物源短肽库 -> Attention/LSTM/BERT AMP 预测 -> AD/健康差异 -> 来源菌与生态网络 -> LPS/SCFA/屏障/炎症 -> 条件性 Aβ/BBB 验证`

## 最重要的结论

1. 主对象是 **AD 相关差异微生物源 AMP**，不是预先寻找的 Aβ 抑制剂。
2. 保护性或抑制性 AMP 只是差异候选中的一个功能亚类。
3. “与 Aβ 结合”只说明分子相互作用，不能单独说明导致 AD；要看寡聚体方向、炎症、膜损伤、暴露和干预证据。
4. 微生物源 AMP、宿主 LL-37/防御素和宿主 Aβ 必须分开。
5. 当前仓库没有真实候选 FASTA、样本×肽丰度矩阵或 FDR 结果，因此文档没有虚构具体肽的 AD 效应；AMP-C01 等只是填写模板。

## 文件

- `深度学习筛选肠道抗菌肽_AD病理关联机制解释版_20260926_1025.docx`：零基础友好的详细解释、分层判据、组学/生态/MD/QM 方法和答辩话术。
- `深度学习筛选肠道抗菌肽_AD病理关联机制解释版_20260926_1025.pptx`：41 页汇报版，每页带演讲备注，重点解释“为什么不是简单找抑制剂”。
- `code/make_amp_ad_pathology_linkage.py`：可重复生成脚本。
- `code/amp_ad_linkage_content.py`：正文、表格、幻灯和参考文献映射。

## 使用真实候选结果时

把实际候选表接入“候选肽机制卡片”，至少提供 candidate_id、sequence、source_ORF/MAG、sample prevalence、effect size、FDR、模型概率和表达证据。结果用 `AD-associated candidate`、`potentially protective candidate` 或 `unknown-direction candidate`，在干预证据之前不要写 `causative peptide`。
