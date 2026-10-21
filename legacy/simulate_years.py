# -*- coding: utf-8 -*-
"""
10 万本金 · 小市值+反转前10只 · 持有10天轮换 —— 分年份模拟（2024/2025/2026）
口径：t日收盘选股 → t+1买入 → 持有10交易日 → t+11卖出；成本0.3%/期
输出：每年期明细 + 期末金额 + 收益率(扣/未扣成本) + 最大回撤
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
print(f"[准备完成 {time.time()-t0:.1f}s]", flush=True)

COST = 0.003
CAPITAL = 100000.0

def simulate(year):
    dyear = sorted(df[df["交易日期"].str.startswith(year)]["交易日期"].unique())
    if not dyear:
        return None
    idxs = list(range(0, len(dyear) - 11, 10))
    cap_raw = CAPITAL
    cap_net = CAPITAL
    navs = [CAPITAL]
    rows = []
    for i in idxs:
        t = dyear[i]
        sub = df[df["交易日期"] == t]
        top = sub.nsmallest(10, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < 5:
            continue
        ret = r.mean()
        cap_raw *= (1 + ret)
        cap_net *= (1 + ret - COST)
        navs.append(cap_net)
        rows.append({"选股日": t, "期收益%": round(ret * 100, 2),
                     "扣成本后市值": round(cap_net, 0)})
    nav = pd.Series(navs)
    mdd = (nav / nav.cummax() - 1).min() * 100
    n_trade = len(dyear)
    years = n_trade / 242.0
    ann_net = (cap_net / CAPITAL) ** (1 / years) - 1 if years > 0 and cap_net > 0 else np.nan
    return dict(year=year, start=dyear[0], end=dyear[-1], n_trade=n_trade, n_period=len(rows),
                cap_raw=cap_raw, cap_net=cap_net,
                ret_raw=(cap_raw/CAPITAL-1)*100, ret_net=(cap_net/CAPITAL-1)*100,
                mdd=mdd, ann_net=ann_net*100, rows=rows)

results = []
for y in ["2024", "2025", "2026"]:
    r = simulate(y)
    if r:
        results.append(r)
        print(f"\n===== {y} ({r['start']}~{r['end']}, {r['n_trade']}交易日, {r['n_period']}期) =====")
        print(f"  期末(未扣成本): {r['cap_raw']:,.0f} 元  +{r['ret_raw']:.1f}%")
        print(f"  期末(扣成本)  : {r['cap_net']:,.0f} 元  +{r['ret_net']:.1f}%  (年化 {r['ann_net']:.1f}%)")
        print(f"  最大回撤      : {r['mdd']:.1f}%")

# 汇总表
print("\n\n################ 三年汇总 ################")
print(f"{'年份':<6}{'期数':>4}{'期末(扣成本)':>13}{'收益率':>9}{'年化':>8}{'最大回撤':>10}")
for r in results:
    print(f"{r['year']:<6}{r['n_period']:>4}{r['cap_net']:>12,.0f}元{r['ret_net']:>+8.1f}%{r['ann_net']:>+7.1f}%{r['mdd']:>9.1f}%")

# 存明细
allrows = []
for r in results:
    for row in r["rows"]:
        allrows.append({"年份": r["year"], **row})
pd.DataFrame(allrows).to_csv("模拟10万_分年份明细.csv", index=False, encoding="utf-8-sig")
print("\n明细已存: 模拟10万_分年份明细.csv")
print(f"[总耗时 {time.time()-t0:.1f}s]")
