# experiment-coding 可执行 resource map（stage 6）

> 本图回答“按什么顺序读什么、产什么、跑什么门”。`SKILL.md` 定义行为与红线；本图定义逐步交接；
> `references/tools.md` 解释机制；`assets/project-scaffold/` 是可复制代码；`templates/` 是机读/人读产物契约；
> `scripts/` 是门。它们不是四份重复清单。

## 入口契约：先冻结，再写码

开始前读取并计算 SHA256：

1. research-plan 的 question/estimand、`experiment_matrix.md`、pre-registration 及其 provenance；
   以及 `.light/failure_tree_report.json` 的 locator、SHA256、PASS/WARN 状态和 warning decisions；
2. data-engineering 的 fixed revision、raw/curated hash、lineage、split ID 与 `split_leakage` 证据；
3. 当前代码 commit/dirty state，以及 result-analysis 的 raw-run/provenance 消费契约。

把这些指针写入每行配置和 run manifest。实现阶段不得修改 primary outcome、comparison family、
exclusion、stopping 或 fair-comparison 常量；若计划不可执行，带证据返回 research-plan 让人决策，不用代码默认值
静默漂移。
每个 matrix row 还必须写 `failure_tree_refs`：关联的 hypothesis_ids、success/failure/inconclusive
branch_action_ids，以及适用的 guardrail_ids。没有这些引用，执行端无法知道该监控哪些 counter-metric 或触发什么 kill action。

## 八步执行图

| 步 | 动作 | 必产物 / 可执行验收 |
|---|---|---|
| 1 冻结输入 | 校验 question/estimand/matrix/prereg/failure-tree/lineage 的文件、revision、hash；为每个 matrix row 分配稳定 ID | `config.json` 回指 frozen-plan SHA、failure_tree_report SHA、matrix row、split ID、data SHA；缺项即停 |
| 2 建骨架 | 复制 `assets/project-scaffold/`；保留 `uv.lock`；用 JSON Schema 校验配置；定义 data/model/metric 接口 | `uv sync --locked --extra dev`；`configs/experiment.schema.json`；禁止隐式全局配置 |
| 3 测试先行 | 先写并亲眼看 gold、property、metamorphic 测试失败，再实现 preprocessing/train/eval | gold 固定已知答案；Hypothesis 检性质；metamorphic 检输入变换关系；预处理只在训练折 fit，CV 用 Pipeline |
| 4 控随机性 | 分开 `fixed_repro` 与 `randomness_estimation`；设置 Python/NumPy/框架/CUDA/DataLoader/worker | 固定 seed 用于同环境复跑；多 seeds 估计算法随机性；seed 数绝不冒充患者/实体样本量 |
| 5 数值边界 | 显式 device/dtype/mixed precision；定义容差；拒绝 NaN/Inf；记录排序、线程、并行与非确定算子 | CPU/GPU、fp32/fp64/AMP 适用性与容差写入 config/test；同环境契约不外推为跨硬件 bitwise 保证 |
| 6 逐 run 留证 | 每个 matrix row、config、seed、attempt 独立 run dir；失败也不覆盖/删除 | manifest、config、env、commit、输入 hash、stdout、stderr、raw metrics、patient/entity predictions、test evidence、failure artifact；禁止只留汇总 CSV |
| 7 真门控 | 跑 review/seed/repro/artifact 门和 stage-6 checkpoint；同固定 seed 真跑两次 | `review_gate.py`、`seed_audit.py`、`repro_gate.py`、`run_artifact_check.py` 均留 exit code；两次比较 predictions/raw_metrics hash；checkpoint 由 canonical findings 驱动 |
| 8 下游交接 | 把全部 raw runs（含 failed/coverage）交 result-analysis，不先替它做 claim | result-analysis 若判实现 bug/不可复现，只生成 7→6 reroute 建议；**落回边前停下让用户拍板** |

## 随机性与数值控制清单

- 进程启动前设置 `PYTHONHASHSEED`；入口设置 `random.seed`、NumPy RNG、实际框架 RNG。
- PyTorch/CUDA：`manual_seed`、`cuda.manual_seed_all`、cuDNN deterministic/benchmark、需要时
  `use_deterministic_algorithms` 与 `CUBLAS_WORKSPACE_CONFIG`。
