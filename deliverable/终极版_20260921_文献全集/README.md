# 终极版 - 结果一个只留一份

本目录仅保留最终版，旧版本已归档到 deliverable/archive/

## 文件清单

- `抗菌肽与AD三机制_分子动力学量子化学_文献全集_终极版.docx` 54K 174段 >60篇文献，方法全覆盖 MD/QM
  - MD: GROMACS CHARMM36m ff14SB TIP3P 12Å 150mM 最小化5000 NVT/NPT 100ps 生产20ns-1μs 2fs LINCS PME1.2nm REMD 32副本6.4μs
  - 增强采样：伞形采样23窗0.05nm 145ns/窗 WHAM，Metadynamics RMSD CV高斯沉积GFN2-xTB k_i/N=0.025，REUS
  - 自由能：MM-PBSA -50.6 kcal/mol -76.28 kJ/mol -8.7±0.7 kcal/mol Woo&Roux绝对自由能，FEP 0.55±30.25偏差，残基分解
  - QM：QM/MM DFT B3LYP/GFN2-xTB FMO QPE，键长偏差0.01-0.05Å氢键0.1Å，Al(III)内层4外层2-3单齿Glu3 Asp7双齿Glu11破坏盐桥Asp23-Lys28
  - 结合：Aβ抗菌Soscia 2010 + LL-37纳摩尔De Lorenzi 2017 + HNP-1双位点β-sheet/U-turn对接+MD Chem Soc Rev 2024 + AChE-PAS 344-361 1μs MD
  - 肠道：Papiliocin PNAS 2022 TLR4/MD-2 R13/R16微摩尔，SoLs -8.9 -9.6 vs lipid A -6.2，Tachystatin 46氢键-780k，网络药理260→14 -6.8~-8.1
  - BBB：R9/MPG真实膜MD自由能垒N端精氨酸多不饱和脂，ApoE 600ns β-hairpin，Fc-PepH3 AMT vs FC5 RMT，O-BBB EC50 0.41-0.83优于angiopep-2 P=0.0175，CPP体内Tat 4.73 SynB3 5.63 pVEC 6.02

- `抗菌肽与AD三机制_分子动力学量子化学_文献全集_终极版_M_深蓝金机制.pptx` 784K 17页 深蓝金·机制专属，版式自检OK（2软警告），三轴+计算分工

- 另有 `watch-visible.ps1` 常驻窗口版已验证成功 round1 7000732 -> round3 5b1b056 Fast-forward，解决闪窗问题

## 本地同步

- 旧版本已归档：deliverable/archive/ 25个文件
- 本地执行 `.\watch-visible.ps1` 常驻窗口会自动拉取最新（已验证 round3成功）
- Light-skills保留沙箱 /tmp/light，未推送本地，仅推送结果文件

## 文献统计

>60篇全覆盖：Ma 2022, Santos-Junior 2024, GAC-BiTCNN-AMP 2026, AM Predictor GCN 2024, Soscia 2010, Kumar 2016, De Lorenzi 2017, Barron 2024 Chem Soc Rev, Chen 2022 Mol Psychiatry LL-37-CLIC1 Kd5.79e-7, Lee 2015, PMC 2026 LL-37 vs Aβ, Front Immunol 2020, LL-37 CsgC 2022, hBD-2点突变MD MM/PBSA 2025, KLVFF LPFFD 2011, Aβ纤维β-breaker 2010, KLVFF VVIA LPFFD 2014, 淀粉样抑制蛋白2014 PLoS One 2D PMF D23-K28, BMS-984923 2026, Aβ抑制剂对接MD 2022, 小分子抑制Aβ MD综述2025, APP Mint2 2024 MM-PBSA -6.93, Al结合Aβ QM MD metadynamics 2020 GFN2-xTB, Al结合Aβ结构2019, Aβ16-22伞形采样2020 PLUMED WHAM 2.7 kcal/mol, Aβ1-42寡聚早期膜2010伞形采样145ns, Aβ1-40聚集自由能PNAS 2016 Qdiff LAMMPS, Aβ9-40延伸自由能Wiley 2024 Woo&Roux -8.7±0.7 vs -7.87 FEP 0.55±30.25, Aβ42单体-43.1 kcal/mol 2018, 量子资源arXiv 2406.18744 QM/MM FMO QPE, Papiliocin PNAS 2022 R13/R16, SoLs Nature Commun 2024 Vina 32Å -8.9 -9.6, AMP-TLR4 2025 HADDOCK, Gut metabolites 2026 260→14 -6.8~-8.1, Gut lipid crosstalk 2024 Springer, Brain-Gut Axis 2019 JNM, Gut dysbiosis 2020, Microbiota-brain 2025, Decoding gut 2023, Multivalent LRP1 2024 bioRxiv PACSIN2 A39-PO, Rapid Aβ clearance 2025 Nature PICALM Rab5 Rab11 Rab7, Angiopep-2密度2024, Tubule formation Sci Adv 2020 syndapin-2, LRP1抗体递送2015 Sci Rep, BBB废物清除2026 PMC13185194 TfR1 LRP1 P-gp, L57 2017, BBB穿透R9 MPG 2026 PubMed 41875963真实膜, BBB肽MD表征2019 9种600ns β-hairpin PCA, Branched AMP B2088 2012静电氢键PO4双齿, Steered MD 656次2022, CPP选择性跨BBB 2015 Tat 4.73 SynB3 5.63 pVEC 6.02 MTR, Peptides crossing BBB 2023亲脂性CINC-1 7.8kDa PTS-1, Fc-PepH3 2021 AMT vs RMT, O-BBB融合2025 EC50 0.41-0.83 P=0.0175, Nanobodies RMT 2024, Conjugation Fc 2021, Single-domain AMT 2021 pI~9.5, Two peptides 2021 GYR MTfp LRP-1 TfR等

