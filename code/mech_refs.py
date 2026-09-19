#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mech_refs.py - 机制解释部分的文献库（唯一数据源）。

`code/make_mech_doc.py`（机制说明 docx）与 `code/make_ppt_mech.py`（PPT 机制页）
都从这里取文献与结论，避免两处口径不一致。

八个问题（按老师的提问顺序）：
    1. 抗菌肽与 AD 的关联        5. 筛选出的抗菌肽是否导致 AD（致病方向）
    2. AD 与感染的关联           6. 抗菌活性（抗感染）这一侧的证据
    3. 抗菌活性为什么可以预测     7. 为什么 AD 组更多（炎症的关系）
    4. AD 组特有抗菌肽的合理性    8. 正常人 vs AD 谁更多（方向与例外）

口径（2026-09-19 起）：第 5 问与分子动力学部分一律按**致病方向**写——验证候选抗菌肽是否
促进 Aβ 成核/聚集、生成更毒的聚集体、放大神经炎症（推动 AD），不再用“抑制 AD”的框架；
抗菌活性只作为这些肽的本职功能与来源背景（第 6 问）。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 参考文献
# 只列能溯源到具体出版物/数据库记录的条目；DOI 取自检索结果原文。
REFS: dict[int, str] = {
    1: "Soscia SJ, Kirby JE, Washicosky KJ, et al. The Alzheimer's disease-associated "
       "amyloid β-protein is an antimicrobial peptide. PLoS ONE, 2010, 5(3): e9505. "
       "doi:10.1371/journal.pone.0009505",
    2: "Moir RD, Lathe R, Tanzi RE. The antimicrobial protection hypothesis of Alzheimer's "
       "disease. Alzheimers Dement, 2018, 14(12): 1602-1614. doi:10.1016/j.jalz.2018.06.3040",
    3: "Kumar DK, Choi SH, Washicosky KJ, et al. Amyloid-β peptide protects against microbial "
       "infection in mouse and worm models of Alzheimer's disease. Sci Transl Med, 2016, "
       "8(340): 340ra72. doi:10.1126/scitranslmed.aaf1059",
    4: "Eimer WA, Vijaya Kumar DK, Navalpur Shanmugam NK, et al. Alzheimer's disease-associated "
       "β-amyloid is rapidly seeded by Herpesviridae to protect against brain infection. "
       "Neuron, 2018, 99(1): 56-63. doi:10.1016/j.neuron.2018.06.030",
    5: "Wozniak MA, Itzhaki RF, Shipley SJ, Dobson CB. Herpes simplex virus infection causes "
       "cellular β-amyloid accumulation and secretase upregulation. Neurosci Lett, 2007, "
       "429(2-3): 95-100. doi:10.1016/j.neulet.2007.09.077",
    6: "Chen X, Deng S, Wang W, et al. Human antimicrobial peptide LL-37 contributes to "
       "Alzheimer's disease progression. Mol Psychiatry, 2022, 27(11): 4790-4799. "
       "doi:10.1038/s41380-022-01790-6",
    7: "Lee M, Shi X, Barron AE, McGeer E, McGeer PL. Human antimicrobial peptide LL-37 induces "
       "glial-mediated neuroinflammation. Biochem Pharmacol, 2015, 94(2): 130-141. "
       "doi:10.1016/j.bcp.2015.02.003",
    8: "Williams WM, Torres S, Siedlak SL, et al. Antimicrobial peptide β-defensin-1 expression "
       "is upregulated in Alzheimer's brain. J Neuroinflammation, 2013, 10: 127. "
       "doi:10.1186/1742-2094-10-127",
    9: "Brock DG, Loewy A, Bloomfield S, et al. The antimicrobial protein CAP37 is upregulated "
       "in pyramidal neurons during Alzheimer's disease. Histochem Cell Biol, 2015, 144(5): "
       "447-460. doi:10.1007/s00418-015-1347-x（TNF-α 与 Aβ 上调神经元 CAP37 表达）",
    10: "Antimicrobial peptides (AMPs) in the pathogenesis of Alzheimer's disease: implications "
        "for diagnosis and treatment. Antibiotics, 2022, 11(6): 726. doi:10.3390/antibiotics11060726"
        "（α-防御素 1—4、β-防御素 2、乳铁蛋白、胱抑素、组氨基素等在唾液/血液/脑脊液中变化的汇总）",
    11: "Zhan X, Stamova B, Sharp FR. Lipopolysaccharide associates with amyloid plaques, neurons "
        "and oligodendrocytes in Alzheimer's disease brain. Front Aging Neurosci, 2018, 10: 42. "
        "doi:10.3389/fnagi.2018.00042（AD 脑 LPS 为对照的 2—3 倍，血浆约 3 倍）",
    12: "Emery DC, Shoemark DK, Batstone TE, et al. 16S rRNA next generation sequencing analysis "
        "shows bacteria in Alzheimer's post-mortem brain. Front Aging Neurosci, 2017, 9: 195. "
        "doi:10.3389/fnagi.2017.00195（AD 脑细菌读段为对照的 5—10 倍）",
    13: "Balin BJ, Gérard HC, Arking EJ, et al. Identification and localization of Chlamydia "
        "pneumoniae in the Alzheimer's brain. Med Microbiol Immunol, 1998, 187(1): 23-42. "
        "doi:10.1007/s004300050071（AD 脑 89% 阳性，对照 5%）",
    14: "Dominy SS, Lynch C, Ermini F, et al. Porphyromonas gingivalis in Alzheimer's disease "
        "brains: evidence for disease causation and treatment with small-molecule inhibitors. "
        "Sci Adv, 2019, 5(1): eaau3333. doi:10.1126/sciadv.aau3333",
    15: "Alzheimer's disease and infectious agents: a comprehensive review of pathogenic "
        "mechanisms and microRNA roles. 2025. PMID: 39840010（HSV-1、EBV、CMV、流感、SARS-CoV-2、"
        "幽门螺杆菌、螺旋体、衣原体与牙周致病菌的系统综述）",
    16: "Beyond association: a quantitative analysis of the infectious burden in Alzheimer's "
        "disease. 2026. PMC13291386（人群归因分数：HSV-1 约 13.5%、慢性牙周炎约 19.4%、"
        "C. pneumoniae 约 31%；三者合计 31%—51.9%）",
    17: "Preoperative microbiomes and intestinal barrier function can differentiate prodromal "
        "Alzheimer's disease in elderly patients. Front Cell Infect Microbiol, 2021. PMC8044800"
        "（SCD 患者血浆 LPS 与 CRP 升高、aMCI 患者血浆 occludin 升高）",
    18: "Gut permeability and cognitive decline: a pilot investigation in the Northern Manhattan "
        "Study. 2021. PMC8186438（血浆 LPS 与 sCD14 升高与认知下降相关，并与 IL-1/IL-17/TNF "
        "通路活化相关）",
    19: "Lipopolysaccharide-binding protein and Alzheimer's disease risk. Front Neurol, 2024, 15: "
        "1408220. doi:10.3389/fneur.2024.1408220（LBP 是肠通透性标志物，前瞻队列中可预测 AD 风险）",
    20: "Amyloid-β as an effector of innate immunity: pathological or preventative? Infect Immun, "
        "2026. doi:10.1128/iai.00085-26（Aβ 的抗黏附、调理素、纤维网捕获与生物膜破坏四种机制）",
    21: "Ma Y, Guo Z, Xia B, et al. Identification of antimicrobial peptides from the human gut "
        "microbiome using deep learning. Nat Biotechnol, 2022, 40(6): 921-931. "
        "doi:10.1038/s41587-022-01226-0（11 条候选肽在耐药革兰阴性菌与小鼠肺炎模型中验证有效）",
    22: "Santos-Júnior CD, Torres MDT, Duan Y, et al. Discovery of antimicrobial peptides in the "
        "global microbiome with machine learning. Cell, 2024, 187(14): 3761-3778. "
        "doi:10.1016/j.cell.2024.05.013（AMPSphere：863 498 条非冗余候选抗菌肽）",
    23: "Santos-Júnior CD, Pan S, Zhao XM, Coelho LP. Macrel: antimicrobial peptide screening in "
        "genomes and metagenomes. PeerJ, 2020, 8: e10555. doi:10.7717/peerj.10555",
    24: "Detection of antimicrobial peptides from fecal samples of FMT donors using deep learning. "
        "2025. PMID: 41164228（与研究同一套流程：宏基因组+深度学习挖掘 → 宏蛋白组互证 → "
        "分子动力学模拟 → 合成与活性验证）",
    25: "Wan F, Wong F, Collins JJ, de la Fuente-Nunez C. Machine learning for antimicrobial "
        "peptide identification and design. Nat Rev Bioeng, 2024, 2: 392-407. "
        "doi:10.1038/s44222-024-00152-x",
    26: "Cattaneo A, Cattane N, Galluzzi S, et al. Association of brain amyloidosis with "
        "pro-inflammatory gut bacterial taxa and peripheral inflammation markers in cognitively "
        "impaired elderly. Neurobiol Aging, 2017, 49: 60-68. "
        "doi:10.1016/j.neurobiolaging.2016.08.019",
    27: "Vogt NM, Kerby RL, Dill-McFarland KA, et al. Gut microbiome alterations in Alzheimer's "
        "disease. Sci Rep, 2017, 7: 13537. doi:10.1038/s41598-017-13601-y",
    28: "The correlation and gut microbial characteristics in the whole spectrum of Alzheimer's "
        "disease: a systematic review and meta-analysis. Front Neurosci, 2026. "
        "doi:10.3389/fnins.2026.1775002（Proteobacteria 在 MCI 阶段下降，Firmicutes 在 AD 阶段"
        "下降；Fusobacteria、Lactobacillus 呈阶段梯度）",
    29: "Distinct gut microbiota profiles and network properties in older individuals with "
        "subjective cognitive decline, mild cognitive impairment, and Alzheimer's disease. "
        "Alzheimers Res Ther, 2025. doi:10.1186/s13195-025-01820-9（SCD 组的 Anaerosacchariphilus、"
        "Anaerobutyricum 等为阶段特有）",
    30: "Gut microbiome dysbiosis in Alzheimer's disease and mild cognitive impairment: "
        "a systematic review and meta-analysis. PLoS ONE, 2023, 18(5): e0285346. "
        "doi:10.1371/journal.pone.0285346（菌群失衡始于前驱期）",
    31: "Atanasova M, Dimitrov I, Ivanov S. Molecular dynamics simulations of "
        "acetylcholinesterase – beta-amyloid peptide complex. Cybernetics and Information "
        "Technologies, 2020, 20(6): 140-154. doi:10.2478/cait-2020-0068（1 μs 模拟，复合物稳定；"
        "Aβ 主要停留区段为 AChE 344—361）",
    32: "De Ferrari GV, Canales MA, Shin I, et al. A structural motif of acetylcholinesterase "
        "that promotes amyloid β-peptide fibril formation. Biochemistry, 2001, 40(35): "
        "10447-10457. doi:10.1021/bi0101392（对接给出四处 AChE–Aβ 结合位点，疏水肽段可被"
        "掺入生长中的纤维）",
    33: "Inestrosa NC, Dinamarca MC, Alvarez A. Amyloid–cholinesterase interactions. FEBS J, 2008, "
        "275(4): 625-632. doi:10.1111/j.1742-4658.2007.06238.x（PAS 抑制剂丙锭可阻断 AChE 促"
        "聚集效应，催化位点抑制剂无此作用；丁酰胆碱酯酶反而延缓纤维形成）",
    34: "A new motif in the N-terminal of acetylcholinesterase triggers amyloid-β aggregation and "
        "deposition. 2019. PMC6493010（PAS 的高负电荷密度可经静电作用把 Aβ 由 α-螺旋推向"
        "β-发夹；AChE 7—20 肽段同样可促进聚集）",
    35: "Rees T, Hammond PI, Soreq H, Younkin S, Brimijoin S. Butyrylcholinesterase attenuates "
        "amyloid fibril formation in vitro. PNAS, 2006, 103(23): 8783-8788. "
        "doi:10.1073/pnas.0602922103",
    36: "Zheng J, et al. Antimicrobial peptides as cross-seeding modulators at the "
        "neurodegenerative–infectious interface. Research, 2026. doi:10.34133/research.1149"
        "（三条机制：结构兼容、定向成核不对称、表面催化；并提出病原—淀粉样正反馈环）",
    37: "Exploring pathological link between antimicrobial and amyloid peptides. Chem Soc Rev, "
        "2024. doi:10.1039/D3CS00878A（交叉成核可加速、抑制或改变纤维形态；中性粒细胞弹性"
        "蛋白酶与组织蛋白酶 G 可切割 Aβ42，CAP37 则以淬灭方式抑制）",
    38: "Unveiling the inhibition mechanism of host-defense peptide cathelicidin LL-37 on the "
        "amyloid aggregation of the human islet amyloid polypeptide. Nanoscale, 2025. "
        "doi:10.1039/D4NR05075D（全原子离散分子动力学：疏水与 π–π 相互作用为主，"
        "结合淀粉样生成区并封堵纤维延伸面）",
    39: "Membrane core-specific antimicrobial action of cathelicidin LL-37 peptide switches "
        "between pore and nanofibre formation. Sci Rep, 2016, 6: 38184. doi:10.1038/srep38184"
        "（MD 显示 LL-37 自身可经盐桥形成纤维样聚集体）",
    40: "Polymyxin-B as a novel inhibitor of amyloid beta aggregation: computational insights and "
        "experimental validation. J Mol Biol, 2025（抗菌肽类分子与 Aβ 单体/原纤维的对接与 100 ns "
        "动力学，并用 Tricine-SDS-PAGE 验证聚集抑制）",
    41: "Identification of new pentapeptides as potential inhibitors of amyloid-β42 aggregation "
        "using virtual screening and molecular dynamics simulations. J Mol Graph Model, 2023"
        "（短肽库虚拟筛选 + MM-PBSA + MD，破坏 Asp23—Lys28 盐桥）",
    42: "Associations of serum antimicrobial peptide LL-37 with longitudinal cognitive decline "
        "and neurodegeneration among older adults with memory complaints. J Alzheimers Dis, 2023. "
        "doi:10.3233/JAD-230007（高 LL-37 组 MMSE 下降 ≥3 分的 OR 为 2.11，NfL 与 pTau181 上升更快）",
    43: "Decreased salivary lactoferrin levels are specific to Alzheimer's disease. EBioMedicine, "
        "2020, 57: 102834. doi:10.1016/j.ebiom.2020.102834（MCI-PET+ 3.8、AD 3.6 vs 对照 "
        "7.7 μg/mL）",
    44: "Salivary lactoferrin levels decrease in Alzheimer's disease patients (early stage). 2025. "
        "PMC11716888（早中期 AD 9.02 vs 对照 26.07 μg/mL）",
    45: "Mechanistic insights into the role of amyloid-β in innate immunity. Sci Rep, 2024. "
        "doi:10.1038/s41598-024-55423-9（Aβ 寡聚体经 α-折叠与大杆菌 CsgA 相互作用，"
        "抑制 curli 与生物膜）",
    46: "Synergistic regulation of Alzheimer's disease and intestinal barrier: the LPS–TLR4/NF-κB "
        "axis. 2026. PMC13539905（菌群失衡 → 肠屏障通透性升高 → LPS 入血 → TLR4/NF-κB → "
        "Aβ 沉积的前馈环；IL-6/CRP 与临床分期相关）",
    # ---- 47—58：2026-09-19 新增，支撑“候选抗菌肽→推动 AD”的致病方向 ----
    47: "Javed I, Zhang Z, Adamcik J, et al. Accelerated amyloid beta pathogenesis by bacterial "
        "amyloid FapC. Adv Sci, 2020, 7(18): 2001299. doi:10.1002/advs.202001299"
        "（FapC 片段作为催化表面加速 Aβ 纤维化；斑马鱼幼虫与成鱼中加重 Aβ 沉积、突触丢失与"
        "行为损害；绿脓杆菌生物膜片段同样加速）",
    48: "Perov S, Lidor O, Salinas N, et al. Structural insights into curli CsgA cross-β fibril "
        "architecture inspire repurposing of anti-amyloid compounds as anti-biofilm agents. "
        "PLoS Pathog, 2019, 15(8): e1007978. doi:10.1371/journal.ppat.1007978"
        "（CsgA 的 steric zipper 与人类病理淀粉样纤维同构；CsgA 种子加速 Aβ1—40 纤维化）",
    49: "Asti A, Gioglio L. Can a bacterial endotoxin be a key factor in the kinetics of amyloid "
        "fibril formation? J Alzheimers Dis, 2014, 39(1): 169-179. doi:10.3233/JAD-131394"
        "（内毒素 LPS 缩短成核滞后期、加速 Aβ 纤维化，被视为纤维化的促进因子）",
    50: "Wang LM, Wu Q, Kirk RA, et al. Lipopolysaccharide endotoxemia induces amyloid-β and "
        "p-tau formation in the rat brain. Am J Nucl Med Mol Imaging, 2018, 8(2): 86-99"
        "（单次腹腔注射 LPS 后大鼠脑内可溶性 Aβ 升高，皮层 Aβ 斑块与 p-tau 在 7—9 天内"
        "进行性增加，对照组无斑块）",
    51: "Bacterial amyloid curli associated gut epithelial neuroendocrine activation predominantly "
        "observed in Alzheimer's disease mice with central amyloid-β pathology. J Alzheimers Dis, "
        "2022, 88(1): 191-205. doi:10.3233/JAD-220106（Tg-AD 小鼠肠内 curli 与 TLR2 升高、"
        "与神经内分泌标志物 PGP9.5 共定位并伴迷走神经激活，构成肠—迷走—脑通路）",
    52: "Forgham H, Albornoz EA, Pietrogrande G, et al. Gut-bacterial amyloids can prime microglia "
        "against endogenous amyloid-β and mediate neuroinflammation in Alzheimer's disease. "
        "npj Dementia, 2026, 2: 59. doi:10.1038/s44400-026-00122-7（FapC 与 CsgA 混合种子在人源"
        "小胶质、干细胞脑类器官与斑马鱼模型中把 Aβ 压实成更小团块、诱发促炎表型，对旁观神经元"
        "产生毒性）",
    53: "Wang X, Österlund N, Pereira Curia G, et al. LL-37 and its truncated fragments modulate "
        "amyloid-β dynamics, aggregation and toxicity through hetero-oligomer and cluster "
        "formation. Angew Chem Int Ed, 2025, 64(43): e202516241. doi:10.1002/anie.202516241"
        "（PMID: 40916348；LL-37 及其片段与 Aβ40 形成异源寡聚体与纳米/微米团簇，在抑制纤维的"
        "同时生成毒性更强的聚集体）",
    54: "Asti AL. β-Amyloid (Aβ) and human cathelicidin LL-37: two sides of the same coin? "
        "Int J Mol Sci, 2026, 27(12): 5460. doi:10.3390/ijms27125460（综述：LL-37 在炎症条件下"
        "上调并结合 Aβ 调节其聚集动力学；LPS 作为异源成核的促进因子，与 LL-37 共同把过程"
        "推向致病一侧）",
    55: "Szekeres M, Ivitz E, Datki Z, et al. Relevance of defensin β-2 and α defensins (HNP1-3) "
        "in Alzheimer's disease. Psychiatry Res, 2016, 239: 342-345. "
        "doi:10.1016/j.psychres.2016.03.045（PMID: 27082275；AD 患者 DEFB4 拷贝数更高，hBD-2 与"
        "HNP1-3 在血清与脑脊液中显著升高，作者据此提出防御素可能参与 AD 的发生）",
    56: "Zhang Y, Liu Y, Tang Y, et al. Antimicrobial α-defensins as multi-target inhibitors "
        "against amyloid formation and microbial infection. Chem Sci, 2021, 12(26): 9124-9139. "
        "doi:10.1039/D1SC01133B（反向证据：HNP-1 与 NP-3A 在等摩尔比下完全抑制 Aβ 纤维化，"
        "说明同为防御素方向并不一致，写入边界）",
    57: "De Lorenzi E, Chiari M, Colombo R, et al. Evidence that the human innate immune peptide "
        "LL-37 may be a binding partner of amyloid-β and inhibitor of fibril assembly. "
        "J Alzheimers Dis, 2017, 59(4): 1213-1226. doi:10.3233/JAD-170223（体系依赖：LL-37 抑制"
        "长纤维形成，但把 Aβ42 的平衡推向低分子量寡聚体，并在该体系中降低微胶质介导的毒性）",
    58: "Fernández-Calvet A, Matilla-Cuenca L, Izco M, et al. Gut microbiota produces "
        "biofilm-associated amyloids with potential for neurodegeneration. Nat Commun, 2024, "
        "15: 4150. doi:10.1038/s41467-024-48309-x（人粪便来源的生物膜相关淀粉样蛋白在 AD/PD "
        "患者中更丰富，可交叉成核 αSyn，并在体外参与 Aβ 的成核）",
    59: "Zhao Z, Zhao F, Zhang M, et al. Multi-omics profiling reveals gut microbiome "
        "signatures associated with cognitive decline in Alzheimer's disease. iScience, 2026, "
        "29(8): 116622. doi:10.1016/j.isci.2026.116622（宏基因组 + 代谢组：AD 组富集 "
        "Akkermansia massiliensis、Alistipes onderdonkii、Barnesiella intestinihominis 等菌种，"
        "物种层面的特征可区分 AD 且与 MMSE 负相关——说明“AD 组特异”的微生物特征在物种层面"
        "可以被识别）",
    60: "Gut microbiota changes in patients with Alzheimer's disease spectrum based on 16S "
        "rRNA sequencing: a systematic review and meta-analysis. Front Aging Neurosci, 2024, "
        "16: 1422350. doi:10.3389/fnagi.2024.1422350（PMC11338931；AD 谱系中 12 个属显著改变："
        "Ruminococcus、Faecalibacterium、Lachnospira 等下降，Phascolarctobacterium、Lactobacillus "
        "与 Akkermansia muciniphila 富集；作者提出这些改变可作为 AD 相关的菌群特征）",
}

