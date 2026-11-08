# -*- coding: utf-8 -*-
"""A股量化 · Postgres 访问封装

六张表定义在 ~/quant-pg/init/01_schema.sql：
    stock            股票主表（代码/名称/交易所/板块/行业/上市退市）
    data_sync_log    数据更新日志（哪天缺、哪天重、增量对不对）
    adjust_factor    复权因子版本（保证回测可复现）
    backtest_run     回测实验记录（params/nav 用 JSONB）
    signal           每日选股信号（含事后收益回填）
    trade            交易账本（真实成交流水，持仓由它推导）

连接：只读 ~/quant-pg/.env 里的 PG_PASSWORD，库只监听 127.0.0.1:5432。

用法：
    import db

    with db.session() as conn:
        db.log_sync(conn, source="baidu-pull", kind="daily",
                    status="ok", file_date="2026-10-30", rows_added=5568)
"""
from __future__ import annotations

import os
import threading
import time as _time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.types.json import Jsonb

ENV_FILE = Path.home() / "quant-pg" / ".env"
REMOTE = dict(host="127.0.0.1", port=5432, dbname="quant", user="quant")

# 密码与连接的复用：web 进程每次请求都重新读 .env、重新 TCP 握手很浪费
# （实测一次 connect ≈ 8ms，而 watchlist 查询本身只要 0.3ms）。
_PWD_CACHE: dict[str, Any] = {"mtime": None, "value": None}
_POOL: list[tuple[float, Any]] = []
_POOL_LOCK = threading.Lock()
_POOL_MAX = 4          # webapp 是单进程低并发，4 条足够
_POOL_TTL = 60.0       # 空闲超过 60s 的连接丢弃，避免用到被 VM 悄悄掐断的旧连接


def _password() -> str | None:
    if pwd := os.getenv("PG_PASSWORD"):
        return pwd
    try:
        mt = ENV_FILE.stat().st_mtime
    except OSError:
        return None
    if _PWD_CACHE["mtime"] == mt:
        return _PWD_CACHE["value"]
    val = None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("PG_PASSWORD="):
            val = line.split("=", 1)[1].strip() or None
            break
    _PWD_CACHE.update(mtime=mt, value=val)
    return val


def dsn() -> str:
    params: dict[str, Any] = dict(REMOTE)
    if pwd := _password():
        params["password"] = pwd
    return " ".join(f"{k}={v}" for k, v in params.items())


def connect() -> psycopg.Connection:
    """返回未提交的连接。日常请用 session()，它负责提交/回滚/关闭。"""
    return psycopg.connect(dsn())


def _acquire() -> psycopg.Connection:
    """从池里取一条可用连接，取不到就新建。"""
    now = _time.time()
    with _POOL_LOCK:
        while _POOL:
            ts, conn = _POOL.pop()
            if now - ts <= _POOL_TTL and not conn.closed and not getattr(conn, "broken", False):
                return conn
            try:
                conn.close()
            except Exception:                  # noqa: BLE001
                pass
    return psycopg.connect(dsn())


def _release(conn: psycopg.Connection) -> None:
    """归还连接；坏连接直接关掉，不让它污染池子。"""
    if conn.closed or getattr(conn, "broken", False):
        try:
            conn.close()
        except Exception:                      # noqa: BLE001
            pass
        return
    with _POOL_LOCK:
        if len(_POOL) < _POOL_MAX:
            _POOL.append((_time.time(), conn))
            return
    try:
        conn.close()
    except Exception:                          # noqa: BLE001
        pass


@contextmanager
def session():
    """事务上下文：正常结束提交，异常回滚。

    连接来自进程内小池子（最多 4 条、空闲 60s 失效），成功/失败后都会归还。
    """
    conn = _acquire()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:                      # noqa: BLE001
            pass
        raise
    finally:
        _release(conn)


def _as_date(value: Any) -> date | None:
    """接受 date / 'YYYY-MM-DD' / 'YYYYMMDD'，统一成 date。"""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    s = str(value).replace("-", "").strip()
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"无法解析日期：{value!r}")
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))


# ============================ data_sync_log ============================

