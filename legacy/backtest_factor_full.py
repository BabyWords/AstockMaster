# -*- coding: utf-8 -*-
"""
全样本因子回测 + 样本外验证（2022-2026）
================================================================
单因子分组法：每个调仓日按因子值分5组，统计各组未来20日等权收益。
多因子组合：SIZE(小市值) + REV(反转) Z-score 等权，买前10%等权篮子。
分段：全样本 / 2022-2024(样本外) / 2025-2026(原样本内)
================================================================
"""
import os
import glob
import time
import pandas as pd
import numpy as np

DATA = "/Volumes/TOSHIBA/炒股"
DAILY_DIR = os.path.join(DATA, "每日行情")
OUT = "/Volumes/TOSHIBA/炒股/回测"
CACHE = os.path.join(OUT, "daily_full_2022_2026.csv")
YEARS = ["2022", "2023", "2024", "2025", "2026"]

COLS = ["交易日期", "股票代码", "股票名称", "收盘价（元）",
        "复权因子", "换手率（%）", "量比",
        "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]


def extract():
    files = []
    for y in YEARS:
        files += sorted(glob.glob(os.path.join(DAILY_DIR, y, "*.csv")))
    print(f"[提取] 共 {len(files)} 个日线文件", flush=True)
    parts = []
    for i, f in enumerate(files):
        try:
            parts.append(pd.read_csv(f, usecols=COLS,
                                     dtype={"股票代码": str, "交易日期": str},
                                     encoding="utf-8-sig", low_memory=False))
        except Exception as e:
            print(f"  [跳过] {f}: {e}", flush=True)
        if (i + 1) % 100 == 0:
            print(f"  已读 {i + 1}/{len(files)}", flush=True)
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(CACHE, index=False)
    print(f"[提取] 完成，{len(df)} 行", flush=True)
    return df


def prep(df):
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    num_cols = ["收盘价（元）", "复权因子", "换手率（%）", "量比",
                "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "流通市值（万元）"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["收盘价（元）"])
    df = df.sort_values(["股票代码", "交易日期"])
    base = df.groupby("股票代码")["复权因子"].last().rename("base_factor")
    df = df.merge(base, on="股票代码", how="left")
    df["adj"] = df["复权因子"] / df["base_factor"]
    df["close_adj"] = df["收盘价（元）"] * df["adj"]
    return df


def add_factors(df):
    g = df.groupby("股票代码", sort=False)
    df["ret"] = g["close_adj"].pct_change()
    df["REV"] = -g["close_adj"].pct_change(20)                     # 反转
    df["MOM"] = g["close_adj"].pct_change(60)                      # 动量
    df["VOL"] = -g["ret"].transform(lambda s: s.rolling(20).std())  # 低波
    df["TURN"] = -g["换手率（%）"].transform(lambda s: s.rolling(20).mean())  # 低换手
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))     # 小市值
    pe = df["市盈率（TTM）"]
    df["EP"] = np.where(pe > 0, 1.0 / pe, np.nan)                  # 低估值 E/P
    df["DY"] = df["股息率（TTM）（%）"]                             # 高股息
    # 未来20日收益
    df["next20"] = g["close_adj"].transform(lambda s: s.shift(-20) / s - 1.0)
    df["year"] = df["交易日期"].str[:4]
    return df


def zscore(s):
    m = s.mean()
    std = s.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - m) / std


def seg_ok(t, seg):
    if seg == "ALL":
        return True
    if seg == "OOS":  # 样本外 2022-2024
        return t[:4] in ("2022", "2023", "2024")
    if seg == "IS":   # 样本内 2025-2026
        return t[:4] in ("2025", "2026")
    return True


def single_factor(df, factor, rebal, seg):
    rows = []
    for t in rebal:
        if not seg_ok(t, seg):
            continue
        sub = df[(df["交易日期"] == t)].dropna(subset=[factor, "next20"]).copy()
        if len(sub) < 50:
            continue
        sub["rank"] = sub[factor].rank(method="first")
        sub["q"] = pd.qcut(sub["rank"], 5, labels=[1, 2, 3, 4, 5])
        for q, grp in sub.groupby("q"):
            rows.append({"date": t, "q": int(q), "ret": grp["next20"].mean()})
    r = pd.DataFrame(rows)
    if len(r) == 0:
        return None
    piv = r.pivot_table(index="date", columns="q", values="ret")
    if 1 not in piv.columns or 5 not in piv.columns:
        return None
    spread = (piv[5] - piv[1]).mean() * 100
    pos_ratio = ((piv[5] - piv[1]) > 0).mean() * 100
    q5 = piv[5].mean() * 100
    q1 = piv[1].mean() * 100
    return (spread, pos_ratio, q5, q1, len(piv))


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


