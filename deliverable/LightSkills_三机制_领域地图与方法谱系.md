# Light-skills 检索：抗菌肽与AD三机制领域地图（MD/QM/肠道/BBB）
使用 light-literature-search 三层分别检索 + web_search 真实文献补充
分支：arena/01a0a949-zhongqi 时间：2026-09-21
推送验证：此文件通过 watch-visible.ps1 常驻窗口自动拉取验证

## 检索协议
查询：1) antimicrobial peptide Alzheimer binding molecular dynamics QM/MM 2) gut microbiota antimicrobial peptide Alzheimer LPS TLR4 docking 3) blood brain barrier antimicrobial peptide penetration molecular dynamics 4) LL-37 amyloid beta interaction umbrella sampling
覆盖度门：HTTP200=none（离线），失败源 OpenAlex=0 Crossref=0 DOAJ=0，未覆盖CNKI/万方/维普，真实文献通过web_search补充，绝不臆造DOI

## 核心发现
- 结合：Aβ本身抗菌 Soscia 2010 + LL-37纳摩尔 De Lorenzi 2017 + HNP-1双位点β-sheet/U-turn对接+MD Chem Soc Rev 2024 + AChE-PAS 344-361 1μs MD Atanasova 2020
- MD：GROMACS CHARMM36m ff14SB TIP3P 12Å 150mM NVT/NPT 100ps生产20ns-1μs 2fs LINCS PME1.2nm
- 增强采样：REMD 32副本300-500K 200ns/副本6.4μs，伞形采样23窗0.05nm每窗145ns WHAM，Metadynamics RMSD CV高斯沉积GFN2-xTB k_i/N=0.025 E_h，REUS
- 自由能：MM-PBSA -50.6 kcal/mol ADNP7-Aβ，-76.28 kJ/mol RR-AFC，-8.7±0.7绝对结合自由能Woo&Roux校正无序熵 vs 实验-7.87 FEP 0.55±30.25偏差大，Amentoflavone 16KLVFFAEDV24非极性>71%
- QM：QM/MM DFT B3LYP/GFN2-xTB QM区金属+配位残基，FMO碎片组合，QPE双因子化qubitization，键长偏差0.01-0.05Å氢键0.1Å，Al(III)内层4外层2-3单齿Glu3 Asp7双齿Glu11主链O参与破坏盐桥Asp23-Lys28
- 肠道：Papiliocin PNAS 2022 STD NMR+对接TLR4/MD-2/LPS晶体N端界面C端疏水口袋氢键K7-S118 Q31-K122静电R1-D294微摩尔亲和R13/R16关键，AMP-TLR4 HADDOCK Tachystatin 46氢键-780k，网络药理260→14 IL6/NFKB1 CB-Dock2 -6.8~-8.1
- BBB：R9/MPG真实人脑内皮膜MD 2026自由能垒N端精氨酸多不饱和脂可塑性，ApoE 600ns β-hairpin，Fc-PepH3 AMT快速vs FC5 RMT巨胞饮，O-BBB OspA N端β10-11净电荷-3.4 EC50 0.41-0.83μM 1h去极化1h优于angiopep-2 P=0.0175，CPP体内Tat 4.73 SynB3 5.63 pVEC 6.02 μl/g/min非饱和

## 信号
最像的一篇：Barron 2024 Chem Soc Rev DOI:10.1039/D3CS00878A HNP-1二聚体对接+MD结合Aβ/hIAPP五聚体，喂idea-critique撞车预警
年代偏斜：recent_heavy缺奠基根 → snowball backward补Soscia 2010等

## 方法移植建议
R9/MPG真实膜MD+增强采样移植到候选肽BBB自由能垒，Papiliocin TLR4/MD-2对接+STD NMR移植到肠道特有抗菌肽，Woo&Roux绝对自由能移植到Aβ-AMP无序肽，GFN2-xTB metadynamics QM/MM用于金属多配位探索

## 推送验证
watch-visible.ps1 round 1已成功 up to date 7000732，round 2应自动拉取本文件
Light-skills保留沙箱/tmp/light，不推送本地，符合要求

引用：RSC 2024, Soscia 2010, De Lorenzi 2017, Atanasova 2020, PNAS 2022 Papiliocin, Sci Rep 2025 O-BBB, R9/MPG 2026, Int J Nanomedicine 2019 9种BBB肽MD, PLoS One 2015 CPP BBB, ACS Med Chem Lett 2021 Fc-PepH3, PMC 2025网络药理, PMC 2025 AMP-TLR4, arXiv 2406.18744 QM/MM FMO QPE, R Soc Open Sci 2020 Al binding metadynamics, PMC 2020 umbrella PLUMED WHAM, Wiley 2024 Aβ9-40 Woo&Roux
