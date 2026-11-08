# A股量化系统 · 回测 + 选股 + 网页终端

A 股量化项目，主线策略是**「小市值 + 20 日反转 − 低波」**：每 20 个交易日调仓，
收盘后选股 → 次日收盘买入 → 持有 20 个交易日 → 到期换仓。

三件事共用同一份代码：
1. **回测**（验证策略在过去是否有效）
2. **每日选股**（今天买哪几只，落 `signal` 表）
3. **网页终端**（K线 + 指标 + 自选 + 助手：选股/回测/模拟盘 + 买卖点标注）

> 操作手册：[`docs/reports/小市值反转策略使用手册.md`](docs/reports/小市值反转策略使用手册.md)

---

## 目录结构

按「**核心库 → 脚本入口 → Web 应用**」三层组织，依赖严格单向，不许反向 import。

```
回测/
├── quant/                    ★ 核心库（纯 Python，不依赖 web、不打印、不解析命令行）
│   ├── config.py             L0 配置：全项目唯一的路径来源（env 可覆盖）
│   ├── data.py               L1 数据：CSV/pkl 读写、脏数据归一、过滤、前复权
│   ├── indicators.py         L1 指标：MA/MACD/KDJ/RSI/BOLL… 通达信口径纯函数
│   ├── factors.py            L2 因子：原始因子、事件信号 SIG2ST
│   ├── picker.py             L2 选股：过滤→标准化→打分→前N（回测与实盘唯一实现）
│   ├── engine.py             L3 执行：策略注册表、调仓循环、净值/分年评估
│   ├── strategies.py         L3 策略库：@register 注册（加策略改这里）
│   ├── expr.py               L3 公式策略：因子表达式 → 策略函数（白名单 AST）
│   ├── selection.py          L3 选股管线：面板 → pick → 名单 → CSV/DB
│   ├── report.py             L4 呈现：终端报告（只有 CLI 用）
│   └── db.py                 L4 Postgres 访问（可选依赖，库挂了不影响回测）
│
├── scripts/                  ★ 运维/命令行入口（薄壳：参数、IO、打印）
│   ├── update_cache.py       每日增量更新（launchd / fetch.py 调它）
│   ├── build_cache.py        全量重建缓存（首次/大改）
│   ├── build_recent.py       切最近 140 交易日选股面板
│   ├── select_stocks.py      每日选股（写 signal 表 + CSV）
│   ├── run_backtest.py       命令行回测
│   ├── backtest_job.py       单次回测子进程（网页「助手」调用）
│   ├── backfill_signals.py   回填 signal 真实收益（样本外验证闭环）
│   └── sync_stock_meta.py    灌 stock 主表
│
├── webapp/                   ★ 网页系统（FastAPI + ECharts）
│   ├── app.py                组装层：建 app、挂路由
│   ├── config.py             路径 + sys.path 引导 + 股票索引 + 数据库句柄
│   ├── services/             领域逻辑（路由不含算法）
│   │   ├── store.py          单股分片读取(LRU)/重采样/序列化/搜索
│   │   ├── market.py         腾讯实时行情（批量 + TTL 缓存）
│   │   ├── chart.py          K线 payload（指标 + 盘中实时 bar + ETag）
│   │   ├── minute.py         分时 payload（本地分钟 CSV / 盘中实时）
│   │   ├── paper.py          模拟盘（逐日净值、持仓、到期）
│   │   ├── catalog.py        策略目录、因子表、公式策略保存
│   │   └── jobs.py           回测子进程任务管理（TTL 回收）
│   ├── api/                  路由层（只做参数校验 + 协议转换，共 ~430 行）
│   ├── static/               前端（ECharts、双主题、移动端适配）
│   └── build_store.py        预构建 data_store/ 分片
│
├── tests/                    ★ 单元测试（合成数据，拔盘可跑）
├── data/                     数据缓存（daily_full_2019_2026.csv + .pkl 旁路）
├── 选股结果/                 每日选股输出 CSV
├── docs/reports/             回测报告 + 使用手册（.md）
├── legacy/                   历史一次性脚本（归档，不再维护）
│
├── backtest_engine.py        兼容 façade（re-export quant，旧引用不用改）
├── update_cache.py           兼容入口 → scripts/update_cache.py（launchd 的硬编码路径）
├── run_backtest.py           兼容入口 → scripts/run_backtest.py
└── select_stocks.py          兼容入口 → scripts/select_stocks.py
```

### 分层规则（改代码前先看这一节）

| 规则 | 说明 |
|---|---|
| **依赖单向** | `api → services → quant → config`。`quant` 里**不许** import webapp/scripts 的任何东西 |
| **路径只在 config** | 任何 `/Volumes/TOSHIBA/...` 字面量只允许出现在 `quant/config.py` |
| **选股只有一份** | 所有「今天买哪几只」的逻辑都在 `picker.pick()`，回测/CLI/网页都调它 |
| **引擎不碰 IO** | `quant/engine.py` 不打印、不读命令行、不写库；呈现放 `report.py`，落库放 `db.py` |
| **脚本是薄壳** | `scripts/*` 只做参数解析 + 打印 + 调用；业务逻辑必须下沉到 `quant` |
| **路由是薄壳** | `webapp/api/*` 只做参数校验 + HTTP 语义；业务在 `services/*` |
| **私有函数不跨模块** | 跨模块只用公开名（`load_raw` 而不是 `_load_raw`），旧名另留兼容别名 |

