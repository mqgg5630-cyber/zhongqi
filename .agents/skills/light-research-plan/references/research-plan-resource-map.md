# 从可行 idea 到冻结方案：真实研究者资源地图与 stage-5 闭环

> 本文件回答“研究者会去哪里、按什么顺序把可行数据变成可执行研究方案”。它与
> [`../references.md`](../references.md) 分工明确：`references.md` 保存 DVC/MLflow/Hydra/statsmodels 等
> **工具调用细节**；本文件保存 **question→estimand→design→power/sensitivity→preregistration→Light 门→下游/回炉**
> 的工作流与 access 决策。竞品机制以
> [`docs/competitors/research-plan.md`](../../../docs/competitors/research-plan.md) 为 SSOT。

## A. 八步闭环

### Step 1 · 从 idea + data feasibility 写 question、estimand 与判定边界

先读 idea-critique 放行记录、data card、feasibility verdict、lineage、split 约束；不要先挑检验或模型。

至少冻结：

- **目标人群/对象**与外推边界；
- **统计单位、随机化单位、分析单位**；三者不同必须解释；
- **比较**（treatment/exposure/method A vs B）与目标条件；
- **outcome** 的变量、计算、聚合和 timepoint；
- **estimand**：要估计的 effect/contrast 及 summary measure；
- **成功、失败、无结论**三种结果，不把“不显著”自动写成“无效”；
- 已知 intercurrent events、missingness、domain shift 如何影响 estimand。

若存在 association/causal、连续/阈值、population/subgroup 等多种合理 framing，给 2–3 个备选与
trade-off，推荐一个后让用户定。**不要把机器最易算的那个偷偷当研究问题。**

### Step 2 · 选 design、单位、对照与负对照

按问题选 randomized / quasi-experimental / observational / repeated-measures / cluster / factorial /
cross-over / offline benchmark；再明确：

1. 分配或抽样方法、blocking/stratification；
2. baseline 的实现、输入信息、数据划分、搜索空间、调参/训练预算与 early stopping 是否等价；
3. negative control / sham / random-label / placebo / falsification endpoint；
4. 每个 ablation 只改变一个机制；联合 ablation 不归因单组件；
5. design 对应的分析模型、误差层级与独立重复单位。

统计单位错配是结构性失败：同一患者的 fold、同一实验的 seed、同一 cluster 内样本不能因行数多就当独立 n。

### Step 3 · 用 pilot/先验/SESOI 做 power 或 sensitivity

顺序固定：

1. 先写 planned analysis 与独立单位；
2. 效应量优先 **SESOI（最小科学/实践重要效应）**，其次外部 meta/高质量先验，再次经收缩的 pilot；
3. 同时记录方差、baseline rate、ICC、attrition、cluster size、comparison family K 等假设；
4. 简单双样本均值设计才用 `power_check.py`；
5. paired、比例、ANOVA、mixed/cluster、survival、repeated CV 等设计，用对应 statsmodels/R 方法或
   simulation；不可用时写 `UNAVAILABLE` 并给 sensitivity/MDE，不硬算；
6. 至少给 low/base/high 三个效应情景或一条 power/MDE curve。

**禁止：**用 Cohen 0.2/0.5/0.8 冒充领域先验；用 observed effect 做 post-hoc power；把 seeds/folds
自动当独立样本。固定公开数据不能加样本时，优先回答“当前 N 能排除多大的效应？”。

### Step 4 · 锁 outcome、family、exclusion 与 stopping

在看 confirmatory outcome 前锁：

- primary outcome **只能有明确有限个**；secondary 与 exploratory 分栏；
- 每个 outcome 写 variable、analysis metric、aggregation、timepoint；
- comparison family 的成员与 Bonferroni/Holm/BH/层级策略；
- inclusion/exclusion、missingness、outlier、transform、covariate 与 fallback；
- fixed-N 或合法 sequential/alpha-spending stopping rule；
- safety/quality guardrail、kill criterion 与 inconclusive 默认动作。

