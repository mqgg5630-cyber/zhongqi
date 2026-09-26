# -*- coding: utf-8 -*-
"""Integrated content: eight teacher questions + corrected AMP--AD linkage.

The user's supplied supplement is integrated with the previous candidate-AMP
interpretation framework. Claims are deliberately separated into host AMP/Aβ
evidence, microbiome association, computation, and causal validation.
"""
from triq_refs import REF as BASE_REF

REF_EXTRA = {
    "a_beta_innate_2024": "Mechanistic insights into the role of amyloid-beta in innate immunity. Scientific Reports. 2024;14:55423. DOI: 10.1038/s41598-024-55423-9.",
    "crosstalk_2024": "Zhang Y, et al. Exploring pathological link between antimicrobial and amyloid peptides. Chemical Society Reviews. 2024. DOI: 10.1039/D3CS00878A.",
    "delorenzi2017_full": "De Lorenzi E, Chiari M, Colombo R, et al. Evidence that the human innate immune peptide LL-37 may be a binding partner of amyloid-beta and inhibitor of fibril assembly. Journal of Alzheimer’s Disease. 2017;59(4):1213-1226. DOI: 10.3233/JAD-170223; PMID: 28731438.",
    "fmt_amp2025_exact": "Detection of antimicrobial peptides from fecal samples of FMT donors using deep learning. 2025. PMC12560166. Workflow includes metagenomic mining, metaproteomic cross-validation and molecular dynamics.",
    "chen2022_clic1": "Chen X, Deng S, Wang W, et al. Human antimicrobial peptide LL-37 contributes to Alzheimer’s disease progression. Molecular Psychiatry. 2022;27:4790-4799. DOI: 10.1038/s41380-022-01790-6; PMID: 36138130.",
    "ma2022_exact": "Ma Y, Guo Z, Xia B, et al. Identification of antimicrobial peptides from the human gut microbiome using deep learning. Nature Biotechnology. 2022;40(6):921-931. DOI: 10.1038/s41587-022-01226-0; PMID: 35241840.",
    "wan2024_ml": "Wan F, Wong F, Collins JJ, et al. Machine learning for antimicrobial peptide identification and design. Nature Reviews Bioengineering. 2024;2:392-407. DOI: 10.1038/s44222-024-00152-x.",
    "moir2018": "Moir RD, Lathe R, Tanzi RE. The antimicrobial protection hypothesis of Alzheimer’s disease. Alzheimer’s & Dementia. 2018;14(12):1602-1614. DOI: 10.1016/j.jalz.2018.06.3040.",
    "eimer2018": "Eimer WA, Vijaya Kumar DK, Navalpur Shanmugam NK, et al. Alzheimer’s disease-associated β-amyloid is rapidly seeded by Herpesviridae to protect against brain infection. Neuron. 2018;99(1):56-63. DOI: 10.1016/j.neuron.2018.06.030.",
    "wozniak2007": "Wozniak MA, Itzhaki RF, Shipley SJ, Dobson CB. Herpes simplex virus infection causes cellular β-amyloid accumulation and secretase upregulation. Neuroscience Letters. 2007;429(2-3):95-100. DOI: 10.1016/j.neulet.2007.09.077.",
    "williams2013": "Williams WM, Torres S, Siedlak SL, et al. Antimicrobial peptide β-defensin-1 expression is upregulated in Alzheimer’s brain. Journal of Neuroinflammation. 2013;10:127. DOI: 10.1186/1742-2094-10-127.",
    "brock2015": "Brock DG, Loewy A, Bloomfield S, et al. The antimicrobial protein CAP37 is upregulated in pyramidal neurons during Alzheimer’s disease. Histochemistry and Cell Biology. 2015;144(5):447-460. DOI: 10.1007/s00418-015-1347-x.",
    "amp_ad_review2022": "Antimicrobial peptides in the pathogenesis of Alzheimer’s disease: implications for diagnosis and treatment. Antibiotics. 2022;11(6):726. DOI: 10.3390/antibiotics11060726.",
    "zhan2018_lps": "Zhan X, Stamova B, Sharp FR. Lipopolysaccharide associates with amyloid plaques, neurons and oligodendrocytes in Alzheimer’s disease brain. Frontiers in Aging Neuroscience. 2018;10:42. DOI: 10.3389/fnagi.2018.00042.",
    "emery2017": "Emery DC, Shoemark DK, Batstone TE, et al. 16S rRNA next generation sequencing analysis shows bacteria in Alzheimer’s post-mortem brain. Frontiers in Aging Neuroscience. 2017;9:195. DOI: 10.3389/fnagi.2017.00195.",
    "balin1998": "Balin BJ, Gérard HC, Arking EJ, et al. Identification and localization of Chlamydia pneumoniae in the Alzheimer’s brain. Medical Microbiology and Immunology. 1998;187(1):23-42. DOI: 10.1007/s004300050071.",
    "dominy2019": "Dominy SS, Lynch C, Ermini F, et al. Porphyromonas gingivalis in Alzheimer’s disease brains: evidence for disease causation and treatment with small-molecule inhibitors. Science Advances. 2019;5(1):eaau3333. DOI: 10.1126/sciadv.aau3333.",
    "infectious_review2025": "Alzheimer’s disease and infectious agents: a comprehensive review of pathogenic mechanisms and microRNA roles. 2025. PMID: 39840010. Verify final journal metadata before thesis submission.",
    "infectious_burden2026": "Beyond association: a quantitative analysis of the infectious burden in Alzheimer’s disease. 2026. PMC13291386. Population-attributable estimates should not be interpreted as individual causality.",
    "prodromal_barrier2021": "Preoperative microbiomes and intestinal barrier function can differentiate prodromal Alzheimer’s disease in elderly patients. Frontiers in Cellular and Infection Microbiology. 2021. PMC8044800.",
    "gut_permeability2021": "Gut permeability and cognitive decline: a pilot investigation in the Northern Manhattan Study. 2021. PMC8186438.",
    "lbp_ad2024": "Lipopolysaccharide-binding protein and Alzheimer’s disease risk. Frontiers in Neurology. 2024;15:1408220. DOI: 10.3389/fneur.2024.1408220.",
    "amyloid_innate2026": "Amyloid-β as an effector of innate immunity: pathological or preventative? Infection and Immunity. 2026. DOI: 10.1128/iai.00085-26. Verify final metadata before submission.",
    "stage_meta2026": "The correlation and gut microbial characteristics in the whole spectrum of Alzheimer’s disease: a systematic review and meta-analysis. Frontiers in Neuroscience. 2026. DOI: 10.3389/fnins.2026.1775002.",
    "stage_network2025": "Distinct gut microbiota profiles and network properties in older individuals with subjective cognitive decline, mild cognitive impairment, and Alzheimer’s disease. Alzheimer’s Research & Therapy. 2025. DOI: 10.1186/s13195-025-01820-9.",
    "meta_review2023": "Gut microbiome dysbiosis in Alzheimer’s disease and mild cognitive impairment: a systematic review and meta-analysis. PLoS ONE. 2023;18(5):e0285346. DOI: 10.1371/journal.pone.0285346.",
    "ache_md2020": "Atanasova M, Dimitrov I, Ivanov S. Molecular dynamics simulations of acetylcholinesterase-beta-amyloid peptide complex. Cybernetics and Information Technologies. 2020;20(6):140-154. DOI: 10.2478/cait-2020-0068.",
    "deferrari2001": "De Ferrari GV, Canales MA, Shin I, et al. A structural motif of acetylcholinesterase that promotes amyloid beta-peptide fibril formation. Biochemistry. 2001;40(35):10447-10457. DOI: 10.1021/bi0101392.",
    "inestrosa2008": "Inestrosa NC, Dinamarca MC, Alvarez A. Amyloid-cholinesterase interactions. FEBS Journal. 2008;275(4):625-632. DOI: 10.1111/j.1742-4658.2007.06238.x.",
    "pas_2019": "A new motif in the N-terminal of acetylcholinesterase triggers amyloid-beta aggregation and deposition. 2019. PMC6493010. Verify final bibliographic record before submission.",
    "rees2006": "Rees T, Hammond PI, Soreq H, Younkin S, Brimijoin S. Butyrylcholinesterase attenuates amyloid fibril formation in vitro. PNAS. 2006;103(23):8783-8788. DOI: 10.1073/pnas.0602922103.",
    "crossseed2026": "Zheng J, et al. Antimicrobial peptides as cross-seeding modulators at the neurodegenerative-infectious interface. Research. 2026. DOI: 10.34133/research.1149. Verify final metadata before submission.",
    "ll37_membrane2016": "Membrane core-specific antimicrobial action of cathelicidin LL-37 peptide switches between pore and nanofibre formation. Scientific Reports. 2016;6:38184. DOI: 10.1038/srep38184.",
    "polymyxin2025": "Polymyxin-B as a novel inhibitor of amyloid beta aggregation: computational insights and experimental validation. Journal of Molecular Biology. 2025. Verify final bibliographic record before submission.",
    "pentapeptide2023": "Identification of new pentapeptides as potential inhibitors of amyloid-beta42 aggregation using virtual screening and molecular dynamics simulations. Journal of Molecular Graphics and Modelling. 2023. Verify final bibliographic record before submission.",
    "ll37_longitudinal2023": "Associations of serum antimicrobial peptide LL-37 with longitudinal cognitive decline and neurodegeneration among older adults with memory complaints. Journal of Alzheimer’s Disease. 2023. DOI: 10.3233/JAD-230007.",
    "lactoferrin2020": "Decreased salivary lactoferrin levels are specific to Alzheimer’s disease. EBioMedicine. 2020;57:102834. DOI: 10.1016/j.ebiom.2020.102834.",
    "lactoferrin2025": "Salivary lactoferrin levels decrease in Alzheimer’s disease patients at early stage. 2025. PMC11716888. Verify final metadata before submission.",
    "lps_axis2026": "Synergistic regulation of Alzheimer’s disease and intestinal barrier: the LPS-TLR4/NF-kB axis. 2026. PMC13539905. Verify final metadata before submission.",
    "fmt_amp2025_exact2": "Detection of antimicrobial peptides from fecal samples of FMT donors using deep learning. 2025. PMID: 41164228; PMC12560166. Workflow includes metagenomic mining, metaproteomic cross-validation and molecular dynamics.",
}

