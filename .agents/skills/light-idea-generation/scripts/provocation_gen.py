#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""provocation_gen.py — 反 frame-lock 激发器 + legacy 角度/数量诊断。

把 SKILL "不够发散时补技法" 从口头建议变成**可机检**（与 card_gate 同philosophy）：
  模式A 激发(--seed)：用结构化激发算子 × 核心实体**机械生成**发散提问，强制跨域重组——
       组合创新/跨域知识重组实证可提升 idea 多样性与新颖性(组合创新多 agent 研究)。破"在一条思路上死磕"。
  模式B 覆盖(--coverage)：给已生成候选(每条带 angle 标签)，诊断 7 角度覆盖 + ≥15 数量建议；
       某角度 0 候选 → 标 frame-lock 风险；是否阻断由 idea_genealogy 的机制覆盖与判别实验决定。

诚实：本脚本**不产生洞察**（那靠人 + 底座模型 + 喂进的文献/数据质量），只保证**发散面够宽、
不能证明没在单一框架里死锁**。激发提问是脚手架，须研究者/LLM 据本项目填实质内容；覆盖诊断只数角度分布，
不判 idea 好坏（那是 rank_ideas/idea-critique 的事）。垃圾进垃圾出。

算子来源（references 已研究）：Scientific Brainstorming(约束增删/尺度切换/技术外推)、
反事实提示(假设反转)、组合创新研究(跨域强配)、ResearchAgent(核心实体抽取再找高共现邻域)。

用法：
  python provocation_gen.py --seed "对比学习,加速度序列,发情行为"
  python provocation_gen.py --seed entities.json --json     # json: ["实体1","实体2",...]
  python provocation_gen.py --coverage candidates.json       # [{"id","title","angle"},...]
  python provocation_gen.py --selftest
