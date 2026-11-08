// A股分析系统 前端逻辑

/* ============================ 主题 ============================ */
const THEMES = {
  dark: {
    bg: '#0d1117', panel: '#161b22',
    axis: '#2a3340', axisStrong: '#3a4553',
    line: '#1f2630', lineSub: '#171d26',
    text: '#e6edf3', muted: '#8b949e', dim: '#8b98a8', legend: '#a9b4c2',
    up: '#f6465d', down: '#0ecb81',
    upArea: 'rgba(246,70,93,.28)', downArea: 'rgba(14,203,129,.24)',
    areaFade: 'rgba(13,17,23,0)',
    c1: '#fbbf24', c2: '#58a6ff', c3: '#c084fc', c4: '#34d399',
    ma5: '#fbbf24', ma10: '#58a6ff', ma20: '#c084fc',
    ma30: '#f472b6', ma60: '#34d399', ma120: '#8b98a8',
    bollMid: '#8b98a8', bollEdge: '#5c6a7d', ref: '#5c6a7d',
    accentArea: 'rgba(88,166,255,.13)', purpleArea: 'rgba(192,132,252,.13)',
    tipBg: 'rgba(22,27,34,.97)', tipShadow: 'rgba(0,0,0,.45)',
    sliderBg: '#161b22', sliderFill: 'rgba(88,166,255,.16)',
    sliderDataLine: '#2f3a49', sliderDataArea: '#1b222c',
    sliderSelLine: '#3d6b9e', sliderSelArea: '#22344a',
    sliderHandle: '#58a6ff', sliderMove: '#3a4553',
  },
  light: {
    bg: '#ffffff', panel: '#ffffff',
    axis: '#e5e7eb', axisStrong: '#d1d5db',
    line: '#f1f2f4', lineSub: '#f6f7f9',
    text: '#1f2937', muted: '#6b7280', dim: '#9ca3af', legend: '#4b5563',
    up: '#ef232a', down: '#14b143',
    upArea: 'rgba(239,35,42,.20)', downArea: 'rgba(20,177,67,.20)',
    areaFade: 'rgba(255,255,255,0)',
    c1: '#f59e0b', c2: '#3b82f6', c3: '#a855f7', c4: '#10b981',
    ma5: '#f59e0b', ma10: '#3b82f6', ma20: '#a855f7',
    ma30: '#ec4899', ma60: '#10b981', ma120: '#64748b',
    bollMid: '#94a3b8', bollEdge: '#cbd5e1', ref: '#cbd5e1',
    accentArea: 'rgba(37,99,235,.10)', purpleArea: 'rgba(168,85,247,.08)',
    tipBg: 'rgba(255,255,255,.97)', tipShadow: 'rgba(0,0,0,.10)',
    sliderBg: '#ffffff', sliderFill: 'rgba(37,99,235,.18)',
    sliderDataLine: '#dbe1e8', sliderDataArea: '#f3f4f6',
    sliderSelLine: '#93c5fd', sliderSelArea: '#dbeafe',
    sliderHandle: '#3b82f6', sliderMove: '#e5e7eb',
  },
};

let THEME = 'dark';
let T = THEMES.dark;
let BG = T.bg;                    // 主图/画布底色
let UP = T.up, DOWN = T.down;     // 涨=红 跌=绿
const C = Object.assign({}, T);   // 均线与副图配色快照，applyTheme 时同步

const chartBox = document.getElementById('chart');

/* 移动端判定：与 CSS 断点保持一致（820px） */
const MOBILE_BP = 820;
const isMobile = () => window.innerWidth <= MOBILE_BP;
let wasMobile = isMobile();
let chart = null;                       // 延迟到指标条渲染后再 init，避免容器高度取错
const input = document.getElementById('search-input');
const results = document.getElementById('search-results');
const stockInfo = document.getElementById('stock-info');
const emptyTip = document.getElementById('empty-tip');
const chipsBox = document.getElementById('ind-chips');

let current = { code: '600036', period: 'day' };
let MAIN_PCT = 60;      // 主图高度占容器百分比（render 时更新）
let lastData = null;

/* ============================ 副图指标定义 ============================ */
// 每个指标：label 显示名，digits 小数位，main 是否画在主图，build(d) -> series[]
const SUBS = {
  vol: {
    label: '成交量 VOL',
    build: d => ([
      { name: '成交量', type: 'bar', data: d.volume, barMaxWidth: 10,
        itemStyle: { color: p => (d.ohlc[p.dataIndex][1] >= d.ohlc[p.dataIndex][0] ? UP : DOWN) } },
      { name: 'VMA5', type: 'line', data: d.vol_ma.vma5, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'VMA10', type: 'line', data: d.vol_ma.vma10, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
    ]),
  },
  macd: {
    label: 'MACD(12,26,9)',
    build: d => ([
      { name: 'MACD柱', type: 'bar', data: d.macd.hist, barMaxWidth: 8,
        itemStyle: { color: p => (p.value >= 0 ? UP : DOWN) } },
      { name: 'DIF', type: 'line', data: d.macd.dif, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'DEA', type: 'line', data: d.macd.dea, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
    ]),
  },
  kdj: {
    label: 'KDJ(9,3,3)',
    ref: [80, 20],
    build: d => ([
      { name: 'K', type: 'line', data: d.kdj.k, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'D', type: 'line', data: d.kdj.d, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
      { name: 'J', type: 'line', data: d.kdj.j, showSymbol: false,
        lineStyle: { width: 1, color: C.c3 }, itemStyle: { color: C.c3 } },
    ]),
  },
  rsi: {
    label: 'RSI(6,12,24)',
    ref: [70, 30],
    build: d => ([
      { name: 'RSI6', type: 'line', data: d.rsi.rsi6, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'RSI12', type: 'line', data: d.rsi.rsi12, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
      { name: 'RSI24', type: 'line', data: d.rsi.rsi24, showSymbol: false,
        lineStyle: { width: 1, color: C.c3 }, itemStyle: { color: C.c3 } },
    ]),
  },
  wr: {
    label: 'WR(6,10)',
    ref: [80, 20],
    build: d => ([
      { name: 'WR6', type: 'line', data: d.wr.wr6, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'WR10', type: 'line', data: d.wr.wr10, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
    ]),
  },
  bias: {
    label: 'BIAS 乖离率(6,12,24)',
    ref: [0],
    build: d => ([
      { name: 'BIAS6', type: 'line', data: d.bias.bias6, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'BIAS12', type: 'line', data: d.bias.bias12, showSymbol: false,
        lineStyle: { width: 1, color: C.c2 }, itemStyle: { color: C.c2 } },
      { name: 'BIAS24', type: 'line', data: d.bias.bias24, showSymbol: false,
        lineStyle: { width: 1, color: C.c3 }, itemStyle: { color: C.c3 } },
    ]),
  },
  dmi: {
    label: 'DMI(14,6)',
    ref: [25],
    build: d => ([
      { name: 'PDI', type: 'line', data: d.dmi.pdi, showSymbol: false,
        lineStyle: { width: 1, color: UP }, itemStyle: { color: UP } },
      { name: 'MDI', type: 'line', data: d.dmi.mdi, showSymbol: false,
        lineStyle: { width: 1, color: DOWN }, itemStyle: { color: DOWN } },
      { name: 'ADX', type: 'line', data: d.dmi.adx, showSymbol: false,
        lineStyle: { width: 1, color: C.c1 }, itemStyle: { color: C.c1 } },
      { name: 'ADXR', type: 'line', data: d.dmi.adxr, showSymbol: false,
        lineStyle: { width: 1, color: C.c3, type: 'dashed' }, itemStyle: { color: C.c3 } },
    ]),
  },
  obv: {
    label: 'OBV 能量潮(万手)',
    build: d => ([
      { name: 'OBV', type: 'line', data: d.obv, showSymbol: false, smooth: true,
        lineStyle: { width: 1.2, color: T.c2 }, itemStyle: { color: T.c2 },
        areaStyle: { color: T.accentArea } },
    ]),
  },
  atr: {
    label: 'ATR(14) 波动',
    build: d => ([
      { name: 'ATR14', type: 'line', data: d.atr, showSymbol: false,
        lineStyle: { width: 1.2, color: C.c3 }, itemStyle: { color: C.c3 },
        areaStyle: { color: T.purpleArea } },
    ]),
  },
};

const SUB_ORDER = ['vol', 'macd', 'kdj', 'rsi', 'wr', 'bias', 'dmi', 'obv', 'atr'];
const MAX_SUBS = 4;
// 手机屏窄，默认只开 2 个副图，主图才够看
let activeSubs = isMobile() ? ['vol', 'macd'] : ['vol', 'macd', 'kdj', 'rsi'];

/* ============================ 副图选择器 ============================ */
function renderChips() {
  chipsBox.innerHTML = '';
  SUB_ORDER.forEach(k => {
    const el = document.createElement('span');
    el.className = 'chip' + (activeSubs.includes(k) ? ' active' : '');
    el.textContent = SUBS[k].label;
    el.onclick = () => {
      if (activeSubs.includes(k)) {
        activeSubs = activeSubs.filter(x => x !== k);
      } else {
        if (activeSubs.length >= MAX_SUBS) activeSubs = activeSubs.slice(1);
        activeSubs = activeSubs.concat(k);
      }
      // 按固定顺序展示，避免布局抖动
      activeSubs = SUB_ORDER.filter(x => activeSubs.includes(x));
      renderChips();
      if (lastData) render(lastData);
    };
    chipsBox.appendChild(el);
  });
}

/* ============================ 搜索（防抖） ============================ */
let timer = null;
input.addEventListener('input', () => {
  clearTimeout(timer);
  const q = input.value.trim();
  if (!q) { results.classList.remove('show'); return; }
  timer = setTimeout(async () => {
    try {
      const r = await fetch('/api/search?q=' + encodeURIComponent(q));
      const data = await r.json();
      renderSearch(data.results);
    } catch (e) { /* ignore */ }
  }, 180);
});
input.addEventListener('blur', () => setTimeout(() => results.classList.remove('show'), 200));

function renderSearch(list) {
  results.innerHTML = '';
  if (!list || !list.length) { results.classList.remove('show'); return; }
  list.forEach(m => {
    const div = document.createElement('div');
    div.className = 'search-item';
    div.innerHTML = '<span><span class="code">' + m.code + '</span><span class="name">' + m.name +
      '</span></span><span class="close">' + m.last_date + ' · ' + m.last_close.toFixed(2) + '</span>';
    div.onclick = () => {
      current.code = m.code;
      results.classList.remove('show');
      input.value = m.code + ' ' + m.name;
      load();
    };
    results.appendChild(div);
  });
  results.classList.add('show');
}

// ---------- 周期切换 ----------
document.querySelectorAll('.period-tabs button').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.period-tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    current.period = btn.dataset.period;
    load();
  };
});

// ---------- 加载数据 ----------
async function load() {
  const r = await fetch('/api/kline?code=' + current.code + '&period=' + current.period + '&live=1');
  if (!r.ok) { alert('加载失败：' + (await r.text())); return; }
  const d = await r.json();
  lastData = d;
  emptyTip.style.display = 'none';
  stockInfo.innerHTML = '<span class="sname">' + d.name + '</span>' +
    '<span class="scode">' + d.code + '</span>' +
    '<span class="rt" id="rt-bar"></span>';
  markActive();
  render(d);
  if (showTrades) {                    // 买卖点开关开着：拉账本画到 K 线上
    loadTrades(d.code).then(() => { if (lastData === d) render(d); });
  }
  loadRealtime();          // 切股票后立刻补一次实时价
  startRtTimer();
}

// 盘中定时刷新：重新拉 live K 线并重绘（dataZoom 靠 zoomMem 保持原位）
let liveBusy = false;
let mouseInChart = false;
chartBox.addEventListener('mouseenter', () => { mouseInChart = true; });
chartBox.addEventListener('mouseleave', () => { mouseInChart = false; });

async function refreshLiveKline() {
  if (!current.code || liveBusy) return;
  if (Date.now() - lastZoomAt < 1500) return;   // 用户正在缩放/拖动，别打断
  if (mouseInChart) return;                     // 鼠标停在图上（多半在看 tooltip），别打断
  liveBusy = true;
  try {
    const r = await fetch('/api/kline?code=' + current.code +
      '&period=' + current.period + '&live=1');
    if (!r.ok) return;
    const d = await r.json();
    lastData = d;
    render(d, true);                 // 增量更新：只刷数据，不动缩放和结构
  } catch (e) { /* 本轮跳过 */ }
  finally { liveBusy = false; }
}

/* ============================ 实时行情 ============================ */
// 走 /api/realtime（后端接腾讯公开行情接口）。只在交易时段轮询，收盘后不打扰上游。
let rtTimer = null;
let lastRt = null;

function isTradingTime() {
  const d = new Date();
  const wd = d.getDay();
  if (wd === 0 || wd === 6) return false;         // 周末
  const hm = d.getHours() * 100 + d.getMinutes();
  return (hm >= 915 && hm <= 1135) || (hm >= 1255 && hm <= 1505);
}

function renderRealtime(q) {
  const el = document.getElementById('rt-bar');
  if (!el || !q) return;
  const col = q.pct >= 0 ? UP : DOWN;
  const sign = q.pct >= 0 ? '+' : '';
  el.innerHTML =
    '<b style="color:' + col + '">' + q.price.toFixed(2) + '</b>' +
    '<i style="color:' + col + '">' + sign + q.pct.toFixed(2) + '%</i>' +
    (q.time ? '<em>' + q.time.slice(11, 16) + '</em>' : '');
  el.title = (q.name || '') + ' 开' + nv(q.open, 2) + ' 高' + nv(q.high, 2) +
    ' 低' + nv(q.low, 2) + ' 量比' + nv(q.vol_ratio, 2) +
    ' 换手' + nv(q.turnover, 2) + '% 成交' + humanAmt(q.amount);
}

async function loadRealtime() {
  if (!current.code) return;
  try {
    const r = await fetch('/api/realtime?codes=' + encodeURIComponent(current.code));
    const d = await r.json();
    const q = (d.quotes || [])[0];
    if (q) { lastRt = q; renderRealtime(q); }
  } catch (e) { /* 行情拿不到不影响主图 */ }
}

function stopRtTimer() {
  if (rtTimer) { clearInterval(rtTimer); rtTimer = null; }
}

function startRtTimer() {
  stopRtTimer();
  if (!isTradingTime()) return;
  rtTimer = setInterval(() => {
    if (document.hidden) return;                   // 页面在后台就不刷
    loadRealtime();                                // 顶栏实时价
    refreshLiveKline();                            // 当前个股的实时 K 线
    if (watchCodes.length) refreshWatch();         // 自选报价
  }, 5000);
}

// 回到前台时立刻补一次
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && isTradingTime()) { loadRealtime(); startRtTimer(); }
});

