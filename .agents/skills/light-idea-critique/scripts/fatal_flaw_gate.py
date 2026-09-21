#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fatal_flaw_gate.py — idea-critique 的 **critical 否决门 producer**（撞车/无创新一票否决 → findings）。

蓝图 §4.3-4 + orchestrator-spec §4.2 的"及格线"：idea 阶段 Critical = **撞车/无创新(fatal flaw 一票否决)**。
本脚本把三件**严审判据**编排成机读 `light.findings.v1`(producer=**idea-critique**，**critical**)，被总控
`run_checkpoint --stage 4` 聚合 → **Critical fail exit 1**，`reroute` 建议回边 **4→3**(带"具体缺口 + 最像前作")，
与 stage 3 idea-generation 构成 **3⇄4 双向回环**。

这是 **v2 净新增的接线**（与 gen 的 `idea_selfcheck.py` 同构）：v1 的否决引擎(score_aggregate/novelty_audit/
sycophancy_guard)**全部零接 `_shared`/`light.findings.v1`**(grep 实证)——本脚本是把它们接成 critical findings
producer 的新增层，**不重造**否决/撞车/反谄媚逻辑(复用同目录港来的脚本)。

三件严审 → 三个 gate：
  ① collision(critical)：**吃 gen `idea_selfcheck` 的 most_similar + facet 槽位**(留空)，idea-critique **填实**
     target_equivalent + stance → 港来的 `novelty_audit._derive_collision_level`(GraphMind target/background 分解)：
     target 层等价+supporting = **same(真撞车)** → 创新性<45 block；target 不等价 = unrelated(仅共享背景**不误判**)。
     **直接消费 `_shared/semantic_sim`** 复核 idea↔最像前作相似度(留痕 sim_mode)，不只信 gen 自报。
  ② fatal_flaw(critical)：港来的 `score_aggregate.decide` 八维加权 + **确定性否决闸门**(创新性<gate_fatal /
     核心两维<gate_fatal / NOVELTY-PRIOR-CONFLICT)——一个 fatal flaw **不被其他高维度平均救回**。撞车命中时
     创新性封到 block 档(<45)再聚合，否决从文档化的否决引擎路径出，名实一致。
  ③ anti_sycophancy(warn)：港来的 `sycophancy_guard.audit`(让步无证据强制降3 / concession-rate>50% 或小N绝对
     门限报警 / 连续让步 autonomous 自动降级)——抓"对作者反复反驳过度顺从把弱 idea 放行"。**warn**(软门，
     提示人工复核)，不阻断推进；真阻断由 collision/fatal_flaw 两 critical 门负责。

诚实约定(名实对齐见 SKILL，铁律 2/3)：
- **可计算闸门是先验非真值**：八维分须由逐卡完整严审(盲审/检索/五视角/反谄媚)得出，本脚本只**聚合判据 + 出
  critical findings**，不替你判 idea 真新不新(Si et al 2409.04109 实测 LLM 不能可靠自评 idea)。
- **撞车判定吃上游 + 人填 facet**：gen 给"最像前作"(感觉像)，idea-critique 填 target_equivalent/stance 做可追溯
  判定；GIGO——检索覆盖不全(literature-search 漏最像那篇)会漏判，novelty_audit 只勾稽"结论与自己的证据自洽"。
- **离线 semantic_sim 跨语言弱**：中文 idea↔英文标题低分(撞车演示用同语言；真跨语言注入 embedding 档)。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法：
  # 吃 gen idea_selfcheck 的 --json-out(most_similar+facet 槽位) + 本技能的 facet 决策/八维分：
  python fatal_flaw_gate.py --critique critique_input.json --gen-selfcheck gen.json --report findings.json
  python fatal_flaw_gate.py --critique critique_input.json --report findings.json   # 不吃 gen，自带 most_similar
  python fatal_flaw_gate.py --selftest
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 同目录港来的否决引擎（复用不重造：撞车分解 / 否决聚合 / 反谄媚）。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import novelty_audit as na           # noqa: E402  target/background 撞车分解 + 一致性勾稽
import score_aggregate as sa         # noqa: E402  八维加权 + 确定性否决闸门 + decision mapping
import sycophancy_guard as sg        # noqa: E402  反谄媚 concession-rate

