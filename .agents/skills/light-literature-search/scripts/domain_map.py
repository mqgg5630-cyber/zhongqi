#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""domain_map.py — 三层领域地图编排器 + 撞车/覆盖度 findings producer（Light v2 · 本技能灵魂）。

蓝图 §6 的"及格线":文献调研产出**不是论文列表,是可直接喂 idea 的领域地图**。本脚本把 v1 的散件
（search_normalize 的相关度/时效重排 + 经典豁免、cross_domain_search 的正交双轴）**组装成"三层分别检索
分别排序"的编排器**,再产**机读 findings**(撞车信号 + 覆盖度)接 _shared,被总控 run_checkpoint 聚合。

三层（分别检索、分别排序——不是一锅 relevance）：
  ① frontier  近三年前沿：sn.run(recency_boost) 相关度×时效重排,近期相关文上浮(领域动得快)。
  ② classic   经典奠基作：sn.run(sort_by=cited) 被引降序,不受时间限(不懂来路提不出好 idea)。
  ③ cross     跨领域方法移植：cross_domain_search 应用轴×方法轴正交(给 --method 启用;最好的创新常是
              别领域方法搬来)。不给方法轴则诚实跳过并提示。

领域地图三件套（结构化槽位 + 确定性脚手架；深度叙事由宿主 LLM 据证据填——脚本不臆造）：
  研究脉络(lineage)：按年份时间线 + 年均被引角色启发式判级。
  方法谱系(genealogy)：文献耦合(共享 referenced_works,OpenAlex 零额外 API)聚"学派"候选簇。
  未解问题(open_problems)：摘要 gap 短语启发式扫 + 前沿稀疏信号。

findings（接 _shared，warn 为主——critical 撞车判决归 idea-critique，本技能只产信号）：
  search_coverage：覆盖哪些源 / 失败源 / unknown 计数 / 召回 caveat。
  idea_collision ：给 --idea 时,semantic_sim 找最像的前作 + facet 槽位(purpose/mechanism/evaluation/
                  application_domain)留给 idea-critique 与宿主 LLM 拆 delta。

诚实约定（v2 纪律见 SKILL.md「名实对齐」与 _shared/README.md）：
- 不臆造 DOI/被引/可迁移性/新颖性判决；查不到写 unknown;facet delta 与 novel 判决不自做(归 idea-critique)。
- 无网络时各层走 search_normalize 的 [OFFLINE] 合成样本,管线仍可验证并打印 [OFFLINE]。
- 文献耦合仅对带 referenced_works 的 OpenAlex 记录有效;缺则该簇诚实标 unknown,不假装聚成。

用法：
  python domain_map.py "dairy goat behaviour recognition" --current-year 2026
  python domain_map.py "lameness detection in sheep" --method "vision transformer" --current-year 2026
  python domain_map.py "goat behaviour" --idea "用加速度计做奶山羊发情行为识别" --report findings.json
  python domain_map.py --selftest
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 同目录兄弟脚本（复用不重造：sn 三源检索+重排，cd 跨领域正交双轴）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import search_normalize as sn          # noqa: E402
import cross_domain_search as cd       # noqa: E402

# 规范 bootstrap（_shared/README.md）：向上走目录树找仓库根，治硬编码 parents[N] 之脆。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared import semantic_sim as _semsim          # noqa: E402
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates             # noqa: E402
    _SHARED_OK = True
except ImportError:                                       # _shared 不可达：findings 降级
    _semsim = None
    _SHARED_OK = False

# gap 信号短语（中英）：摘要含这些 → 候选未解问题/局限,启发式非定论。
_GAP_PHRASES = [
    "future work", "remains", "remain ", "open question", "open problem",
    "unexplored", "lack of", "challenge", "limitation", "not been",
    "further research", "yet to", "未解决", "有待", "尚未", "缺乏", "亟需", "难以",
]


# ───────────────────────── 工具 ─────────────────────────
def _annual_citations(rec: dict, current_year: int) -> float:
    cb = rec.get("cited_by") or 0
    yr = rec.get("year") or current_year
    return round(cb / max(1, current_year - (yr or current_year) + 1), 1)


