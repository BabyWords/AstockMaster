# -*- coding: utf-8 -*-
"""
「一夜持股（尾盘追强原版）」公式回测（日线 + 5分钟分时）
================================================================
策略：T 日 14:30 用公式选股并买入，T+1 日 10:00 卖出（隔夜）
数据：2025-2026，每日行情 + 分钟级行情(5min)
数据源：/Volumes/TOSHIBA/炒股（余哈哈的数据仓库）

公式（严格复刻通达信原式）：
    PCT:=ZF>=3 AND ZF<=5;                 # 当日涨幅 3~5%
    ZHAN:=EXIST(C>=REF(C,1)*1.098,30);    # 近30日有涨停(涨>=9.8%)
    LIANG:=V>MA(V,5);                     # 今日量 > 5日均量
    VOLUP5:=MA(V,5)>=REF(MA(V,5),1);      # 5日均量在放大
    UP3:=C>=REF(C,3);                     # 收盘 >= 3日前收盘
    DUP:=MA5>MA10 AND MA10>MA20;          # 均线多头排列
    T10UP:=MA10>=REF(MA10,1);             # 10日线向上

14:30 时点取值口径：
    C = T日14:30 的5min价(前复权)
    V = T日截至14:30累计量(股)
    MA5 = (前4日收盘 + C)/5；MA10 = (前9日收盘 + C)/10；MA20 = (前19日收盘 + C)/20
    REF(MA10,1) = 截至昨日的10日均线(全天收盘口径)
    MA(V,5) = (前4日量 + V)/5；REF(MA(V,5),1) = 截至昨日的5日均量(全天量口径)
价格统一前复权 = 原始价 × 复权因子 / 每股最新日复权因子
================================================================
"""
import os
import time
import json
import ssl
import urllib.request
import pandas as pd
import numpy as np

OUT = "/Volumes/TOSHIBA/炒股/回测"
SNAP_CACHE = os.path.join(OUT, "snapshots_5min_2025_2026.csv")
DAILY_CACHE = os.path.join(OUT, "daily_2025_2026.csv")
SIGNAL_OUT = os.path.join(OUT, "backtest_overnight_signals.csv")


def load_index():
    """上证指数日线，返回 {date: ma20} 和 {date: close}"""
    try:
        ctx = ssl.create_default_context()
        url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_=/"
               "CN_MarketDataService.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=500")
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn'})
        txt = urllib.request.urlopen(req, timeout=20, context=ctx).read().decode('utf-8', 'ignore')
        i = txt.find('[')
        j = txt.rfind(']')
        idx = pd.DataFrame(json.loads(txt[i:j + 1])).rename(columns={'day': 'date'})
        idx['close'] = pd.to_numeric(idx['close'], errors='coerce')
        idx['ma20'] = idx['close'].rolling(20).mean()
        idx['date'] = idx['date'].str.replace('-', '')  # 统一成 YYYYMMDD 对齐信号日期
        return dict(zip(idx['date'], idx['ma20'])), dict(zip(idx['date'], idx['close']))
    except Exception as e:
        print(f"[指数] 获取失败: {e}", flush=True)
        return {}, {}


def calc_group(dd):
    """对单只股票向量化计算信号"""
    dd = dd.sort_values("交易日期").reset_index(drop=True)
    close = dd["close_adj"].astype(float).reset_index(drop=True)
    open_ = dd["open_adj"].astype(float).reset_index(drop=True)
    vol = dd["vol_share"].astype(float).reset_index(drop=True)
    c1430 = dd["c1430_adj"].astype(float).reset_index(drop=True)
    c1000 = dd["c1000_adj"].astype(float).reset_index(drop=True)
    v1430 = dd["v1430"].astype(float).reset_index(drop=True)

    # ---- 均线（14:30口径：前 N-1 日收盘 + 今日14:30价） ----
    ma5 = (close.shift(1).rolling(4).sum() + c1430) / 5.0
    ma10 = (close.shift(1).rolling(9).sum() + c1430) / 10.0
    ma20 = (close.shift(1).rolling(19).sum() + c1430) / 20.0
    ma10_prev = close.rolling(10).mean().shift(1)   # 昨日10日线(全天口径)

    # ---- 量 ----
    ma5v_today = (vol.shift(1).rolling(4).sum() + v1430) / 5.0
    ma5v_yesterday = vol.rolling(5).mean().shift(1)

    # ---- 涨幅 ----
    zf = (c1430 - close.shift(1)) / close.shift(1) * 100.0
    pct = (zf >= 3) & (zf <= 5)

    # ---- 涨停基因：近30日(不含今天，避免未来函数)有涨>=9.8% ----
    limit_up = close >= close.shift(1) * 1.098
    zhan = limit_up.rolling(29, min_periods=1).sum().shift(1) > 0

    liang = v1430 > ma5v_today
    volup5 = ma5v_today >= ma5v_yesterday
    up3 = c1430 >= close.shift(3)
    dup = (ma5 > ma10) & (ma10 > ma20)
    t10up = ma10 >= ma10_prev

    sig = pct & zhan & liang & volup5 & up3 & dup & t10up

    # ---- 收益：T日14:30买，T+1日10:00卖 ----
    ret = c1000.shift(-1) / c1430 - 1.0
    # 补充卖出时点：次日开盘/收盘(前复权)
    ret_open = open_.shift(-1) / c1430 - 1.0
    ret_close = close.shift(-1) / c1430 - 1.0

    out = dd[["股票代码", "股票名称", "交易日期"]].copy()
    out["buy"] = c1430
    out["sell"] = c1000.shift(-1)
    out["ret"] = ret
    out["ret_open"] = ret_open
    out["ret_close"] = ret_close
    out["sig"] = sig
    return out[out["sig"] & out["ret"].notna()]


