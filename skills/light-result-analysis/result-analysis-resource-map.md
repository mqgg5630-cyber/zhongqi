# result-analysis 真实用户资源地图

> 这是“去哪里拿证据、按什么顺序把它变成可交接结论”的执行地图，不是统计教材。
>
> - 竞品判据与可证伪笔记：[`docs/competitors/result-analysis.md`](../../docs/competitors/result-analysis.md)
> - 执行红线与脚本路由：[`SKILL.md`](SKILL.md)
> - 方法/工具一手说明：[`references.md`](references.md)
> - 最终人读报告结构：[`assets/result_analysis_report_template.md`](assets/result_analysis_report_template.md)
> - 下游各自的方法：paper-writing / research-ethics / consistency / figure 的 SKILL 与 references
>
> 本页不重复上述内容；只负责把**分析计划→原始运行→设计感知统计→稳健性→claim/provenance→交总控**
> 串成闭环。

## 先选工作模式

| 模式 | 何时用 | 允许的结论 |
|---|---|---|
| confirmatory | 结果前已有 hypothesis/estimand/primary metric/family/exclusion | 按冻结计划检验；变更必须另标 |
| exploratory | 结果已看过才提出切片/检验/假设 | 生成候选规律，不得回填成 a-priori |
| sensitivity | 用另一合理处理/检验/语言核结论是否依赖选择 | 只能说“对该选择稳健/敏感”，不是新主假设 |
| descriptive-only | 只有汇总均值、统计单位不独立或复杂设计暂不能建模 | 报分布/覆盖/限制，不做确认性显著结论 |

## 六步闭环

### 1. 冻结问题与分析计划

从 research-plan / experiment-coding 取：

- hypothesis / estimand（比较谁、对谁、什么结果、什么时间窗）；
- primary / secondary metric；
- `unit_of_analysis`：participant / sample / seed / dataset / cluster，而不是 CSV 行数；
- design：independent / paired / repeated_measures / clustered / hierarchical / nested_cv /
  repeated_holdout / time_series；
- comparison family：一个科学问题下**计划运行的完整比较集合**；
- exclusion / outlier / missingness 规则、停止条件；
- failure-tree / guardrail refs：success/failure/inconclusive 分支、guardrail/counter-metric、kill action 与 claim impact；
- `locked_at` 与 `results_available_at`。

先跑 warn-only 审计：

```powershell
python scripts/analysis_plan_audit.py `
  --spec analysis_audit.json `
  --report analysis_audit_findings.json `
  --json-out analysis_audit_full.json
```

最小结构：

```json
{
  "project": "p1",
  "plan": {
    "status": "frozen",
    "locked_at": "2026-07-01T09:00:00+08:00",
    "results_available_at": "2026-07-01T10:00:00+08:00",
    "hypotheses": ["H1"],
    "primary_metric": "accuracy",
    "unit_of_analysis": "seed",
    "design": "paired",
    "exclusion_rules": ["parse failure only"],
    "comparison_families": [{
      "family_id": "primary-model-comparison",
      "planned_comparisons": 2,
      "reported_comparisons": 2,
      "correction": "bh"
    }]
  },
  "analysis": {"paired_by": "seed", "aggregate_only": false},
  "coverage": {"expected_units": [0, 1], "observed_units": [0, 1]},
  "inputs": [{
    "path": "results/raw.csv",
    "role": "raw_results",
    "sha256": "...",
    "owner": "researcher",
    "captured_at": "2026-07-01T10:00:00+08:00",
    "run_manifest": "run_manifest.json",
    "commit": "abc123"
  }]
}
```

结果后改规则：保留 old/new/time/reason，`declared_as` 只能是 `exploratory` 或 `sensitivity`；
绝不回填成 preregistered。

### 2. 收齐并验证真实结果

优先顺序：

1. 逐 sample / seed / fold / dataset 的 raw CSV/Parquet/JSON；
2. experiment-coding 的 run manifest；
3. guardrail evidence（如 `guardrails.json`）及其 SHA-256、failure-tree refs 和 claim impact；
4. config、数据划分、commit、环境锁、日志；
5. 失败/中断运行与 exclusion log；
6. 最后才是均值汇总表。

为每个输入记录：

| 字段 | 最低要求 |
|---|---|
| path + role | raw_results / run_manifest / config / split / log |
| hash | SHA-256，防止分析后静默换文件 |
| owner + captured_at | 谁确认、何时取得 |
| run locator | run id / seed / fold / commit / config |
| guardrail evidence | guardrail id / status / observed / threshold / claim impact / SHA-256 |
| public source | URL、版本/取得日期、字段、license |
| coverage | expected vs observed units；缺失必须解释 |

禁止把“12 个 fold 的均值”当 12 个独立原始样本；禁止把失败 seed 从表里删掉后仍写 coverage=100%。

### 3. 按设计选分析，不按显著性选

简单设计：

```powershell
# independent
python scripts/analyze_results.py results.csv --group method --metric accuracy f1 `
  --emit-claim-table --emit-evidence --outdir analysis

# paired：claim/evidence 只采用 paired comparisons；独立结果仅留 advisory
python scripts/analyze_results.py results.csv --group method --metric accuracy f1 `
  --paired-by seed --emit-claim-table --emit-evidence --outdir analysis
