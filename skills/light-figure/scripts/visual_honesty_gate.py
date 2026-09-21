#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""visual_honesty_gate.py — figure 的**视觉诚实(critical)/把不显著当主图(9→7 发起) producer**。

蓝图 §4.3-9 的「及格线」:图服务论点 + 出版级 + **诚实性** + 渲染回看 + 程序化生成绝不 AI 生图。
本脚本把"视觉诚实"这条编排成机读 `light.findings.v1`(producer=**figure**)。门名对齐
`STAGE_GATES[9]=[visual_honesty]`(spec §4.2 figure Critical=**不诚实(截 y 轴/双 y 轴伪相关)**;
warn=误差棒缺失、集合超预算):

  ① **visual_honesty(截 y 轴/双 y 轴伪相关/3D 透视)= critical**:编排同目录 `figure_integrity_lint`
     静态扫绘图代码,AXIS_TRUNCATE/TWIN_AXIS/PIE_3D → 阻断 → 被总控 `run_checkpoint --stage 9` 聚合
     **exit 1**。issue **刻意不带 9→7 信号**(不显著/图文不一致/证据)→ `reroute --stage 9` 给
     **manual = 本阶段重画修**(同 result-analysis p-hacking→manual 的诚实落点:画法不诚实在 figure 内
     重画即可,非回 result-analysis)。静态 lint 只抓"形态可疑",正当截断(放大真实小差异+断轴标注+
     caption 说明)可经 run_checkpoint **授权 FAIL→PASS 记 notes**(spec §6)。

  ② **misrepresent_evidence(把不显著当主图/图文不一致)= critical, 9→7 回炉发起**:消费 result-analysis
     的 `evidence_strength.json`,**must 优先级的图绑到 grade=none(不显著/CI 跨 0/q≥.05)的 claim** →
     图与证据强度不一致 → 阻断。issue **带「不显著/图文不一致/证据/主图」信号** → `reroute` 命中
     `ROUTES[9]` 建议 **9→7**(回 result-analysis 核「该图对应的证据强度」)。**figure 是 9→7 回边发起方。**

  ③ **error_bars(误差棒缺失)= warn**(spec §4.2):figure_integrity_lint 的 BAR_NO_ERR/ERRBAR_NO_TYPE/
     BAR_PLOT_SMALL——柱图应带误差棒、caption 须注明 SD/SEM/CI 与 n(Cumming 2007)。
  ④ **colormap(jet/rainbow)= warn**:RAINBOW_CMAP——非感知均匀且非色盲安全,有序数据改 viridis。
     **warn 非 critical**:类别型 rainbow + caption 可辩护,静态 lint 分不清有序/类别(诚实降级)。
  ⑤ **display_budget(集合超预算)= warn**(spec §4.2):编排同目录 `audit_figure_set` 计数对照 venue
     `--cap`,超则按砍序(可删→可做降附录→必做不动)。**warn 非 critical**(spec §4.2 列在 warn 列)。
  ⑥ **panel_redundancy(反冗余)= warn**:同 claim 同图型族 = 候选冗余(audit_figure_set,挂 semantic_sim)。

这是 **v2 净新增的接线**(与 paper-writing `claim_evidence_gate`、result-analysis `stat_rigor_gate`、
experiment-coding `repro_gate` 同构):**编排同目录港来件 + 消费 _shared/上游证据档 → critical findings
producer**,**不重造**——
  - 视觉诚实静态判据:同目录 `figure_integrity_lint`(纯 stdlib 正则扫绘图代码;Cairo 零基线 + 双轴伪相关)。
  - 集合预算/反冗余:同目录 `audit_figure_set`(挂 `_shared/semantic_sim`)。
  - 证据档:消费 result-analysis emit 的 `evidence_strength.json`(`light.evidence_strength.v1`),
    用 `_shared/semantic_sim` 把图的"绑定 claim"匹配到证据 claim 取 grade。
  - 几何/对比度/render-then-look:同目录 `figure_visual_qa`(消费 `_shared/visual_qa`),**不重造几何引擎**。

