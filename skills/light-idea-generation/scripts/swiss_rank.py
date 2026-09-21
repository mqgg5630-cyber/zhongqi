# -*- coding: utf-8 -*-
"""swiss_rank.py — 瑞士轮/ELO 配对比较排序（Light idea-generation，灭审查病4：自报绝对分）。

为什么
------
审查病4：idea-generation rank_ideas 此前用 LLM 自报的绝对分(impact/novelty 1-5)做主排序键。
Si et al. 2024(arXiv 2409.04109)证 LLM 自评分与人类一致性仅 ~53%；SciMuse/co-scientist
等多方研究验证**配对比较(pairwise)远优于绝对自评分**。本脚本把排序主键换成由
两两配对裁判累积的 ELO 分。

机制
----
- 瑞士轮配对：每轮按当前 ELO 邻近配对(强碰强)，避免全配对的 O(n²) 开销。
- 配对裁判可注入：set_judge(fn)，fn(a, b)->'A'|'B'|'tie'。裁判 prompt 模板
  JUDGE_PROMPT 强制要求引用双方"最近邻文献"做 grounding(撞车/差异)，而非空谈。
- 无裁判(离线)时：用候选自带的 prior 分或固定胜负矩阵兜底，保证 selftest 可跑。
- ELO 更新标准公式(K=32)，输出排序 + 每条的 elo/wins/losses 留痕。

被谁消费
--------
rank_ideas.py 把 ELO 分作为 lane 内主排序键（替换/加权自报分）。

纯 stdlib。`python swiss_rank.py --selftest` 自测(验 ELO 收敛 + 传递性)。
"""

from __future__ import annotations
import argparse
import json
import math
import sys

_JUDGE = None  # callable(a:dict, b:dict) -> 'A' | 'B' | 'tie'

JUDGE_PROMPT = (
    "You are judging which research idea is more worth pursuing. "
    "Cite each idea's nearest-neighbor papers to ground your call on novelty "
    "(collision vs genuine gap) and feasibility — do NOT rate in the abstract.\n\n"
    "IDEA A: {a_text}\nA nearest papers: {a_neighbors}\n\n"
    "IDEA B: {b_text}\nB nearest papers: {b_neighbors}\n\n"
    "Reply with exactly one token: A, B, or tie."
)


def set_judge(fn):
    """注入配对裁判函数: (a_dict, b_dict) -> 'A'|'B'|'tie'。"""
    global _JUDGE
    _JUDGE = fn


def _expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _update_elo(ra, rb, score_a, k=32):
    """score_a: 1=A胜 0=A负 0.5=平。返回 (ra', rb')。"""
    ea = _expected(ra, rb)
    ra2 = ra + k * (score_a - ea)
    rb2 = rb + k * ((1 - score_a) - (1 - ea))
    return ra2, rb2


def _swiss_pairings(order):
    """瑞士轮：按当前排名相邻配对。order 是按 elo 降序的索引列表。"""
    pairs = []
    for i in range(0, len(order) - 1, 2):
        pairs.append((order[i], order[i + 1]))
    return pairs


def _default_judge(a, b):
    """离线兜底裁判：比较候选自带的 prior 分(prior/score/impact 任一)。无则平。"""

    def _p(x):
        for k in ("prior", "score", "impact", "_prior"):
            if isinstance(x.get(k), (int, float)):
                return float(x[k])
        return 0.0

    pa, pb = _p(a), _p(b)
    if pa > pb:
        return "A"
    if pb > pa:
        return "B"
    return "tie"


def swiss_rank(candidates, rounds=None, k=32, judge=None):
    """对候选做瑞士轮 ELO 排序。

    candidates: [{id?, text/title, neighbors?, prior?}]
    rounds: 轮数(默认 ceil(log2 n)+2，够区分)。
    judge: 配对裁判，缺省用注入的 _JUDGE，再缺省用 _default_judge(离线)。
    返回排序后的列表(降序)，每条加 elo/wins/losses/ties/_rank。
    """
    j = judge or _JUDGE or _default_judge
    n = len(candidates)
    state = []
    for i, c in enumerate(candidates):
        state.append(
            {"i": i, "elo": 1500.0, "wins": 0, "losses": 0, "ties": 0, "cand": c}
        )
    if n < 2:
        for s in state:
            s["cand"] = dict(s["cand"], elo=s["elo"], wins=0, losses=0, ties=0, _rank=1)
        return [s["cand"] for s in state]
    if rounds is None:
        rounds = max(3, math.ceil(math.log2(n)) + 2)

    for _ in range(rounds):
        order = [s["i"] for s in sorted(state, key=lambda s: -s["elo"])]
        for ia, ib in _swiss_pairings(order):
            sa = next(s for s in state if s["i"] == ia)
            sb = next(s for s in state if s["i"] == ib)
            verdict = j(sa["cand"], sb["cand"])
            if verdict == "A":
                score_a = 1.0
                sa["wins"] += 1
                sb["losses"] += 1
            elif verdict == "B":
                score_a = 0.0
                sb["wins"] += 1
                sa["losses"] += 1
            else:
                score_a = 0.5
                sa["ties"] += 1
                sb["ties"] += 1
            sa["elo"], sb["elo"] = _update_elo(sa["elo"], sb["elo"], score_a, k)

    ranked = sorted(state, key=lambda s: -s["elo"])
    out = []
    for rank, s in enumerate(ranked, 1):
        out.append(
            dict(
                s["cand"],
                elo=round(s["elo"], 1),
                wins=s["wins"],
                losses=s["losses"],
                ties=s["ties"],
                _rank=rank,
            )
        )
    return out


