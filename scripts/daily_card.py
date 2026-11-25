"""李大霄框架 · 盘前/盘后基调卡（客观读数部分）

usage: python daily_card.py [--fetch] [--data DIR]
  --fetch  用 akshare 重新拉数据到 DIR（默认 ./data）
输出：各读数 + 隔夜外盘 + 分板块估值 + 四个信号灯（恐慌/狂热/国家队/巨量不涨）+ 一行估值基调。
补充源由 fetch_extra.py 拉取；文件缺失的块自动跳过。股东增减持明细未接。
"""
import argparse, os, sys
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--fetch', action='store_true')
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
a = ap.parse_args()
D = a.data
os.makedirs(D, exist_ok=True)

if a.fetch:
    from akcompat import ak
    ak.stock_zh_index_daily(symbol='sh000001').to_csv(f'{D}/sse.csv', index=False)
    ak.stock_a_ttm_lyr().to_csv(f'{D}/a_pe.csv', index=False)
    ak.stock_a_all_pb().to_csv(f'{D}/a_pb.csv', index=False)
    ak.stock_a_below_net_asset_statistics(symbol='全部A股').to_csv(f'{D}/below_net.csv', index=False)
    ak.stock_index_pe_lg(symbol='上证50').to_csv(f'{D}/pe_sz50.csv', index=False)
    b = ak.bond_zh_us_rate(start_date='20070101')
    b.iloc[:, [0, 3]].set_axis(['date', 'cn10y'], axis=1).to_csv(f'{D}/bond10.csv', index=False)
    # 补充源 + 当日收盘（历史接口常晚一天，这里用实时行情补当天一行）
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_extra.py')], check=False)

sse = pd.read_csv(f'{D}/sse.csv', parse_dates=['date']).set_index('date')['close']
pe = pd.read_csv(f'{D}/a_pe.csv', parse_dates=['date']).iloc[-1]
pb = pd.read_csv(f'{D}/a_pb.csv', parse_dates=['date']).iloc[-1]
bn = pd.read_csv(f'{D}/below_net.csv', parse_dates=['date'])
bd = pd.read_csv(f'{D}/bond10.csv')
cn10 = pd.to_numeric(bd.iloc[:, 1] if bd.shape[1] == 2 else bd.iloc[:, 3], errors='coerce').dropna().iloc[-1]

last = sse.index[-1]
hi3 = sse[sse.index >= last - pd.DateOffset(years=3)]
peak_d = hi3.idxmax()
dd = sse.iloc[-1] / hi3.max() - 1
months_since_peak = (last - peak_d).days / 30.4
bn_q = (bn['below_net_asset_ratio'] <= bn['below_net_asset_ratio'].iloc[-1]).mean()

pe_q = float(pe['quantileInRecent10YearsMiddlePeTtm'])
pb_q = float(pb['quantileInRecent10YearsMiddlePB'])
val_q = (pe_q + pb_q) / 2
# 蓝筹优先（回放盲测 v2 验证）：上证50 滚动PE 近10年分位定阶段，全A中位只作参考
s50_q = None
if os.path.exists(f'{D}/pe_sz50.csv'):
    s5 = pd.read_csv(f'{D}/pe_sz50.csv')
    s5 = pd.Series(pd.to_numeric(s5['滚动市盈率'], errors='coerce').values, index=pd.to_datetime(s5['日期'])).dropna()
    # 用 2005 至今全样本分位：与回放盲测 v2 / analog.py 口径一致（近10年窗口未经验证，会显著偏高）
    s50_q = float((s5 <= s5.iloc[-1]).mean())
    s5_10 = s5[s5.index >= s5.index[-1] - pd.DateOffset(years=10)]
    s50_q10 = float((s5_10 <= s5_10.iloc[-1]).mean())
    s50_pe = float(s5.iloc[-1])
stage_q = s50_q if s50_q is not None else val_q
tone = '勇气/播种' if stage_q < 0.2 else ('淡泊/摘果子' if stage_q > 0.8 else '坚持')

print(f'日期 {last.date()}  上证 {sse.iloc[-1]:.2f}')
print(f'[F1] 全A 中位PE-TTM {pe["middlePETTM"]} (10年分位 {pe_q:.0%}) | 中位PB {pb["middlePB"]} (10年分位 {pb_q:.0%})')
print(f'[R8补] 破净股占比 {bn["below_net_asset_ratio"].iloc[-1]:.1%} (2005起历史分位 {bn_q:.0%})')
print(f'[F8] 距3年高点 {hi3.max():.2f}@{peak_d.date()} 回撤 {dd:.1%}，已过 {months_since_peak:.0f} 个月')