诚实约定(名实对齐见 SKILL,铁律 2):
- **静态 lint 只抓「形态可疑」非「证明误导」**:AXIS_TRUNCATE 抓"ylim 起点≠0 且无断轴标注",但截断
  **可能完全合理**(Correll 2019 实证);TWIN_AXIS 抓 twinx 存在,双轴有时正当。→ critical 默认阻断,
  **真误导终判需 caption + 人/审稿人**,正当者可授权 FAIL→PASS。
- **图↔claim 绑定是启发式**:优先 claim_id 精确匹配,否则 claim 文本语义相似(≥阈值)匹配;无匹配 →
  grade 未知 → **不 flag**(保守,少误报 critical)。精确逐图匹配需规划卡显式写 claim_id。
- **misrepresent_evidence 核「图对应证据强度」非「证据真伪」**:只核"主图绑的 claim 有没有达显著",不核
  结论对不对(那要复现/同行)。
- **程序化生成绝不 AI 生图**:本门只机检诚实形态,figure 技能本身的永久底线是论文数据图一律程序化生成。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  python visual_honesty_gate.py --spec spec.json --report fig_findings.json
  python visual_honesty_gate.py --plot-code plot.py --cards F1.md F2.md --evidence evidence_strength.json --cap 8
  python visual_honesty_gate.py --plot-code plot.py        # 仅查视觉诚实(截/双轴/误差棒/色图)
  python visual_honesty_gate.py --selftest

spec(也可 --spec spec.json 一把传):
  {"project":"goat-estrus",
   "plot_code":"<绘图代码正文或路径>",
   "cards":["<规划卡正文或路径>", ...],         # 供集合预算/反冗余 + 派生图↔claim 绑定
   "figures":[{"figure_id":"F1","claim_id":"c1","claim":"...","priority":"必做"}],  # 显式覆盖(否则从 cards 派生)
   "evidence":"<evidence_strength.json 路径>",
   "cap":8}
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

# 同目录港来的纯工具/引擎(复用不重造)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import figure_integrity_lint as fil          # noqa: E402  视觉诚实静态判据
    _HAS_FIL = True
except Exception:
    _HAS_FIL = False
try:
    import audit_figure_set as afs               # noqa: E402  集合预算/反冗余 + 解析图↔claim
    _HAS_AFS = True
except Exception:
    _HAS_AFS = False

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,治硬编码 parents[N] 之脆。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    from _shared import evidence_contract as ec                              # noqa: E402
    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False
try:
    from _shared.semantic_sim import similarity as _sem_sim                  # noqa: E402
    _HAS_SEM = True
except ImportError:
    _HAS_SEM = False


# ───────────────────────── 工具:优先级归一 + 证据档查找 ─────────────────────────
def _prio(v) -> str:
    """优先级归一:必做/must→must, 可删/cut→cut, 可做/nice→nice。"""
    s = str(v or "").lower()
    if "必做" in s or s == "must":
        return "must"
    if "可删" in s or s == "cut":
        return "cut"
    if "可做" in s or s == "nice":
        return "nice"
    return ""


def _index_evidence(evidence: dict):
    """evidence_strength.json → ({claim_id: grade}, [(text, grade)])。grade 缺则按 q/效应量现算。"""
    claims = (evidence or {}).get("claims") or []
    by_id, items = {}, []
    for c in claims:
        g = c.get("evidence_grade")
        if g is None and _SHARED_OK:
            g = ec.grade_evidence(c.get("q_fdr"), c.get("effect_size"), c.get("ci95"), c.get("n"))
        g = g or "none"
        cid = c.get("claim_id")
        if cid is not None:
            by_id[str(cid)] = g
        items.append((c.get("text", ""), g))
    return by_id, items


