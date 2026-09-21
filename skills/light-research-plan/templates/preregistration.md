# 预注册包：{{研究名称}}

> 在看 confirmatory outcome 前填写并冻结。若已经看过 outcome，把受影响分析标为
> **exploratory**；补时间戳不能把它洗回 confirmatory。

## 0. 身份、版本与 provenance

| 字段 | 值 |
|---|---|
| plan version | {{v1}} |
| frozen at（含时区） | {{YYYY-MM-DDTHH:MM:SS+08:00}} |
| git commit | {{commit}} |
| 本文件 SHA256 | {{冻结后计算}} |
| data provider / id | {{provider/id}} |
| source URL + revision/version | {{固定 URL + revision}} |
| raw / cleaned SHA256 | {{hashes}} |
| split scheme / seed / group/time key | {{固定划分}} |
| registry | {{OSF / AsPredicted / trial registry / PROSPERO / local-only}} |
| registration status | {{DRAFT / SUBMITTED / REGISTERED / EMBARGOED / UNAVAILABLE}} |
| registration ID / URL / PDF SHA256 | {{未提交写 N/A，不伪造}} |

## 1. Question 与 estimand

- **目标人群/对象与外推边界**：{{population}}
- **统计单位 / 随机化单位 / 分析单位**：{{三者分别写；不同则解释}}
- **比较**：{{A vs B，在何条件}}
- **outcome**：{{variable + computation + aggregation + timepoint}}
- **estimand**：{{要估计的 contrast/effect + summary measure}}
- **成功**：{{支持 H1 的量化门槛}}
- **失败/反证**：{{推翻 H1 的量化结果}}
- **无结论**：{{CI/precision/guardrail 何时判 inconclusive}}

## 2. 假设与 outcome registry

| ID | 角色 | 假设/问题 | outcome 定义 | 反证条件 |
|---|---|---|---|---|
| H1 | primary confirmatory | {{}} | {{variable/metric/aggregation/timepoint}} | {{}} |
| H2 | secondary confirmatory | {{}} | {{}} | {{}} |
| E1 | exploratory | {{}} | {{}} | 不作 confirmatory 判决 |

## 3. Design、对照与分析

- **design / sampling / allocation**：{{randomized / observational / repeated / cluster / benchmark}}
- **blocking / stratification / blinding**：{{}}
- **baseline 公平性**：{{实现、数据/划分、搜索空间、调参/训练预算、early stopping、重复数}}
- **negative control / sham / falsification endpoint**：{{}}
- **primary analysis**：{{exact model/test + variables + covariates + transforms}}
- **comparison family K 与校正**：{{成员列表 + Holm/BH/Bonferroni/层级策略}}
- **missingness / outlier / exclusion**：{{规则在看结果前写死}}
- **assumption failure fallback**：{{if-then；不得按结果挑最有利版本}}

## 4. Power / sensitivity

| 项 | 预注册值 |
|---|---|
| 独立样本单位 | {{患者/cluster/独立 run；不得写 fold/同一对象重复}} |
| 效应量或 SESOI | {{值、尺度}} |
| 来源与 locator | {{meta / 外部研究 / pilot；pilot 是否 shrink}} |
| 方差/baseline rate/ICC/attrition 假设 | {{}} |
| low / base / high 情景 | {{至少三点}} |
| 方法 | {{power_check 仅双样本 t；否则 statsmodels/R/simulation/MDE}} |
| 目标 power / alpha | {{}} |
| 结论 | {{所需 N 或固定 N 下 MDE；不可用写 UNAVAILABLE+原因}} |

## 5. Stopping、guardrail 与资源

- **固定 N / 合法 sequential rule**：{{禁止 optional stopping}}
- **guardrail / counter-metric**：{{阈值}}
- **kill criterion**：{{何时提前停止；安全/质量/资源绝对下限}}
- **inconclusive 默认动作**：{{不 ship / 降 claim / 新数据复验}}
- **预算**：{{runs × repeats × sweep × 时长/费用/存储 + 30–50% 冗余}}

## 6. Secondary、exploratory 与偏离

- 预注册 secondary：{{}}
- 允许的 exploratory：{{单列，不冒充 confirmatory}}
- 若修改本计划，追加而不覆盖：

| amendment | 日期时间 | 原版本/hash | 改动与理由 | 是否看过 outcome | 受影响 claim | 新版本/hash |
|---|---|---|---|---|---|---|
| A1 | {{}} | {{}} | {{}} | {{是→受影响项转 exploratory}} | {{}} | {{}} |

## 7. 冻结前自检

- [ ] question、estimand、统计/随机化/分析单位一致。
- [ ] primary/secondary/exploratory 已分轨，comparison family 有边界。
- [ ] exclusion、missingness、fallback、stopping 不依赖未来结果。
- [ ] effect size 有来源与 sensitivity，不把经验阈值或 seed 数冒充正式 power。
- [ ] baseline 公平、ablation 单变量、negative control 与 guardrail 已写。
- [ ] data revision/hash/split、plan commit/hash、registry status 可复核。
- [ ] 未登录/受限资源如实写 `UNAVAILABLE`，没有把 DRAFT 写成 REGISTERED。
