#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novelty_density.py — 嵌入密度新颖性先验（域无关，借 RND 相对邻域密度）。

为什么有这个脚本（补 m04 最硬的名实落差）
------------------------------------------------
idea-critique 的 headline 是"查新"，但此前"新不新"全靠 agent 手判 + novelty_audit.py
对人填的 JSON 做自洽性勾稽——**没有任何可复算、独立于 LLM 自评的新颖度数值**。竞品
RND（相对邻域密度，跨域 AUROC 0.782）/ GraphMind（论文图谱，0.75 F1）都给得出 0-100 的
可复算新颖分。本脚本补上这个独立数字，专抓 PRISM 实测的 LLM 审稿"过度背书"病：
**"LLM 嘴上说创新性 85，但 idea 其实落在密集语义簇里（密度百分位 20）"** 这种矛盾。

RND 核心思想（域无关 = 关键）
-----------------------------
新颖性 = 一个点相对其**局部邻域自身密度**有多孤立。之所以域无关：稠密领域里所有工作都
彼此靠近，但参考分布也整体偏密，百分位归一化后仍能分辨"比邻居更孤立 / 更扎堆"。

算法（消费 m01 已检索的最近邻论文集的嵌入）：
  1. 输入 idea 嵌入 + n 个最近邻论文嵌入 E（m01 literature-search 本就拉 OpenAlex/S2 带摘要）
  2. 对 idea 算 k-NN 平均余弦**距离** d_k(idea)（对 E 求；距离越大 = 越孤立）
  3. 参考分布 = 每个邻居自身的 k-NN 平均距离 d_k(e_i)（leave-one-out，对 E\{e_i} 求）
  4. novelty_prior = d_k(idea) 在参考分布中的**百分位** × 100（0-100，域无关新颖分）
     - idea 比多数邻居更孤立 → 高百分位 → 高新颖
     - idea 扎在密集簇里（比邻居更挤）→ 低百分位 → 低新颖

把这个 novelty_prior 传 score_aggregate.decide(novelty_prior=N)：当 LLM 创新性≥75 但
N≤30，触发 NOVELTY-PRIOR-CONFLICT 红旗、创新性维度封顶——给"查新"一个 LLM 自评之外的交叉校验。

诚实边界
--------
- 这是**先验/交叉校验信号，不是新颖性判定的真值**。它只反映"idea 在已检索到的邻居集合里
  几何上多孤立"——若 m01 检索覆盖不全（漏了最像的那篇），密度会高估新颖性。GIGO 同 novelty_audit。
- 最佳输入是真句向量嵌入（m01 口径：对 idea 摘要与邻居摘要用同一句向量模型）。无嵌入只有
  文本时降级用 _shared/semantic_sim（离线档为字符 n-gram，**远弱于嵌入**，仅供管线连通/自测，
  真用须传嵌入）——降级路径显式标注 mode，绝不假装等同嵌入。

用法：
  python novelty_density.py --embeddings nbr.json     # {"idea":[...], "neighbors":[[...],...]}
  python novelty_density.py --texts texts.json        # {"idea":"...", "neighbors":["...",...]}（降级）
  python novelty_density.py --selftest                # 离线合成嵌入自测
"""
from __future__ import annotations
import argparse
import json
import math
import pathlib
import sys

# 降级路径用共享语义相似度（无真嵌入、只有文本时）。规范 bootstrap（_shared/README.md）：
# 向上走目录树找含 _shared 包的仓库根，治 v1 硬编码 ../../_shared 在 v2（_shared 在仓库根、
# 与 skills/ 平级，嵌套深度变了）必断之脆，三 harness/全局安装/任意嵌套都可靠。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared.semantic_sim import similarity as _sem_sim  # noqa: E402
    _HAS_SEM = True
except ImportError:
    _HAS_SEM = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_K = 10


def _cosine_distance(a: list, b: list) -> float:
    """余弦距离 = 1 - 余弦相似度。范围 [0,2]，归一化向量上落 [0,1] 居多。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


def _knn_mean_dist(dists: list, k: int) -> float:
    """给定一个点到其它点的距离列表，取最近 k 个的平均（k-NN 密度，越大越孤立）。"""
    if not dists:
        return 0.0
    kk = min(k, len(dists))
    nearest = sorted(dists)[:kk]
    return sum(nearest) / len(nearest)


def _density_from_distfn(point_idx, points, distfn, k):
    """点 point_idx 到 points 里其它点（leave-one-out）的 k-NN 平均距离。"""
    dists = [distfn(point_idx, j) for j in range(len(points)) if j != point_idx]
    return _knn_mean_dist(dists, k)