def _figure_grade(fig: dict, by_id: dict, items: list, sim_threshold: float = 0.6):
    """求图绑定 claim 的证据档:claim_id 精确 > claim 文本精确 > 语义相似(≥阈值);无匹配→None(不 flag)。"""
    cid = fig.get("claim_id")
    if cid is not None and str(cid) in by_id:
        return by_id[str(cid)]
    text = (fig.get("claim") or "").strip()
    if not text:
        return None
    for t, g in items:
        if t and t.strip() == text:
            return g
    if _HAS_SEM and items:
        best_g, best_s = None, 0.0
        for t, g in items:
            if not t:
                continue
            s = _sem_sim(text, t)
            if s > best_s:
                best_s, best_g = s, g
        if best_s >= sim_threshold:
            return best_g
    return None   # 无法匹配 → 证据档未知 → 保守不 flag


# ───────────────────────── 六个 gate 函数(接 _shared) ─────────────────────────
# critical 措辞红线:visual_honesty 的 gate 名/rule/issue **绝不**含 9→7 信号(不显著/图文不一致/
# 证据/evidence/主图/insignific/mismatch),好让 reroute 给 manual(本阶段重画);misrepresent_evidence
# 的 issue **必带**这些信号,好让 reroute 命中 ROUTES[9] 建议 9→7。(reroute 只匹配 gate名+rule+issue。)
_CRIT_HONESTY = {
    "AXIS_TRUNCATE": "y 轴截断(起点非 0 且无断轴标注)——夸大组间高度差",
    "TWIN_AXIS": "双 y 轴——两轴各自缩放易制造看似相关的伪关系",
    "PIE_3D": "3D 图——透视扭曲面积/高度比例",
}


def _visual_honesty_gate(art: dict) -> "GateResult":
    """视觉不诚实(critical):截 y 轴/双 y 轴伪相关/3D 透视 → 阻断 → 本阶段重画(reroute→manual)。"""
    code = art["plot_code"]
    if not code:
        return GateResult("visual_honesty", "skip", "info", [],
                          note="未提供绘图代码:截 y 轴/双 y 轴诚实门跳过(给 --plot-code)。")
    if not _HAS_FIL:
        return GateResult("visual_honesty", "skip", "info", [],
                          note="同目录 figure_integrity_lint 不可用:视觉诚实门跳过。")
    lint = fil.lint_text(code)
    hits = [f for f in lint if f["category"] in _CRIT_HONESTY]
    if not hits:
        return GateResult("visual_honesty", "pass", "info", [],
                          note="绘图代码未见截 y 轴/双 y 轴伪相关/3D 透视等视觉不诚实形态(spec §4.2 critical)。")
    finds = []
    for h in hits:
        loc = f"plot:L{h['line']}" if h.get("line") else "plot"
        finds.append(Finding(
            loc=loc,
            issue=f"视觉不诚实:{_CRIT_HONESTY[h['category']]}",
            fix="在本阶段重画诚实化:柱图改零基线、或加断轴标注(brokenaxes/对角线)并在图注说明;"
                "双轴拆成两个 panel;3D 改 2D。确属正当(如放大真实细小差异)可经 run_checkpoint 授权"
                "通过并记 notes(spec §6 确认点)",
            evidence=f"category={h['category']};context={h.get('context', '')[:60]}",
            rule=f"visual_honesty.{h['category'].lower()}"))
    return GateResult("visual_honesty", "fail", "critical", finds,
                      note="视觉不诚实(critical,spec §4.2:截 y 轴/双 y 轴伪相关)→ run_checkpoint "
                           "--stage 9 exit 1。**本阶段重画修**(画法不诚实非数据问题:issue 不带 9→7 信号 → "
                           "reroute 给 manual);静态 lint 只抓形态可疑,真误导终判需图注+人,正当截断可授权放行。")


