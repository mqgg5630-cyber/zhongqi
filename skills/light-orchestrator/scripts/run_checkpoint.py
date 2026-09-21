#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_checkpoint.py — 把"确认点"从给 LLM 的指令变成可执行的闸门聚合器。

orchestrator 编排器最大的 claim-vs-code 空洞（见审查 brief）：SKILL/checkpoints.md 反复说
"阶段产出后先跑机器闸门、Critical FAIL 默认阻断、确认点证据必须新鲜"，但仓库里
**没有任何脚本真的去调用并聚合这些闸门结果**——passport.py 只校验 gate.result 枚举
是否合法，"确认点"实际全靠 LLM 自律。本脚本补上这一环：

  1) 收集本阶段各闸门**已产出的 light.findings.v1 报告**（--findings），和/或
  2) **实际 subprocess 跑**指定闸门命令（--gate label=cmd），按退出码定 pass/fail；
  把它们经 _shared/gate_runner 聚合成一份统一 light.findings.v1 报告（任一 critical
  fail → 整体 verdict=fail），并把 **gate.result + 新鲜证据指针（来源@内容sha@时间戳）**
  写回 passport 对应阶段。Critical fail → 退出码 1，可在 CI/编排中**确定性阻断推进**。

这把 Light 最自豪的"诚信编排"从口号落到代码，且复用各技能已有的 findings 产物
（data-engineering split_leakage 的 leak_findings.json、self-review review_lint、
research-ethics claim_evidence_bind、paper-writing draft_lint、
result-analysis evidence_strength→research-ethics 等），不重造闸门。

诚实边界：
- 本脚本**不替你判断闸门内容对错**——它聚合各闸门自己给出的 verdict/severity。
  闸门本身的准确性仍由各技能脚本与人工负责。
- 默认 **dry-run**（只打印将写入什么）；--write 才真正落 passport。对总控台账动手
  必须显式授权，符合"对外/难撤销动作先确认"的纪律。
- 证据指针记 sha256(报告内容)+时间戳，证明"这份 verdict 来自这次具体输出"，但
  时间戳由调用方传入（--ts，selftest 用固定值），脚本不偷偷读系统时钟伪造新鲜。

阶段→闸门对照（checkpoints.md §各阶段闸门，单一口径在那边，这里只存机读映射）：
  数据评估→research-ethics+self-review+check_access_level   实验/结果→self-review   写作→paper-writing 诚信门
  引用→citation verify   排版→self-review   跨阶段→consistency

用法：
  # 聚合本阶段已产出的 findings 报告，预览将写入 passport 的内容（不落盘）：
  python run_checkpoint.py --file .light/passport.yaml --stage 2 \
      --findings leak_findings.json review_lint.json --ts 2026-06-15T10:00
  # 真正写回 passport（含证据指针），critical fail 退出码 1：
  python run_checkpoint.py --file .light/passport.yaml --stage 2 \
      --findings leak_findings.json --write --ts 2026-06-15T10:00
  # 同时实际跑一个闸门命令（退出码定 pass/fail）：
  python run_checkpoint.py --file p.yaml --stage 8 \
      --gate "draft_lint=python skills/light-paper-drafting/scripts/draft_lint.py draft.md"
  python run_checkpoint.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 同目录 passport.py（读写台账，复用不重造）──
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import passport  # noqa: E402  同目录台账工具

# ── _shared 契约：规范 bootstrap（向上走目录树找含 _shared 包的仓库根）──
# 治 v1 硬编码 `sys.path.insert(.., "..","..","_shared")` 之脆：v2 的 _shared 在仓库根、
# 与 skills/ 平级，脚本嵌套深度也变了，硬编码必断。规范 bootstrap 不依赖深度，三 harness /
# 全局安装 / 任意嵌套都可靠（见 _shared/README.md）。找不到则 _HAS_FINDINGS=False，main 诚实报错。
try:
    _r = pathlib.Path(__file__).resolve()
    while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
        _r = _r.parent
    if not (_r / "_shared" / "__init__.py").exists():
        raise ImportError("向上未找到 _shared 包目录（请确保脚本在 Light-Skills 树内）")
    sys.path.insert(0, str(_r))
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates  # noqa: E402

    _HAS_FINDINGS = True
