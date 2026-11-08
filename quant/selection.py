# -*- coding: utf-8 -*-
"""选股管线 —— 「今天买哪几只」的唯一实现（CLI 与网页共用）。
==============================================================

    data(recent_panel) → preprocess → compute_factors → picker.pick → 名单
                                                            ↑
                                          回测 engine.run_backtest 调的是同一个 pick

所以页面上回测跑出来的成绩，就是按这个名单实盘能拿到的成绩。

本模块只做「算 + 落盘/落库」，不打印、不解析命令行（那些在
scripts/select_stocks.py 和 webapp/api/assistant.py 里）。
"""
from __future__ import annotations

import os
import re
import threading

import numpy as np
import pandas as pd

from . import config, picker as pk
from .data import load_raw, preprocess
from .factors import compute_factors

DEFAULT_STRATEGY = "小市值反转低波"
TOP_N = 5
OUT_DIR = config.SELECT_OUT

# 选股面板缓存：recent_panel 有 97MB / 78 万行，读 CSV + 算因子约 2.5s。
# 网页上换个策略再选一次不该重读一遍，所以按 (路径, mtime) 缓存最近一份。
_PANEL: dict = {}
_PANEL_LOCK = threading.Lock()
_PANEL_MAX = 1


def load_panel(panel_path: str | None = None) -> pd.DataFrame:
    """读选股面板（已算好因子）。同文件不重复读：命中缓存约 0.05s。"""
    path = panel_path or config.RECENT
    if not os.path.exists(path):
        raise FileNotFoundError(f"选股缓存不存在：{path}（先跑 scripts/build_recent.py）")
    key = (path, os.path.getmtime(path))
    with _PANEL_LOCK:
        if _PANEL.get("key") == key:
            return _PANEL["df"]
    raw = load_raw(path)
    df = preprocess(raw, {"min_price": 0})       # 价格门槛交给 picker，保证口径统一
    df = compute_factors(df)
    with _PANEL_LOCK:
        _PANEL.clear()
        _PANEL.update(key=key, df=df)
    return df


def clear_panel_cache():
    """数据更新后调用，避免网页继续用旧面板。"""
    with _PANEL_LOCK:
        _PANEL.clear()


def _style_reference(panel: pd.DataFrame, lookback: int = 20):
    """大小盘风格参考：小盘组(市值最小50%) vs 大盘组(市值最大20%) 近 20 日累计涨幅。

    只作参考，不拦截选股（2024-2026 回测证明择时闸门整体负贡献）。
    """
    dates = sorted(panel["交易日期"].unique())
    if len(dates) < lookback + 1:
        return None
    sub = panel[panel["交易日期"] >= dates[-lookback]]
    small_daily, large_daily = [], []
    for d, g in sub.groupby("交易日期"):
        g = g.dropna(subset=["流通市值（万元）", "涨跌幅（%）"])
        g = g[g["流通市值（万元）"] > 0]
        if len(g) < 100:
            continue
        g = g.sort_values("流通市值（万元）")
        n = len(g)
        large = g.tail(max(1, int(n * 0.2)))["涨跌幅（%）"].astype(float) / 100
        small = g.head(max(1, int(n * 0.5)))["涨跌幅（%）"].astype(float) / 100
        small_daily.append(float(small.mean()))     # 组内等权日收益
        large_daily.append(float(large.mean()))
    if not small_daily:
        return None
    s = float(np.prod([1 + x for x in small_daily]) - 1) * 100
    la = float(np.prod([1 + x for x in large_daily]) - 1) * 100
    return {"small": s, "large": la, "excess": s - la, "days": len(small_daily)}


def select(strategy: str = DEFAULT_STRATEGY, top_n: int = TOP_N,
           target: str | None = None, filters: dict | None = None,
           panel_path: str | None = None) -> dict:
    """跑一次选股，返回 {date, strategy, filters, pool, rows[...], style}。"""
    from . import expr
    fn = expr.resolve(strategy)                  # 代码策略或用户保存的公式策略
    df = load_panel(panel_path)

    dates = sorted(df["交易日期"].unique())
    if target:
        target = str(target).replace("-", "")
        if target not in dates:
            raise ValueError(f"指定日期 {target} 不在数据中，最新可用：{dates[-1]}")
        cur = target
    else:
        cur = dates[-1]

    day = df[df["交易日期"] == cur]
    top = pk.pick(day, fn, filters, top_n)

    rows = []
    for rank, (_, r) in enumerate(top.iterrows(), start=1):
        rev = r.get("REV20")
        vol = r.get("VOL20")
        rows.append({
            "rank": rank,
            "code": str(r["股票代码"]),
            "name": str(r["股票名称"]),
            "score": round(float(r["score"]), 4),
            "close": round(float(r["收盘价（元）"]), 2),
            "pct": round(float(r.get("PCT") if pd.notna(r.get("PCT")) else 0), 2),
            "rev20": round(float(-rev) * 100, 2) if pd.notna(rev) else None,
            "vol20": round(float(vol) * 100, 2) if pd.notna(vol) else None,
            "mktcap": round(float(r["流通市值（万元）"]) / 10000, 1),
            "turn": round(float(r.get("TURN") if pd.notna(r.get("TURN")) else 0), 2),
            "amt": round(float(r.get("AMT") if pd.notna(r.get("AMT")) else 0) / 10000, 2),
            "f_size": float(r.get("SIZE") or 0),
            "f_rev20": float(rev) if pd.notna(rev) else None,
            "f_vol20": float(vol) if pd.notna(vol) else None,
        })

    return {
        "date": cur,
        "strategy": strategy,
        "top_n": top_n,
        "filters": {**pk.DEFAULT_FILTERS, **(filters or {})},
        "universe": pk.describe_filters(filters),
        "pool": int(len(pk.apply_filters(day, filters))),
        "rows": rows,
        "style": _style_reference(df),
    }


def save_csv(res: dict, out_dir: str | None = None) -> str:
    """把名单存成 CSV（utf-8-sig，Excel 直接打开不乱码）。"""
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    suffix = "" if res["strategy"] == DEFAULT_STRATEGY else f"_{res['strategy']}"
    # 公式策略的名字里可能有空格/斜杠，别让它变成路径分隔符
    suffix = re.sub(r'[\\/:*?"<>|\s]+', "_", suffix)
    path = os.path.join(out_dir, f"选股{suffix}_{res['date']}.csv")
    pd.DataFrame([{
        "股票代码": r["code"], "股票名称": r["name"], "综合得分": r["score"],
        "收盘价": r["close"], "涨跌幅%": r["pct"], "20日涨幅": r["rev20"],
        "20日波动": r["vol20"], "流通市值万": r["mktcap"] * 10000,
        "换手率%": r["turn"], "成交额万": r["amt"] * 10000,
    } for r in res["rows"]]).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def save_db(res: dict, hold_days: int = 20) -> str:
    """写进 signal 表，供事后回填真实收益、验证策略在样本外是否还有效。"""
    try:
        from . import db
    except Exception as e:                       # noqa: BLE001
        return f"跳过写库（{e}）"
    try:
        with db.session() as conn:
            n = db.save_signals(conn, res["date"], res["strategy"],
                                [{"code": r["code"], "rank": r["rank"],
                                  "score": r["score"], "f_size": r["f_size"],
                                  "f_rev20": r["f_rev20"], "f_vol20": r["f_vol20"],
                                  "ref_price": r["close"]} for r in res["rows"]],
                                hold_days=hold_days)
        return f"已写入 signal 表 {n} 条"
    except Exception as e:                       # noqa: BLE001
        return f"写库失败（{e}）"
