#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data_feasibility_gate.py — data-engineering 的**数据可行性前置 Critical 门 producer**。

蓝图 §4.3-2 的"及格线"①：很多 idea 死在"数据根本不够/不可得/质量差"。本脚本把**数据可行性
前置门**编排成机读 `light.findings.v1`（producer=**data-engineering**），**数据不足以支撑 idea 所需
统计功效（idea-killing insufficient）→ critical fail** → 被总控 `run_checkpoint --stage 2` 聚合
**exit 1**，`reroute --stage 2` 命中已就位的 `ROUTES[2]`（signals=insufficient/sample/power/功效/
数据不够/样本/不足）→ 建议回边 **2⊣3（拦在 idea 前）**：idea-generation 前置读 data verdict，不够则
先补数据 / 改 idea 降数据门槛。**偏紧（warn）不阻断**（spec §4.2 把"样本量不足/划分不合理"列 warn）。

这是 **v2 净新增的接线**（与 idea 侧 `idea_selfcheck`/`fatal_flaw_gate` 同构）：v1 的 `sample_size_check`/
`data_feasibility` **全是纯工具、零接 `_shared`/`light.findings.v1`**（grep 实证）——本脚本是把它们接成
critical findings producer 的新增层，**不重造**功效粗筛 / 四问判定逻辑（复用同目录港来的脚本）。

两个 gate：
  ① sample_power（功效粗筛）：港来 `sample_size_check.check`（分类每类样本 / 回归 EPV / 检测每类实例的
     **经验阈值**粗筛）→ insufficient=critical（撑不起统计显著）/ warn=偏紧 / ok=过。**经验阈值非 power
     analysis**（诚实边界），主结论样本量仍须正式功效论证。
  ② data_feasibility（四问）：港来 `data_feasibility.assess`（足以支撑 / 质量可靠 / 规模足够 / 特征可挖，
     取最差档）→ insufficient=critical（拦在 idea 前）/ warn=有保留项 / ok=过。规模问可由 ① 自动回填。

诚实约定（名实对齐见 SKILL，铁律 2/3）：
- **功效是经验阈值非 power analysis**：粗筛"低于经验下限就预警"，绝不替代正式样本量论证；阈值经验默认、可调。
- **四问档位是人/脚本判定、非自动真值**：本脚本只**聚合判据 + 出 findings**，不替你判"数据到底够不够"（GIGO）。
- **输入源自 idea 的"数据可行性必答字段"**：idea-generation 立项卡点名 idea 要什么数据/规模/标注 → 本门据此
  填四问 + 功效参数；verdict 再被 idea 阶段前置读到（2⊣3 双向）。本脚本不从 idea 文本自动推可行性。
- **_shared 不可达** → findings 诚实降级 None（不假装产机读交接）。

用法：
  python data_feasibility_gate.py --spec feasibility_spec.json --report feas_findings.json
  python data_feasibility_gate.py --selftest

spec JSON 形如：
  {"project":"goat-estrus", "idea":"...",
   "sample":{"task":"clf","n":90,"classes":3,"per_class":[60,20,10]},
   "feasibility":{"sufficiency":"ok:有判别性特征","quality":"warn:偶发越界",
                  "feature_value":"ok:剔除泄漏列后25维"}}   # scale 缺省由 sample 自动回填
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

# 同目录港来的纯工具（复用不重造：功效经验粗筛 / 四问可行性判定）。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import sample_size_check as sa   # noqa: E402  规模充足性经验粗筛（非 power analysis）
import data_feasibility as df    # noqa: E402  数据先行四问 → 最差档 verdict

# 规范 bootstrap（_shared/README.md）：向上走目录树找含 _shared 包的仓库根，治硬编码 parents[N] 之脆。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    _SHARED_OK = True
except ImportError:                                                          # _shared 不可达：findings 降级
    _SHARED_OK = False


# ───────────────────────── 编排港来的纯工具 ─────────────────────────
def run_sample(spec: dict | None) -> dict | None:
    """跑 sample_size_check.check（经验功效粗筛）。spec 缺省 → None（该 gate 跳过）。"""
    if not spec:
        return None
    return sa.check(spec.get("task", "clf"), int(spec.get("n", 0)),
                    int(spec.get("classes", 0)), int(spec.get("features", 0)),
                    int(spec.get("positives", 0)), spec.get("per_class"))


