"""可复现性工具：一处设全局随机种子，覆盖复现清单的全部 ★ 易漏项。

科研代码的首要复现门槛是随机性可控。本模块对齐 PyTorch 官方 randomness 文档与
research-plan 的 reproducibility-checklist，覆盖**最常被漏**的几项：
  - PYTHONHASHSEED（set/dict 跨进程顺序）—— 须在进程启动前设，本函数也写一份供子进程。
  - stdlib random / numpy / torch / torch.cuda 种子。
  - cuDNN 确定性（deterministic=True + benchmark=False）或更强的 use_deterministic_algorithms。
  - DataLoader worker 种子（seed_worker + make_generator）—— 多进程取数顺序确定。

写法「能设的都设、装了才设、缺了就降级」：scaffold 默认零运行期依赖，numpy/torch 未必装，
故全部「尝试导入，失败则跳过」，绝不因缺包而抛错。

用法::

    from example.reproducibility import set_global_seed, seed_worker, make_generator
    set_global_seed(42)                       # 训练 / 实验入口最早处调用一次
    # DataLoader 多进程取数也要可复现：
    loader = DataLoader(ds, num_workers=4,
                        worker_init_fn=seed_worker,
                        generator=make_generator(42))

⚠ 诚实边界：本函数把「能设的种子」一次性设全，但**可复现的终判是同种子真跑两次结果一致**，
   不是「调了本函数就一定可复现」（仍可能有未覆盖的非确定算子 / 第三方库内部随机）。
   PYTHONHASHSEED 在进程内 set 只对**子进程**生效；要本进程也确定，须在启动前于 shell/launcher 设。

返回值是一份「实际设置了哪些后端」的报告，便于在日志里留痕、复现核对。
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedReport:
    """记录 set_global_seed 实际作用到了哪些后端，便于日志留痕。

    seed:    本次使用的种子值。
    python:  是否设了 stdlib random + PYTHONHASHSEED。
    numpy:   是否设了 numpy 全局种子（未装则 False）。
    torch:   是否设了 torch 种子（未装则 False）。
    cudnn:   是否启用了 cudnn 确定性模式（无 CUDA / 未装 torch 则 False）。
    strict:  是否启用了 torch.use_deterministic_algorithms(True)（最强档）。
    """

    seed: int
    python: bool
    numpy: bool
    torch: bool
    cudnn: bool
    strict: bool


def set_global_seed(
    seed: int = 42,
    *,
    deterministic_cudnn: bool = True,
    strict_deterministic: bool = False,
) -> SeedReport:
    """固定全局随机种子，覆盖 stdlib / numpy / torch / cuDNN，缺包自动降级。

    Args:
        seed: 种子值，需非负整数（哈希种子等场景要求）。
        deterministic_cudnn: 装了 torch 且有 CUDA 时，是否开启 cuDNN 确定性
            （`deterministic=True` + `benchmark=False`）。会牺牲少量速度换可复现。
        strict_deterministic: 是否额外启用 `torch.use_deterministic_algorithms(True)`
            （最强档：遇到无确定实现的算子会抛 RuntimeError；并设 CUBLAS_WORKSPACE_CONFIG）。

    Returns:
        SeedReport: 标明各后端是否实际生效。

    Raises:
        ValueError: seed 为负数时。
    """
    if seed < 0:
        raise ValueError(f"seed 需为非负整数，收到 {seed}")

    # 1) PYTHONHASHSEED 影响哈希随机化（set/dict 顺序）。进程内 set 仅对子进程生效，
    #    要本进程确定须在启动前设；这里写下它，让 subprocess / 重启场景拿到确定值。
    os.environ["PYTHONHASHSEED"] = str(seed)

    # 2) stdlib random —— 永远可用。
    random.seed(seed)

    # 3) numpy —— 装了才设。保留全局 seed 兼容老代码；新代码建议用 np.random.default_rng(seed)。
    numpy_set = False
    try:
        import numpy as np

        np.random.seed(seed)
        numpy_set = True
    except ImportError:
        pass

    # 4) torch —— 装了才设；CUDA 存在再设 cuda 种子与 cuDNN 确定性。
    torch_set = False
    cudnn_set = False
    strict_set = False
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            if deterministic_cudnn:
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
                cudnn_set = True
        if strict_deterministic:
            # 最强档：CUBLAS workspace 须在用 CUDA 前设，否则 cuBLAS 仍可能非确定。
            os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:2")
            torch.use_deterministic_algorithms(True)
            strict_set = True
        torch_set = True
    except ImportError:
        pass

    return SeedReport(
        seed=seed,
        python=True,
        numpy=numpy_set,
        torch=torch_set,
        cudnn=cudnn_set,
        strict=strict_set,
    )


def seed_worker(worker_id: int) -> None:
    """DataLoader 的 worker_init_fn：用 torch.initial_seed() 派生每个 worker 的种子，
    重新固定该 worker 进程内的 numpy / random，使多进程取数顺序可复现。

    对齐 PyTorch 官方 randomness 文档的 DataLoader 复现写法。缺包则降级为 no-op。
    """
    try:
        import torch

        worker_seed = torch.initial_seed() % 2**32
    except ImportError:
        worker_seed = worker_id
    try:
        import numpy as np

        np.random.seed(worker_seed)
    except ImportError:
        pass
    random.seed(worker_seed)


def make_generator(seed: int = 42):
    """返回一个种子固定的 torch.Generator，供 DataLoader(generator=...) 用以确定打乱顺序。

    Returns:
        torch.Generator（装了 torch）或 None（未装，调用方应据此降级）。
    """
    try:
        import torch

        g = torch.Generator()
        g.manual_seed(seed)
        return g
    except ImportError:
        return None
