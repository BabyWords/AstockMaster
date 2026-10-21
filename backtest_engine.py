# -*- coding: utf-8 -*-
"""
通用回测引擎（稳定版，策略无关）
=================================
数据加载 → 过滤 → 前复权 → 因子计算 → 横截面标准化 → 回测执行 → 评估。

【策略接口】策略是一个函数：
    def 策略名(day: pd.DataFrame) -> pd.Series:
        # day: 选股日 t 的横截面，含因子列（原始 + z_ 标准化），见 FACTORS 说明
        # 返回: 与 day 同 index 的打分 Series，值越大越优先买入
        return day["z_SIZE"] + day["z_REV20"]

【口径】t日收盘选股 → t+1收盘买入 → 持有 hold_days 个交易日 → 卖出（延迟买入，避前视）。
【调仓】每 hold_days 个交易日调仓一次（不重叠轮换）。
【成本】每期扣 cost（默认 0.3%），复利滚动。

用法：
  python backtest_engine.py                # 列出所有已注册策略
  python backtest_engine.py 小市值反转      # 跑指定策略（默认配置）
  python backtest_engine.py 小市值反转 -n 5 -hold 10 -price 2
"""
import os, sys, time
import pandas as pd, numpy as np

# 数据缓存路径：可用环境变量 BACKTEST_CACHE 覆盖（便于测试注入小数据 / 更换数据源）。
# 默认指向 data/ 子目录下的全样本缓存（2020~2026，含复权因子）。
CACHE = os.environ.get("BACKTEST_CACHE",
                       "/Volumes/TOSHIBA/炒股/回测/data/daily_full_2020_2026.csv")

# ============================ 默认配置 ============================
DEFAULT_CONFIG = {
    "top_n": 5,           # 每期买入多少只（等权）
    "hold_days": 10,      # 持有多少个交易日
    "cost": 0.003,        # 每期成本（双边）
    "capital": 100000.0,  # 复利模拟本金
    "min_price": 2.0,     # 股价下限：剔除面值退市高危垃圾股（关键修正，勿删）
    "start": "20210101",  # 回测起始日（YYYYMMDD）
    "end": "99991231",    # 回测结束日
}

# ============================ 策略注册表 ============================
STRATEGIES = {}


def register(name):
    """装饰器：把策略函数注册进 STRATEGIES"""
    def deco(fn):
        STRATEGIES[name] = fn
        return fn
    return deco


