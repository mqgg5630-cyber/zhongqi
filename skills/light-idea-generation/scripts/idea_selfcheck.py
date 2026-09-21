#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""idea_selfcheck.py — idea-generation 自查门 producer（撞车前置自查 + 防伪多样 + 反 frame-lock → findings）。

蓝图 §4.3-3 的"及格线":提 idea 时就**自带撞车前置自查**(最像的前作 + facet delta),不等 idea-critique
才发现;且强制多角度、防伪多样。本脚本把三件自查**编排成机读 findings**接 _shared,被总控
run_checkpoint --stage 3 聚合,与 stage 4 idea-critique 构成 3⇄4 回环。

三件自查(全 warn——这是**信号/自查门**,不是 critical 否决；novel/无创新的一票否决判决归 idea-critique，
对齐 Si et al(2409.04109)实测"LLM 不能可靠自评 idea 质量"):
  ① 撞车前置自查(collision)：**直接吃上游 literature-search 的领域地图**(--domain-map 它的 --json-out)，
     对每个候选 idea 用 _shared/semantic_sim 找"最像的那一篇" + facet 槽位(application_domain/purpose/
     mechanism/evaluation 留空，给 idea-critique 拆 delta)。最像≠撞车，novel 判决不自做。
  ② 防伪多样(pseudo_diversity)：复用 candidate_dedup(接 semantic_sim) 标"疑似变体对"=换皮凑数。
  ③ 反 frame-lock(frame_lock)：复用 provocation_gen.coverage 报 7 角度与数量 advisory；
     机制覆盖硬门由 idea_genealogy.py 负责。

诚实约定(名实对齐见 SKILL):
- 不下 novel/not-novel 判决(归 idea-critique);只产 warn 信号 + facet 待拆 + 启发式自检。
- 离线 semantic_sim 跨语言弱(中文 idea↔英文标题低分)——撞车演示用同语言;真跨语言注入 embedding 档。
- 无 prior-work 池(未给 --domain-map/--papers)时撞车自查诚实 skip,不假装查过。
- _shared 不可达时 findings 诚实降级为 None(不假装产机读交接)。

用法：
  # 吃上游 literature-search 的领域地图(它先 --json-out dmap.json)：
  python idea_selfcheck.py --in candidates.json --domain-map dmap.json --report findings.json
  python idea_selfcheck.py --in candidates.json --papers papers.json   # 直接给 prior-work 池
  python idea_selfcheck.py --selftest
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

# 同目录兄弟脚本（复用不重造：provocation 覆盖门、dedup 伪多样）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import provocation_gen as pg          # noqa: E402
import candidate_dedup as cdd         # noqa: E402

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

# facet 槽位：对齐 literature-search detect_collision / Idea Novelty Checker 四 facet（留空给下游拆 delta）
_FACET_SLOTS = {"application_domain": "", "purpose": "", "mechanism": "", "evaluation": ""}


def _idea_text(c: dict) -> str:
    return f"{c.get('title','')} {c.get('claim','') or c.get('novelty','')}".strip()


def _paper_text(p: dict) -> str:
    return ((p.get("title") or "") + ". " + " ".join((p.get("abstract") or "").split()[:60])).strip()


def _lexical(a: str, b: str) -> float:
    """_shared 不可达时的纯词面降级（与 domain_map 同口径，易漏纯同义）。"""
    qa = set(re.findall(r"[a-z0-9]+|[一-鿿]", a.lower()))
    ta = set(re.findall(r"[a-z0-9]+|[一-鿿]", b.lower()))
    return round(len(qa & ta) / len(qa | ta), 3) if (qa | ta) else 0.0


def papers_from_domain_map(dmap: dict) -> list:
    """从 literature-search 的领域地图 JSON(--json-out) 抽 prior-work 池(三层 records 去重)。"""
    layers = dmap.get("layers") or {}
    recs = []
    for key in ("frontier", "classic"):
        recs += (layers.get(key) or {}).get("records") or []
    cross = layers.get("cross")
    if cross:
        recs += (cross.get("method") or {}).get("records") or []
    # 去重（按 doi 或 标题）
    seen, out = set(), []
    for r in recs:
        k = (r.get("doi") or "") or (r.get("title") or "")
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


