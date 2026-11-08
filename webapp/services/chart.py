# -*- coding: utf-8 -*-
"""K 线 payload —— 指标计算、盘中实时 bar 合并、内容指纹（ETag）。
===============================================================

路由层只负责 HTTP（304 判断、gzip 之外的 header），这里返回
(payload_dict, etag)，纯计算。
"""
from __future__ import annotations

import pandas as pd

from quant import indicators as ind

from . import market
from .store import etag_of, load_stock, resample, series


def merge_live(d, code):
    """把当日实时 bar 合并进日线（只做临时展示，不落盘）。

    pkl 里存原始价，load_stock 已按「最后一天的复权因子」做前复权，
    所以前复权序列的最后一天恰好等于原始价；只要当天没有除权，
    实时价可以直接接到尾部，不需要再换算。当天真除权时会有跳空，
    等网盘数据到了自然修正。
    """
    qs = market.realtime_batch([code])
    if not qs:
        return d
    q = qs[0]
    ts = q.get("time") or ""
    if len(ts) < 10 or q.get("open") is None or q.get("price") is None:
        return d
    day = ts[:10].replace("-", "")
    if not day.isdigit():
        return d

    vals = {
        "open": float(q["open"]),
        "high": float(q["high"] or q["price"]),
        "low": float(q["low"] or q["price"]),
        "close": float(q["price"]),
        "volume": float(q.get("volume") or 0),
        "amount": float(q.get("amount") or 0),
    }

    d = d.copy()
    last = str(d["交易日期"].iloc[-1])
    if day == last:                       # 已经有一根 → 盘中更新它
        i = d.index[-1]
        for k, v in vals.items():
            d.at[i, k] = v
    elif day > last:                      # 还没有 → 追加今天这根
        new = d.iloc[-1:].copy()
        new["交易日期"] = day
        for k, v in vals.items():
            new[k] = v
        d = pd.concat([d, new], ignore_index=True)
    return d


def build(code: str, period: str = "day", live: bool = False):
    """返回 (payload, etag)。payload 结构与前端约定的字段一一对应。"""
    if period not in ("day", "week", "month"):
        period = "day"
    d = load_stock(code)
    name = str(d["股票名称"].iloc[-1])
    if live:
        d = merge_live(d, code)          # 盘中把今天这根接上去
    d = resample(d, period)

    # 内容指纹只看「会改变输出」的东西：根数 + 最后一根的 OHLCV。
    # 盘中价格没变（小盘股常见）就直接 304 —— 省掉全部指标计算和 500KB 传输。
    last = d.iloc[-1]
    etag = etag_of(code, period, len(d), d.index[-1],
                   round(float(last["open"]), 2), round(float(last["close"]), 2),
                   round(float(last["low"]), 2), round(float(last["high"]), 2),
                   round(float(last["volume"]), 0))

    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    pct_chg = (c.pct_change() * 100).round(2)   # 涨跌幅%（前复权后等价于原始涨跌幅）

    ma5, ma10, ma20, ma30 = ind.ma(c, 5), ind.ma(c, 10), ind.ma(c, 20), ind.ma(c, 30)
    ma60, ma120 = ind.ma(c, 60), ind.ma(c, 120)
    bu, bm, bl = ind.boll(c)
    dif, dea, hist = ind.macd(c)
    K, D, J = ind.kdj(h, l, c)
    r6, r12, r24 = ind.rsi(c, 6), ind.rsi(c, 12), ind.rsi(c, 24)
    vma5, vma10 = v.rolling(5).mean(), v.rolling(10).mean()
    wr6, wr10 = ind.wr(h, l, c, 6), ind.wr(h, l, c, 10)
    b6, b12, b24 = ind.bias(c, 6), ind.bias(c, 12), ind.bias(c, 24)
    pdi, mdi, adx, adxr = ind.dmi(h, l, c)
    obv = ind.obv(c, v)
    atr14 = ind.atr(h, l, c, 14)

    dates = [ts.strftime("%Y-%m-%d") for ts in d.index]
    # ECharts candlestick 顺序: [open, close, low, high]
    ohlc = [[round(float(o), 2), round(float(c_), 2), round(float(lo), 2), round(float(hi), 2)]
            for o, c_, lo, hi in zip(d["open"], d["close"], d["low"], d["high"])]

    payload = {
        "code": code, "name": name, "period": period,
        "dates": dates, "ohlc": ohlc,
        "volume": series(v, 0), "amount": series(d["amount"], 0), "pct_chg": series(pct_chg, 2),
        "ma": {"ma5": series(ma5, 2), "ma10": series(ma10, 2), "ma20": series(ma20, 2),
               "ma30": series(ma30, 2), "ma60": series(ma60, 2), "ma120": series(ma120, 2)},
        "boll": {"upper": series(bu, 2), "mid": series(bm, 2), "lower": series(bl, 2)},
        "macd": {"dif": series(dif, 3), "dea": series(dea, 3), "hist": series(hist, 3)},
        "kdj": {"k": series(K, 1), "d": series(D, 1), "j": series(J, 1)},
        "rsi": {"rsi6": series(r6, 1), "rsi12": series(r12, 1), "rsi24": series(r24, 1)},
        "wr": {"wr6": series(wr6, 1), "wr10": series(wr10, 1)},
        "bias": {"bias6": series(b6, 2), "bias12": series(b12, 2), "bias24": series(b24, 2)},
        "dmi": {"pdi": series(pdi, 1), "mdi": series(mdi, 1),
                "adx": series(adx, 1), "adxr": series(adxr, 1)},
        "obv": series(obv / 10000.0, 2),
        "atr": series(atr14, 3),
        "vol_ma": {"vma5": series(vma5, 0), "vma10": series(vma10, 0)},
    }
    return payload, etag
