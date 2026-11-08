# -*- coding: utf-8 -*-
"""路由层 —— 只做 HTTP：参数校验、状态码、序列化。业务在 services/。

    kline      /api/kline /api/search /api/meta
    minute     /api/minute
    realtime   /api/realtime /api/quotes
    watchlist  /api/watchlist（库主存 + JSON 降级）
    assistant  /api/assistant/*（策略目录、因子表、选股、子进程回测）
    trades     /api/trades（K 线买卖点标注）
    paper      /api/paper/*（模拟盘：逐日净值 + 到期跟踪）
"""
