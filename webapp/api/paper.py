# -*- coding: utf-8 -*-
"""模拟盘路由（薄壳）—— 计算与存取都在 services/paper.py。

GET    /api/paper/list        组合清单（含当前收益，用于下拉框）
POST   /api/paper/create      新建组合（代码列表 + 买入日 + 本金）
GET    /api/paper/{pid}       组合详情：逐日净值 + 持仓明细 + 到期状态
DELETE /api/paper/{pid}       删除组合
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from services import paper as svc

router = APIRouter()


@router.get("/api/paper/list")
def paper_list():
    svc.need_db()
    try:
        return {"portfolios": svc.list_portfolios(), "db": True}
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(503, f"读组合失败：{e}")


@router.post("/api/paper/create")
def paper_create(payload: dict = Body(...)):
    svc.need_db()
    return svc.create(payload)


@router.get("/api/paper/{pid}")
def paper_detail(pid: int):
    svc.need_db()
    try:
        return svc.cached(pid)
    except HTTPException:
        raise
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"计算净值失败：{e}")


@router.delete("/api/paper/{pid}")
def paper_delete(pid: int):
    svc.need_db()
    try:
        return svc.delete(pid)
    except HTTPException:
        raise
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"删除失败：{e}")
