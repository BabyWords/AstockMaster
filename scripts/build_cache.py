# -*- coding: utf-8 -*-
"""全量重建日线缓存（首次建仓 / 源数据大改时用；日常增量走 update_cache.py）。
================================================================================

数据源：{数据根}/每日行情/{年份}/*.csv（百度网盘同步下来的 28 字段日线）
输出：  data/daily_full_2019_2026.csv（18 个关键字段）

用法：python scripts/build_cache.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import glob
import os
import time

import pandas as pd

from quant import config
from quant.data import normalize_frame

YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]

# 关键 18 字段：量价（开高低收昨收+涨跌幅+成交量+成交额）+ 复权 + 估值 + 流动性
COLS = ["交易日期", "股票代码", "股票名称",
        "开盘价（元）", "最高价（元）", "最低价（元）", "收盘价（元）", "昨收价（元）",
        "涨跌幅（%）", "成交量（手）", "成交额（万元）", "复权因子",
        "换手率（%）", "量比", "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]


def main():
    files = []
    for y in YEARS:
        for f in sorted(glob.glob(os.path.join(config.DAILY_DIR, y, "*.csv"))):
            if "(1)" in f:      # 跳过重复文件（2021 有 45 个带 "(1)" 的重复）
                continue
            files.append(f)
    print(f"[提取] 共 {len(files)} 个日线文件，抽取 {len(COLS)} 字段", flush=True)

    parts = []
    for i, f in enumerate(files):
        try:
            parts.append(pd.read_csv(f, usecols=COLS, dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:              # noqa: BLE001
            print(f"  [跳过] {os.path.basename(f)}: {e}", flush=True)
        if (i + 1) % 300 == 0:
            print(f"  已读 {i + 1}/{len(files)}", flush=True)

    df = normalize_frame(pd.concat(parts, ignore_index=True))
    df.to_csv(config.CACHE, index=False)
    print(f"[完成] {len(df):,} 行，{len(df.columns)} 字段 → {config.CACHE}", flush=True)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[总耗时 {time.time() - t0:.0f}s]")
