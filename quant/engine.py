# -*- coding: utf-8 -*-
"""L3 执行层 —— 调仓循环与净值评估（纯计算，不含任何 print / CLI）。
=================================================================

职责边界：
    选股规则在 picker，因子在 factors，数据在 data。本层只做
    「按 hold_days 调仓 → 收集每期收益 → 汇总指标」，不打印、不读命令行。

【策略接口】策略是函数 day -> Series（越大越优先）：
    def 策略名(day: pd.DataFrame) -> pd.Series:
        return day["z_SIZE"] + day["z_REV20"]

【口径】t 日收盘选股 → t+1 收盘买入 → 持有 hold_days 个交易日 → 卖出（延迟买入避前视）。
【调仓】每 hold_days 个交易日调一次（不重叠轮换）。
【成本】每期扣 cost（默认 0.3%），复利滚动。
"""
from __future__ import annotations

import collections.abc
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import picker as pk
from .data import load_raw, preprocess
from .factors import compute_factors

# ============================ 默认配置 ============================
DEFAULT_CONFIG = {
    "top_n": 5,           # 每期买入多少只（等权）
    "hold_days": 20,      # 持有多少个交易日（主线策略经回测验证的持有期）
    "cost": 0.003,        # 每期成本（双边）
    "capital": 100000.0,  # 复利模拟本金
    "min_price": 2.0,     # 股价下限：剔除面值退市高危垃圾股（关键修正，勿删）
    "start": "20190101",  # 回测起始日（YYYYMMDD）：全样本缓存从 2019 年开始
    "end": "99991231",    # 回测结束日
    # 可交易性过滤：默认沿用实盘口径（picker.DEFAULT_FILTERS）。
    # 必须和 scripts/select_stocks.py 用同一套，否则回测买的票实盘买不到。
    "filters": dict(pk.DEFAULT_FILTERS),
}

# ============================ 策略注册表 ============================
# 策略定义在 quant/strategies.py，import 时通过 register 装饰器注册进来。
STRATEGIES: dict = {}


def register(name):
    """装饰器：把策略函数注册进 STRATEGIES"""
    def deco(fn):
        STRATEGIES[name] = fn
        return fn
    return deco


# ============================ 数据集 ============================
@dataclass
class Dataset:
    """一次 load_all 的产物。显式传递，不再往 cfg 里塞 _groups/_dlist 隐藏状态。"""
    groups: collections.abc.Mapping          # 交易日 -> 当日横截面（惰性切片）
    dates: list                              # 有序交易日
    load_seconds: float = 0.0
    meta: dict = field(default_factory=dict)  # 行数、区间等，供报告/落库使用

    def __len__(self):
        return len(self.dates)


def _add_fwd(df, hold):
    """未来持有收益：t+1 收盘买入，t+(hold+1) 收盘卖出。"""
    g = df.groupby("股票代码", sort=False)
    df["fwd"] = g["close_adj"].shift(-(hold + 1)) / g["close_adj"].shift(-1) - 1.0
    return df


class _LazyDateGroups(collections.abc.Mapping):
    """按交易日惰性切横截面（字典接口，和原来的 dict 用法完全兼容）。

    原来一次性把 841 万行 × 60 列切成 1899 份：耗时 4.4s、峰值多占约 4GB。
    而回测实际只用到 1/hold 的日期（持有 20 天 → 95 天）。改成按需切片：
    先算一次「日期 → 行号」映射，访问时才取那一张子表，只缓存最近 4 张。
    """

    __slots__ = ("_df", "_keep", "_pos", "_cache")

    def __init__(self, df, keep):
        self._df = df
        self._keep = keep
        self._pos = df.groupby("交易日期", sort=False).indices   # {日期: iloc 行号}
        self._cache = {}

    def __getitem__(self, t):
        key = str(t)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        pos = self._pos[key]
        g = self._df.iloc[pos][self._keep]
        if len(self._cache) >= 4:
            self._cache.clear()
        self._cache[key] = g
        return g

    def __iter__(self):
        return iter(self._pos)

    def __len__(self):
        return len(self._pos)


_KEEP_COLS = [
    "交易日期", "股票代码", "股票名称", "收盘价（元）", "流通市值（万元）", "fwd",
    "开盘价（元）", "最高价（元）", "最低价（元）", "成交额（万元）", "涨跌幅（%）",
    "open_adj", "high_adj", "low_adj", "close_adj",
    "MA5", "MA10", "MA20", "MA60",
    "SIZE", "REV5", "REV20", "REV60", "MOM20", "VOL20", "TURN", "PB", "PE", "DIV",
    "LB", "TURN_STD20", "MAXUP20", "MAXDN20", "NEWHIGH20", "MA_GAP", "SIG2ST",
    "AMT", "AMT20", "VOL_RATIO", "PCT", "GAP", "TAIL", "IS_YANG",
    "z_SIZE", "z_REV5", "z_REV20", "z_REV60", "z_MOM20", "z_VOL20", "z_TURN",
    "z_PB", "z_PE", "z_DIV",
    "z_LB", "z_TURN_STD20", "z_MAXUP20", "z_MAXDN20", "z_NEWHIGH20", "z_MA_GAP",
    "z_AMT", "z_AMT20", "z_VOL_RATIO", "z_PCT", "z_GAP", "z_TAIL", "z_IS_YANG",
]