REF = dict(BASE_REF)
REF.update(REF_EXTRA)


def T(title, header, rows):
    return ("table", {"title": title, "header": header, "rows": rows})


BLOCKS = [
    ("h1", "整合说明：把“八个问题”与深度学习差异肽主线合在一起"),
    ("p", "本材料把中期检查补充材料的八个问题、AChE-Aβ 分子动力学依据、感染与肠道菌群证据，以及上一版对“差异肽不是自动等于致病肽”的纠偏合并。全文始终区分四类对象：宿主 AMP、Aβ、微生物基因组编码的 AMP、以及用于治疗的抑制性肽。你的研究主对象是第三类；前两类提供病理背景和机制模板，第四类只是候选功能方向。"),
    ("p", "修正版的一句话结论是：AD 相关的肠道菌群和屏障炎症变化，可能改变微生物源抗菌肽的组成与暴露；这些差异肽再通过菌群竞争、LPS/SCFA、肠屏障和免疫信号与 AD 病理建立关联。部分候选可能偏向风险样，部分可能偏向保护样，Aβ 或 AChE-PAS 只是高优先级候选的条件性分子验证，不是所有候选肽的统一结论。[[ma2022_exact,cryan2019,marizzoni2020,crosstalk_2024]]"),
    ("note", "证据纪律：文献中的宿主 AMP/Aβ 结果是背景证据；本课题的微生物源 AMP 差异和阶段特异性需要本课题数据；计算结果是候选与优先序；因果需要干预。"),
    T("表 1　七环逻辑链：证据强度和本课题位置", ["环节", "逻辑", "证据类型", "本课题能回答什么"], [
        ["1 AD 与感染/炎症相关", "感染、LPS、炎症信号与 AD 病理共现", "人群、组织、动物和综述证据", "不能由 AMP 预测单独证明"],
        ["2 宿主 Aβ/AMP 是先天免疫效应分子", "Aβ、LL-37、防御素等具有抗感染和免疫调节属性", "体外、组织和动物证据", "提供病理背景，不等于微生物 AMP"],
        ["3 肠道菌群/屏障改变", "肠漏、LPS、SCFA 和菌群网络连接肠与脑", "队列、动物和中介线索", "为微生物源 AMP 提供上游环境"],
        ["4 宏基因组产生短肽库", "ORF 翻译得到大量候选短肽", "计算方法", "可复现地建立候选全集"],
        ["5 深度学习筛 AMP", "Attention/LSTM/BERT 预测 AMP 特征", "模型和活性验证先例", "缩小候选空间，不判定 AD"],
        ["6 AD/健康差异与阶段特异", "不同阶段菌群编码肽的组成可能不同", "本课题核心分析", "筛选 AD 相关差异候选"],
        ["7 病理方向与因果", "风险样或保护样，最终需干预验证", "网络、MD/QM、细胞/动物", "提出优先级和可检验假设"],
    ]),

    ("h1", "一、逐条回答老师提出的八个问题"),
    ("h2", "问题 1：抗菌肽与 AD 到底有什么关联？"),
    ("p", "结论：Aβ 本身具有抗菌性质，AD 脑内还观察到 LL-37、β-防御素和 CAP37 等宿主 AMP 的表达或含量变化；你的课题进一步研究第三类，即肠道微生物基因组编码的 AMP 是否在 AD 与健康人群之间存在差异，以及这些差异能否通过肠-脑轴与病理过程建立联系。[[soscia2010,moir2018,kumar2016,williams2013,brock2015,chen2022_clic1,amp_ad_review2022]]"),
    ("b", "Aβ 对临床相关微生物具有抗菌活性，AD 脑匀浆的总抗菌活性高于同龄对照，并且抗 Aβ 抗体清除后活性降低。"),
    ("b", "宿主 AMP 的组织或体液变化可以作为先天免疫和炎症状态的背景证据，但不能直接替代微生物源 AMP 的差异结果。"),
    ("b", "本课题的创新衔接是：把宿主 AMP/Aβ 的病理背景，与宏基因组中预测得到的微生物源 AMP 差异联系起来。"),
    ("note", "边界：宿主 AMP 与微生物源 AMP 不是同一个数据对象；在没有真实候选表前，不能写“微生物源 AMP 已在 AD 中升高”。"),
    T("表 2　问题 1 的对象区分", ["对象", "来源", "在材料中的作用", "当前证据强度"], [
        ["Aβ", "宿主 APP 加工", "AD 病理对象，同时具有先天免疫属性", "相对强，但机制具有双向性"],
        ["LL-37/防御素/CAP37", "宿主细胞", "宿主 AMP 病理模板和炎症标志物", "组织/体液/动物证据"],
        ["微生物源候选 AMP", "肠道微生物 ORF", "本课题主要筛选对象", "等待本课题差异和表达结果"],
        ["设计的 Aβ 抑制肽", "合成或工程设计", "治疗性比较对象", "不是本课题首要目标"],
    ]),

    ("h2", "问题 2：AD 与感染的关联，有没有病原体进入脑内？"),
    ("p", "结论：多种病原体、细菌组分和外周感染负担曾在 AD 组织或队列中被报道，但不同队列的可重复性、污染控制和因果方向必须谨慎。更稳妥的表述是“病原体/内毒素与 AD 病理存在关联线索”，而不是所有 AD 都由病原体直接入脑导致。[[emery2017,zhan2018_lps,balin1998,dominy2019,wozniak2007,eimer2018,infectious_review2025]]"),
    ("b", "AD 脑组织中细菌读段、LPS 或特定病原体的检出差异，为感染—炎症假说提供线索；这些结果需要严格的阴性对照、死后间隔和批次控制。"),
    ("b", "HSV-1、牙龈卟啉单胞菌和肺炎衣原体等研究分别提出感染、分泌酶、Aβ 反应或神经炎症的可能路径。"),
    ("b", "人群归因分数是总体公共卫生估计，不是单个患者的病因概率；材料中的 13.5%、19.4% 和 31% 应在投稿前按原文核验。[[infectious_burden2026]]"),
    ("b", "外周 LPS、LBP、sCD14、CRP 和肠屏障指标把感染/菌群问题与脑病理连接起来，但仍然不能证明某条微生物 AMP 已进入脑内。[[prodromal_barrier2021,gut_permeability2021,lbp_ad2024]]"),
    ("note", "边界：感染证据可以解释为什么宿主免疫 AMP/Aβ 被诱导，却不能直接把所有微生物源 AMP 定性为致病因子。"),

    ("h2", "问题 3：抗菌活性为什么可以预测，有没有先例？"),
    ("p", "结论：有成熟先例。宏基因组短 ORF 翻译成肽库，再用深度学习预测 AMP，是可复现的候选发现路线；但预测输出是“具有 AMP 特征的候选”，不是“会导致 AD 的肽”。Ma 等从人类肠道宏基因组中筛出 2,349 条候选，合成 216 条后有 181 条显示抗菌活性，说明这一层方法能够有效缩小候选空间。[[ma2022_exact,macrel2020,amplify2022,ampsphere2024,fmt_amp2025_exact2,wan2024_ml]]"),
    ("b", "Attention、LSTM 和 BERT 可以从序列模式学习短肽特征，适合处理短序列和低同源新肽。"),
    ("b", "AMPSphere、Macrel 和 AMPlify 可作为候选扩展、交叉预测或新颖性过滤工具。"),
    ("b", "FMT 粪便流程进一步把宏蛋白组互证、分子动力学、化学合成与活性验证串起来，但它验证的是 AMP 功能，不是 AD 病理。"),
    ("note", "本课题的约束链应写成：三模型共识 → 差异分析 → 表达/宏蛋白组二次去重 → 代表性候选实验；不能把模型概率写成病理因果。"),
    T("表 3　深度学习输出如何被正确翻译", ["输出", "可以写", "不能写"], [
        ["AMP 模型概率高", "具有 AMP 序列特征", "会导致 AD"],
        ["模型 2/3 或 3/3 共识", "降低单模型假阳性", "已经有体内抗菌活性"],
        ["AD 组编码丰度升高", "与 AD 状态相关的候选", "脑内浓度升高"],
        ["宏蛋白组/肽组学检出", "表达或加工证据增强", "一定激活炎症"],
        ["MD 界面稳定", "值得实验验证的结构假说", "体内已结合并致病"],
    ]),

    ("h2", "问题 4：AD 组特有抗菌肽为什么能与 AD 关联？"),
    ("p", "结论：如果不同认知阶段的肠道菌群组成、丰度和网络结构存在梯度差异，那么这些菌群编码的 AMP 序列库也可能呈现阶段特异性。阶段特有肽首先是一个计算筛选产物，只有在表达、来源菌、生态网络和病理中介证据一致时，才可以升级为机制优先候选。[[vogt2017,cattaneo2017,zhuang2018,liu2019bai,li2019mci,stage_meta2026,stage_network2025,meta_review2023]]"),
    ("b", "按 NC、SCS、SCD、MCI、AD 分层，可观察菌群和 AMP 组成是否随认知状态改变；实际样本量和效应值应以本课题数据为准。"),
    ("b", "促炎菌、脑淀粉样沉积、IL-1β/NLRP3 或 LPS/SCFA 的关联可以作为中间层，而不是直接把阶段特有肽称为致病肽。"),
    ("b", "宏蛋白组或肽组学二次验证用于剔除“DNA 中存在、但没有表达或加工”的假阳性。"),
    ("note", "最稳妥的论文表达是“阶段特异性 AD-associated AMP candidate”，不是“AD 特异致病 AMP”。"),
    T("表 4　阶段特异性候选肽的判定层级", ["层级", "规则", "结论"], [
        ["组内出现", "组内检出率达到预设阈值", "阶段富集线索"],
        ["组间差异", "效应量、FDR、协变量校正稳定", "AD/健康差异候选"],
        ["病程趋势", "NC→SCS→SCD→MCI→AD 或病程分数趋势", "随病程变化候选"],
        ["表达支持", "宏蛋白组/肽组学或转录支持", "真实暴露可能性增强"],
        ["功能机制", "菌群、炎症、屏障、Aβ/BBB 多层支持", "机制优先候选"],
    ]),

    ("h2", "问题 5：抗菌肽是促进 AD，还是抑制感染？"),
    ("p", "结论：两种方向都可能，取决于肽的来源、浓度、聚集状态、盐度、作用部位和靶细胞。抗菌作用与病理作用不是逻辑矛盾：一个 AMP 可以在局部抑制感染，同时在长期过量、异常聚集或错误区室中放大炎症。[[soscia2010,kumar2016,chen2022_clic1,lee2015_ll37_neuroinf,crossseed2026,chemsocrev2024]]"),
    ("b", "保护/抗感染方向：Aβ 或其他 AMP 捕获病原体、干扰膜或生物膜；这说明先天免疫功能。[[amyloid_innate2026,a_beta_innate_2024]]"),
    ("b", "风险样方向：宿主 LL-37 可促进 CLIC1 膜转位、小胶质过度活化和神经炎症，提示 AMP 在特定环境下可能放大病理。[[chen2022_clic1]]"),
    ("b", "交叉成核方向：AMP 与淀粉样肽可能促进、抑制或重定向聚集；方向需要序列、构象和浓度特异性计算与实验。"),
    ("note", "对你的微生物源候选肽，应先分类为风险样、保护样或未知方向；不要预先把所有候选写成促进 AD，也不要预先全部写成抑制剂。"),
    T("表 5　双刃剑的判定读数", ["层面", "保护/抑制样", "风险/病理样", "本课题的计算读数"], [
        ["菌群", "抑制高风险菌并保留共生菌", "广谱破坏共生菌、增加 LPS", "膜选择性、生态模型"],
        ["炎症", "降低 TLR4/FPR2/NLRP3/NF-kB", "促进受体聚集、ROS、IL-6/TNF", "受体界面、网络/ODE"],
        ["Aβ", "减少有毒寡聚体或促进清除", "稳定有毒寡聚体或促进成核", "寡聚态、β-sheet、PMF"],
        ["BBB", "维持紧密连接或促进外排", "破坏屏障或增加有害通量", "膜 PMF、Papp、转运模型"],
    ]),

    ("h2", "问题 6：抑制感染这一侧有哪些证据？"),
    ("p", "结论：Aβ/宿主 AMP 的抗感染证据包括体外抗菌活性、感染动物模型存活优势、病原体捕获和生物膜/膜破坏机制。它们支持“先天免疫效应分子”背景，但微生物源候选 AMP 是否对 AD 有保护作用，需要本课题逐条验证。[[soscia2010,kumar2016,eimer2018,amyloid_innate2026]]"),
    ("b", "Aβ 对多种微生物有抗菌活性，Aβ 寡聚化与病原体捕获/膜作用有关。"),
    ("b", "Aβ 可与病毒表面或细菌淀粉样蛋白相互作用，形成捕获、聚集或生物膜抑制效应。"),
    ("b", "微生物源 AMP 需要用菌种/菌膜匹配的抑菌、膜通透性和选择性实验来验证，不可由宿主 Aβ 文献直接外推。"),
    ("note", "抑制感染是候选肽的一种功能方向，不等于治疗 AD；要进入 AD 保护性解释，还需屏障、炎症或 Aβ/Tau 连接。"),

    ("h2", "问题 7：为什么 AD 组可能更多，和炎症是什么关系？"),
    ("p", "结论需要改成“为什么部分 AD 相关 AMP 可能更多”，而不是“所有抗菌肽都更多”。一种可检验的正反馈模型是：菌群失衡和肠屏障通透性增加 → LPS/微生物组分入血 → TLR4/NF-kB 与促炎因子增加 → 宿主 AMP/Aβ 诱导和微胶质激活 → 病理性聚集与屏障损伤进一步放大。这个模型解释的是宿主 AMP 和部分微生物源 AMP 的可能方向，不能代替实际差异结果。[[zhan2018_lps,marizzoni2020,lps_axis2026,brock2015,chen2022_clic1,prodromal_barrier2021,gut_permeability2021]]"),
    ("b", "LPS、LBP、CRP、sCD14 和肠屏障标志物可以作为肠—血—脑中间层。"),
    ("b", "TNF-α 与 Aβ 可诱导 CAP37；LL-37 在感染/炎症和 AD 病理中具有宿主免疫模板意义。"),
    ("b", "血清 LL-37 与纵向认知下降的关联可以作为临床方向参考，但仍不是微生物源候选的因果证明。[[ll37_longitudinal2023]]"),
    ("note", "本课题可以补上的空白是：AD 与健康、以及 NC/SCS/SCD/MCI/AD 各阶段中，微生物源 AMP 的编码潜力和表达支持如何变化。"),
    T("表 6　“AD 组更多”应如何分层说", ["对象/部位", "可说的方向", "不能泛化的地方"], [
        ["部分宿主 AMP，脑/血/CSF", "若文献支持可说升高或与病程相关", "不是所有分子、所有标本都升高"],
        ["Aβ/脑匀浆总抗菌活性", "AD 侧可有升高证据", "不能等同于微生物源 AMP"],
        ["微生物源 AMP，肠道宏基因组", "方向由本课题差异分析决定", "目前不能用宿主文献替代"],
        ["乳铁蛋白等特定分子", "可能下降", "反例说明必须逐分子报告"],
    ]),

    ("h2", "问题 8：正常人与 AD，谁的抗菌肽更多？"),
    ("p", "正确回答不是一句“AD 更多”，而是“要说明是哪一种肽、哪个部位、哪个阶段”。文献中 LL-37、β-防御素、CAP37、Aβ 及部分唾液/血液 AMP 方向可偏向 AD 升高，但乳铁蛋白等分子可下降。你的论文要把宿主 AMP 文献方向与微生物源 AMP 的实测/计算结果分开。[[chen2022_clic1,williams2013,brock2015,amp_ad_review2022,lactoferrin2020,lactoferrin2025]]"),
    T("表 7　按分子、部位和证据类型回答“谁更多”", ["分子或指标", "文献方向", "部位/标本", "在本课题中如何使用"], [
        ["LL-37", "部分研究为升高/与病程相关", "脑、血清", "宿主 AMP 病理模板"],
        ["β/α-防御素", "部分组织/体液研究为升高", "脑、唾液、血液、CSF", "宿主防御背景"],
        ["CAP37", "AD 皮层神经元增加，可被炎症/ Aβ 诱导", "脑组织", "炎症诱导模板"],
        ["Aβ42/总抗菌活性", "AD 脑侧可升高", "脑匀浆/病理组织", "宿主抗菌—病理双重属性"],
        ["乳铁蛋白", "部分研究为下降", "唾液", "证明不存在普遍同向变化"],
        ["微生物源 AMP", "必须由本课题结果决定", "肠道宏基因组/宏蛋白组", "论文主结果对象"],
    ]),
    ("note", "如果老师问“AD 组的抗菌肽是否更多”，最安全的答复是：部分宿主 AMP/总抗菌活性在文献中偏高，但不是普遍规律；本课题重点检验微生物源 AMP 的分子和阶段特异差异。"),

    ("h1", "二、分子机制一：AChE-Aβ 复合物为什么可作为计算参照"),
    ("p", "AChE-Aβ 研究可以作为“如何从结构模拟提出可检验界面假设”的方法学参照：模拟观察 Aβ 在 AChE 表面的稳定停留、主要接触区段和构象变化，再由 PAS 相关实验判断其是否促进聚集。它不是在证明你的微生物源 AMP 已经作用于 AChE，而是提供一个可迁移的建模框架。[[ache_md2020,deferrari2001,inestrosa2008,pas_2019,rees2006]]"),
    ("b", "AChE 的 PAS 附近和 344-361 区段可作为候选肽竞争或调节的结构假设区域。"),
    ("b", "AChE 促 Aβ 构象转换和成核的方向，必须结合对接、长时间 MD、自由能和实验读数。"),
    ("b", "BChE 与 Aβ 的相反效应提醒我们：界面性质决定方向，不能看到“结合”就判定促聚集。[[rees2006]]"),
    T("表 8　AChE-Aβ 参照体系的结果与边界", ["参照结果", "可以借鉴的地方", "不能直接外推的地方"], [
        ["1 μs 模拟中复合物稳定", "报告接触、驻留和构象稳定性的方法", "未知微生物 AMP 也会稳定"],
        ["Aβ 主要停留 344-361", "设置竞争/调节界面的假设", "该区域不是所有候选肽的必然靶点"],
        ["PAS 抑制剂阻断促聚集", "把 MD 假设与酶/聚集实验联接", "docking 分数不等于阻断实验"],
        ["BChE 延缓纤维形成", "说明结合方向可相反", "不能事先判定保护或风险"],
    ]),
    ("p", "对候选微生物 AMP 的建议计算顺序是：先预测肽构象并做柔性对接，再对 AChE-PAS/344-361 和 Aβ 片段分别做至少 3 条独立 MD；比较界面接触、β-sheet、聚集自由能和 Aβ 构象分布。若没有表达/暴露证据，该结果只能作为结构线索。"),

    ("h1", "三、分子机制二：抗菌肽与 Aβ 的交叉成核"),
    ("p", "抗菌肽和淀粉样肽都可能具有两亲性、带电界面和 β 结构倾向，因此可能发生交叉成核、表面催化或结构重定向。文献中既有抑制纤维延伸，也有稳定寡聚体或促进异常聚集的可能；这正是为什么必须观察聚集路径和毒性，而不能只报告结合能。[[ll37_ab_partner2017,delorenzi2017_full,chemsci_defensins2021,chemsci_crossseed2022,chemsocrev2024,crossseed2026,ll37_membrane2016,polymyxin2025,pentapeptide2023]]"),
    T("表 9　交叉成核的三种可能方向", ["方向", "分子读数", "病理解释", "必须增加的验证"], [
        ["抑制/无毒化", "β-sheet 下降、毒性寡聚体减少、off-pathway 复合物", "潜在保护/抑制肽", "细胞毒性、清除和浓度关系"],
        ["重定向但未知", "纤维减少但寡聚体驻留增加", "可能把病理停留在另一条路径", "寡聚体谱和时间序列"],
        ["促进病理", "成核加快、膜活性和有毒寡聚体增加", "风险样机制线索", "细胞/动物和阻断实验"],
    ]),
    ("p", "AChE-PAS、Aβ 生成区、膜表面是三个可计算的候选介入位置。对你的论文，这三者应排在差异、来源菌和表达证据之后。尤其是 Aβ 结合的解释，必须和微生物源肽的肠道来源、稳定性以及是否入血放在同一张机制卡片里。"),
    T("表 10　Aβ/AMP 模拟的验收指标", ["指标", "保护方向", "风险方向", "未知时如何报告"], [
        ["结合自由能/PMF", "稳定合理复合物", "稳定病理构象或界面", "只报趋势和误差"],
        ["β-sheet/二级结构", "减少有毒路径", "增加或延长病理构象", "区分单体/寡聚体/纤维"],
        ["寡聚体分布", "降低 on-pathway 寡聚体", "提高有毒寡聚体比例", "不能只看纤维终点"],
        ["膜效应", "降低泄漏/微胶质激活", "增强泄漏/ROS", "需要细胞或膜实验"],
    ]),

    ("h1", "四、分阶段组与本课题的深度学习分析"),
    ("p", "建议沿用 NC、SCS、SCD、MCI、AD 五个认知阶段作为解释框架，并在性别和年龄层面匹配或建模校正。这样做的目的不是预设某个阶段一定升高，而是检验 AMP 组成是否出现病程梯度。实际样本数、纳入排除标准和缺失值处理应以你的 476 样本数据台账为准。[[stage_meta2026,stage_network2025,meta_review2023,liu2019bai,li2019mci]]"),
    T("表 11　五阶段设计如何服务于 AMP 差异分析", ["阶段", "分组含义", "可以观察的信号", "不能预先断言"], [
        ["NC", "认知正常基线", "AMP 多样性、来源菌和 SCFA 相关基线", "所有健康富集肽都保护"],
        ["SCS", "主观认知下降", "早期组成偏移和候选肽初始变化", "一定已进入 AD 病理"],
        ["SCD", "可疑认知障碍", "屏障/炎症中间层与网络变化", "所有变化都由 AMP 引起"],
        ["MCI", "轻度认知障碍", "与前驱期和 AD 比较的过渡趋势", "是单向病因节点"],
        ["AD", "阿尔茨海默症", "疾病相关富集或缺失候选", "所有候选都促病理"],
    ]),
    ("h2", "4.1 与论文题目完全对应的八步技术路线"),
    ("p", "第一步，质控、去宿主、组装、分箱和 ORF 预测；第二步，形成 12-50 aa 微生物短肽库；第三步，Attention/LSTM/BERT 共识预测 AMP；第四步，把 reads 回贴到 ORF/肽序列并构建样本×肽丰度矩阵；第五步，用组成性差异方法筛选 AD/健康和五阶段候选；第六步，用宏蛋白组/肽组学或转录证据进行二次去重；第七步，对高优先级候选做来源菌—生态—炎症—膜/LPS—Aβ/BBB 的分层机制分析；第八步，用代表性风险样和保护样候选做抑菌、酶活、屏障或炎症验证。[[fastp2018,bowtie2_2012,megahit2015,metaspades2017,metabat2_2019,checkm2015,prodigal2010,cdhit2006,ancombc2_2024,maaslin2_2021]]"),
    T("表 12　宏基因组 AMP 差异分析的方法门槛", ["环节", "建议方法", "关键输出", "与病理解释的关系"], [
        ["候选构建", "MEGAHIT/metaSPAdes、Prodigal、CD-HIT", "序列、ORF、MAG、来源菌", "决定候选是否可追溯"],
        ["模型共识", "Attention/LSTM/BERT 或同类模型", "AMP 概率和模型一致性", "只说明 AMP 候选"],
        ["定量", "read 回贴、长度校正、CLR/相对丰度敏感性分析", "样本×肽矩阵", "提供 AD/健康差异基础"],
        ["差异", "ANCOM-BC2/Maaslin2/计数模型", "效应量、FDR、检出率、趋势", "筛选 AD-associated AMP"],
        ["表达验证", "宏转录组/宏蛋白组/肽组学", "表达/加工证据", "提高真实暴露可信度"],
        ["机制分层", "网络、中介、MD/QM、结构和实验", "风险/保护/未知标签", "提出可检验病理假设"],
    ]),

    ("h1", "五、候选肽到底应该怎样分类"),
    ("p", "在真实结果出来后，不建议只保留“有益/有害”两个标签，而是建立四类：AD 富集且促炎/屏障损伤样；AD 富集但方向未知；健康富集且屏障/抗炎/清除样；只有 AMP 预测、缺少差异和表达支持。分类依据必须同时包含效应量、FDR、来源菌、表达、生态路径和分子方向。"),
    T("表 13　筛选后的四类候选肽", ["类别", "数据条件", "优先机制", "推荐措辞"], [
        ["风险样候选", "AD 富集/随病程增加 + 炎症/LPS/屏障或膜/受体证据", "生态选择、TLR4/NF-kB、微胶质、Aβ 路径", "可能参与病理的 AD-associated candidate"],
        ["保护样候选", "健康富集/病程下降 + 有益菌/屏障/抗炎/Aβ 清除证据", "选择性抑菌、SCFA、屏障或无毒化", "potentially protective candidate"],
        ["方向未知", "稳定差异但机制读数矛盾或不足", "先做表达和结构/功能验证", "AD-associated candidate, direction unresolved"],
        ["预测层候选", "只有模型概率或低检出率", "不进入病理结论", "prediction-only candidate"],
    ]),
    ("p", "如果老师问“你是找病理相关的肽还是抑制剂相关的肽”，可回答：研究主体是 AD 相关差异肽；病理样和保护/抑制样是对同一差异候选集合进行的方向性分层。不能把论文改成只寻找已知 Aβ 抑制剂，因为那会绕开论文题目中的“AD 患者与健康人群肠道微生物组差异”。"),
    ("h2", "5.1 机制优先级评分"),
    ("p", "可用 D、G、H、X、M 五项建立候选机制卡片：D 是差异稳健性，G 是来源菌/生态连接，H 是炎症和屏障连接，X 是表达、稳定性和跨区室可行性，M 是膜/LPS/受体/Aβ 的分子方向。每项 0-2 分只用于排序，不是因果概率；真实候选表到位后再填写。"),
    T("表 14　候选机制卡片字段", ["字段", "必须记录", "没有时怎么办"], [
        ["身份", "candidate ID、序列、长度、电荷、序列簇", "不进入最终机制结论"],
        ["来源", "ORF、contig、MAG、GTDB-Tk 分类", "只能说未知来源"],
        ["预测", "Attention/LSTM/BERT 概率与共识", "保留模型不确定性"],
        ["差异", "效应量、FDR、检出率、分期趋势", "只能是 prediction-only"],
        ["表达", "转录/蛋白/肽组学或分泌线索", "标记为 DNA-level evidence only"],
        ["机制", "生态、炎症、MD/QM、Aβ/BBB 证据", "方向标为 unknown"],
        ["结论", "risk-like/protective/unknown", "不用 causative peptide"],
    ]),

    ("h1", "六、分子动力学与量化计算如何排优先级"),
    ("p", "对微生物源 AMP，第一优先级应是候选肽与来源菌或相关菌膜、LPS 和 lipid A；第二优先级是 TLR4/MD-2、FPR2 等炎症受体；第三优先级才是 AChE-PAS、Aβ 聚集或 BBB。这个顺序能够避免把一个肠道来源不明、没有表达证据的肽直接解释成脑内 Aβ 作用分子。[[charmmgui_lps,cm15_om_2022,pore_fe2025,charmm36m,gmxmmpbsa2021,ache_md2020,bbb_md2026,bbb_ml2025]]"),
    T("表 15　候选 AMP 的 MD/QM 优先级", ["优先级", "体系", "主要问题", "输出"], [
        ["1", "AMP + LPS/lipid A/细菌膜", "是否具有来源相关的膜选择性和生态功能", "吸附、PMF、孔形成、离子通量"],
        ["2", "AMP + TLR4/MD-2/FPR2 等", "是否存在炎症受体结构线索", "界面、驻留、构象和网络方向"],
        ["3", "AMP + Aβ/AChE-PAS", "是否改变聚集路径或竞争界面", "寡聚体、β-sheet、PMF、聚集方向"],
        ["4", "AMP + BBB 膜/转运体", "直接入脑是否物理可行", "膜 PMF、Papp、转运路径"],
    ]),
    ("p", "MD 结果必须包括重复、收敛、力场敏感性和误差。MM-PBSA、伞形采样或 DFT 只能把结构假设量化，不能独立产生细胞或动物因果。对 Aβ，要分单体、寡聚体和纤维；对 BBB，要先确认暴露和完整肽稳定性。"),
    T("表 16　Aβ/BBB 追加计算的进入条件", ["条件", "必须有的证据", "没有时的降级写法"], [
        ["候选差异", "AD/健康或阶段差异稳定", "只是 AMP prediction"],
        ["来源表达", "宏蛋白组/肽组学/转录或分泌线索", "远端肠道关联"],
        ["区室暴露", "血液/屏障/稳定性或转运依据", "不能说进入脑"],
        ["方向读数", "寡聚体、膜、炎症至少一个方向", "Aβ binding, direction unresolved"],
        ["验证", "阻断/加入/去除改变表型", "机制假设，不是因果"],
    ]),

    ("h1", "七、目前可以给出的结果、还不能给出的结果"),
    ("p", "如果当前还没有真实的候选 FASTA、样本×肽丰度矩阵和差异统计表，就不能在中期材料中写“已经找到某条微生物源抗菌肽导致 AD”。可以写的是：已经建立候选预测和机制关联框架，等待真实差异结果；可以明确写出候选肽如何分层、如何计算、如何验证。"),
    T("表 17　结果状态和正确措辞", ["状态", "可以写", "不能写"], [
        ["方法已完成", "建立短肽库、模型共识和差异分析流程", "已发现致病 AMP"],
        ["预测已完成", "得到 AMP prediction candidates", "这些肽在脑内起作用"],
        ["差异已完成", "得到 AD-associated differential AMP", "差异说明因果"],
        ["机制计算完成", "提出结构和通路优先级", "MD 证明 AD 病因"],
        ["干预验证完成", "支持风险或保护方向", "直接推广到所有 AD 患者"],
    ]),
    ("p", "当前仓库没有真实候选文件，因此文档中的候选机制卡片只保留字段和判定规则，不编造 AMP-C01 的序列、P 值、FDR、丰度或病理方向。实际结果到位后，应按候选逐条填入。"),

    ("h1", "八、分子机制与阶段证据的整合解释"),
    ("p", "阶段层面回答“什么时候出现差异”，生态层面回答“可能影响了谁”，分子层面回答“可能怎么作用”，病理层面回答“是否与 Aβ/Tau、炎症和屏障方向一致”。四层必须逐层连接，不能从最后一层反推前面三层。"),
    T("表 18　从阶段差异到病理机制的四层证据", ["层", "核心问题", "数据/方法", "结论边界"], [
        ["阶段", "哪一组、哪一阶段出现差异", "五阶段模型、协变量校正、趋势", "时间/状态关联"],
        ["生态", "差异肽的来源菌和共现对象是谁", "MAG、菌群网络、LPS/SCFA", "生态候选路径"],
        ["分子", "它能否与膜、LPS、受体或 Aβ 相互作用", "MD、PMF、MM-PBSA、DFT", "结构机制线索"],
        ["病理", "是否指向炎症、BBB、Aβ/Tau 或突触", "中介、细胞/动物、干预", "病理方向/因果强度"],
    ]),
    ("p", "因此，AChE-Aβ 模拟可以保留，但它要放在“高优先级候选的分子机制验证”章节；不能把它放在全文开头，让评委误以为你的研究目标是寻找 Aβ 抑制剂。"),

    ("h1", "九、汇报口径和老师追问的回答"),
    ("quote", "我的研究首先筛选的是 AD 患者与健康人群肠道微生物组中有差异的微生物源抗菌肽。机制分析再把这些差异肽分为可能促进病理、可能保护或方向未知三类。Aβ 结合只是高优先级候选的一个分子读数，不能单独说明导致 AD；真正的主路径是微生物 AMP 通过菌群竞争、LPS/SCFA、肠屏障和炎症信号与 AD 病理建立关联。"),
    T("表 19　答辩问答卡", ["老师追问", "推荐回答"], [
        ["你找的是致病肽还是抑制剂？", "首先找 AD 相关差异微生物源 AMP；致病样和保护/抑制样是后续方向性分类。"],
        ["Aβ 结合能证明什么？", "证明一种可能的分子相互作用，必须继续判断聚集方向、炎症、膜损伤和暴露。"],
        ["为什么做 AChE-PAS？", "借鉴已有 AChE-Aβ MD 的界面解析方法，为候选肽竞争或调节提出可检验假设。"],
        ["微生物 AMP 会进入脑吗？", "目前不能默认；先做生态/炎症主路径，直接入脑只对有暴露证据的候选做条件性验证。"],
        ["为什么 AD 组更多？", "部分宿主 AMP/总抗菌活性文献方向偏高，但不是所有 AMP 都高；微生物源 AMP 方向由本课题结果决定。"],
        ["为什么不全部合成验证？", "先计算筛选和表达去重，再按风险样/保护样/未知方向选择代表性候选降低成本。"],
        ["能不能说导致 AD？", "在横断面和计算证据阶段只能说 AD-associated candidate；因果需要加入、去除、阻断或动物验证。"],
    ]),

    ("h1", "十、最终研究闭环与验证计划"),
    ("p", "最终闭环是：476 样本与认知阶段设计 → 宏基因组组装和 ORF → 微生物源短肽库 → 深度学习 AMP 共识 → AD/健康和阶段差异 → 表达证据二次去重 → 来源菌和生态网络 → LPS/SCFA/屏障/炎症中介 → 优先候选膜/受体/Aβ/BBB 计算 → 代表性风险样和保护样实验验证 → 只对干预结果讨论因果。"),
    T("表 20　从计算关联走向因果还需要什么", ["计算可以提供", "仍需补的证据", "验证方式"], [
        ["候选身份与差异", "真实表达和加工后的肽浓度", "宏蛋白组、肽组学、靶向定量"],
        ["来源菌与生态关联", "活菌环境中的选择效应", "共培养、菌群模拟、动物或 FMT"],
        ["LPS/受体结构线索", "细胞信号和炎症方向", "受体阻断、微胶质/肠上皮细胞"],
        ["Aβ/BBB 计算方向", "体内暴露和病理表型", "血液/CSF/脑组织及 BBB 模型"],
        ["风险/保护标签", "干预后表型逆转", "加入、去除、敲低或中和候选肽"],
    ]),
    ("p", "最终结论建议写成：本研究筛选并优先排序与 AD 状态或病程相关的微生物源抗菌肽候选，提出其通过肠道生态、屏障和炎症通路参与 AD 相关过程的可检验机制；部分候选可能具有风险样方向，部分可能具有保护/抑制潜力，具体方向和因果关系仍需表达、功能和干预验证。"),
    ("note", "不要写“筛选出导致 AD 的抗菌肽”，除非已经完成明确的去除/加入/阻断实验并且有独立验证。"),

    ("h1", "附录：文献使用说明"),
    ("p", "本版将用户补充材料中的 46 条文献线索与已有 AMP、肠道菌群、深度学习、MD/QM 和 BBB 文献库合并。正文引用按首次出现顺序自动编号；其中 2025—2026 年条目、预印本或用户提供的检索记录，提交论文前应再次核对 DOI、卷页、样本数和原文图表。数值型结论均应回到原文，不把补充材料中的汇总数字当作本课题结果。"),
]