# ──────────────────────────── selftest ────────────────────────────
def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")

    print("swiss_rank selftest")

    # 1. 固定真实强弱(prior)→ ELO 应收敛到与 prior 同序(传递性)
    cands = [{"id": f"c{i}", "text": f"idea {i}", "prior": i} for i in range(8)]
    # 打乱输入顺序，确保排序靠 ELO 而非输入序
    shuffled = [
        cands[3],
        cands[7],
        cands[0],
        cands[5],
        cands[1],
        cands[6],
        cands[2],
        cands[4],
    ]
    ranked = swiss_rank(shuffled, rounds=12)
    priors_in_rank_order = [c["prior"] for c in ranked]
    check(priors_in_rank_order[0] == 7, "最强(prior=7)排第1")
    check(priors_in_rank_order[-1] == 0, "最弱(prior=0)排末位")
    # 单调性(传递性)：排名序的 prior 应大致降序(允许相邻偶发，但首尾必对)
    inversions = sum(
        1
        for i in range(len(priors_in_rank_order) - 1)
        if priors_in_rank_order[i] < priors_in_rank_order[i + 1]
    )
    check(inversions <= 1, f"ELO 排序与真实强弱基本一致(逆序对={inversions}<=1)")

    # 2. ELO 分有区分度(最强 > 最弱)
    check(ranked[0]["elo"] > ranked[-1]["elo"], "最强 ELO > 最弱 ELO")

    # 3. 注入裁判生效：自定义"偏好 text 含 'good'"
    def my_judge(a, b):
        ga = "good" in a.get("text", "")
        gb = "good" in b.get("text", "")
        return "A" if ga and not gb else ("B" if gb and not ga else "tie")

    set_judge(my_judge)
    c2 = [
        {"id": "x", "text": "bad idea"},
        {"id": "y", "text": "good idea"},
        {"id": "z", "text": "bad idea"},
        {"id": "w", "text": "good idea"},
    ]
    r2 = swiss_rank(c2, rounds=6)
    set_judge(None)
    check("good" in r2[0]["text"], "注入裁判：good 候选排前")

    # 4. 边界：单候选不崩
    r1 = swiss_rank([{"id": "solo", "text": "only"}])
    check(len(r1) == 1 and r1[0]["_rank"] == 1, "单候选返回 rank=1")

    # 5. ELO 更新公式正确性(胜者加分)
    ra, rb = _update_elo(1500, 1500, 1.0)
    check(ra > 1500 > rb and abs((ra - 1500) - 16) < 0.01, "等分对局胜者+16(K=32)")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="瑞士轮/ELO 配对比较排序(替代自报绝对分)")
    ap.add_argument(
        "candidates", nargs="?", help="candidates.json([{id,text,prior?,neighbors?}])"
    )
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    if not a.candidates:
        print(__doc__)
        print(
            "用法: python swiss_rank.py candidates.json [--rounds N] [--out ranked.json]"
        )
        print("（无注入裁判时用候选自带 prior 分离线兜底排序）")
        return
    cands = json.load(open(a.candidates, encoding="utf-8"))
    if isinstance(cands, dict):
        cands = cands.get("candidates", cands.get("ideas", []))
    ranked = swiss_rank(cands, rounds=a.rounds)
    out = a.out or "ranked_elo.json"
    json.dump(
        {"schema": "light.swiss_rank.v1", "ranked": ranked},
        open(out, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=2,
    )
    print(
        f"wrote {out}  (top: {ranked[0].get('text', '?')[:50]} elo={ranked[0]['elo']})"
    )


if __name__ == "__main__":
    main()
