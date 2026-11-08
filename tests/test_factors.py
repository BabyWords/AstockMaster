# -*- coding: utf-8 -*-
"""测试 compute_factors（因子计算）与 standardize（横截面标准化）。"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

import unittest
import numpy as np
import pandas as pd

import backtest_engine as be
from sample_data import make_panel


class TestComputeFactors(unittest.TestCase):

    def setUp(self):
        self.cfg = dict(be.DEFAULT_CONFIG)
        raw = make_panel(n_stocks=5, n_days=40)
        self.df = be.preprocess(raw, self.cfg)
        self.df = be.compute_factors(self.df)

    def test_size_is_negative_log_marketcap(self):
        expected = -np.log(self.df["流通市值（万元）"].clip(lower=1))
        np.testing.assert_allclose(self.df["SIZE"], expected, rtol=1e-12)

    def test_rev20_equals_negative_pct_change_20(self):
        g = self.df.groupby("股票代码", sort=False)["close_adj"]
        expected = -g.pct_change(20)
        np.testing.assert_allclose(self.df["REV20"], expected, equal_nan=True)

    def test_rev5_and_rev60(self):
        g = self.df.groupby("股票代码", sort=False)["close_adj"]
        np.testing.assert_allclose(self.df["REV5"], -g.pct_change(5), equal_nan=True)
        np.testing.assert_allclose(self.df["REV60"], -g.pct_change(60), equal_nan=True)

    def test_mom20_is_negative_rev20(self):
        np.testing.assert_allclose(self.df["MOM20"], -self.df["REV20"], equal_nan=True)

    def test_factor_columns_exist(self):
        for c in ["SIZE", "REV5", "REV20", "REV60", "MOM20", "VOL20",
                  "TURN", "PB", "PE", "DIV"]:
            self.assertIn(c, self.df.columns)

    def test_extended_factor_columns_exist(self):
        for c in ["LB", "TURN_STD20", "MAXUP20", "MAXDN20", "NEWHIGH20", "MA_GAP"]:
            self.assertIn(c, self.df.columns)

    def test_price_volume_factor_columns_exist(self):
        for c in ["AMT", "AMT20", "VOL_RATIO", "PCT", "GAP", "TAIL", "IS_YANG"]:
            self.assertIn(c, self.df.columns)

    def test_lb_equals_liangbi(self):
        np.testing.assert_allclose(self.df["LB"], self.df["量比"],
                                   rtol=1e-12, equal_nan=True)

    def test_newhigh20_has_values_after_warmup(self):
        """NEWHIGH20 = 收盘/前20日最高价(不含当天)-1，前10天NaN(需滚动历史)，之后有值。"""
        for code, g in self.df.groupby("股票代码"):
            nh = g["NEWHIGH20"]
            self.assertTrue(nh.iloc[:10].isna().all(), f"{code} 前10天应NaN")
            self.assertTrue(nh.iloc[15:].notna().all(), f"{code} 第15天后应有值")

    def test_maxdn20_nonpositive(self):
        """MAXDN20 = 20日最大单日跌幅，取 ret1 的 rolling min，应 <= 0。"""
        self.assertTrue((self.df["MAXDN20"].dropna() <= 1e-9).all())

    def test_vol_ratio_equals_amt_over_amt20(self):
        expected = self.df["成交额（万元）"] / self.df["AMT20"]
        np.testing.assert_allclose(self.df["VOL_RATIO"], expected, rtol=1e-9, equal_nan=True)

    def test_vol20_nonnegative(self):
        self.assertTrue((self.df["VOL20"].dropna() >= 0).all())


class TestStandardize(unittest.TestCase):

    def setUp(self):
        self.cfg = dict(be.DEFAULT_CONFIG)
        raw = make_panel(n_stocks=5, n_days=40)
        self.df = be.preprocess(raw, self.cfg)
        self.df = be.compute_factors(self.df)
        self.df = be.standardize(self.df)

    def test_zscore_matches_manual(self):
        """z = (x - mean) / std，按交易日横截面手算对比。"""
        d = self.df["交易日期"].iloc[25]
        sub = self.df[self.df["交易日期"] == d]
        m = sub["SIZE"].mean()
        s = sub["SIZE"].std()
        expected = (sub["SIZE"] - m) / s
        np.testing.assert_allclose(sub["z_SIZE"], expected, rtol=1e-12)

    def test_zscore_mean_zero_std_one(self):
        """标准化后每期截面均值≈0、标准差≈1（排除 REV20 前 20 天的 NaN）。"""
        for d, g in self.df.groupby("交易日期"):
            z = g["z_REV20"].dropna()
            if len(z) < 2:
                continue
            self.assertAlmostEqual(z.mean(), 0.0, places=9)
            self.assertAlmostEqual(z.std(), 1.0, places=9)

    def test_constant_factor_yields_nan(self):
        """某因子在某天全部相同 → std=0 → z 值为 NaN（replace 0→NaN）。"""
        df = self.df.copy()
        df.loc[df["交易日期"] == df["交易日期"].iloc[0], "TURN"] = 7.0
        df = be.standardize(df)
        d = df["交易日期"].iloc[0]
        sub = df[df["交易日期"] == d]
        self.assertTrue(sub["z_TURN"].isna().all())


if __name__ == "__main__":
    unittest.main()
