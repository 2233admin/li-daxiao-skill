"""持仓体检：拿李大霄的尺子逐只量用户的持仓。任何 A 股都能量（亏损、不分红、新股也行）。

usage: python checkup.py 600036 中国神华 300750 [--cost 600036=35.2,300750=280]
  代码或名称都行；--cost 给持仓成本可算浮盈亏（R22：看错要认错，好公司给改错机会）。
依赖 fetch_screen.py 的缓存（spot.csv、industry.csv、fhps_*.csv）和 data/ipo.csv。

输出每只：好股票四条（行业地位 / 估值 / 分红 / 盈利）各自是否满足、高估五类沾了哪几样、
以及一行"体检标签"。只给标准对照，不给买卖结论——结论由用户自己下（SKILL.md "守住角色"）。
"""
import argparse, os, sys, glob, datetime as dt
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
S = os.path.join(D, 'screen')
ap = argparse.ArgumentParser()
ap.add_argument('stocks', nargs='+')
ap.add_argument('--cost', default='')
a = ap.parse_args()


def code6(s):
    return s.astype(str).str.extract(r'(\d{6})')[0]


spot = pd.read_csv(os.path.join(S, 'spot.csv'), dtype={'代码': str})
spot['code'] = code6(spot['代码'])
spot['price'] = spot['最新价'].where(spot['最新价'] > 0, spot['昨收'])
spot = spot.drop_duplicates('code').set_index('code')
ind = pd.read_csv(os.path.join(S, 'industry.csv'), dtype={'code': str}).drop_duplicates('code').set_index('code')
ind['rank'] = ind.groupby('industry')['cap'].rank(ascending=False, method='first')
ind_n = ind.groupby('industry').size()
ind_pe = ind[ind['pe'] > 0].groupby('industry')['pe'].median()
fh, fi = {}, {}
for f in sorted(glob.glob(os.path.join(S, 'fhps_*.csv'))):
    x = pd.read_csv(f, dtype={'代码': str})
    x['code'] = code6(x['代码'])
    p = os.path.basename(f)[5:13]
    (fh if p.endswith('1231') else fi)[p] = x.drop_duplicates('code').set_index('code')
fh = dict(sorted(fh.items())[-5:])


def cash(p, k, src):
    return (src[p].loc[k, '现金分红-现金分红比例'] / 10) if k in src[p].index and src[p].loc[k, '现金分红-现金分红比例'] > 0 else 0
ipo = pd.read_csv(os.path.join(D, 'ipo.csv'), dtype={'股票代码': str})
ipo['上市日期'] = pd.to_datetime(ipo['上市日期'], format='mixed', errors='coerce')
listed = ipo.dropna(subset=['上市日期']).drop_duplicates('股票代码').set_index('股票代码')['上市日期']
bd = pd.read_csv(os.path.join(D, 'bond10.csv'))
cn10 = float(pd.to_numeric(bd.iloc[:, -1], errors='coerce').dropna().iloc[-1])
cost = dict(kv.split('=') for kv in a.cost.split(',') if '=' in kv)
FIN = '货币金融|资本市场|保险|其他金融'
today = pd.Timestamp(dt.date.today())
years = sorted(fh)


names = pd.concat([ipo.drop_duplicates('股票代码').set_index('股票代码')['股票简称'], spot['名称']])
names = names[~names.index.duplicated(keep='last')]


def resolve(s):
    if s.isdigit() and len(s) == 6:
        return s
    hit = names.index[names.astype(str).str.replace(' ', '') == s]
    return hit[0] if len(hit) else None


