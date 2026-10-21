# -*- coding: utf-8 -*-
"""
策略库 —— 在这里定义/修改策略，跑的时候用 backtest_engine.py。

【怎么加一个策略】
1. 用 @register("策略名") 装饰一个函数
2. 函数输入 day（选股日当天的横截面 DataFrame），返回打分 Series（越大越优先）

【day 里可用的列（因子）】
  原始值:  SIZE  REV5  REV20  REV60  MOM20  VOL20  TURN  PB  PE  DIV
  标准化:  z_SIZE  z_REV5  z_REV20  z_REV60  z_MOM20  z_VOL20  z_TURN  z_PB  z_PE  z_DIV
  (还有 股票代码/股票名称/收盘价/流通市值 等字段)
  含义：SIZE=小市值(越大越小盘)  REVn=反转(跌得越深越大)  MOM=动量  VOL=波动  TURN=换手

【跑】
  python backtest_engine.py 小市值反转
  python backtest_engine.py 小市值反转 -n 5 -hold 10 -price 2
"""
import numpy as np
import pandas as pd

from backtest_engine import register


# ---------------- 现有策略（已验证） ----------------

@register("小市值反转")
def 小市值反转(day):
    """当前基准策略：小市值 + 20日反转，等权。"""
    return day["z_SIZE"] + day["z_REV20"]


@register("纯小市值")
def 纯小市值(day):
    return day["z_SIZE"]


@register("纯反转")
def 纯反转(day):
    return day["z_REV20"]


@register("小市值反转低波")
def 小市值反转低波(day):
    """示例：在基准上减去波动（偏好低波），之前回测证明会稀释收益，仅作参考。"""
    return day["z_SIZE"] + day["z_REV20"] - day["z_VOL20"]


@register("等权基准")
def 等权基准(day):
    """全市场等权（随机选股）—— 用来衡量策略的「超额收益」。"""
    return day["SIZE"] * 0.0


# ---------------- 新策略往这里加 ----------------
# 示例：反转 + 低换手
# @register("反转低换手")
# def 反转低换手(day):
#     return day["z_REV20"] - day["z_TURN"]
