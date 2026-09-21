# 复现清单 checklist：{{项目/课题名称}}

逐项勾选，给出具体配置而非工具名。`[ ]` 未完成 / `[x]` 已完成。
> 对齐 NeurIPS Paper Checklist（code+环境版本+权重+超参 + 多种子误差棒）。按项目规模选档（轻/标/完整），
> 别给小课题套重型工具（DVC/Snakemake）；档位说明见 SKILL「可复现规划」。

## 环境
- [ ] OS / 驱动 / CUDA / cuDNN 版本已记录：{{填写}}
- [ ] 依赖锁版本（requirements.txt 固定版本 / environment.yml / uv.lock / poetry.lock）：{{文件路径}}
- [ ] 硬件记录（GPU 型号 / 数量；CPU 实验记核心数）：{{填写}}

## 目录脚手架
- [ ] 目录布局已生成 —— **调用 project-structure `scaffold.py` 或 `ccds` 生成**（Cookiecutter Data Science 布局），本清单不重复造脚手架
- [ ] raw 数据只读不改：{{确认}}
- [ ] 可复用逻辑下沉到 `src/`，notebook 不放核心逻辑：{{确认}}

## 随机种子全覆盖（★ 最常漏：不止 `torch.manual_seed`）
> 只 set 一个框架种子 ≠ 可复现。下面这些**常被漏**，漏一个就换机/换次跑结果飘：
- [ ] Python `random.seed(s)` + `os.environ["PYTHONHASHSEED"]=str(s)`（**须在进程启动前设**，否则 set/dict 顺序仍随机）：{{确认}}
- [ ] NumPy `np.random.default_rng(s)`（弃用全局 `np.random.seed`）：{{确认}}
- [ ] 框架种子：PyTorch `torch.manual_seed(s)` + `torch.cuda.manual_seed_all(s)` / TF `tf.random.set_seed(s)`：{{确认}}
- [ ] **cuDNN 确定性**：`torch.backends.cudnn.deterministic=True` + `torch.backends.cudnn.benchmark=False`（或 `torch.use_deterministic_algorithms(True)` + 设 `CUBLAS_WORKSPACE_CONFIG`）：{{确认}}
- [ ] **DataLoader worker 种子**：`worker_init_fn` 固定每个 worker 种子 + `generator=torch.Generator().manual_seed(s)`（多进程取数顺序）：{{确认}}
- [ ] 多种子是**算法随机性重复**，数量按目标 Monte Carlo precision/稳定性与预算定；只有独立 run 本身是
  estimand 单位时才进入 run-level power。它 ≠ 患者/cluster 样本量，也 ≠ 单次可复现的固定种子：{{种子列表与用途}}

## 配置管理
- [ ] Hydra 分层配置（conf/ 下 model、dataset 分组 + defaults 列表）：{{conf 路径}}
- [ ] 命令行可覆盖（如 `lr=0.1`），run 自动存最终合成配置：{{确认}}

## 数据 / 模型版本（完整档；小课题可跳）
- [ ] DVC 跟踪大文件（`dvc add`，git 只存 .dvc 指针）：{{确认}}
- [ ] `dvc.yaml` 定义 stages（cmd/deps/params/outs/metrics）+ `dvc.lock` 锁哈希，`dvc repro` 增量复现：{{确认}}

## 流水线（完整档；Windows 注意 Snakemake shell 兼容差→WSL 或换 invoke/make）
- [ ] 流水线 rule（input/output/params）自动推 DAG + 每 rule `conda:`/`container:` 锁环境：{{Snakefile 路径}}

## 实验日志
- [ ] MLflow（set_experiment→start_run→log_param/log_metric(step=)/log_artifact）或 W&B（init→log，Artifacts 管血缘）：{{选型}}
- [ ] 敏感数据用 offline 模式避免外发（`WANDB_MODE=offline`）：{{确认}}

## 固定项
- [ ] 数据划分已固定（划分脚本 + 种子，防泄漏走 data-engineering `safe_split`/`split_leakage`）：{{划分记录}}
- [ ] 超参 / 训练策略已记录：{{配置链接}}
- [ ] 结果文件命名规范已定义：{{规范}}
- [ ] 运行命令已记录（可一键复现，含具体 seed/config）：{{命令}}

> 收尾验证（verification-before-completion）：声明"做完"前过一遍——同种子两次跑结果一致、build 通过、关键函数测试通过、
> 产出逐条对上成功标准、临时文件清理。**可复现的硬验收 = 别人/未来的你用本清单能复跑出同一个数。**
