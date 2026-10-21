# -*- coding: utf-8 -*-
"""「股价≥2元」过滤下的分年度回测（TOP4/5/10 对比）"""
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
    return {t: g for t, g in sub.groupby("交易日期", sort=False)}


def run(groups, dlist, n):
    idxs = list(range(0, len(dlist) - 11, 10))
    rows = []
    for i in idxs:
        t = dlist[i]
        r = groups[t].nsmallest(n, "rank")["fwd10_lag"].dropna()
        if len(r) < max(1, n - 2):
            continue
        rows.append((t, r.mean()))
    return rows


def main():
    raw = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    df = add_factors(prep(raw, 2))
    groups = build_groups(df)
    dlist = sorted(groups.keys())
    print(f"[股价≥2元] {len(dlist)} 交易日（用时{time.time()-t0:.0f}s）\n")

    years = ["2021", "2022", "2023", "2024", "2025", "2026"]
    print("=" * 70)
    print("【分年度收益（每年独立10万本金，扣成本）· 股价≥2元】")
    print("=" * 70)
    header = f"{'年份':<6}" + "".join(f"{'TOP'+str(n):>14}" for n in [4, 5, 10])
    print(header)
    for y in years:
        dy = [t for t in dlist if t.startswith(y)]
        line = f"{y:<6}"
        for n in [4, 5, 10]:
            rows = run(groups, dy, n)
            cap = CAPITAL
            for _, x in rows:
                cap *= 1 + x - COST
            line += f"{(cap/CAPITAL-1)*100:>+13.1f}%"
        print(line)

    print("\n" + "=" * 70)
    print("【分年度最大回撤（%）· 股价≥2元】")
    print("=" * 70)
    print(header)
    for y in years:
        dy = [t for t in dlist if t.startswith(y)]
        line = f"{y:<6}"
        for n in [4, 5, 10]:
            rows = run(groups, dy, n)
            ret = pd.Series([x for _, x in rows])
            nav = (1 + (ret - COST)).cumprod()
            mdd = (nav / nav.cummax() - 1).min() * 100
            line += f"{mdd:>+13.1f}%"
        print(line)

    # 期胜率
    print("\n" + "=" * 70)
    print("【期胜率（%）· 股价≥2元】")
    print("=" * 70)
    print(header)
    for y in years:
        dy = [t for t in dlist if t.startswith(y)]
        line = f"{y:<6}"
        for n in [4, 5, 10]:
            rows = run(groups, dy, n)
            ret = pd.Series([x for _, x in rows])
            line += f"{(ret>0).mean()*100:>+13.0f}%"
        print(line)

    print(f"\n[总耗时 {time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
