# -*- coding: utf-8 -*-
"""
前视偏差检验：对比两种买入口径
  原版    = t日收盘算信号 + t日收盘买入 + 持有到t+20收盘卖出  (有轻微前视)
  延迟版  = t日收盘算信号 + t+1日收盘买入 + 持有到t+21收盘卖出 (无前视)
结论若两者接近 -> 前视偏差影响小、结论稳健；若差异大 -> 需修正。
"""
import pandas as pd, numpy as np, time

CACHE = "daily_full_2022_2026.csv"
t0 = time.time()

df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str})
print(f"[读缓存] {len(df)} 行, {time.time()-t0:.1f}s", flush=True)

# prep（与 backtest_factor_full.py 完全一致）
df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
num_cols = ["收盘价（元）", "复权因子", "换手率（%）", "量比",
            "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]
for c in num_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["收盘价（元）"])
df = df.sort_values(["股票代码", "交易日期"])
base = df.groupby("股票代码")["复权因子"].last().rename("base_factor")
df = df.merge(base, on="股票代码", how="left")
df["adj"] = df["复权因子"] / df["base_factor"]
df["close_adj"] = df["收盘价（元）"] * df["adj"]

# 因子
g = df.groupby("股票代码", sort=False)
df["ret"] = g["close_adj"].pct_change()
df["REV"] = -g["close_adj"].pct_change(20)
df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
# 两种口径的未来20日收益
df["next20"] = g["close_adj"].transform(lambda s: s.shift(-20) / s - 1.0)          # 原版：t日买
df["next20_delay"] = g["close_adj"].transform(lambda s: s.shift(-21) / s.shift(-1) - 1.0)  # 延迟：t+1日买
df["year"] = df["交易日期"].str[:4]
print(f"[因子完成] {time.time()-t0:.1f}s", flush=True)

dates = sorted(df["交易日期"].unique())
rebal = dates[::20]

def zscore(s):
    m = s.mean(); std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - m) / std

def run_combo(factor_cols, retcol):
    rows = []
    for t in rebal:
        sub = df[df["交易日期"] == t].dropna(subset=factor_cols + [retcol]).copy()
        if len(sub) < 50:
            continue
        score = pd.Series(0.0, index=sub.index)
        for f in factor_cols:
            score = score + zscore(sub[f])
        sub["score"] = score
        sub = sub.sort_values("score", ascending=False)
        top = sub.head(max(1, int(len(sub) * 0.10)))
        rows.append({"date": t, "ret": top[retcol].mean(), "year": t[:4]})
    return pd.DataFrame(rows)

def stat(r, name):
    r = r.sort_values("date").reset_index(drop=True)
    ann = (1 + r["ret"]).prod() ** (12 / len(r)) - 1
    cum = (1 + r["ret"]).cumprod()
    mdd = (cum / cum.cummax() - 1).min() * 100
    print(f"    {name:12s} 期数{len(r):3d} 月均{r['ret'].mean()*100:+6.3f}%  "
          f"年化{ann*100:+6.2f}%  胜率{(r['ret']>0).mean()*100:4.0f}%  回撤{mdd:6.2f}%")

for fc, fn in [(["SIZE"], "纯小市值"), (["SIZE", "REV"], "小市值+反转")]:
    r_orig = run_combo(fc, "next20")
    r_delay = run_combo(fc, "next20_delay")
    for seg, yrs in [("全样本", None), ("样本外22-24", ("2022", "2023", "2024")),
                     ("样本内25-26", ("2025", "2026"))]:
        ro = r_orig if yrs is None else r_orig[r_orig["year"].isin(yrs)]
        rd = r_delay if yrs is None else r_delay[r_delay["year"].isin(yrs)]
        print(f"\n[{fn} · {seg}]")
        stat(ro, "原版(收盘买)")
        stat(rd, "延迟(t+1买)")

print(f"\n[总耗时] {time.time()-t0:.1f}s")
