# -*- coding: utf-8 -*-
"""全局配置 —— 全项目**唯一**允许出现路径字面量的地方。
==========================================================

为什么单独抽一层：
    之前 8 个文件各自写死了 "/Volumes/TOSHIBA/炒股/回测/..."，换机器 / 换盘符 /
    做测试注入小数据都得挨个改。现在所有路径都在这里推导，其余模块一律
    `from quant import config` 取用。

约定：
    · 项目根（回测/）= 本包的上一级目录，随代码走，不依赖当前工作目录
    · 数据根（/Volumes/TOSHIBA/炒股）可被 STOCK_DATA_ROOT 覆盖（外置盘换位置时）
    · 缓存目录可被 BACKTEST_DATA_DIR / BACKTEST_CACHE 覆盖（测试注入小样本）
    · 统一给 **字符串**（下游大量 os.path.* 与 "a" + ".tmp" 拼接），目录同理
"""
from __future__ import annotations

import os

_PKG = os.path.dirname(os.path.abspath(__file__))     # 回测/quant
ROOT = os.path.dirname(_PKG)                          # 回测/

# ============================ 目录 ============================
DATA_ROOT = os.environ.get("STOCK_DATA_ROOT", "/Volumes/TOSHIBA/炒股")
DAILY_DIR = os.path.join(DATA_ROOT, "每日行情")          # ① 原始日线（百度网盘同步）
MIN_ROOT = os.path.join(DATA_ROOT, "分钟级行情")         # 1min/5min… 原始分时
DATA_DIR = os.environ.get("BACKTEST_DATA_DIR", os.path.join(ROOT, "data"))   # ② 缓存产物
SELECT_OUT = os.environ.get("BACKTEST_SELECT_OUT", os.path.join(ROOT, "选股结果"))
WEBAPP_DIR = os.path.join(ROOT, "webapp")
STORE_DIR = os.path.join(WEBAPP_DIR, "data_store")       # ③ 网页分片
STATIC_DIR = os.path.join(WEBAPP_DIR, "static")

# ============================ 文件 ============================
CACHE = os.environ.get("BACKTEST_CACHE",
                       os.path.join(DATA_DIR, "daily_full_2019_2026.csv"))
# 二进制旁路：CSV 是文本，外置盘读 1.1GB + 解析要 14s；pkl 反序列化约 1s
PKL = os.environ.get("BACKTEST_PKL", os.path.splitext(CACHE)[0] + ".pkl")
RECENT = os.path.join(DATA_DIR, "recent_panel.csv")       # 选股用轻量面板（最近 140 日）
STATE = os.path.join(DATA_DIR, ".latest_date")            # 缓存已知最新交易日（秒退用）
STOCKS_LIST = os.path.join(DATA_DIR, "stocks_list.csv")   # 代码/名称快照

# webapp 分片与本地缓存
STOCK_STORE = os.path.join(STORE_DIR, "stocks")
STOCK_INDEX = os.path.join(STORE_DIR, "stock_list.pkl")
MINUTE_CACHE = os.path.join(STORE_DIR, "minutes")
WATCHLIST_JSON = os.path.join(STORE_DIR, "watchlist.json")
JOB_DIR = os.path.join(STORE_DIR, "jobs")


def ensure_dir(path: str) -> str:
    """按需建目录（调用点很多都要求父目录存在）。"""
    os.makedirs(path, exist_ok=True)
    return path
