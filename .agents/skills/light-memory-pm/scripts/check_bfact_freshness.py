#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bfact_freshness.py — B-fact 裸数值 + 快照超期扫描（把口头"硬性"变成真硬性）。

为什么有这个脚本（补 v1 memory-pm 最大的名不副实缺口）
--------------------------------------------
SKILL.md 把"B-fact 引用三件套（快照值 + [snapshot] 标记 + 用前重核）"和"超期重核
（计量>90 天/许可>365 天）"反复称为**硬性**，但 check_project_card.py 根本不查——
一条声称硬性却零执行的纪律比没有更危险（给虚假安全感）。本脚本把它落成可跑检查：
扫项目卡/决策日志里的可变事实数值，无 [snapshot] 标记的报 BARE_NUMBER，带标记但超期的
报 STALE，并产出可直接喂 literature-search/venue-matching 在线重核的清单。

⚠ 本脚本只**读** .light/ 项目卡/决策日志做扫描（路径由参数给），**不修改 .light/**（只读不写）。

两类发现
--------
  BARE_NUMBER：行内出现可变计量事实（h_index/被引/影响因子/分区/录用率/许可…）的具体数值，
               但无伴随 `[snapshot YYYY-MM-DD, src=...]` 标记——违反 G1/G3 薄缓存纪律，应补标记。
  STALE：带 [snapshot] 标记但快照日期距今超阈值——计量类 >90 天、许可类 >365 天，列入重核清单。

⚠ 诚实边界：正则启发式按关键词+数字识别"可变事实"，会漏报（生造指标名）/误报（恰好含数字的
  普通叙述）；不替代人判断某数值是否真需快照。阈值（90/365 天）是经验默认值，可调。

用法：
  python check_bfact_freshness.py --files project_card.md decision_log.md
  python check_bfact_freshness.py --project-dir <项目 .light/ 目录> --today 2026-06-15
  python check_bfact_freshness.py --selftest
"""
from __future__ import annotations
import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# [snapshot 2026-06-06, src=OpenAlex:venue/..., ...] 标记（src 指向在线/官方源）
SNAP_RE = re.compile(r"\[snapshot\s+(\d{4})-(\d{2})-(\d{2})[^\]]*\]", re.I)
# 计量类可变事实（90 天阈值）：随时间漂移
CIT_METRIC = re.compile(
    r"h[_\- ]?index|h\s*指数|被引|cit(?:ation|ed|es)|影响因子|impact\s*factor|\bIF\b|"
    r"分区|JCR|中科院|录用率|接收率|accept(?:ance)?\s*rate|CCF|SJR|"
    r"star(?:s|数)?|下载量|订阅", re.I)
# 许可/权属类可变事实（365 天阈值）：变动较慢但仍需复核
LIC_METRIC = re.compile(r"许可|licen[sc]e|授权协议|CC[\- ]?BY|\bMIT\b|Apache|\bGPL\b|开源协议|权属", re.I)
_NUM = re.compile(r"\d")
CIT_THRESHOLD_DAYS = 90
LIC_THRESHOLD_DAYS = 365


def _parse_date(y, m, d):
    try:
        return _dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def scan_text(text: str, today: _dt.date, location: str = "<text>") -> list:
    """逐行扫 B-fact 裸数值与快照超期。"""
    findings = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        m_snap = SNAP_RE.search(line)
        value_part = SNAP_RE.sub("", line)   # 去掉快照标记后的"被断言值"部分
        is_cit = bool(CIT_METRIC.search(value_part))
        is_lic = bool(LIC_METRIC.search(value_part))
        if not (is_cit or is_lic):
            continue
        # 计量类要求有数字（"影响因子 5.2"才是值；只提"影响因子"不算）；许可类关键词本身即值
        if is_cit and not _NUM.search(value_part):
            if not is_lic:
                continue
            is_cit = False
        cls = "计量" if is_cit else "许可"
        threshold = CIT_THRESHOLD_DAYS if is_cit else LIC_THRESHOLD_DAYS

        if m_snap:
            sd = _parse_date(*m_snap.groups())
            if sd is None:
                findings.append({"kind": "BAD_SNAPSHOT_DATE", "severity": "major",
                                 "loc": f"{location}:{lineno}", "line": line,
                                 "msg": "snapshot 日期非法，无法判断时效。"})
                continue
            age = (today - sd).days
            if age > threshold:
                findings.append({"kind": "STALE", "severity": "minor",
                                 "loc": f"{location}:{lineno}", "line": line,
                                 "class": cls, "snapshot": sd.isoformat(), "age_days": age,
                                 "msg": f"{cls}类事实快照距今 {age} 天 > {threshold} 天阈值——"
                                        f"投前/引用前用 literature-search/venue-matching 在线重核刷新快照。"})
        else:
            findings.append({"kind": "BARE_NUMBER", "severity": "major",
                             "loc": f"{location}:{lineno}", "line": line, "class": cls,
                             "msg": f"{cls}类可变事实数值无 [snapshot YYYY-MM-DD, src=...] 标记——"
                                    f"违反 B-fact 三件套（值+快照标记+用前重核），补标记或改指针模型。"})
    return findings


def build_recheck_list(findings: list) -> list:
    """把 STALE/BARE 整理成可喂 literature-search/venue-matching 的在线重核清单。"""
    out = []
    for f in findings:
        if f["kind"] in ("STALE", "BARE_NUMBER"):
            out.append({"loc": f["loc"], "class": f.get("class"),
                        "reason": f["kind"], "snapshot": f.get("snapshot"),
                        "age_days": f.get("age_days"), "excerpt": f["line"][:80]})
    return out


def scan_paths(paths: list, today: _dt.date) -> dict:
    all_f = []
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.md"), recursive=True)
        elif p.endswith(".md"):
            files.append(p)
    for fp in sorted(set(files)):
        try:
            with open(fp, encoding="utf-8") as fh:
                all_f += scan_text(fh.read(), today, location=fp)
        except OSError as e:
            all_f.append({"kind": "READ_ERROR", "severity": "major", "loc": fp,
                          "line": "", "msg": str(e)})
    by = {"major": 0, "minor": 0}
    for f in all_f:
        by[f["severity"]] = by.get(f["severity"], 0) + 1
    return {"n_files": len(files), "n_findings": len(all_f), "by_severity": by,
            "findings": all_f, "recheck_list": build_recheck_list(all_f),
            "today": today.isoformat()}


def to_markdown(rep: dict) -> str:
    b = rep["by_severity"]
    lines = [f"# B-fact 时效扫描（今天={rep['today']}）— {rep['n_findings']} 问题"
             f"（BARE/坏快照 major={b.get('major',0)} STALE minor={b.get('minor',0)}）\n"]
    if not rep["findings"]:
        lines.append("✓ 未发现裸数值或超期快照。")
    for f in rep["findings"]:
        lines.append(f"- [{f['severity']}] {f['kind']} @ {f['loc']}：{f['msg']}\n    « {f['line'][:90]} »")
    if rep["recheck_list"]:
        lines.append(f"\n## 重核清单（喂 literature-search/venue-matching 在线刷新，{len(rep['recheck_list'])} 项）")
        for r in rep["recheck_list"]:
            lines.append(f"- {r['loc']} [{r['class']}/{r['reason']}"
                         + (f"/{r['age_days']}天" if r.get('age_days') else "") + f"]：{r['excerpt']}")
    lines.append("\n> 正则启发式，会漏/误报；阈值(90/365天)为经验默认可调；不替代人判断。本脚本只读不改 .light/。")
    return "\n".join(lines)


def _selftest() -> int:
    print("### check_bfact_freshness 离线自测", file=sys.stderr)
    today = _dt.date(2026, 6, 15)
    text = """
# 决策日志
- [2026-06-06] 选刊 X — 该刊 h_index≈220、2yr均被引≈9.19 — 来源 venue-matching
- [2026-06-06] 选刊 Y — 影响因子 5.2 `[snapshot 2026-01-01, src=OpenAlex:venue]` — 来源 venue-matching
- [2025-01-01] 数据集 D — 许可 CC-BY-4.0 `[snapshot 2025-01-01, src=HF-datasets]` — 来源 data-engineering
- [2026-06-10] 选刊 Z — 录用率 25% `[snapshot 2026-06-10, src=OpenAlex:venue]` — 来源 venue-matching
- [2026-06-06] 跟踪改用 OC-SORT — 白羊外观同质化 re-id 不可分 — 来源 idea-critique
""".strip()
    findings = scan_text(text, today, "dlog")
    print(to_markdown({
        "today": today.isoformat(), "n_files": 1, "n_findings": len(findings),
        "by_severity": {"major": sum(1 for f in findings if f["severity"] == "major"),
                        "minor": sum(1 for f in findings if f["severity"] == "minor")},
        "findings": findings, "recheck_list": build_recheck_list(findings)}), file=sys.stderr)
    # 行2: h_index/被引 无 snapshot → BARE_NUMBER
    assert any(f["kind"] == "BARE_NUMBER" and "h_index" in f["line"] for f in findings), findings
    # 行3: 影响因子带 2026-01-01 快照, 距 6-15 约 165 天 >90 → STALE
    assert any(f["kind"] == "STALE" and f.get("class") == "计量" and f["age_days"] > 90
               for f in findings), findings
    # 行4: 许可 2025-01-01 快照, 距今约 530 天 >365 → STALE
    assert any(f["kind"] == "STALE" and f.get("class") == "许可" and f["age_days"] > 365
               for f in findings), findings
    # 行5: 录用率 2026-06-10 快照, 距今 5 天 <90 → 不报
    assert not any("录用率" in f["line"] for f in findings), "新鲜快照不应报"
    # 行6: 无计量事实 → 不报
    assert not any("OC-SORT" in f["line"] for f in findings), "纯方法描述不应报"
    print("[1] BARE_NUMBER + 计量STALE + 许可STALE 命中，新鲜/无指标不误报 ... OK", file=sys.stderr)

    # 重核清单包含 BARE + 两条 STALE
    rl = build_recheck_list(findings)
    assert len(rl) >= 3, rl
    print(f"[2] 重核清单 {len(rl)} 项 ... OK", file=sys.stderr)

    # 干净文本：全带新鲜快照 → 零发现
    clean = "- [2026-06-14] 选刊 — 影响因子 3.1 `[snapshot 2026-06-14, src=OpenAlex:venue]` — venue-matching"
    assert not scan_text(clean, today, "c"), "干净文本不应报"
    # 坏快照日期
    bad = "- 影响因子 3.1 `[snapshot 2026-13-99, src=x]`"
    assert any(f["kind"] == "BAD_SNAPSHOT_DATE" for f in scan_text(bad, today, "b")), "坏日期应报"
    print("[3] 干净文本零误报 + 坏快照日期检出 ... OK", file=sys.stderr)

    print("[selftest] PASS check_bfact_freshness offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="B-fact 裸数值 + 快照超期扫描（只读不改 .light/）")
    ap.add_argument("--files", nargs="*", help="要扫的 .md 文件")
    ap.add_argument("--project-dir", help="项目 .light/ 目录（扫其下所有 .md）")
    ap.add_argument("--today", help="基准日期 YYYY-MM-DD（默认今天；用于可复现/CI）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest or (not args.files and not args.project_dir):
        return _selftest()
    today = _dt.date.today()
    if args.today:
        y, m, d = args.today.split("-")
        today = _dt.date(int(y), int(m), int(d))
    paths = list(args.files or [])
    if args.project_dir:
        paths.append(args.project_dir)
    rep = scan_paths(paths, today)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else to_markdown(rep))
    return 1 if rep["by_severity"].get("major") else 0


if __name__ == "__main__":
    sys.exit(main())
