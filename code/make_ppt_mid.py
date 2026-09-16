#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_mid.py - 中间版（提交给老师）PPT：整份页数砍一半（16 -> 8，含机制页 12）。

完整版 16 页（deliverable/）保持不动。本版是同一份内容的压缩稿：

    封面
    研究背景与切入点
    研究思路与完成进度（figA）
    队列分阶段 + 三模型共识预测（figB）
    分阶段差异 + 宏蛋白组二次去重（figD）
    机制关联与抑菌实验验证（figE）
    进度与开题计划对照（原生表格，4 行）
    后续安排与总结（含致谢）

版式、配色、参考线、最小字号（15 pt）与 H 版完全一致 —— 直接复用
`make_ppt_nature.py` 的版式函数，所以两版看起来是一套东西。

用法
----
    python code/make_ppt_mid.py           # 中间版 1（篇幅减半，进度同完整版）-> 中间版/
    python code/make_ppt_mid.py --half    # 中间版 2（进度也减半）-> 中间版2/
    python code/make_ppt_mid.py --audit   # 顺带跑 nature-skills 的审计脚本
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_ppt_nature as N          # noqa: E402  (复用 H 版版式与配色)
import make_ppt_mech as MECH         # noqa: E402  (机制补充页)

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = ROOT / "docs" / "ppt_outline.json"
OUT = ROOT / "中间版" / "中期答辩_H_nature风.pptx"
OUT_HALF = ROOT / "中间版2" / "中期答辩_H_nature风.pptx"
QA_DIR = ROOT / "results" / "qa"


