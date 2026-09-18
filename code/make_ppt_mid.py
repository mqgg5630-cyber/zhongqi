#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ppt_mid.py - 中间版（提交给老师）PPT：10 页主体 + 4 页机制补充 = 14 页。

两版共用同一套版式函数（复用 `make_ppt_nature.py`），差别只在进度口径与个别页：

    中间版 1（--half 不加）      进度同完整版：主体分析已完成
    中间版 2（--half）           进度减半：中期前完成数据与预测，其余下一阶段

页面结构（两版一致）：

     1 封面
     2 背景与切入点
     3 研究路线与完成状态（figA / figA_半程）
     4 宏基因组分析流程（原生流程页，含完成状态）
     5 分阶段组的划分（原生分组页）
     6 三模型共识预测（figB）
     7 分阶段差异分析 / 二次去重（figC 或 figD）
     8 机制关联与抑菌实验验证（figE）
     9 与开题计划对照（原生表格）
    10 后续安排与总结（含致谢）
    11—14 机制补充页（七环逻辑链 / AChE–Aβ 动力学 / 八问作答 / 文献支撑）

用法
----
    python code/make_ppt_mid.py           # 中间版 1 -> 中间版/
    python code/make_ppt_mid.py --half    # 中间版 2（进度减半）-> 中间版2/
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
import make_ppt_nature as N          # noqa: E402  (版式与配色)
import make_ppt_mech as MECH         # noqa: E402  (机制补充页)

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = ROOT / "docs" / "ppt_outline.json"
OUT = ROOT / "中间版" / "中期答辩_H_nature风.pptx"
OUT_HALF = ROOT / "中间版2" / "中期答辩_H_nature风.pptx"
QA_DIR = ROOT / "results" / "qa"

MECH_PAGES = 4


