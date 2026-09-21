# 安装 Light v2 常驻触发(三 harness)

Light 是装进 **Claude Code / Codex / OpenCode** 的科研全流程总控技能包。三者**共用同一套
`skills/` + `scripts/`**(SKILL.md 已成开放标准,均原生消费),**仅"如何被发现 / 常驻触发"的
注入层不同**。本文逐 harness 给安装步。

> **纪律(spec §8)**:安装器只**链接技能 + 文档化注入步**,**不擅自改你的全局配置**。下面凡涉及
> 改 `CLAUDE.md` / `AGENTS.md` / `settings.json` 的,都给出**幂等、带 marker 守卫**的步骤,由你执行。
>
> 下文 `<LIGHT_DIR>` = 你克隆 Light-Skills 仓库的**绝对路径**(示例用 `~/.claude/Light-Skills`)。

---

## 机制对照(均已上网核实,2026-06)

| harness | 技能发现 | 常驻触发手段 | 续跑状态汇报 |
|---|---|---|---|
| **Claude Code** | `~/.claude/skills/<name>/`(自动) | ✅ **SessionStart hook**(harness 确定性,resume/compact 重跑)+ `CLAUDE.md` 块 | **自动**(hook 调 `pm.py resume` 注入) |
| **Codex** | 自身 skills 目录(2025-12 起原生消费 SKILL.md) | `AGENTS.md`(模型读,无 hook) | **一条确定性命令** `pm.py resume`(会话开头主动跑;与 hook 同一份) |
| **OpenCode** | `.opencode/skills/` 或 `~/.config/opencode/skills/`,**兼容 `.claude/skills/`**(自动,向上走到 git 根) | `AGENTS.md` / `~/.config/opencode/AGENTS.md`(模型读,**无 session-start hook**) | 同 Codex(`pm.py resume`) |