except Exception:
    _HAS_FINDINGS = False

# 阶段→该阶段确认点应覆盖的闸门/Critical 判据（机读版 orchestrator-spec §4.2；判据口径在 spec）。
# 诚实边界：各门的**实现**在批 1+ 各技能，总控只**聚合 + 判定 + 按根因回炉**；批 0 总控用合成
# gate 演示接线，不假装这些门已全部实现。本表仅作"本阶段应覆盖哪些门"的机读提示，进 summary/render。
STAGE_GATES = {
    # Names are canonical producer/script contracts, not aspirational labels.
    # Keep this table byte-for-byte aligned with references/integration-contract.json.
    2: ["split_leakage", "data_feasibility"],
    3: ["idea_genealogy", "innovation_engine", "idea_collision", "pseudo_diversity", "frame_lock"],
    4: ["collision", "fatal_flaw", "anti_sycophancy"],
    5: ["fair_baseline", "falsifiable"],
    6: ["leakage", "reproducible"],
    7: ["stat_validity", "evidence_strength"],
    8: ["claim_evidence", "overclaim"],
    9: ["visual_honesty", "misrepresent_evidence"],
    10: ["citation_verify"],
    11: ["compile", "desk_reject"],
    13: ["reviewer_classify"],
}
CROSS_STAGE_GATE = "consistency"  # 跨阶段一致性回扫(术语/指标/创新点)


def _sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def load_findings_report(path: str) -> "FindingsReport":
    """读一个 light.findings.v1 文件成 FindingsReport（校验 schema）。
    兼容 split_leakage 那种额外带 raw_findings 字段的报告（from_dict 只读契约字段）。"""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return FindingsReport.from_dict(d)


def gate_from_findings_file(path: str):
    """把一个已产出的 findings 文件包成 gate 函数：取其最严重 gate 的 status/severity
    汇成一条 GateResult（gate 名取文件名），供 gate_runner 聚合。"""

    def _gate(_artifact):
        rep = load_findings_report(path)
        v = rep.compute_verdict()
        status = "fail" if v == "fail" else ("warn" if v == "warn" else "pass")
        sev = rep.worst_severity()
        # 收敛该报告内所有 finding 作为本 gate 的证据明细
        fs = []
        for g in rep.gates:
            for f in g.findings:
                fs.append(
                    Finding(
                        loc=f.loc,
                        issue=f.issue,
                        fix=f.fix,
                        rule=f"{rep.producer}:{g.gate}",
                    )
                )
        label = os.path.basename(path)
        return GateResult(
            gate=label,
            status=status,
            severity=sev,
            findings=fs,
            note=f"源自 {rep.producer} 的 {len(fs)} 条 finding",
        )

    return _gate


def gate_from_command(label: str, cmd: str):
    """把一条 shell 闸门命令包成 gate 函数：退出码 0→pass，非 0→fail(critical)。
    捕获 stdout 作为证据内容（算 sha）。命令异常由 gate_runner 兜成 critical fail。"""

    def _gate(_artifact):
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            return GateResult(
                gate=label,
                status="pass",
                severity="info",
                note=f"exit=0 sha={_sha8(out)}",
            )
        sev = "critical"
        return GateResult(
            gate=label,
            status="fail",
            severity=sev,
            findings=[
                Finding(
                    loc=label,
                    issue=f"闸门命令非零退出 exit={proc.returncode}",
                    fix="见命令输出修复后重跑",
                    rule="subprocess_gate",
                )
            ],
            note=f"exit={proc.returncode} sha={_sha8(out)}",
        )

    return _gate


# === aggregate / writeback / main / selftest appended below ===


