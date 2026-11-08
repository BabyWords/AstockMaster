# -*- coding: utf-8 -*-
"""实时行情路由：腾讯实时报价 + 本地收盘价兜底。"""
from __future__ import annotations

import time

from fastapi import APIRouter

from services import market
from services.store import load_stock

router = APIRouter()


@router.get("/api/realtime")
def realtime(codes: str = ""):
    """/api/realtime?codes=600036,000338（也支持单只）"""
    return {"quotes": market.realtime_batch(codes.split(","))}


# ============================ 本地收盘行情（降级用） ============================
_Q_CACHE: dict = {}      # code -> (ts, quote)
_Q_TTL = 300             # 5 分钟（数据每天才更新一次）
_Q_MAX = 256


def _quote(code):
    """取单只股票最新收盘与涨跌幅（原始价，未复权）。

    走 store.load_stock（带 LRU），不再自己 open(pkl) —— 那是每次请求一次磁盘读。
    """
    now = time.time()
    hit = _Q_CACHE.get(code)
    if hit and now - hit[0] < _Q_TTL:
        return hit[1]
    try:
        d = load_stock(code)
    except Exception:                           # noqa: BLE001
        return None
    close = d["收盘价（元）"]
    if len(close) == 0:
        return None
    c0 = float(close.iloc[-1])
    p0 = float(close.iloc[-2]) if len(close) > 1 else c0
    item = {
        "code": code,
        "name": str(d["股票名称"].iloc[-1]),
        "date": str(d["交易日期"].iloc[-1]),
        "close": round(c0, 2),
        "prev_close": round(p0, 2),
        "pct": round((c0 - p0) / p0 * 100, 2) if p0 else 0.0,
    }
    if len(_Q_CACHE) > _Q_MAX:
        _Q_CACHE.clear()
    _Q_CACHE[code] = (now, item)
    return item


@router.get("/api/quotes")
def quotes(codes: str = ""):
    """/api/quotes?codes=600036,000338"""
    out = []
    for c in [x.strip() for x in codes.split(",") if x.strip()][:80]:
        q = _quote(c.split(".")[0])
        if q:
            out.append(q)
    return {"quotes": out}
