# -*- coding: utf-8 -*-
"""测试评估函数：_mdd（最大回撤）与 evaluate（复利/年化/胜率）。"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

import unittest
import numpy as np
import pandas as pd

import backtest_engine as be


class TestMdd(unittest.TestCase):

    def test_max_drawdown(self):
        nav = pd.Series([1.0, 1.2, 0.9, 1.5, 1.0])
        # cummax=[1.0,1.2,1.2,1.5,1.5]; dd=[0,0,-0.25,0,-0.3333]
        self.assertAlmostEqual(be._mdd(nav), -33.3333, places=3)

    def test_monotonic_nav_zero_drawdown(self):
        nav = pd.Series([1.0, 1.1, 1.2, 1.3])
        self.assertAlmostEqual(be._mdd(nav), 0.0, places=9)

    def test_single_point(self):
        self.assertAlmostEqual(be._mdd(pd.Series([1.0])), 0.0, places=9)


class TestEvaluate(unittest.TestCase):

    def _cfg(self):
        return {"cost": 0.003, "capital": 100000.0, "hold_days": 10}

    def test_compounding_capital(self):
        """cap = capital × ∏(1 + ret - cost)。"""
        periods = [("20210101", 0.1, 5, 0), ("20210201", -0.05, 5, 0)]
        r = be.evaluate(periods, self._cfg())
        expected = 100000 * (1 + 0.1 - 0.003) * (1 - 0.05 - 0.003)
        self.assertAlmostEqual(r["cap"], expected, places=2)

    def test_win_rate(self):
        periods = [("20210101", 0.1, 5, 0), ("20210201", -0.05, 5, 0)]
        r = be.evaluate(periods, self._cfg())
        self.assertAlmostEqual(r["win"], 50.0, places=6)

    def test_net_cum_and_annualized(self):
        periods = [("20210101", 0.1, 5, 0), ("20210201", -0.05, 5, 0)]
        r = be.evaluate(periods, self._cfg())
        net = pd.Series([0.1, -0.05]) - 0.003
        net_cum = (1 + net).prod() - 1
        n_years = 2 * 10 / 242.0
        ann = (1 + net_cum) ** (1 / n_years) - 1
        self.assertAlmostEqual(r["net_cum"] / 100, net_cum, places=9)
        self.assertAlmostEqual(r["ann"] / 100, ann, places=9)

    def test_nan_count_aggregated(self):
        periods = [("20210101", 0.1, 4, 1), ("20210201", -0.05, 3, 2)]
        r = be.evaluate(periods, self._cfg())
        self.assertEqual(r["nan_cnt"], 3)

    def test_empty_periods(self):
        r = be.evaluate([], self._cfg())
        self.assertEqual(r["n"], 0)
        self.assertTrue(np.isnan(r["ann"]))


if __name__ == "__main__":
    unittest.main()
