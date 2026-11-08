# -*- coding: utf-8 -*-
"""
止盈/止损 网格搜索：小市值反转低波 选股 + 动态退出
=====================================================
在「到期20天卖」的动态退出框架下，网格扫描 tp(止盈) × sl(止损)，
输出累计收益矩阵 + 最大回撤矩阵，找历史最优组合。

口径与 backtest_dynamic_exit.py 完全一致：t+1收盘买入，t+2起用当日高/低价
判断（止损优先），未触发则到期收盘卖，每期扣双边成本 cost。
"""
import pandas as pd
import numpy as np
import backtest_engine as be
import strategies  # noqa: F401


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
    dlist = cfg["_dlist"]
    dpos = cfg["_dpos"]
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
            holds.append(dpos[sell_day] - dpos[buy_day])
        if len(rets) >= max(1, n - 2):
            periods.append((t, float(np.mean(rets)), len(rets), n - len(rets), float(np.mean(holds))))
    return periods


def metrics(periods, cfg):
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
    return dict(n=len(ret), net_cum=net_cum * 100, ann=ann * 100, mdd=mdd,
                win=win, cap=cap)


if __name__ == "__main__":
    cfg = {**be.DEFAULT_CONFIG, "hold_days": 20, "start": "20190101"}
    print("[准备] 加载数据 + 因子（约 20 秒）...")
    cfg["_data"] = load(cfg)
    cfg["_dlist"] = sorted(cfg["_data"][0].keys())
    cfg["_dpos"] = {d: i for i, d in enumerate(cfg["_dlist"])}
    fn = be.STRATEGIES["小市值反转低波"]

    TPs = [None, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]
    SLs = [None, -0.05, -0.08, -0.10, -0.15, -0.20, -0.30]

    # 预跑基准
    base = metrics(run_dynamic(fn, cfg, None, None), cfg)

    print(f"\n{'':>6}" + "".join(f"{('无' if s is None else f'{s*100:.0f}%'):>9}" for s in SLs) + f"{'':>3}回撤基准-41.0%")
    print(" 止损→  " + "".join(f"{'无' if s is None else f'{s*100:.0f}%':>9}" for s in SLs))
    print("止盈↓")
    results = {}
    for tp in TPs:
        row_ret, row_mdd = [], []
        for sl in SLs:
            periods = run_dynamic(fn, cfg, tp, sl)
            m = metrics(periods, cfg)
            results[(tp, sl)] = m
            row_ret.append(m["net_cum"])
            row_mdd.append(m["mdd"])
        label = "无" if tp is None else f"{tp*100:.0f}%"
        print(f"{label:>5} " + "".join(f"{r:>+8.1f}%" for r in row_ret))

    print("\n最大回撤矩阵（%）")
    for tp in TPs:
        label = "无" if tp is None else f"{tp*100:.0f}%"
        row = "".join(f"{results[(tp, sl)]['mdd']:>+8.1f}%" for sl in SLs)
        print(f"{label:>5} {row}")

    # 全局最优（累计收益最大）
    best = max(results.items(), key=lambda kv: kv[1]["net_cum"])
    (btp, bsl), bm = best
    print("\n" + "=" * 70)
    print(f"历史累计收益最高组合：止盈 {('无' if btp is None else f'{btp*100:.0f}%')} / "
          f"止损 {('无' if bsl is None else f'{bsl*100:.0f}%')}")
    print(f"  累计 {bm['net_cum']:+.1f}%  年化 {bm['ann']:+.2f}%  回撤 {bm['mdd']:.1f}%  "
          f"胜率 {bm['win']:.0f}%  10万→{bm['cap']:,.0f}")
    print(f"  （基准：累计 {base['net_cum']:+.1f}%  回撤 {base['mdd']:.1f}%）")
    print("=" * 70)
    print("\n注意：网格搜索的最优参数极易过拟合，单点最优 ≠ 样本外有效。")
    print("真正稳健的是『方向』：止盈越高越好（最好不设）、止损越宽越好。")
