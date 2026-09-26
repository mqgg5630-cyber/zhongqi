# -*- coding: utf-8 -*-
"""生成「抗菌肽与 AD 三大问题（纯计算：MD + 量化计算）」的 DOCX + PPTX 单独版交付物。

只回答三个问题：
  ① 抗菌肽与 Aβ 如何结合
  ② 抗菌肽与肠道菌群调控如何导致 AD
  ③ 抗菌肽穿过血脑屏障如何导致 AD
方法学只写计算类：MD、增强采样与自由能、对接与结构预测、DFT/QM-MM/片段化量子化学，
以及与三问直接相关的组学统计与机器学习。
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import triq_common as C
import triq_refs as R
import triq_q1, triq_q2, triq_q3, triq_q4
from triq_render import render_docx, assign_numbers
from triq_render_pptx import render_pptx
from triq_slides import SLIDES

BJ = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(BJ)
TS = os.environ.get("TRIQ_TS") or now.strftime("%Y%m%d_%H%M")  # 可用 TRIQ_TS 固定时间戳，避免重复生成产生多个文件夹
HUMAN = now.strftime("%Y-%m-%d %H:%M")
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "deliverable", "三问计算版_%s_MD与量化计算_LightSkills23" % TS)
os.makedirs(OUTDIR, exist_ok=True)
DOCX = os.path.join(OUTDIR, "抗菌肽与AD三大问题_计算机制详解_%s_MD与QM.docx" % TS)
PPTX = os.path.join(OUTDIR, "抗菌肽与AD三大问题_计算机制详解_%s_MD与QM.pptx" % TS)


def build_appendix():
    blocks = []
    gl = C.GLOSSARY
    split = next(i for i, (k, _) in enumerate(gl) if k.startswith("AMP 挖掘"))
    for head, items in (("A.1 计算与物理（问题一、三常用）", gl[:split]),
                        ("A.2 组学与统计（问题二常用）", gl[split:])):
        blocks.append(("h2", head))
        blocks.append(("table", {
            "title": head.replace("A.1 ", "表 A-1　").replace("A.2 ", "表 A-2　"),
            "header": ["术语", "一句话解释"],
            "rows": [[k, v] for k, v in items],
        }))
    blocks.append(("h2", "A.3 三个问题的「一句话答案」"))
    blocks.append(("table", {
        "title": "表 A-3　三问一句话回答（答辩可直接背）",
        "header": ["问题", "一句话回答", "核心计算证据"],
        "rows": [
            ["① 抗菌肽与 Aβ 如何结合",
             "静电牵引（AMP 正电残基 ↔ Aβ 的 E11/E22/D23）+ 疏水与芳香锚定（F19/F20 ↔ AMP 疏水面）+ 结构互补（防御素 β 面交叉成核）；结果是抑制长直纤维但可能稳定毒性异源寡聚体。",
             "μs 级 MD 接触频率 + MM-PBSA 残基分解 + 伞形采样 PMF + DFT 片段相互作用能分解"],
            ["② 抗菌肽与肠道菌群调控如何导致 AD",
             "宿主与微生物 AMP 与菌群互为因果：AMP 通过膜选择压力重塑组成（总量不变），菌群通过 TLR/NOD2/IL-22 轴调控 AMP；失衡后经 LPS/SCFA/屏障损伤推动 AD 病理。",
             "宏基因组 AMP 挖掘（共识模型）+ 差异丰度 + 共现网络 + 中介/MR + 生态动力学模型 + AMP-菌膜/LPS 的 MD 与 DFT"],
            ["③ 抗菌肽如何穿过血脑屏障导致 AD",
             "高正电两亲肽纯被动扩散极难（势垒 >20 kcal/mol），主要经膜缺陷/转运体（PEPT2）/受体转胞吞，炎症时旁细胞途径开放使通量放大数量级；入脑后与 Aβ 共聚集并激活微胶质，形成 BBB 损伤正反馈。",
             "BBB 膜 PMF + ISD 渗透系数 + 转运体/受体对接与 MM-PBSA + logBB 机器学习互证 + 信号 ODE 分岔分析"],
        ],
    }))
    return blocks


def main():
    blocks = []
    blocks.append(("h1", "阅读说明"))
    blocks += C.USAGE[1:]
    blocks.append(C.OVERVIEW_TITLE)
    blocks.append(C.OVERVIEW_INTRO)
    blocks.append(("table", C.OVERVIEW_TABLE))
    blocks.append(("h2", "三条最关键的提醒"))
    for t in C.OVERVIEW_NOTES:
        blocks.append(("b", t))
    blocks += triq_q1.BLOCKS
    blocks += triq_q2.BLOCKS
    blocks += triq_q3.BLOCKS
    # 第四篇：替换附录占位块
    q4 = []
    skip = False
    for kind, payload in triq_q4.BLOCKS:
        if kind == "h1" and payload.startswith("附录 A"):
            skip = True
        if skip:
            if kind == "h1":
                q4.append((kind, payload))
                q4 += build_appendix()
                skip = False
            continue
        q4.append((kind, payload))
    blocks += q4

    seen, order = assign_numbers(blocks)
    meta = {
        "title": C.TITLE,
        "subtitle": C.SUBTITLE,
        "claim": C.CLAIM,
        "meta_lines": [
            "生成时间（北京时间）：%s" % HUMAN,
            "范围：只回答三个命题；方法只含计算类（MD / 增强采样与自由能 / 对接与结构预测 / DFT-QM / 组学统计与机器学习）",
            "引用文献：%d 条（含 DOI / PMID / PMC 可核验条目）" % len(order),
            "生成脚本：code/make_triq_computational.py（模块：triq_common / triq_refs / triq_q1-q4 / triq_render / triq_render_pptx / triq_slides）",
            "技能：Light-skills 23 项（light-literature-search / light-paper-writing / light-citation / light-figure / light-data-engineering 等）"
            " + find-skills 3.5M + docx + pptx + content-research-writer + doc-coauthoring",
        ],
        "footer_left": "抗菌肽与 AD 三大问题·计算机制详解（MD + 量化计算）｜%s 北京时间" % HUMAN,
    }

    info = render_docx(blocks, R.REF, DOCX, meta)
    if info["missing"]:
        print("!! 缺失引用键：%s" % ", ".join(info["missing"]))

    # 表格索引（按标题前缀）
    tables = {}
    for kind, payload in blocks:
        if kind == "table":
            t = payload["title"].split("　")[0].strip()
            tables[t] = payload
    used = set(s.get("ref") for s in SLIDES if s["type"] == "table")
    miss_tbl = sorted(u for u in used if u not in tables)
    if miss_tbl:
        print("!! PPT 缺失表格 ref：%s" % ", ".join(miss_tbl))
    npages = render_pptx(SLIDES, tables, seen, meta, PPTX)

    print("DOCX: %s (%d bytes) 引用 %d 条" % (DOCX, os.path.getsize(DOCX), info["citations"]))
    print("PPTX: %s (%d bytes) %d 页" % (PPTX, os.path.getsize(PPTX), npages))
    print("文件夹: %s" % OUTDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