def _misrepresent_evidence_gate(art: dict) -> "GateResult":
    """把不显著当主图/图文不一致(critical,9→7 发起):must 图绑到 grade=none 的 claim → 回 result-analysis。"""
    figures = art["figures"]
    evidence = art["evidence"]
    if not figures:
        return GateResult("misrepresent_evidence", "skip", "info", [],
                          note="未提供图↔claim 绑定(figures 或带 claim/优先级的规划卡):"
                               "把不显著当主图门跳过。")
    if evidence is None:
        return GateResult("misrepresent_evidence", "skip", "info", [],
                          note="未随附 result-analysis 的 evidence_strength.json:无法核图对应证据强度"
                               "(给 --evidence)。")
    by_id, items = _index_evidence(evidence)
    finds = []
    for fig in figures:
        if _prio(fig.get("priority")) != "must":
            continue   # 只查主图(must);可删/可做/附录不算"当主图"
        grade = _figure_grade(fig, by_id, items)
        if grade == "none":
            fid = fig.get("figure_id") or "?"
            claim_ref = fig.get("claim_id") or (fig.get("claim") or "")[:30]
            finds.append(Finding(
                loc=str(fid),
                issue=f"把不显著结果当主图:主图 {fid} 绑定的 claim 证据档=none(不显著/CI 跨 0/q≥.05),"
                      f"却作为支撑核心论点的主图——图与证据强度不一致(图文不一致)",
                fix="回 result-analysis(9→7)核该图对应的证据强度:补/强化证据使其达显著,或把该图降为"
                    "附录/改为如实展示『未见显著差异』,不当主图",
                evidence=f"figure={fid};claim={claim_ref};grade=none;priority=must",
                rule="misrepresent_evidence.insignificant_as_main"))
    if not finds:
        return GateResult("misrepresent_evidence", "pass", "info", [],
                          note="主图均绑到有证据档(weak+)的 claim;无『把不显著当主图』。"
                               "(图↔claim 绑定是启发式,精确逐图匹配需规划卡写 claim_id。)")
    return GateResult("misrepresent_evidence", "fail", "critical", finds,
                      note="把不显著当主图/图文不一致(critical)→ **9→7 回炉发起**:reroute 按"
                           "「不显著/图文不一致/证据」信号建议回 result-analysis 核该图对应的证据强度。"
                           "figure 是 9→7 回边发起方。图↔claim 绑定为启发式,终判仍需人。")


def _error_bars_gate(art: dict) -> "GateResult":
    """误差棒缺失/未标类型(warn,spec §4.2):柱图无误差棒 / 有误差棒未标 SD/SEM/CI。"""
    code = art["plot_code"]
    if not code or not _HAS_FIL:
        return GateResult("error_bars", "skip", "info", [],
                          note="未提供绘图代码或 figure_integrity_lint 不可用:误差棒门跳过。")
    cats = {"BAR_NO_ERR", "ERRBAR_NO_TYPE", "BAR_PLOT_SMALL"}
    hits = [f for f in fil.lint_text(code) if f["category"] in cats]
    if not hits:
        return GateResult("error_bars", "pass", "info", [],
                          note="未见柱图缺误差棒 / 误差棒未标类型。")
    finds = [Finding(loc=(f"plot:L{h['line']}" if h.get("line") else "plot"),
                     issue=h["issue"], rule=f"error_bars.{h['category'].lower()}",
                     evidence=h.get("context", "")[:60]) for h in hits]
    return GateResult("error_bars", "warn", "major", finds,
                      note="误差棒缺失/未标类型(warn,spec §4.2 不阻断):柱图应带误差棒、图注须注明"
                           "SD/SEM/CI 与 n(Cumming 2007)。该用哪种误差棒、重叠是否显著仍需人判。")


def _colormap_gate(art: dict) -> "GateResult":
    """jet/rainbow 色图(warn):非感知均匀且非色盲安全 → 有序数据改 viridis。warn 非 critical(类别型可辩护)。"""
    code = art["plot_code"]
    if not code or not _HAS_FIL:
        return GateResult("colormap", "skip", "info", [],
                          note="未提供绘图代码或 figure_integrity_lint 不可用:色图门跳过。")
    hits = [f for f in fil.lint_text(code) if f["category"] == "RAINBOW_CMAP"]
    if not hits:
        return GateResult("colormap", "pass", "info", [],
                          note="未见 jet/rainbow 等非感知均匀色图。")
    finds = [Finding(loc=(f"plot:L{h['line']}" if h.get("line") else "plot"),
                     issue=h["issue"], rule="colormap.rainbow_cmap",
                     evidence=h.get("context", "")[:60]) for h in hits]
    return GateResult("colormap", "warn", "minor", finds,
                      note="jet/rainbow 色图(warn):非感知均匀(绿黄处对比骤升)且色盲不安全,有序数据改"
                           "viridis/cividis。**warn 非 critical**:类别型 rainbow + 图注可辩护,静态 lint "
                           "分不清有序/类别(诚实降级)。")


