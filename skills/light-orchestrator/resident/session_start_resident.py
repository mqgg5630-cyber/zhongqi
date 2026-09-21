#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_start_resident.py — Light v2 常驻纪律 + 续跑状态的确定性注入钩子。

(Claude Code SessionStart hook;港 v1 `Light/hooks/session_start_resident.py` 并按 v2 升级。)

为什么存在(机制已上网核实 code.claude.com/docs/en/hooks):
  Claude Code 技能只有两种触发——用户打 /name,或模型读 description 概率匹配自主加载。
  没有第三种。正文只在被调用那次进上下文,compaction 后可能整段掉。于是"常驻技能后台生效"
  "研究伦理 100% 触发"在纯 description 机制下是**愿望非保证**。本钩子是用户拍板的
  "CLAUDE.md + hooks 双保险"里的 hook 半边:每次会话开始(SessionStart)由 harness 确定性
  注入①常驻纪律 + 红线 ②**读 .light/passport.yaml 出的续跑状态汇报**(上次断哪 / 卡哪门 /
  下一步)。这是 harness 层强制,不依赖模型自觉。

v2 相对 v1 的增量:
  1. 技能名从 v1 的 a07-a10 编号 → v2 的 23 个**命名技能**(总控 1 + 常驻 5 + 主线 13 + 工程/IP 4),
     并强调总控**会停下问用户**(协作式半自主)。
  2. **续跑状态汇报**:读 hook 输入里的 `cwd` → 找 `.light/passport.yaml` → 出"当前阶段 /
     status / 卡门 / 需重验 / 下一步建议"。把 spec §8 的"会话开头自动汇报续跑点"从 SKILL
     喊话落成 harness 确定性注入(E2E①)。
  3. **(Round 2 / R4.e)续跑逻辑抽到 memory-pm 的 resume_report.py(单一真相源)**:本 hook
     **委托** `resume_report.build_status_report`,与三 harness 通用的 `pm.py resume` 跑同一份
     (DRY,杜绝两份实现漂移)。CC 由 hook 自动调,Codex/OpenCode 经 AGENTS.md 约定显式调。

SessionStart 协议要点(已核实):
  - stdin 收 JSON:{session_id, transcript_path, cwd, hook_event_name, source, model}(source ∈
    startup/resume/clear/compact);**resume 会重跑**——正好刷新续跑状态。
  - exit 0 时:纯 stdout 直接进上下文,或 JSON `hookSpecificOutput.additionalContext`(本钩子用后者,
    显式、可被 selftest 机验)。**SessionStart 不能阻断会话**(exit 2 仅显错)。
  - `additionalContext` 上限 **10000 字**(超出 harness 转存文件)→ 本钩子自带截断保护。

设计纪律:
  - 纯 stdlib、零网络、跨平台(Windows/macOS/Linux 同一份);幂等无副作用(只读 + 输出,绝不写文件)。
  - 解析失败 / 无台账 / 台账损坏都**不让会话崩**——降级为仍注入常驻纪律(纪律一定到位,错误进 stderr 不静默吞)。
  - 只用 passport 的**库函数**(load/effective_status/stale_check…),不调会打印的 cmd_* 处理器,
    保证 stdout 只有最终 JSON,不污染 harness 解析。

安装:见 resident/INSTALL.md(三 harness)。自测:python session_start_resident.py --selftest
"""
from __future__ import annotations

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 复用同目录树的脚本(复用不重造):passport 引擎 + memory-pm 续跑汇报 ──
# 钩子在 skills/light-orchestrator/resident/;passport 在 ../scripts/;
# 续跑汇报单一真相源 resume_report 在 ../../light-memory-pm/scripts/。
# 整个技能树一起复制/链接,故这些相对路径在本地/全局安装下都成立。
# Round 2(R4.e):续跑汇报逻辑已抽到 memory-pm 的 resume_report.py(单一真相源),
# 本 hook **反过来 import 它并委托**(DRY)——CC hook 与 `pm.py resume` 跑同一份,
# 杜绝"hook 一份 + pm.py 一份"的漂移(上一轮 citation 正是漂移/未覆盖才崩)。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "scripts"))                       # passport
sys.path.insert(0, os.path.join(_HERE, "..", "..", "light-memory-pm", "scripts"))  # resume_report
try:
    import passport  # noqa: E402,F401  同技能树台账工具(selftest 用其 save)
    _HAS_PASSPORT = True
except Exception:  # noqa: BLE001  导入失败不致命:降级只注纪律
    _HAS_PASSPORT = False
try:
    import resume_report  # noqa: E402  续跑汇报单一真相源(memory-pm)
    _HAS_RESUME = True
except Exception:  # noqa: BLE001  导入失败不致命:降级只注纪律(续跑段缺失但纪律到位)
    _HAS_RESUME = False

HOOK_EVENT = "SessionStart"
_CTX_CAP = 9800  # 留余量于 harness 的 10000 字硬上限
_DISCIPLINE_BUDGET = 4200
_RESUME_BUDGET = 5400

# ── 常驻纪律精简版(指针式,不复制各 SKILL 正文;真相源在各 SKILL.md / spec)──
RESIDENT_CONTEXT = """\
# Light v2 科研技能包 · 常驻纪律(SessionStart 确定性注入)

