<!-- LIGHT-SKILLS-START -->
## Light v2 科研技能包(常驻纪律 + 路由)

Light 把科研全流程拆成 **23 个技能**(总控 1 + 常驻 5 + 主线 13 + 工程/IP 4),已链接到 `~/.claude/skills/`,
Claude Code 按各 SKILL.md 的 `name`/`description` 自动发现并触发。本块补 description 兜不住的两件事:
①声明**哪些技能常驻**;②**协作式半自主**纪律(总控会停下问你)。详见 `light-orchestrator/SKILL.md`。

### 总控 = 协作式半自主(会停下问你)
**light-orchestrator**:跨多阶段大任务 或「继续·刚断了·接手·恢复上下文」断点恢复时**自动启动**;
逐阶段卡机读检查点、维护 `.light/passport.yaml` 台账。它**不黑箱自动驾驶**——大决策(选方向 /
定 idea / 选 venue / 回炉)一律**停下问你**,给「推荐 + 理由 + 备选」。**单阶段轻任务不启动总控。**

> 若装了 SessionStart hook(见 `resident/INSTALL.md`),会话开头会**自动注入**这份纪律 +
> 读 `.light/passport.yaml` 出的「上次断哪 / 卡哪门 / 下一步」续跑汇报。本 CLAUDE.md 块是其
> 模型读侧的双保险(开头必载),hook 是 harness 强制侧(compaction / resume 后仍注入)。
> **没装 hook**(或想手动刷新)时:在"继续/接手/刚断了"开头跑
> `python light-memory-pm/scripts/pm.py resume --dir <项目根>`——与 hook **同一份**续跑汇报
> (`resume_report.py` 单一真相源),故"完美续上"不再"只有装了 hook 才有"。

### 5 个常驻技能(无需 /调用,相关任务默认生效)
- **light-consistency**:术语 / 指标 / 创新点跨材料一致;定义一改回扫所有产物。
- **light-research-ethics**:诚实底线——不臆造文献 / 数据 / DOI / 端点;区分「已验证」与「推测」。
- **light-memory-pm**:项目台账(`.light/`:passport / 决策日志 / 版本史)、跨会话记忆。
- **light-file-reading**:涉及读文件时自动触发。
- **light-project-structure**:项目文件夹结构整理。
- (self-review 已并入总控「收尾 self-check」,每次对外输出前过一遍。)

### 科研主线(总控按 DAG 调度)
文献 → `light-literature-search`;数据 → `light-data-engineering`;创新点 →
`light-idea-generation` ⇄ `light-idea-critique`(成环);方案 → `light-research-plan`;
实验 → `light-experiment-coding`;分析 → `light-result-analysis`;写作 → `light-paper-writing`;
图 → `light-figure`;引用 → `light-citation`;排版 → `light-typesetting`;
投稿 → `light-venue-matching`;审稿/rebuttal → `light-review-rebuttal`。
工程/IP(按需,不进科研 DAG):`light-system-design` / `light-frontend-design` /
`light-patent-disclosure` / `light-software-copyright`。

### 易混边界
- 「继续 / 刚断了 / 接手」指向断点恢复 → `light-memory-pm` + `light-orchestrator`,先读 passport/git/CI 再继续。
- 「继续写 / 润色当前段落」→ 单技能 `light-paper-writing`,**不启动**总控。

### 红线(NON-NEGOTIABLE)
不替用户定方向 / idea / 结论 / venue;不自称「门过了」(诚信门必须机读 exit code + 用户确认);
不编造文献 / 数据 / DOI / 端点(写「待核查 / GAP」);不把判断当事实(新颖性 / 显著性 → 降级「建议核实」);
不静默回炉、不静默带病冲过失败门;不覆盖未提交改动。论文图 / 数据图**程序化生成,绝不 AI 生图**。
确认点用 `light-orchestrator/scripts/run_checkpoint.py` 聚合 findings 做机读闸门,Critical fail 默认阻断(exit 1)。
<!-- LIGHT-SKILLS-END -->
