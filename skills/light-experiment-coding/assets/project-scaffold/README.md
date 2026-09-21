# example-project

`light-experiment-coding` 的可运行科研实验代码骨架。复制本目录改名即用。

## 安装

```bash
uv sync --locked --extra dev  # 严格按已提交的 uv.lock 安装
uv run pre-commit install   # 启用提交钩子（可选）
```

无 uv 时可退回：

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## 运行测试

```bash
uv run pytest                                   # 全测试，首失败即停
uv run pytest --cov=src --cov-report=term-missing   # 看覆盖率
```

## 质量门

```bash
uv run ruff check .          # linter
uv run ruff format --check . # formatter（与 linter 是两个命令）
uv run mypy src              # 静态类型检查
uv run pre-commit run --all-files
```

**类型检查档位**（按项目性质二选一）：
- **应用 / 科研代码**：用默认基础档起步（`[tool.mypy]` 已配，仅检明显类型错，不强制全注解）。pyright 用户设 `"typeCheckingMode": "basic"`。
- **库代码 / 对外 API**：解开 `pyproject.toml` 里 `[tool.mypy]` 的 `strict = true`（要求全量类型注解，最严）。pyright 用 `"strict"`。

## 复现

- Python 版本锁在 `pyproject.toml` 的 `requires-python`；CI matrix 跑 3.11/3.12/3.13。
- 已带 `uv.lock`；改依赖后显式 `uv lock` 并审 diff，CI 用 `uv sync --locked`，锁漂移直接失败。
- 固定随机种子：实验入口最早处调一次 `set_global_seed()`（见 `src/example/reproducibility.py`，覆盖 stdlib/numpy/torch，缺包自动降级），并记录环境（`uv pip freeze` 或 lock 文件）。
- `configs/experiment.schema.json` 是每个 experiment-matrix row 的配置契约；复制
  `experiment.example.json`，填写冻结计划/data revision/hash，绝不在实现阶段改 outcome、comparison family、
  exclusion 或 stopping。

## 转 Poetry 的最小 diff

默认走 uv（最快、lock 通用）。若团队约定用 Poetry，仅需三处改动，业务代码与测试不动：

1. `pyproject.toml` 换 build-system：

   ```toml
   [build-system]
   requires = ["poetry-core>=2.0"]
   build-backend = "poetry.core.masonry.api"
   ```

2. dev 依赖从 `[project.optional-dependencies].dev` 搬到 Poetry 的 group（运行期 `dependencies` 仍可用 PEP 621 标准段，Poetry 2.x 兼容）：

   ```toml
   [tool.poetry.group.dev.dependencies]
   pytest = ">=9.0"
   pytest-cov = ">=7.0"
   hypothesis = ">=6.155,<7"
   ruff = ">=0.15"
   pre-commit = ">=4.0"
   mypy = ">=1.13"
   ```

3. CI（`.github/workflows/ci.yml`）把 uv 换成 Poetry：

   ```yaml
   - name: Install Poetry
     run: pipx install poetry
   - name: Install deps
     run: poetry install --with dev
   # 其余步骤把 `uv run` 换成 `poetry run`
   ```

   提交 `poetry.lock`（`poetry lock` 生成）替代 `uv.lock`。

## 结构

```
pyproject.toml                  # 元数据 + 依赖 + ruff/mypy/pytest 配置
uv.lock                        # 可复现依赖解析（提交，不手改）
configs/experiment.schema.json # matrix row 配置 schema
configs/experiment.example.json# 一行实验的最小配置
.pre-commit-config.yaml         # ruff + 基础钩子，rev 锁版本
.github/workflows/ci.yml        # checkout -> setup-python -> uv sync -> ruff -> mypy -> pytest
src/example/stats.py            # 示例模块（单一职责 + 输入校验）
src/example/reproducibility.py  # 全局随机种子（stdlib/numpy/torch，缺包降级）
src/example/experiment_contracts.py # data/model/metric/preprocessing 最小接口
tests/test_experiment_contracts.py  # gold + property + metamorphic + train-only fit
tests/test_stats.py             # parametrize + 异常断言
tests/test_reproducibility.py   # 复现性测试（importorskip 跳过未装后端）
tests/conftest.py               # 共享路径设置
```