> **诚实差异(Round 2 已缩小)**:续跑汇报逻辑已抽成 memory-pm 的 `resume_report.py`(**单一真相源**),
> 由 `pm.py resume` 暴露成**三 harness 通用的确定性命令**,CC 的 hook 也复用它——故**三 harness 出同一份
> 续跑报告**(项目/阶段/卡门/需重验/下一步),"完美续上"不再"只有装了 CC hook 才有"。**仍存的差**:
> CC 由 hook **harness 层自动**调(resume/compact 重跑,零人力);Codex/OpenCode **无 session-start
> 机制**,要靠 `AGENTS.md` 约定让模型**在会话开头主动跑**该命令(命令确定性,但"何时触发"仍是模型读约定、
> 非 harness 强制)。**已验**:该命令仅凭 `.light/` 即出正确续跑(E2E,harness 无关);**未验**:真
> Codex/OpenCode model 进程里的端到端自动续跑(守零-key 未跑 model 会话——见 memory-pm SKILL 名实对齐 #4)。

---

## A. Claude Code(双保险:hook + CLAUDE.md)

### A1. 克隆 + 链接技能
```bash
git clone <repo-url> ~/.claude/Light-Skills
# 把 skills/ 下每个技能链接进 ~/.claude/skills/(Claude Code 自动发现)
for d in ~/.claude/Light-Skills/skills/*/; do
  ln -s "$d" "$HOME/.claude/skills/$(basename "$d")"
done
```
Windows(PowerShell,管理员或开发者模式):
```powershell
git clone <repo-url> "$env:USERPROFILE\.claude\Light-Skills"
Get-ChildItem "$env:USERPROFILE\.claude\Light-Skills\skills" -Directory | ForEach-Object {
  New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\$($_.Name)" -Target $_.FullName
}
```

### A2. 追加常驻纪律到全局 `CLAUDE.md`(幂等,marker 守卫)
```bash
mkdir -p ~/.claude && touch ~/.claude/CLAUDE.md
if ! grep -q '<!-- LIGHT-SKILLS-START -->' ~/.claude/CLAUDE.md; then
  cat ~/.claude/Light-Skills/skills/light-orchestrator/resident/CLAUDE.snippet.md >> ~/.claude/CLAUDE.md
else
  echo 'Light 常驻块已存在;升级请手动替换 START/END 之间旧块。'
fi
```

### A3. 注册 SessionStart hook 到全局 `settings.json`(**手动合并**,勿盲拼 JSON)
`settings.json` 是 JSON 不是 marker 文本,不能像 CLAUDE.md 那样 append。把
`resident/settings.snippet.windows.json`(Win)或 `settings.snippet.unix.json`(Unix)里的
`SessionStart` 数组**手动并进** `~/.claude/settings.json` 的 `hooks` 段(已有 `hooks` 就并数组)。

> **技术约束(已核实)**:① 故意写**绝对路径**而非 `${CLAUDE_PROJECT_DIR}`——后者指当前项目,
> 而 hook 装在全局克隆里,必须不随项目变;脚本内部用 `Path(__file__)` 自定位 `../scripts/passport.py`。
> ② Windows 用 `%USERPROFILE%`、Unix 用 `$HOME`(stock Windows shell 不展开 `$HOME`)。
> ③ SessionStart **不可阻断会话**,hook 失败仅 debug log 记一行;**JSON 仅在 exit 0 被解析**;
> `additionalContext` 上限 **10000 字**(脚本自带截断保护)。④ `matcher` 设 `startup|resume|clear|compact`,
> 故 resume / compaction 后会**重新注入**续跑状态(SessionStart on resume 会重跑,正合"续跑自动汇报")。

---

## B. Codex

### B1. 链接技能
把 `skills/` 下各技能放进 Codex 的 skills 目录(Codex 2025-12 起原生消费 SKILL.md;
具体路径见你的 Codex 版本文档,常见为 `~/.codex/skills/` 或项目 `.agents/skills/`)。

### B2. 注入常驻纪律到 `AGENTS.md`(幂等,marker 守卫)
```bash
touch ~/.codex/AGENTS.md   # 或项目根 AGENTS.md
if ! grep -q '<!-- LIGHT-SKILLS-START -->' ~/.codex/AGENTS.md; then
  cat <LIGHT_DIR>/skills/light-orchestrator/resident/AGENTS.snippet.md >> ~/.codex/AGENTS.md
fi
```
> Codex 无 session-start hook → 常驻全靠这份 `AGENTS.md`(模型读)。续跑状态在会话开头**跑确定性命令
> `python light-memory-pm/scripts/pm.py resume --dir <项目根>`**(与 CC hook 同一份 `resume_report.py`;
> `AGENTS.snippet.md` 已写明该步)。

---

## C. OpenCode

### C1. 链接技能(自动发现,向上走到 git 根)
放进任一被 OpenCode 扫描的目录即可,无需注册:
- 项目级:`.opencode/skills/<name>/SKILL.md`(也兼容 `.claude/skills/`、`.agents/skills/`)
- 全局:`~/.config/opencode/skills/<name>/SKILL.md`(也兼容 `~/.claude/skills/`)

> 若你已按 A1 链到 `~/.claude/skills/`,OpenCode 可直接复用(兼容 Claude Code 约定),无需重链。
> 可选 `opencode.json` 做权限控制:`{"permission": {"skill": {"*": "allow"}}}`。

### C2. 注入常驻纪律到 `AGENTS.md`(幂等,marker 守卫)
```bash
mkdir -p ~/.config/opencode && touch ~/.config/opencode/AGENTS.md
if ! grep -q '<!-- LIGHT-SKILLS-START -->' ~/.config/opencode/AGENTS.md; then
  cat <LIGHT_DIR>/skills/light-orchestrator/resident/AGENTS.snippet.md >> ~/.config/opencode/AGENTS.md
fi
```
> OpenCode **无 session-start hook**,技能只能经内置 `skill` 工具按需加载 → 常驻全靠这份 `AGENTS.md`
> (全局 `~/.config/opencode/AGENTS.md`;OpenCode 也兼容 `~/.claude/CLAUDE.md` 兜底)。续跑状态同 Codex:
> 会话开头跑 `pm.py resume --dir <项目根>`(与 CC hook 同一份)。

---

## 验证

```bash
# 1) hook 脚本自测(应 ALL PASS、exit 0;含"读台账出续跑汇报"用例)
set PYTHONUTF8=1   # Windows
python <LIGHT_DIR>/skills/light-orchestrator/resident/session_start_resident.py --selftest

# 1b) 续跑命令自测 + 跨 harness 通用性(应 ALL PASS;含"与 hook 输出逐字一致"防漂移用例)
python <LIGHT_DIR>/skills/light-memory-pm/scripts/resume_report.py --selftest
# 任意 harness 会话开头跑这条,出"项目/阶段/卡门/需重验/下一步"(指向你某个有 .light/ 的项目):
python <LIGHT_DIR>/skills/light-memory-pm/scripts/pm.py resume --dir <你的项目>

# 2) (仅 Claude Code)按 harness 真实契约喂 SessionStart 输入,看真·注入内容:
echo '{"session_id":"t","source":"resume","hook_event_name":"SessionStart","cwd":"<你的项目>"}' \
  | python <LIGHT_DIR>/skills/light-orchestrator/resident/session_start_resident.py
```
3) **(仅 Claude Code)重启 Claude Code、新开/resume 会话**:模型上下文开头应含
   "Light v2 科研技能包 · 常驻纪律";若项目有 `.light/passport.yaml`,还应见"📍 项目续跑状态"。
4) 输入「帮我做文献调研」「这篇该投哪个 venue」「继续,刚断了」,预期路由到对应 `light-*` 技能;
   断点恢复类先走 `light-memory-pm` + `light-orchestrator`,**先读 passport 再继续**。

## 卸载
1. 删 `CLAUDE.md` / `AGENTS.md` 里 `LIGHT-SKILLS-START`/`END` 之间整块。
2. 删 `~/.claude/settings.json` 里手动加的 `SessionStart` hook 项。
3. 删技能链接(**只删链接,勿对源目录 blanket `rm -rf`**;Windows junction 用 `cmd /c rmdir`)。
