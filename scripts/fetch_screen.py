"""选股尺子所需的个股数据（慢，按需跑，结果缓存在 data/screen/）。

usage: python fetch_screen.py [--years 2021,2022,2023,2024,2025] [--refresh-annual]
- fhps_<YYYYMMDD>.csv  东财分红送配（年报 + 中报），含每股收益、每股净资产、总股本、净利润同比、现金分红（每10股）、除息日。
                       历年年报不会变，已有就不重拉（--refresh-annual 强制）；最近两期中报/年报每次重拉。
- spot.csv             新浪全A实时行情（价格）。
- industry.csv         新浪行业板块（证监会口径 84 个）成分：code, industry, pe, pb, cap(亿)。用于行业相对估值和行业内市值排名。
- cons_<code>.csv      中证指数成分：000300 沪深300、000922 中证红利、000905 中证500、000016 上证50。
每个源独立子进程 + 超时，并发 3 个。
"""
import argparse, os, sys, subprocess, datetime as dt
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, 'data', 'screen')
os.makedirs(S, exist_ok=True)
ap = argparse.ArgumentParser()
ap.add_argument('--years', default=','.join(str(y) for y in range(dt.date.today().year - 5, dt.date.today().year)))
ap.add_argument('--refresh-annual', action='store_true')
a = ap.parse_args()

years = [int(y) for y in a.years.split(',')]
this = dt.date.today().year
periods = [f'{y}1231' for y in years] + [f'{this - 1}0630', f'{this}0630']
recent = {f'{years[-1]}1231', f'{this}0630', f'{this - 1}0630'}

tasks = []
for p in periods:
    f = os.path.join(S, f'fhps_{p}.csv')
    if os.path.exists(f) and p not in recent and not a.refresh_annual:
        continue
    tasks.append((f'fhps_{p}', f"ak.stock_fhps_em(date='{p}').to_csv(r'{f}', index=False)", 300))
tasks.append(('spot', f"ak.stock_zh_a_spot().to_csv(r'{os.path.join(S, 'spot.csv')}', index=False)", 180))
IND = os.path.join(S, 'industry.csv')
tasks.append(('industry', f'''
import pandas as pd, time
from concurrent.futures import ThreadPoolExecutor
sec = ak.stock_sector_spot(indicator='行业')
def one(row):
    for _ in range(3):
        try:
            d = ak.stock_sector_detail(sector=row['label'])
            return pd.DataFrame({{'code': d['code'].astype(str), 'industry': row['板块'], 'pe': d['per'], 'pb': d['pb'], 'cap': d['mktcap'] / 1e4}})
        except Exception:
            time.sleep(2)
    return pd.DataFrame()
with ThreadPoolExecutor(4) as ex:
    out = pd.concat(list(ex.map(one, [r for _, r in sec.iterrows()])))
out.drop_duplicates('code').to_csv(r'{IND}', index=False)
print(len(out), out['industry'].nunique())
''', 600))
for c in ['000300', '000922', '000905', '000016']:
    tasks.append((f'cons_{c}', f"ak.index_stock_cons_weight_csindex(symbol='{c}').to_csv(r'{os.path.join(S, f'cons_{c}.csv')}', index=False)", 120))


def run(t):
    name, code, to = t
    msg = ''
    for attempt in range(3):  # 东财分页偶发 ChunkedEncodingError，重试
        try:
            r = subprocess.run([sys.executable, '-c', f'import sys\nsys.path.insert(0, {HERE!r})\nfrom akcompat import ak\n{code}'], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=to)
            if r.returncode == 0:
                return f'OK   {name}' + (f'（第 {attempt + 1} 次）' if attempt else '')
            msg = (r.stderr.strip().splitlines() or ['?'])[-1][:120]
        except subprocess.TimeoutExpired:
            msg = f'超时 >{to}s'
    return f'FAIL {name} {msg}（已试 3 次）'


with ThreadPoolExecutor(3) as ex:
    for line in ex.map(run, tasks):
        print(line, flush=True)