def _p(name):
    return os.path.join(D, name) if os.path.exists(os.path.join(D, name)) else None


def q(series, x):
    return float((series <= x).mean())


# 当日情绪（涨跌家数）
if _p('activity.csv'):
    ac = pd.read_csv(_p('activity.csv')).iloc[-1]
    print(f"[情绪] {ac['date']} 上涨 {int(ac['上涨'])} / 下跌 {int(ac['下跌'])} 家，真实涨停 {int(ac['真实涨停'])} / 真实跌停 {int(ac['真实跌停'])}，活跃度 {ac['活跃度']}")
    print(f"       上证当日 {sse.iloc[-1] / sse.iloc[-2] - 1:+.2%}")
# R18 股债差：上证A股股息率 - 10Y
if _p('gxl.csv'):
    g = pd.read_csv(_p('gxl.csv'), parse_dates=['日期']).set_index('日期')['股息率']
    b = pd.read_csv(f'{D}/bond10.csv')
    b = pd.Series(pd.to_numeric(b.iloc[:, -1], errors='coerce').values, index=pd.to_datetime(b.iloc[:, 0])).dropna()
    spread = (g.reindex(b.index, method='ffill') - b).dropna()
    print(f"[R18] 上证A股股息率 {g.iloc[-1]:.2f}% − 10Y {b.iloc[-1]:.3f}% = 股债差 {spread.iloc[-1]:+.2f}pp（2007起分位 {q(spread, spread.iloc[-1]):.0%}）")
# F6 杠杆：融资余额
if _p('margin.csv'):
    m = pd.read_csv(_p('margin.csv'), parse_dates=['日期']).set_index('日期')
    fz = m['融资余额']
    ch20 = fz.iloc[-1] / fz.iloc[-21] - 1
    buy = m['融资买入额']
    wb = m['平均维持担保比例'].dropna()
    print(f"[F6] 融资余额 {fz.iloc[-1]:,.0f} 亿（2012起分位 {q(fz, fz.iloc[-1]):.0%}，近20日 {ch20:+.1%}）| 融资买入 {buy.iloc[-1]:,.0f} 亿（近1年分位 {q(buy.iloc[-250:], buy.iloc[-1]):.0%}）"
          f"| 维持担保比例 {wb.iloc[-1]:.0f}%@{wb.index[-1].date()}（截至 {fz.index[-1].date()}）")
# F5 新发偏股基金（主动：股票型 + 混合型-偏股；被动：指数型-股票）
if _p('fund_new.csv'):
    fn = pd.read_csv(_p('fund_new.csv'), parse_dates=['成立日期'])
    fn['kind'] = fn['基金类型'].map(lambda t: '主动' if t in ('股票型', '混合型-偏股') else ('被动' if t == '指数型-股票' else None))
    mo = fn.dropna(subset=['kind']).groupby([pd.Grouper(key='成立日期', freq='ME'), 'kind'])['募集份额'].sum().unstack().fillna(0)
    act3 = mo['主动'].rolling(3).sum().dropna()
    last = fn['成立日期'].max()
    rec = fn[(fn['成立日期'] > last - pd.Timedelta(days=30)) & fn['kind'].notna()]
    big = (rec['募集份额'] >= 50).sum()
    print(f"[F5] 近30天新成立 主动偏股 {rec[rec.kind=='主动']['募集份额'].sum():.0f} 亿份 / 指数型 {rec[rec.kind=='被动']['募集份额'].sum():.0f} 亿份，单只≥50亿份 {big} 只 | 主动近3月滚动 2013起分位 {q(act3, act3.iloc[-1]):.0%}（数据截至 {last.date()}）")
