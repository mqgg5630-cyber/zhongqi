#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""critique_self_audit.py — 对本次评审 verdict 做 PRISM 式自审 + 判决语料下沉(跨技能反哺)。

为什么有这个脚本
----------------
多维 LLM 审稿人评测(PRISM)实证：LLM 审稿人有两类系统病——
  (1) constructiveness 缺口：只挑刺不给可执行方案；
  (2) surface trap：精力浪费在格式/排版/措辞等表层问题（TreeReview arXiv 2506.07642 实证现有法
      "常产肤浅反馈、缺深度"）；
另有 novelty 过度背书（Pitfalls-of-Automating-Reviews arXiv 2512.22145 实证 LLM 系统高估、对弱稿
  也给高分；OpenReviewer arXiv 2505.07920 实证通用 LLM 比专用审稿更正面/更谄媚）。
⚠ 诚实(铁律 2)：v1 此处曾写"SEA 过度背书 79% vs 人 59%""TreeReview surface 24%"两具体数字，
  2026-06-18 一手 fetch 两篇原文均**无此数字** → 已剥离，只留可核机制(过度背书/肤浅反馈，定性)。
Light 已有反谄媚硬协议（sycophancy_guard）抓"对作者过度顺从"，但**没有量化"我这次评审
本身够不够建设性 / 有没有陷在表层 / 有没有在没给检索证据时空口背书新颖性"**。本脚本补这层
"评审者自审"：把 verdict 正文喂进来，正则统计三轴体检分，对超标轴出结构化 findings。

两件事
------
A. self_audit(verdict_text)：PRISM 三轴自审（surface 占比 / solutions:problems 比 / 过度背书），
   输出 light.findings.v1（挂 _shared/findings_schema），接总控交付门 / orchestrator 闸门。
B. build_critique_corpus(...)：把"拒稿理由预演 top-3"与拉到的真实 OpenReview review 引用，
   结构化成 critique_corpus.json——**让 idea-critique 的产物喂养下游**：
   paper-writing 读 top3_reject_reasons 在 related-work/动机段逐条预反驳；
   review-rebuttal 读 reviewer_corpus_refs 拼 rebuttal 底稿；总控交付门复查是否已化解。
   （同构 result-analysis 证据强度绑 paper-writing 措辞的跨技能反哺；判决语料按 SKILL 落
   memory-pm 台账(.light/ decision_log)，本脚本只产结构化件。）

⚠ 诚实边界：三轴是**正则/启发式**自审，非语义真值——它抓"verdict 行文层面的征兆"，
  不替代人对"这条意见到底建不建设性"的判断。阈值是经验默认值、可调超参，不假装有数据背书。

用法：
  python critique_self_audit.py --in verdict.md            # 对 verdict 做 PRISM 自审
  python critique_self_audit.py --in verdict.md --json     # 输出 findings JSON
  python critique_self_audit.py --emit-corpus corpus_in.json --out critique_corpus.json
  python critique_self_audit.py --selftest                 # 离线合成自测
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys

# 规范 bootstrap（_shared/README.md）：向上走目录树找含 _shared 包的仓库根，
# 治 v1 硬编码 ../../_shared 在 v2（_shared 在仓库根、与 skills/ 平级）必断之脆。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    _HAS_FINDINGS = True
except ImportError:
    _HAS_FINDINGS = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# === 经验默认阈值（可调超参，非数据反推）===
DEFAULTS = {
    "constructiveness_floor": 0.5,   # solutions:problems 比 < 此 → constructiveness 缺口（PRISM 病）
    "surface_ratio_ceiling": 0.4,    # 表层问题占比 > 此 → surface trap（陷在格式/措辞）
    "min_problems": 3,               # 问题数 < 此 → 比值不稳，降级为 info 不报 fail（小 N 防脆弱）
}

# 标志词（中英）——启发式，匹配"行文征兆"，非语义判定
_PROBLEM = re.compile(
    r"问题|缺陷|弱点|不足|缺乏|缺少|未能|没有|无法|不能|错误|风险|存疑|质疑|薄弱|遗漏|不清|不够|过度|偏弱|"
    r"weakness|flaw|lack|missing|fail|risk|unclear|insufficient|concern|doubt|problematic", re.I)