# 规范 bootstrap（_shared/README.md）：向上走目录树找含 _shared 包的仓库根，治硬编码 parents[N] 之脆。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared import semantic_sim as _semsim                                  # noqa: E402
    from _shared.findings_schema import Finding, GateResult, FindingsReport      # noqa: E402
    from _shared.gate_runner import run_gates                                    # noqa: E402
    _SHARED_OK = True
except ImportError:                                                             # _shared 不可达：findings 降级
    _semsim = None
    _SHARED_OK = False

# 撞车命中(same)时把创新性封到 block 档(<gate_fatal=45)，让否决从 score_aggregate 文档化的否决引擎路径出。
_BLOCK_ORIGINALITY = 40
# facet 槽位（与 gen idea_selfcheck / Idea Novelty Checker 四 facet 对齐；idea-critique 在此填 delta）
_FACETS = ("application_domain", "purpose", "mechanism", "evaluation")


# ───────────────────────── 吃上游 gen idea_selfcheck ─────────────────────────
def gen_most_similar(gen_data: dict, idea_id: str) -> list:
    """从 gen `idea_selfcheck.py --json-out` 抽某候选的 most_similar(最像前作 + facet 槽位，槽位留空)。

    gen 输出形如 {"collision": {"per_idea": [{"id","idea","most_similar":[{similarity,title,year,doi,
    facet_overlap_slots}]}]}}。本函数取目标 idea 的 most_similar 列表(感觉像)，交 idea-critique 填实 facet。"""
    per = ((gen_data or {}).get("collision") or {}).get("per_idea") or []
    for e in per:
        if str(e.get("id")) == str(idea_id):
            return e.get("most_similar") or []
    return []


def merge_most_similar(critique_ms: list, gen_ms: list) -> list:
    """合并：以 gen 的 most_similar(感觉像)为底，叠 idea-critique 的 facet 决策(target_equivalent/stance/delta)。
    匹配键 = doi(优先)否则 title。critique 端补充的前作(gen 没给)也并入。"""
    by_key = {}
    for m in gen_ms or []:
        k = (m.get("doi") or "") or (m.get("title") or "")
        by_key[k] = dict(m)
    for c in critique_ms or []:
        k = (c.get("doi") or "") or (c.get("title") or "")
        base = by_key.get(k, {})
        base.update({kk: vv for kk, vv in c.items() if vv is not None})
        by_key[k] = base
    return list(by_key.values())


# ───────────────────────── 撞车 → novelty_audit 论断（吃 facet 槽位）─────────────────────────
def _verify_sim(idea_text: str, title: str, mode: str = "auto") -> tuple:
    """直接消费 _shared/semantic_sim 复核 idea↔最像前作(不只信 gen 自报)。返回 (sim, mode)。"""
    if _semsim is None or not idea_text or not title:
        return (None, "n/a")
    s = _semsim.similarity(idea_text, title, mode=mode)
    return (round(float(s), 3), _semsim.last_mode())


def build_collisions(idea_text: str, most_similar: list) -> tuple:
    """把(已填 facet 决策的) most_similar 转 novelty_audit 的 collisions，并直接复核 semantic_sim。
    返回 (collisions, sim_mode, verified[])。target_equivalent/stance 由 idea-critique 填(GraphMind 分解)。"""
    collisions, verified = [], []
    sim_mode = "n/a"
    for m in most_similar or []:
        ref = m.get("doi") or m.get("title") or "?"
        sim, mode = _verify_sim(idea_text, m.get("title") or "")
        if mode != "n/a":
            sim_mode = mode
        verified.append({"ref": ref, "title": (m.get("title") or "")[:90],
                         "gen_similarity": m.get("similarity"), "critique_verified_sim": sim})
        col = {"ref": ref, "level": m.get("level"), "delta": m.get("delta", "")}
        # facet 决策(idea-critique 填实空槽)：target/background 分解 + 引用立场
        if m.get("target_equivalent") is not None:
            col["target_equivalent"] = m.get("target_equivalent")
        if m.get("stance"):
            col["stance"] = m.get("stance")
        collisions.append(col)
    return collisions, sim_mode, verified


