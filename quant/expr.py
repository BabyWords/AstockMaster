# -*- coding: utf-8 -*-
"""L3 公式策略 —— 用因子表达式定义策略，不用写 Python。
=====================================================

表达式就是因子的线性组合，例如：

    z_SIZE + z_REV20 - z_VOL20          小市值 + 反转 + 低波（= 主线策略）
    z_SIZE + z_REV20                     小市值反转
    z_REV20 - z_TURN                     反转 + 低换手
    2*z_SIZE + z_REV20 - 0.5*z_VOL20     可以给因子加权重

允许的语法（白名单校验，`eval` 关闭了 builtins）：
    变量    因子名，原始值或 z_ 前缀标准化值（见 FACTOR_NAMES）
    常量    数字
    运算    + - * / 和括号、一元负号
其它任何写法（函数调用、属性、下标、比较）都会被拒绝。

为什么要白名单：表达式会从网页表单进来并直接 eval，只认列名和四则运算，
就没有任何注入面。解析完缓存编译结果，回测循环里不重复解析。
"""
from __future__ import annotations

import ast
import threading

import numpy as np
import pandas as pd

from . import picker as pk

# 可用的因子：picker.FACTOR_COLS（原始 + 自动生成 z_ 列）+ 几个均线/事件列
_BASE = list(pk.FACTOR_COLS) + ["SIG2ST", "MA5", "MA10", "MA20", "MA60"]
FACTOR_NAMES = _BASE + ["z_" + c for c in _BASE]
_NAME_SET = set(FACTOR_NAMES)

# 给前端显示用的一句话说明（不是全部，够填公式时参考）
FACTOR_DOC = {
    "SIZE": "流通市值（取负对数，越大越小盘）",
    "REV5": "近5日反转（跌得越深越大）",
    "REV20": "近20日反转（跌得越深越大）",
    "REV60": "近60日反转",
    "MOM20": "20日动量（= -REV20）",
    "VOL20": "20日波动率（越大越不稳）",
    "TURN": "换手率%",
    "TURN_STD20": "换手率20日波动",
    "PB": "市净率",
    "PE": "市盈率TTM",
    "DIV": "股息率%",
    "LB": "量比",
    "AMT": "当日成交额（万元）",
    "AMT20": "20日均成交额",
    "VOL_RATIO": "放量倍数",
    "MAXUP20": "20日最大单日涨幅",
    "MAXDN20": "20日最大单日跌幅（负值）",
    "NEWHIGH20": "突破前20日最高价幅度（>0 创新高）",
    "MA_GAP": "均线多头发散度",
    "PCT": "当日涨跌幅%",
    "GAP": "隔夜跳空%",
    "TAIL": "日内位置（收盘相对振幅）",
    "IS_YANG": "阳线（收>开为1）",
    "SIG2ST": "二次站稳五日线事件（0/1）",
    "MA5": "5日均价（元）",
    "MA10": "10日均价（元）",
    "MA20": "20日均价（元）",
    "MA60": "60日均价（元）",
}

# 前端分组的展示顺序（只影响界面，不影响计算）
FACTOR_CAT_ORDER = ["规模", "反转·动量", "量能", "波动", "估值", "形态", "均线", "事件"]

FACTOR_CAT = {
    "SIZE": "规模",
    "REV5": "反转·动量", "REV20": "反转·动量", "REV60": "反转·动量", "MOM20": "反转·动量",
    "TURN": "量能", "LB": "量能", "AMT": "量能", "AMT20": "量能", "VOL_RATIO": "量能",
    "VOL20": "波动", "TURN_STD20": "波动", "MAXUP20": "波动", "MAXDN20": "波动",
    "MA_GAP": "波动",
    "PB": "估值", "PE": "估值", "DIV": "估值",
    "PCT": "形态", "GAP": "形态", "TAIL": "形态", "IS_YANG": "形态",
    "NEWHIGH20": "形态",
    "MA5": "均线", "MA10": "均线", "MA20": "均线", "MA60": "均线",
    "SIG2ST": "事件",
}

_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


class ExprError(ValueError):
    """表达式非法（语法错误 / 用了不认识的因子 / 用了不允许的运算）。"""


