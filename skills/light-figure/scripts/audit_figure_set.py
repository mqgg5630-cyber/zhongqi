#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_figure_set.py — 整组规划卡的集合级 display item 预算 + 反冗余机检门禁。

为什么有这个脚本（补"图集合规划"着墨最重却没机制化的卖点）
----------------------------------------------------------
SKILL 把"display item 预算核查（F#+T# 计数对照 venue 上限、超预算强制砍序）"与"反冗余
panel 检验"作为核心交付反复强调，但此前**没有任何脚本做集合级计数与裁定**——validate_plan_card.py
只做单卡契约校验，不跨卡数 display item、不对照 venue cap、不查冗余。最重的两个主张全靠人脑+prose。
本脚本把这两件事从 prose 升级成可机检门禁，与 validate_plan_card 一起作为交绘制前的双门;
其 audit_set() 引擎被灵魂门 visual_honesty_gate 编排消费(集合超预算/反冗余 → warn findings)。

两段检查
--------
  1. **display item 预算**：统计正文 F#(图)+T#(表) 总数，对照 venue 上限（--cap，权威值取目标刊
     作者指南；无 --cap 时只报计数 + 顶刊常 6-8 件的软参考，不擅自判超）。超预算时按 SKILL 既定
     **砍序**给可执行裁定：先砍"可删"→"可做"降附录→"必做"不动（删了没核心论证的不许砍）。
  2. **反冗余**：解析每卡"绑定 claim"+figure_type，把"两卡绑同一 claim 且 figure_type 同族"
     机检为候选冗余（把"遮住一个 panel 丢独有信息"部分落成 claim 重叠×图型族重叠）。claim 重叠用
     _shared/semantic_sim（挂接地基契约2，非词面 Jaccard），同族用图型关键词族字典。

⚠ 诚实边界：①venue cap 须用户给权威值（不内嵌某刊上限臆测，无本地期刊库）；②冗余是
  "候选"提示，最终合并/删除仍需人判（两卡同 claim 同族也可能是有意的 overview→deviation 递进）；
  ③只查可机检的计数/重叠，不替你判图好不好。出 light.findings.v1 接 orchestrator 闸门。