def build_groups(df, cfg):
    """按回测区间切好 fwd 收益，返回惰性的「交易日 → 横截面」映射。"""
    df = df[(df["交易日期"] >= cfg["start"]) & (df["交易日期"] <= cfg["end"])]
    df = _add_fwd(df, cfg["hold_days"])
    keep = [c for c in _KEEP_COLS if c in df.columns]   # 兼容旧缓存/测试的精简列
    return _LazyDateGroups(df, keep)


def load_all(cfg) -> Dataset:
    """读缓存 → 过滤/复权 → 算因子 → 切成按日横截面。返回 Dataset。"""
    t0 = time.time()
    df = preprocess(load_raw(), cfg)
    df = compute_factors(df)
    # 不预计算全市场 z_ 列：picker.pick() 会在「过滤后的池子」里重算（口径才正确），
    # 这里算一遍既用不上，又要多占约 1.5GB 内存。
    groups = build_groups(df, cfg)
    return Dataset(groups=groups, dates=sorted(groups.keys()),
                   load_seconds=time.time() - t0,
                   meta={"rows": int(len(df))})


# ============================ 回测执行 ============================
def run_backtest(strategy, cfg, ds: Dataset):
    """每个调仓日调一次 picker.pick()，收集当期的等权持有收益。

    选股逻辑全在 picker 里，这里只负责「循环调仓 + 统计」。实盘选股调的是同一个
    pick()，所以回测和每天选出来的票是同一套规则。

    返回 [(交易日, 期收益, 有效票数, 缺数据票数), ...]
    """
    dlist = ds.dates
    hold = int(cfg["hold_days"])
    n = int(cfg["top_n"])
    filters = cfg.get("filters")
    groups = ds.groups
    periods = []
    for i in range(0, len(dlist) - hold - 1, hold):
        t = dlist[i]
        top = pk.pick(groups[t], strategy, filters, n)
        if len(top) == 0:
            continue
        r = top["fwd"].dropna()
        if len(r) < max(1, n - 2):   # 允许个别停牌缺数据，但至少要有大部分
            continue
        periods.append((t, float(r.mean()), len(r), n - len(r)))
    return periods


# ============================ 评估 ============================
def mdd(nav):
    """最大回撤（%）。nav 为净值序列。"""
    if len(nav) == 0:
        return 0.0
    return float((nav / nav.cummax() - 1).min() * 100)


_mdd = mdd          # 兼容旧名（tests / legacy）


def equity(periods, cfg):
    """按调仓期滚动出净值曲线：[{d, v}]，首个点是本金。"""
    cap = float(cfg["capital"])
    out = [{"d": periods[0][0] if periods else cfg["start"], "v": round(cap, 2)}]
    for t, ret, _n, _miss in periods:
        cap *= 1 + ret - cfg["cost"]
        out.append({"d": t, "v": round(cap, 2)})
    return out


def by_year(periods, cfg):
    """分年汇总：{year: {n, ret, mdd}}，ret 为扣成本后的区间累计收益（比例）。"""
    buckets = {}
    for t, ret, _n, _miss in periods:
        buckets.setdefault(t[:4], []).append(ret)
    out = {}
    for y, rr in sorted(buckets.items()):
        net = np.asarray(rr) - cfg["cost"]
        curve = np.cumprod(1 + net)
        out[y] = {"n": len(rr),
                  "ret": float(curve[-1] - 1),
                  "mdd": float((curve / np.maximum.accumulate(curve) - 1).min())}
    return out


def evaluate(periods, cfg):
    """汇总指标。收益类字段为**百分数**（-12.3 表示 -12.3%）。"""
    ret = pd.Series([p[1] for p in periods], dtype="float64")
    if len(ret) == 0:
        return dict(n=0, net_cum=0.0, ann=np.nan, mdd=0.0, win=0.0,
                    cap=float(cfg["capital"]), nan_cnt=0)
    net = ret - cfg["cost"]
    nav = (1 + net).cumprod()
    n_years = len(ret) * cfg["hold_days"] / 242.0
    net_cum = float(nav.iloc[-1] - 1)
    ann = (1 + net_cum) ** (1 / n_years) - 1 if net_cum > -1 and n_years > 0 else np.nan
    return dict(n=len(ret),
                net_cum=net_cum * 100,
                ann=ann * 100,
                mdd=mdd(nav),
                win=float((ret > 0).mean() * 100),
                cap=float(cfg["capital"] * nav.iloc[-1]),
                nan_cnt=sum(p[3] for p in periods))
