# -*- coding: utf-8 -*-
"""
A股「弱市一夜持股」公式回测（新浪数据源）
公式三：弱市一夜持股
  温和涨: 0 < ZF <= 3
  尾盘强: C >= H - (H-L)*0.3
  站上十线: C >= MA10
  十线稳: MA10 >= REF(MA10,1)
  温和量: 量比 1~2.5 (量比=V/REF(MA(V,5),1))
  换手OK: 换手率 2~8% (V股/流通股本*100)
买卖：T日收盘买，T+1开盘卖
"""
import json, ssl, time, os, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
CTX = ssl.create_default_context()
REFERER = 'https://finance.sina.com.cn'
CACHE = '/Volumes/TOSHIBA/炒股/回测/backtest_kline_sina.csv'

def http_get(url, referer=None, timeout=15, retries=4):
    last = None
    for i in range(retries):
        try:
            h = dict(UA)
            if referer:
                h['Referer'] = referer
            req = urllib.request.Request(url, headers=h)
            r = urllib.request.urlopen(req, timeout=timeout, context=CTX)
            return r.read().decode('utf-8', 'ignore')
        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))
    raise last

# ---------- 股票列表 ----------
def fetch_stock_list():
    rows = []; page = 1
    while True:
        url = ("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               "Market_Center.getHQNodeData?page=%d&num=100&sort=symbol&asc=1"
               "&node=hs_a&symbol=&_s_r_a=page" % page)
        txt = http_get(url, referer=REFERER)
        try:
            data = json.loads(txt)
        except Exception:
            break
        if not isinstance(data, list) or not data:
            break
        rows.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.1)
    return rows

def code_to_symbol(code):
    if code.startswith(('60', '68')):
        return 'sh' + code
    if code.startswith(('00', '30')):
        return 'sz' + code
    return None

print('[1] 股票列表...', flush=True)
LIST_CACHE = '/Volumes/TOSHIBA/炒股/回测/stocks_list.csv'
raw = None
if os.path.exists(LIST_CACHE):
    try:
        raw = pd.read_csv(LIST_CACHE, dtype={'code': str}).to_dict('records')
        print('    从缓存读取列表 %d 条' % len(raw), flush=True)
    except Exception:
        raw = None
if raw is None:
    raw = fetch_stock_list()
    pd.DataFrame(raw).to_csv(LIST_CACHE, index=False)
    print('    列表已缓存 %d 条' % len(raw), flush=True)
stocks = {}
for it in raw:
    code = it.get('code', ''); sym = code_to_symbol(code)
    if not sym:
        continue
    name = it.get('name', '')
    if 'ST' in name.upper() or '退' in name:
        continue
    try:
        trade = float(it['trade']); nmc = float(it['nmc'])
    except (TypeError, ValueError, KeyError):
        continue
    if trade <= 0 or nmc <= 0:
        continue
    stocks[code] = {'name': name, 'shares': nmc * 10000.0 / trade, 'sym': sym}
print('    沪深A股(剔ST/退/北交所) %d 只' % len(stocks), flush=True)

# ---------- 上证指数（新浪） ----------
def fetch_kline_sina(sym, datalen=400):
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%%20_=/CN_MarketDataService.getKLineData"
           "?symbol=%s&scale=240&ma=no&datalen=%d" % (sym, datalen))
    txt = http_get(url, referer=REFERER)
    i = txt.find('['); j = txt.rfind(']')
    if i < 0 or j < 0:
        raise ValueError('no json')
    arr = json.loads(txt[i:j+1])
    df = pd.DataFrame(arr)
    df = df.rename(columns={'day': 'date'})
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['close'])
    return df[['date', 'open', 'high', 'low', 'close', 'volume']]

print('[2] 上证指数...', flush=True)
idx = fetch_kline_sina('sh000001', 400).sort_values('date').reset_index(drop=True)
idx['ma20'] = idx['close'].rolling(20).mean()
idx_regime = dict(zip(idx['date'], idx['ma20']))
idx_close = dict(zip(idx['date'], idx['close']))
print('    上证 %d 交易日' % len(idx), flush=True)

# ---------- 拉取全市场日线（增量保存 + 多轮补抓） ----------
already = set()
if os.path.exists(CACHE):
    try:
        already = set(pd.read_csv(CACHE, usecols=['code'], dtype={'code': str})['code'])
    except Exception:
        already = set()
print('[3] 拉取日线（已缓存 %d 只）...' % len(already), flush=True)

import threading
lock = threading.Lock()
header_written = os.path.exists(CACHE)

def fetch_and_save(code):
    sym = stocks[code]['sym']
    try:
        df = fetch_kline_sina(sym, 400)
        df['code'] = code
        with lock:
            if not os.path.exists(CACHE):
                df.to_csv(CACHE, index=False)
            else:
                df.to_csv(CACHE, mode='a', header=False, index=False)
        return True
    except Exception:
        return False

todo = [c for c in stocks if c not in already]
for p in range(3):
    if not todo:
        break
    t0 = time.time(); ok = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch_and_save, c): c for c in todo}
        for f in as_completed(futs):
            if f.result():
                ok += 1
        time.sleep(0.15)
    done = len(todo) - (len(todo) - ok)
    print('    pass%d: %d/%d 成功, %.0fs' % (p+1, ok, len(todo), time.time()-t0), flush=True)
    # 重新读取缓存得到剩余未成功的
    got = set(pd.read_csv(CACHE, usecols=['code'], dtype={'code': str})['code'])
    todo = [c for c in stocks if c not in got]

