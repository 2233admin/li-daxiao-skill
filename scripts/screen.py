"""李大霄选股尺子：把"好股票 / 高估五类"写成可核对的规则，筛全A。

usage: python screen.py [--top 40] [--csv]
先跑 fetch_screen.py 取数。输出：逐条规则的漏斗、通过名单（按规模档、股息率排序），可选落盘 data/screen/result_<日期>.csv。

这是"符合他标准的候选池"，不是买卖建议：不含买点、仓位，"全国第一"无法机读，需人工核对行业地位。

规则出处（worldview.md / voice.md）：
  好股票：抓大放小、先全球最好再全国第一（4.11）；估值低（蓝筹十倍上下）；分红真；盈利实。
  高估五类（ch5 5.16）：小、新、差、题材、伪成长——一票否决。
"""
import argparse, os, sys, glob, datetime as dt
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 30)
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
S = os.path.join(D, 'screen')
ap = argparse.ArgumentParser()
ap.add_argument('--top', type=int, default=40)
ap.add_argument('--csv', action='store_true')
ap.add_argument('--explain', default='', help='逗号分隔的 6 位代码：逐只列出读数和卡在哪条规则')
a = ap.parse_args()

RULE = {
    # 估值按行业相对：绝对 PE≤15 会让结果几乎全是银行（2026-11-25 首版 143 只里 31 只银行、龙头级 38 只里 19 只）
    'pe_max': 20,          # 估值低：年报 PE ≤ 20 的硬上限……
    'pe_vs_ind': 1.0,      # ……且 ≤ 行业 PE 中位数 × 1.0（新浪行业，正 PE 个股）
    'pe_max_fin': 15,      # 金融：绝对 PE ≤ 15（不比行业中位）
    'pb_max': 3.0,         # 估值低：PB ≤ 3（非金融）
    'pb_max_fin': 2.0,     # 估值低：PB ≤ 2（银行/保险/券商）
    'per_ind': 3,          # 非金融每个行业最多展示 3 只（按行业内市值排名），防止一个行业刷屏
    'div_years': 5,        # 分红真：最近 5 个年报连续现金分红
    'dy_over_10y': 1.5,    # 分红真：股息率（最近年报+最近中报）≥ 10Y + 1.5pp
    'payout_min': 0.20,    # 分红真：年报派息率 ≥ 20%（防象征性分红）
    'np_yoy_min': -20,     # 盈利实：最近年报净利润同比 ≥ -20%；且近 5 年 EPS 全为正
    'cap_min': 100,        # 高估五类·小：总市值 < 100 亿排除
    'new_years': 3,        # 高估五类·新：上市不满 3 年排除
    # 精选档（最符合他的标准）：行业前 3、市值≥300亿、EPS 波动≤0.2、无周期/特别分红标记、股息率≥3.5%、净利同比≥0。
    # 行业第一且 EPS 波动≤0.15 的，净利同比放宽到 ≥-10%：一年小幅回落不算"差"，看多年稳定（中国移动 -0.9%、神华 -5.3% 由此进入）
    'core_rank': 3, 'core_cap': 300, 'core_cv': 0.2, 'core_dy': 3.5,
    'core_np': 0, 'core_np_leader': -10, 'core_cv_leader': 0.15,
    'cyc_cv': 0.35,        # 近 5 年 EPS 变异系数 > 0.35 标"周期?"（不排除，只提醒：周期股 PE 低常在利润高点）
}
TIER = [(1000, '龙头级'), (300, '大'), (100, '中')]


def code6(s):
    return s.astype(str).str.extract(r'(\d{6})')[0]


# ---- 读数据 ----
spot = pd.read_csv(os.path.join(S, 'spot.csv'), dtype={'代码': str})
spot['code'] = code6(spot['代码'])
spot['price'] = spot['最新价'].where(spot['最新价'] > 0, spot['昨收'])
spot = spot[spot['price'] > 0].set_index('code')

fh = {}
for f in sorted(glob.glob(os.path.join(S, 'fhps_*.csv'))):
    p = os.path.basename(f)[5:13]
    x = pd.read_csv(f, dtype={'代码': str})
    x['code'] = code6(x['代码'])
    fh[p] = x.drop_duplicates('code').set_index('code')
