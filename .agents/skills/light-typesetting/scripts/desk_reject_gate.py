#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""desk_reject_gate.py — typesetting 的 **desk-reject 一票否决 findings producer**（critical 静态门）。

蓝图 §4.3-11 的「及格线」之一：desk-reject 雷区前置（投稿前一票否决项）。本脚本把「投稿合规/匿名扫描」
编排成机读 `light.findings.v1`（producer=**typesetting**）。门名对齐 `STAGE_GATES[11]=[compile, desk_reject]`
（spec §4.2 行 172：typesetting Critical=**编译报错 / desk-reject(页数·双盲)**；warn=警告；消费 findings(命令门)）：

  ① **desk_reject(超页数 / 双盲露作者名 / PDF 元数据露名) = critical(一票否决)**：编排同目录港来 `submission_check`
     的源级静态扫。三种确定形态（submission_check 自身标 severity=high）：
       - **PAGES_OVER**：PDF 页数 > `--max-pages`（venue 给）→ 超页 desk-reject。
       - **BLIND_IDENTITY**：双盲稿含未注释的 \\author/\\thanks/\\affiliation → 露作者身份。
       - **PDF_AUTHOR_META**（双盲下 high）：PDF 元数据 /Author 露名。
     任一 → 阻断 → 被总控 `run_checkpoint --stage 11` 聚合 **exit 1**。
     **无回边出边(铁律核实)**：reroute ROUTES 无 key 11、spec §5 回边表无 typesetting → issue **只指本阶段内修**
     （删减/匿名化），不带跨阶段路由信号 → `reroute --stage 11` 给 **manual**（同 citation，非回边发起方）。

  ② **anonymity(致谢/基金/自指/可识别链接) = warn**：双盲软信号——高风险但非确凿 desk-reject（如 github 链接
     可能已是匿名仓库，机器分不清）→ 诚实降级交人核对。
  ③ **residual(\\todo/TODO/XXX/占位) = warn**：投稿前必清，非 desk-reject 硬错但显业余。
  ④ **bib_integrity(\\cite↔.bib 缺键/重复/冗余) = warn**：**复用 citation 的 `citekey_audit`（跨技能 import，不重造）**。
     缺键→编译出 ??，但 latexmk 仍 exit 0（非 compile_error）→ warn；引用**真实性**归 citation(stage 10)。
  ⑤ **compile_log(.log 细粒度) = warn/skip**：复用同目录港来 `precheck_log` 扫 .log 的 undefined ref/cite、overfull box。
     **诚实:真编译 pass/fail 归 compile 命令门(真 latexmk 退出码),此门只作 .log 细粒度提示,不重复判编译成败。**

这是 **v2 净新增的接线**（与 paper-writing `claim_evidence_gate`、figure `visual_honesty_gate`、citation
`citation_verify_gate` 同构）：**编排港来纯工具 + 接 `_shared` 规范 bootstrap → critical findings producer**，不重造：
  - 源级合规扫：同目录港来 `submission_check`（双盲/页数/元数据/TODO，纯 stdlib 离线）。
  - \\cite↔.bib 对账：**跨技能** import `light-citation/scripts/citekey_audit`（照 experiment-coding `repro_gate`
    跨技能 import data-engineering `split_leakage` 的先例，缺则优雅降级）。
  - .log 扫描：同目录港来 `precheck_log`（de-wrap 长引用名 + 严重度分级）。

诚实约定（名实对齐见 SKILL，铁律 2）：
- **页数限不内嵌**：依 venue 且逐年变 → 走 `--max-pages`（用户/venue 给），不给则页数检查 skip，机器不替猜 venue 限值。
- **只扫静态雷区**：渲染版式级合规（压缩 PDF 还数不准）、语义级露馅（正文点单位名/图里 logo）静态扫查不全 →
  命中是「高风险需人工确认」，非绝对违规；终判靠人 + 目标 venue 投稿须知 + 官方 analyzer。
- **compile 与 desk_reject 分工**：真编译成败 = compile **命令门**（compile_driver 退出码）；本 producer 只产 desk-reject
  静态门 findings。二者经 `run_checkpoint --stage 11 --gate "compile=..." --findings desk_reject.json` 一并聚合。
- **_shared 不可达** → findings 诚实降级 None（不假装产机读交接）。

