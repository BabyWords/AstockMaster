# -*- coding: utf-8 -*-
"""自选股路由：Postgres watchlist 表为主，本地 JSON 降级。"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Body

from config import DEFAULT_WATCH, WL_PATH, dbmod

router = APIRouter()


def _wl_from_db():
    """读自选表；库不可用返回 None（调用方据此降级）。"""
    if dbmod is None:
        return None
    try:
        with dbmod.session() as conn:
            with conn.cursor() as cur:
                cur.execute("select code from watchlist order by sort_order, added_at")
                return [r[0] for r in cur.fetchall()]
    except Exception:                           # noqa: BLE001
        return None


def _wl_to_db(codes):
    """整表覆盖写入自选。返回是否写成功。"""
    if dbmod is None:
        return False
    try:
        with dbmod.session() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from watchlist")
                for i, c in enumerate(codes):
                    cur.execute(
                        "insert into watchlist (code, sort_order) values (%s, %s) "
                        "on conflict (code) do nothing", (c, i))
        return True
    except Exception:                           # noqa: BLE001
        return False


@router.get("/api/watchlist")
def get_watchlist():
    codes = _wl_from_db()
    if codes is not None:
        return {"codes": codes, "source": "db"}
    if os.path.exists(WL_PATH):
        try:
            with open(WL_PATH, encoding="utf-8") as f:
                c = json.load(f)
            if isinstance(c, list):
                return {"codes": [str(x) for x in c], "source": "json"}
        except Exception:                       # noqa: BLE001
            pass
    return {"codes": list(DEFAULT_WATCH), "source": "default"}


@router.post("/api/watchlist")
def set_watchlist(payload: dict = Body(...)):
    codes = []
    for c in payload.get("codes", []) or []:
        c = str(c).split(".")[0].strip()
        if c and c not in codes:
            codes.append(c)
    codes = codes[:80]
    # 双写：库是主存储，JSON 只作降级快照（库没起来时页面还能用）
    ok_db = _wl_to_db(codes)
    tmp = WL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False)
    os.replace(tmp, WL_PATH)
    return {"ok": True, "codes": codes, "db": ok_db}