---

## 快速开始

```bash
PY=/Users/jason_wu/.workbuddy/binaries/python/envs/default/bin/python
cd /Volumes/TOSHIBA/炒股/回测
```

### 跑回测

```bash
$PY scripts/run_backtest.py                       # 列出所有已注册策略
$PY scripts/run_backtest.py 小市值反转低波          # 默认 TOP5 / 持有20天 / 实盘口径
$PY scripts/run_backtest.py 小市值反转 -n 5 -hold 20 -price 2 -cost 0.003
$PY scripts/run_backtest.py 小市值反转 --start 20260101
$PY scripts/run_backtest.py 小市值反转 --no-liq     # 关流动性门槛（旧口径，仅对比用）
```

旧的 `$PY run_backtest.py` 仍然可用（兼容 shim）。

### 每日选股

```bash
$PY scripts/select_stocks.py                    # 最新交易日，前 5 只，写库
$PY scripts/select_stocks.py -d 20261106        # 指定日期
$PY scripts/select_stocks.py -s 纯小市值 -n 10
$PY scripts/select_stocks.py --no-db            # 只打印不写库
```

结果存 `选股结果/选股_<日期>.csv` + `signal` 表。

### 更新数据

```bash
$PY scripts/update_cache.py      # 增量（幂等，可反复跑；退出码 2 = 有更新）
$PY scripts/build_cache.py       # 全量重建（首次/源数据大改）
$PY scripts/build_recent.py      # 只重切选股面板
$PY webapp/build_store.py        # 只重刷网页分片
```

`scripts/update_cache.py` 成功后会自动串跑：重建选股面板 → 写同步日志 →
当日选股 → 回填历史信号收益 → 重建 pkl 旁路。

### 网页

```bash
cd webapp && ./start.sh          # 只绑局域网 IP（默认），HOST=/PORT= 可覆盖
```

### 测试

```bash
$PY -m unittest discover -s tests -v     # 50 个用例，合成数据，秒级
```

---

## 策略接口

一个策略就是一个函数：输入选股日当天的横截面，输出打分（越大越优先）。

```python
# quant/strategies.py
@register("反转低换手")
def 反转低换手(day):
    return day["z_REV20"] - day["z_TURN"]
```

也可以在网页「助手 → 选股」里用**因子表达式**定义策略（存 `strategy` 表，`kind='expr'`）：

```
z_SIZE + z_REV20 - z_VOL20      小市值 + 反转 + 低波
z_REV20 - z_TURN                反转 + 低换手
```

表达式走 AST 白名单（只认因子名、数字、`+ - * /`、括号、负号），
`__import__` / 比较 / 属性访问一律拒识。

| 因子 | 含义 |
|---|---|
| `SIZE` | 小市值（取负对数，越大越小盘） |
| `REV5 / REV20 / REV60` | 反转（跌得越深越大） |
| `MOM20` | 动量（= −REV20） |
| `VOL20` | 20 日波动率 |
| `TURN / PB / PE / DIV` | 换手 / 市净 / 市盈 / 股息 |
| `LB / AMT / AMT20 / VOL_RATIO` | 量比 / 成交额 / 20日均额 / 放量倍数 |
| `NEWHIGH20 / MA_GAP / SIG2ST` | 20日新高 / 均线发散 / 二次站稳五日线事件 |

全部因子都另有一份 `z_` 前缀的横截面标准化版本。

## 回测口径（重要）

- **选股**：t 日收盘选股 → **t+1 收盘买入** → 持有 `hold_days` 天卖出（延迟买入，避前视）
- **调仓**：每 `hold_days` 个交易日一次（不重叠）
- **成本**：每期扣 `cost`（默认 0.3% 双边），复利滚动
- **股票池（实盘口径）**：剔 ST/退市、股价 ≥ 2 元、**成交额 ≥ 5000 万**、**剔除涨幅 ≥ 9.5%**
  这几条必须和实盘一致，否则回测买得进、实盘买不进

## 已验证结果（诚实版）

主线「小市值反转低波」TOP5 / 持有 20 天 / 2019-2026：

| 口径 | 累计 | 年化 | 最大回撤 | 期胜率 |
|---|---|---|---|---|
| 旧口径（只剔 ST + 股价≥2） | +362.8% | 22.1% | −41% | — |
| **实盘口径（默认）** | **+54.6%** | **5.83%** | **−46.9%** | 47.3% |

差额全部来自日成交 2000~3000 万、流通市值 5~14 亿的微盘股 —— 回测买得进、实盘买不进。
**报收益一律用实盘口径。**

## 数据

- 全样本缓存：`data/daily_full_2019_2026.csv`（18 字段）+ 同名 `.pkl` 旁路（读 15s → 1s）
- 选股面板：`data/recent_panel.csv`（最近 140 个交易日）
- 原始日线：`/Volumes/TOSHIBA/炒股/每日行情/{年份}/*.csv`（百度网盘同步）
- 覆盖路径：`STOCK_DATA_ROOT` / `BACKTEST_DATA_DIR` / `BACKTEST_CACHE` / `BACKTEST_PKL`