annual = sorted(p for p in fh if p.endswith('1231'))[-RULE['div_years']:]
exp = [f'{int(annual[-1][:4]) - i}1231' for i in range(RULE['div_years'] - 1, -1, -1)]
if annual != exp:
    print(f"警告：年报缺 {sorted(set(exp) - set(annual))}，连续分红/盈利只按 {len(annual)} 年算，结论偏宽。先重跑 fetch_screen.py")
interim = sorted(p for p in fh if p.endswith('0630'))
last_a = annual[-1]
last_i = [p for p in interim if p > last_a][-1:]  # 最近年报之后的中报
prev_i = [p for p in interim if p[:4] == last_a[:4]]  # 与最近年报同年的中报（算派息率）

bd = pd.read_csv(os.path.join(D, 'bond10.csv'))
cn10 = float(pd.to_numeric(bd.iloc[:, -1], errors='coerce').dropna().iloc[-1])

tags = {}
for c, n in [('000016', '上证50'), ('000300', '沪深300'), ('000922', '中证红利'), ('000905', '中证500')]:
    f = os.path.join(S, f'cons_{c}.csv')
    if os.path.exists(f):
        for k in code6(pd.read_csv(f, dtype={'成分券代码': str})['成分券代码']):
            tags.setdefault(k, []).append(n)

FIN = '货币金融|资本市场|保险|其他金融'
ind = pd.read_csv(os.path.join(S, 'industry.csv'), dtype={'code': str}).drop_duplicates('code').set_index('code')
ind['rank'] = ind.groupby('industry')['cap'].rank(ascending=False, method='first')
ind_n = ind.groupby('industry').size()
ind_pe = ind[ind['pe'] > 0].groupby('industry')['pe'].median()

ipo = pd.read_csv(os.path.join(D, 'ipo.csv'), dtype={'股票代码': str})
ipo['上市日期'] = pd.to_datetime(ipo['上市日期'], format='mixed', errors='coerce')
listed = ipo.dropna(subset=['上市日期']).drop_duplicates('股票代码').set_index('股票代码')['上市日期']

# ---- 组装 ----
A = fh[last_a]
df = pd.DataFrame(index=A.index)
df['名称'] = A['名称']
df['price'] = spot['price'].reindex(df.index)
df['eps'] = A['每股收益']
df['bps'] = A['每股净资产']
df['shares'] = A['总股本']
df['np_yoy'] = A['净利润同比增长']
cash = lambda p: fh[p]['现金分红-现金分红比例'].reindex(df.index).fillna(0) / 10  # 每 10 股 → 每股
# 近12个月 ≈ 最近年报 + 最近一次中报；今年中报预案还没出的（如招行 2026-11 时），退回用去年中报，否则股息率少算一半
ci_new = sum(cash(p) for p in last_i) if last_i else 0
ci_old = sum(cash(p) for p in prev_i) if prev_i else 0
df['dps_ttm'] = cash(last_a) + (ci_new.where(ci_new > 0, ci_old) if hasattr(ci_new, 'where') else ci_old)
df['dps_fy'] = cash(last_a) + sum(cash(p) for p in prev_i)
df['div_yrs'] = sum((cash(p) > 0).astype(int) for p in annual)
df['eps_pos_yrs'] = sum((fh[p]['每股收益'].reindex(df.index) > 0).astype(int) for p in annual)
E = pd.concat([fh[p]['每股收益'].reindex(df.index) for p in annual], axis=1)
df['eps_cv'] = E.std(axis=1) / E.mean(axis=1).abs()  # 近年 EPS 波动：高 = 周期股，低 PE 可能是利润高点
df['pe'] = df['price'] / df['eps']
df['pb'] = df['price'] / df['bps']
df['pb_bad'] = df['pb'] > 15  # 源里每股净资产个别错（中国移动 PB 算出 36），这类不让 PB 一关误杀，表里标 ?
df['cap'] = df['price'] * df['shares'] / 1e8
df['dy'] = df['dps_ttm'] / df['price'] * 100
df['payout'] = df['dps_fy'] / df['eps']
df['listed'] = listed.reindex(df.index)
df['指数'] = [','.join(tags.get(k, [])) for k in df.index]
df['行业'] = ind['industry'].reindex(df.index).fillna('未分类')
df['ind_rank'] = ind['rank'].reindex(df.index)
df['ind_n'] = df['行业'].map(ind_n)
df['ind_pe'] = df['行业'].map(ind_pe)
df['fin'] = df['行业'].str.contains(FIN)
df = df.dropna(subset=['price'])

