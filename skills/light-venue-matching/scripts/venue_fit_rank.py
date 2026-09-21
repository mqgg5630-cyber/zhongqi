#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""venue_fit_rank.py — 冲刺/稳妥/保底 分层推荐引擎 + 决策点（Light / light-venue-matching, stage 12）。

输入一篇稿件画像（成色/方向/背景约束）+ 一组候选 venue（每个带 venue_signal 信号或用户给的最小字段），
输出**分层推荐工件** `light.venue_reco.v1`：把候选分成
  ① 冲刺(reach)：够一够可能中、回报高（venue 门槛高于本稿成色，但有真实机会）
  ② 稳妥(match)：实力匹配、大概率中（门槛与本稿成色相当）
  ③ 保底(safety)：确保能发/能毕业（门槛低于本稿成色、录用可能性高）
  ④ 不推荐/劝退(excluded)：官方 article/scope/format 明确不匹配或作者 hard constraint 命中。
     掠夺/劫持软信号只保留 warn，绝不自动剔除或终判。

**门型诚实（spec §1.2(e)/§2.2/§2.3/§6 + 蓝图 §4.3-12）**：venue 选择是**决策点**不是确认点闸门——
  本工具**只产分层建议 + 摆每档后果**，`decision_point=True` 恒真、`chosen=None` 恒空：
  **绝不替用户选 venue、绝不自动投**。用户拍板由调用方经 AskUserQuestion 完成（见 SKILL §决策点）。
  这与 reroute.py「只产建议不执行」同范式：押战略分支的事，执行权永远留用户。

**不编造（铁律 2）**：
- 录用可能性只给定性 band(高/中/低) + 逐条理由，**绝不编录用概率/百分比**（除非候选自带官方接收率）。
- venue 门槛(venue_tier) 由用户给/在线查的标记解析（CCF-A/中科院1区/官方接收率%），解析不了标 unknown，不臆造档位。
- 方向匹配/作者实力为启发式参考（来自 venue_signal 信号6/7），非真值；最终人工定档。
- venue 数据有时效：本工具不内嵌任何 venue 库，候选字段全由上游(venue_signal/用户)给。

**分层逻辑**（可解释，每条带 because）：
  per-candidate 先算 ①录用可能性 band（rubric 汇总：方向匹配 × 作者实力 × 方法规模，致命短板=方向/方法不达标）
  + ②venue 门槛 vs 本稿成色 关系（above/at/below/unknown，成色由 novelty 自评 × 作者实力）；
  再 (band × 关系) → tier。预警信号进入 risk_warnings，不改变 tier；终判由用户多源人工完成。

**档内排序**（转投顺序字典序，v1 SKILL）：方向匹配↓ → 录用 band↓ → 审稿周期↑ → APC↑
  （deadline_sensitive 时周期权重前移；budget_sensitive 时 APC 权重前移）。

用法：
    python venue_fit_rank.py --manuscript ms.json --candidates cands.json --out reco.json
    python venue_fit_rank.py --candidates cands.json   # 稿件画像可省（成色按 unknown）
    python venue_fit_rank.py --selftest

依赖：纯 Python stdlib。无网络、无外部数据、无第三方包（取数在 venue_signal.py，本脚本只做分层）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA_RECO = "light.venue_reco.v1"

_LEVELS = ("高", "中", "低")
_LEVEL_RANK = {"高": 2, "中": 1, "低": 0, None: -1}

# 成色档（本稿）/ venue 门槛档 的统一 0-2 量纲（越大越强/越难）。
_STRENGTH_RANK = {"high": 2, "mid": 1, "low": 0, "unknown": -1}
_NOVELTY_TO_RANK = {"new_paradigm": 2, "significant": 1, "incremental": 0}


# ───────────────────────── venue 门槛解析（不臆造，解析不了标 unknown） ─────────────────────────

