# -*- coding: utf-8 -*-
"""测试策略注册表、策略函数返回契约、命令行参数解析。"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

import unittest
import numpy as np
import pandas as pd

import backtest_engine as be
import strategies  # noqa: F401  触发策略注册
from sample_data import make_panel


def _make_day():
    """构造一个含全部 z_ 因子的单日横截面。"""
    raw = make_panel(n_stocks=5, n_days=30)
    cfg = dict(be.DEFAULT_CONFIG)
    df = be.preprocess(raw, cfg)
    df = be.compute_factors(df)
    df = be.standardize(df)
    d = df["交易日期"].iloc[25]
    return df[df["交易日期"] == d]


class TestRegister(unittest.TestCase):

    def test_builtin_strategies_registered(self):
        for name in ["小市值反转", "纯小市值", "纯反转", "小市值反转低波", "等权基准"]:
            self.assertIn(name, be.STRATEGIES)

    def test_register_decorator(self):
        @be.register("__测试策略__")
        def f(day):
            return day["z_SIZE"]
        self.assertIn("__测试策略__", be.STRATEGIES)
        self.assertIs(be.STRATEGIES["__测试策略__"], f)
        # 清理，避免污染其他测试
        del be.STRATEGIES["__测试策略__"]


class TestStrategyContract(unittest.TestCase):

    def test_strategies_return_series_matching_index(self):
        day = _make_day()
        for name, fn in be.STRATEGIES.items():
            score = fn(day)
            self.assertIsInstance(score, pd.Series, f"{name} 应返回 Series")
            self.assertEqual(len(score), len(day), f"{name} 长度应与 day 一致")
            self.assertTrue(score.index.equals(day.index), f"{name} 的 index 应与 day 一致")
            self.assertFalse(score.isna().all(), f"{name} 不应全为 NaN")


class TestParseArgs(unittest.TestCase):

    def test_no_args(self):
        name, ov = be._parse_args([])
        self.assertIsNone(name)
        self.assertEqual(ov, {})

    def test_strategy_name(self):
        name, ov = be._parse_args(["小市值反转"])
        self.assertEqual(name, "小市值反转")

    def test_top_n(self):
        _, ov = be._parse_args(["小市值反转", "-n", "7"])
        self.assertEqual(ov["top_n"], 7)

    def test_hold_days(self):
        _, ov = be._parse_args(["小市值反转", "-hold", "15"])
        self.assertEqual(ov["hold_days"], 15)

    def test_min_price_and_cost(self):
        _, ov = be._parse_args(["x", "-price", "3", "-cost", "0.005"])
        self.assertEqual(ov["min_price"], 3.0)
        self.assertEqual(ov["cost"], 0.005)

    def test_start_separate_form(self):
        _, ov = be._parse_args(["小市值反转", "--start", "20260101"])
        self.assertEqual(ov["start"], "20260101")

    def test_start_equals_form(self):
        """--start=YYYYMMDD 形式（曾因吞掉后续参数而有 bug）。"""
        _, ov = be._parse_args(["小市值反转", "--start=20260101"])
        self.assertEqual(ov["start"], "20260101")

    def test_start_equals_form_does_not_swallow_next_arg(self):
        name, ov = be._parse_args(["小市值反转", "--start=20260101", "-n", "3"])
        self.assertEqual(ov["start"], "20260101")
        self.assertEqual(ov["top_n"], 3)

    def test_start_without_value(self):
        """--start 位于末尾无值时不应抛异常。"""
        name, ov = be._parse_args(["小市值反转", "--start"])
        self.assertEqual(name, "小市值反转")
        self.assertNotIn("start", ov)


if __name__ == "__main__":
    unittest.main()
