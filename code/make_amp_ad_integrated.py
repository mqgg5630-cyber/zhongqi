#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the integrated eight-question AMP--AD mechanism DOCX and PPTX."""
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from amp_ad_integrated_content import BLOCKS, REF, SLIDES, TABLES
from triq_render import render_docx, assign_numbers
from triq_render_pptx import render_pptx

BJ = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(BJ)
TS = os.environ.get("AMP_INTEGRATED_TS") or now.strftime("%Y%m%d_%H%M")
try:
    _ts_dt = datetime.datetime.strptime(TS, "%Y%m%d_%H%M").replace(tzinfo=BJ)
    HUMAN = _ts_dt.strftime("%Y-%m-%d %H:%M 北京时间")
except ValueError:
    HUMAN = now.strftime("%Y-%m-%d %H:%M 北京时间")

OUT = ROOT / "deliverable" / ("抗菌肽_AD关联机制整合版_%s_八问与深度学习衔接" % TS)
OUT.mkdir(parents=True, exist_ok=True)
DOCX = OUT / ("抗菌肽与AD关联机制说明_八问整合版_%s.docx" % TS)
PPTX = OUT / ("抗菌肽与AD关联机制说明_八问整合版_%s.pptx" % TS)


def main():
    seen, order = assign_numbers(BLOCKS)
    meta = {
        "title": "抗菌肽与 AD 关联机制说明",
        "subtitle": "中期检查补充材料·八问整合版·深度学习差异肽衔接",
        "claim": "主对象是 AD 相关差异微生物源 AMP；Aβ/AChE/BBB 是高优先级候选的条件性机制验证",
        "meta_lines": [
            "文绍华　2024110316　｜　指导教师：申亮　｜　生命科学学院",
            "生成时间：%s" % HUMAN,
            "对应课题：基于深度学习的阿尔茨海默症患者与健康人群肠道微生物组中抗菌肽的差异性研究",
            "证据口径：宿主 AMP/Aβ 背景、微生物源 AMP 差异、本课题计算结果、因果验证严格分层",
            "当前没有实际候选 FASTA/丰度矩阵/FDR 表；候选机制卡片仅提供真实结果的填写框架",
        ],
        "footer_left": "抗菌肽与 AD 关联机制说明·八问整合版｜%s" % HUMAN,
    }
    info = render_docx(BLOCKS, REF, str(DOCX), meta)
    pages = render_pptx(SLIDES, TABLES, seen, meta, str(PPTX))
    readme = OUT / "README.md"
    readme.write_text("""# 抗菌肽与 AD 关联机制说明——八问整合版

生成时间：%s

## 本版整合内容

本版把用户提供的《抗菌肽与 AD 关联机制说明》、中期检查八个问题、AChE-Aβ 分子动力学依据、感染/肠道菌群证据，以及上一版关于“差异 AMP 不等于致病肽”的纠偏合并为一套 DOCX + PPTX。

核心关系：

`AD/健康肠道宏基因组 -> 短肽库 -> 深度学习 AMP 共识 -> 五阶段差异 -> 表达二次去重 -> 来源菌/生态网络 -> LPS/SCFA/屏障/炎症 -> 高优先级候选的 MD/QM -> 实验验证`

## 必须记住的结论

- 研究主体是 AD 患者与健康人群肠道微生物组中的 **差异微生物源 AMP**。
- 宿主 LL-37、防御素和 Aβ 是病理背景/机制模板，不是微生物源候选本身。
- Aβ 结合只能证明可能存在分子相互作用，不能单独证明导致 AD。
- 候选肽应分为风险样、保护/抑制样、方向未知和仅预测层，不能全部归为致病肽或抑制剂。
- “AD 组更多”必须按分子、部位和阶段说明；部分宿主 AMP 可升高，乳铁蛋白等可下降；微生物源 AMP 的方向以本课题结果为准。
- AChE-PAS、Aβ 聚集和 BBB 模拟是高优先级候选的条件性验证，不能代替差异分析和表达证据。
- 当前仓库没有真实候选 FASTA、丰度矩阵或 FDR 表，因此没有编造 AMP-C01 的序列和结果。

## 文件

- `%s`：逐条回答八个问题、七环逻辑链、阶段证据、AChE-Aβ/交叉成核、计算流程、候选分类、答辩问答和文献审计说明。
- `%s`：36 页汇报版，每页有演讲备注。
- `code/make_amp_ad_integrated.py`：生成脚本。
- `code/amp_ad_integrated_content.py`：整合正文、表格、幻灯和文献映射。

## 结果接入

拿到真实预测结果后，至少接入 candidate_id、sequence、ORF/contig/MAG、来源菌、样本检出率、效应量、FDR、模型概率和表达证据；再依据表 13-16 逐条给出 risk-like、protective 或 unknown 标签。在干预证据前统一使用 `AD-associated candidate`，不要写 `causative peptide`。

## 文献审计

正文引用了用户补充材料和仓库文献库。2025—2026 年条目、预印本、数据库记录和数值型汇总在提交论文前应再次核对 DOI、卷页、样本量、图表和原文语义；人口归因分数不能解释成个体病因概率。
""" % (HUMAN, DOCX.name, PPTX.name), encoding="utf-8")
    print("DOCX: %s (%d bytes), citations=%d, missing=%s" % (DOCX, DOCX.stat().st_size, info["citations"], info["missing"]))
    print("PPTX: %s (%d bytes), slides=%d" % (PPTX, PPTX.stat().st_size, pages))
    print("README: %s" % readme)
    return 1 if info["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
