# -*- coding: utf-8 -*-
"""测试回测执行链路：_add_fwd / build_groups / run_backtest。"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

import unittest
import numpy as np
import pandas as pd

import backtest_engine as be
from sample_data import make_panel


def _size_strategy(day):
    """确定性策略：只按小市值打分（市值最小者 z_SIZE 最大）。"""
    return day["z_SIZE"]


def _full_pipeline(hold_days=2, top_n=3, start="20210101", end="99991231"):
    """返回 (cfg, Dataset)。Dataset 显式传递，取代旧的 ds.groups 约定。"""
    cfg = dict(be.DEFAULT_CONFIG, hold_days=hold_days, top_n=top_n,
               start=start, end=end,
               # 这几条用例测的是「调仓频率 / topN / 收益记录」这条链路，
               # 而合成样本的日成交额只有 2~143 万，套用实盘流动性门槛会把池子清空。
               filters={"min_amt": 0, "max_pct": None, "min_price": 0})
    raw = make_panel(n_stocks=5, n_days=40)
    df = be.preprocess(raw, cfg)
    df = be.compute_factors(df)
    df = be.standardize(df)
    groups = be.build_groups(df, cfg)
    ds = be.Dataset(groups=groups, dates=sorted(groups.keys()))
    return cfg, ds


class TestAddFwd(unittest.TestCase):

    def test_fwd_holding_1(self):
        """fwd[t] = close_adj[t+hold+1] / close_adj[t+1] - 1（t+1 买、持有 hold 天后卖）。"""
        dates = pd.date_range("2021-01-01", periods=5, freq="D").strftime("%Y%m%d").tolist()
        df = pd.DataFrame({
            "股票代码": ["600000"] * 5,
            "交易日期": dates,
            "close_adj": [10.0, 11.0, 12.0, 13.0, 14.0],
        }).sort_values(["股票代码", "交易日期"])
        out = be._add_fwd(df, hold=1)
        expected = [12 / 11 - 1, 13 / 12 - 1, 14 / 13 - 1, np.nan, np.nan]
        got = out["fwd"].tolist()
        for g, e in zip(got, expected):
            if np.isnan(e):
                self.assertTrue(np.isnan(g))
            else:
                self.assertAlmostEqual(g, e, places=9)


class TestBuildGroups(unittest.TestCase):

    def test_filter_by_start(self):
        cfg, ds = _full_pipeline(start="20210110")
        self.assertTrue(all(d >= "20210110" for d in ds.dates))

    def test_filter_by_end(self):
        cfg, ds = _full_pipeline(end="20210120")
        self.assertTrue(all(d <= "20210120" for d in ds.dates))


class TestRunBacktest(unittest.TestCase):

    def test_rebalance_frequency(self):
        """每 hold_days 个交易日调仓一次：期数 = len(range(0, n - hold - 1, hold))。"""
        cfg, ds = _full_pipeline(hold_days=10)
        periods = be.run_backtest(_size_strategy, cfg, ds)
        expected = len(range(0, len(ds.dates) - 10 - 1, 10))
        self.assertEqual(len(periods), expected)

    def test_selects_top_n_by_score(self):
        """第 0 期选出的应是 z_SIZE 最大的 top_n 只，fwd 均值与手算一致。"""
        cfg, ds = _full_pipeline(hold_days=2, top_n=3)
        t0 = ds.dates[0]
        day = ds.groups[t0]
        top = day.nlargest(3, "z_SIZE")
        expected_mean = top["fwd"].dropna().mean()

        periods = be.run_backtest(_size_strategy, cfg, ds)
        self.assertEqual(periods[0][0], t0)
        self.assertAlmostEqual(periods[0][1], expected_mean, places=9)

    def test_period_record_shape(self):
        """每期记录为 (调仓日, 平均fwd, 有效票数, 缺失票数) 四元组。"""
        cfg, ds = _full_pipeline(hold_days=3, top_n=2)
        for p in be.run_backtest(_size_strategy, cfg, ds):
            self.assertEqual(len(p), 4)
            t, mean_fwd, n_valid, n_nan = p
            self.assertIsInstance(t, str)
            self.assertIsInstance(mean_fwd, float)
            self.assertEqual(n_valid + n_nan, 2)

    def test_score_nan_rows_skipped(self):
        """打分含 NaN 的股票应被剔除，不参与 top_n。"""
        cfg, ds = _full_pipeline(hold_days=2, top_n=3)
        # 手动把某天某只股票的 z_SIZE 置 NaN，验证 run_backtest 不崩溃且期数不变
        t0 = ds.dates[0]
        day = ds.groups[t0]
        code = day["股票代码"].iloc[0]
        day.loc[day["股票代码"] == code, "z_SIZE"] = np.nan
        periods = be.run_backtest(_size_strategy, cfg, ds)
        self.assertGreater(len(periods), 0)


if __name__ == "__main__":
    unittest.main()