# F7 新股：近 20 只上市新股首日破发率、近 30 天上市家数
if _p('ipo.csv'):
    ip = pd.read_csv(_p('ipo.csv'))
    ip['上市日期'] = pd.to_datetime(ip['上市日期'], format='mixed', errors='coerce')  # 东财有时带时分
    ip = ip.dropna(subset=['上市日期', '首日收盘价', '发行价格']).sort_values('上市日期')
    ip = ip[ip['板块'] != '北交所']
    l20 = ip.tail(20)
    brk = (l20['首日收盘价'] < l20['发行价格']).mean()
    gain = (l20['首日收盘价'] / l20['发行价格'] - 1).median()
    n30 = (ip['上市日期'] > ip['上市日期'].max() - pd.Timedelta(days=30)).sum()
    # 基准：近一年上市新股（注册制放开前5日涨跌幅后，首日 +100%~+200% 是常态，不能直接当"炒新热"）
    y1 = ip[ip['上市日期'] > ip['上市日期'].max() - pd.DateOffset(years=1)]
    g1 = (y1['首日收盘价'] / y1['发行价格'] - 1)
    b1 = (y1['首日收盘价'] < y1['发行价格']).mean()
    rel = gain / g1.median() if g1.median() > 0 else float('nan')
    verdict = '偏热' if rel >= 1.5 or (brk == 0 and b1 >= 0.1) else ('偏冷' if rel <= 0.5 or brk >= 2 * b1 + 0.1 else '常态')
    print(f"[F7] 近20只新股（沪深）首日破发率 {brk:.0%}，首日涨幅中位 {gain:+.0%} | 近1年基准：破发率 {b1:.0%}、涨幅中位 {g1.median():+.0%}（{len(y1)} 只）"
          f" => 相对基准 {rel:.1f} 倍，{verdict} | 近30天上市 {n30} 家")
# F3 产业资本（回购代理；增减持接口全量翻页过慢，未接）
if _p('repurchase.csv'):
    rp = pd.read_csv(_p('repurchase.csv'), parse_dates=['最新公告日期', '回购起始时间'])
    cut = rp['最新公告日期'].max() - pd.Timedelta(days=30)
    newp = rp[rp['回购起始时间'] > cut]
    amt = newp['计划回购金额区间-上限'].sum() / 1e8
    print(f"[F3] 近30天新启动回购 {len(newp)} 家，计划金额上限合计 {amt:,.0f} 亿元（回购代理；增减持未接入）")
# F4 国家队 ETF 份额
if _p('etf_nat.csv'):
    et = pd.read_csv(_p('etf_nat.csv'), dtype={'code': str})
    tot = et.groupby('date')['shares'].sum().sort_index() / 1e8
    if len(tot) >= 2:
        d1 = tot.diff().dropna()
        z = (d1.iloc[-1] - d1.mean()) / d1.std() if len(d1) > 5 and d1.std() > 0 else float('nan')
        c5 = tot.iloc[-1] - tot.iloc[-6] if len(tot) > 5 else float('nan')
        print(f"[F4] 宽基ETF(沪市6只)份额 {tot.iloc[-1]:,.0f} 亿份 @{tot.index[-1]}，当日 {d1.iloc[-1]:+.1f} 亿份（z={z:.1f}），近5日 {c5:+.1f} 亿份（样本 {len(tot)} 天）")
# 隔夜外盘（盘前用）：日期早于今天的说明该市场还没开/没收
if _p('overnight.csv'):
    on = pd.read_csv(_p('overnight.csv'))
    print('[隔夜] ' + ' | '.join(f"{r['name']} {r['close']:,.2f} {r['chg']:+.2%}@{r['date']}" if r['name'] != 'USDCNH'
                               else f"USDCNH {r['close']:.4f} {r['chg']:+.2%}@{r['date']}" for _, r in on.iterrows()))
    # 盘前时点检查：外盘是否已走完 A 股收盘日那一夜
    import datetime as _dt
    adate = str(sse.index[-1].date())
    us = on[on['name'].isin(['标普500', '纳指', '道指'])]['date']
    a50 = on[on['name'] == '富时A50期货']
    us_done = len(us) and str(us.max()) >= adate
    now = _dt.datetime.now()
    a50_done = now >= _dt.datetime.fromisoformat(adate) + _dt.timedelta(days=1, hours=5)
    if us_done and a50_done:
        print(f'[盘前时点] 外盘已走完 {adate} 当夜，可以下盘前结论')
    else:
        miss = ([] if us_done else [f'美股 {adate} 盘未收（最新 {us.max() if len(us) else "无"}）']) + ([] if a50_done else ['A50 夜盘未结束'])
        a50_txt = f"，A50 现报 {a50['close'].iloc[0]:,.0f}（{a50['chg'].iloc[0]:+.2%}）" if len(a50) else ''
        print(f"[盘前时点] 未就绪：{'；'.join(miss)}{a50_txt}。此时只能写条件句，或明早 08:30 后重跑 --fetch")
    if len(a50):
        # 条件线：以 A 股收盘日 A50 日盘收盘为基准；修复线 = 收回基准，偏弱线 = 基准 −0.8%（约 A50 日波动 1σ 的一半）
        base = float(a50['prev'].iloc[0]) if str(a50['date'].iloc[0]) > adate else float(a50['close'].iloc[0])
        print(f"[A50条件线] 基准 {base:,.0f}（{adate} 日盘收）｜偏弱线 {base * 0.992:,.0f}（-0.8%）｜修复线 {base:,.0f}｜现报 {a50['close'].iloc[0]:,.0f}")