# ---------------------------------------------------------------- 聚合
def aggregate(
    findings_files: list, gate_cmds: list, stage: int, target: str = ""
) -> "FindingsReport":
    """把 findings 文件 + 闸门命令聚合成一份 light.findings.v1。"""
    gate_fns = []
    for p in findings_files or []:
        gate_fns.append(gate_from_findings_file(p))
    for label, cmd in gate_cmds or []:
        gate_fns.append(gate_from_command(label, cmd))
    expected = STAGE_GATES.get(stage)
    summary = f"stage {stage} 闸门聚合"
    if expected:
        summary += f"（应覆盖 {'/'.join(expected)}）"
    rep = run_gates(
        gate_fns,
        artifact=None,
        producer="orchestrator",
        target=target or f"stage-{stage}",
        summary=summary,
        fresh_evidence=True,
    )
    return rep


# gate.result → v2 显式 status（写回时同步置位，把"门结论"落成 passport 阶段状态）。
_RESULT_TO_STATUS = {
    "PASS": "delivered",
    "WARN": "delivered",
    "FAIL->PASS": "delivered",
    "FAIL→PASS": "delivered",
    "FAIL": "gate_failed",
}


def build_gate_record(rep: "FindingsReport", stage: int, ts: str) -> dict:
    """从聚合报告构造写回 passport 的 gate dict：result + 新鲜证据指针。
    证据指针 = 每个子 gate 的 来源@severity@内容sha（证明 verdict 来自这次具体输出）。"""
    v = rep.compute_verdict()
    result = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[v]
    # 证据指针：把各子 gate 压成稳定字符串（gate名:status:severity），整体算 sha
    parts = [f"{g.gate}:{g.status}:{g.severity}" for g in rep.gates]
    evidence_payload = "|".join(sorted(parts)) + f"|stage{stage}"
    evidence_sha = hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest()
    n_block = sum(1 for g in rep.gates if g.is_blocking())
    notes = (
        f"run_checkpoint 聚合 {len(rep.gates)} 闸门，"
        f"{n_block} 项 critical fail；证据@{ts}"
    )
    return {
        "type": "confirm",
        "result": result,
        "notes": notes,
        "evidence": f"sha256:{evidence_sha}@{ts}",
        "evidence_state": "FAILED" if result == "FAIL" else "VERIFIED",
        "fresh": ts != "unstamped",
        "gates": ",".join(g.gate for g in rep.gates) or "(none)",
    }


def _project_root_for_passport(passport_file: str) -> str:
    parent = os.path.dirname(os.path.abspath(passport_file))
    return os.path.dirname(parent) if os.path.basename(parent) == ".light" else parent


def _refresh_success_provenance(
    data: dict, target_st: dict, passport_file: str
) -> None:
    """Bind a successful checkpoint to its current output and upstream bytes."""
    root = _project_root_for_passport(passport_file)
    if not target_st.get("artifacts"):
        output = target_st.get("output")
        if isinstance(output, str) and os.path.isfile(os.path.join(root, output)):
            target_st["artifacts"] = [output]
    dependencies = target_st.get("depends_on") or []
    if dependencies:
        upstream: list[str] = []
        for stage in data.get("stages") or []:
            if stage.get("stage") in dependencies:
                upstream.extend(stage.get("artifacts") or [])
        if upstream:
            target_st["inputs_fingerprint"] = passport.compute_fingerprint(
                upstream, root
            )