def parse_venue_bar(venue_tier: Optional[str]) -> str:
    """把用户给/在线查的 venue 档位标记解析为门槛档 high/mid/low/unknown。
    诚实：只认明确模式（CCF-A/B/C、中科院/分区 1-4 区、官方接收率%），其余一律 unknown，绝不臆造。"""
    if not venue_tier:
        return "unknown"
    t = str(venue_tier).strip().lower()
    # 官方接收率（仅当显式给 acc_rate=X% / 接收率 X%）：<15% 高门槛, 15-30% 中, >30% 低
    m = re.search(r"(?:acc[_a-z]*rate|接收率|录用率)\s*[=:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%", t)
    if m:
        v = float(m.group(1))
        return "high" if v < 15 else ("mid" if v <= 30 else "low")
    # CCF A/B/C
    m = re.search(r"ccf[\s\-]*([abc])", t)
    if m:
        return {"a": "high", "b": "mid", "c": "low"}[m.group(1)]
    # 中科院/JCR 分区：1 区=高, 2 区=中, 3/4 区=低；Q1=高,Q2=中,Q3/Q4=低
    m = re.search(r"([1-4])\s*区", t)
    if m:
        return {"1": "high", "2": "mid", "3": "low", "4": "low"}[m.group(1)]
    m = re.search(r"q([1-4])", t)
    if m:
        return {"1": "high", "2": "mid", "3": "low", "4": "low"}[m.group(1)]
    return "unknown"


def paper_strength(ms: dict) -> str:
    """本稿成色档 high/mid/low/unknown：novelty 自评(主观) × 作者实力(venue_signal 信号7)取较高侧偏保守。
    novelty 缺失则只看作者实力；都缺 → unknown。诚实标注 novelty 为主观自评。"""
    nov = ms.get("novelty")
    nov_rank = _NOVELTY_TO_RANK.get(nov) if nov else None
    astr = ms.get("author_strength")
    a_rank = {"高": 2, "中": 1, "低": 0}.get(astr) if astr else None
    ranks = [r for r in (nov_rank, a_rank) if r is not None]
    if not ranks:
        return "unknown"
    # 取均值四舍五入（成色是 novelty 与作者实力的综合，偏保守用 floor 于 .5）
    avg = sum(ranks) / len(ranks)
    if avg >= 1.5:
        return "high"
    if avg >= 0.5:
        return "mid"
    return "low"


# ───────────────────────── per-candidate 录用可能性 band（rubric 汇总） ─────────────────────────

