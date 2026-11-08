# -*- coding: utf-8 -*-
"""模拟盘 —— 把一次选股当一笔「纸上交易」跟踪到底。
====================================================

口径（与回测 _add_fwd 保持一致，否则模拟盘和回测数字对不上）：
    · 买入价 = 买入日收盘价（前复权）
    · 每只投入 = 本金 ÷ 只数，股数按 100 股整手向下取整，余额留现金
    · 净值(t) = Σ 股数 × 收盘价(t) + 现金
    · 到期 = 买入日之后第 hold_days 个交易日收盘

**价格一律现算，不落库**：前复权价是「按最新因子折算」的动态序列，分红送股后
历史价会整体缩放，但「今日/买入日」的比值不变。若把买入价存成快照，一次除权
就会让整条曲线错位。股数同理，由买入价现推。
"""
from __future__ import annotations

import bisect
import datetime as dt
import re
import threading
import time

import pandas as pd
from fastapi import HTTPException

from config import NAME_OF, dbmod

from . import market
from .store import load_stock

_SCHEMA = """
create table if not exists paper_portfolio (
    id          serial primary key,
    name        varchar(64) not null,
    strategy    varchar(48),
    buy_date    date        not null,
    hold_days   smallint    not null default 20,
    capital     numeric(14, 2) not null default 100000,
    note        text,
    created_at  timestamptz not null default now()
);
create table if not exists paper_position (
    id            serial primary key,
    portfolio_id  integer    not null references paper_portfolio (id) on delete cascade,
    code          varchar(6) not null,
    name          varchar(32),
    rank          smallint   not null default 0,
    unique (portfolio_id, code)
);
create index if not exists paper_portfolio_buy_idx on paper_portfolio (buy_date desc, id desc);
create index if not exists paper_position_pid_idx on paper_position (portfolio_id, rank, code);
"""

_schema_ready = False
_schema_lock = threading.Lock()

# 组合详情缓存：盘中每 5 秒轮询，5 只票要读 5 个 pkl + 拼 40 天曲线，没必要每次重算。
# 行情 TTL 3 秒，这里给 5 秒，够新又不打爆磁盘。
_CACHE: dict = {}
_CACHE_TTL = 5.0
_CACHE_MAX = 32


# ============================ 表结构 / 连接 ============================
def ensure_schema():
    """表已由 ~/quant-pg/init/03_paper.sql 建好；这里兜底老库升级。"""
    global _schema_ready
    if _schema_ready or dbmod is None:
        return
    with _schema_lock:
        if _schema_ready:
            return
        try:
            with dbmod.session() as conn:
                with conn.cursor() as cur:
                    cur.execute(_SCHEMA)
            _schema_ready = True
        except Exception as e:                  # noqa: BLE001
            print(f"[paper] 建表失败：{e}")


def need_db():
    if dbmod is None:
        raise HTTPException(503, "数据库不可用（Postgres 没起来），模拟盘功能暂不可用")
    ensure_schema()


# ============================ 小工具 ============================
def ymd(d) -> str:
    if isinstance(d, (dt.date, dt.datetime)):
        return d.strftime("%Y%m%d")
    return str(d).replace("-", "")[:8]


