#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小市值 + 反转 每日选股工具（含大小盘风格闸门）
==============================================
每天收盘后（数据更新到硬盘后）运行，先做「大小盘风格判断」，
风格不符合时直接拦截、不选股；符合时再用「小市值+反转」双因子
给全市场打分，输出前 N 只候选股。

用法：
  python select_stocks.py              # 用最新数据，选前 5 只
  python select_stocks.py 20261020     # 指定日期
  python select_stocks.py -n 20        # 输出前 20 只
  python select_stocks.py --gate      # 开启风格闸门拦截（默认关闭，仅打印参考不拦截）

依赖：pandas / numpy（已装在隔离 venv 中）
运行：/Users/jason_wu/.workbuddy/binaries/python/envs/default/bin/python select_stocks.py
"""
import os, sys, re
import pandas as pd, numpy as np

DATA = "/Volumes/TOSHIBA/炒股"
DAILY = os.path.join(DATA, "每日行情")
OUT = os.path.join(DATA, "回测", "选股结果")

# ---------- 选股参数 ----------
TOP_N = 5           # 默认输出前 5 只（回测结论：选3只崩、选5只最优、选10只收益反而更低）
LOOKBACK = 20        # 反转因子回看 20 个交易日
MIN_AMT = 5000       # 成交额下限（万元）= 5000 万
MAX_PCT = 9.5        # 剔除当日涨跌幅 >= 9.5%（接近涨停，不追高）
MIN_PRICE = 2.0      # 股价下限（元）：剔除 1~2 元"面值退市高危股"。
                     # 2026-10 回测发现：之前策略的高收益几乎全来自这类垃圾股的保壳暴涨
                     # （名家汇/景峰医药/京蓝科技等），实盘吃不到且退市风险极高，必须剔除。

# ---------- 大小盘风格闸门参数（想调就在这里改） ----------
ENABLE_STYLE_GATE = False  # 风格闸门总开关：默认【关闭】。
                           # 三年回测(2024-2026)证明"择时闸门整体负贡献"——无论用哪种规则
                           # (小盘跑输大盘就停 / 小盘绝对暴跌才停)，三年复利都低于"无闸门"的
                           # 3.32 倍。正确风控靠"仓位30~50% + 等权10只 + -8%止损"，不是择时。
                           # 默认关闭=只打印风格参考、不拦截选股；想强制拦截才改 True 或加 --gate。
STYLE_LOOKBACK = 20        # 风格判断回看交易日数（约 1 个月）
STYLE_EXCESS_MIN = 0.0     # 放行线：20日「小盘-大盘」超额 >= 该值才放行（仅在开启闸门时生效）
SMALL_PCT = 0.5            # 小盘组 = 流通市值最小的 50%
LARGE_PCT = 0.2            # 大盘组 = 流通市值最大的 20%


def collect_dates():
    """扫描所有日线文件，返回按日期升序的 [(日期, 路径), ...]"""
    files = []
    for y in os.listdir(DAILY):
        yd = os.path.join(DAILY, y)
        if not os.path.isdir(yd):
            continue
        for f in os.listdir(yd):
            if f.startswith("._") or not f.endswith(".csv"):
                continue
            m = re.match(r"(\d{8})", f)
            if m:
                files.append((m.group(1), os.path.join(yd, f)))
    files.sort()
    return files


def load_day_style(path):
    """风格判断专用：只读轻量字段（流通市值 + 涨跌幅）"""
    cols = ["股票代码", "股票名称", "流通市值（万元）", "涨跌幅（%）"]
    df = pd.read_csv(path, usecols=cols, dtype={"股票代码": str}, encoding="utf-8-sig")
    for c in ["流通市值（万元）", "涨跌幅（%）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_day(path):
    cols = ["股票代码", "股票名称", "收盘价（元）", "复权因子",
            "流通市值（万元）", "涨跌幅（%）", "成交额（万元）", "换手率（%）"]
    df = pd.read_csv(path, usecols=cols, dtype={"股票代码": str}, encoding="utf-8-sig")
    for c in ["收盘价（元）", "复权因子", "流通市值（万元）",
              "涨跌幅（%）", "成交额（万元）", "换手率（%）"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def style_gate(files, idx):
    """
    大小盘风格判断：
    用本地个股数据自建「小盘指数 / 大盘指数」近 STYLE_LOOKBACK 交易日累计收益，
    返回 (超额百分点, 详情dict)。
    """
    small_daily, large_daily = [], []
    start = idx - STYLE_LOOKBACK
    for j in range(start, idx + 1):
        df = load_day_style(files[j][1])
        df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
        df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
        df = df.dropna(subset=["流通市值（万元）", "涨跌幅（%）"])
        df = df[df["流通市值（万元）"] > 0]
        if len(df) < 100:
            continue
        df = df.sort_values("流通市值（万元）")
        n = len(df)
        n_large = max(1, int(n * LARGE_PCT))
        n_small = max(1, int(n * SMALL_PCT))
        large = df.tail(n_large)   # 市值最大前 LARGE_PCT
        small = df.head(n_small)   # 市值最小前 SMALL_PCT
        large_daily.append(large["涨跌幅（%）"].mean())
        small_daily.append(small["涨跌幅（%）"].mean())

    if not small_daily:
        return None, None
    small_cum = (np.prod([1 + r / 100 for r in small_daily]) - 1) * 100
    large_cum = (np.prod([1 + r / 100 for r in large_daily]) - 1) * 100
    excess = small_cum - large_cum
    info = {
        "small_cum": small_cum, "large_cum": large_cum,
        "excess": excess, "days": len(small_daily)
    }
    return excess, info


def main():
    target = None
    n = TOP_N
    force_gate = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "-n" and i + 1 < len(args):
            n = int(args[i + 1]); i += 2
        elif args[i] == "--gate":
            force_gate = True; i += 1
        elif re.match(r"^\d{8}$", args[i]):
            target = args[i]; i += 1
        else:
            i += 1

    files = collect_dates()
    if not files:
        print("❌ 未找到任何日线文件，请确认硬盘已挂载：", DAILY)
        sys.exit(1)
    dates = [d for d, _ in files]
    latest = dates[-1]

    if target:
        if target not in dates:
            print(f"❌ 指定日期 {target} 不在数据中。最新可用日期：{latest}")
            sys.exit(1)
        cur = target
    else:
        cur = latest

    idx = dates.index(cur)
    if idx < LOOKBACK:
        print(f"❌ 日期 {cur} 往前不足 {LOOKBACK} 个交易日，无法算反转因子")
        sys.exit(1)

    # ============ 第 0 步：大小盘风格参考（默认不拦截，仅展示） ============
    excess, info = style_gate(files, idx)
    if excess is not None:
        print("=" * 78)
        print(f"【大小盘风格参考】近 {info['days']} 个交易日")
        print(f"  小盘组(市值最小{int(SMALL_PCT*100)}%) 累计: {info['small_cum']:+.2f}%")
        print(f"  大盘组(市值最大{int(LARGE_PCT*100)}%) 累计: {info['large_cum']:+.2f}%")
        print(f"  → 小盘超额: {info['excess']:+.2f}%")
        if ENABLE_STYLE_GATE or force_gate:
            if excess >= STYLE_EXCESS_MIN:
                print("✅ 风格闸门已开启且放行选股。")
            else:
                print("❌ 风格闸门已开启且触发，本轮【暂停，不选股】。")
                sys.exit(0)
        else:
            print("ℹ️ 风格闸门默认关闭（回测证明择时负贡献），以上仅作参考，不拦截选股。")
        print("=" * 78)

    prev_date = dates[idx - LOOKBACK]

    # 读目标日 + 20 日前
    cur_df = load_day(files[idx][1])
    prev_df = load_day(dict(files)[prev_date])

    # 合并：20 日前收盘价、复权因子
    prev_df = prev_df[["股票代码", "收盘价（元）", "复权因子"]].rename(
        columns={"收盘价（元）": "收盘价_prev", "复权因子": "因子_prev"})
    df = cur_df.merge(prev_df, on="股票代码", how="left")

    # 过滤
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df.dropna(subset=["流通市值（万元）", "收盘价（元）", "复权因子",
                           "收盘价_prev", "因子_prev"])

    # 反转因子：近20日涨跌幅（用复权价算比例，消除除权跳空）
    df["rev_pct"] = (df["收盘价（元）"] * df["复权因子"]) / \
                    (df["收盘价_prev"] * df["因子_prev"]) - 1.0
    df["REV"] = -df["rev_pct"] * 100.0          # 跌得越深，REV 越大
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))

    # 可交易性过滤
    df = df[df["成交额（万元）"] >= MIN_AMT]          # 流动性
    df = df[df["涨跌幅（%）"] < MAX_PCT]              # 不追高/不买涨停
    df = df[df["收盘价（元）"] >= MIN_PRICE]          # 剔除面值退市高危低价股（关键修正）

    # 横截面 Z-score
    for f in ["SIZE", "REV"]:
        m, s = df[f].mean(), df[f].std()
        df["Z_" + f] = (df[f] - m) / s if s > 0 else 0.0
    df["score"] = df["Z_SIZE"] + df["Z_REV"]

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    pool = len(df)
    top = df.head(n)

    # 输出
    print("=" * 78)
    print(f"小市值+反转 选股结果 · 数据日期 {cur}（反转回看 {LOOKBACK} 日）")
    print(f"候选池 {pool} 只（已剔 ST/退、涨停、成交额<5000万、股价<{MIN_PRICE}元、次新/停牌）")
    print("=" * 78)
    print(f"{'排名':<4}{'代码':<8}{'名称':<10}{'得分':>7}{'涨跌幅%':>8}"
          f"{'20日涨幅%':>9}{'流通市值亿':>10}{'换手%':>7}{'成交额亿':>9}")
    print("-" * 78)
    for r in range(len(top)):
        row = top.iloc[r]
        print(f"{r+1:<4}{row['股票代码']:<8}{row['股票名称']:<10}{row['score']:>7.2f}"
              f"{row['涨跌幅（%）']:>8.2f}{row['rev_pct']*100:>9.2f}"
              f"{row['流通市值（万元）']/10000:>10.1f}{row['换手率（%）']:>7.2f}"
              f"{row['成交额（万元）']/10000:>9.2f}")

    # 保存
    os.makedirs(OUT, exist_ok=True)
    out_csv = os.path.join(OUT, f"选股_{cur}.csv")
    save_cols = {"股票代码": "股票代码", "股票名称": "股票名称", "score": "综合得分",
                 "收盘价（元）": "收盘价", "涨跌幅（%）": "涨跌幅%",
                 "rev_pct": "20日涨幅", "流通市值（万元）": "流通市值万",
                 "换手率（%）": "换手率%", "成交额（万元）": "成交额万"}
    top.rename(columns=save_cols)[list(save_cols.values())].to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("-" * 78)
    print(f"已保存完整候选池前 {n} 只 → {out_csv}")
    print("\n提醒：本结果为收盘后选股，建议次日开盘买入、持有约 10 个交易日卖出，单票 -8% 止损。")


if __name__ == "__main__":
    main()
