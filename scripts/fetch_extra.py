"""补充数据：两融、股息率、新发基金、新股、回购、国家队 ETF 份额、当日涨跌家数、当日收盘、隔夜外盘、分板块估值。

usage: python fetch_extra.py [--etf-backfill N] [--only NAME[,NAME]] [--skip NAME[,NAME]]
全部写入 ./data/。每个源在独立子进程里跑，带硬超时（akshare 不设请求超时，单个源卡住曾拖死全部，
2026-11-25 实测 gxl 挂 3 小时）。失败或超时只打印一行，不影响其它源。
数据源优先级：能走本地 tdxcli-rs（TQLEX，通达信自家 HTTP）的先走它（margin_tq / ipo_tq），只补文件里缺的近期行；
akshare 同名任务负责深历史和额外字段，两边合并不互相覆盖丢行，任一边挂了另一边兜底。
本地 tdxcli-rs 是可选的：设环境变量 TDXCLI_REPO=<仓库目录> 才启用，否则这两项跳过。
- margin.csv      两融（东财 2012-09 起含维持担保比例；TQLEX 近一年沪深北合计补最新日；单位：亿元；`来源` 列标记）
- ipo.csv         新股（东财全量；TQLEX ipo_result 补最近 30 只，srzf 首日涨幅与东财逐只一致）
- gxl.csv         上证A股股息率（乐咕，2005 起，%）
- fund_new.csv    新成立基金（东财，2013 起，募集份额：亿份）
- ipo.csv         新股申购与上市（东财，含发行价、首日收盘价、上市日期）
- repurchase.csv  回购快照（东财，含最新公告日期、计划金额；接口慢，超时 300s）
- etf_nat.csv     国家队常用宽基 ETF 份额（上交所，逐交易日增量累积）
- activity.csv    当日涨跌/涨停跌停家数（乐咕，逐日追加）
- sse.csv         若新浪实时行情给出更新的收盘，则追加当日一行（成交量 手→股 ×100）
- overnight.csv   隔夜外盘：标普500/纳指/道指、恒指/恒生科技、富时A50期货连续（含夜盘）、USDCNH
- sector_lg.csv   分指数 PE(滚动)/PB 月末历史（乐咕，2005 起）：上证50/沪深300/上证红利/中证500/中证1000
- csindex.csv     中证官方 PE/股息率（近 20 日，逐日累积）：中证红利/中证银行/中证A50
"""
import argparse, os, sys, subprocess, datetime as dt, time
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data')
os.makedirs(D, exist_ok=True)
ap = argparse.ArgumentParser()
ap.add_argument('--etf-backfill', type=int, default=20, help='ETF 份额缺失时最多回补多少个交易日')
ap.add_argument('--only', default='', help='只跑这些源（逗号分隔）；子进程模式也用它')
ap.add_argument('--skip', default='', help='跳过这些源（逗号分隔）')
ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
a = ap.parse_args()

NAT_ETF = {'510300': '华泰柏瑞沪深300', '510310': '易方达沪深300', '510330': '华夏沪深300',
           '510050': '华夏上证50', '510500': '南方中证500', '588000': '华夏科创50'}


def save(df, f):
    df.to_csv(os.path.join(D, f), index=False)
    return len(df)


def upsert(df, f, keys):
    p = os.path.join(D, f)
    old = pd.read_csv(p, dtype=str) if os.path.exists(p) else pd.DataFrame()
    df = df.astype(str)
    new = pd.concat([old, df]).drop_duplicates(keys, keep='last').sort_values(keys)
    return save(new, f)


# 可选：本地 tdxcli-rs（通达信 TQLEX 命令行）。不设 TDXCLI_REPO 就跳过 margin_tq / ipo_tq，只用 akshare。
TDX_REPO = os.environ.get('TDXCLI_REPO', '')
TDX_EXE = os.path.join(TDX_REPO, 'target', 'release', 'tdx-cli.exe' if os.name == 'nt' else 'tdx-cli')


