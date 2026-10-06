"""列出所有候选都已核页、且还没分块的款。用法：ready.py [上限]"""
import os, json, sys, glob
from pathlib import Path
S = Path(os.environ['XUNPAN_WORK']); B = Path(os.environ['XUNPAN_BATCH'])
q = json.load(open(B / 'queue.json'))
done = set()
for f in glob.glob(str(S / 'chunks/*/input.json')):
    done |= {r['序'] for r in json.load(open(f))}
need = {}
for e in q:
    for k in e['对应款']:
        need.setdefault(k['序'], []).append(e['商品'][0]['offerId'])
ready = [s for s, os_ in need.items() if s not in done and all((B / 'pages' / f'{o}.json').exists() for o in os_)]
print(len(need), '已分块', len(done), '可分', len(ready))
print(','.join(map(str, ready[:int(sys.argv[1]) if len(sys.argv) > 1 else 9999])))