def build_mid(meta: dict, cover: dict, total: int = 8) -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = N.SLIDE_W, N.SLIDE_H

    # 1 封面 ---------------------------------------------------------------
    N.cover(prs, cover, total, meta)

    # 2 背景与切入点 -------------------------------------------------------
    N.claim_slide(prs, 2, total,
        headline="肠—脑轴把 AD 与肠道微生物组联系起来，但缺少落到分子层面的对象",
        support=[
            "AD 患者与健康人群的肠道微生物组在组成与功能上存在差异，菌群失衡可通过免疫与代谢途径影响中枢炎症状态。",
            "微生物基因组的小开放阅读框可编码抗菌肽，直接存在于肠腔，是连接微生物刺激与神经炎症的候选效应分子；"
            "现有研究缺少面向 AD 人群、并按认知阶段分层比较的工作。",
        ],
        aside=["本次汇报重点：", "研究思路，以及各项", "工作完成到哪一步；",
               "不展开技术细节。"],
        note="研究背景可以概括为两句话：AD 与肠道微生物组的关系已有较多证据；微生物基因组编码的抗菌肽是可能的效应分子。"
             "现有研究缺少面向 AD 人群、按认知阶段分层的分析，这就是本课题的切入点。"
             "本次汇报重点说明研究思路和各项工作的完成程度。")

    # 3 研究思路与完成进度 -------------------------------------------------
    N.figure_slide(prs, 3, total,
        headline="研究按“数据—预测—统计—功能”四层推进，主体分析已完成",
        figure="figA_研究思路总览.png", layout="full",
        reading="数据与序列、预测、统计与表达三层已完成，功能层正在实施；整体进度与开题计划一致。",
        caption="研究技术路线与完成状态",
        note="整体研究分四层：数据与序列层、预测层、统计与表达层、功能层。"
             "前三层已完成，第四层正在实施，这也是本次中期检查要说明的完成度。")

    # 4 队列与三模型共识预测 -----------------------------------------------
    N.figure_slide(prs, 4, total,
        headline="队列按认知功能分五个阶段，三模型一致阳性才纳入候选集合",
        figure="figB_三模型预测.png", layout="rail",
        reading="队列按 NC、SCS、SCD、MCI 与 AD 五个认知阶段分组，样本与元数据一一对应；"
                "Attention、LSTM、BERT 三个模型相互独立地给出预测，只有三者一致判为阳性的序列才进入候选集合，"
                "以降低单一模型的偏倚。该步骤已完成。",
        source="图：本项目自制（results/figures/figB）",
        note="队列按认知功能分为 NC、SCS、SCD、MCI 与 AD 五个阶段，样本的临床分组信息与测序数据一一对应。"
             "预测环节采用 Attention、LSTM、BERT 三个模型分别预测，只有三者一致判为阳性的序列才纳入候选集合，"
             "目的是降低单一模型的假阳性。这一步已经完成。")

    # 5 分阶段差异与二次去重 -----------------------------------------------
    N.figure_slide(prs, 5, total,
        headline="宏蛋白组表达证据二次去重后，得到健康人与各阶段特有抗菌肽",
        figure="figD_宏蛋白组去重.png", layout="full",
        reading="先按认知阶段比较候选抗菌肽的丰度与组成差异，再引入宏蛋白组表达证据，剔除“有预测、无表达”的序列；"
                "二次去重后按组内共有、组间特比较，得到健康人群特有与各阶段特有的抗菌肽清单。该步骤已完成。",
        note="差异分析按认知阶段分组比较候选抗菌肽的丰度与组成差异；随后引入宏蛋白组表达证据做二次去重，"
             "只保留在蛋白层面可检出的序列，再按组内共有、组间特比较，得到健康人群特有与各阶段特有的抗菌肽清单。"
             "这两步都已完成。")

    # 6 机制与验证 ---------------------------------------------------------
    N.figure_slide(prs, 6, total,
        headline="机制关联与抑菌实验验证正在开展",
        figure="figE_机制关联.png", layout="rail",
        reading="机制关联从三个方向展开：候选肽与 Aβ 的相互作用及其对聚集的影响、与 AChE 外周阴离子位点结合从而"
                "干扰成核的可能性、以及经免疫与炎症通路参与神经炎症的可能性，结论定位为线索发现。"
                "抑菌实验验证以代表性候选肽对大肠杆菌与金黄色葡萄球菌进行纸片扩散法初筛，"
                "并以微量肉汤稀释法测定最低抑菌浓度。",
        source="图：本项目自制（results/figures/figE）",
        note="机制关联参照乙酰胆碱酯酶—β-淀粉样肽复合物分子模拟研究的思路，从与 Aβ 的相互作用、与 AChE 外周阴离子位点"
             "结合、以及免疫与炎症通路三个方向展开，把结论定位为线索发现。抑菌实验验证选取有代表性的候选抗菌肽人工合成，"
             "以大肠杆菌与金黄色葡萄球菌为指示菌，先用纸片扩散法初筛，再用微量肉汤稀释法测最低抑菌浓度。"
             "两项工作正在开展。")

    # 7 进度与开题对照 -----------------------------------------------------
    N.table_slide(prs, 7, total,
        headline="与开题计划相比，研究方向未变，预测与去重环节做了调整",
        rows=[
            ("数据准备", "使用公开宏基因组数据", "已完成全队列数据处理与参考集构建"),
            ("候选肽挖掘", "提取 sORF 并预测抗菌肽", "已完成短肽库构建与三模型共识预测"),
            ("差异分析", "按病程阶段比较", "已完成分阶段差异分析，新增宏蛋白组二次去重"),
            ("机制与验证", "功能与可视化分析", "正在开展机制关联分析与抑菌实验验证"),
        ],
        note="这张表把开题计划与现阶段结果逐条对照：数据准备、候选肽挖掘、差异分析三项已完成；"
             "模型方案由自建模型改为三个已发表模型协同预测；机制与验证环节正在实施。研究方向没有变，"
             "调整都发生在方法层面。")

    # 8 后续安排与总结 -----------------------------------------------------
    N.closing(prs, 8, total,
        headline="主体分析已完成，后续安排集中在验证与撰写",
        lines=[
            "已完成：数据资源与参考集、短肽库、三模型共识预测、分阶段差异分析、宏蛋白组二次去重与特有抗菌肽筛选。",
            "进行中：特有抗菌肽的机制关联分析、候选抗菌肽的抑菌实验验证，"
            "以及学位论文与以第一作者投稿的 SCI 论文撰写。",
            "时间安排：按开题计划推进，后续不依赖新的数据生产，整体风险可控。",
        ],
        note="总结一下：主体分析工作已经在中期完成，后续是机制关联的结论整理、抑菌实验验证和论文撰写，"
             "整体风险可控。我的汇报到此结束，请各位老师批评指正。",
        thanks=True)

    return prs


