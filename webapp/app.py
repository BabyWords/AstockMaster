# -*- coding: utf-8 -*-
"""A股分析系统后端（FastAPI）—— 组装层。
========================================
本文件只做三件事：创建 app、挂静态资源、挂路由。

分层：
    config.py          路径常量 + sys.path 引导 + 股票索引 + 数据库句柄
    services/          领域逻辑（store / market / chart / minute / paper / catalog / jobs）
    api/               路由（参数校验 + 协议转换，不含算法）

数据来源：data_store/ 下的分片（由 build_store.py 预构建），查询时只读单只股票的
pkl，毫秒级。指标复用 quant/indicators.py 的纯函数（通达信口径）。

启动：./start.sh（内部 uvicorn app:app）
"""
import os

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config                                       # noqa: F401  先导入：设置 sys.path、加载股票索引
from api import assistant, kline, minute, paper, realtime, trades, watchlist

app = FastAPI(title="A股分析系统")
# K 线响应 520KB，gzip 后 151KB（29%）。盘中每 5 秒拉一次，公网隧道下差别很大。
app.add_middleware(GZipMiddleware, minimum_size=2048)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

app.include_router(kline.router)
app.include_router(minute.router)
app.include_router(realtime.router)
app.include_router(watchlist.router)
app.include_router(assistant.router)
app.include_router(trades.router)
app.include_router(paper.router)


@app.get("/")
def index():
    return FileResponse(os.path.join(config.STATIC_DIR, "index.html"))
