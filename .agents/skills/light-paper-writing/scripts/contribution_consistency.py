#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contribution_consistency.py — 贡献跨章节一致性核验（把 paper-writing 招牌 claim 工具化）。

为什么有这个脚本（补 paper-writing 最大的 claim-vs-code 缺口）
----------------------------------------------------
SKILL 把"贡献三处一致（abstract/intro/conclusion 措辞对齐）"当深层 novelty 的**招牌示范**
反复强调，但三个脚本里没有任何一个做跨章节贡献一致性核验——这个最有区分度的深层检查完全
靠 LLM 裸眼。而三处贡献句分散在长稿首尾，恰是裸模型最易遗漏不一致的地方（如 abstract 说
"raises 3.1 points" 但 conclusion 只说 "improves performance"，审稿人会质疑贡献缩水/夸大）。
本脚本把它落成可复现检查：抽三处贡献句，跨章节匹配，flag 数字漂移 / 强度漂移 / 覆盖漂移。

三类漂移（category=contribution_drift，入 _shared/findings_schema）
----------------------------------------------------------------
  NUMBER-DRIFT：同一贡献在某章节带量化指标（3.1 points / 76.1%）而在另一章节缺失或数字不同
  STRENGTH-DRIFT：同一贡献的断言强度跨章节差≥1 档（demonstrate↔improve↔may）
  COVERAGE-DRIFT：abstract/intro 声明的贡献在 conclusion 找不到对应（虎头蛇尾），或反之

匹配用 _shared/semantic_sim（挂接地基契约2，非词面 Jaccard）。⚠ 诚实边界：离线档对纯同义
改写匹配偏弱（真用注入 embedding 档提召回）；启发式抽贡献句会漏/误报，**不替代人读三处对齐**。

用法：
  python contribution_consistency.py --in draft.md
  python contribution_consistency.py --in draft.md --json     # light.findings.v1
  python contribution_consistency.py --selftest
