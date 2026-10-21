# -*- coding: utf-8 -*-
"""
合成数据构造器 —— 单元测试专用，不依赖真实大缓存。

生成一个「多股票 × 多交易日」的面板，字段与真实缓存完全一致，
便于测试 preprocess / compute_factors / standardize / run_backtest 等核心函数。
"""
import pandas as pd
import numpy as np

# 与 backtest_engine.py 中 _load_raw 读取的字段保持一致
FIELDS = ["股票代码", "股票名称", "交易日期", "收盘价（元）", "复权因子",
          "流通市值（万元）", "换手率（%）", "市盈率（TTM）", "市净率",
          "股息率（TTM）（%）", "量比"]


def make_panel(n_stocks=5, n_days=40, start="2021-01-01", seed=42):
    """干净面板：n_stocks 只股票、每只 n_days 个连续交易日。

    价格用确定性随机游走（seed 固定），复权因子恒为 1（前复权不改变价格），
    流通市值按股票序号递增（用于验证 SIZE = -log(市值)）。
    """
    codes = ["600000", "000001", "300750", "600519", "002594"][:n_stocks]
    names = ["浦发银行", "平安银行", "宁德时代", "贵州茅台", "比亚迪"][:n_stocks]
    dates = pd.date_range(start, periods=n_days, freq="D").strftime("%Y%m%d").tolist()

    rng = np.random.default_rng(seed)
    rows = []
    for ci, code in enumerate(codes):
        price = 10.0 + ci * 5.0                     # 每只不同起点
        mktcap = float((ci + 1) * 10000)            # 万元，市值随 ci 递增
        for d in dates:
            price = price * (1 + rng.normal(0, 0.02))
            rows.append({
                "股票代码": code,
                "股票名称": names[ci],
                "交易日期": d,
                "收盘价（元）": round(float(price), 4),
                "复权因子": 1.0,
                "流通市值（万元）": mktcap,
                "换手率（%）": round(float(rng.uniform(0.5, 15)), 4),
                "市盈率（TTM）": round(float(rng.uniform(5, 100)), 4),
                "市净率": round(float(rng.uniform(0.5, 10)), 4),
                "股息率（TTM）（%）": round(float(rng.uniform(0, 8)), 4),
                "量比": round(float(rng.uniform(0.5, 3)), 4),
            })
    return pd.DataFrame(rows)


def make_dirty_panel(n_days=10):
    """含脏数据的面板：用于验证 preprocess 的过滤逻辑。

    混入：ST 股、退市股、非沪深代码、低价股（< min_price）、复权因子缺失股。
    每类各 1 只，外加 2 只干净股作为对照组。
    """
    dates = pd.date_range("2021-01-01", periods=n_days, freq="D").strftime("%Y%m%d").tolist()
    rows = []

    def add(code, name, price=10.0, factor=1.0, mktcap=10000.0):
        for d in dates:
            rows.append({
                "股票代码": code, "股票名称": name, "交易日期": d,
                "收盘价（元）": price, "复权因子": factor,
                "流通市值（万元）": mktcap,
                "换手率（%）": 5.0, "市盈率（TTM）": 20.0, "市净率": 2.0,
                "股息率（TTM）（%）": 1.0, "量比": 1.0,
            })

    add("600000", "干净A", price=10.0)          # 干净，保留
    add("000001", "干净B", price=12.0)          # 干净，保留
    add("600001", "ST风险", price=8.0)          # 含 ST，剔除
    add("600002", "退市股", price=9.0)          # 含 退，剔除
    add("830001", "北交所", price=10.0)         # 代码前缀不符，剔除
    add("600003", "低价股", price=1.5)          # 股价 < 2，剔除
    add("600004", "缺因子", price=10.0, factor=np.nan)  # 复权因子缺失，剔除

    return pd.DataFrame(rows)
