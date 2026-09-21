#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""venue_risk_gate.py — venue-matching 的**预警风险 warn-findings producer**（stage 12，warn-only）。

消费 `venue_signal.py` 的多信号 JSON（--signals-json），编排成机读 `light.findings.v1`
（producer=**venue-matching**）。**门型诚实（与前 11 技能根本不同）**：

  venue-matching **不在 STAGE_GATES**（run_checkpoint keys 无 12）、**非回边发起方**（reroute ROUTES 无 12）。
  spec §1.2(e)/§2.2/§6：选 venue 是**决策点(不可逆战略)**，总控**绝不替用户定 venue**。
  ⇒ 本 producer **只产 warn/info，绝不产 critical**：预警刊不是机器「一票否决」，而是
     **warn 启发信号 + 指向权威人工名单 + 在决策点让用户看着风险自己定**。
     run_checkpoint --stage 12 聚合本报告 → verdict=warn → **exit 0 不阻断**（演示 warn 非 critical）。

为什么 warn 不 critical（对标 §competitors）：连专业付费库(Cabells, 74 指标/3 级严重度)都靠
**多指标 + 人工取证**——掠夺/劫持判定**非机器能终判**。DOAJ 未收录 ≠ 掠夺（可能订阅刊）；
外向自引高 ≠ 操纵（综述/窄领域刊天然高）。故只作 warn 提示 + 指人工核当前权威名单。

四类 warn/info（**全 warn/info/skip，无 fail/critical**）：
  ① **predatory_signal(warn/major)**：DOAJ 未收录且收 APC / 超快审稿(不保证录用) / 发文激增 /
     外向自引偏高——TCS+Cabells 启发，每条带「非掠夺终判、去查权威名单」caveat。
  ② **scope_match(warn/minor)**：稿件→venue 语义契合=低（venue_signal 信号6）→ 投错 scope 浪费周期。
  ③ **whitelist(pass/info/skip)**：DOAJ 收录(+Seal)=正面信号；in_doaj=None→skip(查询失败≠未收录)。
  ④ summary 指针：Cabells / Beall 存档 / Retraction Watch 劫持 / 中科院预警 / Think-Check-Submit
     **当前版**（人工核，**绝不内嵌易腐名单**，铁律 2）。

**warn 措辞红线**：venue-matching **无回边出边**（ROUTES 无 12，reroute→manual），issue/fix **绝不写
「回炉上游」**——只指「决策点由用户定夺 / 对照权威名单人工核 / 换 venue」（本阶段决策内消化）。

用法：
  python venue_risk_gate.py --signals-json venue_signal_out.json --report risk_findings.json
  python venue_risk_gate.py --signals-json sig.json     # 仅出报告 md（不写 findings）
  python venue_risk_gate.py --selftest                  # 离线合成信号自测

依赖：纯 Python stdlib + _shared(findings_schema/gate_runner, 规范 bootstrap)。_shared 不可达 → 诚实降级。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 规范 bootstrap（_shared/README.md）：向上走目录树找含 _shared 包的仓库根，治硬编码 parents[N] 之脆。
try:
    _ROOT = pathlib.Path(__file__).resolve()
    while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
        _ROOT = _ROOT.parent
    if not (_ROOT / "_shared" / "__init__.py").exists():
        raise ImportError("向上未找到 _shared 包目录（请确保脚本在 Light-Skills 树内）")
    sys.path.insert(0, str(_ROOT))
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    _HAS_FINDINGS = True
except Exception:
    _HAS_FINDINGS = False

PRODUCER = "venue-matching"

# 权威人工名单指针（去查当前版，绝不内嵌——venue 预警数据逐年腐，铁律 2）。
AUTHORITATIVE_POINTERS = (
    "预警判定非机器终判，去对照**当前版**人工核："
    "Cabells Predatory Reports(付费) / Beall 存档 beallslist.net(2017 起仅存档,过期风险高) / "
    "Retraction Watch Hijacked Journal Checker(劫持/克隆刊) / 中科院《国际期刊预警名单》(年度) / "
    "Think-Check-Submit 判刊清单(免费) / 出版商官网+同行评议实据。"
)