/* ============================ 提示框 ============================ */
function nv(v, dg) { return (v == null || isNaN(v)) ? '--' : Number(v).toFixed(dg); }
function c2(label, val, color) {
  const st = color ? ' style="color:' + color + '"' : '';
  return '<span class="tt-c"><i' + st + '>' + label + '</i>' + val + '</span>';
}
function humanVol(hand) {
  if (hand == null) return '--';
  return hand >= 1e4 ? (hand / 1e4).toFixed(2) + '万手' : hand + '手';
}
function humanAmt(w) {   // 后端单位：万元
  if (w == null) return '--';
  return w >= 1e4 ? (w / 1e4).toFixed(2) + '亿' : w.toFixed(0) + '万';
}

function tooltipFormatter(d) {
  return function (params) {
    const p = Array.isArray(params) ? params : [params];
    const k = p.find(x => x.seriesType === 'candlestick');
    if (!k) return '';
    const i = k.dataIndex;
    const ohlc = d.ohlc[i];
    if (!Array.isArray(ohlc) || ohlc.length < 4) return '';
    const o = ohlc[0], cl = ohlc[1], lo = ohlc[2], hi = ohlc[3];
    const prev = i > 0 ? d.ohlc[i - 1][1] : o;
    const chg = cl - prev;
    const pct = d.pct_chg[i];
    const col = chg >= 0 ? UP : DOWN;
    const pctStr = (pct == null) ? '' : ('（' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%）');

    let h = '<div class="tt-head">' + k.axisValue + '</div>';
    h += '<div class="tt-row">' +
      c2('开', nv(o, 2), col) + c2('收', nv(cl, 2), col) +
      c2('高', nv(hi, 2), UP) + c2('低', nv(lo, 2), DOWN) + '</div>';
    h += '<div class="tt-row">' +
      c2('涨跌', (chg >= 0 ? '+' : '') + nv(chg, 2) + pctStr, col) +
      c2('成交量', humanVol(d.volume[i])) + c2('成交额', humanAmt(d.amount[i])) + '</div>';

    // 主图均线 + BOLL
    h += '<div class="tt-sep"></div><div class="tt-row">';
    ['ma5', 'ma10', 'ma20', 'ma30', 'ma60', 'ma120'].forEach(key => {
      h += c2(key.toUpperCase(), nv(d.ma[key][i], 2), C[key]);
    });
    h += c2('BOLL上', nv(d.boll.upper[i], 2), T.dim) +
         c2('BOLL中', nv(d.boll.mid[i], 2), T.dim) +
         c2('BOLL下', nv(d.boll.lower[i], 2), T.dim) + '</div>';

    // 副图指标
    activeSubs.forEach(key => {
      let items = '';
      if (key === 'vol') {
        items = c2('VOL', humanVol(d.volume[i])) + c2('VMA5', humanVol(d.vol_ma.vma5[i])) +
                c2('VMA10', humanVol(d.vol_ma.vma10[i]));
      } else if (key === 'macd') {
        items = c2('DIF', nv(d.macd.dif[i], 3), C.c1) + c2('DEA', nv(d.macd.dea[i], 3), C.c2) +
                c2('MACD柱', nv(d.macd.hist[i], 3), d.macd.hist[i] >= 0 ? UP : DOWN);
      } else if (key === 'kdj') {
        items = c2('K', nv(d.kdj.k[i], 1), C.c1) + c2('D', nv(d.kdj.d[i], 1), C.c2) +
                c2('J', nv(d.kdj.j[i], 1), C.c3);
      } else if (key === 'rsi') {
        items = c2('RSI6', nv(d.rsi.rsi6[i], 1), C.c1) + c2('RSI12', nv(d.rsi.rsi12[i], 1), C.c2) +
                c2('RSI24', nv(d.rsi.rsi24[i], 1), C.c3);
      } else if (key === 'wr') {
        items = c2('WR6', nv(d.wr.wr6[i], 1), C.c1) + c2('WR10', nv(d.wr.wr10[i], 1), C.c2);
      } else if (key === 'bias') {
        items = c2('BIAS6', nv(d.bias.bias6[i], 2) + '%', C.c1) +
                c2('BIAS12', nv(d.bias.bias12[i], 2) + '%', C.c2) +
                c2('BIAS24', nv(d.bias.bias24[i], 2) + '%', C.c3);
      } else if (key === 'dmi') {
        items = c2('PDI', nv(d.dmi.pdi[i], 1), UP) + c2('MDI', nv(d.dmi.mdi[i], 1), DOWN) +
                c2('ADX', nv(d.dmi.adx[i], 1), C.c1) + c2('ADXR', nv(d.dmi.adxr[i], 1), C.c3);
      } else if (key === 'obv') {
        items = c2('OBV', nv(d.obv[i], 2) + '万手', T.c2);
      } else if (key === 'atr') {
        items = c2('ATR14', nv(d.atr[i], 3), C.c3);
      }
      h += '<div class="tt-sep"></div><div class="tt-row">' + items + '</div>';
    });

    // 这根 K 线上的成交（交易账本）
    const tr = (showTrades && tradesCache[d.code]) || [];
    if (tr.length) {
      let tlines = '';
      tr.forEach(t => {
        if (tradeIndexFor(d.dates, t.date, d.period === 'day') === i) {
          const buy = t.side === 'buy';
          tlines += c2(buy ? '买入' : '卖出', nv(t.price, 2) + ' ×' + t.shares + '股', buy ? UP : DOWN);
        }
      });
      if (tlines) h += '<div class="tt-sep"></div><div class="tt-row">' + tlines + '</div>';
    }
    return h;
  };
}

/* ============================ 买卖点标注（交易账本 trade 表） ============================ */
const tradeBtn = document.getElementById('trade-btn');
let showTrades = false;
try { showTrades = localStorage.getItem('show_trades') === '1'; } catch (e) { /* 忽略 */ }
const tradesCache = {};          // code -> 买卖点数组（undefined=还没拉过）

async function loadTrades(code) {
  try {
    const r = await fetch('/api/trades?code=' + code);
    const d = await r.json();
    tradesCache[code] = d.trades || [];
  } catch (e) { tradesCache[code] = []; }
  return tradesCache[code];
}

// 某笔成交落在第几根 K 线上：
//   日线精确匹配（后端已对齐交易日，非交易日取之前最近一根）；
//   周/月线取该日期所属周期桶（首个标签 >= 成交日的桶）。
function tradeIndexFor(dates, iso, isDay) {
  if (isDay) {
    let i = dates.indexOf(iso);
    if (i < 0) {
      let lo = 0, hi = dates.length - 1;
      while (lo < hi) { const m = (lo + hi + 1) >> 1; dates[m] <= iso ? (lo = m) : (hi = m - 1); }
      i = dates[lo] <= iso ? lo : -1;
    }
    return i;
  }
  for (let i = 0; i < dates.length; i++) {
    if (dates[i] >= iso) return i;
  }
  return dates.length - 1;
}

// 买 = 红底白字 B（贴最低价下方）；卖 = 蓝底白字 S（贴最高价上方），与券商标注一致
const TRADE_B = '#d0453c';     // 买入红
const TRADE_S = '#3b7dd8';     // 卖出蓝

function buildTradeSeries(d) {
  if (!showTrades) return null;
  const tr = tradesCache[d.code];
  if (!tr || !tr.length) return null;
  const isDay = d.period === 'day';
  const pts = [];
  tr.forEach(t => {
    const i = tradeIndexFor(d.dates, t.date, isDay);
    if (i < 0 || i >= d.dates.length) return;
    const bar = d.ohlc[i];
    if (!bar || bar.length < 4) return;
    const buy = t.side === 'buy';
    const rng = bar[3] - bar[2];
    const off = rng > 0 ? rng * 0.22 : (bar[1] || 20) * 0.002;
    pts.push({
      value: [i, buy ? bar[2] - off : bar[3] + off],
      symbol: 'roundRect', symbolSize: [14, 13],
      symbolOffset: [0, buy ? 5 : -5],
      itemStyle: { color: buy ? TRADE_B : TRADE_S, borderRadius: 2 },
      label: { show: true, formatter: buy ? 'B' : 'S', color: '#fff',
               fontSize: 9, fontWeight: 700, position: 'inside' },
    });
  });
  if (!pts.length) return null;
  return { name: '买卖点', type: 'scatter', xAxisIndex: 0, yAxisIndex: 0,
           z: 12, silent: true, legendHoverLink: false, data: pts };
}

if (tradeBtn) {
  tradeBtn.classList.toggle('active', showTrades);
  tradeBtn.onclick = async () => {
    showTrades = !showTrades;
    try { localStorage.setItem('show_trades', showTrades ? '1' : '0'); } catch (e) { /* 忽略 */ }
    tradeBtn.classList.toggle('active', showTrades);
    if (showTrades && current.code) await loadTrades(current.code);   // 每次打开都重新拉，账本有新成交能立刻看到
    if (lastData) render(lastData);
  };
}

/* ============================ 记住缩放窗口 ============================ */
// 换股票 / 换周期时沿用上次的缩放：记「窗口里有几根 K 线」+「是否贴着最右边」
// （用根数而不是百分比，因为不同股票总根数不同，按百分比会看成完全不同的密集度）
const ZOOM_KEY = 'kline_zoom';
let zoomMem = (() => {
  try {
    const o = JSON.parse(localStorage.getItem(ZOOM_KEY) || 'null');
    if (o && typeof o.count === 'number' && o.count > 0) {
      return { count: o.count, startPct: o.startPct ?? 0,
               endPct: o.endPct ?? 100, rightEdge: o.rightEdge !== false };
    }
  } catch (e) { /* 隐私模式忽略 */ }
  return { count: null, startPct: 0, endPct: 100, rightEdge: true };
})();
let zoomApplied = null;       // 最近一次由代码设定的窗口（用于区分「程序设置」和「用户缩放」）
let zoomSaveTimer = null;
let lastZoomAt = 0;           // 用户最近一次缩放/拖动的时间，用于避开实时刷新

function saveZoomMem() {
  if (!chart || !lastData) return;
  let dz = null;
  try {
    dz = (chart.getOption().dataZoom || [])[0] || null;
  } catch (e) { return; }
  if (!dz || dz.start == null || dz.end == null) return;
  // 值跟我们刚 setOption 进去的一模一样 → 是程序造成的，不是用户动的
  if (zoomApplied &&
      Math.abs(dz.start - zoomApplied.start) < 0.05 &&
      Math.abs(dz.end - zoomApplied.end) < 0.05) return;
  const N = lastData.dates.length;
  if (!N) return;
  const span = Math.max(0, dz.end - dz.start);
  if (span <= 0) return;
  zoomMem = {
    count: Math.max(5, Math.round(span / 100 * N)),
    startPct: dz.start,
    endPct: dz.end,
    rightEdge: dz.end >= 99.5,
  };
  try { localStorage.setItem(ZOOM_KEY, JSON.stringify(zoomMem)); } catch (e) { /* 忽略 */ }
}

/* ============================ 渲染 ============================ */
let lastSeriesCount = 0;      // 上次全量渲染的 series 条数，用于判断能否增量更新

function render(d, patchOnly) {
  const dates = d.dates;
  const N = dates.length;

  // 缩放窗口：有记忆就沿用，没有就默认最近 300 根
  let zoomStart, zoomEnd;
  if (zoomMem.count && N > 0) {
    const pct = Math.min(100, zoomMem.count / N * 100);
    if (zoomMem.rightEdge || zoomMem.endPct >= 99.5) {
      zoomEnd = 100;
      zoomStart = Math.max(0, 100 - pct);
    } else {
      zoomStart = Math.min(100 - pct, Math.max(0, zoomMem.startPct));
      zoomEnd = zoomStart + pct;
    }
  } else {
    zoomStart = N > 300 ? Math.max(0, (1 - 300 / N) * 100) : 0;
    zoomEnd = 100;
  }
  // 记下这次由代码设定的窗口，供 saveZoomMem 判断变化来源
  zoomApplied = { start: zoomStart, end: zoomEnd };

  // 百分比布局：随容器高度自适应，永不溢出
  const n = activeSubs.length;
  const CFG = { 1: { h: 14, g: 2.0 }, 2: { h: 12, g: 2.0 },
                3: { h: 10.5, g: 2.0 }, 4: { h: 9.2, g: 2.2 } };
  const L = CFG[n] || { h: 0, g: 0 };
  const TOP = 4, BOTTOM = 4;
  const GLEFT = isMobile() ? 44 : 64;      // 手机屏窄，收窄左边距让 K 线有地方
  const GRIGHT = isMobile() ? 10 : 26;
  const mainH = n ? (100 - TOP - BOTTOM - L.h * n - L.g * (n + 1)) : 88;
  MAIN_PCT = mainH;   // 主图高度百分比，点击分时时用来判断是否落在主图内

  const grid = [], xAxis = [], yAxis = [], series = [], titles = [];
  const gridIdxAll = [];

  // 主图
  grid.push({ left: GLEFT, right: GRIGHT, top: TOP + '%', height: mainH + '%' });
  gridIdxAll.push(0);
  let yCursor = TOP + mainH + L.g;

  // 副图
  activeSubs.forEach((key, idx) => {
    const gi = idx + 1;
    grid.push({ left: GLEFT, right: GRIGHT, top: yCursor + '%', height: L.h + '%' });
    gridIdxAll.push(gi);
    titles.push({
      text: SUBS[key].label, left: GLEFT + 2, top: (yCursor - 2.4) + '%',
      textStyle: { fontSize: 11, color: T.muted, fontWeight: 500 },
    });
    yCursor += L.h + L.g;
  });

  // x 轴
  grid.length && grid.forEach((_, i) => {
    xAxis.push({
      type: 'category', data: dates, gridIndex: i, boundaryGap: true,
      axisLine: { lineStyle: { color: T.axis } }, axisTick: { show: false },
      axisLabel: { show: i === grid.length - 1, color: T.muted,
                   fontSize: isMobile() ? 9 : 10, hideOverlap: true },
      splitLine: { show: false }, axisPointer: { label: { show: false } },
    });
  });

  // y 轴：主图带刻度，副图也给刻度（不再隐藏）
  yAxis.push({
    gridIndex: 0, scale: true, position: 'left', splitNumber: 4,
    axisLabel: { color: T.muted, fontSize: isMobile() ? 9 : 10,
                 formatter: isMobile() ? (v => String(+v.toFixed(1))) : undefined },
    axisLine: { show: false }, axisTick: { show: false },
    splitLine: { lineStyle: { color: T.line } },
  });
  for (let i = 1; i < grid.length; i++) {
    const key = activeSubs[i - 1];
    const ax = {
      gridIndex: i, scale: true, position: 'left', splitNumber: 2,
      axisLabel: { color: T.muted, fontSize: isMobile() ? 8 : 9 },
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: T.lineSub } },
    };
    if (key === 'vol') {
      ax.axisLabel.formatter = v => (Math.abs(v) >= 1e4 ? (v / 1e4).toFixed(0) + '万' : String(v));
    }
    yAxis.push(ax);
  }

  // 主图 series：K线 + MA + BOLL
  series.push({
    name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0, data: d.ohlc,
    itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
  });
  [['ma5', 'MA5'], ['ma10', 'MA10'], ['ma20', 'MA20'], ['ma30', 'MA30'],
   ['ma60', 'MA60'], ['ma120', 'MA120']].forEach(([key, label]) => {
    series.push({
      name: label, type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: d.ma[key],
      showSymbol: false, lineStyle: { width: 1, color: C[key] }, itemStyle: { color: C[key] },
    });
  });
  [['upper', 'BOLL上轨', 'dashed'], ['mid', 'BOLL中轨', 'solid'], ['lower', 'BOLL下轨', 'dashed']]
    .forEach(([key, label, tp]) => {
      series.push({
        name: label, type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: d.boll[key],
        showSymbol: false, lineStyle: { width: 1, type: tp, color: key === 'mid' ? T.dim : T.bollEdge },
        itemStyle: { color: T.dim },
      });
    });

  // 买卖点标注（交易账本，开关在指标条右侧「买卖点」）
  const tser = buildTradeSeries(d);
  if (tser) series.push(tser);

  // 副图 series
  activeSubs.forEach((key, idx) => {
    const gi = idx + 1;
    const list = SUBS[key].build(d);
    const refs = SUBS[key].ref || [];
    list.forEach((s, si) => {
      const ser = Object.assign({}, s, { xAxisIndex: gi, yAxisIndex: gi });
      if (si === 0 && refs.length) {
        ser.markLine = {
          silent: true, symbol: 'none', animation: false,
          lineStyle: { color: C.ref, type: 'dashed', width: 1 },
          label: { show: false },
          data: refs.map(v => ({ yAxis: v })),
        };
      }
      series.push(ser);
    });
  });

  const option = {
    animation: false,
    backgroundColor: BG,
    title: titles,
    legend: {
      top: isMobile() ? 2 : 4, left: GLEFT, right: GRIGHT,
      itemGap: isMobile() ? 7 : 12,
      // 手机上只列常用几条，否则图例会换行挤占主图
      data: isMobile()
        ? ['MA5', 'MA10', 'MA20', 'BOLL上轨']
        : ['MA5', 'MA10', 'MA20', 'MA30', 'MA60', 'MA120', 'BOLL上轨', 'BOLL中轨', 'BOLL下轨'],
      itemWidth: isMobile() ? 11 : 14, itemHeight: 8,
      textStyle: { fontSize: isMobile() ? 10 : 11, color: T.legend },
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross', label: {
        backgroundColor: T.axis, borderColor: T.axisStrong, borderWidth: 1,
        color: T.text, fontSize: 11, padding: [3, 5],
      } }, confine: true,
      backgroundColor: T.tipBg, borderColor: T.axis,
      textStyle: { color: T.text, fontSize: 12 }, padding: [7, 10],
      extraCssText: 'box-shadow:0 6px 20px ' + T.tipShadow + ';border-radius:8px;z-index:50;max-width:' +
        (isMobile() ? '92vw' : '520px') + ';',
      formatter: tooltipFormatter(d),
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: grid,
    xAxis: xAxis,
    yAxis: yAxis,
    dataZoom: [
      { type: 'inside', xAxisIndex: gridIdxAll, start: zoomStart, end: zoomEnd,
        zoomOnMouseWheel: true,      // 滚轮 = 缩放
        moveOnMouseWheel: false,     // 滚轮不再平移
        moveOnMouseMove: true,       // 按住鼠标拖动 = 左右平移
        zoomOnPinch: true,           // 触控板双指捏合 = 缩放
        preventDefaultMouseMove: true },
      { type: 'slider', xAxisIndex: gridIdxAll, start: zoomStart, end: zoomEnd,
        bottom: 2, height: isMobile() ? 16 : 20, borderColor: T.axis,
        backgroundColor: T.panel, fillerColor: T.sliderFill,
        dataBackground: { lineStyle: { color: T.sliderDataLine }, areaStyle: { color: T.sliderDataArea } },
        selectedDataBackground: { lineStyle: { color: T.sliderSelLine }, areaStyle: { color: T.sliderSelArea } },
        handleStyle: { color: T.c2, borderColor: T.c2 },
        moveHandleStyle: { color: T.axisStrong },
        textStyle: { fontSize: 10, color: T.muted },
        brushSelect: false, moveHandleSize: 8 },
    ],
    series: series,
  };

  // 盘中每 5 秒刷一次：结构没变就只更新数据。
  // 全量 setOption(…, true) 会重建 1900 根蜡烛 + 15 条 series 并重置 dataZoom，
  // 既闪烁又会打断用户正在进行的缩放/拖动。
  if (patchOnly && chart && lastSeriesCount === series.length) {
    chart.setOption({
      xAxis: xAxis.map(x => ({ data: x.data })),
      series: series.map(s => ({ data: s.data })),
      tooltip: option.tooltip,          // formatter 闭包捕获了新的 d
    }, { lazyUpdate: true });
    return;
  }

  chart.setOption(option, true);
  lastSeriesCount = series.length;
}



