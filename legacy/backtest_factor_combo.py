# -*- coding: utf-8 -*-
"""
多因子组合回测：小市值(SIZE) + 反转(REV)
================================================================
基于单因子分组结果，SIZE(+1.94%/月) 和 REV(+1.77%/月) 是唯二正向因子。
这里把两者 Z-score 标准化后等权组合，买前10%等权篮子，月度调仓(20日)。
对比：纯SIZE组合 vs SIZE+REV组合 vs 全市场等权基准。
================================================================
"""
import os
import time
import pandas as pd
import numpy as np

OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = os.path.join(OUT, "daily_full_2025_2026.csv")

COLS = ["交易日期", "股票代码", "股票名称", "收盘价（元）", "复权因子",
        "换手率（%）", "市盈率（TTM）", "股息率（TTM）（%）", "流通市值（万元）"]


def load_prep():
    df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["收盘价（元）", "复权因子", "换手率（%）", "市盈率（TTM）",
              "股息率（TTM）（%）", "流通市值（万元）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）"])
    df = df.sort_values(["股票代码", "交易日期"])
    base = df.groupby("股票代码")["复权因子"].last().rename("base_factor")
    df = df.merge(base, on="股票代码", how="left")
    df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["base_factor"]
    g = df.groupby("股票代码", sort=False)
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
    df["REV"] = -g["close_adj"].pct_change(20)
    df["next20"] = g["close_adj"].transform(lambda s: s.shift(-20) / s - 1.0)
    return df


def zscore(s):
    m = s.mean()
    std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - m) / std


def run_combo(df, factor_cols, name):
    dates = sorted(df["交易日期"].unique())
    rebal = dates[::20]
    rows = []
    for t in rebal:
        sub = df[df["交易日期"] == t].dropna(subset=factor_cols + ["next20"]).copy()
        if len(sub) < 50:
            continue
        # 横截面 Z-score
        score = pd.Series(0.0, index=sub.index)
        for f in factor_cols:
            score = score + zscore(sub[f])
        sub["score"] = score
        sub = sub.sort_values("score", ascending=False)
        top_n = max(1, int(len(sub) * 0.10))
        top = sub.head(top_n)
        rows.append({"date": t, "ret": top["next20"].mean(), "n": len(top)})
    r = pd.DataFrame(rows)
    return r


def stats(r, bench_r, name):
    r = r.sort_values("date").reset_index(drop=True)
    r["cum"] = (1 + r["ret"]).cumprod()
    total = r["cum"].iloc[-1] - 1
    months = len(r)
    ann = (1 + r["ret"]).prod() ** (12 / months) - 1
    win = (r["ret"] > 0).mean() * 100
    merged = r.merge(bench_r.rename(columns={"ret": "bench_ret"}), on="date", how="inner")
    excess = merged["ret"] - merged["bench_ret"]
    ex_win = (excess > 0).mean() * 100
    mdd = (r["cum"] / r["cum"].cummax() - 1).min() * 100
    print(f"\n=== {name} ===")
    print(f"  调仓期数: {months}  平均持仓: {r['n'].mean():.0f} 只")
    print(f"  平均月收益: {r['ret'].mean()*100:+.3f}%")
    print(f"  年化收益: {ann*100:+.2f}%")
    print(f"  累计收益: {total*100:+.2f}%")
    print(f"  月度胜率: {win:.0f}%")
    print(f"  超额(相对基准): 月均 {excess.mean()*100:+.3f}%  跑赢占比 {ex_win:.0f}%")
    print(f"  最大回撤: {mdd:.2f}%")
    return r


def main():
    t0 = time.time()
    df = load_prep()
    print(f"[数据] {len(df)} 行", flush=True)

    dates = sorted(df["交易日期"].unique())
    rebal = dates[::20]
    bench_rows = [df[df["交易日期"] == t]["next20"].mean() for t in rebal]
    bench = pd.DataFrame({"date": rebal, "ret": bench_rows}).dropna()

    r_size = run_combo(df, ["SIZE"], "组合A：纯小市值")
    r_both = run_combo(df, ["SIZE", "REV"], "组合B：小市值+反转")

    stats(r_size, bench, "组合A：纯小市值(前10%)")
    stats(r_both, bench, "组合B：小市值+反转(前10%)")

    print(f"\n[基准] 全市场等权 月均 {bench['ret'].mean()*100:+.3f}%  累计 {(1+bench['ret']).prod()-1:+.2f}%")

    # 按月对比
    print("\n[按月收益对比]")
    cmp = bench[["date", "ret"]].rename(columns={"ret": "基准"})
    cmp = cmp.merge(r_size[["date", "ret"]].rename(columns={"ret": "小市值"}), on="date", how="left")
    cmp = cmp.merge(r_both[["date", "ret"]].rename(columns={"ret": "小市值+反转"}), on="date", how="left")
    cmp["date"] = cmp["date"].str[:6]
    print(cmp.set_index("date").mul(100).round(2).to_string())

    print(f"\n总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
