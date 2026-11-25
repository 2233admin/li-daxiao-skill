"""盘中卡：实时指数、涨跌家数、信号灯，以及好股票池的实时行情。约 5 秒出结果，盘中随问随跑。

usage: python intraday.py [--pool all|core] [--top 12]
数据：
- 指数与个股实时价：新浪 hq.sinajs.cn 批量接口（公开行情，185 只约 0.7s）
- 涨跌家数、涨跌停：乐咕 stock_market_activity_legu（实时）
- 好股票池：screen.py 最近一次落盘的 data/screen/result_*.csv（含 精选 标记、dps_ttm）
输出：时点、指数、大小盘分化、涨跌家数、盘中信号灯（与 daily_card 同阈值）、好股票池整体表现、
精选档实时、池内今天跌得最多的（实时股息率被动抬高 = "好股票打折"）、池内逆势上涨的。
"""
import argparse, os, sys, glob, datetime as dt
import pandas as pd, requests

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
ap = argparse.ArgumentParser()
ap.add_argument('--pool', default='all', choices=['all', 'core'])
ap.add_argument('--top', type=int, default=12)
a = ap.parse_args()

IDX = {'sh000001': '上证', 'sh000016': '上证50', 'sh000300': '沪深300', 'sh000905': '中证500',
       'sh000852': '中证1000', 'sz399006': '创业板', 'sh000922': '中证红利'}


def hq(symbols):
    """新浪批量行情 → DataFrame(sym, name, open, prev, price, high, low, date, time)。"""
    out = []
    for i in range(0, len(symbols), 400):
        r = requests.get('https://hq.sinajs.cn/list=' + ','.join(symbols[i:i + 400]),
                         headers={'Referer': 'https://finance.sina.com.cn'}, timeout=10)
        r.encoding = 'gbk'
        for line in r.text.split(';'):
            if '="' not in line:
                continue
            sym = line.split('hq_str_')[1].split('=')[0]
            f = line.split('="')[1].rstrip('"\n').split(',')
            if len(f) < 32 or not f[0]:
                continue
            out.append({'sym': sym, 'name': f[0], 'open': float(f[1]), 'prev': float(f[2]), 'price': float(f[3]),
                        'high': float(f[4]), 'low': float(f[5]), 'date': f[30], 'time': f[31]})
    d = pd.DataFrame(out)
    d['price'] = d['price'].where(d['price'] > 0, d['prev'])  # 停牌/集合竞价前用昨收
    d['chg'] = d['price'] / d['prev'] - 1
    return d


now = dt.datetime.now()
ix = hq(list(IDX)).set_index('sym')
t0 = f"{ix['date'].iloc[0]} {ix['time'].iloc[0]}"
session = ('盘前' if now.time() < dt.time(9, 30) else '午休' if dt.time(11, 30) <= now.time() < dt.time(13) else
           '盘中' if now.time() < dt.time(15) else '已收盘') if now.weekday() < 5 else '休市'
print(f'[盘中时点] 行情时间 {t0}｜现在 {now:%H:%M}（{session}）')
print('[指数] ' + ' | '.join(f"{IDX[s]} {ix.loc[s, 'price']:,.2f} {ix.loc[s, 'chg']:+.2%}" for s in IDX if s in ix.index))
spread = ix.loc['sh000016', 'chg'] - ix.loc['sh000852', 'chg']
if abs(spread) >= 0.02:
    side = '大盘抗跌、小盘重挫（对照 CB-15 微盘股崩塌、CB-21 退市出清）' if spread > 0 else '小盘强、大盘弱（题材活跃，提防高估五类）'
    print(f'[分化] 上证50 − 中证1000 = {spread * 100:+.1f}pp：{side}')

# 涨跌家数（乐咕实时）
r0 = float(ix.loc['sh000001', 'chg'])
try:
    from akcompat import ak
    s = ak.stock_market_activity_legu()
    row = dict(zip(s['item'], s['value']))
    up, dn, zt, dt_ = float(row['上涨']), float(row['下跌']), float(row['真实涨停']), float(row['真实跌停'])
    dn_sh = dn / (up + dn)
    print(f"[宽度] 上涨 {up:.0f} / 下跌 {dn:.0f}（下跌占比 {dn_sh:.0%}）｜真实涨停 {zt:.0f} / 跌停 {dt_:.0f}｜统计 {str(row.get('统计日期'))[:16]}")
    sse = pd.read_csv(os.path.join(D, 'sse.csv'), parse_dates=['date']).set_index('date')['close']
    ret = sse[sse.index >= '2005-01-01'].pct_change().dropna()
    lo, hi = float(ret.quantile(0.03)), float(ret.quantile(0.97))
    panic = (r0 <= lo and dn_sh >= 0.85) or (dt_ >= 100 and dt_ >= 3 * zt)
    frenzy = r0 >= hi and (1 - dn_sh) >= 0.85 and zt >= 100
    lit = [n for n, v in [('恐慌', panic), ('狂热', frenzy)] if v]
    weak = '；普跌（下跌占比≥85%）但幅度未到 3% 分位，算"弱"' if not panic and dn_sh >= 0.85 else ''
    print(f"[盘中信号灯] {'、'.join(lit) + ' 亮' if lit else '恐慌、狂热都没亮'}（上证 {r0:+.2%}，阈值 {lo:+.2%} / {hi:+.2%}）{weak}")
except Exception as e:
    print(f'[宽度] 乐咕取数失败：{type(e).__name__}，涨跌家数这项今天盘中没有')

# 好股票池
files = sorted(glob.glob(os.path.join(D, 'screen', 'result_*.csv')))
if not files:
    print('[好股票池] 还没有选股结果，先跑 fetch_screen.py 和 screen.py --csv')
    sys.exit(0)
pool = pd.read_csv(files[-1], dtype={'code': str}).set_index('code')
if a.pool == 'core':
    pool = pool[pool['精选']]
q = hq([('sh' if c[0] in '69' else 'sz') + c for c in pool.index])
q['code'] = q['sym'].str[2:]
p = pool.join(q.set_index('code')[['price', 'chg']], how='inner')
p['实时股息率%'] = p['dps_ttm'] / p['price'] * 100
age = os.path.basename(files[-1])[7:15]
print(f"\n[好股票池] {len(p)} 只（选股日 {age}）｜池内平均 {p['chg'].mean():+.2%}，中位 {p['chg'].median():+.2%}，"
      f"上涨 {(p['chg'] > 0).sum()} / 下跌 {(p['chg'] < 0).sum()}｜对比上证 {r0:+.2%}、中证1000 {ix.loc['sh000852', 'chg']:+.2%}")
cols = ['名称', '行业地位', 'price', 'chg', '实时股息率%', 'PE']
fmt = lambda d: d[cols].rename(columns={'price': '现价', 'chg': '涨跌'}).assign(涨跌=lambda x: (x['涨跌'] * 100).round(2).astype(str) + '%').round({'实时股息率%': 2, '现价': 2})
core = p[p['精选']]
if len(core):
    print(f'\n[精选档实时] {len(core)} 只')
    print(fmt(core.sort_values('chg')).to_string())
print(f'\n[好股票打折] 池内今天跌得最多的 {a.top} 只（价格跌、股息率被动抬高）')
print(fmt(p.sort_values('chg').head(a.top)).to_string())
print(f'\n[逆势] 池内今天涨得最多的 {min(6, a.top)} 只')
print(fmt(p.sort_values('chg', ascending=False).head(min(6, a.top))).to_string())
print('\n注：池子是选股日收盘时的结果，盘中不重新过尺子；股息率按近12个月每股分红 / 实时价。')
