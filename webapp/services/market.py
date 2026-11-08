# -*- coding: utf-8 -*-
"""实时行情（腾讯公开接口）—— 批量拉取 + 短 TTL 缓存。
========================================================

不走通达信 MCP：那是会话级通道（Bearer token + context 头每会话变化），
webapp 是独立进程，拿不到也不该复用。腾讯行情无需鉴权、支持批量，更适合这里。
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request

RT_URL = "https://qt.gtimg.cn/q="
RT_TTL = float(os.environ.get("RT_TTL", "3"))      # 同只股票 3 秒内复用，避免刷屏打爆上游
_RT_CACHE: dict = {}
_RT_LOCK = threading.Lock()
_RT_MAX = 512                                       # 上限：自选+模拟盘规模远小于此，防泄漏

# urllib 的 opener 构造有开销，且 ProxyHandler({}) 只是「强制直连」的开关，
# 进程内复用同一个即可（原来每次请求都 build 一次）。
_OPENER_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER_PROXY = urllib.request.build_opener()


def rt_prefix(code):
    """代码 -> 腾讯行情前缀（sh/sz/bj）。"""
    c = str(code)
    if c[0] in "69":
        return "sh"
    if c[0] in "023":
        return "sz"
    if c[0] in "48":
        return "bj"
    return "sh"


def opener():
    """默认强制直连（本机代理会把行情请求劫持成 502）；RT_USE_PROXY=1 时走代理。"""
    return _OPENER_PROXY if os.environ.get("RT_USE_PROXY") == "1" else _OPENER_DIRECT


def _f(f, i, digits=2):
    try:
        v = float(f[i])
    except (ValueError, IndexError, TypeError):
        return None
    return round(v, digits)


def parse(payload: str):
    """解析腾讯行情返回的一条（字段顺序见 qt.gtimg.cn 协议）。"""
    f = payload.split("~")
    if len(f) < 50 or not f[2]:
        return None
    price = _f(f, 3)
    prev = _f(f, 4)
    if price is None or prev is None:
        return None
    # 停牌/未开盘时现价为 0，用昨收顶上，避免前端显示 0
    if price <= 0:
        price = prev

    def lvl(base):
        out = []
        for k in range(5):
            p = _f(f, base + k * 2)
            v = _f(f, base + k * 2 + 1, 0)
            if p:
                out.append({"p": p, "v": v or 0})
        return out

    ts = f[30] if len(f) > 30 else ""
    if len(ts) >= 14:
        ts = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"

    return {
        "code": f[2],
        "name": f[1],
        "price": price,
        "prev_close": prev,
        "open": _f(f, 5),
        "high": _f(f, 33),
        "low": _f(f, 34),
        "chg": _f(f, 31),
        "pct": _f(f, 32),
        "volume": _f(f, 36, 0),          # 手
        "amount": _f(f, 37, 0),          # 万元
        "turnover": _f(f, 38),           # %
        "pe": _f(f, 39),
        "amplitude": _f(f, 43),          # %
        "float_cap": _f(f, 44),          # 亿
        "total_cap": _f(f, 45),          # 亿
        "pb": _f(f, 46),
        "limit_up": _f(f, 47),
        "limit_down": _f(f, 48),
        "vol_ratio": _f(f, 49),
        "avg_price": _f(f, 51),
        "time": ts,
        "bids": lvl(9),
        "asks": lvl(19),
    }


def realtime_batch(codes):
    """批量取实时行情，命中缓存的不再请求上游。返回 list（顺序同入参）。"""
    codes = [str(c).split(".")[0].strip() for c in codes if str(c).strip()]
    codes = [c for c in dict.fromkeys(codes) if c.isdigit()][:60]
    if not codes:
        return []

    now = time.time()
    out, need = {}, []
    with _RT_LOCK:
        for c in codes:
            hit = _RT_CACHE.get(c)
            if hit and now - hit[0] < RT_TTL:
                out[c] = hit[1]
            else:
                need.append(c)

    if need:
        url = RT_URL + ",".join(rt_prefix(c) + c for c in need)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://gu.qq.com/",
            })
            raw = opener().open(req, timeout=4).read().decode("gbk", errors="ignore")
        except Exception as e:                      # noqa: BLE001
            print(f"[realtime] 拉取失败：{e}")
            return list(out.values())

        got = {}
        for line in raw.split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            item = parse(line.partition("=")[2].strip().strip('"'))
            if item:
                got[item["code"]] = item
        with _RT_LOCK:
            if len(_RT_CACHE) > _RT_MAX:            # 简单防泄漏：满了就整体清空
                _RT_CACHE.clear()
            for c, item in got.items():
                _RT_CACHE[c] = (now, item)
        out.update(got)

    return [out[c] for c in codes if c in out]