```

配对设计的键必须在每组内唯一；不同方法共享同一 seed/fold/sample 才能配。Round 2 修复后，
`--paired-by` 不再同时产一套“独立样本 duplicate claims”。

复杂设计：

| 设计 | 首选方向 | 当前 Light 行为 |
|---|---|---|
| repeated measures | mixed model / GEE / repeated-measures ANOVA/Friedman | audit warn；简单 paired 仅敏感性 |
| hierarchical/cluster | mixed model / cluster-robust SE / cluster bootstrap | audit warn；不把行当独立 |
| nested/repeated CV | corrected resampled test / dataset-level comparison | audit warn；fold 不作无限独立重复 |
| time series | blocked/rolling evaluation、autocorrelation-aware inference | audit warn；随机独立检验不可终判 |

每条 claim 至少带 effect + CI + p/q + n。多个比较的 family 由**冻结计划**定义，不由脚本替用户
猜；`stat_rigor_gate` 必须一次看到完整 family 的 claims，不能拆成多次调用规避校正。

### 4. 做稳健性、失败与敏感性分析

最低覆盖：

- seed / dataset / split 的方向与方差；
- subgroup/slice 的 coverage 与小 n；
- missingness、异常值、排除规则的 alternate specification；
- leakage / train-val-test gap；
- negative/null/contradictory result；
- 结果后新增分析的 exploratory 标签。

```powershell
python scripts/leakage_overfit_check.py --train train.csv --test test.csv --target y
python scripts/analyze_results.py results.csv --group method --metric accuracy `
  --slice-by subgroup --outdir slice-analysis
```

不要为拿到显著结果自动切换检验、删异常值、改 family。assumption 失败时：

1. 先记录失败；
2. 查冻结计划是否预先规定替代；
3. 没规定则主分析照计划，新增方法作为 sensitivity/exploratory；
4. 并列报告结论是否改变。

### 5. 绑定 claim 与 provenance

标准工件：

- `claim_evidence_table.md`：人读 claim↔test/effect/CI/q/n；
- `evidence_strength.json`：`light.evidence_strength.v1`，下游措辞上限；
- `result_card_report.json` / `result_card_findings.json`：每条 claim 的 target、analysis set、
  missingness、provenance、assumption、family、effect、language 与 decision ledger 机器门；
- `analysis_audit_full.json`：计划/设计/family/coverage/provenance 警告；
- 分析报告：现象→原因→证据→论文意义；
- 可选 claims/metrics **候选**：带 source file/run/commit/locator，交 consistency 人工确认。

重要边界：

- `_shared/evidence_contract` 当前 schema 不保存完整 run provenance；
- `result_card_gate.py` 的 `as_of` 用来裁定分析时间轴：`locked_at`、`results_available_at`、
  `computed_at` 不得来自未来，且 `computed_at` 不得早于 `results_available_at`；
- `decision=REVISION_REQUIRED/UNKNOWN` 是阻断性裁定，不能交给 paper-writing/research-ethics；
- result-analysis **不得直接写** `.light/consistency/*.yaml`；
- consistency 的 canonical authority 必须由 owner 人工确认后，经 memory-pm/项目流程写入；
- SHAP/相关/事后 slice 是关联或探索证据，不能写成因果发现。

### 6. 交总控、停下问人、修后全量重跑

```powershell
python scripts/stat_rigor_gate.py --spec stat_spec.json `
  --report stat_findings.json --evidence-out evidence_strength.json

python ../light-orchestrator/scripts/run_checkpoint.py --stage 7 `
  --findings stat_findings.json analysis_audit_findings.json
```