如果 outcome 已看过，把受影响分析标 exploratory；不能靠补写时间戳洗成 confirmatory。

同一阶段还要生成 `failure-tree.json` 并运行 `failure_tree_gate.py`：每条 hypothesis 必须有
`success/failure/inconclusive` 三分支，写清可量化 condition、action_kind 与 claim_impact；guardrail/counter-metric
必须有阈值、监控阶段、kill_action 与 claim impact。没有 guardrail 只能写显式不适用理由，并在 final package 中当
warning 决策处理；不能让失败或无结论分支继续保留 confirmatory claim。

### Step 5 · 规划 baseline、ablation、robustness、repeat 与预算

用 [`../templates/experiment_matrix.md`](../templates/experiment_matrix.md) 逐行登记：

- main baseline 与公平性证据；
- single-variable ablation、negative control、confirmation；
- robustness（noise/missing/domain shift）、sensitivity（参数/分析选择）、generalization；
- seed/repeat 只服务随机性估计，不假装独立样本量；
- 每行 runs × repeats × sweep points × 单次时长/费用/存储；
- 30–50% 调试/失败重跑冗余。

需要派生评测集时，写 `derive_spec` 回 data-engineering；只动特征、不碰标签、固定 revision/seed、仅评测。

### Step 6 · 生成预注册包并冻结 provenance

先填 [`../templates/preregistration.md`](../templates/preregistration.md)，本地至少保存：

```text
plan_version + frozen_at + git_commit + file_sha256
data_source_url + revision + raw/clean hash + split scheme/seed
registry + registration_id/url/status
primary/secondary/exploratory + family + exclusion + stopping
amendments/deviations (date, reason, affected claim, new version)
```

平台选择：

- 通用验证性研究：OSF Registrations；
- 一页轻量计划：AsPredicted；
- 随机临床试验：适用法域/期刊要求的 trial registry，并用 SPIRIT protocol；
- 系统综述：PROSPERO 或适用 registry；
- 仅探索性工作：可注册设计/流程，但必须诚实标 exploratory。

账号、共同作者确认、embargo、公开提交都是用户决策。Light 只准备包和核字段，**不代提交不可逆注册**。

### Step 7 · 跑本技能门与 stage-5 checkpoint

```powershell
python scripts/plan_lint.py --file experiments/experiment_matrix.md
python scripts/power_check.py --effect 0.5 --n 5
python scripts/plan_gate.py --spec plan_spec.json --report plan_findings.json
python scripts/failure_tree_gate.py --input failure-tree.json --json-out .light/failure_tree_report.json
python ../light-orchestrator/scripts/run_checkpoint.py --file .light/passport.yaml --stage 5 `
  --findings plan_findings.json --write --ts 2026-07-02T12:00
python scripts/research_package_gate.py --manifest plan_package.json --final `
  --json-out research_package_report.json
```

- `plan_lint`：四要素缺项 exit 1；语义/ablation/family 提示是 advisory；
- `power_check`：只对其声明的双样本 t 场景解释；
- `plan_gate`：明确不公平或缺 falsifier 才是 critical；
- `failure_tree_gate`：成功/失败/无结论/guardrail 分支结构闭合；`FAIL` 不得下游，`WARN` 需 warning_decisions；
- checkpoint fail 时在 stage 5 内修方案；**没有 `ROUTES[5]` 出边**；
- `research_package_gate --final`：完整计划包交付门。缺 `PROJECT_PLAN.md`/实验矩阵/target-chain 报告/plan_findings/
  预注册包/复现清单、warning 未记录修复或降 claim、缺用户授权，都会 fail-closed；`WARN` 只有在
  `warning_decisions` 写清处理与用户授权时才允许交接。

机器绿只表示结构/声明未触发已编码门，不表示因果可识别、领域合理或伦理批准。方案定型仍停下让用户确认。

### Step 8 · 交 experiment-coding；结果不支撑时按 7→5 回炉

