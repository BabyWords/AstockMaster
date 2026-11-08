# -*- coding: utf-8 -*-
"""兼容入口 —— 实现在 scripts/update_cache.py。

保留这个文件是因为外部有两条硬编码的绝对路径调用它，路径不能变：
    · launchd  com.jason.stockcache.update（每 300s）
    · 百度网盘拉取脚本 baidu-pull/fetch.py（拉完日线后串行调用）
新代码请直接 `python scripts/update_cache.py`。
"""
import sys

from scripts.update_cache import main

if __name__ == "__main__":
    sys.exit(main())