# ───────────────────────── 三件自查 ─────────────────────────
def collision_selfcheck(candidates: list, papers: list, *, top_k: int = 3, mode: str = "auto") -> dict:
    """对每个候选 idea 找最像的前作 + facet 槽位。不下 novel 判决（归 idea-critique）。"""
    if not papers:
        return {"per_idea": [], "sim_mode": "n/a",
                "note": "未提供 prior-work 池(--domain-map/--papers):撞车前置自查跳过,不假装查过。"}
    degraded = _semsim is None
    ptexts = [_paper_text(p) for p in papers]
    per_idea = []
    for c in candidates:
        itext = _idea_text(c)
        scored = []
        for p, pt in zip(papers, ptexts):
            s = _lexical(itext, pt) if degraded else _semsim.similarity(itext, pt, mode=mode)
            scored.append((float(s), p))
        scored.sort(key=lambda x: -x[0])
        top = [{"similarity": round(s, 3), "title": (p.get("title") or "")[:100],
                "year": p.get("year"), "doi": p.get("doi") or "unknown",
                "facet_overlap_slots": dict(_FACET_SLOTS)} for s, p in scored[:top_k]]
        per_idea.append({"id": c.get("id", "?"), "idea": itext[:120], "most_similar": top})
    used = "lexical_only(_shared不可达)" if degraded else (_semsim.last_mode() if _semsim else "n/a")
    return {"per_idea": per_idea, "sim_mode": used,
            "note": "相似度为语义相似启发式;**最像≠撞车**,novel/not-novel 判决归 idea-critique(target/"
                    "background 分解)。facet 槽位留下游拆 delta。"
                    + (" [降级] _shared 不可达,退化纯词面,易漏纯同义。" if degraded else "")}


# ───────────────────────── gate 函数（接 _shared） ─────────────────────────
def _collision_gate_fn(art: dict) -> "GateResult":
    coll = art["collision"]
    per = coll.get("per_idea") or []
    if not per:
        return GateResult("idea_collision", "skip", "info", [],
                          note=coll.get("note", "撞车前置自查跳过。"))
    findings = []
    for e in per:
        top = (e.get("most_similar") or [{}])[0]
        if not top:
            continue
        sim = top.get("similarity", 0.0)
        hot = "（高度疑似撞车,务必交 idea-critique 复核）" if sim >= 0.5 else ""
        findings.append(Finding(
            loc=f"{e['id']}→{top.get('doi','unknown')}",
            issue=f"候选「{e['id']}」最像前作:「{top.get('title','')}」({top.get('year')}) 语义相似={sim}{hot}",
            fix="提出时即带'最像前作+delta':沿 application_domain/purpose/mechanism/evaluation 拆;"
                "撞车一票否决判决归 idea-critique,本门只预警。",
            evidence=f"sim_mode={coll.get('sim_mode')}; facet 槽位见 collision.per_idea",
            rule="collision.semantic_sim"))
    return GateResult("idea_collision", "warn", "major", findings,
                      note="撞车前置自查(warn):每候选的最像前作+facet 槽位喂 idea-critique;novel 判决归下游,本门不阻断。")


def _diversity_gate_fn(art: dict) -> "GateResult":
    dd = art["dedup"]
    variants = dd.get("suspected_variants") or []
    if not variants:
        return GateResult("pseudo_diversity", "pass", "info", [],
                          note=f"无显著高于均值的相似对(mode={dd.get('mode')}):候选多样性 OK。")
    findings = [Finding(
        loc=f"{p['a']}↔{p['b']}",
        issue=f"疑似换皮变体对:{p['a']} ↔ {p['b']} 相似度={p['sim']} ≥ 批内阈值={dd.get('threshold')}",
        fix="合并为一条或回 provocation_gen 重发散——别拿同一 idea 的变体凑数(伪多样)。",
        evidence=f"mode={dd.get('mode')}; mean={dd.get('mean_sim')} std={dd.get('std_sim')}",
        rule="diversity.semantic_sim") for p in variants]
    return GateResult("pseudo_diversity", "warn", "major", findings,
                      note="防伪多样(warn):semantic_sim 标'疑似变体对';提示人工合并,不自动删,不阻断。")


def _framelock_gate_fn(art: dict) -> "GateResult":
    cov = art.get("coverage")
    if cov is None:
        return GateResult("frame_lock", "skip", "info", [],
                          note="候选未带 angle 标签:反 frame-lock 覆盖自查跳过。")
    errs, warns = cov.get("errors") or [], cov.get("warnings") or []
    if not errs and not warns:
        return GateResult("frame_lock", "pass", "info", [],
                          note=f"7 角度覆盖 + 总量≥{cov.get('min_total')}:发散面够宽,无 frame-lock。")
    findings = []
    for e in errs:
        findings.append(Finding(loc="divergence", issue=e,
                                fix="回 provocation_gen --seed 补缺失角度再收敛;frame-lock 是自查警示,非阻断。",
                                rule="frame_lock.coverage"))
    for w in warns:
        findings.append(Finding(loc="divergence", issue=w,
                                fix="补其余角度均衡发散。", rule="frame_lock.coverage"))
    sev = "major" if errs else "minor"
    return GateResult("frame_lock", "warn", sev, findings,
                      note="反 frame-lock(warn):某角度0/总量不足=发散面窄;非阻断,只提示回去补激发算子。")


