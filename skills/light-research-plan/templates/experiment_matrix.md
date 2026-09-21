# 实验矩阵表：{{项目/课题名称}}

每行一个实验条目（EXP 主 / ABL 消融 / SEN 敏感 / GEN 泛化 / ROB 鲁棒）。状态：`未开始 / 进行中 / 已完成 / 阻塞 / 放弃`。
**完成判定 = 用什么结果回答对应假设**（达到则记支持/不支持该假设）——这是四要素里最易跑偏的一项（EXP-Bench 实证）。
> 填完跑 `python scripts/plan_lint.py --file experiments/experiment_matrix.md` 自查四要素 + 语义弱校验 + 严谨性评分。
> 对照公平/可证伪的 **critical 门**走 `plan_gate.py`；消融隔离/统计功效是 warn/advisory，不冒充科学终判。

## 0. Question、estimand 与单位

- **Population / 外推边界**：{{}}
- **统计单位 / 随机化单位 / 分析单位**：{{分别写；不同则解释}}
- **Comparison**：{{A vs B，在何条件}}
- **Outcome**：{{variable + metric + aggregation + timepoint}}
- **Estimand**：{{contrast/effect + summary measure}}
- **成功 / 失败 / 无结论**：{{三种量化边界}}

> 同一患者的多次测量、同一 split 的 seeds/folds、同一 cluster 内样本不是自动独立 n。design 与 analysis 必须尊重层级。

## 1. 实验矩阵（四要素 + outcome family + 独立单位 + 唯一变化）

| 实验ID | 对应假设 | 角色/family | 数据集 | baseline | 指标 | 独立单位/重复 | 唯一变化 | 已控混淆/负对照 | 随机种子 | 状态 | 完成判定 |
|--------|----------|-------------|--------|----------|------|---------------|----------|-----------------|------------|------|----------|
| EXP-01 | H1 | primary/F1 | {{数据集}} | {{最强可得 baseline}} | {{主指标}} | {{患者/独立 run；N}} | {{方法 A→B}} | {{同等调参预算}} | {{估计随机性用；非自动 power n}} | 未开始 | {{效应+CI/校正后判据}} |
| EXP-02 | H1 | secondary/F1 | {{数据集}} | {{baseline}} | {{指标}} | {{}} | {{}} | {{}} | {{}} | 未开始 | {{判定门槛(可量化)}} |
| EXP-03 | H2 | exploratory/E1 | {{数据集}} | {{baseline}} | {{指标}} | {{}} | {{}} | {{}} | {{}} | 未开始 | {{不作 confirmatory 判决}} |
| ABL-01 | H1 | secondary/F2 | {{数据集}} | {{移除组件X}} | {{指标}} | {{}} | **只移除 X** | {{随机标签负对照+同等预算}} | {{}} | 未开始 | {{掉点幅度支持/反驳 X 贡献}} |
| ABL-02 | H2 | secondary/F2 | {{数据集}} | {{移除组件Y}} | {{指标}} | {{}} | **只移除 Y** | {{}} | {{}} | 未开始 | {{掉点幅度支持/反驳 Y 贡献}} |
| SEN-01 | {{假设}} | sensitivity/S1 | {{数据集}} | {{扫参基线}} | {{指标}} | {{}} | {{只改一个分析/参数选择}} | {{}} | {{}} | 未开始 | {{趋势稳定/最优区间}} |
| GEN-01 | {{假设}} | generalization/G1 | {{跨域数据集}} | {{baseline}} | {{指标}} | {{}} | {{只换目标域}} | {{}} | {{}} | 未开始 | {{跨域不掉超过阈值}} |
| ROB-01 | {{假设}} | robustness/R1 | {{加噪/缺失数据}} | {{baseline}} | {{指标}} | {{}} | {{只改扰动}} | {{}} | {{}} | 未开始 | {{扰动下性能下界}} |

> **每条创新假设须配 ≥1 消融行（ABL-）**：plan_lint 查"假设无消融"会 warn——缺消融难归因增益来自创新点本身。
> **做因果/贡献声明的行（"证明…贡献"）须填「已控混淆/负对照」**：缺负对照难排除替代解释（Popper 严格 Type-I）。
> **联合 ablation 只能说明组合重要**；要声明单组件贡献，必须有只改变该组件的一行与固定项。

## 2. 假设 ↔ 反证条件（可证伪，**critical**：没有能推翻假设的设计 = 不是科学，是包装）

| 假设 | 陈述 | 主指标 | **反证条件**（什么结果能推翻 H，须可量化） |
|---|---|---|---|
| H1 | {{假设陈述}} | {{主指标}} | {{如：top-1 提升 < 2% 或 p ≥ 0.05，则 H1 被推翻}} |
| H2 | {{假设陈述}} | {{主指标}} | {{如：消融掉点 < 1%，则"组件Y有贡献"被推翻}} |

> `plan_gate.py` 的 `falsifiable` 门：假设**缺反证条件 → critical**；反证条件在但不可量化 → warn。**可证伪 ≠ 已证伪**——
> 反证条件设得合不合理须领域判断，脚本只查"有没有"。

## 3. 对照公平性声明（**critical**：baseline 放水 = 提升是假象，对照不公平直接否决结论）