def _role_hint(rec: dict, current_year: int) -> str:
    """年龄×被引启发式判级（领域差异大，标'启发式'非硬证据）。"""
    yr = rec.get("year")
    cb = rec.get("cited_by")
    if yr is None or cb is None:
        return "unknown(年份/被引缺失)"
    age = current_year - yr
    ann = _annual_citations(rec, current_year)
    if age >= 8 and ann >= 30:
        return "foundational(奠基-启发式)"
    if 3 <= age < 8 and ann >= 15:
        return "milestone(里程碑-启发式)"
    if age <= 3:
        return "frontier/sota(新锐-启发式)"
    if ann < 1:
        return "long-tail(长尾存疑-启发式)"
    return "regular(常规-启发式)"


def _uniq_by_key(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        k = sn._norm_doi(r.get("doi")) or (sn._norm_title(r.get("title")) + str(r.get("year") or ""))
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def year_distribution_skew(records: list[dict], current_year: int) -> dict:
    """检出语料的【年代分布偏斜】advisory（warn-only 信号，绝不判缺陷、绝不替用户定）。

    Round 2 R1 借 imbad0202/academic-research-skills(34.6K★) 的 DISTRIBUTIONAL_SKEW_ADVISORY
    思路——但**只做年代轴**:方法/地域轴需全文元数据,免 key 摘要级拿不全(OpenAlex topics ≠ 方法学/地域),
    诚实不做(见 SKILL 名实对齐 / competitors §3.4)。给的是"分布信号 + 具体补救动作",不是"检索做错了"。
    """
    known = [r for r in records if r.get("year")]
    if not current_year or len(known) < 5:
        return {"skew": "unknown", "n_known": len(known), "advisory_hint": "",
                "note": "样本<5 或无 --current-year,不足判年代分布(诚实不臆断)。"}
    recent = sum(1 for r in known if (current_year - r["year"]) <= 3)
    old = sum(1 for r in known if (current_year - r["year"]) >= 8)
    recent_share = round(recent / len(known), 3)
    old_share = round(old / len(known), 3)
    # 判据按真实多源数据校准(活体 E2E 实测):三层 union 里经典层结构性注入老文,纯"近三年占比≥85%"
    # 几乎永不触发(diffusion 实测 recent=0.667/old=0.0 仍 <0.85)。更有用且能真触发的信号 =
    # 「近三年占多数 且 几近无 ≥8 年奠基作(old_share≈0)」→ 领域地图缺历史根,这正是研究者需要的预警。
    if old_share <= 0.10 and recent_share >= 0.50:
        skew, hint = "recent_heavy", (
            f"近三年占 {int(recent_share*100)}%、≥8 年奠基作仅 {int(old_share*100)}%(几近为零)→ 领域地图缺历史根:"
            "对头部种子跑 snowball.py --two-hop-direction backward 补奠基,或确认该方向是否确无更早源头。")
    elif recent == 0 and old_share >= 0.85:
        skew, hint = "classic_heavy", (
            f"检出全部 ≥8 年、近三年 0 篇({old}/{len(known)}) → 方向可能已饱和或冷门:"
            "用 cross_domain_search.py 嫁接前沿方法轴,或换角度(见 ASK「方向太窄文稀」决策点)。")
    else:
        skew, hint = "balanced", ""
    return {"skew": skew, "recent_share": recent_share, "old_share": old_share,
            "n_known": len(known), "advisory_hint": hint,
            "note": "年代分布偏斜=warn-only 信号(借 imbad0202 DISTRIBUTIONAL_SKEW_ADVISORY,仅年代轴);"
                    "判据按真实多源数据校准(缺奠基根/已饱和);非缺陷判决,研究者据研究问题定取舍。"}


# ───────────────────────── 三层检索 ─────────────────────────
def three_layer_search(query: str, *, method: str = "", current_year: int = 0,
                        per_page: int = 8, offline: bool = False,
                        require_terms: list | None = None) -> dict:
    """三层分别检索分别排序。返回 {frontier, classic, cross, ...}，各层 records 已各自排序。"""
    cy = current_year or 0
    # ① 前沿层：相关度×时效（half_life 短=更偏最新），经典豁免仍在(防漏根)。
    frontier = sn.run(query, per_page=per_page, offline_sample=offline,
                      sort_by="relevance", recency_boost=bool(cy), current_year=cy,
                      half_life=2, require_terms=require_terms)
    # ② 经典层：在「相关集合」内按被引降序召回奠基作。
    # 坑(实跑发现)：直接 sort_by="cited" 会顶出蹭宽词的领域外超高被引文(如搜"sheep lameness"
    # 顶出高被引奶牛/通用文)，叠加 require_terms 过滤后这些被全滤掉 → 经典层空。正解=先按相关度
    # 召回(留在本领域)，再对相关集合按被引降序，得"领域内最高被引"=真奠基作。
    classic = sn.run(query, per_page=per_page * 2, offline_sample=offline,
                     sort_by="relevance", require_terms=require_terms)
    classic["records"] = sorted(classic.get("records") or [],
                                key=lambda r: -(r.get("cited_by") or 0))[:per_page]
    classic["sort_by"] = "relevance→cited(领域内被引降序)"
    # ③ 跨领域层：给方法轴才启用（应用轴×方法轴正交，不拼词）。
    cross = None
    if method:
        cross = cd.cross_domain(query, method, per_page=per_page,
                                current_year=cy, half_life=3, offline=offline)
    return {
        "query": query, "method_axis": method, "current_year": cy,
        "offline": frontier.get("offline") or classic.get("offline"),
        "frontier": frontier, "classic": classic, "cross": cross,
    }


# ───────────────────────── 领域地图合成（脚手架） ─────────────────────────
def biblio_coupling_clusters(records: list[dict], min_shared: int = 2) -> dict:
    """文献耦合：共享 referenced_works ≥min_shared 的记录归一"学派"候选簇。
    仅对带 referenced_works 的 OpenAlex 记录有效；缺则诚实标 unknown。"""
    have = [r for r in records if r.get("referenced_works")]
    if not have:
        return {"clusters": [], "note": "unknown：检出记录均无 referenced_works"
                "（非 OpenAlex 源/未取该字段），文献耦合不可算，不假装聚成。"}
    # 并查集按共享参考聚簇
    parent = {i: i for i in range(len(have))}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    refsets = [set(r.get("referenced_works") or []) for r in have]
    for i in range(len(have)):
        for j in range(i + 1, len(have)):
            if len(refsets[i] & refsets[j]) >= min_shared:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(have)):
        groups.setdefault(find(i), []).append(i)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        clusters.append({
            "size": len(members),
            "titles": [(have[m].get("title") or "")[:80] for m in members],
            "shared_refs_min": min_shared,
        })
    clusters.sort(key=lambda c: -c["size"])
    return {"clusters": clusters,
            "note": f"文献耦合(共享参考≥{min_shared})候选学派簇,共 {len(clusters)} 簇;"
                    "簇=候选,学派判定交研究者(启发式非定论)。"}


