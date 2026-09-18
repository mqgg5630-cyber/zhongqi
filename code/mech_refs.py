#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mech_refs.py - 机制解释部分的文献库（唯一数据源）。

`code/make_mech_doc.py`（机制说明 docx）与 `code/make_ppt_mech.py`（PPT 机制页）
都从这里取文献与结论，避免两处口径不一致。

八个问题（按老师的提问顺序）：
    1. 抗菌肽与 AD 的关联        5. 促进 AD 发生还是抑制感染
    2. AD 与感染的关联           6. 抑制感染的证据
    3. 抗菌活性为什么可以预测     7. 为什么 AD 组更多（炎症的关系）
    4. AD 组特有抗菌肽的合理性    8. 正常人 vs AD 谁更多（方向与例外）
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
        n=4, q="AD 组特有抗菌肽为什么能与 AD 关联",
        a="因为肠道菌群本身随认知阶段呈梯度变化，同一队列内不同阶段的菌群组成不同，"
          "由这些菌群编码的抗菌肽自然会出现阶段特异性的组成差异；这正是“阶段特有肽”的生物学基础。",
        strength="中", refs=[17, 26, 27, 28, 29, 30],
        evidence=[
            "按认知阶段分层的研究显示 Proteobacteria 在 MCI 阶段下降最明显，Firmicutes 在 AD 阶段"
            "下降更明显，Fusobacteria、Lactobacillus 呈阶段梯度 [28]。",
            "SCD、MCI、AD 三组的菌群网络结构不同，SCD 组存在阶段特有的菌属 [29]；"
            "菌群失衡在前驱期即已开始 [30]。",
            "促炎菌富集与脑内淀粉样沉积、外周 IL-1β 等炎症指标相关 [26]；AD 组菌群变化幅度大于"
            "MCI 组 [27]。",
        ],
        boundary="“阶段特有肽”目前是计算层面的产物，其生物学功能需要表达证据与实验支持；"
                 "本课题以宏蛋白组表达证据做二次去重来降低假阳性。",
    ),
    dict(
        n=5, q="抗菌肽是促进 AD 发生，还是抑制感染？",
        a="两者同时成立，取决于浓度、聚集状态与所处部位——这正是“双刃剑”。低浓度、寡聚化时以抗菌"
          "为主；长期过量时经成核与炎症通路推动 AD 病理。",
        strength="中—强（两种作用均有实验证据）", refs=[1, 2, 3, 4, 6, 9, 20, 36, 37, 38, 45],
        evidence=[
            "抗菌一侧：Aβ 对细菌、真菌、病毒均有活性，纤维化本身参与捕获病原体 [1][4][20]；"
            "Aβ 寡聚体可解聚并抑制细菌淀粉样蛋白与生物膜 [45]。",
            "致病一侧：LL-37 经 CLIC1 引起小胶质过度活化与神经炎症，小鼠与猴模型中可致 Aβ 升高、"
            "tau 病理与脑萎缩 [6]；血清 LL-37 高者两年内 MMSE 下降的比值比为 2.11 [42]。"
            "CAP37 可由 Aβ 与 TNF-α 诱导，参与神经炎症调节 [9]。",
            "分子机制：抗菌肽与淀粉样肽存在交叉成核，β-折叠结构兼容时既可能加速也可能抑制纤维形成，"
            "方向由序列与界面决定 [36][37][38]。",
        ],
        boundary="方向不能一概而论：同一种肽在不同浓度与环境下作用相反，本课题只给候选与优先序，"
                 "不做“促进/抑制”的单向断言。",
    ),
    dict(
        n=6, q="抑制感染这一侧有哪些证据",
        a="体外、体内与机制三条证据链都有：抗菌活性测定、感染模型的存活优势，以及纤维网捕获病原体"
          "的形态学证据。",
        strength="强", refs=[1, 3, 4, 20, 45],
        evidence=[
            "5×FAD 小鼠（持续表达人 Aβ）颅内接种鼠伤寒沙门菌后存活时间显著长于野生型，"
            "临床评分更低、体重下降更少、细菌负荷更低；寡聚化是抗菌活性所必需 [1][3]。",
            "Aβ 寡聚体结合疱疹病毒表面糖蛋白，30 分钟内形成纤维网把病毒颗粒捕获，显著降低感染性"
            "[4]；机制综述归纳为抗黏附、调理素、纤维网捕获与生物膜破坏四种方式 [20]。",
        ],
        boundary="这些是 Aβ 的证据；微生物源抗菌肽是否同样参与，需要本课题的抑菌实验来回答。",
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
    ("AChE–Aβ 复合物（本课题参照）", "1 μs 全原子模拟，复合物稳定；Aβ 主要停留区段 344—361，"
                                     "紧邻 PAS 且不受双位点抑制剂位阻", "[31]"),
    ("AChE 促聚集的结构基序", "对接给出四处结合位点；靠近 PAS 的疏水肽段可掺入生长中的纤维，"
                              "Kd≈184 μM，以疏水作用为主", "[32]"),
    ("PAS 与成核机制", "PAS 抑制剂丙锭可阻断 AChE 诱导的聚集，催化位点抑制剂无效；"
                       "高负电荷密度使 Aβ 由 α-螺旋转向 β-发夹", "[33][34]"),
    ("丁酰胆碱酯酶的反向作用", "与 AChE 相反，BChE 结合可溶性 Aβ 并延缓纤维形成，"
                               "说明界面性质决定方向", "[35]"),
    ("LL-37 与淀粉样肽", "全原子离散动力学：疏水与 π–π 作用为主，结合淀粉样生成区、"
                         "封堵纤维延伸面 [38]；LL-37 自身亦可经盐桥形成纤维样聚集体 [39]", "[38][39]"),
    ("抗菌肽类分子与 Aβ42", "多粘菌素 B 与 Aβ 单体/原纤维的对接与动力学，稳定 α-螺旋、"
                             "破坏 β-折叠，并用凝胶电泳验证", "[40]"),
    ("短肽抑制剂的筛选", "912 条五肽虚拟筛选 + MM-PBSA + MD，命中肽可破坏 Asp23—Lys28 盐桥、"
                         "降低 β-折叠含量", "[41]"),
    ("交叉成核的通用框架", "结构兼容、定向成核不对称、表面催化三条机制；"
                           "并提出病原—淀粉样正反馈环", "[36][37]"),
]

# ------------------------------------------------------------ PPT 用短句
SLIDE_SHORT = {
    1: "Aβ 本身即抗菌肽；LL-37、β-防御素-1、CAP37 等在 AD 中上调",
    2: "AD 脑细菌读段 5—10 倍、LPS 2—3 倍；衣原体 89% vs 5%；感染负担归因 13%—52%",
    3: "宏基因组 + 深度学习挖抗菌肽已有完整先例（含宏蛋白组互证 + 动力学 + 合成验证）",
    4: "菌群随认知阶段梯度变化：Proteobacteria 先在 MCI 降，Firmicutes 在 AD 降",
    5: "低浓度抗菌、长期过量致病：LL-37 经 CLIC1 致小胶质活化，Aβ 捕获病原体",
    6: "5×FAD 小鼠抗感染存活更久；Aβ 纤维网 30 分钟捕获疱疹病毒；寡聚化为活性必需",
    7: "LPS→TLR4/NF-κB→促炎因子→Aβ 与抗菌肽；TNF-α/Aβ 可诱导 CAP37 表达",
    8: "多数上调（LL-37、防御素、CAP37），少数下调（乳铁蛋白、铁调素）——分肽、分部位、分阶段",
}
