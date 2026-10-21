# -*- coding: utf-8 -*-
"""
「小市值 + 反转」策略 · 持有 10 天 完整回测
============================================
口径（避免前视偏差）：
- 因子：SIZE = -log(流通市值万元)、REV = -(近20日涨跌幅)，用前复权收盘价算
- 每日收盘后横截面 Z-score 标准化，score = Z_SIZE + Z_REV
- 周期调仓：每 10 个交易日一次。t 日收盘算分选股 → t+1 日收盘买入 → 持有 10 个交易日 → t+11 日收盘卖出
- 成本：每期一买一卖合计 0.3%（单边 0.15%）
- 股票池：沪深主板 + 创业板 + 科创板，剔除 ST / 退市
输出：单票视角（胜率/平均/盈亏比）+ 组合视角（累计/年化/回撤/期胜率），全样本/样本外/样本内三段
"""
import pandas as pd, numpy as np, time

CACHE = "daily_full_2022_2026.csv"
t0 = time.time()
print("读取缓存...", flush=True)
df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str})

df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
df = df.sort_values(["股票代码", "交易日期"])

# 前复权
base = df.groupby("股票代码")["复权因子"].last().rename("bf")
df = df.merge(base, on="股票代码", how="left")
df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]

g = df.groupby("股票代码", sort=False)
df["REV"] = -g["close_adj"].pct_change(20)
df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
df["fwd10"] = g["close_adj"].transform(lambda s: s.shift(-10) / s - 1.0)          # t收盘买→t+10收盘卖
df["next_close"] = g["close_adj"].shift(-1)                                        # t+1 收盘
df["close_11"] = g["close_adj"].shift(-11)                                         # t+11 收盘
df["fwd10_lag"] = df["close_11"] / df["next_close"] - 1.0                          # t+1买→t+11卖(延迟1日仍持10日)

# 横截面 z-score
gd = df.groupby("交易日期")
for f in ["SIZE", "REV"]:
    m = gd[f].transform("mean")
    s = gd[f].transform("std").replace(0, np.nan)
    df["z_" + f] = (df[f] - m) / s
df["score"] = df["z_SIZE"] + df["z_REV"]
df["rank"] = df.groupby("交易日期")["score"].rank(method="first", ascending=False)
df["rank_pct"] = df.groupby("交易日期")["score"].rank(pct=True)
df["year"] = df["交易日期"].str[:4]

dates = sorted(df["交易日期"].unique())
print(f"[准备完成] {time.time()-t0:.1f}s, 股票×日 {len(df):,} 行, 交易日 {len(dates)}", flush=True)

# ============ 单票视角 ============
def seg_mask(sub, seg):
    if seg == "ALL":
        return sub
    if seg == "OOS":
        return sub[sub["year"].isin(["2022", "2023", "2024"])]
    return sub[sub["year"].isin(["2025", "2026"])]

def single_report(df, seg, name, use_lag):
    col = "fwd10_lag" if use_lag else "fwd10"
    sub = seg_mask(df, seg)
    print(f"\n=== 单票视角 [{name}] {'(延迟t+1买,严谨)' if use_lag else '(t日买)'} ===")
    for lab, sel in [("前10只", sub[sub["rank"] <= 10]),
                     ("前10%", sub[sub["rank_pct"] >= 0.90])]:
        r = sel[col].dropna()
        if len(r) == 0:
            continue
        win = (r > 0)
        up = r[r > 0].mean(); dn = -r[r < 0].mean()
        pl = (up / dn) if dn > 0 else np.nan
        print(f"  {lab:6s}: 样本{len(r):7d}  单票胜率{win.mean()*100:5.1f}%  "
              f"平均{r.mean()*100:+6.3f}%  中位{r.median()*100:+6.3f}%  盈亏比{pl:.2f}")

