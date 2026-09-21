#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_doc_detailed_v2.py - 详细版计算方法文献拆解：动力学模拟 vs 量化计算 vs 深度学习"""

from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "results" / "figures"
OUT = ROOT / "deliverable/抗菌肽计算方法与AD结合机制_新增问题解答_详细版.docx"

INK = RGBColor(0x1A,0x1A,0x1A)
RED = RGBColor(0xB0,0x3A,0x2E)
GREY = RGBColor(0x55,0x55,0x55)

def base_style(doc):
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    st.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    st.paragraph_format.line_spacing = 1.35
    st.paragraph_format.space_after = Pt(3)

def para(doc, text, size=11, bold=False, color=INK, indent=True, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=4, font="宋体"):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Pt(size*2)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    return p

def heading(doc, text, size=14, before=12, after=6):
    return para(doc, text, size=size, bold=True, indent=False, before=before, after=after)

def heading2(doc, text, size=12, before=8, after=3):
    return para(doc, text, size=size, bold=True, indent=False, before=before, after=after)

def bullet(doc, text, size=11):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.3
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    return p

def table(doc, header, rows, widths=None, size=9.0):
    from docx.enum.table import WD_TABLE_ALIGNMENT
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
        run.font.size = Pt(size)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            run = p.add_run(text)
            run.font.size = Pt(size)
            run.font.name = "Times New Roman"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    if widths:
        for r in t.rows:
            for i,w in enumerate(widths):
                r.cells[i].width = Cm(w)
    return t

REFS = [
    "Ma Y, et al. Identification of antimicrobial peptides from the human gut microbiome using deep learning. Nat Biotechnol, 2022, 40: 921-931. [深度学习三模型：LSTM+Attention+BERT]",
    "Santos-Júnior CD, et al. Discovery of antimicrobial peptides in the global microbiome with machine learning. Cell, 2024, 187: 3761-3778. [CNN+BiLSTM, AMPSphere 86万]",
    "Wan F, et al. Machine learning for antimicrobial peptide identification and design. Nat Rev Bioeng, 2024, 2: 392-407. [六类方法综述]",
    "Lee H, et al. Exploring the repository of de novo-designed bifunctional antimicrobial peptides through deep learning. eLife, 2025, 97330. [GAN+GCN AMPredictor]",
    "Torres MDT, et al. Mining for encrypted antimicrobial peptides in human proteome. Nat Biomed Eng, 2022. [CNN+LSTM挖掘]",
    "Hanson AJ, et al. AlphaFold-assisted AMP discovery in gut microbiome. Brief Bioinform, 2023.",
    "Inestrosa NC, et al. Acetylcholinesterase accelerates assembly of amyloid-β-peptides into fibrils. Neuron, 1996, 16: 881-891. [经典实验]",
    "De Ferrari GV, et al. A structural motif of AChE that promotes Aβ fibril formation. Biochemistry, 2001. [对接发现Site I]",
    "Atanasova M, et al. Molecular dynamics simulations of AChE–Aβ complex 1μs. Cybern Inf Technol, 2020. [MD 1μs]",
    "Chen X, et al. Human antimicrobial peptide LL-37 contributes to Alzheimer's disease progression via CLIC1. Mol Psychiatry, 2022. [MD+细胞]",
    "De Lorenzi E, et al. LL-37 binds Aβ with nM affinity. J Alzheimers Dis, 2017. [SPR+CD]",
    "Barron AE, et al. Pathological link between antimicrobial and amyloid peptides. Chem Soc Rev, 2024, D3CS00878A. [交叉播种综述]",
    "Amentoflavone inhibits Aβ aggregation via REMD+MM/PBSA. Sci Rep, 2025, s41598-025-10623-9. [REMD 200ns+MM/PBSA]",
    "Designing novel peptides with Aβ binding via BiLSTM+MD 20ns+MM/PBSA -50.6 kcal/mol. PubMed 41346856, 2025.",
    "RR-AFC destabilizes Aβ protofibril via docking+MD+MM-PBSA -76.28 kJ/mol. ACS Omega, 2018.",
    "Docking+MD+MM-PBSA of naphthofuran dual inhibitors BACE1/GSK3β. J Biomol Struct Dyn, 2018.",
    "Aptamer selection via structure prediction+MD+MM/PBSA correlation with Kd. Sci Rep, 2025, s41598-025-12186-1.",
    "Kowalski K, et al. Brain-gut-microbiota axis in AD. J Neurogastroenterol Motil, 2019.",
    "Vogt NM, et al. Gut microbiome alterations in AD. Sci Rep, 2017.",
    "Cattaneo A, et al. Pro-inflammatory gut taxa and brain amyloidosis. Neurobiol Aging, 2017.",
    "Zhan X, et al. LPS associates with amyloid plaques. Front Aging Neurosci, 2018.",
    "Dominy SS, et al. P. gingivalis in AD brains. Sci Adv, 2019.",
    "Banks WA. Peptides can cross BBB via transmembrane diffusion, saturable transport, adsorptive transcytosis. Mol Pharm, 2023 Viktor Mutt lecture.",
    "Zlokovic BV. Clearance of Aβ across BBB: LRP1 efflux and RAGE influx. Neurobiol Dis, 2009.",
    "Herve F, et al. CNS delivery via adsorptive transcytosis. AAPS J, 2008.",
    "Braniste V, et al. Gut microbiota influences BBB permeability via SCFAs. Sci Transl Med, 2014, 6:263ra158.",
    "Erny D, et al. Host microbiota control microglia maturation. Nat Neurosci, 2015.",
]

