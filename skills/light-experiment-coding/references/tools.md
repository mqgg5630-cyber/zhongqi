# experiment-coding 工具与机制锚

> 核验日 2026-07-02。逐步工作流见 `experiment-coding-resource-map.md`；同类实读见
> `docs/competitors/experiment-coding.md`。

## 四个本地门

| 工具 | 输入 → 输出 | 退出 1 的含义 |
|---|---|---|
| `review_gate.py` | Python 文件/目录 → `light.findings.v1` 或 Markdown | 交付扫描命中 critical；含 known sklearn holdout/CV 之前 preprocessing fit |
| `seed_audit.py` | 实际训练代码 + seed helper → 覆盖报告 | 按已使用框架推断出的 critical seed 机制缺失 |
| `repro_gate.py` | code + 可选 split artifact spec → canonical experiment-coding findings | leakage 或 reproducible critical；float/security 在研究 checkpoint 只 warn |
| `run_artifact_check.py` | 单个 run bundle，或两个固定同 seed run → JSON | 文件缺失/hash 篡改/provenance 身份不等/未来或倒序 run 时间/指定 artifact hash 不同 |

```bash
python scripts/review_gate.py src/ --json
python scripts/seed_audit.py src/train.py src/reproducibility.py
python scripts/repro_gate.py --spec repro_spec.json --report repro_findings.json
python scripts/run_artifact_check.py --manifest runs/EXP-01/run-a/manifest.json
python scripts/run_artifact_check.py --compare runs/EXP-01/run-a/manifest.json runs/EXP-01/run-b/manifest.json
```

四者都有离线 `--selftest`。静态门是必要非充分条件；artifact pair 是运行证据，也不外推为跨平台绝对复现。

## 随机性

按实际框架覆盖：

```python
import os, random
import numpy as np
import torch

os.environ["PYTHONHASHSEED"] = str(seed)  # 对当前进程须在启动前由 launcher 设置
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
torch.use_deterministic_algorithms(True)
```

PyTorch DataLoader 另需固定 `generator`，并在 `worker_init_fn` 中由 `torch.initial_seed()` 派生 NumPy/Python seed；
CUDA 算子按需在使用前设 `CUBLAS_WORKSPACE_CONFIG`。官方明确：跨 release、platform、CPU/GPU 不保证完全一致。
可运行 helper 在 scaffold `src/example/reproducibility.py`。

`fixed_repro` 是复跑同一实现；`randomness_estimation` 是多个 seeds 估计算法随机性。后者的重复数不是患者样本量，
不得写进功效分析的 n。

## 泄漏

sklearn 规则：先划分，预处理只 `fit` 训练数据；交叉验证把预处理放进 `Pipeline`，由每个训练折拟合。
`review_gate` 查代码形态，`repro_gate` 复用 data-engineering `split_leakage` 查产物中的行/实体/近重复/目标编码穿越。
二者都不证明不存在所有语义泄漏。

## 数值与测试

- gold test：小型已知答案；
- property test：Hypothesis 生成输入验证范围/对称性/单调性等性质；
- metamorphic test：置换、缩放或等价表示后输出关系保持；
- 浮点用 `pytest.approx` / `numpy.testing.assert_allclose(rtol, atol)`，先声明 device/dtype/AMP；
- NaN/Inf 默认 fail；并行或无序聚合先稳定排序再比较。

scaffold 依赖已写入 `uv.lock`：

```bash
uv sync --locked --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Ruff/Bandit 查通用安全 shape，不带科研 leakage/框架 seed coverage；MLflow/DVC 可作本地增强，但核心闭环只依赖普通文件、
git、hash 与上述免费工具。
