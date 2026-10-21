# -*- coding: utf-8 -*-
"""
「小市值+反转」持有10天 · 修正版回测（低价股过滤 × 选股数扫描）—— 优化版
========================================================================
用 groupby 预分组替代逐日全表扫描，加速。
扫描：PRICE_MIN ∈ {0, 2, 3, 5} × N ∈ {3, 4, 5, 10}，全样本 2021-2026。
"""
import time
import pandas as pd, numpy as np

CACHE = "/Volumes/TOSHIBA/炒股/回测/daily_full_2020_2026.csv"
COST = 0.003
CAPITAL = 100000.0
t0 = time.time()


def prep(df, price_min):
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
    if price_min > 0:
        df = df[df["收盘价（元）"] >= price_min]
    df = df.sort_values(["股票代码", "交易日期"])
    base = df.groupby("股票代码")["复权因子"].last().rename("bf")
    df = df.merge(base, on="股票代码", how="left")
    df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]
    return df


def add_factors(df):
    g = df.groupby("股票代码", sort=False)
    df["REV"] = -g["close_adj"].pct_change(20)
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
    df["next_close"] = g["close_adj"].shift(-1)
    df["close_11"] = g["close_adj"].shift(-11)
    df["fwd10_lag"] = df["close_11"] / df["next_close"] - 1.0
    gd = df.groupby("交易日期")
    for f in ["SIZE", "REV"]:
        m = gd[f].transform("mean")
        s = gd[f].transform("std").replace(0, np.nan)
        df["z_" + f] = (df[f] - m) / s
    df["score"] = df["z_SIZE"] + df["z_REV"]
    df["rank"] = df.groupby("交易日期")["score"].rank(method="first", ascending=False)
    return df


def build_groups(df):
    sub = df[df["交易日期"] >= "20210101"][["交易日期", "rank", "fwd10_lag"]]
    groups = {t: g for t, g in sub.groupby("交易日期", sort=False)}
    dlist = sorted(groups.keys())
    return groups, dlist


def run(groups, dlist, n):
    idxs = list(range(0, len(dlist) - 11, 10))
    rows = []
    for i in idxs:
        t = dlist[i]
        top = groups[t].nsmallest(n, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < max(1, n - 2):
            continue
        rows.append((t, r.mean()))
    return rows


def main():
    raw = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    results = []

    for price_min in [0, 2, 3, 5]:
        df = add_factors(prep(raw.copy(), price_min))
        groups, dlist = build_groups(df)
        print(f"\n[股价>={price_min}元] {len(dlist)} 交易日（用时{time.time()-t0:.0f}s）")
        for n in [3, 4, 5, 10]:
            rows = run(groups, dlist, n)
            ret = pd.Series([x for _, x in rows])
            net = ret - COST
            cap = CAPITAL
            for x in ret:
                cap *= 1 + x - COST
            net_cum = (1 + net).prod() - 1
            nav = (1 + net).cumprod()
            mdd = (nav / nav.cummax() - 1).min() * 100
            win = (ret > 0).mean() * 100
            results.append(dict(pm=price_min, n=n, ret=net_cum * 100, mdd=mdd, cap=cap, win=win, cnt=len(ret)))
            print(f"  TOP{n:>2}: 期数{len(ret):>3}  10万→{cap:>10,.0f}  {net_cum*100:>+8.1f}%  胜率{win:>4.0f}%  回撤{mdd:>7.1f}%")
        del df, groups

    print("\n" + "=" * 100)
    print("【汇总：股价过滤 × 选股数 → 全样本累计(扣成本)/最大回撤】")
    print("=" * 100)
    print(f"{'':>12}", end="")
    for n in [3, 4, 5, 10]:
        print(f"{'TOP'+str(n):>22}", end="")
    print()
    for pm in [0, 2, 3, 5]:
        label = "无过滤" if pm == 0 else f"股价≥{pm}元"
        print(f"{label:>12}", end="")
        for n in [3, 4, 5, 10]:
            r = next(x for x in results if x["pm"] == pm and x["n"] == n)
            print(f"{r['ret']:>+10.1f}% /{r['mdd']:>+7.1f}%", end="")
        print()

    print(f"\n[总耗时 {time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
