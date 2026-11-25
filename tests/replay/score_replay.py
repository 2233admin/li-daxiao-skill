"""Score blind replay. usage: python score_replay.py <replay_dir>"""
import sys, os, json, re
sys.stdout.reconfigure(encoding='utf-8')
R = sys.argv[1]
PK = sys.argv[2] if len(sys.argv) > 2 else 'pkg'
AN = sys.argv[3] if len(sys.argv) > 3 else 'ans'
man = json.load(open(f'{R}/{PK}/manifest.json', encoding='utf-8'))
rows = []
for m in man:
    p = f"{R}/{AN}/{m['tid']}.txt"
    txt = open(p, encoding='utf-8').read() if os.path.exists(p) else ''
    js = None
    for mm in re.finditer(r'\{[^{}]*"direction"[^{}]*\}', txt):
        try:
            js = json.loads(mm.group(0))
        except Exception:
            pass
    val = ((m['pe_q'] or 0) + (m['pb_q'] or 0)) / 2 if m['pe_q'] is not None else None
    rule = 'bear' if (val is not None and val > 0.8) else 'bull'  # 估值分位规则：>80% 淡泊=看空，否则偏多
    s5, h6, d6 = m.get('s50_q'), m.get('hot60'), m.get('dd60')
    rule2 = 'bear' if ((s5 or 0) > 0.8 or ((h6 or 0) > 0.6 and (d6 or -1) > -0.08)) else 'bull'
    rows.append({**m, 'rule2': rule2, 'persona': (js or {}).get('direction'), 'stage': (js or {}).get('stage'),
                 'conf': (js or {}).get('confidence'), 'rule': rule, 'always_bull': 'bull', 'val_q': val})


def metrics(key):
    ok = [r for r in rows if r[key]]
    acc = sum(r[key] == r['truth'] for r in ok) / len(ok)
    labels = ['bull', 'bear', 'neutral']
    n = len(ok)
    pe = sum((sum(r['truth'] == l for r in ok) / n) * (sum(r[key] == l for r in ok) / n) for l in labels)
    kappa = (acc - pe) / (1 - pe) if pe < 1 else 0
    bear = [r for r in ok if r['truth'] == 'bear']
    bear_rec = sum(r[key] == 'bear' for r in bear) / len(bear) if bear else None
    pred_bear = [r for r in ok if r[key] == 'bear']
    bear_prec = sum(r['truth'] == 'bear' for r in pred_bear) / len(pred_bear) if pred_bear else None
    return {'n': n, 'acc': round(acc, 3), 'kappa': round(kappa, 3), 'bear_recall': bear_rec and round(bear_rec, 3),
            'bear_precision': bear_prec and round(bear_prec, 3)}


res = {k: metrics(k) for k in ('persona', 'rule', 'rule2', 'always_bull')}
print(json.dumps(res, ensure_ascii=False, indent=1))
print('\ntid  asof        truth   persona stage conf  rule  val_q')
for r in rows:
    flag = '' if r['persona'] == r['truth'] else '  <-- 不一致'
    print(f"{r['tid']} {r['asof']} {r['truth']:7} {str(r['persona']):7} {str(r['stage']):4} {str(r['conf']):5} {r['rule']:5} {r['val_q'] if r['val_q'] is None else round(r['val_q'],2)}{flag}")
json.dump({'metrics': res, 'rows': rows}, open(f'{R}/replay_result_{AN}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)