def _display_budget_gate(art: dict) -> "GateResult":
    """集合超预算(warn,spec §4.2):display item 超 venue 上限 → 按砍序裁定。"""
    audit = art["set_audit"]
    if audit is None:
        return GateResult("display_budget", "skip", "info", [],
                          note="未提供规划卡(cards):集合预算门跳过。")
    b = audit["budget"]
    if b["status"] != "fail":
        return GateResult("display_budget", "pass", "info", [], note=b["note"])
    cut = "; ".join(f"{p['figure_id']}→{p['action']}" for p in b.get("cut_plan", []))
    finds = [Finding(loc="figure_set", issue=b["note"], fix=cut or "合并 panel 或与作者权衡",
                     evidence=f"total={b['total']};cap={b['cap']};over={b.get('over_by', 0)}",
                     rule="display_budget.over_cap")]
    return GateResult("display_budget", "warn", "major", finds,
                      note="集合超预算(warn,spec §4.2 不阻断):display item 超 venue 上限,按砍序"
                           "(可删→可做降附录→必做不动)。cap 须用目标刊作者指南权威值。")


def _panel_redundancy_gate(art: dict) -> "GateResult":
    """反冗余(warn):两卡同 claim 同图型族 = 候选冗余 panel。"""
    audit = art["set_audit"]
    if audit is None:
        return GateResult("panel_redundancy", "skip", "info", [],
                          note="未提供规划卡(cards):反冗余门跳过。")
    r = audit["redundancy"]
    if not r.get("pairs"):
        return GateResult("panel_redundancy", "pass", "info", [],
                          note=f"无候选冗余 panel({r.get('mode', '')})。")
    finds = [Finding(loc="+".join(p["cards"]), issue=p["msg"], rule="panel_redundancy.same_claim_family")
             for p in r["pairs"]]
    return GateResult("panel_redundancy", "warn", "minor", finds,
                      note="候选冗余 panel(warn):同 claim 同图型族,可能回答同一科学问题。须人判"
                           "(也可能是有意的 overview→deviation 递进);离线语义档对同义改写会漏判。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装视觉诚实 critical findings:编排 figure_integrity_lint + audit_figure_set + evidence_strength → 六 gate。"""
    project = str(spec.get("project", "unnamed"))
    plot_code = spec.get("plot_code") or ""
    cards = spec.get("cards") or []
    evidence = spec.get("evidence")          # dict | None(已 load)
    cap = spec.get("cap")

    figures = spec.get("figures")
    if figures is None and cards and _HAS_AFS:
        figures = [afs.parse_set_card(t) for t in cards]
    figures = figures or []

    set_audit = afs.audit_set(cards, cap) if (cards and _HAS_AFS) else None

    art = {"project": project, "plot_code": plot_code, "figures": figures,
           "evidence": evidence, "cap": cap, "set_audit": set_audit}

    report = None
    if _SHARED_OK:
        report = run_gates(
            [_visual_honesty_gate, _misrepresent_evidence_gate, _error_bars_gate,
             _colormap_gate, _display_budget_gate, _panel_redundancy_gate],
            art, producer="figure", target=project,
            summary="figure 视觉诚实门:截 y 轴/双 y 轴伪相关(critical,本阶段重画→reroute manual)+ "
                    "把不显著当主图(critical,9→7 回炉发起)+ 误差棒缺失/jet-rainbow/集合超预算/反冗余"
                    "(warn)→ 任一 critical → run_checkpoint --stage 9 exit 1;figure 是 9→7 回炉发起方。",
            fresh_evidence=True)

    return {"project": project, "n_figures": len(figures),
            "has_evidence": evidence is not None, "has_plot_code": bool(plot_code),
            "cap": cap, "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# figure 视觉诚实门:{result['project']}", ""]
    lines.append(f"- 绘图代码:{'有(查截/双轴/误差棒/色图)' if result.get('has_plot_code') else '无(视觉诚实门跳过)'}"
                 f";证据档:{'有 evidence_strength.json' if result.get('has_evidence') else '无(把不显著当主图门跳过)'}"
                 f";图数:{result.get('n_figures', 0)};cap:{result.get('cap')}")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=figure);"
                  f"run_checkpoint --stage 9 聚合,视觉不诚实/把不显著当主图→critical fail→exit 1;"
                  f"figure 是 9→7(把不显著当主图回 result-analysis)回炉发起方。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}  {g.get('note', '')[:56]}")
            for x in g.get("findings", [])[:4]:
                lines.append(f">       · {x['loc']}: {x['issue'][:80]}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    TRUNC = ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n"
             "ax.bar([1,2,3],[10,11,12])\nax.set_ylim(9,13)  # 偷偷截断\n")
    TWIN = ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n"
            "ax.plot(x,y)\nax2 = ax.twinx()\nax2.plot(x,z)\n")
    CLEAN = ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n"
             "# error bars = SEM, n=200 per group\n"
             "ax.errorbar(x,y,yerr=sem,capsize=3,fmt='o')\nax.set_ylim(0,13)\n"
             "ax.imshow(d, cmap='viridis')\n")
    BAR_NOERR = ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n"
                 "ax.bar([1,2,3],[10,11,12])\n")
    RAINBOW = ("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n"
               "ax.imshow(d, cmap='jet')\n")

    # 1. 截 y 轴 → visual_honesty critical → 整体 fail;issue 不带 9→7 信号
    r1 = build({"project": "p1", "plot_code": TRUNC})
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f1["producer"] == "figure", f"producer 应 figure,得 {f1['producer']}")
        names = {g["gate"] for g in f1["gates"]}
        check("visual_honesty" in names, f"门名应含 STAGE_GATES[9] 的 visual_honesty,得 {names}")
        vh = next(g for g in f1["gates"] if g["gate"] == "visual_honesty")
        check(vh["status"] == "fail" and vh["severity"] == "critical",
              "截 y 轴应 visual_honesty critical")
        check(f1["verdict"] == "fail", f"截 y 轴应整体 fail,得 {f1['verdict']}")
        # 关键:visual_honesty 的 gate名+rule+issue 绝不带 9→7 信号(好让 reroute→manual)
        blob = (vh["gate"] + " " + " ".join(x["issue"] + x.get("rule", "")
                                            for x in vh["findings"])).lower()
        sigs = ("不显著", "图文不一致", "证据", "evidence", "主图", "insignific", "mismatch")
        check(not any(s in blob for s in sigs),
              f"visual_honesty 绝不带 9→7 信号(本阶段重画),命中:{[s for s in sigs if s in blob]}")

    # 2. 双 y 轴 → visual_honesty critical
    r2 = build({"project": "p2", "plot_code": TWIN})
    if _SHARED_OK:
        vh2 = next(g for g in r2["findings"]["gates"] if g["gate"] == "visual_honesty")
        check(vh2["status"] == "fail" and vh2["severity"] == "critical",
              "双 y 轴应 visual_honesty critical")
        check(any(x["rule"] == "visual_honesty.twin_axis" for x in vh2["findings"]),
              "应命中 visual_honesty.twin_axis")

    # 3. 把不显著当主图:must 图绑 grade=none claim → misrepresent_evidence critical,issue 带 9→7 信号
    ev_none = ec.build_evidence_json([
        {"claim_id": "c1", "text": "method A outperforms baseline", "q_fdr": 0.3,
         "effect_size": 0.1, "ci95": [-0.2, 0.4], "n": 50}]) if _SHARED_OK else None
    r3 = build({"project": "p3", "plot_code": CLEAN,
                "figures": [{"figure_id": "F1", "claim_id": "c1",
                             "claim": "method A outperforms baseline", "priority": "必做"}],
                "evidence": ev_none})
    if _SHARED_OK:
        f3 = r3["findings"]
        me = next(g for g in f3["gates"] if g["gate"] == "misrepresent_evidence")
        check(me["status"] == "fail" and me["severity"] == "critical",
              "把不显著当主图应 misrepresent_evidence critical")
        check(f3["verdict"] == "fail", "把不显著当主图应整体 fail")
        # 关键:misrepresent_evidence 的 gate名+rule+issue 必带 9→7 信号(好让 reroute→9→7)
        blob3 = (me["gate"] + " " + " ".join(x["issue"] + x.get("rule", "")
                                             for x in me["findings"])).lower()
        check(any(s in blob3 for s in ("不显著", "图文不一致", "证据", "evidence")),
              f"misrepresent_evidence 必带 9→7 信号,blob:{blob3[:80]}")

    # 4. 干净:诚实绘图 + must 图绑 strong claim → 无 critical
    ev_strong = ec.build_evidence_json([
        {"claim_id": "c1", "text": "method A outperforms baseline", "q_fdr": 0.001,
         "effect_size": 0.9, "ci95": [0.4, 1.3], "n": 120}]) if _SHARED_OK else None
    r4 = build({"project": "p4", "plot_code": CLEAN,
                "figures": [{"figure_id": "F1", "claim_id": "c1",
                             "claim": "method A outperforms baseline", "priority": "必做"}],
                "evidence": ev_strong})
    if _SHARED_OK:
        f4 = r4["findings"]
        check(f4["verdict"] != "fail", f"诚实图 + strong 证据不应 fail,得 {f4['verdict']}")
        vh4 = next(g for g in f4["gates"] if g["gate"] == "visual_honesty")
        check(vh4["status"] == "pass", "诚实绘图应 visual_honesty pass")
        me4 = next(g for g in f4["gates"] if g["gate"] == "misrepresent_evidence")
        check(me4["status"] == "pass", "must 图绑 strong claim 应 misrepresent_evidence pass")

    # 5. 误差棒缺失 → error_bars warn(非 critical)
    r5 = build({"project": "p5", "plot_code": BAR_NOERR})
    if _SHARED_OK:
        eb = next(g for g in r5["findings"]["gates"] if g["gate"] == "error_bars")
        check(eb["status"] == "warn" and eb["severity"] != "critical",
              f"柱图无误差棒应 error_bars warn 非 critical,得 {eb['status']}/{eb['severity']}")
        # 仅误差棒缺失(无截/双轴)→ 整体不 fail
        check(r5["findings"]["verdict"] != "fail", "仅误差棒缺失不应整体 fail")

    # 6. rainbow → colormap warn(非 critical)
    r6 = build({"project": "p6", "plot_code": RAINBOW})
    if _SHARED_OK:
        cm = next(g for g in r6["findings"]["gates"] if g["gate"] == "colormap")
        check(cm["status"] == "warn" and cm["severity"] != "critical",
              f"jet 应 colormap warn 非 critical,得 {cm['status']}/{cm['severity']}")

    # 7. 集合超预算 → display_budget warn;反冗余 → panel_redundancy warn
    def _card(fid, claim, ftype, prio):
        return (f"| **figure_id** | `{fid}` |\n| **绑定 claim** | {claim} |\n"
                f"| **优先级** | {prio} |\n| **figure_type** | {ftype} |\n")
    cards = [
        _card("F1", "方法A在三数据集上准确率高于基线", "分组柱状图+误差棒", "必做（支撑核心贡献）"),
        _card("F2", "方法A在三数据集上的准确率优于基线方法", "分组条形图", "可做（增强）"),  # 与 F1 冗余
        _card("F3", "消融各组件贡献", "热力图", "可删（冗余或弱）"),
        _card("F4", "训练收敛曲线", "折线图", "可做（增强）"),
        _card("T1", "超参数设置表", "表格", "可做（增强）"),
    ]
    r7 = build({"project": "p7", "cards": cards, "cap": 3})
    if _SHARED_OK:
        f7 = r7["findings"]
        db = next(g for g in f7["gates"] if g["gate"] == "display_budget")
        check(db["status"] == "warn" and db["severity"] != "critical",
              f"5 件 cap=3 应 display_budget warn 非 critical,得 {db['status']}/{db['severity']}")
        pr = next(g for g in f7["gates"] if g["gate"] == "panel_redundancy")
        check(pr["status"] == "warn", f"F1×F2 同 claim 同族应 panel_redundancy warn,得 {pr['status']}")
        check(f7["verdict"] == "warn", f"仅集合超预算/冗余应整体 warn(不阻断),得 {f7['verdict']}")

    # 8. 可做(非 must)图绑 grade=none → 不算"当主图",不 flag
    r8 = build({"project": "p8",
                "figures": [{"figure_id": "F9", "claim_id": "c1", "priority": "可做"}],
                "evidence": ev_none})
    if _SHARED_OK:
        me8 = next(g for g in r8["findings"]["gates"] if g["gate"] == "misrepresent_evidence")
        check(me8["status"] == "pass", f"非主图(可做)绑不显著 claim 不应 flag,得 {me8['status']}")

    # 9. findings 往返 + 阻断 gate + producer
    if _SHARED_OK:
        rep = FindingsReport.from_json(json.dumps(r1["findings"], ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1,
              "findings 应可往返且有阻断 gate")
        check(rep.producer == "figure", "往返后 producer 仍 figure")

    # 10. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 11. markdown 不崩
    check("视觉诚实门" in to_markdown(r1), "markdown 应含视觉诚实门标题")

    if failures:
        print("[SELFTEST][visual_honesty_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][visual_honesty_gate] OK:截 y 轴 critical(本阶段重画,不带 9→7 信号) / 双 y 轴 critical / "
          "把不显著当主图 critical(带 9→7 信号,9→7 发起) / 诚实图+strong pass / 误差棒缺失 warn / "
          "jet warn / 集合超预算 warn / 反冗余 warn / 非主图不误 flag / findings(figure) 往返"
          + ("" if _SHARED_OK else "(_shared 不可达,走诚实降级)") + "。")
    return 0


def _load_text(val: str) -> str:
    """字段:是存在的文件路径 → 读文件;否则当作内联正文。"""
    if val and os.path.exists(val):
        with open(val, encoding="utf-8", errors="replace") as f:
            return f.read()
    return val or ""


def main() -> None:
    ap = argparse.ArgumentParser(
        description="figure 视觉诚实/把不显著当主图 Critical 门 producer"
                    "(截 y 轴/双 y 轴→critical→stage 9 exit 1;把不显著当主图→9→7 回炉发起方)")
    ap.add_argument("--spec", help="spec JSON(project/plot_code/cards/figures/evidence/cap 一把传)")
    ap.add_argument("--plot-code", help="绘图代码 .py 路径(或内联文本)")
    ap.add_argument("--cards", nargs="*", help="规划卡 .md 路径(多张,供集合预算/反冗余/派生图↔claim)")
    ap.add_argument("--evidence", help="result-analysis 的 evidence_strength.json 路径")
    ap.add_argument("--cap", type=int, default=None, help="venue display item 上限(作者指南权威值)")
    ap.add_argument("--project", default="unnamed")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整视觉诚实门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        spec["plot_code"] = _load_text(spec.get("plot_code", ""))
        if spec.get("cards"):
            spec["cards"] = [_load_text(c) for c in spec["cards"]]
        ev_path = spec.get("evidence")
        spec["evidence"] = (ec.load(ev_path) if (ev_path and _SHARED_OK and os.path.exists(ev_path))
                            else None)
    else:
        plot_code = _load_text(args.plot_code) if args.plot_code else ""
        cards = [_load_text(c) for c in args.cards] if args.cards else []
        evidence = (ec.load(args.evidence) if (args.evidence and _SHARED_OK
                                               and os.path.exists(args.evidence)) else None)
        if not (plot_code or cards):
            ap.error("需要 --spec 或 --plot-code/--cards(或 --selftest)")
        spec = {"project": args.project, "plot_code": plot_code, "cards": cards,
                "evidence": evidence, "cap": args.cap}

    result = build(spec)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整视觉诚实门 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
