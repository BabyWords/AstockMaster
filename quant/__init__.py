# -*- coding: utf-8 -*-
"""quant —— A股量化核心库
==========================

依赖方向严格单向（下面的序号就是 import 顺序），不允许反向或循环：

    L0  quant.config      配置：全项目唯一的路径来源（零依赖）
    L1  quant.data        数据：CSV/pkl 读写、脏数据归一、过滤、前复权
    L1  quant.indicators  指标：MA/MACD/KDJ… 纯函数（只依赖 pandas/numpy）
    L2  quant.factors     因子：原始因子、事件信号（← picker.FACTOR_COLS）
    L2  quant.picker      选股：过滤 → 标准化 → 打分 → 前 N（回测/实盘共用同一份）
    L3  quant.engine      执行：策略注册表、调仓循环、净值/分年评估
    L3  quant.strategies  策略库：@register 注册到 engine.STRATEGIES
    L3  quant.expr        公式策略：因子表达式 → 策略函数（白名单 AST）
    L3  quant.selection   选股管线：面板 → pick → 名单 → CSV/DB（CLI 与网页共用）
    L4  quant.report      呈现：终端报告（只有 CLI 用）
    L4  quant.db          Postgres 访问（**可选**依赖；库/驱动缺失时为 None）

`import quant` 会顺带完成策略注册（等价于老代码 `import strategies`），
所以业务侧只要 `from quant import picker, engine, expr` 就够了。
"""
from . import config, data, indicators, factors, picker, engine     # noqa: F401
from . import strategies                                            # noqa: F401  触发注册
from . import expr, selection, report                               # noqa: F401

try:                                                                # 数据库是可选依赖
    from . import db                                                # noqa: F401
except Exception as _e:                                             # noqa: BLE001
    db = None
    _db_error = str(_e)

__all__ = ["config", "data", "indicators", "factors", "picker",
           "engine", "strategies", "expr", "selection", "report", "db"]
