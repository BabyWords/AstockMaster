# -*- coding: utf-8 -*-
"""测试 preprocess：过滤 + 前复权。"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                      # tests/（import sample_data）
sys.path.insert(0, os.path.join(_HERE, ".."))  # 回测根（import backtest_engine）

import unittest
import numpy as np
import pandas as pd

import backtest_engine as be
from sample_data import make_dirty_panel


class TestPreprocess(unittest.TestCase):

    def setUp(self):
        self.cfg = dict(be.DEFAULT_CONFIG)  # min_price 默认 2.0

    def _codes(self):
        return set(be.preprocess(make_dirty_panel(), self.cfg)["股票代码"])

    def test_keep_clean_stocks(self):
        codes = self._codes()
        self.assertIn("600000", codes)
        self.assertIn("000001", codes)

    def test_filter_st(self):
        self.assertNotIn("600001", self._codes())   # 名称含 ST

    def test_filter_delist(self):
        self.assertNotIn("600002", self._codes())   # 名称含 退

    def test_filter_code_prefix(self):
        self.assertNotIn("830001", self._codes())   # 北交所/非沪深代码

    def test_filter_min_price(self):
        self.assertNotIn("600003", self._codes())   # 收盘价 1.5 < 2.0

    def test_dropna_adjust_factor(self):
        self.assertNotIn("600004", self._codes())   # 复权因子 NaN

    def test_close_adj_forward_adjustment(self):
        """前复权公式：close_adj = 收盘价 × 复权因子 ÷ 基准因子（该股复权因子末值）。"""
        dates = pd.date_range("2021-01-01", periods=3, freq="D").strftime("%Y%m%d").tolist()
        df = pd.DataFrame({
            "股票代码": ["600000"] * 3,
            "股票名称": ["测试"] * 3,
            "交易日期": dates,
            "收盘价（元）": [10.0, 11.0, 12.0],
            "复权因子": [1.0, 1.1, 1.2],
            "流通市值（万元）": [10000.0] * 3,
            "换手率（%）": [5.0] * 3,
            "市盈率（TTM）": [20.0] * 3,
            "市净率": [2.0] * 3,
            "股息率（TTM）（%）": [1.0] * 3,
            "量比": [1.0] * 3,
        })
        out = be.preprocess(df, self.cfg).sort_values("交易日期")
        bf = 1.2  # 该股复权因子末值
        expected = [10 * 1.0 / bf, 11 * 1.1 / bf, 12 * 1.2 / bf]
        got = out["close_adj"].tolist()
        for g, e in zip(got, expected):
            self.assertAlmostEqual(g, e, places=6)
        # 基准日（最后一天）的前复权价应等于原始收盘价
        self.assertAlmostEqual(got[-1], 12.0, places=6)

    def test_min_price_zero_disables_filter(self):
        """min_price=0 时不过滤低价股。"""
        cfg = dict(self.cfg, min_price=0.0)
        codes = set(be.preprocess(make_dirty_panel(), cfg)["股票代码"])
        self.assertIn("600003", codes)


if __name__ == "__main__":
    unittest.main()
