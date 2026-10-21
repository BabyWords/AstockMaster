# -*- coding: utf-8 -*-
"""
风格中性多因子组合回测（2022-2026 全样本）
================================================================
思路：单一因子（如小市值）强依赖某一种市场风格，风格切换就失效。
这里把"小市值 + 反转"（进攻）和"低波动 + 低换手"（防御）组合起来，
看风格中性组合能否在跨风格时更稳健——尤其样本外 2022-2024 的回撤。

组合对比（全部 Z-score 等权，买前10%等权篮子，20日调仓）：
  A: SIZE（纯小市值，基线）
  B: SIZE + REV
  C: SIZE + REV + VOL（三因子·风格中性）
  D: SIZE + REV + VOL + TURN（四因子）

因子方向（分高=越好）：
  SIZE 小市值 = -log(流通市值)
  REV  反转   = -(20日收益率)
  VOL  低波动 = -(20日收益率标准差)
  TURN 低换手 = -(20日均换手率)
================================================================
"""
import os
import time
import pandas as pd
import numpy as np

OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = os.path.join(OUT, "daily_full_2022_2026.csv")


def load_prep():
    df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["收盘价（元）", "复权因子", "换手率（%）", "市盈率（TTM）",
              "股息率（TTM）（%）", "流通市值（万元）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）"])
    df = df.sort_values(["股票代码", "交易日期"])
    base = df.groupby("股票代码")["复权因子"].last().rename("base_factor")
    df = df.merge(base, on="股票代码", how="left")
    df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["base_factor"]

    g = df.groupby("股票代码", sort=False)
    df["ret"] = g["close_adj"].pct_change()
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
    df["REV"] = -g["close_adj"].pct_change(20)
    df["VOL"] = -g["ret"].transform(lambda s: s.rolling(20).std())
    df["TURN"] = -g["换手率（%）"].transform(lambda s: s.rolling(20).mean())
    df["MOM"] = g["close_adj"].pct_change(60)
    pe = df["市盈率（TTM）"]
    df["EP"] = np.where(pe > 0, 1.0 / pe, np.nan)
    df["DY"] = df["股息率（TTM）（%）"]
    df["next20"] = g["close_adj"].transform(lambda s: s.shift(-20) / s - 1.0)
    df["year"] = df["交易日期"].str[:4]
    return df


def zscore(s):
    m = s.mean()
    std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - m) / std


def factor_corr(df, rebal):
    """每个调仓日算因子横截面相关系数，取平均"""
    factors = ["SIZE", "REV", "VOL", "TURN", "MOM", "EP", "DY"]
    corr_list = []
    for t in rebal:
        sub = df[df["交易日期"] == t][factors].dropna()
        if len(sub) < 200:
            continue
        corr_list.append(sub.corr())
    if not corr_list:
        return None
    avg = pd.concat(corr_list).groupby(level=0).mean()
    return avg


def run_combo(df, factor_cols, rebal):
    rows = []
    for t in rebal:
        sub = df[df["交易日期"] == t].dropna(subset=factor_cols + ["next20"]).copy()
        if len(sub) < 50:
            continue
        score = pd.Series(0.0, index=sub.index)
        for f in factor_cols:
            score = score + zscore(sub[f])
        sub["score"] = score
        sub = sub.sort_values("score", ascending=False)
        top_n = max(1, int(len(sub) * 0.10))
        top = sub.head(top_n)
        rows.append({"date": t, "ret": top["next20"].mean(),
                     "n": len(top), "year": t[:4]})
    return pd.DataFrame(rows)


def stats(r, bench, name):
    r = r.sort_values("date").reset_index(drop=True)
    r["cum"] = (1 + r["ret"]).cumprod()
    total = r["cum"].iloc[-1] - 1
    months = len(r)
    ann = (1 + r["ret"]).prod() ** (12 / months) - 1
    win = (r["ret"] > 0).mean() * 100
    merged = r.merge(bench.rename(columns={"ret": "bench_ret"}), on="date", how="inner")
    excess = merged["ret"] - merged["bench_ret"]
    ex_win = (excess > 0).mean() * 100
    mdd = (r["cum"] / r["cum"].cummax() - 1).min() * 100
    print(f"\n=== {name} ===")
    print(f"  期数 {months}  平均持仓 {r['n'].mean():.0f} 只")
    print(f"  月均 {r['ret'].mean()*100:+.3f}%  年化 {ann*100:+.2f}%  累计 {total*100:+.2f}%")
    print(f"  胜率 {win:.0f}%  超额月均 {excess.mean()*100:+.3f}%  跑赢占比 {ex_win:.0f}%  最大回撤 {mdd:.2f}%")
    return {"name": name, "months": months, "avg_n": r['n'].mean(),
            "month": r['ret'].mean(), "ann": ann, "total": total,
            "win": win, "excess": excess.mean(), "ex_win": ex_win, "mdd": mdd}


def main():
    t0 = time.time()
    df = load_prep()
    print(f"[数据] {len(df)} 行", flush=True)

    dates = sorted(df["交易日期"].unique())
    rebal = dates[::20]
    print(f"[调仓] {len(rebal)} 期，区间 {rebal[0]} ~ {rebal[-1]}", flush=True)

    # 因子相关性（用于说明互补性）
    corr = factor_corr(df, rebal)
    if corr is not None:
        print("\n[因子横截面相关系数（全样本平均）]")
        print(corr[["SIZE", "REV", "VOL", "TURN"]].round(2).to_string())

    # 基准
    bench = pd.DataFrame({
        "date": rebal,
        "ret": [df[df["交易日期"] == t]["next20"].mean() for t in rebal]
    }).dropna()
    bench["year"] = bench["date"].str[:4]

    combos = [
        ("A 纯小市值", ["SIZE"]),
        ("B 小市值+反转", ["SIZE", "REV"]),
        ("C 三因子(风格中性)", ["SIZE", "REV", "VOL"]),
        ("D 四因子(含低换手)", ["SIZE", "REV", "VOL", "TURN"]),
    ]

    # 跑全样本组合（一次性），再按 year 分段统计
    results = {}
    for name, cols in combos:
        results[name] = run_combo(df, cols, rebal)
        print(f"[组合] {name}: {len(results[name])} 期", flush=True)

    segs = [("ALL", "全样本", None),
            ("OOS", "样本外 2022-2024", ["2022", "2023", "2024"]),
            ("IS", "样本内 2025-2026", ["2025", "2026"])]

    summary = {}
    for seg, segname, ys in segs:
        b = bench if ys is None else bench[bench["year"].isin(ys)]
        print(f"\n{'='*64}\n>>> {segname} <<<  (基准月均 {b['ret'].mean()*100:+.3f}%)")
        for name, cols in combos:
            r = results[name]
            r = r if ys is None else r[r["year"].isin(ys)]
            summary[(seg, name)] = stats(r, b, name)

    # 汇总表
    print("\n" + "=" * 64)
    print("[汇总表] 月均 / 年化 / 超额 / 最大回撤")
    print(f"{'组合':24s} {'样本':16s} {'期数':>4s} {'月均':>8s} {'年化':>8s} {'胜率':>6s} {'超额':>8s} {'回撤':>8s}")
    for seg, segname, ys in segs:
        for name, cols in combos:
            r = summary[(seg, name)]
            print(f"{name:24s} {segname:16s} {r['months']:4d} "
                  f"{r['month']*100:+8.2f}% {r['ann']*100:+8.2f}% {r['win']:5.0f}% "
                  f"{r['excess']*100:+8.2f}% {r['mdd']:7.2f}%")

    print(f"\n总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