/* ============================ 左侧自选列表 ============================ */
const watchListEl = document.getElementById('watch-list');
const watchEl = document.getElementById('watch');
const watchMaskEl = document.getElementById('watch-mask');
const watchToggleEl = document.getElementById('watch-toggle');
let watchCodes = [];

/* 手机上自选栏是抽屉：默认收起，点 ☰ 拉开 */
function openWatch() {
  watchEl.classList.add('open');
  watchMaskEl.classList.add('open');
}
function closeWatch() {
  watchEl.classList.remove('open');
  watchMaskEl.classList.remove('open');
}
function toggleWatch() {
  watchEl.classList.contains('open') ? closeWatch() : openWatch();
}
watchToggleEl.onclick = toggleWatch;
watchMaskEl.onclick = closeWatch;
// 屏幕变宽（旋转到横屏/放大窗口）时收起抽屉，避免遮住图表
window.addEventListener('resize', () => { if (!isMobile()) closeWatch(); });


async function loadWatch() {
  try {
    const r = await fetch('/api/watchlist');
    const d = await r.json();
    watchCodes = d.codes || [];
  } catch (e) { watchCodes = []; }
  await refreshWatch();
}

async function refreshWatch() {
  if (!watchCodes.length) {
    watchListEl.innerHTML = '<div class="w-empty">还没有自选股<br>点右上角 ＋ 加入</div>';
    return;
  }
  // 优先走实时行情；拿不到再退回本地 pkl（盘后/断网时仍有数据）
  try {
    const r = await fetch('/api/realtime?codes=' + encodeURIComponent(watchCodes.join(',')));
    const d = await r.json();
    if ((d.quotes || []).length) { renderWatch(d.quotes); return; }
  } catch (e) { /* 走降级 */ }
  try {
    const r = await fetch('/api/quotes?codes=' + encodeURIComponent(watchCodes.join(',')));
    const d = await r.json();
    renderWatch(d.quotes || []);
  } catch (e) { /* 忽略 */ }
}