- DataLoader：显式 `generator` 与 `worker_init_fn`；记录 worker 数、sampler、drop-last、线程数。
- 其他框架按实际使用覆盖，未使用的机制标 `not_applicable`，不可伪装已验证。
- 固定 seed 两次一致是“同代码、数据、环境、配置”的证据，不证明跨 release、平台或硬件绝对复现。
- 多 seeds 的单位是算法重复；功效分析的单位是患者/实体。二者必须分别记录。
- 比较浮点输出前先约定 dtype/device/AMP、`rtol`/`atol` 和排序键；NaN/Inf 默认 fail，不用静默填补。

## run bundle 契约

每个目录至少含：

```text
runs/<matrix-row>/<run-id>/
  manifest.json              # light.run_manifest.v3
  config.json                # schema 校验后的最终配置
  environment.json           # Python/OS/包/硬件/线程
  stdout.log
  stderr.log
  raw_metrics.jsonl          # 每折/每患者聚合前原始指标
  predictions.csv            # patient/entity-level prediction
  test_evidence.json
  guardrails.json             # completed 且 research-plan 要求 guardrail 时必有
  failure.json               # status=failed 时必有；completed 时可无
```

`manifest.json` 必须记录 run ID、matrix row、seed role/value、argv 数组、带时区且真实已发生的
`started_at/ended_at`、代码 commit/dirty、所有文件和输入 SHA256、source revision、状态与时间。用
`python scripts/run_artifact_check.py --manifest <run>/manifest.json` 校验；同固定 seed 两次用
`--compare <run-a>/manifest.json <run-b>/manifest.json`。默认比较 predictions 与 raw_metrics 的内容 hash；环境/代码/config/input 任一身份不等，
比较直接失败，避免拿两种实验冒充复现。

`experiment_execution_contract.py` 的 `as_of` 用来裁定冻结与授权时间轴：`frozen_at`、远程/付费执行
`approved_at` 不得晚于 `as_of`；`decision=NOT_READY/UNKNOWN` 是阻断性裁定，不能交给 result-analysis。
同一门还会核 `experiment_spec.failure_tree` 与 `matrix_rows[].failure_tree_refs`；上游 failure-tree
`FAIL/UNKNOWN`、`WARN` 无决策、row 未绑定 guardrail、completed run 缺 guardrail evidence 都必须 fail-closed。

## 门与路由边界

1. `review_gate` 是交付扫描门；代码级 leakage 命中退出 1。
2. `repro_gate` 产 canonical `light.findings.v1`：stage 6 只有 leakage/reproducible 是 critical；
   float/security 在研究 checkpoint 为 warn，严重度不得扩张。
3. `run_checkpoint --stage 6` fail 后就在 stage 6 修，**不存在 `ROUTES[6]` 出边**。
4. 数据件泄漏复用 data-engineering 的 `split_leakage`，不复制实现。
5. result-analysis 的真实 bug/unreproducible finding 才能建议 7→6；reroute 不是授权，用户确认后才落 back-edge。

## 资源可用性分层

| 层级 | 可用资源 | 核心路径规则 |
|---|---|---|
| 本地免费 | Python、uv/pip、pytest、Hypothesis、sklearn Pipeline、ruff、Bandit、git、四个本技能脚本、`split_leakage` | **默认核心路径**；离线时仍能跑门与已有数据 |
| 免费公开 / 可选登录 | PyPI、GitHub、Hugging Face 固定 revision、公开论文、MLflow local、DVC local/公开 remote | 下载后固定 revision/hash；登录 token 只走环境变量；不可用写 `UNAVAILABLE:原因` |
| 机构受限 | 受控患者数据、机构 GPU/HPC、付费数据库 | 记录访问条件与替代验证；不得把受限数据复制进 run bundle |
| 付费闭源 | 私有 IDE、云实验追踪、闭源 AutoML | 只能可选增强；不可作为复跑、门控或 provenance 的唯一载体 |

核心闭环不得依赖付费 IDE、云追踪或私有 key。某资源不可用时，manifest 明写 `UNAVAILABLE`，并用本地文件
artifact 保留同等字段；不能把“没装/没权限”写成 pass。