_SOLUTION = re.compile(
    r"建议|应当|应该|可改为|可以|方案|补充|增加|新增|替换|改用|考虑|推荐|须|需要|改进|修订|可加|不妨|"
    r"recommend|suggest|consider|should|add|replace|improve|propose|fix|revise|could", re.I)
_SURFACE = re.compile(
    r"格式|排版|拼写|错别字|字体|图表清晰|清晰度|参考文献格式|标点|语法|措辞|用词|文字表述|typo|"
    r"formatting|citation format|wording|grammar|typesetting|spelling", re.I)
_ENDORSE = re.compile(
    r"新颖|创新性?(?:高|强|充分|突出)|原创|突破性?|很有价值|颇具|novel|original|innovative|breakthrough|"
    r"high\s+novelty|strong\s+originality", re.I)
_EVIDENCE = re.compile(
    r"检索|查新|openalex|semantic\s*scholar|\bs2\b|arxiv|\bdoi\b|最像|前作|相关工作|collision|撞车|"
    r"最近邻|密度|novelty_?(audit|density|prior)|openreview|百分位", re.I)


def _split_units(text: str) -> list:
    """把 verdict 拆成评判单元：项目符号行优先，否则按句切。"""
    units = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 去掉项目符号/标题井号
        s = re.sub(r"^[\-\*\d\.\)#\s]+", "", s).strip()
        if not s:
            continue
        # 句内再按中英文句末切，让一行多句也分开计数
        parts = re.split(r"[。！？!?；;]\s*|\.\s+", s)
        units.extend(p.strip() for p in parts if p.strip())
    return units


def self_audit(text: str, thresholds: dict | None = None) -> dict:
    """对 verdict 正文做 PRISM 三轴自审，返回指标 + flags。"""
    t = dict(DEFAULTS)
    if thresholds:
        t.update(thresholds)
    units = _split_units(text)
    problem_units = [u for u in units if _PROBLEM.search(u)]
    solution_units = [u for u in units if _SOLUTION.search(u)]
    surface_problem_units = [u for u in problem_units if _SURFACE.search(u)]

    n_prob = len(problem_units)
    n_sol = len(solution_units)
    n_surface = len(surface_problem_units)

    constructiveness = round(n_sol / n_prob, 3) if n_prob else None
    surface_ratio = round(n_surface / n_prob, 3) if n_prob else 0.0

    endorse = bool(_ENDORSE.search(text))
    has_evidence = bool(_EVIDENCE.search(text))

    flags = []
    small_n = n_prob < t["min_problems"]
    # 轴1 constructiveness 缺口（只挑刺不给方案）
    if constructiveness is not None and constructiveness < t["constructiveness_floor"]:
        sev = "info" if small_n else "major"
        flags.append({"axis": "constructiveness", "code": "CONSTRUCTIVENESS-GAP",
                      "severity": sev,
                      "msg": f"solutions:problems={constructiveness}<{t['constructiveness_floor']}"
                             f"（{n_sol}方案/{n_prob}问题）——只挑刺不给可执行方案，PRISM 实测的审稿通病。"
                             + ("(问题数小N<%d,降级 info 仅提示)" % t["min_problems"] if small_n else
                                " 给每条 CRITICAL 配一个可执行修复方向。")})
    # 轴2 surface trap（陷在格式/措辞表层）
    if n_prob and surface_ratio > t["surface_ratio_ceiling"]:
        sev = "info" if small_n else "major"
        flags.append({"axis": "surface_trap", "code": "SURFACE-TRAP", "severity": sev,
                      "msg": f"表层(格式/措辞/排版)问题占比={surface_ratio}>{t['surface_ratio_ceiling']}"
                             f"（{n_surface}/{n_prob}）——精力陷在 surface，"
                             f"顶会审稿应聚焦创新性/可靠性/证据等实质维度。"})
    # 轴3 过度背书（背书新颖但没给检索证据）
    if endorse and not has_evidence:
        flags.append({"axis": "over_endorsement", "code": "NOVELTY-OVER-ENDORSE",
                      "severity": "major",
                      "msg": "verdict 背书了新颖性/创新性，但正文找不到检索/查新/最近邻证据的痕迹——"
                             "Pitfalls(2512.22145)实证 LLM 审稿系统过度背书。背书新颖前须有 novelty_audit/novelty_density 证据。"})

    return {
        "n_units": len(units), "n_problems": n_prob, "n_solutions": n_sol,
        "n_surface_problems": n_surface,
        "constructiveness_ratio": constructiveness,
        "surface_ratio": surface_ratio,
        "endorses_novelty": endorse, "shows_retrieval_evidence": has_evidence,
        "small_n": small_n, "flags": flags,
        "note": ("PRISM 三轴启发式自审(constructiveness/surface/过度背书)，正则匹配行文征兆非语义真值。"
                 "阈值为经验默认值可调。问题数<min_problems 时比值轴降级 info 防小 N 脆弱。"),
    }