"""
from __future__ import annotations
import argparse
import json
import re
import sys

# 规范 bootstrap(向上走目录树找含 _shared 包的仓库根)，治 v1 硬编码 ../../_shared 在 v2 仓库根上移后必断之脆(见 _shared/README.md)。
import pathlib  # noqa: E402
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.semantic_sim import similarity as _sem_sim  # noqa: E402
    _HAS_SEM = True
except Exception:
    _HAS_SEM = False
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    _HAS_FINDINGS = True
except Exception:
    _HAS_FINDINGS = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 章节标题识别
_SEC_PATS = {
    "abstract": re.compile(r"^\s*#{0,4}\s*\d*\.?\s*(abstract|摘要)\b", re.I),
    "introduction": re.compile(r"^\s*#{0,4}\s*\d*\.?\s*(introduction|引言|绪论)\b", re.I),
    "conclusion": re.compile(r"^\s*#{0,4}\s*\d*\.?\s*(conclusions?|结论|总结|结语)\b", re.I),
}
# 贡献信号词（用词干 + \w* 吸收时态/单复数：propose/proposed/proposes、show/showed…）
_CONTRIB = re.compile(
    r"\bwe\s+(?:also\s+|further\s+|then\s+|first\s+|additionally\s+)?"
    r"(propos|present|introduc|develop|design|contribut|show|demonstrat|achiev|establish|"
    r"prov|find|provid|reduc|improv|outperform|gain|surpass)\w*"
    r"|our\s+(?:main\s+)?contribution|提出|贡献|本文(提出|设计|实现)|我们(提出|设计)", re.I)
# 量化指标
_METRIC = re.compile(r"\d+\.?\d*\s*(?:%|percentage\s*points?|points?|pp|×|x倍|倍|个百分点|p\s*[<=]\s*0?\.\d+)", re.I)
_NUM = re.compile(r"\d+\.?\d*")
# 断言强度分档（越大越强）
_STRENGTH = [
    (re.compile(r"\b(demonstrate|establish|prove|confirm)\b", re.I), 3),
    (re.compile(r"\b(show|achieve|outperform|improv|reduc|increas|gain|surpass)", re.I), 2),
    (re.compile(r"\b(suggest|indicate|may|might|could|appear|提出)\b", re.I), 1),
]
_STRENGTH_NAME = {3: "强(demonstrate档)", 2: "中(show/improve档)", 1: "弱(suggest/may档)", 0: "未定"}
MATCH_THRESHOLD = 0.5


def split_sections(text: str) -> dict:
    """按标题把正文切成 abstract/introduction/conclusion 段（其余忽略）。"""
    lines = text.splitlines()
    secs, cur = {}, None
    for ln in lines:
        matched = None
        for name, pat in _SEC_PATS.items():
            if pat.match(ln):
                matched = name
                break
        if matched:
            cur = matched
            secs.setdefault(cur, [])
            continue
        # 遇到其它 section 标题则离开当前段
        if re.match(r"^\s*#{1,4}\s+\S", ln) and cur and not any(p.match(ln) for p in _SEC_PATS.values()):
            cur = None
        if cur is not None:
            secs[cur].append(ln)
    return {k: "\n".join(v).strip() for k, v in secs.items()}


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _strength(sent: str) -> int:
    for pat, val in _STRENGTH:
        if pat.search(sent):
            return val
    return 0


def extract_contributions(sec_text: str) -> list:
    """抽含贡献信号词的句子 + 其量化指标集合 + 强度。"""
    out = []
    for s in _sentences(sec_text):
        if _CONTRIB.search(s):
            metrics = set(_NUM.findall(" ".join(_METRIC.findall(s))))
            out.append({"text": s, "metrics": metrics, "strength": _strength(s)})
    return out


def _best_match(c, candidates: list):
    """在 candidates 里找与 c 语义最相近的贡献，返回 (idx, sim) 或 (None, 0)。"""
    best_i, best_s = None, 0.0
    for i, d in enumerate(candidates):
        sim = _sem_sim(c["text"], d["text"]) if _HAS_SEM else (1.0 if c["text"] == d["text"] else 0.0)
        if sim > best_s:
            best_i, best_s = i, sim
    return best_i, best_s


def check_consistency(text: str) -> dict:
    secs = split_sections(text)
    contribs = {k: extract_contributions(v) for k, v in secs.items()}
    issues = []

    abstr = contribs.get("abstract", [])
    concl = contribs.get("conclusion", [])
    intro = contribs.get("introduction", [])

    # abstract 的每条贡献：在 conclusion 找匹配，比数字/强度；无匹配=覆盖漂移
    for c in abstr:
        idx, sim = _best_match(c, concl)
        if idx is None or sim < MATCH_THRESHOLD:
            issues.append({"code": "COVERAGE-DRIFT", "severity": "major",
                           "loc": "abstract", "text": c["text"][:90],
                           "msg": "abstract 的此贡献在 conclusion 找不到对应——虎头蛇尾，conclusion 应呼应每条贡献。"})
            continue
        m = concl[idx]
        # 数字漂移：abstract 有量化指标但 conclusion 无，或数字不同
        if c["metrics"] and not (c["metrics"] & m["metrics"]):
            issues.append({"code": "NUMBER-DRIFT", "severity": "major",
                           "loc": "abstract↔conclusion", "text": c["text"][:70],
                           "msg": f"贡献量化指标跨章节不一致：abstract={sorted(c['metrics'])} 但 "
                                  f"conclusion={sorted(m['metrics']) or '无数字'}——对齐数字或都给/都不给。"})
        # 强度漂移：差 ≥1 档
        if c["strength"] and m["strength"] and abs(c["strength"] - m["strength"]) >= 1:
            issues.append({"code": "STRENGTH-DRIFT", "severity": "minor",
                           "loc": "abstract↔conclusion", "text": c["text"][:70],
                           "msg": f"贡献断言强度漂移：abstract={_STRENGTH_NAME[c['strength']]} vs "
                                  f"conclusion={_STRENGTH_NAME[m['strength']]}——同一贡献措辞强度应一致。"})

    # intro 列了贡献但 abstract 完全没提（反向覆盖）——仅当两节都有内容时检
    for c in intro:
        if abstr and _best_match(c, abstr)[1] < MATCH_THRESHOLD and _best_match(c, concl)[1] < MATCH_THRESHOLD:
            issues.append({"code": "COVERAGE-DRIFT", "severity": "minor",
                           "loc": "introduction", "text": c["text"][:90],
                           "msg": "introduction 的此贡献在 abstract/conclusion 均无对应——三处贡献应一致覆盖。"})

    by = {"major": 0, "minor": 0}
    for i in issues:
        by[i["severity"]] = by.get(i["severity"], 0) + 1
    return {"sections_found": sorted(secs.keys()),
            "n_contrib": {k: len(v) for k, v in contribs.items()},
            "n_issues": len(issues), "by_severity": by, "issues": issues,
            "match_mode": "semantic_sim" if _HAS_SEM else "exact-fallback"}


def to_findings(rep: dict) -> dict:
    if not _HAS_FINDINGS:
        gates = [{"gate": "contribution_consistency",
                  "status": "fail" if rep["by_severity"].get("major") else ("warn" if rep["issues"] else "pass"),
                  "severity": "major" if rep["by_severity"].get("major") else "minor",
                  "findings": [{"loc": i["loc"], "issue": i["msg"], "fix": "", "rule": i["code"]} for i in rep["issues"]]}]
        verdict = "warn" if rep["issues"] else "pass"
        return {"schema": "light.findings.v1", "producer": "paper-writing", "target": "draft.md",
                "verdict": verdict, "gates": gates, "summary": f"贡献一致性:{rep['n_issues']}漂移",
                "fresh_evidence": True, "_degraded": True}
    r = FindingsReport(producer="paper-writing", target="draft.md", fresh_evidence=True,
                       summary=f"贡献跨章节一致性：{rep['n_issues']} 处漂移")
    if not rep["issues"]:
        r.gates.append(GateResult("contribution_consistency", "pass", "info"))
    for i in rep["issues"]:
        # 贡献漂移是 presentation/significance 风险，不阻断流水线（major→warn 级 gate）
        sev = "major" if i["severity"] == "major" else "minor"
        r.gates.append(GateResult("contribution_drift", "warn", sev,
                                  [Finding(i["loc"], i["msg"], evidence=i["text"], rule=i["code"])]))
    return r.finalize().to_dict()


def to_markdown(rep: dict) -> str:
    b = rep["by_severity"]
    lines = [f"# 贡献跨章节一致性 — 章节{rep['sections_found']} 贡献句{rep['n_contrib']}"
             f"｜{rep['n_issues']} 漂移（major={b.get('major',0)} minor={b.get('minor',0)}，{rep['match_mode']}）\n"]
    if not rep["issues"]:
        lines.append("✓ abstract/intro/conclusion 贡献数字与强度一致、互相呼应。")
    for i in rep["issues"]:
        lines.append(f"- [{i['severity']}] {i['code']} @ {i['loc']}：{i['msg']}\n    « {i['text']} »")
    lines.append("\n> 启发式抽贡献句 + 语义匹配，会漏/误报；离线档对同义改写偏弱(真用注入 embedding)；不替代人读三处对齐。")
    return "\n".join(lines)


def _selftest() -> int:
    print("### contribution_consistency 离线自测", file=sys.stderr)
    draft = """