def scan_open_problems(records: list[dict], max_hits: int = 8) -> list[dict]:
    """启发式扫摘要里的 gap 短语 → 候选未解问题。命中=候选,非定论。"""
    hits = []
    for r in records:
        abs_txt = (r.get("abstract") or "")
        low = abs_txt.lower()
        for ph in _GAP_PHRASES:
            idx = low.find(ph)
            if idx >= 0:
                snippet = abs_txt[max(0, idx - 40): idx + 80].replace("\n", " ").strip()
                hits.append({"doi": r.get("doi") or "unknown",
                             "phrase": ph, "snippet": snippet})
                break
        if len(hits) >= max_hits:
            break
    return hits


def build_domain_map(layers: dict, *, current_year: int) -> dict:
    """把三层 records 合成领域地图脚手架：脉络时间线 + 方法谱系簇 + 未解问题候选 + 信号。"""
    cy = current_year or 0
    fr = layers["frontier"].get("records") or []
    cl = layers["classic"].get("records") or []
    cross = layers.get("cross")
    cross_recs = ((cross or {}).get("method", {}) or {}).get("records", []) if cross else []
    all_recs = _uniq_by_key(fr + cl + cross_recs)

    # 研究脉络：时间线（按年份升序）+ 角色启发式
    timeline = sorted(
        [{"year": r.get("year"), "title": (r.get("title") or "")[:80],
          "cited_by": r.get("cited_by"), "cited_by_src": r.get("cited_by_src"),
          "doi": r.get("doi") or "unknown",
          "annual_cites": _annual_citations(r, cy) if cy else "unknown",
          "role": _role_hint(r, cy) if cy else "unknown(需 --current-year)"}
         for r in all_recs if r.get("year")],
        key=lambda x: (x["year"] or 0))

    # 信号识别（蓝图 §6 ③）
    recent_cnt = sum(1 for r in all_recs if r.get("year") and cy and (cy - r["year"]) <= 3)
    signals = {
        "frontier_sparse": bool(cy) and recent_cnt < 3,
        "frontier_recent_count": recent_cnt,
        "frontier_sparse_hint": ("近三年相关文稀少 → 提示考虑跨领域方法嫁接(--method)或换角度"
                                 if (cy and recent_cnt < 3) else ""),
        "pseudo_hotspot_hint": "高被引但 year 老且年均被引低者 = 疑伪热点(方法可能过时),见 lineage role(启发式)",
        "year_skew": year_distribution_skew(all_recs, cy),  # R1 新增:年代分布偏斜 advisory(warn-only)
    }

    return {
        "research_lineage": {
            "timeline": timeline,
            "synthesis_slot": "",  # 宿主 LLM 据 timeline 填："问题怎么提出→怎么被解决→还剩什么"
            "note": "时间线+角色为确定性脚手架(角色判级启发式);演进叙事由研究者/宿主据证据填,脚本不臆造。",
        },
        "method_genealogy": biblio_coupling_clusters(all_recs),
        "open_problems": {
            "gap_phrase_hits": scan_open_problems(all_recs),
            "synthesis_slot": "",  # 宿主 LLM 据 hits + 缺口填"哪些坑没填好"
            "note": "gap 短语命中=候选未解问题(启发式扫摘要),非定论;研究者据全文核实。",
        },
        "signals": signals,
        "n_unique": len(all_recs),
    }


