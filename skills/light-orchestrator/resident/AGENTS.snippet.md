<!-- LIGHT-SKILLS-START -->
## Light v2 科研技能包(常驻纪律 + 路由)—— Codex / OpenCode

Light 把科研全流程拆成 **23 个技能**(总控 1 + 常驻 5 + 主线 13 + 工程/IP 4)。Codex(2025-12 起)
与 OpenCode 均**原生消费 SKILL.md**;技能放在各自的 skills 目录即被自动发现(OpenCode:
`.opencode/skills/` 或 `~/.config/opencode/skills/`,也兼容 `.claude/skills/`、`.agents/skills/`)。
本块补两件 SKILL description 兜不住的事:①声明常驻纪律;②**协作式半自主**(总控会停下问你)。

> ⚠ **重要差异(诚实)**:Codex / OpenCode **没有 Claude Code 那种 SessionStart hook**——技能只能
> 按需加载,**不会**在会话开头自动注入续跑状态。**补法 = 在会话开头(或"继续/接手/刚断了"时)先跑
> 一条确定性命令**,搞清「上次断哪 / 卡哪门 / 哪些产物陈旧 / 下一步」**再开口**,别凭记忆猜进度:
>
> ```bash
> python light-memory-pm/scripts/pm.py resume --dir <项目根>   # 项目/阶段/卡门/需重验/下一步,确定性
> ```
>
> 这条命令与 Claude Code SessionStart hook **跑的是同一份实现**(`resume_report.py` 单一真相源),
> 故三 harness 出**同一份**续跑汇报——只是 CC 由 hook **自动**调、Codex/OpenCode 靠本约定让你
> **在会话开头主动**调。无 `.light/` 的非科研任务忽略本步。

### 总控 = 协作式半自主(会停下问你)
**light-orchestrator**:跨多阶段大任务 或「继续 / 刚断了 / 接手」断点恢复时启动;逐阶段卡机读
检查点、维护 `.light/passport.yaml` 台账。它**不黑箱自动驾驶**——大决策(选方向 / 定 idea / 选 venue /
回炉)一律**停下问用户**,给「推荐 + 理由 + 备选」。**单阶段轻任务不启动总控。**

### 5 个常驻技能(相关任务默认生效)
- **light-consistency**:术语 / 指标 / 创新点跨材料一致;定义一改回扫所有产物。
- **light-research-ethics**:诚实底线——不臆造文献 / 数据 / DOI / 端点;区分「已验证」与「推测」。
- **light-memory-pm**:项目台账(`.light/`)、跨会话记忆。
- **light-file-reading**:涉及读文件时自动触发。
- **light-project-structure**:项目文件夹结构整理。
- (self-review 已并入总控「收尾 self-check」,每次对外输出前过一遍。)

### 科研主线(总控按 DAG 调度)
文献 → `light-literature-search`;数据 → `light-data-engineering`;创新点 →
`light-idea-generation` ⇄ `light-idea-critique`;方案 → `light-research-plan`;实验 →
`light-experiment-coding`;分析 → `light-result-analysis`;写作 → `light-paper-writing`;
图 → `light-figure`;引用 → `light-citation`;排版 → `light-typesetting`;投稿 →
`light-venue-matching`;审稿/rebuttal → `light-review-rebuttal`。工程/IP(按需,不进科研 DAG):
`light-system-design` / `light-frontend-design` / `light-patent-disclosure` /
`light-software-copyright`。

### 红线(NON-NEGOTIABLE)
不替用户定方向 / idea / 结论 / venue;不自称「门过了」(诚信门必须机读 exit code + 用户确认);
不编造文献 / 数据 / DOI / 端点(写「待核查 / GAP」);不把判断当事实(新颖性 / 显著性 → 降级
「建议核实」);不静默回炉、不静默带病冲过失败门;不覆盖未提交改动。论文图 / 数据图**程序化
生成,绝不 AI 生图**。确认点用 `light-orchestrator/scripts/run_checkpoint.py` 聚合 findings 做机读
闸门,Critical fail 默认阻断(exit 1),不靠「口头说跑了」。
<!-- LIGHT-SKILLS-END -->
