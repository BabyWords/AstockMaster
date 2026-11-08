# -*- coding: utf-8 -*-
"""增量更新日线缓存（幂等，可高频轮询，秒级）。
====================================================

只扫描「每日行情」目录里比缓存最新日期更新的文件，解析后并入缓存。
设计目标：可被定时任务（launchd 每 5 分钟）反复触发 ——
    · 外置硬盘未挂载 → 秒退
    · 没有新数据 → 读状态文件秒退（不碰 900 万行全量缓存）
    · 有新数据 → 才读全量缓存合并写回

与 build_cache.py（全量重建）的分工：首次建仓或大改源数据时用全量；
日常每天补几天用本脚本。

退出码（调用方据此决定是否刷新网页分片）：
    0 = 已是最新，无变化
    1 = 异常（未挂载 / 缓存缺失 / 新文件全读失败）
    2 = 已完成增量更新（有新增数据）

用法：python scripts/update_cache.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import glob
import os
import sys
import time

import pandas as pd

from quant import config, data, db
from quant.data import normalize_frame

YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]

COLS = ["交易日期", "股票代码", "股票名称",
        "开盘价（元）", "最高价（元）", "最低价（元）", "收盘价（元）", "昨收价（元）",
        "涨跌幅（%）", "成交量（手）", "成交额（万元）", "复权因子",
        "换手率（%）", "量比", "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]


def _file_date(path):
    """从文件名提取 YYYYMMDD（文件形如 20261029@...csv）。"""
    head = os.path.basename(path)[:8]
    return head if head.isdigit() else ""


def _latest_known():
    """已知最新日期：优先读状态文件（秒级），否则回退读缓存全量。"""
    if os.path.exists(config.STATE):
        d = str(open(config.STATE, encoding="utf-8").read().strip()).split(".")[0]
        if d.isdigit() and len(d) == 8:
            return d
    if os.path.exists(config.CACHE):
        d = pd.read_csv(config.CACHE, usecols=["交易日期"], dtype={"交易日期": str},
                        low_memory=False)["交易日期"]
        d = d.dropna().astype(str).str.split(".").str[0]
        d = d[d.str.len() == 8].max()
        # 回退读全量后顺手写状态文件，下次即可秒退
        if d is not None and str(d).isdigit():
            try:
                with open(config.STATE, "w", encoding="utf-8") as f:
                    f.write(str(d))
            except OSError:
                pass
        return d
    return None


def _scan_new_files(latest):
    new_files = []
    for y in YEARS:
        d = os.path.join(config.DAILY_DIR, y)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "*.csv")):
            if "(1)" in f:                 # 跳过重复文件
                continue
            fd = _file_date(f)
            if fd and fd > latest:
                new_files.append((fd, f))
    new_files.sort()
    return new_files


def _merge(new_df):
    """把新数据并入缓存：按 (日期, 代码) 去重（新数据覆盖旧）+ 重新排序。"""
    old = normalize_frame(pd.read_csv(config.CACHE, dtype={"股票代码": str, "交易日期": str},
                                      low_memory=False))
    merged = pd.concat([old, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["交易日期", "股票代码"], keep="last")
    merged = merged.sort_values(["交易日期", "股票代码"]).reset_index(drop=True)
    dup = int(merged.duplicated(subset=["交易日期", "股票代码"]).sum())
    if dup:
        print(f"[警告] 合并后仍有 {dup} 行重复（本不该发生，请检查源文件）")
    return old, merged


def _after_update(merged, old, t0):
    """增量成功后的下游动作，每一步失败都只告警、不影响主缓存。"""
    merged.to_csv(config.CACHE, index=False)
    with open(config.STATE, "w", encoding="utf-8") as f:
        f.write(merged["交易日期"].max())
    print(f"[完成] 缓存 {len(old):,} → {len(merged):,} 行 "
          f"(+{len(merged) - len(old):,})，最新 {merged['交易日期'].max()}")

    # ① 重建选股用的轻量面板（最近 140 个交易日）
    try:
        from scripts import build_recent
        build_recent.build()
    except Exception as e:                       # noqa: BLE001
        print(f"[警告] 刷新选股缓存失败，不影响主缓存：{e}")

    # ② 记一条同步日志
    try:
        with db.session() as conn:
            db.log_sync(conn, source="update_cache", kind="daily",
                        file_date=merged["交易日期"].max(),
                        rows_added=len(merged) - len(old),
                        cache_before=len(old), cache_after=len(merged),
                        status="ok", duration_ms=int((time.time() - t0) * 1000))
    except Exception as e:                       # noqa: BLE001
        print(f"[警告] 写同步日志失败（库没起？不影响缓存）：{e}")

    # ③ 每日选股（收盘数据进缓存后选今天的票，on conflict 幂等）
    try:
        from quant import selection
        selection.clear_panel_cache()            # 面板已变，别让网页用旧的
        res = selection.select()
        selection.save_csv(res)
        print(f"[选股] {res['date']} {res['strategy']} TOP{res['top_n']} → "
              f"{selection.save_db(res)}")
    except Exception as e:                       # noqa: BLE001
        print(f"[警告] 每日选股失败（不影响缓存）：{e}")

    # ④ 回填历史 signal 的真实收益（样本外验证闭环）
    try:
        from scripts import backfill_signals
        backfill_signals.run()
    except Exception as e:                       # noqa: BLE001
        print(f"[警告] signal 回填失败（不影响缓存）：{e}")

    # ⑤ 重建 pkl 旁路（CSV 变了 pkl 就失效）。夜里多花约 25s，
    #    换白天第一次回测不用再等读 1.1GB CSV（15s → 1s）。
    try:
        data.load_raw()
        print("[缓存] 已重建 .pkl 旁路缓存")
    except Exception as e:                       # noqa: BLE001
        print(f"[警告] 重建 pkl 失败，下次回测会自动重建：{e}")


def main():
    t0 = time.time()

    if not os.path.exists(config.DAILY_DIR):
        print(f"[跳过] 外置硬盘未挂载（{config.DAILY_DIR} 不存在）")
        return 1
    if not os.path.exists(config.CACHE):
        print("[错误] 缓存不存在，请先跑 scripts/build_cache.py 全量建仓")
        return 1

    latest = _latest_known()
    print(f"[缓存] 最新交易日 = {latest}")

    new_files = _scan_new_files(latest)
    if not new_files:
        print("[增量] 已是最新，无需更新")
        print(f"[总耗时 {time.time() - t0:.1f}s]")
        return 0
    print(f"[增量] 发现 {len(new_files)} 个新文件："
          f"{new_files[0][0]} ~ {new_files[-1][0]}")

    parts = []
    for fd, f in new_files:
        try:
            parts.append(pd.read_csv(f, usecols=COLS, dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:                   # noqa: BLE001
            print(f"  [跳过] {os.path.basename(f)}: {e}")
    if not parts:
        print("[警告] 新文件全部读取失败，本次跳过")
        print(f"[总耗时 {time.time() - t0:.1f}s]")
        return 1

    new_df = normalize_frame(pd.concat(parts, ignore_index=True))
    print(f"[增量] 新数据 {len(new_df):,} 行")

    old, merged = _merge(new_df)
    _after_update(merged, old, t0)
    print(f"[总耗时 {time.time() - t0:.1f}s]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
