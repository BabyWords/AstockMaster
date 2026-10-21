# -*- coding: utf-8 -*-
"""
「小市值+反转」持有10天 · 2026年回测（带大小盘风格闸门 vs 无闸门 对比）
========================================================================
口径（与实盘 select_stocks.py + simulate_10w.py 一致）：
- t日收盘选股 → t+1买入 → 持有10交易日 → t+11卖出（延迟买入，避前视）
- 每 10 个交易日调仓一次，前 10 只等权
- 成本：每期一买一卖合计 0.3%
- 风格闸门：调仓日收盘判断「小盘组(市值最小50%) vs 大盘组(市值最大20%)」
  近 20 个交易日累计收益，超额 < STYLE_EXCESS_MIN 则该期空仓（不买，资金闲置）

输出：无闸门 vs 有闸门 的累计收益、回撤、参与/空仓期数、逐期明细。
"""
import pandas as pd, numpy as np, time

CACHE = "/Volumes/TOSHIBA/炒股/回测/daily_full_2022_2026.csv"
STYLE_LOOKBACK = 20      # 风格判断回看交易日数（与 select_stocks.py 一致）
STYLE_EXCESS_MIN = 0.0   # 放行线：超额 < 0 则空仓
SMALL_PCT = 0.5          # 小盘组 = 市值最小 50%
LARGE_PCT = 0.8          # 大盘组 = 市值最大 20%（分位 >= 0.8）
COST = 0.003
CAPITAL = 100000.0

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
df["pct"] = g["close_adj"].pct_change() * 100          # 日涨跌幅 %
df["REV"] = -g["close_adj"].pct_change(20)
df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
df["next_close"] = g["close_adj"].shift(-1)
df["close_11"] = g["close_adj"].shift(-11)
df["fwd10_lag"] = df["close_11"] / df["next_close"] - 1.0

# 横截面 z-score
gd = df.groupby("交易日期")
for f in ["SIZE", "REV"]:
    m = gd[f].transform("mean")
    s = gd[f].transform("std").replace(0, np.nan)
    df["z_" + f] = (df[f] - m) / s
df["score"] = df["z_SIZE"] + df["z_REV"]
df["rank"] = df.groupby("交易日期")["score"].rank(method="first", ascending=False)

# 风格闸门：每日市值分位 + 小盘/大盘等权涨跌幅
df["mcap_pct"] = df.groupby("交易日期")["流通市值（万元）"].rank(pct=True)
small_daily = df[df["mcap_pct"] <= SMALL_PCT].groupby("交易日期")["pct"].mean()
large_daily = df[df["mcap_pct"] >= LARGE_PCT].groupby("交易日期")["pct"].mean()

dates = sorted(df["交易日期"].unique())
date_pos = {d: i for i, d in enumerate(dates)}

def style_excess(t):
    i = date_pos[t]
    j0 = max(0, i - STYLE_LOOKBACK)
    seg = dates[j0:i + 1]
    sd = small_daily.reindex(seg).dropna()
    ld = large_daily.reindex(seg).dropna()
    sc = np.prod(1 + sd / 100) - 1
    lc = np.prod(1 + ld / 100) - 1
    return (sc - lc) * 100, sc * 100, lc * 100

d2026 = sorted(df[df["交易日期"] >= "20260101"]["交易日期"].unique())
print(f"2026 区间: {d2026[0]} ~ {d2026[-1]}, 共 {len(d2026)} 个交易日")

idxs = list(range(0, len(d2026) - 11, 10))
rows = []
for i in idxs:
    t = d2026[i]
    sub = df[df["交易日期"] == t]
    top = sub.nsmallest(10, "rank")
    r = top["fwd10_lag"].dropna()
    if len(r) < 5:
        continue
    ex, sc, lc = style_excess(t)
    gate_ok = ex >= STYLE_EXCESS_MIN
    rows.append({
        "期数": len(rows) + 1,
        "选股日": t,
        "小盘20日%": round(sc, 2),
        "大盘20日%": round(lc, 2),
        "超额%": round(ex, 2),
        "闸门": "放行" if gate_ok else "空仓",
        "前10只收益": r.mean(),
        "命中数": len(r),
        "股票": "/".join(top["股票名称"].astype(str).tolist()),
    })

rr = pd.DataFrame(rows)
print(f"调仓期数: {len(rr)}")

# 累积对比
cap_no = CAPITAL   # 无闸门：每期都参与
cap_gate = CAPITAL # 有闸门：空仓期市值不变
nav_gate = [CAPITAL]
details = []
for _, row in rr.iterrows():
    r = row["前10只收益"]
    cap_no *= (1 + r - COST)
    if row["闸门"] == "放行":
        cap_gate *= (1 + r - COST)
    nav_gate.append(cap_gate)
    details.append((row["选股日"], row["闸门"], r * 100, cap_gate))

print(f"\n{'选股日':<10}{'闸门':<5}{'期收益%':>9}{'扣成本后市值':>14}")
for d, gate, r, cap in details:
    print(f"{d:<10}{gate:<5}{r:>8.2f}%{cap:>13,.0f}")

nav = pd.Series(nav_gate)
mdd_gate = (nav / nav.cummax() - 1).min() * 100

n_hold = (rr["闸门"] == "放行").sum()
n_skip = (rr["闸门"] == "空仓").sum()

print(f"\n{'='*62}")
print(f"=== 2026 回测结果（10 万本金，{d2026[0]} ~ {d2026[-1]}，成本0.3%/期）===")
print(f"{'':<16}{'无闸门':>14}{'有闸门':>14}")
print(f"{'期末市值(元)':<16}{cap_no:>14,.0f}{cap_gate:>14,.0f}")
print(f"{'累计收益率':<16}{(cap_no/CAPITAL-1)*100:>13.1f}%{(cap_gate/CAPITAL-1)*100:>13.1f}%")
print(f"{'参与期数':<16}{len(rr):>14}{n_hold:>14}")
print(f"{'空仓期数':<16}{0:>14}{n_skip:>14}")
print(f"{'最大回撤':<16}{'--':>14}{mdd_gate:>13.1f}%")
print(f"{'='*62}")

# 空仓期明细
skip_dates = rr[rr["闸门"] == "空仓"]["选股日"].tolist()
print(f"\n闸门拦截（空仓）的调仓日: {', '.join(skip_dates) if skip_dates else '无'}")

rr["期收益%"] = (rr["前10只收益"] * 100).round(2)
rr[["期数", "选股日", "小盘20日%", "大盘20日%", "超额%", "闸门", "期收益%", "命中数", "股票"]].to_csv(
    "/Volumes/TOSHIBA/炒股/回测/模拟10万_2026带闸门明细.csv", index=False, encoding="utf-8-sig")
print("明细已存: 模拟10万_2026带闸门明细.csv")
print(f"[耗时 {time.time()-t0:.1f}s]")
