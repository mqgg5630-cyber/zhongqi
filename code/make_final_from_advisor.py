#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_final_from_advisor.py - 在导师改好的那份 docx 上把段前分页挪到「Ⅱ.导师指导情况」，
另存为最终版；**除这一个分页标记外，文件逐字节不动**。

背景（2026-09-19）
------------------
导师把 `sources/中期_导师.docx` 改好交回来，要求：**Ⅱ.导师指导情况及其之后的全部内容放在同一页
（含 Ⅱ.导师指导情况本身）** —— 也就是把段前分页从「2. 导师综合评语」上移到「Ⅱ.导师指导情况」。

导师同时把「1. 论文指导情况」「2. 导师综合评语」两段改短了，正是为了让 Ⅱ 起这一整块
（Ⅱ → 1 → 2 → Ⅲ.评议情况 → 检查小组成员 → 检查意见 → 组长签字 / 单位盖章）装得进一页。

做法（zip 层动手术，不重排 XML）
------------------------------
* 直接把 `word/document.xml` 当文本改：在 `Ⅱ.导师指导情况` 那一行的第一个 `<w:pPr>` 后插入
  `<w:pageBreakBefore/>`，把 `2. 导师综合评语` 那一行里的同名标记删掉；
* 其它 zip 条目原样拷贝（字节级一致），所以除了这两处没人能碰得到别的格式；
* 自检：
  1) 除了 `<w:pageBreakBefore/>`，新文件的 document.xml 与导师版逐字节相同；
  2) 其它所有 zip 条目逐字节相同；
  3) Ⅱ 起那一整块装得进一页（用 `code/check_docx_layout.py` 的同一套估算）。

用法
----
    python code/make_final_from_advisor.py                 # -> deliverable/中期_最终版.docx
    python code/make_final_from_advisor.py --src X.docx --out Y.docx
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docx_layout as L          # noqa: E402  共用同一套分页估算

from docx import Document              # noqa: E402
from docx.oxml.ns import qn            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "中期_导师.docx"
OUT = ROOT / "deliverable" / "中期_最终版.docx"
FROM_LABEL = "导师综合评语"            # 分页标记原来挂在这一行
TO_LABEL = "Ⅱ.导师指导情况"            # 现在挂到这一行
PBB = "<w:pageBreakBefore/>"
ROW_RE = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
T_RE = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")


def row_spans(xml: str):
    """所有表格行的 (起点, 终点, 行 XML, 行内纯文本)。"""
    out = []
    for m in ROW_RE.finditer(xml):
        out.append((m.start(), m.end(), m.group(0), "".join(T_RE.findall(m.group(0)))))
    return out