def tq(query):
    """tdxcli-rs TQLEX datacenter（通达信自家 HTTP，非东财）。须在仓库目录里跑。"""
    import json
    r = subprocess.run([TDX_EXE, 'datacenter', '--query', query, '--json'], capture_output=True, cwd=TDX_REPO, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace')[-150:] or r.stdout.decode('utf-8', 'replace')[-150:])
    return pd.DataFrame(json.loads(r.stdout.decode('utf-8'))['items'])


def merge_keep(new, f, key):
    """new 覆盖同 key 行；文件里 new 没有的 key 行保留（互为兜底，谁晚到都不丢另一边的行）。"""
    p = os.path.join(D, f)
    if os.path.exists(p):
        old = pd.read_csv(p, dtype={key: str})
        new = pd.concat([old[~old[key].astype(str).isin(new[key].astype(str))], new])
    return save(new.sort_values(key), f)


def margin_tq():
    """主源：TQLEX 近一年两融（沪+深+北合计，亿元）。只补文件里没有的日期，akshare 的行字段更全，保留。"""
    x = tq('margin_trading_market_summary')
    g = x.groupby('t001')[['t003', 't004', 't006']].sum().reset_index()
    g.columns = ['日期', '融资余额', '融资买入额', '融券余额']
    g['来源'] = 'tqlex'
    p = os.path.join(D, 'margin.csv')
    old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=['日期'])
    add = g[~g['日期'].isin(old['日期'].astype(str))]
    save(pd.concat([old, add]).sort_values('日期'), 'margin.csv')
    return f'+{len(add)} 天（TQLEX 最新 {g["日期"].max()}）'


def margin():
    """兜底与深历史：akshare 2012 起，含维持担保比例。"""
    from akcompat import ak
    m = ak.stock_margin_account_info()
    m['日期'] = m['日期'].astype(str)
    m['来源'] = 'akshare'
    return merge_keep(m, 'margin.csv', '日期')


def gxl():
    from akcompat import ak
    return save(ak.stock_a_gxl_lg(symbol='上证A股'), 'gxl.csv')


def fund_new():
    from akcompat import ak
    return save(ak.fund_new_found_em(), 'fund_new.csv')


TQ_BOARD = {'012001': ('非科创板', '上海证券交易所'), '012029': ('科创板', '上海证券交易所'),
            '012002': ('非科创板', '深圳证券交易所'), '012015': ('非科创板', '深圳证券交易所'),
            '012046': ('北交所', '北京证券交易所')}


def ipo_tq():
    """主源：TQLEX 最近 30 只已上市新股。srzf=首日涨幅%（2026-11-25 与东财 30/30 逐只一致）。"""
    x = tq('ipo_result')
    df = pd.DataFrame({'股票代码': x['zqdm'].astype(str), '股票简称': x['zqjc'],
                       '板块': x['t007'].map(lambda k: TQ_BOARD.get(k, ('?', '?'))[0]),
                       '交易所': x['t007'].map(lambda k: TQ_BOARD.get(k, ('?', '?'))[1]),
                       '发行价格': x['t010'], '首日收盘价': (x['t010'] * (1 + x['srzf'] / 100)).round(2),
                       '上市日期': pd.to_datetime(x['st008'].astype(str)).dt.strftime('%Y-%m-%d'), '来源': 'tqlex'})
    p = os.path.join(D, 'ipo.csv')
    old = pd.read_csv(p, dtype={'股票代码': str}) if os.path.exists(p) else pd.DataFrame(columns=['股票代码'])
    add = df[~df['股票代码'].isin(old['股票代码'])]
    save(pd.concat([old, add]), 'ipo.csv')
    return f'+{len(add)} 只（TQLEX 最新上市 {df["上市日期"].max()}）'


