# -*- coding: utf-8 -*-
"""把股票列表同步进 stock 表。
===============================

数据源：data/stocks_list.csv（某日行情快照，含 symbol/code/name）
只能填出：code / name / exchange / board
填不出：industry（行业）、list_date（上市日）—— 源文件没有这两个字段，
        后续可从行情接口或交易所名单补，缺了不影响回测与选股。

用法：
    python scripts/sync_stock_meta.py            # 增量更新（upsert）
    python scripts/sync_stock_meta.py --dry-run  # 只看会写多少行
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import sys

import pandas as pd

from quant import config, db

SRC = config.STOCKS_LIST


def board_of(code: str, exchange: str) -> str:
    if exchange == "SH":
        return "科创板" if code.startswith("68") else "主板"
    if exchange == "SZ":
        return "创业板" if code.startswith("30") else "主板"
    return "北交所"


def main() -> int:
    dry = "--dry-run" in sys.argv
    if db is None:
        print("数据库模块不可用（psycopg 未安装）")
        return 1

    raw = pd.read_csv(SRC, dtype=str)
    raw = raw.dropna(subset=["code", "name"])
    raw["code"] = raw["code"].str.strip().str.zfill(6)
    raw["exchange"] = raw["symbol"].str[:2].str.upper()

    # 只保留三大交易所的 A 股，剔除 B 股（900/200 开头）
    raw = raw[raw["exchange"].isin(["SH", "SZ", "BJ"])]
    raw = raw[~raw["code"].str.startswith(("900", "200"))]
    raw["board"] = [board_of(c, e) for c, e in zip(raw["code"], raw["exchange"])]

    rows = list(raw[["code", "name", "exchange", "board"]].itertuples(index=False, name=None))
    print(f"源文件 {len(raw)} 只股票")

    if dry:
        print("dry-run，不写库。前 5 条：")
        for r in rows[:5]:
            print("  ", r)
        return 0

    sql = """
        insert into stock (code, name, exchange, board, is_active)
        values (%s, %s, %s, %s, true)
        on conflict (code) do update
           set name     = excluded.name,
               exchange = excluded.exchange,
               board    = excluded.board,
               updated_at = now()
    """
    with db.session() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
            affected = cur.rowcount
        with conn.cursor() as cur:
            cur.execute("select count(*), count(*) filter (where is_active) from stock")
            total, active = cur.fetchone()
        db.log_sync(conn, source="sync_stock_meta", kind="daily", status="ok",
                    rows_in_file=len(rows), rows_added=affected,
                    message=f"stock 表 {total} 行，在市 {active} 只")

    print(f"写入/更新 {affected} 行；stock 表共 {total} 行，在市 {active} 只")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
