"""历史没有新鲜事：找与某一天最相似的历史时刻。

usage:
  python analog.py [--asof YYYY-MM-DD] [--top 5] [--cases ../references/cases_index.csv] [--json]

状态向量（只用 asof 当天及之前的数据，无未来函数）：
  pe_q     全A 中位 PE-TTM 在 2005 至今的扩张分位
  pb_q     全A 中位 PB 扩张分位
  bn_q     破净股占比扩张分位
  eb_q     股债差 = 上证50 滚动PE 倒数 - 10Y 国债，扩张分位（2007 起）
  dd3      上证距 3 年高点回撤（0 到 -0.7）
  r12      上证近 12 个月收益
  heat     上证 20 日均量 / 250 日均量
输出：
  1) 当天状态
  2) 书中案例锚定日里最像的 top N（cases_index.csv: id,anchor,name）
  3) 2007 起所有月末里最像的 top N，以及之后 60/250 个交易日的上证收益
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
ap = argparse.ArgumentParser()
ap.add_argument('--asof')
ap.add_argument('--top', type=int, default=5)
ap.add_argument('--cases', default=os.path.join(HERE, '..', 'references', 'cases_index.csv'))
ap.add_argument('--json', action='store_true')
ap.add_argument('--exclude-after', action='store_true',
                help='回放测试用：案例和月末候选都只取 asof 之前、且与 asof 相隔 >250 交易日的时刻（事后 250 日走势不越过 asof）')
ap.add_argument('--blind', action='store_true', help='回放测试用：不输出 asof 日期和指数点位')
a = ap.parse_args()
sys.stdout.reconfigure(encoding='utf-8')

sse = pd.read_csv(f'{D}/sse.csv', parse_dates=['date']).set_index('date')
close, vol = sse['close'], sse['volume']
pe = pd.read_csv(f'{D}/a_pe.csv', parse_dates=['date']).set_index('date')['middlePETTM']
pb = pd.read_csv(f'{D}/a_pb.csv', parse_dates=['date']).set_index('date')['middlePB']
bn = pd.read_csv(f'{D}/below_net.csv', parse_dates=['date']).set_index('date')['below_net_asset_ratio']
bd = pd.read_csv(f'{D}/bond10.csv')
bd = pd.Series(pd.to_numeric(bd.iloc[:, -1], errors='coerce').values, index=pd.to_datetime(bd.iloc[:, 0])).dropna()
s50 = pd.read_csv(f'{D}/pe_sz50.csv')
s50 = pd.Series(pd.to_numeric(s50['滚动市盈率'], errors='coerce').values, index=pd.to_datetime(s50['日期'])).dropna()


def asof_val(s, d):
    s = s[s.index <= d]
    return (s.iloc[-1], s) if len(s) else (np.nan, s)


def pct(s, x):
    return float((s <= x).mean()) if len(s) >= 12 else np.nan


def state(d):
    d = pd.Timestamp(d)
    o = {'date': str(d.date())}
    x, h = asof_val(pe, d); o['pe'] = x; o['pe_q'] = pct(h, x)
    x, h = asof_val(pb, d); o['pb'] = x; o['pb_q'] = pct(h, x)
    x, h = asof_val(bn, d); o['bn'] = x; o['bn_q'] = pct(h, x)
    y50, h50 = asof_val(s50, d)
    b10, hb = asof_val(bd, d)
    if not np.isnan(y50) and not np.isnan(b10) and len(hb):
        eb_hist = (100 / h50).reindex(hb.index, method='ffill') - hb
        eb_hist = eb_hist.dropna()
        o['eb'] = 100 / y50 - b10; o['eb_q'] = pct(eb_hist, o['eb']); o['cn10y'] = b10
    c = close[close.index <= d]
    v = vol[vol.index <= d]
    o['sse'] = float(c.iloc[-1])
    o['dd3'] = float(c.iloc[-1] / c.iloc[-750:].max() - 1)
    o['r12'] = float(c.iloc[-1] / c.iloc[-250] - 1) if len(c) > 250 else np.nan
    o['heat'] = float(v.iloc[-20:].mean() / v.iloc[-250:].mean()) if len(v) > 250 else np.nan
    # 蓝筹估值：他看上证50，优先于被小盘拉高的全A中位
    o['s50pe'] = y50; o['s50_q'] = pct(h50, y50)
    # 巨量持续：近60日里成交量高于近3年80分位的天数占比（"万亿成交22天"的代理）
    o['hot60'] = float((v.iloc[-60:] > v.iloc[-750:].quantile(0.8)).mean()) if len(v) > 750 else np.nan
    # 急跌：距近60日高点
    o['dd60'] = float(c.iloc[-1] / c.iloc[-60:].max() - 1)
    return o


FEAT = {'pe_q': 0.7, 'pb_q': 0.7, 's50_q': 1.2, 'bn_q': 1.0, 'eb_q': 1.0, 'dd3': 1.5, 'r12': 1.0, 'heat': 0.5,
        'hot60': 1.0, 'dd60': 1.0}
SCALE = {'pe_q': 1, 'pb_q': 1, 's50_q': 1, 'bn_q': 1, 'eb_q': 1, 'dd3': 0.5, 'r12': 0.8, 'heat': 2.0,
         'hot60': 1, 'dd60': 0.3}


def dist(p, q):
    s, w = 0.0, 0.0
    for k, wt in FEAT.items():
        if k in p and k in q and not (np.isnan(p[k]) or np.isnan(q[k])):
            s += wt * ((p[k] - q[k]) / SCALE[k]) ** 2; w += wt
    return np.sqrt(s / w) if w else np.nan


def fwd(d):
    pos = close.index.searchsorted(pd.Timestamp(d))
    o = {}
    for h in (60, 250):
        if pos + h < len(close):
            o[f'fwd{h}'] = round(float(close.iloc[pos + h] / close.iloc[pos] - 1), 3)
    return o


asof = pd.Timestamp(a.asof) if a.asof else close.index[-1]
now = state(asof)

cases = []
if os.path.exists(a.cases):
    ci = pd.read_csv(a.cases, encoding='utf-8')
    for _, r in ci.iterrows():
        ad = pd.Timestamp(r['anchor'])
        if a.exclude_after and close.index.searchsorted(ad) > close.index.searchsorted(asof) - 250:
            continue
        st = state(ad)
        cases.append({'id': r['id'], 'name': r['name'], 'anchor': str(ad.date()), 'dist': round(dist(now, st), 3),
                      **{k: (round(st[k], 3) if isinstance(st.get(k), float) else st.get(k)) for k in FEAT}, **fwd(ad)})
    cases = sorted([c for c in cases if not np.isnan(c['dist'])], key=lambda c: c['dist'])[:a.top]

months = close[close.index >= '2007-06-01'].resample('ME').last().index
idx_dates = [close.index[close.index <= m][-1] for m in months]
pos_asof = close.index.searchsorted(asof)
hist = []
for d in idx_dates:
    p = close.index.get_loc(d)
    if a.exclude_after and p > pos_asof - 250:
        continue
    if not a.exclude_after and abs(p - pos_asof) < 120:
        continue
    st = state(d)
    hist.append({'date': str(d.date()), 'sse': round(st['sse'], 2), 'dist': round(dist(now, st), 3), **fwd(d)})
hist = sorted([h for h in hist if not np.isnan(h['dist'])], key=lambda h: h['dist'])[:a.top]

res = {'asof': now, 'nearest_cases': cases, 'nearest_months': hist}
if a.json:
    print(json.dumps(res, ensure_ascii=False, default=float, indent=1))
    sys.exit(0)

f = lambda x, p=0: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else (f'{x:.0%}' if p else f'{x:.2f}')
print('状态（日期隐藏）' if a.blind else f"状态 {now['date']} 上证 {now['sse']:.2f}")
print(f"  全A中位PE {f(now['pe'])} 分位{f(now['pe_q'],1)} | PB {f(now['pb'])} 分位{f(now['pb_q'],1)} | 破净 {f(now['bn'],1)} 分位{f(now['bn_q'],1)}")
print(f"  蓝筹 上证50滚动PE {f(now.get('s50pe'))} 分位{f(now.get('s50_q'),1)} | 股债差(上证50盈利收益率-10Y) {f(now.get('eb'))}pp 分位{f(now.get('eb_q'),1)}")
print(f"  距3年高点 {f(now['dd3'],1)} | 距60日高点 {f(now['dd60'],1)} | 近12月 {f(now['r12'],1)} | 量能热度 {f(now['heat'])} | 近60日巨量天数占比 {f(now['hot60'],1)}")
print('\n最像的书中案例：')
for c in cases:
    print(f"  {c['id']} {c['anchor']} 距离{c['dist']} {c['name']}  之后60日{f(c.get('fwd60'),1)} 250日{f(c.get('fwd250'),1)}")
if not cases:
    print('  （无 cases_index.csv）')
print('\n最像的历史月末（2007 起）：')
for h in hist:
    print(f"  {h['date']} 上证{h['sse']} 距离{h['dist']}  之后60日{f(h.get('fwd60'),1)} 250日{f(h.get('fwd250'),1)}")
