# run manifest 使用说明（`light.run_manifest.v3`）

`run_manifest.template.json` 是 stage 6 → result-analysis 的**机读事实入口**；本文件只作人读索引，不替代 JSON。
每个 matrix row × config × seed × attempt 建独立目录，失败 run 也保留。禁止用一张汇总 CSV 代替 raw run。

## 建目录

```text
runs/<matrix-row>/<run-id>/
  manifest.json
  config.json
  environment.json
  stdout.log
  stderr.log
  raw_metrics.jsonl
  predictions.csv
  test_evidence.json
  guardrails.json       # research-plan 要求 guardrail/counter-metric 时必须
  failure.json          # status=failed 时必须
```

从 `run_manifest.template.json` 复制 `manifest.json`，填**具体值**：

- identity：稳定 `run_id`、冻结的 `matrix_row`、`status`；
- time：`started_at/ended_at` 必须是带时区 ISO-8601、已经发生，且 `ended_at >= started_at`；
- termination：自然退出、timeout、max iterations、用户取消、错误或抢占；达到轮数上限
  只能是 `aborted`，不能冒充 completed；
- completion：与 termination 分开；只有真实 oracle 和证据 artifact 齐全才写 `PASS`，
  未评价写 `NOT_EVALUATED`；
- seed：`fixed_repro` 或 `randomness_estimation` 及整数值，二者不可混；
- command：argv 数组，不存不可重放的 shell 字符串；只记环境变量/key 名，
  `--api-key/--token/--password/--secret` 及其值不得落 manifest；
- config/environment/code/input：路径、git commit/dirty、source revision 与 SHA256；
- logs/tests/artifacts：stdout、stderr、测试证据、raw metric、patient/entity prediction、guardrail evidence；每个文件都带 SHA256；
- failed run：`artifacts.failure` 必填，保存异常、阶段、exit code 与最后 stderr，绝不覆盖成成功 run。

## 校验与同 seed 真复现

```bash
python scripts/run_artifact_check.py --manifest runs/EXP-01/run-a/manifest.json
python scripts/run_artifact_check.py \
  --compare runs/EXP-01/run-a/manifest.json runs/EXP-01/run-b/manifest.json
```

比较模式先要求 matrix/config/env/code/input/固定 seed 身份相同，再比较 manifest 中
`reproducibility.compare_artifacts` 指定的 artifacts；模板默认比较 `predictions` 和 `raw_metrics`。hash 不同即 exit 1，差异作为
failure evidence 留给 stage 6 修复。

## 人读索引（可选）

如需 `RUNS.md`，每行只列：

| run_id | matrix row | seed(role/value) | status | manifest |
|---|---|---|---|---|
| `wdbc-exp01-s20260305-a` | `EXP-01` | `fixed_repro/20260305` | completed | `runs/.../manifest.json` |

统计汇总、比较与 claim 属于 result-analysis；experiment-coding 只交可重算的 raw evidence。