async function saveWatch() {
  try {
    await fetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes: watchCodes }),
    });
  } catch (e) { /* 忽略 */ }
}

function renderWatch(quotes) {
  // 结构没变就只改数字：5 秒一刷，重建 DOM 会让 hover 时的删除按钮一直闪
  const cur = Array.from(watchListEl.querySelectorAll('.w-item')).map(e => e.dataset.code);
  if (cur.length && cur.length === quotes.length && cur.every((c, i) => c === quotes[i].code)) {
    quotes.forEach((q, i) => {
      const el = watchListEl.querySelectorAll('.w-item')[i];
      const px = (q.price != null) ? q.price : q.close;
      const pct = (q.pct != null) ? q.pct : 0;
      const col = pct >= 0 ? UP : DOWN;
      el.querySelector('.w-close').textContent = px.toFixed(2);
      const pe = el.querySelector('.w-pct');
      pe.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
      pe.style.color = col;
      el.classList.toggle('active', q.code === current.code);
    });
    return;
  }

  watchListEl.innerHTML = '';
  if (!quotes.length) {
    watchListEl.innerHTML = '<div class="w-empty">还没有自选股<br>点右上角 ＋ 加入</div>';
    return;
  }
  quotes.forEach(q => {
    const el = document.createElement('div');
    el.className = 'w-item' + (q.code === current.code ? ' active' : '');
    el.dataset.code = q.code;
    const px = (q.price != null) ? q.price : q.close;       // 实时接口给 price，本地 pkl 给 close
    const pct = (q.pct != null) ? q.pct : 0;
    const col = pct >= 0 ? UP : DOWN;
    el.innerHTML =
      '<div class="w-main"><div class="w-name">' + q.name + '</div>' +
      '<div class="w-sub">' + q.code + '</div></div>' +
      '<div class="w-right"><div class="w-close">' + px.toFixed(2) + '</div>' +
      '<div class="w-pct" style="color:' + col + '">' +
      (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%</div></div>' +
      '<button class="w-del" title="移出自选">×</button>';

    el.onclick = () => {
      if (isMobile()) closeWatch();       // 手机上选完就收起抽屉
      if (current.code === q.code) return;
      current.code = q.code;
      input.value = q.code + ' ' + q.name;
      load();
    };
    el.querySelector('.w-del').onclick = async ev => {
      ev.stopPropagation();
      watchCodes = watchCodes.filter(c => c !== q.code);
      await saveWatch();
      await refreshWatch();
    };
    watchListEl.appendChild(el);
  });
}

function markActive() {
  watchListEl.querySelectorAll('.w-item').forEach(el => {
    el.classList.toggle('active', el.dataset.code === current.code);
  });
}

document.getElementById('watch-add').onclick = async () => {
  if (!lastData) return;
  const code = lastData.code;
  const btn = document.getElementById('watch-add');
  if (watchCodes.includes(code)) {
    btn.textContent = '✓';
    setTimeout(() => { btn.textContent = '＋'; }, 900);
    return;
  }
  watchCodes.push(code);
  await saveWatch();
  await refreshWatch();
  btn.textContent = '✓';
  setTimeout(() => { btn.textContent = '＋'; }, 900);
};

/* ============================ 分时浮层（点击日K） ============================ */
const maskEl = document.getElementById('minute-mask');
const minBox = document.getElementById('minute-chart');
const minTip = document.getElementById('minute-tip');
const minTitle = document.getElementById('minute-title');
const minNums = document.getElementById('minute-nums');
let minChart = null;
let lastMinute = null;   // 最近一次打开的分时数据，切主题时重绘

function closeMinute() {
  stopMinTimer();
  maskEl.classList.remove('show');
  try { if (minChart) minChart.dispatchAction({ type: 'hideTip' }); } catch (e) { /* 忽略 */ }
}

/* 分时数据加载（silent=true 时用于盘中静默刷新，不显示 loading、失败也不清图） */
async function loadMinuteData(code, ymd, silent) {
  if (!silent) {
    minTip.textContent = '正在加载分时数据…';
    minTip.style.display = 'flex';
  }
  try {
    const r = await fetch('/api/minute?code=' + code + '&date=' + ymd);
    const txt = await r.text();
    if (!r.ok) {
      let msg = txt;
      try { msg = JSON.parse(txt).detail || txt; } catch (e) { /* 原样 */ }
      throw new Error(msg);
    }
    const d = JSON.parse(txt);
    lastMinute = d;
    minTip.style.display = 'none';
    const iso = ymd.slice(0, 4) + '-' + ymd.slice(4, 6) + '-' + ymd.slice(6, 8);
    minTitle.textContent = (d.name || code) + ' ' + code + ' · ' + iso +
      ' 分时（1分钟）' + (d.live ? ' · 实时' : '');
    renderMinute(d);
    return d;
  } catch (e) {
    if (!silent) {
      minChart.clear();
      minTip.textContent = '加载失败：' + e.message;
      minTip.style.display = 'flex';
    }
    return null;
  }
}

/* 盘中每 5 秒刷新当前分时（仅当日实时数据；历史日期不刷） */
let minTimer = null;
function stopMinTimer() {
  if (minTimer) { clearInterval(minTimer); minTimer = null; }
}
function startMinTimer() {
  stopMinTimer();
  if (!isTradingTime()) return;
  minTimer = setInterval(() => {
    if (document.hidden || !maskEl.classList.contains('show')) return;
    if (!lastMinute || !lastMinute.live) return;
    loadMinuteData(lastMinute.code, lastMinute.date, true);
  }, 5000);
}

async function openMinute(code, name, ymd) {
  maskEl.classList.add('show');
  // 清掉主图残留的 tooltip 与十字光标（遮罩覆盖后不会再触发 mousemove，需手动收）
  const killTip = () => {
    try {
      chart.dispatchAction({ type: 'updateAxisPointer', currTrigger: 'leave' });
      chart.dispatchAction({ type: 'hideTip' });
    } catch (e) { /* 无关紧要 */ }
  };
  killTip();
  requestAnimationFrame(killTip);
  if (!minChart) minChart = echarts.init(minBox);
  // 遮罩刚从 display:none 切过来，此刻容器还没 reflow，直接 resize 会读到 0 尺寸
  requestAnimationFrame(() => { if (minChart) minChart.resize(); });

  const iso = ymd.slice(0, 4) + '-' + ymd.slice(4, 6) + '-' + ymd.slice(6, 8);
  minTitle.textContent = name + ' ' + code + ' · ' + iso + ' 分时（1分钟）';
  minNums.innerHTML = '';

  await loadMinuteData(code, ymd, false);
  startMinTimer();
}

function renderMinute(d) {
  const base = d.prev_close;
  const up = d.pct >= 0;
  const col = up ? UP : DOWN;

  // 上下对称的涨跌幅范围，让价格轴与右侧百分比轴严格对齐
  let m = 0;
  d.price.forEach(p => { if (p != null) m = Math.max(m, Math.abs(p / base - 1) * 100); });
  m = Math.max(0.5, Math.ceil(m * 1.15 * 10) / 10);
  const yMin = base * (1 - m / 100), yMax = base * (1 + m / 100);

  const volColors = d.price.map((p, i) => {
    const prev = i > 0 ? d.price[i - 1] : base;
    return p >= prev ? UP : DOWN;
  });

  minNums.innerHTML = [
    ['开', d.day.open.toFixed(2), col],
    ['高', d.day.high.toFixed(2), UP],
    ['低', d.day.low.toFixed(2), DOWN],
    ['收', d.day.close.toFixed(2), col],
    ['涨跌幅', (d.pct >= 0 ? '+' : '') + d.pct.toFixed(2) + '%', col],
    ['成交量', (d.day.volume / 1e4).toFixed(2) + '万手', ''],
  ].map(([k, v, c]) => '<span>' + k + ' <b style="color:' + (c || T.text) + '">' + v + '</b></span>').join('');

  const option = {
    animation: false,
    backgroundColor: T.panel,
    legend: {
      top: 2, left: isMobile() ? 46 : 64, itemWidth: 14, itemHeight: 8, itemGap: 14,
      data: ['价格', '均价'],
      textStyle: { fontSize: 11, color: T.legend },
    },
    grid: isMobile()
      ? [{ left: 46, right: 46, top: 26, height: '61%' },
         { left: 46, right: 46, top: '76%', height: '16%' }]
      : [{ left: 64, right: 62, top: 28, height: '64%' },
         { left: 64, right: 62, top: '78%', height: '15%' }],
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross', label: {
        backgroundColor: T.axis, borderColor: T.axisStrong, borderWidth: 1,
        color: T.text, fontSize: 11, padding: [3, 5],
      } }, confine: true,
      backgroundColor: T.tipBg, borderColor: T.axis,
      textStyle: { color: T.text, fontSize: 12 }, padding: [7, 10],
      extraCssText: 'box-shadow:0 6px 20px ' + T.tipShadow + ';border-radius:8px;max-width:' +
        (isMobile() ? '90vw' : '360px') + ';',
      formatter: function (params) {
        const i = (Array.isArray(params) ? params[0] : params).dataIndex;
        const p = d.price[i], a = d.avg[i];
        if (p == null) return '';
        const pct = (p - base) / base * 100;
        const c = p >= base ? UP : DOWN;
        const vw = d.volume[i] == null ? '--'
          : (d.volume[i] / 100 >= 1e4 ? (d.volume[i] / 1e6).toFixed(2) + '万手'
                                      : (d.volume[i] / 100).toFixed(0) + '手');
        return '<div class="tt-head">' + d.times[i] + '</div>' +
          '<div class="tt-row">' + c2('价格', p.toFixed(2), c) +
          c2('涨跌幅', (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%', c) + '</div>' +
          '<div class="tt-row">' + c2('均价', a == null ? '--' : a.toFixed(3), T.c1) +
          c2('成交量', vw) + '</div>' +
          '<div class="tt-row">' + c2('成交额', humanAmt(d.amount[i] == null ? null : d.amount[i] / 1e4)) + '</div>';
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      { type: 'category', data: d.times, gridIndex: 0, boundaryGap: false,
        axisLabel: { show: false }, axisTick: { show: false },
        axisLine: { lineStyle: { color: T.axis } }, splitLine: { show: false },
        axisPointer: { label: { show: false } } },
      { type: 'category', data: d.times, gridIndex: 1, boundaryGap: false,
        axisTick: { show: false }, splitLine: { show: false },
        axisLine: { lineStyle: { color: T.axis } },
        axisLabel: { color: T.muted, fontSize: 10, interval: 29 } },
    ],
    yAxis: [
      { gridIndex: 0, min: yMin, max: yMax, splitNumber: 4,
        axisLabel: { fontSize: 10, color: T.muted, formatter: v => v.toFixed(2) },
        axisPointer: { label: { formatter: v => Number(v).toFixed(2) } },
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: T.line } } },
      { gridIndex: 0, position: 'right', min: -m, max: m, splitNumber: 4,
        axisLabel: {
          fontSize: 9, color: T.muted,
          formatter: v => (v > 0 ? '+' : '') + v.toFixed(1) + '%',
        },
        axisPointer: {
          label: { formatter: v => (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%' },
        },
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { show: false } },
      { gridIndex: 1, splitNumber: 1,
        axisLabel: { show: false }, axisLine: { show: false },
        axisTick: { show: false }, splitLine: { show: false } },
    ],
    series: [
      { name: '价格', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: d.price,
        showSymbol: false, lineStyle: { width: 1.4, color: col }, itemStyle: { color: col },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: up ? T.upArea : T.downArea },
            { offset: 1, color: T.areaFade },
          ]),
        },
        markLine: {
          silent: true, symbol: 'none', animation: false,
          lineStyle: { color: T.muted, type: 'dashed', width: 1 },
          label: { show: false }, data: [{ yAxis: base }],
        } },
      { name: '均价', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: d.avg,
        showSymbol: false, lineStyle: { width: 1.1, color: T.c1 }, itemStyle: { color: T.c1 } },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: d.volume,
        barMaxWidth: 3, itemStyle: { color: p => volColors[p.dataIndex] } },
    ],
  };
  minChart.setOption(option, true);
  minChart.resize();          // setOption 后按当前真实尺寸再校一次
}

