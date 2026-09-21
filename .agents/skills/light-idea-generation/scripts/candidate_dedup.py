#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate_dedup.py — 候选 idea 去重/伪多样性检测（接 _shared/semantic_sim，相似阈值算法化）。

防伪多样性是 idea-generation 的硬需求：Si et al(arXiv 2409.04109)实测 LLM 扩规模后"新 idea 多是
重复/极相似"，换皮凑数的伪多样会骗过浅检。本脚本把"显著高于其余对视为变体"**算法化**：
  - 默认档：复用 `_shared/semantic_sim`（字符 3-gram 余弦 + 词干 Jaccard + 语序惩罚，识别倒装、
    中文按字 bigram）算两两相似矩阵——比 v1 裸 difflib 强；_shared 不可达时降级 difflib 兜底。
  - 自动阈值：批内所有对的相似度算 mean+1σ，**高于此线的对标"疑似变体"**（相对差非拍脑袋绝对值）。
  - embedding 升级：调用方传入 embedding（--emb embeddings.json，{id: [向量]}）则改用余弦，
    口径与 literature-search 的 SPECTER2 语义嵌入一致。

诚实：离线 semantic_sim 仍是**字面/词形**匹配，抓不到纯同义（"换标题的同义 idea"需 embedding 档）；
跨语言弱（中文 idea↔英文标题低分）。标"疑似变体"是提示人工合并，不自动删。

用法：
  python candidate_dedup.py --in candidates.json
  python candidate_dedup.py --in candidates.json --emb emb.json   # SPECTER2 升级
  python candidate_dedup.py --selftest
