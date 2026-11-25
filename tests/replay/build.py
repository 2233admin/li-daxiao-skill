"""Build blind replay packages. usage: python build.py <skill_dir> <out_dir>"""
import sys, os, re, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')
SK, OUT = sys.argv[1], sys.argv[2]
HOLD = len(sys.argv) > 3 and sys.argv[3] == 'holdout'
os.makedirs(OUT, exist_ok=True)
# (asof, truth) — truth = his direction that day per ledger (bull/neutral merged to bull)
TESTS = [('2007-11-19', 'bear'), ('2009-02-03', 'bull'), ('2012-01-04', 'bull'), ('2013-08-14', 'bull'),
         ('2015-05-05', 'bear'), ('2015-06-09', 'bear'), ('2015-06-15', 'bear'), ('2015-08-27', 'bull'),
         ('2015-10-19', 'bull'), ('2019-01-07', 'bull'), ('2021-08-19', 'bear'), ('2021-10-18', 'bear'),
         ('2021-10-29', 'bear'), ('2022-10-27', 'bull'), ('2022-12-01', 'bull'), ('2023-07-11', 'bull'),
         ('2023-08-08', 'bull'), ('2024-02-05', 'bull'), ('2024-02-22', 'bull'), ('2024-03-04', 'bull'),
         ('2024-03-21', 'bull'), ('2024-04-16', 'neutral'), ('2024-05-07', 'bull'), ('2024-06-24', 'bull'),
         ('2024-10-08', 'bull')]
if HOLD:
    TESTS = [(d, 'bull') for d in ['2024-02-07','2024-02-19','2024-02-21','2024-02-26','2024-03-01','2024-03-05','2024-03-18',
             '2024-03-19','2024-03-22','2024-04-08','2024-04-12','2024-04-29','2024-05-06','2024-05-08','2024-05-13',
             '2024-06-13','2024-10-16']]
cases_txt = open(os.path.join(SK, 'references', 'cases.md'), encoding='utf-8').read()
blocks = {}
for b in re.split(r'\n(?=## )', cases_txt):
    m = re.search(r'- id:\s*(\S+)', b)
    if m:
        b = re.sub(r'\n- (出处|交叉引用):[^\n]*', '', b)  # cross refs point to later cases
        blocks[m.group(1)] = b.strip()
brief = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brief.md'), encoding='utf-8').read()
analog = os.path.join(SK, 'scripts', 'analog.py')
manifest = []
for i, (d, truth) in enumerate(TESTS):
    args = [sys.executable, analog, '--asof', d, '--exclude-after', '--top', '4']
    txt = subprocess.run(args + ['--blind'], capture_output=True, text=True, encoding='utf-8').stdout
    js = json.loads(subprocess.run(args + ['--json'], capture_output=True, text=True, encoding='utf-8').stdout)
    ids = [c['id'] for c in js['nearest_cases'][:3]]
    case_text = '\n\n'.join(blocks[x] for x in ids if x in blocks) or '（今天之前没有足够早的书中案例）'
    a = js['asof']
    prompt = (f"## 今日读数与历史相似时刻\n```\n{txt.strip()}\n```\n\n"
              f"## 匹配到的历史案例全文（均早于今天至少一年）\n{case_text}\n\n"
              "## 问题\n李老师，今天盘前怎么看？\n\n"
              "## 输出格式\n先用他的口吻写不超过 250 字的盘前评论。最后单独一行输出 JSON，不要加代码块："
              '{"direction":"bull|bear|neutral","stage":"勇气|坚持|淡泊","confidence":0到1之间的小数}')
    tid = f"{'H' if HOLD else 'T'}{i+1:02d}"
    open(os.path.join(OUT, f'{tid}.prompt.md'), 'w', encoding='utf-8').write(prompt)
    manifest.append({'tid': tid, 'asof': d, 'truth': truth, 'cases': ids,
                     'pe_q': a.get('pe_q'), 's50_q': a.get('s50_q'), 'hot60': a.get('hot60'), 'dd60': a.get('dd60'), 'pb_q': a.get('pb_q'), 'r12': a.get('r12'), 'dd3': a.get('dd3')})
open(os.path.join(OUT, 'system.md'), 'w', encoding='utf-8').write(brief)
json.dump(manifest, open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)
print(len(manifest), 'packages')
for m in manifest:
    print(m['tid'], m['asof'], m['truth'], m['cases'])