# ───────────────────────── 撞车检测（findings 灵魂） ─────────────────────────
def detect_collision(idea: str, layers: dict, *, top_k: int = 3, mode: str = "auto") -> dict:
    """用 _shared/semantic_sim 找'最像你设想的那一篇'。产候选 + facet 槽位,不下 novel 判决。"""
    fr = layers["frontier"].get("records") or []
    cl = layers["classic"].get("records") or []
    cross = layers.get("cross")
    cross_recs = ((cross or {}).get("method", {}) or {}).get("records", []) if cross else []
    cands = _uniq_by_key(fr + cl + cross_recs)
    if not cands:
        return {"most_similar": [], "note": "无候选记录,无法做撞车检测。"}
    degraded = _semsim is None
    scored = []
    for r in cands:
        text = ((r.get("title") or "") + ". " + " ".join((r.get("abstract") or "").split()[:60])).strip()
        if degraded:
            # 降级：纯词面 Jaccard（_shared 不可达）
            qa = set(re.findall(r"[a-z0-9]+|[一-鿿]", idea.lower()))
            ta = set(re.findall(r"[a-z0-9]+|[一-鿿]", text.lower()))
            sim = round(len(qa & ta) / len(qa | ta), 3) if (qa | ta) else 0.0
        else:
            sim = _semsim.similarity(idea, text, mode=mode)
        scored.append((sim, r))
    scored.sort(key=lambda x: -x[0])
    used_mode = "lexical_only(_shared不可达)" if degraded else (_semsim.last_mode() if _semsim else "n/a")
    top = []
    for sim, r in scored[:top_k]:
        top.append({
            "similarity": round(float(sim), 3),
            "title": (r.get("title") or "")[:100],
            "year": r.get("year"), "doi": r.get("doi") or "unknown",
            "cited_by": r.get("cited_by"),
            # facet 槽位：留给 idea-critique / 宿主 LLM 拆 delta（对齐 Idea Novelty Checker 的
            # purpose/mechanism/evaluation/application-domain 四 facet）——脚本不臆造判决。
            "facet_overlap_slots": {"application_domain": "", "purpose": "",
                                    "mechanism": "", "evaluation": ""},
        })
    return {
        "idea": idea, "most_similar": top, "sim_mode": used_mode,
        "note": "相似度为语义相似启发式(档位见 sim_mode);**最像≠撞车**,novel/not-novel 判决归 "
                "idea-critique(结构性 AI 不能自评)。facet 槽位留给下游拆 delta。"
                + (" [降级] _shared 不可达,退化纯词面,易漏纯同义。" if degraded else ""),
    }


