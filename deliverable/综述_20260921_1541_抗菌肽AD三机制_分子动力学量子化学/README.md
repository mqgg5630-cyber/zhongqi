# 综述 - 北京时间 2026-09-21 15:41:20 CST

基于中期+三机制全内容生成，零基础详解，>80篇文献。

## 文件
- `抗菌肽与AD三机制_综述_20260921_1541_零基础详解_2026年09月21.docx` 综述全文，399+段，14章，含摘要、关键词、引言、中期框架、抗菌预测、5大必答题、三重机制、MD/QM全量方法、肠道脑轴、治疗启示、结论、参考文献分类
- `大纲_20260921_1541.md` 大纲MD
- `README.md` 本文件

## 大纲（14章）
1. 引言：AD负担与感染假说复兴
2. 抗菌肽概述
3. 中期框架：数据资源→三模型→差异→宏蛋白组去重→机制关联→抑菌验证
4. 抗菌活性预测
5. Q2 正常人vs AD谁更多
6. Q3 为什么多炎症
7. Q4 促进还是抑制双刃剑三维模型
8. Q5 AD感染关联
9. 三重机制总览
10. 计算方法全景 MD/QM/对接/BBB/网络药理
11. 肠道脑轴
12. 治疗启示未来
13. 结论
14. 参考文献>80篇分类

## 方法全覆盖
- MD: CHARMM36m TIP3P 12Å 150mM NVT/NPT 100ps 20ns-1μs 2fs LINCS PME1.2nm REMD 32副本6.4μs 伞形23窗0.05nm 145ns WHAM Metadynamics GFN2-xTB
- 自由能: MM-PBSA -50.6 -76kJ Woo&Roux -8.7 FEP
- QM: QM/MM DFT B3LYP GFN2-xTB FMO QPE
- 对接: Vina box20Å exhaust20 HADDOCK CB-Dock2
- 膜BBB: R9/MPG真实膜 LRP1 PACSIN2 PICALM O-BBB EC50 0.41-0.83
- 网络: 260→14核心

## 技能
- find-skills, docx, pptx, content-research-writer, doc-coauthoring 已安装全局 ~/.agents/skills/
- 使用content-research-writer工作流：大纲→研究→引用→拼接
- 使用doc-coauthoring三阶段：背景收集→细化结构→读者测试

## 推送
- 分支 arena/01a0a949-zhongqi
- 北京时间 2026-09-21 15:41:20 CST
- 旧版已全删，单一文件夹，watch-visible.ps1常驻监控已修复schannel自动重试，解放双手
