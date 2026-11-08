# -*- coding: utf-8 -*-
"""策略目录 —— 下拉框、默认参数、公式策略保存、因子表。
====================================================

策略的两个来源：
    ① 代码注册表（quant/strategies.py 的 @register）
    ② strategy 表里 kind='expr' 的公式策略（quant/expr.py 解析执行）
本模块只做「读目录 / 写目录」，具体执行仍在 quant.expr + quant.engine。
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from config import dbmod
from quant import engine, expr
from quant import picker as pk


def default_params() -> dict:
    """回测表单的默认值（唯一来源是 engine.DEFAULT_CONFIG）。"""
    c = engine.DEFAULT_CONFIG
    f = {**pk.DEFAULT_FILTERS, **c.get("filters", {})}
    return {"top_n": c["top_n"], "hold_days": c["hold_days"], "cost": c["cost"],
            "start": c["start"], "min_price": f.get("min_price"),
            "min_amt": f.get("min_amt"), "max_pct": f.get("max_pct")}


def strategies() -> dict:
    """策略清单：优先读 strategy 表（带描述/参数），库不可用就从代码注册表生成。"""
    out = []
    if dbmod is not None:
        try:
            with dbmod.session() as conn:
                with conn.cursor() as cur:
                    cur.execute("""select name, kind, description, params, enabled, expr
                                     from strategy order by sort_order, name""")
                    for nm, kind, desc, params, enabled, ex in cur.fetchall():
                        out.append({"name": nm, "kind": kind, "desc": desc or "",
                                    "expr": ex,
                                    "params": {**default_params(), **(params or {})},
                                    "enabled": bool(enabled)})
        except Exception:                       # noqa: BLE001
            out = []
    if not out:
        out = [{"name": n, "kind": "python", "desc": "", "expr": None,
                "params": default_params(), "enabled": True} for n in engine.STRATEGIES]
    return {"strategies": out, "engine": True, "engine_error": None,
            "db": dbmod is not None}


def factors() -> dict:
    """公式策略可用的因子名 + 说明（按类别分组，前端直接渲染）。"""
    items = []
    for n in expr.FACTOR_NAMES:
        base = n[2:] if n.startswith("z_") else n
        items.append({"name": n, "base": base,
                      "doc": expr.FACTOR_DOC.get(base, ""),
                      "cat": expr.FACTOR_CAT.get(base, "其它"),
                      "z": n.startswith("z_")})
    return {"factors": items,
            "cats": expr.FACTOR_CAT_ORDER,
            "examples": [
                {"name": "小市值反转", "expr": "z_SIZE + z_REV20"},
                {"name": "小市值反转低波", "expr": "z_SIZE + z_REV20 - z_VOL20"},
                {"name": "反转低换手", "expr": "z_REV20 - z_TURN"},
                {"name": "超跌缩量", "expr": "z_REV60 - z_AMT20 - z_LB"},
            ]}


def save_formula(payload: dict) -> dict:
    """把一条因子表达式保存成策略（写 strategy 表，kind='expr'）。"""
    if dbmod is None:
        raise HTTPException(503, "数据库不可用，公式策略存不了（回测/选股也会拿不到它）")

    name = str(payload.get("name") or "").strip()[:48]
    if not name:
        raise HTTPException(400, "策略名不能为空")
    if name in engine.STRATEGIES:
        raise HTTPException(400, f"「{name}」是内置策略名，换一个")
    try:
        info = expr.check(payload.get("expr") or "")
        expr.compile_expr(info["expr"])          # 真正编译一次，确认能跑
    except expr.ExprError as e:
        raise HTTPException(400, str(e))
    except Exception as e:                       # noqa: BLE001
        raise HTTPException(400, f"表达式无法执行：{e}")

    desc = str(payload.get("desc") or "").strip()[:400] or f"公式策略：{info['expr']}"
    params = {**default_params(), **(payload.get("params") or {})}
    try:
        with dbmod.session() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into strategy (name, kind, expr, description, params, sort_order) "
                    "values (%s, 'expr', %s, %s, %s::jsonb, "
                    "        coalesce((select max(sort_order) + 1 from strategy), 1)) "
                    "on conflict (name) do update set expr = excluded.expr, "
                    "  description = excluded.description, kind = 'expr'",
                    (name, info["expr"], desc, json.dumps(params)))
    except Exception as e:                       # noqa: BLE001
        raise HTTPException(500, f"保存失败：{e}")
    return {"ok": True, "name": name, "expr": info["expr"], "factors": info["factors"]}


def history(limit: int = 12) -> dict:
    """最近几次回测记录（backtest_run 表），库不可用返回空。"""
    if dbmod is None:
        return {"runs": [], "db": False}
    try:
        with dbmod.session() as conn:
            runs = dbmod.top_backtests(conn, limit)
        for r in runs:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif isinstance(v, float):
                    r[k] = round(v, 4)
        return {"runs": runs, "db": True}
    except Exception:                            # noqa: BLE001
        return {"runs": [], "db": False}
