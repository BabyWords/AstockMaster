# -*- coding: utf-8 -*-
"""单次回测的独立进程入口 —— 被 webapp「助手 · 回测」以子进程方式调用。
=========================================================================

为什么必须用子进程：
    一次全样本回测峰值内存约 4.0GB、耗时约 20-50 秒（读外置盘的 1.1G 缓存）。
    pandas 吃掉的堆内存基本不还给系统，若跑在 FastAPI 进程里，点两次就 OOM。

用法：
    python scripts/backtest_job.py <spec.json> <out.json>

spec.json:
    {
      "name":     "小市值反转低波 · TOP5/20天",   // 展示用，随结果回显
      "strategy": "小市值反转低波",               // 代码策略或公式策略名
      "params":   {"top_n":5,"hold_days":20,"cost":0.003,
                   "start":"20190101","min_amt":5000,"max_pct":9.5}
    }

out.json：无论成功失败都会写出，前端据此展示。
    {"ok":true, "metrics":{...}, "yearly":{...}, "nav":[...], "run_id":12, ...}
    {"ok":false,"error":"..."}
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import json
import os
import sys
import time
import traceback

from quant import db, engine, expr, picker as pk

# 可以覆盖 DEFAULT_CONFIG 的键（其余一律忽略，避免前端乱传）
_CFG_KEYS = ("top_n", "hold_days", "cost", "capital", "min_price", "start", "end")


def _write(path: str, payload: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def _build_cfg(params: dict) -> tuple[dict, dict]:
    """spec.params -> (engine 配置, 只含过滤项的 filters)。"""
    cfg = dict(engine.DEFAULT_CONFIG)
    for k in _CFG_KEYS:
        if params.get(k) is not None:
            cfg[k] = params[k]
    # 股票池过滤：显式传 None 表示不限，未传则用默认（实盘口径）
    cfg["filters"] = {k: params[k] for k in ("min_price", "min_amt", "max_pct")
                      if k in params}
    return cfg, cfg["filters"]


def run(spec: dict) -> dict:
    """执行一次回测，返回结果字典（不写文件）。"""
    t0 = time.time()
    name = spec.get("strategy")
    fn = expr.resolve(name)                       # 代码策略或 strategy 表里的公式策略
    cfg, filters = _build_cfg(spec.get("params") or {})

    print(f"[job] {name} 配置 {cfg}", flush=True)
    ds = engine.load_all(cfg)
    periods = engine.run_backtest(fn, cfg, ds)
    m = engine.evaluate(periods, cfg)
    yearly = engine.by_year(periods, cfg)

    res = {
        "ok": True,
        "name": spec.get("name") or f"{name} · TOP{cfg['top_n']}/{cfg['hold_days']}天",
        "strategy": name,
        "params": {"top_n": cfg["top_n"], "hold_days": cfg["hold_days"],
                   "cost": cfg["cost"], "start": cfg["start"], "end": cfg["end"],
                   "capital": cfg["capital"],
                   "filters": {**pk.DEFAULT_FILTERS, **filters}},
        "universe": pk.describe_filters(filters),
        "metrics": {
            "periods": m["n"],
            "total_return": round(m["net_cum"] / 100, 4),
            "annual_return": round(m["ann"] / 100, 4) if m["ann"] == m["ann"] else None,
            "max_drawdown": round(m["mdd"] / 100, 4),
            "win_rate": round(m["win"] / 100, 4),
            "final_capital": round(m["cap"], 2),
            "miss": m["nan_cnt"],
        },
        "yearly": {y: round(s["ret"], 4) for y, s in yearly.items()},
        "yearly_n": {y: s["n"] for y, s in yearly.items()},
        "yearly_mdd": {y: round(s["mdd"], 4) for y, s in yearly.items()},
        "nav": engine.equity(periods, cfg),
        "elapsed": round(time.time() - t0, 1),
    }

    # 存进 backtest_run，方便以后检索「我做过哪些实验」
    try:
        with db.session() as conn:
            res["run_id"] = db.save_backtest(
                conn,
                name=res["name"], strategy=name,
                params={**res["params"], "universe": res["universe"]},
                start_date=ds.dates[0] if ds.dates else cfg["start"],
                end_date=ds.dates[-1] if ds.dates else None,
                topn=cfg["top_n"], hold_days=cfg["hold_days"],
                cost_bps=round(cfg["cost"] * 10000, 2),
                universe=res["universe"], init_cash=cfg["capital"],
                total_return=res["metrics"]["total_return"],
                annual_return=res["metrics"]["annual_return"],
                max_drawdown=res["metrics"]["max_drawdown"],
                win_rate=res["metrics"]["win_rate"],
                trade_count=m["n"] * cfg["top_n"],
                yearly=res["yearly"], nav=res["nav"],
                note=spec.get("note"),
            )
    except Exception as e:                       # noqa: BLE001
        res["db_error"] = str(e)
    return res


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/backtest_job.py <spec.json> <out.json>")
        return 2
    spec_path, out_path = sys.argv[1], sys.argv[2]
    try:
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        res = run(spec)
        _write(out_path, res)
        print(f"[job] 完成 {res['elapsed']}s 累计 {res['metrics']['total_return'] * 100:+.1f}%",
              flush=True)
        return 0
    except Exception as e:                       # noqa: BLE001
        traceback.print_exc()
        _write(out_path, {"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