| baseline | 公平性档（ok/warn/unfair:说明） |
|---|---|
| {{最强可得 baseline 名}} | {{ok: 同数据同划分 + 等量调参预算（各 N 轮 Optuna）+ 取当前 SOTA 官方实现}} |
| {{对比 baseline 2}} | {{warn: 受算力限只调到 70%，论文须如实标}} |

> 依据 Dacrema 2019（1907.06902）：**优化过的方法 vs 未优化的方法之间的比较，无法告诉我们新方法是否推进 SOTA**。
> `plan_gate.py` 的 `fair_baseline` 门：声明 `unfair` → critical；未声明 → warn（须补，脚本不替你判 baseline 调够没，GIGO）。

## 4. 功效 / sensitivity（warn/advisory；先匹配设计，后算数字）

| 假设/对比 | 独立单位 | SESOI/效应范围 | 来源+locator/收缩 | family K/校正 | 方法 | 结论 |
|---|---|---|---|---|---|---|
| H1 | {{患者/cluster/独立 run}} | {{low/base/high}} | {{meta / 外部研究 / pilot×shrink}} | {{K + BH/Holm/Bonferroni}} | {{power_check双样本t / 对应Power类 / simulation / 固定N下MDE}} | {{N范围或MDE；不可用写UNAVAILABLE}} |

> `power_check.py` 只适用双独立样本均值近似。d=0.5 达 0.8 约需 64/组，但不能把这个数直接翻译成
> “64 seeds”。paired CV、cluster、mixed/repeated measure、比例等用匹配方法或 simulation；固定公开数据优先 MDE/sensitivity。

## 5. Outcome、排除与 stopping 锁

| 项 | 预注册值 |
|---|---|
| primary outcomes | {{有限列表；variable/metric/aggregation/timepoint}} |
| secondary outcomes | {{}} |
| exploratory | {{单列，不混入 confirmatory family}} |
| inclusion/exclusion | {{在看结果前锁}} |
| missing/outlier/transform/covariates | {{含 if-then fallback}} |
| stopping rule | {{fixed N 或合法 sequential/alpha-spending}} |
| guardrail / kill | {{counter-metric 阈值、绝对安全/质量下限}} |
| inconclusive action | {{降 claim / 新数据 / 不 ship}} |
| frozen provenance | {{plan version + timestamp+tz + git commit + SHA256 + registry status/URL}} |

> 完整注册包用 `templates/preregistration.md`。未登录/未提交写 `DRAFT/UNAVAILABLE`，绝不把本地文档冒充已注册。

## 6. 派生数据规格（回 data-engineering 构建鲁棒性/泛化/敏感性评测集）

ROB/GEN/SEN 行常需主流水线之外的派生评测集。下表的"变换+参数"= 交 data-engineering 的派生数据需求；写成 JSON
（格式见同目录 `examples/plan_spec.example.json` 的 `derive_spec`，对齐 data-engineering `derive_eval_set.py`）回它构建：

| 实验ID | 基础数据集 | 变换(noise/missing/subset/scale) | 关键参数 | eval_dim |
|--------|------------|----------------------------------|----------|----------|
| ROB-01 | {{基础集}} | noise / missing | {{scale=0.5 / rate=0.2(+MCAR·MAR·MNAR)}} | robustness |
| GEN-01 | {{源域}} | subset | {{col=domain, values=[目标域]}} | generalization |
| SEN-01 | {{基础集}} | scale | {{factor=1.5, cols=[...]}} | sensitivity |

> 铁律（data-engineering 兑现）：派生**只动特征不碰标签 + 固定种子 + 仅评测不回流训练折**。完整清单同步写入
> `research-plan.md` §3「派生评测集清单」。

## 7. 算力 / 成本预算（方案定型前算账）

逐实验行估算，汇总对照预算上限。单价随厂商/区域/竞价波动大，**记来源 + 日期**，禁凭记忆。
单次成本 = GPU 时数 × 卡数 × 单价/卡时；总预算另加 30~50% 调试/失败重跑冗余。

| 实验ID | GPU 型号 | 卡数 | 单次时数 | 重复次数(种子×扫参点) | 单价(/卡时,来源+日期) | 小计 |
|--------|----------|------|----------|------------------------|------------------------|------|
| EXP-01 | {{如 A100-80G}} | {{1}} | {{8h}} | {{种子数}} | {{现查云价+日期}} | {{小计}} |
| **合计** | | | | | | {{Σ + 30~50% 冗余}} |

> 重复数 × 扫参网格是预算放大器：超预算则缩 comparison family、扫参范围或 claim；若减少独立样本/重复，记录
> sensitivity/precision 损失，不静默欠功效。

## 说明
- 多种子结果报 **均值±标准差 + 误差棒 + seed 数**；独立样本 n 另报，绝不混称。统计方法与 result-analysis family 口径对齐。
- 参数敏感性建议 Hydra multirun（`-m lr=0.01,0.1 model=a,b` 笛卡尔积）或 W&B Sweeps（grid/random/bayes）系统扫参。
- 实验运行配置与代码落地走 experiment-coding；目录与命名走 project-structure；派生评测集构建回 data-engineering。
