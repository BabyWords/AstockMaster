# -*- coding: utf-8 -*-
"""
持有期对比：10天 vs 20天（一次加载数据，复用因子）
==================================================
回答用户"试算20天"：把持有期从10天拉长到20天，看收益/回撤/成本如何变化。
"""
import backtest_engine as be
import strategies  # noqa: F401


def main():
    cfg = {**be.DEFAULT_CONFIG}

    print("[准备] 加载数据 + 因子（约 50 秒）...")
    raw = be._load_raw()
    df = be.preprocess(raw, cfg)
    df = be.compute_factors(df)
    df = be.standardize(df)
    print("[准备] 完成，开始回测\n")

    for hold in [10, 20]:
        c = {**cfg, "hold_days": hold}
        groups = be.build_groups(df, c)
        c["_groups"] = groups
        c["_dlist"] = sorted(groups.keys())
        for nm in ["纯小市值", "小市值反转"]:
            periods = be.run_backtest(be.STRATEGIES[nm], c)
            r = be.evaluate(periods, c)
            be.print_report(nm, c, periods, r)


if __name__ == "__main__":
    main()
