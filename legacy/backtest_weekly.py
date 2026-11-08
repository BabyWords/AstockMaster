# -*- coding: utf-8 -*-
"""
周度回测：周五收盘选股 → 下周一收盘买入 → 下周五收盘卖出（周末空仓）
=====================================================================
对比"持有10天"的滚动调仓，回答用户"能不能周一买、周五卖"。

口径（无前视）：
  - 每周最后一个交易日（通常周五）收盘选股，按策略打分取前 top_n 只
  - 下一周第一个交易日（通常周一）收盘买入
  - 下一周最后一个交易日（通常周五）收盘卖出
  - 周末空仓；收益 = 卖出收盘价 / 买入收盘价 - 1
成本：每期双边扣 cost（默认 0.3%），每周一期，频率是10天调仓的约 2 倍。

用法：
  python backtest_weekly.py                 # 跑纯小市值 + 小市值反转 周度 vs 10天 对比
  python backtest_weekly.py -n 5 -price 2 --start 20210101
"""
import sys
import pandas as pd
import numpy as np

import backtest_engine as be
import strategies  # noqa: F401  触发策略注册


# ----------------------------- 周度执行 -----------------------------
def run_weekly(strategy, cfg):
    groups = cfg["_groups"]
    dlist = sorted(groups.keys())
    n = cfg["top_n"]

    # 每个交易日 -> (iso年, iso周, 星期几)
    dts = [pd.Timestamp(d) for d in dlist]
    year = np.array([d.isocalendar()[0] for d in dts])
    week = np.array([d.isocalendar()[1] for d in dts])
    wday = np.array([d.weekday() for d in dts])   # 0=周一 ... 4=周五
    dd = pd.DataFrame({"d": dlist, "year": year, "week": week, "wday": wday})
    gb = dd.groupby(["year", "week"], sort=True)
    first = gb["d"].first()   # 每周第一个交易日（周一，节假日顺延）
    last = gb["d"].last()     # 每周最后一个交易日（周五，节假日提前）
    keys = sorted(gb.groups.keys())

    periods = []
    for wi in range(len(keys) - 1):
        sel_day = last.iloc[wi]          # 本周最后一个交易日收盘选股
        buy_day = first.iloc[wi + 1]     # 下周一收盘买入
        sell_day = last.iloc[wi + 1]     # 下周五收盘卖出
        if buy_day == sell_day:          # 下周只有 1 个交易日，跳过
            continue
        day = groups[sel_day]
        score = strategy(day)
        s = pd.Series(score, index=day.index)
        s = s[s.notna()]
        if len(s) == 0:
            continue
        top = s.nlargest(n)
        codes = day.loc[top.index, "股票代码"].tolist()
        buy = groups[buy_day].set_index("股票代码")["close_adj"]
        sell = groups[sell_day].set_index("股票代码")["close_adj"]
        bp = buy.reindex(codes)
        sp = sell.reindex(codes)
        valid = bp.notna() & sp.notna()
        if int(valid.sum()) < max(1, n - 2):
            continue
        ret = sp[valid] / bp[valid] - 1.0
        periods.append((buy_day, float(ret.mean()), int(valid.sum()), n - int(valid.sum())))
    return periods


# ----------------------------- 评估 -----------------------------
def _mdd(nav):
    return (nav / nav.cummax() - 1).min() * 100


def evaluate_weekly(periods, cfg):
    ret = pd.Series([p[1] for p in periods])
    net = ret - cfg["cost"]
    cap = cfg["capital"]
    for x in ret:
        cap *= 1 + x - cfg["cost"]
    nav = (1 + net).cumprod()
    mdd = _mdd(nav)
    n = len(ret)
    net_cum = (1 + net).prod() - 1
    ann = (1 + net_cum) ** (52.0 / n) - 1 if net_cum > -1 and n > 0 else np.nan
    win = (ret > 0).mean() * 100
    return dict(n=n, net_cum=net_cum * 100, ann=ann * 100, mdd=mdd, win=win, cap=cap)


def print_weekly(name, cfg, periods, r, tag):
    print("\n" + "=" * 82)
    print(f"【{tag} · {name}】 TOP{cfg['top_n']} / 股价≥{cfg['min_price']:.0f}元 / 成本{cfg['cost']*100:.1f}%")
    print("=" * 82)
    print(f"  期数 {r['n']:>4}   10万→{r['cap']:>12,.0f}   "
          f"累计 {r['net_cum']:>+8.1f}%   年化 {r['ann']:>+6.2f}%")
    print(f"  期胜率 {r['win']:>4.0f}%   最大回撤 {r['mdd']:>7.1f}%")
    # 分年
    by_year = {}
    for p in periods:
        by_year.setdefault(p[0][:4], []).append(p[1])
    print("  " + "-" * 60)
    print(f"  {'年份':<6}{'期数':>5}{'收益(扣成本)':>14}{'胜率':>8}")
    for y in sorted(by_year):
        rr = pd.Series(by_year[y])
        c = cfg["capital"]
        for x in rr:
            c *= 1 + x - cfg["cost"]
        print(f"  {y:<6}{len(rr):>5}{(c/cfg['capital']-1)*100:>+13.1f}%{(rr>0).mean()*100:>7.0f}%")
    print()


def main():
    overrides = be._parse_args(sys.argv[1:])[1]
    cfg = {**be.DEFAULT_CONFIG, **overrides}

    print("[准备] 加载数据 + 因子（约 50 秒，含均线信号）...")
    be.load_all(cfg)
    print(f"[准备] 完成，{len(cfg['_dlist'])} 个交易日，区间 {cfg['_dlist'][0]} ~ {cfg['_dlist'][-1]}")

    names = ["纯小市值", "小市值反转"]
    for nm in names:
        fn = be.STRATEGIES[nm]

        # 周度：周一买、周五卖
        pw = run_weekly(fn, cfg)
        rw = evaluate_weekly(pw, cfg)
        print_weekly(nm, cfg, pw, rw, "周度(周一买周五卖)")

        # 对照：10天滚动调仓（现有基准）
        pd10 = be.run_backtest(fn, cfg)
        r10 = be.evaluate(pd10, cfg)
        be.print_report(nm, cfg, pd10, r10)


if __name__ == "__main__":
    main()