def build_half(meta: dict, cover: dict, total: int = 8) -> Presentation:
    """中间版 2：内容减半 + **进度也减半**（只把数据与预测算作中期完成的工作）。"""
    prs = Presentation()
    prs.slide_width, prs.slide_height = N.SLIDE_W, N.SLIDE_H

    # 1 封面 ---------------------------------------------------------------
    N.cover(prs, cover, total, meta)

    # 2 背景与切入点（含"本次汇报重点"窄栏，进度口径写清楚）-----------------
    N.claim_slide(prs, 2, total,
        headline="肠—脑轴把 AD 与肠道微生物组联系起来，但缺少落到分子层面的对象",
        support=[
            "AD 患者与健康人群的肠道微生物组在组成与功能上存在差异，菌群失衡可通过免疫与代谢途径影响中枢炎症状态。",
            "微生物基因组的小开放阅读框可编码抗菌肽，直接存在于肠腔，是连接微生物刺激与神经炎症的候选效应分子；"
            "现有研究缺少面向 AD 人群、并按认知阶段分层比较的工作。",
        ],
        aside=["本次汇报重点：", "研究思路，以及各项", "工作完成到哪一步；",
               "本次中期前完成数据", "与预测工作，其余按", "计划在下一阶段推进。"],
        note="研究背景可以概括为两句话：AD 与肠道微生物组的关系已有较多证据；微生物基因组编码的抗菌肽是可能的效应分子。"
             "现有研究缺少面向 AD 人群、按认知阶段分层的分析，这就是本课题的切入点。"
             "本次汇报重点说明研究思路和各项工作的完成程度：中期前完成数据与预测工作，其余环节按计划在下一阶段推进。")

    # 3 研究思路与半程进度（专用图：4/8 完成 + 4/8 下一阶段）----------------
    N.figure_slide(prs, 3, total,
        headline="研究按“数据—预测—统计—功能”四层推进，数据与预测阶段已完成",
        figure="figA_研究思路总览_半程.png", layout="full",
        reading="八项工作分为两半：数据资源、参考集、短肽库与三模型共识预测四项已完成；"
                "分阶段差异分析、宏蛋白组二次去重、特有抗菌肽筛选与机制关联验证四项按计划在下一阶段推进。",
        caption="研究技术路线与完成状态（4/8 已完成）",
        note="整体研究分四个层次：数据与序列层、预测层、统计与表达层、功能层，共八项工作。"
             "本次中期完成的是数据与预测这一半：数据资源与参考集、微生物源短肽库、三模型共识预测；"
             "另一半是分阶段差异分析、宏蛋白组二次去重、特有抗菌肽筛选以及机制关联与验证，"
             "实施方案已经确定，按计划在中期之后推进。")

    # 4 队列与三模型共识预测（已完成）--------------------------------------
    N.figure_slide(prs, 4, total,
        headline="队列按认知功能分五个阶段，三模型一致阳性才纳入候选集合",
        figure="figB_三模型预测.png", layout="rail",
        reading="队列按 NC、SCS、SCD、MCI 与 AD 五个认知阶段分组，样本与元数据一一对应；"
                "Attention、LSTM、BERT 三个模型相互独立地给出预测，只有三者一致判为阳性的序列才进入候选集合。"
                "该步骤已完成，候选抗菌肽名单已产出。",
        source="图：本项目自制（results/figures/figB）",
        note="队列按认知功能分为 NC、SCS、SCD、MCI 与 AD 五个阶段，样本的临床分组信息与测序数据一一对应。"
             "预测环节采用 Attention、LSTM、BERT 三个模型分别预测，只有三者一致判为阳性的序列才纳入候选集合，"
             "目的是降低单一模型的假阳性。这一步已经完成，候选名单已经产出。")

    # 5 分阶段差异分析（下一阶段）------------------------------------------
    N.figure_slide(prs, 5, total,
        headline="下一阶段：分阶段比较候选抗菌肽，并引入表达证据二次去重",
        figure="figC_分阶段差异分析.png", layout="full",
        reading="按认知阶段分组比较候选抗菌肽的丰度与组成差异，识别随病程变化的候选抗菌肽；"
                "再以宏蛋白组表达证据二次去重，剔除缺少蛋白层面支持的序列，"
                "并筛选健康人群特有与各阶段特有的抗菌肽。两项工作已确定实施方案，自中期后启动。",
        note="下一阶段先做分阶段差异分析：按认知阶段分组比较候选抗菌肽的丰度与组成差异，"
             "识别随病程变化的候选抗菌肽；再引入宏蛋白组表达证据做二次去重，剔除没有表达支持的序列，"
             "筛选出健康人群特有与各疾病阶段特有的抗菌肽清单。这两项工作的方案已经确定，中期之后启动。")

    # 6 机制关联与抑菌实验验证（下一阶段）----------------------------------
    N.figure_slide(prs, 6, total,
        headline="下一阶段：机制关联分析，以及候选抗菌肽的抑菌实验验证",
        figure="figE_机制关联.png", layout="rail",
        reading="机制关联从三个方向展开：候选肽与 Aβ 的相互作用及其对聚集的影响、与 AChE 外周阴离子位点结合从而"
                "干扰成核的可能性、以及经免疫与炎症通路参与神经炎症的可能性，结论定位为线索发现。"
                "抑菌实验验证以代表性候选肽对大肠杆菌与金黄色葡萄球菌进行纸片扩散法初筛，"
                "并以微量肉汤稀释法测定最低抑菌浓度。两项工作均已确定方案。",
        source="图：本项目自制（results/figures/figE）",
        note="机制关联参照乙酰胆碱酯酶—β-淀粉样肽复合物分子模拟研究的思路，从与 Aβ 的相互作用、与 AChE 外周阴离子位点"
             "结合、以及免疫与炎症通路三个方向展开，把结论定位为线索发现。抑菌实验验证选取有代表性的候选抗菌肽人工合成，"
             "以大肠杆菌与金黄色葡萄球菌为指示菌，先用纸片扩散法初筛，再用微量肉汤稀释法测最低抑菌浓度。这两项均已确定方案，"
             "待差异分析与特有肽清单完成后依次实施。")

    # 7 进度与开题对照（半程口径）------------------------------------------
    N.table_slide(prs, 7, total,
        headline="与开题计划相比：数据与预测已完成，分析与验证在下一阶段",
        rows=[
            ("数据准备", "使用公开宏基因组数据", "已完成队列数据处理与参考集构建"),
            ("候选肽挖掘", "提取 sORF 并预测抗菌肽", "已完成短肽库构建与三模型共识预测"),
            ("差异分析", "按病程阶段比较", "下一阶段开展，方案与输入数据已确定"),
            ("机制与验证", "功能与可视化分析", "下一阶段开展，机制与抑菌方案已确定"),
        ],
        note="这张表把开题计划与现阶段结果逐条对照：数据准备、候选肽挖掘两项已完成；"
             "分阶段差异分析与宏蛋白组二次去重、机制关联与抑菌实验验证安排在下一阶段，方案已经确定。"
             "研究方向没有变，调整都发生在方法层面。")

    # 8 下一阶段安排与总结 --------------------------------------------------
    N.closing(prs, 8, total,
        headline="阶段目标明确，下一阶段按计划推进",
        lines=[
            "已完成：全队列宏基因组数据处理与微生物基因组参考集、微生物源短肽库，以及三模型共识预测的候选抗菌肽名单。",
            "下一阶段：分阶段差异分析与宏蛋白组二次去重、特有抗菌肽筛选，随后开展机制关联分析与抑菌实验验证。",
            "时间安排：按开题计划推进，分析与验证所需数据与方案均已具备，"
            "学位论文与以第一作者投稿的 SCI 论文撰写同步准备。",
        ],
        note="总结一下：中期完成的是数据与预测这一半，候选抗菌肽名单已经形成；"
             "下一阶段推进分阶段差异分析、二次去重与特有肽筛选，随后开展机制关联分析与抑菌实验验证，"
             "论文撰写同步准备。我的汇报到此结束，请各位老师批评指正。",
        thanks=True)

    return prs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--half", action="store_true",
                    help="出中间版 2（进度也减半）到 中间版2/")
    ap.add_argument("--no-mech", action="store_true",
                    help="不追加后面的 4 页机制补充页")
    a = ap.parse_args(argv)

    outline = json.loads(OUTLINE.read_text(encoding="utf-8"))
    meta = outline["meta"]
    cover = outline["slides"][0]

    out = OUT_HALF if a.half else OUT
    total = 8 if a.no_mech else 12
    prs = build_half(meta, cover, total) if a.half else build_mid(meta, cover, total)
    if not a.no_mech:
        MECH.append(prs, first_idx=9, total=total)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))

    slides = len(prs.slides._sldIdLst)
    runs = sum(len(p.runs) for s in prs.slides for sh in s.shapes if sh.has_text_frame
               for p in sh.text_frame.paragraphs)
    print(f"wrote {out.relative_to(ROOT)}")
    print(f"slides: {slides} (完整版 16 页) | runs: {runs}"
          f"{' | 进度口径：前四项已完成、其余下一阶段' if a.half else ''}")

    if a.audit:
        script = N.AUDIT
        if not script.exists():
            print("先运行 python code/fetch_nature_skills.py 下载审计脚本")
            return 1
        QA_DIR.mkdir(parents=True, exist_ok=True)
        tag = "中期版2" if a.half else "中期版"
        md = QA_DIR / f"{tag}_audit.md"
        js = QA_DIR / f"{tag}_audit.json"
        rc = subprocess.run([sys.executable, str(script), str(out), "--report", str(md),
                             "--json", str(js), "--fail-on", "none"]).returncode
        print(f"skill audit -> {md.relative_to(ROOT)} / {js.relative_to(ROOT)}")
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
