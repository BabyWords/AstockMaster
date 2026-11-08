# -*- coding: utf-8 -*-
"""生成选股专用的轻量面板 data/recent_panel.csv。
=================================================

为什么需要它：
    全量缓存 908 万行 / 1.1G，读一次要 40 多秒、峰值内存 4G —— 挂在网页按钮上
    完全不能用。但每日选股其实只需要「最近 N 个交易日」的横截面（够算 MA60 /
    REV60 / 20 日波动即可）。

    所以单独切一份最近 140 个交易日的小面板，读它只要 2~3 秒，因子计算复用
    同一套 quant.factors，口径和全量回测完全一致。

用法：
    python scripts/build_recent.py            # 默认 140 个交易日
    python scripts/build_recent.py 200

被 scripts/update_cache.py 在增量更新成功后自动调用。
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import os
import sys
import time

from quant import config
from quant.data import read_csv

DAYS = 140          # 保留的交易日数：够 60 日均线 + REV60，再多留余量


def build(days: int = DAYS, cache: str | None = None, out: str | None = None) -> int:
    """从全量缓存切出最近 days 个交易日，写入 out。返回写出的行数。"""
    cache = cache or config.CACHE
    out = out or config.RECENT
    if not os.path.exists(cache):
        print(f"[错误] 全量缓存不存在：{cache}")
        return 0
    t0 = time.time()
    # read_csv 内部已做「空日期脏行」归一化（曾导致 sorted() 抛 float/str 不可比）
    df = read_csv(cache)
    dates = sorted(df["交易日期"].unique())
    if len(dates) > days:
        df = df[df["交易日期"] >= dates[-days]]
    df = df.sort_values(["股票代码", "交易日期"])

    tmp = out + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, out)
    size = os.path.getsize(out) / 1024 / 1024
    print(f"[完成] recent_panel {len(df):,} 行 / {size:.0f}MB / "
          f"{df['交易日期'].min()}~{df['交易日期'].max()} / {time.time() - t0:.0f}s")
    return len(df)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DAYS
    build(n)