def acceptance_band(cand: dict) -> tuple:
    """rubric 汇总规则（v1 SKILL）→ 录用可能性 band(高/中/低) + 逐条理由。
    致命短板：方向匹配=低 或 方法规模=不足 → 直接低。否则按"高"信号多寡定 高/中。
    返回 (band, reasons:list[str], fatal:bool)。绝不编概率，只定性。"""
    fit = cand.get("direction_fit")
    method = cand.get("method_scale")
    author = cand.get("author_strength")
    reasons = []
    fatal = False
    if fit:
        reasons.append(f"方向匹配={fit}")
    if author:
        reasons.append(f"作者实力={author}")
    if method:
        reasons.append(f"方法规模={method}")
    # 致命短板判定
    if fit == "低":
        fatal = True
        reasons.append("致命短板：方向明显不达标(投错 scope 浪费周期)")
    if method == "不足":
        fatal = True
        reasons.append("致命短板：方法/数据规模明显不足")
    if fatal:
        return "低", reasons, True
    present = [x for x in (fit, author, method_to_level(method)) if x in _LEVELS]
    if not present:
        return "中", reasons + ["可核查信号不足，暂按中（须人工补方向/作者/方法评估）"], False
    highs = sum(1 for x in present if x == "高")
    lows = sum(1 for x in present if x == "低")
    if highs >= max(1, (len(present) + 1) // 2) and lows == 0:
        return "高", reasons, False
    return "中", reasons, False


def method_to_level(method: Optional[str]) -> Optional[str]:
    """方法规模 达标/部分/不足 → 高/中/低（用于 band 计票）。"""
    return {"达标": "高", "部分": "中", "不足": "低"}.get(method) if method else None


# ───────────────────────── 预警剔除（命中即出局，入 excluded） ─────────────────────────

def is_flagged(cand: dict) -> List[str]:
    """返回掠夺/劫持软预警，供解释展示，不作自动剔除。
    信号由上游 venue_risk_gate / venue_signal 给；多源人工核查才可终判。"""
    flags = list(cand.get("predatory_flags") or [])
    return flags


# ───────────────────────── 分层映射 ─────────────────────────

# (band, relation) → tier。relation: above/at/below/unknown（venue 门槛相对本稿成色）。
def map_tier(band: str, relation: str) -> str:
    if band == "低":
        return "excluded"            # 致命短板 → 不推荐（方向/方法不达标）
    if relation == "below":
        return "保底" if band == "高" else "稳妥"
    if relation == "at":
        return "稳妥"
    if relation == "above":
        return "冲刺" if band in ("高", "中") else "excluded"
    # unknown 门槛：按 band 退化（标待核查档位）
    return "稳妥" if band == "高" else "冲刺"


def relation_of(cand: dict, p_strength: str) -> str:
    """venue 门槛 vs 本稿成色：above/at/below/unknown。"""
    bar = parse_venue_bar(cand.get("venue_tier"))
    if bar == "unknown" or p_strength == "unknown":
        return "unknown"
    d = _STRENGTH_RANK[bar] - _STRENGTH_RANK[p_strength]
    return "above" if d > 0 else ("below" if d < 0 else "at")


# ───────────────────────── 档内排序（转投顺序字典序，v1 SKILL） ─────────────────────────

def sort_key(entry: dict, budget_sensitive: bool, deadline_sensitive: bool):
    """方向匹配↓ → 录用 band↓ → 审稿周期↑ → APC↑（敏感项权重前移）。
    返回排序元组（升序排序，故"越优先"映射到越小的值：用负 rank / 正周期·APC）。"""
    fit_r = -_LEVEL_RANK.get(entry.get("direction_fit"), -1)
    band_r = -_LEVEL_RANK.get(entry.get("acceptance_band"), -1)
    weeks = entry.get("review_weeks")
    weeks_k = weeks if isinstance(weeks, (int, float)) else 9999
    apc = entry.get("apc_usd")
    apc_k = apc if isinstance(apc, (int, float)) else 999999
    base = [fit_r, band_r]
    if deadline_sensitive:
        return tuple([weeks_k] + base + [apc_k])
    if budget_sensitive:
        return tuple([apc_k] + base + [weeks_k])
    return tuple(base + [weeks_k, apc_k])


# ───────────────────────── 主流程 ─────────────────────────

@dataclass
class Reco:
    """分层推荐工件（决策点恒真、chosen 恒空：绝不替用户选）。"""
    manuscript: dict
    paper_strength: str
    tiers: dict = field(default_factory=lambda: {"冲刺": [], "稳妥": [], "保底": []})
    excluded: list = field(default_factory=list)
    decision_point: bool = True
    chosen: Optional[str] = None     # 恒 None：本工具绝不自动选 venue
    schema: str = SCHEMA_RECO
    note: str = ("分层推荐=建议非决定：venue 选择是决策点(spec §2.2/§6)，停下问用户(给冲刺/稳妥/保底"
                 "+每档后果+推荐理由)，**绝不替用户选 venue、绝不自动投**；用户拍板由 AskUserQuestion 完成。")
    caveats: list = field(default_factory=lambda: [
        "录用可能性为定性 band(高/中/低)+理由，非概率；无官方接收率绝不编百分比。",
        "venue 门槛由用户给/在线查标记解析，解析不了标 unknown(待核查档位)，不臆造。",
        "方向匹配/作者实力为 venue_signal 启发式参考非真值；最终人工定档。",
        "预警命中=warn 启发(见 venue_risk_gate)非掠夺终判；劝退候选仍由用户在决策点定夺。",
        "venue 数据有时效，投前在线重核(venue_signal --issn)、冲突信在线、查不到标 unknown。",
    ])

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "decision_point": self.decision_point,
            "chosen": self.chosen,
            "paper_strength": self.paper_strength,
            "manuscript": self.manuscript,
            "tiers": self.tiers,
            "excluded": self.excluded,
            "note": self.note,
            "caveats": self.caveats,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def rank(manuscript: dict, candidates: list) -> Reco:
    ms = manuscript or {}
    p_strength = paper_strength(ms)
    reco = Reco(manuscript=ms, paper_strength=p_strength)
    budget = bool(ms.get("budget_sensitive"))
    deadline = bool(ms.get("deadline_sensitive"))

    for cand in candidates or []:
        name = cand.get("name") or cand.get("venue_name") or "(未命名 venue)"
        flags = is_flagged(cand)
        band, reasons, fatal = acceptance_band(cand)
        relation = relation_of(cand, p_strength)
        bar = parse_venue_bar(cand.get("venue_tier"))
        entry = {
            "name": name,
            "type": cand.get("type"),
            "direction_fit": cand.get("direction_fit"),
            "acceptance_band": band,
            "venue_bar": bar,
            "bar_vs_paper": relation,
            "review_weeks": cand.get("review_weeks"),
            "apc_usd": cand.get("apc_usd"),
            "indexing": cand.get("indexing"),
            "official_acceptance_rate": cand.get("official_acceptance_rate"),  # 仅官方公开才填
        }
        if flags:
            entry["risk_warnings"] = flags
        tier = map_tier(band, relation)
        # because：把分层依据落成可解释一句话（无裸结论，铁律：每条分级跟"因为…"）
        bar_zh = {"high": "高门槛", "mid": "中门槛", "low": "低门槛", "unknown": "门槛待核查"}[bar]
        rel_zh = {"above": "高于本稿成色(够一够)", "at": "与本稿成色相当",
                  "below": "低于本稿成色(录用可能性高)", "unknown": "门槛未知"}[relation]
        risk_note = (
            "；软风险只 warn、待多源人工终判=" + "；".join(flags)
            if flags else ""
        )
        entry["because"] = (f"录用 band={band}({'；'.join(reasons)})；venue {bar_zh}、{rel_zh}"
                            f" → 归 {tier if tier != 'excluded' else '不推荐'}{risk_note}")
        if tier == "excluded":
            entry["reason"] = "scope_or_method_not_met" if fatal else "reach_too_far"
            reco.excluded.append(entry)
        else:
            reco.tiers[tier].append(entry)

    # 档内排序（转投顺序字典序）
    for t in reco.tiers:
        reco.tiers[t].sort(key=lambda e: sort_key(e, budget, deadline))
    return reco


def render(reco: Reco) -> str:
    L = ["# 投稿定位 · 分层推荐（决策点，停下问用户——绝不替你选 venue）", ""]
    L.append(f"- 本稿成色档：**{reco.paper_strength}**"
             f"（novelty={reco.manuscript.get('novelty', '未给')} ×"
             f" 作者实力={reco.manuscript.get('author_strength', '未给')}；novelty 为主观自评）")
    L.append("")
    tier_desc = {"冲刺": "够一够可能中、回报高", "稳妥": "实力匹配、大概率中", "保底": "确保能发/能毕业"}
    for t in ("冲刺", "稳妥", "保底"):
        items = reco.tiers[t]
        L.append(f"## {t}（{tier_desc[t]}）— {len(items)} 个")
        if not items:
            L.append("- （无候选）")
        for e in items:
            acc = e.get("official_acceptance_rate")
            acc_s = f"｜官方接收率 {acc}" if acc else "｜接收率 待核查(禁编概率)"
            rev = e.get("review_weeks")
            rev_s = f"{rev}周" if rev is not None else "待核查"
            apc = e.get("apc_usd")
            apc_s = f"${apc}" if apc is not None else "待核查"
            L.append(f"- **{e['name']}**（{e.get('type') or '?'}）：方向匹配={e.get('direction_fit') or '?'}"
                     f"｜录用 band={e['acceptance_band']}{acc_s}｜审稿≈{rev_s}｜APC={apc_s}"
                     f"｜索引={e.get('indexing') or '?'}")
            L.append(f"  - 因为：{e['because']}")
        L.append("")
    if reco.excluded:
        L.append(f"## 不推荐 / 劝退 — {len(reco.excluded)} 个")
        for e in reco.excluded:
            L.append(f"- **{e['name']}**：{e['because']}")
        L.append("")
    L.append("> 🧑 " + reco.note)
    L.append("> ⚠ 数据时效：venue 字段投前用 `venue_signal.py --issn` 在线重核；预警判定非终判，"
             "对照 Cabells/Beall 存档/Retraction Watch 劫持/中科院预警**当前版**人工确认。")
    return "\n".join(L)


# ───────────────────────── selftest（离线，合成候选） ─────────────────────────

def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")

    # venue 门槛解析（不臆造）
    check(parse_venue_bar("CCF-A") == "high", "CCF-A → high 门槛")
    check(parse_venue_bar("中科院1区") == "high", "中科院1区 → high")
    check(parse_venue_bar("中科院2区") == "mid", "中科院2区 → mid")
    check(parse_venue_bar("JCR Q3") == "low", "Q3 → low")
    check(parse_venue_bar("acc_rate=8%") == "high", "接收率 8% → high 门槛")
    check(parse_venue_bar("接收率 45%") == "low", "接收率 45% → low 门槛")
    check(parse_venue_bar("某不知名刊") == "unknown", "未知标记 → unknown(不臆造)")
    check(parse_venue_bar(None) == "unknown", "无标记 → unknown")

    # 本稿成色
    check(paper_strength({"novelty": "new_paradigm", "author_strength": "高"}) == "high", "新范式+高作者 → high")
    check(paper_strength({"novelty": "incremental", "author_strength": "低"}) == "low", "增量+低作者 → low")
    check(paper_strength({}) == "unknown", "无画像 → unknown 成色")

    # 录用 band：致命短板（方向=低）→ 低 + fatal
    b, r, fatal = acceptance_band({"direction_fit": "低", "author_strength": "高"})
    check(b == "低" and fatal, "方向=低 → band 低 + fatal")
    b2, _, f2 = acceptance_band({"direction_fit": "高", "author_strength": "高", "method_scale": "达标"})
    check(b2 == "高" and not f2, "全高 → band 高")
    b3, _, _ = acceptance_band({"direction_fit": "高", "author_strength": "低", "method_scale": "部分"})
    check(b3 == "中", "互有高低 → band 中")

    # 分层映射
    check(map_tier("中", "above") == "冲刺", "band中×门槛高于成色 → 冲刺")
    check(map_tier("高", "at") == "稳妥", "band高×门槛相当 → 稳妥")
    check(map_tier("高", "below") == "保底", "band高×门槛低于成色 → 保底")
    check(map_tier("低", "at") == "excluded", "band低(致命短板) → excluded")
    check(map_tier("高", "unknown") == "稳妥", "门槛未知×band高 → 稳妥(待核查)")

    # 端到端：合成稿件 + 4 候选（冲刺/稳妥/保底/预警劝退）
    ms = {"novelty": "significant", "author_strength": "中", "budget_sensitive": True}
    cands = [
        {"name": "Reach-Conf-A", "type": "conference", "venue_tier": "CCF-A",
         "direction_fit": "高", "author_strength": "中", "method_scale": "部分",
         "review_weeks": 12, "apc_usd": 0, "indexing": "EI"},
        {"name": "Match-Journal-B", "type": "journal", "venue_tier": "中科院2区",
         "direction_fit": "高", "author_strength": "中", "method_scale": "达标",
         "review_weeks": 10, "apc_usd": 1800, "indexing": "SCIE"},
        {"name": "Safety-Journal-C", "type": "journal", "venue_tier": "JCR Q3",
         "direction_fit": "高", "author_strength": "高", "method_scale": "达标",
         "review_weeks": 8, "apc_usd": 800, "indexing": "ESCI"},
        {"name": "Predatory-X", "type": "journal", "venue_tier": "unknown",
         "direction_fit": "中", "predatory_flags": ["DOAJ 未收录且高 APC", "超快审稿(48h 录用)"],
         "review_weeks": 1, "apc_usd": 2500},
        {"name": "OffScope-Y", "type": "journal", "venue_tier": "中科院2区",
         "direction_fit": "低", "review_weeks": 9, "apc_usd": 1200},
    ]
    reco = rank(ms, cands)
    # 成色 significant(1)×中(1)=mid
    check(reco.paper_strength == "mid", f"本稿成色=mid（得 {reco.paper_strength}）")
    # Reach-Conf-A: CCF-A(high) vs mid成色 → above；band 中 → 冲刺
    check(any(e["name"] == "Reach-Conf-A" for e in reco.tiers["冲刺"]), "CCF-A 高门槛 → 冲刺")
    # Match-B: 2区(mid) vs mid → at；band 高 → 稳妥
    check(any(e["name"] == "Match-Journal-B" for e in reco.tiers["稳妥"]), "2区相当 → 稳妥")
    # Safety-C: Q3(low) vs mid → below；band 高 → 保底
    check(any(e["name"] == "Safety-Journal-C" for e in reco.tiers["保底"]), "Q3 低门槛+band高 → 保底")
    # Predatory-X：软信号只 warn，不自动剔除/误判掠夺。
    pred = next(e for t in reco.tiers.values() for e in t if e["name"] == "Predatory-X")
    check(pred.get("risk_warnings") and "软风险只 warn" in pred["because"],
          "软预警 → 保留候选 + warn（不自动误判掠夺）")
    # OffScope-Y → excluded（方向=低致命短板）
    check(any(e["name"] == "OffScope-Y" and e["reason"] == "scope_or_method_not_met"
              for e in reco.excluded), "方向=低 → excluded(scope 不达标)")

    # 决策点恒真、chosen 恒空（绝不替用户选 / 自动投）
    check(reco.decision_point is True and reco.chosen is None,
          "decision_point=True 且 chosen=None（绝不自动选 venue/自动投）")
    d = json.loads(reco.to_json())
    check(d["chosen"] is None and d["decision_point"] is True, "JSON 序列化保留决策点契约")
    check("绝不替用户选" in d["note"], "note 明示绝不替用户选 venue")

    # 每条推荐带 because（无裸结论）
    all_entries = [e for t in reco.tiers.values() for e in t] + reco.excluded
    check(all(e.get("because") for e in all_entries), "每条候选都带 because(可解释,无裸结论)")

    # 禁编概率：未给官方接收率的候选，render 标"待核查(禁编概率)"，不出现伪百分比
    md = render(reco)
    check("禁编概率" in md and "决策点" in md, "render 标禁编概率 + 决策点")

    # 档内排序：budget_sensitive 时 APC 低者优先（保底档只 1 个，构造稳妥档 2 个验证）
    cands2 = [
        {"name": "Hi-APC", "venue_tier": "中科院2区", "direction_fit": "高",
         "author_strength": "中", "method_scale": "达标", "review_weeks": 8, "apc_usd": 3000},
        {"name": "Lo-APC", "venue_tier": "中科院2区", "direction_fit": "高",
         "author_strength": "中", "method_scale": "达标", "review_weeks": 12, "apc_usd": 500},
    ]
    reco2 = rank({"novelty": "significant", "author_strength": "中", "budget_sensitive": True}, cands2)
    wen = reco2.tiers["稳妥"]
    check(len(wen) == 2 and wen[0]["name"] == "Lo-APC",
          "budget_sensitive → 稳妥档低 APC 者排前(转投顺序 APC↑)")

    # 空候选不崩
    reco3 = rank({}, [])
    check(reco3.paper_strength == "unknown" and not reco3.excluded, "空候选 → 不崩、成色 unknown")

    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def _load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="冲刺/稳妥/保底 分层推荐 + 决策点（绝不替用户选 venue/自动投）")
    ap.add_argument("--manuscript", help="稿件画像 JSON（novelty/author_strength/method_scale/预算·deadline 敏感）")
    ap.add_argument("--candidates", help="候选 venue 列表 JSON（每个带 venue_signal 信号或最小字段）")
    ap.add_argument("--out", help="把分层推荐工件 JSON 写到文件（默认 stdout md）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON（默认人读 md）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not args.candidates:
        ap.error("需要 --candidates FILE（或 --selftest）")

    ms = _load_json(args.manuscript) if args.manuscript else {}
    cands = _load_json(args.candidates)
    if not isinstance(cands, list):
        ap.error("--candidates 必须是 JSON 数组")
    reco = rank(ms, cands)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(reco.to_json())
        print(f"Wrote {args.out}", file=sys.stderr)
    if args.json and not args.out:
        print(reco.to_json())
    else:
        print(render(reco))
    return 0


if __name__ == "__main__":
    sys.exit(main())