def build(meta: dict, cover: dict, total: int = 14, half: bool = False) -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = N.SLIDE_W, N.SLIDE_H
    p = "下一阶段" if half else "已完成"

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
        aside=(["本次汇报重点：", "研究思路，以及各项", "工作完成到哪一步；",
                "中期前完成数据与", "预测工作，其余按", "计划在下一阶段推进。"] if half else
               ["本次汇报重点：", "研究思路，以及各项", "工作完成到哪一步；",
                "不展开技术细节。"]),
        note="研究背景可以概括为两句话：AD 与肠道微生物组的关系已有较多证据；微生物基因组编码的抗菌肽是可能的效应分子。"
             "现有研究缺少面向 AD 人群、按认知阶段分层的分析，这就是本课题的切入点；"
             "本次汇报重点说明研究思路和各项工作的完成程度。")

    # 3 研究路线与完成状态 --------------------------------------------------
    if half:
        N.figure_slide(prs, 3, total,
            headline="研究按“数据—预测—统计—功能”四层推进，数据与预测阶段已完成",
            figure="figA_研究思路总览_半程.png", layout="full",
            reading="八项工作分为两半：数据资源、参考集、短肽库与三模型共识预测四项已完成；"
                    "分阶段差异分析、二次去重、特有肽筛选与机制验证四项在下一阶段推进。",
            caption="研究技术路线与完成状态（4/8 已完成）",
            note="整体研究分四个层次：数据与序列层、预测层、统计与表达层、功能层，共八项工作。"
                 "本次中期完成的是数据与预测这一半；另一半的实施方案已经确定，按计划在中期之后推进。")
    else:
        N.figure_slide(prs, 3, total,
            headline="研究按“数据—预测—统计—功能”四层推进，主体分析已完成",
            figure="figA_研究思路总览.png", layout="full",
            reading="数据与序列、预测、统计与表达三层已完成，功能层正在实施；整体进度与开题计划一致。",
            caption="研究技术路线与完成状态",
            note="整体研究分四层：数据与序列层、预测层、统计与表达层、功能层。"
                 "前三层已完成，第四层正在实施，这也是本次中期检查要说明的完成度。")

    # 4 流程页 -------------------------------------------------------------
    N.std_flow_slide(prs, 4, total, progress=("half" if half else "full"))

    # 5 分组页 -------------------------------------------------------------
    N.std_stage_slide(prs, 5, total)

    # 6 三模型共识预测 ------------------------------------------------------
    N.figure_slide(prs, 6, total,
        headline="队列按认知功能分五个阶段，三模型一致阳性才纳入候选集合",
        figure="figB_三模型预测.png", layout="rail",
        reading="Attention、LSTM、BERT 三个模型相互独立地给出预测，只有三者一致判为阳性的序列进入候选集合，"
                "以降低单一模型的偏倚。该步骤" + p + "。",
        source="图：本项目自制（results/figures/figB）",
        note="预测环节采用 Attention、LSTM、BERT 三个模型分别预测，只有三者一致判为阳性的序列才纳入候选集合，"
             "目的是降低单一模型的假阳性。")

    # 7 差异分析 / 二次去重 -------------------------------------------------
    if half:
        N.figure_slide(prs, 7, total,
            headline="下一阶段：分阶段比较候选抗菌肽，并引入表达证据二次去重",
            figure="figC_分阶段差异分析.png", layout="full",
            reading="按认知阶段比较候选抗菌肽的丰度与组成差异，再以宏蛋白组表达证据二次去重，"
                    "筛选健康人群特有与各阶段特有抗菌肽；实施方案已确定。",
            note="下一阶段先做分阶段差异分析，再引入宏蛋白组表达证据做二次去重，剔除没有表达支持的序列，"
                 "筛选出健康人群特有与各疾病阶段特有的抗菌肽清单。两项工作的方案已经确定。")
    else:
        N.figure_slide(prs, 7, total,
            headline="宏蛋白组表达证据二次去重后，得到健康人与各阶段特有抗菌肽",
            figure="figD_宏蛋白组去重.png", layout="full",
            reading="先按认知阶段比较丰度与组成差异，再引入宏蛋白组表达证据，剔除“有预测、无表达”的序列，"
                    "得到健康人群特有与各阶段特有的抗菌肽清单。该步骤已完成。",
            note="序列层面去冗余解决重复；宏蛋白组表达证据解决“有预测、无表达”的假阳性。"
                 "二次去重后按组内共有、组间特比较，得到健康人群特有与各疾病阶段特有的抗菌肽清单。")

    # 8 机制关联与抑菌实验 --------------------------------------------------
    N.figure_slide(prs, 8, total,
        headline="机制关联与抑菌实验验证正在开展",
        figure="figE_机制关联.png", layout="rail",
        reading="机制关联从三个方向展开：候选肽与 Aβ 的相互作用及其对聚集的影响、与 AChE 外周阴离子位点"
                "结合从而干扰成核的可能性、以及经免疫与炎症通路参与神经炎症的可能性，结论定位为线索发现。"
                "抑菌实验验证以代表性候选肽对大肠杆菌与金黄色葡萄球菌做纸片扩散法初筛，"
                "并以微量肉汤稀释法测定最低抑菌浓度。",
        source="图：本项目自制（results/figures/figE）",
        note="机制关联参照乙酰胆碱酯酶—β-淀粉样肽复合物分子模拟研究的思路，从三个方向展开，"
             "把结论定位为线索发现；抑菌实验验证选取有代表性的候选抗菌肽人工合成，"
             "以大肠杆菌与金黄色葡萄球菌为指示菌，先用纸片扩散法初筛，再用微量肉汤稀释法测最低抑菌浓度。")

    # 9 与开题计划对照 ------------------------------------------------------
    if half:
        N.table_slide(prs, 9, total,
            headline="与开题计划相比：数据与预测已完成，分析与验证在下一阶段",
            rows=[
                ("数据准备", "使用公开宏基因组数据", "已完成队列数据处理与参考集构建"),
                ("候选肽挖掘", "提取 sORF 并预测抗菌肽", "已完成短肽库构建与三模型共识预测"),
                ("差异分析", "按病程阶段比较", "下一阶段开展，方案与输入数据已确定"),
                ("机制与验证", "功能与可视化分析", "下一阶段开展，机制与抑菌方案已确定"),
            ],
            note="开题计划逐条对照：数据准备、候选肽挖掘两项已完成；"
                 "分阶段差异分析与二次去重、机制关联与抑菌实验验证安排在下一阶段，方案已经确定。"
                 "研究方向没有变，调整都发生在方法层面。")
    else:
        N.table_slide(prs, 9, total,
            headline="与开题计划相比，研究方向未变，预测与去重环节做了调整",
            rows=[
                ("数据准备", "使用公开宏基因组数据", "已完成全队列数据处理与参考集构建"),
                ("候选肽挖掘", "提取 sORF 并预测抗菌肽", "已完成短肽库构建与三模型共识预测"),
                ("差异分析", "按病程阶段比较", "已完成分阶段差异分析，新增宏蛋白组二次去重"),
                ("模型方案", "拟构建 DeepMetaAMP", "改用 Attention / LSTM / BERT 三模型协同预测"),
                ("机制与验证", "功能与可视化分析", "正在开展机制关联分析与抑菌实验验证"),
            ],
            note="数据准备、候选肽挖掘、差异分析三项已完成；模型方案由自建模型改为三个已发表模型协同预测；"
                 "机制与验证环节正在实施。研究方向没有变，调整都发生在方法层面。")

    # 10 后续安排与总结 -----------------------------------------------------
    if half:
        N.closing(prs, 10, total,
            headline="阶段目标明确，下一阶段按计划推进",
            lines=[
                "已完成：全队列宏基因组数据处理与微生物基因组参考集、微生物源短肽库，"
                "以及三模型共识预测的候选抗菌肽名单。",
                "下一阶段：分阶段差异分析与宏蛋白组二次去重、特有抗菌肽筛选，"
                "随后开展机制关联分析与抑菌实验验证。",
                "时间安排：按开题计划推进，分析与验证所需数据与方案均已具备，"
                "学位论文与以第一作者投稿的 SCI 论文撰写同步准备。",
            ],
            note="中期完成的是数据与预测这一半，候选抗菌肽名单已经形成；"
                 "下一阶段推进分阶段差异分析、二次去重与特有肽筛选，随后开展机制关联分析与抑菌实验验证，"
                 "论文撰写同步准备。我的汇报到此结束，请各位老师批评指正。",
            thanks=True)
    else:
        N.closing(prs, 10, total,
            headline="主体分析已完成，后续安排集中在验证与撰写",
            lines=[
                "已完成：数据资源与参考集、短肽库、三模型共识预测、分阶段差异分析、"
                "宏蛋白组二次去重与特有抗菌肽筛选。",
                "进行中：特有抗菌肽的机制关联分析、候选抗菌肽的抑菌实验验证，"
                "以及学位论文与以第一作者投稿的 SCI 论文撰写。",
                "时间安排：按开题计划推进，后续不依赖新的数据生产，整体风险可控。",
            ],
            note="主体分析工作已经在中期完成，后续是机制关联的结论整理、抑菌实验验证和论文撰写，"
                 "整体风险可控。我的汇报到此结束，请各位老师批评指正。",
            thanks=True)

    # 11—14 机制补充页 ------------------------------------------------------
    MECH.append(prs, first_idx=11, total=total, which="mid")
    return prs