print("\n################ 单票视角（持有10天） ################")
for seg, name in [("ALL", "全样本 2022-2026"), ("OOS", "样本外 2022-2024"), ("IS", "样本内 2025-2026")]:
    single_report(df, seg, name, use_lag=True)

# ============ 组合视角（周期调仓，每10个交易日） ============
def combo_report(df, seg, topk, use_lag):
    """周期调仓组合：每10个交易日，选前 topk 只等权，期收益=fwd10_lag均值"""
    col = "fwd10_lag" if use_lag else "fwd10"
    d = seg_mask(df, seg)
    dl = sorted(d["交易日期"].unique())
    # 调仓日：从有20日数据的第21个交易日开始，每隔10天；且需保证 t+11 有数据
    idxs = list(range(20, len(dl) - 11, 10))
    rows = []
    for i in idxs:
        t = dl[i]
        sub = d[d["交易日期"] == t]
        if len(sub) < 30:
            continue
        top = sub.nsmallest(topk, "rank") if topk > 1 else sub[sub["rank_pct"] >= 0.90]
        r = top[col].dropna()
        if len(r) < 5:
            continue
        rows.append({"date": t, "ret": r.mean(), "n": len(r)})
    rr = pd.DataFrame(rows)
    if len(rr) == 0:
        print(f"  无数据")
        return None
    ret = rr["ret"]
    cum = (1 + ret).prod() - 1
    months = len(ret) * 10 / 21.0          # 每月约21个交易日
    ann = (1 + cum) ** (1 / (months / 12)) - 1 if cum > -1 else -1
    win = (ret > 0).mean() * 100
    net = ret - 0.003                        # 扣成本0.3%
    net_cum = (1 + net).prod() - 1
    net_ann = (1 + net_cum) ** (1 / (months / 12)) - 1 if net_cum > -1 else -1
    # 回撤
    nav = (1 + ret).cumprod()
    mdd = (nav / nav.cummax() - 1).min() * 100
    return dict(cum=cum*100, ann=ann*100, win=win, mdd=mdd, n=len(rr),
                net_cum=net_cum*100, net_ann=net_ann*100)

print("\n################ 组合视角（周期调仓·持有10天·延迟t+1买入） ################")
for seg, name in [("ALL", "全样本 2022-2026"), ("OOS", "样本外 2022-2024"), ("IS", "样本内 2025-2026")]:
    print(f"\n[{name}]")
    for lab, tk in [("前10只", 10), ("前10%", 0)]:
        res = combo_report(df, seg, tk, use_lag=True)
        if res:
            print(f"  {lab}: {res['n']}期  累计{res['cum']:+.1f}%  年化{res['ann']:+.1f}%  "
                  f"期胜率{res['win']:.0f}%  回撤{res['mdd']:.1f}%  "
                  f"| 扣成本后 累计{res['net_cum']:+.1f}% 年化{res['net_ann']:+.1f}%")

# 基准：全市场等权，同周期调仓持有10天
print("\n[全市场等权基准（同口径）]")
for seg, name in [("ALL", "全样本"), ("OOS", "样本外"), ("IS", "样本内")]:
    d = seg_mask(df, seg)
    dl = sorted(d["交易日期"].unique())
    idxs = list(range(20, len(dl) - 11, 10))
    rows = []
    for i in idxs:
        t = dl[i]
        sub = d[d["交易日期"] == t]
        r = sub["fwd10_lag"].dropna()
        if len(r) < 30:
            continue
        rows.append(r.mean())
    if rows:
        ret = pd.Series(rows)
        cum = (1 + ret).prod() - 1
        months = len(ret) * 10 / 21.0
        ann = (1 + cum) ** (1 / (months / 12)) - 1 if cum > -1 else -1
        print(f"  {name}: {len(ret)}期  累计{cum*100:+.1f}%  年化{ann*100:+.1f}%  期胜率{(ret>0).mean()*100:.0f}%")

print(f"\n[总耗时] {time.time()-t0:.1f}s")