# ------------------------------------------------------------ 抗菌肽的方向
# 第 8 问用的方向表：同一分子在 AD 中的方向并不一致，必须分清部位与阶段。
DIRECTION: list[tuple[str, str, str, str]] = [
    # (分子, 方向, 标本/部位, 文献号)
    ("LL-37（cathelicidin）", "升高", "AD 脑组织；血清高者认知下降更快", "[6][7][42]"),
    ("β-防御素-1（hBD-1）", "升高", "AD 脑海马星形胶质细胞、神经元、脉络丛", "[8][10]"),
    ("β-防御素-2（hBD-2）", "升高", "AD 血清与脑脊液", "[10]"),
    ("α-防御素 1—4", "升高", "AD 唾液、血液、血清、脑脊液", "[10]"),
    ("CAP37（AZU1）", "升高", "AD 颞叶/顶叶皮层锥体神经元（可被 TNF-α 与 Aβ 诱导）", "[9]"),
    ("组氨基素 1、富酪蛋白、胸腺素 β4", "升高", "AD 唾液蛋白组", "[10]"),
    ("Aβ42（本身即抗菌肽）", "升高", "AD 脑匀浆抗菌活性高于同龄对照", "[1]"),
    ("乳铁蛋白", "降低", "AD 唾液（早中期即下降，诊断 AUC 0.93—0.95）", "[43][44]"),
    ("铁调素、胱抑素 C", "降低", "AD 血清/脑脊液", "[10][43]"),
]