"""
from __future__ import annotations
import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# SKILL 的 7 个发散角度（与 SKILL.md "生成策略" 一一对应）
ANGLES = ["gap-driven", "method-transfer", "data-driven", "problem-reframe",
          "combination", "theory-gap", "efficiency"]

# 单实体激发算子：(算子名, 归属角度, 提问模板)。每角度至少被一个算子覆盖。
_SOLO_OPS = [
    ("空白直击", "gap-driven",
     "针对「{e}」，文献里最该做却没人做的那一个点是什么？至今没人做是因为难、不重要、还是没人想到？"),
    ("技术外推", "method-transfer",
     "用最新技术（大模型 / 因果推断 / 扩散模型 / 自监督）重做「{e}」，能否绕开现有瓶颈？搬哪个领域的 SOTA 最省力？"),
    ("尺度切换", "data-driven",
     "把「{e}」从当前尺度切换（个体↔群体、毫秒↔年、局部↔全局），哪个尺度上有人没做过、数据却支持？"),
    ("假设反转", "problem-reframe",
     "把「{e}」的核心假设反过来：若其前提不成立、或结论相反会怎样？反转后是否暴露被忽略的新机会或新评价方式？"),
    ("失效驱动", "theory-gap",
     "「{e}」在什么条件下必然失败？这个失效点能否反转成新理论缺口或可解释性/泛化保证的切入点？"),
    ("约束增删", "efficiency",
     "若算力/数据/时间无限，「{e}」能做到什么极限？反过来只剩 1/10 资源，「{e}」如何更快更省更小地重做？"),
]


def generate(entities: list) -> list:
    """实体 × 算子机械生成发散提问。跨域强配做实体两两组合(combination 角度)。"""
    provos = []
    for e in entities:
        for op, angle, tmpl in _SOLO_OPS:
            provos.append({"op": op, "angle": angle, "entity": e, "q": tmpl.format(e=e)})
    # 跨域强配：实体两两组合 → combination 角度（组合创新跨域重组）
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            a, b = entities[i], entities[j]
            provos.append({
                "op": "跨域强配", "angle": "combination", "entity": f"{a}+{b}",
                "q": (f"把「{a}」与「{b}」强行组合：1+1>2 的机理是什么？"
                      f"不是堆叠——是哪一方补了另一方的本质短板？反过来组合行不行？")})
    return provos


def coverage(items: list, min_total: int = 15) -> dict:
    """诊断候选的 7 角度与数量；它们是 advisory，硬门交 idea_genealogy。"""
    counts = {a: 0 for a in ANGLES}
    unknown = []
    for it in items:
        a = (it.get("angle") or "").strip()
        if a in counts:
            counts[a] += 1
        else:
            unknown.append(a or "(空)")
    total = len(items)
    missing = [a for a, c in counts.items() if c == 0]
    errors, warnings = [], []
    if total < min_total:
        warnings.append(
            f"原始候选仅 {total} 条 < 建议值 {min_total}；数量不单独阻断，检查机制谱系与判别实验"
        )
    if missing:
        warnings.append(f"以下 legacy 角度 0 候选（frame-lock 信号）：{', '.join(missing)}")
    if len(missing) >= 4:
        warnings.append("7 角度中 ≥4 角度空白：建议重发散，但由机制/假设/证据路径覆盖决定是否阻断")
    if unknown:
        warnings.append(f"{len(unknown)} 条候选 angle 标签非法或缺失：{set(unknown)}——无法计入覆盖统计")
    # 角度过度集中（某角度占比 > 60%）也是变相 frame-lock
    if total:
        for a, c in counts.items():
            if c / total > 0.6 and total >= 5:
                warnings.append(f"角度「{a}」占比 {c}/{total} > 60%，发散偏科，建议补其余角度")
    return {"total": total, "min_total": min_total, "counts": counts,
            "missing_angles": missing, "passed": True, "advisory": True,
            "errors": errors, "warnings": warnings}


def render_seed(provos: list, entities: list) -> str:
    lines = [f"# 强制发散激发单（{len(entities)} 实体 × 算子 → {len(provos)} 条提问）", "",
             "> 逐条带着本项目背景作答，每条至少逼出 1 个候选 idea；答完汇成 candidates.json 再跑 --coverage 自检覆盖。",
             "> 提问是脚手架，不是 idea 本身——洞察靠你 + 文献 + 数据，本单只保证你没在单一思路上死磕。", ""]
    by_angle = {a: [] for a in ANGLES}
    for p in provos:
        by_angle.setdefault(p["angle"], []).append(p)
    for a in ANGLES:
        if by_angle[a]:
            lines.append(f"## {a}")
            for p in by_angle[a]:
                lines.append(f"- [{p['op']} · {p['entity']}] {p['q']}")
            lines.append("")
    return "\n".join(lines)


def render_cov(res: dict) -> str:
    mark = "ℹ️ advisory（数量/旧角度不单独阻断）"
    lines = [f"# 发散覆盖诊断 — {mark}", "",
             f"原始候选 {res['total']} 条（建议值 ≥{res['min_total']}）。各角度计数：", ""]
    for a in ANGLES:
        c = res["counts"][a]
        flag = " ⚠️空" if c == 0 else ""
        lines.append(f"- {a}: {c}{flag}")
    lines.append("")
    for e in res["errors"]:
        lines.append(f"- [拦截] {e}")
    for w in res["warnings"]:
        lines.append(f"- [警示] {w}")
    lines += ["", "> 数量与旧角度只作信号；机制谱系和最小判别实验由 idea_genealogy 硬门检查。"]
    return "\n".join(lines)


def _parse_entities(raw: str) -> list:
    raw = raw.strip()
    if raw.startswith("["):
        return [str(x).strip() for x in json.loads(raw) if str(x).strip()]
    return [s.strip() for s in raw.replace("，", ",").split(",") if s.strip()]


def _selftest() -> int:
    print("### provocation_gen 离线自测", file=sys.stderr)
    ents = ["对比学习", "加速度序列", "发情行为"]
    provos = generate(ents)
    angles_hit = {p["angle"] for p in provos}
    # 7 角度必须全被激发覆盖（保证发散单不偏科）
    assert set(ANGLES) == angles_hit, f"激发未覆盖全部角度: {set(ANGLES) - angles_hit}"
    # 3 实体两两组合 = 3 条跨域强配
    combos = [p for p in provos if p["op"] == "跨域强配"]
    assert len(combos) == 3, len(combos)
    # 每实体 6 个单算子 → 18 + 3 跨域 = 21
    assert len(provos) == len(ents) * len(_SOLO_OPS) + 3, len(provos)

    # 覆盖诊断：齐全且 ≥15 无警告
    good = [{"id": f"I{i}", "angle": ANGLES[i % 7]} for i in range(15)]
    cov = coverage(good)
    assert cov["passed"], cov["errors"]
    # 只有 1 个角度、且 <15 → 警告但不凭形式阈值阻断
    bad = [{"id": f"I{i}", "angle": "gap-driven"} for i in range(3)]
    cov2 = coverage(bad)
    assert cov2["passed"] and cov2["advisory"], cov2
    assert any("frame-lock" in warning or "数量" in warning for warning in cov2["warnings"])
    assert len(cov2["missing_angles"]) == 6, cov2["missing_angles"]
    # 非法 angle 标签告警
    cov3 = coverage([{"id": "x", "angle": "瞎写的"}] + good)
    assert any("非法" in w for w in cov3["warnings"]), cov3["warnings"]
    # 过度集中告警（某角度 > 60%）
    skew = [{"id": f"I{i}", "angle": "gap-driven"} for i in range(12)] + \
           [{"id": f"J{i}", "angle": ANGLES[i + 1]} for i in range(6)]
    cov4 = coverage(skew)
    assert any("占比" in w for w in cov4["warnings"]), cov4["warnings"]
    # 渲染不崩
    assert "强制发散激发单" in render_seed(provos, ents)
    assert "发散覆盖诊断" in render_cov(cov2)
    # 实体解析：逗号 / 中文逗号 / json 三种
    assert _parse_entities("a,b，c") == ["a", "b", "c"]
    assert _parse_entities('["x","y"]') == ["x", "y"]
    print("[selftest] PASS provocation_gen offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="反 frame-lock 激发器 + legacy 角度/数量诊断")
    ap.add_argument("--seed", help="核心实体：逗号分隔字符串 或 JSON 数组文件路径")
    ap.add_argument("--coverage", dest="cov", help="候选 JSON [{id,title,angle}] 做 advisory 诊断")
    ap.add_argument("--min-total", type=int, default=15, help="数量建议值，默认 15")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or (not args.seed and not args.cov):
        return _selftest()

    if args.cov:
        with open(args.cov, encoding="utf-8") as f:
            items = json.load(f)
        res = coverage(items, args.min_total)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render_cov(res))
        return 0 if res["passed"] else 1

    raw = args.seed
    try:
        with open(raw, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        pass  # 不是文件就当逗号分隔字符串
    entities = _parse_entities(raw)
    if not entities:
        print("未解析到实体", file=sys.stderr)
        return 2
    provos = generate(entities)
    print(json.dumps(provos, ensure_ascii=False, indent=2) if args.json else render_seed(provos, entities))
    return 0


if __name__ == "__main__":
    sys.exit(main())
