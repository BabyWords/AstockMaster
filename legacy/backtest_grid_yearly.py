# -*- coding: utf-8 -*-
"""验证网格最优组合(止盈20%/无止损)的分年稳健性，判断是否过拟合。"""
import pandas as pd
import numpy as np
import backtest_engine as be
import strategies  # noqa: F401
from backtest_grid import load, run_dynamic


def year_table(periods, cfg):
    by_year = {}
    for p in periods:
        by_year.setdefault(p[0][:4], []).append(p[1])
    rows = []
    for y in sorted(by_year):
        rr = pd.Series(by_year[y])
        c = cfg["capital"]
        for x in rr:
            c *= 1 + x - cfg["cost"]
        m = ((1 + (rr - cfg["cost"])).cumprod() / (1 + (rr - cfg["cost"])).cumprod().cummax() - 1).min() * 100
        rows.append((y, len(rr), (c / cfg["capital"] - 1) * 100, m, (rr > 0).mean() * 100))
    return rows


if __name__ == "__main__":
    cfg = {**be.DEFAULT_CONFIG, "hold_days": 20, "start": "20190101"}
    print("[准备] 加载数据 + 因子（约 20 秒）...")
    cfg["_data"] = load(cfg)
    cfg["_dlist"] = sorted(cfg["_data"][0].keys())
    cfg["_dpos"] = {d: i for i, d in enumerate(cfg["_dlist"])}
    fn = be.STRATEGIES["小市值反转低波"]

    variants = [
        ("基准 无退出",             None, None),
        ("止盈20% 无止损(最优)",      0.20, None),
        ("止盈15% 无止损",           0.15, None),
        ("止盈20% 止损-10%",         0.20, -0.10),
    ]
    data = {}
    for name, tp, sl in variants:
        data[name] = year_table(run_dynamic(fn, cfg, tp, sl), cfg)

    print("\n分年对比（每年独立10万，扣成本0.3%）")
    print(f"{'年份':<6}" + "".join(f"{n:>20}" for n in data.keys()))
    print("-" * (6 + 20 * len(data)))
    for y in sorted({y for rows in data.values() for y, *_ in rows}):
        line = f"{y:<6}"
        for name in data:
            row = next((r for r in data[name] if r[0] == y), None)
            if row:
                line += f"{row[2]:>+19.1f}%"
            else:
                line += f"{'':>20}"
        print(line)

    print("\n各年份胜率")
    print(f"{'年份':<6}" + "".join(f"{n:>20}" for n in data.keys()))
    for y in sorted({y for rows in data.values() for y, *_ in rows}):
        line = f"{y:<6}"
        for name in data:
            row = next((r for r in data[name] if r[0] == y), None)
            line += f"{row[4]:>19.0f}%" if row else f"{'':>20}"
        print(line)

    # 汇总：累计（复利）
    print("\n全样本复利汇总（10万滚动）")
    for name, tp, sl in variants:
        periods = run_dynamic(fn, cfg, tp, sl)
        ret = pd.Series([p[1] for p in periods])
        net = ret - cfg["cost"]
        cap = cfg["capital"]
        for x in ret:
            cap *= 1 + x - cfg["cost"]
        mdd = ((1 + net).cumprod() / (1 + net).cumprod().cummax() - 1).min() * 100
        print(f"  {name:<22} 累计{(1+net).prod()*100-100:>+7.1f}%  回撤{mdd:>6.1f}%  10万→{cap:>10,.0f}")