def build_audit_data(idea_id: str, idea_text: str, most_similar: list,
                     declared_novelty: str, evidence_sources: list) -> tuple:
    """组装单论断的 novelty_audit 输入(四阶段留痕)。evidence_sources=检索过的库(覆盖度勾稽)。"""
    collisions, sim_mode, verified = build_collisions(idea_text, most_similar)
    evidence = [{"source": s, "http": 200} for s in (evidence_sources or [])]
    claim = {"id": idea_id, "declared_novelty": declared_novelty,
             "evidence": evidence, "collisions": collisions}
    return {"claims": [claim]}, sim_mode, verified


# ───────────────────────── 三个 gate 函数（接 _shared） ─────────────────────────
def _collision_top(rep: dict, verified: list) -> dict:
    """选**触发 same 撞车**的那条前作作证据指针(优先 decomposed=target_equivalent 填实的)，
    而非 merge 顺序的 verified[0]。治：gen 的离线 semantic_sim 是词面启发式，most_similar 可能 mis-rank
    (活体 E2E 实测——把 'Amharic legal QA' 排在真撞车 'Heart Failure RAG MQA' 之前)；若 reroute 的
    '最像前作'指向 verified[0] 会把回炉引向**错误**的前作。无 same 时退回 verified[0]。"""
    same_refs = []
    for claim in rep.get("claims", []) or []:
        for c in claim.get("collisions", []) or []:
            if c.get("derived_level") == "same":
                same_refs.append((c.get("ref"), bool(c.get("decomposed"))))
    same_refs.sort(key=lambda x: (not x[1],))    # decomposed(target_equivalent 填实)的 same 优先
    for ref, _ in same_refs:
        for v in verified:
            if v.get("ref") == ref:
                return v
    return verified[0] if verified else {}


def _collision_gate_fn(art: dict) -> "GateResult":
    """撞车门(critical)：吃 gen most_similar + idea-critique 填的 facet → novelty_audit 可追溯判定。"""
    rep = art["novelty_report"]
    hooks = rep.get("verdict_hooks", {})
    verified = art["verified"]
    sim_mode = art["sim_mode"]
    block = hooks.get("trigger_originality_block") or hooks.get("trigger_target_collision")
    underclaim = hooks.get("trigger_collision_underclaim")
    # 取**触发 same 撞车**的前作作证据指针(供 reroute 出"最像的前作"，非 merge 顺序 verified[0])
    top = _collision_top(rep, verified)
    loc = f"{art['idea_id']}→{top.get('ref', 'unknown')}"
    if block:
        findings = [Finding(
            loc=loc,
            issue=f"撞车一票否决：「{art['idea_id']}」最像前作「{top.get('title', '')}」"
                  f"(gen_sim={top.get('gen_similarity')}, 复核 sim={top.get('critique_verified_sim')})"
                  f" target 层等价+supporting → same 撞车，创新性<45 block。",
            fix="回 idea-generation(4→3)带具体缺口重提：换 target(解决的新问题)/换 mechanism，"
                "或据 contrasting 立场把 delta 拆到方法层(非仅换数据集)。",
            evidence=f"sim_mode={sim_mode}; novelty_audit target/background 分解(GraphMind); "
                     f"flags={[f['code'] for f in rep.get('flags', [])]}",
            rule="collision.same.block")]
        # 漏判补刀：自报 unrelated 但 target 等价
        if underclaim:
            findings.append(Finding(loc=loc, issue="自报 unrelated 但 target 层等价+supporting=漏判撞车",
                                    fix="升 same 并触发 block", rule="collision.underclaim"))
        return GateResult("collision", "fail", "critical", findings,
                          note="撞车可追溯判定(GraphMind target/background)：same 撞车=fatal flaw 一票否决。")
    # 非 same：extension/单库/缺 delta → warn(非阻断)；全 unrelated/novel → pass
    warn_flags = [f for f in rep.get("flags", []) if f["severity"] in ("high", "warn")]
    if warn_flags:
        findings = [Finding(loc=f"{art['idea_id']}", issue=f["msg"], fix="补 delta/补检索交叉验证",
                            rule=f["code"]) for f in warn_flags]
        return GateResult("collision", "warn", "major", findings,
                          note=f"未判 same 撞车，但有增量/覆盖警示(overall={rep.get('overall_novelty')})。")
    return GateResult("collision", "pass", "info", [],
                      note=f"target/background 分解未命中 same 撞车(overall={rep.get('overall_novelty')})；"
                           f"sim_mode={sim_mode}。")


