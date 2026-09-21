#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""venue_signal.py — 投稿 venue 多信号对照查询 (Light / light-venue-matching)

输入：--issn <ISSN> 和/或 --author "姓名" 和/或 稿件 --title/--abstract/--keywords。
封装 OpenAlex Sources / Authors / Works 查询，输出多信号对照 JSON：
  1. 发文量趋势        ← OpenAlex Sources counts_by_year
  2. 自引率粗查        ← 采样本刊近作 referenced_works，批量解析回指本刊比例(粗略外向自引)
  3. 审稿周期线索      ← venue 卡(--venues-csv 按 ISSN 取，或 --card-fields 内联)
  4. 作者与该刊主题重叠← OpenAlex Authors x_concepts/topics 与 Sources 主题重叠
  5. APC 与分区        ← venue 卡 + OpenAlex Sources apc_usd
  6. 稿件→venue 语义契合← 稿件标题/摘要/关键词 vs venue scope(concepts+topics+近作标题)
                          经 _shared/semantic_sim，输出契合分 + 命中/缺失主题词（品类核心能力）
  7. 作者相对实力       ← 作者 h-index 对比 venue 近作作者 h-index 分布(中位数+百分位)，定高/中/低

跨技能反哺：信号6 的稿件摘要可直接消费 paper-writing 的 draft.md 草稿；信号7/4 的主题向量与
literature-search 的概念抽取同源（取数复用 lit-search 免 key 端点同口径）；候选发现直接走
OpenAlex Sources（按方向/topic/OA/APC 过滤 + cursor 翻页，见 references.md），不依赖任何本地 venue 库。

诚实约定：
- OpenAlex 2026-02-13 起需免费 API key（polite pool/mailto 已停用）；key/限流/计费/退避的唯一口径见
  literature-search references「OpenAlex 接入真相源」节，本脚本不复写数字。
  key 经 --api-key 或环境变量 OPENALEX_API_KEY 传入；礼貌池邮箱经 --mailto 或 OPENALEX_MAILTO 传入；
  均不传则匿名查询（灰度期或仍 200，但不保证；不伪造邮箱/key），失败由上层降级 unavailable。
- 任一信号取数失败 → 该信号 status="unavailable" + reason，不编数、不崩溃（能查多少出多少）。
- 作者重名严重：Authors search 取首个命中仅作线索，输出标 disambiguation_caveat，
  需 ORCID/机构二次确认，禁当定论（与 SKILL rubric 一致）。
- 自引率为"外向自引"粗估(本刊论文引用本刊的比例)，非官方入向期刊自引率，输出已注明 method。
- venue 卡的审稿周期/APC/分区为社区/官方混合口径，引用各标来源年份(见 SKILL §3)。venue 卡
  来自用户给的薄缓存(--venues-csv) 或内联(--card-fields) 或在线现建临时卡——**本技能不内嵌 venue 库**(易腐)。
- IF 口径(G3/G5)：按 venue 卡 risk_note 内 if_kind= 子串区分——jcr=真 JCR 权威快照(不被代理覆盖)，
  proxy=OpenAlex 代理值(非 JCR 真值，附在线 2yr 供交叉验证)，na=无 IF。

用法：
    python scripts/venue_signal.py --issn 1234-5678 --author "Zhang San" --mailto you@x.edu --api-key $OPENALEX_API_KEY
    python scripts/venue_signal.py --issn 1234-5678 --venues-csv <用户给的venue卡>.csv
    python scripts/venue_signal.py --batch <用户给的venue卡>.csv   # 全库复查产 diff 清单
    python scripts/venue_signal.py --selftest   # 离线 mock 自测（不打网络）
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# 挂接 _shared 共享语义相似度契约（不重造 Jaccard 轮子）。规范 bootstrap（_shared/README.md）：
# 向上走目录树找含 _shared 包的仓库根——治 v1 硬编码 `parents[2]/"_shared"` 之脆（v2 的 _shared 在
# 仓库根、与 skills/ 平级，脚本嵌套深度也变了，硬编码必断；三 harness/全局安装/任意嵌套都可靠）。
# 缺失则降级到本地 set Jaccard 并显式标注 sim_engine="jaccard_fallback"，绝不静默假成功。
try:
    _r = pathlib.Path(__file__).resolve()
    while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
        _r = _r.parent
    if not (_r / "_shared" / "__init__.py").exists():
        raise ImportError("向上未找到 _shared 包目录（请确保脚本在 Light-Skills 树内）")
    sys.path.insert(0, str(_r))
    from _shared import semantic_sim as _semsim
    _SEMSIM_OK = True
except Exception:
    _semsim = None
    _SEMSIM_OK = False

# 礼貌池邮箱：优先环境变量 OPENALEX_MAILTO，其次 --mailto，否则不带 mailto（OpenAlex 仍可匿名查，
# 只是不进礼貌池）。不再硬编码伪造邮箱——伪造邮箱违反 OpenAlex 礼貌池约定且无意义。
DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO", "").strip()
TIMEOUT = 30
OA = "https://api.openalex.org"

# 采样上限（控制请求数；注释解释取舍）
SELF_REF_SAMPLE_WORKS = 25     # 采样本刊近作篇数
SELF_REF_MAX_REFS = 200        # 解析的被引文献 ID 上限
RESOLVE_CHUNK = 50             # OpenAlex OR 过滤单批上限
AUTHOR_DIST_SAMPLE_WORKS = 20  # 信号7：采样本刊近作篇数(估该刊作者 h-index 分布)
AUTHOR_DIST_MAX_AUTHORS = 60   # 信号7：纳入分布的作者上限(控批量请求)
MANUSCRIPT_FIT_TOP_CONCEPTS = 12  # 信号6：取 venue 前 N 个高权重概念做 scope 词面
FIT_TERM_THRESHOLD = 0.45      # 信号6：单主题词判"命中"的相似度阈值(启发式)


def _sim(a: str, b: str) -> float:
    """语义相似度：优先 _shared/semantic_sim(治词序/屈折)，缺失则降级裸 set Jaccard。
    返回 [0,1]。调用方据 sim_engine 字段留痕实际所用引擎。"""
    if _SEMSIM_OK:
        return _semsim.similarity(a, b, mode="auto")
    # 降级：纯 stdlib set Jaccard（显式标注，绝不静默假成功）
    ta = set(re.findall(r"[a-z0-9]+", (a or "").lower()))
    tb = set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _sim_engine() -> str:
    """本次 _sim 实际所用引擎，供输出留痕。"""
    if not _SEMSIM_OK:
        return "jaccard_fallback(_shared/semantic_sim 不可用)"
    return "semantic_sim:%s" % (_semsim.last_mode() or "offline")