def to_findings_report(metrics: dict, target: str = "critique_verdict.md") -> dict:
    """把自审指标转成 light.findings.v1（挂 _shared/findings_schema），供总控交付门/orchestrator 消费。"""
    if not _HAS_FINDINGS:
        # 降级：手工拼等价 dict（不静默假成功，明确标 schema 与降级）
        gates = []
        for f in metrics["flags"]:
            status = "warn" if f["severity"] in ("info", "minor") else "fail"
            gates.append({"gate": f["axis"], "status": status, "severity": f["severity"],
                          "findings": [{"loc": "critique_verdict.md", "issue": f["msg"],
                                        "fix": "", "rule": f["code"]}]})
        verdict = "fail" if any(g["severity"] in ("major", "critical") and g["status"] == "fail"
                                for g in gates) else ("warn" if gates else "pass")
        return {"schema": "light.findings.v1", "producer": "idea-critique", "target": target,
                "verdict": verdict, "gates": gates, "summary": "PRISM 自审(findings_schema 不可用,降级手拼)",
                "fresh_evidence": True, "_degraded": True}

    rep = FindingsReport(producer="idea-critique", target=target, fresh_evidence=True,
                         summary="idea-critique PRISM 式评审自审(constructiveness/surface/过度背书)")
    if not metrics["flags"]:
        rep.gates.append(GateResult("prism_self_audit", "pass", "info"))
    for f in metrics["flags"]:
        status = "warn" if f["severity"] in ("info", "minor") else "fail"
        rep.gates.append(GateResult(
            f["axis"], status, f["severity"],
            [Finding("critique_verdict.md", f["msg"], rule=f["code"])]))
    return rep.finalize().to_dict()


def build_critique_corpus(verdict_id: str, top3_reject_reasons: list,
                          reviewer_corpus_refs: list | None = None,
                          collision_summary: str = "") -> dict:
    """判决语料下沉(跨技能反哺)：结构化 idea-critique 产出给 paper-writing/review-rebuttal/交付门消费。

    top3_reject_reasons: [{reason, rebuttable(bool), evidence_gap}]——拒稿理由预演 top-3
    reviewer_corpus_refs: [DOI...]——拉到的真实 OpenReview review / 最像前作（供 review-rebuttal 拼 rebuttal）
    返回结构化件（写 critique_corpus.json）；按 SKILL 该语料落 memory-pm 台账(.light/ decision_log)。
    """
    reasons = []
    for r in (top3_reject_reasons or []):
        if isinstance(r, str):
            reasons.append({"reason": r, "rebuttable": None, "evidence_gap": ""})
        else:
            reasons.append({"reason": r.get("reason", ""),
                            "rebuttable": r.get("rebuttable"),
                            "evidence_gap": r.get("evidence_gap", "")})
    return {
        "schema": "light.critique_corpus.v1",
        "producer": "idea-critique",
        "verdict_id": verdict_id,
        "top3_reject_reasons": reasons,          # paper-writing 在正文逐条预反驳
        "reviewer_corpus_refs": list(reviewer_corpus_refs or []),  # review-rebuttal 拼 rebuttal 底稿
        "collision_summary": collision_summary,
        # ★Round 2 R1：拒稿预演完整性 advisory(warn-only，借 paperjury two-sided trial)随语料下沉
        "rehearsal_advisory": rehearsal_audit(top3_reject_reasons),
        "consumers": {"paper-writing": "related-work/动机段预反驳 top3_reject_reasons",
                      "review-rebuttal": "reviewer_corpus_refs 作 rebuttal 语料",
                      "delivery-gate": "总控交付门复查 top3_reject_reasons 是否已化解"},
        "note": "判决语料下沉，兑现 idea-critique→paper-writing/review-rebuttal 跨技能反哺。"
                "落 memory-pm 台账(.light/ decision_log) 由 SKILL 协议负责。",
    }