alldata = pd.read_csv(CACHE, dtype={'code': str}).drop_duplicates(subset=['code', 'date'])
print('    合计 %d 只股票, %d 行' % (alldata['code'].nunique(), len(alldata)), flush=True)

# ---------- 计算信号 ----------
print('[4] 计算信号...', flush=True)
g = alldata.groupby('code', sort=False)
signals = []

def process(code, df):
    df = df.sort_values('date').reset_index(drop=True)
    if len(df) < 45:
        return []
    c = df['close']; h = df['high']; l = df['low']; v = df['volume']
    ma10 = c.rolling(10).mean()
    ma_v5 = v.rolling(5).mean()
    zf = c.pct_change() * 100.0
    liangbi = v / ma_v5.shift(1)
    shares = stocks[code]['shares']
    hsl = v / shares * 100.0
    out = []; n = len(df)
    for i in range(15, n - 1):
        if pd.isna(ma10.iloc[i]) or pd.isna(liangbi.iloc[i]) or pd.isna(hsl.iloc[i]):
            continue
        if not (0 < zf.iloc[i] <= 3):
            continue
        if not (c.iloc[i] >= h.iloc[i] - (h.iloc[i] - l.iloc[i]) * 0.3):
            continue
        if not (c.iloc[i] >= ma10.iloc[i] and ma10.iloc[i] >= ma10.iloc[i-1]):
            continue
        if not (1.0 <= liangbi.iloc[i] <= 2.5):
            continue
        if not (2.0 <= hsl.iloc[i] <= 8.0):
            continue
        buy = c.iloc[i]; sell = df['open'].iloc[i+1]
        if buy <= 0 or sell <= 0:
            continue
        out.append({'code': code, 'name': stocks[code]['name'], 'date': df['date'].iloc[i],
                    'next_date': df['date'].iloc[i+1], 'ret': sell / buy - 1.0,
                    'zf': zf.iloc[i], 'hsl': hsl.iloc[i], 'liangbi': liangbi.iloc[i]})
    return out

with ThreadPoolExecutor(max_workers=6) as ex:
    futs = [ex.submit(process, code, g.get_group(code)) for code in g.groups]
    for f in as_completed(futs):
        signals.extend(f.result())

res = pd.DataFrame(signals)
print('    信号数 %d' % len(res), flush=True)
if len(res) == 0:
    raise SystemExit('零信号')

res['ma20'] = res['date'].map(idx_regime)
res['idx_close'] = res['date'].map(idx_close)
def regime_of(r):
    if pd.isna(r['ma20']) or pd.isna(r['idx_close']):
        return '未知'
    return '弱市' if r['idx_close'] < r['ma20'] else '强市'
res['regime'] = res.apply(regime_of, axis=1)
res.to_csv('/Volumes/TOSHIBA/炒股/回测/backtest_signals.csv', index=False)

# ---------- 统计 ----------
def stats(sub, label):
    n = len(sub)
    if n == 0:
        print('\n[%s] 无信号' % label); return
    ret = sub['ret']
    wr = (ret > 0).mean() * 100
    avg = ret.mean() * 100; med = ret.median() * 100
    print('\n[%s] n=%d' % (label, n))
    print('    毛收益: 胜率%.1f%%  平均%+.2f%%  中位%+.2f%%' % (wr, avg, med))
    for cost, cn in [(0.0, '无成本'), (0.0015, '成本0.15%'), (0.003, '成本0.30%')]:
        net = ret - cost
        print('    %-9s -> 净胜率%.1f%%  净平均%+.2f%%' % (cn, (net > 0).mean() * 100, net.mean() * 100))
    pos = ret[ret > 0]; neg = ret[ret < 0]
    pf = pos.sum() / (-neg.sum()) if len(neg) and neg.sum() < 0 else float('inf')
    print('    盈亏比PF=%.2f  平均盈利%+.2f%%/平均亏损%.2f%%  最大单笔%+.2f%%/最差%+.2f%%' %
          (pf, pos.mean() * 100, neg.mean() * 100, ret.max() * 100, ret.min() * 100))

stats(res, '全时段')
stats(res[res['regime'] == '弱市'], '弱市(上证<MA20)')
stats(res[res['regime'] == '强市'], '强市(上证>=MA20)')

res['ym'] = res['date'].str[:7]
print('\n按月:')
g2 = res.groupby('ym').agg(n=('ret', 'size'), 均收益=('ret', lambda x: x.mean()*100), 胜率=('ret', lambda x: (x>0).mean()*100))
print(g2.round(2).to_string())

# 汇总json
summary = {
    'total': int(len(res)),
    'weak_n': int((res['regime']=='弱市').sum()),
    'strong_n': int((res['regime']=='强市').sum()),
    'overall': {'win_rate': float((res['ret']>0).mean()), 'avg_ret': float(res['ret'].mean()), 'median_ret': float(res['ret'].median())},
}
for key, tag in [('weak', '弱市'), ('strong', '强市')]:
    w = res[res['regime'] == tag]
    if len(w):
        summary[key] = {'win_rate': float((w['ret']>0).mean()), 'avg_ret': float(w['ret'].mean()),
                        'median_ret': float(w['ret'].median()), 'n': int(len(w))}
with open('/Volumes/TOSHIBA/炒股/回测/backtest_summary.json', 'w') as fp:
    json.dump(summary, fp, ensure_ascii=False, indent=2)
print('\nDONE')