交付包至少含 `PROJECT_PLAN.md`、experiment matrix、preregistration、reproducibility checklist、
data lineage、plan findings、target-chain report、registry provenance、`plan_package.json` 与
failure-tree report、`research_package_report.json`。experiment-coding 按冻结矩阵实现，不自行改 primary outcome。

result-analysis 若产真实 root-cause finding“结果不支撑 Hx”，运行：

```powershell
python ../light-orchestrator/scripts/reroute.py --findings result_findings.json --stage 7 `
  --passport .light/passport.yaml
```

`reroute` **只建议** 7→5，并携带 Hx、effect/CI 与 evidence pointer。到这里停下让用户选择：
重规划、降低 claim、转 exploratory/known limitation，或在充分理由下继续。用户拍板后才
`passport add-back-edge --to 5 --from 7`。

## B. 资源地图（按 access 分级）

### B1 · 免费公开、核心路径可读

| 资源 | 用在何处 | 接入方式与边界 |
|---|---|---|
| SPIRIT–CONSORT 2025 | 随机试验 protocol/outcome/report trace | 公开 checklist；只在适用试验使用，不把临床表硬套 ML benchmark |
| ICH E9(R1) estimand addendum | objective→estimand→analysis/sensitivity 对齐 | 公开规范；结构可迁移，领域定义仍需专家 |
| EQUATOR Network | 按研究类型找 reporting guideline | 公开检索；reporting 完整不等于设计无偏 |
| statsmodels docs | t/paired/ANOVA/normal/chi-square power | 公开文档与开源包；按类的适用条件，不硬套 |
| R `pwr` / simulation 自写 | 经典检验或复杂设计 sensitivity | 开源；记录版本、脚本、DGP 与 Monte Carlo CI |
| Dacrema / NeurIPS checklist / EXP-Bench | 公平 baseline、复现与四要素 | 方法学锚，不是 registry 或机器批准 |

### B2 · 免费但需登录/共同作者确认

| 资源 | 用法 | access 处理 |
|---|---|---|
| OSF Registrations | 通用 preregistration、embargo、DOI/冻结版本 | 免费账号；提交后不可直接改附件；Light 只备包，用户提交 |
| AsPredicted | 轻量单页 preregistration | 邮箱/共同作者确认；生成 PDF 后保留 URL+SHA256 |
| ClinicalTrials.gov / ISRCTN / AEA / EGAP / PROSPERO 等 | 特定研究类型或法域注册 | 资格、审核与字段因 registry 而异；提交当天重核 |

未登录、未获共同作者确认或 registry 不接受时，写 `UNAVAILABLE`，保留本地 git timestamp+hash，
转 OSF/适用公开替代；不得声称“已预注册”。

### B3 · 机构/受限

- IRB/伦理系统、医院 CTMS、受控数据 enclave、机构统计咨询与 sponsor protocol system。
- 需要机构身份、审批、DUA 或法域义务时，状态写 `RESTRICTED`/`PENDING`；不代登录、不绕过。
- 无权访问时继续做本地公开核心路径，但不得开展需要批准的招募/干预。

### B4 · 付费闭源

- JMP、Design-Expert、nQuery、PASS、商业 trial management 与部分 power SaaS。
- 可作人工复核，不作为 Light 核心路径。没有许可证时写 `UNAVAILABLE`，改用 statsmodels/R/simulation。
- G*Power 免费但闭源 GUI，归辅助复核；自动化证据仍保留脚本、版本和输入假设。

## C. 当天复核入口

- OSF：`https://help.osf.io/article/330-welcome-to-registrations`
- AsPredicted：`https://aspredicted.org/`
- SPIRIT–CONSORT：`https://www.consort-spirit.org/`
- ICH E9(R1)：`https://www.ema.europa.eu/en/ich-e9-statistical-principles-clinical-trials-scientific-guideline`
- statsmodels power：`https://www.statsmodels.org/stable/stats.html#power-and-sample-size-calculations`
- EQUATOR：`https://www.equator-network.org/`

平台字段、费用、账号与服务状态会变；**使用当天重核**。查不到写 `unknown/UNAVAILABLE`，不用旧笔记冒充实时状态。
