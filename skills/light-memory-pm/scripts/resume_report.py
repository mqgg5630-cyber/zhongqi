#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resume_report.py — 会话开头「续跑汇报」的**单一真相源**(跨 harness 确定性)。

为什么存在(Round 2 / R4.e,2026-06-23)
------------------------------------------------------------
批 0 把续跑汇报逻辑(`build_status_report`)只写在 light-orchestrator 的
SessionStart hook 里,且**只有 Claude Code 的 hook 会调它**。Codex / OpenCode
无 session-start hook,批 0 只能在 AGENTS.md 里叫模型"自己跑 get-current-stage +
stale-check 再脑补"——两条命令 + 模型合成,非确定性单命令(诚实落后项 #4)。

本模块把续跑汇报抽成 memory-pm **自有的确定性能力**(对标 jayzeng/agentmemory 的
`agent-memory context` 命令 + WeirdSky924/agent-handoff-skill 的"约定读单文件"):
  - `pm.py resume` 一条确定性命令产出**同一份**续跑报告(项目/阶段/卡门/重验/下一步);
  - Claude Code 的 SessionStart hook **反过来 import 本模块**并调 `build_status_report`
    (DRY:杀掉"hook 一份 + pm.py 一份"的漂移隐患——上一轮 citation 正是漂移/未覆盖才崩);
  - Codex / OpenCode 经 AGENTS.md 约定在会话开头**显式跑 `pm.py resume`**。
→ "完美续上"从"装了 CC hook 才有"变成"建了 .light/ + 一条命令就有",三 harness 同一份。

设计纪律(与 hook 一致,保证 hook 反调后行为零变)
  - **纯 stdlib + 仅依赖 passport**(读台账解析器,复用不重造);**绝不**接 _shared / 3 校验器
    (那些是 audit 的重依赖;续跑只读不审,hook 要崩不起)。
  - 幂等无副作用(只读 + 返回字符串,绝不写文件);解析失败 / 无台账 / 台账损坏都**不抛**,
    降级为可读提示(纪律侧由 hook 兜)。
  - 输出字符串与批 0 hook `build_status_report` **逐字一致**(token 级),hook selftest 不改即过。

自测:python resume_report.py --selftest   用法:python resume_report.py --dir <项目根>
(规范入口是 `pm.py resume --dir <项目根>`;本文件可独立跑,便于 hook 复用与单测。)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 路径 bootstrap:找到 passport 引擎(复用不重造)。两条路都试,稳。──
#   ① 向上走目录树找仓库根(含 _shared/__init__.py),加 skills/light-orchestrator/scripts(对齐 pm.py)。
#   ② 直接兄弟路径兜底:本文件在 skills/light-memory-pm/scripts/,passport 在
#      skills/light-orchestrator/scripts/(整个技能树一起复制/链接,相对路径成立)。
_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
_CANDIDATES = [
    _ROOT / "skills" / "light-orchestrator" / "scripts",
    _HERE.parent.parent / "light-orchestrator" / "scripts",
]
for _c in _CANDIDATES:
    if (_c / "passport.py").exists():
        sys.path.insert(0, str(_c))
        break

try:
    import passport  # 复用的台账解析器(不重造)
    _HAS_PASSPORT = True
except Exception:  # noqa: BLE001  导入失败不致命:调用方据 _HAS_PASSPORT 降级
    _HAS_PASSPORT = False
try:
    import handoff_contract
    _HAS_HANDOFF_CONTRACT = True
except Exception:  # noqa: BLE001  旧安装降级为不显示交接问题
    _HAS_HANDOFF_CONTRACT = False


def _e2e_selftest_dir() -> pathlib.Path:
    root = _ROOT / ".upgrade" / "_e2e"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _next_step(status: str, stage) -> str:
    """据当前阶段有效状态给「下一步」确定性建议(对齐 SKILL §0-§2 指令流)。"""
    return {
        "gate_failed": (f"⛔ 确认点 Critical fail。跑 `reroute.py --stage {stage}` 出建议回边 → "
                        "**停下问用户** → 拍板后 `passport.py add-back-edge` 落账。"),
        "needs_rework": ("🔁 被下游按根因回炉,待返修。带回边证据修复产物 → 重跑 "
                         "`run_checkpoint`(通过则 status 翻 delivered)。"),
        "delivered": "✅ 本阶段已交付。推进 DAG 下游阶段 / 跑其确认点。",
        "in_progress": "🔨 本阶段进行中。完成产物 → 跑 `run_checkpoint` 过确认点。",
        "not_started": "▶ 本阶段未开始。从本阶段产出开始。",
    }.get(status, "先 `passport.py get-current-stage` 复核状态再决定。")