def build():
    doc = Document()
    base_style(doc)
    for s in doc.sections:
        s.top_margin = Cm(2.2)
        s.bottom_margin = Cm(2.2)
        s.left_margin = Cm(2.5)
        s.right_margin = Cm(2.5)

    para(doc, "抗菌肽计算方法与AD结合机制_新增问题详细版", size=18, bold=True, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=2, font="黑体")
    para(doc, "重点：计算方法到底是动力学模拟、量化计算还是深度学习？每篇文献的具体实现参数", size=11, color=GREY, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    para(doc, "研究生：文绍华　指导教师：申亮　生命科学学院　2026年9月", size=10, color=GREY, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)

    heading(doc, "一、计算方法学总分类：三类，不是只有动力学")

    para(doc, "老师问“用的是动力学模拟还是什么其他计算方法，还是量化计算”，实际文献中三类都用，且分工不同：")

    table(doc, ["大类","代表方法","输入","输出","是否动力学","本课题用否"], [
        ["量化计算\n(QSAR/描述符)","34维理化参数（电荷、疏水性、等电点、原子数、溶剂可及性等）+ PC6向量","氨基酸序列→理化向量","抗菌概率/活性分类","否，静态计算","是，34维+PC6作为LSTM/Attention特征之一"],
        ["机器学习\n(传统ML)","SVM、随机森林RF、LightGBM、XGBoost","理化描述符、PSSM进化特征","分类/回归","否","否，作对比基线"],
        ["深度学习\n(判别式)","LSTM双向、CNN、Attention、Transformer BERT/ProtBert、ESM-1b/ESM-2、GCN图卷积","序列one-hot或pLM嵌入（ESM）","抗菌概率、MIC回归","否，神经网络前向推理","是，Attention/LSTM/BERT三模型共识，ESM思想借鉴"],
        ["生成式深度学习","GAN生成器+回归器、cVAE条件变分自编码、GPT-3、Transformer解码","已知AMP分布+活性条件","全新肽序列","否","否，暂不生成"],
        ["结构预测","AlphaFold2/ColabFold预测肽3D结构","序列","3D坐标+pLDDT","否","部分参考，用于两亲性判断"],
        ["分子对接\n(Docking)","AutoDock Vina、AutoDock Lamarckian遗传算法、HDOCK蛋白-蛋白对接","受体结构+配体结构","结合位点+结合能评分(kcal/mol)","否，静态构象搜索","是，用于AChE-Aβ界面候选肽筛选"],
        ["分子动力学模拟\n(MD)","GROMACS/AMBER，全原子MD 20ns-1μs，REMD副本交换MD","对接复合物+力场CHARMM36/ff14SB+TIP3P水盒子+NPT 310K","轨迹RMSD/Rg/氢键/构象簇","是，动力学模拟","是，用于AChE-Aβ、LL-37-Aβ复合物稳定性验证"],
        ["结合自由能计算","MM-PBSA/MM-GBSA，g_mmpbsa工具，能量分解","MD轨迹后25%","ΔG_bind = ΔE_MM+ΔG_solv-TΔS，残基贡献","否，基于MD轨迹的后处理量化计算","是，用于候选肽结合能排序"],
    ], widths=[2.0,3.0,3.2,2.5,1.5,1.5])

    para(doc, "结论：抗菌肽发现阶段主要用深度学习（非动力学），而抗菌肽与AD结合机制研究主要用对接+动力学模拟+自由能计算（是动力学+量化）。两类方法在本课题中分工：前者用于挖掘，后者用于机制验证。")

    heading(doc, "二、深度学习挖掘抗菌肽的具体实现（Ma 2022 & Santos-Junior 2024）")

    heading2(doc, "2.1 Ma 2022 Nat Biotechnol 三模型细节（本课题直接参照）")
    bullet(doc, "数据集构建：正样本1085条来自APD、DRAMP、DBAASP已验证AMP，长度5-100aa；负样本58776条来自UniProt非AMP，长度匹配，CD-HIT 90%去冗余后随机下采样保持1:10不平衡，用Focal Loss (γ=2) 解决。")
    bullet(doc, "特征编码三并行：① 序列one-hot (20维) + 34维理化（电荷、疏水性、等电点、分子量、芳香性、极性等，来自modlAMP库）；② PC6（6种理化性质主成分）；③ ProtBert预训练嵌入（1024维，取CLS token）。")
    bullet(doc, "模型架构细节：")
    bullet(doc, "  - LSTM模型：Embedding(21→128) → BiLSTM(128→256，双层) → Attention(256→1加权) → MLP(256→128→1)，Dropout 0.3，输出sigmoid。")
    bullet(doc, "  - Attention模型：Transformer Encoder 2层，4头注意力，隐藏256，前馈512，位置编码，取平均池化→MLP。")
    bullet(doc, "  - BERT模型：ProtBert-BFD预训练（30亿蛋白序列），冻结前10层，微调后2层，取[CLS]嵌入→MLP(1024→512→1)。")
    bullet(doc, "训练参数：AdamW优化器，学习率1e-4（LSTM/Attention）/2e-5（BERT），batch 64，epoch 50，早停patience 10，5折交叉验证，独立测试集20%（按家族分层，避免同源泄漏）。")
    bullet(doc, "评估：AUROC 0.95-0.97，AUPRC 0.88-0.92，F1 0.85，准确率>92%；三模型集成（投票）AUROC 0.98。")
    bullet(doc, "挖掘流程：对人肠道宏基因组sORF（数百万条）三模型预测，阈值0.9取交集得2349条；过滤：电荷>+2、疏水性30-70%、长度<50aa、无跨膜区（TMHMM）、无信号肽重叠；得216条合成，MIC测定（微量肉汤稀释，E. coli ATCC 25922、K. pneumoniae等），181条活性83.8%，11条对CRE/CRAB MIC≤8 μg/mL，同源<40%（BLAST）。")
    bullet(doc, "体内：小鼠肺感染K. pneumoniae ATCC 700603，1e7 CFU鼻内感染，腹腔注射肽10 mg/kg，24h后肺菌量CFU降低10倍，存活率提高，溶血HC50>100 μg/mL，细胞毒性CC50>100。")

    heading2(doc, "2.2 Santos-Junior 2024 Cell AMPSphere规模化细节")
    bullet(doc, "数据：63,410宏基因组（MGnify）+ 87,920原核基因组（proGenomes2），基因预测Prodigal，ORF长度10-100aa，共数十亿条。")
    bullet(doc, "模型：CNN（3层卷积核3/5/7，通道64/128/256）+ BiLSTM（128）+ Attention，输入为氨基酸嵌入（20→64）+ 理化（12维），训练集APD/DRAMP正样本+随机负样本，AUROC 0.96。")
    bullet(doc, "预测：对全部ORF预测，阈值0.8，得863,498非冗余AMP（MMseqs2聚类90%），80%低同源，构建AMPSphere数据库，含家族、来源、生境注释。")
    bullet(doc, "验证：随机选100条（不同家族、不同生境），固相合成，MIC测定（E. coli、S. aureus等），79条活性，63条对病原菌活性，SYTOX Green验证膜破坏机制（荧光增加）。")
    bullet(doc, "计算特点：非动力学，是深度学习判别式大规模推理，计算资源：GPU集群数天，数据库搜索用MMseqs2加速。")

    heading2(doc, "2.3 生成式方法（文献补充，非本课题但属量化+深度学习）")
    bullet(doc, "HydrAMP cVAE：编码器将AMP序列映射到潜空间z（维度128），解码器以活性条件c（MIC<10）生成新序列，损失 = 重构损失 + KL散度 + 分类器损失（预训练AMP分类器保证活性）+ 潜空间匹配损失；creativity参数控制与输入相似度，可定向改造已有肽。")
    bullet(doc, "AM Predictor GCN回归器：图构建：残基为节点，接触图（AlphaFold预测，距离<8Å连边）为边，节点特征为ESM-2嵌入（1280维）+ 理化；图卷积3层→全局池化→MLP回归MIC，RMSE 0.535，PCC 0.71，SHAP解释关键残基；用于GAN生成肽打分。")
    bullet(doc, "GAC-BiTCNN-AMP（2026）：GAN增强数据多样性 + Capsule Network建模层次依赖 + BiTCNN捕捉上下文 + PsePSSM-DCT进化特征 + XGB特征选择 + SHAP可解释，准确率97.42%，MCC 0.923。")

    heading(doc, "三、抗菌肽与AD结合的计算方法：对接+动力学模拟+自由能（是动力学+量化）")

    heading2(doc, "3.1 分子对接（Docking）：静态量化计算")
    para(doc, "对接用于预测抗菌肽与Aβ或AChE的结合位点和亲和力，不是动力学，是构象搜索+打分函数量化计算。")
    bullet(doc, "工具：AutoDock Vina（速度快，适合高通量虚拟筛选）、AutoDock 4（Lamarckian遗传算法+经验自由能函数）、HDOCK（蛋白-蛋白对接，适用于LL-37-Aβ）。")
    bullet(doc, "步骤：① 受体准备：Aβ42结构来自PDB 1IYT或AlphaFold预测，加氢、加电荷、能量最小化；AChE结构来自PDB 1ACJ，去除水和配体，定义PAS口袋（Trp279、Tyr70、Tyr121等）。② 配体准备：抗菌肽序列建模（PEP-FOLD或AlphaFold），加电荷。③ 口袋定义：以PAS为中心，盒子大小20×20×20Å。④ 对接：Vina exhaustiveness=20，产生9个pose，按结合能（kcal/mol）排序，取最低。⑤ 评分：Vina score ≈ -7至-10 kcal/mol为强结合；De Ferrari 2001年报道Site I 35肽Kd 184μM对应ΔG≈-5 kcal/mol。")
    bullet(doc, "文献实例：De Ferrari 2001年用对接发现AChE上4个潜在Aβ结合位点，Site I为疏水表面；2025年BiLSTM生成新肽+对接筛选Aβ结合肽，取Top 10进入MD。")

    heading2(doc, "3.2 分子动力学模拟（MD）：动力学模拟")
    para(doc, "MD是动力学模拟，模拟原子随时间运动，验证对接复合物稳定性，观察构象变化。")
    bullet(doc, "软件：GROMACS 2022.5或AMBER 20，力场CHARMM36m或ff14SB，适用于蛋白和肽。")
    bullet(doc, "体系构建：对接复合物放入立方水盒子，TIP3P水模型，边界距蛋白12Å，加Na+/Cl-中和至150 mM，约5-10万原子。")
    bullet(doc, "能量最小化：最陡下降5000步，收敛阈值1000 kJ/mol/nm。")
    bullet(doc, "平衡：NVT 100ps（310K，V-rescale控温）+ NPT 100ps（1 bar，Parrinello-Rahman控压），约束蛋白重原子。")
    bullet(doc, "生产模拟：全原子MD，时间步2fs，LINCS约束氢键，PME处理静电，截断1.2nm，NPT系综310K，模拟时长20ns-1μs：")
    bullet(doc, "  - Atanasova 2020：AChE-Aβ复合物1μs (1000ns)，显示稳定，Aβ主要停留344-361区段，RMSD<3Å。")
    bullet(doc, "  - BiLSTM+MD 2025：ADNP7-Aβ42复合物20ns，RMSD稳定2-3Å，Rg稳定，氢键数稳定，证实稳定。")
    bullet(doc, "  - REMD副本交换MD：Amentoflavone抑制Aβ聚集研究用REMD，32个副本，温度300-500K，每2ps交换，200ns/副本，共6.4μs采样，克服能垒，得到构象簇。")
    bullet(doc, "分析：RMSD（稳定性）、RMSF（柔性）、Rg（紧密度）、SASA（溶剂可及）、氢键数、二级结构（DSSP）、构象聚类（GROMOS，cutoff 0.2nm）。")

    heading2(doc, "3.3 结合自由能计算（MM-PBSA/MM-GBSA）：量化计算，基于MD轨迹")
    para(doc, "MM-PBSA是量化计算，基于MD轨迹后处理，估算结合自由能，比对接打分更准。")
    bullet(doc, "公式：ΔG_bind = G_complex - (G_receptor + G_ligand) = ΔE_MM + ΔG_solv - TΔS")
    bullet(doc, "  ΔE_MM = ΔE_vdw + ΔE_elec（真空分子力学范德华+静电）")
    bullet(doc, "  ΔG_solv = ΔG_PB/GB + ΔG_SA（极性溶剂化Poisson-Boltzmann/Generalized Born + 非极性表面积）")
    bullet(doc, "  -TΔS熵贡献常省略，因计算贵且不改善与实验一致性。")
    bullet(doc, "工具：g_mmpbsa（GROMACS）或gmx_MMPBSA 1.6.3，取MD最后25%轨迹，每100ps一帧，共200帧。")
    bullet(doc, "文献实例：")
    bullet(doc, "  - BiLSTM+MD 2025：ADNP7-Aβ42 MM/PBSA -50.6 kcal/mol，疏水和芳香作用主导，PHE12和TRP50贡献大。")
    bullet(doc, "  - RR-AFC破坏Aβ原纤维：盲对接复合物MM-PBSA -76.28 kJ/mol，静电、范德华、非极性溶剂化主导。")
    bullet(doc, "  - Amentoflavone抑制Aβ：200ns MD后MM/PBSA，能量分解显示16KLVFFAEDV24疏水核心是热点，非极性贡献>71%。")
    bullet(doc, "  - 适配体研究：10-15ns MD后MM/PBSA，ΔG与实验Kd相关，DNA适配体r=0.616。")
    bullet(doc, "残基分解：MmPbSaDecomp.py计算每个残基对ΔG贡献，找出热点，如Ala2、Phe4、Tyr10等贡献最大-43.1 kcal/mol。")

    heading2(doc, "3.4 本课题中计算方法分工")
    table(doc, ["阶段","方法类型","具体工具","时长/参数","输出","是否动力学"], [
        ["AMP挖掘","深度学习判别","LSTM/Attention/BERT, AdamW, Focal Loss","5折交叉, epoch 50, batch 64","抗菌概率","否"],
        ["表达去重","生物信息量化","CD-HIT, 宏蛋白组质谱","90%聚类","真实存在肽清单","否"],
        ["AChE-Aβ界面筛选","分子对接","AutoDock Vina, 口袋PAS 20Å","exhaustiveness 20, 9 poses","结合能Top 10","否，静态"],
        ["复合物稳定性","分子动力学","GROMACS, CHARMM36, TIP3P, NPT 310K","20ns-1μs, 2fs步长","RMSD/Rg/氢键","是，动力学"],
        ["结合能排序","自由能计算","g_mmpbsa, MM-PBSA","最后25%轨迹200帧","ΔG_bind, 残基分解","否，基于MD的量化"],
        ["BBB穿透预测","理化量化+经验规则","电荷、疏水性、分子量","电荷>+2, <5kDa","AMT可能性","否"],
    ], widths=[1.5,2.0,2.5,2.5,2.0,1.2])

    heading(doc, "四、抗菌肽与AD结合、肠道、BBB的整合（同前版，略）")

    para(doc, "抗菌肽与AD结合：Aβ本身抗菌[6-8]，LL-37纳摩尔结合Aβ抑制纤维但稳定寡聚体[15,16]，AChE-PAS成核中心[24-26]；肠道调控：菌群失调促炎↑产丁酸↓[18,19]，LPS 3倍与斑块共定位[21,22]，P. gingivalis[23]，TLR4/MyD88/NF-κB正反馈，细菌淀粉样交叉播种，SCFA/TMAO调节；BBB穿透：5类转运RMT/AMT[27-30]，阳离子AMT电荷关键[29]，LRP1外排RAGE内流失衡[28]，LL-37经CLIC1致病[13,14]，病理BBB通透↑。肠-血-脑轴整合模型同前。")

    heading(doc, "五、参考文献（详细版）")
    for i, ref in enumerate(REFS, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.2
        run = p.add_run(f"[{i}] {ref}")
        run.font.size = Pt(8.8)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    return doc

if __name__ == "__main__":
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    from docx import Document as D
    saved = D(str(OUT))
    chars = sum(len(p.text) for p in saved.paragraphs)
    print(f"wrote {OUT.relative_to(ROOT)} paragraphs={len(saved.paragraphs)} tables={len(saved.tables)} chars={chars}")
