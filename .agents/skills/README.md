# 技能目录（skills）

23 个技能逐个填入（每个 = `SKILL.md` + `scripts/*.py`，面向用户的核心脚本带 `--selftest`）。

公开架构：总控 1 + 常驻 5 + 主线 13 + 工程/IP 4；具体实现以本目录下各 `light-*` 技能为准。
**做透优先于做多——一个对话做透一个技能**（先按需联网核验同类 skill/工具/论文/文章，优先读直接同功能与可定位源码；记录 commit、stars、证据范围与不迁移边界；再做专家级深挖、实现、selftest 亲手跑 exit 0、名实对齐）。不要把“10 个”“最强”“父仓热度”当成未核验宣传口径。

本目录是 canonical 技能源。项目级给 Claude Code / Codex / OpenCode 使用时，不要手工复制单个技能；在仓库根目录运行：

```powershell
$env:PYTHONUTF8="1"
python scripts\bootstrap_agent_skills.py --mode auto --force
```

它会生成 `.agents/skills`、`.claude/skills`、`.opencode/skills` 发现入口；copy 模式下修改 `skills/` 后需重新运行 `--force` 刷新。
