#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mid2_content.py - 中间版 2（进度半程 + 内容减半）的 docx 草稿。

与中间版 1 的区别
------------------
中间版 1 只压缩了篇幅，进度口径与完整版一致（前五项已完成）。
中间版 2 是**平行版本**：进度也砍一半 —— 只把"数据 + 预测"这几步作为中期完成的工作，
分阶段差异分析、宏蛋白组去重与特有肽筛选、机制关联、抑菌实验验证全部列为
中期之后推进的计划；相应地，差异化结果一类的表述也从"已完成"改为"正在实施"。

完整版 `deliverable/中期检查表_填写内容.md` 与中间版 1 的草稿都不动。

    python code/make_mid2_content.py     -> docs/中间版2_填写内容.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "deliverable" / "中期检查表_填写内容.md"
DST = ROOT / "docs" / "中间版2_填写内容.md"

# 保留哪些原始行（0 起数，按小节内顺序）
KEEP = {
    "1": [0,                       # （一）背景与意义：抗菌肽作为切入点的理由
          5, 8, 9,                 # （二）现状与不足 + 本研究切入点
          10, 11,                  # （三）研究目标
          12, 13, 14, 16, 18, 20,  # （四）研究内容 1 / 2 / 3 / 5 / 7（其余作为后续计划）
          22, 23,                  # （五）技术路线（整体四层）
          26, 27, 28, 29],         # （六）进度：1 / 2 / 3 —— 数据与预测
    "2": [0, 1,                    # （一）数据资源与分析流程
          3,                       # （二）预测结果
          13,                      # （五）成果形式与阶段性结论（正文在 CUSTOM）
          10, 11],                 # （四）机制关联方案（含抑菌实验方案）
        # 注：（五）成果形式与阶段性结论 见 CUSTOM
    "3": [0, 1],                   # 暂无发表 + 投稿计划
    "4": [0, 1,                    # （一）机制关联：内容 + 方案
          4, 6,                    # （二）抑菌实验：方案
          8, 10,                   # （三）结果整理与投稿
          12],                     # （四）存在的问题与应对措施（正文在 EXTRA 里）
}

# 覆盖写（把"已完成"改成"下一阶段"的表述；id 与完整版行号对应）
CUSTOM = {
    # 进度：两项已完成 + 五项下一阶段
    ("1", 35): "从完成结构上看，研究内容中的宏基因组数据处理与微生物基因组参考集构建、"
               "小开放阅读框预测与微生物源短肽库构建两项已全部完成，三模型共识预测已形成候选抗菌肽名单，"
               "构成了课题的主体分析基础；分阶段差异分析、宏蛋白组去重与特有抗菌肽筛选正在开展，"
               "机制关联分析、抑菌实验验证与论文撰写安排在后续阶段进行。",
    ("1", 36): "截至本次中期检查，课题整体进度与开题报告拟定的安排基本一致：数据处理与预测环节已形成完整结果，"
               "后续分析所需的短肽库与候选名单已经具备，剩余工作的输入条件成熟，进度风险可控。",
    # 阶段性成果里，差异分析与特有肽筛选改为"正在实施"
    ("2", 6): "!（三）分阶段差异分析与特有抗菌肽筛选（正在实施）",
    ("2", 7): "分阶段差异分析已进入实施：按 NC、SCS、SCD、MCI 与 AD 五个认知阶段比较候选抗菌肽的丰度与组成差异，"
              "识别可能随病程变化的候选抗菌肽。该环节与后续的二次去重衔接，分析结果将作为特有抗菌肽筛选的输入。",
    ("2", 8): "宏蛋白组表达证据二次去重按计划推进：在序列去冗余的基础上，逐步引入蛋白层面的表达证据，"
              "剔除缺少表达支持的序列，再按组内共有、组间特比较，筛选健康人群特有与各疾病阶段特有的抗菌肽。",
    # 机制关联方案：补上英文缩写写法（与 PPT 口径一致）
    ("2", 11): "已完成特有抗菌肽与 AD 发病机制关联分析的技术方案设计：以分子对接与分子动力学模拟按致病方向考察"
               "候选肽与 β-淀粉样肽（Aβ）、乙酰胆碱酯酶（AChE）外周阴离子位点的结合情况与复合物稳定性，"
               "判断其是否促进 Aβ 的成核与聚集，并结合文献比对与功能注释分析其可能涉及的免疫与炎症通路。"
               "相关分析按方案在下一阶段实施，候选肽的序列与结构准备、参数设置与流程搭建等前期工作已完成。",

    # 阶段性结论：不再声称主体分析已完成
    ("2", 14): "阶段性成果以数据资源、分析流程与候选名单为主要形式：已形成完整可重复的分析流程与技术文档；"
               "已形成候选抗菌肽名单及预测环节的统计信息；分阶段差异分析与特有抗菌肽筛选正在实施。"
               "阶段性成果中暂无以第一作者公开发表的学术论文。",
}