# ───────────────────────── findings 产出（接 _shared） ─────────────────────────
def _coverage_gate_fn(art: dict) -> "GateResult":
    layers = art["layers"]
    offline = layers.get("offline")
    fr, cl = layers["frontier"], layers["classic"]
    http = {**(fr.get("http") or {}), **(cl.get("http") or {})}   # 各源真实 HTTP 码(不臆测)
    recs = (fr.get("records") or []) + (cl.get("records") or [])
    n_no_doi = sum(1 for r in recs if not r.get("doi"))
    n_no_cite = sum(1 for r in recs if r.get("cited_by") is None)
    covered = [s for s, c in http.items() if c == 200]
    failed = [f"{s}={c}" for s, c in http.items() if c not in (200, None)]
    if offline:
        failed = failed or ["network-down→[OFFLINE]合成样本"]
    findings = [Finding(
        loc=f"query:{layers.get('query')}",
        issue=(f"实测覆盖源(HTTP200)={covered or 'none'};失败/降级源={failed or 'none'};"
               f"未覆盖(无免费API)=CNKI/万方/维普;无DOI {n_no_doi} 条、无被引 {n_no_cite} 条(标 unknown,不臆造)。"),
        fix="高利害方向加 --method 跨领域层、生医补 Europe PMC/PubMed、中文补 ISSN→OpenAlex;免key接口配额限不保证召全。",
        evidence=f"per-source HTTP={http or '{}(offline)'}",
        rule="coverage.honest")]
    # R1 新增:年代分布偏斜 advisory(借 imbad0202 DISTRIBUTIONAL_SKEW_ADVISORY,机读进 findings,warn-only)。
    # 复用 build_domain_map 已算的单一值(同 markdown 信号,避免两处口径不一);缺则就地按本门记录集算。
    skew = art.get("year_skew") or year_distribution_skew(recs, layers.get("current_year") or 0)
    if skew.get("skew") in ("recent_heavy", "classic_heavy"):
        findings.append(Finding(
            loc=f"corpus_year_distribution(n_known={skew['n_known']})",
            issue=f"年代分布偏斜[{skew['skew']}]:{skew['advisory_hint']}",
            fix="按 advisory_hint 补检索(滚雪球补根 / cross_domain 嫁接);这是分布信号非缺陷,研究者据 RQ 定。",
            evidence=f"recent_share={skew.get('recent_share')}, old_share={skew.get('old_share')}",
            rule="coverage.year_skew"))
    status = "warn" if (offline or failed or n_no_doi or n_no_cite
                        or skew.get("skew") in ("recent_heavy", "classic_heavy")) else "pass"
    return GateResult("search_coverage", status, "minor", findings,
                      note="覆盖度诚实门:按各源真实 HTTP 码标 covered/失败/unknown + 年代分布偏斜 advisory,"
                           "不假装查全(warn 非阻断,绝不替用户判)。")


def _collision_gate_fn(art: dict) -> "GateResult":
    coll = art.get("collision")
    if not coll or not coll.get("most_similar"):
        return GateResult("idea_collision", "skip", "info", [],
                          note="未给 --idea 或无候选:跳过撞车检测。")
    top = coll["most_similar"][0]
    findings = [Finding(
        loc=top.get("doi") or "unknown",
        issue=f"最像你设想的前作:「{top['title']}」({top.get('year')}) 语义相似={top['similarity']}({coll.get('sim_mode')})",
        fix="喂 idea-critique 做撞车预警:沿 purpose/mechanism/evaluation/application-domain 拆 delta;最像≠撞车,judge 归 idea-critique。",
        evidence=f"top{len(coll['most_similar'])} 候选+facet 槽位见 collision.most_similar",
        rule="collision.semantic_sim")]
    # warn:这是给 idea 阶段门的信号,不是本技能的 critical 判决。
    return GateResult("idea_collision", "warn", "major", findings,
                      note="撞车预警信号(warn):最像前作+facet 槽位喂 idea-critique;novel 判决归下游,本门不阻断。")


def emit_findings(layers: dict, collision: dict | None, *, query: str, year_skew: dict | None = None):
    """产 light.findings.v1（producer=literature-search）。无 _shared 则诚实降级不假装。"""
    if not _SHARED_OK:
        return None
    art = {"layers": layers, "collision": collision, "year_skew": year_skew}
    return run_gates([_coverage_gate_fn, _collision_gate_fn], art,
                     producer="literature-search", target=query,
                     summary="literature-search 信号门:覆盖度(warn)+撞车预警(warn);critical 撞车判决归 idea-critique。",
                     fresh_evidence=True)