def main():
    t0 = time.time()
    snap = pd.read_csv(SNAP_CACHE, dtype={"code": str, "date": str})
    daily = pd.read_csv(DAILY_CACHE, dtype={"股票代码": str, "交易日期": str})
    print(f"[读取] 快照 {len(snap)} 行, 日线 {len(daily)} 行", flush=True)

    # 过滤 ST/退/北交所
    daily = daily[~daily["股票名称"].str.upper().str.contains("ST|退", na=False)]
    daily = daily[daily["股票代码"].str.startswith(("60", "68", "00", "30"))]
    for c in ["开盘价（元）", "收盘价（元）", "成交量（手）", "复权因子"]:
        daily[c] = pd.to_numeric(daily[c], errors="coerce")
    daily = daily.dropna(subset=["收盘价（元）"])
    daily["vol_share"] = daily["成交量（手）"] * 100.0

    # 前复权：日线
    daily = daily.sort_values(["股票代码", "交易日期"])
    base = daily.groupby("股票代码")["复权因子"].last().rename("base_factor")
    daily = daily.merge(base, on="股票代码", how="left")
    daily["adj"] = daily["复权因子"] / daily["base_factor"]
    daily["close_adj"] = daily["收盘价（元）"] * daily["adj"]
    daily["open_adj"] = daily["开盘价（元）"] * daily["adj"]

    # 前复权：快照
    snap = snap.merge(
        daily[["股票代码", "交易日期", "adj"]].rename(
            columns={"股票代码": "code", "交易日期": "date"}),
        on=["code", "date"], how="left")
    snap["c1430_adj"] = snap["c1430"] * snap["adj"]
    snap["c1000_adj"] = snap["c1000"] * snap["adj"]

    # 快照并入日线
    snap_cols = snap[["code", "date", "c1430_adj", "c1000_adj", "v1430"]].rename(
        columns={"code": "股票代码", "date": "交易日期"})
    daily = daily.merge(snap_cols, on=["股票代码", "交易日期"], how="left")
    print("[合并] 完成", flush=True)

    # 向量化计算
    print("[回测] 计算信号...", flush=True)
    frames = [calc_group(g) for _, g in daily.groupby("股票代码", sort=False)]
    res = pd.concat(frames, ignore_index=True)
    print(f"[回测] 信号数 {len(res)}", flush=True)

    if len(res) == 0:
        print("零信号，结束", flush=True)
        return

    res.to_csv(SIGNAL_OUT, index=False)

    # ---- 统计 ----
    ret = res["ret"]
    wr = (ret > 0).mean() * 100
    avg = ret.mean() * 100
    med = ret.median() * 100
    pos = ret[ret > 0]
    neg = ret[ret < 0]
    pf = pos.sum() / (-neg.sum()) if len(neg) and neg.sum() < 0 else float("inf")

    print("\n========== 回测结果（14:30买 / 次日10:00卖）==========")
    print(f"信号数: {len(res)}")
    print(f"胜率(毛): {wr:.2f}%")
    print(f"平均收益(毛): {avg:+.3f}%")
    print(f"中位收益(毛): {med:+.3f}%")
    print(f"盈亏比 PF: {pf:.3f}")
    print(f"平均盈利: {pos.mean()*100:+.3f}%  平均亏损: {neg.mean()*100:+.3f}%")
    print(f"最大单笔: {ret.max()*100:+.3f}%  最差单笔: {ret.min()*100:+.3f}%")
    for cost, cn in [(0.0015, "0.15%"), (0.003, "0.30%")]:
        net = ret - cost
        print(f"  成本{cn} -> 净胜率{(net>0).mean()*100:.2f}%  净平均{net.mean()*100:+.3f}%")

    # 卖出时点对比
    print("\n[卖出时点对比]")
    for col, nm in [("ret", "10:00卖"), ("ret_open", "次日开盘卖"), ("ret_close", "次日收盘卖")]:
        r = res[col].dropna() * 100
        print(f"  {nm:10s} 胜率{(r>0).mean()*100:5.1f}%  平均{r.mean():+.3f}%")

    # 强市/弱市分组
    ma20_map, close_map = load_index()
    if ma20_map:
        def _regime(d):
            if d in ma20_map and d in close_map:
                m, c = ma20_map[d], close_map[d]
                if pd.notna(m) and pd.notna(c):
                    return "弱市" if c < m else "强市"
            return "未知"
        res["regime"] = res["交易日期"].map(_regime)
        print("\n[强/弱市分组]")
        for rg, nm in [("强市", "强市(上证>=MA20)"), ("弱市", "弱市(上证<MA20)"), ("未知", "未知(无指数数据)")]:
            sub = res[res["regime"] == rg]
            if len(sub):
                r = sub["ret"] * 100
                print(f"  {nm:18s} n={len(sub):5d}  胜率{(r>0).mean()*100:5.1f}%  平均{r.mean():+.3f}%")

    # 按月
    res["ym"] = res["交易日期"].str[:6]
    print("\n按月:")
    g2 = res.groupby("ym").agg(n=("ret", "size"),
                               胜率=("ret", lambda x: (x > 0).mean() * 100),
                               均收益=("ret", lambda x: x.mean() * 100))
    print(g2.round(2).to_string())

    print(f"\n总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
