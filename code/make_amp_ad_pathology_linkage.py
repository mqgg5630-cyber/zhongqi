#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the corrected AMP--AD pathology linkage DOCX and PPTX.

The deliverable is intentionally not an Aβ-binding review. It explains how
AD/healthy differential microbial AMPs from the thesis can be classified into
pathology-associated, protective/inhibitory, and unknown candidates, without
inventing candidate sequences or results that are not present in the repository.
"""
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from amp_ad_linkage_content import BLOCKS, REF, SLIDES, TABLES
from triq_render import render_docx, assign_numbers
from triq_render_pptx import render_pptx

BJ = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(BJ)
TS = os.environ.get("AMP_LINK_TS") or now.strftime("%Y%m%d_%H%M")
try:
    _ts_dt = datetime.datetime.strptime(TS, "%Y%m%d_%H%M").replace(tzinfo=BJ)
    HUMAN = _ts_dt.strftime("%Y-%m-%d %H:%M 北京时间")
except ValueError:
    HUMAN = now.strftime("%Y-%m-%d %H:%M 北京时间")
OUT = ROOT / "deliverable" / ("候选抗菌肽_AD病理关联解释版_%s_深度学习衔接" % TS)
OUT.mkdir(parents=True, exist_ok=True)
DOCX = OUT / ("深度学习筛选肠道抗菌肽_AD病理关联机制解释版_%s.docx" % TS)
PPTX = OUT / ("深度学习筛选肠道抗菌肽_AD病理关联机制解释版_%s.pptx" % TS)


def main():
    seen, order = assign_numbers(BLOCKS)
    meta = {
        "title": "深度学习筛选的肠道抗菌肽与 AD 病理关联机制",
        "subtitle": "差异肽解释版：从 AD/健康差异，到风险样与保护样候选",
        "claim": "核心纠偏：先筛选 AD 相关差异微生物源 AMP，再分层解释病理关联；Aβ 结合不是致病结论",
        "meta_lines": [
            "生成时间：%s" % HUMAN,
            "对应课题：基于深度学习的 AD 患者与健康人群肠道微生物组 AMP 差异性研究",
            "主对象：AD 相关差异微生物源 AMP；保护/抑制肽仅作为功能亚类；预测、差异、机制和因果分层",
            "重要说明：当前仓库没有实际候选 FASTA、丰度矩阵或 FDR 表，AMP-C01 等均为占位符",
        ],
        "footer_left": "候选 AMP 与 AD 病理关联解释版｜%s" % HUMAN,
    }
    info = render_docx(BLOCKS, REF, str(DOCX), meta)
    pages = render_pptx(SLIDES, TABLES, seen, meta, str(PPTX))
    readme = OUT / "README.md"
    readme.write_text("""# 候选抗菌肽与 AD 病理关联解释版

生成时间：%s

## 这版解决什么问题

这不是把 Aβ 结合文献再讲一遍，而是解释：论文中用深度学习从 AD 患者与健康人群肠道微生物组筛出的候选抗菌肽，如何与 AD 病理建立有证据边界的关联。

主线是：

`476 样本/宏基因组 -> 微生物源短肽库 -> Attention/LSTM/BERT AMP 预测 -> AD/健康差异 -> 来源菌与生态网络 -> LPS/SCFA/屏障/炎症 -> 条件性 Aβ/BBB 验证`

## 最重要的结论

1. 主对象是 **AD 相关差异微生物源 AMP**，不是预先寻找的 Aβ 抑制剂。
2. 保护性或抑制性 AMP 只是差异候选中的一个功能亚类。
3. “与 Aβ 结合”只说明分子相互作用，不能单独说明导致 AD；要看寡聚体方向、炎症、膜损伤、暴露和干预证据。
4. 微生物源 AMP、宿主 LL-37/防御素和宿主 Aβ 必须分开。
5. 当前仓库没有真实候选 FASTA、样本×肽丰度矩阵或 FDR 结果，因此文档没有虚构具体肽的 AD 效应；AMP-C01 等只是填写模板。

## 文件

- `%s`：零基础友好的详细解释、分层判据、组学/生态/MD/QM 方法和答辩话术。
- `%s`：41 页汇报版，每页带演讲备注，重点解释“为什么不是简单找抑制剂”。
- `code/make_amp_ad_pathology_linkage.py`：可重复生成脚本。
- `code/amp_ad_linkage_content.py`：正文、表格、幻灯和参考文献映射。

## 使用真实候选结果时

把实际候选表接入“候选肽机制卡片”，至少提供 candidate_id、sequence、source_ORF/MAG、sample prevalence、effect size、FDR、模型概率和表达证据。结果用 `AD-associated candidate`、`potentially protective candidate` 或 `unknown-direction candidate`，在干预证据之前不要写 `causative peptide`。
""" % (HUMAN, DOCX.name, PPTX.name), encoding="utf-8")
    print("DOCX: %s (%d bytes), citations=%d, missing=%s" % (DOCX, DOCX.stat().st_size, info["citations"], info["missing"]))
    print("PPTX: %s (%d bytes), slides=%d" % (PPTX, PPTX.stat().st_size, pages))
    print("README: %s" % readme)
    return 1 if info["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
