# -*- coding: utf-8 -*-
"""兼容 façade —— 旧代码里的 `import backtest_engine as be` 仍然可用。
====================================================================

真实实现在 quant/ 包里（2026-11-04 起分层，2026-11-08 整理目录）：

    quant/config.py      L0 路径与常量
    quant/data.py        L1 数据：读写、脏数据归一、过滤、前复权
    quant/factors.py     L2 因子：原始因子、事件信号、标准化
    quant/picker.py      L2 选股：唯一的一份选股实现
    quant/engine.py      L3 执行：策略注册、调仓循环、评估
    quant/strategies.py  L3 策略库（import 即注册）

新代码请直接 `from quant import engine, picker`，别再用这个文件。
"""
from quant.data import (CACHE, PKL, _NUM_COLS, read_csv, normalize_frame,
                        load_raw, _load_raw, _read_csv, _save_pkl, preprocess)
from quant.factors import _second_stand_signal, compute_factors, standardize
from quant.engine import (DEFAULT_CONFIG, STRATEGIES, Dataset, register,
                          _add_fwd, _LazyDateGroups, build_groups, load_all,
                          run_backtest, evaluate, equity, by_year, mdd, _mdd)

__all__ = [
    # L1 data
    "CACHE", "PKL", "_NUM_COLS", "read_csv", "normalize_frame",
    "load_raw", "_load_raw", "_read_csv", "_save_pkl", "preprocess",
    # L2 factors
    "_second_stand_signal", "compute_factors", "standardize",
    # L3 engine
    "DEFAULT_CONFIG", "STRATEGIES", "Dataset", "register",
    "_add_fwd", "_LazyDateGroups", "build_groups", "load_all",
    "run_backtest", "evaluate", "equity", "by_year", "mdd", "_mdd",
]