def _percentile(sorted_vals: list, p: float) -> float:
    """sorted_vals(升序)的 p 分位(0-100)，线性插值。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# 运行时礼貌池邮箱 + OpenAlex API key（main/selftest 可覆盖）。空串=匿名/无 key。口径与
# literature-search 同：OPENALEX_MAILTO 进礼貌池；OPENALEX_API_KEY 走 OpenAlex 2026-02-13 起所需
# 免费 key（key/限流/计费的唯一口径见 literature-search references「OpenAlex 接入真相源」，不复写数字）。
_MAILTO = DEFAULT_MAILTO
_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()


def _user_agent() -> str:
    if _MAILTO:
        return "Light-venue-matching/1.0 (mailto:%s)" % _MAILTO
    return "Light-venue-matching/1.0"


def http_fetch(url: str) -> dict:
    """真实 GET，返回解析后的 JSON dict。失败抛异常由上层捕获降级。"""
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent(), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _oa_params(params: dict) -> str:
    """给 OpenAlex 查询参数按需注入 mailto（礼貌池）与 api_key（2026-02-13 起 OpenAlex 需免费 key）。
    不伪造邮箱/key；缺失则匿名查（灰度期或仍可，但不保证，失败由上层降级 unavailable）。"""
    p = dict(params)
    if _MAILTO:
        p.setdefault("mailto", _MAILTO)
    if _API_KEY:
        p.setdefault("api_key", _API_KEY)
    return urllib.parse.urlencode(p)


def _sid_short(sid: str) -> str:
    return (sid or "").rsplit("/", 1)[-1]


# ---- OpenAlex 实体查询 -------------------------------------------------

def oa_source_by_issn(issn: str, fetch) -> dict | None:
    url = f"{OA}/sources/issn:{urllib.parse.quote(issn)}?" + _oa_params({
        "select": "id,display_name,works_count,cited_by_count,apc_usd,"
                  "is_oa,is_in_doaj,summary_stats,counts_by_year,x_concepts,topics"})
    return fetch(url)


def oa_author_by_name(name: str, fetch) -> dict | None:
    url = f"{OA}/authors?" + _oa_params({
        "search": name, "per_page": 1,
        "select": "id,display_name,works_count,cited_by_count,summary_stats,"
                  "last_known_institutions,x_concepts,topics,orcid"})
    data = fetch(url)
    results = (data or {}).get("results") or []
    return results[0] if results else None


# ---- DOAJ 收录核查（白名单正面信号；免 key REST）-----------------------

DOAJ = "https://doaj.org/api"


def doaj_by_issn(issn: str, fetch) -> dict:
    """DOAJ 收录核查：按 ISSN 查 DOAJ Articles/Journals API（免 key）。

    DOAJ 收录是 OA 期刊质量白名单的正面信号（区别于 OpenAlex 的 is_in_doaj 标志——
    此处直查 DOAJ 官方库做独立交叉确认，OpenAlex 的标志可能滞后）。
    返回三态：in_doaj=True/False/None（None=查询失败，未知，不等于未收录）。
    诚实约定：查不到记 status=unavailable + reason，绝不把"查询失败"当成"未被收录"。
    """
    url = f"{DOAJ}/search/journals/issn:{urllib.parse.quote(issn)}"
    try:
        data = fetch(url)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "in_doaj": None,
                "reason": f"DOAJ 查询失败({e.__class__.__name__})——未知，非"
                          f"未收录；投前人工核 doaj.org"}
    total = (data or {}).get("total")
    if total is None:
        return {"status": "unavailable", "in_doaj": None,
                "reason": "DOAJ 响应无 total 字段，无法判定"}
    in_doaj = int(total) > 0
    out = {"status": "ok", "in_doaj": in_doaj, "doaj_hits": int(total),
           "source": "doaj.org/api/search/journals"}
    if in_doaj:
        # 取首条的 Seal 标记（DOAJ Seal 是更高质量信号）
        results = (data or {}).get("results") or []
        if results:
            bib = (results[0] or {}).get("bibjson") or {}
            out["doaj_seal"] = bool(bib.get("boai") or bib.get("seal"))
        out["note"] = "DOAJ 收录=OA 期刊白名单正面信号；非质量保证，仍须看分区/预警名单"
    else:
        out["note"] = "DOAJ 未收录——可能是非 OA 刊（正常）或确未收录；结合其他信号判断，勿单独据此劝退"
    return out


# ---- 五信号 ------------------------------------------------------------

def signal_volume_trend(source: dict) -> dict:
    """信号1：发文量趋势（counts_by_year 近 3 年均值 vs 更早 3 年均值）。"""
    if not source:
        return {"status": "unavailable", "reason": "source 未取到"}
    cby = sorted(source.get("counts_by_year") or [], key=lambda r: r.get("year", 0))
    years = [(r.get("year"), r.get("works_count", 0)) for r in cby if r.get("year")]
    if len(years) < 4:
        return {"status": "unavailable", "reason": "counts_by_year 不足 4 年", "by_year": years}
    recent = [w for _, w in years[-3:]]
    earlier = [w for _, w in years[-6:-3]] or [w for _, w in years[:-3]]
    r_mean = sum(recent) / len(recent)
    e_mean = sum(earlier) / len(earlier) if earlier else 0
    if e_mean == 0:
        trend = "unknown"
    elif r_mean > e_mean * 1.15:
        trend = "rising"
    elif r_mean < e_mean * 0.85:
        trend = "declining"
    else:
        trend = "stable"
    return {"status": "ok", "trend": trend,
            "recent3y_mean_works": round(r_mean, 1),
            "earlier3y_mean_works": round(e_mean, 1),
            "by_year": years[-6:],
            "note": "发文量上升只描述规模变化；合法热门/巨刊同样会增长。仅作人工复核线索，不单独指向掠夺。"}


def _concept_weights(entity: dict) -> dict:
    """从实体取 {concept_id: score}，优先 x_concepts，回退 topics。"""
    out = {}
    for c in (entity.get("x_concepts") or []):
        cid = _sid_short(c.get("id", ""))
        if cid:
            out[cid] = float(c.get("score", 0) or 0)
    if out:
        return out
    for t in (entity.get("topics") or []):
        tid = _sid_short(t.get("id", ""))
        if tid:
            out[tid] = float(t.get("count", 0) or 0)
    return out


def signal_author_match(author: dict, source: dict) -> dict:
    """信号4：作者与该刊主题重叠（x_concepts/topics 加权 Jaccard）。"""
    if not author or not source:
        return {"status": "unavailable", "reason": "author 或 source 未取到"}
    aw = _concept_weights(author)
    sw = _concept_weights(source)
    if not aw or not sw:
        return {"status": "unavailable", "reason": "缺主题/概念字段"}
    inter = set(aw) & set(sw)
    union = set(aw) | set(sw)
    jacc = len(inter) / len(union) if union else 0
    overlap_score = sum(min(aw[c], sw[c]) for c in inter)
    level = "高" if jacc >= 0.4 else ("中" if jacc >= 0.15 else "低")
    shared = sorted(inter, key=lambda c: min(aw[c], sw[c]), reverse=True)[:5]
    return {"status": "ok", "match_level": level,
            "jaccard": round(jacc, 3), "weighted_overlap": round(overlap_score, 3),
            "shared_concepts": shared,
            "disambiguation_caveat": "作者按姓名 search 取首个命中，重名未排歧，"
                                     "需 ORCID/机构二次确认，勿当定论"}


def _concept_names(entity: dict, top: int = 99) -> list:
    """取实体 [(display_name, weight)] 按权重降序，优先 x_concepts(有 display_name)，
    回退 topics。用于稿件→venue 语义匹配的 scope 词面。"""
    out = []
    for c in (entity.get("x_concepts") or []):
        nm = (c.get("display_name") or "").strip()
        if nm:
            out.append((nm, float(c.get("score", 0) or 0)))
    if not out:
        for t in (entity.get("topics") or []):
            nm = (t.get("display_name") or "").strip()
            if nm:
                out.append((nm, float(t.get("count", 0) or 0)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:top]


def _manuscript_terms(title: str, abstract: str, keywords: list) -> list:
    """从稿件抽待匹配主题词：keywords 优先(权威)，否则用标题去停用词的名词性 token。
    abstract 仅用于补充关键词缺失时的兜底覆盖。返回去重的词列表。"""
    terms = []
    seen = set()

    def _add(s):
        s = (s or "").strip()
        k = s.lower()
        if s and k not in seen and len(s) >= 2:
            seen.add(k)
            terms.append(s)

    for kw in (keywords or []):
        _add(kw)
    # 标题词组（去停用词，保留 ≥3 字母的实词）作为补充主题词
    stop = {"a", "an", "the", "for", "of", "to", "in", "on", "and", "or", "with",
            "is", "are", "be", "by", "as", "at", "via", "using", "based", "towards",
            "toward", "novel", "new", "approach", "method", "study", "analysis"}
    src = title if title else ""
    if not keywords and abstract:
        src = (title + ". " + abstract) if title else abstract
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", src):
        if tok.lower() not in stop:
            _add(tok)
    return terms[:20]


def signal_manuscript_fit(source: dict, title: str, abstract: str,
                          keywords: list, official_scope_terms: list | None = None) -> dict:
    """信号6：稿件文本 → venue 语义契合（品类核心能力，竞品 Jane/Jot/B!SON 立身之本）。

    把稿件主题词（keywords 优先，否则标题/摘要抽词）逐一对 venue scope 词面
    （OpenAlex x_concepts/topics 的 display_name）做语义相似度，取每个主题词对
    venue 概念集合的最高相似度。fit_score = 命中主题词的平均最佳相似度。
    输出**命中主题词 + 缺失主题词**（SKILL 早承诺『缺失主题词』却从未实现，此处补上）。

    诚实约定：fit_score 是启发式参考非真值；语义引擎档位经 sim_engine 留痕
    （semantic_sim:embed/llm/offline 或 jaccard_fallback）；无稿件/无 venue 概念 → unavailable。
    """
    if not source and not official_scope_terms:
        return {"status": "unavailable", "reason": "venue source 与当天官方 scope 均未取到"}
    terms = _manuscript_terms(title, abstract, keywords)
    if not terms:
        return {"status": "unavailable",
                "reason": "未提供稿件文本(--title/--abstract/--keywords 至少其一)"}
    official_scope_terms = [
        str(item).strip() for item in (official_scope_terms or []) if str(item).strip()
    ]
    venue_concepts = (
        [(item, 1.0) for item in official_scope_terms]
        if official_scope_terms
        else _concept_names(source, top=MANUSCRIPT_FIT_TOP_CONCEPTS)
    )
    if not venue_concepts:
        return {"status": "unavailable",
                "reason": "venue 无 x_concepts/topics 概念，无法做 scope 匹配"}
    venue_names = [n for n, _ in venue_concepts]
    matched, missing, per_term = [], [], []
    best_scores = []
    for term in terms:
        best = 0.0
        best_concept = None
        for vn in venue_names:
            sc = _sim(term, vn)
            if sc > best:
                best, best_concept = sc, vn
        per_term.append({"term": term, "best_sim": round(best, 3),
                         "nearest_venue_concept": best_concept})
        if best >= FIT_TERM_THRESHOLD:
            matched.append(term)
            best_scores.append(best)
        else:
            missing.append(term)
    # fit_score：命中词的平均最佳相似度 × 命中覆盖率（覆盖率惩罚大量缺失主题）
    cover = len(matched) / len(terms) if terms else 0.0
    mean_best = sum(best_scores) / len(best_scores) if best_scores else 0.0
    fit_score = round(mean_best * (0.5 + 0.5 * cover), 3)  # 覆盖率折半加权，避免单命中虚高
    level = "高" if fit_score >= 0.55 else ("中" if fit_score >= 0.30 else "低")
    return {"status": "ok", "fit_score": fit_score, "match_level": level,
            "coverage": round(cover, 3),
            "matched_topics": matched, "missing_topics": missing,
            "venue_scope_concepts": venue_names,
            "per_term": per_term,
            "sim_engine": _sim_engine(),
            "scope_source": "current_official_scope" if official_scope_terms else "openalex_topics_proxy",
            "input_source": "keywords" if keywords else ("title+abstract" if abstract else "title"),
            "note": (
                "fit_score/分级为启发式参考非真值；优先使用调用方当天从官方 Aims & Scope "
                "抄录的 scope_keywords；未给时 OpenAlex topics 只是覆盖代理，低分不得当官方 scope mismatch。"
            )}


def signal_author_strength(author: dict, source: dict, fetch) -> dict:
    """信号7：作者相对实力（h-index 在该刊作者 h-index 分布中的分位 → 高/中/低）。

    操作化 rubric 信号①：不再只并列两个裸数字，而是采样本刊近作的作者、批量取其
    h-index 建经验分布，算稿件作者 h-index 落在该分布的百分位，据此定高/中/低。

    诚实约定：分布为近作小样本估计（非该刊全量作者），样本量随输出；作者重名未排歧，
    沿用 disambiguation_caveat；取数失败 → unavailable，不编数。
    """
    if not author or not source:
        return {"status": "unavailable", "reason": "author 或 source 未取到"}
    a_h = ((author or {}).get("summary_stats") or {}).get("h_index")
    if a_h is None:
        return {"status": "unavailable", "reason": "作者无 h_index"}
    sid = _sid_short(source.get("id", ""))
    if not sid:
        return {"status": "unavailable", "reason": "source 无 id"}
    try:
        # 1) 采样本刊近作，收作者 ID
        wurl = f"{OA}/works?" + _oa_params({
            "filter": f"primary_location.source.id:{sid}",
            "select": "id,authorships", "per_page": AUTHOR_DIST_SAMPLE_WORKS,
            "sort": "publication_date:desc"})
        works = (fetch(wurl) or {}).get("results") or []
        aid_set = []
        seen = set()
        for w in works:
            for a in (w.get("authorships") or []):
                aid = _sid_short((a.get("author") or {}).get("id", ""))
                if aid and aid not in seen:
                    seen.add(aid)
                    aid_set.append(aid)
        aid_set = aid_set[:AUTHOR_DIST_MAX_AUTHORS]
        if len(aid_set) < 3:
            return {"status": "unavailable",
                    "reason": "本刊近作作者样本不足(<3)，无法建 h-index 分布",
                    "sampled_authors": len(aid_set)}
        # 2) 批量取这些作者 h-index
        h_vals = []
        for i in range(0, len(aid_set), RESOLVE_CHUNK):
            chunk = aid_set[i:i + RESOLVE_CHUNK]
            aurl = f"{OA}/authors?" + _oa_params({
                "filter": f"ids.openalex:{'|'.join(chunk)}",
                "select": "id,summary_stats", "per_page": RESOLVE_CHUNK})
            for r in (fetch(aurl) or {}).get("results") or []:
                hv = ((r.get("summary_stats") or {}).get("h_index"))
                if hv is not None:
                    h_vals.append(float(hv))
        if len(h_vals) < 3:
            return {"status": "unavailable",
                    "reason": "解析到的作者 h-index 样本不足(<3)",
                    "sampled_authors": len(aid_set), "resolved_h": len(h_vals)}
        h_vals.sort()
        below = sum(1 for v in h_vals if v < a_h)
        pct = round(100.0 * below / len(h_vals), 1)
        level = "高" if pct >= 60 else ("中" if pct >= 30 else "低")
        return {"status": "ok", "match_level": level,
                "author_h_index": a_h, "percentile_in_venue": pct,
                "venue_author_h_median": round(_percentile(h_vals, 50), 1),
                "venue_author_h_p25": round(_percentile(h_vals, 25), 1),
                "venue_author_h_p75": round(_percentile(h_vals, 75), 1),
                "sample_authors": len(h_vals),
                "disambiguation_caveat": "作者按姓名 search 取首个命中，重名未排歧，"
                                         "需 ORCID/机构二次确认；分布为本刊近作小样本估计非全量",
                "note": "作者 h-index 高于该刊典型作者(分位≥60)→实力相对高；明显低于(分位<30)→低"}
    except Exception as e:  # noqa: BLE001 — 优雅降级
        return {"status": "unavailable", "reason": f"查询失败: {e.__class__.__name__}"}


def signal_self_citation(source: dict, fetch) -> dict:
    """信号2：自引率粗查（外向自引：采样本刊近作 → 解析其 referenced_works → 回指本刊比例）。

    说明：OpenAlex 不直接给官方"入向期刊自引率"。这里用可计算的外向自引粗估：
    抽 N 篇本刊近作，收集它们引用的文献，批量解析这些被引文献的 primary source，
    统计回指本刊的占比。是粗略信号（受样本与年份影响），输出已注明 method 与样本量。
    任一步失败 → unavailable，不编数。
    """
    if not source:
        return {"status": "unavailable", "reason": "source 未取到"}
    sid = _sid_short(source.get("id", ""))
    if not sid:
        return {"status": "unavailable", "reason": "source 无 id"}
    try:
        sample_url = f"{OA}/works?" + _oa_params({
            "filter": f"primary_location.source.id:{sid}",
            "select": "id,referenced_works", "per_page": SELF_REF_SAMPLE_WORKS,
            "sort": "publication_date:desc"})
        works = (fetch(sample_url) or {}).get("results") or []
        ref_ids = []
        for w in works:
            ref_ids.extend(_sid_short(r) for r in (w.get("referenced_works") or []))
        ref_ids = [r for r in ref_ids if r][:SELF_REF_MAX_REFS]
        if not ref_ids:
            return {"status": "unavailable", "reason": "采样近作无 referenced_works",
                    "sample_works": len(works)}
        self_hits = 0
        for i in range(0, len(ref_ids), RESOLVE_CHUNK):
            chunk = ref_ids[i:i + RESOLVE_CHUNK]
            url = f"{OA}/works?" + _oa_params({
                "filter": f"ids.openalex:{'|'.join(chunk)},primary_location.source.id:{sid}",
                "select": "id", "per_page": RESOLVE_CHUNK})
            self_hits += (fetch(url) or {}).get("meta", {}).get("count", 0)
        rate = self_hits / len(ref_ids)
        # ⚠ 口径修正：25% 是"入向期刊自引率"(incoming，掠夺刊预警线，如 Web of Science 抑制名单口径)的
        # 经验线；本脚本算的是"外向自引"(outgoing，本刊论文引本刊比例)，两者口径不同——outgoing 偏高
        # 不必然=掠夺/操纵(综述刊、窄领域刊天然偏高)。故这里**只作参考提示、不作判据**，且阈值标来源。
        if rate > 0.40:
            flag = "outgoing 自引明显偏高(>40%)——仅供参考，需结合 incoming 自引率(本脚本不算)与领域特性人工核，勿据此单独判掠夺"
        elif rate > 0.25:
            flag = "outgoing 自引偏高(>25%，该线本是 incoming 预警经验线，套到 outgoing 仅作弱提示)"
        else:
            flag = "outgoing 自引常规区间"
        return {"status": "ok", "self_ref_rate": round(rate, 3),
                "self_ref_direction": "outgoing(本刊引本刊)", "sample_works": len(works),
                "refs_resolved": len(ref_ids), "self_refs": self_hits, "flag": flag,
                "threshold_note": "25%/40% 为参考线非判据；官方入向(incoming)期刊自引率本脚本不算，"
                                  "掠夺判定须看 incoming + 领域 + 预警名单(联动 research-ethics)，不可仅凭 outgoing",
                "method": "外向自引粗估(本刊论文引用本刊比例)，非官方入向自引率；受样本/年份影响"}
    except Exception as e:  # noqa: BLE001 — 优雅降级
        return {"status": "unavailable", "reason": f"查询失败: {e.__class__.__name__}"}


def _parse_risk_subfields(risk_note: str) -> dict:
    """从 risk_note 抽标准子串 oa_id=/issn=/domain_scope=/if_kind=(venue 卡 risk_note 锚点规整后)。"""
    out = {}
    for key in ("oa_id", "issn", "domain_scope", "if_kind"):
        m = re.search(rf"(?:^|[;；]\s*){key}=([^;；]+)", risk_note or "")
        if m:
            out[key] = m.group(1).strip()
    return out


def _load_card_from_csv(issn: str, venue_name: str, csv_path: str) -> dict | None:
    """从用户给的 venue 卡 CSV 取一行卡。优先按规整后的 issn=/oa_id= 锚点精确匹配，
    回退刊名匹配。匹配到的行附加解析出的 _subfields(oa_id/issn/domain_scope/if_kind)。"""
    try:
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None
    issn = (issn or "").strip()
    name_l = (venue_name or "").strip().lower()
    fallback = None
    for row in rows:
        sub = _parse_risk_subfields(row.get("risk_note", ""))
        # 精确锚点匹配：ISSN 子串 或 indexing 内 ISSN
        if issn and (sub.get("issn") == issn or issn in (row.get("indexing", "") or "")):
            row["_subfields"] = sub
            return row
        if name_l and name_l == (row.get("venue_name", "") or "").strip().lower():
            fallback = fallback or row
            fallback["_subfields"] = sub
    return fallback


def signal_review_cycle(card: dict | None) -> dict:
    """信号3：审稿周期线索（来自 venue 卡 review_cycle 字段）。"""
    if not card:
        return {"status": "unavailable",
                "reason": "无 venue 卡(传 --venues-csv 或 --card-fields review_cycle=...)"}
    rc = (card.get("review_cycle") or "").strip()
    if not rc:
        return {"status": "unavailable", "reason": "venue 卡 review_cycle 为空"}
    fast = any(k in rc for k in ("周", "week", "天", "day")) and \
        not any(k in rc for k in ("月", "month"))
    return {"status": "ok", "review_cycle": rc,
            "fast_flag": "审稿异常快需对照掠夺特征" if fast else "—",
            "source": f"venue 卡 last_checked={card.get('last_checked_date', '?')}，投前重核"}


def signal_apc_quartile(card: dict | None, source: dict) -> dict:
    """信号5：APC 与分区（venue 卡为主，OpenAlex apc_usd 兜底）。

    G3/G5 诚实口径：按 venue 卡的 if_kind 子串区分 IF 来源——
      if_kind=jcr   → 真 JCR(LetPub journalid)，权威快照，不被 OpenAlex 代理值覆盖；
      if_kind=proxy → OpenAlex 2yr 代理值/付费墙不可得，明确标注"非 JCR 真值"；
      if_kind=na    → 会议等无 IF。
    """
    out = {"status": "ok"}
    got = False
    if card:
        for k in ("apc_fee", "cas_quartile", "jcr_quartile", "impact_factor",
                  "level", "indexing"):
            v = (card.get(k) or "").strip()
            if v:
                out[k] = v
                got = True
        sub = card.get("_subfields") or {}
        if_kind = sub.get("if_kind")
        if if_kind:
            out["if_kind"] = if_kind
            out["if_caveat"] = {
                "jcr": "impact_factor 为真 JCR 快照(LetPub journalid)，权威值，投前仍核最新年度",
                "proxy": "impact_factor 非 JCR 真值(付费墙)，为 OpenAlex 2yr 均被引代理，"
                         "真 JCR/分区须查 Clarivate JCR/LetPub 付费源，勿当 JCR 引用",
                "na": "该 venue 无 IF(会议/无 JCR 收录)",
            }.get(if_kind, "")
        if sub.get("domain_scope"):
            out["domain_scope"] = sub["domain_scope"]
        out["source"] = f"venue 卡 last_checked={card.get('last_checked_date', '?')}"
    oa_apc = (source or {}).get("apc_usd")
    if oa_apc is not None:
        out["openalex_apc_usd"] = oa_apc
        got = True
    if (source or {}).get("is_in_doaj"):
        out["doaj"] = True
        got = True
    # 代理 IF 场景：附 OpenAlex 2yr 在线值供交叉验证(G1 冲突默认信在线)
    oa_2yr = ((source or {}).get("summary_stats") or {}).get("2yr_mean_citedness")
    if oa_2yr is not None and out.get("if_kind") == "proxy":
        out["openalex_2yr_mean_citedness_live"] = round(oa_2yr, 2)
        got = True
    if not got:
        return {"status": "unavailable", "reason": "venue 卡与 OpenAlex 均无 APC/分区"}
    out["note"] = "三套分区(JCR/SJR/中科院)口径不同，引用须标来源年份，禁混用(SKILL §3)"
    return out


def assemble(issn: str, author_name: str, card: dict | None, fetch,
             title: str = "", abstract: str = "", keywords: list | None = None) -> dict:
    keywords = keywords or []
    source = None
    if issn:
        try:
            source = oa_source_by_issn(issn, fetch)
        except Exception as e:  # noqa: BLE001
            source = None
            src_err = e.__class__.__name__
    author = None
    if author_name:
        try:
            author = oa_author_by_name(author_name, fetch)
        except Exception:  # noqa: BLE001
            author = None
    has_manuscript = bool(title or abstract or keywords)
    report = {
        "query": {"issn": issn or None, "author": author_name or None,
                  "manuscript": {"title": title or None,
                                 "has_abstract": bool(abstract),
                                 "keywords": keywords or None} if has_manuscript else None},
        "venue": {
            "openalex_id": _sid_short(source.get("id", "")) if source else None,
            "display_name": source.get("display_name") if source else None,
            "works_count": source.get("works_count") if source else None,
            "h_index": ((source or {}).get("summary_stats") or {}).get("h_index"),
        },
        "author": {
            "display_name": author.get("display_name") if author else None,
            "h_index": ((author or {}).get("summary_stats") or {}).get("h_index"),
            "orcid": author.get("orcid") if author else None,
        } if author_name else None,
        "signals": {
            "1_volume_trend": signal_volume_trend(source),
            "2_self_citation": signal_self_citation(source, fetch),
            "3_review_cycle": signal_review_cycle(card),
            "4_author_match": signal_author_match(author, source) if author_name
            else {"status": "unavailable", "reason": "未提供 --author"},
            "5_apc_quartile": signal_apc_quartile(card, source),
            "6_manuscript_fit": signal_manuscript_fit(
                source, title, abstract, keywords,
                [
                    item.strip()
                    for item in re.split(r"[|,;]", str((card or {}).get("scope_keywords") or ""))
                    if item.strip()
                ],
            )
            if has_manuscript
            else {"status": "unavailable",
                  "reason": "未提供稿件 --title/--abstract/--keywords"},
            "7_author_strength": signal_author_strength(author, source, fetch)
            if author_name
            else {"status": "unavailable", "reason": "未提供 --author"},
        },
        # 白名单正面信号（DOAJ 收录核查，独立于打分信号；预警筛查用）
        "whitelist": {
            "doaj": doaj_by_issn(issn, fetch) if issn
            else {"status": "unavailable", "in_doaj": None, "reason": "未提供 --issn"},
            "openalex_is_in_doaj": (source or {}).get("is_in_doaj") if source else None,
        },
    }
    if issn and source is None:
        report["venue"]["fetch_error"] = locals().get("src_err", "未取到 source")
    avail = sum(1 for s in report["signals"].values() if s.get("status") == "ok")
    total = len(report["signals"])
    # VM-3 最低可评估信号门槛：可核查信号 <2 时，总评只能给"数据不足"，不许硬凑定性结论
    if avail < 2:
        assess_gate = ("⚠ 数据不足：可核查信号仅 %d 项(<2)——总评只能给『数据不足，暂不下定性结论』，"
                       "勿据稀疏信号硬判 venue 适配/掠夺。补 --issn/--author/稿件文本或换有 OpenAlex 覆盖的刊再评。" % avail)
    else:
        assess_gate = "可核查信号 ≥2，可进入 rubric 综合评估(但脚本信号只覆盖部分维度，见 rubric_coverage)"
    report["summary"] = {
        "signals_ok": avail, "signals_total": total,
        "min_signal_gate": assess_gate,
        # VM-2 脚本信号 ↔ rubric 维度映射：防"跑完脚本=完成评估"的误解
        "rubric_coverage": {
            "脚本可程序化覆盖": ["体量趋势", "外向自引(参考)", "审稿周期(读卡)", "作者方向匹配",
                          "APC/分区(读卡)", "DOAJ 白名单", "稿件→venue 语义契合(信号6)",
                          "作者相对实力分位(信号7)"],
            "仍须人工(脚本不覆盖)": ["真实接收率/命中概率", "创新性与刊调性匹配",
                            "incoming 期刊自引率", "同行评审质量口碑", "审稿人构成"],
            "note": "本脚本只产『信号』非『结论』；跑完脚本≠完成 venue 评估，接收率/创新匹配/口碑须人工补",
        },
        "caveat": "OpenAlex 接入口径见 literature-search references 真相源节；"
                  "期刊数据有时效，投前在线重核、冲突信在线，查不到标 unknown"}
    return report


# ---- 离线 selftest（mock fetcher，不打网络）----------------------------

class _MockFetcher:
    """按 URL 形态返回 mock JSON，覆盖五信号全路径。"""

    def __init__(self):
        # 80 篇近作各引 1 篇；解析时每 4 篇回指本刊 → 自引率应 ≈0.25
        self._work_ids = [f"W{i:02d}" for i in range(80)]

    def __call__(self, url: str) -> dict:
        if "doaj.org/api" in url:  # DOAJ 收录核查 mock：命中 1 条带 seal
            return {"total": 1, "results": [{"bibjson": {"seal": True}}]}
        if "/sources/issn:" in url:
            return self._source()
        if "/authors?" in url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            filt = qs.get("filter", [""])[0]
            if "ids.openalex:" in filt:  # 信号7：批量取本刊作者 h-index 分布
                chunk = []
                for part in filt.split(","):
                    if part.startswith("ids.openalex:"):
                        chunk = part.split(":", 1)[1].split("|")
                # 给一组递增 h-index，构造可算分位的分布
                return {"results": [
                    {"id": aid, "summary_stats": {"h_index": 5 + (i * 3) % 40}}
                    for i, aid in enumerate(chunk)]}
            return {"results": [self._author()]}  # 信号4：按姓名 search 取首个
        if "ids.openalex" in url:  # 解析回指本刊的批次（冒号被编码，匹配前缀即可）
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            filt = qs.get("filter", [""])[0]
            chunk = []
            for part in filt.split(","):
                if part.startswith("ids.openalex:"):
                    chunk = part.split(":", 1)[1].split("|")
            hits = sum(1 for wid in chunk if self._is_self(wid))
            return {"meta": {"count": hits}, "results": []}
        if "/works?" in url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            select = qs.get("select", [""])[0]
            if "authorships" in select:  # 信号7：采样近作收作者 ID
                return {"results": [
                    {"id": f"S{i}", "authorships": [
                        {"author": {"id": f"https://openalex.org/A{i:03d}"}},
                        {"author": {"id": f"https://openalex.org/A{(i + 7):03d}"}}]}
                    for i in range(self._sample_works)]}
            # 信号2：采样近作收 referenced_works
            return {"results": [{"id": f"S{i}", "referenced_works":
                    [f"https://openalex.org/{w}"]}
                    for i, w in enumerate(self._work_ids)]}
        raise RuntimeError(f"mock 未覆盖 URL: {url}")

    _sample_works = 20

    @staticmethod
    def _is_self(wid: str) -> bool:
        try:
            return int(wid[1:]) % 4 == 0
        except ValueError:
            return False

    @staticmethod
    def _source() -> dict:
        return {
            "id": "https://openalex.org/S123", "display_name": "Journal of Mock Studies",
            "works_count": 5000, "cited_by_count": 90000, "apc_usd": 1800,
            "is_oa": True, "is_in_doaj": True,
            "summary_stats": {"h_index": 95, "2yr_mean_citedness": 4.2},
            "counts_by_year": [
                {"year": 2019, "works_count": 200}, {"year": 2020, "works_count": 210},
                {"year": 2021, "works_count": 230}, {"year": 2022, "works_count": 300},
                {"year": 2023, "works_count": 340}, {"year": 2024, "works_count": 360}],
            "x_concepts": [{"id": "https://openalex.org/C41008148", "score": 80,
                            "display_name": "Computer Science"},
                           {"id": "https://openalex.org/C154945302", "score": 60,
                            "display_name": "Artificial Intelligence"},
                           {"id": "https://openalex.org/C119857082", "score": 40,
                            "display_name": "Machine Learning"}],
        }

    @staticmethod
    def _author() -> dict:
        return {
            "id": "https://openalex.org/A99", "display_name": "Zhang San",
            "works_count": 60, "cited_by_count": 1500,
            "summary_stats": {"h_index": 22}, "orcid": None,
            "x_concepts": [{"id": "https://openalex.org/C41008148", "score": 75},
                           {"id": "https://openalex.org/C154945302", "score": 50},
                           {"id": "https://openalex.org/C777", "score": 20}],
        }


def _selftest() -> int:
    fetch = _MockFetcher()
    card = {"venue_name": "Journal of Mock Studies", "review_cycle": "约 8 周一审",
            "apc_fee": "1800 USD", "cas_quartile": "2区", "jcr_quartile": "Q2",
            "last_checked_date": "2026-06-11", "indexing": "SCIE; ISSN 1234-5678"}
    rep = assemble("1234-5678", "Zhang San", card, fetch,
                   title="Deep learning for image classification",
                   keywords=["machine learning", "artificial intelligence", "quantum cryptography"])
    sig = rep["signals"]
    assert sig["1_volume_trend"]["status"] == "ok", sig["1_volume_trend"]
    assert sig["1_volume_trend"]["trend"] == "rising", sig["1_volume_trend"]
    assert sig["2_self_citation"]["status"] == "ok", sig["2_self_citation"]
    assert abs(sig["2_self_citation"]["self_ref_rate"] - 0.25) < 0.05, sig["2_self_citation"]
    assert sig["3_review_cycle"]["status"] == "ok", sig["3_review_cycle"]
    assert sig["4_author_match"]["status"] == "ok", sig["4_author_match"]
    assert sig["4_author_match"]["match_level"] in ("高", "中"), sig["4_author_match"]
    assert sig["5_apc_quartile"]["status"] == "ok", sig["5_apc_quartile"]
    # 信号6：稿件→venue 语义契合（品类核心能力）。matched 应含与 venue scope 贴合的词，
    # missing 应含明显跨界词(quantum cryptography 不在该刊 CS/AI/ML scope)。
    s6 = sig["6_manuscript_fit"]
    assert s6["status"] == "ok", s6
    assert "missing_topics" in s6 and "matched_topics" in s6, s6
    assert "quantum cryptography" in s6["missing_topics"], s6  # 跨界词应被判缺失
    assert any("machine learning" == t for t in s6["matched_topics"]), s6  # scope 命中
    assert s6["match_level"] in ("高", "中", "低"), s6
    assert "sim_engine" in s6, s6  # 语义引擎留痕（治"dead import"：semantic_sim 实际被调用）
    # 信号7：作者相对实力分位（h-index 在该刊作者分布的百分位）
    s7 = sig["7_author_strength"]
    assert s7["status"] == "ok", s7
    assert s7["match_level"] in ("高", "中", "低"), s7
    assert "percentile_in_venue" in s7 and "venue_author_h_median" in s7, s7
    assert s7["author_h_index"] == 22, s7
    assert rep["summary"]["signals_ok"] == 7, rep["summary"]
    assert rep["summary"]["signals_total"] == 7, rep["summary"]
    # VM-2 信号编号映射 + VM-3 最低信号门槛：5 信号全 ok → 门禁放行 + rubric_coverage 列人工项
    assert "rubric_coverage" in rep["summary"] and "仍须人工(脚本不覆盖)" in rep["summary"]["rubric_coverage"], rep["summary"]
    assert "≥2" in rep["summary"]["min_signal_gate"], rep["summary"]["min_signal_gate"]
    # VM-3 反例：信号 <2 时门禁给"数据不足"。空 card + 网络全失败 → 卡信号与网络信号都缺
    rep_sparse = assemble("0000-0000", "", {}, lambda u: (_ for _ in ()).throw(Exception("net")))
    assert rep_sparse["summary"]["signals_ok"] < 2, rep_sparse["summary"]
    assert "数据不足" in rep_sparse["summary"]["min_signal_gate"], rep_sparse["summary"]["min_signal_gate"]
    # VM-1 自引口径：flag/方向标 outgoing、阈值标参考非判据
    sc = sig["2_self_citation"]
    if sc.get("status") == "ok":
        assert sc.get("self_ref_direction", "").startswith("outgoing"), sc
        assert "threshold_note" in sc, sc

    # DOAJ 白名单核查（mock 命中 1 条带 seal）
    wl = rep["whitelist"]["doaj"]
    assert wl["status"] == "ok" and wl["in_doaj"] is True, wl
    assert wl["doaj_hits"] == 1 and wl.get("doaj_seal") is True, wl
    # DOAJ 查询失败 → unavailable + in_doaj=None（绝不当成未收录）
    def doaj_boom(url):
        if "doaj.org" in url:
            raise urllib.error.URLError("offline")
        return fetch(url)
    rep_d = assemble("1234-5678", "", card, doaj_boom)
    assert rep_d["whitelist"]["doaj"]["status"] == "unavailable", rep_d["whitelist"]["doaj"]
    assert rep_d["whitelist"]["doaj"]["in_doaj"] is None, rep_d["whitelist"]["doaj"]

    # 降级路径：无卡 + 无作者 → 信号3/4 unavailable，不崩
    rep2 = assemble("1234-5678", "", None, fetch)
    assert rep2["signals"]["3_review_cycle"]["status"] == "unavailable"
    assert rep2["signals"]["4_author_match"]["status"] == "unavailable"
    assert rep2["signals"]["1_volume_trend"]["status"] == "ok"

    # source 取数失败 → venue fetch_error，信号不崩
    def boom(url):
        raise urllib.error.URLError("offline")
    rep3 = assemble("1234-5678", "", card, boom)
    assert rep3["signals"]["1_volume_trend"]["status"] == "unavailable"
    assert rep3["signals"]["3_review_cycle"]["status"] == "ok"  # 卡信号不依赖网络

    # venue 卡 risk_note 锚点/口径解析
    sub = _parse_risk_subfields("CCF等级=A; oa_id=S4363607701; issn=0162-8828; "
                                "domain_scope=中国CS; if_kind=jcr")
    assert sub == {"oa_id": "S4363607701", "issn": "0162-8828",
                   "domain_scope": "中国CS", "if_kind": "jcr"}, sub

    # if_kind=jcr → caveat 标"权威值"；proxy → 标"非 JCR 真值"
    card_jcr = dict(card, _subfields={"if_kind": "jcr", "domain_scope": "中国CS"},
                    impact_factor="18.6(JCR2024,LetPub journalid=3411)")
    s5j = signal_apc_quartile(card_jcr, _MockFetcher._source())
    assert s5j["if_kind"] == "jcr" and "权威" in s5j["if_caveat"], s5j
    card_proxy = dict(card, _subfields={"if_kind": "proxy"},
                      impact_factor="OpenAlex 2yr均被引=4.2作替代")
    s5p = signal_apc_quartile(card_proxy, _MockFetcher._source())
    assert s5p["if_kind"] == "proxy" and "非 JCR" in s5p["if_caveat"], s5p
    assert "openalex_2yr_mean_citedness_live" in s5p, "proxy 应附在线 2yr 值供交叉验证"

    # 挂接 _shared/semantic_sim 验证：契约可 import 且实际被调用（治 dead import）。
    # 倒装/词序敏感性由 semantic_sim 自身 selftest 保证；此处验证本脚本确实经它打分。
    assert _SEMSIM_OK, "应能 import _shared/semantic_sim（同仓地基契约）"
    assert s6["sim_engine"].startswith("semantic_sim:"), s6["sim_engine"]
    # _sim 经语义引擎对"machine learning"与"Machine Learning"给高分（非 0）
    assert _sim("machine learning", "Machine Learning") > 0.5
    s6_official = signal_manuscript_fit(
        _MockFetcher._source(), "Reproducible research software", "", ["research software"],
        ["research software", "reproducibility", "open source"],
    )
    assert s6_official["scope_source"] == "current_official_scope"
    assert s6_official["match_level"] in ("高", "中")

    print("[selftest] PASS venue_signal（7 信号 + 稿件契合 + 作者分位 + 降级 + "
          "离线 + if_kind口径 + 锚点解析 + semantic_sim 挂接）")
    return 0


def _parse_card_fields(pairs: list[str]) -> dict | None:
    if not pairs:
        return None
    card = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            card[k.strip()] = v.strip()
    return card or None


def _batch_recheck(csv_path: str, fetch, limit: int = 0, only_stale_days: int = 0) -> dict:
    """全库 batch 复查：逐行按 issn/oa_id 锚点查 OpenAlex，对比本地快照，产 diff 清单。
    仅复查有锚点的行；无锚点行计入 skipped。only_stale_days>0 时只查 last_checked 超期行。"""
    try:
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError as e:
        return {"status": "error", "reason": str(e)}
    diffs, no_anchor, checked, errors = [], 0, 0, 0
    for row in rows:
        sub = _parse_risk_subfields(row.get("risk_note", ""))
        issn = sub.get("issn")
        if not issn:
            no_anchor += 1
            continue
        if limit and checked >= limit:
            break
        try:
            src = oa_source_by_issn(issn, fetch)
            checked += 1
        except Exception:  # noqa: BLE001
            errors += 1
            continue
        if not src:
            continue
        live_2yr = ((src.get("summary_stats") or {}).get("2yr_mean_citedness"))
        diffs.append({
            "venue": row.get("venue_name"), "issn": issn,
            "if_kind": sub.get("if_kind"),
            "local_impact_factor": row.get("impact_factor", "")[:60],
            "openalex_2yr_live": round(live_2yr, 2) if live_2yr is not None else None,
            "openalex_works_count": src.get("works_count"),
            "local_last_checked": row.get("last_checked_date"),
            "note": "if_kind=jcr 时本地为权威真值不被覆盖；proxy 时以在线 2yr 为准复核",
        })
    return {"status": "ok", "total_rows": len(rows), "checked": checked,
            "no_anchor_skipped": no_anchor, "fetch_errors": errors, "diffs": diffs}


def main() -> None:
    global _MAILTO, _API_KEY
    ap = argparse.ArgumentParser(description="投稿 venue 多信号对照查询（7 信号）")
    ap.add_argument("--issn", default="", help="期刊 ISSN（信号1/2/5/6/7 主键）")
    ap.add_argument("--author", default="", help="作者姓名（信号4/7，重名需 ORCID 排歧）")
    ap.add_argument("--venues-csv", default="",
                    help="用户给的 venue 卡 CSV 路径（薄缓存，非内嵌库），按 ISSN/刊名取卡")
    ap.add_argument("--card-fields", nargs="*", default=[],
                    help="内联 venue 卡字段，如 review_cycle='8周' apc_fee='1800 USD' "
                         "scope_keywords='research software|reproducibility'（必须来自当天官方 scope）")
    ap.add_argument("--title", default="", help="稿件标题（信号6 稿件→venue 语义契合）")
    ap.add_argument("--abstract", default="", help="稿件摘要（信号6；可接 paper-writing 的 draft.md 摘要段）")
    ap.add_argument("--keywords", nargs="*", default=[],
                    help="稿件关键词（信号6 主匹配项，优先于标题/摘要抽词）")
    ap.add_argument("--mailto", default="",
                    help="OpenAlex 礼貌池邮箱(也可设环境变量 OPENALEX_MAILTO)；不传则匿名查")
    ap.add_argument("--api-key", default="",
                    help="OpenAlex 免费 API key(也可设环境变量 OPENALEX_API_KEY)；2026-02-13 起需 key，"
                         "口径见 literature-search references；不传则匿名查(灰度期或仍可,不保证)")
    ap.add_argument("--batch", default="",
                    help="全库复查模式：传 venues.csv 路径，逐行按锚点查 OpenAlex 产 diff 清单")
    ap.add_argument("--batch-limit", type=int, default=0, help="batch 复查行数上限(0=全部)")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--selftest", action="store_true", help="离线 mock 自测")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if args.mailto:
        _MAILTO = args.mailto.strip()
    if args.api_key:
        _API_KEY = args.api_key.strip()

    if args.batch:
        rep = _batch_recheck(args.batch, http_fetch, limit=args.batch_limit)
        text = json.dumps(rep, ensure_ascii=False, indent=2)
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                f.write(text)
        print(text)
        if rep.get("status") == "ok":
            print(f"\n[BATCH] checked={rep['checked']} no_anchor={rep['no_anchor_skipped']} "
                  f"errors={rep['fetch_errors']}", file=sys.stderr)
        return

    if not args.issn and not args.author and not (args.title or args.abstract or args.keywords):
        ap.error("至少提供 --issn / --author / 稿件文本(--title/--abstract/--keywords) 其一"
                 "（或 --batch / --selftest）")

    card = _parse_card_fields(args.card_fields)
    if card is None and args.venues_csv:
        card = _load_card_from_csv(args.issn, args.author, args.venues_csv)

    report = assemble(args.issn, args.author, card, http_fetch,
                      title=args.title, abstract=args.abstract, keywords=args.keywords)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    s = report["summary"]
    print(f"\n[SUMMARY] signals_ok={s['signals_ok']}/{s['signals_total']}", file=sys.stderr)


if __name__ == "__main__":
    main()
