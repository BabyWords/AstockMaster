# -*- coding: utf-8 -*-
"""选股层 —— 全项目唯一的一份选股实现，回测与实盘共用。
=========================================================

分工（不要再在别处重写一遍选股逻辑）：

    preprocess / compute_factors   算原始因子（数据层，只做一次）
    picker.pick()                  过滤 → 横截面标准化 → 策略打分 → 取前 N
    engine.run_backtest           循环调 pick()，统计持有收益
    selection.select              只调一次 pick()，输出今天的名单

为什么要单独抽这一层：
    以前回测引擎和 select_stocks.py 各写了一套因子和过滤条件，同一个策略名
    两处规则不同 —— 回测买的票实盘买不到。2026-10-31 实测「小市值反转低波」
    2019-2026：只剔 ST + 股价≥2 → +362.8%；再加上成交额≥5000万 + 剔涨停
    → +54.6%。所以过滤条件必须是参数，且回测默认沿用实盘口径。

过滤参数 filters（全部可选，缺省值 = 实盘口径）：
    min_price  收盘价下限（元）      默认 2.0
    min_amt    当日成交额下限（万元）默认 5000
    max_pct    涨跌幅上限（%）       默认 9.5（剔除接近涨停，不追高）
    restd      是否在过滤后重算 z_   默认 True
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 参与横截面标准化的因子列（与 backtest_engine.compute_factors 产出一一对应）
FACTOR_COLS = [
    "SIZE", "REV5", "REV20", "REV60", "MOM20", "VOL20",
    "TURN", "PB", "PE", "DIV",
    "LB", "TURN_STD20", "MAXUP20", "MAXDN20", "NEWHIGH20", "MA_GAP",
    "AMT", "AMT20", "VOL_RATIO", "PCT", "GAP", "TAIL", "IS_YANG",
]

# 默认过滤 = 实盘口径。回测默认也用它，否则回测买进的票你实盘买不到。
DEFAULT_FILTERS = {
    "min_price": 2.0,     # 收盘价下限（元）：剔除面值退市高危股
    "min_amt": 5000.0,    # 成交额下限（万元）：买不进的票不参与比较
    "max_pct": 9.5,       # 涨跌幅上限（%）：剔除接近涨停，不追高
}


def apply_filters(day: pd.DataFrame, filters: dict | None = None) -> pd.DataFrame:
    """按可交易性过滤当天横截面。"""
    f = {**DEFAULT_FILTERS, **(filters or {})}
    d = day
    if f.get("min_price"):
        d = d[d["收盘价（元）"] >= float(f["min_price"])]
    if f.get("min_amt"):
        d = d[d["AMT"].fillna(0) >= float(f["min_amt"])]
    if f.get("max_pct"):
        d = d[d["PCT"].fillna(0) < float(f["max_pct"])]
    return d


def standardize_day(day: pd.DataFrame) -> pd.DataFrame:
    """在【过滤后】的当天横截面里重新算 z_ 列。

    实盘选股是先按流动性筛掉一批，再在剩下的票里比较「谁更小、谁跌得更深」。
    若沿用全市场 z 值，Score 会系统性地偏向那些本来就买不进的微盘股。
    """
    d = day.copy()
    cols = [c for c in FACTOR_COLS if c in d.columns]
    if not cols:
        return d
    m = d[cols].mean()
    s = d[cols].std().replace(0, np.nan)
    for c in cols:
        d["z_" + c] = (d[c] - m[c]) / s[c]
    return d


def pick(day: pd.DataFrame, strategy, filters: dict | None = None,
         top_n: int = 5) -> pd.DataFrame:
    """选股：过滤 → 标准化 → 打分 → 取前 top_n。

    day       某一天的全市场横截面（含原始因子列 + 前复权价）
    strategy  策略函数，输入横截面，返回打分 Series（越大越优先）
    filters   可交易性过滤参数，见模块说明
    top_n     取前几名

    返回按 score 降序的 DataFrame（含 score 列）；池子为空时返回空表。
    """
    d = apply_filters(day, filters)
    if len(d) == 0:
        return d
    if (filters or {}).get("restd", True):
        d = standardize_day(d)
    score = strategy(d)
    d = d.assign(score=score)
    d = d[d["score"].notna()]
    if len(d) == 0:
        return d
    return d.nlargest(int(top_n), "score")


def describe_filters(filters: dict | None = None) -> str:
    """把过滤参数拼成一句人能看懂的话，存进 backtest_run.universe。"""
    f = {**DEFAULT_FILTERS, **(filters or {})}
    bits = ["剔除ST/退市"]
    if f.get("min_price"):
        bits.append(f"股价≥{f['min_price']:g}元")
    if f.get("min_amt"):
        bits.append(f"成交额≥{f['min_amt']:g}万")
    if f.get("max_pct"):
        bits.append(f"涨幅<{f['max_pct']:g}%")
    return " ".join(bits)
