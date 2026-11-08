# -*- coding: utf-8 -*-
"""脚本层公共引导 —— 让 `python scripts/xxx.py` 能找到 quant 包。

为什么需要：直接跑 `python scripts/update_cache.py` 时 sys.path[0] 是 scripts/，
而 quant 包在上一级。这里是**唯一**允许做 sys.path 操作的地方，其余脚本
第一行 `import _bootstrap` 即可。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 回测/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
