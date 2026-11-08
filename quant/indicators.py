# -*- coding: utf-8 -*-
"""
A股技术指标计算库
==================
从全样本日线缓存读取单只股票，做前复权后计算全套技术指标。
纯函数设计，分钟级数据（同为 OHLCV）也可复用同一批指标函数。

【口径】全部对齐通达信，关键点：
  - 技术指标一律用「前复权价」计算（收盘×复权因子÷期末基准），消除除权跳空。
  - EMA  用 alpha=2/(N+1)（等价 ewm(span=N, adjust=False)）。
  - SMA  用递归 Y=(M*X+(N-M)*Y')/N，从第一个非 NaN 起算。
  - BOLL 标准差用总体标准差（ddof=0）。
  - 成交量单位：手；成交额单位：万元（与日线缓存一致）。

【指标清单】
  均线    MA5/10/20/60, EMA12/26
  MACD(12,26,9)   DIF / DEA / 柱(2*(DIF-DEA))
  KDJ(9,3,3)      K / D / J
  RSI(6/12/24)    通达信 SMA 口径
  BOLL(20,2)      上轨 / 中轨 / 下轨
  BIAS(6/12/24)   乖离率
  WR(10/6)        威廉指标
  ATR(14)         真实波幅
  DMI(14,6)       PDI / MDI / ADX / ADXR
  OBV             能量潮（量单位：手）
  量能    MAVOL5/10、量比

【用法】
  python indicators.py 600036               # 打印最近 15 个交易日核心指标
  python indicators.py 600036 --rows 30     # 看最近 30 天
  python indicators.py 600036 --full        # 打印全部指标列
  python indicators.py 600036 --csv         # 保存全指标到 数据/指标_600036.csv
  python indicators.py 600036 --end 20261021
"""
import os
import argparse
import pandas as pd
import numpy as np

from .config import CACHE      # 路径统一在 quant.config 推导

RAW_COLS = ["交易日期", "股票代码", "股票名称", "开盘价（元）", "最高价（元）", "最低价（元）",
            "收盘价（元）", "昨收价（元）", "涨跌幅（%）", "成交量（手）", "成交额（万元）",
            "复权因子", "换手率（%）", "量比"]


# ============================ 基础工具 ============================
def _sma(s, n, m=1):
    """通达信 SMA(X,N,M)：Y = (M*X + (N-M)*Y') / N，从第一个非 NaN 起算。"""
    s = np.asarray(s, dtype=float)
    r = np.full(len(s), np.nan)
    valid = ~np.isnan(s)
    if not valid.any():
        return r
    start = int(np.argmax(valid))
    r[start] = s[start]
    for i in range(start + 1, len(s)):
        r[i] = (m * s[i] + (n - m) * r[i - 1]) / n
    return r


def load_stock(code):
    """读缓存，取单只股票并做前复权。

    code 支持 '600036' 或 '600036.SH'（自动去掉交易所后缀）。
    返回含 open/high/low/close（前复权）、volume/amount/pct 等列的 DataFrame，
    已按日期升序、去掉无价格/无复权因子的行。
    """
    code = str(code).split(".")[0]
    df = pd.read_csv(CACHE, usecols=[c for c in RAW_COLS if c in RAW_COLS],
                     dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    d = df[df["股票代码"] == code].copy()
    if d.empty:
        raise ValueError(f"缓存中找不到股票代码 {code}")
    for c in ["开盘价（元）", "最高价（元）", "最低价（元）", "收盘价（元）", "昨收价（元）",
              "涨跌幅（%）", "成交量（手）", "成交额（万元）", "复权因子", "换手率（%）", "量比"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.sort_values("交易日期").reset_index(drop=True)
    d = d.dropna(subset=["收盘价（元）", "复权因子"]).reset_index(drop=True)

    # 前复权（以样本末期为基准）
    base = d["复权因子"].iloc[-1]
    for raw, adj in [("开盘价（元）", "open"), ("最高价（元）", "high"),
                     ("最低价（元）", "low"), ("收盘价（元）", "close")]:
        d[adj] = d[raw] * d["复权因子"] / base

    d = d.rename(columns={"成交量（手）": "volume", "成交额（万元）": "amount",
                          "涨跌幅（%）": "pct"})
    if "换手率（%）" in d.columns:
        d = d.rename(columns={"换手率（%）": "turn"})
    if "量比" in d.columns:
        d = d.rename(columns={"量比": "volume_ratio"})
    return d


# ============================ 指标函数（纯函数，输入 Series）============================
def ma(s, n):
    return s.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def macd(close, fast=12, slow=26, signal=9):
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = 2 * (dif - dea)
    return dif, dea, hist


def kdj(high, low, close, n=9, k=3, d=3):
    llv = low.rolling(n).min()
    hhv = high.rolling(n).max()
    rsv = (close - llv) / (hhv - llv) * 100
    K = _sma(rsv.values, k, 1)
    D = _sma(K, d, 1)
    return K, D, 3 * K - 2 * D


def rsi(close, n):
    lc = close.shift(1)
    diff = close - lc
    up = diff.clip(lower=0)
    absd = diff.abs()
    return _sma(up.values, n, 1) / _sma(absd.values, n, 1) * 100


def boll(close, n=20, m=2):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)
    return mid + m * std, mid, mid - m * std


def bias(close, n):
    ma_n = close.rolling(n).mean()
    return (close - ma_n) / ma_n * 100


def wr(high, low, close, n=10):
    hhv = high.rolling(n).max()
    llv = low.rolling(n).min()
    return (hhv - close) / (hhv - llv) * 100


def _true_range(high, low, close):
    prev_c = close.shift(1)
    return pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()],
                     axis=1).max(axis=1)


