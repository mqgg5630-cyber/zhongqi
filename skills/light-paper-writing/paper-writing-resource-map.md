# paper-writing 真实资源工作流

> 这是作者执行地图，不是网址清单。`docs/competitors/paper-writing.md` 是对标判据 SSOT；`SKILL.md` 是执行与红线；`references/*` 解释方法；`templates/*` 定工件；result-analysis 提供统计证据；citation / figure / research-ethics / consistency / typesetting 各管自己的门。本页只回答：真实作者从现有材料到可交付稿件，按什么顺序做、产生什么、何时停。

## 六步闭环

### 1. 冻结任务、venue 与 claim / argument plan

输入：

- research-plan 的问题、假设、计划锁与 post-hoc 记录；
- result-analysis 的分析报告、`claim_evidence_table.md`、`evidence_strength.json`、逐 claim `light.result_card.v1`（含 `guardrail_analysis`）；
- 目标 venue 当年的官方 author instructions、review form、checklist；
- 项目内部 contribution registry、术语表、限制与失败实验。

动作：

1. 写一句研究问题、一句 audience、一到三条核心贡献；区分 planned 与 post-hoc。
2. 给每条 claim 定 `claim_type`、warrant、boundary、section coverage。
3. 用 `templates/claim_argument_plan.json` 建 `light.paper_claims.v1`：顶层写当前草稿 UTF-8 `draft_sha256`；`checked_at/captured_at/updated_at` 只写真实已发生时间；每条 `claim_id/text/locator` 逐条绑定自己的 `evidence_claim_ids/source_locators`，并为实证 claim 绑定 result-card 的 locator/SHA-256/decision/language_strength/guardrail_summary。
4. 用 `templates/argument-outline.example.json` 的结构建真实 argument outline：每条 claim 填 `claim_type`，每段填 `role`，并给 causal/mechanism/null/post-hoc claim 写清设计、测试、精度/功效或披露。
5. 给每条 claim 登记 citation candidate、figure requirement、limitation；这里只交需求，不替下游造引用或画图。
6. 把 venue 每条要求映射到真实稿件 span 或明确 `N/A + reason`，不做空白 checklist。

产出：approved claim/argument plan、venue requirement map、section coverage 表。

### 2. 收齐证据与材料

最低输入：

- `claim_evidence_table.md`：读统计字段与比较定义；
- `evidence_strength.json`：只代表统计强度，不等于 full provenance / full GRADE；
- `light.result_card.v1`：写作前的结论卡，提供 `decision=CLAIM_READY`、`language.strength` 与 `guardrail_analysis.checks[].claim_impact`；它必须以 locator+SHA-256 进入 claim plan；
- analysis report + plan audit：读 negative/null/contradictory findings、变更与设计边界；
- raw result hash、run manifest、config/commit：上游有则保留；没有则如实标缺，不补造。

规则：

- claim 的来源至少落到 `artifact path + claim_id/field`；run/commit/hash 能取到再加。
- `source_artifacts.path`、`draft_path`、`source_locators` 必须是公开交接包内相对路径/锚点；不要写本机绝对路径、`..` 越界路径或模板占位符。
- `sha256` 只在真实算过时填写 64 位十六进制值；未知就留空，不能写 `unknown`、`{{...}}` 或假 hash。
- `source_locators` 缺失只产生 traceability warn，不冒充“已核”。
- 无证据留 `GAP`、删除强断言、或请求 8→7 / 8→6；语言流畅度不是补数值、引用、机制或实验设置的许可证。

产出：可追溯 material packet，包含 planned、negative、failed、limitation，不只收“好看结果”。

### 3. 按 section contract 写

建议顺序：Results → Methods → Discussion → Introduction → Abstract → Conclusion。

| Section | 必须做 | 不得做 |
|---|---|---|
| Abstract | 问题、方法、主要结果、边界；只回收已支持 claim | 新增正文没有的贡献；无证据 SOTA |
| Introduction | territory → gap → insight → contribution；点明 delta | 边写边发明贡献；把 citation candidate 当真引用 |
| Methods | 写实际执行的设计、数据、配置、统计单位 | 补造没运行的步骤/超参 |
| Results | 观察、数值、不确定性与 null/negative result | 把相关、SHAP、事后切片直接写成因果/机制 |
| Discussion | 解释、替代解释、局限、外推边界 | 把推测装成结果；删除不利结果求“像顶会” |
| Conclusion | 只回收已支持 claim，强度与数字对齐 | 引入新 claim |

每完成一节：

1. 把实际句子精确回填 claim plan 的 `text` 与 `locator`；
2. 重算并更新 `draft_sha256`，防止旧 claim map 在修稿后继续通过；
3. 更新 section coverage 与 paragraph `role`；
4. 检查 Results/Discussion 分工与 claim boundary：Results 不写推测/解释，Discussion 不把推测装成结果；
5. 修改 claim 时同步更新所有出现位置，不让 abstract/introduction/conclusion 漂移。