你装载了 **Light 科研全流程技能包**(23 技能:总控 1 + 常驻 5 + 主线 13 + 工程/IP 4)。
下列是 harness 层提醒,不是可选建议。

## 总控 = 协作式半自主(会停下问你)
**light-orchestrator** 是总控大脑:跨多阶段大任务 /「继续·刚断了·接手」断点恢复时**自动启动**。
它**不黑箱自动驾驶**——大决策(选方向 / 定 idea / 选 venue / 回炉)一律**停下问用户**,给「推荐 + 理由 + 备选」。

## 5 个常驻技能(无需 /调用,相关任务即生效)
- **memory-pm**:项目台账(.light/passport.yaml + 决策日志),跨会话记忆归属。
- **project-structure**:项目文件夹结构整理。
- **consistency**:术语 / 指标 / 创新点跨材料一致性,定义一改回扫所有产物。
- **research-ethics**:学术诚信红线门——不臆造文献 / 数据 / DOI / 端点,区分「已验证」与「推测」。
- **file-reading**:涉及读文件时自动触发。
- (self-review 已并入「收尾 self-check」,不单设技能;每次对外输出前过一遍。)

## 13 主线技能(总控按 DAG 调度,非每次全跑)
literature-search → data-engineering / idea-generation ⇄ idea-critique → research-plan →
experiment-coding → result-analysis → paper-writing / figure / citation → typesetting →
venue-matching → review-rebuttal。工程/IP 4:frontend-design / system-design / patent-disclosure /
software-copyright(做系统 / 界面 / 软件作品 / 成果转化材料时按需用,不进科研 DAG)。