用法：
  # 扫一份稿(源级 + 可选 PDF 页数/元数据 + \\cite↔.bib 对账 + .log)→ 产 findings
  python desk_reject_gate.py --tex paper.tex --pdf paper.pdf --double-blind --max-pages 8 \
      --bib refs.bib --log build/paper.log --report desk_reject_findings.json
  python desk_reject_gate.py --selftest
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

# 同目录港来的纯工具（复用不重造：源级合规扫 / .log 扫描）。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import submission_check as sc      # noqa: E402  双盲/页数/元数据/TODO 源级静态扫
    _HAS_SC = True
except Exception:
    _HAS_SC = False
try:
    import precheck_log as pl          # noqa: E402  .log 扫描（de-wrap + 严重度）
    _HAS_PL = True
except Exception:
    _HAS_PL = False

# 规范 bootstrap（_shared/README.md）：向上走目录树找含 _shared 包的仓库根，治硬编码 parents[N] 之脆。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent

# 跨技能复用 citation 的 \cite↔.bib 对账（不重造；照 experiment-coding repro_gate 跨技能 import 先例）。
_CITATION_SCRIPTS = _ROOT / "skills" / "light-citation" / "scripts"
try:
    if _CITATION_SCRIPTS.is_dir():
        sys.path.insert(0, str(_CITATION_SCRIPTS))
    import citekey_audit as cka        # noqa: E402  \cite↔.bib 对账（纯 stdlib 离线，citation 域）
    _HAS_CKA = True
except Exception:
    _HAS_CKA = False

sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False

# submission_check 的 code → desk_reject 归类。critical 仅对「确定形态 + severity=high」生效。
_CRITICAL_CODES = {
    "PAGES_OVER", "BLIND_IDENTITY", "PDF_AUTHOR_META",
    "TEMPLATE_CLASS", "REQUIRED_PACKAGE", "PAGE_SIZE", "FONT_NOT_EMBEDDED",
}   # profile 明示的客观一票否决项（须 severity=high）
_ANON_WARN_CODES = {"BLIND_ACK", "BLIND_LINK", "BLIND_SELFREF"}         # 双盲软信号 warn
_RESIDUAL_CODES = {"RESIDUAL_TODO"}                                     # 残留占位 warn


# ───────────────────────── 五个 gate 函数（接 _shared） ─────────────────────────
# critical 措辞红线：typesetting 无回边出边（ROUTES 无 key 11），issue **只指本阶段内修**
# （删减/匿名化），不带任何跨阶段路由信号 → reroute --stage 11 给 manual。
def _desk_reject_gate(art: dict) -> "GateResult":
    """desk-reject 一票否决（critical）：超页数 / 双盲露作者名 / PDF 元数据露名 → 阻断 → 本阶段内修。"""
    if not art["scanned"]:
        return GateResult("desk_reject", "skip", "info", [],
                          note="未提供 --tex/--pdf 扫描输入：desk-reject 门跳过。")
    crit = [f for f in art["sub_findings"]
            if f["code"] in _CRITICAL_CODES and f["severity"] == "high"]
    if not crit:
        return GateResult("desk_reject", "pass", "info", [],
                          note="未见超页/双盲露名等一票否决雷区（诚实局限：只扫静态雷区，"
                               "渲染版式级/语义级露馅 + 目标 venue 投稿须知仍须人工核）。")
    finds = []
    for f in crit:
        if f["code"] == "PAGES_OVER":
            finds.append(Finding(
                loc="pdf:pages", issue=f"页数超限：{f['msg']}",
                fix="在本阶段内修：删减正文/移附录/压缩图表到 venue 页数限内"
                    "（typesetting 无回边出边，自身门在 stage 11 内修）",
                evidence=f["code"], rule="desk_reject.pages_over"))
        elif f["code"] == "BLIND_IDENTITY":
            finds.append(Finding(
                loc="tex:author", issue=f"双盲露作者身份：{f['msg']}",
                fix="在本阶段内修：注释/匿名化 \\author\\thanks\\affiliation（投稿版），终稿录用后再加回",
                evidence=f["code"], rule="desk_reject.blind_identity"))
        elif f["code"] == "PDF_AUTHOR_META":
            finds.append(Finding(
                loc="pdf:meta", issue=f"双盲 PDF 元数据露名：{f['msg']}",
                fix="在本阶段内修：hyperref `pdfauthor={}` 清空，或导出后 exiftool 清元数据",
                evidence=f["code"], rule="desk_reject.pdf_author_meta"))
        else:
            finds.append(Finding(
                loc=f"profile:{f['code'].lower()}",
                issue=f"profile 声明的格式硬规则未满足：{f['msg']}",
                fix="在本阶段内修：按当前 venue/profile 的来源记录修模板、版芯或字体后重编",
                evidence=f["code"], rule=f"desk_reject.{f['code'].lower()}"))
    note = (f"desk-reject 一票否决（critical，spec §4.2）：超页/双盲/明示格式硬规则 {len(finds)} 项 → run_checkpoint "
            f"--stage 11 exit 1。**本阶段内修**（版式/匿名化；typesetting 无回边出边 → reroute 给 manual）。"
            f"诚实：只扫静态雷区，渲染版式级/语义级露馅仍须人工 + 目标 venue 投稿须知核对。")
    return GateResult("desk_reject", "fail", "critical", finds, note=note)