# 分指数估值：乐咕月末历史 2005 起分位；中证官方只有近 20 日，给水平和股息率−10Y
if _p('sector_lg.csv'):
    sl = pd.read_csv(_p('sector_lg.csv'))
    parts = []
    for k, g in sl.groupby('index', sort=False):
        g = g.sort_values('date')
        pe_s = pd.to_numeric(g['pe'], errors='coerce').dropna()
        pb_s = pd.to_numeric(g['pb'], errors='coerce').dropna()
        if len(pe_s):
            parts.append(f"{k} PE {pe_s.iloc[-1]:.2f}({q(pe_s, pe_s.iloc[-1]):.0%}) PB {pb_s.iloc[-1]:.2f}({q(pb_s, pb_s.iloc[-1]):.0%}) 自{str(g['date'].iloc[0])[:7]}起{len(pe_s)}个月")
    print(f"[分板块] {' | '.join(parts)}（括号=该指数有数据以来的月末分位，起点各不同，截至 {sl['date'].max()}）")
if _p('csindex.csv'):
    ci = pd.read_csv(_p('csindex.csv')).sort_values('date').groupby('index').tail(1)
    print('[红利银行] ' + ' | '.join(f"{r['index']} PE {r['pe']:.2f} 股息率 {r['dy']:.2f}%（−10Y {r['dy'] - cn10:+.2f}pp）" for _, r in ci.iterrows())
          + f"（中证官方，截至 {ci['date'].max()}）")

# 四个信号灯（阈值见 worldview 3.x；亮=触发）
vol = pd.read_csv(f'{D}/sse.csv', parse_dates=['date']).set_index('date')['volume']
hot60 = float((vol.iloc[-60:] > vol.iloc[-750:].quantile(0.8)).mean())
dd60 = float(sse.iloc[-1] / sse.iloc[-60:].max() - 1)
lights = []
# 涨跌幅阈值用上证 2005 起日收益分布校准：单靠"下跌占比≥85%"在普通 -2% 日也会亮（2026-11-25 实测）。
# 涨跌家数历史目前只有 activity.csv 逐日累积的样本（乐咕只给当天）；满 250 天后改用其自身分位。
ret = sse[sse.index >= '2005-01-01'].pct_change().dropna()
r0 = float(ret.iloc[-1])
r_lo, r_hi = float(ret.quantile(0.03)), float(ret.quantile(0.97))
r_q = q(ret, r0)
if _p('activity.csv'):
    acs = pd.read_csv(_p('activity.csv'))
    ac = acs.iloc[-1]
    up, dn, zt, dt_ = float(ac['上涨']), float(ac['下跌']), float(ac['真实涨停']), float(ac['真实跌停'])
    dn_sh = dn / (up + dn)
    if len(acs) >= 250:
        sh = acs['下跌'] / (acs['上涨'] + acs['下跌'])
        br_lo, br_hi, br_note = float(sh.quantile(0.95)), float(1 - sh.quantile(0.05)), f'涨跌家数自身 95% 分位（{len(acs)} 天）'
    else:
        br_lo, br_hi, br_note = 0.85, 0.85, f'涨跌家数暂用固定 85%（历史仅 {len(acs)} 天）'
    stampede = dt_ >= 100 and dt_ >= 3 * zt
    panic = (r0 <= r_lo and dn_sh >= br_lo) or stampede
    lights.append(f"恐慌[{'亮' if panic else '灭'}] 上证 {r0:+.2%}（2005起日收益分位 {r_q:.1%}，阈值 ≤{r_lo:+.2%} 即 3% 分位）且下跌占比 {dn_sh:.0%}（≥{br_lo:.0%}）"
                  f"；或踩踏：跌停 {dt_:.0f}（≥100 且 ≥3×涨停 {zt:.0f}）{'【踩踏】' if stampede else ''}｜{br_note}")
    if not panic and dn_sh >= 0.85:
        lights[-1] += '｜注：普跌但幅度不够极端，算"弱"，不算恐慌'
    fren = [f'上证 {r0:+.2%}（≥{r_hi:+.2%} 即 97% 分位）且上涨占比 {1 - dn_sh:.0%}（≥{br_hi:.0%}）且涨停 {zt:.0f}（≥100）']
    hot = r0 >= r_hi and (1 - dn_sh) >= br_hi and zt >= 100
