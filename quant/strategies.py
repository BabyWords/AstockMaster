# -*- coding: utf-8 -*-
"""
策略库 —— 在这里定义/修改策略，跑的时候用 scripts/run_backtest.py。

【怎么加一个策略】
1. 用 @register("策略名") 装饰一个函数
2. 函数输入 day（选股日当天的横截面 DataFrame），返回打分 Series（越大越优先）

【day 里可用的列（因子）】
  原始值:  SIZE  REV5  REV20  REV60  MOM20  VOL20  TURN  PB  PE  DIV
           LB  TURN_STD20  MAXUP20  MAXDN20  NEWHIGH20  MA_GAP
           AMT  AMT20  VOL_RATIO  PCT  GAP  TAIL  IS_YANG
  标准化:  z_SIZE  z_REV5  z_REV20  z_REV60  z_MOM20  z_VOL20  z_TURN  z_PB  z_PE  z_DIV
           z_LB  z_TURN_STD20  z_MAXUP20  z_MAXDN20  z_NEWHIGH20  z_MA_GAP
           z_AMT  z_AMT20  z_VOL_RATIO  z_PCT  z_GAP  z_TAIL  z_IS_YANG
  (还有 股票代码/股票名称/收盘价/开盘价/最高价/最低价/成交额/流通市值 等字段)
  含义：SIZE=小市值(越大越小盘)  REVn=反转(跌得越深越大)  MOM=动量  VOL=波动  TURN=换手
        LB=量比(越大越放量)  TURN_STD20=换手率20日波动  MAXUP20=20日最大单日涨幅
        MAXDN20=20日最大单日跌幅(负值)  NEWHIGH20=突破前20日最高价幅度(>0创新高)
        MA_GAP=均线多头发散度  AMT=当日成交额  AMT20=20日均成交额  VOL_RATIO=放量倍数
        PCT=涨跌幅%  GAP=隔夜跳空  TAIL=日内(尾盘/开盘)  IS_YANG=阳线(收>开为1)

【跑】
  python scripts/run_backtest.py 小市值反转
  python scripts/run_backtest.py 小市值反转 -n 5 -hold 20 -price 2
"""
import numpy as np
import pandas as pd

from .engine import register


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
    """小市值 + 20日反转 + 低波动（当前推荐主线）。

    2019-2026 八年逐年回测（持有20天）验证：
      8年总盈利 +21.5万(每年独立10万) vs 纯小市值反转 +12.3万，多赚 9.2 万；
      低波把 2020/2022/2023 三个亏损年全部转正，8年只剩 2026 一年亏损；
      回撤普遍降低（多数年份 -10%~-17% vs 对照 -15%~-27%）。
    注意：低波=熊市/震荡市避险，牛市/抱团年(2021)略跑输，小盘系统性暴跌(2026)同样扛不住。
    """
    return day["z_SIZE"] + day["z_REV20"] - day["z_VOL20"]


@register("等权基准")
def 等权基准(day):
    """全市场等权（随机选股）—— 用来衡量策略的「超额收益」。"""
    return day["SIZE"] * 0.0


# ---------------- 开源策略移植（GitHub 移植） ----------------
# 说明：本地数据仅含 收盘价/复权因子/换手率/量比/PE/PB/股息/流通市值，
#       缺少 成交量/成交额/开盘价/最高最低价，故以下策略对原始开源策略做了"可翻译近似"：
#       依赖"放量/阳线/涨停/成交额"的原始因子被省略或替换，其余方向已对齐原文。

@register("v9小盘反转")
def v9小盘反转(day):
    """移植 nyc1013/a-share-quant-v9 的 8 因子小盘反转（经增量验证的最优近似）。

    原文 8 因子，但用本地数据逐因子增量回测后，只有「20日低成交额」这一量价因子
    有正贡献（+154.5%→+172.9%）；「缩量」「低隔夜跳空」「尾盘」均为负贡献（已剔除）。
    最终：小市值 + 超跌反转 + 约束最大涨幅 + 换手稳定 + 低PB + 缩量(量比低) + 低成交额。
    """
    return (day["z_SIZE"] + day["z_REV20"] - day["z_MAXUP20"]
            - day["z_TURN_STD20"] - day["z_PB"] - day["z_LB"] - day["z_AMT20"])


@register("海龟突破")
def 海龟突破(day):
    """移植 sngyai/Sequoia-X 的 TurtleTrade（20 日新高突破）。

    原文：收盘突破前 20 日最高价 + 成交额过亿 + 阳线防诱多。
    现在用真实最高价算突破幅度（NEWHIGH20>0 即创新高），叠加「成交额大」+「阳线」加分。
    """
    return day["z_NEWHIGH20"] + day["z_AMT"] + day["z_IS_YANG"]


@register("均线多头")
def 均线多头(day):
    """移植 Sequoia-X 的 MaVolume（均线 + 放量突破）。

    原文含放量条件，现在补齐「放量（成交额放大）」因子：均线多头发散 + 放量。
    """
    return day["z_MA_GAP"] + day["z_VOL_RATIO"]


@register("RPS突破")
def rps突破(day):
    """移植 Sequoia-X 的 RpsBreakout（欧奈尔相对强度突破）。

    RPS = 个股涨幅在全市场排名的分位，这里用 20 日动量（已横截面标准化）近似。
    """
    return day["z_MOM20"]


# ---------------- 用户自定义形态策略 ----------------

@register("二次站稳五日线")
def 二次站稳五日线(day):
    """连续跌破所有均线(MA5/10/20/60)后，第二次上穿五日线（收盘价上穿 MA5）的买点。

    事件触发型：当天触发该信号的股票等权买入，未触发返回 NaN 被过滤。
    信号识别在引擎因子层完成（SIG2ST 列，0/1）。
    触发股内部用「小市值 + 反转」做次级排序（仅用于同一天多只触发时挑最超跌小盘者，
    系数 0.001 不影响主排序，主排序仍是"是否触发信号"本身）。
    """
    sig = day["SIG2ST"]
    tie = 0.001 * (day["z_SIZE"].fillna(0) + day["z_REV20"].fillna(0))
    return (sig + tie).where(sig > 0)


# ---------------- 新策略往这里加 ----------------
# 示例：反转 + 低换手
# @register("反转低换手")
# def 反转低换手(day):
#     return day["z_REV20"] - day["z_TURN"]
