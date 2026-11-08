# -*- coding: utf-8 -*-
"""脚本层 —— 运维与命令行入口（薄壳：只做参数、IO、打印，不含业务逻辑）。

这里做一次 sys.path 引导，使两种调用方式都能工作：
    python scripts/update_cache.py            # 直接跑脚本（sys.path[0] = scripts/）
    python -c "from scripts.update_cache import main"   # 当包导入（根目录 shim 用）
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # 回测/scripts
_ROOT = os.path.dirname(_HERE)                              # 回测
for _p in (_HERE, _ROOT):                                   # scripts 自身（_bootstrap）+ 项目根（quant）
    if _p not in sys.path:
        sys.path.insert(0, _p)