def _fatal_flaw_gate_fn(art: dict) -> "GateResult":
    """无创新一票否决门(critical)：score_aggregate 八维加权 + 确定性否决闸门(高均值救不回 fatal flaw)。"""
    scores = art["scores"]
    if not scores:
        return GateResult("fatal_flaw", "skip", "info", [],
                          note="未提供八维严审分(scores)：无创新否决门跳过(须先逐卡完整严审)。")
    rep = art["novelty_report"]
    hooks = rep.get("verdict_hooks", {})
    collision_block = hooks.get("trigger_originality_block") or hooks.get("trigger_target_collision")
    scores_eff = dict(scores)
    if collision_block:  # 撞车→创新性封 block 档，让否决从文档化的否决引擎路径出(名实一致)
        scores_eff["originality"] = min(scores_eff.get("originality", 100), _BLOCK_ORIGINALITY)
    v = sa.decide(scores_eff, unresolved_critical=art.get("unresolved_critical", False),
                  novelty_prior=art.get("novelty_prior"))
    if v.decision == "不通过":
        return GateResult("fatal_flaw", "fail", "critical",
                          [Finding(loc=f"{art['idea_id']}",
                                   issue=f"无创新/fatal flaw 一票否决：Weighted={v.weighted} Overall={v.overall} → 不通过。",
                                   fix="回 idea-generation 据否决理由定向重提(非微调)。",
                                   evidence="; ".join(v.reasons), rule="score_aggregate.veto")],
                          note="确定性否决闸门：一个 fatal flaw 不被其他高维度平均救回。")
    sev_status = "warn" if v.decision.startswith("有条件通过") else "pass"
    status = "pass" if sev_status == "pass" else "warn"
    return GateResult("fatal_flaw", status, "major" if status == "warn" else "info",
                      [Finding(loc=f"{art['idea_id']}", issue=f"判决={v.decision}(Weighted={v.weighted})",
                               fix="按 Revision_Roadmap 化解后再放行", rule="score_aggregate.decide")]
                      if status == "warn" else [],
                      note=f"score_aggregate 判决={v.decision}；border_review={v.border_review or '无'}")


