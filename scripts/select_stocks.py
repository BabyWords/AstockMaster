# -*- coding: utf-8 -*-
"""每日选股（命令行）。
=====================

    python scripts/select_stocks.py                    # 默认策略，最新交易日，前 5
    python scripts/select_stocks.py -s 纯小市值 -n 10
    python scripts/select_stocks.py -d 20261030        # 指定日期
    python scripts/select_stocks.py --min-amt 0        # 关掉成交额门槛
    python scripts/select_stocks.py --no-db            # 不写库

算的一部分在 quant.selection（回测与网页共用同一个 pick），
本文件只负责解析参数、落盘/落库、打印。
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import re
import sys

from quant import report, selection


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    strategy = selection.DEFAULT_STRATEGY
    top_n, target, write_db = selection.TOP_N, None, True
    filters = {}

    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-s", "--strategy") and i + 1 < len(argv):
            strategy = argv[i + 1]; i += 2
        elif a in ("-n", "--top") and i + 1 < len(argv):
            top_n = int(argv[i + 1]); i += 2
        elif a in ("-d", "--date") and i + 1 < len(argv):
            target = argv[i + 1]; i += 2
        elif a in ("-amt", "--min-amt") and i + 1 < len(argv):
            filters["min_amt"] = float(argv[i + 1]); i += 2
        elif a in ("-price", "--min-price") and i + 1 < len(argv):
            filters["min_price"] = float(argv[i + 1]); i += 2
        elif a == "--max-pct" and i + 1 < len(argv):
            filters["max_pct"] = float(argv[i + 1]); i += 2
        elif a == "--no-db":
            write_db = False; i += 1
        elif re.match(r"^\d{8}$", a):
            target = a; i += 1
        else:
            i += 1

    res = selection.select(strategy, top_n, target, filters)
    report.print_selection(res)
    print(f"\n已保存 → {selection.save_csv(res)}")
    if write_db:
        print(selection.save_db(res))
    print("\n提醒：收盘后选股，次日买入，持有约 20 个交易日，单票 -8% 止损。")
    return res


if __name__ == "__main__":
    main()
