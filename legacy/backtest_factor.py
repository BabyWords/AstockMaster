# -*- coding: utf-8 -*-
"""
因子打分组合回测（单因子分组法 + 多因子组合）
================================================================
数据：余哈哈数据仓库日线，2025-2026，前复权
调仓：每 20 个交易日（约月度），持有 20 日
分组：每个调仓日按因子值分 5 组，统计各组未来 20 日等权收益
因子：
  REV   反转    = -(20日收益率)        跌得多→分高(超跌反弹)
  MOM   动量    = 60日收益率           涨得多→分高(强者恒强)
  VOL   低波动  = -(20日收益率std)     波动小→分高
  TURN  低换手  = -(20日均换手率)      换手低→分高
  SIZE  小市值  = -log(流通市值)       市值小→分高
  EP    低估值  = 1/PE(TTM)            PE低→分高
  DY    高股息  = 股息率(TTM)%         股息高→分高
================================================================
"""
import os
import glob
import time
import pandas as pd
import numpy as np

DATA = "/Volumes/TOSHIBA/炒股"
DAILY_DIR = os.path.join(DATA, "每日行情")
OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = os.path.join(OUT, "daily_full_2025_2026.csv")
YEARS = ["2025", "2026"]

COLS = ["交易日期", "股票代码", "股票名称", "开盘价（元）", "收盘价（元）",
        "成交量（手）", "复权因子", "换手率（%）", "量比",
        "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]


def extract():
    files = []
    for y in YEARS:
        files += sorted(glob.glob(os.path.join(DAILY_DIR, y, "*.csv")))
    print(f"[提取] 共 {len(files)} 个日线文件", flush=True)
    parts = []
    for i, f in enumerate(files):
        try:
            parts.append(pd.read_csv(f, usecols=COLS,
                                     dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:
            print(f"  [跳过] {f}: {e}", flush=True)
        if (i + 1) % 100 == 0:
            print(f"  已读 {i + 1}/{len(files)}", flush=True)
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(CACHE, index=False)
    print(f"[提取] 完成，{len(df)} 行", flush=True)
    return df


def prep(df):
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    num_cols = ["收盘价（元）", "成交量（手）", "复权因子", "换手率（%）",
                "量比", "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）"])
    df = df.sort_values(["股票代码", "交易日期"])
    base = df.groupby("股票代码")["复权因子"].last().rename("base_factor")
    df = df.merge(base, on="股票代码", how="left")
    df["adj"] = df["复权因子"] / df["base_factor"]
    df["close_adj"] = df["收盘价（元）"] * df["adj"]
    return df


def add_factors(df):
    g = df.groupby("股票代码", sort=False)
    df["ret"] = g["close_adj"].pct_change()
    df["REV"] = -g["close_adj"].pct_change(20)                    # 反转
    df["MOM"] = g["close_adj"].pct_change(60)                     # 动量
    df["VOL"] = -g["ret"].transform(lambda s: s.rolling(20).std())  # 低波
    df["TURN"] = -g["换手率（%）"].transform(lambda s: s.rolling(20).mean())  # 低换手
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))    # 小市值
    pe = df["市盈率（TTM）"]
    df["EP"] = np.where(pe > 0, 1.0 / pe, np.nan)                 # 低估值 E/P
    df["DY"] = df["股息率（TTM）（%）"]                            # 高股息
    return df


def main():
    t0 = time.time()
    if os.path.exists(CACHE):
        df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
        print(f"[缓存] 读取 {len(df)} 行", flush=True)
    else:
        df = extract()
    df = prep(df)
    print("[预处理] 完成", flush=True)
    df = add_factors(df)
    print("[因子] 计算完成", flush=True)

    # 未来20日收益
    g = df.groupby("股票代码", sort=False)
    df["next20"] = g["close_adj"].transform(lambda s: s.shift(-20) / s - 1.0)

    dates = sorted(df["交易日期"].unique())
    rebal = dates[::20]
    print(f"[调仓] 共 {len(rebal)} 个调仓日，区间 {rebal[0]} ~ {rebal[-1]}", flush=True)

    factors = ["REV", "MOM", "VOL", "TURN", "SIZE", "EP", "DY"]
    summary = {}
    for f in factors:
        rows = []
        for t in rebal:
            sub = df[df["交易日期"] == t].dropna(subset=[f, "next20"]).copy()
            if len(sub) < 50:
                continue
            sub["rank"] = sub[f].rank(method="first")
            sub["q"] = pd.qcut(sub["rank"], 5, labels=[1, 2, 3, 4, 5])
            for q, grp in sub.groupby("q"):
                rows.append({"date": t, "q": int(q), "ret": grp["next20"].mean()})
        r = pd.DataFrame(rows)
        if len(r) == 0:
            print(f"\n=== {f}: 数据不足 ===")
            continue
        piv = r.pivot_table(index="date", columns="q", values="ret")
        means = piv.mean() * 100
        print(f"\n=== 因子 {f} ===")
        for q in [1, 2, 3, 4, 5]:
            if q in piv.columns:
                print(f"  Q{q}({'差' if q==1 else '好' if q==5 else '中'}): 平均月收益 {means[q]:+.3f}%")
        if 1 in piv.columns and 5 in piv.columns:
            spread = (piv[5] - piv[1]).mean() * 100
            pos_ratio = ((piv[5] - piv[1]) > 0).mean() * 100
            print(f"  >>> Q5-Q1 因子收益: {spread:+.3f}%/月  (正收益占比 {pos_ratio:.0f}%)")
            summary[f] = (spread, pos_ratio)

    # 全市场等权基准（所有调仓日的平均 next20）
    bench_rows = [df[df["交易日期"] == t]["next20"].mean() for t in rebal]
    bench = np.mean([x for x in bench_rows if pd.notna(x)]) * 100
    print(f"\n[基准] 全市场等权月收益约 {bench:+.3f}%")

    print("\n========== 因子收益汇总 ==========")
    for f, (s, p) in sorted(summary.items(), key=lambda kv: kv[1][0], reverse=True):
        print(f"  {f:6s}  Q5-Q1 {s:+.3f}%/月  (正占比 {p:.0f}%)")

    print(f"\n总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
