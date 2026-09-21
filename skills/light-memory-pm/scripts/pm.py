#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pm.py — memory-pm 的 .light/ 项目记忆 CLI（包装 passport，不重造台账引擎）。

定位（Light v2 / light-memory-pm，常驻横切·记忆与项目管理）
------------------------------------------------------------
memory-pm 是「项目运行时记忆」的归属方（蓝图决策 A：原项目状态库改名并入）。它**复用**
light-orchestrator 的 `passport.py` 引擎（DAG 台账：阶段/状态/一等回边/stale-check/
指纹），在其之上定 `.light/` 目录约定、管 passport 不碰的「非 DAG 项目记忆」，并维护
跨材料一致性的**事实源** + **变更广播**。本脚本不重写 DAG/校验/stale-check——只包装。

.light/ 目录约定（memory-pm 定义；三 harness 共读，随仓库走、版本控制）
  .light/
  ├── passport.yaml        DAG 科研台账（passport.py 引擎管；本脚本只调库不重造）
  ├── project_card.md      项目卡（14 字段 + frontmatter created；next_actions 会话开头先读）
  ├── decision_log.md      决策日志（ADR 式，只追加不改写）
  ├── version_history.md   版本史（Keep a Changelog 式，与 git tag 对齐）
  ├── memory_items.json    项目记忆条目（scope/敏感级别/保留期/来源/替代链/删除）
  ├── terminology.md       受控术语/指标/创新点（人读事实源，供 consistency；改它=触发广播）
  ├── consistency/*.yaml   机读受控 schema（4 份，严格校验用；模板在 light-consistency/assets/）
  └── handoff/S<NN>-*.md   跨会话交接卡（链式，可追到任意上级会话）

子命令
  init       建项目 .light/ 骨架（复用 passport init 建 passport.yaml + 从模板铺记忆文件）
  audit      台账/记忆**自洽**审计（复用 passport.validate/stage_status + 3 个校验器）。
             --report 出 light.findings.v1（producer=memory-pm）——**仅账本自洽门**，
             非 C1/C2 那种科研内容门，默认不进 run_checkpoint 常开阻断（见 SKILL 名实对齐）。
  broadcast  变更广播:事实源(terminology/consistency)一改 → 算受影响材料(passport artifacts
             并集) → 发 consistency 回扫指令(审计归 consistency,本脚本不重复造)。
  resume     会话开头续跑汇报(**跨 harness 确定性单一真相源**):读 .light/passport.yaml 出
             项目/阶段/卡门/需重验/下一步。委托 resume_report——CC 的 SessionStart hook 亦
             复用同一份(DRY);Codex/OpenCode 经 AGENTS.md 约定在会话开头跑本命令(R4.e)。
  --selftest 离线合成自测,自清理无残留。

诚实边界
  - 跨会话记忆靠 .light/ 显式文件 + hook 注入 + Grep 字面检索,**无向量语义召回 / 无自动抽取**。
  - audit 是「账本自洽」(日期/枚举/行格式/链路/版本对齐/快照新鲜/孤儿产物),**不判科研质量**。
  - 变更广播只算「该回扫谁」+ 发指令,**查不一致是 consistency 的事**(职责分离)。

依赖:Python 标准库 + PyYAML(passport/校验器需要);接 `_shared`(findings 门)。无网络。
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import pathlib
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 路径 bootstrap:向上走目录树找仓库根(治硬编码 parents[N] 之脆,对齐 _shared 规范)──
_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))                                            # _shared
sys.path.insert(0, str(_ROOT / "skills" / "light-orchestrator" / "scripts"))  # passport(复用)
sys.path.insert(0, str(_HERE))                                           # 同目录 3 校验器

try:
    import passport  # 复用的台账引擎(不重造)
except ImportError as e:  # noqa: BLE001
    sys.stderr.write(f"[pm] 无法 import passport 引擎(应在 skills/light-orchestrator/scripts/):{e}\n")
    raise
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
from _shared.gate_runner import run_gates  # noqa: E402
import check_project_card as cpc  # noqa: E402
import version_tag_reconcile as vtr  # noqa: E402
import check_bfact_freshness as cbf  # noqa: E402
import resume_report  # noqa: E402  会话开头续跑汇报单一真相源(跨 harness 确定性;hook 亦复用)
import memory_items as mi  # noqa: E402  无数据库的项目记忆条目契约
import handoff_contract as hc  # noqa: E402  交接卡内容合同(自包含续跑)

ASSETS = _HERE.parent / "assets"
CONSISTENCY_ASSETS = _ROOT / "skills" / "light-consistency" / "assets"
CONSISTENCY_SCRIPT = _ROOT / "skills" / "light-consistency" / "scripts" / "consistency_audit.py"
CONSISTENCY_SCHEMAS = ["glossary.yaml", "method_lock.yaml",
                       "metric_registry.yaml", "claims_registry.yaml"]
# memory-pm 铺的记忆文件 ← 对应模板(passport.yaml 由 passport 引擎单独建)
MEMORY_TEMPLATES = {
    "project_card.md": "project_card.template.md",
    "decision_log.md": "decision_log.template.md",
    "version_history.md": "version_history.template.md",
    "terminology.md": "terminology.template.md",
}
AUDIT_GATES = ["ledger_structure", "project_card", "handoff_contract",
               "memory_items", "version_tag", "bfact_freshness",
               "artifact_integrity"]


def _write_no_bom(path: str, text: str) -> None:
    """UTF-8 无 BOM 写出(给 Python 读的 JSON/YAML 不带 BOM,Windows 安全)。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _e2e_selftest_dir() -> pathlib.Path:
    root = _ROOT / ".upgrade" / "_e2e"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ===========================================================================
# init —— 建 .light/ 骨架(复用 passport init + 从模板铺记忆文件)
# ===========================================================================
def init_light(project_root: str, project: str, pipeline: str, created=None,
               dag_template=None, with_consistency=False, force=False) -> int:
    light = os.path.join(project_root, ".light")
    os.makedirs(light, exist_ok=True)
    created = created or datetime.date.today().isoformat()

    # 1) passport.yaml —— **复用** passport.cmd_init,不重造台账引擎
    pp = os.path.join(light, "passport.yaml")
    rc = passport.cmd_init(passport._NS(out=pp, force=force, project=project,
                                        pipeline=pipeline, created=created,
                                        dag_template=dag_template))
    if rc != 0 and not os.path.exists(pp):
        return rc

    # 2) 从模板铺记忆文件(占位替换:项目名 + 建档日期)
    created_files = [pp]
    for fname, tname in MEMORY_TEMPLATES.items():
        dst = os.path.join(light, fname)
        if os.path.exists(dst) and not force:
            print(f"[init] 跳过已存在:{fname}(加 --force 覆盖)")
            continue
        tpl = (ASSETS / tname).read_text(encoding="utf-8")
        tpl = tpl.replace("<PROJECT_NAME>", project).replace("<CREATED_DATE>", created)
        _write_no_bom(dst, tpl)
        created_files.append(dst)

    # 3) 建无数据库的结构化项目记忆条目文件；不存 restricted/secret 值。
    memory_path = os.path.join(light, "memory_items.json")
    if not os.path.exists(memory_path) or force:
        _write_no_bom(
            memory_path,
            json.dumps(mi.empty_ledger(project), ensure_ascii=False, indent=2) + "\n",
        )
        created_files.append(memory_path)
    else:
        print("[init] 跳过已存在:memory_items.json(加 --force 覆盖)")

    # 4) 可选:铺机读受控 schema(从 light-consistency/assets 复制空模板)
    if with_consistency:
        cdir = os.path.join(light, "consistency")
        os.makedirs(cdir, exist_ok=True)
        for sch in CONSISTENCY_SCHEMAS:
            src = CONSISTENCY_ASSETS / sch
            dst = os.path.join(cdir, sch)
            if not src.exists():
                print(f"[init] ⚠ 未找到 schema 模板:{src}(跳过)", file=sys.stderr)
                continue
            if os.path.exists(dst) and not force:
                continue
            _write_no_bom(dst, src.read_text(encoding="utf-8"))
            created_files.append(dst)

    os.makedirs(os.path.join(light, "handoff"), exist_ok=True)
    print(f"[init] 已建 .light/ 项目记忆({len(created_files)} 文件):{light}")
    for f in created_files:
        print(f"        + {os.path.relpath(f, project_root)}")
    return 0


# ===========================================================================
# audit —— 台账/记忆自洽审计(复用 passport + 3 校验器,汇成内部 findings)
# ===========================================================================
def _f(gate, kind, sev, loc, detail, fix):
    return {"gate": gate, "kind": kind, "sev": sev,
            "loc": loc, "detail": detail, "fix": fix}


def collect_integrity_findings(light_dir, project_root, today=None,
                               tags=None, git_dir=None):
    """跑全部自洽检查,汇成统一内部 findings(sev ∈ error/warn/minor)。"""
    findings = []
    pp = os.path.join(light_dir, "passport.yaml")
    data = None

    # 1) 台账结构(复用 passport.validate)
    if os.path.exists(pp):
        try:
            data = passport.load(pp)
            rep = passport.validate(data)
            for e in rep.get("errors", []):
                findings.append(_f("ledger_structure", "LEDGER_STRUCT", "error",
                                   "passport.yaml", e, "passport.py validate 修复结构"))
            for w in rep.get("warnings", []):
                findings.append(_f("ledger_structure", "LEDGER_WARN", "warn",
                                   "passport.yaml", w, "核对台账字段是否漏更新"))
        except Exception as e:  # noqa: BLE001  台账损坏当结构错(不静默)
            findings.append(_f("ledger_structure", "LEDGER_PARSE", "error",
                               "passport.yaml", f"台账解析失败:{e}", "修复 YAML 或重建台账"))
    else:
        findings.append(_f("ledger_structure", "NO_PASSPORT", "warn", "passport.yaml",
                           ".light/passport.yaml 不存在(无 DAG 台账)",
                           "pm.py init / passport.py init 建台账"))

    # 2) 项目卡/决策日志/版本史/交接链(复用 check_project_card)
    for fd in cpc.run_audit(project_dir=light_dir,
                            handoff_dir=os.path.join(light_dir, "handoff")):
        sev = "error" if fd["severity"] == "error" else "warn"
        findings.append(_f("project_card", fd["kind"], sev,
                           fd["location"], fd["detail"], fd["suggestion"]))

    # 2b) 交接卡内容合同：链可达不等于下一会话能续上。卡本身必须自包含：
    # 已完成+验证、工作区状态、1-3 条可执行下一步、必读文件、禁止凭记忆。
    handoff_dir = os.path.join(light_dir, "handoff")
    if os.path.isdir(handoff_dir):
        for fd in hc.audit_dir(pathlib.Path(handoff_dir)):
            sev = "error" if fd["severity"] == "error" else "warn"
            findings.append(_f("handoff_contract", fd["kind"], sev,
                               fd["location"], fd["detail"], fd["suggestion"]))

    # 3) 结构化项目记忆条目：作用域/敏感级别/过期/替代链/删除自洽。
    memory_path = os.path.join(light_dir, "memory_items.json")
    if os.path.exists(memory_path):
        try:
            memory_ledger = json.loads(pathlib.Path(memory_path).read_text(encoding="utf-8-sig"))
            for item in mi.validate(memory_ledger):
                sev = "error" if item["severity"] == "error" else "warn"
                findings.append(_f(
                    "memory_items", item["code"], sev,
                    f"memory_items.json:{item['item_id']}",
                    item["message"],
                    "用 memory_items.py delete/add 修复；restricted/secret 值移到仓库外",
                ))
        except Exception as e:  # noqa: BLE001
            findings.append(_f(
                "memory_items", "MEMORY_ITEMS_PARSE", "error", "memory_items.json",
                f"项目记忆条目解析/校验失败:{e}",
                "修复 JSON/schema；不要用文本编辑绕过 sensitivity/retention 校验",
            ))
    else:
        findings.append(_f(
            "memory_items", "NO_MEMORY_ITEMS", "minor", "memory_items.json",
            "未启用结构化项目记忆条目；旧项目仍可只用 project_card/decision_log",
            "需要可验证的作用域、过期和删除时运行 memory_items.py init",
        ))

    # 4) version_history ↔ git tag(复用 version_tag_reconcile)
    vh = os.path.join(light_dir, "version_history.md")
    if os.path.exists(vh):
        taglist = tags
        if taglist is None and git_dir:
            try:
                taglist = vtr.git_tags(git_dir)
            except Exception as e:  # noqa: BLE001
                findings.append(_f("version_tag", "GIT_TAG_READ", "warn",
                                   "version_history.md", f"读 git tag 失败:{e}",
                                   "在仓库内运行或用 --tags 注入 tag 列表"))
        if taglist is not None:
            res = vtr.reconcile(vtr.parse_version_history(vh), vtr.parse_tags(taglist))
            for r in res["record_no_tag"]:
                findings.append(_f("version_tag", "RECORD_NO_TAG", "warn",
                                   f"version_history.md:{r['lineno']}",
                                   f"记录 {vtr._ver_str(r['ver'])} 无对应 git tag(破坏可复现)",
                                   f"补 git tag -a {vtr._ver_str(r['ver'])} -m ... 并 push --tags"))
            for t in res["tag_no_record"]:
                findings.append(_f("version_tag", "TAG_NO_RECORD", "warn", f"git:{t['tag']}",
                                   f"git tag {t['tag']} 无对应版本记录(漏记)",
                                   "在 version_history.md 补该版本记录行"))

    # 5) B-fact 快照新鲜度(复用 check_bfact_freshness)
    bf_targets = [os.path.join(light_dir, n) for n in ("project_card.md", "decision_log.md")
                  if os.path.exists(os.path.join(light_dir, n))]
    if bf_targets:
        t = datetime.date.today()
        if today:
            y, m, d = str(today).split("-")
            t = datetime.date(int(y), int(m), int(d))
        brep = cbf.scan_paths(bf_targets, t)
        for fd in brep["findings"]:
            sev = "warn" if fd["severity"] == "major" else "minor"
            findings.append(_f("bfact_freshness", fd["kind"], sev, fd["loc"], fd["msg"],
                               "补 [snapshot YYYY-MM-DD, src=在线/官方源] 或在线重核"))

    # 6) 产物完整性(复用 passport.stage_status:台账登记的产物缺失=孤儿/缺失 artifact)
    if data is not None:
        for st in data.get("stages") or []:
            if not isinstance(st, dict) or not (st.get("artifacts") or []):
                continue  # 未登记产物的阶段(未开始)不算缺失,跳过
            stt = passport.stage_status(data, st.get("stage"), root=project_root)
            if stt.get("state") == "incomplete":
                findings.append(_f("artifact_integrity", "MISSING_ARTIFACT", "error",
                                   f"passport.yaml:stage{st.get('stage')}",
                                   stt.get("reason", "台账登记的产物缺失"),
                                   "补产物文件或修正 stage 的 artifacts 路径"))
    return findings


_SEV_LABEL = {"error": "ERROR", "warn": "WARN ", "minor": "minor"}


def render_report(findings, target):
    out = ["=" * 64, f"memory-pm 台账/记忆自洽审计  target={target}",
           f"发现总数:{len(findings)}", "=" * 64]
    by = {}
    for f in findings:
        by.setdefault(f["gate"], []).append(f)
    n = 0
    for g in AUDIT_GATES:
        items = by.get(g, [])
        out.append(f"\n## [{g}]　({len(items)} 条)")
        if not items:
            out.append("  （无）")
        for f in items:
            n += 1
            out.append(f"  {n:>3}. [{_SEV_LABEL[f['sev']]}] {f['kind']} @ {f['loc']}")
            out.append(f"       问题：{f['detail']}")
            out.append(f"       建议：{f['fix']}")
    n_err = sum(1 for f in findings if f["sev"] == "error")
    out.append("\n" + "=" * 64)
    verdict = ("⛔ FAIL（有结构性损坏）" if n_err
               else ("⚠ WARN（有卫生项）" if findings else "✓ PASS"))
    out.append(f"自洽结论：{verdict}　error={n_err} 总计={len(findings)}")
    out.append("=" * 64)
    return "\n".join(out)


def _build_gate(gate, grp):
    """内部 findings → GateResult。error→critical fail(阻断);warn/minor→warn(不阻断)。"""
    if not grp:
        return GateResult(gate=gate, status="pass", severity="info", findings=[])
    fobjs = [Finding(loc=f["loc"], issue=f["detail"], fix=f["fix"], rule=f["kind"])
             for f in grp]
    if any(f["sev"] == "error" for f in grp):
        return GateResult(gate=gate, status="fail", severity="critical", findings=fobjs,
                          note="台账结构性损坏(阻断:交接/投稿前须修)")
    worst = "major" if any(f["sev"] == "warn" for f in grp) else "minor"
    return GateResult(gate=gate, status="warn", severity=worst, findings=fobjs,
                      note="台账卫生项(建议修,不阻断)")


def build_report(findings, target) -> FindingsReport:
    """内部 findings → light.findings.v1（producer=memory-pm，走 _shared gate_runner）。"""
    by = {}
    for f in findings:
        by.setdefault(f["gate"], []).append(f)
    gate_fns = []
    for gate in AUDIT_GATES:
        gr = _build_gate(gate, by.get(gate, []))

        def _fn(_artifact, _gr=gr):  # 默认参数捕获,避免 late-binding 循环 bug
            return _gr
        _fn.__name__ = gate
        gate_fns.append(_fn)
    return run_gates(gate_fns, target, producer="memory-pm", target=target,
                     summary="memory-pm 台账/记忆自洽审计（账本自洽门，非科研内容门）",
                     fresh_evidence=True)


def audit_light(light_dir, project_root, today=None, tags=None, git_dir=None,
                report_path=None, target=None):
    findings = collect_integrity_findings(light_dir, project_root, today, tags, git_dir)
    target = target or (os.path.basename(os.path.abspath(project_root)) + "/.light")
    report = build_report(findings, target)
    if report_path:
        _write_no_bom(report_path, report.to_json())
    return findings, report


# ===========================================================================
# broadcast —— 变更广播(事实源改 → 受影响材料 → consistency 回扫指令)
# ===========================================================================
def affected_materials(light_dir):
    """受影响材料 = passport 全部 stage 的 artifacts 并集(相对项目根)。"""
    pp = os.path.join(light_dir, "passport.yaml")
    if not os.path.exists(pp):
        return []
    try:
        data = passport.load(pp)
    except Exception:  # noqa: BLE001
        return []
    arts = []
    for st in data.get("stages") or []:
        if isinstance(st, dict):
            for a in st.get("artifacts") or []:
                if a not in arts:
                    arts.append(a)
    return sorted(arts)


def broadcast(light_dir, project_root, changed=None, run=False, update_fp=False):
    """算受影响材料 + 发 consistency 回扫指令;可选 --run 真调 consistency(不重造审计)。"""
    if not changed:
        changed = []
        term = os.path.join(light_dir, "terminology.md")
        if os.path.exists(term):
            changed.append(term)
        cdir = os.path.join(light_dir, "consistency")
        if os.path.isdir(cdir):
            changed += sorted(glob.glob(os.path.join(cdir, "*.yaml")))
    rel_changed = [os.path.relpath(c, light_dir) for c in changed]

    # 指纹比对(复用 passport.compute_fingerprint):事实源真的变了吗?
    fp = passport.compute_fingerprint(rel_changed, root=light_dir)
    state_path = os.path.join(light_dir, "broadcast_state.json")
    prev = None
    if os.path.exists(state_path):
        try:
            prev = json.load(open(state_path, encoding="utf-8")).get("fingerprint")
        except Exception:  # noqa: BLE001
            prev = None
    changed_detected = (prev != fp)

    materials = affected_materials(light_dir)
    mats = " ".join(materials) if materials else "<已产出材料...>"
    try:
        cons_ref = os.path.relpath(CONSISTENCY_SCRIPT, project_root)
    except ValueError:  # Windows 跨盘(项目与技能包不同盘)→ 退回绝对路径
        cons_ref = str(CONSISTENCY_SCRIPT)
    rescan_cmd = (f"python {cons_ref} "
                  f"--source .light/consistency --materials {mats} "
                  f"--report .light/_audit/cons.findings.json")

    run_result = None
    if run and materials:
        rep_out = os.path.join(light_dir, "_audit", "cons.findings.json")
        os.makedirs(os.path.dirname(rep_out), exist_ok=True)
        abs_mats = [os.path.join(project_root, m) for m in materials]
        proc = subprocess.run(
            [sys.executable, str(CONSISTENCY_SCRIPT),
             "--source", os.path.join(light_dir, "consistency"),
             "--materials", *abs_mats, "--report", rep_out],
            capture_output=True, text=True)
        verdict = "unknown"
        if os.path.exists(rep_out):
            try:
                verdict = json.load(open(rep_out, encoding="utf-8")).get("verdict", "unknown")
            except Exception:  # noqa: BLE001
                pass
        run_result = {"returncode": proc.returncode, "report": rep_out,
                      "verdict": verdict, "stderr_tail": (proc.stderr or "")[-300:]}

    if update_fp:
        _write_no_bom(state_path, json.dumps(
            {"fingerprint": fp, "at": passport.now_minute(),
             "sources": rel_changed}, ensure_ascii=False, indent=2))

    return {"changed_sources": rel_changed, "fingerprint": fp, "prev_fingerprint": prev,
            "changed_detected": changed_detected, "affected": materials,
            "rescan_cmd": rescan_cmd, "run_result": run_result}


def render_broadcast(res):
    out = ["=" * 64, "memory-pm 变更广播（事实源改 → 受影响材料 → consistency 回扫）", "=" * 64]
    out.append(f"变更事实源：{', '.join(res['changed_sources']) or '(无)'}")
    out.append(f"事实源指纹：{res['fingerprint']}"
               + ("（与上次不同 → 确有变更，需回扫）" if res["changed_detected"]
                  else "（与上次相同 → 事实源未变）"))
    out.append(f"\n受影响材料（passport artifacts 并集，{len(res['affected'])} 份）：")
    for m in res["affected"]:
        out.append(f"  - {m}")
    if not res["affected"]:
        out.append("  （passport 尚无登记 artifacts；产出材料后再广播）")
    out.append("\n→ 交 consistency 回扫（审计归 consistency，memory-pm 只发指令）：")
    out.append(f"  {res['rescan_cmd']}")
    if res["run_result"]:
        rr = res["run_result"]
        out.append(f"\n[--run 已真调 consistency] verdict={rr['verdict']} "
                   f"returncode={rr['returncode']} report={rr['report']}")
    out.append("=" * 64)
    return "\n".join(out)


# ===========================================================================
# CLI
# ===========================================================================
def cmd_init(args) -> int:
    return init_light(args.dir, args.project, args.pipeline, created=args.created,
                      dag_template=args.dag_template,
                      with_consistency=args.with_consistency, force=args.force)


def _resolve_light(args):
    if getattr(args, "light", None):
        light = args.light
        project_root = os.path.dirname(os.path.abspath(light.rstrip("/\\")))
    else:
        project_root = args.dir
        light = os.path.join(project_root, ".light")
    return light, project_root


def cmd_audit(args) -> int:
    light, project_root = _resolve_light(args)
    if not os.path.isdir(light):
        sys.stderr.write(f"[audit] 找不到 .light/ 目录:{light}\n")
        return 2
    findings, report = audit_light(light, project_root, today=args.today,
                                   tags=args.tags, git_dir=args.git_dir,
                                   report_path=args.report)
    print(render_report(findings, report.target))
    if args.report:
        print(f"\n[audit] 已写 light.findings.v1：{args.report}（verdict={report.verdict}，"
              f"producer=memory-pm，账本自洽门）")
    n_err = sum(1 for f in findings if f["sev"] == "error")
    if args.strict:
        return 1 if findings else 0
    return 1 if n_err else 0


def cmd_broadcast(args) -> int:
    light, project_root = _resolve_light(args)
    if not os.path.isdir(light):
        sys.stderr.write(f"[broadcast] 找不到 .light/ 目录:{light}\n")
        return 2
    res = broadcast(light, project_root, changed=args.changed, run=args.run,
                    update_fp=args.update_fingerprint)
    print(render_broadcast(res))
    return 0


def cmd_resume(args) -> int:
    """会话开头续跑汇报(跨 harness 确定性单一真相源):读 .light/passport.yaml 出
    项目 / 阶段 / 卡门 / 需重验 / 下一步。**委托 resume_report**(CC SessionStart hook 亦
    复用同一份,DRY,不重造)。Codex/OpenCode 经 AGENTS.md 约定在会话开头跑本命令。
    始终 exit 0(只读汇报,不阻断;无台账给明确提示)。"""
    print(resume_report.render_cli(args.dir))
    return 0


# ===========================================================================
# 自测(合成项目,自清理无残留)
# ===========================================================================
def _selftest() -> int:
    import tempfile
    import shutil
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
        ok = ok and bool(cond)

    tmp = tempfile.mkdtemp(prefix="pm_selftest_", dir=str(_e2e_selftest_dir()))
    try:
        # 1. init —— 复用 passport 建台账 + 铺记忆文件 + 受控 schema
        rc = init_light(tmp, project="demo-proj", pipeline="A",
                        created="2026-06-17", with_consistency=True)
        light = os.path.join(tmp, ".light")
        check(rc == 0, "init 返回 0")
        for f in ("passport.yaml", "project_card.md", "decision_log.md",
                  "version_history.md", "terminology.md", "memory_items.json"):
            check(os.path.exists(os.path.join(light, f)), f"已铺 {f}")
        check(os.path.exists(os.path.join(light, "consistency", "glossary.yaml")),
              "已铺 consistency/glossary.yaml")
        check(os.path.isdir(os.path.join(light, "handoff")), "已建 handoff/ 目录")

        # 2. 复用 passport 往返不破坏:append-stage / validate / stale-check
        passport.cmd_append_stage(passport._mk_append(
            os.path.join(light, "passport.yaml"), stage=1, skill="literature-search",
            artifacts=["docs/lit.md"], gate_type="confirm", gate_result="PASS"))
        data = passport.load(os.path.join(light, "passport.yaml"))
        check(passport.validate(data)["verdict"] in ("PASS", "WARN"),
              "passport append+validate 往返 PASS/WARN")

        # 3. audit 干净项目(stage1 artifacts 不存在→应抓 MISSING_ARTIFACT=error)
        findings, report = audit_light(light, tmp, today="2026-06-17")
        kinds = {f["kind"] for f in findings}
        check("MISSING_ARTIFACT" in kinds, "抓到孤儿/缺失 artifact(docs/lit.md 不存在)")
        check(report.verdict == "fail", f"含缺失产物→findings verdict=fail（实得 {report.verdict}）")
        check(report.producer == "memory-pm", "findings producer=memory-pm")

        # 补上产物→该 error 消失,verdict 不再 fail
        os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
        _write_no_bom(os.path.join(tmp, "docs", "lit.md"), "# lit\n")
        findings2, report2 = audit_light(light, tmp, today="2026-06-17")
        check(not any(f["kind"] == "MISSING_ARTIFACT" for f in findings2),
              "补产物后 MISSING_ARTIFACT 消失")
        check(report2.verdict in ("pass", "warn"),
              f"补产物后 verdict 非 fail（实得 {report2.verdict}）")

        # 4. audit 抓坏记忆:注入相对日期 + 坏行格式 的 decision_log
        _write_no_bom(os.path.join(light, "decision_log.md"),
                      "# 决策日志\n- 最近改了方案因为效果不好\n")
        findings3, report3 = audit_light(light, tmp, today="2026-06-17")
        k3 = {f["kind"] for f in findings3}
        check("ABS_DATE" in k3, "抓到相对日期(ABS_DATE)")
        check(report3.verdict == "fail", "坏决策日志(error 级)→ verdict=fail")
        # findings JSON 往返(机读契约)
        rt = FindingsReport.from_dict(json.loads(report3.to_json()))
        check(rt.producer == "memory-pm" and rt.verdict == "fail", "findings JSON 往返保真")

        # 5. version_history ↔ git tag(注入式 tag)
        _write_no_bom(os.path.join(light, "version_history.md"),
                      "# 版本记录\n- [2026-06-17] 代码 v1.1.0 — 加跟踪模块（忘打 tag）\n")
        f5, _ = audit_light(light, tmp, today="2026-06-17", tags=["v1.0.0"])
        check(any(f["kind"] == "RECORD_NO_TAG" for f in f5),
              "抓到 version_history 记录无 git tag(RECORD_NO_TAG)")

        # 6. broadcast:改 terminology → 算受影响材料 = passport artifacts 并集
        passport.cmd_append_stage(passport._mk_append(
            os.path.join(light, "passport.yaml"), stage=8, skill="paper-writing",
            artifacts=["paper.md", "slides.md"], gate_type="confirm", gate_result="PASS"))
        res = broadcast(light, tmp, update_fp=True)
        check(set(res["affected"]) == {"docs/lit.md", "paper.md", "slides.md"},
              f"受影响材料=artifacts 并集（实得 {res['affected']}）")
        check("consistency_audit.py" in res["rescan_cmd"]
              and "--source .light/consistency" in res["rescan_cmd"],
              "回扫指令指向 consistency_audit + .light/consistency")
        # 指纹:刚 update_fp,未改 → 再广播应 changed_detected=False
        res2 = broadcast(light, tmp)
        check(res2["changed_detected"] is False, "事实源未变 → 指纹相同(不误报变更)")
        # 改 terminology → 指纹变,changed_detected=True
        with open(os.path.join(light, "terminology.md"), "a", encoding="utf-8") as fh:
            fh.write("\n| 方法 | DCA-Net | | | 主方法 |\n")
        res3 = broadcast(light, tmp)
        check(res3["changed_detected"] is True, "改 terminology → 指纹变,检出变更")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"  [cleanup] removed {tmp} exists={os.path.exists(tmp)}")

    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="memory-pm 的 .light/ 项目记忆 CLI（包装 passport）")
    ap.add_argument("--selftest", action="store_true", help="离线合成自测,自清理无残留")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="建项目 .light/ 骨架（复用 passport init + 铺记忆文件）")
    p.add_argument("--dir", default=".", help="项目根目录(默认当前)")
    p.add_argument("--project", required=True, help="项目名")
    p.add_argument("--pipeline", default="core-13", help="DAG pipeline 名(默认 core-13)")
    p.add_argument("--created", help="建档日期 YYYY-MM-DD(默认今天)")
    p.add_argument("--dag-template", dest="dag_template", help="DAG 模板 id(可选)")
    p.add_argument("--with-consistency", action="store_true",
                   help="同时铺机读受控 schema(4 份)到 .light/consistency/")
    p.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("audit", help="台账/记忆自洽审计（账本自洽门，非科研内容门）")
    p.add_argument("--dir", default=".", help="项目根目录(默认当前)")
    p.add_argument("--light", help="直接指定 .light/ 目录(覆盖 --dir)")
    p.add_argument("--today", help="基准日期 YYYY-MM-DD(B-fact 超期判定;默认今天)")
    p.add_argument("--tags", nargs="*", help="注入式 git tag 列表(不调 git;离线/CI 用)")
    p.add_argument("--git-dir", dest="git_dir", help="git 仓库目录(从中读 tag)")
    p.add_argument("--report", help="把 light.findings.v1 写到该文件(可被 run_checkpoint 聚合)")
    p.add_argument("--strict", action="store_true", help="有任何发现(含 warn)即 exit 1")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("broadcast", help="变更广播：事实源改 → 受影响材料 → consistency 回扫指令")
    p.add_argument("--dir", default=".", help="项目根目录(默认当前)")
    p.add_argument("--light", help="直接指定 .light/ 目录(覆盖 --dir)")
    p.add_argument("--changed", nargs="*",
                   help="变更的事实源文件(默认 terminology.md + consistency/*.yaml)")
    p.add_argument("--run", action="store_true",
                   help="真调 consistency_audit 回扫(默认只打印指令;审计归 consistency)")
    p.add_argument("--update-fingerprint", dest="update_fingerprint", action="store_true",
                   help="把当前事实源指纹记入 .light/broadcast_state.json")
    p.set_defaults(func=cmd_broadcast)

    p = sub.add_parser("resume",
                       help="会话开头续跑汇报（跨 harness 确定性：读 .light/ 出上次断哪/卡门/下一步）")
    p.add_argument("--dir", default=".", help="项目根目录(.light/ 的父目录,默认当前)")
    p.set_defaults(func=cmd_resume)

    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not getattr(args, "cmd", None):
        ap.error("需要子命令(init/audit/broadcast/resume)或 --selftest")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