today = pd.Timestamp(dt.date.today())
checks = [
    ('差：非ST', ~df['名称'].astype(str).str.contains('ST')),
    ('新：上市满3年', ~(df['listed'] > today - pd.DateOffset(years=RULE['new_years']))),
    ('小：市值≥100亿', df['cap'] >= RULE['cap_min']),
    ('盈利实：近5年EPS全正', df['eps_pos_yrs'] >= len(annual)),
    ('盈利实：净利同比≥-20%', df['np_yoy'] >= RULE['np_yoy_min']),
    # 金融不比行业中位：银行中位 PE 7.0，会把招行(7.6)、工行(9.2)这类质量溢价龙头刷掉（2026-11-25 实测），金融沿用绝对 PE≤15
    ('估值低：PE≤20且≤行业中位（金融≤15）', (df['pe'] > 0) & (
        (~df['fin'] & (df['pe'] <= RULE['pe_max']) & ((df['pe'] <= df['ind_pe'] * RULE['pe_vs_ind']) | df['ind_pe'].isna()))
        | (df['fin'] & (df['pe'] <= RULE['pe_max_fin'])))),
    ('估值低：PB≤3（金融≤2）', ((df['pb'] > 0) & (df['pb'] <= df['fin'].map({True: RULE['pb_max_fin'], False: RULE['pb_max']})))
     | df['pb_bad']),
    (f'分红真：连续{len(annual)}年', df['div_yrs'] >= len(annual)),
    (f'分红真：股息率≥{cn10 + RULE["dy_over_10y"]:.2f}%', df['dy'] >= cn10 + RULE['dy_over_10y']),
    ('分红真：派息率≥20%', df['payout'] >= RULE['payout_min']),
]
if a.explain:
    for k in a.explain.split(','):
        if k not in df.index:
            nm = spot['名称'].get(k, '?') if '名称' in spot else '?'
            print(f'{k} {nm}：不在样本（{last_a} 年报没有分配预案，或无行情）')
            continue
        x = df.loc[k]
        fails = [n for n, c in checks if not bool(pd.Series(c).reindex([k]).fillna(False).iloc[0])]
        print(f"{k} {x['名称']}［{x['行业']} 行业内市值第 {x['ind_rank']:.0f}/{x['ind_n']:.0f}，行业PE中位 {x['ind_pe']:.1f}］：PE {x['pe']:.1f} PB {x['pb']:.2f} 市值 {x['cap']:,.0f}亿 股息率 {x['dy']:.2f}% 派息率 {x['payout']:.2f} "
              f"连续分红 {x['div_yrs']:.0f}/{len(annual)} EPS为正 {x['eps_pos_yrs']:.0f}/{len(annual)} 净利同比 {x['np_yoy']:.1f}% EPS波动 {x['eps_cv']:.2f}"
              f" => {'全部通过' if not fails else '卡在：' + '、'.join(fails)}")
    sys.exit(0)
print(f'样本：{last_a} 年报有分配预案的 {len(df)} 只（全A {len(spot)} 只；没有分配预案的公司不分红，直接不进池）')
print(f'口径：PE/PB 用 {last_a} 年报 EPS/BPS × 最新价；股息率 = ({last_a} 年报 + {"、".join(last_i) or "无"} 中报，无今年中报预案的退回用 {"、".join(prev_i) or "无"}) 每股现金分红 / 最新价；10Y {cn10:.3f}%')
mask = pd.Series(True, index=df.index)
print('\n漏斗（逐条叠加）：')
for name, c in checks:
    mask &= c.fillna(False)
    print(f'  {name:<22} 剩 {mask.sum():>4}')

