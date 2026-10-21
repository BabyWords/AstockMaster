# -*- coding: utf-8 -*-
"""
「放量破十日线」公式回测（结合日线 + 5分钟分时数据）
================================================================
策略：T 日 14:30 用公式选股并买入，T+1 日 10:00 卖出（隔夜）
数据：2025-2026，每日行情 + 分钟级行情(5min)
数据源：/Volumes/TOSHIBA/炒股（余哈哈的数据仓库）

公式（严格复刻通达信原式）：
    DOWN:=C<M20 AND M10<M20;      # 空头排列
    YEST:=REF(C,1)<REF(M10,1);    # 昨收跌破10日线
    BREAK:=C>M10;                 # 今日站上10日线
    VOLUP:=V>=1.5*MA(V,5);        # 放量
    RISE:=C>O AND C>REF(C,1) AND C<REF(C,1)*1.05;  # 收阳涨<5%

14:30 时点取值口径：
    C = T日14:30 的5min收盘价(前复权)；O = 日线开盘价(前复权)
    V = T日截至14:30累计量(股)
    M10 = (前9日收盘 + C)/10；M20 = (前19日收盘 + C)/20
    REF(M10,1) = 截至昨日的10日均线；MA(V,5) = (前4日量 + V)/5
价格统一前复权 = 原始价 × 复权因子 / 每股最新日复权因子
================================================================
"""
import os
import glob
import time
import pandas as pd
import numpy as np

DATA = "/Volumes/TOSHIBA/炒股"
DAILY_DIR = os.path.join(DATA, "每日行情")
MIN5_DIR = os.path.join(DATA, "分钟级行情")
OUT = "/Volumes/TOSHIBA/炒股/回测"

SNAP_CACHE = os.path.join(OUT, "snapshots_5min_2025_2026.csv")
DAILY_CACHE = os.path.join(OUT, "daily_2025_2026.csv")
YEARS = ["2025", "2026"]


def extract_snapshots():
    """每个交易日每只股票：14:30价、10:00价、截至14:30累计量、复权因子"""
    files = []
    for y in YEARS:
        files += sorted(glob.glob(os.path.join(MIN5_DIR, y, "5min", "*.csv")))
    print(f"[快照] 共 {len(files)} 个 5min 文件", flush=True)
    cols = ["证券代码", "分钟时间", "收盘价（元）", "成交量", "复权因子"]
    all_snap = []
    for i, f in enumerate(files):
        date = os.path.basename(f)[:8]
        try:
            df = pd.read_csv(f, usecols=cols, dtype={"证券代码": str},
                             encoding="utf-8-sig", low_memory=False)
        except Exception as e:
            print(f"  [跳过] {date}: {e}", flush=True)
            continue
        df["hm"] = df["分钟时间"].str[11:19]
        code = df["证券代码"].str[:6]
        keep = code.str.startswith(("60", "68", "00", "30"))
        df = df[keep].copy()
        df["code"] = code[keep].values
        r1430 = (df[df["hm"] == "14:30:00"][["code", "收盘价（元）", "复权因子"]]
                 .rename(columns={"收盘价（元）": "c1430", "复权因子": "factor"}))
        r1000 = (df[df["hm"] == "10:00:00"][["code", "收盘价（元）"]]
                 .rename(columns={"收盘价（元）": "c1000"}))
        v1430 = (df[df["hm"] <= "14:30:00"].groupby("code")["成交量"]
                 .sum().rename("v1430"))
        snap = r1430.merge(r1000, on="code", how="left").merge(v1430, on="code", how="left")
        snap["date"] = date
        all_snap.append(snap)
        if (i + 1) % 50 == 0:
            print(f"  已处理 {i + 1}/{len(files)}", flush=True)
    snap = pd.concat(all_snap, ignore_index=True).dropna(subset=["c1430"])
    snap.to_csv(SNAP_CACHE, index=False)
    print(f"[快照] 完成，{len(snap)} 行", flush=True)
    return snap


