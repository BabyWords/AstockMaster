# -*- coding: utf-8 -*-
"""兼容入口 —— 实现在 scripts/run_backtest.py（用法完全一致）。"""
import sys

from scripts.run_backtest import main

if __name__ == "__main__":
    sys.exit(main())