# 在某个 id 之后追加的行
EXTRA = {
    ("1", 29): [
        "4. 其余各项（分阶段差异分析、宏蛋白组二次去重与特有抗菌肽筛选、机制关联分析、抑菌实验验证、"
        "结果整理与论文撰写）为中期之后的工作，实施方案与所需材料已确定。",
    ],
    ("4", 12): [
        "1. 预测结果可能存在假阳性。应对：以多模型共识判定提高候选集合的可信度，"
        "再以宏蛋白组表达证据二次去重，最后通过抑菌实验对代表性候选肽进行验证，形成层层递进的证据链。",
        "2. 分阶段差异分析与特有抗菌肽筛选尚在实施。应对：按既定流程推进，先完成差异比较与表达证据过滤，"
        "再冻结特有肽清单；后续机制关联分析与抑菌实验共用同一份清单，避免重复分析、控制工作量。",
        "3. 机制关联分析的证据强度有限。应对：以分子对接与分子动力学模拟、文献比对为主，"
        "按致病方向检验候选肽是否推动 Aβ 聚集与神经炎症，同时将研究定位为线索发现与假设提出，"
        "不夸大因果性结论。",
    ],
}

# Ⅱ.导师指导情况：按"半程进度"写
ADVISOR = {
    "论文指导情况": (
        "自开题以来，导师在论文选题与总体框架、研究方案与技术路线、阶段成果整理与学术规范等方面给予持续指导。"
        "研究实施阶段，针对单一模型预测容易产生假阳性的问题，指导采用多个模型独立预测、"
        "取一致阳性结果构成候选集合；对公开数据的来源与处理口径、分析流程的可复现性提出明确要求，"
        "强调区分计算预测与实验证据，并通过定期组会与阶段汇报督促研究进度。"
        "目前数据处理与预测环节已完成，分阶段差异分析与特有抗菌肽筛选正在推进，"
        "机制关联分析与抑菌实验验证已排入后续计划。"
    ),
    "导师综合评语": (
        "该生科研作风严谨，能够独立查阅文献、完成数据处理与建模工作，具备较好的生物信息学分析基础。"
        "中期阶段已完成全队列宏基因组数据处理、微生物源短肽库构建与多模型共识预测等主体分析工作，"
        "候选抗菌肽名单已经形成，进度与开题计划一致；对预测假阳性等问题已有明确处理办法，"
        "后续工作安排合理。同意该生参加学位论文预答辩。"
    ),
}


def parse(lines: list[str]):
    cover, title, sections, order, advisor, members = [], None, {}, [], {}, []
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
        elif cur == "title" and title is None:
            title = line.strip()
        elif cur == "advisor" and "：" in line:
            k, v = line.split("：", 1)
            advisor[k.strip()] = v.strip()
        elif cur == "members":
            members.append(line.strip())
        elif cur in sections:
            sections[cur].append(line)
    return cover, title, sections, order, advisor, members


SECTION_TITLE = {
    "1": "论文研究主要内容及工作进度",
    "2": "阶段性成果",
    "3": "公开发表学术论文情况",
    "4": "尚需完成的研究工作（包括内容、方案）",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(DST))
    a = ap.parse_args(argv)

    lines = Path(a.src).read_text(encoding="utf-8").splitlines()
    cover, title, sections, order, _advisor, members = parse(lines)

    out = ["# 封面信息"] + cover + ["", "# 论文题目", title, ""]
    kept_body = total_body = 0
    kept_chars = total_chars = 0
    import re as _re
    counter = {"n": 0}

    def renumber(text: str) -> str:
        """小节内的编号重排：保留的行删掉中间几项后仍然连续。"""
        if text.startswith("!") or text[:1] in "（":
            counter["n"] = 0
            return text
        m = _re.match(r"^(\d+)([.、])", text)
        if not m:
            return text
        counter["n"] += 1
        return f"{counter['n']}{m.group(2)}" + text[m.end():]
    for key in order:
        out += [f"## {key}. {SECTION_TITLE.get(key, '')}", ""]
        items = sections[key]
        keep = set(KEEP.get(key, range(len(items))))
        customs = {i: t for (k, i), t in CUSTOM.items() if k == key}
        for i, line in enumerate(items):
            body = line[1:] if line.startswith("!") else line
            is_head = line.startswith("!") or line[:1] in "（"
            total_chars += len(body)
            total_body += 0 if is_head else 1
            if i in customs:
                text = customs[i]
                out.append(renumber(("!" + text) if text.startswith("（") else text))
                kept_chars += len(text)
                kept_body += 0 if text.startswith("（") else 1
            elif i in keep:
                out.append(renumber(line))
                kept_chars += len(body)
                kept_body += 0 if is_head else 1
            for extra in EXTRA.get((key, i), []):
                out.append(renumber(extra))
                kept_chars += len(extra)
                kept_body += 1
        out.append("")

    out += ["# 导师指导情况", ""]
    for k, v in ADVISOR.items():
        out.append(f"{k}：{v}")
        kept_chars += len(v)
        kept_body += 1
    out += ["", "# 检查小组成员", ""] + members + [""]

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {Path(a.out).relative_to(ROOT)}")
    print(f"  正文段落 {kept_body}/{total_body} = {kept_body / total_body:.0%}")
    print(f"  字数 {kept_chars}/{total_chars} = {kept_chars / total_chars:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