# ───────────────────────── 编排入口 ─────────────────────────
def build(query: str, *, method: str = "", idea: str = "", current_year: int = 0,
          per_page: int = 8, offline: bool = False, require_terms: list | None = None) -> dict:
    layers = three_layer_search(query, method=method, current_year=current_year,
                                per_page=per_page, offline=offline, require_terms=require_terms)
    dmap = build_domain_map(layers, current_year=current_year)
    collision = detect_collision(idea, layers) if idea else None
    # 把 domain_map 已算的年代偏斜单一值传进 findings,保证 markdown 信号与机读 findings 口径一致。
    report = emit_findings(layers, collision, query=query,
                           year_skew=(dmap.get("signals") or {}).get("year_skew"))
    return {"query": query, "offline": layers.get("offline"),
            "layers": layers, "domain_map": dmap, "collision": collision,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def _layer_titles(run_out: dict, n: int = 3) -> list[str]:
    return [(r.get("title") or "")[:60] for r in (run_out.get("records") or [])[:n]]


def to_markdown(result: dict) -> str:
    q = result["query"]
    L = result["layers"]
    dm = result["domain_map"]
    lines = [f"# 领域地图：{q}", "",
             "> 三层**分别检索分别排序**(不是一锅 relevance);领域地图=研究脉络+方法谱系+未解问题"
             "(脚手架确定,叙事由研究者据证据填);被引标来源库不跨库比。",
             ("> **[OFFLINE]** 网络不可达,走合成样本,仅验证管线。" if result.get("offline") else ""), "",
             "## ① 前沿层(近三年,相关度×时效)", ""]
    for i, t in enumerate(_layer_titles(L["frontier"]), 1):
        lines.append(f"{i}. {t}")
    lines += ["", "## ② 经典奠基层(被引降序)", ""]
    for i, t in enumerate(_layer_titles(L["classic"]), 1):
        lines.append(f"{i}. {t}")
    lines += ["", "## ③ 跨领域方法层", ""]
    if L.get("cross"):
        for i, t in enumerate(_layer_titles(L["cross"]["method"]), 1):
            lines.append(f"{i}. {t}")
    else:
        lines.append("_未给方法轴(--method),已跳过。窄领域近三年文稀时强烈建议启用。_")
    lines += ["", "## 研究脉络(时间线脚手架)", ""]
    for e in dm["research_lineage"]["timeline"][:12]:
        lines.append(f"- {e['year']} · {e['title']} · cited={e['cited_by']}({e.get('cited_by_src')}) · {e['role']}")
    lines += ["", "## 方法谱系(文献耦合候选簇)", "", dm["method_genealogy"]["note"]]
    lines += ["", "## 未解问题(gap 短语候选)", ""]
    for h in dm["open_problems"]["gap_phrase_hits"][:6]:
        lines.append(f"- [{h['phrase']}] {h['snippet']} ({h['doi']})")
    lines += ["", "## 信号", "",
              f"- 近三年相关文数={dm['signals']['frontier_recent_count']}"
              + (f" ⚠ {dm['signals']['frontier_sparse_hint']}" if dm['signals']['frontier_sparse'] else "")]
    _skew = dm["signals"].get("year_skew") or {}
    if _skew.get("advisory_hint"):
        lines.append(f"- ⚠ 年代分布偏斜[{_skew['skew']}]:{_skew['advisory_hint']}")
    if result.get("collision"):
        lines += ["", "## 撞车预警(最像的前作 → 喂 idea-critique)", "", result["collision"]["note"], ""]
        for c in result["collision"]["most_similar"]:
            lines.append(f"- sim={c['similarity']} · {c['title']} ({c.get('year')}) · {c['doi']}")
    return "\n".join(line for line in lines if line is not None)


# ───────────────────────── selftest（离线，确定性） ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 注入一个层分离清晰的离线 fixture：2024 低被引(前沿) vs 2010 高被引(经典)，带 referenced_works 测耦合。
    fixture = [
        {"source_api": "OpenAlex", "title": "Transformer goat behaviour recognition 2024",
         "authors": ["New A"], "year": 2024, "venue": "CEA", "doi": "10.1/new",
         "cited_by": 5, "cited_by_src": "OpenAlex", "type": "article",
         "abstract": "A new method. Future work remains on generalization.",
         "url": "oa:new", "referenced_works": ["W100", "W101", "W102"]},
        {"source_api": "OpenAlex", "title": "Foundational accelerometer activity recognition 2010",
         "authors": ["Old B"], "year": 2010, "venue": "Animals", "doi": "10.1/old",
         "cited_by": 900, "cited_by_src": "OpenAlex", "type": "article",
         "abstract": "Seminal work. A key limitation is small sample.",
         "url": "oa:old", "referenced_works": ["W100", "W101", "W200"]},
        {"source_api": "OpenAlex", "title": "Mid goat monitoring survey 2018",
         "authors": ["Mid C"], "year": 2018, "venue": "Sensors", "doi": "10.1/mid",
         "cited_by": 120, "cited_by_src": "OpenAlex", "type": "article",
         "abstract": "A survey of goat monitoring.", "url": "oa:mid",
         "referenced_works": ["W100", "W101", "W300"]},
    ]
    orig = sn._SYNTHETIC
    sn._SYNTHETIC = fixture
    try:
        # 1. 三层分别排序：前沿层 2024 在前，经典层 900-cited 在前 → 头条不同。
        res = build("goat behaviour recognition", current_year=2026, offline=True)
        fr = res["layers"]["frontier"]["records"]
        cl = res["layers"]["classic"]["records"]
        check(fr and cl, "三层应有 records")
        check(cl[0].get("cited_by") == 900, f"经典层头条应是 900-cited,实得 {cl[0].get('cited_by')}")

        def _pos(recs, doi):
            for i, r in enumerate(recs):
                if r.get("doi") == doi:
                    return i
            return 999
        # 分别排序的证据(对经典豁免鲁棒)：2024 新文在前沿层比经典层排得更靠前；
        # 且前沿层每条带 recency rerank_parts(经典层是纯被引序,无)。
        check(_pos(fr, "10.1/new") < _pos(cl, "10.1/new"),
              f"2024 新文应在前沿层更靠前(fr={_pos(fr,'10.1/new')} < cl={_pos(cl,'10.1/new')})")
        check(all("rerank_parts" in r for r in fr), "前沿层每条应带时效重排 rerank_parts(经典层无)")
        check(not any("rerank_parts" in r for r in cl), "经典层应是纯被引序,不带 rerank_parts")

        # 2. 领域地图三件套结构
        dm = res["domain_map"]
        check(dm["research_lineage"]["timeline"][0]["year"] == 2010, "脉络时间线应按年份升序(2010 在前)")
        check(any("foundational" in e["role"] for e in dm["research_lineage"]["timeline"]),
              "900-cited 2010 文应判 foundational(启发式)")
        check(dm["method_genealogy"]["clusters"], "三条共享 W100/W101 应聚成 1 个文献耦合簇")
        check(dm["method_genealogy"]["clusters"][0]["size"] == 3, "耦合簇应含 3 条")
        check(dm["open_problems"]["gap_phrase_hits"], "应扫出 gap 短语(future work/limitation)")

        # 3. 撞车检测：给 idea，最像应是 accelerometer 那条(语义/词面)
        res2 = build("goat behaviour recognition",
                     idea="accelerometer activity recognition in goats", current_year=2026, offline=True)
        coll = res2["collision"]
        check(coll and coll["most_similar"], "应产撞车候选")
        check(coll["most_similar"][0]["similarity"] >= coll["most_similar"][-1]["similarity"],
              "撞车候选应按相似度降序")
        check("facet_overlap_slots" in coll["most_similar"][0], "撞车候选应带 facet 槽位")

        # 4. findings 接 _shared：light.findings.v1 合法、verdict=warn、含两门
        if _SHARED_OK:
            rep = res2["findings"]
            check(rep is not None and rep["schema"] == "light.findings.v1", "应产 light.findings.v1")
            check(rep["producer"] == "literature-search", "producer 应为 literature-search")
            check(rep["verdict"] == "warn", f"信号门应 warn(无 critical),实得 {rep.get('verdict')}")
            gates = {g["gate"] for g in rep["gates"]}
            check("search_coverage" in gates and "idea_collision" in gates, "应含覆盖度+撞车两门")
            # round-trip
            rt = FindingsReport.from_json(json.dumps(rep, ensure_ascii=False))
            check(rt.producer == "literature-search", "findings JSON 应可往返")
            # 撞车门是 warn 不阻断（critical 判决归 idea-critique）
            coll_gate = next(g for g in rep["gates"] if g["gate"] == "idea_collision")
            check(coll_gate["status"] == "warn" and coll_gate["severity"] != "critical",
                  "撞车门应 warn 非 critical(本技能不下 novel 判决)")
        else:
            check(res2["findings"] is None, "_shared 不可达时 findings 应诚实为 None,不假装")

        # 5. 跨领域层：给 method 才启用
        res3 = build("goat behaviour", method="vision transformer", current_year=2026, offline=True)
        check(res3["layers"]["cross"] is not None, "给 --method 应启用跨领域层")
        check("未给方法轴" in to_markdown(res), "不给 method 的 markdown 应标跳过跨领域层")

        # 6. 年代分布偏斜 advisory（R1 新增，warn-only，单元级直测）
        recent_corpus = [{"year": y} for y in (2024, 2025, 2024, 2026, 2023, 2025)]  # 全近三年
        sk_recent = year_distribution_skew(recent_corpus, 2026)
        check(sk_recent["skew"] == "recent_heavy", f"全近三年应判 recent_heavy,实得 {sk_recent['skew']}")
        check(sk_recent["advisory_hint"] and "snowball" in sk_recent["advisory_hint"],
              "recent_heavy 应建议 backward 滚雪球补根")
        classic_corpus = [{"year": y} for y in (2008, 2010, 2005, 2012, 2009, 2011)]  # 全 ≥8 年
        sk_classic = year_distribution_skew(classic_corpus, 2026)
        check(sk_classic["skew"] == "classic_heavy", f"全 ≥8 年应判 classic_heavy,实得 {sk_classic['skew']}")
        check("cross_domain" in (sk_classic["advisory_hint"] or ""), "classic_heavy 应建议 cross_domain 嫁接")
        balanced_corpus = [{"year": y} for y in (2024, 2010, 2018, 2022, 2008, 2025)]  # 新老混合
        check(year_distribution_skew(balanced_corpus, 2026)["skew"] == "balanced", "新老混合应判 balanced")
        check(year_distribution_skew([{"year": 2024}, {"year": 2023}], 2026)["skew"] == "unknown",
              "样本<5 应诚实判 unknown(不臆断)")
        # 偏斜进 findings(机读):recent_heavy 语料应在覆盖度门多一条 coverage.year_skew finding
        if _SHARED_OK:
            sn._SYNTHETIC = [{"source_api": "OpenAlex", "title": f"recent paper {i}", "year": y,
                              "doi": f"10.9/r{i}", "cited_by": 3, "cited_by_src": "OpenAlex",
                              "abstract": "x", "url": f"oa:{i}", "referenced_works": []}
                             for i, y in enumerate((2024, 2025, 2024, 2026, 2023, 2025, 2024, 2025))]
            res_sk = build("recent heavy topic", current_year=2026, offline=True)
            rules = {f["rule"] for g in res_sk["findings"]["gates"] for f in g["findings"]}
            check("coverage.year_skew" in rules, "recent_heavy 语料应产 coverage.year_skew finding(机读)")
            check(res_sk["findings"]["verdict"] == "warn", "偏斜门仍 warn,绝不 critical")
            sn._SYNTHETIC = fixture  # 复位给 finally（虽 finally 还会复位 orig）
    finally:
        sn._SYNTHETIC = orig

    if failures:
        print("[SELFTEST][domain_map] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][domain_map] OK：三层分别排序 + 领域地图三件套 + 撞车检测 + findings(warn) 全通过。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="三层领域地图编排器 + 撞车/覆盖度 findings")
    ap.add_argument("query", nargs="?", help="研究方向检索式")
    ap.add_argument("--method", default="", help="方法轴检索式(启用跨领域层)")
    ap.add_argument("--idea", default="", help="你设想的 idea(启用撞车检测)")
    ap.add_argument("--current-year", type=int, default=0, help="当前年份(时效重排/判级,显式传保可复现)")
    ap.add_argument("--per-page", type=int, default=8)
    ap.add_argument("--require-terms", default="", help="逗号分隔,标题/摘要须全含")
    ap.add_argument("--offline", action="store_true", help="强制走合成样本(离线验证)")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整领域地图 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.query:
        ap.error("需要 query(或 --selftest)")

    req = [t.strip() for t in args.require_terms.split(",") if t.strip()] or None
    result = build(args.query, method=args.method, idea=args.idea,
                   current_year=args.current_year, per_page=args.per_page,
                   offline=args.offline, require_terms=req)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整领域地图 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)


if __name__ == "__main__":
    main()
