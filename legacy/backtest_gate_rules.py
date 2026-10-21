# -*- coding: utf-8 -*-
"""
闸门规则扫描：哪种风格闸门（如果有）能在牛市不踏空、熊市躲暴跌？
=================================================================
对比多种闸门规则三年（2024/2025/2026）表现：
- 无闸门（基线）
- 相对闸门：小盘20日超额 < T 拦截（T = 0 / -3 / -5）
- 绝对暴跌闸门：小盘20日绝对收益 < T 拦截（T = -10 / -15）

口径：t日收盘选股→t+1买→持有10日→t+11卖；每10交易日调仓；前10只等权；成本0.3%/期
"""
import pandas as pd, numpy as np, time

CACHE = "/Volumes/TOSHIBA/炒股/回测/daily_full_2022_2026.csv"
SMALL_PCT = 0.5
LARGE_PCT = 0.8
COST = 0.003
CAPITAL = 100000.0
LOOKBACK = 20

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

def style_metrics(t):
    i = date_pos[t]
    j0 = max(0, i - LOOKBACK)
    seg = dates[j0:i + 1]
    sd = small_daily.reindex(seg).dropna()
    ld = large_daily.reindex(seg).dropna()
    sc = (np.prod(1 + sd / 100) - 1) * 100
    lc = (np.prod(1 + ld / 100) - 1) * 100
    return sc, lc, sc - lc   # 小盘绝对, 大盘绝对, 超额

print(f"[准备完成 {time.time()-t0:.1f}s]", flush=True)

# 规则定义：(名称, 判定函数) —— 返回 True=放行, False=空仓
def rule_none(sc, lc, ex): return True
def rule_rel_0(sc, lc, ex): return ex >= 0
def rule_rel_m3(sc, lc, ex): return ex >= -3
def rule_rel_m5(sc, lc, ex): return ex >= -5
def rule_abs_m10(sc, lc, ex): return sc >= -10
def rule_abs_m15(sc, lc, ex): return sc >= -15

rules = [
    ("无闸门", rule_none),
    ("相对<0停", rule_rel_0),
    ("相对<-3停", rule_rel_m3),
    ("相对<-5停", rule_rel_m5),
    ("小盘跌>10%停", rule_abs_m10),
    ("小盘跌>15%停", rule_abs_m15),
]

def simulate(year, gate_fn):
    dyear = sorted(df[df["交易日期"].str.startswith(year)]["交易日期"].unique())
    if not dyear:
        return None
    idxs = list(range(0, len(dyear) - 11, 10))
    cap = CAPITAL
    nav = [CAPITAL]
    n_skip = 0
    for i in idxs:
        t = dyear[i]
        sub = df[df["交易日期"] == t]
        top = sub.nsmallest(10, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < 5:
            continue
        ret = r.mean()
        sc, lc, ex = style_metrics(t)
        if gate_fn(sc, lc, ex):
            cap *= (1 + ret - COST)
        else:
            n_skip += 1
        nav.append(cap)
    nav_s = pd.Series(nav)
    mdd = (nav_s / nav_s.cummax() - 1).min() * 100
    return dict(ret=(cap / CAPITAL - 1) * 100, mdd=mdd, skip=n_skip, n=len(idxs))

# 逐规则 × 逐年
print("\n各规则逐年收益率（%）:")
print(f"{'规则':<14}" + "".join(f"{y:>12}" for y in ["2024", "2025", "2026"]) + f"{'三年复利':>12}")
cum = {}
for name, fn in rules:
    line = f"{name:<14}"
    mult = 1.0
    for y in ["2024", "2025", "2026"]:
        r = simulate(y, fn)
        line += f"{r['ret']:>+11.1f}%"
        mult *= (1 + r['ret'] / 100)
    cum[name] = mult
    line += f"{mult:>11.2f}x"
    print(line)

print("\n各规则逐年最大回撤（%）:")
print(f"{'规则':<14}" + "".join(f"{y:>12}" for y in ["2024", "2025", "2026"]))
for name, fn in rules:
    line = f"{name:<14}"
    for y in ["2024", "2025", "2026"]:
        r = simulate(y, fn)
        line += f"{r['mdd']:>11.1f}%"
    print(line)

print("\n各规则空仓期数（共约24/24/17期）:")
print(f"{'规则':<14}" + "".join(f"{y:>12}" for y in ["2024", "2025", "2026"]))
for name, fn in rules:
    line = f"{name:<14}"
    for y in ["2024", "2025", "2026"]:
        r = simulate(y, fn)
        line += f"{r['skip']:>12}"
    print(line)

print(f"\n[总耗时 {time.time()-t0:.1f}s]")