def atr(high, low, close, n=14):
    return _true_range(high, low, close).rolling(n).mean()


def dmi(high, low, close, n=14, m=6):
    prev_h = high.shift(1)
    prev_l = low.shift(1)
    tr = _true_range(high, low, close)
    hd = high - prev_h
    ld = prev_l - low
    dmp = pd.Series(np.where((hd > 0) & (hd > ld), hd, 0.0), index=close.index)
    dmm = pd.Series(np.where((ld > 0) & (ld > hd), ld, 0.0), index=close.index)
    mtr = tr.rolling(n).sum()
    pdi = dmp.rolling(n).sum() / mtr * 100
    mdi = dmm.rolling(n).sum() / mtr * 100
    dx = ((mdi - pdi).abs() / (mdi + pdi) * 100).replace([np.inf, -np.inf], 0.0)
    adx = dx.rolling(m).mean()
    adxr = (adx + adx.shift(m)) / 2
    return pdi, mdi, adx, adxr


def obv(close, volume):
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


# ============================ 汇总 ============================
def compute_all(d):
    """输入 load_stock 的结果，返回追加全套指标列后的 DataFrame。"""
    c, h, l = d["close"], d["high"], d["low"]
    v = d["volume"]
    out = d.copy()

    out["MA5"], out["MA10"], out["MA20"], out["MA60"] = ma(c, 5), ma(c, 10), ma(c, 20), ma(c, 60)
    out["EMA12"], out["EMA26"] = ema(c, 12), ema(c, 26)
    out["MACD_DIF"], out["MACD_DEA"], out["MACD_HIST"] = macd(c)
    out["KDJ_K"], out["KDJ_D"], out["KDJ_J"] = kdj(h, l, c)
    out["RSI6"], out["RSI12"], out["RSI24"] = rsi(c, 6), rsi(c, 12), rsi(c, 24)
    out["BOLL_UPPER"], out["BOLL_MID"], out["BOLL_LOWER"] = boll(c)
    out["BIAS6"], out["BIAS12"], out["BIAS24"] = bias(c, 6), bias(c, 12), bias(c, 24)
    out["WR10"], out["WR6"] = wr(h, l, c, 10), wr(h, l, c, 6)
    out["ATR14"] = atr(h, l, c)
    out["DMI_PDI"], out["DMI_MDI"], out["DMI_ADX"], out["DMI_ADXR"] = dmi(h, l, c)
    out["OBV"] = obv(c, v)
    out["MAVOL5"], out["MAVOL10"] = v.rolling(5).mean(), v.rolling(10).mean()
    return out


def get_indicators(code, end=None, rows=None):
    """主入口：计算单只股票全套指标，可选截取日期区间 / 最近 N 行。"""
    d = compute_all(load_stock(code))
    if end:
        d = d[d["交易日期"] <= str(end)]
    if rows:
        d = d.tail(rows)
    return d


# 打印用核心列（人看，避免全列过宽）
CORE_COLS = ["交易日期", "收盘价（元）", "pct", "MA5", "MA20",
             "MACD_DIF", "MACD_HIST", "KDJ_K", "KDJ_D", "KDJ_J",
             "RSI6", "BOLL_UPPER", "BOLL_MID", "BOLL_LOWER", "WR10", "ATR14", "DMI_ADX"]


def _print(d, full=False, code=""):
    name = d["股票名称"].iloc[-1] if "股票名称" in d.columns else code
    print("=" * 100)
    print(f"【{code} {name}】 技术指标 · 共 {len(d)} 行 · 前复权")
    print("=" * 100)
    cols = list(d.columns) if full else CORE_COLS
    cols = [c for c in cols if c in d.columns]
    view = d[cols].copy()
    view["交易日期"] = view["交易日期"].str[4:]
    view = view.rename(columns={"交易日期": "日期", "收盘价（元）": "收盘", "pct": "涨跌%"})
    for c in ["MA5", "MA20", "BOLL_UPPER", "BOLL_MID", "BOLL_LOWER", "ATR14"]:
        if c in view.columns:
            view[c] = view[c].round(2)
    for c in ["MACD_DIF", "MACD_HIST"]:
        if c in view.columns:
            view[c] = view[c].round(3)
    for c in ["KDJ_K", "KDJ_D", "KDJ_J", "RSI6", "WR10", "DMI_ADX"]:
        if c in view.columns:
            view[c] = view[c].round(1)
    if "涨跌%" in view.columns:
        view["涨跌%"] = view["涨跌%"].round(2)
    print(view.to_string(index=False))


def _main(argv=None):
    ap = argparse.ArgumentParser(description="A股技术指标计算库")
    ap.add_argument("code", help="股票代码，如 600036 或 600036.SH")
    ap.add_argument("--rows", type=int, default=15, help="打印最近多少行（默认15）")
    ap.add_argument("--end", help="截止日期 YYYYMMDD")
    ap.add_argument("--full", action="store_true", help="打印全部指标列")
    ap.add_argument("--csv", action="store_true", help="保存全指标 CSV 到 数据/ 目录")
    args = ap.parse_args(argv)

    d = get_indicators(args.code, end=args.end)
    print_row = d.tail(args.rows)
    _print(print_row, full=args.full, code=args.code)

    if args.csv:
        outdir = os.path.abspath(os.path.join(os.path.dirname(CACHE), "..", "数据"))
        os.makedirs(outdir, exist_ok=True)
        out_csv = os.path.join(outdir, f"指标_{args.code.split('.')[0]}.csv")
        d.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"\n已保存全套指标（{len(d)} 行）→ {out_csv}")


if __name__ == "__main__":
    _main()