def combo_stats(r, bench_r, name):
    r = r.sort_values("date").reset_index(drop=True)
    r["cum"] = (1 + r["ret"]).cumprod()
    total = r["cum"].iloc[-1] - 1
    months = len(r)
    ann = (1 + r["ret"]).prod() ** (12 / months) - 1
    win = (r["ret"] > 0).mean() * 100
    merged = r.merge(bench_r.rename(columns={"ret": "bench_ret"}), on="date", how="inner")
    excess = merged["ret"] - merged["bench_ret"]
    ex_win = (excess > 0).mean() * 100
    mdd = (r["cum"] / r["cum"].cummax() - 1).min() * 100
    print(f"\n=== {name} ===")
    print(f"  调仓期数: {months}  平均持仓: {r['n'].mean():.0f} 只")
    print(f"  平均月收益: {r['ret'].mean()*100:+.3f}%  年化: {ann*100:+.2f}%  累计: {total*100:+.2f}%")
    print(f"  月度胜率: {win:.0f}%  超额月均: {excess.mean()*100:+.3f}%  跑赢占比: {ex_win:.0f}%  最大回撤: {mdd:.2f}%")
    return {"name": name, "months": months, "avg_n": r['n'].mean(),
            "month_ret": r['ret'].mean(), "ann": ann, "total": total,
            "win": win, "excess": excess.mean(), "ex_win": ex_win, "mdd": mdd}


def main():
    t0 = time.time()
    if os.path.exists(CACHE):
        df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
        print(f"[缓存] 读取 {len(df)} 行", flush=True)
    else:
        df = extract()
    df = prep(df)
    print(f"[预处理] {len(df)} 行", flush=True)
    df = add_factors(df)
    print("[因子] 计算完成", flush=True)

    dates = sorted(df["交易日期"].unique())
    rebal = dates[::20]
    print(f"[调仓] 共 {len(rebal)} 个调仓日，区间 {rebal[0]} ~ {rebal[-1]}", flush=True)
    print(f"[样本] 年份分布: {df['year'].value_counts().sort_index().to_dict()}", flush=True)

    factors = ["REV", "MOM", "VOL", "TURN", "SIZE", "EP", "DY"]
    fname = {"REV": "反转", "MOM": "动量", "VOL": "低波动", "TURN": "低换手",
             "SIZE": "小市值", "EP": "低估值", "DY": "高股息"}

    # 基准（全市场等权 next20）
    bench_rows = [df[df["交易日期"] == t]["next20"].mean() for t in rebal]
    bench = pd.DataFrame({"date": rebal, "ret": bench_rows}).dropna()
    bench["year"] = bench["date"].str[:4]

    print("\n" + "=" * 70)
    print("【单因子分组回测：Q5-Q1 因子月收益（+为正因子）】")
    print("=" * 70)
    segs = [("ALL", "全样本"), ("OOS", "样本外2022-2024"), ("IS", "样本内2025-2026")]
    single_summary = {}
    for seg, segname in segs:
        print(f"\n---- {segname} ----")
        for f in factors:
            res = single_factor(df, f, rebal, seg)
            if res is None:
                print(f"  {fname[f]:6s}: 数据不足")
                continue
            spread, pos_ratio, q5, q1, nper = res
            print(f"  {fname[f]:6s}: Q5-Q1 {spread:+.3f}%/月 (正占比{pos_ratio:.0f}%, Q1={q1:+.2f}%, Q5={q5:+.2f}%, {nper}期)")
            single_summary[(seg, f)] = res

    # 组合回测
    print("\n" + "=" * 70)
    print("【组合回测：前10%等权篮子】")
    print("=" * 70)
    r_size = run_combo(df, ["SIZE"], rebal)
    r_both = run_combo(df, ["SIZE", "REV"], rebal)

    combo_res = {}
    for seg, segname in [("ALL", "全样本"), ("OOS", "样本外2022-2024"), ("IS", "样本内2025-2026")]:
        ys = {"ALL": None, "OOS": ["2022", "2023", "2024"], "IS": ["2025", "2026"]}[seg]
        b = bench if ys is None else bench[bench["year"].isin(ys)]
        rs = r_size if ys is None else r_size[r_size["year"].isin(ys)]
        rb = r_both if ys is None else r_both[r_both["year"].isin(ys)]
        print(f"\n>>> {segname} <<<")
        combo_res[(seg, "size")] = combo_stats(rs, b, "组合A：纯小市值")
        combo_res[(seg, "both")] = combo_stats(rb, b, "组合B：小市值+反转")
        bm = b["ret"].mean() * 100
        bcum = (1 + b["ret"]).prod() - 1
        print(f"  [基准] 全市场等权 月均 {bm:+.3f}%  累计 {bcum*100:+.2f}%")

    # 汇总表格
    print("\n" + "=" * 70)
    print("【组合结果汇总表】")
    print("=" * 70)
    print(f"{'组合':20s} {'样本':16s} {'期数':>4s} {'月均':>8s} {'年化':>8s} {'胜率':>6s} {'超额':>8s} {'回撤':>8s}")
    for seg, segname in [("ALL", "全样本"), ("OOS", "样本外"), ("IS", "样本内")]:
        for k, nm in [("size", "纯小市值"), ("both", "小市值+反转")]:
            r = combo_res[(seg, k)]
            print(f"{nm:20s} {segname:16s} {r['months']:4d} {r['month_ret']*100:+8.2f}% {r['ann']*100:+8.2f}% {r['win']:5.0f}% {r['excess']*100:+8.2f}% {r['mdd']:7.2f}%")

    print(f"\n总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
