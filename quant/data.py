# -*- coding: utf-8 -*-
"""L1 数据层 —— 缓存的读写、脏数据归一、过滤与前复权。
======================================================

职责边界：只管「把 CSV/pkl 变成干净的 DataFrame」，
不碰因子（→ quant.factors）、不碰回测（→ quant.engine）。

依赖方向：只依赖 quant.config（路径），是本包最底层之一。
"""
from __future__ import annotations

import os

import pandas as pd

from .config import CACHE, PKL     # 路径统一在 quant.config 推导（见那里说明）

_NUM_COLS = ["开盘价（元）", "最高价（元）", "最低价（元）", "收盘价（元）", "昨收价（元）",
             "涨跌幅（%）", "成交量（手）", "成交额（万元）", "复权因子", "流通市值（万元）",
             "换手率（%）", "市盈率（TTM）", "市净率", "股息率（TTM）（%）", "量比"]

_DATE, _CODE = "交易日期", "股票代码"


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """把「日期」「代码」两列归一化成 8 位 / 6 位字符串，并丢掉脏行。

    2026-11-05 踩过的坑：源文件里混进一行「交易日期为空」的脏数据，读进来后
    整列被 pandas 当成 float（20261105.0），再和字符串版的新数据 concat，
    drop_duplicates 认为 "20261105" 和 20261105.0 是两行不同记录 —— 于是
    同一天被追加了两遍（那天 11,142 行 = 2×5,571）。

    这段逻辑原来分散在 update_cache._norm / build_recent / 一次性清洗脚本里各写
    一遍，现在收敛到本函数，任何入口读 CSV 后都先过一遍。
    """
    df = df[df[_DATE].notna()].copy()
    df[_DATE] = df[_DATE].astype(str).str.split(".").str[0].str.strip()
    df = df[df[_DATE].str.len() == 8]
    df[_CODE] = df[_CODE].astype(str).str.split(".").str[0].str.zfill(6)
    return df


def read_csv(path, cols=None) -> pd.DataFrame:
    """读原始 CSV（统一 dtype + 数值列转 float + 脏行归一）。"""
    df = pd.read_csv(path, dtype={_CODE: str, _DATE: str},
                     usecols=cols, low_memory=False)
    df = normalize_frame(df)
    for c in _NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _read_csv(path):
    """兼容旧名。"""
    return read_csv(path)


def _save_pkl(df, path=None):
    """原子写 pkl 缓存（写坏了宁可下次重读 CSV）。"""
    path = path or PKL
    tmp = path + ".tmp"
    try:
        df.to_pickle(tmp, protocol=5)
        os.replace(tmp, path)
        return True
    except Exception as e:                     # noqa: BLE001
        print(f"[cache] 写 pkl 失败（不影响本次运行）：{e}")
        try:
            os.path.exists(tmp) and os.remove(tmp)
        except OSError:
            pass
        return False


def load_raw(path=None) -> pd.DataFrame:
    """读全样本缓存。同一份 CSV 会优先命中 .pkl 旁路缓存。

    为什么 pkl 里要把 3 个字符串列存成 category：900 万行的 Python 字符串
    反序列化要 12s，category 只要 0.27s（实测 45 倍），内存也从 2.6GB 降到 1.1GB。
    返回前把「交易日期」转回普通字符串——下游有 `>=` 范围比较，category 不支持。
    """
    path = path or CACHE
    pkl = os.path.splitext(path)[0] + ".pkl"
    if os.path.exists(pkl):
        try:
            if os.path.getmtime(pkl) >= os.path.getmtime(path):
                df = pd.read_pickle(pkl)
                df["交易日期"] = df["交易日期"].astype(str)
                df.attrs["sorted_by_code_date"] = True
                return df
        except Exception as e:                 # noqa: BLE001
            print(f"[cache] pkl 不可用，回退读 CSV：{e}")
    df = read_csv(path)
    # 缓存里就按 (代码, 日期) 排好，preprocess 不用再排一次 909 万行
    df = df.sort_values(["股票代码", "交易日期"], kind="stable")
    df.attrs["sorted_by_code_date"] = True
    for c in ("股票代码", "股票名称", "交易日期"):
        if c in df.columns:
            df[c] = df[c].astype("category")
    _save_pkl(df, pkl)
    df["交易日期"] = df["交易日期"].astype(str)
    return df


_load_raw = load_raw        # 兼容旧名（legacy / 未迁移调用点）


def preprocess(df, cfg):
    """过滤 + 前复权。返回含 close_adj 的干净面板。"""
    already_sorted = bool(df.attrs.get("sorted_by_code_date"))
    # 先按代码筛板块（字符串前缀比正则匹配名称快得多），再剔 ST/退
    df = df[df["股票代码"].str.startswith(("60", "68", "00", "30"))]
    df = df[~df["股票名称"].str.upper().str.contains("ST|退", na=False)]
    df = df.dropna(subset=["收盘价（元）", "流通市值（万元）", "复权因子"])
    if cfg["min_price"] > 0:
        df = df[df["收盘价（元）"] >= cfg["min_price"]]
    if not already_sorted:                     # 缓存已排序，这步通常可以跳过
        df = df.sort_values(["股票代码", "交易日期"], kind="stable")
    # 前复权（以每只股票样本末期为基准）。transform 比 merge 少一次 900 万行 hash join
    bf = df.groupby("股票代码", observed=True)["复权因子"].transform("last")
    df["close_adj"] = df["收盘价（元）"] * df["复权因子"] / bf
    # 开盘/最高/最低也做前复权（有字段才做，否则回退到 close_adj 保证兼容）
    for raw, adj in [("开盘价（元）", "open_adj"), ("最高价（元）", "high_adj"),
                     ("最低价（元）", "low_adj")]:
        if raw in df.columns:
            df[adj] = df[raw] * df["复权因子"] / bf
    for adj in ["open_adj", "high_adj", "low_adj"]:
        if adj not in df.columns:
            df[adj] = df["close_adj"]
    return df
