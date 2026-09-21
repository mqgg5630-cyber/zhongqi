# 端到端范例：strong A 不得兜底 unsupported B

完整真实运行见 `docs/e2e/paper-writing-round2.md`。本页只保留最小可复制模式。

## 1. 上游证据

`evidence_strength.json` 同时含：

- evidence A：strong；
- evidence B：none。

这很常见：同一论文的主比较显著，另一个模型差异不显著。不能取整份文件最高档 strong 给全文。每条实证 claim 还要携带对应
`light.result_card.v1` 摘要，因为 result card 才记录 `CLAIM_READY`、`language.strength` 与 guardrail/counter-metric 的
`claim_impact`。

## 2. 先建 claim plan

从 `templates/claim_argument_plan.json` 复制，给每个实际草稿句子填：

```json
{
  "schema": "light.paper_claims.v1",
  "claims": [
    {
      "claim_id": "C-A-results",
      "text": "Method A demonstrates a reliable improvement over the prior baseline.",
      "locator": "draft.md:Results:p1",
      "evidence_claim_ids": ["metric:prior_vs_A:paired"],
      "source_locators": [
        "analysis/evidence_strength.json#metric:prior_vs_A:paired",
        "analysis/claim_evidence_table.md#row-1"
      ],
      "result_card": {
        "claim_id": "metric:prior_vs_A:paired",
        "locator": "analysis/result-card-prior-vs-A.json",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "decision": "CLAIM_READY",
        "language_strength": "IMPROVES",
        "guardrail_summary": {
          "required": true,
          "status": "PASS",
          "claim_impact": "允许主 claim，但需保留 declared datasets 范围。",
          "evidence_locator": "analysis/guardrails.json#metric:prior_vs_A:paired"
        }
      },
      "status": "supported",
      "post_hoc": false
    }
  ]
}
```

若草稿另写 “Method A significantly outperforms B and is SOTA”，但没有独立 claim entry，门会把它判为 `claim_binding.unregistered_assertion`；A 的 strong evidence 不会遮住它。

## 3. 首跑与 checkpoint

```bash
python scripts/claim_binding.py \
  --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json
python scripts/claim_evidence_gate.py \
  --draft draft.md --evidence evidence_strength.json --claim-map claim_plan.json \
  --report claim_findings.json
python ../light-orchestrator/scripts/run_checkpoint.py \
  --file .light/passport.yaml --stage 8 --findings claim_findings.json --write
```

未登记强断言、未知 evidence ID、只绑定 `none` evidence 的强断言，或缺 result-card/guardrail handoff → critical → checkpoint exit 1。

## 4. 修稿

真实结果是 none 时，不补造实验或数字。删除 SOTA/优于断言，改为：

> No significant difference was observed between A and B in this analysis.

再给这句绑定 evidence B，并在 limitations 写明“failure to reject is not proof of equivalence”。

## 5. 复跑与回炉

修后全量重跑；目标是 coverage error、result-card guardrail error 与 overclaim 消失，checkpoint exit 0。

若核心 claim 真缺分析，reroute 默认建议 8→7；若实验根本没产出，用户可改判 8→6。`ROUTES[8]` 不替用户自动判断这两种根因。

> 边界：绑定存在不等于证据真实、逻辑充分、创新成立或会被录用。paper-writing 只做写作期门；citation/figure/research-ethics/consistency/typesetting 各自继续接棒。