# === ★Round 2 R1：拒稿预演完整性 advisory（借 paperjury two-sided trial / contestability）===
# 北极星：NEVER#4「以目标会审稿人身份列 top-3 拒稿理由，逐条预演反驳能否站住，预演不出有效反驳=未化解
# CRITICAL」原本只写在 SKILL prose——`build_critique_corpus` 被动接受未预演的拒稿点(字符串→rebuttable:None
# 静默放过)，零机检。借 paperjury(u7079256, 453★)的 two-sided trial / contestability routing(每个 issue 经
# 两面庭审才能 close、ledger 带 close_criterion)，补一条**只检完整性**的 warn-only advisory。
REHEARSAL_DEFAULTS = {"min_top_reasons": 3}   # NEVER#4：top-3 拒稿理由


def rehearsal_audit(top3_reject_reasons: list, thresholds: dict | None = None) -> dict:
    """检 NEVER#4「拒稿理由预演 top-3」做没做齐（warn-only advisory，**绝不 critical、绝不阻断**）。

    只检**完整性**(top-3 是否齐、每条是否预演过 rebuttable、预演不出反驳的拒稿点是否浮出)，
    **不语义判反驳是否有效**(那是宿主 LLM/人的活)。rebuttable 由本技能填、可被乱填 True 糊弄——
    故 warn-only，真 critical 阻断仍归 collision/fatal_flaw 两门，不靠这条 advisory。

    top3_reject_reasons: [{reason, rebuttable(bool|None), evidence_gap}] 或 [str...]
    rebuttable 语义：True=作者能给有效反驳(拒稿点可化解)；False=预演不出有效反驳(拒稿点站得住=
      未化解风险)；None=尚未预演。
    """
    t = dict(REHEARSAL_DEFAULTS)
    if thresholds:
        t.update(thresholds)
    norm = []
    for r in (top3_reject_reasons or []):
        if isinstance(r, str):
            norm.append({"reason": r, "rebuttable": None, "evidence_gap": ""})
        else:
            norm.append({"reason": r.get("reason", ""), "rebuttable": r.get("rebuttable"),
                         "evidence_gap": r.get("evidence_gap", "")})
    n = len(norm)
    unrehearsed = [x for x in norm if x["rebuttable"] is None]
    unresolved = [x for x in norm if x["rebuttable"] is False]
    flags = []
    if n < t["min_top_reasons"]:
        flags.append({"code": "REHEARSAL-INCOMPLETE",
                      "msg": f"拒稿理由仅 {n} 条 < top-{t['min_top_reasons']}（NEVER#4 要以目标会审稿人身份"
                             f"列 top-3）——补齐再判，否则可能漏掉真致命拒稿点。"})
    if unrehearsed:
        flags.append({"code": "REHEARSAL-MISSING",
                      "msg": f"{len(unrehearsed)} 条拒稿点未预演反驳(rebuttable=None)："
                             f"{[x['reason'][:24] for x in unrehearsed]}——NEVER#4 要逐条预演作者反驳能否站住"
                             f"(借 paperjury two-sided trial)，未预演=没做两面对抗。"})
    if unresolved:
        flags.append({"code": "REHEARSAL-UNRESOLVED",
                      "msg": f"{len(unresolved)} 条拒稿点预演不出有效反驳(rebuttable=False)："
                             f"{[x['reason'][:24] for x in unresolved]}——按 NEVER#4 这是『未化解』风险，应停下走"
                             f" ASK 回炉决策，不当通过(本 advisory 只提示不替你判/不阻断；真否决在 collision/fatal_flaw)。"})
    return {"n_reasons": n, "n_unrehearsed": len(unrehearsed), "n_unresolved": len(unresolved),
            "flags": flags,
            "note": "拒稿预演完整性 advisory（warn-only）：只检 NEVER#4 做没做齐，不语义判反驳是否有效；"
                    "rebuttable 可被糊弄，真 critical 阻断归 collision/fatal_flaw。"}