def writeback(passport_file: str, stage: int, gate_rec: dict, do_write: bool) -> dict:
    """把 gate 记录写回 passport 对应阶段（找到则更新其 gate，找不到报错）。
    do_write=False 时仅返回'将写入什么'，不落盘（dry-run，默认）。"""
    data = passport.load(passport_file)
    stages = data.get("stages") or []
    target_st = None
    for st in stages:
        if isinstance(st, dict) and st.get("stage") == stage:
            target_st = st
            break
    if target_st is None:
        raise ValueError(f"passport 中无 stage={stage}，请先 append-stage 再跑闸门")
    new_status = _RESULT_TO_STATUS.get(gate_rec.get("result"))
    preview = {
        "stage": stage,
        "old_gate": target_st.get("gate"),
        "new_gate": gate_rec,
        "old_status": target_st.get("status"),
        "new_status": new_status,
        "written": False,
    }
    if do_write:
        target_st["gate"] = gate_rec
        # v2：把门结论同步落成显式 status（fail→gate_failed / pass·warn·FAIL→PASS→delivered）。
        if new_status:
            target_st["status"] = new_status
        if new_status == "delivered":
            _refresh_success_provenance(data, target_st, passport_file)
        target_st["evidence_state"] = gate_rec.get(
            "evidence_state", "FAILED" if new_status == "gate_failed" else "VERIFIED"
        )
        data["evidence_state"] = target_st["evidence_state"]
        if new_status == "gate_failed":
            data["next_action"] = (
                f"inspect blocking evidence at stage {stage}, generate a reroute "
                "suggestion, and stop for user authorization"
            )
        elif new_status == "delivered":
            data["next_action"] = (
                f"stage {stage} checkpoint verified; select the next "
                "dependency-ready stage or prepare a delivery decision"
            )
        data["updated"] = gate_rec["evidence"].split("@")[-1]
        rep = passport.validate(data, verify_hash=False)
        if rep["verdict"] == "FAIL":
            raise ValueError(f"写回后 passport 校验 FAIL：{rep['errors']}")
        passport.save(passport_file, data)
        preview["written"] = True
    return preview


