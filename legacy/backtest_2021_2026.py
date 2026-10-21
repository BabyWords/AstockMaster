# -*- coding: utf-8 -*-
"""
「小市值+反转」持有10天 · 2021-01 ~ 2026-10 全样本回测（机械执行，无择时）
========================================================================
口径（与 backtest_hold10.py / simulate_years.py 完全一致）：
- 因子：SIZE=-log(流通市值万元)、REV=-(近20日涨跌幅)，前复权收盘价
- 每日收盘横截面 Z-score 标准化，score = Z_SIZE + Z_REV，取前 10 只等权
- t日收盘选股 → t+1买入 → 持有10交易日 → t+11卖出（延迟买入，避前视）
- 每 10 个交易日调仓一次；成本每期 0.3%
- 数据从 2020 开始读（为 2021 年初算 REV 预热），回测区间 2021-01-01 起

输出：全样本累计/年化/回撤/期胜率 + 分年明细 + 10万本金连续复利。
"""
import os, glob, time
import pandas as pd, numpy as np

DATA = "/Volumes/TOSHIBA/炒股"
DAILY_DIR = os.path.join(DATA, "每日行情")
OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = os.path.join(OUT, "daily_full_2020_2026.csv")
YEARS = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]

COLS = ["交易日期", "股票代码", "股票名称", "收盘价（元）",
        "复权因子", "换手率（%）", "量比",
        "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]

COST = 0.003
CAPITAL = 100000.0
t0 = time.time()


def extract():
    files = []
    for y in YEARS:
        for f in sorted(glob.glob(os.path.join(DAILY_DIR, y, "*.csv"))):
            if "(1)" in f:      # 跳过重复文件（2021 有 45 个带"(1)"的重复）
                continue
            files.append(f)
    print(f"[提取] 共 {len(files)} 个日线文件", flush=True)
    parts = []
    for i, f in enumerate(files):
        try:
            parts.append(pd.read_csv(f, usecols=COLS,
                                     dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:
            print(f"  [跳过] {os.path.basename(f)}: {e}", flush=True)
        if (i + 1) % 200 == 0:
            print(f"  已读 {i+1}/{len(files)}", flush=True)
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(CACHE, index=False)
    print(f"[提取] 完成，{len(df):,} 行 → {CACHE}", flush=True)
    return df


def prep(df):
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["收盘价（元）", "复权因子", "流通市值（万元）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
    df = df.sort_values(["股票代码", "交易日期"])
    # 前复权（以每只股票样本期末复权因子为基准）
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


def run(df, dlist):
    """给定交易日列表，机械执行：每10交易日调仓前10只，返回每期(日期,收益)"""
    idxs = list(range(0, len(dlist) - 11, 10))
    rows = []
    for i in idxs:
        t = dlist[i]
        sub = df[df["交易日期"] == t]
        top = sub.nsmallest(10, "rank")
        r = top["fwd10_lag"].dropna()
        if len(r) < 5:
            continue
        rows.append((t, r.mean()))
    return rows


def stats(rows, label):
    ret = pd.Series([r for _, r in rows])
    cum = (1 + ret).prod() - 1
    net = ret - COST
    net_cum = (1 + net).prod() - 1
    n_years = len(ret) * 10 / 242.0
    ann = (1 + net_cum) ** (1 / n_years) - 1 if net_cum > -1 and n_years > 0 else np.nan
    win = (ret > 0).mean() * 100
    nav = (1 + net).cumprod()
    mdd = (nav / nav.cummax() - 1).min() * 100
    print(f"\n=== {label} ===")
    print(f"  调仓期数: {len(ret)}  区间 {rows[0][0]} ~ {rows[-1][0]}")
    print(f"  累计(未扣成本): {cum*100:+.1f}%  累计(扣成本): {net_cum*100:+.1f}%")
    print(f"  年化(扣成本): {ann*100:+.2f}%  期胜率: {win:.0f}%  最大回撤: {mdd:.1f}%")
    return dict(n=len(ret), cum=cum*100, net_cum=net_cum*100, ann=ann*100, win=win, mdd=mdd)


def main():
    if os.path.exists(CACHE):
        df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
        print(f"[缓存] 读取 {len(df):,} 行", flush=True)
    else:
        df = extract()
    df = prep(df)
    print(f"[预处理] {len(df):,} 行", flush=True)
    df = add_factors(df)
    print(f"[因子] 完成，耗时 {time.time()-t0:.0f}s", flush=True)

    # 回测区间：2021-01-01 起
    df_bt = df[df["交易日期"] >= "20210101"]
    dlist = sorted(df_bt["交易日期"].unique())
    print(f"\n[回测] 区间 {dlist[0]} ~ {dlist[-1]}，共 {len(dlist)} 交易日")

    # 全样本
    rows = run(df_bt, dlist)
    res_all = stats(rows, f"全样本 2021-2026（机械执行，前10只，持有10天）")

    # 分年
    print("\n" + "=" * 70)
    print("【分年度（每年独立 10 万本金）】")
    print("=" * 70)
    year_rows = {}
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        dy = sorted(df_bt[df_bt["交易日期"].str.startswith(y)]["交易日期"].unique())
        if not dy:
            continue
        r = run(df_bt, dy)
        year_rows[y] = r
        ret = pd.Series([x for _, x in r])
        cap = CAPITAL
        for x in ret:
            cap *= (1 + x - COST)
        nav = (1 + (ret - COST)).cumprod()
        mdd = (nav / nav.cummax() - 1).min() * 100
        print(f"  {y}: {len(ret):>3}期  期末 {cap:>10,.0f} 元  收益 {(cap/CAPITAL-1)*100:>+7.1f}%  回撤 {mdd:>6.1f}%")

    # 10万本金连续复利（2021 起不间断）
    cap = CAPITAL
    nav_all = [CAPITAL]
    for _, x in rows:
        cap *= (1 + x - COST)
        nav_all.append(cap)
    nav_all_s = pd.Series(nav_all)
    mdd_all = (nav_all_s / nav_all_s.cummax() - 1).min() * 100
    print("\n" + "=" * 70)
    print(f"【10万本金连续复利】2021-01 ~ 2026-10（扣成本0.3%/期）")
    print(f"  10万 → {cap:,.0f} 元  ({cap/CAPITAL:.2f} 倍)")
    print(f"  最大回撤 {mdd_all:.1f}%")
    print("=" * 70)

    # 保存分年明细
    allrows = []
    for y, r in year_rows.items():
        for t, x in r:
            allrows.append({"年份": y, "选股日": t, "期收益%": round(x * 100, 2)})
    pd.DataFrame(allrows).to_csv(os.path.join(OUT, "回测明细_2021_2026.csv"),
                                 index=False, encoding="utf-8-sig")
    print("\n明细已存: 回测明细_2021_2026.csv")
    print(f"[总耗时 {time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