# 阈值（启发式参考非判据，输出留痕）。
SELF_CITE_WARN = 0.40          # 外向自引 > 40% → 软提示（非掠夺判据）
VOLUME_SURGE_MIN_WORKS = 2000  # 发文量「激增」软线：近 3 年均量大且上升才提示（合法巨刊亦大，故仅软提示）


def _sig(signals: dict, key: str) -> dict:
    s = (signals or {}).get(key)
    return s if isinstance(s, dict) else {}


def _venue_name(art: dict) -> str:
    v = (art or {}).get("venue") or {}
    return v.get("display_name") or (art.get("query") or {}).get("issn") or "(未知 venue)"


# ───────────────────────── gate ① predatory_signal（warn/major，绝不 critical） ─────────────────────────

def _predatory_signal_gate(art: dict) -> "GateResult":
    signals = art.get("signals") or {}
    name = _venue_name(art)
    finds = []

    # 1.1 DOAJ 未收录且收 APC（OA 收费刊却不在 OA 白名单）——TCS 信号。未收录≠掠夺(可能订阅刊)故须配 APC。
    doaj = ((art.get("whitelist") or {}).get("doaj") or {})
    in_doaj = doaj.get("in_doaj")
    apc = _extract_apc(_sig(signals, "5_apc_quartile"))
    if in_doaj is False and isinstance(apc, (int, float)) and apc > 0:
        finds.append(Finding(
            loc=f"{name}:doaj", rule="predatory.doaj_absent_with_fee",
            issue=f"收 APC(${apc}) 却未被 DOAJ 收录——OA 白名单缺位的软预警信号",
            fix="对照 Think-Check-Submit + 权威预警名单人工核(非掠夺终判)；订阅刊不收录属正常，结合其他信号在决策点定夺"))
    elif in_doaj is None:
        pass  # DOAJ 查询失败 → 不当成未收录（whitelist gate 会标 skip）

    # 1.2 超快审稿（TCS：不保证录用/极短评审）——signal_3 fast_flag
    rc = _sig(signals, "3_review_cycle")
    if rc.get("status") == "ok" and "异常快" in str(rc.get("fast_flag", "")):
        finds.append(Finding(
            loc=f"{name}:review_cycle", rule="predatory.too_fast_review",
            issue=f"审稿周期异常快({rc.get('review_cycle')})——TCS 红线「不保证录用/极短评审」软信号",
            fix="核该刊是否有实质同行评议(独立外审/几位审稿人)；对照权威名单，在决策点定夺"))

    # 1.3 发文量激增（掠夺/水刊量产软信号；合法巨刊亦大，故仅软提示）——signal_1
    vt = _sig(signals, "1_volume_trend")
    if vt.get("status") == "ok" and vt.get("trend") == "rising":
        recent = vt.get("recent3y_mean_works") or 0
        if isinstance(recent, (int, float)) and recent >= VOLUME_SURGE_MIN_WORKS:
            finds.append(Finding(
                loc=f"{name}:volume", rule="predatory.volume_surge",
                issue=f"发文量大且上升(近 3 年均 {recent} 篇/年)——量产软信号(合法巨刊亦如此，非判据)",
                fix="结合自引/审稿/索引综合看，对照中科院预警名单当前版人工核；在决策点定夺"))

    # 1.4 外向自引偏高（v1 口径：outgoing≠掠夺判据，仅弱提示）——signal_2
    sc = _sig(signals, "2_self_citation")
    if sc.get("status") == "ok":
        rate = sc.get("self_ref_rate")
        if isinstance(rate, (int, float)) and rate > SELF_CITE_WARN:
            finds.append(Finding(
                loc=f"{name}:self_cite", rule="predatory.high_outgoing_selfcite",
                issue=f"外向自引偏高({rate:.0%}, >40%)——仅弱提示(综述/窄领域刊天然高，非掠夺判据)",
                fix="掠夺判定须看 incoming 期刊自引率(本工具不算)+领域+预警名单；勿仅凭此劝退"))

    note = AUTHORITATIVE_POINTERS
    if not finds:
        return GateResult("predatory_signal", "pass", "info", [],
                          note="未触发掠夺软信号(DOAJ/审稿/发文量/自引)。" + note)
    # warn/major——绝不 critical：预警是决策点的输入，不机器阻断
    return GateResult("predatory_signal", "warn", "major", finds,
                      note=f"{len(finds)} 项掠夺软信号(warn 非阻断)。" + note)