def run_feasibility(project: str, answers_raw: dict, sample_rep: dict | None) -> dict:
    """跑 data_feasibility.assess（四问最差档）。规模问 Q3 优先用 sample_size_check 结果自动回填。"""
    answers, sources = {}, {}
    for key in ("sufficiency", "quality", "feature_value"):
        if answers_raw.get(key):
            answers[key] = df.parse_answer(answers_raw[key])
    if sample_rep is not None:
        answers["scale"] = df.scale_from_json(sample_rep)      # 复用 v1 转换：粗筛结果 → Q3 (level, note)
        sources["scale"] = "sample_size_check.py"
    elif answers_raw.get("scale"):
        answers["scale"] = df.parse_answer(answers_raw["scale"])
    return df.assess(project, answers, sources)


# ───────────────────────── 两个 gate 函数（接 _shared） ─────────────────────────
def _sample_power_gate_fn(art: dict) -> "GateResult":
    """统计功效粗筛门（insufficient=critical）：撑不起 idea 所需统计显著 → 拦在 idea 前。"""
    rep = art["sample_rep"]
    if rep is None:
        return GateResult("sample_power", "skip", "info", [],
                          note="未提供样本规模参数(sample)：统计功效粗筛跳过。")
    level = rep["level"]
    detail = "；".join(rep.get("findings", []))
    loc = f"{art['project']}:sample(task={rep.get('task')},n={rep.get('n')})"
    if level == "insufficient":
        return GateResult(
            "sample_power", "fail", "critical",
            [Finding(loc=loc,
                     issue=f"数据规模不足以支撑统计功效（insufficient，样本量不足）：{detail}",
                     fix="补采 / 合并小类 / 降特征，或改 idea 降数据门槛（拦在 idea 前，回边 2⊣3）",
                     evidence=rep.get("advice", ""), rule="sample_size.insufficient")],
            note="经验功效粗筛 insufficient（非 power analysis）：撑不起 idea 所需统计显著。")
    if level == "warn":
        return GateResult(
            "sample_power", "warn", "major",
            [Finding(loc=loc, issue=f"样本量偏紧（warn）：{detail}",
                     fix="优先正则 / 特征筛选 / 多次跑多种子，慎报单点指标",
                     rule="sample_size.tight")],
            note="样本量偏紧（warn，不阻断推进）。")
    return GateResult("sample_power", "pass", "info", [],
                      note="样本量在经验阈值之上（仍建议主结论正式 power analysis 背书）。")