# 第 4 问：阶段特异的微生物学证据（用于说明“AD 组特有肽”的合理性）
STAGES: list[tuple[str, str]] = [
    ("NC", "认知正常：菌群多样性与短链脂肪酸生成能力最高，作为比较基线 [27][30]"),
    ("SCS", "主观认知下降：组成已有偏移，SCD 组出现阶段特有的 Anaerosacchariphilus、"
            "Anaerobutyricum 等 [29]"),
    ("SCD", "可疑认知障碍：血浆 LPS 与 CRP 已升高，提示肠屏障改变早于痴呆 [17]"),
    ("MCI", "轻度认知障碍：Proteobacteria 下降最明显，菌群失衡与 IL-1β、NLRP3 相关 [26][28]"),
    ("AD", "阿尔茨海默症：Firmicutes 下降、Bacteroides/Megamonas 升高，"
           "菌群变化幅度大于前驱期 [27][28]"),
]

# ------------------------------------------------------------ 八个问题
QUESTIONS: list[dict] = [
    dict(
        n=1, q="抗菌肽与 AD 到底有什么关联？",
        a="Aβ 本身就是一种抗菌肽，脑内还有一类宿主抗菌肽（LL-37、β-防御素、CAP37 等）在 AD 中显示"
          "上调，两者同属先天免疫效应分子；因此“抗菌肽”可以同时指 Aβ 与 LL-37 这类分子，"
          "本课题研究的是第三类——微生物基因组编码的抗菌肽。",
        strength="强", refs=[1, 2, 3, 4, 6, 8, 9, 10],
        evidence=[
            "Aβ 对 12 种临床相关微生物中的 8 种有活性，对其中 7 种不弱于经典抗菌肽 LL-37；"
            "AD 脑匀浆的抗菌活性显著高于同龄对照，且可被抗 Aβ 抗体清除 [1]。",
            "β-防御素-1 在 AD 脑内表达上调 [8]；CAP37 在 AD 皮层锥体神经元中增多，且 TNF-α 与 Aβ "
            "本身即可诱导其表达 [9]；LL-37 在 AD 脑内升高并与病程进展相关 [6][7]。",
            "多种抗菌肽在 AD 唾液、血清与脑脊液中升高，被作为潜在的诊断标志物研究 [10]。",
        ],
        boundary="以上多为组织或体液层面的关联，不能直接推出因果；宿主来源抗菌肽与 Aβ 的证据强，"
                 "微生物源抗菌肽在 AD 中的变化尚无直接报道，这正是本课题要做的事。",
    ),
    dict(
        n=2, q="AD 与感染的关联（有没有病原体进入脑内）",
        a="有多类病原体与 AD 脑组织共定位的报道，且细菌载量与内毒素水平在 AD 组更高；"
          "感染负担的人群归因分数估计在 13%—52% 量级。",
        strength="中—强", refs=[4, 5, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        evidence=[
            "16S 测序显示 AD 脑组织的细菌读段为对照的 5—10 倍 [12]；AD 脑 LPS 为对照的 2—3 倍，"
            "血 LPS 约 3 倍，且与斑块、神经元、寡突胶质细胞共定位 [11]。",
            "特定病原体：肺炎衣原体在 AD 脑 89% 阳性、对照 5% [13]；牙龈卟啉单胞菌及其牙龈蛋白酶"
            "在 AD 脑中检出且具神经毒性 [14]；HSV-1 感染可上调分泌酶、促进 Aβ 累积 [5]，"
            "并在动物与三维人神经培养中加速 Aβ 沉积 [4]。",
            "定量估计：HSV-1、慢性牙周炎、肺炎衣原体的人群归因分数分别约 13.5%、19.4%、31%，"
            "三者合计 31%—51.9% [16]。",
            "外周侧：SCD 患者血浆 LPS 与 CRP 已升高 [17]，血浆 LPS/sCD14 与认知下降相关 [18]，"
            "肠通透性标志物 LBP 在前瞻队列中与 AD 风险相关 [19]。",
        ],
        boundary="病理与流行病学证据多为关联；部分病原体的检出在不同队列间难以复现，"
                 "文中以“关联/线索”表述，不使用“导致”。",
    ),
    dict(
        n=3, q="抗菌活性为什么可以预测（有没有先例）",
        a="有。从宏基因组小开放阅读框出发、用深度学习预测并体外验证抗菌活性，已经是可复现的技术路线，"
          "并且是同一套流程的完整先例。",
        strength="强（方法学）", refs=[21, 22, 23, 24, 25],
        evidence=[
            "从人肠道宏基因组挖掘的候选肽中，11 条在体外与小鼠肺炎模型中显示活性，对耐药革兰阴性菌"
            "有效，细菌负荷下降十倍以上 [21]。",
            "AMPSphere 从全球微生物组预测出 863 498 条非冗余候选抗菌肽，构成可检索的公共资源 [22]；"
            "Macrel 提供了从基因组/宏基因组直接预测抗菌肽的流水线 [23]。",
            "与本课题最接近的先例：从粪便宏基因组用深度学习挖掘抗菌肽，再以宏蛋白组互证、分子动力学"
            "筛选、化学合成与活性验证，最终确证 2 条具广谱活性 [24]。",
        ],
        boundary="预测只是候选筛选，最终必须回到实验；本课题的预测结果同样以三模型共识 + 表达证据 + "
                 "抑菌实验逐层约束。",
    ),
    dict(
        n=4, q="AD 特异性特有抗菌肽为什么能与 AD 关联",
        a="因为肠道菌群本身随认知阶段呈梯度变化：AD 组的菌群组成与参照组不同，且物种层面的特征"
          "可以区分 AD；由这些菌群编码的抗菌肽因此会出现“只在 AD 组出现”的组成差异，"
          "这正是 AD 特异性特有肽的生物学基础。",
        strength="中", refs=[17, 26, 27, 28, 29, 30, 59, 60],
        evidence=[
            "按认知阶段分层的研究显示 Proteobacteria 在 MCI 阶段下降最明显，Firmicutes 在 AD 阶段"
            "下降更明显，Fusobacteria、Lactobacillus 呈阶段梯度 [28]。",
            "SCD、MCI、AD 三组的菌群网络结构不同，SCD 组存在阶段特有的菌属 [29]；"
            "菌群失衡在前驱期即已开始 [30]。",
            "促炎菌富集与脑内淀粉样沉积、外周 IL-1β 等炎症指标相关 [26]；AD 组菌群变化幅度大于"
            "MCI 组 [27]。",
            "多组学分析显示 AD 组富集 Akkermansia massiliensis、Alistipes onderdonkii 等菌种，"
            "物种层面特征可区分 AD 并与 MMSE 负相关 [59]；16S 元分析显示 AD 谱系有 12 个属显著改变、"
            "可作为 AD 相关菌群特征 [60]。",
        ],
        boundary="两点限定：① 目前公开文献里没有“AD 组特有抗菌肽”的直接报道——菌群层面的 AD 组"
                 "特异特征有据（[59][60]），肽层面的只有阶段差异与宿主抗菌肽升高；AD 特异性特有肽的"
                 "判定是本课题的计算结果，必须由表达证据与实验支持；② 判定为计算层面产物，"
                 "本课题以宏蛋白组表达证据做二次去重来降低假阳性。",
    ),
    dict(
        n=5, q="筛选出的抗菌肽是不是导致 AD 的那一侧（致病方向）？",
        a="本课题按“致病方向”设计与验证：考察候选抗菌肽是否像文献中的 LL-37 与细菌淀粉样蛋白那样，"
          "促进 Aβ 的成核与聚集、生成毒性更强的聚集体、放大神经炎症，从而推动 AD 病理。"
          "抗菌活性是这些肽的本职功能（第 6 问），不作为“抑制 AD”的结论。",
        strength="中—强（致病方向在细菌淀粉样蛋白、内毒素与 LL-37 上都有体内外证据；"
                 "但针对本课题筛选出的候选肽，仍属待验证假设）",
        refs=[6, 42, 47, 48, 49, 50, 51, 52, 53, 54, 55],
        evidence=[
            "微生物来源的淀粉样蛋白有直接的致病先例：FapC 片段作为催化表面加速 Aβ 纤维化，"
            "并在斑马鱼幼虫与成鱼中加重 Aβ 沉积、突触丢失与行为损害，绿脓杆菌生物膜片段同样加速 "
            "[47]；CsgA 的 steric zipper 与人类病理纤维同构，CsgA 种子加速 Aβ1—40 纤维化 [48]；"
            "人粪便来源的生物膜相关淀粉样蛋白在 AD/PD 患者中更丰富并参与 Aβ 成核 [58]。",
            "内毒素这一侧：LPS 缩短成核滞后期、加速 Aβ 纤维化 [49]；单次腹腔注射 LPS 后，"
            "大鼠脑内可溶性 Aβ 升高，皮层 Aβ 斑块与 p-tau 在 7—9 天内进行性增加，对照无斑块 [50]。",
            "宿主抗菌肽这一侧：LL-37 经 CLIC1 引起小胶质过度活化，小鼠与猴模型出现 Aβ42 升高、"
            "tau 病理与脑萎缩 [6]；LL-37 及其片段与 Aβ40 形成异源寡聚体与团簇，在抑制纤维的同时"
            "生成毒性更强的聚集体 [53]；AD 患者血清与脑脊液中 hBD-2、HNP1-3 升高，作者据此提出"
            "防御素可能参与 AD 的发生 [55]；血清高 LL-37 者两年内 MMSE 下降 ≥3 分的比值比为 2.11 [42]。",
            "通路这一侧：AD 模型小鼠肠内 curli 与 TLR2 升高、与 PGP9.5 共定位并伴迷走神经激活，"
            "构成肠—迷走—脑通路 [51]；FapC 与 CsgA 混合种子把人源小胶质“预激活”，把 Aβ 压成更小"
            "团块并诱发促炎表型，对旁观神经元产生毒性 [52]；综述把这一整体过程概括为“同一枚硬币的"
            "两面”，在慢性感染与菌群失调条件下转向致病 [54]。",
        ],
        boundary="方向不能一概而论，模拟也不等于因果：同一家族中 HNP-1、NP-3A 在等摩尔比下完全"
                 "抑制 Aβ 纤维化 [56]；LL-37 在某些体系中抑制长纤维却把平衡推向低分子量寡聚体 [57]。"
                 "因此本课题主张的是“候选肽的致病方向值得优先验证”，而非已证明因果。",
    ),
    dict(
        n=6, q="抗菌活性（抗感染）这一侧有哪些证据？（本职功能）",
        a="体外、体内与机制三条证据链都有：抗菌活性测定、感染模型的存活优势，以及纤维网捕获病原体"
          "的形态学证据。这一侧说明抗菌肽的来路与本职功能，不构成“抑制 AD”的结论——本课题的"
          "分子动力学与机制分析走的是第 5 问的致病方向。",
        strength="强", refs=[1, 3, 4, 20, 45],
        evidence=[
            "5×FAD 小鼠（持续表达人 Aβ）颅内接种鼠伤寒沙门菌后存活时间显著长于野生型，"
            "临床评分更低、体重下降更少、细菌负荷更低；寡聚化是抗菌活性所必需 [1][3]。",
            "Aβ 寡聚体结合疱疹病毒表面糖蛋白，30 分钟内形成纤维网把病毒颗粒捕获，显著降低感染性"
            "[4]；机制综述归纳为抗黏附、调理素、纤维网捕获与生物膜破坏四种方式 [20]。",
        ],
        boundary="这些是 Aβ 的证据；微生物源抗菌肽是否同样参与，需要本课题的抑菌实验来回答。"
                 "抑菌结果是“有抗菌活性”的证据，与致病方向的验证并行，二者不互相替代。",
    ),
    dict(
        n=7, q="为什么 AD 组更多（和炎症是什么关系）",
        a="存在一个自增强的炎症—Aβ/抗菌肽环：菌群失衡与肠屏障通透性升高使内毒素长期入血，"
          "经 TLR4/NF-κB 升高促炎因子，促炎因子又上调 Aβ 与抗菌肽的表达，聚集后的 Aβ 再激活"
          "小胶质细胞产生更多炎症介质。",
        strength="中—强", refs=[6, 9, 11, 17, 42, 46],
        evidence=[
            "AD 脑与血中 LPS 升高，LPS 经 TLR4/CD14 触发 NF-κB 与促炎因子，促炎因子再上调 Aβ 生成"
            "[11]；菌群失衡—LPS—TLR4/NF-κB—Aβ 构成前馈环，且 IL-6/CRP 与临床分期相关 [46]。",
            "炎症直接上调抗菌肽的证据：TNF-α 与 Aβ 可诱导神经元表达 CAP37 [9]；LL-37 本身"
            "“在感染与炎症后升高”，并在 AD 脑内与病程进展相关 [6]；血清高 LL-37 与更快的认知下降、"
            "更高的 NfL/pTau181 增速相关 [42]。",
            "上游驱动：SCD 阶段血浆 LPS 与 CRP 已升高 [17]，说明炎症放大在痴呆前已经存在。",
        ],
        boundary="“为什么更多”目前是用多条独立证据拼出的机制假设，尚未在同一个队列中完整验证。",
    ),
    dict(
        n=8, q="正常人与 AD，谁的抗菌肽更多？",
        a="总体方向是 AD 侧更高，但并非所有抗菌肽都升高——乳铁蛋白、铁调素等在 AD 中是下降的；"
          "回答这个问题必须说清三点：哪一种肽、哪个部位、哪个阶段。",
        strength="中（方向一致，但有例外）", refs=[1, 6, 8, 9, 10, 42, 43, 44],
        evidence=[
            "升高的：LL-37（脑、血清）、β-防御素-1/2、α-防御素 1—4、CAP37、Aβ42 本身"
            "[1][6][8][9][10][42]。",
            "降低的：唾液乳铁蛋白在 MCI-PET+ 与 AD 中显著低于对照（3.6—3.8 vs 7.7 μg/mL），"
            "并被当作诊断标志物 [43][44]；铁调素、胱抑素 C 在 AD 中亦有下降报道 [10]。",
            "所以实验室里的方向是“多数上调、少数下调”，而不是“全部更多”；本课题给出的正是"
            "按阶段划分的微生物源抗菌肽差异，用于补上这一层的空白。",
        ],
        boundary="不要把“AD 更多”当作结论性的普适命题；在论文中按分子、部位、阶段三层分别表述。",
    ),
]

# --------------------------------------------------- 分子动力学文献一览
MD_TABLE: list[tuple[str, str, str]] = [
    # ---- 致病方向的先例：本课题的动力学要验证的正是这一类作用 ----
    ("致病先例：细菌淀粉样蛋白 FapC", "FapC 片段作为催化表面加速 Aβ 纤维化，斑马鱼幼虫与成鱼中"
                                      "加重 Aβ 沉积、突触丢失与行为损害；绿脓杆菌生物膜片段同样加速",
     "[47]"),
    ("致病先例：细菌淀粉样蛋白 CsgA", "CsgA 的 steric zipper 与人类病理纤维同构，CsgA 种子"
                                      "加速 Aβ1—40 纤维化", "[48]"),
    ("致病先例：内毒素 LPS", "缩短成核滞后期、加速 Aβ 纤维化 [49]；LPS 内毒素血症大鼠 7—9 天内"
                             "出现皮层 Aβ 斑块与 p-tau，对照无斑块 [50]", "[49][50]"),
    ("致病先例：LL-37", "与 Aβ40 形成异源寡聚体与团簇，抑制纤维的同时生成毒性更强的聚集体 [53]；"
                        "经 CLIC1 造成小鼠与猴模型的 Aβ 升高、tau 病理与脑萎缩 [6]", "[6][53]"),
    ("致病先例：小胶质被预激活", "FapC 与 CsgA 混合种子在人源小胶质与脑类器官中把 Aβ 压成更小"
                                 "团块、诱发促炎表型，对旁观神经元产生毒性 [52]", "[52]"),
    # ---- 本课题参照的 AChE–Aβ 复合物模拟 ----
    ("AChE–Aβ 复合物（本课题参照）", "1 μs 全原子模拟，复合物稳定；Aβ 主要停留区段 344—361，"
                                     "紧邻 PAS 且不受双位点抑制剂位阻", "[31]"),
    ("AChE 促聚集的结构基序", "对接给出四处结合位点；靠近 PAS 的疏水肽段可掺入生长中的纤维，"
                              "Kd≈184 μM，以疏水作用为主", "[32]"),
    ("PAS 与成核机制", "PAS 抑制剂丙锭可阻断 AChE 诱导的聚集，催化位点抑制剂无效；"
                       "高负电荷密度使 Aβ 由 α-螺旋转向 β-发夹——PAS 是可被候选肽介入的成核界面",
     "[33][34]"),
    ("丁酰胆碱酯酶的反向作用", "与 AChE 相反，BChE 结合可溶性 Aβ 并延缓纤维形成，"
                               "说明界面性质决定方向", "[35]"),
    ("LL-37 与淀粉样肽（方向依赖）", "全原子离散动力学：疏水与 π–π 作用为主，结合淀粉样生成区、"
                                     "封堵纤维延伸面 [38]；LL-37 自身亦可经盐桥形成纤维样聚集体 [39]",
     "[38][39]"),
    ("抗菌肽类分子与 Aβ42（反例）", "多粘菌素 B 与 Aβ 单体/原纤维的对接与动力学，稳定 α-螺旋、"
                                    "破坏 β-折叠，并用凝胶电泳验证", "[40]"),
    ("短肽抑制剂的筛选（反例）", "912 条五肽虚拟筛选 + MM-PBSA + MD，命中肽可破坏 Asp23—Lys28 "
                                 "盐桥、降低 β-折叠含量", "[41]"),
    ("交叉成核的通用框架", "结构兼容、定向成核不对称、表面催化三条机制；"
                           "并提出病原—淀粉样正反馈环", "[36][37]"),
    ("本课题的动力学验证设计（致病方向）",
     "对接 + 动力学考察候选肽在 AChE–Aβ 界面（PAS 与 344—361 区段）与 Aβ 淀粉样生成区的结合模式、"
     "MM-PBSA 结合自由能、β-折叠含量、D23—K28 盐桥与氢键网络、纤维延伸面的结合方式；"
     "据此判断 AD 特异性特有肽与 AD 的关联方向（是否促进成核与聚集、是否把产物推向更毒的"
     "寡聚体），再对结果指向同一方向的候选肽做 ThT 聚集动力学、电镜形态与"
     "细胞毒性/炎症因子验证", "本课题"),
]

# ------------------------------------------------------------ PPT 用短句
SLIDE_SHORT = {
    1: "Aβ 本身即抗菌肽；LL-37、β-防御素-1、CAP37 等在 AD 中上调",
    2: "AD 脑细菌读段 5—10 倍、LPS 2—3 倍；衣原体 89% vs 5%；感染负担归因 13%—52%",
    3: "宏基因组 + 深度学习挖抗菌肽已有完整先例（含宏蛋白组互证 + 动力学 + 合成验证）",
    4: "AD 组的菌种与功能特征可区分 AD；由这些菌群编码的肽在 AD 组更可能出现特有组成",
    5: "致病方向：FapC/CsgA 加速 Aβ 纤维化、LPS 促斑块与 p-tau、LL-37 经 CLIC1 致 AD 样病理",
    6: "抗菌活性是本职功能（5×FAD 小鼠抗感染更久、纤维网捕获病毒），不作为“抑制 AD”的结论",
    7: "LPS→TLR4/NF-κB→促炎因子→Aβ 与抗菌肽；TNF-α/Aβ 可诱导 CAP37 表达",
    8: "多数上调（LL-37、防御素、CAP37），少数下调（乳铁蛋白、铁调素）——分肽、分部位、分阶段",
}