def rehearsal_to_findings(metrics: dict, target: str = "critique_verdict.md") -> dict:
    """把拒稿预演完整性 advisory 转 light.findings.v1（**status=warn / severity=minor，永不 fail/阻断**）。"""
    if not _HAS_FINDINGS:
        status = "warn" if metrics["flags"] else "pass"
        gates = [{"gate": "rehearsal_completeness", "status": status,
                  "severity": "minor" if metrics["flags"] else "info",
                  "findings": [{"loc": target, "issue": f["msg"], "fix": "", "rule": f["code"]}
                               for f in metrics["flags"]]}]
        return {"schema": "light.findings.v1", "producer": "idea-critique", "target": target,
                "verdict": "warn" if metrics["flags"] else "pass", "gates": gates,
                "summary": "拒稿预演完整性 advisory(findings_schema 不可用,降级手拼)",
                "fresh_evidence": True, "_degraded": True}
    rep = FindingsReport(producer="idea-critique", target=target, fresh_evidence=True,
                         summary="idea-critique 拒稿预演完整性 advisory(借 paperjury two-sided trial，warn-only)")
    if not metrics["flags"]:
        rep.gates.append(GateResult("rehearsal_completeness", "pass", "info"))
    else:
        rep.gates.append(GateResult(
            "rehearsal_completeness", "warn", "minor",
            [Finding(target, f["msg"], rule=f["code"]) for f in metrics["flags"]]))
    return rep.finalize().to_dict()


