# 跨 harness 续跑：三个 harness 各自"开新对话续上"的确定性路径

> memory-pm「续跑」能力的下沉细则(Round 2 / R4.e,2026-06-23)。全局纪律见本技能 `SKILL.md`。
> 本文回答北极星之问:**"开新对话无缝续上"是不是只有 Claude Code(装了 hook)才有?** —— 不是。
> 续跑汇报已抽成**单一真相源** `scripts/resume_report.py`,经 `pm.py resume` 暴露成**三 harness
> 通用的确定性命令**;CC 的 SessionStart hook 也复用同一份。下面给三 harness 各自的确定性路径。

---

## 0. 核心:一条命令、一份实现、三处调用

```bash
python skills/light-memory-pm/scripts/pm.py resume --dir <项目根>
python skills/light-memory-pm/scripts/memory_governance_gate.py --input <memory-governance.json> --base <项目根>
```

读 `<项目根>/.light/passport.yaml`(+ `project_card.md` 的 `next_actions`),**确定性**产出:
项目 / pipeline / 当前阶段 / 阶段状态 + 门结果 / DAG 派生下一步 / 人写的下一步 / 卡哪门 / stale 最小重验范围。

- **单一真相源** = `scripts/resume_report.py`(纯 stdlib + 仅依赖 passport;**不接** _shared/校验器,要崩不起)。
- **三处调用同一份**(DRY,杜绝漂移):① `pm.py resume`(规范 CLI);② CC 的 `session_start_resident.py`
  hook **import 它并委托**;③ `resume_report.py` 本身可独立跑。三者输出**逐字一致**(selftest 有断言守)。

> 为什么这是真能力而非口号:它**只读 `.light/`**,不依赖聊天历史、不依赖任何 harness 特性——
> 在哪个 harness、从哪个目录跑都出同一份(E2E 已从无关 cwd 仅凭 `--dir` 验证)。
> `memory_governance_gate.py` 是交接/续跑前的硬门:重算 passport state hash,核 handoff 是否 stale,
> 核 memory item 的 scope/sensitivity/reversibility/storage、artifact version、failure index 与采集策略。

---

## 1. 三 harness 确定性路径

| harness | 会话开头怎么续上 | 自动程度 | 确定性 |
|---|---|---|---|
| **Claude Code** | SessionStart hook(`session_start_resident.py`)**自动**调 `resume_report` 注入续跑汇报 | **harness 强制**(resume/compact 重跑,零人力) | ✅ 完全确定性 |
| **Codex** | `AGENTS.md`(注入了 `AGENTS.snippet.md`)指令模型**在会话开头主动跑** `pm.py resume --dir .` | 模型读约定后执行(命令本身确定) | ✅ 命令确定;触发=模型读约定 |
| **OpenCode** | 同 Codex(`AGENTS.md` / `~/.config/opencode/AGENTS.md` 约定 → 跑 `pm.py resume`) | 同 Codex | ✅ 同上 |

**没装 CC hook 的 Claude Code 用户**:CLAUDE.md 块已写明可手动跑 `pm.py resume`——故 CC 即使没装 hook 也能续上。

---

## 2. 与"用户驱动交接卡 + 启动提示词"的关系(互补,不重复)

memory-pm 有两条续跑轨,**互补**:

- **常驻自动续跑(本文)**:**每**次会话开头由 `pm.py resume` / hook 出"当前真实台账态"。优点:无需上次会话留种;
  缺点:只给台账能算出的(阶段/门/stale),给不了"我上次脑子里想的下一步细节"。
- **用户驱动交接(`references/session_handoff.md`)**:上下文将尽/收尾时**主动**留 `handoff/S<NN>-*.md` 卡 +
  打印启动提示词,链式 `parent_session` 可追任意上级会话。优点:带"具体下一步 + 禁止事项";缺点:要上次主动留。

**最佳实践**:接手时**先跑 `pm.py resume`** 看台账真实态(项目/卡门/stale),**再读最新 handoff 卡**补"具体下一步"。
两者都不替代"按 orchestrator 纪律刷新 `git status`/CI 等当前证据"——卡与汇报是入口,不是现实本身。

---

## 3. 诚实边界(只声称验过的)

- **已验(E2E,harness 无关)**:`pm.py resume` / `resume_report.py` 仅凭 `.light/` 即产出**正确**续跑汇报
  (项目/阶段/卡门/stale 重验/下一步);`resume_report` selftest 含"与 hook 输出逐字一致"防漂移断言;
  CC hook selftest(22 项)在委托重构后全绿。本机 **Codex CLI 0.138.0 / OpenCode 1.17.6 已装**(2026-06-23 核)。
- **未验(诚实标)**:**未在真 Codex / OpenCode 的 model 会话里端到端跑**"会话开头自动续跑"——守"零付费 key"
  铁律,未触发需 key 的 model 会话(且 model 是否在开头读 AGENTS.md 约定属非确定行为)。故**绝不声称
  "三 harness 都已实测自动续跑"**;只声称"确定性命令仅凭 `.light/` 能续上(已验)+ Codex/OpenCode 经
  AGENTS.md 约定调它(命令确定、触发靠模型读约定)"。
- **harness 自动程度差**(非缺陷,是机制现实):CC hook 是 harness 强制(最强);Codex/OpenCode 靠模型读约定
  触发(命令一旦被调,结果与 CC 完全一致)。这条差异在 SKILL「名实对齐 #4」与 `INSTALL.md` 均如实写明。
