# -*- coding: utf-8 -*-
"""单股行情读取层 —— 分片读取（LRU）+ 重采样 + JSON 序列化 + 搜索。
===================================================================

数据来源：data_store/stocks/{code}.pkl（由 build_store.py 预构建，存原始价 + 复权因子）。
查询时按「该股最新因子」做前复权，与 quant.data.preprocess / indicators 同口径。
"""
from __future__ import annotations

import hashlib
import os
import pickle
import threading

import numpy as np
import pandas as pd
from fastapi import HTTPException

from config import STOCKS, stock_list

# ============================ 单股读取（LRU） ============================
_LOAD_CACHE: dict = {}                  # code -> (mtime, DataFrame)
_LOAD_LOCK = threading.Lock()
_LOAD_MAX = 24                          # 约 24 × 200KB，随手翻几只票不会反复读盘


def load_stock(code) -> pd.DataFrame:
    """读单只股票分片并做前复权。返回的 DataFrame 视为只读（下游都要先 copy）。"""
    code = str(code).split(".")[0]
    p = os.path.join(STOCKS, f"{code}.pkl")
    if not os.path.exists(p):
        raise HTTPException(404, f"未找到股票代码 {code}（可能分片尚未构建完）")
    mt = os.path.getmtime(p)
    with _LOAD_LOCK:
        hit = _LOAD_CACHE.get(code)
        if hit and hit[0] == mt:
            return hit[1]

    with open(p, "rb") as f:
        d = pickle.load(f)
    base = d["复权因子"].iloc[-1]
    for raw, adj in [("开盘价（元）", "open"), ("最高价（元）", "high"),
                     ("最低价（元）", "low"), ("收盘价（元）", "close")]:
        d[adj] = d[raw] * d["复权因子"] / base
    d = d.rename(columns={"成交量（手）": "volume", "成交额（万元）": "amount"})

    with _LOAD_LOCK:
        if len(_LOAD_CACHE) >= _LOAD_MAX:
            _LOAD_CACHE.pop(next(iter(_LOAD_CACHE)))     # FIFO，够用
        _LOAD_CACHE[code] = (mt, d)
    return d


def resample(d, period):
    """日线直接返回；周/月线按周期聚合 OHLCV。"""
    d = d.copy()
    d["date"] = pd.to_datetime(d["交易日期"], format="%Y%m%d")
    if period == "day":
        return d.set_index("date")
    d = d.set_index("date")
    rule = "W-FRI" if period == "week" else "ME"
    return d.resample(rule).agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "amount": "sum",
    }).dropna(subset=["open", "close"])


def series(s, nd=3):
    """Series/ndarray -> list，NaN/Inf 转 None，四舍五入到 nd 位。

    向量化实现：np.round + tolist。原来逐元素 pd.isna() 要 10ms（一条 K 线
    有 25 条序列），现在约 1ms，是整个接口最大的一块 CPU。
    """
    a = np.asarray(s, dtype="float64")
    if a.size == 0:
        return []
    r = np.round(a, nd)
    out = r.tolist()
    for i in np.flatnonzero(~np.isfinite(r)):   # NaN / ±Inf 都要变 null，否则 JSON 非法
        out[i] = None
    return out


def etag_of(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
    return '"%s"' % h


def search(q: str, limit: int = 20):
    """按代码或名称模糊搜索（代码前缀/包含，名称包含）。"""
    q = (q or "").strip()
    if not q or not stock_list:
        return []
    res = []
    for m in stock_list:
        if q in m["code"] or q in m["name"]:
            res.append(m)
            if len(res) >= limit:
                break
    return res


def meta():
    return {"count": len(stock_list),
            "last_date": max((m.get("last_date") or "" for m in stock_list), default="")}