SLIDES = [
    {"type": "cover"},
    {"type": "bullets", "title": "先给老师一个清楚的答案", "sub": "这不是单纯的 Aβ 抑制剂筛选", "bullets": [
        (0, "主对象：AD 患者与健康人群肠道微生物组中的差异微生物源 AMP。"),
        (0, "机制层：判断差异肽可能偏风险样、保护样或方向未知。"),
        (0, "Aβ 结合：只是候选机制读数，不等于导致 AD。"),
        (0, "主路径：AMP—菌群—LPS/SCFA—屏障/炎症—脑病理。"),
    ]},
    {"type": "table", "title": "表 1　七环逻辑链：证据强度和本课题位置", "sub": "蓝色背景证据、绿色计算、橙色待验证"},
    {"type": "section", "num": "01", "title": "八个问题先逐条回答", "sub": "每个问题都同时给结论、证据和边界"},
    {"type": "table", "title": "表 2　问题 1 的对象区分", "sub": "宿主 AMP、Aβ、微生物源 AMP 和抑制肽"},
    {"type": "bullets", "title": "问题 1：抗菌肽与 AD 有什么关系", "sub": "Aβ 和宿主 AMP 提供背景，微生物 AMP 是本课题对象", "bullets": [
        (0, "Aβ 具有抗菌性质，宿主 AMP 在 AD 组织/体液中有变化。"),
        (0, "你的研究对象是肠道微生物 ORF 编码的 AMP。"),
        (0, "宿主 AMP 文献不能直接替代微生物 AMP 的差异结果。"),
    ]},
    {"type": "bullets", "title": "问题 2：AD 与感染有关吗", "sub": "可以说有关联线索，不能说所有 AD 都由感染直接导致", "bullets": [
        (0, "脑组织病原体、LPS 和外周屏障指标有多类报道。"),
        (0, "不同队列的污染、可重复性和因果方向需要控制。"),
        (0, "人群归因分数是总体估计，不是个人病因概率。"),
    ]},
    {"type": "table", "title": "表 3　深度学习输出如何被正确翻译", "sub": "AMP 概率不是 AD 病理概率"},
    {"type": "bullets", "title": "问题 3：抗菌活性为什么可以预测", "sub": "宏基因组 AMP 挖掘已有技术先例", "bullets": [
        (0, "Attention/LSTM/BERT 适合短肽候选发现。"),
        (0, "Ma 等肠道宏基因组工作给出高阳性率活性验证先例。"),
        (0, "AMPSphere、Macrel、FMT 流程可做扩展和交叉验证。"),
        (0, "它们证明能找 AMP，不证明 AMP 会导致 AD。"),
    ]},
    {"type": "table", "title": "表 4　阶段特异性候选肽的判定层级", "sub": "从出现到表达再到机制"},
    {"type": "bullets", "title": "问题 4：阶段特异性为什么能与 AD 关联", "sub": "阶段特异肽首先是计算产物", "bullets": [
        (0, "NC、SCS、SCD、MCI、AD 的菌群组成和网络可能呈梯度变化。"),
        (0, "来源菌变化会带来编码 AMP 组成变化。"),
        (0, "需要宏蛋白组/肽组学二次去重。"),
    ]},
    {"type": "table", "title": "表 5　双刃剑的判定读数", "sub": "同一类分子可以有保护和风险方向"},
    {"type": "bullets", "title": "问题 5：抗菌肽是促进 AD 还是抑制感染", "sub": "答案是：方向取决于浓度、聚集态、部位和靶细胞", "bullets": [
        (0, "局部、适度、正常聚集态：可能抑制感染。"),
        (0, "长期过量、异常聚集或错误区室：可能放大炎症。"),
        (0, "微生物源候选先分风险样、保护样和未知。"),
    ]},
    {"type": "bullets", "title": "问题 6：抑制感染一侧的证据", "sub": "Aβ/宿主 AMP 证据是背景，不是微生物候选的直接结果", "bullets": [
        (0, "体外抗菌活性、感染动物模型、病原体捕获和膜机制都有先例。"),
        (0, "微生物源 AMP 仍需要菌种匹配的抑菌和膜实验。"),
        (0, "保护性功能不等同于治疗 AD。"),
    ]},
    {"type": "bullets", "title": "问题 7：为什么部分 AD 相关 AMP 可能更多", "sub": "改成“部分”，不要泛化所有抗菌肽", "bullets": [
        (0, "肠屏障破坏和 LPS 入血激活 TLR4/NF-kB。"),
        (0, "炎症可诱导宿主 AMP/Aβ 和微胶质反应。"),
        (0, "病理反馈可能进一步放大屏障和炎症。"),
        (0, "微生物源 AMP 方向仍由本课题数据决定。"),
    ]},
    {"type": "table", "title": "表 6　“AD 组更多”应如何分层说", "sub": "分子、部位、证据类型三层"},
    {"type": "table", "title": "表 7　按分子、部位和证据类型回答“谁更多”", "sub": "乳铁蛋白等下降是重要反例"},
    {"type": "section", "num": "02", "title": "AChE-Aβ 与交叉成核", "sub": "为什么 MD 参照有用，但不能越级"},
    {"type": "table", "title": "表 8　AChE-Aβ 参照体系的结果与边界", "sub": "方法学参照，不是微生物 AMP 已致病的证明"},
    {"type": "bullets", "title": "AChE-PAS 的三个可检验假设", "sub": "把分子模拟落到候选肽", "bullets": [
        (0, "H1：候选肽竞争 PAS 或 344-361 区段，减少 AChE 促成核。"),
        (0, "H2：候选肽直接改变 Aβ 单体/寡聚体/纤维路径。"),
        (0, "H3：候选肽在膜表面改变微胶质识别和炎症信号。"),
        (1, "三条假设都必须先有差异和暴露依据，再做 MD/QM。"),
    ]},
    {"type": "table", "title": "表 9　交叉成核的三种可能方向", "sub": "抑制、重定向、促进不能只看结合能"},
    {"type": "table", "title": "表 10　Aβ/AMP 模拟的验收指标", "sub": "从结合到病理方向的必要读数"},
    {"type": "section", "num": "03", "title": "五阶段设计与深度学习差异分析", "sub": "NC—SCS—SCD—MCI—AD"},
    {"type": "table", "title": "表 11　五阶段设计如何服务于 AMP 差异分析", "sub": "不预设哪个阶段一定升高"},
    {"type": "table", "title": "表 12　宏基因组 AMP 差异分析的方法门槛", "sub": "从短肽库到病理机制"},
    {"type": "section", "num": "04", "title": "候选肽分类和计算优先级", "sub": "病理样、保护样、未知样和预测层"},
    {"type": "table", "title": "表 13　筛选后的四类候选肽", "sub": "这才回答“找什么肽”"},
    {"type": "table", "title": "表 14　候选机制卡片字段", "sub": "拿到真实结果后逐条填充"},
    {"type": "table", "title": "表 15　候选 AMP 的 MD/QM 优先级", "sub": "先菌膜/LPS，再受体，最后 Aβ/BBB"},
    {"type": "table", "title": "表 16　Aβ/BBB 追加计算的进入条件", "sub": "不能默认所有候选都入脑"},
    {"type": "section", "num": "05", "title": "结果边界与答辩口径", "sub": "计算关联不能直接写成因果"},
    {"type": "table", "title": "表 17　结果状态和正确措辞", "sub": "不把方法示例冒充真实结果"},
    {"type": "table", "title": "表 18　从阶段差异到病理机制的四层证据", "sub": "阶段—生态—分子—病理"},
    {"type": "table", "title": "表 19　答辩问答卡", "sub": "老师追问时直接按证据边界回答"},
    {"type": "table", "title": "表 20　从计算关联走向因果还需要什么", "sub": "验证路线"},
    {"type": "closing", "lines": [
        "主对象：AD 相关差异微生物源 AMP",
        "主路径：AMP—菌群—LPS/SCFA—肠屏障/炎症—脑病理",
        "Aβ/AChE/BBB：高优先级候选的条件性机制验证",
        "最终结论：先说关联和优先级，干预后才讨论因果",
    ]},
]

TABLES = {payload["title"]: payload for kind, payload in BLOCKS if kind == "table"}
for _spec in SLIDES:
    if _spec.get("type") == "table":
        _spec["ref"] = _spec["title"]
