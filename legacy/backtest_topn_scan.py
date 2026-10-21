# -*- coding: utf-8 -*-
"""
「小市值+反转」持有10天 · 选股数量扫描（TOP_N = 3 / 4 / 5 / 10）
========================================================================
口径与 backtest_2021_2026.py 完全一致，唯一变量 = 每期买入的股票数量 N。
- 因子：SIZE=-log(流通市值万元)、REV=-(近20日涨跌幅)，前复权
- 每日收盘横截面 Z-score，score = Z_SIZE + Z_REV，取前 N 只等权
- t日收盘选股 → t+1买入 → 持有10交易日 → t+11卖出（延迟买入，避前视）
- 每 10 个交易日调仓一次；成本每期 0.3%；满仓 100%（等权分 N 只）
"""
import time
import pandas as pd, numpy as np

OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = OUT + "/daily_full_2020_2026.csv"
COST = 0.003
CAPITAL = 100000.0
t0 = time.time()


def prep(df):
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
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


def run(df, dlist, n):
    idxs = list(range(0, len(dlist) - 11, 10))
    rows = []
    for i in idxs:
        t = dlist[i]
        sub = df[df["交易日期"] == t]
        top = sub.nsmallest(n, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < max(1, n - 2):   # 允许个别票停牌缺数据，但至少要有大部分
            continue
        rows.append((t, r.mean()))
    return rows


def summarize(rows, label):
    ret = pd.Series([x for _, x in rows])
    net = ret - COST
    net_cum = (1 + net).prod() - 1
    n_years = len(ret) * 10 / 242.0
    ann = (1 + net_cum) ** (1 / n_years) - 1 if net_cum > -1 and n_years > 0 else np.nan
    win = (ret > 0).mean() * 100
    nav = (1 + net).cumprod()
    mdd = (nav / nav.cummax() - 1).min() * 100
    cap = CAPITAL
    for x in ret:
        cap *= (1 + x - COST)
    print(f"{label:<28} 期数{len(ret):>4}  10万→{cap:>10,.0f}  {net_cum*100:>+8.1f}%  "
          f"年化{ann*100:>+6.2f}%  胜率{win:>4.0f}%  回撤{mdd:>7.1f}%")
    return dict(n=len(ret), net_cum=net_cum * 100, ann=ann * 100, win=win, mdd=mdd, cap=cap)


def main():
    df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    df = prep(df)
    df = add_factors(df)
    print(f"[数据] {len(df):,} 行，因子计算完成，耗时 {time.time()-t0:.0f}s\n")

    df_bt = df[df["交易日期"] >= "20210101"]
    dlist = sorted(df_bt["交易日期"].unique())
    print(f"[回测] 2021-01 ~ 2026-10，共 {len(dlist)} 交易日\n")

    print("=" * 100)
    print("【全样本 2021-2026 · 满仓等权，不同选股数对比】")
    print("=" * 100)
    for n in [3, 4, 5, 10]:
        rows = run(df_bt, dlist, n)
        summarize(rows, f"TOP {n} 只")

    print("\n" + "=" * 100)
    print("【分年度收益率（%）· 满仓等权】")
    print("=" * 100)
    header = f"{'年份':<6}" + "".join(f"{'TOP'+str(n):>14}" for n in [3, 4, 5, 10])
    print(header)
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        dy = sorted(df_bt[df_bt["交易日期"].str.startswith(y)]["交易日期"].unique())
        line = f"{y:<6}"
        for n in [3, 4, 5, 10]:
            r = run(df_bt, dy, n)
            ret = pd.Series([x for _, x in r])
            cap = CAPITAL
            for x in ret:
                cap *= (1 + x - COST)
            line += f"{(cap/CAPITAL-1)*100:>+13.1f}%"
        print(line)

    # 分年度回撤
    print("\n" + "=" * 100)
    print("【分年度最大回撤（%）· 满仓等权】")
    print("=" * 100)
    print(header)
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        dy = sorted(df_bt[df_bt["交易日期"].str.startswith(y)]["交易日期"].unique())
        line = f"{y:<6}"
        for n in [3, 4, 5, 10]:
            r = run(df_bt, dy, n)
            ret = pd.Series([x for _, x in r])
            nav = (1 + (ret - COST)).cumprod()
            mdd = (nav / nav.cummax() - 1).min() * 100
            line += f"{mdd:>+13.1f}%"
        print(line)

    print(f"\n[总耗时 {time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
