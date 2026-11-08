# -*- coding: utf-8 -*-
"""
动态退出回测：小市值反转低波 选股 + 止盈/止损/到期卖出
=====================================================
口径（无前视）：
  t 日收盘选股(打分取 top_n) → t+1 收盘买入(close_adj) → 自 t+2 起逐日检查：
    1. 止损优先：当日最低价 <= 买入价*(1+sl) → 按 sl 卖出
    2. 止盈：当日最高价 >= 买入价*(1+tp) → 按 tp 卖出
    3. 均未触发 → 持有到 t+1+hold 到期，按到期日收盘卖出
  每期(买卖一个完整循环)扣一次双边成本 cost，周期不重叠(每 hold 天选一次股)。

对比多组止盈/止损参数，看"涨了就走、跌了止损"相比固定 20 天到期是赚是亏。
"""
import pandas as pd
import numpy as np
import backtest_engine as be
import strategies  # 触发策略注册，noqa: F401


def load(cfg):
    raw = be._load_raw()
    df = be.preprocess(raw, cfg)
    df = be.compute_factors(df)
    df = be.standardize(df)
    df = df[(df["交易日期"] >= cfg["start"]) & (df["交易日期"] <= cfg["end"])]
    df = df.sort_values(["交易日期", "股票代码"])
    close = df.set_index(["交易日期", "股票代码"])["close_adj"].sort_index()
    high = df.set_index(["交易日期", "股票代码"])["high_adj"].sort_index()
    low = df.set_index(["交易日期", "股票代码"])["low_adj"].sort_index()
    groups = {t: g for t, g in df.groupby("交易日期", sort=False)}
    return groups, close, high, low


def run_dynamic(strategy_fn, cfg, tp=None, sl=None):
    groups, close, high, low = cfg["_data"]
    dlist = sorted(groups.keys())
    hold = cfg["hold_days"]
    n = cfg["top_n"]
    periods = []
    idxs = list(range(0, len(dlist) - hold - 1, hold))
    for i in idxs:
        t = dlist[i]
        day = groups[t]
        score = strategy_fn(day)
        day = day.assign(_score=pd.Series(score, index=day.index))
        day = day[day["_score"].notna()]
        if len(day) == 0:
            continue
        top = day.nlargest(n, "_score")
        codes = top["股票代码"].tolist()
        buy_day = dlist[i + 1]
        expire_day = dlist[i + 1 + hold]
        rets, holds = [], []
        for code in codes:
            try:
                buy = close.loc[(buy_day, code)]
            except KeyError:
                continue
            sell_ret, sell_day = None, expire_day
            # 逐日检查：买入次日 t+2 起，含到期日(最后一天无触发则收盘卖)
            for d in dlist[i + 2: i + 1 + hold + 1]:
                try:
                    h = high.loc[(d, code)]
                    l = low.loc[(d, code)]
                except KeyError:
                    continue
                if sl is not None and l <= buy * (1 + sl):
                    sell_ret, sell_day = sl, d
                    break
                if tp is not None and h >= buy * (1 + tp):
                    sell_ret, sell_day = tp, d
                    break
            if sell_ret is None:
                try:
                    sell_ret = close.loc[(expire_day, code)] / buy - 1.0
                except KeyError:
                    continue
            rets.append(float(sell_ret))
            holds.append(dlist.index(sell_day) - dlist.index(buy_day))
        if len(rets) >= max(1, n - 2):
            periods.append((t, float(np.mean(rets)), len(rets), n - len(rets), float(np.mean(holds))))
    return periods


def evaluate_dyn(periods, cfg):
    ret = pd.Series([p[1] for p in periods])
    net = ret - cfg["cost"]
    cap = cfg["capital"]
    for x in ret:
        cap *= 1 + x - cfg["cost"]
    nav = (1 + net).cumprod()
    mdd = (nav / nav.cummax() - 1).min() * 100
    total_days = sum(p[4] for p in periods)
    n_years = total_days / 242.0
    net_cum = (1 + net).prod() - 1
    ann = (1 + net_cum) ** (1 / n_years) - 1 if net_cum > -1 and n_years > 0 else np.nan
    win = (ret > 0).mean() * 100
    avg_hold = np.mean([p[4] for p in periods])
    return dict(n=len(ret), net_cum=net_cum * 100, ann=ann * 100, mdd=mdd,
                win=win, cap=cap, avg_hold=avg_hold)


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
        rows.append((y, len(rr), (c / cfg["capital"] - 1) * 100, (rr > 0).mean() * 100))
    return rows


if __name__ == "__main__":
    cfg = {**be.DEFAULT_CONFIG, "hold_days": 20, "start": "20190101"}
    print("[准备] 加载数据 + 因子（约 20 秒）...")
    cfg["_data"] = load(cfg)
    fn = be.STRATEGIES["小市值反转低波"]

    variants = [
        ("基准 · 到期20天卖",            None,    None),
        ("+3%止盈 / -8%止损",            0.03,   -0.08),
        ("+5%止盈 / -8%止损",            0.05,   -0.08),
        ("+10%止盈 / -8%止损",           0.10,   -0.08),
        ("仅 +3%止盈",                   0.03,    None),
        ("仅 +5%止盈",                   0.05,    None),
        ("仅 -8%止损",                    None,   -0.08),
        ("仅 -5%止损",                    None,   -0.05),
    ]

    print("\n" + "=" * 96)
    print(f"动态退出回测 · 小市值反转低波 · TOP{cfg['top_n']} · 到期{cfg['hold_days']}天 · 成本{cfg['cost']*100:.1f}% · 2019起")
    print("=" * 96)
    header = f"{'方案':<22}{'期数':>5}{'10万→':>11}{'累计':>9}{'年化':>8}{'回撤':>8}{'胜率':>7}{'均持仓天':>9}"
    print(header)
    print("-" * 96)
    all_periods = {}
    for name, tp, sl in variants:
        periods = run_dynamic(fn, cfg, tp, sl)
        all_periods[name] = periods
        r = evaluate_dyn(periods, cfg)
        print(f"{name:<22}{r['n']:>5}{r['cap']:>11,.0f}{r['net_cum']:>+8.1f}%"
              f"{r['ann']:>+7.2f}%{r['mdd']:>+7.1f}%{r['win']:>6.0f}%{r['avg_hold']:>8.1f}天")

    # 分年对比：基准 vs 用户方案(+3%/-8%)
    print("\n" + "=" * 96)
    print("分年对比（每年独立10万，扣成本）")
    print("=" * 96)
    base = all_periods["基准 · 到期20天卖"]
    alt = all_periods["+3%止盈 / -8%止损"]
    yb = {y: (n, r, w) for y, n, r, w in year_table(base, cfg)}
    ya = {y: (n, r, w) for y, n, r, w in year_table(alt, cfg)}
    print(f"{'年份':<6}{'基准期数':>7}{'基准收益':>11}{'基准胜率':>9}{'止盈止损期数':>11}{'止盈止损收益':>13}{'止盈止损胜率':>11}")
    print("-" * 96)
    for y in sorted(set(yb) | set(ya)):
        b = yb.get(y, (0, 0, 0)); a = ya.get(y, (0, 0, 0))
        print(f"{y:<6}{b[0]:>7}{b[1]:>+10.1f}%{b[2]:>8.0f}%{a[0]:>11}{a[1]:>+12.1f}%{a[2]:>10.0f}%")
    print()
