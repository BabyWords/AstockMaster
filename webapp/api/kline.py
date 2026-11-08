# -*- coding: utf-8 -*-
"""K 线 / 搜索 / 元信息路由。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from services import chart
from services.store import meta as store_meta
from services.store import search as store_search

router = APIRouter()


@router.get("/api/search")
def search(q: str = ""):
    return {"results": store_search(q)}


@router.get("/api/meta")
def meta():
    return store_meta()


@router.get("/api/kline")
def kline(code: str, period: str = "day", live: int = 0, request: Request = None):
    payload, etag = chart.build(code, period, bool(live))
    if request is not None and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )
