# -*- coding: utf-8 -*-
"""webapp 服务层 —— 领域逻辑都在这里，路由层只做参数校验与协议转换。

    store.py    单股分片读取（LRU）、重采样、序列化、搜索
    market.py   腾讯实时行情（批量 + TTL 缓存）
    chart.py    K 线 payload（指标计算 + 盘中实时 bar 合并 + ETag）
    minute.py   分时 payload（本地分钟 CSV 优先，盘中回落实时分时）
    paper.py    模拟盘（表结构、逐日净值、持仓明细）
    jobs.py     回测子进程任务管理（同时只允许一个）
"""
