# -*- coding: utf-8 -*-
"""
10 万本金模拟：小市值+反转，前10只，持有10天轮换，从 2026-01 起
口径与 backtest_hold10.py 一致：t日收盘选股 → t+1日买入 → 持有10交易日 → t+11卖出（延迟买入避前视）
成本：每期一买一卖 0.3%
"""
import pandas as pd, numpy as np, time

CACHE = "daily_full_2022_2026.csv"
t0 = time.time()
df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str})
df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
df = df.sort_values(["股票代码", "交易日期"])

base = df.groupby("股票代码")["复权因子"].last().rename("bf")
df = df.merge(base, on="股票代码", how="left")
df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]

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

d2026 = sorted(df[df["交易日期"] >= "20260101"]["交易日期"].unique())
print(f"2026 区间: {d2026[0]} ~ {d2026[-1]}, 共 {len(d2026)} 个交易日")

COST = 0.003
CAPITAL = 100000.0
idxs = list(range(0, len(d2026) - 11, 10))

rows = []
for i in idxs:
    t = d2026[i]
    sub = df[df["交易日期"] == t]
    top = sub.nsmallest(10, "rank")
    r = top["fwd10_lag"].dropna()
    if len(r) < 5:
        continue
    rows.append({
        "期数": len(rows) + 1,
        "选股日": t,
        "前10只收益": r.mean(),
        "命中数": len(r),
        "股票": "/".join(top["股票名称"].astype(str).tolist()),
    })

rr = pd.DataFrame(rows)
print(f"调仓期数: {len(rr)}")

# 累积（扣成本）
cap_raw = CAPITAL
cap_net = CAPITAL
details = []
for _, row in rr.iterrows():
    r = row["前10只收益"]
    cap_raw *= (1 + r)
    cap_net *= (1 + r - COST)
    details.append((row["选股日"], r * 100, cap_net))

print(f"\n{'选股日':<10}{'期收益%':>9}{'扣成本后市值':>14}")
for d, r, cap in details:
    print(f"{d:<10}{r:>8.2f}%{cap:>13,.0f}")

raw_ret = cap_raw / CAPITAL - 1
net_ret = cap_net / CAPITAL - 1
print(f"\n=== 结果（10 万本金，2026-01 ~ {d2026[-1]}）===")
print(f"未扣成本: 期末 {cap_raw:,.0f} 元, 收益率 {raw_ret*100:+.1f}%")
print(f"扣成本0.3%/期: 期末 {cap_net:,.0f} 元, 收益率 {net_ret*100:+.1f}%")
print(f"期间上证/全市场背景见报告; 最大单期亏损 {rr['前10只收益'].min()*100:+.2f}%, 最大单期盈利 {rr['前10只收益'].max()*100:+.2f}%")

rr["期收益%"] = (rr["前10只收益"] * 100).round(2)
rr[["期数", "选股日", "期收益%", "命中数", "股票"]].to_csv(
    "模拟10万_2026轮换明细.csv", index=False, encoding="utf-8-sig")
print("\n明细已存: 模拟10万_2026轮换明细.csv")
print(f"[耗时 {time.time()-t0:.1f}s]")
