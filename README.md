# A股小市值反转策略 · 回测项目

这是一个 A 股量化回测与每日选股的项目，核心策略是**「小市值 + 20 日反转」双因子**：
每 10 个交易日调仓一次，收盘后选股 → 次日开盘等权买入 → 持有 10 个交易日 → 到期换仓。

> 完整操作手册见 [`reports/小市值反转策略使用手册.md`](reports/小市值反转策略使用手册.md)

## 目录结构

```
回测/
├── backtest_engine.py    # ★ 回测引擎（稳定，策略无关，别动）
├── strategies.py         # ★ 策略库（加/改策略在这里）
├── run_backtest.py       # ★ 回测入口（唯一入口）
├── select_stocks.py      # ★ 每日选股工具（实盘用）
├── tests/                # ★ 单元测试
│   ├── sample_data.py         # 合成数据构造器（测试专用）
│   ├── test_preprocess.py     # 过滤 + 前复权
│   ├── test_factors.py        # 因子计算 + 标准化
│   ├── test_engine.py         # 回测执行链路
│   ├── test_evaluate.py       # 评估指标
│   └── test_strategies.py     # 策略契约 + 参数解析
├── data/                 # 数据缓存（当前用 daily_full_2020_2026.csv）
├── reports/              # 所有回测报告 + 使用手册（.md）
├── legacy/               # 历史一次性脚本（归档，一般不再用）
├── outputs/              # 回测明细 CSV
└── 选股结果/             # 每日选股输出
```

## 快速开始

运行环境：隔离 venv 的 Python（已装 pandas/numpy）。

```bash
PY=/Users/jason_wu/.workbuddy/binaries/python/envs/default/bin/python
```

### 1. 跑回测

```bash
$PY run_backtest.py                    # 列出所有已注册策略
$PY run_backtest.py 小市值反转          # 跑指定策略（默认 TOP5 / 持有10天 / 股价≥2元）
$PY run_backtest.py 小市值反转 -n 5 -hold 10 -price 2 -cost 0.003
$PY run_backtest.py 小市值反转 --start 20260101   # 只测 2026 年
```

### 2. 每日选股（实盘）

```bash
$PY select_stocks.py              # 用最新数据，选前 5 只
$PY select_stocks.py 20261020     # 指定日期
$PY select_stocks.py -n 10        # 输出前 10 只
```

结果同时保存到 `选股结果/选股_<日期>.csv`。

### 3. 跑单元测试

```bash
cd /Volumes/TOSHIBA/炒股/回测
$PY -m unittest discover -s tests -v
```

测试用**合成数据**，不读真实大缓存，秒级完成，外置硬盘拔掉也能跑。

## 策略接口

一个策略就是一个函数：输入选股日当天的横截面，输出打分（越大越优先买入）。

```python
# 在 strategies.py 里：
@register("反转低换手")              # 起个名字
def 反转低换手(day):
    return day["z_REV20"] - day["z_TURN"]   # 20日反转 + 偏好低换手
```

`day` 里可用的因子（已做横截面 Z-score 标准化，用 `z_` 前缀）：

| 因子 | 含义 |
|---|---|
| `SIZE` | 小市值（越大越盘小） |
| `REV5 / REV20 / REV60` | 反转（跌得越深越大） |
| `MOM20` | 动量（= -REV20） |
| `VOL20` | 波动率 |
| `TURN / PB / PE / DIV` | 换手 / 市净率 / 市盈率 / 股息率 |

## 回测口径（重要）

- **选股**：t 日收盘选股，**t+1 收盘买入**，持有 `hold_days` 天卖出（延迟买入，避免前视偏差）。
- **调仓**：每 `hold_days` 个交易日调仓一次（不重叠轮换）。
- **成本**：每期扣 `cost`（默认 0.3% 双边），复利滚动。
- **过滤**：剔除 ST/退、非沪深代码、股价 < `min_price`（默认 2 元，**关键修正**——之前的高收益是退市垃圾股保壳暴涨造成的假象）。

## 数据

- 当前使用的全样本缓存：`data/daily_full_2020_2026.csv`（含复权因子，2020~2026）。
- 引擎读缓存路径可用环境变量 `BACKTEST_CACHE` 覆盖（默认指向上面文件）。
- 原始日线在 `/Volumes/TOSHIBA/炒股/每日行情/`（按年份分目录，每日一个 CSV）。
- 旧缓存（`daily_full_2022_2026.csv`、`daily_full_2025_2026.csv` 等）已归档在 `data/`，仅作备份。

## 已验证结果（诚实版）

策略真实水平（股价≥2元过滤后，2021-2026 全样本）：

| 指标 | 数值 |
|---|---|
| 累计收益 | +92.5%（约 1.9 倍） |
| 年化 | 约 12% |
| 最大回撤 | 约 -50% |
| 分年 | 4 正 2 负（2022 -18.6%、2026 -5.3% 为亏损年） |

**这是「小盘风格 beta + 薄 alpha」的高波动策略**，不是暴利，过程极颠簸。详见 [`reports/垃圾股污染修正报告.md`](reports/垃圾股污染修正报告.md) 和 [`reports/2021-2026全样本回测报告.md`](reports/2021-2026全样本回测报告.md)。