### 4. 审稿人视角 + 作者声音循环

先做 reverse outline，再做四维自审：

- soundness：claim 是否有自己的 evidence / argument；替代解释是否处理；
- significance：对谁重要，贡献是否窄而可守；
- originality：与最相近工作 delta 是否具体；
- clarity：每段有唯一作用，术语稳定，图表/引用需求清楚。

Reverse outline 每段记录：`段落作用 | claim_id | evidence/reasoning locator | 与上一段关系`。无法映射到 section thesis 的段落移动、合并或删除。

最后才做机械润色：

- `style_fingerprint.py` 是表层统计画像，不是作者声音的全部；
- `mechanical_check.py` / `polish.py` 不得改变科学内容；
- `polish.py` 默认离线，`--online` 仅显式 opt-in；未授权稿件/敏感数据不发公共端点。

### 5. 机读门与 provenance

```bash
python scripts/claim_binding.py --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json --as-of 2026-07-05
python scripts/claim_evidence_gate.py --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json --report claim_findings.json
python scripts/draft_lint.py draft.md --final --evidence evidence_strength.json --claim-map claim_plan.json
python scripts/contribution_consistency.py --in draft.md --json
python scripts/mechanical_check.py --file draft.md --evidence-map evidence_strength.json
```

真相边界：

- `claim_evidence_gate` 的 canonical 判定来自逐 claim 精确绑定；整份 evidence 的最高档只可显示，不参与兜底。
- `result_card_guardrail` 要求实证 claim 消费固定版本 result card；`decision != CLAIM_READY`、guardrail `FAIL/UNKNOWN` 或 WARN 未写限制会阻断写作。
- `draft_lint --claim-map` 复用同一绑定；不带 claim map 的旧式全文×每档扫描仅为启发式，会误报。
- `mechanical_check --evidence-map` 是 sentence↔evidence text 的语义启发式，可提示 under/over-claim，不能替代 canonical claim map。
- `contribution_consistency` 区分 NUMBER / STRENGTH / COVERAGE drift，但中英混写、同义改写仍会漏/误报；跨材料归 consistency。
- lint 通过不证明逻辑充分、创新成立、证据真实或录用概率。

产出：`light.findings.v1`（producer=`paper-writing`）、lint 报告、claim/section coverage 与变更记录。

### 6. 交总控与下游

- `claim_evidence` critical → `run_checkpoint --stage 8` exit 1。
- 缺分析证据 → `reroute --stage 8` 建议 8→7；实验根本没产出 → 用户可改判 8→6。回炉是用户决策点，不自动执行。
- citation candidates + locator → citation 真核，不把候选当已核。
- figure requirements + claim/evidence ID → figure，不顺手画统计图。
- 稿件 + evidence + claim plan → research-ethics 交付红线复核。
- claim/metric + provenance candidates → consistency 人工确认后登记。
- 稿件结构与 venue template → typesetting 编译。
- 任一科学 claim 或证据变化后，全量重跑，不只跑改动段。

## 资源访问分级

### 本地 / 无 key

- 本技能脚本、templates、references；
- result-analysis 工件、git、run manifest、稿件 Markdown/LaTeX；
- 本地 venue 模板副本（记录版本、取得日期、官方 URL）；
- 正则、文本统计与本地 semantic similarity。

### 公开权威 / 无 key

- 目标 venue 当前 author guidelines、review form、checklist；
- 适用时的 EQUATOR reporting guideline；
- CRediT、COPE、ICMJE、数据/代码可用性与 AI disclosure 官方要求；
- 公开优秀论文与 OpenReview reviews/rebuttals：只学结构，不复制措辞；
- 公共数据集与公开复现实验仓库。

### 登录 / 付费 / 闭源

Overleaf、Writefull、Paperpal、Grammarly、Trinka、投稿系统只能列为可选。它们不能成为任务完成前提；无账号时走本地与公开资源。不得上传未授权稿件或敏感数据，也不得伪造“已检查”。

### 项目内部（最重要）

approved claim plan、evidence strength/table/report、method/config/run/commit、contribution/terminology registry、limitations、failed/negative results、owner、更新时间与变更记录。公开指南不能替代这些内部事实。

## 六条硬约束

1. 一条 strong evidence 不给所有 claim 兜底。
2. 不凭流畅度补数字、引用、机制、实验设置或统计结论。
3. 不把 q≥阈值写成“证明没有效应”，不把相关/SHAP/事后切片写成因果。
4. 不为“更像顶会”删除 null、negative、contradictory findings 或限制。
5. venue checklist 每条定位到真实 span，或明确 N/A + reason。
6. lint 通过不等于逻辑、创新、证据真伪或录用率已被证明。