## 红线(NON-NEGOTIABLE,违反 = 严重失职)
1. 绝不替用户定方向 / idea / 结论 / venue(押上数月,只能用户拥有)。
2. 绝不自称「门过了」——诚信门必须**机读 exit code + 用户确认**,不口头当证据。
3. 绝不编造(引用 / 数字 / 结果 / DOI / API 端点)→ 写「待核查 / GAP」。
4. 绝不把判断当事实(新颖性 / 显著性 → 降级「建议核实」)。
5. 绝不静默回炉、绝不静默带病冲过失败门 → 都浮出来问用户。
6. 绝不覆盖未提交改动 / 无授权做难撤销副作用。
论文图 / 数据图必须**程序化生成,绝不 AI 生图**。确认点用 light-orchestrator/scripts/run_checkpoint.py
聚合各技能 findings 做机读闸门,Critical fail 默认阻断(exit 1),不靠「口头说跑了」。
"""


def build_status_report(cwd) -> str:
    """续跑状态段:**委托 memory-pm 的 resume_report**(单一真相源,DRY)。

    Round 2(R4.e)前,本逻辑写在这里且只有 CC hook 调它;现抽到 resume_report.py,
    `pm.py resume`(三 harness 通用)与本 hook 跑**同一份**实现。resume_report 不可用
    时降级为空段(仅注纪律),绝不让会话崩——纪律一定到位。
    """
    if not cwd:
        return ""
    if not _HAS_RESUME:
        return ("\n## Resident resume degradation\n"
                "- evidence_state: UNAVAILABLE\n"
                "- reason: memory-pm resume_report could not be imported\n"
                "- next: run `python light-memory-pm/scripts/pm.py resume --dir <project>`\n")
    try:
        return resume_report.build_status_report(cwd)
    except Exception as e:  # noqa: BLE001  续跑段失败不致命,纪律必到位
        sys.stderr.write(f"[session_start_resident] 续跑段生成失败:{e}\n")
        return ""


def build_output(payload: dict) -> dict:
    """构造 SessionStart hook 输出 JSON:常驻纪律 + 续跑状态,带 10000 字截断保护。"""
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    discipline = RESIDENT_CONTEXT
    if len(discipline) > _DISCIPLINE_BUDGET:
        discipline = discipline[:_DISCIPLINE_BUDGET] + (
            "\n…(resident discipline budget exceeded; read light-orchestrator/SKILL.md)")
    resume = build_status_report(cwd)
    if len(resume) > _RESUME_BUDGET:
        resume = resume[:_RESUME_BUDGET] + (
            "\n…(resume report budget exceeded; read canonical .light/passport.yaml)")
    ctx = discipline + resume
    if len(ctx) > _CTX_CAP:
        ctx = ctx[:_CTX_CAP] + "\n…(超出 10000 字上限已截断;详见 .light/passport.yaml)"
    return {"hookSpecificOutput": {
        "hookEventName": HOOK_EVENT,
        "additionalContext": ctx,
    }}


def run(stdin_text: str) -> str:
    """读 hook 输入文本 → 返回应打印到 stdout 的 JSON 文本。
    解析失败不抛:降级为仍注入常驻纪律(纪律一定到位,续跑状态段缺失但会话不崩)。"""
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except (json.JSONDecodeError, ValueError):
        sys.stderr.write("[session_start_resident] hook 输入非合法 JSON,降级仍注入常驻纪律\n")
        payload = {}
    return json.dumps(build_output(payload), ensure_ascii=False)


def _selftest() -> int:
    import tempfile
    import shutil

    failures = []

    def check(cond, msg):
        print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
        if not cond:
            failures.append(msg)

    # 1. 合法 SessionStart 输入 → 结构正确、含 v2 命名技能 + 红线 + 总控
    out = run(json.dumps({"session_id": "x", "source": "startup",
                          "hook_event_name": "SessionStart", "cwd": "/no/such/dir"}))
    d = json.loads(out)
    hso = d.get("hookSpecificOutput", {})
    check(hso.get("hookEventName") == "SessionStart", "hookEventName 应为 SessionStart")
    ctx = hso.get("additionalContext", "")
    for tok in ("light-orchestrator", "research-ethics", "consistency", "memory-pm",
                "review-rebuttal", "停下问用户", "绝不编造", "run_checkpoint", "NON-NEGOTIABLE"):
        check(tok in ctx, f"注入上下文应含「{tok}」")
    check("a07" not in ctx and "a10" not in ctx, "不应残留 v1 的 a07-a10 编号")

    # 2. 空 stdin → 仍注入纪律(降级不崩)
    check("research-ethics" in json.loads(run(""))["hookSpecificOutput"]["additionalContext"],
          "空输入应降级仍注入纪律")

    # 3. 非法 JSON → 不抛、仍注入
    check("light-orchestrator" in json.loads(run("not-json{{{"))
          ["hookSpecificOutput"]["additionalContext"], "非法 JSON 应降级仍注入纪律")

    # 4. 输出恒为单个合法 JSON 对象(harness 要能解析)
    try:
        json.loads(run(json.dumps({"source": "resume"})))
        check(True, "输出为合法 JSON")
    except Exception as e:  # noqa: BLE001
        check(False, f"输出应为合法 JSON:{e}")

    # 5. 有台账的 cwd → 注入续跑状态(项目名 / 当前阶段 / 卡门 / 下一步)
    tmp = tempfile.mkdtemp(prefix="light_hook_e2e_")
    try:
        pp = os.path.join(tmp, ".light", "passport.yaml")
        data = {
            "schema": "light.passport.v2",
            "project": "selftest-proj", "pipeline": "A",
            "created": "2026-06-16T00:00", "updated": "2026-06-16T00:00",
            "current_stage": 8,
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
        out5 = run(json.dumps({"source": "resume", "cwd": tmp}))
        ctx5 = json.loads(out5)["hookSpecificOutput"]["additionalContext"]
        check("📍 项目续跑状态" in ctx5, "有台账应注入续跑状态段")
        check("selftest-proj" in ctx5, "续跑状态应含项目名")
        check("paper-writing" in ctx5 and "gate_failed" in ctx5, "应报当前阶段与状态")
        check("reroute" in ctx5, "gate_failed → 下一步建议应提 reroute")
        check("stage8=gate_failed" in ctx5, "需关注段应列出卡门阶段")

        # 6. 台账损坏 → 降级提示,不崩
        with open(pp, "w", encoding="utf-8") as f:
            f.write(":\n  : bad\n   broken: [unclosed\n")
        out6 = run(json.dumps({"source": "startup", "cwd": tmp}))
        ctx6 = json.loads(out6)["hookSpecificOutput"]["additionalContext"]
        check("research-ethics" in ctx6, "台账损坏仍应注入常驻纪律")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 7. 无台账的 cwd → 提示建台账,不崩
    tmp2 = tempfile.mkdtemp(prefix="light_hook_e2e_")
    try:
        ctx7 = json.loads(run(json.dumps({"source": "startup", "cwd": tmp2})))[
            "hookSpecificOutput"]["additionalContext"]
        check("未发现" in ctx7 and "passport.py init" in ctx7, "无台账应提示建台账")
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # 8. 截断保护:超长上下文不超 10000 字
    check(len(json.loads(run("{}"))["hookSpecificOutput"]["additionalContext"]) <= 10000,
          "注入上下文不超 harness 10000 字上限")
    check(_DISCIPLINE_BUDGET + _RESUME_BUDGET <= _CTX_CAP,
          "resident discipline/resume budgets fit total context cap")

    if failures:
        print(f"\n[selftest] session_start_resident SOME FAILED({len(failures)} 条):")
        for f in failures:
            print("  -", f)
        return 1
    print("\n[selftest] session_start_resident ALL PASS")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    print(run(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