def iso(d) -> str:
    if isinstance(d, (dt.date, dt.datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def clean_codes(raw):
    codes = []
    for c in raw or []:
        s = re.sub(r"\D", "", str(c).split(".")[0])
        if len(s) == 6 and s not in codes:
            codes.append(s)
    return codes


def next_trading_day(code, ymd_: str) -> str:
    """信号日 -> 下一个交易日（T 日收盘选，T+1 收盘买入，与回测口径一致）。"""
    days = [str(x) for x in load_stock(code)["交易日期"].tolist()]
    i = bisect.bisect_right(days, ymd_)
    if i >= len(days):
        raise HTTPException(400, f"{ymd_} 之后还没有新的交易日数据，等明天数据到了再建")
    return days[i]


def _stock_series(code, buy_ymd):
    """返回 (买入价, {交易日: 收盘价}, 实际买入日) —— 从买入日往后，前复权。"""
    d = load_stock(code)
    days = [str(x) for x in d["交易日期"].tolist()]
    closes = d["close"].astype("float64").tolist()
    i0 = bisect.bisect_right(days, buy_ymd) - 1
    if i0 < 0:
        raise HTTPException(400, f"{code} 在 {buy_ymd} 之前没有行情数据")
    buy_price = closes[i0]
    if not buy_price or buy_price <= 0:
        raise HTTPException(400, f"{code} 买入日价格异常（{buy_price}）")
    return buy_price, {days[i]: closes[i] for i in range(i0, len(days))}, days[i0]


def _merge_live(series_map, codes):
    """今日数据还没进 pkl 时，用实时价补最后一根（只补今天，不改历史）。"""
    today = dt.date.today()
    if today.weekday() >= 5:                    # 周末没有实时价
        return None
    ymd_ = today.strftime("%Y%m%d")
    if any(ymd_ in s for s in series_map.values()):
        return None                             # 数据已经到了，不用补
    quotes = market.realtime_batch(codes)
    if not quotes:
        return None
    for q in quotes:
        if q.get("price"):
            series_map.setdefault(q["code"], {})[ymd_] = float(q["price"])
    return ymd_


# ============================ 核心计算 ============================
def build(pid: int) -> dict:
    """算一个组合的完整视图。纯函数式：每次都从行情重算。"""
    with dbmod.session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, name, strategy, buy_date, hold_days, capital, note "
                "from paper_portfolio where id = %s", (pid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"组合 {pid} 不存在")
            cur.execute(
                "select code, name, rank from paper_position "
                "where portfolio_id = %s order by rank, code", (pid,))
            positions = cur.fetchall()

    (_pid, name, strategy, buy_date, hold_days, capital, note) = row
    capital = float(capital)
    hold_days = int(hold_days or 20)
    buy_ymd = ymd(buy_date)
    n = len(positions)
    if not n:
        raise HTTPException(400, "这个组合里没有成分股")

    series_map, buy_prices, names, actual_buy = {}, {}, {}, {}
    for code, pname, _rank in positions:
        bp, s, actual = _stock_series(code, buy_ymd)
        series_map[code] = s
        buy_prices[code] = bp
        actual_buy[code] = actual
        names[code] = pname or NAME_OF.get(code, "")

    live_ymd = _merge_live(series_map, [p[0] for p in positions])

    per = capital / n
    shares = {code: int(per // buy_prices[code] // 100 * 100) for code in series_map}
    cash = capital - sum(shares[c] * buy_prices[c] for c in series_map)

    # 交易日轴 = 各票从买入日起的日期并集；停牌票按前值 fill。
    # 用 reindex+ffill 一次算完（原来是逐日 sorted(...) 找前值，组合越久越慢）。
    close_df = pd.DataFrame({c: pd.Series(s, dtype="float64") for c, s in series_map.items()})
    close_df = close_df.sort_index().ffill()
    close_df = close_df.fillna(0.0)                 # 买入日之前没有持仓
    share_s = pd.Series(shares, dtype="float64")
    value = close_df.mul(share_s, axis=1).sum(axis=1) + cash
    axis = list(value.index)

    nav, last_val = [], None
    for ymd_, v in zip(axis, value.tolist()):
        pct = 0.0 if last_val in (None, 0) else (v / last_val - 1) * 100
        nav.append({"ymd": ymd_,
                    "d": f"{ymd_[:4]}-{ymd_[4:6]}-{ymd_[6:8]}",
                    "v": round(v, 2),
                    "pct": round(pct, 2),
                    "cum": round((v / capital - 1) * 100, 2),
                    "live": ymd_ == live_ymd})
        last_val = v

    # 到期日 = 买入日之后第 hold_days 个交易日
    i0 = axis.index(min(actual_buy.values()))
    end_i = i0 + hold_days
    end_date = axis[end_i] if end_i < len(axis) else None
    days_held = len(axis) - 1 - i0
    cur_v = nav[-1]["v"]
    peak, mdd = None, 0.0
    for x in nav:
        peak = x["v"] if peak is None else max(peak, x["v"])
        mdd = min(mdd, x["v"] / peak - 1)

    last_prices = close_df.iloc[-1]
    pos_out = []
    for code, pname, rank in positions:
        bp = buy_prices[code]
        lp = float(last_prices.get(code) or 0) or None
        mv = shares[code] * (lp or bp)
        pos_out.append({
            "code": code,
            "name": names[code] or pname or "",
            "rank": rank,
            "buy_date": actual_buy[code],
            "buy_price": round(bp, 3),
            "last_price": round(lp, 3) if lp else None,
            "shares": shares[code],
            "cost": round(shares[code] * bp, 2),
            "mv": round(mv, 2),
            "ret": round((lp / bp - 1) * 100, 2) if lp else None,
            "pnl": round(mv - shares[code] * bp, 2),
            "weight": round(mv / cur_v * 100, 1) if cur_v else None,
        })
    pos_out.sort(key=lambda x: (x["rank"], x["code"]))

    return {
        "id": pid,
        "name": name,
        "strategy": strategy or "",
        "buy_date": iso(buy_date),
        "buy_ymd": buy_ymd,
        "hold_days": hold_days,
        "capital": round(capital, 2),
        "note": note or "",
        "cash": round(cash, 2),
        "nav": nav,
        "positions": pos_out,
        "metrics": {
            "current_value": round(cur_v, 2),
            "cur_return": round((cur_v / capital - 1) * 100, 2),
            "cur_pnl": round(cur_v - capital, 2),
            "max_drawdown": round(mdd * 100, 2),
            "days_held": days_held,
            "days_left": max(0, hold_days - days_held),
            "end_date": f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}" if end_date else None,
            "end_value": nav[end_i]["v"] if end_date else None,
            "end_return": round((nav[end_i]["v"] / capital - 1) * 100, 2) if end_date else None,
            "status": "done" if end_date else "holding",
            "live": bool(live_ymd),
        },
    }


def cached(pid: int) -> dict:
    now = time.time()
    hit = _CACHE.get(pid)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    data = build(pid)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.clear()
    _CACHE[pid] = (now, data)
    return data


def invalidate(pid: int):
    _CACHE.pop(pid, None)


# ============================ CRUD ============================
def list_portfolios(limit: int = 30) -> list[dict]:
    """下拉框数据：最近 N 个组合 + 各自当前收益（复用详情缓存）。"""
    with dbmod.session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select p.id, p.name, p.strategy, p.buy_date, p.hold_days, "
                "       p.capital, p.created_at, count(s.id) "
                "from paper_portfolio p left join paper_position s "
                "  on s.portfolio_id = p.id "
                "group by p.id order by p.buy_date desc, p.id desc limit %s", (limit,))
            rows = cur.fetchall()

    out = []
    for pid, name, strategy, buy_date, hold_days, capital, created, cnt in rows:
        item = {"id": pid, "name": name, "strategy": strategy or "",
                "buy_date": iso(buy_date), "hold_days": int(hold_days or 20),
                "capital": float(capital), "count": int(cnt),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created)}
        try:                                    # 收益算不出来不影响下拉框可用
            m = cached(pid)["metrics"]
            item.update({"cur_return": m["cur_return"], "status": m["status"],
                         "days_held": m["days_held"]})
        except Exception:                       # noqa: BLE001
            item.update({"cur_return": None, "status": "error", "days_held": None})
        out.append(item)
    return out


def create(payload: dict) -> dict:
    codes = clean_codes(payload.get("codes"))
    if not codes:
        raise HTTPException(400, "至少要给一个 6 位股票代码")
    buy_date = str(payload.get("buy_date") or "").replace("-", "")[:8]
    signal_date = str(payload.get("signal_date") or "").replace("-", "")[:8]
    if not re.fullmatch(r"\d{8}", buy_date):
        # 只给信号日也行：自动取下一个交易日，省得前端算交易日历
        if re.fullmatch(r"\d{8}", signal_date):
            buy_date = next_trading_day(codes[0], signal_date)
        else:
            raise HTTPException(400, "buy_date 需为 YYYYMMDD（或改用 signal_date）")
    capital = float(payload.get("capital") or 100000)
    hold_days = int(payload.get("hold_days") or 20)
    name = (payload.get("name") or "").strip() or f"{buy_date} 模拟盘"
    strategy = (payload.get("strategy") or "").strip() or None
    names = payload.get("names") or {}

    # 先验一遍数据：买入日没有行情就别建，否则后面每次详情都报错
    for c in codes:
        _stock_series(c, buy_date)

    try:
        with dbmod.session() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into paper_portfolio (name, strategy, buy_date, hold_days, capital, note) "
                    "values (%s, %s, %s, %s, %s, %s) returning id",
                    (name[:64], strategy, f"{buy_date[:4]}-{buy_date[4:6]}-{buy_date[6:8]}",
                     hold_days, capital, payload.get("note")))
                pid = cur.fetchone()[0]
                for i, c in enumerate(codes):
                    nm = str(names.get(c) or NAME_OF.get(c) or "")[:32]
                    cur.execute(
                        "insert into paper_position (portfolio_id, code, name, rank) "
                        "values (%s, %s, %s, %s)", (pid, c, nm or None, i + 1))
    except HTTPException:
        raise
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(500, f"写库失败：{e}")

    invalidate(pid)
    return {"ok": True, "id": pid, "detail": build(pid)}


def delete(pid: int) -> dict:
    with dbmod.session() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from paper_portfolio where id = %s", (pid,))
            n = cur.rowcount
    invalidate(pid)
    return {"ok": bool(n), "deleted": n}
