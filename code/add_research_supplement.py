#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在论文主要内容之后插入独立的研究内容补充页。

只在 word/document.xml 中新增一个表格行；源文档中已有的段落、签字页和其他
zip 条目均逐字节保留。补充行首段带 pageBreakBefore，确保它从新页开始。
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "中期_最终版.docx"
OUT = ROOT / "deliverable" / "中期_最终版_论文研究主要内容补充页.docx"
ROW_RE = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
P_RE = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)
T_RE = re.compile(r"(<w:t(?:\s[^>]*)?>).*?(</w:t>)", re.S)

SUPPLEMENT = [
    "论文研究主要内容补充：",
    "为进一步说明论文的研究内容与技术路线，现对主要研究环节补充如下。补充内容与原研究方案一致，不新增数据生产环节，所有分析均以已建立的数据资源、候选肽清单和可复现的分析流程为基础。",
    "1. 宏基因组数据处理与参考集构建：在已完成质量控制、去宿主、组装的基础上，结合 MetaBAT2、MaxBin2、CONCOCT 三种分箱方法获得微生物基因组，经过质量评估与去冗余形成统一参考集，并保留样本来源和基因组溯源信息，为后续序列预测和丰度比较提供基础。",
    "2. 微生物源短肽库构建：在参考基因组上预测小开放阅读框，按序列长度、完整性和可信度进行筛选，去除重复序列，构建覆盖全队列的非冗余短肽库；对候选序列保留来源样本、基因组和基因位置等信息，保证结果可回溯、可复核。",
    "3. 多模型共识预测与候选确定：采用注意力机制、长短期记忆网络和语言模型三类结构进行独立预测，仅将三个模型均判定为阳性的序列纳入候选集合；通过模型间交集降低单一模型偏倚和假阳性，并为后续差异分析保留统一的候选集合。",
    "4. 分阶段差异分析与 AD 特异性特有肽筛选：依据认知功能与临床诊断将样本划分为 NC、SCS、SCD、MCI 和 AD 五个阶段，在统一分析口径下比较候选肽的丰度及组成差异；再结合宏蛋白组表达证据进行二次去重，筛选 AD 组特有、具有阶段特征且来源可追溯的候选肽。",
    "5. 特有肽与 AD 发病机制的关联分析：以 AD 特异性特有肽清单为对象，采用分子对接与分子动力学模拟考察候选肽与 Aβ 以及 AChE 外周阴离子位点的结合模式和复合物稳定性，按致病方向重点判断其是否促进 Aβ 成核与聚集、是否使产物偏向更毒的寡聚体，并结合文献和功能注释分析免疫与炎症通路环节。",
    "6. 结果整理与论文撰写：将候选肽名单、五阶段差异分析结果、AD 特异性特有肽清单和机制关联分析结果汇总为完整的图表与结论体系，统一数据口径和图表规范；在此基础上完成学位论文相关章节及投稿论文初稿，并对计算预测、文献证据和机制假设的证据强度分别说明。",
]


def text(p: str) -> str:
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", p, re.S))


def set_para_text(p: str, value: str) -> str:
    """保留首个 run 的全部格式，把该段文字放进首个 w:t，清掉其余 w:t。"""
    found = False
    def repl(m: re.Match[str]) -> str:
        nonlocal found
        if not found:
            found = True
            return m.group(1) + escape(value) + m.group(2)
        return m.group(1) + m.group(2)
    out = T_RE.sub(repl, p)
    if not found:
        raise ValueError("模板段落没有 w:t")
    return out


def add_page_break_before(p: str) -> str:
    ppr = re.search(r"<w:pPr(?:\s[^>]*)?>.*?</w:pPr>", p, re.S)
    if not ppr:
        raise ValueError("模板段落没有 w:pPr")
    body = ppr.group(0)
    if "<w:pageBreakBefore" not in body:
        body = body.replace("</w:pPr>", '<w:pageBreakBefore w:val="1"/></w:pPr>')
    return p[:ppr.start()] + body + p[ppr.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out)
    if not src.exists():
        print(f"[ERROR] source not found: {src}", file=sys.stderr); return 1
    if len(SUPPLEMENT) != 8:
        print("[ERROR] supplement/template paragraph count mismatch", file=sys.stderr); return 1

    with zipfile.ZipFile(src) as zin:
        original = zin.read("word/document.xml").decode("utf-8")
        tables = list(re.finditer(r"<w:tbl>.*?</w:tbl>", original, re.S))
        if len(tables) != 2:
            print(f"[ERROR] expected 2 tables, got {len(tables)}", file=sys.stderr); return 1
        table = tables[1].group(0)
        rows = list(ROW_RE.finditer(table))
        target = next((m for m in rows if "1. 论文研究主要内容及工作进度" in text(m.group(0))), None)
        if target is None:
            print("[ERROR] target row not found", file=sys.stderr); return 1
        template_match = next((m for m in rows if "4. 尚需完成的研究工作" in text(m.group(0))), None)
        if template_match is None:
            print("[ERROR] row template not found", file=sys.stderr); return 1
        template = template_match.group(0)
        paras = P_RE.findall(template)
        if len(paras) != 8:
            print(f"[ERROR] expected 8 template paragraphs, got {len(paras)}", file=sys.stderr); return 1
        new_paras = [set_para_text(p, v) for p, v in zip(paras, SUPPLEMENT)]
        new_paras[0] = add_page_break_before(new_paras[0])
        # The template row has one fully merged cell and the desired table borders/margins.
        new_row = template
        for old, new in zip(paras, new_paras):
            if old not in new_row:
                print("[ERROR] template paragraph not found while cloning row", file=sys.stderr); return 1
            new_row = new_row.replace(old, new, 1)

        insert_at = target.end()
        new_table = table[:insert_at] + new_row + table[insert_at:]
        new_xml = original[:tables[1].start()] + new_table + original[tables[1].end():]

        # Existing table rows are byte-identical and the only new XML is one row.
        old_rows = [m.group(0) for m in ROW_RE.finditer(table)]
        new_rows = [m.group(0) for m in ROW_RE.finditer(new_table)]
        if len(new_rows) != len(old_rows) + 1:
            print("[ERROR] row count did not increase by one", file=sys.stderr); return 1
        if new_rows[:old_rows.index(target.group(0)) + 1] != old_rows[:old_rows.index(target.group(0)) + 1]:
            print("[ERROR] rows before insertion changed", file=sys.stderr); return 1
        idx = old_rows.index(target.group(0))
        if new_rows[idx + 1] != new_row or new_rows[idx + 2:] != old_rows[idx + 1:]:
            print("[ERROR] rows after insertion changed", file=sys.stderr); return 1

        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = new_xml.encode("utf-8")
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zout.writestr(zi, data)

    with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
        changed = [n for n in a.namelist() if n != "word/document.xml" and a.read(n) != b.read(n)]
        if changed:
            print(f"[ERROR] non-document.xml entries changed: {changed}", file=sys.stderr)
            out.unlink(missing_ok=True); return 1
    print(f"OK   inserted one standalone supplement row after research-content row")
    print(f"OK   existing table rows unchanged; other {len(a.namelist()) - 1} zip entries byte-identical")
    print(f"OK   wrote {out} ({out.stat().st_size} bytes)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
