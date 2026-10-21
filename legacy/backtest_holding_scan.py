# -*- coding: utf-8 -*-
"""
持有期扫描：小市值+反转因子，每日收盘(近似14:30)按横截面打分选前10%，
持有 H 天后卖出，看单票胜率与平均收益随持有期的变化。
口径：单票胜率 = 所有被选中「股票×日期」样本中，持有H天收益>0 的比例。
"""
import pandas as pd, numpy as np, time

CACHE = "daily_full_2022_2026.csv"
t0 = time.time()
df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str})

df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["收盘价（元）"])
df = df.sort_values(["股票代码", "交易日期"])
base = df.groupby("股票代码")["复权因子"].last().rename("bf")
df = df.merge(base, on="股票代码", how="left")
df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]

g = df.groupby("股票代码", sort=False)
df["REV"] = -g["close_adj"].pct_change(20)
df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
for H in [1, 2, 3, 5, 10, 20]:
    df[f"fwd{H}"] = g["close_adj"].transform(lambda s: s.shift(-H) / s - 1.0)
df["year"] = df["交易日期"].str[:4]

gd = df.groupby("交易日期")
for f in ["SIZE", "REV"]:
    m = gd[f].transform("mean")
    s = gd[f].transform("std").replace(0, np.nan)
    df["z_" + f] = (df[f] - m) / s
df["score"] = df["z_SIZE"] + df["z_REV"]
df["rank_pct"] = df.groupby("交易日期")["score"].rank(pct=True)

sel = df[df["rank_pct"] >= 0.90].copy()
print(f"[准备完成] {time.time()-t0:.1f}s, 前10%信号行数 {len(sel)}", flush=True)

def report(sub, label):
    print(f"\n=== {label} ===")
    for H in [1, 2, 3, 5, 10, 20]:
        r = sub[f"fwd{H}"].dropna()
        if len(r) == 0:
            continue
        print(f"  持有{H:2d}天: 样本{len(r):7d}  单票胜率{(r>0).mean()*100:5.1f}%  "
              f"平均{r.mean()*100:+6.3f}%  中位{r.median()*100:+6.3f}%")

report(sel, "小市值+反转 前10%（全样本 2022-2026）")
report(sel[sel["year"].isin(["2022", "2023", "2024"])], "样本外 2022-2024")
report(sel[sel["year"].isin(["2025", "2026"])], "样本内 2025-2026")

print("\n=== 全市场等权基准（对比） ===")
for H in [1, 2, 3, 5, 10, 20]:
    r = df[f"fwd{H}"].dropna()
    print(f"  持有{H:2d}天: 单票胜率{(r>0).mean()*100:5.1f}%  平均{r.mean()*100:+6.3f}%")

print(f"\n[总耗时] {time.time()-t0:.1f}s")
