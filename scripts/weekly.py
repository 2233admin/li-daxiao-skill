"""周报 / 月报卡：一段时间内的变化量。

usage: python weekly.py [--days 5]     # 5 = 周报，20 = 月报
读 daily_card / fetch_extra 的缓存，另取 6 个宽基指数日线（新浪，约 10s）。
输出：各指数区间涨跌、大小盘分化、全A估值分位变化、破净占比变化、股债差变化、两融变化、
国家队 ETF 份额变化、新发基金、区间最大单日跌幅/涨幅日。
"""
import argparse, os, sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
ap = argparse.ArgumentParser()
ap.add_argument('--days', type=int, default=5)
a = ap.parse_args()
N = a.days

sse = pd.read_csv(f'{D}/sse.csv', parse_dates=['date']).set_index('date')['close']
d1, d0 = sse.index[-1], sse.index[-1 - N]
print(f"[区间] {d0:%Y-%m-%d} → {d1:%Y-%m-%d}（{N} 个交易日，{'周报' if N <= 5 else '月报' if N <= 22 else '区间'}）")

IDX = {'sh000001': '上证', 'sh000016': '上证50', 'sh000300': '沪深300', 'sh000852': '中证1000', 'sz399006': '创业板', 'sh000922': '中证红利'}
try:
    from akcompat import ak
    chg = {}
    for s, n in IDX.items():
        x = ak.stock_zh_index_daily(symbol=s).set_index('date')['close']
        x.index = pd.to_datetime(x.index)
        x = x[x.index <= d1]
        chg[n] = x.iloc[-1] / x.iloc[-1 - N] - 1
    print('[指数] ' + ' | '.join(f'{k} {v:+.2%}' for k, v in chg.items()))
    sp = chg['上证50'] - chg['中证1000']
    print(f"[分化] 上证50 − 中证1000 = {sp * 100:+.1f}pp" + ('（大盘强、小盘弱）' if sp > 0.02 else '（小盘强、大盘弱）' if sp < -0.02 else '（大小盘同步）'))
except Exception as e:
    print(f'[指数] 取数失败 {type(e).__name__}；上证 {sse.iloc[-1] / sse.iloc[-1 - N] - 1:+.2%}')

r = sse.pct_change().iloc[-N:]
print(f"[波动] 区间最大单日跌 {r.min():+.2%}@{r.idxmin():%m-%d}，最大单日涨 {r.max():+.2%}@{r.idxmax():%m-%d}，收阴 {(r < 0).sum()} 天")


def at(df, col, dcol, when):
    s = df.set_index(pd.to_datetime(df[dcol]))[col].dropna()
    s = s[s.index <= when]
    return float(s.iloc[-1]) if len(s) else float('nan')


# 全A中位 PE/PB 源是月末序列（只有最新一行带分位）：自己算近10年分位，起点取 d0 之前最近的一个月末
def q10(df, col, when):
    s = df.set_index(pd.to_datetime(df['date']))[col].dropna()
    s = s[s.index <= when]
    w = s[s.index >= s.index[-1] - pd.DateOffset(years=10)]
    return float((w <= w.iloc[-1]).mean()), s.index[-1]


pe = pd.read_csv(f'{D}/a_pe.csv')
pb = pd.read_csv(f'{D}/a_pb.csv')
(p1, t1), (p0, t0) = q10(pe, 'middlePETTM', d1), q10(pe, 'middlePETTM', d0)
(k1, _), (k0, _) = q10(pb, 'middlePB', d1), q10(pb, 'middlePB', d0)
bn = pd.read_csv(f'{D}/below_net.csv')
b1, b0 = at(bn, 'below_net_asset_ratio', 'date', d1), at(bn, 'below_net_asset_ratio', 'date', d0)
print(f'[估值] 全A 中位PE 近10年分位 {p0:.0%}@{t0:%m-%d} → {p1:.0%}@{t1:%m-%d}｜中位PB {k0:.0%} → {k1:.0%}（源为月末，起点是最近月末）'
      f'｜破净占比 {b0:.1%} → {b1:.1%}（越多越便宜）')

if os.path.exists(f'{D}/gxl.csv'):
    g = pd.read_csv(f'{D}/gxl.csv')
    bd = pd.read_csv(f'{D}/bond10.csv')
    bd.columns = ['date', 'cn10'][:bd.shape[1]] if bd.shape[1] == 2 else bd.columns
    s1 = at(g, '股息率', '日期', d1) - at(bd, bd.columns[-1], bd.columns[0], d1)
    s0 = at(g, '股息率', '日期', d0) - at(bd, bd.columns[-1], bd.columns[0], d0)
    print(f'[股债差] {s0:+.2f}pp → {s1:+.2f}pp')
if os.path.exists(f'{D}/margin.csv'):
    m = pd.read_csv(f'{D}/margin.csv')
    m1, m0 = at(m, '融资余额', '日期', d1), at(m, '融资余额', '日期', d0)
    print(f'[两融] 融资余额 {m0:,.0f} → {m1:,.0f} 亿（{m1 / m0 - 1:+.1%}）')
if os.path.exists(f'{D}/etf_nat.csv'):
    e = pd.read_csv(f'{D}/etf_nat.csv', dtype={'code': str}).groupby('date')['shares'].sum() / 1e8
    e.index = pd.to_datetime(e.index)
    e1, e0 = e[e.index <= d1], e[e.index <= d0]
    if len(e0):
        print(f'[国家队] 沪市6只宽基ETF份额 {e0.iloc[-1]:,.0f} → {e1.iloc[-1]:,.0f} 亿份（{e1.iloc[-1] - e0.iloc[-1]:+.1f}，截至 {e1.index[-1]:%m-%d}）')
if os.path.exists(f'{D}/fund_new.csv'):
    f = pd.read_csv(f'{D}/fund_new.csv', parse_dates=['成立日期'])
    f = f[(f['成立日期'] > d0) & (f['成立日期'] <= d1)]
    act = f[f['基金类型'].isin(['股票型', '混合型-偏股'])]['募集份额'].sum()
    print(f'[新发基金] 区间新成立主动偏股 {act:.0f} 亿份（新发基金数据常晚几天）')
print('[提示] 信号灯和好股票池的逐日变化不存历史；周报里要讲的话，先跑 daily_card.py 和 intraday.py 看当前状态。')