document.getElementById('minute-close').onclick = closeMinute;
maskEl.addEventListener('click', e => { if (e.target === maskEl) closeMinute(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && maskEl.classList.contains('show')) closeMinute();
});

// 点击主图（不必精确点中蜡烛）→ 打开当日分时
// 用 zrender 原生 click：它内部已经做了拖拽判定，手势平移结束时不会误触发
function bindMinuteClick() {
  const zr = chart.getZr();
  let down = null;

  zr.on('mousedown', e => { down = [e.offsetX, e.offsetY]; });

  zr.on('click', e => {
    // 再兜一层位移判断：手指/鼠标抖动不算点击
    const thr = isMobile() ? 14 : 6;
    const moved = down &&
      (Math.abs(e.offsetX - down[0]) > thr || Math.abs(e.offsetY - down[1]) > thr);
    down = null;
    if (moved) return;
    if (current.period !== 'day' || !lastData) return;

    const H = chart.getHeight();
    const top = 0.04 * H, bottom = (0.04 + MAIN_PCT / 100) * H;
    if (e.offsetY < top || e.offsetY > bottom) return;   // 只响应主图区域

    const pt = chart.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY]);
    if (!pt || pt[0] == null) return;
    const i = Math.round(pt[0]);
    if (i < 0 || i >= lastData.dates.length) return;

    openMinute(lastData.code, lastData.name, lastData.dates[i].replace(/-/g, ''));
  });
}


/* ============================ 助手：选股 / 回测 ============================ */
const asMaskEl = document.getElementById('as-mask');
var asStrategies = [];
var asNavChart = null;
var lastBacktest = null;
var asPollTimer = null;

function asNum(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const v = String(el.value).trim();
  return v === '' ? null : Number(v);
}

function asSetStatus(pre, txt) {
  const el = document.getElementById('as-' + pre + '-status');
  if (el) el.textContent = txt || '';
}

function openAssistant() {
  asMaskEl.classList.add('show');
  if (!asStrategies.length) loadStrategies();
  if (asNavChart) setTimeout(() => asNavChart.resize(), 40);
  pmStartTimer();          // 模拟盘盘中自动刷新（只在 paper 页签 + 交易时段生效）
  // 深链：#fx / #因子表 → 打开助手并直接展开因子表
  if (/fx|因子/i.test(location.hash || '')) {
    setTimeout(() => {
      const b = document.getElementById('as-f-help');
      const box = document.getElementById('as-factors');
      if (b && box && !box.classList.contains('show')) b.click();
    }, 30);
  }
}

function closeAssistant() { asMaskEl.classList.remove('show'); pmStopTimer(); }

document.getElementById('assistant-btn').onclick = openAssistant;
document.getElementById('as-close').onclick = closeAssistant;
asMaskEl.onclick = ev => { if (ev.target === asMaskEl) closeAssistant(); };
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && asMaskEl.classList.contains('show')) closeAssistant();
});

function asTab(name) {
  document.querySelectorAll('.as-tabs button').forEach(x =>
    x.classList.toggle('active', x.dataset.tab === name));
  document.querySelectorAll('.as-pane').forEach(p =>
    p.classList.toggle('active', p.dataset.pane === name));
  if (name === 'backtest' && asNavChart) setTimeout(() => asNavChart.resize(), 40);
  if (name === 'paper') {
    if (pmChart) setTimeout(() => pmChart.resize(), 40);
    // 第一次切过来才拉列表；之后重算一次（净值可能已经变了）
    if (!pmListEl.options.length) pmLoadList();
    else if (pmListEl.value) pmLoad(pmListEl.value);
  }
}

document.querySelectorAll('.as-tabs button').forEach(b => {
  b.onclick = () => asTab(b.dataset.tab);
});

/* ---------- 策略列表（来自 strategy 表，库挂了就从代码注册表生成） ---------- */
const SELECT_STRATEGY = '小市值反转';   // 选股页只留这一个内置策略（其余走公式策略）
let lastSelect = null;                  // 最近一次选股结果，供「回测 / 模拟盘」串联
let pickStrategy = null;                // 记住选股下拉的选择，刷新列表后不丢

async function loadStrategies(keepSel) {
  let list = [];
  try {
    const r = await fetch('/api/assistant/strategies');
    const d = await r.json();
    list = d.strategies || [];
    if (!d.engine) asSetStatus('s', '回测引擎不可用：' + (d.engine_error || ''));
  } catch (e) {
    asSetStatus('s', '读取策略失败：' + e.message);
  }
  asStrategies = list;
  if (!list.length) return;

  const mkOpts = arr => arr.map(s =>
    '<option value="' + s.name + '">' + s.name + (s.kind === 'expr' ? ' ⟨公式⟩' : '') + '</option>'
  ).join('');

  const bSel = document.getElementById('as-b-strategy');
  const sSel = document.getElementById('as-s-strategy');
  bSel.innerHTML = mkOpts(list);
  const bdef = list.find(s => s.name === '小市值反转低波') || list[0];
  bSel.value = bdef.name;
  applyStrategyParams(bdef, 'b');
  bSel.onchange = () => applyStrategyParams(list.find(s => s.name === bSel.value), 'b');

  // 选股页：只留「小市值反转」+ 用户自己存的公式策略
  const sList = list.filter(s => s.name === SELECT_STRATEGY || s.kind === 'expr');
  const use = sList.length ? sList : list;
  sSel.innerHTML = mkOpts(use);
  const want = (keepSel && use.some(s => s.name === keepSel)) ? keepSel
    : (pickStrategy && use.some(s => s.name === pickStrategy)) ? pickStrategy
      : (use.find(s => s.name === SELECT_STRATEGY) || use[0]).name;
  sSel.value = want;
  pickStrategy = want;
  applyStrategyParams(use.find(s => s.name === want), 's');
  sSel.onchange = () => {
    pickStrategy = sSel.value;
    applyStrategyParams(list.find(s => s.name === sSel.value), 's');
  };
}

function applyStrategyParams(st, pre) {
  if (!st) return;
  const p = st.params || {};
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el && v !== null && v !== undefined) el.value = v;
  };
  if (pre === 's') {
    set('as-s-topn', p.top_n);
    set('as-s-amt', p.min_amt);
    set('as-s-price', p.min_price);
    set('as-s-pct', p.max_pct);
  } else {
    set('as-b-topn', p.top_n);
    set('as-b-hold', p.hold_days);
    if (p.cost !== null && p.cost !== undefined) set('as-b-cost', +(p.cost * 100).toFixed(2));
    set('as-b-start', p.start);
    set('as-b-amt', p.min_amt);
    set('as-b-price', p.min_price);
    set('as-b-pct', p.max_pct);
  }
  asSetStatus(pre, st.desc ? st.desc : '');
}