# ============================ 数据加载与预处理 ============================
def _load_raw():
    df = pd.read_csv(CACHE, dtype={"股票代码": str, "交易日期": str}, low_memory=False)
    for c in ["收盘价（元）", "复权因子", "流通市值（万元）", "换手率（%）",
              "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "量比"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def preprocess(df, cfg):
    """过滤 + 前复权。返回含 close_adj 的干净面板。"""
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
    if cfg["min_price"] > 0:
        df = df[df["收盘价（元）"] >= cfg["min_price"]]
    df = df.sort_values(["股票代码", "交易日期"])
    # 前复权（以每只股票样本末期为基准）
    base = df.groupby("股票代码")["复权因子"].last().rename("bf")
    df = df.merge(base, on="股票代码", how="left")
    df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / df["bf"]
    return df


# ============================ 因子计算 ============================
# 可用因子列（策略函数里直接用，全部只用历史数据，点-in-time 正确）：
#   SIZE   = -log(流通市值万元)        越小市值值越大
#   REV5 / REV20 / REV60 = -(近5/20/60日涨幅)   跌得越深值越大
#   MOM20  = 近20日涨幅（动量，= -REV20）
#   VOL20  = 近20日日收益率标准差（波动率）
#   TURN   = 换手率%  PB=市净率  PE=市盈率TTM  DIV=股息率%
# 每个因子都有对应的 z_ 前缀标准化列（如 z_SIZE、z_REV20）。
def compute_factors(df):
    g = df.groupby("股票代码", sort=False)
    c = df["close_adj"]
    df["ret1"] = g["close_adj"].pct_change(1)
    df["REV5"] = -g["close_adj"].pct_change(5)
    df["REV20"] = -g["close_adj"].pct_change(20)
    df["REV60"] = -g["close_adj"].pct_change(60)
    df["MOM20"] = g["close_adj"].pct_change(20)
    df["VOL20"] = df.groupby("股票代码", sort=False)["ret1"].transform(
        lambda s: s.rolling(20, min_periods=10).std())
    df["SIZE"] = -np.log(df["流通市值（万元）"].clip(lower=1))
    df["TURN"] = df["换手率（%）"]
    df["PB"] = df["市净率"]
    df["PE"] = df["市盈率（TTM）"]
    df["DIV"] = df["股息率（TTM）（%）"]
    return df


def standardize(df):
    """横截面 Z-score 标准化，生成 z_ 前缀列。"""
    factor_cols = ["SIZE", "REV5", "REV20", "REV60", "MOM20", "VOL20",
                   "TURN", "PB", "PE", "DIV"]
    gd = df.groupby("交易日期")
    for f in factor_cols:
        m = gd[f].transform("mean")
        s = gd[f].transform("std").replace(0, np.nan)
        df["z_" + f] = (df[f] - m) / s
    return df


def _add_fwd(df, hold):
    """未来持有收益：t+1收盘买入，t+(hold+1)收盘卖出。"""
    g = df.groupby("股票代码", sort=False)
    df["fwd"] = g["close_adj"].shift(-(hold + 1)) / g["close_adj"].shift(-1) - 1.0
    return df


def build_groups(df, cfg):
    df = df[(df["交易日期"] >= cfg["start"]) & (df["交易日期"] <= cfg["end"])]
    df = _add_fwd(df, cfg["hold_days"])
    keep = ["交易日期", "股票代码", "股票名称", "收盘价（元）", "流通市值（万元）", "fwd",
            "SIZE", "REV5", "REV20", "REV60", "MOM20", "VOL20", "TURN", "PB", "PE", "DIV",
            "z_SIZE", "z_REV5", "z_REV20", "z_REV60", "z_MOM20", "z_VOL20", "z_TURN",
            "z_PB", "z_PE", "z_DIV"]
    groups = {t: g for t, g in df[keep].groupby("交易日期", sort=False)}
    return groups


# ============================ 回测执行 ============================
def run_backtest(strategy, cfg):
    dlist = sorted(cfg["_dlist"])
    hold = cfg["hold_days"]
    n = cfg["top_n"]
    groups = cfg["_groups"]
    idxs = list(range(0, len(dlist) - hold - 1, hold))
    periods = []
    for i in idxs:
        t = dlist[i]
        day = groups[t]
        score = strategy(day)
        day = day.assign(_score=pd.Series(score, index=day.index))
        day = day[day["_score"].notna()]
        if len(day) == 0:
            continue
        top = day.nlargest(n, "_score")
        r = top["fwd"].dropna()
        if len(r) < max(1, n - 2):   # 允许个别停牌缺数据，但至少要有大部分
            continue
        periods.append((t, r.mean(), len(r), n - len(r)))
    return periods


# ============================ 评估 ============================
def _mdd(nav):
    return (nav / nav.cummax() - 1).min() * 100


def evaluate(periods, cfg):
    ret = pd.Series([p[1] for p in periods])
    net = ret - cfg["cost"]
    cap = cfg["capital"]
    for x in ret:
        cap *= 1 + x - cfg["cost"]
    nav = (1 + net).cumprod()
    mdd = _mdd(nav)
    n_years = len(ret) * cfg["hold_days"] / 242.0
    net_cum = (1 + net).prod() - 1
    ann = (1 + net_cum) ** (1 / n_years) - 1 if net_cum > -1 and n_years > 0 else np.nan
    win = (ret > 0).mean() * 100
    nan_cnt = sum(p[3] for p in periods)
    return dict(n=len(ret), net_cum=net_cum * 100, ann=ann * 100, mdd=mdd,
                win=win, cap=cap, nan_cnt=nan_cnt)


def print_report(name, cfg, periods, r):
    print("\n" + "=" * 82)
    print(f"【策略：{name}】 TOP{cfg['top_n']} / 持有{cfg['hold_days']}天 / 成本{cfg['cost']*100:.1f}%")
    print("=" * 82)
    print(f"  调仓期数 {r['n']:>4}   10万→{r['cap']:>12,.0f}   "
          f"累计 {r['net_cum']:>+8.1f}%   年化 {r['ann']:>+6.2f}%")
    print(f"  期胜率 {r['win']:>4.0f}%   最大回撤 {r['mdd']:>7.1f}%   "
          f"停牌/缺数据票数 {r['nan_cnt']}")

    # 分年
    dlist = cfg["_dlist"]
    by_year = {}
    for p in periods:
        y = p[0][:4]
        by_year.setdefault(y, []).append(p[1])
    print("  " + "-" * 60)
    print(f"  {'年份':<6}{'期数':>5}{'收益(扣成本)':>14}{'回撤':>10}{'胜率':>8}")
    for y in sorted(by_year):
        rr = pd.Series(by_year[y])
        net = rr - cfg["cost"]
        c = cfg["capital"]
        for x in rr:
            c *= 1 + x - cfg["cost"]
        m = _mdd((1 + net).cumprod())
        print(f"  {y:<6}{len(rr):>5}{(c/cfg['capital']-1)*100:>+13.1f}%{m:>+9.1f}%{(rr>0).mean()*100:>7.0f}%")
    print()


def load_all(cfg):
    t0 = time.time()
    raw = _load_raw()
    df = preprocess(raw, cfg)
    df = compute_factors(df)
    df = standardize(df)
    groups = build_groups(df, cfg)
    cfg["_groups"] = groups
    cfg["_dlist"] = sorted(groups.keys())
    return time.time() - t0


def run_strategy(name, overrides):
    fn = STRATEGIES[name]
    cfg = {**DEFAULT_CONFIG, **overrides}
    print(f"[准备] 加载数据 + 因子（约20秒）...")
    dt = load_all(cfg)
    print(f"[准备] 完成，{len(cfg['_dlist'])} 个交易日，耗时 {dt:.0f}s")
    periods = run_backtest(fn, cfg)
    r = evaluate(periods, cfg)
    print_report(name, cfg, periods, r)
    return periods, r


# ============================ 命令行参数解析 ============================
def _parse_args(argv):
    overrides = {}
    name = None
    i = 0
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
        elif a == "--start":
            if i + 1 < len(argv):
                overrides["start"] = argv[i + 1]
            i += 2
        elif a.startswith("--start="):
            overrides["start"] = a.split("=", 1)[1]
            i += 1
        else:
            if name is None:
                name = a
            i += 1
    return name, overrides


# 入口在 run_backtest.py（避免 __main__ 双重导入导致注册表错位）