r = df[mask].copy()
r['规模'] = r['cap'].map(lambda c: next(t for lim, t in TIER if c >= lim))
r['_t'] = r['规模'].map({t: i for i, (_, t) in enumerate(TIER)})
r['周期?'] = r['eps_cv'].map(lambda v: '周期?' if v > RULE['cyc_cv'] else '')
r['pb'] = r['pb'].mask(r['pb_bad'])  # 打印成 NaN = 源数据异常
# 近12个月分红 > 年报 EPS：多半含特别分红或中报一次性大派，股息率不可持续（健康元 9.1%、海澜之家 10.5% 这类）
r['周期?'] = r['周期?'] + r.apply(lambda x: ' 特别分红?' if x['dps_ttm'] > x['eps'] else '', axis=1)
r['行业地位'] = r.apply(lambda x: f"第{x['ind_rank']:.0f}/{x['ind_n']:.0f}" if pd.notna(x['ind_rank']) else '?', axis=1)
r['行业PE'] = r['ind_pe']
r = r.sort_values(['_t', 'dy'], ascending=[True, False])
COLS = ['名称', '行业', '行业地位', '规模', 'cap', 'pe', '行业PE', 'pb', 'dy', 'payout', 'np_yoy', 'eps_cv', '周期?', '指数']
NAMES = {'cap': '市值亿', 'pe': 'PE', 'pb': 'PB', 'dy': '股息率%', 'payout': '派息率', 'np_yoy': '净利同比%', 'eps_cv': 'EPS波动'}
RND = {'市值亿': 0, 'PE': 1, '行业PE': 1, 'PB': 2, '股息率%': 2, '派息率': 2, '净利同比%': 1, 'EPS波动': 2}
fmt = lambda x: x[COLS].rename(columns=NAMES).round(RND)
out = fmt(r)
nf, fi = r[~r['fin']], r[r['fin']]
# 非金融：每个行业取行业内市值排名最靠前的 per_ind 只（"全国第一"的代理），再按规模档、股息率排
nf_top = nf.sort_values('ind_rank').groupby('行业', group_keys=False).head(RULE['per_ind']).sort_values(['_t', 'dy'], ascending=[True, False])
print(f"\n通过 {len(out)} 只：非金融 {len(nf)} 只（{nf['行业'].nunique()} 个行业）、金融 {len(fi)} 只")
print(f"\n== 非金融：每行业最多 {RULE['per_ind']} 只（按行业内市值排名），共 {len(nf_top)} 只（前 {a.top}）==")
print(fmt(nf_top).head(a.top).to_string())
print('\n非金融行业分布：', nf['行业'].value_counts().head(15).to_dict())
print(f"\n== 金融（银行/保险/券商）{len(fi)} 只，前 12（按规模档、股息率）==")
print(fmt(fi).head(12).to_string())
rk_lim = r['ind_rank'] <= r['fin'].map({True: 10, False: RULE['core_rank']})  # 银行 44 家、券商 51 家，金融放到前 10
leader = (r['ind_rank'] == 1) & (r['eps_cv'] <= RULE['core_cv_leader'])
core = r[rk_lim & (r['cap'] >= RULE['core_cap']) & (r['eps_cv'] <= RULE['core_cv']) & (r['周期?'] == '')
         & (r['dy'] >= RULE['core_dy']) & ((r['np_yoy'] >= RULE['core_np']) | (leader & (r['np_yoy'] >= RULE['core_np_leader'])))]
core = core.assign(入选=lambda x: x.apply(lambda y: '龙头放宽' if y['np_yoy'] < RULE['core_np'] else '', axis=1))
print(f"\n== 精选档（最符合标准）{len(core)} 只：非金融在前，按股息率 ==")
print(core.sort_values(['fin', 'dy'], ascending=[True, False])[COLS + ['入选']].rename(columns=NAMES).round(RND).to_string())
out['精选'] = out.index.isin(core.index)
out['dps_ttm'] = r['dps_ttm'].round(4)  # 盘中用：实时股息率 = dps_ttm / 实时价
print('\n规模档分布：', out['规模'].value_counts().to_dict())
print('未覆盖：行业地位只按新浪行业内市值排名代理，"全国第一/全球最好"、题材属性需人工核对；行业 PE 用新浪动态 PE 中位，个股 PE 用年报 EPS，口径不完全一致。')
if a.csv:
    f = os.path.join(S, f'result_{dt.date.today():%Y%m%d}.csv')
    out.to_csv(f, encoding='utf-8-sig')
    print('已落盘', f)