def emit_findings(collision: dict, dedup: dict, coverage: dict | None, *, direction: str):
    """产 light.findings.v1（producer=idea-generation，warn 为主）。无 _shared 则诚实降级 None。"""
    if not _SHARED_OK:
        return None
    art = {"collision": collision, "dedup": dedup, "coverage": coverage}
    return run_gates([_collision_gate_fn, _diversity_gate_fn, _framelock_gate_fn], art,
                     producer="idea-generation", target=direction,
                     summary="idea-generation 自查门:撞车前置自查(warn)+防伪多样(warn)+反 frame-lock(warn);"
                             "critical 撞车/无创新一票否决归 idea-critique(stage 4)。",
                     fresh_evidence=True)


# ───────────────────────── 编排入口 ─────────────────────────
def build(candidates: list, *, papers: list | None = None, direction: str = "",
          min_total: int = 15) -> dict:
    papers = papers or []
    collision = collision_selfcheck(candidates, papers)
    dedup = cdd.dedup(candidates)
    # 覆盖自查仅在候选带 angle 标签时有意义；否则诚实置 None → gate skip
    has_angle = any((c.get("angle") or "").strip() for c in candidates)
    coverage = pg.coverage(candidates, min_total) if has_angle else None
    report = emit_findings(collision, dedup, coverage, direction=direction)
    return {"direction": direction, "n_candidates": len(candidates),
            "collision": collision, "dedup": dedup, "coverage": coverage,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# idea-generation 自查门：{result.get('direction') or '(未命名方向)'}", "",
             f"候选 {result['n_candidates']} 条。三件自查全 warn(信号门)——撞车/无创新的一票否决归 idea-critique。", ""]
    # 撞车
    coll = result["collision"]
    lines += ["## ① 撞车前置自查（最像的前作 → 喂 idea-critique）", "", coll.get("note", ""), ""]
    for e in coll.get("per_idea", []):
        top = (e.get("most_similar") or [{}])[0]
        if top:
            lines.append(f"- {e['id']}：最像 sim={top.get('similarity')} · {top.get('title')} ({top.get('year')}) · {top.get('doi')}")
    # 伪多样
    dd = result["dedup"]
    lines += ["", "## ② 防伪多样（疑似换皮变体对）", ""]
    if dd.get("suspected_variants"):
        for p in dd["suspected_variants"]:
            lines.append(f"- {p['a']} ↔ {p['b']}：相似度 {p['sim']} ≥ 阈值 {dd.get('threshold')}")
    else:
        lines.append("无显著高于均值的相似对——多样性 OK。")
    # frame-lock
    cov = result["coverage"]
    lines += ["", "## ③ 反 frame-lock（7 角度覆盖）", ""]
    if cov is None:
        lines.append("_候选未带 angle 标签，跳过覆盖自查。_")
    else:
        for a in pg.ANGLES:
            lines.append(f"- {a}: {cov['counts'][a]}" + (" ⚠️空" if cov['counts'][a] == 0 else ""))
        for e in cov.get("errors", []):
            lines.append(f"- [warn] {e}")
    if result.get("findings"):
        lines += ["", f"> findings: light.findings.v1 verdict={result['findings']['verdict']} "
                  f"(producer=idea-generation)；run_checkpoint --stage 3 聚合。"]
    return "\n".join(lines)


