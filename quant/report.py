# -*- coding: utf-8 -*-
"""L4 呈现层 —— 把回测结果打印成人能读的表格（只被 CLI 脚本调用）。
=================================================================

引擎本身不做任何 IO：这样换成 web / JSON / 写库都只是换一个呈现层，
计算逻辑一份。要加新的输出形式（成交明细、Excel），也放这里。
"""
from __future__ import annotations

from . import picker as pk
from .engine import by_year


def print_backtest(name, cfg, periods, r):
    """终端回测报告：总体指标 + 分年明细。"""
    print("\n" + "=" * 82)
    print(f"【策略：{name}】 TOP{cfg['top_n']} / 持有{cfg['hold_days']}天 / "
          f"成本{cfg['cost'] * 100:.1f}%")
    print(f"  股票池：{pk.describe_filters(cfg.get('filters'))}")
    print("=" * 82)
    print(f"  调仓期数 {r['n']:>4}   10万→{r['cap']:>12,.0f}   "
          f"累计 {r['net_cum']:>+8.1f}%   年化 {r['ann']:>+6.2f}%")
    print(f"  期胜率 {r['win']:>4.0f}%   最大回撤 {r['mdd']:>7.1f}%   "
          f"停牌/缺数据票数 {r['nan_cnt']}")

    years = by_year(periods, cfg)
    if years:
        print("  " + "-" * 60)
        print(f"  {'年份':<6}{'期数':>5}{'收益(扣成本)':>14}{'回撤':>10}{'胜率':>8}")
        for y, st in years.items():
            bucket = [p[1] for p in periods if p[0][:4] == y]
            win = sum(1 for x in bucket if x > 0) / len(bucket) * 100
            print(f"  {y:<6}{st['n']:>5}{st['ret'] * 100:>+13.1f}%"
                  f"{st['mdd'] * 100:>+9.1f}%{win:>7.0f}%")
    print()


def print_selection(res):
    """终端选股报告（scripts/select_stocks.py 用）。"""
    print("=" * 84)
    print(f"{res['strategy']} · 数据日期 {res['date']} · "
          f"候选池 {res['pool']} 只 · TOP{res['top_n']}")
    print(f"股票池：{res['universe']}")
    print("=" * 84)
    if not res["rows"]:
        print("⚠️ 候选池为空（可能数据未更新或过滤过严）")
        return
    print(f"{'#':<3}{'代码':<8}{'名称':<10}{'得分':>7}{'收盘':>8}{'涨幅%':>8}"
          f"{'20日涨幅':>9}{'20日波动':>9}{'市值亿':>8}{'换手%':>7}{'成交额亿':>9}")
    print("-" * 84)
    for r in res["rows"]:
        rev = f"{r['rev20']:>9.2f}" if r["rev20"] is not None else f"{'—':>9}"
        vol = f"{r['vol20']:>9.2f}" if r["vol20"] is not None else f"{'—':>9}"
        print(f"{r['rank']:<3}{r['code']:<8}{r['name']:<10}{r['score']:>7.2f}"
              f"{r['close']:>8.2f}{r['pct']:>8.2f}{rev}{vol}"
              f"{r['mktcap']:>8.1f}{r['turn']:>7.2f}{r['amt']:>9.2f}")
    st = res.get("style")
    if st:
        print("-" * 84)
        print(f"风格参考（近{st['days']}日）：小盘 {st['small']:+.2f}% / "
              f"大盘 {st['large']:+.2f}% / 小盘超额 {st['excess']:+.2f}%  （仅参考，不拦截）")