def audit(path: Path) -> int:
    rc = 0
    print(f"[self-check] {path.name}")
    r = subprocess.run([sys.executable, str(ROOT / "code" / "check_ppt.py"), str(path)],
                       capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-2] if r.stdout.strip() else r.stderr[-400:])
    if "RESULT: OK" not in r.stdout:
        rc = 1
    if N.AUDIT.exists():
        tag = "中期版2" if "中间版2" in str(path) else "中期版"
        rep = QA_DIR / f"{tag}_audit.md"
        r2 = subprocess.run([sys.executable, str(N.AUDIT), str(path), "--report", str(rep),
                             "--json", str(QA_DIR / f"{tag}_audit.json"), "--fail-on", "none"],
                            capture_output=True, text=True)
        print(r2.stdout.strip()[-400:] or r2.stderr[-400:])
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", action="store_true",
                    help="出中间版 2（进度也减半）到 中间版2/")
    ap.add_argument("--no-mech", action="store_true", help="不追加机制补充页")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args(argv)

    outline = json.loads(OUTLINE.read_text(encoding="utf-8"))
    meta, cover = outline["meta"], {s["n"]: s for s in outline["slides"]}[1]
    total = 14 if not a.no_mech else 10
    prs = build(meta, cover, total, half=a.half)
    if a.no_mech:                                   # 只出主体 10 页
        prs = build(meta, cover, 10, half=a.half)
        while len(prs.slides._sldIdLst) > 10:
            xml = prs.slides._sldIdLst[-1]
            rId = xml.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            prs.part.drop_rel(rId)
            prs.slides._sldIdLst.remove(xml)
    out = OUT_HALF if a.half else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    slides = len(prs.slides._sldIdLst)
    notes = sum(1 for s in prs.slides
                if s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip())
    runs = sum(len(p.runs) for s in prs.slides for sh in s.shapes if sh.has_text_frame
               for p in sh.text_frame.paragraphs)
    print(f"wrote {out.relative_to(ROOT)}")
    print(f"slides: {slides} | runs: {runs} | notes: {notes}"
          + ("  | 进度口径：中期前完成数据与预测，其余下一阶段" if a.half else ""))
    if N.PROBLEMS:
        print("PROBLEMS:")
        for p in N.PROBLEMS:
            print("  -", p)
        return 1
    return audit(out) if a.audit else 0


if __name__ == "__main__":
    raise SystemExit(main())