def _anonymity_gate(art: dict) -> "GateResult":
    """双盲软信号（warn）：致谢/基金/自指/可识别链接——高风险但非确凿 desk-reject（机器分不清匿名仓库等）。"""
    if not art["scanned"]:
        return GateResult("anonymity", "skip", "info", [], note="未提供扫描输入：匿名软信号门跳过。")
    soft = [f for f in art["sub_findings"] if f["code"] in _ANON_WARN_CODES]
    # 非双盲下的 PDF_AUTHOR_META（med，非 high）也归这里作提示，不进 critical
    soft += [f for f in art["sub_findings"]
             if f["code"] == "PDF_AUTHOR_META" and f["severity"] != "high"]
    if not soft:
        return GateResult("anonymity", "pass", "info", [], note="未见致谢/自指/可识别链接等软露名信号。")
    finds = [Finding(loc=f"tex:{f['code'].lower()}", issue=f["msg"],
                     fix="双盲投稿版核对：致谢/基金移除或匿名、自指改第三人称、链接换匿名仓库",
                     rule=f"anonymity.{f['code'].lower()}") for f in soft]
    return GateResult("anonymity", "warn", "major", finds,
                      note="双盲软信号（warn，非阻断）：致谢/基金/自指/链接高风险但非确凿"
                           "（如 github 链接可能已是匿名仓库），交人核对。")


def _residual_gate(art: dict) -> "GateResult":
    """残留占位（warn）：\\todo/TODO/XXX/占位——投稿前必清（非 desk-reject 硬错但显业余、减印象分）。"""
    if not art["scanned"]:
        return GateResult("residual", "skip", "info", [], note="未提供扫描输入：残留占位门跳过。")
    res = [f for f in art["sub_findings"] if f["code"] in _RESIDUAL_CODES]
    if not res:
        return GateResult("residual", "pass", "info", [], note="未见 TODO/XXX/占位残留。")
    finds = [Finding(loc="tex:todo", issue=f["msg"], fix="投稿前清零所有占位/待办",
                     rule="residual.todo") for f in res]
    return GateResult("residual", "warn", "major", finds,
                      note="残留占位（warn，非阻断）：投稿前必清，审稿人见 TODO/XXX 减印象分。")


def _bib_integrity_gate(art: dict) -> "GateResult":
    """\\cite↔.bib 对账（warn，复用 citation citekey_audit）：缺键→编译 ??、重复定义、冗余键。
    诚实：缺键不致 compile_error（latexmk 仍 exit 0 出 ??）→ warn；真编译 pass/fail 归 compile 命令门；
    引用**真实性**（查无此文/嵌合）归 citation(stage 10)，此门只对账键集不核存在性。"""
    ck = art["citekey_audit"]
    if ck is None:
        return GateResult("bib_integrity", "skip", "info", [],
                          note="未提供 --tex/--bib：\\cite↔.bib 对账门跳过（复用 citation citekey_audit，不重造）。")
    finds = []
    for k in ck.get("missing_keys", []):
        finds.append(Finding(loc=f"cite:{k}", issue=f"\\cite{{{k}}} 引了但 .bib 未定义（编译出 ??）",
                             fix="在 .bib 补该条或改正键名", rule="bib_integrity.missing_key"))
    for k in ck.get("duplicate_bib_keys", []):
        finds.append(Finding(loc=f"bib:{k}", issue=f".bib 重复定义键 `{k}`",
                             fix="合并/删除重复条目", rule="bib_integrity.duplicate_key"))
    uncited = ck.get("uncited_keys", [])
    if uncited:
        finds.append(Finding(loc="bib", issue=f".bib 有 {len(uncited)} 个冗余键（定义但正文未引）",
                             fix="投稿前清理冗余条目（审稿人嫌库脏）", rule="bib_integrity.uncited_key"))
    if not finds:
        return GateResult("bib_integrity", "pass", "info", [], note="\\cite↔.bib 键集对齐，无缺失/重复/冗余。")
    sev = "major" if (ck.get("missing_keys") or ck.get("duplicate_bib_keys")) else "minor"
    return GateResult("bib_integrity", "warn", sev, finds,
                      note="\\cite↔.bib 对账（warn，非阻断，复用 citation citekey_audit）：缺键→编译 ??；"
                           "真编译 pass/fail 归 compile 命令门；引用真实性归 citation(stage 10)。")