def ipo():
    """兜底与深历史：东财全量（含未上市）。"""
    from akcompat import ak
    m = ak.stock_xgsglb_em(symbol='全部股票')
    m['股票代码'] = m['股票代码'].astype(str)
    m['来源'] = 'akshare'
    return merge_keep(m, 'ipo.csv', '股票代码')


def repurchase():
    from akcompat import ak
    return save(ak.stock_repurchase_em(), 'repurchase.csv')


def activity():
    from akcompat import ak
    s = ak.stock_market_activity_legu()
    row = dict(zip(s['item'], s['value']))
    row = {'date': str(row.pop('统计日期'))[:10], **row}
    p = os.path.join(D, 'activity.csv')
    old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
    new = pd.concat([old[old['date'] != row['date']] if len(old) else old, pd.DataFrame([row])]).sort_values('date')
    return save(new, 'activity.csv')


def sse_today():
    from akcompat import ak
    sp = ak.stock_zh_index_spot_sina()
    r = sp[sp['代码'] == 'sh000001'].iloc[0]
    p = os.path.join(D, 'sse.csv')
    s = pd.read_csv(p)
    today = dt.date.today().isoformat()
    now = dt.datetime.now()
    if s['date'].iloc[-1] >= today:
        return 'already has ' + s['date'].iloc[-1]
    if now.weekday() >= 5 or now.hour < 15:
        return 'skip（非交易日或未收盘）'
    row = {'date': today, 'open': r['今开'], 'high': r['最高'], 'low': r['最低'], 'close': r['最新价'],
           'volume': int(r['成交量']) * 100}
    s = pd.concat([s, pd.DataFrame([row])])
    save(s, 'sse.csv')
    return f"appended {today} close {r['最新价']}"


def etf_nat():
    from akcompat import ak
    p = os.path.join(D, 'etf_nat.csv')
    old = pd.read_csv(p, dtype={'code': str}) if os.path.exists(p) else pd.DataFrame(columns=['date', 'code', 'name', 'shares'])
    have = set(old['date'].astype(str))
    days = pd.read_csv(os.path.join(D, 'sse.csv'))['date'].astype(str).tolist()[-a.etf_backfill:]
    rows, miss = [], 0
    for d in days:
        if d in have:
            continue
        try:
            e = ak.fund_etf_scale_sse(date=d.replace('-', ''))
        except Exception:
            miss += 1
            continue
        e['基金代码'] = e['基金代码'].astype(str)
        for _, r in e[e['基金代码'].isin(NAT_ETF)].iterrows():
            rows.append({'date': d, 'code': r['基金代码'], 'name': NAT_ETF[r['基金代码']], 'shares': r['基金份额']})
        new = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(['date', 'code']).sort_values(['date', 'code'])
        save(new, 'etf_nat.csv')  # 逐日落盘，超时也不丢
    new = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(['date', 'code']).sort_values(['date', 'code'])
    return f'+{len(rows)} rows, {miss} days unavailable, total days {new["date"].nunique()}'


def overnight():
    """每个品种取最近两根日线：name, date, close, prev, chg。单个品种失败不影响其它。"""
    from akcompat import ak
    src = {
        '标普500': lambda: ak.index_us_stock_sina(symbol='.INX'),
        '纳指': lambda: ak.index_us_stock_sina(symbol='.IXIC'),
        '道指': lambda: ak.index_us_stock_sina(symbol='.DJI'),
        '恒指': lambda: ak.stock_hk_index_daily_sina(symbol='HSI'),
        '恒生科技': lambda: ak.stock_hk_index_daily_sina(symbol='HSTECH'),
        '富时A50期货': lambda: ak.futures_foreign_hist(symbol='CHA50CFD'),
        'USDCNH': lambda: ak.forex_hist_em(symbol='USDCNH').rename(columns={'日期': 'date', '最新价': 'close'}),
    }
    rows, bad = [], []
    for k, f in src.items():
        for attempt in range(2):
            try:
                x = f()[['date', 'close']].dropna().tail(2)
                c, p = float(x['close'].iloc[-1]), float(x['close'].iloc[-2])
                rows.append({'name': k, 'date': str(x['date'].iloc[-1])[:10], 'close': c, 'prev': p, 'chg': c / p - 1})
                break
            except Exception:
                time.sleep(2)
        else:
            bad.append(k)
    save(pd.DataFrame(rows), 'overnight.csv')
    return f'{len(rows)} ok' + (f', fail {bad}' if bad else '')