/* ---------- 公式策略：因子表 / 保存 ---------- */
let fxData = null;          // {factors:[{name,base,doc,cat,z}], cats:[], examples:[]}
let fxZMode = true;         // 插入时是否带 z_ 前缀（标准化，默认开）
let fxKeyword = '';

const fxExprEl = () => document.getElementById('as-f-expr');
const fxBoxEl = () => document.getElementById('as-factors');

/** 光标处插入因子名（替换选中的内容），插完把焦点还回输入框。 */
function fxInsert(name) {
  const el = fxExprEl();
  const s = el.selectionStart ?? el.value.length;
  const e = el.selectionEnd ?? s;
  const before = el.value.slice(0, s);
  const after = el.value.slice(e);
  // 前后自动补空格，免得连成 z_SIZEz_REV20
  const padL = before && !/[\s(]$/.test(before) ? ' ' : '';
  const padR = after && !/^[\s)]/.test(after) ? ' ' : '';
  el.value = before + padL + name + padR + after;
  const pos = before.length + padL.length + name.length + padR.length;
  el.focus();
  try { el.setSelectionRange(pos, pos); } catch (err) { /* 忽略 */ }
  fxMarkUsed();
}

/** 表达式里已经出现的因子 → 高亮，方便看还差什么。 */
function fxMarkUsed() {
  const used = new Set((fxExprEl().value.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []));
  fxBoxEl().querySelectorAll('.fxchip').forEach(c => {
    c.classList.toggle('used', used.has(c.dataset.name));
  });
}

function fxRender() {
  const box = fxBoxEl();
  const d = fxData;
  if (!d) return;
  const kw = fxKeyword.trim().toLowerCase();
  const hit = f => !kw || f.base.toLowerCase().includes(kw) || f.doc.toLowerCase().includes(kw);
  // 只列原始名（base），z_ 前缀由顶部开关决定，避免 56 个名字重复两遍
  const bases = [];
  const seen = new Set();
  d.factors.forEach(f => { if (!seen.has(f.base)) { seen.add(f.base); bases.push(f); } });

  const rows = [];
  d.cats.forEach(cat => {
    const list = bases.filter(f => f.cat === cat && hit(f));
    if (!list.length) return;
    rows.push(
      '<div class="fx-group"><div class="fx-cat">' + cat + '</div><div class="fx-list">' +
      list.map(f => {
        const nm = fxZMode ? 'z_' + f.base : f.base;
        return '<span class="fxchip" data-name="' + nm + '" title="点击插入 ' + nm +
          (f.doc ? '（' + f.doc + '）' : '') + '">' +
          '<code>' + (fxZMode ? 'z_' : '') + f.base + '</code>' +
          (f.doc ? '<span class="d">' + f.doc + '</span>' : '') + '</span>';
      }).join('') +
      '</div></div>');
  });

  const exs = d.examples.filter(e => !kw || e.name.toLowerCase().includes(kw) ||
    e.expr.toLowerCase().includes(kw));
  const tail = exs.length
    ? '<div class="fx-group fx-ex"><div class="fx-cat">例子</div><div class="fx-list">' +
      exs.map(e => '<span class="fxex" data-expr="' + e.expr + '" data-name="' + e.name + '">' +
        '<b>' + e.name + '</b><code>' + e.expr + '</code></span>').join('') +
      '</div></div>'
    : '';

  box.innerHTML =
    '<div class="fx-head">' +
      '<span class="fx-title">因子表 <em>' + bases.length + '</em></span>' +
      '<span class="fx-hint">点一下插入到表达式</span>' +
      '<div class="fx-mode">' +
        '<button data-z="1" class="' + (fxZMode ? 'on' : '') + '">z_ 标准化</button>' +
        '<button data-z="0" class="' + (fxZMode ? '' : 'on') + '">原始值</button>' +
      '</div>' +
      '<input class="fx-search" placeholder="搜索因子…" value="' + fxKeyword.replace(/"/g, '&quot;') + '">' +
    '</div>' +
    (rows.length ? rows.join('') : '<div class="fx-empty">没有匹配「' + fxKeyword + '」的因子</div>') +
    tail;

  // 交互绑定
  box.querySelectorAll('.fxchip').forEach(c => {
    c.onclick = () => fxInsert(c.dataset.name);
  });
  box.querySelectorAll('.fxex').forEach(c => {
    c.onclick = () => {
      fxExprEl().value = c.dataset.expr;
      const nameEl = document.getElementById('as-f-name');
      if (!nameEl.value.trim()) nameEl.value = c.dataset.name;
      fxMarkUsed();
      fxExprEl().focus();
    };
  });
  box.querySelectorAll('.fx-mode button').forEach(b => {
    b.onclick = () => {
      fxZMode = b.dataset.z === '1';
      fxRender();
    };
  });
  const se = box.querySelector('.fx-search');
  if (se) {
    se.oninput = () => {
      fxKeyword = se.value;
      const caret = se.selectionStart;
      fxRender();
      const s2 = fxBoxEl().querySelector('.fx-search');
      s2.focus();
      try { s2.setSelectionRange(caret, caret); } catch (err) { /* 忽略 */ }
    };
  }
  fxMarkUsed();
}

async function loadFactors() {
  if (fxData) return fxRender();
  const box = fxBoxEl();
  box.innerHTML = '<div class="fx-empty">读取中…</div>';
  try {
    const r = await fetch('/api/assistant/factors');
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '读取失败');
    fxData = { factors: d.factors || [], cats: d.cats || [], examples: d.examples || [] };
    fxRender();
  } catch (e) {
    box.innerHTML = '<div class="fx-empty">因子表读取失败：' + e.message + '</div>';
  }
}

document.getElementById('as-f-help').onclick = async () => {
  const box = fxBoxEl();
  const btn = document.getElementById('as-f-help');
  const show = !box.classList.contains('show');
  box.classList.toggle('show', show);
  btn.textContent = show ? '收起' : '因子表';
  if (show) await loadFactors();
};

fxExprEl().addEventListener('input', fxMarkUsed);