def load_daily():
    files = []
    for y in YEARS:
        files += sorted(glob.glob(os.path.join(DAILY_DIR, y, "*.csv")))
    print(f"[日线] 共 {len(files)} 个文件", flush=True)
    cols = ["交易日期", "股票代码", "股票名称", "开盘价（元）",
            "收盘价（元）", "成交量（手）", "复权因子"]
    parts = []
    for f in files:
        try:
            parts.append(pd.read_csv(f, usecols=cols,
                                     dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:
            print(f"  [跳过] {f}: {e}", flush=True)
    daily = pd.concat(parts, ignore_index=True)
    daily.to_csv(DAILY_CACHE, index=False)
    print(f"[日线] 完成，{len(daily)} 行", flush=True)
    return daily


def calc_group(dd):
    """对单只股票向量化计算信号"""
    dd = dd.sort_values("交易日期").reset_index(drop=True)
    close = dd["close_adj"].astype(float).reset_index(drop=True)
    open_ = dd["open_adj"].astype(float).reset_index(drop=True)
    vol = dd["vol_share"].astype(float).reset_index(drop=True)
    c1430 = dd["c1430_adj"].astype(float).reset_index(drop=True)
    c1000 = dd["c1000_adj"].astype(float).reset_index(drop=True)
    v1430 = dd["v1430"].astype(float).reset_index(drop=True)

    m10 = (close.shift(1).rolling(9).sum() + c1430) / 10.0
    m20 = (close.shift(1).rolling(19).sum() + c1430) / 20.0
    m10_prev = close.rolling(10).mean().shift(1)
    ma5v = (vol.shift(1).rolling(4).sum() + v1430) / 5.0

    down = (c1430 < m20) & (m10 < m20)
    yest = close.shift(1) < m10_prev
    brk = c1430 > m10
    volup = v1430 >= 1.5 * ma5v
    rise = (c1430 > open_) & (c1430 > close.shift(1)) & (c1430 < close.shift(1) * 1.05)
    sig = down & yest & brk & volup & rise

    ret = c1000.shift(-1) / c1430 - 1.0
    out = dd[["股票代码", "股票名称", "交易日期"]].copy()
    out["buy"] = c1430
    out["sell"] = c1000.shift(-1)
    out["ret"] = ret
    out["sig"] = sig
    return out[out["sig"] & out["ret"].notna()]


def main():
    t0 = time.time()
    snap = pd.read_csv(SNAP_CACHE, dtype={"code": str, "date": str})
    daily = pd.read_csv(DAILY_CACHE, dtype={"股票代码": str, "交易日期": str})
    print(f"[读取] 快照 {len(snap)} 行, 日线 {len(daily)} 行", flush=True)

    # 过滤 ST/退/北交所
    daily = daily[~daily["股票名称"].str.upper().str.contains("ST|退", na=False)]
    daily = daily[daily["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["开盘价（元）", "收盘价（元）", "成交量（手）", "复权因子"]:
        daily[c] = pd.to_numeric(daily[c], errors="coerce")
    daily = daily.dropna(subset=["收盘价（元）"])
    daily["vol_share"] = daily["成交量（手）"] * 100.0

    # 前复权：日线
    daily = daily.sort_values(["股票代码", "交易日期"])
    base = daily.groupby("股票代码")["复权因子"].last().rename("base_factor")
    daily = daily.merge(base, on="股票代码", how="left")
    daily["adj"] = daily["复权因子"] / daily["base_factor"]
    daily["close_adj"] = daily["收盘价（元）"] * daily["adj"]
    daily["open_adj"] = daily["开盘价（元）"] * daily["adj"]

    # 前复权：快照
    snap = snap.merge(
        daily[["股票代码", "交易日期", "adj"]].rename(
            columns={"股票代码": "code", "交易日期": "date"}),
        on=["code", "date"], how="left")
    snap["c1430_adj"] = snap["c1430"] * snap["adj"]
    snap["c1000_adj"] = snap["c1000"] * snap["adj"]

    # 快照并入日线
    snap_cols = snap[["code", "date", "c1430_adj", "c1000_adj", "v1430"]].rename(
        columns={"code": "股票代码", "date": "交易日期"})
    daily = daily.merge(snap_cols, on=["股票代码", "交易日期"], how="left")
    print("[合并] 完成", flush=True)

    # 向量化计算
    print("[回测] 计算信号...", flush=True)
    frames = [calc_group(g) for _, g in daily.groupby("股票代码", sort=False)]
    res = pd.concat(frames, ignore_index=True)

    print(f"[回测] 信号数 {len(res)}", flush=True)
    if len(res) == 0:
        print("零信号，结束", flush=True)
        return

    res.to_csv(os.path.join(OUT, "backtest_break10_signals.csv"), index=False)

    # 统计
    ret = res["ret"]
    wr = (ret > 0).mean() * 100
    avg = ret.mean() * 100
    med = ret.median() * 100
    pos = ret[ret > 0]
    neg = ret[ret < 0]
    pf = pos.sum() / (-neg.sum()) if len(neg) and neg.sum() < 0 else float("inf")

    print("\n========== 回测结果 ==========")
    print(f"信号数: {len(res)}")
    print(f"胜率(毛): {wr:.2f}%")
    print(f"平均收益(毛): {avg:+.3f}%")
    print(f"中位收益(毛): {med:+.3f}%")
    print(f"盈亏比 PF: {pf:.3f}")
    print(f"平均盈利: {pos.mean()*100:+.3f}%  平均亏损: {neg.mean()*100:+.3f}%")
    print(f"最大单笔: {ret.max()*100:+.3f}%  最差单笔: {ret.min()*100:+.3f}%")
    for cost, cn in [(0.0015, "0.15%"), (0.003, "0.30%")]:
        net = ret - cost
        print(f"  成本{cn} -> 净胜率{(net>0).mean()*100:.2f}%  净平均{net.mean()*100:+.3f}%")

    res["ym"] = res["交易日期"].str[:6]
    print("\n按月:")
    g2 = res.groupby("ym").agg(n=("ret", "size"),
                               胜率=("ret", lambda x: (x > 0).mean() * 100),
                               均收益=("ret", lambda x: x.mean() * 100))
    print(g2.round(2).to_string())

    print(f"\n总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
