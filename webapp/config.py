# -*- coding: utf-8 -*-
"""webapp 配置与引导 —— 路径常量、sys.path、股票索引、数据库句柄。
==================================================================

这是 webapp 里**唯一**做 sys.path 引导的地方：把项目根（回测/）放进 path，
之后 `from quant import ...` 才可用。所以 app.py 的第一行必须是
`import config`（api/ 与 services/ 里的 `from config import ...` 也会先触发它）。

路由层不许再出现路径拼接，一律从这里或 services 取。
"""
from __future__ import annotations

import os
import pickle
import sys

# ============================ sys.path 引导 ============================
BASE = os.path.dirname(os.path.abspath(__file__))      # 回测/webapp
ROOT = os.path.dirname(BASE)                           # 回测
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ============================ 路径 ============================
from quant import config as qcfg                       # noqa: E402  必须在引导之后

STORE = qcfg.STORE_DIR
STOCKS = qcfg.STOCK_STORE
STATIC_DIR = qcfg.STATIC_DIR
STOCK_INDEX = qcfg.STOCK_INDEX
MIN_ROOT = qcfg.MIN_ROOT                               # 1min 原始 CSV 目录
MIN_CACHE = qcfg.MINUTE_CACHE                          # 单股单日分时缓存
WL_PATH = qcfg.WATCHLIST_JSON                          # 自选股降级快照
JOB_DIR = qcfg.JOB_DIR                                 # 回测子进程的 spec/out
DEFAULT_WATCH = ["600036", "000338", "600900"]

# ============================ 股票列表索引（搜索用） ============================
stock_list: list[dict] = []
if os.path.exists(STOCK_INDEX):
    try:
        with open(STOCK_INDEX, "rb") as f:
            stock_list = pickle.load(f)
    except Exception as e:                             # noqa: BLE001
        print(f"[config] 股票索引损坏，搜索将不可用：{e}")

NAME_OF: dict[str, str] = {str(s.get("code")): s.get("name") or "" for s in stock_list}

# ============================ 数据库（可选，失败即降级） ============================
try:
    from quant import db as dbmod
except Exception:                                      # noqa: BLE001
    dbmod = None