document.getElementById('as-f-save').onclick = async () => {
  const btn = document.getElementById('as-f-save');
  const name = document.getElementById('as-f-name').value.trim();
  const expr = document.getElementById('as-f-expr').value.trim();
  if (!name) return asSetStatus('s', '❌ 先给策略起个名字');
  if (!expr) return asSetStatus('s', '❌ 先填因子表达式');
  btn.disabled = true;
  asSetStatus('s', '保存中…');
  try {
    const r = await fetch('/api/assistant/strategy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, expr }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '保存失败');
    await loadStrategies(d.name);          // 刷新下拉并选中新策略
    document.getElementById('as-f-name').value = '';
    asSetStatus('s', '✅ 已保存策略「' + d.name + '」：' + d.expr);
  } catch (e) {
    asSetStatus('s', '❌ ' + e.message);
  } finally {
    btn.disabled = false;
  }
};

/* ---------- 选股 → 回测 → 模拟盘 串联 ---------- */
function selCodes() {
  return (lastSelect && lastSelect.rows || []).map(x => x.code);
}

document.getElementById('as-s-tobt').onclick = () => {
  const s = lastSelect;
  if (!s) return asSetStatus('s', '先跑一次选股');
  asTab('backtest');
  const bSel = document.getElementById('as-b-strategy');
  if (s.strategy && [].some.call(bSel.options, o => o.value === s.strategy)) {
    bSel.value = s.strategy;
  }
  const setv = (id, v) => {
    const el = document.getElementById(id);
    if (el && v !== null && v !== undefined) el.value = v;
  };
  setv('as-b-topn', s.top_n);
  const f = s.filters || {};
  setv('as-b-amt', f.min_amt);
  setv('as-b-price', f.min_price);
  setv('as-b-pct', f.max_pct);
  asSetStatus('b', '来自 ' + s.date + ' 的选股（' + s.rows.length + ' 只），参数已带入，开始回测…');
  document.getElementById('as-b-run').click();
};

async function pmFromSelection(btn) {
  const s = lastSelect;
  if (!s || !s.rows || !s.rows.length) {
    pmSetStatus('❌ 没有可用的选股名单，先在「选股」页跑一次');
    return;
  }
  btn.disabled = true;
  pmSetStatus('创建中…（买入日自动取选股日的下一个交易日）');
  try {
    const r = await fetch('/api/paper/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: s.strategy + ' · ' + s.date.slice(4),
        strategy: s.strategy,
        signal_date: s.date,
        capital: asNum('pm-cap') || 100000,
        hold_days: asNum('pm-hold') || 20,
        codes: s.rows.map(x => x.code),
        names: s.rows.reduce((m, x) => { m[x.code] = x.name; return m; }, {}),
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '创建失败');
    asTab('paper');
    await pmLoadList(d.id);
    pmSetStatus('已用 ' + s.date + ' 的选股结果建组合 #' + d.id + '（T+1 收盘买入，持有 ' +
      (asNum('pm-hold') || 20) + ' 天）');
  } catch (e) {
    pmSetStatus('❌ ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

document.getElementById('as-s-topm').onclick = ev => pmFromSelection(ev.currentTarget);
document.getElementById('as-b-topm').onclick = ev => pmFromSelection(ev.currentTarget);
document.getElementById('as-b-back').onclick = () => asTab('select');

/* ---------- 选股 ---------- */
document.getElementById('as-s-run').onclick = async () => {
  const btn = document.getElementById('as-s-run');
  const strategy = document.getElementById('as-s-strategy').value;
  if (!strategy) return asSetStatus('s', '没有可用策略');
  const body = {
    strategy,
    top_n: asNum('as-s-topn'),
    min_amt: asNum('as-s-amt'),
    min_price: asNum('as-s-price'),
    max_pct: asNum('as-s-pct'),
  };
  const dt = document.getElementById('as-s-date').value.trim();
  if (dt) body.date = dt;

  btn.disabled = true;
  asSetStatus('s', '选股中…（约 5 秒）');
  try {
    const r = await fetch('/api/assistant/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || '请求失败');
    renderSelectResult(res);
    asSetStatus('s', res.date + ' · 候选池 ' + res.pool + ' 只 · 耗时 ' +
      res.elapsed + 's · ' + (res.db_msg || ''));
  } catch (e) {
    asSetStatus('s', '❌ ' + e.message);
  } finally {
    btn.disabled = false;
  }
};

function renderSelectResult(res) {
  const emptyEl = document.getElementById('as-s-empty');
  const tbl = document.getElementById('as-s-table');
  const tb = tbl.querySelector('tbody');
  const rows = res.rows || [];
  if (!rows.length) {
    emptyEl.style.display = 'block';
    emptyEl.innerHTML = '候选池为空<br>可能是数据没更新，或者过滤条件太严';
    tbl.style.display = 'none';
    document.getElementById('as-s-actions').classList.remove('show');
    lastSelect = null;
    return;
  }
  emptyEl.style.display = 'none';
  tbl.style.display = '';
  tb.innerHTML = rows.map(r => {
    const pc = r.pct >= 0 ? 'pos' : 'neg';
    const rev = r.rev20 == null ? '--' : r.rev20.toFixed(2);
    const vol = r.vol20 == null ? '--' : r.vol20.toFixed(2);
    return '<tr data-code="' + r.code + '" data-name="' + r.name + '">' +
      '<td>' + r.rank + '</td>' +
      '<td class="c-code">' + r.code + '</td>' +
      '<td class="c-name">' + r.name + '</td>' +
      '<td>' + r.score.toFixed(2) + '</td>' +
      '<td>' + r.close.toFixed(2) + '</td>' +
      '<td class="' + pc + '">' + r.pct.toFixed(2) + '</td>' +
      '<td class="' + (r.rev20 >= 0 ? 'pos' : 'neg') + '">' + rev + '</td>' +
      '<td>' + vol + '</td>' +
      '<td>' + r.mktcap.toFixed(1) + '</td>' +
      '<td>' + r.turn.toFixed(2) + '</td>' +
      '<td>' + r.amt.toFixed(2) + '</td>' +
      '<td><button class="add-w" data-add="' + r.code + '">自选</button></td>' +
      '</tr>';
  }).join('');

  tb.querySelectorAll('tr').forEach(tr => {
    tr.onclick = ev => {
      if (ev.target.dataset.add) return;       // 点「自选」按钮不切换股票
      current.code = tr.dataset.code;
      input.value = tr.dataset.code + ' ' + tr.dataset.name;
      closeAssistant();
      load();
    };
  });
  tb.querySelectorAll('.add-w').forEach(b => {
    b.onclick = async ev => {
      ev.stopPropagation();
      const code = b.dataset.add;
      if (!watchCodes.includes(code)) {
        watchCodes.push(code);
        await saveWatch();
        await refreshWatch();
      }
      b.textContent = '已加';
      b.disabled = true;
    };
  });

  // 记住这次选股，供「用这批股回测 / 放进模拟盘」使用
  lastSelect = {
    date: res.date,
    strategy: res.strategy,
    rows: res.rows,
    filters: res.filters || {},
    top_n: res.top_n || rows.length,
    universe: res.universe || '',
  };
  document.getElementById('as-s-pickinfo').textContent =
    res.date + ' · ' + res.strategy + ' · ' + rows.length + ' 只 · ' + (res.universe || '');
  document.getElementById('as-s-actions').classList.add('show');
}

/* ---------- 回测 ---------- */
document.getElementById('as-b-run').onclick = async () => {
  const btn = document.getElementById('as-b-run');
  const strategy = document.getElementById('as-b-strategy').value;
  if (!strategy) return asSetStatus('b', '没有可用策略');
  const costPct = asNum('as-b-cost');
  const body = {
    strategy,
    top_n: asNum('as-b-topn'),
    hold_days: asNum('as-b-hold'),
    cost: costPct == null ? null : costPct / 100,
    start: document.getElementById('as-b-start').value.trim() || null,
    min_amt: asNum('as-b-amt'),
    min_price: asNum('as-b-price'),
    max_pct: asNum('as-b-pct'),
  };

  btn.disabled = true;
  document.getElementById('as-b-empty').style.display = 'none';
  document.getElementById('as-b-result').style.display = 'none';
  asSetStatus('b', '提交任务…');
  try {
    const r = await fetch('/api/assistant/backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || '提交失败');
    asSetStatus('b', '回测中…（全样本约 40~60 秒）');
    pollJob(res.job_id);
  } catch (e) {
    asSetStatus('b', '❌ ' + e.message);
    btn.disabled = false;
  }
};

async function pollJob(jobId) {
  clearTimeout(asPollTimer);
  try {
    const r = await fetch('/api/assistant/backtest/' + jobId);
    const j = await r.json();
    if (j.status === 'running') {
      asSetStatus('b', '回测中… 已 ' + j.elapsed + 's（读 1.1G 缓存 + 算因子，请稍候）');
      asPollTimer = setTimeout(() => pollJob(jobId), 1500);
      return;
    }
    document.getElementById('as-b-run').disabled = false;
    if (j.status === 'error') {
      asSetStatus('b', '❌ ' + ((j.result && j.result.error) || '回测失败'));
      return;
    }
    renderBacktest(j.result);
    asSetStatus('b', '完成 · 耗时 ' + j.result.elapsed + 's' +
      (j.result.run_id ? ' · 已存 backtest_run #' + j.result.run_id : '') +
      (j.result.db_error ? ' · 写库失败：' + j.result.db_error : ''));
  } catch (e) {
    asSetStatus('b', '❌ 轮询失败：' + e.message);
    document.getElementById('as-b-run').disabled = false;
  }
}

function asPct(x) {
  if (x === null || x === undefined || isNaN(x)) return '--';
  return (x * 100).toFixed(2) + '%';
}

function renderBacktest(res) {
  lastBacktest = res;
  document.getElementById('as-b-empty').style.display = 'none';
  document.getElementById('as-b-result').style.display = 'block';
  const m = res.metrics || {};
  const cls = v => (v > 0 ? 'pos' : (v < 0 ? 'neg' : ''));
  const cards = [
    ['累计收益', asPct(m.total_return), cls(m.total_return)],
    ['年化', asPct(m.annual_return), cls(m.annual_return)],
    ['最大回撤', asPct(m.max_drawdown), 'neg'],
    ['期胜率', asPct(m.win_rate), ''],
    ['10万→', Math.round(m.final_capital || 0).toLocaleString(), ''],
    ['调仓期数', m.periods || 0, ''],
  ];
  document.getElementById('as-b-metrics').innerHTML = cards.map(
    ([k, v, c]) => '<div class="as-metric"><div class="k">' + k +
      '</div><div class="v ' + c + '">' + v + '</div></div>').join('');

  const p = res.params || {};
  document.getElementById('as-b-note').textContent =
    (res.name || res.strategy) + ' · ' + (res.universe || '') +
    ' · TOP' + p.top_n + ' / 持有' + p.hold_days + '天 / 成本' +
    ((p.cost || 0) * 100).toFixed(2) + '%';

  const y = res.yearly || {};
  const yn = res.yearly_n || {};
  const ym = res.yearly_mdd || {};
  document.getElementById('as-b-year').innerHTML =
    '<table><thead><tr><th>年份</th><th>期数</th><th>收益（扣成本）</th><th>年内回撤</th></tr></thead><tbody>' +
    Object.keys(y).sort().map(k =>
      '<tr><td>' + k + '</td><td>' + (yn[k] || '') + '</td>' +
      '<td class="' + (y[k] >= 0 ? 'pos' : 'neg') + '">' + asPct(y[k]) + '</td>' +
      '<td class="neg">' + asPct(ym[k]) + '</td></tr>').join('') +
    '</tbody></table>';

  // 回测跑完：如果是从选股发起的，就能直接把这批票放进模拟盘
  const linked = !!(lastSelect && lastSelect.strategy === res.strategy);
  document.getElementById('as-b-actions').classList.add('show');
  document.getElementById('as-b-topm').style.display = linked ? '' : 'none';
  document.getElementById('as-b-pickinfo').textContent = linked
    ? ('配合 ' + lastSelect.date + ' 的选股名单（' + lastSelect.rows.length + ' 只）建立模拟盘')
    : '这次回测没有关联的选股名单 —— 先「选股 → 用这批股回测」就能串起来';

  renderAsNav();
}

function renderAsNav() {
  if (!lastBacktest) return;
  const nav = lastBacktest.nav || [];
  const el = document.getElementById('as-nav');
  if (!nav.length || !el) return;
  if (!asNavChart) asNavChart = echarts.init(el);
  asNavChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: isMobile() ? 46 : 64, right: isMobile() ? 12 : 20, top: 16, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: T.tipBg, borderColor: T.axis,
      textStyle: { color: T.text, fontSize: 11.5 },
      formatter: ps => {
        const it = ps[0];
        return it.axisValue + '<br/>资产 ' + Math.round(it.value).toLocaleString() + ' 元';
      },
    },
    xAxis: {
      type: 'category', data: nav.map(x => x.d), boundaryGap: false,
      axisLine: { lineStyle: { color: T.axis } },
      axisLabel: { color: T.muted, fontSize: 10.5 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', scale: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        color: T.muted, fontSize: 10.5,
        formatter: v => (v / 10000).toFixed(1) + '万',
      },
      splitLine: { lineStyle: { color: T.line } },
    },
    series: [{
      type: 'line', data: nav.map(x => x.v), showSymbol: false,
      lineStyle: { width: 1.8, color: T.c2 },
      itemStyle: { color: T.c2 },
      areaStyle: { color: 'rgba(88,166,255,.14)' },
    }],
  }, true);
  asNavChart.resize();
}
window.__asRenderNav = renderAsNav;

/* ============================ 模拟盘 ============================ */
const pmListEl = document.getElementById('pm-list');
const pmNavEl = document.getElementById('pm-nav');
let pmChart = null;
let lastPaper = null;
let pmTimer = null;
let pmRefreshing = false;

function pmSetStatus(t) {
  const el = document.getElementById('pm-status');
  if (el) el.textContent = t || '';
}

function pmMoney(v, dg) {
  if (v == null || isNaN(v)) return '--';
  return Number(v).toLocaleString('zh-CN', {
    minimumFractionDigits: dg || 0, maximumFractionDigits: dg || 0,
  });
}

function pmSigned(x, dg) {
  if (x == null || isNaN(x)) return ['--', ''];
  const s = (x > 0 ? '+' : '') + Number(x).toFixed(dg == null ? 2 : dg);
  return [s, x > 0 ? 'pos' : (x < 0 ? 'neg' : '')];
}

async function pmLoadList(selectId) {
  try {
    const r = await fetch('/api/paper/list');
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '读取失败');
    const list = d.portfolios || [];
    if (!list.length) {
      pmSetStatus('还没有模拟盘 — 填买入日 + 代码，点「建模拟盘」');
      return;
    }
    pmListEl.innerHTML = list.map(p => {
      const [, c] = pmSigned(p.cur_return);
      const ret = p.cur_return == null ? '--'
        : (p.cur_return > 0 ? '+' : '') + p.cur_return.toFixed(2) + '%';
      const st = p.status === 'done' ? '已到期' : ('第 ' + (p.days_held || 0) + ' 天');
      return '<option value="' + p.id + '">' + p.name + ' · ' + p.buy_date +
        ' · ' + st + ' · ' + ret + '</option>';
    }).join('');
    const want = selectId || (lastPaper ? lastPaper.id : null);
    const hit = list.find(x => x.id === want) || list[0];
    pmListEl.value = String(hit.id);
    await pmLoad(hit.id);
  } catch (e) {
    pmSetStatus('❌ ' + e.message);
  }
}

async function pmLoad(id) {
  try {
    const r = await fetch('/api/paper/' + id);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '读取失败');
    pmRender(d);
  } catch (e) {
    pmSetStatus('❌ ' + e.message);
  }
}

function pmRender(d) {
  lastPaper = d;
  document.getElementById('pm-empty').style.display = 'none';
  document.getElementById('pm-result').style.display = 'block';
  const m = d.metrics || {};
  const done = m.status === 'done';

  const cards = [
    ['当前净值', pmMoney(m.current_value) + ' 元', ''],
    ['累计收益', ...pmSigned(m.cur_return)],
    ['盈亏', (m.cur_pnl > 0 ? '+' : '') + pmMoney(m.cur_pnl) + ' 元',
      m.cur_pnl > 0 ? 'pos' : (m.cur_pnl < 0 ? 'neg' : '')],
    ['最大回撤', (m.max_drawdown || 0).toFixed(2) + '%', 'neg'],
    ['已持有', (m.days_held || 0) + ' / ' + d.hold_days + ' 天', ''],
    done
      ? ['到期收益', ...pmSigned(m.end_return)]
      : ['到期日', m.end_date || ('还剩 ' + (m.days_left || 0) + ' 天'), ''],
  ];
  document.getElementById('pm-metrics').innerHTML = cards.map(
    ([k, v, c]) => '<div class="as-metric"><div class="k">' + k +
      '</div><div class="v ' + (c || '') + '">' + v + '</div></div>').join('');

  const tag = done
    ? '<span class="pm-tag done">已到期</span>'
    : '<span class="pm-tag">持仓中 · 还剩 ' + (m.days_left || 0) + ' 个交易日</span>';
  const live = m.live ? '<span class="pm-tag">含今日实时价</span>' : '';
  document.getElementById('pm-note').innerHTML =
    d.name + ' · ' + (d.strategy || '—') + ' · ' + d.buy_date + ' 收盘买入' +
    ' · ' + d.positions.length + ' 只等权 · 本金 ' + pmMoney(d.capital) + ' 元 · 余现金 ' +
    pmMoney(d.cash) + ' 元（整手取整）' + tag + live;

  pmRenderChart();

  // 持仓明细
  document.getElementById('pm-pos').innerHTML =
    '<table><thead><tr><th>#</th><th>名称</th><th>买入价</th><th>现价</th>' +
    '<th>收益</th><th>股数</th><th>成本</th><th>市值</th><th>盈亏</th><th>权重</th>' +
    '</tr></thead><tbody>' +
    d.positions.map(p => {
      const [rs, rc] = pmSigned(p.ret);
      return '<tr><td>' + p.rank + '</td>' +
        '<td>' + (p.name || '') + ' <span class="c-code">' + p.code + '</span></td>' +
        '<td>' + p.buy_price.toFixed(2) + '</td>' +
        '<td>' + (p.last_price == null ? '--' : p.last_price.toFixed(2)) + '</td>' +
        '<td class="' + rc + '">' + rs + '%</td>' +
        '<td>' + pmMoney(p.shares) + '</td>' +
        '<td>' + pmMoney(p.cost) + '</td>' +
        '<td>' + pmMoney(p.mv) + '</td>' +
        '<td class="' + (p.pnl >= 0 ? 'pos' : 'neg') + '">' +
        (p.pnl > 0 ? '+' : '') + pmMoney(p.pnl) + '</td>' +
        '<td>' + (p.weight == null ? '--' : p.weight.toFixed(1)) + '%</td></tr>';
    }).join('') + '</tbody></table>';

  // 逐日明细（倒序，最近的在上面）
  const rows = (d.nav || []).slice().reverse();
  document.getElementById('pm-daily').innerHTML =
    '<table><thead><tr><th>日期</th><th>净值</th><th>当日</th><th>累计</th></tr></thead><tbody>' +
    rows.map(x => {
      const [ps, pc] = pmSigned(x.pct);
      const [cs, cc] = pmSigned(x.cum);
      return '<tr><td>' + x.d + (x.live ? ' <span class="pm-tag">实时</span>' : '') + '</td>' +
        '<td>' + pmMoney(x.v, 0) + '</td>' +
        '<td class="' + pc + '">' + ps + '%</td>' +
        '<td class="' + cc + '">' + cs + '%</td></tr>';
    }).join('') + '</tbody></table>';

  const lastNav = (d.nav || []).slice(-1)[0];
  pmSetStatus(d.name + ' · 最新 ' + (lastNav ? lastNav.d : '') +
    (m.live ? '（含今日实时）' : '') + ' · 共 ' + (d.nav || []).length + ' 个交易日');
}

function pmRenderChart() {
  if (!lastPaper || !pmNavEl) return;
  const nav = lastPaper.nav || [];
  if (!nav.length) return;
  if (!pmChart) {
    pmChart = echarts.init(pmNavEl);
    // 面板从 display:none 切过来时容器尺寸可能还没稳定，跟一下尺寸变化
    if (window.ResizeObserver) {
      new ResizeObserver(() => { if (pmChart) pmChart.resize(); }).observe(pmNavEl);
    }
  }
  const base = lastPaper.capital;
  pmChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: isMobile() ? 52 : 70, right: isMobile() ? 26 : 24, top: 24, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: T.tipBg, borderColor: T.axis,
      textStyle: { color: T.text, fontSize: 11.5 },
      formatter: ps => {
        const it = ps[0];
        const p = nav[it.dataIndex] || {};
        const s = (v) => (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%';
        return it.axisValue + '<br/>净值 ' + pmMoney(it.value) + ' 元<br/>' +
          '当日 ' + s(p.pct || 0) + ' · 累计 ' + s(p.cum || 0);
      },
    },
    xAxis: {
      type: 'category', data: nav.map(x => x.d), boundaryGap: false,
      axisLine: { lineStyle: { color: T.axis } },
      axisLabel: { color: T.muted, fontSize: 10.5, formatter: v => v.slice(5) },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', scale: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        color: T.muted, fontSize: 10.5,
        formatter: v => (v / 10000).toFixed(1) + '万',
      },
      splitLine: { lineStyle: { color: T.line } },
    },
    series: [{
      type: 'line', data: nav.map(x => x.v), showSymbol: nav.length < 30,
      symbolSize: 5,
      lineStyle: { width: 1.8, color: T.c2 },
      itemStyle: { color: T.c2 },
      areaStyle: { color: 'rgba(88,166,255,.14)' },
      markLine: {
        silent: true, symbol: 'none',
        label: {
          formatter: '本金', position: 'insideEndTop',
          color: T.muted, fontSize: 10,
        },
        lineStyle: { color: T.muted, type: 'dashed', width: 1 },
        data: [{ yAxis: base }],
      },
    }],
  }, true);
  pmChart.resize();
  requestAnimationFrame(() => { if (pmChart) pmChart.resize(); });
}
window.__pmRender = pmRenderChart;

