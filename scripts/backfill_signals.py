# -*- coding: utf-8 -*-
"""回填 signal 表的真实收益 —— 样本外验证闭环的最后一块。
=========================================================

signal 表每天存「策略今天选了哪几只」，这个脚本负责回答：
**这些票后来实际涨了多少？** 不填这一步，永远只能「相信回测」；
填了才能「验证策略」—— 策略失效了能看出来。

口径与引擎 `_add_fwd` 严格一致：
    买入价 = 信号日【次日】收盘（close_adj.shift(-1)）
    fwd_ret_N = close_adj.shift(-(N+1)) / close_adj.shift(-1) - 1
  （用前复权价比值，复权因子自动约掉，与基准期无关，除权不引入误差）

规则：
    · 只填「已经走完对应天数」的信号：不足 20 个交易日的先填 1/5，20 到位后补
    · 旧值不覆盖（coalesce），重跑幂等
    · fwd_ret_20 填上时，仍为 pending 的信号标记 expired，避免污染 pending 列表

数据源：优先 recent_panel（140 个交易日，读约 1s）；更早的信号回退全样本缓存。

用法：python scripts/backfill_signals.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  注入 sys.path
import os

import pandas as pd

from quant import config, db
from quant.data import load_raw

FWD_N = (1, 5, 20)


def _fwd_table(raw: pd.DataFrame, codes: set[str]) -> dict:
    """返回 {(code, ymd): {1: ret, 5: ret, 20: ret}}，按引擎口径算前复权未来收益。"""
    sub = raw[raw["股票代码"].astype(str).isin(codes)].copy()
    sub["股票代码"] = sub["股票代码"].astype(str)
    sub["交易日期"] = sub["交易日期"].astype(str)
    sub = sub.dropna(subset=["收盘价（元）", "复权因子"])
    if not len(sub):
        return {}
    sub = sub.sort_values(["股票代码", "交易日期"], kind="stable")
    # 前复权（基准=每只股票样本末期，与 preprocess 相同）
    base = sub.groupby("股票代码")["复权因子"].transform("last")
    sub["close_adj"] = sub["收盘价（元）"] * sub["复权因子"] / base

    g = sub.groupby("股票代码", sort=False)
    buy = g["close_adj"].shift(-1)                    # 次日收盘买入
    for n in FWD_N:
        sub[f"_fwd{n}"] = g["close_adj"].shift(-(n + 1)) / buy - 1.0

    # 只保留有任意一个未来收益的行，再一次性转成字典（比逐行 Python 循环快一个量级）
    keep = sub.dropna(subset=[f"_fwd{n}" for n in FWD_N], how="all")
    if not len(keep):
        return {}
    cols = [f"_fwd{n}" for n in FWD_N]
    idx = pd.MultiIndex.from_arrays([keep["股票代码"], keep["交易日期"]])
    frame = pd.DataFrame(keep[cols].to_numpy(dtype="float64"), index=idx, columns=cols)
    return {k: {n: float(v[n]) for n in FWD_N if pd.notna(v[n])}
            for k, v in frame.to_dict("index").items()}


def run() -> int:
    """回填所有缺收益的信号。返回更新行数。"""
    # ① 捞出还有收益没填的信号
    with db.session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id, signal_date, code, status
                     from signal
                    where fwd_ret_1 is null or fwd_ret_5 is null or fwd_ret_20 is null
                    order by signal_date, rank""")
            rows = cur.fetchall()
    if not rows:
        print("[回填] signal 表没有待回填的信号")
        return 0
    print(f"[回填] 待处理信号 {len(rows)} 条（{rows[0][1]} ~ {rows[-1][1]}）")

    dates_needed = {r[1].strftime("%Y%m%d") for r in rows}
    codes_needed = {str(r[2]).zfill(6) for r in rows}

    # ② 数据源：先试 recent_panel；覆盖不到的日期再上全样本
    table: dict = {}
    missing: set[str] = set()
    if os.path.exists(config.RECENT):
        raw = load_raw(config.RECENT)
        have = set(raw["交易日期"].astype(str).unique())
        missing = dates_needed - have
        table = _fwd_table(raw, codes_needed)
    else:
        missing = dates_needed

    if missing:
        print(f"[回填] {len(missing)} 个信号日期超出 recent_panel，读全样本缓存补")
        table.update(_fwd_table(load_raw(config.CACHE), codes_needed))

    # ③ 逐条回填（coalesce 不覆盖旧值；fwd_ret_20 到位时 pending → expired）
    updated = filled20 = expired = 0
    with db.session() as conn:
        with conn.cursor() as cur:
            for sid, sdate, code, status in rows:
                vals = table.get((str(code).zfill(6), sdate.strftime("%Y%m%d")))
                if not vals:
                    continue                      # 还没到时间 / 退市无数据
                f1, f5, f20 = vals.get(1), vals.get(5), vals.get(20)
                cur.execute(
                    """update signal set
                         fwd_ret_1  = coalesce(fwd_ret_1,  %s),
                         fwd_ret_5  = coalesce(fwd_ret_5,  %s),
                         fwd_ret_20 = coalesce(fwd_ret_20, %s),
                         status = case when status = 'pending' and %s
                                       then 'expired' else status end
                       where id = %s""",
                    (f1, f5, f20, f20 is not None, sid))
                updated += cur.rowcount
                if f20 is not None:
                    filled20 += 1
                    if status == "pending":
                        expired += 1
    print(f"[回填] 更新 {updated} 条；fwd_ret_20 已齐 {filled20} 条"
          f"（其中 pending→expired {expired} 条）")
    return updated


def report():
    """打印 v_signal_perf（样本外验证的核心视图）。"""
    with db.session() as conn:
        with conn.cursor() as cur:
            cur.execute("""select strategy, n_signal, avg_ret_1, avg_ret_5,
                                  avg_ret_20, top5_avg_ret_20
                             from v_signal_perf order by strategy""")
            perf = cur.fetchall()
            cur.execute("""select signal_date, strategy, count(*) n,
                                  round(avg(fwd_ret_1)*100, 2) as ret1
                             from signal where fwd_ret_1 is not null
                            group by 1,2 order by 1 desc, 2 limit 15""")
            daily = cur.fetchall()
    if perf:
        print("\n=== 策略样本外表现（v_signal_perf）===")
        print(f"{'策略':<14}{'信号数':>6}{'1日均%':>9}{'5日均%':>9}{'20日均%':>9}{'TOP5均%':>9}")
        for s, n, r1, r5, r20, t5 in perf:
            fmt = lambda x: f"{(x * 100) if x is not None else float('nan'):>9.2f}"  # noqa: E731
            print(f"{s:<14}{n:>6}{fmt(r1)}{fmt(r5)}{fmt(r20)}{fmt(t5)}")
    else:
        print("\n（还没有信号走完 20 个交易日，v_signal_perf 暂空——正常，20 天后自然出现）")
    if daily:
        print("\n=== 已出 1 日收益的信号 ===")
        for d, s, n, r1 in daily:
            print(f"  {d} {s:<14} {n} 只  次日平均 {r1:+.2f}%")


if __name__ == "__main__":
    run()
    report()