def _sycophancy_gate_fn(art: dict) -> "GateResult":
    """反谄媚门(warn)：有反驳应答时跑 concession-rate；报警=可能对作者过度顺从放行弱 idea。"""
    rebuttals = art.get("rebuttals")
    if not rebuttals:
        return GateResult("anti_sycophancy", "skip", "info", [],
                          note="无反驳应答记录：反谄媚门跳过(单轮严审无须)。")
    rs = [sg.Rebuttal(r.get("text", ""), int(r.get("score", 3)),
                      bool(r.get("has_new_evidence", False))) for r in rebuttals]
    a = sg.audit(rs, autonomous=bool(art.get("autonomous", True)))
    # 空口让步被强制降 3 的条数（"不被空口反驳放行"机制的留痕）
    stripped = sum(1 for _, note in a["normalized"] if "强制降为3" in note)
    # 协议是否介入：报警 OR 连续让步自动降级 OR 有空口让步被剥。任一即 warn(不被顺从放行，浮出供人工复核)。
    intervened = a["sycophancy_alert"] or a["autonomous_downgrades"] or stripped
    if intervened:
        issue = (f"反谄媚介入：concession-rate={a['concession_rate']}% "
                 f"({a['n_concessions']}/{a['n_rebuttals']} 让步)；空口让步强制降 3 共 {stripped} 条；"
                 f"连续让步自动降级 {len(a['autonomous_downgrades'])} 处。")
        if a["sycophancy_alert"]:
            issue = a["alert_msg"] + "；" + issue
        findings = [Finding(loc=f"{art['idea_id']}", issue=issue,
                            fix="复核每条让步是否挂扎实新证据；不被作者反复反驳顺从放行弱 idea。",
                            evidence=f"reason={a['alert_reason']}; consecutive={a['consecutive_flags']}; "
                                     f"autonomous_downgrades={a['autonomous_downgrades']}",
                            rule="sycophancy.concession_rate")]
        return GateResult("anti_sycophancy", "warn", "major", findings,
                          note="反谄媚介入(warn)：空口让步被剥/连续让步降级/让步偏多，浮出人工复核，不自动放行。")
    return GateResult("anti_sycophancy", "pass", "info", [],
                      note=f"concession-rate={a['concession_rate']}%，无过度顺从信号。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(critique: dict, gen_data: dict | None = None):
    """组装 critical findings：吃 gen most_similar(感觉像) + idea-critique facet 决策 → 三 gate。

    critique: {id, idea, direction, scores{8维}, most_similar[ {doi/title, target_equivalent, stance, delta} ],
               rebuttals[], novelty_prior, evidence_sources[], declared_novelty, unresolved_critical, autonomous}
    gen_data: gen idea_selfcheck 的 --json-out(可选；吃其 most_similar+facet 槽位)。
    """
    idea_id = str(critique.get("id", "?"))
    idea_text = critique.get("idea", "")
    gen_ms = gen_most_similar(gen_data, idea_id) if gen_data else []
    most_similar = merge_most_similar(critique.get("most_similar") or [], gen_ms)
    audit_data, sim_mode, verified = build_audit_data(
        idea_id, idea_text, most_similar,
        declared_novelty=critique.get("declared_novelty", "novel"),
        evidence_sources=critique.get("evidence_sources", []))
    novelty_report = na.audit(audit_data)

    art = {"idea_id": idea_id, "scores": critique.get("scores"),
           "novelty_report": novelty_report, "verified": verified, "sim_mode": sim_mode,
           "rebuttals": critique.get("rebuttals"), "novelty_prior": critique.get("novelty_prior"),
           "unresolved_critical": critique.get("unresolved_critical", False),
           "autonomous": critique.get("autonomous", True)}

    report = None
    if _SHARED_OK:
        report = run_gates([_collision_gate_fn, _fatal_flaw_gate_fn, _sycophancy_gate_fn], art,
                           producer="idea-critique", target=idea_id,
                           summary="idea-critique critical 否决门：撞车(critical)+无创新(critical)+反谄媚(warn)；"
                                   "撞车/无创新一票否决 → run_checkpoint --stage 4 聚合 exit 1 → reroute 4→3。",
                           fresh_evidence=True)
    return {"idea_id": idea_id, "direction": critique.get("direction", ""),
            "most_similar": most_similar, "verified": verified, "sim_mode": sim_mode,
            "novelty_report": novelty_report,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    nr = result["novelty_report"]
    lines = [f"# idea-critique 否决门：{result['idea_id']}"
             f"（{result.get('direction') or '未命名方向'}）", "",
             f"撞车可追溯判定(GraphMind target/background) · 整体 novelty={nr.get('overall_novelty')} · "
             f"high flags={nr.get('high_flag_count')} · sim_mode={result.get('sim_mode')}", ""]
    lines += ["## 最像前作（吃 gen most_similar + 本技能复核 semantic_sim）", ""]
    for v in result.get("verified", []):
        lines.append(f"- {v['ref']}：{v['title']} · gen_sim={v['gen_similarity']} · "
                     f"复核 sim={v['critique_verified_sim']}")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** "
                  f"(producer=idea-critique)；run_checkpoint --stage 4 聚合，critical fail→exit 1→reroute 4→3。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}")
    else:
        lines += ["", "> _shared 不可达：findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest（离线，确定性） ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # gen idea_selfcheck --json-out 形态（most_similar + 空 facet 槽位，撞车演示用同语言英文）
    gen_data = {"collision": {"per_idea": [
        {"id": "I-COLLIDE", "idea": "Contrastive self-supervised goat estrus behaviour recognition",
         "most_similar": [{"similarity": 0.71, "title": "Self-supervised contrastive learning for goat "
                           "estrus detection from accelerometers", "year": 2023, "doi": "10.1/a",
                           "facet_overlap_slots": {k: "" for k in _FACETS}}]},
        {"id": "I-NOVEL", "idea": "Topological data analysis of medieval trade route networks",
         "most_similar": [{"similarity": 0.12, "title": "Graph neural networks for protein folding",
                           "year": 2021, "doi": "10.1/b",
                           "facet_overlap_slots": {k: "" for k in _FACETS}}]},
    ]}}

    high_scores = dict(originality=85, soundness=84, data=82, experiment=83,
                       contribution=85, delta=80, feasibility=84, impact=82)

    # 1. 撞车一票否决：高分 idea，但 idea-critique 填 target_equivalent=True+supporting → same → critical 否决
    crit_collide = {"id": "I-COLLIDE", "idea": "Contrastive self-supervised goat estrus behaviour recognition",
                    "direction": "dairy goat estrus detection", "scores": high_scores,
                    "evidence_sources": ["openalex", "s2"], "declared_novelty": "novel",
                    "most_similar": [{"doi": "10.1/a", "target_equivalent": True, "stance": "supporting"}]}
    res = build(crit_collide, gen_data=gen_data)
    check(res["novelty_report"]["verdict_hooks"]["trigger_target_collision"],
          "target 等价+supporting 应推导 same(trigger_target_collision)")
    check(res["sim_mode"] in ("offline", "exact", "embed", "llm"),
          f"应直接消费 semantic_sim 复核(sim_mode={res.get('sim_mode')})")
    if _SHARED_OK:
        f = res["findings"]
        check(f and f["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f["producer"] == "idea-critique", "producer 应为 idea-critique")
        check(f["verdict"] == "fail", f"撞车应整体 fail(critical)，实得 {f and f['verdict']}")
        coll = next(g for g in f["gates"] if g["gate"] == "collision")
        check(coll["status"] == "fail" and coll["severity"] == "critical",
              "撞车门应 critical fail(一票否决)")
        fatal = next(g for g in f["gates"] if g["gate"] == "fatal_flaw")
        check(fatal["status"] == "fail" and fatal["severity"] == "critical",
              "撞车封顶创新性后 fatal_flaw 门应 critical fail(高均值救不回)")
        # 证据指针含"最像前作"(供 reroute 4→3 带最像前作)
        check("10.1/a" in coll["findings"][0]["loc"], "撞车 finding loc 应含最像前作 doi")
        # round-trip
        rt = FindingsReport.from_json(json.dumps(f, ensure_ascii=False))
        check(rt.producer == "idea-critique" and rt.compute_verdict() == "fail", "findings 应可往返且 fail")
        check(len(rt.blocking_gates()) >= 1, "应有阻断 gate(供 reroute 路由 4→3)")

    # 2. 不撞车放行：target 不等价(仅共享背景) → unrelated 不误判 → 高分 → 通过(pass)
    crit_novel = {"id": "I-NOVEL", "idea": "Topological data analysis of medieval trade route networks",
                  "direction": "computational history", "scores": high_scores,
                  "evidence_sources": ["openalex", "arxiv"], "declared_novelty": "novel",
                  "most_similar": [{"doi": "10.1/b", "target_equivalent": False, "stance": "contrasting"}]}
    res2 = build(crit_novel, gen_data=gen_data)
    check(res2["novelty_report"]["overall_novelty"] == "novel",
          "target 不等价 → 仅共享背景不误判撞车(overall=novel)")
    if _SHARED_OK:
        f2 = res2["findings"]
        check(f2["verdict"] == "pass", f"不撞车高分应 pass，实得 {f2['verdict']}")
        coll2 = next(g for g in f2["gates"] if g["gate"] == "collision")
        check(coll2["status"] == "pass", "不撞车 → 撞车门 pass(GraphMind 关键点：共享背景不误判)")

    # 3. 无创新否决(非撞车路径)：创新性<gate_fatal 直接否决(一票否决，不靠撞车)
    weak = dict(high_scores, originality=40)
    crit_weak = {"id": "I-WEAK", "idea": "incremental tweak", "scores": weak,
                 "evidence_sources": ["openalex", "s2"],
                 "most_similar": [{"doi": "10.1/c", "target_equivalent": False, "stance": "contrasting"}]}
    res3 = build(crit_weak, gen_data=None)
    if _SHARED_OK:
        f3 = res3["findings"]
        fatal3 = next(g for g in f3["gates"] if g["gate"] == "fatal_flaw")
        check(fatal3["status"] == "fail" and fatal3["severity"] == "critical",
              "创新性<45 → fatal_flaw critical(无创新一票否决，非撞车路径)")

    # 4. 反谄媚 warn：明显弱 idea + 作者连续无证据让步 → concession 报警(不被顺从放行)
    crit_syco = {"id": "I-SYCO", "idea": "weak idea", "scores": high_scores,
                 "evidence_sources": ["openalex", "s2"],
                 "most_similar": [{"doi": "10.1/d", "target_equivalent": False, "stance": "contrasting"}],
                 "rebuttals": [{"text": "其实我有新意", "score": 5, "has_new_evidence": True},
                               {"text": "再让一步", "score": 5, "has_new_evidence": True},
                               {"text": "还能让", "score": 4, "has_new_evidence": True}]}
    res4 = build(crit_syco, gen_data=None)
    if _SHARED_OK:
        f4 = res4["findings"]
        syco = next(g for g in f4["gates"] if g["gate"] == "anti_sycophancy")
        check(syco["status"] == "warn", f"高让步率应触发反谄媚 warn，实得 {syco['status']}")

    # 5. 吃 gen most_similar：critique 没给 title，靠 gen 提供 → 复核 sim 仍能算(消费上游)
    check(res["verified"] and res["verified"][0]["title"], "应从 gen most_similar 取到最像前作标题(吃上游)")
    check(res["verified"][0]["gen_similarity"] == 0.71, "应保留 gen 自报相似度做对照")

    # 6. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(res["findings"] is None, "_shared 不可达时 findings 应诚实为 None")

    # 6b. ★Round 2 修复(活体 E2E 抓)：gen 词面 most_similar mis-rank 时，撞车 finding 须指向**触发 same 的
    #     真撞车前作**(非 merge 顺序 verified[0])。E2E 实测 gen 把噪声 'Amharic legal QA' 排在真撞车之前。
    gen_misrank = {"collision": {"per_idea": [
        {"id": "I-MIS", "idea": "Retrieval-augmented generation grounded in clinical guidelines for medical QA",
         "most_similar": [
             {"similarity": 0.30, "title": "Improving Amharic legal question answering with retrieval",
              "year": 2025, "doi": "10.9/noise", "facet_overlap_slots": {k: "" for k in _FACETS}},
             {"similarity": 0.08, "title": "Retrieval-augmented generation for medical QA on heart failure",
              "year": 2026, "doi": "10.9/hit", "facet_overlap_slots": {k: "" for k in _FACETS}}]}]}}
    crit_mis = {"id": "I-MIS", "idea": "Retrieval-augmented generation grounded in clinical guidelines for medical QA",
                "scores": high_scores, "evidence_sources": ["openalex", "crossref"], "declared_novelty": "novel",
                # idea-critique 只对真撞车那条(10.9/hit)填 target_equivalent=True+supporting
                "most_similar": [{"doi": "10.9/hit", "target_equivalent": True, "stance": "supporting"}]}
    res_mis = build(crit_mis, gen_data=gen_misrank)
    if _SHARED_OK:
        coll_m = next(g for g in res_mis["findings"]["gates"] if g["gate"] == "collision")
        check(coll_m["status"] == "fail", "mis-rank 场景仍应判 same 撞车 fail")
        loc_m = coll_m["findings"][0]["loc"]
        check("10.9/hit" in loc_m,
              f"撞车 finding 应指向触发 same 的真撞车前作 10.9/hit(非 gen 词面 top 10.9/noise)，实得 {loc_m}")
        check("10.9/noise" not in loc_m, "撞车 finding 不应指向 gen mis-rank 的噪声前作")

    # 7. markdown 不崩
    check("否决门" in to_markdown(res), "markdown 应含否决门标题")

    if failures:
        print("[SELFTEST][fatal_flaw_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][fatal_flaw_gate] OK：撞车一票否决(critical) + 无创新否决 + 反谄媚 warn + "
          "吃 gen most_similar + 消费 semantic_sim + findings(idea-critique) 全通过"
          + ("" if _SHARED_OK else "（_shared 不可达，findings 走诚实降级路径）") + "。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="idea-critique critical 否决门 producer（撞车/无创新一票否决→findings）")
    ap.add_argument("--critique", help="本技能严审输入 JSON(id/idea/scores/most_similar+facet 决策/rebuttals...)")
    ap.add_argument("--gen-selfcheck", help="gen idea_selfcheck 的 --json-out(吃其 most_similar+facet 槽位)")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整否决 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.critique:
        ap.error("需要 --critique critique_input.json(或 --selftest)")

    with open(args.critique, encoding="utf-8") as f:
        critique = json.load(f)
    gen_data = None
    if args.gen_selfcheck:
        with open(args.gen_selfcheck, encoding="utf-8") as f:
            gen_data = json.load(f)

    result = build(critique, gen_data=gen_data)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整否决 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达，无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    # critical fail → 退出码 1（与 run_checkpoint 同口径，便于单独跑也能确定性阻断）
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
