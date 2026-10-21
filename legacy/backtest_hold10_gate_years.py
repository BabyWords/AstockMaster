# -*- coding: utf-8 -*-
"""
「小市值+反转」持有10天 · 分年份回测（带大小盘风格闸门 vs 无闸门）
====================================================================
口径：t日收盘选股 → t+1买入 → 持有10交易日 → t+11卖出；每10交易日调仓；前10只等权；成本0.3%/期
风格闸门：调仓日收盘判断「小盘组(市值最小50%) vs 大盘组(市值最大20%)」近20日超额，<0则空仓
        （与实盘 select_stocks.py 完全一致）

输出：2024 / 2025 / 2026 每年 无闸门 vs 有闸门 的收益率、回撤、参与/空仓期数，及三年汇总。
"""
import pandas as pd, numpy as np, time

CACHE = "/Volumes/TOSHIBA/炒股/回测/daily_full_2022_2026.csv"
STYLE_LOOKBACK = 20
STYLE_EXCESS_MIN = 0.0
SMALL_PCT = 0.5
LARGE_PCT = 0.8
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

base = df.groupby("股票代码")["复权因子"].last().rename("bf")
df = df.merge(base, on="股票代码", how="left")
df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]

g = df.groupby("股票代码", sort=False)
df["pct"] = g["close_adj"].pct_change() * 100
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

print(f"[准备完成 {time.time()-t0:.1f}s]", flush=True)

def simulate(year):
    dyear = sorted(df[df["交易日期"].str.startswith(year)]["交易日期"].unique())
    if not dyear:
        return None
    idxs = list(range(0, len(dyear) - 11, 10))
    cap_no = CAPITAL
    cap_gate = CAPITAL
    nav_no = [CAPITAL]
    nav_gate = [CAPITAL]
    n_hold = 0
    n_skip = 0
    skip_dates = []
    rows = []
    for i in idxs:
        t = dyear[i]
        sub = df[df["交易日期"] == t]
        top = sub.nsmallest(10, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < 5:
            continue
        ret = r.mean()
        ex, sc, lc = style_excess(t)
        gate_ok = ex >= STYLE_EXCESS_MIN
        cap_no *= (1 + ret - COST)
        nav_no.append(cap_no)
        if gate_ok:
            cap_gate *= (1 + ret - COST)
            n_hold += 1
        else:
            n_skip += 1
            skip_dates.append(t)
        nav_gate.append(cap_gate)
        rows.append({"选股日": t, "闸门": "放行" if gate_ok else "空仓",
                     "小盘20日%": round(sc, 2), "大盘20日%": round(lc, 2), "超额%": round(ex, 2),
                     "期收益%": round(ret * 100, 2)})

    nav_no_s = pd.Series(nav_no)
    nav_gate_s = pd.Series(nav_gate)
    mdd_no = (nav_no_s / nav_no_s.cummax() - 1).min() * 100
    mdd_gate = (nav_gate_s / nav_gate_s.cummax() - 1).min() * 100
    return dict(year=year, start=dyear[0], end=dyear[-1], n_period=len(rows),
                ret_no=(cap_no / CAPITAL - 1) * 100, ret_gate=(cap_gate / CAPITAL - 1) * 100,
                cap_no=cap_no, cap_gate=cap_gate, mdd_no=mdd_no, mdd_gate=mdd_gate,
                n_hold=n_hold, n_skip=n_skip, skip_dates=skip_dates, rows=rows)

results = []
for y in ["2024", "2025", "2026"]:
    r = simulate(y)
    if not r:
        continue
    results.append(r)
    print(f"\n===== {y} ({r['start']}~{r['end']}, {r['n_period']}期) =====")
    print(f"  无闸门: 期末 {r['cap_no']:,.0f} 元  收益率 {r['ret_no']:+.1f}%  回撤 {r['mdd_no']:.1f}%")
    print(f"  有闸门: 期末 {r['cap_gate']:,.0f} 元  收益率 {r['ret_gate']:+.1f}%  回撤 {r['mdd_gate']:.1f}%  "
          f"(参与{r['n_hold']}期/空仓{r['n_skip']}期)")
    if r["skip_dates"]:
        print(f"  空仓调仓日: {', '.join(r['skip_dates'])}")

print("\n\n" + "=" * 74)
print("################ 三年汇总（带闸门 vs 无闸门） ################")
print(f"{'年份':<6}{'无闸门收益':>11}{'有闸门收益':>11}{'无闸门回撤':>11}{'有闸门回撤':>11}{'参与/空仓':>10}")
for r in results:
    hold_skip = f"{r['n_hold']}/{r['n_skip']}"
    print(f"{r['year']:<6}{r['ret_no']:>+10.1f}%{r['ret_gate']:>+10.1f}%"
          f"{r['mdd_no']:>10.1f}%{r['mdd_gate']:>10.1f}%{hold_skip:>10}")
print("=" * 74)

# 三年连续复利对比（无闸门 / 有闸门，各自每年从10万起连续复利）
cap_no_cum = CAPITAL
cap_gate_cum = CAPITAL
for r in results:
    cap_no_cum *= (1 + r["ret_no"] / 100)
    cap_gate_cum *= (1 + r["ret_gate"] / 100)
print(f"\n三年连续复利(10万→): 无闸门 {cap_no_cum:,.0f} 元 ({cap_no_cum/CAPITAL:.2f}x)  |  "
      f"有闸门 {cap_gate_cum:,.0f} 元 ({cap_gate_cum/CAPITAL:.2f}x)")

allrows = []
for r in results:
    for row in r["rows"]:
        allrows.append({"年份": r["year"], **row})
pd.DataFrame(allrows).to_csv("/Volumes/TOSHIBA/炒股/回测/模拟10万_分年份带闸门明细.csv",
                             index=False, encoding="utf-8-sig")
print("\n明细已存: 模拟10万_分年份带闸门明细.csv")
print(f"[总耗时 {time.time()-t0:.1f}s]")
