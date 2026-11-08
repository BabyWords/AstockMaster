# -*- coding: utf-8 -*-
"""分时（1 分钟）路由。"""
from __future__ import annotations

from fastapi import APIRouter

from services import minute as minute_svc

router = APIRouter()


@router.get("/api/minute")
def minute(code: str, date: str):
    """某只股票某一天的 1 分钟分时（价格 / 均价 / 成交量），前复权与日线同口径。

    date: YYYYMMDD 或 YYYY-MM-DD；当日盘中自动回落实时分时。
    """
    return minute_svc.build(code, date)