def _check_tree(tree):
    """只允许：数字、因子名、四则运算、括号、一元负号。返回用到的因子名。"""
    used = []
    for node in ast.walk(tree):
        # walk 会把运算符节点（Add/Sub…）和 ctx（Load）也吐出来，跳过它们
        if isinstance(node, (ast.operator, ast.unaryop, ast.expr_context)):
            continue
        if isinstance(node, ast.Expression):
            continue
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, _OPS):
                raise ExprError(f"不支持运算 {type(node.op).__name__}，只能用 + - * /")
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.UAdd, ast.USub)):
                raise ExprError("只支持正负号")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ExprError("只允许数字常量")
        elif isinstance(node, ast.Name):
            if node.id not in _NAME_SET:
                raise ExprError(f"未知因子「{node.id}」")
            used.append(node.id)
        else:
            raise ExprError(f"不允许的语法 {type(node).__name__}（只能用因子名、数字、+ - * /）")
    if not used:
        raise ExprError("表达式里至少要有一个因子")
    return sorted(set(used))


def normalize(expr):
    """去掉全角符号和多余空格，前端用户经常直接粘贴中文逗号/全角加号。"""
    s = str(expr or "").strip()
    for a, b in (("＋", "+"), ("－", "-"), ("＊", "*"), ("／", "/"),
                 ("（", "("), ("）", ")"), ("　", " ")):
        s = s.replace(a, b)
    return " ".join(s.split())


_CACHE: dict = {}
_LOCK = threading.Lock()


def compile_expr(expr):
    """表达式 -> 策略函数 fn(day) -> Series。结果按表达式文本缓存。"""
    expr = normalize(expr)
    with _LOCK:
        hit = _CACHE.get(expr)
    if hit is not None:
        return hit

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误：{e.msg}") from None
    used = _check_tree(tree)
    code = compile(tree, "<expr>", "eval")

    def fn(day):
        env = {}
        for n in used:
            if n in day.columns:
                env[n] = day[n]
            else:                       # 缺列就当缺失值，别整段报错
                env[n] = pd.Series(np.nan, index=day.index)
        with np.errstate(all="ignore"):
            out = eval(code, {"__builtins__": {}}, env)   # noqa: S307  白名单已校验
        if np.isscalar(out):
            out = pd.Series(float(out), index=day.index)
        elif not isinstance(out, pd.Series):
            out = pd.Series(np.asarray(out, dtype="float64"), index=day.index)
        return out.astype("float64")

    fn.__name__ = "expr"
    fn.expr = expr
    with _LOCK:
        _CACHE[expr] = fn
    return fn


def check(expr):
    """只校验不执行，给「保存策略」按钮做前置检查。返回 {ok, factors}。"""
    expr = normalize(expr)
    tree = ast.parse(expr, mode="eval") if expr else None
    if tree is None:
        raise ExprError("表达式为空")
    used = _check_tree(tree)
    return {"expr": expr, "factors": used}


# ============================ 策略解析 ============================
def lookup_db(name):
    """从 strategy 表取 kind='expr' 的表达式；没有就返回 None。"""
    try:
        from . import db
    except Exception:                       # noqa: BLE001
        return None
    try:
        with db.session() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select expr from strategy where name = %s and kind = 'expr' "
                    "and enabled and expr is not null", (name,))
                row = cur.fetchone()
        return row[0] if row else None
    except Exception:                       # noqa: BLE001
        return None


def resolve(name):
    """策略名 -> 可调用的打分函数。

    先查代码注册表（strategies.py），再查 strategy 表里的公式策略。
    回测、选股、命令行都走这里，保证「页面上选的策略」和「回测跑的策略」是同一个。
    """
    from .engine import STRATEGIES
    from . import strategies                   # noqa: F401  触发注册
    if name in STRATEGIES:
        return STRATEGIES[name]
    expr = lookup_db(name)
    if expr:
        return compile_expr(expr)
    raise ValueError(f"未找到策略「{name}」，可选：{sorted(STRATEGIES)} 或已保存的公式策略")


def catalog():
    """策略清单（代码注册 + 公式策略），供页面下拉框。"""
    from .engine import STRATEGIES
    from . import strategies                   # noqa: F401
    out = [{"name": n, "kind": "python", "expr": None} for n in STRATEGIES]
    try:
        from . import db
        with db.session() as conn:
            with conn.cursor() as cur:
                cur.execute("select name, expr from strategy where kind='expr' "
                            "and enabled order by sort_order, name")
                for n, e in cur.fetchall():
                    out.append({"name": n, "kind": "expr", "expr": e})
    except Exception:                       # noqa: BLE001
        pass
    return out