def _extract_apc(s5: dict):
    """从信号5 取 APC 数值（OpenAlex apc_usd 优先，否则解析卡 apc_fee 的数字）。取不到返回 None。"""
    if not isinstance(s5, dict):
        return None
    v = s5.get("openalex_apc_usd")
    if isinstance(v, (int, float)):
        return v
    fee = str(s5.get("apc_fee") or "")
    import re as _re
    m = _re.search(r"([0-9][0-9,]*)", fee)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


# ───────────────────────── gate ② scope_match（warn/minor，绝不 critical） ─────────────────────────

def _scope_match_gate(art: dict) -> "GateResult":
    name = _venue_name(art)
    s6 = _sig(art.get("signals") or {}, "6_manuscript_fit")
    if s6.get("status") != "ok":
        return GateResult("scope_match", "skip", "info", [],
                          note="无稿件→venue 语义契合信号(venue_signal 未带稿件 --title/--keywords)：方向匹配门跳过。")
    level = s6.get("match_level")
    missing = s6.get("missing_topics") or []
    if level == "低":
        miss = "、".join(str(x) for x in missing[:6]) or "(多数主题词)"
        return GateResult("scope_match", "warn", "minor", [Finding(
            loc=f"{name}:scope", rule="scope.direction_mismatch",
            issue=f"稿件→venue 语义契合=低(fit_score={s6.get('fit_score')})；缺失主题词：{miss}",
            fix="方向明显偏离该刊 scope，投错=浪费一个审稿周期；换更对口的 venue 或在决策点确认")],
            note="方向匹配为启发式参考非真值，最终人工定；属 warn(提示换 scope)非阻断。")
    return GateResult("scope_match", "pass", "info", [],
                      note=f"稿件→venue 语义契合={level}(fit_score={s6.get('fit_score')})，方向无明显偏离。")


# ───────────────────────── gate ③ whitelist（pass/info/skip，正面信号，绝不 warn/critical） ─────────────────────────

def _whitelist_gate(art: dict) -> "GateResult":
    name = _venue_name(art)
    doaj = ((art.get("whitelist") or {}).get("doaj") or {})
    in_doaj = doaj.get("in_doaj")
    if in_doaj is True:
        seal = doaj.get("doaj_seal")
        return GateResult("whitelist", "pass", "info", [],
                          note=f"{name} 被 DOAJ 收录{'(有 Seal,更强信号)' if seal else ''}=OA 白名单正面信号"
                               "(非质量保证，仍看分区/预警)。")
    if in_doaj is None:
        return GateResult("whitelist", "skip", "info", [],
                          note=f"DOAJ 查询失败/未提供——未知，**非未收录**({doaj.get('reason', '')})；投前人工核 doaj.org。")
    # in_doaj False：订阅刊不收录属正常；是否软预警由 predatory gate(配 APC)判，这里只如实标
    return GateResult("whitelist", "skip", "info", [],
                      note=f"{name} 未被 DOAJ 收录——可能是非 OA 订阅刊(正常)；勿单独据此劝退。")


# ───────────────────────── 编排 ─────────────────────────

def build_report(art: dict) -> "FindingsReport":
    name = _venue_name(art)
    rep = run_gates(
        [_predatory_signal_gate, _scope_match_gate, _whitelist_gate],
        artifact=art, producer=PRODUCER, target=name,
        summary=(f"venue 预警风险扫({name})：warn-only(选 venue 是决策点,绝不机器一票否决)。" + AUTHORITATIVE_POINTERS),
        fresh_evidence=True)
    return rep


def render(rep: "FindingsReport") -> str:
    L = [f"# venue 预警风险（warn-only · 决策点输入，非阻断门）— {rep.target}", ""]
    v = rep.compute_verdict()
    mark = {"pass": "✅ 无预警软信号", "warn": "⚠ 有预警软信号(warn,不阻断)", "fail": "⛔ fail"}[v]
    L.append(f"- 整体：**{mark}**（venue-matching 不产 critical：预警是决策点输入，用户拍板）")
    L.append("")
    L.append("| gate | status | severity | findings | note |")
    L.append("| --- | --- | --- | --- | --- |")
    for g in rep.gates:
        L.append(f"| {g.gate} | {g.status} | {g.severity} | {len(g.findings)} | {g.note[:60]}… |")
    L.append("")
    for g in rep.gates:
        for f in g.findings:
            L.append(f"- **[{g.gate}]** {f.issue}")
            L.append(f"  - → {f.fix}")
    L.append("")
    L.append("> ⚠ 预警判定**非机器终判**：" + AUTHORITATIVE_POINTERS)
    L.append("> 🧑 venue-matching 无回边出边：预警不回炉上游，由用户在决策点对照权威名单定夺(换 venue/带风险投/继续核)。")
    return "\n".join(L)


