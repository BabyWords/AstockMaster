# -*- coding: utf-8 -*-
"""
因子增量实验：能否靠加因子规避小市值反转的亏损年份？
====================================================
在基准 z_SIZE + z_REV20 上逐个叠加候选因子，持有20天，看分年（尤其亏损年）变化。
候选因子来自已有因子库：低波VOL20 / 低换手TURN / 低成交额AMT20 / 低量比LB / 低PB / 换手波动TURN_STD20 / 最大涨幅MAXUP20。
"""
import pandas as pd
import numpy as np
import backtest_engine as be
import strategies  # noqa: F401

VARIANTS = {
    "基准 z_SIZE+z_REV20":        lambda d: d["z_SIZE"] + d["z_REV20"],
    "+低波(-z_VOL20)":            lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_VOL20"],
    "+低换手(-z_TURN)":           lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_TURN"],
    "+低成交额(-z_AMT20)":        lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_AMT20"],
    "+低量比(-z_LB)":             lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_LB"],
    "+低PB(-z_PB)":               lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_PB"],
    "+低波+低换手":               lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_VOL20"] - d["z_TURN"],
    "v9完整7因子":                lambda d: (d["z_SIZE"] + d["z_REV20"] - d["z_MAXUP20"]
                                        - d["z_TURN_STD20"] - d["z_PB"] - d["z_LB"] - d["z_AMT20"]),
}


def yearly(periods, cfg):
    by_year = {}
    for p in periods:
        by_year.setdefault(p[0][:4], []).append(p[1])
    out = {}
    for y in sorted(by_year):
        rr = pd.Series(by_year[y])
        c = cfg["capital"]
        for x in rr:
            c *= 1 + x - cfg["cost"]
        out[y] = (c / cfg["capital"] - 1) * 100
    return out


def main():
    cfg = {**be.DEFAULT_CONFIG, "hold_days": 20}
    print("[准备] 加载数据 + 因子（约 50 秒）...")
    raw = be._load_raw()
    df = be.preprocess(raw, cfg)
    df = be.compute_factors(df)
    df = be.standardize(df)
    groups = be.build_groups(df, cfg)
    cfg["_groups"] = groups
    cfg["_dlist"] = sorted(groups.keys())
    print("[准备] 完成\n")

    years = ["2021", "2022", "2023", "2024", "2025", "2026"]
    header = f"{'变体':<26}{'累计':>9}{'回撤':>8}" + "".join(f"{y:>9}" for y in years)
    print(header)
    print("-" * len(header))

    for name, fn in VARIANTS.items():
        periods = be.run_backtest(fn, cfg)
        r = be.evaluate(periods, cfg)
        yv = yearly(periods, cfg)
        row = f"{name:<26}{r['net_cum']:>+8.1f}%{r['mdd']:>+7.1f}%"
        for y in years:
            v = yv.get(y, float('nan'))
            row += f"{v:>+8.1f}%" if not np.isnan(v) else f"{'—':>9}"
        print(row)

    print("\n说明：每年独立10万本金、扣成本0.3%、TOP5、股价≥2元、持有20天。")
    print("目标：找一个变体，让 2023(基准-35.1%) 亏损明显收窄，同时其他年份不大幅缩水。")


if __name__ == "__main__":
    main()
