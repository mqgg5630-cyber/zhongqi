#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度机制版：抗菌肽与AD结合、肠道菌群调控导致AD、BBB穿透
重点：分子动力学 + 量子化学 + 增强采样 + 自由能计算 的文献方法细节
"""
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "deliverable" / "抗菌肽与AD结合机制_分子动力学与量子化学_深度版.docx"

doc = Document()

style = doc.styles['Normal']
style.font.name = '宋体'
style.font.size = Pt(12)
style.paragraph_format.line_spacing = 1.15
style.paragraph_format.space_after = Pt(6)

def add_title(t, level=1):
    p = doc.add_heading(t, level=level)
    return p

def add_para(text):
    p = doc.add_paragraph(text)
    return p

def add_bullet(text):
    p = doc.add_paragraph(text, style='List Bullet')
    return p

# 封面
p = doc.add_paragraph()
p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
run = p.add_run("抗菌肽与AD结合机制_分子动力学与量子化学_深度版\n")
run.bold = True
run.font.size = Pt(18)
run = p.add_run("重点：抗菌肽如何结合AD、如何通过肠道菌群调控导致AD、如何进入血脑屏障导致AD\n分子动力学、量子化学、增强采样、自由能计算的文献方法拆解")
run.font.size = Pt(12)

add_para("研究生：文绍华  学号：2024110316  指导教师：申亮  生命科学学院  2026年9月  分支：arena/01a0a949-zhongqi")
add_para("本文档对应老师追问的三大机制，采用Light-skills检索策略：每类机制按 计算方法分类→工具→参数→时长→公式→实例→证据强度 结构化回答。")

# 一、总览
add_title("一、三大机制总览与计算方法分工", level=1)
add_para("1. 抗菌肽与AD结合（直接结合）：Aβ本身是抗菌肽，LL-37与Aβ纳摩尔亲和，HNP-1二聚体结合Aβ/hIAPP五聚体的β-sheet和U-turn区，改变聚集路径。计算方法：分子对接（HDOCK蛋白-蛋白）+ 全原子MD（GROMACS/AMBER CHARMM36m/ff14SB TIP3P 20ns-1μs）+ 增强采样（REMD 32副本 300-500K 6.4μs，伞形采样23窗口0.05nm WHAM）+ 自由能MM-PBSA/MM-GBSA（-50.6 kcal/mol, -76.28 kJ/mol, -8.7±0.7 kcal/mol）+ 量子化学（QM/MM FMO DFT B3LYP GFN2-xTB metadynamics）。")
add_para("2. 肠道菌群调控导致AD（间接调控）：肠道失调→肠屏障↑→LPS入血→TLR4/MD-2激活→NF-κB→IL-1β/TNF-α→APP/Aβ/抗菌肽↑正反馈；细菌淀粉样CsgA与Aβ交叉播种；SCFA丁酸抗炎↓TMAO激活NLRP3。计算方法：分子对接（papiliocin与TLR4/MD-2，AutoDock Vina，STD NMR验证，Kd微摩尔，R13/R16关键）+ MD（TLR4/MD-2/LPS复合物稳定性）+ 网络药理学（260代谢物→196靶点→14核心IL6/NFKB1/IL1B/PTGS2/TLR4/PPARG，CB-Dock2盲对接 -6.8~-8.1 kcal/mol）+ 系统生物学。")
add_para("3. 血脑屏障穿透导致AD（入脑路径）：BBB结构紧密连接，5类转运（旁路极受限、亲脂扩散、载体介导、RMT LRP1/RAGE/TfR、AMT阳离子与阴离子糖萼静电吸附）。抗菌肽+2~+9阳离子符合AMT，精氨酸越多越强；LL-37 37aa +6符合。计算方法：全原子MD+增强采样（R9与MPG在人脑微血管内皮细胞真实膜模型，伞形采样/偏置交换，自由能垒显著，N端精氨酸起始，多不饱和脂肪酸链可塑性关键）+ 粗粒化MD + 对接（Angiopep-2/O-BBB与LRP1）。病理BBB破坏claudin-5/occludin↓，LPS/炎症↑通透，Braniste 2014无菌小鼠BBB↑ SCFA恢复。")

# 二、抗菌肽与AD结合的MD与QM
add_title("二、抗菌肽与AD结合：分子动力学与量子化学方法拆解", level=1)

add_title("2.1 经典全原子MD：GROMACS/AMBER", level=2)
add_para("软件：GROMACS 2022.5/5.1.4/2020, AMBER 20, LAMMPS；力场：CHARMM36m, ff14SB, GROMOS96 43a1, OPLS-AA；水模型：TIP3P/SPC；适用于蛋白-肽复合物。")
add_bullet("体系构建：对接复合物（HDOCK或Vina）放入立方水盒子，TIP3P，边界距蛋白12Å，加NaCl 150mM中和，5-10万原子；对于膜体系：人脑微血管内皮细胞真实膜模型，含PC/PE/PS/胆固醇/多不饱和脂肪酸链（PLUMED 2.2.0插件）。")
add_bullet("能量最小化：最陡下降5000步，收敛阈值1000 kJ/mol/nm。")
add_bullet("平衡：NVT 100ps 310K V-rescale控温 + NPT 100ps 1bar Parrinello-Rahman控压，约束重原子。")
add_bullet("生产：全原子MD步长2fs LINCS约束氢键 PME静电截断1.2nm NPT 310K 20ns-1μs：Atanasova 2020 AChE-Aβ 1μs RMSD<3Å停留344-361区段；BiLSTM+MD 2025 ADNP7-Aβ42 20ns RMSD2-3Å Rg稳定氢键数稳定；R9/MPG BBB穿透MD 2026 显著自由能垒，R9诱导更大膜扰动，N端精氨酸起始结合。")
add_bullet("分析：RMSD稳定性、RMSF柔性、Rg紧密度、SASA溶剂可及、氢键数、DSSP二级结构、GROMOS聚类cutoff0.2nm、PCA主成分、接触图。")

add_title("2.2 增强采样：REMD、伞形采样、Metadynamics", level=2)
add_para("经典MD受限于能垒，Aβ为内在无序肽，构象空间大，需增强采样。")
add_bullet("REMD副本交换：Amentoflavone抑制Aβ聚集用REMD 32副本温度300-500K每2ps交换200ns/副本共6.4μs克服能垒，得到构象簇；Atanasova 2020也用REMD验证AChE-Aβ第二界面。")
add_bullet("伞形采样Umbrella Sampling：定义反应坐标CV：单体-单体质心距离0.20-1.30nm，23窗口每0.05nm一窗，每窗145ns+5ns平衡，谐振偏置，WHAM构建PMF势能平均力；用于Aβ二聚化自由能ΔG_Dimerization = ΔG_Release+ΔG_Dissociation；Aβ9-40原纤维延伸自由能计算，不加约束时标准结合自由能偏差大，加Woo&Roux约束后与实验-7.87 kcal/mol吻合，总模拟2.2μs可缩至1.0μs。")
add_bullet("Metadynamics：集体变量CV选RMSD或配位数，沉积高斯偏置势，探索自由能面；量子化学MD中用于Al(III)与Aβ N端结合，GFN2-xTB水平，bias常数k_i/N=0.025 E_h，短20-50ps肽构象灵活后Al配位键断裂，探索Glu/Asp/主链O多种配位模式，证明结合高度易变，所有酸性侧链参与配位。")
add_bullet("副本交换伞形采样REUS：从不同初始条件出发，增强膜蛋白二聚化自由能收敛，解决粗粒化力场近天然构象占优但Kd合理的问题。")

add_title("2.3 自由能计算：MM-PBSA/MM-GBSA/FEP/绝对结合自由能", level=2)
add_para("公式：ΔG_bind = G_complex - (G_rec+G_lig) = ΔE_MM + ΔG_solv - TΔS；ΔE_MM=ΔE_vdw+ΔE_elec；ΔG_solv=ΔG_PB/GB+ΔG_SA极性PB/GB+非极性表面积；-TΔS常省略或准谐近似。")
add_bullet("工具：g_mmpbsa, gmx_MMPBSA 1.6.3, MMPBSA.py (AMBER)；取MD最后25%每100ps一帧200帧。")
add_bullet("实例1：BiLSTM+MD 2025 ADNP7-Aβ42 MM/PBSA -50.6 kcal/mol疏水芳香主导PHE12 TRP50贡献大。")
add_bullet("实例2：RR-AFC破坏Aβ原纤维盲对接-76.28 kJ/mol静电范德华非极性主导。")
add_bullet("实例3：Amentoflavone抑制Aβ 200ns MD后MM/PBSA 16KLVFFAEDV24热点非极性>71%表1。")
add_bullet("实例4：Mint2-APP 400ns 5重复氢键概率>20%筛选，MM-PBSA突变体比WT低6.93 kcal/mol疏水主导。")
add_bullet("实例5：绝对结合自由能Woo&Roux方法：引入构象/取向约束，校正PMF，公式ΔG°= -ΔG_Ω(x_B)+ΔU_Ω(x_B)+ΔG_V，解决无序肽构象熵惩罚，实验Kd -7.87 vs 计算-8.7±0.7 kcal/mol吻合，而FEP 2.3μs得0.55±30.25 kcal/mol偏差大。")
add_bullet("残基分解：MmPbSaDecomp.py每残基贡献找热点Ala2 Phe4 Tyr10等-43.1 kcal/mol。")

add_title("2.4 量子化学：QM/MM, DFT, GFN2-xTB, FMO, QPE", level=2)
add_para("背景：Aβ与金属离子Al(III)/Cu/Zn结合影响聚集，经典力场无法描述电荷转移和配位键断裂，需量子化学。")
add_bullet("QM/MM：QM区选金属+配位残基Glu3 Asp7 Glu11及水，DFT B3LYP/6-31G*或GFN2-xTB半经验，MM区CHARMM36，电子结构每步自洽，响应环境变化。")
add_bullet("GFN2-xTB metadynamics：半经验紧束缚，速度快可达ns级，验证：Al-A单齿结合Asp键长比DFT短0.01-0.03Å，水配位偏差<0.05Å，氢键偏差0.1Å可接受；用于探索Al(H2O)6与EAAAD从氢键接触到配位的无偏发现。")
add_bullet("FMO碎片分子轨道：将大体系分碎片，QM计算每碎片能量后组合，适用于Aβ16金属结合亲和力；工作流：PDB实验几何→经典力场粗优化得多个局部极小→QM/MM精优化→FMO能量比较→加色散和溶剂化校正→结合亲和力= E_protein+metal - (E_protein+E_metal)。")
add_bullet("QPE量子相位估计：双因子化qubitization，T门复杂度评估，用于未来量子计算机加速FMO+FCI级别高精度计算，区分多种配位模式能量差异。")
add_bullet("发现：Al(III)结合N端酸性残基高度易变，配位数内层4外层2-3，单齿Glu3 Asp7双齿Glu11常见，主链O也参与；结合破坏盐桥（Asp23-Lys28重要纤维形成），诱导高螺旋含量，锚定Asp7-Glu11段RMSF<3.6Å，CHC区Leu17-Ala21和C端高度易变，Gly33因氢键低RMSF。")

add_title("2.5 交叉播种：HNP-1与Aβ/hIAPP", level=2)
add_para("Chem Soc Rev 2024综述：唯一近期计算研究结合对接+MD研究HNP-1二聚体与Aβ和hIAPP五聚体结合，强亲和β-sheet和U-turn区，双结合模式干扰侧向缔合和延伸，改变一级二级结构，增强抑制能力。机制：构象选择结合，β-rich结构为结构基础和模板，高度结构相似性降低跨物种势垒，促进异源淀粉样组装。")
add_para("α-防御素以序列非依赖方式抑制淀粉样，β结构接合为核心；Tyrocidine二聚体多态性类似淀粉样，二聚体稳定力不同，有的氢键主导有的疏水主导。")

# 三、肠道菌群调控导致AD
add_title("三、肠道菌群调控导致AD：LPS-TLR4/MD-2与细菌淀粉样", level=1)

add_title("3.1 LPS-TLR4/MD-2轴：对接与MD细节", level=2)
add_para("通路：肠道失调Firmicutes/Bifidobacterium↓ Bacteroidetes↑ (Vogt 2017)；Escherichia/Shigella↑ E.rectale↓与IL-1β/NLRP3正相关(Cattaneo 2017)；LPS与斑块共定位Zhan 2018血浆3倍Zhao 2017 P.gingivalis Dominy 2019；LPS经LBP→CD14→TLR4/MD-2二聚化→MyD88→NF-κB→IL-1β/TNF-α/IL-6→APP/Aβ/抗菌肽↑正反馈；TREM2结合LPS促进小胶质M1极化。")
add_bullet("Papiliocin案例（PNAS 2022）：昆虫抗菌肽，双重机制：①直接结合LPS中和，②竞争性结合TLR4/MD-2抑制LPS结合。方法：结合分析+对接模拟+流式细胞术。STD NMR揭示肽与TLR4/MD-2分子间相互作用。对接用TLR4/MD-2/LPS晶体结构，Papiliocin N端螺旋在TLR4/MD-2界面，C端疏水螺旋插入MD-2疏水口袋，氢键K7-S118, Q31-K122，静电R1-D294模拟LPS内核。亲和力微摩尔级，LPS结合TLR4 1.41×10^-5 M, MD-2 0.87×10^-5 M。关键残基R13/R16突变R13E/R16E结合↓，而K3/K6+柔性铰链G23/P24对LPS结合关键。")
add_bullet("AMP-TLR4对接（PMC 2025）：Tachystatin, Pleurocidin, Subtilisin A与ACE2/CRP/MMP9/NLRP3/TLR4对接，HADDOCK评分，TLR4结合能与范德华r=0.61强相关，Tachystatin氢键46个势能-780,309.925 kcal/mol vs 对照DX600 -755,432.195，更稳定；RMSF显示柔性差异。")
add_bullet("网络药理学+对接（PMC 2025）：260肠道代谢物→196交集靶点→14核心IL6/NFKB1/IL1B/PTGS2/TLR4/PPARG，KEGG富集NOD/TNF/NF-κB，CB-Dock2盲对接，IL6 PDB 1ALU Enterodiol -7.2, NFKB1 1SVC Coumarin -6.8, 3,9-dihydroxy -8.1 kcal/mol，表面可及口袋非实验验证活性位点，需MD验证，RMSD未做。")

add_title("3.2 细菌淀粉样交叉播种与代谢物", level=2)
add_para("细菌淀粉样CsgA等通过分子模拟促进Aβ错误折叠，微胶质 priming；Aβ本身抗菌肽，经TLR2识别触发神经炎症；SCFA丁酸抑制Tau磷酸化、氧化应激、促炎因子，调节小胶质稳态，AD中降低；TMAO激活NLRP3；胆汁酸调节Tau/Aβ和线粒体生物合成；神经递质GABA/5-HT/乙酰胆碱/多巴胺/NE由Lactobacillus/Bacteroides等产生，影响突触可塑性、BDNF、淀粉样清除。")
add_para("计算：粗粒化MD模拟细菌淀粉样与Aβ共聚集，自由能面分析，接触图，氢键网络；代谢物-靶点对接后需MD验证稳定性。")

add_title("3.3 本课题肠道-AMP-AD计算分工", level=2)
add_para("宏基因组层面：476例粪便宏基因组2.19亿sORF→9139万非冗余→757高质量MAGs→1971种代表→sORF挖掘，同Ma 2022流程；差异分析：健康 vs AD各阶段特有抗菌肽，电荷>+2疏水30-70%等筛选；机制假设：肠道特有抗菌肽↑→LPS协同→TLR4激活→Aβ↑→BBB↑→入脑→小胶质激活→AD；验证：对接TLR4/MD-2（Vina 20Å盒子 exhaustiveness20）+ MD 20ns-1μs CHARMM36 TIP3P + MM-PBSA + 细胞实验TNF-α/IL-6/CLIC1检测。")

# 四、BBB穿透
add_title("四、抗菌肽进入血脑屏障导致AD：AMT与RMT的MD与对接", level=1)

add_title("4.1 BBB结构与转运分类", level=2)
add_para("结构：内皮紧密连接（claudin-5/occludin）+基底膜+星形胶质足突；5类转运：①旁路极受限 ②亲脂扩散小分子 ③载体介导 ④RMT受体介导转胞吞TfR LRP1胰岛素受体 ⑤AMT吸附介导转胞吞阳离子与阴离子糖萼（硫酸乙酰肝素唾液酸）静电吸附触发。抗菌肽+2~+9阳离子符合AMT，精氨酸胍基双齿氢键与PO4结合更稳定，平面疏水可溶入膜。")

add_title("4.2 全原子MD+增强采样：R9与MPG案例（2026最新）", level=2)
add_para("文献：Mechanisms of BBB penetration: MD study on R9 and MPG translocation, 2026。方法：真实人脑微血管内皮细胞膜模型（含PC/PE/PS/胆固醇/多不饱和脂肪酸），MD+增强采样（伞形采样/偏置交换），采样集体变量CV：膜弯曲、肽部分去折叠、COM距离。")
add_bullet("结果：R9诱导更大膜扰动 vs MPG，但两者均面临显著自由能垒；首次相互作用由N端发起，精氨酸突出，即使MPG也以精氨酸起始；可塑性关键：BBB弯曲+CPP部分去折叠，长链多不饱和酰基脂质重要作用；为合理设计提供指导。")
add_bullet("对比：R9 Arg9全精氨酸，强AMT；MPG两亲性，含疏水段+亲核定位，自由能垒略低但仍高；力峰对应肽进入膜，656次steered MD拉取7种淀粉样抗菌肽+多肽（Poly Ala/Leu等10聚体）研究穿膜最小阻力。")
add_bullet("模拟参数：CHARMM36m，TIP3P，150mM NaCl，310K，2fs，PME 1.2nm，伞形采样23窗口0.05nm，WHAM，自由能面收敛需副本交换伞形采样REUS从不同初始条件。")

add_title("4.3 其他BBB穿透肽的MD表征（2019-2025）", level=2)
add_bullet("9种BBB穿透肽MD表征（Int J Nanomedicine 2019）：ApoE, Angiopep-2, RVG29, TGN, CooP, tLyp1, RiGD等，ApoE 600ns后β-hairpin（CHARMM36m和OPLS-AA均如此，水中构象），ApoEo类似；RMSD 500ns达平台，CLT-1 300ns后探索多构象，tLyp1 300ns后收敛80簇；PCA自由能面大集体运动驱动靶标相互作用。")
add_bullet("Fc-PepH3平台（ACS Med Chem Lett 2021）：PepH3可逆跨内皮膜AMT，静电相互作用快速， vs FC5 RMT需受体，动力学曲线不同；DPepH3对映体策略验证受体非依赖，内化经巨胞饮；血清稳定性t1/2↑。")
add_bullet("O-BBB融合AMP（Sci Rep 2025）：Borrelia OspA内皮结合域N端β-sheet10-11（O-BBB）净电荷-3.4 pH7减少非特异静电，融合Cx7C环肽Bor-11/16/18/26，EC50 0.41-0.83μM对螺旋体/囊性，1h内膜去极化，BBB模型穿透1h显著高于angiopep-2 (P=0.0175)，2h匹配，3h更高；机制：OspA-CD40相互作用模拟RME。")
add_bullet("CPP体内BBB流入（PLoS One 2015）：Tat47-57 4.73, SynB3 5.63, pVEC 6.02 μl/g/min高流入，TP10 0.05接近零；非饱和机制（过量10μg未抑制），pVEC Vi从24→1 μl/g饱和结合位点；二级结构膜界面pVEC β-sheet, TP10 α-helix, SynB3/Tat无规卷曲；脑内流不能与细胞穿透能力正相关。")

add_title("4.4 RMT与AMT的计算设计", level=2)
add_para("RMT：Aβ经LRP1脑→血外排，RAGE血→脑内流失衡蓄积Zlokovic 2009；抗菌肽利用LRP1类似Angiopep-2（TFFYGGSRGKRNNFKTEEY）净电荷+2，乳铁蛋白经LRP1转运，AD中LRP1上调；对接：Angiopep-2与LRP1簇，盒子20Å，Vina评分-7~-9 kcal/mol。")
add_para("AMT：阳离子AMP与硫酸乙酰肝素唾液酸静电吸附，精氨酸胍基双齿氢键与PO4，电荷是AMT关键预测因子，LL-37 37aa +6符合；MD显示高浓度B2088分支AMP在细菌膜快速积累氢键稳定，精氨酸Bidentate更有利，平面胍基疏水可溶入膜，浓度依赖结构扰动，水跨膜转位↑。")
add_para("病理BBB↑：AD中claudin-5/occludin↓，LPS/炎症↑通透，Braniste 2014无菌小鼠BBB通透↑ SCFA丁酸恢复；LPS 3倍血浆，P.gingivalis在AD脑。")

add_title("4.5 穿透后致病：LL-37-CLIC1与肠-血-脑轴", level=2)
add_para("Lee 2015 LL-37诱导TNF-α/IL-6 NF-κB核转位；Chen 2022 LL-37促CLIC1膜转位形成氯通道致小胶质活化ROS Aβ↑NFT↑脑萎缩侧脑室扩大Clic1 KO阻断；Erny 2015菌群控制小胶质成熟。")
add_para("整合模型：肠失调→肠屏障↑→LPS/抗菌肽入血→BBB↑→RAGE/AMT入脑→小胶质TLR4/NLRP3/CLIC1→Aβ/抗菌肽↑→AChE-PAS纤维化→正反馈；证据分级：强（Aβ抗菌、Aβ经LRP1/RAGE转运、AChE经PAS促聚集、MM-PBSA实例），中-强（肠道失衡、LPS共定位、P.gingivalis、LL-37经CLIC1），中（AMT穿透、LL-37与Aβ纳摩尔结合、SCFA调控BBB），待验证（微生物源抗菌肽五阶段变化、候选肽经BBB入脑致病对接→MD→MM-PBSA→细胞检测）。")

# 五、计算方法总结
add_title("五、计算方法总结：如何回答老师追问", level=1)
add_para("老师问：是动力学模拟还是量化计算？回答：三类分工，挖掘用深度学习非动力学，结合机制用对接+MD+自由能（动力学+量化），BBB穿透用MD+自由能（动力学+量化），肠道调控用对接+网络药理学（量化）+MD验证（动力学）。")
add_bullet("量化计算：34维理化+PC6+PsePSSM-DCT静态毫秒级，用于特征工程，非动力学。")
add_bullet("深度学习：LSTM双向128→256 Attention加权，BERT ProtBert 30亿预训练冻结10层微调2层，AdamW Focal Loss 5折AUROC0.95-0.97，非动力学神经网络推理。")
add_bullet("对接：AutoDock Vina盒子20Å exhaustiveness20 9pose评分-7~-10 kcal/mol，HDOCK蛋白-蛋白，CB-Dock2盲对接，静态量化初筛。")
add_bullet("分子动力学：GROMACS CHARMM36 TIP3P水盒子12Å 150mM NVT100ps NPT100ps生产20ns-1μs 2fs LINCS PME1.2nm 310K，REMD 32副本300-500K 200ns/副本共6.4μs，RMSD/Rg/氢键/DSSP聚类。")
add_bullet("增强采样：伞形采样23窗口0.05nm 145ns/窗 WHAM PMF，Metadynamics RMSD CV高斯沉积，REUS副本交换伞形采样克服能垒。")
add_bullet("自由能：MM-PBSA ΔG=G_complex-(G_rec+G_lig)=ΔE_vdw+ΔE_elec+ΔG_PB/GB+ΔG_SA-TΔS g_mmpbsa最后25%200帧-50.6 kcal/mol -76.28 kJ/mol -8.7±0.7 kcal/mol残基分解。")
add_bullet("量子化学：QM/MM DFT B3LYP/GFN2-xTB FMO碎片能量组合 QPE量子相位估计，用于金属结合，配位键长偏差0.01-0.05Å，氢键0.1Å，探索多种配位模式。")
add_bullet("整合：挖掘非动力学，结合是动力学+量化，BBB穿透动力学+量化，肠道调控量化+动力学验证，肠-血-脑轴串联四问。")

add_title("六、本地值守常驻窗口版说明", level=1)
add_para("为解决闪窗问题，新增watch-visible.ps1常驻可见窗口版值守：")
add_bullet("用法：.\\watch-visible.ps1  前台常驻，每2分钟自动拉取，窗口一直显示拉取信息")
add_bullet("注册开机自启可见：.\\watch-visible.ps1 -RegisterVisible  登录后自动打开常驻窗口")
add_bullet("查看状态：.\\watch-visible.ps1 -Status")
add_bullet("移除：.\\watch-visible.ps1 -UnregisterVisible")
add_bullet("特点：不使用隐藏launcher，窗口一直可见，实时显示sync.ps1拉取信息、时间戳、分支、heartbeat、最新5条提交、自动推送、手册检查请求；可与原有watch.ps1零窗口版共存；关闭窗口=暂停值守，10分钟后keeper重启或手动再运行；另开窗口执行命令，不在此窗口输入。")
add_bullet("原有watch.ps1零窗口版仍可用：.\\watch.ps1 -Register 零窗口，.\\watch.ps1 -Register -Flash 闪窗一次，.\\watch.ps1 -Status查看，.\\watch.ps1 -Test自检，.\\watch.ps1 -Focus本会话为活跃，.\\watch.ps1 -RestoreParked恢复其他。")
add_bullet("Light-skills已安装：23个技能（light-literature-search, light-idea-critique, light-figure等）已复制到skills/和.agents/skills/，可用于后续文献检索、想法批判、图表生成等。")

# 保存
OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(str(OUT))
print(f"wrote {OUT} paragraphs={len(doc.paragraphs)}")