# ───────────────────────── selftest（离线，合成 venue_signal 信号） ─────────────────────────

def _selftest() -> int:
    assert _HAS_FINDINGS, "_shared/findings_schema+gate_runner 必须可导入（规范 bootstrap 失败？）"
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")

    # 合成「掠夺嫌疑」venue_signal 输出：DOAJ 未收录 + 收 APC + 超快审稿 + 发文激增 + 外向自引高
    art_pred = {
        "venue": {"display_name": "Suspect Mega OA Journal"},
        "signals": {
            "1_volume_trend": {"status": "ok", "trend": "rising", "recent3y_mean_works": 5000,
                               "earlier3y_mean_works": 1000},
            "2_self_citation": {"status": "ok", "self_ref_rate": 0.52,
                                "self_ref_direction": "outgoing(本刊引本刊)"},
            "3_review_cycle": {"status": "ok", "review_cycle": "约 5 天",
                               "fast_flag": "审稿异常快需对照掠夺特征"},
            "5_apc_quartile": {"status": "ok", "openalex_apc_usd": 2500},
            "6_manuscript_fit": {"status": "ok", "match_level": "中", "fit_score": 0.4,
                                 "missing_topics": []},
        },
        "whitelist": {"doaj": {"status": "ok", "in_doaj": False}},
    }
    rep = build_report(art_pred)
    pg = [g for g in rep.gates if g.gate == "predatory_signal"][0]
    check(pg.status == "warn" and pg.severity == "major", "掠夺嫌疑 → predatory_signal warn/major")
    rules = {f.rule for g in rep.gates for f in g.findings}
    check("predatory.doaj_absent_with_fee" in rules, "DOAJ 缺+收 APC → 软信号")
    check("predatory.too_fast_review" in rules, "超快审稿 → 软信号")
    check("predatory.volume_surge" in rules, "发文激增 → 软信号")
    check("predatory.high_outgoing_selfcite" in rules, "外向自引高 → 软信号")
    # **关键：绝不 critical**——整体 verdict=warn 不是 fail，无 blocking gate
    check(rep.compute_verdict() == "warn", "整体 verdict=warn（绝不 critical/fail）")
    check(len(rep.blocking_gates()) == 0, "无 blocking gate（venue-matching 绝不一票否决）")
    check(all(g.severity != "critical" for g in rep.gates), "所有 gate severity 均非 critical")
    # warn 措辞红线：issue/fix 绝不含「回炉上游」
    alltext = " ".join(f.issue + f.fix for g in rep.gates for f in g.findings)
    check("回炉" not in alltext, "warn 措辞不含「回炉」(venue 无回边出边)")
    # 指针不内嵌名单（提到去查当前版）
    check("当前版" in rep.summary and "Cabells" in rep.summary, "summary 指权威名单当前版(不内嵌)")

    # 合成「干净」venue：DOAJ 收录(Seal) + 正常审稿 + 稳定发文 + 方向高契合
    art_clean = {
        "venue": {"display_name": "Reputable Journal"},
        "signals": {
            "1_volume_trend": {"status": "ok", "trend": "stable", "recent3y_mean_works": 300},
            "2_self_citation": {"status": "ok", "self_ref_rate": 0.08},
            "3_review_cycle": {"status": "ok", "review_cycle": "约 12 周", "fast_flag": "—"},
            "5_apc_quartile": {"status": "ok", "openalex_apc_usd": 0, "doaj": True},
            "6_manuscript_fit": {"status": "ok", "match_level": "高", "fit_score": 0.7},
        },
        "whitelist": {"doaj": {"status": "ok", "in_doaj": True, "doaj_seal": True}},
    }
    rep2 = build_report(art_clean)
    check(rep2.compute_verdict() == "pass", "干净 venue → 整体 pass")
    wl = [g for g in rep2.gates if g.gate == "whitelist"][0]
    check(wl.status == "pass" and "Seal" in wl.note, "DOAJ 收录+Seal → whitelist pass 正面信号")

    # 方向不匹配（scope=低）→ scope_match warn/minor（非 critical）
    art_offscope = {
        "venue": {"display_name": "Wrong Scope Journal"},
        "signals": {
            "6_manuscript_fit": {"status": "ok", "match_level": "低", "fit_score": 0.15,
                                 "missing_topics": ["quantum cryptography", "lattice"]},
        },
        "whitelist": {"doaj": {"status": "ok", "in_doaj": True}},
    }
    rep3 = build_report(art_offscope)
    sg = [g for g in rep3.gates if g.gate == "scope_match"][0]
    check(sg.status == "warn" and sg.severity == "minor", "方向=低 → scope_match warn/minor")
    check(rep3.compute_verdict() == "warn" and not rep3.blocking_gates(), "scope 不匹配=warn 非阻断")

    # DOAJ 查询失败 → whitelist skip（不当成未收录），不触发掠夺
    art_doajfail = {
        "venue": {"display_name": "Unknown DOAJ Journal"},
        "signals": {"5_apc_quartile": {"status": "ok", "openalex_apc_usd": 1500}},
        "whitelist": {"doaj": {"status": "unavailable", "in_doaj": None, "reason": "DOAJ 查询失败"}},
    }
    rep4 = build_report(art_doajfail)
    wl4 = [g for g in rep4.gates if g.gate == "whitelist"][0]
    check(wl4.status == "skip", "DOAJ 查询失败 → whitelist skip(非未收录)")
    pg4 = [g for g in rep4.gates if g.gate == "predatory_signal"][0]
    check(pg4.status == "pass", "DOAJ=None 不触发 doaj_absent 软信号(查询失败≠未收录)")

    # 订阅刊(DOAJ False 但无 APC) → 不触发掠夺(未收录≠掠夺)
    art_sub = {
        "venue": {"display_name": "Subscription Journal"},
        "signals": {"5_apc_quartile": {"status": "ok", "openalex_apc_usd": 0}},
        "whitelist": {"doaj": {"status": "ok", "in_doaj": False}},
    }
    rep5 = build_report(art_sub)
    check(rep5.compute_verdict() == "pass", "订阅刊(DOAJ未收录+无APC) → pass(未收录≠掠夺)")

    # JSON 往返 + producer 正确
    js = rep.to_json()
    back = FindingsReport.from_json(js)
    check(back.producer == "venue-matching", "producer=venue-matching")
    check(back.verdict == "warn", "往返后 verdict=warn 保真")

    # render 含 warn 提示 + 无回边出边说明
    md = render(rep)
    check("非机器终判" in md and "无回边出边" in md, "render 标预警非终判 + 无回边出边")

    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="venue 预警风险 warn-findings producer（warn-only，绝不 critical；选 venue 是决策点）")
    ap.add_argument("--signals-json", help="venue_signal.py 输出的多信号 JSON 文件")
    ap.add_argument("--report", help="把 light.findings.v1 写到文件（供 run_checkpoint --findings）")
    ap.add_argument("--json", action="store_true", help="stdout 输出机读 findings JSON（默认人读 md）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not _HAS_FINDINGS:
        print("[venue_risk_gate] 致命：_shared/findings_schema+gate_runner 不可导入，"
              "无法产机读 findings。请确保脚本在 Light-Skills 树内（规范 bootstrap）。", file=sys.stderr)
        return 2
    if not args.signals_json:
        ap.error("需要 --signals-json FILE（venue_signal.py 输出）或 --selftest")

    with open(args.signals_json, encoding="utf-8") as fh:
        art = json.load(fh)
    rep = build_report(art)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(rep.to_json())
        print(f"Wrote {args.report}", file=sys.stderr)
    if args.json and not args.report:
        print(rep.to_json())
    else:
        print(render(rep))
    # warn-only producer：始终 exit 0（确定性阻断由 run_checkpoint 负责，且本阶段 verdict 最多 warn 不阻断）。
    return 0


if __name__ == "__main__":
    sys.exit(main())