用法：
  python audit_figure_set.py F1.md F2.md T1.md --cap 8
  python audit_figure_set.py cards/*.md --cap 6 --json
  python audit_figure_set.py --selftest
"""
from __future__ import annotations
import argparse
import os
import pathlib
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)   # 复用同目录 validate_plan_card.parse_card
try:
    from validate_plan_card import parse_card as _parse_ascii   # noqa: E402
    _HAS_PARSE = True
except Exception:
    _HAS_PARSE = False

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,
# 治 v1 硬编码 `../../_shared` 之脆(v2 _shared 在仓库根、嵌套深度已变)。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.semantic_sim import similarity as _sem_sim     # noqa: E402
    _HAS_SEM = True
except ImportError:
    _HAS_SEM = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 图型族字典：同族两图回答同类问题→冗余候选
_FT_FAMILY = [
    (("柱", "bar", "条形", "直方"), "bar"),
    (("折线", "line", "曲线", "趋势", "收敛"), "line"),
    (("散点", "scatter", "回归"), "scatter"),
    (("热力", "heatmap", "热图", "矩阵"), "heatmap"),
    (("箱线", "box", "violin", "小提琴", "分布"), "distribution"),
    (("饼", "pie", "环形", "donut", "占比"), "pie"),
    (("雷达", "radar", "蛛网"), "radar"),
    (("表", "table"), "table"),
    (("流程", "flow", "架构", "framework", "示意", "结构图", "schematic"), "schematic"),
]

# Chinese/混合字段标签（parse_card 只认 ASCII 键，narrative 中文字段在此补抽）
_CN_FIELD = re.compile(r"^\|\s*\*{0,2}\s*(绑定\s*claim|优先级|组图归属|讲什么故事)\s*\*{0,2}\s*\|\s*(.*?)\s*\|\s*$")
_FIGID_RE = re.compile(r"^[FT]\d+$")


def _clean(v: str) -> str:
    v = v.replace("**", "").replace("`", "").strip()
    if v.startswith("{{") and v.endswith("}}"):
        return ""
    return v


def parse_set_card(text: str) -> dict:
    """抽出集合级审计需要的字段：figure_id / figure_type / 绑定claim / 优先级。"""
    fields = _parse_ascii(text) if _HAS_PARSE else {}
    # 补抽中文 narrative 字段
    for line in text.splitlines():
        m = _CN_FIELD.match(line)
        if m:
            key = re.sub(r"\s+", "", m.group(1)).lower()  # 绑定claim / 优先级 ...
            val = _clean(m.group(2))
            if val:
                fields[key] = val
    return {
        "figure_id": fields.get("figure_id", ""),
        "figure_type": fields.get("figure_type", ""),
        "claim_id": fields.get("claim_id", ""),   # 精确图↔claim 绑定(供 visual_honesty_gate)
        "claim": fields.get("绑定claim", "") or fields.get("claim", ""),
        "priority": _norm_priority(fields.get("优先级", "")),
        "purpose": fields.get("purpose", ""),
    }


def _norm_priority(v: str) -> str:
    if "必做" in v:
        return "must"
    if "可删" in v:
        return "cut"
    if "可做" in v:
        return "nice"
    return ""   # 未标


def _family(figure_type: str) -> str:
    ft = figure_type.lower()
    for kws, fam in _FT_FAMILY:
        if any(k.lower() in ft for k in kws):
            return fam
    return "other:" + (figure_type[:12] or "?")


def check_budget(cards: list, cap: int | None) -> dict:
    figs = [c for c in cards if c["figure_id"].startswith("F")]
    tabs = [c for c in cards if c["figure_id"].startswith("T")]
    total = len(figs) + len(tabs)
    out = {"n_figures": len(figs), "n_tables": len(tabs), "total": total, "cap": cap,
           "over_by": 0, "cut_plan": [], "status": "pass"}
    if cap is None:
        out["note"] = ("未传 --cap：只报计数。顶刊/顶会正文 display item 常 6-8 件（以目标刊作者指南为准），"
                       "传 --cap N 启用超预算砍序裁定。")
        return out
    if total <= cap:
        out["note"] = f"display item 总数 {total} ≤ venue 上限 {cap}，预算内。"
        return out
    # 超预算：按砍序给裁定（可删→可做降附录→必做不动）
    need = total - cap
    out["over_by"] = need
    out["status"] = "fail"
    plan = []
    # 先砍可删
    for c in [c for c in cards if c["priority"] == "cut"]:
        if len(plan) >= need:
            break
        plan.append({"figure_id": c["figure_id"], "action": "删除", "reason": "优先级=可删（冗余或弱）"})
    # 不够再把可做降附录
    if len(plan) < need:
        for c in [c for c in cards if c["priority"] == "nice"]:
            if len(plan) >= need:
                break
            plan.append({"figure_id": c["figure_id"], "action": "降附录", "reason": "优先级=可做（增强），移附录减正文件数"})
    out["cut_plan"] = plan
    if len(plan) < need:
        out["note"] = (f"超预算 {need} 件，但可删/可做仅够裁 {len(plan)} 件——剩余须砍'必做'或合并同质图。"
                       f"砍序铁律不删核心论证图，请合并 panel 或与作者权衡。")
        out["residual_unresolved"] = need - len(plan)
    else:
        out["note"] = f"超预算 {need} 件，已按砍序（可删→可做降附录）给出 {len(plan)} 件裁定建议，必做不动。"
    return out


def check_redundancy(cards: list, sim_threshold: float = 0.65) -> dict:
    """两卡绑同一 claim（语义近似）且 figure_type 同族 → 候选冗余。

    claim 重叠用 _shared/semantic_sim。⚠ 离线档（字符 n-gram）能抓字面近似的重复 claim，但
    对纯同义改写（"基线"↔"baseline"、"高于"↔"优于"）会漏判——真用建议注入 embedding 档
    （semantic_sim.set_embed_fn）提升同义级冗余召回，与本仓库其它技能挂 semantic_sim 同口径。
    """
    pairs = []
    n = len(cards)
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = cards[i], cards[j]
            cl_i, cl_j = ci["claim"], cj["claim"]
            if not cl_i or not cl_j:
                continue
            sim = _sem_sim(cl_i, cl_j) if _HAS_SEM else (1.0 if cl_i == cl_j else 0.0)
            fam_i, fam_j = _family(ci["figure_type"]), _family(cj["figure_type"])
            if sim >= sim_threshold and fam_i == fam_j:
                pairs.append({
                    "cards": [ci["figure_id"] or f"#{i}", cj["figure_id"] or f"#{j}"],
                    "claim_sim": round(sim, 3), "family": fam_i,
                    "severity": "major",
                    "msg": f"{ci['figure_id']} 与 {cj['figure_id']} 绑定 claim 语义近似(sim={round(sim,2)})"
                           f"且图型同族({fam_i})——候选冗余：两 panel 可能回答同一科学问题。"
                           f"考虑合并、删一张、或改成回答新问题的视角(如绝对值图→相对基线偏差)。"})
    return {"n_pairs": len(pairs), "pairs": pairs,
            "mode": "semantic_sim" if _HAS_SEM else "exact-fallback",
            "status": "fail" if pairs else "pass"}


def audit_set(card_texts: list, cap: int | None = None) -> dict:
    cards = [parse_set_card(t) for t in card_texts]
    budget = check_budget(cards, cap)
    redundancy = check_redundancy(cards)
    return {"n_cards": len(cards), "budget": budget, "redundancy": redundancy,
            "cards": [{"figure_id": c["figure_id"], "priority": c["priority"],
                       "family": _family(c["figure_type"]), "claim": c["claim"][:30]} for c in cards]}


def to_findings(rep: dict) -> dict:
    """转 light.findings.v1。预算超标(unresolved)或冗余 → 阻断。"""
    gates = []
    b = rep["budget"]
    if b["status"] == "fail":
        sev = "critical" if b.get("residual_unresolved") else "major"
        findings = [{"loc": "figure_set", "issue": b["note"], "fix": "; ".join(
            f"{p['figure_id']}→{p['action']}" for p in b["cut_plan"]), "rule": "DISPLAY-ITEM-BUDGET"}]
        gates.append({"gate": "display_item_budget", "status": "fail", "severity": sev, "findings": findings})
    else:
        gates.append({"gate": "display_item_budget", "status": "pass", "severity": "info", "findings": []})
    r = rep["redundancy"]
    if r["pairs"]:
        gates.append({"gate": "panel_redundancy", "status": "fail", "severity": "major",
                      "findings": [{"loc": "+".join(p["cards"]), "issue": p["msg"], "fix": "",
                                    "rule": "PANEL-REDUNDANCY"} for p in r["pairs"]]})
    else:
        gates.append({"gate": "panel_redundancy", "status": "pass", "severity": "info", "findings": []})
    verdict = "fail" if any(g["status"] == "fail" and g["severity"] == "critical" for g in gates) \
        else ("warn" if any(g["status"] == "fail" for g in gates) else "pass")
    return {"schema": "light.findings.v1", "producer": "figure", "target": "figure_set",
            "verdict": verdict, "gates": gates,
            "summary": f"图集审计：{rep['n_cards']}卡 预算{b['total']}/{b['cap']} 冗余{r['n_pairs']}对",
            "fresh_evidence": True}


def to_markdown(rep: dict) -> str:
    b, r = rep["budget"], rep["redundancy"]
    lines = [f"# 图集合级审计 — {rep['n_cards']} 张规划卡\n",
             f"## display item 预算：图 {b['n_figures']} + 表 {b['n_tables']} = {b['total']}"
             + (f" / 上限 {b['cap']}" if b["cap"] is not None else "（未传上限）"),
             f"> {b['note']}"]
    if b["cut_plan"]:
        lines.append("\n**砍序裁定（可删→可做降附录，必做不动）：**")
        lines += [f"- {p['figure_id']}：{p['action']}（{p['reason']}）" for p in b["cut_plan"]]
    lines.append(f"\n## 反冗余：{r['n_pairs']} 对候选冗余（claim 重叠×图型同族，{r['mode']}）")
    for p in r["pairs"]:
        lines.append(f"- [{p['severity']}] {p['msg']}")
    if not r["pairs"]:
        lines.append("✓ 无候选冗余 panel。")
    lines.append("\n> 须人判定夺：冗余为候选提示（同 claim 同族也可能是有意的 overview→deviation 递进）；"
                 "venue 上限须用目标刊作者指南权威值。与 validate_plan_card 一起作交绘制前双门。")
    return "\n".join(lines)


def _selftest() -> int:
    print("### audit_figure_set 离线自测", file=sys.stderr)

    def card(fid, claim, ftype, prio):
        return (f"# 图表规划卡 · `{fid}`\n"
                f"| **figure_id** | `{fid}` |\n"
                f"| **绑定 claim** | {claim} |\n"
                f"| **优先级** | {prio} |\n"
                f"| **figure_type** | {ftype} |\n"
                f"| **target_journal** | `nature` |\n"
                f"| **source_card** | x |\n")

    cards = [
        card("F1", "方法A在三数据集上准确率高于基线", "分组柱状图+误差棒", "必做（支撑核心贡献）"),
        card("F2", "方法A在三数据集上的准确率优于基线方法", "分组条形图", "可做（增强）"),  # 与F1字面近似冗余
        card("F3", "消融实验各组件贡献", "热力图", "可删（冗余或弱）"),
        card("F4", "训练收敛曲线", "折线图+置信带", "可做（增强）"),
        card("T1", "超参数设置表", "表格", "可做（增强）"),
        card("F5", "敏感性分析", "折线图", "可删（冗余或弱）"),
    ]
    # 1) 解析正确
    parsed = [parse_set_card(c) for c in cards]
    assert parsed[0]["figure_id"] == "F1" and parsed[0]["priority"] == "must", parsed[0]
    assert parsed[2]["priority"] == "cut" and parsed[4]["figure_id"] == "T1", parsed
    print(f"[parse] F1 claim='{parsed[0]['claim'][:20]}' prio={parsed[0]['priority']} "
          f"fam={_family(parsed[0]['figure_type'])}", file=sys.stderr)

    # 2) 预算：6 件，cap=4 → 超 2，砍序应先砍可删(F3/F5)
    rep = audit_set(cards, cap=4)
    b = rep["budget"]
    print(to_markdown(rep), file=sys.stderr)
    assert b["total"] == 6 and b["over_by"] == 2, b
    cut_ids = [p["figure_id"] for p in b["cut_plan"]]
    assert cut_ids == ["F3", "F5"], cut_ids   # 两张可删优先被砍
    assert all(p["action"] == "删除" for p in b["cut_plan"]), b["cut_plan"]
    print("[budget] 超2件,砍序先砍可删F3/F5 ... OK", file=sys.stderr)

    # 3) 预算够大不超 → pass
    rep_ok = audit_set(cards, cap=8)
    assert rep_ok["budget"]["status"] == "pass", rep_ok["budget"]

    # 4) 砍序：cap=3 需砍3,可删只2张→不够,降1张可做附录
    rep3 = audit_set(cards, cap=3)
    b3 = rep3["budget"]
    assert b3["over_by"] == 3 and len(b3["cut_plan"]) == 3, b3
    actions = [p["action"] for p in b3["cut_plan"]]
    assert actions.count("删除") == 2 and actions.count("降附录") == 1, actions
    print("[budget] cap=3:删2可删+降1可做附录 ... OK", file=sys.stderr)

    # 5) 冗余：F1 与 F2 绑近似 claim + 同族(bar) → 候选冗余
    r = rep["redundancy"]
    assert r["n_pairs"] >= 1, r
    assert any(set(p["cards"]) == {"F1", "F2"} for p in r["pairs"]), r["pairs"]
    print(f"[redundancy] F1×F2 候选冗余({r['mode']}) ... OK", file=sys.stderr)

    # 6) F4(折线) 与 F5(折线) claim 不同(收敛 vs 敏感性) → 不应误判冗余
    assert not any(set(p["cards"]) == {"F4", "F5"} for p in r["pairs"]), "claim 不同不应判冗余"
    print("[redundancy] 同族但 claim 不同不误判 ... OK", file=sys.stderr)

    # 7) findings 转换
    f = to_findings(rep)
    assert f["schema"] == "light.findings.v1", f
    assert any(g["gate"] == "panel_redundancy" and g["status"] == "fail" for g in f["gates"]), f

    # 8) 无 cap：只报计数不判超
    rep_nc = audit_set(cards, cap=None)
    assert rep_nc["budget"]["status"] == "pass" and rep_nc["budget"]["cap"] is None, rep_nc["budget"]
    print("[budget] 无cap只报计数 ... OK", file=sys.stderr)

    print("[selftest] PASS audit_figure_set offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="图集合级 display item 预算 + 反冗余审计")
    ap.add_argument("cards", nargs="*", help="规划卡 .md 路径（多张）")
    ap.add_argument("--cap", type=int, default=None, help="venue display item 上限（目标刊作者指南权威值）")
    ap.add_argument("--json", action="store_true", help="输出 light.findings.v1 JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or not args.cards:
        return _selftest()
    texts = []
    for p in args.cards:
        with open(p, encoding="utf-8") as f:
            texts.append(f.read())
    rep = audit_set(texts, cap=args.cap)
    if args.json:
        import json
        print(json.dumps(to_findings(rep), ensure_ascii=False, indent=2))
    else:
        print(to_markdown(rep))
    # 预算 unresolved 超标 或 有冗余 → 退出码 1（接 orchestrator 闸门）
    bad = rep["budget"].get("residual_unresolved") or rep["redundancy"]["pairs"] \
        or rep["budget"]["status"] == "fail"
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