"""
from __future__ import annotations
import argparse
import difflib
import json
import math
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 规范 bootstrap（_shared/README.md）：向上走目录树找仓库根，复用共享语义相似度引擎。
import pathlib
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared import semantic_sim as _semsim   # noqa: E402
    _SEMSIM_OK = True
except ImportError:          # _shared 不可达：降级 difflib 文本相似度
    _semsim = None
    _SEMSIM_OK = False


def _text(it: dict) -> str:
    return f"{it.get('title','')} {it.get('claim','') or it.get('novelty','')}".strip()


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+|[一-鿿]", (s or "").lower()))


def text_sim(a: str, b: str) -> float:
    """文本相似度：字符级 SequenceMatcher 与 词级 Jaccard 取均值（零依赖）。"""
    seq = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    ta, tb = _tokens(a), _tokens(b)
    jac = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    return round((seq + jac) / 2, 4)


def _sim_text(a: str, b: str) -> float:
    """文本相似度分派：优先 _shared/semantic_sim（更强，识别倒装/中文/词干），不可达降级 difflib。"""
    if _SEMSIM_OK:
        return round(_semsim.similarity(a, b), 4)
    return text_sim(a, b)


def cosine(u: list, v: list) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return round(dot / (nu * nv), 4) if nu and nv else 0.0


def dedup(items: list, embeddings: dict | None = None) -> dict:
    """两两相似 + mean+1σ 自动标变体。embeddings 给了则用余弦(SPECTER2 口径)，否则文本相似度。"""
    n = len(items)
    ids = [it.get("id", f"#{i}") for i, it in enumerate(items)]
    mode = ("specter2-cosine" if embeddings
            else ("semantic_sim-offline" if _SEMSIM_OK else "text-similarity(difflib降级)"))
    pairs = []
    sims = []
    for i in range(n):
        for j in range(i + 1, n):
            if embeddings and ids[i] in embeddings and ids[j] in embeddings:
                s = cosine(embeddings[ids[i]], embeddings[ids[j]])
            else:
                s = _sim_text(_text(items[i]), _text(items[j]))
            pairs.append({"a": ids[i], "b": ids[j], "sim": s})
            sims.append(s)
    # 自动阈值 mean+1σ（相对差，非绝对拍脑袋）
    if sims:
        mean = sum(sims) / len(sims)
        var = sum((x - mean) ** 2 for x in sims) / len(sims)
        std = math.sqrt(var)
        threshold = round(mean + std, 4)
    else:
        mean = std = threshold = 0.0
    variants = [p for p in pairs if p["sim"] >= threshold and p["sim"] > 0]
    variants.sort(key=lambda p: -p["sim"])
    _NOTES = {
        "specter2-cosine": "SPECTER2 余弦，与 literature-search 语义嵌入口径一致。",
        "semantic_sim-offline": "_shared/semantic_sim 离线档(字符3gram余弦+词干Jaccard+语序惩罚，"
                                "识别倒装/中文按字)；仍是字面/词形匹配，纯同义/跨语言需 embedding 档。",
        "text-similarity(difflib降级)": "_shared 不可达，降级 difflib：只抓换皮措辞、漏语义变体，"
                                        "高要求传 --emb 或修复 _shared。",
    }
    return {
        "n": n, "mode": mode, "n_pairs": len(pairs),
        "mean_sim": round(mean, 4), "std_sim": round(std, 4), "threshold": threshold,
        "suspected_variants": variants,
        "note": _NOTES[mode] + " 标'疑似变体'是提示人工合并，不自动删。阈值=批内 mean+1σ（相对差）。",
    }


def render(res: dict) -> str:
    lines = [f"# 候选 idea 去重/伪多样性检测（{res['mode']}）", "",
             f"- {res['n']} 条候选，{res['n_pairs']} 对；相似度 mean={res['mean_sim']} "
             f"std={res['std_sim']}，自动阈值(mean+1σ)={res['threshold']}", ""]
    if res["suspected_variants"]:
        lines.append("**疑似变体对（建议人工合并/分化，按相似度降序）：**")
        for p in res["suspected_variants"]:
            lines.append(f"- {p['a']} ↔ {p['b']}：相似度 {p['sim']} ≥ 阈值")
    else:
        lines.append("无显著高于均值的相似对——候选多样性 OK。")
    lines += ["", f"> {res['note']}"]
    return "\n".join(lines)


def _selftest() -> int:
    print("### candidate_dedup 离线自测", file=sys.stderr)
    items = [
        {"id": "I-01", "title": "时序对比学习做奶山羊发情识别", "claim": "自监督时序对比学习"},
        {"id": "I-02", "title": "用对比学习做奶山羊发情行为识别", "claim": "对比学习自监督时序"},  # 与 I-01 几乎换皮
        {"id": "I-03", "title": "图神经网络做蛋白质结构预测", "claim": "GNN 折叠"},            # 完全不同
    ]
    res = dedup(items)
    assert res["mode"] in ("semantic_sim-offline", "text-similarity(difflib降级)"), res
    # I-01↔I-02 应是疑似变体（换皮）
    var_pairs = {(p["a"], p["b"]) for p in res["suspected_variants"]}
    assert ("I-01", "I-02") in var_pairs, res["suspected_variants"]
    # I-03 与谁都不该高相似
    assert not any("I-03" in (p["a"], p["b"]) for p in res["suspected_variants"]), res

    # SPECTER2 升级路径：传 embedding 用余弦
    emb = {"I-01": [1.0, 0.0], "I-02": [0.99, 0.01], "I-03": [0.0, 1.0]}
    res2 = dedup(items, embeddings=emb)
    assert res2["mode"] == "specter2-cosine", res2
    assert ("I-01", "I-02") in {(p["a"], p["b"]) for p in res2["suspected_variants"]}, res2

    # 文本相似度对称、自相似=1
    assert text_sim("abc", "abc") == 1.0
    assert text_sim("abc def", "def abc") > 0  # 词 Jaccard 命中
    # 渲染
    md = render(res)
    assert "疑似变体" in md and "mean+1σ" in md, md
    # 单条不崩（无对）
    assert dedup([{"id": "x", "title": "only one"}])["n_pairs"] == 0
    print("[selftest] PASS candidate_dedup offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="候选 idea 去重/伪多样性检测")
    ap.add_argument("--in", dest="infile", help="候选 JSON 数组")
    ap.add_argument("--emb", help="可选 SPECTER2 embedding JSON {id: [向量]}")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or not args.infile:
        return _selftest()
    with open(args.infile, encoding="utf-8") as f:
        items = json.load(f)
    emb = None
    if args.emb:
        with open(args.emb, encoding="utf-8") as f:
            emb = json.load(f)
    res = dedup(items, emb)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
