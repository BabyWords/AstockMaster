# -*- coding: utf-8 -*-
"""
回测入口 —— 运行策略的唯一入口。
用法：
  python run_backtest.py                     # 列出所有已注册策略
  python run_backtest.py 小市值反转           # 跑指定策略（默认配置）
  python run_backtest.py 小市值反转 -n 5 -hold 10 -price 2 -cost 0.003
"""
import sys

import backtest_engine as be
import strategies  # noqa: F401  触发策略注册


def main():
    if len(sys.argv) == 1:
        print("已注册策略：")
        for k in be.STRATEGIES:
            print(f"  - {k}")
        print("\n用法：python run_backtest.py <策略名> [-n 5] [-hold 10] [-price 2] [-cost 0.003] [--start 20210101]")
        sys.exit(0)

    name, overrides = be._parse_args(sys.argv[1:])
    if name not in be.STRATEGIES:
        print(f"❌ 未找到策略「{name}」。可选：{list(be.STRATEGIES)}")
        sys.exit(1)
    be.run_strategy(name, overrides)


if __name__ == "__main__":
    main()
