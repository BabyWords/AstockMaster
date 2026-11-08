# -*- coding: utf-8 -*-
"""
预构建股票数据分片（一次性 / 缓存更新后重跑）
==============================================
把全样本日线缓存（约 900 万行 / 1.1GB）按股票代码拆分成独立 pkl 分片，
并生成股票列表索引，供 webapp 后端毫秒级查询单只股票。

产物：
  data_store/stocks/{code}.pkl   —— 单只股票全历史原始 OHLCV+复权因子（前复权在查询时算）
  data_store/stock_list.pkl      —— [{code,name,last_date,last_close,rows}, ...] 搜索索引

说明：分片存的是「原始价 + 复权因子」，前复权放到查询时按该股最新基准算，
      与 quant/indicators.py 口径一致。之后每日增量更新缓存后，重跑本脚本即可刷新分片。
      分片采用「临时文件 + os.replace」原子写，避免 web 服务读到半截文件。
"""
import os
import pickle
import tempfile
import time
import pandas as pd

import config                     # 触发 sys.path 引导（把 回测/ 加进 path）
from quant import config as qcfg
from quant.data import read_csv    # 统一 dtype + 数值列 + 脏行归一（曾因脏行把同日数据写两遍）

CACHE = qcfg.CACHE
STORE = qcfg.STORE_DIR
STOCKS = qcfg.STOCK_STORE

COLS = ["交易日期", "股票代码", "股票名称", "开盘价（元）", "最高价（元）", "最低价（元）",
        "收盘价（元）", "昨收价（元）", "涨跌幅（%）", "成交量（手）", "成交额（万元）",
        "复权因子", "换手率（%）", "量比"]
NUM_COLS = ["开盘价（元）", "最高价（元）", "最低价（元）", "收盘价（元）", "昨收价（元）",
            "涨跌幅（%）", "成交量（手）", "成交额（万元）", "复权因子", "换手率（%）", "量比"]


def _atomic_dump(obj, path):
    """原子写 pkl：先写临时文件再 os.replace，避免 web 服务读到半截文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main():
    os.makedirs(STOCKS, exist_ok=True)
    t0 = time.time()

    print("读取全量缓存（只取 14 列）...")
    df = read_csv(CACHE, cols=COLS)
    print(f"读取完成 {len(df):,} 行，耗时 {time.time()-t0:.1f}s")

    df = df.sort_values("交易日期", kind="stable")
    # 防御：代码为空的脏行会生成 "nan.pkl"，直接丢掉
    df = df[df["股票代码"].str.len() == 6]

    meta = []
    groups = df.groupby("股票代码", sort=False)
    n = len(groups)
    for i, (code, g) in enumerate(groups):
        g = g.reset_index(drop=True)
        _atomic_dump(g, os.path.join(STOCKS, f"{code}.pkl"))
        meta.append({
            "code": code,
            "name": g["股票名称"].iloc[-1],
            "last_date": g["交易日期"].iloc[-1],
            "last_close": float(g["收盘价（元）"].iloc[-1]),
            "rows": len(g),
        })
        if (i + 1) % 1000 == 0:
            print(f"  进度 {i+1}/{n}（{(i+1)/n*100:.0f}%）")

    _atomic_dump(meta, os.path.join(STORE, "stock_list.pkl"))

    print(f"\n完成：{len(meta)} 只股票分片，索引已生成，总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