def _feasibility_gate_fn(art: dict) -> "GateResult":
    """数据可行性四问门（insufficient=critical）：四问取最差档，idea-killing → 拦在 idea 前。"""
    rep = art["feas_rep"]
    level = rep["verdict_level"]
    worst = [q for q in rep["questions"] if q["level"] == level and level != "ok"]
    detail = "；".join(f"{q['label']}={q['level']}:{q['note']}" for q in worst)
    loc = f"{art['project']}"
    if level == "insufficient":
        return GateResult(
            "data_feasibility", "fail", "critical",
            [Finding(loc=loc,
                     issue=f"数据可行性四问 INSUFFICIENT（数据不够支撑 idea）：{detail}",
                     fix="先补数据 / 补质 / 改 idea（数据可行性前置于 idea 定稿，回边 2⊣3）",
                     evidence=f"verdict={rep['verdict']}", rule="data_feasibility.insufficient")],
            note="四问取最差档=insufficient：数据不足以支撑，拦在 idea 前（2⊣3）。")
    if level == "warn":
        return GateResult(
            "data_feasibility", "warn", "major",
            [Finding(loc=loc, issue=f"数据可行性含保留项（warn）：{detail}",
                     fix="可进 idea，但 idea 须正视保留项、idea-critique 复核 data 维",
                     rule="data_feasibility.caveats")],
            note="含 warn 保留项（可进 idea，不阻断）。")
    return GateResult("data_feasibility", "pass", "info", [],
                      note="四问皆 ok：数据基础充分。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict):
    """组装数据可行性 critical findings：港来功效粗筛 + 四问 → 两 gate。

    spec: {project, idea, sample{task,n,classes,features,positives,per_class}, feasibility{四问 raw}}
    """
    project = str(spec.get("project", "unnamed"))
    sample_rep = run_sample(spec.get("sample"))
    feas_rep = run_feasibility(project, spec.get("feasibility") or {}, sample_rep)
    art = {"project": project, "idea": spec.get("idea", ""),
           "sample_rep": sample_rep, "feas_rep": feas_rep}

    report = None
    if _SHARED_OK:
        report = run_gates([_sample_power_gate_fn, _feasibility_gate_fn], art,
                           producer="data-engineering", target=project,
                           summary="data-engineering 数据可行性前置门：统计功效(经验粗筛)+四问 → "
                                   "insufficient(idea-killing)=critical → run_checkpoint --stage 2 "
                                   "exit 1 → reroute 2⊣3（拦在 idea 前，补数据/改 idea）；偏紧=warn 不阻断。",
                           fresh_evidence=True)
    return {"project": project, "idea": spec.get("idea", ""),
            "sample": sample_rep, "feasibility": feas_rep,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    feas = result["feasibility"]
    lines = [f"# data-engineering 数据可行性前置门：{result['project']}", "",
             f"四问 verdict = **{feas['icon']} {feas['verdict']}**"
             + (f" · 功效粗筛={result['sample']['level']}" if result.get("sample") else ""), ""]
    if result.get("sample"):
        lines += ["## 统计功效粗筛（sample_size_check，经验阈值非 power analysis）", ""]
        lines += [f"- {x}" for x in result["sample"]["findings"]]
        lines.append("")
    lines += ["## 数据先行四问", ""]
    for q in feas["questions"]:
        lines.append(f"- {q['label']}：**{q['level']}** — {q['note']}（{q['source']}）")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** "
                  f"(producer=data-engineering)；run_checkpoint --stage 2 聚合，"
                  f"insufficient→critical fail→exit 1→reroute 2⊣3（拦在 idea 前）。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}")
    else:
        lines += ["", "> _shared 不可达：findings 诚实降级 None（不假装产机读交接）。"]
    return "\n".join(lines)


# ───────────────────────── selftest（离线，确定性） ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 数据不足以支撑功效：分类 3 类、最小类 10 (<50) → sample_power critical；scale 自动回填 → 四问也 insufficient
    spec_bad = {"project": "goat-estrus",
                "idea": "contrastive SSL goat estrus detection from accelerometer",
                "sample": {"task": "clf", "n": 90, "classes": 3, "per_class": [60, 20, 10]},
                "feasibility": {"sufficiency": "ok:有判别性传感器特征",
                                "quality": "ok:质检通过", "feature_value": "ok:25维有效特征"}}
    res = build(spec_bad)
    check(res["sample"]["level"] == "insufficient",
          f"最小类 10<50 应判 insufficient（得 {res['sample']['level']}）")
    check(res["feasibility"]["verdict_level"] == "insufficient",
          "scale 自动回填 insufficient → 四问最差档应 insufficient")
    if _SHARED_OK:
        f = res["findings"]
        check(f and f["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f["producer"] == "data-engineering", "producer 应为 data-engineering")
        check(f["verdict"] == "fail", f"数据不足应整体 fail(critical)，实得 {f and f['verdict']}")
        sp = next(g for g in f["gates"] if g["gate"] == "sample_power")
        check(sp["status"] == "fail" and sp["severity"] == "critical",
              "功效粗筛不足应 critical fail")
        fe = next(g for g in f["gates"] if g["gate"] == "data_feasibility")
        check(fe["status"] == "fail" and fe["severity"] == "critical",
              "四问 insufficient 应 critical fail")
        # 2⊣3 路由信号：阻断 gate 文本须含 ROUTES[2] 的信号（insufficient/sample/power/功效/样本/不足/数据不够）
        rep = FindingsReport.from_json(json.dumps(f, ensure_ascii=False))
        signals = ("insufficient", "sample", "power", "功效", "样本", "不足", "数据不够")
        blob = " ".join(
            (g.gate or "") + " " + " ".join((fd.rule or "") + " " + (fd.issue or "")
                                            for fd in g.findings)
            for g in rep.blocking_gates()).lower()
        check(any(s.lower() in blob for s in signals),
              f"阻断 gate 文本应含 ROUTES[2] 路由信号（供 reroute 建议 2⊣3）；blob={blob[:120]}")
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1,
              "findings 应可往返且有阻断 gate（供 reroute 路由 2⊣3）")

    # 2. 偏紧 warn：回归 EPV=15（10~20）→ sample_power warn；四问其余 ok → 整体 warn（不阻断）
    spec_tight = {"project": "p2", "sample": {"task": "reg", "n": 300, "features": 20},
                  "feasibility": {"sufficiency": "ok:x", "quality": "ok:y", "feature_value": "ok:z"}}
    res2 = build(spec_tight)
    check(res2["sample"]["level"] == "warn", f"EPV=15 应判 warn（得 {res2['sample']['level']}）")
    if _SHARED_OK:
        f2 = res2["findings"]
        check(f2["verdict"] == "warn", f"偏紧应整体 warn（不阻断），实得 {f2['verdict']}")
        sp2 = next(g for g in f2["gates"] if g["gate"] == "sample_power")
        check(sp2["status"] == "warn" and not sp2["severity"] == "critical",
              "偏紧功效应 warn 非 critical（spec §4.2：样本量不足列 warn）")

    # 3. 充足 + 四问皆 ok → pass
    spec_ok = {"project": "p3", "sample": {"task": "clf", "n": 600, "classes": 3, "features": 10},
               "feasibility": {"sufficiency": "ok:a", "quality": "ok:b", "feature_value": "ok:c"}}
    res3 = build(spec_ok)
    check(res3["sample"]["level"] == "ok", "每类 200、EPV 60 应判 ok")
    if _SHARED_OK:
        f3 = res3["findings"]
        check(f3["verdict"] == "pass", f"充足且四问 ok 应 pass，实得 {f3['verdict']}")

    # 4. 质量 insufficient（非规模路径）：样本充足但质量不可靠 → data_feasibility critical（一票最差档）
    spec_q = {"project": "p4", "sample": {"task": "clf", "n": 600, "classes": 3, "features": 10},
              "feasibility": {"sufficiency": "ok:a", "quality": "insufficient:标注 IAA κ=0.2 不可信",
                              "feature_value": "ok:c"}}
    res4 = build(spec_q)
    if _SHARED_OK:
        f4 = res4["findings"]
        fe4 = next(g for g in f4["gates"] if g["gate"] == "data_feasibility")
        check(fe4["status"] == "fail" and fe4["severity"] == "critical",
              "质量 insufficient → 四问门 critical（非规模路径也能 idea-killing）")
        sp4 = next(g for g in f4["gates"] if g["gate"] == "sample_power")
        check(sp4["status"] == "pass", "样本充足 → 功效门 pass（与四问门独立）")

    # 5. 未提供 sample → 功效门 skip（不静默当 pass）
    res5 = build({"project": "p5", "feasibility": {"sufficiency": "ok:a", "quality": "ok:b",
                                                    "scale": "ok:c", "feature_value": "ok:d"}})
    if _SHARED_OK:
        sp5 = next(g for g in res5["findings"]["gates"] if g["gate"] == "sample_power")
        check(sp5["status"] == "skip", f"无 sample 参数 → 功效门应 skip，实得 {sp5['status']}")

    # 6. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(res["findings"] is None, "_shared 不可达时 findings 应诚实为 None")

    # 7. markdown 不崩 + 含可行性前置门标题
    check("数据可行性前置门" in to_markdown(res), "markdown 应含可行性前置门标题")

    if failures:
        print("[SELFTEST][data_feasibility_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][data_feasibility_gate] OK：数据不足 critical(2⊣3 信号) + 偏紧 warn + 充足 pass + "
          "质量 insufficient critical + 无 sample skip + findings(data-engineering) 全通过"
          + ("" if _SHARED_OK else "（_shared 不可达，findings 走诚实降级路径）") + "。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="data-engineering 数据可行性前置 Critical 门 producer（不足→critical→2⊣3）")
    ap.add_argument("--spec", help="数据可行性 spec JSON（project/idea/sample/feasibility）")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整可行性 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.spec:
        ap.error("需要 --spec feasibility_spec.json（或 --selftest）")

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    result = build(spec)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整可行性 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达，无 findings 可写（诚实不假装）。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    # critical fail → 退出码 1（与 run_checkpoint 同口径，便于单独跑也能确定性阻断）
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
