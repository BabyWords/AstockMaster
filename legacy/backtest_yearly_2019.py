# -*- coding: utf-8 -*-
"""
逐年回测（2019~2026）：新策略「小市值反转 + 低波」vs 对照「小市值反转」
========================================================================
口径：持有20天、TOP5、股价≥2元、成本0.3%、每年独立10万本金（年初投10万、年末结算）。
数据：daily_full_2019_2026.csv（2019 起全样本）。
"""
import backtest_engine as be
import strategies  # noqa: F401

STRAT = {
    "小市值反转+低波(新)": lambda d: d["z_SIZE"] + d["z_REV20"] - d["z_VOL20"],
    "小市值反转(对照)":  lambda d: d["z_SIZE"] + d["z_REV20"],
}

YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]


def main():
    cfg = {**be.DEFAULT_CONFIG, "hold_days": 20, "start": "20190101"}
    print("[准备] 加载数据 + 因子（约 60 秒）...")
    be.load_all(cfg)
    print(f"[准备] 完成，区间 {cfg['_dlist'][0]} ~ {cfg['_dlist'][-1]}，共 {len(cfg['_dlist'])} 交易日\n")

    for name, fn in STRAT.items():
        print("=" * 70)
        print(f"【{name}】 持有20天 / TOP5 / 每年独立10万 / 成本0.3%")
        print("=" * 70)
        print(f"  {'年份':<6}{'累计收益':>10}{'10万→':>12}{'回撤':>8}{'胜率':>7}{'期数':>6}")
        print("  " + "-" * 50)
        total_profit = 0.0
        for y in YEARS:
            sub_dlist = [d for d in cfg["_dlist"] if d[:4] == y]
            if len(sub_dlist) == 0:
                continue
            sc = {**cfg, "_dlist": sub_dlist}
            periods = be.run_backtest(fn, sc)
            if not periods:
                print(f"  {y:<6}{'—':>10}{'—':>12}")
                continue
            r = be.evaluate(periods, sc)
            total_profit += r["cap"] - cfg["capital"]
            print(f"  {y:<6}{r['net_cum']:>+9.1f}%{r['cap']:>12,.0f}{r['mdd']:>+7.1f}%{r['win']:>6.0f}%{r['n']:>6}")
        print("  " + "-" * 50)
        print(f"  8年总盈亏(每年独立10万，不跨年复利): {total_profit:+,.0f} 元")
        print()


if __name__ == "__main__":
    main()
