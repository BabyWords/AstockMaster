# -*- coding: utf-8 -*-
"""回测入口（命令行）—— 跑一个策略并打印报告。
================================================

    python scripts/run_backtest.py                     # 列出所有已注册策略
    python scripts/run_backtest.py 小市值反转           # 默认配置
    python scripts/run_backtest.py 小市值反转 -n 5 -hold 10 -price 2 -cost 0.003
    python scripts/run_backtest.py 小市值反转 --start 20190101 --no-liq

公式策略（存在 strategy 表里的表达式）同样可以直接按名字跑。
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import sys

from quant import engine, expr, report

USAGE = ("用法：python scripts/run_backtest.py <策略名> [-n 5] [-hold 20] "
         "[-price 2] [-cost 0.003] [--start 20190101] [--no-liq]")


def parse_args(argv):
    """命令行参数 -> (策略名, 覆盖项)。"""
    overrides, name, i = {}, None, 0
    while i < len(argv):
        a = argv[i]
        if a in ("-n", "--top"):
            overrides["top_n"] = int(argv[i + 1]); i += 2
        elif a in ("-hold", "--hold"):
            overrides["hold_days"] = int(argv[i + 1]); i += 2
        elif a in ("-price", "--min-price"):
            overrides["min_price"] = float(argv[i + 1]); i += 2
        elif a in ("-cost",):
            overrides["cost"] = float(argv[i + 1]); i += 2
        elif a in ("-amt", "--min-amt"):
            overrides["filters"] = {**overrides.get("filters", {}),
                                    "min_amt": float(argv[i + 1])}; i += 2
        elif a == "--max-pct":
            overrides["filters"] = {**overrides.get("filters", {}),
                                    "max_pct": float(argv[i + 1])}; i += 2
        elif a in ("--no-liq", "--no-liquidity"):
            # 关掉流动性门槛（旧口径），只用于和实盘对比，不建议实际使用
            overrides["filters"] = {**overrides.get("filters", {}),
                                    "min_amt": 0.0, "max_pct": None}; i += 1
        elif a == "--start":
            if i + 1 < len(argv):
                overrides["start"] = argv[i + 1]
            i += 2
        elif a.startswith("--start="):
            overrides["start"] = a.split("=", 1)[1]; i += 1
        else:
            if name is None:
                name = a
            i += 1
    return name, overrides


def main():
    if len(sys.argv) == 1:
        print("已注册策略：")
        for k in engine.STRATEGIES:
            print(f"  - {k}")
        print("\n" + USAGE)
        return 0

    name, overrides = parse_args(sys.argv[1:])
    try:
        fn = expr.resolve(name)
    except ValueError as e:
        print(f"❌ {e}")
        return 1

    cfg = {**engine.DEFAULT_CONFIG, **overrides}
    print("[准备] 加载数据 + 因子（约 20 秒）...")
    ds = engine.load_all(cfg)
    print(f"[准备] 完成，{len(ds.dates)} 个交易日，耗时 {ds.load_seconds:.0f}s")
    periods = engine.run_backtest(fn, cfg, ds)
    report.print_backtest(name, cfg, periods, engine.evaluate(periods, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
