# Claim / Argument Plan 契约

这份契约解决一个具体问题：`evidence_strength.json` 是多条统计 claim 的集合，不能拿整份文件的最高证据档给全文所有句子兜底。写 prose 前先建立 `light.paper_claims.v1`，让每条 claim 指向自己的 evidence ID 与真实来源。

模板：`templates/claim_argument_plan.json`。机检：`scripts/claim_binding.py`；canonical stage-8 producer：`scripts/claim_evidence_gate.py --claim-map ...`。

## 最小字段

每条 `claims[]` 必须有：

- 顶层 `draft_sha256`：当前草稿全文按 UTF-8 计算的 SHA-256。修稿后必须重算；不允许 `UNKNOWN`/占位符。旧 hash 会被 `claim_binding.py` 当成绑定失效处理。
- `venue.checked_at`、`source_artifacts[].captured_at`、`claims[].updated_at`：只写真实已发生的 ISO 日期/时间；未来时间或模板占位符会被视作伪 provenance。
- `draft_path`、`source_artifacts[].path`、`source_locators[]`：使用公开交接包内相对路径/锚点；不允许本机绝对路径、家目录、UNC 路径或 `..` 越界路径。
- `claim_id`：论文内部稳定 ID，不复用。
- `text`：从当前草稿精确复制的一句，且在草稿中只出现一次。修稿后同步更新，避免陈旧绑定。
- `locator`：`draft.md:L12`、section/paragraph anchor 等可复核落点。
- `evidence_claim_ids`：只填 `evidence_strength.json` 中真实存在的 `claim_id`。没有证据就留空并标 `status=gap/speculative`，不要借别的 claim。
- `source_locators`：至少保留 evidence artifact 路径 + claim ID/字段；若上游有 run manifest、commit、hash，再放入 `source_artifacts`。`sha256` 只填真实 64 位十六进制值；上游没给完整 provenance 时如实留空对应字段，不伪造。
- `result_card`：所有绑定 `evidence_claim_ids` 的实证 claim（除明确 `METHOD/POSITIONING/LIMITATION/SPECULATION`）必须携带 result-analysis 的 `light.result_card.v1` 摘要：`locator`、`sha256`、`decision`、`language_strength`、`guardrail_summary.required/status/claim_impact/evidence_locator`。这不是重复 `evidence_strength.json`，而是防止 `guardrail_analysis`、`CLAIM_READY` 与 `claim_impact` 在写论文时丢失。

建议同时填：

- `sections`：该 claim 应覆盖 abstract/introduction/results/discussion/conclusion 的哪些位置。
- `claim_type`：建议与 `argument_contract.py` 对齐：`RESULT` / `NULL_RESULT` / `MECHANISM` / `CAUSAL` / `SPECULATION` / `LIMITATION` / `METHOD` / `POSITIONING`。
- `citation_candidates`：只交候选与 locator，真实性归 citation。
- `figure_requirements`：只交 claim、数据与证据要求，绘图归 figure。
- `limitations`：该 claim 的样本、数据域、设计或外推边界。
- `post_hoc`：看结果后新提炼的贡献必须为 `true`，不得伪装成预先计划。
- `owner` / `updated_at`：多人协作与变更追踪。

## 写作顺序

1. 冻结 venue、研究问题与一到三条核心贡献。
2. 读取 result-analysis 的 `claim_evidence_table.md`、`evidence_strength.json`、分析报告、计划审计与 run/config locator。
3. 建 claim/argument plan：先定 claim、warrant、boundary、section coverage，再写 prose；写入当前 draft 的 `draft_sha256`。
4. 每写完一节，把实际句子精确回填到 `text`，不要只保留抽象摘要。
5. 跑：

```bash
python scripts/claim_binding.py --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json
python scripts/claim_evidence_gate.py --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json --report claim_findings.json
python scripts/draft_lint.py draft.md --final --evidence evidence_strength.json --claim-map claim_plan.json
```

## 判定

- 强断言未登记、绑定 ID 不存在、或只绑定 `none` evidence：`claim_evidence` critical。
- `draft_sha256` 缺失、不是 64 位 SHA-256、或与当前草稿不一致：`claim_evidence` critical。修稿后必须同步 claim plan。
- 未来 `checked_at/captured_at/updated_at`、占位符日期、占位符 path、绝对路径/`..` 越界 locator、假 SHA-256：`claim_evidence` critical。机器台账不能预填未来、泄漏私人路径或伪造来源。
- 措辞强于该 claim 自己的 weak/moderate evidence：`overclaim` warn；终稿 `draft_lint` 仍要求修。
- `locator` / `source_locators` 缺失：`claim_traceability` warn，不扩大 stage-8 blocking 面，但交付前应补真实指针。
- 实证 claim 缺 `result_card`、result-card SHA/locator 不可交接、`decision != CLAIM_READY`、`guardrail status=FAIL/UNKNOWN`，或 `status=WARN` 但 claim 没有 `limitations`：`result_card_guardrail` critical。
- `guardrail status=WARN` 且已写 `limitations`：允许限制性推进，但 `result_card_guardrail` 会给 warn，提醒摘要/结果/结论必须继承 `claim_impact`，并在 Discussion/Limitations 呼应。
- `claim_binding` 证明的是“绑定存在、强度相容、result-card/guardrail 交接未断”，不是证据真实、逻辑充分、创新成立或会被录用。

## Reverse outline

初稿完成后逐段填三列：`段落作用`、`服务 claim_id`、`证据/推理 locator`。`argument_contract.py` 现在会要求段落 `role` 与章节职责匹配：
Results 只报告结果/过渡；解释、替代解释、推测和限制放到 Discussion/Conclusion。无法服务 section thesis 或任何 claim 的段落，移动、合并或删除；同一 claim 若只在摘要出现而 Results/Conclusion 无对应，回到贡献覆盖检查。这个动作以人判为主，不把关键词匹配吹成论证证明。