def render(rep: "FindingsReport", preview: dict, stage: int) -> str:
    L = [f"# Checkpoint 聚合报告 — stage {stage}", ""]
    v = rep.compute_verdict()
    mark = {"pass": "✅ PASS", "warn": "⚠ WARN", "fail": "⛔ FAIL"}[v]
    L.append(f"- 整体裁定：**{mark}**  |  闸门数：{len(rep.gates)}")
    expected = STAGE_GATES.get(stage)
    if expected:
        L.append(
            f"- 本阶段应覆盖闸门：{'/'.join(expected)}（checkpoints.md §各阶段闸门对照）"
        )
    L.append("")
    L.append("| gate | status | severity | findings | note |")
    L.append("| --- | --- | --- | --- | --- |")
    for g in rep.gates:
        st_mark = f"**{g.status}**" if g.status == "fail" else g.status
        L.append(
            f"| {g.gate} | {st_mark} | {g.severity} | {len(g.findings)} | {g.note} |"
        )
    L.append("")
    if preview is not None:
        tag = (
            "已写入 passport"
            if preview["written"]
            else "dry-run（未写，加 --write 落盘）"
        )
        L.append(
            f"> passport stage[{stage}].gate ← {preview['new_gate']['result']}"
            f"（{tag}），证据指针 {preview['new_gate']['evidence']}"
        )
        if preview.get("new_status"):
            L.append(
                f"> passport stage[{stage}].status ← {preview['new_status']}"
                f"（门结论同步置位）"
            )
    if v == "fail":
        L.append("")
        L.append(
            "> ⛔ 存在 critical fail：确认点**默认阻断推进**（退出码 1）。"
            "修复闸门项或经用户显式 FAIL→PASS 决策并记 notes 后方可继续。"
        )
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def _selftest() -> int:
    import tempfile

    print("### run_checkpoint 离线自测", file=sys.stderr)
    assert _HAS_FINDINGS, "findings_schema/gate_runner 契约必须可导入"
    tmp = tempfile.mkdtemp(prefix="runchk_selftest_")
    ok = True
    try:
        # 造一个"干净"findings 文件（全 pass）和一个"有 HIGH"findings 文件
        clean = FindingsReport(producer="m02", target="clean").finalize()
        clean.gates.append(GateResult("c1", "pass", "info"))
        dirty = FindingsReport(producer="m02", target="data")
        dirty.gates.append(
            GateResult(
                "exact_dup",
                "fail",
                "critical",
                [Finding("f1,f2", "跨 split 精确重复", "去重重划分")],
            )
        )
        dirty.finalize()
        clean_f = os.path.join(tmp, "clean.json")
        dirty_f = os.path.join(tmp, "leak_findings.json")
        with open(clean_f, "w", encoding="utf-8") as fh:
            fh.write(clean.to_json())
        with open(dirty_f, "w", encoding="utf-8") as fh:
            # 模拟 split_leakage 那种带额外 raw_findings 的报告
            d = dirty.to_dict()
            d["raw_findings"] = [{"check": "exact_dup"}]
            json.dump(d, fh, ensure_ascii=False)

        # 1. 聚合：含一个 critical fail → verdict=fail
        rep = aggregate([clean_f, dirty_f], [], stage=2, target="data")
        good = rep.compute_verdict() == "fail"
        ok &= good
        print(
            f"  [{'OK' if good else 'FAIL'}] aggregate critical→fail (gates={len(rep.gates)})"
        )

        # 2. 干净聚合 → pass
        rep2 = aggregate([clean_f], [], stage=2)
        good = rep2.compute_verdict() == "pass"
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] aggregate clean→pass")

        # 3. 闸门命令：退出码 0→pass、非 0→critical fail
        g_ok = gate_from_command("ok", sys.executable + ' -c "import sys;sys.exit(0)"')(
            None
        )
        g_bad = gate_from_command(
            "bad", sys.executable + ' -c "import sys;sys.exit(3)"'
        )(None)
        good = g_ok.status == "pass" and g_bad.is_blocking()
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] command gate exit-code→status")

        # 4. build_gate_record：fail→FAIL + 证据指针含 sha 与时间戳
        rec = build_gate_record(rep, stage=2, ts="2026-06-15T10:00")
        good = (
            rec["result"] == "FAIL"
            and rec["evidence"].startswith("sha256:")
            and rec["evidence"].endswith("2026-06-15T10:00")
            and rec["type"] == "confirm"
            and rec["evidence_state"] == "FAILED"
            and rec["fresh"] is True
        )
        ok &= good
        print(
            f"  [{'OK' if good else 'FAIL'}] gate record FAIL + fresh evidence pointer"
        )

        # 5. 证据指针对内容敏感：闸门集合变了 sha 必变
        rec_clean = build_gate_record(rep2, stage=2, ts="2026-06-15T10:00")
        good = rec_clean["evidence"] != rec["evidence"]
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] evidence sha sensitive to gate set")

        # 6. writeback dry-run 不落盘 / --write 落盘并通过 passport 校验
        ppath = os.path.join(tmp, "passport.yaml")
        passport.cmd_init(
            passport._NS(
                out=ppath,
                force=False,
                project="d",
                pipeline="A",
                created="2026-06-15T09:00",
            )
        )
        with open(os.path.join(tmp, "up.txt"), "w", encoding="utf-8") as fh:
            fh.write("upstream bytes")
        passport.cmd_append_stage(
            passport._mk_append(
                ppath, stage=1, skill="m01", artifacts=["up.txt"], status="delivered"
            )
        )
        passport.cmd_append_stage(
            passport._mk_append(
                ppath,
                stage=2,
                skill="m02",
                artifacts=["data_card.md"],
                depends_on=[1],
                gate_type="confirm",
                gate_result="WARN",
            )
        )
        prev_dry = writeback(ppath, 2, rec, do_write=False)
        reloaded = passport.load(ppath)
        st2 = [s for s in reloaded["stages"] if s.get("stage") == 2][0]
        good = not prev_dry["written"] and st2["gate"].get("result") == "WARN"
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] dry-run leaves passport untouched")

        prev_w = writeback(ppath, 2, rec, do_write=True)
        reloaded = passport.load(ppath)
        st2 = [s for s in reloaded["stages"] if s.get("stage") == 2][0]
        good = (
            prev_w["written"]
            and st2["gate"].get("result") == "FAIL"
            and "sha256:" in str(st2["gate"].get("evidence"))
            and st2.get("status") == "gate_failed"
            and st2.get("evidence_state") == "FAILED"
            and st2["gate"].get("gates") == "clean.json,leak_findings.json"
            and "reroute" in reloaded.get("next_action", "")
            and passport.validate(reloaded)["verdict"] != "FAIL"
        )
        ok &= good
        print(
            f"  [{'OK' if good else 'FAIL'}] --write preserves multi-gate value, "
            "hash, evidence and status"
        )

        # 6b. v2：干净聚合写回 → status=delivered（门 pass 同步置位）
        rec_ok = build_gate_record(rep2, stage=2, ts="2026-06-15T10:00")
        writeback(ppath, 2, rec_ok, do_write=True)
        reloaded = passport.load(ppath)
        st2 = [s for s in reloaded["stages"] if s.get("stage") == 2][0]
        good = (
            st2["gate"].get("result") == "PASS"
            and st2.get("status") == "delivered"
            and st2.get("evidence_state") == "VERIFIED"
            and str(st2.get("inputs_fingerprint", "")).startswith("sha256:")
            and "delivery decision" in reloaded.get("next_action", "")
        )
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] clean writeback → status=delivered")

        # 7. 写回不存在的 stage 报错（不静默）
        try:
            writeback(ppath, 99, rec, do_write=False)
            good = False
        except ValueError:
            good = True
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] writeback unknown stage raises")

        # 8. render 含裁定与证据指针
        md = render(rep, prev_w, 2)
        good = "FAIL" in md and "证据指针" in md and "阻断推进" in md
        ok &= good
        print(
            f"  [{'OK' if good else 'FAIL'}] render shows verdict+evidence+block notice"
        )
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
        print(f"  [cleanup] removed {tmp} exists={os.path.exists(tmp)}")
    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