def novelty_prior_from_embeddings(idea_vec: list, neighbor_vecs: list,
                                  k: int = DEFAULT_K) -> dict:
    """RND 相对邻域密度：返回 idea 的域无关新颖分 0-100 + 留痕。

    idea_vec: idea 的嵌入向量
    neighbor_vecs: n 个最近邻论文的嵌入向量（m01 供）
    k: k-NN 的 k（默认 10；邻居不足时自动取 n-1 / n）
    """
    n = len(neighbor_vecs)
    if n == 0:
        return {"novelty_prior": None, "mode": "embedding", "n_neighbors": 0, "k": k,
                "note": "无最近邻嵌入——无法算密度新颖分（先让 m01 检索出最近邻论文集）。"}
    if n == 1:
        # 只有一个邻居：用单点距离的相对位置无意义，给个粗判（越远越新）但标低置信
        d = _cosine_distance(idea_vec, neighbor_vecs[0])
        return {"novelty_prior": round(min(100.0, d * 100), 2), "mode": "embedding",
                "n_neighbors": 1, "k": 1, "idea_density": round(d, 4),
                "low_confidence": True,
                "note": "仅 1 个邻居，无参考分布，新颖分=与该邻居的余弦距离×100，置信低。"}

    keff = max(1, min(k, n - 1))
    # idea 对全体邻居的 k-NN 密度
    idea_dists = [_cosine_distance(idea_vec, e) for e in neighbor_vecs]
    idea_density = _knn_mean_dist(idea_dists, keff)

    # 参考分布：每个邻居对其余邻居（leave-one-out）的 k-NN 密度
    def _nbr_distfn(i, j):
        return _cosine_distance(neighbor_vecs[i], neighbor_vecs[j])
    ref_densities = [_density_from_distfn(i, neighbor_vecs, _nbr_distfn, keff)
                     for i in range(n)]

    # 百分位：参考分布里 d_k <= idea_density 的占比 ×100（idea 越孤立→越高）
    le = sum(1 for r in ref_densities if r <= idea_density)
    percentile = round(100.0 * le / len(ref_densities), 2)

    return {
        "novelty_prior": percentile,
        "mode": "embedding",
        "n_neighbors": n,
        "k": keff,
        "idea_density": round(idea_density, 4),
        "ref_density_median": round(sorted(ref_densities)[len(ref_densities) // 2], 4),
        "ref_density_min": round(min(ref_densities), 4),
        "ref_density_max": round(max(ref_densities), 4),
        "interpretation": _interpret(percentile),
        "note": ("域无关新颖分：idea 的 k-NN 密度在邻居自身密度分布中的百分位。"
                 "高=比多数邻居更孤立(新)，低=扎在密集簇里(可能过度背书)。"
                 "GIGO：m01 检索漏掉最像的那篇会高估。"),
    }


def novelty_prior_from_texts(idea_text: str, neighbor_texts: list,
                             k: int = DEFAULT_K) -> dict:
    """文本降级路径：无真嵌入时用 _shared/semantic_sim 把相似度转距离(1-sim)算密度。

    ⚠ 离线档 semantic_sim 是字符 n-gram，远弱于句向量，仅供管线连通/自测。真用传嵌入。
    """
    if not _HAS_SEM:
        return {"novelty_prior": None, "mode": "text-degraded-unavailable",
                "note": "_shared/semantic_sim 不可用，且未传嵌入——无法算密度新颖分。"}
    n = len(neighbor_texts)
    if n == 0:
        return {"novelty_prior": None, "mode": "text-degraded", "n_neighbors": 0,
                "note": "无最近邻文本——无法算密度新颖分。"}
    # 用相似度→距离构造，复用嵌入版逻辑但 distfn 走 semantic_sim
    all_texts = [idea_text] + list(neighbor_texts)

    def _dist(a_idx, b_idx):
        return 1.0 - _sem_sim(all_texts[a_idx], all_texts[b_idx])

    keff = max(1, min(k, n - 1)) if n >= 2 else 1
    if n == 1:
        d = _dist(0, 1)
        return {"novelty_prior": round(min(100.0, d * 100), 2), "mode": "text-degraded",
                "n_neighbors": 1, "low_confidence": True,
                "note": "仅 1 个邻居 + 文本降级档(非嵌入)，置信很低。"}

    idea_dists = [_dist(0, j) for j in range(1, n + 1)]
    idea_density = _knn_mean_dist(idea_dists, keff)
    ref_densities = []
    for i in range(1, n + 1):
        dists = [_dist(i, j) for j in range(1, n + 1) if j != i]
        ref_densities.append(_knn_mean_dist(dists, keff))
    le = sum(1 for r in ref_densities if r <= idea_density)
    percentile = round(100.0 * le / len(ref_densities), 2)
    return {
        "novelty_prior": percentile,
        "mode": "text-degraded",
        "n_neighbors": n,
        "k": keff,
        "idea_density": round(idea_density, 4),
        "interpretation": _interpret(percentile),
        "note": ("⚠ 文本降级档(semantic_sim 离线档=字符 n-gram，非句向量)：仅供管线连通，"
                 "新颖分不可当嵌入版数值用，真用须按 m01 口径传句向量嵌入。"),
    }


def _interpret(percentile: float) -> str:
    if percentile is None:
        return "unknown"
    if percentile >= 70:
        return "高新颖先验(语义上比多数邻居孤立)"
    if percentile >= 45:
        return "中等新颖先验(与邻域密度相当)"
    if percentile >= 30:
        return "偏低新颖先验(略扎堆)"
    return "低新颖先验(落在密集语义簇——警惕 LLM 过度背书)"


def _selftest() -> int:
    print("### novelty_density 离线自测（合成嵌入）", file=sys.stderr)

    def ang(deg):
        r = math.radians(deg)
        return [math.cos(r), math.sin(r)]

    # 邻居集合：10 个大致 30° 散开的点（180~210 留空形成稀疏弧）+ 4 个挤在 30° 附近的密集簇
    spread = [ang(d) for d in (30, 60, 90, 120, 150, 240, 270, 300, 330, 0)]
    pocket = [ang(d) for d in (30.5, 31.0, 31.5, 32.0)]
    neighbors = spread + pocket

    # 1) 新颖 idea：落在 180~240 的稀疏空隙（195°），离所有邻居都远 → 高百分位
    novel = ang(195)
    rn = novelty_prior_from_embeddings(novel, neighbors, k=3)
    print(f"[A] novel  idea: prior={rn['novelty_prior']} dens={rn['idea_density']} "
          f"ref_med={rn['ref_density_median']} -> {rn['interpretation']}", file=sys.stderr)

    # 2) 扎堆 idea：落在密集簇里（31.2°），k-NN 密度极小 → 低百分位
    crowded = ang(31.2)
    rc = novelty_prior_from_embeddings(crowded, neighbors, k=3)
    print(f"[B] crowd  idea: prior={rc['novelty_prior']} dens={rc['idea_density']} "
          f"ref_med={rc['ref_density_median']} -> {rc['interpretation']}", file=sys.stderr)

    # 核心不变量：新颖 idea 新颖分 > 扎堆 idea，且分别落在高/低带
    assert rn["novelty_prior"] > rc["novelty_prior"], (rn["novelty_prior"], rc["novelty_prior"])
    assert rn["novelty_prior"] >= 60, rn["novelty_prior"]
    assert rc["novelty_prior"] <= 40, rc["novelty_prior"]
    print("[1] novel > crowded 且分居高/低带 ... OK", file=sys.stderr)

    # 3) 边界：0 邻居 → None 不崩
    r0 = novelty_prior_from_embeddings(novel, [], k=3)
    assert r0["novelty_prior"] is None and r0["n_neighbors"] == 0, r0
    print("[2] 0 邻居降级 None ... OK", file=sys.stderr)

    # 4) 边界：1 邻居 → 低置信但给值
    r1 = novelty_prior_from_embeddings(novel, [ang(10)], k=3)
    assert r1["novelty_prior"] is not None and r1.get("low_confidence"), r1
    print("[3] 1 邻居低置信 ... OK", file=sys.stderr)

    # 5) k 大于邻居数 → 自动收敛不崩
    rk = novelty_prior_from_embeddings(novel, neighbors, k=999)
    assert rk["k"] == len(neighbors) - 1, rk["k"]
    print("[4] k 超邻居数自动收敛 ... OK", file=sys.stderr)

    # 6) 文本降级路径可用（若 semantic_sim 在）：扎堆文本 < 孤立文本
    if _HAS_SEM:
        nbr_texts = ["deep learning for image classification",
                     "convolutional networks for image recognition",
                     "image classification with neural nets",
                     "a study of quantum error correction codes",
                     "topological quantum computing architectures"]
        rt_crowd = novelty_prior_from_texts("image classification using deep neural networks",
                                            nbr_texts, k=2)
        rt_novel = novelty_prior_from_texts("ethnographic study of medieval trade routes",
                                            nbr_texts, k=2)
        print(f"[C] text crowd={rt_crowd['novelty_prior']} novel={rt_novel['novelty_prior']}",
              file=sys.stderr)
        assert rt_novel["novelty_prior"] >= rt_crowd["novelty_prior"], (rt_novel, rt_crowd)
        assert rt_crowd["mode"] == "text-degraded", rt_crowd
        print("[5] 文本降级档 novel>=crowd 且标 degraded ... OK", file=sys.stderr)
    else:
        print("[5] semantic_sim 不可用，跳过文本降级测试（已诚实标注）", file=sys.stderr)

    print("[selftest] PASS novelty_density offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="嵌入密度新颖性先验(RND 相对邻域密度)")
    ap.add_argument("--embeddings", help='JSON: {"idea":[...], "neighbors":[[...],...]}')
    ap.add_argument("--texts", help='JSON: {"idea":"...", "neighbors":["...",...]}（降级档）')
    ap.add_argument("--k", type=int, default=DEFAULT_K, help="k-NN 的 k（默认 10）")
    ap.add_argument("--selftest", action="store_true", help="离线合成嵌入自测")
    args = ap.parse_args()

    if args.selftest or (not args.embeddings and not args.texts):
        return _selftest()
    if args.embeddings:
        with open(args.embeddings, encoding="utf-8") as f:
            d = json.load(f)
        rep = novelty_prior_from_embeddings(d["idea"], d.get("neighbors", []), k=args.k)
    else:
        with open(args.texts, encoding="utf-8") as f:
            d = json.load(f)
        rep = novelty_prior_from_texts(d["idea"], d.get("neighbors", []), k=args.k)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
