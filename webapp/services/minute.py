# -*- coding: utf-8 -*-
"""分时（1 分钟）payload —— 本地分钟 CSV 优先，当日盘中走腾讯实时分时。
======================================================================

本地文件：{分钟级行情}/{年}/1min/{日期}_*1分钟K线*.csv（全市场一文件，按行首代码过滤）
缓存：    data_store/minutes/{code}/{date}.pkl（按源文件 mtime 失效）
"""
from __future__ import annotations

import glob
import io
import json
import os
import pickle
import subprocess
import time
import urllib.request

import numpy as np
import pandas as pd
from fastapi import HTTPException

from config import MIN_CACHE, MIN_ROOT
from quant import config as qcfg

from . import market
from .store import load_stock, series

_MIN_COLS = ["sym", "name", "trade_date", "minute", "open", "high", "low",
             "close", "volume", "amount", "factor"]

MIN_RT_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code="
_MIN_RT_TTL = 3.0
_MIN_RT_CACHE: dict = {}
_MIN_RT_MAX = 128


def code_suffix(code):
    """股票代码 -> 交易所后缀（用于匹配分钟文件里的证券代码）。"""
    c = str(code)
    if c[0] in "69":
        return ".SH"
    if c[0] in "023":
        return ".SZ"
    if c[0] in "48":
        return ".BJ"
    return ".SH"


def realtime(code, date):
    """当日实时分时（腾讯）。只有当 date 就是今天时才返回，历史日期返回 None。"""
    qs = market.realtime_batch([code])
    if not qs:
        return None
    q = qs[0]
    ts = q.get("time") or ""
    if ts[:10].replace("-", "") != str(date):
        return None                       # 不是今天，交给本地文件处理

    now = time.time()
    hit = _MIN_RT_CACHE.get(code)
    if hit and now - hit[0] < _MIN_RT_TTL:
        return hit[1]

    sym = market.rt_prefix(code) + code
    try:
        req = urllib.request.Request(MIN_RT_URL + sym, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        })
        js = json.loads(market.opener().open(req, timeout=5).read().decode("utf-8", "ignore"))
    except Exception as e:                          # noqa: BLE001
        print(f"[minute] 实时分时拉取失败：{e}")
        return None

    node = (js.get("data") or {}).get(sym) or {}
    rows = ((node.get("data") or {}).get("data")) or []
    if not rows:
        return None

    # 每行: "0930 价格 累计成交量(手) 累计成交额(元)"
    times, price, vol, amt = [], [], [], []
    pv = pa = 0.0
    for line in rows:
        p = line.split()
        if len(p) < 4:
            continue
        t = p[0]
        if not t.isdigit() or t > "1500":           # 15:00 之后的数据不要
            continue
        try:
            px, cv, ca = float(p[1]), float(p[2]), float(p[3])
        except ValueError:
            continue
        times.append(t[:2] + ":" + t[2:])
        price.append(round(px, 2))
        vol.append(round(max(0.0, cv - pv) * 100))  # 手 → 股（与本地 CSV 口径一致）
        amt.append(round(max(0.0, ca - pa)))
        pv, pa = cv, ca

    if not times:
        return None

    avg, sv, sa = [], 0.0, 0.0
    for i, (v, a) in enumerate(zip(vol, amt)):
        sv += v
        sa += a
        avg.append(round(sa / sv, 3) if sv > 0 else price[i])

    res = {
        "code": code, "name": q["name"], "date": str(date),
        "times": times, "price": price, "avg": avg,
        "volume": vol, "amount": amt,
        "prev_close": round(float(q["prev_close"]), 2),
        "day": {"open": q["open"], "high": q["high"], "low": q["low"],
                "close": q["price"], "volume": q["volume"]},
        "pct": q["pct"],
        "live": True,
    }
    if len(_MIN_RT_CACHE) > _MIN_RT_MAX:
        _MIN_RT_CACHE.clear()
    _MIN_RT_CACHE[code] = (now, res)
    return res


def _local_file(date):
    return glob.glob(os.path.join(MIN_ROOT, date[:4], "1min", f"{date}_*1分钟K线*.csv"))


def _parse_local(code, date, src):
    """从全市场分钟 CSV 里抽出单只股票，算前复权价/均价，写入分片缓存。"""
    cache_p = os.path.join(MIN_CACHE, code, f"{date}.pkl")
    src_mtime = os.path.getmtime(src)
    if os.path.exists(cache_p) and os.path.getmtime(cache_p) >= src_mtime:
        with open(cache_p, "rb") as f:
            return pickle.load(f)

    sym = code + code_suffix(code)
    try:
        out = subprocess.run(["grep", "-a", f"^{sym},", src],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"读取分钟数据失败：{e}")
    if not out.strip():
        raise HTTPException(404, f"{date} 没有 {code} 的分时数据（停牌或当日无成交）")

    df = pd.read_csv(io.StringIO(out), header=None, names=_MIN_COLS)
    df = df.sort_values("minute").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume", "amount", "factor"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])

    # 前复权：与日线同口径（价 × 当日因子 ÷ 最新因子）
    daily = load_stock(code)
    latest_f = float(daily["复权因子"].iloc[-1])
    ratio = df["factor"] / latest_f

    price = (df["close"] * ratio).round(2)
    cum_amt = df["amount"].cumsum()
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    avg = ((cum_amt / cum_vol) * ratio).round(3)

    # 昨收：日线里该日的前一根（前复权）
    dts = daily["交易日期"].astype(str)
    hit = dts[dts == date]
    if len(hit):
        i = daily.index.get_loc(hit.index[0])
        prev_close = float(daily["close"].iloc[i - 1]) if i > 0 else float(price.iloc[0])
        o = float(daily["open"].iloc[i]); h = float(daily["high"].iloc[i])
        l = float(daily["low"].iloc[i]); cl = float(daily["close"].iloc[i])
        dv = float(daily["volume"].iloc[i])
    else:
        prev_close = float(price.iloc[0])
        o = h = l = cl = float(price.iloc[0])
        dv = float(df["volume"].sum()) / 100.0

    res = {
        "code": code, "name": str(daily["股票名称"].iloc[-1]), "date": date,
        "times": [str(t)[11:16] for t in df["minute"]],
        "price": series(price, 2),
        "avg": series(avg, 3),
        "volume": series(df["volume"], 0),          # 股
        "amount": series(df["amount"], 0),          # 元
        "prev_close": round(prev_close, 2),
        "day": {"open": round(o, 2), "high": round(h, 2), "low": round(l, 2),
                "close": round(cl, 2), "volume": round(dv, 0)},
        "pct": round((cl - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
    }

    qcfg.ensure_dir(os.path.dirname(cache_p))
    tmp = cache_p + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(res, f, protocol=4)
    os.replace(tmp, cache_p)
    return res


def build(code: str, date: str):
    """返回某只股票某一天的分时 payload（YYYYMMDD 或 YYYY-MM-DD）。"""
    code = str(code).split(".")[0]
    date = date.replace("-", "")
    if len(date) != 8 or not date.isdigit():
        raise HTTPException(400, "日期格式应为 YYYYMMDD")

    files = _local_file(date)
    if not files:
        # 当天的分钟文件要等网盘同步，盘中先用实时分时顶上
        rt = realtime(code, date)
        if rt is not None:
            return rt
        raise HTTPException(404, f"{date} 没有分钟数据文件")
    return _parse_local(code, date, files[0])
