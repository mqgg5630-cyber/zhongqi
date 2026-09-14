#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mid_content.py - 由完整版草稿生成"中间版（提交给老师）"草稿。

完整版 `deliverable/中期检查表_填写内容.md` 不动；本脚本按一张"保留清单"挑出
约一半的段落，写成 `docs/中间版_填写内容.md`，再交给

    python code/build_ops.py --in docs/中间版_填写内容.md --out build/ops_中期_中间版.json
    python code/fill_docx.py --ops build/ops_中期_中间版.json --out 中间版/中期.docx

填出中间版 docx。保留清单写在本文件里（KEEP），改哪几段改这里就行。
段落编号与 `deliverable/中期检查表_填写内容.md` 中每个 `## n.` 小节内的
出现顺序一致（0 起数，含小节标题行）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "deliverable" / "中期检查表_填写内容.md"
DST = ROOT / "docs" / "中间版_填写内容.md"

# 每个 `## n.` 小节里保留哪些行（0 起数）
KEEP = {
    "1": [0, 3,              # （一）背景与意义：抗菌肽作为切入点的理由
          5, 8, 9,           # （二）现状与不足 + 本研究切入点
          10, 11,            # （三）研究目标
          13, 14, 16, 17, 18, 20,  # （四）研究内容 1 / 3 / 4 / 5 / 7
          22,                # （五）技术路线
          26, 27, 29, 31, 32, 33, 35],  # （六）进度：1 / 3 / 5 / 6 / 7 + 完成结构
    "2": [0, 1,              # （一）数据资源与分析流程
          3, 4,              # （二）预测结果
          6, 8,              # （三）分阶段差异与去重
          10, 11,            # （四）机制关联方案
          13, 15],           # （五）阶段性结论
    "3": [0, 1],             # 暂无发表 + 投稿计划
    "4": [0, 1,              # （一）机制关联：内容（方案见阶段性成果）
          4, 5, 6,           # （二）抑菌实验：内容 + 方案
          8, 10,             # （三）结果整理与投稿
          12, 13, 15,        # （四）问题与对策 1 / 3
          17, 18],           # （五）后续工作安排
}

# Ⅱ.导师指导情况：中间版用更短的版本（完整版仍保留全文）
ADVISOR = {
    "论文指导情况": (
        "自开题以来，导师在选题与总体框架、研究方案与技术路线、阶段成果整理与学术规范等方面给予持续指导。"
        "针对单一模型预测容易产生假阳性的问题，指导采用多模型独立预测、取一致阳性结果构成候选集合，"
        "并引入宏蛋白组表达证据二次去重；强调区分计算预测与实验证据、不夸大因果性结论，"
        "并通过定期组会督促研究进度。目前主体分析已完成，机制关联分析与抑菌实验验证正在推进。"
    ),
    "导师综合评语": (
        "该生科研作风严谨，能够独立完成数据处理与建模工作，中期阶段已完成数据资源构建、"
        "多模型共识预测、分阶段差异分析与特有抗菌肽筛选等主体工作，结果可信，进度与开题计划一致。"
        "同意该生参加学位论文预答辩。"
    ),
}


def parse(lines: list[str]):
    cover, title, sections, order = [], None, {}, []
    advisor: dict[str, str] = {}
    members: list[str] = []
    cur = None
    for line in lines:
        if line.startswith("# 封面信息"):
            cur = "cover"
            continue
        if line.startswith("# 论文题目"):
            cur = "title"
            continue
        if line.startswith("# 导师指导情况"):
            cur = "advisor"
            continue
        if line.startswith("# 检查小组成员"):
            cur = "members"
            continue
        if line.startswith("## "):
            cur = line[3:].strip()[0]
            sections[cur] = []
            order.append(cur)
            continue
        if not line.strip():
            continue
        if cur == "cover":
            cover.append(line.strip())
        elif cur == "title":
            if title is None:
                title = line.strip()
        elif cur == "advisor":
            if "：" in line:
                k, v = line.split("：", 1)
                advisor[k.strip()] = v.strip()
        elif cur == "members":
            members.append(line.strip())
        elif cur in sections:
            sections[cur].append(line)
    return cover, title, sections, order, advisor, members


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(DST))
    a = ap.parse_args(argv)

    lines = Path(a.src).read_text(encoding="utf-8").splitlines()
    cover, title, sections, order, _advisor, members = parse(lines)

    out: list[str] = ["# 封面信息"] + cover + ["", "# 论文题目", title, ""]
    kept_chars = total_chars = 0
    kept_items = total_items = 0
    kept_body = total_body = 0
    for key in order:
        out.append(f"## {key}. " + {
            "1": "论文研究主要内容及工作进度",
            "2": "阶段性成果",
            "3": "公开发表学术论文情况",
            "4": "尚需完成的研究工作（包括内容、方案）",
        }.get(key, ""))
        out.append("")
        items = sections[key]
        keep = set(KEEP.get(key, range(len(items))))
        for i, line in enumerate(items):
            body = line[1:] if line.startswith("!") else line
            is_head = line.startswith("!") or line[:1] in "（"
            total_chars += len(body)
            total_items += 1
            total_body += 0 if is_head else 1
            if i in keep:
                out.append(line)
                kept_chars += len(body)
                kept_items += 1
                kept_body += 0 if is_head else 1
        out.append("")

    out.append("# 导师指导情况")
    out.append("")
    for k, v in ADVISOR.items():
        out.append(f"{k}：{v}")
        total_chars += len(v)
        kept_chars += len(v)
        total_items += 1
        kept_items += 1
    out.append("")
    out.append("# 检查小组成员")
    out.append("")
    out += members
    out.append("")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {Path(a.out).relative_to(ROOT)}")
    print(f"  正文段落 {kept_body}/{total_body} = {kept_body / total_body:.0%}")
    print(f"  全部行（含小节标题）{kept_items}/{total_items} = {kept_items / total_items:.0%}")
    print(f"  字数 {kept_chars}/{total_chars} = {kept_chars / total_chars:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