# ───────────────────────── selftest（离线，确定性） ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 同语言 fixture（撞车演示用英文：离线 semantic_sim 跨语言弱，见诚实约定）。
    # I-01 / I-02 是换皮变体（防伪多样应抓）；I-03 与前两者无关。
    cands = [
        {"id": "I-01", "title": "Self-supervised contrastive learning for dairy goat estrus detection",
         "claim": "temporal contrastive model on accelerometer streams", "angle": "method-transfer",
         "impact": 4, "effort": 4, "novelty": 4, "feasibility": 3},
        {"id": "I-02", "title": "Contrastive self-supervised goat estrus behaviour recognition",
         "claim": "temporal contrastive accelerometer model self supervised", "angle": "method-transfer",
         "impact": 4, "effort": 3, "novelty": 3, "feasibility": 3},
        {"id": "I-03", "title": "Graph neural networks for protein structure prediction",
         "claim": "GNN protein folding", "angle": "gap-driven",
         "impact": 5, "effort": 5, "novelty": 5, "feasibility": 2},
    ]
    papers = [
        {"title": "Self-supervised contrastive learning for goat estrus detection from accelerometers",
         "abstract": "contrastive learning temporal accelerometer estrus", "year": 2023, "doi": "10.1/a"},
        {"title": "Graph neural networks for protein folding prediction",
         "abstract": "graph neural network protein structure", "year": 2021, "doi": "10.1/b"},
    ]
    res = build(cands, papers=papers, direction="dairy goat estrus detection")

    # 1. 撞车前置自查：每候选有最像前作；I-03 最像应是 protein 那篇
    per = {e["id"]: e for e in res["collision"]["per_idea"]}
    check(len(per) == 3, "应对 3 候选各做撞车自查")
    check(per["I-03"]["most_similar"][0]["doi"] == "10.1/b", "I-03 最像应是 protein GNN 篇")
    check(per["I-01"]["most_similar"][0]["doi"] == "10.1/a", "I-01 最像应是 goat estrus 篇")
    check("facet_overlap_slots" in per["I-01"]["most_similar"][0], "撞车候选应带 facet 槽位")

    # 2. 防伪多样：I-01↔I-02 换皮应被标变体
    vps = {(p["a"], p["b"]) for p in res["dedup"]["suspected_variants"]}
    check(("I-01", "I-02") in vps, f"I-01↔I-02 换皮应被标变体: {res['dedup']['suspected_variants']}")

    # 3. 反 frame-lock：3 候选 <15 且角度缺 → advisory warnings，不凭形式阈值阻断
    check(
        res["coverage"] is not None
        and res["coverage"]["passed"]
        and bool(res["coverage"]["warnings"]),
        "小样本应触发 frame-lock advisory",
    )

    # 4. findings 接 _shared：light.findings.v1 合法、verdict=warn、三门齐、无 critical
    if _SHARED_OK:
        rep = res["findings"]
        check(rep is not None and rep["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(rep["producer"] == "idea-generation", "producer 应为 idea-generation")
        check(rep["verdict"] == "warn", f"自查门应 warn(无 critical),实得 {rep.get('verdict')}")
        gates = {g["gate"] for g in rep["gates"]}
        check({"idea_collision", "pseudo_diversity", "frame_lock"} <= gates, f"应含三门,实得 {gates}")
        # 撞车门 warn 非 critical（novel 判决归 idea-critique）
        cg = next(g for g in rep["gates"] if g["gate"] == "idea_collision")
        check(cg["status"] == "warn" and cg["severity"] != "critical", "撞车门应 warn 非 critical")
        # round-trip
        rt = FindingsReport.from_json(json.dumps(rep, ensure_ascii=False))
        check(rt.producer == "idea-generation", "findings JSON 应可往返")
    else:
        check(res["findings"] is None, "_shared 不可达时 findings 应诚实为 None")

    # 5. 吃上游领域地图：papers_from_domain_map 能从 literature-search --json-out 抽 prior-work 池
    dmap = {"layers": {"frontier": {"records": [papers[0]]}, "classic": {"records": [papers[1]]},
                       "cross": None}}
    pool = papers_from_domain_map(dmap)
    check(len(pool) == 2, f"应从领域地图三层抽出 2 篇 prior-work,实得 {len(pool)}")

    # 6. 无 papers：撞车自查诚实 skip
    res2 = build(cands, papers=None, direction="x")
    check(not res2["collision"]["per_idea"], "无 prior-work 池撞车自查应跳过")
    if _SHARED_OK:
        cg2 = next(g for g in res2["findings"]["gates"] if g["gate"] == "idea_collision")
        check(cg2["status"] == "skip", "无 prior-work 时撞车门应 skip")

    # 7. markdown 不崩
    check("撞车前置自查" in to_markdown(res), "markdown 应含撞车节")

    if failures:
        print("[SELFTEST][idea_selfcheck] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][idea_selfcheck] OK：撞车前置自查 + 防伪多样 + 反 frame-lock + findings(warn) 全通过。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="idea-generation 自查门 producer（撞车前置自查+防伪多样+反 frame-lock）")
    ap.add_argument("--in", dest="infile", help="候选 idea JSON 数组")
    ap.add_argument("--domain-map", help="literature-search 领域地图 JSON(--json-out),抽 prior-work 池")
    ap.add_argument("--papers", help="prior-work 池 JSON 数组(直接给,替代 --domain-map)")
    ap.add_argument("--direction", default="", help="研究方向(findings target)")
    ap.add_argument("--min-total", type=int, default=15, help="发散数量建议值(默认 15)")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整自查 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.infile:
        ap.error("需要 --in candidates.json(或 --selftest)")

    with open(args.infile, encoding="utf-8") as f:
        candidates = json.load(f)
    papers = []
    if args.papers:
        with open(args.papers, encoding="utf-8") as f:
            papers = json.load(f)
    elif args.domain_map:
        with open(args.domain_map, encoding="utf-8") as f:
            papers = papers_from_domain_map(json.load(f))

    result = build(candidates, papers=papers, direction=args.direction, min_total=args.min_total)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整自查 → {args.json_out}", file=sys.stderr)
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