def find_row(rows, label):
    for k, (s, e, raw, txt) in enumerate(rows):
        if label and label in txt:
            return k, (s, e, raw, txt)
    return None, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把签字页段前分页挪到「Ⅱ.导师指导情况」")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--from-label", default=FROM_LABEL)
    ap.add_argument("--to-label", default=TO_LABEL)
    ap.add_argument("--verify", action="store_true",
                    help="只校验 --out 与 --src 是否只差这一个分页标记（不写文件）")
    a = ap.parse_args(argv)

    src, out = Path(a.src), Path(a.out)
    if not src.exists():
        print(f"[ERROR] 找不到导师版文件 {src}", file=sys.stderr)
        return 1

    zin = zipfile.ZipFile(src)
    doc_xml = zin.read("word/document.xml").decode("utf-8")
    rows = row_spans(doc_xml)

    k_from, from_row = find_row(rows, a.from_label)
    k_to, to_row = find_row(rows, a.to_label)
    if from_row is None or to_row is None:
        print(f"[ERROR] 找不到行：{a.from_label!r} -> {k_from}，{a.to_label!r} -> {k_to}",
              file=sys.stderr)
        return 1
    s_from, e_from, raw_from, _ = from_row
    s_to, e_to, raw_to, _ = to_row
    n_pbb = raw_from.count(PBB)
    if n_pbb == 0:
        print(f"[ERROR] 「{a.from_label}」那一行上没有段前分页可挪", file=sys.stderr)
        return 1
    if PBB in raw_to:
        print(f"[ERROR] 「{a.to_label}」那一行已经有段前分页了", file=sys.stderr)
        return 1

    # ---- 行内手术：先删后插（都用从后往前的偏移，避免位置错乱）
    if s_from > s_to:                                  # 先处理靠后的那一行
        new_raw_to, done_to = _insert_pbb(raw_to)
        xml2 = doc_xml[:s_to] + new_raw_to + doc_xml[e_to:]
        shift = len(new_raw_to) - (e_to - s_to)
        s_from2 = s_from + shift
        e_from2 = e_from + shift
        new_raw_from = raw_from.replace(PBB, "")
        xml3 = xml2[:s_from2] + new_raw_from + xml2[e_from2:]
    else:
        new_raw_from = raw_from.replace(PBB, "")
        xml2 = doc_xml[:s_from] + new_raw_from + doc_xml[e_from:]
        shift = len(new_raw_from) - (e_from - s_from)
        s_to2, e_to2 = s_to + shift, e_to + shift
        new_raw_to, done_to = _insert_pbb(raw_to)
        xml3 = xml2[:s_to2] + new_raw_to + xml2[e_to2:]
    if done_to == 0:
        print(f"[ERROR] 「{a.to_label}」那一行里没找到 <w:pPr>，加不上分页标记", file=sys.stderr)
        return 1
    print(f"OK   段前分页：行 {k_from}「{a.from_label}」删掉 {n_pbb} 个 -> "
          f"行 {k_to}「{a.to_label}」加上 1 个")

    # ---- 自检 1/2：只有这一个标记变了
    if xml3.replace(PBB, "") != doc_xml.replace(PBB, ""):
        print("[ERROR] 除了 <w:pageBreakBefore/>，document.xml 还有别的改动", file=sys.stderr)
        return 1
    if xml3.count(PBB) != doc_xml.count(PBB) - n_pbb + 1:
        print("[ERROR] 分页标记数量不对", file=sys.stderr)
        return 1
    print(f"OK   去掉 <w:pageBreakBefore/> 后与导师版逐字节相同（正文一字未改）")

    if a.verify:
        if not out.exists():
            print(f"[ERROR] 找不到 {out}", file=sys.stderr)
            return 1
        zout0 = zipfile.ZipFile(out)
        out_xml = zout0.read("word/document.xml").decode("utf-8")
        if out_xml.replace(PBB, "") != doc_xml.replace(PBB, ""):
            print("[ERROR] 成品与导师版不只是差一个分页标记", file=sys.stderr)
            return 1
        diff = [n for n in zin.namelist()
                if n != "word/document.xml" and zin.read(n) != zout0.read(n)]
        if diff:
            print(f"[ERROR] 这些 zip 条目被改动了：{diff}", file=sys.stderr)
            return 1
        out_rows = row_spans(out_xml)
        _, f_row = find_row(out_rows, a.from_label)
        _, t_row = find_row(out_rows, a.to_label)
        if f_row is None or t_row is None or PBB in f_row[2] or PBB not in t_row[2]:
            print("[ERROR] 分页标记的位置不对", file=sys.stderr)
            return 1
        print(f"OK   最终版 = 导师版 + 一处分页标记（{a.to_label} 带 <w:pageBreakBefore/>，"
              f"{a.from_label} 不带）：正文与其余 zip 条目逐字节一致")
        return 0

    # ---- 写新 docx：其它条目原样拷贝（字节级）
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                data = xml3.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
    zin.close()

    zin2 = zipfile.ZipFile(src)
    zout2 = zipfile.ZipFile(out)
    diff = [n for n in zin2.namelist()
            if n != "word/document.xml" and zin2.read(n) != zout2.read(n)]
    if diff:
        print(f"[ERROR] 这些 zip 条目被改动了：{diff}", file=sys.stderr)
        out.unlink(missing_ok=True)
        return 1
    print(f"OK   其余 {len(zin2.namelist()) - 1} 个 zip 条目逐字节相同")

    # ---- 自检 3：Ⅱ 起这一整块装得进一页
    doc = Document(str(out))
    tbl = [el for el in doc.element.body.iterchildren() if el.tag == qn("w:tbl")][-1]
    trs = tbl.findall(qn("w:tr"))
    cols, cellmar = L.table_metrics(tbl)
    avail = L.usable_height_tw(doc)
    heights = [L.row_height(tr, cols, cellmar) for tr in trs]
    r_to = next(i for i, tr in enumerate(trs)
                if a.to_label in "".join(t.text or "" for t in tr.iter(qn("w:t"))))
    block = sum(heights[r_to:])
    if block > avail:
        print(f"[ERROR] {a.to_label} 起这一块 {block / L.TW:.0f} pt 超过一页 "
              f"{avail / L.TW:.0f} pt，装不下", file=sys.stderr)
        out.unlink(missing_ok=True)
        return 1
    print(f"OK   {a.to_label} 起（row {r_to}—{len(trs) - 1}，共 {len(trs) - r_to} 行）"
          f"合计 {block / L.TW:.0f} pt <= 一页 {avail / L.TW:.0f} pt"
          f"（占 {block / avail * 100:.0f}%，余 {(avail - block) / L.TW:.0f} pt）")

    page, cur, pages = 1, 0.0, []
    for i, h in enumerate(heights):
        if L.has_page_break_before(trs[i]) and cur > 0:
            page += 1
            cur = 0.0
        rest = h
        if cur and cur + rest > avail * 0.999:
            page += 1
            cur = 0.0
        while rest > avail * 0.999:
            rest -= avail
            page += 1
            cur = 0.0
        cur += rest
        pages.append(page)
    print(f"OK   估算：正文表共 {pages[-1]} 页；Ⅱ 起那一块 = 第 {pages[r_to]} 页"
          f"（{'最后一页' if pages[-1] == pages[r_to] else '不是最后一页'}）")

    print(f"\nsaved -> {out.relative_to(ROOT)}")
    print(f"接着跑：python code/check_docx_layout.py {out.relative_to(ROOT)}")
    return 0


def _insert_pbb(raw_row: str):
    """在行内第一个 <w:pPr> 之后插入 <w:pageBreakBefore/>，返回 (新行 XML, 插入个数)。"""
    m = re.search(r"<w:pPr>", raw_row)
    if not m:
        return raw_row, 0
    i = m.end()
    return raw_row[:i] + PBB + raw_row[i:], 1


if __name__ == "__main__":
    raise SystemExit(main())
