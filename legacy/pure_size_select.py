#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯小市值选股工具（单一因子：流通市值从小到大）
==============================================
与 select_stocks.py 的区别：只按「流通市值」排序，不叠加反转(REV20)因子。
即"买最小市值的前 N 只，不做其他判断"。

用法：
  python pure_size_select.py              # 用最新数据，选前 5 只
  python pure_size_select.py 20261021     # 指定日期
  python pure_size_select.py -n 10        # 输出前 10 只

保留基础可交易性过滤（非策略信号，纯风控）：
  - 仅 60/68/00/30 开头的 A 股
  - 剔除 ST / *ST / 退市股
  - 流通市值 > 0
  - 成交额 >= 5000 万（流动性）
  - 股价 >= 2 元（剔除面值退市高危垃圾股）
  - 当日涨幅 < 9.5%（不追涨停）
"""
import os, sys, re
import pandas as pd

DATA = "/Volumes/TOSHIBA/炒股"
DAILY = os.path.join(DATA, "每日行情")
OUT = os.path.join(DATA, "回测", "选股结果")

TOP_N = 5
MIN_AMT = 5000       # 成交额下限（万元）
MAX_PCT = 9.5        # 剔除接近涨停
MIN_PRICE = 2.0      # 股价下限


def collect_dates():
    files = []
    for y in os.listdir(DAILY):
        yd = os.path.join(DAILY, y)
        if not os.path.isdir(yd):
            continue
        for f in os.listdir(yd):
            if f.startswith("._") or not f.endswith(".csv"):
                continue
            m = re.match(r"(\d{8})", f)
            if m:
                files.append((m.group(1), os.path.join(yd, f)))
    files.sort()
    return files


def main():
    n = TOP_N
    target = None
    for a in sys.argv[1:]:
        if a == "-n" and sys.argv.index(a) + 1 < len(sys.argv):
            n = int(sys.argv[sys.argv.index(a) + 1])
        elif re.match(r"^\d{8}$", a):
            target = a

    files = collect_dates()
    dates = [d for d, _ in files]
    cur = target if target else dates[-1]
    if cur not in dates:
        print(f"❌ 日期 {cur} 不在数据中，最新可用：{dates[-1]}")
        sys.exit(1)
    path = dict(files)[cur]

    cols = ["股票代码", "股票名称", "收盘价（元）", "流通市值（万元）",
            "涨跌幅（%）", "成交额（万元）", "换手率（%）"]
    df = pd.read_csv(path, usecols=cols, dtype={"股票代码": str}, encoding="utf-8-sig")
    for c in ["收盘价（元）", "流通市值（万元）", "涨跌幅（%）", "成交额（万元）", "换手率（%）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 基础过滤
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df.dropna(subset=["流通市值（万元）", "收盘价（元）", "成交额（万元）"])
    df = df[df["流通市值（万元）"] > 0]
    df = df[df["成交额（万元）"] >= MIN_AMT]
    df = df[df["涨跌幅（%）"] < MAX_PCT]
    df = df[df["收盘价（元）"] >= MIN_PRICE]

    # 纯小市值：按流通市值从小到大排序（唯一因子）
    df = df.sort_values("流通市值（万元）", ascending=True).reset_index(drop=True)
    pool = len(df)
    top = df.head(n)

    print("=" * 78)
    print(f"纯小市值选股结果 · 数据日期 {cur}（仅按流通市值升序）")
    print(f"候选池 {pool} 只（已剔 ST/退、涨停、成交额<5000万、股价<{MIN_PRICE}元）")
    print("=" * 78)
    print(f"{'排名':<4}{'代码':<8}{'名称':<10}{'收盘价':>8}{'涨跌幅%':>8}"
          f"{'流通市值亿':>10}{'换手%':>7}{'成交额亿':>9}")
    print("-" * 78)
    for r in range(len(top)):
        row = top.iloc[r]
        print(f"{r+1:<4}{row['股票代码']:<8}{row['股票名称']:<10}{row['收盘价（元）']:>8.2f}"
              f"{row['涨跌幅（%）']:>8.2f}{row['流通市值（万元）']/10000:>10.1f}"
              f"{row['换手率（%）']:>7.2f}{row['成交额（万元）']/10000:>9.2f}")

    os.makedirs(OUT, exist_ok=True)
    out_csv = os.path.join(OUT, f"纯小市值选股_{cur}.csv")
    top.rename(columns={"收盘价（元）": "收盘价", "涨跌幅（%）": "涨跌幅%",
                        "流通市值（万元）": "流通市值万", "换手率（%）": "换手率%",
                        "成交额（万元）": "成交额万"}).to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("-" * 78)
    print(f"已保存前 {n} 只 → {out_csv}")


if __name__ == "__main__":
    main()