def _compile_log_gate(art: dict) -> "GateResult":
    """.log 细粒度（warn/skip，复用 precheck_log）：undefined ref/cite、overfull box 等。
    诚实：真编译 pass/fail 归 compile 命令门（真 latexmk 退出码），此门只作 .log 细粒度提示，不重复判编译成败。"""
    lf = art["log_findings"]
    if lf is None:
        return GateResult("compile_log", "skip", "info", [],
                          note="未提供 --log：.log 细粒度门跳过（真编译 pass/fail 归 compile 命令门）。")
    finds = []
    for key, d in lf.items():
        for item in d.get("items", [])[:5]:
            finds.append(Finding(loc=f"log:{key}", issue=f"{d.get('desc', '')}：{item}",
                                 fix="见 references/latex_errors.md 症状→根因→修法", rule=f"compile_log.{key}"))
    if not finds:
        return GateResult("compile_log", "pass", "info", [], note=".log 未见 undefined ref/cite、overfull 等问题。")
    has_err = any(d.get("severity") == "error" for d in lf.values())
    return GateResult("compile_log", "warn", "major" if has_err else "minor", finds,
                      note="「.log」细粒度（warn，非阻断）：真编译成败归 compile 命令门（真 latexmk 退出码），"
                           "此门只提示 .log 细节（如 undefined ref/cite、overfull box）。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装 desk-reject critical findings：消费 submission_check 记录 + citekey 对账 + .log 扫描 → 五 gate。
    **build() 不打网/不真编译**（consume 已扫/已算的数据）→ 可离线 selftest；实扫由 CLI 编排 submission_check 等。"""
    project = str(spec.get("project", "unnamed"))
    art = {
        "project": project,
        "sub_findings": spec.get("sub_findings") or [],   # submission_check 的 {severity,code,msg} 列表
        "scanned": bool(spec.get("scanned")),             # 是否真做过 tex/pdf 扫描（决定 pass vs skip）
        "citekey_audit": spec.get("citekey_audit"),       # dict | None（citation citekey_audit.audit 产）
        "log_findings": spec.get("log_findings"),         # dict | None（precheck_log.scan 产）
        "double_blind": bool(spec.get("double_blind")),
        "max_pages": int(spec.get("max_pages") or 0),
    }
    report = None
    if _SHARED_OK:
        report = run_gates(
            [_desk_reject_gate, _anonymity_gate, _residual_gate, _bib_integrity_gate, _compile_log_gate],
            art, producer="typesetting", target=project,
            summary="typesetting desk-reject 门：超页/双盲/明示格式硬规则（critical，一票否决，本阶段内修→reroute manual）+ "
                    "致谢/自指/TODO/citekey/.log（warn）→ 任一 critical → run_checkpoint --stage 11 exit 1。"
                    "compile 真编译 pass/fail 走命令门（真 latexmk 退出码）；typesetting 无回边出边（自身门在 stage 11 内修）。",
            fresh_evidence=True)
    n_crit = sum(1 for f in art["sub_findings"]
                 if f["code"] in _CRITICAL_CODES and f["severity"] == "high")
    return {"project": project, "n_sub": len(art["sub_findings"]), "n_critical": n_crit,
            "has_citekey": art["citekey_audit"] is not None, "has_log": art["log_findings"] is not None,
            "double_blind": art["double_blind"],
            "findings": report.to_dict() if report else None, "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# typesetting desk-reject 门：{result['project']}", ""]
    lines.append(f"- 源级扫描发现：{result.get('n_sub', 0)} 条（其中一票否决 critical {result.get('n_critical', 0)} 项）；"
                 f"双盲模式：{'是' if result.get('double_blind') else '否'}；"
                 f"\\cite↔.bib 对账：{'有' if result.get('has_citekey') else '无(跳过)'}；"
                 f".log 扫描：{'有' if result.get('has_log') else '无(跳过)'}")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=typesetting)；"
                  f"run_checkpoint --stage 11 聚合，超页/双盲/明示格式硬规则→critical fail→exit 1；"
                  f"compile 真编译 pass/fail 走命令门；typesetting **无回边出边**（自身门在 stage 11 内修）。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}  {g.get('note', '')[:54]}")
            for x in g.get("findings", [])[:4]:
                lines.append(f">       · {x['loc']}: {x['issue'][:80]}")
    else:
        lines += ["", "> _shared 不可达：findings 诚实降级 None（不假装产机读交接）。"]
    return "\n".join(lines)


# ───────────────────────── selftest（离线，确定性） ─────────────────────────
def _sf(severity: str, code: str, msg: str = "") -> dict:
    """造一条 submission_check 风格记录。"""
    return {"severity": severity, "code": code, "msg": msg or code}


def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 超页 + 双盲露作者名 → desk_reject critical → 整体 fail
    sub1 = [_sf("high", "PAGES_OVER", "PDF 约 12 页 > 上限 8 页"),
            _sf("high", "BLIND_IDENTITY", "双盲稿含未匿名身份命令 1 处")]
    r1 = build({"project": "p1", "sub_findings": sub1, "scanned": True,
                "double_blind": True, "max_pages": 8})
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f1["producer"] == "typesetting", f"producer 应 typesetting，得 {f1['producer']}")
        names = {g["gate"] for g in f1["gates"]}
        check("desk_reject" in names, f"门名应含 STAGE_GATES[11] 的 desk_reject，得 {names}")
        dr = next(g for g in f1["gates"] if g["gate"] == "desk_reject")
        check(dr["status"] == "fail" and dr["severity"] == "critical", "超页+露名应 desk_reject critical")
        check(f1["verdict"] == "fail", f"超页+露名应整体 fail，得 {f1['verdict']}")
        rules = {x["rule"] for x in dr["findings"]}
        check("desk_reject.pages_over" in rules and "desk_reject.blind_identity" in rules,
              f"应命中 pages_over+blind_identity，得 {rules}")
        # critical issue 只指本阶段内修，绝不带跨阶段路由信号（typesetting 无回边出边）
        blob = " ".join(x["issue"] + x["fix"] + x.get("rule", "") for x in dr["findings"])
        for sig in ("回 result-analysis", "回 experiment", "回 paper-writing", "7→", "8→", "9→", "回炉上游"):
            check(sig not in blob, f"typesetting critical issue 不应带跨阶段信号『{sig}』（本阶段内修）")
        check("本阶段" in blob, "typesetting critical fix 应指本阶段内修")

    # 2. 干净稿（扫了但无 critical）→ desk_reject pass → 整体非 fail
    r2 = build({"project": "p2", "sub_findings": [], "scanned": True, "double_blind": True})
    if _SHARED_OK:
        dr2 = next(g for g in r2["findings"]["gates"] if g["gate"] == "desk_reject")
        check(dr2["status"] == "pass", f"干净稿应 desk_reject pass，得 {dr2['status']}")
        check(r2["findings"]["verdict"] != "fail", "干净稿不应 fail")

    # 3. PDF_AUTHOR_META 在非双盲下=med → 不进 critical，归 anonymity warn（不阻断）
    sub3 = [_sf("med", "PDF_AUTHOR_META", "PDF 元数据 /Author='Zhang'")]
    r3 = build({"project": "p3", "sub_findings": sub3, "scanned": True, "double_blind": False})
    if _SHARED_OK:
        f3 = r3["findings"]
        dr3 = next(g for g in f3["gates"] if g["gate"] == "desk_reject")
        check(dr3["status"] == "pass", "非双盲 PDF 元数据 med 不应误升 desk_reject critical")
        an3 = next(g for g in f3["gates"] if g["gate"] == "anonymity")
        check(an3["status"] == "warn", f"非双盲 PDF 元数据应 anonymity warn，得 {an3['status']}")
        check(f3["verdict"] != "fail", "仅 med 元数据不应整体 fail")

    # 4. 致谢/自指/链接 → anonymity warn
    sub4 = [_sf("high", "BLIND_ACK", "含致谢/基金小节"),
            _sf("high", "BLIND_LINK", "含可识别链接"),
            _sf("med", "BLIND_SELFREF", "含『我们之前的工作』式自指")]
    r4 = build({"project": "p4", "sub_findings": sub4, "scanned": True, "double_blind": True})
    if _SHARED_OK:
        f4 = r4["findings"]
        an4 = next(g for g in f4["gates"] if g["gate"] == "anonymity")
        check(an4["status"] == "warn" and an4["severity"] != "critical", f"软信号应 anonymity warn，得 {an4['status']}")
        check(f4["verdict"] != "fail", "仅软信号不应整体 fail（双盲软信号非确凿 desk-reject）")
        dr4 = next(g for g in f4["gates"] if g["gate"] == "desk_reject")
        check(dr4["status"] == "pass", "致谢/链接（非身份命令）不应触发 desk_reject critical")

    # 5. 残留 TODO → residual warn
    sub5 = [_sf("high", "RESIDUAL_TODO", "残留占位/待办 3 处")]
    r5 = build({"project": "p5", "sub_findings": sub5, "scanned": True})
    if _SHARED_OK:
        rg5 = next(g for g in r5["findings"]["gates"] if g["gate"] == "residual")
        check(rg5["status"] == "warn", f"TODO 残留应 residual warn，得 {rg5['status']}")

    # 5b. profile 明示模板类不符 → desk_reject critical
    r5b = build({"project": "p5b",
                 "sub_findings": [_sf("high", "TEMPLATE_CLASS", "profile=acmart, source=article")],
                 "scanned": True})
    if _SHARED_OK:
        dr5b = next(g for g in r5b["findings"]["gates"] if g["gate"] == "desk_reject")
        check(dr5b["status"] == "fail" and dr5b["severity"] == "critical",
              "profile 明示模板硬规则不符应 desk_reject critical")
        check(r5["findings"]["verdict"] != "fail", "仅 TODO 不应整体 fail")

    # 6. citekey 缺失/重复/冗余 → bib_integrity warn（消费 citekey_audit dict）
    ck = {"missing_keys": ["ghost2099"], "duplicate_bib_keys": ["dup2020"], "uncited_keys": ["unused2019"]}
    r6 = build({"project": "p6", "sub_findings": [], "scanned": True, "citekey_audit": ck})
    if _SHARED_OK:
        bi = next(g for g in r6["findings"]["gates"] if g["gate"] == "bib_integrity")
        check(bi["status"] == "warn" and bi["severity"] != "critical", f"citekey 缺失应 bib_integrity warn，得 {bi['status']}")
        check(any(x["rule"] == "bib_integrity.missing_key" for x in bi["findings"]), "应命中 missing_key")
        check(r6["findings"]["verdict"] != "fail", "仅 citekey 问题不应整体 fail（编译硬错归命令门）")

    # 7. .log 扫描有 error → compile_log warn（不重复判编译成败）
    log_findings = {"latex_error": {"severity": "error", "desc": "LaTeX 致命错误", "count": 1,
                                    "items": ["File `fig.png' not found"]}}
    r7 = build({"project": "p7", "sub_findings": [], "scanned": True, "log_findings": log_findings})
    if _SHARED_OK:
        cl = next(g for g in r7["findings"]["gates"] if g["gate"] == "compile_log")
        check(cl["status"] == "warn", f".log error 应 compile_log warn，得 {cl['status']}")
        # 真编译成败归命令门：compile_log 即便有 error 也只 warn，不把整体拉 fail
        check(r7["findings"]["verdict"] != "fail", ".log 提示不应让 desk_reject 门整体 fail（编译成败归命令门）")

    # 8. 未提供任何扫描 → desk_reject/anonymity/residual skip（不误判）
    r8 = build({"project": "p8", "sub_findings": [], "scanned": False})
    if _SHARED_OK:
        f8 = r8["findings"]
        dr8 = next(g for g in f8["gates"] if g["gate"] == "desk_reject")
        check(dr8["status"] == "skip", f"未扫描应 desk_reject skip，得 {dr8['status']}")
        check(f8["verdict"] != "fail", "未扫描不应 fail")

    # 9. findings 往返 + 阻断 gate + producer
    if _SHARED_OK:
        rep = FindingsReport.from_json(json.dumps(r1["findings"], ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1, "findings 应可往返且有阻断 gate")
        check(rep.producer == "typesetting", "往返后 producer 仍 typesetting")

    # 10. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 11. markdown 不崩
    check("desk-reject 门" in to_markdown(r1), "markdown 应含 desk-reject 门标题")

    if failures:
        print("[SELFTEST][desk_reject_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][desk_reject_gate] OK：超页+双盲露名 critical（本阶段内修，不带跨阶段信号） / 干净 pass / "
          "非双盲元数据 med→anonymity warn / 致谢·自指·链接 warn / TODO warn / citekey warn / .log warn（不判编译成败） / "
          "未扫描 skip / findings(typesetting) 往返"
          + (f"｜港接 SC={_HAS_SC} PL={_HAS_PL} CKA={_HAS_CKA}" if _SHARED_OK else "（_shared 不可达，走诚实降级）") + "。")
    return 0


# ───────────────────────── CLI（实扫在此层，build 不打网/不真编译） ─────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="typesetting desk-reject 一票否决门 producer"
                    "（超页/双盲露名→critical→stage 11 exit 1；typesetting 无回边，自身门在 stage 11 内修）")
    ap.add_argument("--tex", help="正文 .tex（源级双盲/TODO 扫 + 配 --bib 跑 \\cite↔.bib 对账）")
    ap.add_argument("--pdf", help="编译出的 PDF（查元数据 + 配 --max-pages 数页）")
    ap.add_argument("--bib", help=".bib 路径（配 --tex 跑 citekey 对账，复用 citation citekey_audit）")
    ap.add_argument("--log", help="编译 .log（配 precheck_log 扫 undefined ref/cite、overfull）")
    ap.add_argument("--profile", help="light.typesetting_venue_profile.v1 或 rules JSON；规则必须来自用户/当天权威规范")
    ap.add_argument("--double-blind", action="store_true", help="双盲投稿：查作者/致谢/链接/元数据泄漏")
    ap.add_argument("--max-pages", type=int, default=0, help="venue 页数上限（>0 才查；不给则页数检查跳过）")
    ap.add_argument("--strict", action="store_true", help="precheck_log strict：undefined ref/cite 升 error")
    ap.add_argument("--project", default="unnamed")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整 desk-reject 门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    sub_findings, scanned = [], False
    profile = {}
    if args.profile:
        profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
        if profile.get("schema") == "light.typesetting_venue_profile.v1":
            profile = profile.get("rules") or {}
    if args.double_blind:
        profile["double_blind"] = True
    if args.max_pages > 0:
        profile["max_pages"] = args.max_pages
    # ①+② 源/PDF/profile 统一审计；profile 未给的 venue 真值绝不猜。
    if args.tex or args.pdf:
        if not _HAS_SC:
            print("[desk_reject_gate] 致命：submission_check 不可导入，无法执行合规审计。", file=sys.stderr)
            sys.exit(2)
        compliance = sc.audit(args.tex, args.pdf, profile)
        sub_findings = compliance["findings"]
        scanned = True
    # ③ \cite↔.bib 对账（跨技能复用 citation citekey_audit）
    citekey_audit = None
    if args.tex and args.bib:
        if not _HAS_CKA:
            print("[desk_reject_gate] 注意：citation citekey_audit 不可导入，跳过 \\cite↔.bib 对账"
                  "（确认 light-citation 在同仓库树内）。", file=sys.stderr)
        else:
            with open(args.tex, encoding="utf-8", errors="replace") as f:
                tex_text = f.read()
            with open(args.bib, encoding="utf-8", errors="replace") as f:
                bib_text = f.read()
            citekey_audit = cka.audit(tex_text, bib_text)
    # ④ .log 扫描（复用 precheck_log）
    log_findings = None
    if args.log:
        if not _HAS_PL:
            print("[desk_reject_gate] 注意：precheck_log 不可导入，跳过 .log 扫描。", file=sys.stderr)
        else:
            with open(args.log, encoding="utf-8", errors="replace") as f:
                log_findings = pl.scan(f.read(), strict=args.strict)

    result = build({"project": args.project, "sub_findings": sub_findings, "scanned": scanned,
                    "citekey_audit": citekey_audit, "log_findings": log_findings,
                    "double_blind": bool(profile.get("double_blind")),
                    "max_pages": int(profile.get("max_pages") or 0)})
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整 desk-reject 门 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达，无 findings 可写（诚实不假装）。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"（verdict={result['findings']['verdict']}）", file=sys.stderr)
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