function pmStopTimer() { clearInterval(pmTimer); pmTimer = null; }
function pmStartTimer() {
  pmStopTimer();
  pmTimer = setInterval(() => {
    if (!pmListEl.value || !isTradingTime() || document.hidden) return;
    if (!document.querySelector('.as-pane[data-pane="paper"]').classList.contains('active')) return;
    if (pmRefreshing) return;
    pmRefreshing = true;
    pmLoad(pmListEl.value).finally(() => { pmRefreshing = false; });
  }, 10000);
}

pmListEl.onchange = () => pmLoad(pmListEl.value);

document.getElementById('pm-new').onclick = async () => {
  const btn = document.getElementById('pm-new');
  const codes = document.getElementById('pm-codes').value
    .split(/[,，\s、]+/).map(s => s.trim()).filter(Boolean);
  if (!codes.length) return pmSetStatus('❌ 先填股票代码（逗号分隔）');
  const body = {
    name: document.getElementById('pm-date').value.trim()
      ? '模拟盘 · ' + document.getElementById('pm-date').value.trim() : null,
    buy_date: document.getElementById('pm-date').value.trim(),
    capital: asNum('pm-cap'),
    hold_days: asNum('pm-hold'),
    codes,
  };
  if (!body.buy_date) return pmSetStatus('❌ 先填买入日（YYYYMMDD）');
  btn.disabled = true;
  pmSetStatus('创建中…');
  try {
    const r = await fetch('/api/paper/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || '创建失败');
    await pmLoadList(res.id);
  } catch (e) {
    pmSetStatus('❌ ' + e.message);
  } finally {
    btn.disabled = false;
  }
};

document.getElementById('pm-del').onclick = async () => {
  const id = pmListEl.value;
  if (!id) return;
  if (!confirm('删除这个模拟盘组合？（不影响任何真实数据）')) return;
  try {
    const r = await fetch('/api/paper/' + id, { method: 'DELETE' });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || '删除失败');
    lastPaper = null;
    pmListEl.innerHTML = '';
    document.getElementById('pm-result').style.display = 'none';
    document.getElementById('pm-empty').style.display = 'block';
    pmSetStatus('已删除');
    await pmLoadList();
  } catch (e) {
    pmSetStatus('❌ ' + e.message);
  }
};

/* ============================ 主题切换 ============================ */
function applyTheme(name, silent) {
  THEME = (name === 'light') ? 'light' : 'dark';
  T = THEMES[THEME];
  BG = T.bg;
  UP = T.up;
  DOWN = T.down;
  Object.keys(T).forEach(k => { C[k] = T[k]; });
  document.documentElement.dataset.theme = THEME;

  const btn = document.getElementById('theme-btn');
  if (btn) {
    btn.textContent = THEME === 'dark' ? '☀' : '☾';
    btn.title = THEME === 'dark' ? '切换到浅色主题' : '切换到深色主题';
  }
  if (silent) return;

  try { localStorage.setItem('theme', THEME); } catch (e) { /* 隐私模式忽略 */ }
  if (lastData) render(lastData);
  if (lastMinute && maskEl.classList.contains('show')) renderMinute(lastMinute);
  // 助手面板里若已有回测净值图，跟着换色
  try { if (window.__asRenderNav) window.__asRenderNav(); } catch (e) { /* 忽略 */ }
  try { if (window.__pmRender) window.__pmRender(); } catch (e) { /* 忽略 */ }
}

document.getElementById('theme-btn').onclick = () => {
  applyTheme(THEME === 'dark' ? 'light' : 'dark');
};

/* ============================ 启动 ============================ */
applyTheme((() => {
  try { return localStorage.getItem('theme') || 'dark'; } catch (e) { return 'dark'; }
})(), true);                             // 先套用主题，再建图
renderChips();                          // 先撑出指标条高度，再初始化图表
chart = echarts.init(chartBox);
// 用户缩放 / 拖动后记住窗口，换股票或换周期时沿用
const onZoomChange = () => {
  lastZoomAt = Date.now();
  clearTimeout(zoomSaveTimer);
  zoomSaveTimer = setTimeout(saveZoomMem, 160);
};
chart.on('datazoom', onZoomChange);     // ECharts 官方事件名（小写）
chart.on('dataZoom', onZoomChange);     // 个别版本按注册名派发，两种都听
window.addEventListener('resize', () => {
  chart.resize();
  if (minChart) minChart.resize();
  if (pmChart) pmChart.resize();
  // 跨越移动端断点时重算布局（左边距、图例项、副图数量都要变）
  const nowMobile = isMobile();
  if (nowMobile !== wasMobile) {
    wasMobile = nowMobile;
    activeSubs = nowMobile ? ['vol', 'macd'] : ['vol', 'macd', 'kdj', 'rsi'];
    renderChips();
    if (lastData) render(lastData);
  }
});
// 容器尺寸变化（如指标条换行、窗口缩放）后同步画布，百分比布局会自动重算
if (window.ResizeObserver) {
  new ResizeObserver(() => chart.resize()).observe(chartBox);
}
window.addEventListener('load', () => chart.resize());
bindMinuteClick();
loadWatch();
load();

/* 深链：直接带 #fx 打开助手 + 因子表 */
if (/fx|因子/i.test(location.hash || '')) openAssistant();