LG = ['上证50', '沪深300', '上证红利', '中证500', '中证1000']


def sector_lg():
    from akcompat import ak
    out, bad = [], []
    for k in LG:
        try:
            pe = ak.stock_index_pe_lg(symbol=k)[['日期', '滚动市盈率']].rename(columns={'日期': 'date', '滚动市盈率': 'pe'})
            pb = ak.stock_index_pb_lg(symbol=k)[['日期', '市净率']].rename(columns={'日期': 'date', '市净率': 'pb'})
            m = pe.merge(pb, on='date', how='outer')
            m.insert(0, 'index', k)
            out.append(m)
        except Exception:
            bad.append(k)
    n = upsert(pd.concat(out), 'sector_lg.csv', ['index', 'date'])
    return f'{n} rows' + (f', fail {bad}' if bad else '')


CS = {'000922': '中证红利', '399986': '中证银行', '930050': '中证A50'}


def csindex():
    from akcompat import ak
    out, bad = [], []
    for code, name in CS.items():
        try:
            x = ak.stock_zh_index_value_csindex(symbol=code)
            out.append(pd.DataFrame({'index': name, 'date': x['日期'].astype(str), 'pe': x['市盈率1'], 'dy': x['股息率1']}))
        except Exception:
            bad.append(name)
    n = upsert(pd.concat(out), 'csindex.csv', ['index', 'date'])
    return f'{n} rows' + (f', fail {bad}' if bad else '')


# (函数, 超时秒)。顺序：快的、当天要用的在前；慢的回购和逐日 ETF 放最后。
JOBS = {
    'sse_today': (sse_today, 60), 'activity': (activity, 60), 'overnight': (overnight, 120),
    'margin_tq': (margin_tq, 90), 'ipo_tq': (ipo_tq, 90),
    'margin': (margin, 120), 'gxl': (gxl, 120), 'fund_new': (fund_new, 120), 'ipo': (ipo, 120),
    'sector_lg': (sector_lg, 240), 'csindex': (csindex, 120),
    'etf_nat': (etf_nat, 900), 'repurchase': (repurchase, 300),
}

if a.child:
    print(JOBS[a.only][0]())
    sys.exit(0)

names = [n for n in (a.only.split(',') if a.only else JOBS) if n and n not in a.skip.split(',')]
if not (TDX_REPO and os.path.exists(TDX_EXE)):
    skipped = [n for n in names if n.endswith('_tq')]
    names = [n for n in names if not n.endswith('_tq')]
    if skipped:
        print(f'SKIP {",".join(skipped)}（未设 TDXCLI_REPO 或找不到 tdx-cli，只用 akshare）', flush=True)
for n in names:
    t0 = time.time()
    cmd = [sys.executable, os.path.abspath(__file__), '--child', '--only', n, '--etf-backfill', str(a.etf_backfill)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=JOBS[n][1])
        if r.returncode == 0:
            print(f'OK   {n} {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""} ({time.time() - t0:.0f}s)', flush=True)
        else:
            err = (r.stderr.strip().splitlines() or ['?'])[-1]
            print(f'FAIL {n} {err[:150]}', flush=True)
    except subprocess.TimeoutExpired:
        print(f'TIMEOUT {n} >{JOBS[n][1]}s（已落盘的部分保留）', flush=True)