else:
    fren, hot = [], False
if _p('margin.csv'):
    mm = pd.read_csv(_p('margin.csv'), parse_dates=['日期']).set_index('日期')
    bq = q(mm['融资买入额'].iloc[-250:], mm['融资买入额'].iloc[-1])
    c20 = mm['融资余额'].iloc[-1] / mm['融资余额'].iloc[-21] - 1
    hot = hot or (bq >= 0.95 and c20 >= 0.08)
    fren.append(f'融资买入1年分位 {bq:.0%}且余额20日 {c20:+.0%}（≥95%且≥+8%）')
if fren:
    lights.append(f"狂热[{'亮' if hot else '灭'}] " + '；'.join(fren))
if _p('etf_nat.csv'):
    et = pd.read_csv(_p('etf_nat.csv'), dtype={'code': str})
    tot = et.groupby('date')['shares'].sum().sort_index() / 1e8
    d1 = tot.diff().dropna()
    if len(d1) > 5 and d1.std() > 0:
        z = (d1.iloc[-1] - d1.mean()) / d1.std()
        # 上交所份额 T+1 公布，晚一个交易日算正常；再旧就不判
        prev_td = str(sse.index[-2].date())
        stale = str(tot.index[-1]) < prev_td
        c5 = tot.iloc[-1] - tot.iloc[-6] if len(tot) > 5 else float('nan')
        d5 = tot.diff(5).dropna()
        z5 = (c5 - d5.mean()) / d5.std() if len(d5) > 5 and d5.std() > 0 else float('nan')
        st = '?' if stale else ('亮' if z >= 3 or z5 >= 3 else '灭')
        lights.append(f"国家队[{st}] 宽基ETF份额 {tot.index[-1]} 当日 {d1.iloc[-1]:+.1f} 亿份 z={z:.1f}（≥3）；近5日 {c5:+.1f} 亿份 z={z5:.1f}（≥3）"
                      + (f'｜数据早于 {prev_td}，不作判断' if stale else '｜上交所 T+1 公布，读数晚一天'))
    else:
        lights.append(f'国家队[?] ETF 份额样本 {len(tot)} 天，不够算 z')
else:
    lights.append('国家队[?] 无 ETF 份额数据')
lights.append(f"巨量不涨[{'亮' if hot60 > 0.6 and dd60 > -0.08 else '灭'}] 近60日巨量占比 {hot60:.0%}（>60%）且距60日高点 {dd60:.1%}（>-8%）")
print('[信号灯] ' + '\n         '.join(lights))
print('未接：股东增减持明细（接口过慢）、两融占流通市值（缺流通市值历史）')
if s50_q is not None:
    print(f'[F1蓝筹] 上证50 滚动PE {s50_pe:.2f} (2005起分位 {s50_q:.0%}；近10年分位 {s50_q10:.0%} 仅参考)')
# 数据脚注（formats.md 规则 7）：直接抄进回答末尾，用不到的源删掉
foot = [f'收盘 {sse.index[-1]:%m-%d}']
if _p('margin.csv'):
    foot.append(f"两融 {pd.to_datetime(pd.read_csv(_p('margin.csv'))['日期'].iloc[-1]):%m-%d}")
if _p('etf_nat.csv'):
    foot.append(f"ETF {pd.to_datetime(pd.read_csv(_p('etf_nat.csv'))['date'].max()):%m-%d}")
if _p('fund_new.csv'):
    foot.append(f"新发基金 {pd.to_datetime(pd.read_csv(_p('fund_new.csv'))['成立日期']).max():%m-%d}")
if _p('overnight.csv'):
    foot.append(f"外盘 {pd.Timestamp(os.path.getmtime(_p('overnight.csv')), unit='s', tz='UTC').tz_convert('Asia/Shanghai'):%H:%M}")
print('[脚注] 数据：' + '｜'.join(foot))
print(f'=> 估值基调：{tone}（定阶段用{"上证50" if s50_q is not None else "全A"}分位 {stage_q:.0%}；全A均分位 {val_q:.0%}）')
