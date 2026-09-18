#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_sign_page.py - 从学校模板里裁出“Ⅲ.评议情况”签字页，单独存成一份一页的 docx。

为什么要单独一份
----------------
中期检查表前面几节（研究内容、阶段性成果、导师指导情况……）还要改，但签字页
明天就要拿去签。把签字页单独做成一份 A4 一页的文件：

  * 打印签字页 -> 找检查小组签字（组长签字、培养单位盖章都在这一页）
  * 正文那几页以后随便改，签好的这一页直接替换 / 装订到最后一页即可

做法（和表里那一页逐字节一致）
------------------------------
不做任何重排：直接打开 `sources/中期.docx`（学校模板），
  * 删掉封面页、填表说明页以及它们的分节符
  * 正文表只保留 “Ⅲ.评议情况” 那一行到表格末尾（行元素原样搬过来，
    框线 / 列宽 / 行高 / 字体 / 单元格内容都不动）
  * 保留表后的空段落与最后一节的 sectPr —— 纸张、页边距、页脚（日期 + 页码）
    与整份表里的那一页完全相同
所以这份文件打印出来的样子，就是整份检查表最后一页的样子。

生成的页码说明：页脚里的页码是 Word 域，单独打印时按“第 1 页”排；
要装订 / 替换进整份表时，页码以整份表为准。

Usage
-----
    python code/make_sign_page.py                     # -> deliverable/中期检查表_签字页.docx
    python code/make_sign_page.py --out X.docx
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "sources" / "中期.docx"
OUT = ROOT / "deliverable" / "中期检查表_签字页.docx"

SIGN_LABEL = "Ⅲ.评议情况"


def strip_ns(xml: str) -> str:
    return re.sub(r'\sxmlns:[a-zA-Z0-9]+="[^"]*"', "", xml)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="裁出签字页，存成一页的 docx")
    ap.add_argument("--docx", default=str(TEMPLATE), help="源模板（默认 sources/中期.docx）")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    src = Path(args.docx)
    if not src.exists():
        print(f"[ERROR] not found: {src}", file=sys.stderr)
        return 1

    doc = Document(str(src))
    body = doc.element.body
    kids = list(body.iterchildren())
    tables = [el for el in kids if el.tag == qn("w:tbl")]
    if not tables:
        print("[ERROR] no table in the template", file=sys.stderr)
        return 1
    tbl = tables[-1]
    trs = tbl.findall(qn("w:tr"))
    sign_row = next((i for i, tr in enumerate(trs)
                     if SIGN_LABEL in "".join(t.text or "" for t in tr.iter(qn("w:t")))), None)
    if sign_row is None:
        print(f"[ERROR] no row with {SIGN_LABEL!r}", file=sys.stderr)
        return 1

    tbl_idx = kids.index(tbl)
    after = kids[tbl_idx + 1:]                      # 表后的空段落 + 最后的 sectPr
    sect = [el for el in after if el.tag == qn("w:sectPr")]
    keep_after = [el for el in after if el.tag != qn("w:sectPr")][:1]     # 只留一个空段落
    keep_after += sect

    # 只保留签字部分的行（行元素本身原样搬过来）
    dropped_rows = [tr for tr in trs[:sign_row]]
    for tr in dropped_rows:
        tbl.remove(tr)

    for el in kids[:tbl_idx]:                       # 封面页 / 填表说明页 / 分节符
        body.remove(el)
    for el in after:
        if el not in keep_after:
            body.remove(el)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))

    # ---------------- 自检 ----------------
    problems = []
    chk = Document(str(out))
    body2 = list(chk.element.body.iterchildren())
    tbls2 = [el for el in body2 if el.tag == qn("w:tbl")]
    par2 = [el for el in body2 if el.tag == qn("w:p")]
    sect2 = [el for el in body2 if el.tag == qn("w:sectPr")]
    trs2 = tbls2[-1].findall(qn("w:tr")) if tbls2 else []

    if len(tbls2) == 1 and len(par2) == 1 and len(sect2) == 1:
        print(f"OK    结构：1 张表（{len(trs2)} 行）+ 1 个空段落 + 1 个 sectPr")
    else:
        problems.append(f"结构不对：{len(tbls2)} 表 / {len(par2)} 段 / {len(sect2)} sectPr")
        print(f"FAIL  结构：{len(tbls2)} 表 / {len(par2)} 段 / {len(sect2)} sectPr")

    first = "".join(t.text or "" for t in trs2[0].iter(qn("w:t"))) if trs2 else ""
    if SIGN_LABEL in first:
        print(f"OK    第一行 = {SIGN_LABEL}（就是签字页本身）")
    else:
        problems.append("第一行不是 Ⅲ.评议情况")
        print(f"FAIL  第一行 = {first[:20]!r}")

    # 每一行都要与模板里的对应行逐字节一致（证明没有重排）
    same = all(strip_ns(a.xml) == strip_ns(b.xml)
               for a, b in zip(trs2, trs[sign_row:]))
    if same and len(trs2) == len(trs) - sign_row:
        print(f"OK    全部 {len(trs2)} 行与模板第 {sign_row}—{len(trs) - 1} 行逐字节一致"
              f"（框线 / 列宽 / 行高 / 字体都原样）")
    else:
        problems.append("行内容与模板不一致")
        print("FAIL  行内容与模板不一致")

    # 页面设置 / 页眉页脚要与整份表的正文节一致
    s_src, s_out = doc.sections, chk.sections
    t = Document(str(src)).sections[-1]
    if (p := chk.sections[-1]).page_width == t.page_width and p.page_height == t.page_height and \
            (p.top_margin, p.bottom_margin, p.left_margin, p.right_margin) == \
            (t.top_margin, t.bottom_margin, t.left_margin, t.right_margin):
        print(f"OK    页面：{p.page_width.inches:.2f}x{p.page_height.inches:.2f} in，"
              f"页边距 T/B {p.top_margin.inches:.2f}/{p.bottom_margin.inches:.2f} in 与正文节一致")
    else:
        problems.append("页面设置与正文节不一致")
        print("FAIL  页面设置与正文节不一致")

    print(f"\nsaved -> {out}  ({len(trs2)} rows kept, {len(dropped_rows)} rows dropped)")
    if problems:
        print(f"RESULT: {len(problems)} problem(s)")
        return 1
    print("RESULT: OK - 签字页已单独成一份一页文件")
    print(f"接着跑：python code/check_docx_layout.py {out} --sign-page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