- critical：多重比较未校正、选择性报告、主假设不支撑、不可复现；
- warn-only：计划锁/复杂设计/family provenance/coverage/input provenance、效应量缺失、过度解读；
- p-hacking：stage 7 内修分析；
- hypothesis unsupported：建议 7→5；
- unreproducible/implementation bug：建议 7→6；
- 回炉与带病推进都是用户决策点，绝不静默。

修复的是分析计划/规格/方法/报告，不是改 raw results 迎合门。修后重跑：

1. analyze；
2. plan/provenance audit；
3. stat rigor gate；
4. checkpoint；
5. paper-writing 或 research-ethics 消费 evidence；
6. figure 只收统计图数据；
7. consistency 只收带 provenance 的候选。

## Python / R 双路径

### 环境检测

```powershell
Rscript --version
$env:RSCRIPT = 'C:\Program Files\R\R-4.6.0\bin\Rscript.exe'
python scripts/r_analysis_crosscheck.py --selftest
```

launcher 按顺序找 `RSCRIPT`、PATH、Windows `C:\Program Files\R\R-*\bin\Rscript.exe`。找不到会
明确返回 R unavailable，不写“R 已支持/已通过”。

### 当前可执行路径

```powershell
python scripts/r_analysis_crosscheck.py `
  --input results.csv --group method --metric accuracy --paired-by seed `
  --out r_accuracy.csv
```

`r_analysis_crosscheck.R` 只用 base R，真算两组 paired t 或 independent Welch t，输出 p、effect、
CI、n。它是**交叉核验/敏感性路径**，不是 mixed model 引擎。

### 可选包与诚实降级

| R 资源 | 用途 | 必需？ | 缺失时 |
|---|---|---:|---|
| base `stats` | t/Wilcoxon/ANOVA/模型基础 | 是 | R 路径不可用 |
| `boot` | bootstrap | 否 | Python bootstrap 或 base 实现并标注 |
| `broom` | tidy model output | 否 | base summary/CSV |
| `effectsize` | 多类 effect size | 否 | Python 现有 d/dz；注明缺项 |
| `rstatix` | 便捷检验 | 否 | base/SciPy |
| `emmeans` | marginal means/contrasts | 复杂模型时有价值 | 不做该终判 |
| `lme4` | mixed effects | repeated/hierarchical 时有价值 | audit warn，转人工方法设计 |

2026-07-01 本机实测：R 4.6.0 全路径可用，base R 与 `boot` 可用；`broom/effectsize/rstatix/
emmeans/lme4` 不可用。不得把文档列名写成“均已安装”。

## 资源访问分级

### 本地 / 无 key

- 本技能 9 个 Python 脚本 + 1 个 R 脚本（以目录实时清单为准）；
- `_shared/evidence_contract` / findings / gate runner；
- pandas / SciPy / statsmodels / scikit-learn（按环境检测）；
- base R；可选 R 包逐项 `requireNamespace()`；
- git、config、run manifest、raw CSV/Parquet/JSON、split、日志。

### 公开权威 / 无 key

- ASA p-value statement；
- NIST/SEMATECH statistical handbook；
- Cochrane Handbook / GRADE；
- EQUATOR 对应研究设计报告清单；
- UCI / OpenML /公开 benchmark 与复现仓库。

公开数据必须记 URL、取得日期、字段、license 与 hash；网页“能下载”不等于统计单位支持当前检验。

### 登录 / 付费 / 闭源（仅备选）

SPSS、Stata、JMP、Prism、托管 W&B/MLflow、受限数据仓库。它们不得成为完成任务前提；无账号时使用
本地文件与开源路径，不伪造“已核”。

### 项目内部（最重要）

preregistration/analysis plan、run manifest、逐 seed/fold/sample 结果、日志、config、commit、split、
已确认 primary/secondary metric、exclusion/stopping rule 与 change log。每项带 owner、绝对时间与
provenance。

## 五条硬约束

1. 不把汇总均值或 fold 当无限独立样本。
2. 不为显著性自动换检验、删异常值、改 comparison family。
3. q≥阈值只表示“未见足够证据”，不是“证明没有效应”；要证明近似等效需 equivalence/
   non-inferiority 设计。
4. 不把 SHAP、相关或事后 slice 写成因果。
5. 文件缺失、解析失败、coverage/provenance 缺口时，不得宣称分析完整或 evidence strong。