def _project_card_next_actions(cwd) -> str:
    """从 project_card.md 提取人写的 `next_actions`(SKILL 反复强调"会话开头先读"的一行,
    往往比 DAG 派生建议更具体)。**纯正则、零 YAML 依赖、剥行内注释**;缺失/模板占位/异常
    一律返回 ""(报告主体不受影响,绝不抛)——与本模块"读不到就降级"的纪律一致。"""
    pc = os.path.join(cwd, ".light", "project_card.md")
    if not os.path.exists(pc):
        return ""
    try:
        with open(pc, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*next_actions\s*:(.*)$", line)
                if not m:
                    continue
                # 按 YAML 语义剥 ` #` 行内注释(含"整行只有注释=空值"的模板占位情形):
                # 行首 # 或空白后 # 起到行尾都算注释。
                val = re.sub(r"(^|\s)#.*$", "", m.group(1)).strip()
                if not val or val.startswith("<"):   # 空 / 模板占位 <...> → 当未填
                    return ""
                return val
    except Exception:  # noqa: BLE001  解析失败不致命
        return ""
    return ""


def build_status_report(cwd) -> str:
    """读 <cwd>/.light/passport.yaml,出续跑状态汇报段;读不到则降级提示,绝不抛。

    cwd = 项目根目录(.light/ 的父目录)。返回以 "\\n## 📍 项目续跑状态" 开头的报告段;
    无 cwd / 无 passport 引擎时返回 ""(由调用方决定是否仅注纪律)。
    **输出字符串与批 0 hook 逐字一致**——hook 反调本函数后行为零变。
    """
    if not cwd or not _HAS_PASSPORT:
        return ""
    pp = os.path.join(cwd, ".light", "passport.yaml")
    if not os.path.exists(pp):
        return ("\n## 📍 项目续跑状态\n"
                "- 未发现 `.light/passport.yaml`。新科研项目可让 light-orchestrator 跑 "
                "`passport.py init` 建台账;非科研任务忽略本段。\n")
    try:
        data = passport.load(pp)
    except Exception as e:  # noqa: BLE001  台账损坏不致命
        sys.stderr.write(f"[resume_report] 台账读取失败:{e}\n")
        return ("\n## 📍 项目续跑状态\n"
                f"- ⚠ 台账存在但读取失败:{e}。建议手动 `passport.py validate --file {pp}`。\n")

    stages = data.get("stages") or []
    by_num = {s.get("stage"): s for s in stages if isinstance(s, dict)}
    cs = data.get("current_stage")
    cur = by_num.get(cs)

    L = ["\n## 📍 项目续跑状态(读自 .light/passport.yaml,确定性,非记忆)"]
    if _HAS_HANDOFF_CONTRACT:
        try:
            pending = handoff_contract.latest_open_questions(
                pathlib.Path(cwd) / ".light" / "handoff"
            )
            questions = pending.get("questions") or []
            if questions:
                card = pathlib.Path(str(pending.get("card"))).name
                L.append(f"- ❓ **上次待用户回答（先处理，来源 {card}）**")
                for item in questions:
                    L.append(
                        f"  - [{item['decision']}] {item['question']} "
                        f"A: {item['option_a']}；B: {item['option_b']}"
                    )
        except Exception as exc:  # noqa: BLE001
            L.append(f"- ⚠ handoff open-question 读取失败：{exc}")
    head = (f"- 项目:{data.get('project')} | pipeline:{data.get('pipeline')} | 当前阶段:{cs}"
            + (f"({cur.get('skill')})" if cur else ""))
    L.append(head)
    state_hash = data.get("state_hash")
    if state_hash and hasattr(passport, "compute_state_hash"):
        expected_hash = passport.compute_state_hash(data)
        if state_hash == expected_hash:
            L.append(f"- 状态指纹:{state_hash}（canonical state 校验通过）")
        else:
            L.append(f"- ⚠ 状态指纹校验失败:记录={state_hash} | 实算={expected_hash}")
    if cur:
        stt = passport.effective_status(cur)
        gate = cur.get("gate") or {}
        L.append(f"- 当前阶段状态:**{stt}**"
                 + (f" | 门结果:{gate.get('result')}" if gate.get("result") else ""))
        L.append(f"- 下一步建议:{_next_step(stt, cs)}")

    # 人写的"下一步"(project_card.next_actions;SKILL 强调会话开头先读,比 DAG 派生更具体)
    na = _project_card_next_actions(cwd)
    if na:
        L.append(f"- 📝 上次记的下一步(project_card.next_actions):{na}")

    # 卡哪门 / 待返修:全 DAG 扫 gate_failed / needs_rework
    attention = []
    for s in stages:
        if not isinstance(s, dict):
            continue
        st = passport.effective_status(s)
        if st in ("gate_failed", "needs_rework"):
            attention.append(f"stage{s.get('stage')}={st}")
    if attention:
        L.append(f"- ⚠ 需关注(卡门 / 待返修):{', '.join(attention)}")

    # stale-check 最小重验范围(断点恢复:别重做已 fresh 的阶段)
    try:
        nr = (passport.stale_check(data, root=cwd) or {}).get("need_reverify") or []
        if nr:
            L.append(f"- 需重验(stale / incomplete,最小范围):stage {nr}")
    except Exception:  # noqa: BLE001  stale 计算失败不致命,状态主体已给
        pass

    return "\n".join(L) + "\n"


def render_cli(cwd) -> str:
    """`pm.py resume` / 独立运行的可读输出:报告段 + 无台账时的明确提示。"""
    if not _HAS_PASSPORT:
        return ("[resume] 无法 import passport 引擎(应在 "
                "skills/light-orchestrator/scripts/)——无法出续跑汇报。")
    section = build_status_report(cwd)
    banner = ("=" * 64 + "\nmemory-pm 续跑汇报(resume · 跨 harness 确定性单一真相源)\n"
              + "=" * 64)
    return banner + section + "=" * 64


# ===========================================================================
# 自测(合成台账,自清理无残留)
# ===========================================================================
def _selftest() -> int:
    import tempfile
    import shutil
    failures = []

    def check(cond, msg):
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
        if not cond:
            failures.append(msg)

    check(_HAS_PASSPORT, "能 import passport 引擎(bootstrap 找到 passport.py)")
    if not _HAS_PASSPORT:
        print("[selftest] resume_report SOME FAILED:passport 不可用")
        return 1

    # 1. 无 cwd → "";无台账目录 → 提示建台账
    check(build_status_report(None) == "", "无 cwd → 空串(交调用方仅注纪律)")
    tmp0 = tempfile.mkdtemp(prefix="resume_e2e_", dir=str(_e2e_selftest_dir()))
    try:
        r0 = build_status_report(tmp0)
        check("📍 项目续跑状态" in r0 and "未发现" in r0 and "passport.py init" in r0,
              "无台账 → 提示建台账,不崩")
    finally:
        shutil.rmtree(tmp0, ignore_errors=True)

    # 2. 有台账(gate_failed)→ 报项目/阶段/卡门/下一步(与 hook 同款断言)
    tmp = tempfile.mkdtemp(prefix="resume_e2e_", dir=str(_e2e_selftest_dir()))
    try:
        pp = os.path.join(tmp, ".light", "passport.yaml")
        data = {
            "schema": "light.passport.v3",
            "project": "selftest-proj", "pipeline": "A",
            "created": "2026-06-23T00:00", "updated": "2026-06-23T00:00",
            "current_stage": 8,
            "state_revision": 0,
            "state_hash": "sha256:" + ("0" * 64),
            "evidence_state": "OBSERVED",
            "next_action": "repair stage 8",
            "delivery_status": "IN_PROGRESS",
            "delivery_authorization_id": None,
            "stages": [
                {"stage": 7, "skill": "result-analysis", "input": "实验结果",
                 "output": "分析", "status": "delivered",
                 "artifacts": ["docs/analysis.md"],
                 "gate": {"type": "confirm", "result": "PASS"}},
                {"stage": 8, "skill": "paper-writing", "input": "分析",
                 "output": "初稿", "status": "gate_failed", "depends_on": [7],
                 "gate": {"type": "confirm", "result": "FAIL"}},
            ],
        }
        passport.save(pp, data)
        r = build_status_report(tmp)
        check("selftest-proj" in r, "续跑报告含项目名")
        check("paper-writing" in r and "gate_failed" in r, "报当前阶段与状态")
        check("状态指纹:" in r and "canonical state 校验通过" in r,
              "v3 台账在续跑报告展示并校验 canonical state hash")
        check("reroute" in r, "gate_failed → 下一步建议提 reroute")
        check("stage8=gate_failed" in r, "需关注段列出卡门阶段")
        # MISSING artifact(docs/analysis.md 不存在)→ stale_check 应把 stage7/8 列入重验
        check("需重验" in r, "缺产物 → stale-check 列入最小重验范围")
        # render_cli 包裹正确
        cli = render_cli(tmp)
        check("续跑汇报(resume" in cli and "selftest-proj" in cli, "render_cli 包裹报告")

        # 2b. project_card.next_actions 提取(人写的下一步,会话开头最该看)
        pc = os.path.join(tmp, ".light", "project_card.md")
        # 模板占位 <...> → 不显示(当未填)
        with open(pc, "w", encoding="utf-8") as f:
            f.write("```yaml\nnext_actions:          # 下一步(会话开始先读这里)\n```\n")
        check("project_card.next_actions" not in build_status_report(tmp),
              "next_actions 为模板占位/空 → 不显示")
        # 填了真值 + 带行内注释 → 显示且剥注释
        with open(pc, "w", encoding="utf-8") as f:
            f.write("```yaml\nnext_actions: 重跑 E2 baseline 换随机种子  # 优先级最高\n```\n")
        rna = build_status_report(tmp)
        check("project_card.next_actions" in rna and "重跑 E2 baseline 换随机种子" in rna,
              "next_actions 填了真值 → 显示")
        check("优先级最高" not in rna, "next_actions 行内 # 注释被剥离")

        # 2c. 最新 handoff 的待用户问题必须在项目状态前置顶，避免新会话漏答后闷头续跑。
        handoff_dir = pathlib.Path(tmp) / ".light" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        (handoff_dir / "S03-open-question.md").write_text(
            """---
session_no: S03
contract_version: 2
suggested_title: "[demo] S04 Continue"
parent_session: none
project: selftest-proj
date: 2026-07-05
---
## 待用户回答
- decision_id=direction-1 | question=是否继续当前方向？ | option_a=继续；影响：冻结当前方向 | option_b=暂缓；影响：先补证据
""",
            encoding="utf-8",
        )
        ropen = build_status_report(tmp)
        check("上次待用户回答" in ropen and "direction-1" in ropen,
              "最新 handoff 的待用户问题进入续跑报告")
        check(ropen.index("上次待用户回答") < ropen.index("- 项目:"),
              "待用户问题在项目状态之前置顶")

        # 2d. 人工篡改 canonical 内容但不重算 hash → 报告必须显式暴露，不可静默续跑。
        tampered = passport.load(pp)
        tampered["next_action"] = "tampered without save"
        with open(pp, "w", encoding="utf-8") as f:
            f.write(passport.emit_yaml(tampered))
        rt = build_status_report(tmp)
        check("状态指纹校验失败" in rt, "台账内容被篡改 → 续跑报告显式告警")
        passport.save(pp, data)

        # 3. 台账损坏 → 降级提示,不崩
        with open(pp, "w", encoding="utf-8") as f:
            f.write(":\n  : bad\n   broken: [unclosed\n")
        rbad = build_status_report(tmp)
        check("📍 项目续跑状态" in rbad, "台账损坏仍出报告段(降级不崩)")

        # 4. 与 hook 输出一致性(关键:验"单一真相源",防漂移):
        #    hook 反调本函数,故此处直接对比 hook 模块的 build_status_report 同输入输出。
        hook_dir = _HERE.parent.parent / "light-orchestrator" / "resident"
        if (hook_dir / "session_start_resident.py").exists():
            sys.path.insert(0, str(hook_dir))
            try:
                import importlib
                ssr = importlib.import_module("session_start_resident")
                # 重新写回好台账再比
                passport.save(pp, data)
                same = ssr.build_status_report(tmp) == build_status_report(tmp)
                check(same, "hook.build_status_report 与本模块输出逐字一致(DRY 无漂移)")
            except Exception as e:  # noqa: BLE001
                check(False, f"导入 hook 比对失败:{e}")
        else:
            print("  [skip] 未找到 hook(session_start_resident.py),跳过一致性比对")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"  [cleanup] removed tmp exists={os.path.exists(tmp)}")

    if failures:
        print(f"\n[selftest] resume_report SOME FAILED({len(failures)} 条):")
        for f in failures:
            print("  -", f)
        return 1
    print("\n[selftest] resume_report ALL PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="会话开头续跑汇报(跨 harness 确定性单一真相源;规范入口 pm.py resume)")
    ap.add_argument("--selftest", action="store_true", help="离线合成自测,自清理无残留")
    ap.add_argument("--dir", default=".", help="项目根目录(.light/ 的父目录,默认当前)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    print(render_cli(args.dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