# ---------------------------------------------------------------- main
def _parse_gate_specs(specs):
    """把 ['label=cmd', ...] 解析成 [(label, cmd), ...]。"""
    out = []
    for s in specs or []:
        if "=" not in s:
            raise ValueError(f"--gate 需 label=cmd 形式，得到：{s}")
        label, cmd = s.split("=", 1)
        out.append((label.strip(), cmd.strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="确认点闸门聚合器：聚合 findings/闸门命令→写回 passport，critical fail 阻断"
    )
    ap.add_argument("--file", default=".light/passport.yaml", help="passport 台账路径")
    ap.add_argument("--stage", type=int, help="本次检查点对应的阶段序号")
    ap.add_argument(
        "--findings",
        nargs="*",
        default=[],
        help="已产出的 light.findings.v1 报告文件（leak_findings.json 等）",
    )
    ap.add_argument(
        "--gate",
        nargs="*",
        default=[],
        dest="gate_specs",
        help="实际执行的闸门命令 label=cmd（退出码定 pass/fail）",
    )
    ap.add_argument(
        "--ts", help="证据时间戳（不传则不写新鲜指针时间，selftest 用固定值）"
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="真正写回 passport（默认 dry-run 仅预览，对台账动手须显式授权）",
    )
    ap.add_argument("--out", help="把聚合报告 md 写到文件（默认 stdout）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not _HAS_FINDINGS:
        print(
            "[run_checkpoint] 致命：_shared/findings_schema+gate_runner 不可导入，"
            "无法聚合闸门。请检查 _shared 路径。",
            file=sys.stderr,
        )
        return 2
    if args.stage is None:
        ap.error("需要 --stage（或 --selftest）")
    if not args.findings and not args.gate_specs:
        ap.error("至少给一个 --findings 文件或一个 --gate label=cmd")

    gate_cmds = _parse_gate_specs(args.gate_specs)
    rep = aggregate(args.findings, gate_cmds, args.stage, target=args.file)
    if args.write and not args.ts:
        ap.error("--write requires --ts with an explicit ISO-8601 evidence time")
    ts = args.ts or "unstamped"
    rec = build_gate_record(rep, args.stage, ts)

    preview = None
    if os.path.exists(args.file):
        preview = writeback(args.file, args.stage, rec, do_write=args.write)
    else:
        print(
            f"[run_checkpoint] 注意：{args.file} 不存在，跳过写回（仅出报告）",
            file=sys.stderr,
        )

    md = render(rep, preview, args.stage)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(md)

    # critical fail → 退出码 1，确定性阻断推进
    return 1 if rep.compute_verdict() == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