def log_sync(conn: psycopg.Connection, *, source: str, kind: str, status: str,
             file_date: Any = None, rows_in_file: int | None = None,
             rows_added: int | None = None, cache_before: int | None = None,
             cache_after: int | None = None, message: str | None = None,
             duration_ms: int | None = None) -> int:
    """记一条数据同步日志，返回 id。

    kind  : daily / min1 / min5 / factor
    status: ok / skipped / error
    """
    with conn.cursor() as cur:
        cur.execute(
            """insert into data_sync_log
                 (source, kind, file_date, rows_in_file, rows_added,
                  cache_before, cache_after, status, message, duration_ms)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (source, kind, _as_date(file_date), rows_in_file, rows_added,
             cache_before, cache_after, status, message, duration_ms),
        )
        return cur.fetchone()[0]


def last_trading_date(conn: psycopg.Connection) -> date | None:
    """缓存已知的最新交易日（从同步日志推，不读 900 万行 CSV）。"""
    with conn.cursor() as cur:
        cur.execute("select max(file_date) from data_sync_log where status = 'ok'")
        row = cur.fetchone()
        return row[0] if row else None


# ============================ backtest_run ============================

def save_backtest(conn: psycopg.Connection, *, name: str, strategy: str,
                  params: dict | None = None, **fields) -> int:
    """存一次回测，返回 id。

    常用 fields：start_date/end_date/topn/hold_days/cost_bps/universe/init_cash/
                total_return/annual_return/max_drawdown/sharpe/win_rate/
                trade_count/yearly/nav/code_hash/git_commit/note
    """
    if "params" in fields:
        fields.pop("params")
    cols: list[str] = ["name", "strategy", "params"]
    vals: list[Any] = [name, strategy, Jsonb(params or {})]

    for key, val in fields.items():
        cols.append(key)
        if key in ("start_date", "end_date"):
            vals.append(_as_date(val))
        elif key in ("yearly", "nav"):
            vals.append(Jsonb(val) if val is not None else None)
        else:
            vals.append(val)

    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"insert into backtest_run ({', '.join(cols)}) values ({placeholders}) returning id"
    with conn.cursor() as cur:
        cur.execute(sql, vals)
        return cur.fetchone()[0]


# ============================ signal ============================

_SIG_COLS = ("signal_date", "code", "strategy", "rank", "score", "f_size",
             "f_rev20", "f_vol20", "ref_price", "hold_days", "status", "note")


def save_signals(conn: psycopg.Connection, signal_date: Any, strategy: str,
                 rows: Iterable[dict], hold_days: int = 20) -> int:
    """写入一天的选股结果，按 (signal_date, code, strategy) 去重覆盖。

    rows 里每项可用键：code / rank / score / f_size / f_rev20 / f_vol20 /
                      ref_price / status / note
    """
    d = _as_date(signal_date)
    payload = []
    for r in rows:
        payload.append((
            d, str(r["code"]).zfill(6), strategy,
            r.get("rank"), r.get("score"), r.get("f_size"), r.get("f_rev20"),
            r.get("f_vol20"), r.get("ref_price"), hold_days,
            r.get("status", "pending"), r.get("note"),
        ))
    if not payload:
        return 0

    updates = ", ".join(
        f"{c} = excluded.{c}" for c in _SIG_COLS[3:]
    )
    sql = (f"insert into signal ({', '.join(_SIG_COLS)}) "
           f"values ({', '.join(['%s'] * len(_SIG_COLS))}) "
           f"on conflict (signal_date, code, strategy) do update set {updates}")
    with conn.cursor() as cur:
        cur.executemany(sql, payload)
        return cur.rowcount


def pending_signals(conn: psycopg.Connection, limit: int = 20) -> list[dict]:
    """待执行信号（status='pending'），按日期倒序。"""
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """select id, signal_date, code, rank, score, ref_price, hold_days
                 from signal where status = 'pending'
                order by signal_date desc, rank limit %s""", (limit,))
        return cur.fetchall()


# ============================ trade ============================

def add_trade(conn: psycopg.Connection, *, code: str, side: str, trade_date: Any,
              price: float, shares: int, fee: float = 0.0, tax: float = 0.0,
              name: str | None = None, strategy: str | None = None,
              signal_id: int | None = None, account: str = "main",
              note: str | None = None) -> int:
    """记一笔成交。amount 自动算，不用手填。"""
    if side not in ("buy", "sell"):
        raise ValueError("side 只能是 buy 或 sell")
    amount = round(float(price) * int(shares), 2)
    with conn.cursor() as cur:
        cur.execute(
            """insert into trade
                 (code, name, side, trade_date, price, shares, amount,
                  fee, tax, strategy, signal_id, account, note)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (str(code).zfill(6), name, side, _as_date(trade_date), price, shares,
             amount, fee, tax, strategy, signal_id, account, note),
        )
        return cur.fetchone()[0]


def positions(conn: psycopg.Connection) -> list[dict]:
    """当前持仓（来自视图 v_position）。"""
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("select * from v_position order by last_trade desc")
        return cur.fetchall()


# ============================ 便捷查询 ============================

def top_backtests(conn: psycopg.Connection, limit: int = 10) -> list[dict]:
    """历史最好成绩，直接回答「我做过最好的十次实验是什么」。"""
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """select id, name, strategy, params, start_date, end_date,
                      total_return, annual_return, max_drawdown, created_at
                 from backtest_run
                where total_return is not null
                order by total_return desc limit %s""", (limit,))
        return cur.fetchall()


def table_sizes(conn: psycopg.Connection) -> list[tuple[str, str, int]]:
    """各表占用，用于确认「库确实很小」。"""
    with conn.cursor() as cur:
        cur.execute("""
            select relname,
                   pg_size_pretty(pg_total_relation_size(c.oid)),
                   pg_total_relation_size(c.oid)
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relkind in ('r', 'v', 'm')
             order by pg_total_relation_size(c.oid) desc""")
        return cur.fetchall()
