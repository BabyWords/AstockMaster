# -*- coding: utf-8 -*-
"""交易账本路由：读 trade 表，返回可直接画在 K 线上的买卖点。

GET /api/trades?code=000338
    ymd       对齐到的交易日（8 位，供前端定位 K 线下标）
    date      同上（ISO 格式）
    side      buy / sell
    price     原始成交价
    adj_price 前复权价（与 /api/kline 同口径：价 × 当日因子 ÷ 最新因子）
    shares    股数
    note      备注

库不可用 / 无记录 → 空列表，页面照常（只是没有标注）。
"""
from __future__ import annotations

import bisect

from fastapi import APIRouter

from config import dbmod
from services.store import load_stock

router = APIRouter()


def _load_trades(code):
    if dbmod is None:
        return None
    try:
        with dbmod.session() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select trade_date, side, price, shares, name, note "
                    "from trade where code = %s order by trade_date, id", (code,))
                return cur.fetchall()
    except Exception:                           # noqa: BLE001
        return None


@router.get("/api/trades")
def trades(code: str = ""):
    code = str(code).split(".")[0].strip()
    if not code.isdigit():
        return {"code": code, "trades": [], "source": "bad-code"}

    rows = _load_trades(code)
    if rows is None:
        return {"code": code, "trades": [], "source": "db-down"}
    if not rows:
        return {"code": code, "trades": [], "source": "db"}

    # 复权换算：与 load_stock 完全同口径（价 × 当日因子 ÷ 最新因子），
    # 这样标出来的价格和 K 线纵轴能对上。
    try:
        d = load_stock(code)
        days = [str(x) for x in d["交易日期"].tolist()]
        factors = d["复权因子"].astype("float64").tolist()
    except Exception:                           # noqa: BLE001
        return {"code": code, "trades": [], "source": "no-data"}

    base = factors[-1]
    out = []
    for tdate, side, price, shares, name, note in rows:
        ymd = str(tdate).replace("-", "")[:8]
        # 因子取「成交日或之前最近一个交易日」的（非交易日成交也换算得准）
        i = max(0, bisect.bisect_right(days, ymd) - 1)
        adj = float(price) * factors[i] / base
        out.append({
            "ymd": ymd,
            "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
            "trade_date": ymd,
            "side": str(side),
            "price": round(float(price), 3),
            "adj_price": round(adj, 3),
            "shares": int(shares),
            "name": name or "",
            "note": note or "",
        })
    return {"code": code, "trades": out, "source": "db"}
