#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the focused three-question mechanism DOCX + 16 pt PPTX."""
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from threeq_mechanism_integrated_content import BLOCKS, REF, SLIDES, TABLES
from triq_render import render_docx, assign_numbers
from threeq_render_pptx16 import render

BJ = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(BJ)
TS = os.environ.get("THREEQ16_TS") or now.strftime("%Y%m%d_%H%M")
try:
    _ts_dt = datetime.datetime.strptime(TS, "%Y%m%d_%H%M").replace(tzinfo=BJ)
    HUMAN = _ts_dt.strftime("%Y-%m-%d %H:%M 北京时间")
except ValueError:
    HUMAN = now.strftime("%Y-%m-%d %H:%M 北京时间")

OUT = ROOT / "deliverable" / ("三问机制整合版_%s_16pt_AChE交叉成核" % TS)
OUT.mkdir(parents=True, exist_ok=True)
DOCX = OUT / ("抗菌肽与AD三问机制整合说明_%s.docx" % TS)
PPTX = OUT / ("抗菌肽与AD三问机制整合汇报_%s_最小16pt.pptx" % TS)


def main():
    seen, order = assign_numbers(BLOCKS)
    meta = {
        "title": "抗菌肽与 AD 三问机制整合说明",
        "subtitle": "AMP-Aβ 交叉成核 + AChE-Aβ 分子动力学 + 肠道菌群/BBB 主线",
        "claim": "主对象：AD 相关差异微生物源 AMP；AChE/Aβ/BBB 是高优先级候选的条件性验证",
        "meta_lines": [
            "对应课题：基于深度学习的 AD 患者与健康人群肠道微生物组 AMP 差异性研究",
            "重点问题：AMP 与 AD 如何结合；AMP 如何经肠道菌群调控关联 AD；AMP 如何在条件满足时参与 BBB/AD",
            "分子机制整合：AChE-Aβ 复合物 MD + AMP-Aβ 交叉成核；PPT 所有可见字体不小于 16 pt",
        ],
        "footer_left": "抗菌肽与 AD 三问机制整合版｜%s" % HUMAN,
        "title_doc": "抗菌肽与 AD 三问机制整合说明",
    }
    info = render_docx(BLOCKS, REF, str(DOCX), {
        "title": meta["title"],
        "subtitle": meta["subtitle"],
        "claim": meta["claim"],
        "meta_lines": [
            "文绍华　2024110316　｜　指导教师：申亮　｜　生命科学学院",
            "生成时间：%s" % HUMAN,
        ] + meta["meta_lines"],
        "footer_left": meta["footer_left"],
    })
    pages = render(SLIDES, TABLES, seen, meta, str(PPTX))
    readme = OUT / "README.md"
    readme.write_text("""# 三问机制整合版（最小 16 pt）

生成时间：%s

## 本版只回答导师的新三问

1. 抗菌肽与 AD 如何结合；
2. 抗菌肽如何通过肠道菌群调控与 AD 关联；
3. 抗菌肽在什么条件下可能进入血脑屏障并参与 AD。

同时把两个分子机制模块整合进问题一：

- 分子机制（一）：AChE-Aβ 复合物的分子动力学，重点是 PAS/344-361 界面、微秒级稳定性、对接-MD-自由能-聚集读数的证据链；
- 分子机制（二）：抗菌肽与 Aβ 的交叉成核，区分促进、抑制和重定向三种方向，不把 Aβ 结合直接写成致病。

## 文件

- `%s`：详细机制说明、三问方法学、文献、候选分类和答辩口径。
- `%s`：三问版汇报 PPT；所有可见文本的最小字号为 16 pt，表格按内容分页，所有页面带备注。
- `code/make_threeq_mechanism_integrated_16.py`：生成脚本。
- `code/threeq_mechanism_integrated_content.py`：正文、表格、幻灯和引用。
- `code/threeq_render_pptx16.py`：16 pt 版式渲染器。

## 口径

主对象是 AD/健康人群肠道宏基因组中筛出的差异微生物源 AMP。宿主 LL-37、防御素和 Aβ 是背景/机制模板，不等于微生物源候选。Aβ 结合、AChE-PAS 对接、MD、PMF 或 BBB 模拟只能提供候选机制和优先级；没有表达、暴露和干预证据时不用 `causative peptide`。

当前仓库没有真实候选 FASTA、样本×肽丰度矩阵和 FDR 表，因此本版没有编造具体候选肽的序列和病理结果；真实结果接入后按候选机制卡片填充。
""" % (HUMAN, DOCX.name, PPTX.name), encoding="utf-8")
    print("DOCX: %s (%d bytes), citations=%d, missing=%s" % (DOCX, DOCX.stat().st_size, info["citations"], info["missing"]))
    print("PPTX: %s (%d bytes), slides=%d, visible_min_pt=16" % (PPTX, PPTX.stat().st_size, pages))
    print("README: %s" % readme)
    return 1 if info["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