def _selftest() -> int:
    print("### critique_self_audit 离线自测", file=sys.stderr)

    # A) 病态 verdict：全是问题、几乎无方案、且陷在表层格式 → constructiveness + surface 报警
    bad = """
    - 这篇 idea 的图表清晰度不足，排版格式不规范。
    - 参考文献格式有错误，措辞也不够严谨。
    - 字体使用不一致，标点符号有问题。
    - 实验设计存在缺陷，缺乏对照。
    - 创新性论证薄弱，没有充分证据。
    - 写作语法有不少错误。
    """
    ma = self_audit(bad)
    codes_a = {f["code"] for f in ma["flags"]}
    print(f"[A] bad: constr={ma['constructiveness_ratio']} surface={ma['surface_ratio']} "
          f"flags={codes_a}", file=sys.stderr)
    assert "CONSTRUCTIVENESS-GAP" in codes_a, codes_a       # 几乎没方案
    assert "SURFACE-TRAP" in codes_a, codes_a               # 表层占比高
    rep_a = to_findings_report(ma)
    assert rep_a["schema"] == "light.findings.v1", rep_a
    assert rep_a["verdict"] in ("fail", "warn"), rep_a["verdict"]

    # B) 健康 verdict：问题与可执行方案平衡、聚焦实质维度、带检索证据 → 全 pass
    good = """
    - 核心创新性存疑：与 OpenAlex 检索到的 Smith2023 在 target 层高度重叠，建议明确 delta。
    - 实验缺乏消融，无法归因增益来源，建议补单变量消融隔离创新点贡献。
    - 数据规模偏小存在过拟合风险，应补充外部验证集或交叉验证。
    - 理论分析不足，建议增加收敛性证明或给出反例边界。
    - 基线选择偏弱，推荐替换为近两年 SOTA 方法做对照。
    """
    mb = self_audit(good)
    print(f"[B] good: constr={mb['constructiveness_ratio']} surface={mb['surface_ratio']} "
          f"evidence={mb['shows_retrieval_evidence']} flags={[f['code'] for f in mb['flags']]}",
          file=sys.stderr)
    assert mb["constructiveness_ratio"] >= 0.5, mb["constructiveness_ratio"]
    assert not any(f["code"] == "SURFACE-TRAP" for f in mb["flags"]), mb["flags"]
    rep_b = to_findings_report(mb)
    assert rep_b["verdict"] == "pass", rep_b

    # C) 过度背书：夸新颖但无检索证据痕迹 → NOVELTY-OVER-ENDORSE
    endorse = "这个 idea 非常新颖，创新性很高，是该领域的突破性工作，强烈建议通过。"
    mc = self_audit(endorse)
    assert any(f["code"] == "NOVELTY-OVER-ENDORSE" for f in mc["flags"]), mc["flags"]
    # 同样背书但带了检索证据 → 不报过度背书
    endorse2 = "经 OpenAlex/S2 两库检索且最像前作 target 层不等价，创新性确实较高，建议通过。"
    mc2 = self_audit(endorse2)
    assert not any(f["code"] == "NOVELTY-OVER-ENDORSE" for f in mc2["flags"]), mc2["flags"]
    print("[C] 过度背书检测(无证据报警/有证据不报) ... OK", file=sys.stderr)

    # D) 小 N：问题很少时 constructiveness 轴降级 info 不当 fail
    small = "- 实验设计有一个小缺陷。"
    md = self_audit(small)
    if any(f["code"] == "CONSTRUCTIVENESS-GAP" for f in md["flags"]):
        g = next(f for f in md["flags"] if f["code"] == "CONSTRUCTIVENESS-GAP")
        assert g["severity"] == "info", g
    print("[D] 小 N 降级 info ... OK", file=sys.stderr)

    # E) 判决语料下沉 corpus（跨技能反哺）
    corpus = build_critique_corpus(
        "verdict-001",
        top3_reject_reasons=[
            {"reason": "核心已被 Smith2023 做过", "rebuttable": False, "evidence_gap": "无 delta"},
            {"reason": "纯增量换数据集", "rebuttable": True, "evidence_gap": "需方法层贡献"},
            "伪缺口：没人做因不重要",
        ],
        reviewer_corpus_refs=["10.1109/abc.2023", "10.1145/xyz.2024"])
    assert corpus["schema"] == "light.critique_corpus.v1", corpus
    assert len(corpus["top3_reject_reasons"]) == 3, corpus
    assert corpus["top3_reject_reasons"][2]["reason"].startswith("伪缺口"), corpus
    assert "paper-writing" in corpus["consumers"] and "review-rebuttal" in corpus["consumers"], corpus
    # JSON 可序列化往返
    rt = json.loads(json.dumps(corpus, ensure_ascii=False))
    assert rt["verdict_id"] == "verdict-001"
    print("[E] critique_corpus 下沉(top3/refs/consumers) ... OK", file=sys.stderr)
    # E 的 corpus 应随带拒稿预演 advisory（1 条 string→未预演 + 1 条 rebuttable:False→未化解）
    adv = corpus["rehearsal_advisory"]
    codes_e = {f["code"] for f in adv["flags"]}
    assert "REHEARSAL-MISSING" in codes_e and "REHEARSAL-UNRESOLVED" in codes_e, adv
    assert "REHEARSAL-INCOMPLETE" not in codes_e, adv   # 正好 3 条，不报不足

    # F) ★Round 2 R1：拒稿预演完整性 advisory（warn-only，绝不 critical/阻断）
    # F1 不足 + 未预演：2 条且都未预演 → INCOMPLETE + MISSING
    mf = rehearsal_audit(["核心已被做过", "纯增量"])
    codes_f = {f["code"] for f in mf["flags"]}
    assert "REHEARSAL-INCOMPLETE" in codes_f and "REHEARSAL-MISSING" in codes_f, codes_f
    rep_f = rehearsal_to_findings(mf)
    assert rep_f["schema"] == "light.findings.v1" and rep_f["producer"] == "idea-critique", rep_f
    assert rep_f["verdict"] == "warn", f"advisory 永不 fail，应 warn，实得 {rep_f['verdict']}"
    g_f = rep_f["gates"][0]
    assert g_f["status"] == "warn" and g_f["severity"] == "minor", g_f  # 永不 critical/fail
    # F2 预演不出反驳：3 条齐但有一条 rebuttable=False → 仅 UNRESOLVED，仍只 warn 不阻断
    mf2 = rehearsal_audit([{"reason": "撞车", "rebuttable": False},
                           {"reason": "增量", "rebuttable": True},
                           {"reason": "可行性", "rebuttable": True}])
    codes_f2 = {f["code"] for f in mf2["flags"]}
    assert codes_f2 == {"REHEARSAL-UNRESOLVED"}, codes_f2
    assert rehearsal_to_findings(mf2)["verdict"] == "warn", "未化解拒稿点仍是 advisory(warn)，不替阻断"
    # F3 top-3 齐且全部预演可反驳 → 无 flag → pass（不打扰）
    mf3 = rehearsal_audit([{"reason": "a", "rebuttable": True}, {"reason": "b", "rebuttable": True},
                           {"reason": "c", "rebuttable": True}])
    assert not mf3["flags"], mf3
    assert rehearsal_to_findings(mf3)["verdict"] == "pass", mf3
    print("[F] 拒稿预演完整性 advisory(不足/未预演/未化解→warn 永不 critical; 齐全→pass) ... OK", file=sys.stderr)

    print("[selftest] PASS critique_self_audit offline"
          + ("" if _HAS_FINDINGS else "（findings_schema 不可用，已用降级 dict 路径）"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="idea-critique PRISM 自审 + 判决语料下沉")
    ap.add_argument("--in", dest="infile", help="verdict 正文(md/txt)路径，做 PRISM 自审")
    ap.add_argument("--emit-corpus", dest="corpus_in",
                    help='判决语料输入 JSON: {verdict_id, top3_reject_reasons, reviewer_corpus_refs}')
    ap.add_argument("--out", help="输出文件路径（corpus 模式默认 critique_corpus.json）")
    ap.add_argument("--rehearsal-report", dest="rehearsal_report",
                    help="corpus 模式下把拒稿预演完整性 advisory(light.findings.v1, warn-only)写到该路径")
    ap.add_argument("--json", action="store_true", help="自审输出 findings JSON")
    ap.add_argument("--selftest", action="store_true", help="离线合成自测")
    args = ap.parse_args()

    if args.selftest or (not args.infile and not args.corpus_in):
        return _selftest()

    if args.corpus_in:
        with open(args.corpus_in, encoding="utf-8") as f:
            d = json.load(f)
        corpus = build_critique_corpus(
            d.get("verdict_id", "?"), d.get("top3_reject_reasons", []),
            d.get("reviewer_corpus_refs", []), d.get("collision_summary", ""))
        out = args.out or "critique_corpus.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(corpus, f, ensure_ascii=False, indent=2)
        print(f"wrote {out}")
        # ★拒稿预演完整性 advisory（warn-only）：浮出供人工/回炉决策参考
        adv = corpus["rehearsal_advisory"]
        if adv["flags"]:
            print(f"  [拒稿预演 advisory] top-3 预演 {adv['n_reasons']} 条 / 未预演 {adv['n_unrehearsed']}"
                  f" / 预演不出反驳 {adv['n_unresolved']}（warn-only，不阻断）：")
            for fl in adv["flags"]:
                print(f"    [{fl['code']}] {fl['msg']}")
        else:
            print("  [拒稿预演 advisory] top-3 已预演齐、均可反驳，无 advisory。")
        if args.rehearsal_report:
            rep = rehearsal_to_findings(adv, target=f"critique:{d.get('verdict_id', '?')}")
            with open(args.rehearsal_report, "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False, indent=2)
            print(f"  [REHEARSAL] light.findings.v1 → {args.rehearsal_report}(verdict={rep['verdict']})",
                  file=sys.stderr)
        return 0

    with open(args.infile, encoding="utf-8") as f:
        text = f.read()
    metrics = self_audit(text)
    rep = to_findings_report(metrics)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(f"PRISM 自审 — 问题{metrics['n_problems']} 方案{metrics['n_solutions']} "
              f"constructiveness={metrics['constructiveness_ratio']} "
              f"surface={metrics['surface_ratio']} 背书={metrics['endorses_novelty']} "
              f"证据={metrics['shows_retrieval_evidence']}")
        for fl in metrics["flags"]:
            print(f"  [{fl['severity']}] {fl['code']}: {fl['msg']}")
        if not metrics["flags"]:
            print("  无 PRISM 轴报警（建设性/表层占比/背书均在阈内）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