# Abstract
We propose a novel tracking method that improves accuracy by 3.1 points over the baseline.
We also demonstrate a new calibration module reducing error by 12 percent.

# 1. Introduction
We propose a novel tracking method for dense scenes.
We further design a contrastive loss for robustness.

# 5. Conclusion
We proposed a novel tracking method that improves accuracy.
"""
    rep = check_consistency(draft)
    codes = {i["code"] for i in rep["issues"]}
    print(to_markdown(rep), file=sys.stderr)
    # tracking 贡献:abstract 有 3.1 points,conclusion 无数字 → NUMBER-DRIFT
    assert "NUMBER-DRIFT" in codes, (codes, rep["issues"])
    # calibration 贡献只在 abstract,conclusion 无 → COVERAGE-DRIFT
    assert "COVERAGE-DRIFT" in codes, codes
    print("[1] NUMBER-DRIFT + COVERAGE-DRIFT 命中 ... OK", file=sys.stderr)

    # 一致草稿:三处贡献数字与强度一致 → 无 major
    good = """
# Abstract
We propose method X that improves accuracy by 3.1 points.

# Introduction
We propose method X improving accuracy.

# Conclusion
We proposed method X that improves accuracy by 3.1 points.
"""
    rg = check_consistency(good)
    print(f"[good] issues={[i['code'] for i in rg['issues']]}", file=sys.stderr)
    assert not any(i["severity"] == "major" for i in rg["issues"]), rg["issues"]
    print("[2] 一致草稿无 major 漂移 ... OK", file=sys.stderr)

    # section 切分
    secs = split_sections(draft)
    assert set(secs) >= {"abstract", "introduction", "conclusion"}, secs
    assert "calibration" in secs["abstract"] and "contrastive" in secs["introduction"], secs
    print("[3] 三章节切分正确 ... OK", file=sys.stderr)

    # findings 转换
    f = to_findings(rep)
    assert f["schema"] == "light.findings.v1", f
    print("[4] findings 转换 ... OK", file=sys.stderr)

    print("[selftest] PASS contribution_consistency offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="贡献跨章节一致性核验")
    ap.add_argument("--in", dest="infile", help="草稿 md 路径")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest or not args.infile:
        return _selftest()
    with open(args.infile, encoding="utf-8") as f:
        rep = check_consistency(f.read())
    print(json.dumps(to_findings(rep), ensure_ascii=False, indent=2) if args.json else to_markdown(rep))
    return 1 if rep["by_severity"].get("major") else 0


if __name__ == "__main__":
    sys.exit(main())
