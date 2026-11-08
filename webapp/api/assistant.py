# -*- coding: utf-8 -*-
"""助手路由（薄壳）—— 业务在 services/catalog.py 与 services/jobs.py。

核心约定：选股和回测走同一个 picker.pick()，所以「回测跑出来的成绩」就是
「按这个名单实盘能拿到的成绩」。回测必须起子进程（峰值 4G 内存，不能塞进 web 进程）。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Body, HTTPException

from quant import expr, selection
from services import catalog, jobs

router = APIRouter()

# 允许前端覆盖的参数白名单
_PARAM_KEYS = ("top_n", "hold_days", "cost", "capital", "start", "end",
               "min_price", "min_amt", "max_pct")


@router.get("/api/assistant/strategies")
def assistant_strategies():
    return catalog.strategies()


@router.get("/api/assistant/factors")
def assistant_factors():
    try:
        return catalog.factors()
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"因子表加载失败：{e}")


@router.post("/api/assistant/strategy")
def assistant_save_strategy(payload: dict = Body(...)):
    return catalog.save_formula(payload)


@router.post("/api/assistant/select")
def assistant_select(payload: dict = Body(...)):
    """跑一次选股（首次约 3 秒，命中面板缓存约 0.2 秒），结果写 signal 表 + CSV。"""
    strategy = payload.get("strategy") or selection.DEFAULT_STRATEGY
    top_n = int(payload.get("top_n") or selection.TOP_N)
    target = payload.get("date") or None
    filters = {k: payload[k] for k in ("min_price", "min_amt", "max_pct")
               if payload.get(k) is not None}
    t0 = time.time()
    try:
        res = selection.select(strategy, top_n, target, filters)
    except FileNotFoundError as e:
        raise HTTPException(500, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"选股失败：{e}")

    res["elapsed"] = round(time.time() - t0, 2)
    try:
        res["csv"] = selection.save_csv(res)
        res["db_msg"] = selection.save_db(res)
    except Exception as e:                      # noqa: BLE001
        res["db_msg"] = f"落盘/写库失败：{e}"
    return res


@router.post("/api/assistant/backtest")
def assistant_backtest(payload: dict = Body(...)):
    """起一个子进程跑回测。同时只允许一个（内存 4G，并发会爆）。"""
    strategy = payload.get("strategy")
    try:
        expr.resolve(strategy)                  # 代码策略或 formula 策略，先验一次
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(400, f"未知策略：{strategy}（{e}）")

    params = {k: payload[k] for k in _PARAM_KEYS
              if k in payload and payload[k] is not None}
    return jobs.start(strategy, params, payload.get("name"))


@router.get("/api/assistant/backtest/{job_id}")
def assistant_backtest_status(job_id: str):
    return jobs.status(job_id)


@router.get("/api/assistant/history")
def assistant_history(limit: int = 12):
    return catalog.history(limit)