print(f'口径：估值用新浪动态 PE/PB；分红看 {years[0][:4]}–{years[-1][:4]} 年报；10Y {cn10:.2f}%；数据截至 {os.path.getmtime(os.path.join(S, "spot.csv")) and dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(S, "spot.csv"))):%Y-%m-%d %H:%M}')
seen = set()
for s in a.stocks:
    k = resolve(s)
    if not k or k not in names.index and k not in ind.index:
        print(f'\n{s}：找不到（代码或名称不对）')
        continue
    if k in seen:
        continue
    seen.add(k)
    # 新浪全A行情夜间北交所为 0、刚上市的新股可能缺：无行情时估值/股息率标"无行情"，其余照量
    nm = names.get(k, k)
    px = float(spot.loc[k, 'price']) if k in spot.index and spot.loc[k, 'price'] > 0 else float('nan')
    i = ind.loc[k] if k in ind.index else None
    industry = i['industry'] if i is not None else '未分类'
    pe = float(i['pe']) if i is not None else float('nan')
    pb = float(i['pb']) if i is not None else float('nan')
    cap = float(i['cap']) if i is not None else float('nan')
    rk = f"第{i['rank']:.0f}/{ind_n[industry]}" if i is not None else '?'
    ipe = ind_pe.get(industry, float('nan'))
    fin = bool(pd.Series([industry]).str.contains(FIN).iloc[0])
    div_yrs = sum(1 for y in years if k in fh[y].index and fh[y].loc[k, '现金分红-现金分红比例'] > 0)
    eps = [fh[y].loc[k, '每股收益'] if k in fh[y].index else None for y in years]
    last = fh[years[-1]].loc[k] if k in fh[years[-1]].index else None
    # 近12个月 = 最近年报 + 最近年报之后的中报；今年中报还没出预案的，退回用同年中报（与 screen.py 同口径）
    la = years[-1]
    new_i = [p for p in fi if p > la]
    old_i = [p for p in fi if p[:4] == la[:4]]
    ci = sum(cash(p, k, fi) for p in new_i) or sum(cash(p, k, fi) for p in old_i)
    dps = cash(la, k, fh) + ci
    dy = dps / px * 100 if px == px and px > 0 else float('nan')
    np_yoy = float(last['净利润同比增长']) if last is not None else float('nan')
    lst = listed.get(k)

    # 高估五类
    five = []
    if cap < 100: five.append(f'小（市值 {cap:.0f} 亿）')
    if lst is not None and lst > today - pd.DateOffset(years=3): five.append(f'新（{lst:%Y-%m} 上市）')
    if 'ST' in str(nm) or pe <= 0: five.append('差（ST 或亏损）')
    elif np_yoy < -20: five.append(f'差（净利同比 {np_yoy:.0f}%）')
    if pe > 40 and div_yrs < 3: five.append(f'题材/伪成长（PE {pe:.0f}，分红 {div_yrs} 年）')
    elif pe > ipe * 1.5 and pe > 30: five.append(f'伪成长（PE {pe:.0f}，行业中位 {ipe:.0f}）')

    # 好股票四条
    rank_ok = i is not None and i['rank'] <= (10 if fin else 3)  # 银行 44 家、券商 51 家，金融放到前 10
    val_ok = 0 < pe <= (15 if fin else min(20, ipe if ipe == ipe else 20)) and 0 < pb <= (2 if fin else 3)
    div_ok = div_yrs >= len(years) and dy >= cn10 + 1.5
    # 分红送配表只收录有预案的公司，不分红的年份没有 EPS（显示 "-"）：按已知年份判，至少要有 3 年
    known = [e for e in eps if e is not None]
    earn_ok = len(known) >= 3 and all(e > 0 for e in known) and pe > 0 and (np_yoy >= -20 if np_yoy == np_yoy else False)
    good = [('行业地位', rank_ok, f'{industry} {rk}'), ('估值低', val_ok, f'PE {pe:.1f}（行业中位 {ipe:.1f}）PB {pb:.2f}'),
            ('分红真', div_ok, f'连续 {div_yrs}/{len(years)} 年，股息率 {dy:.2f}%（门槛 {cn10 + 1.5:.2f}%）'),
            ('盈利实', earn_ok, f'近年 EPS {"/".join("-" if e is None else f"{e:.2f}" for e in eps)}，净利同比 {np_yoy:.1f}%')]
    n_ok = sum(g[1] for g in good)
    tag = ('好股票：四条全过' if n_ok == 4 and not five else
           f'沾高估五类 {len(five)} 样：不是坚持的问题，是要不要认错的问题' if len(five) >= 2 else
           f'好股票四条过 {n_ok} 条' + (f'，沾 {len(five)} 样' if five else ''))
    print(f'\n{k} {nm}  现价 {"无行情" if px != px else f"{px:.2f}"}  市值 {"?" if cap != cap else f"{cap:,.0f}"} 亿')
    for g in good:
        print(f"  {'✓' if g[1] else '✗'} {g[0]}：{g[2]}")
    print(f"  高估五类：{'、'.join(five) if five else '一样不沾'}")
    if k in cost:
        c = float(cost[k])
        pnl = px / c - 1
        print(f"  持仓：成本 {c:.2f}，浮动 {pnl:+.1%}" + ('（跌幅已超过 R22 原文例子的 -22%）' if pnl <= -0.22 else ''))
    print(f'  => 体检标签：{tag}')
