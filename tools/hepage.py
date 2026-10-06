"""核页：只读抓批次里每个商品页，存 pages/<offerId>.json，并回填队列的「页面卖家」「旺旺名」。
用法：python3 tools/hepage.py batches/<批次> [--ids L61,L62] [--force]
已抓过的默认跳过；页面之间随机等 5–15 秒；出现验证或掉登录立刻停。"""
import argparse, json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import browser, load_queue, save_queue

ap = argparse.ArgumentParser()
ap.add_argument('batch')
ap.add_argument('--ids')
ap.add_argument('--force', action='store_true')
a = ap.parse_args()
B = Path(a.batch)
(B / 'pages').mkdir(exist_ok=True)
q = load_queue(B)
want = set(a.ids.split(',')) if a.ids else None
first = True
for x in q:
    if want and x['id'] not in want:
        continue
    for p in x['商品']:
        f = B / 'pages' / f"{p['offerId']}.json"
        if f.exists() and not a.force:
            continue
        if not first:
            time.sleep(random.uniform(5, 15))
        first = False
        r = browser('page.mjs', {'url': p['商品链接']}, timeout=180)
        if r is None or '错误' in (r or {}):
            print(json.dumps({'停止': (r or {}).get('错误', '浏览器无结果'), 'id': x['id'], 'offerId': p['offerId']}, ensure_ascii=False))
            sys.exit(3)
        r = {'offerId': p['offerId'], '条目': x['id'], **r}
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(x['id'], p['offerId'], r.get('状态') or '无数据', r.get('卖家公司'), r.get('旺旺名'), f"规格{len(r.get('规格价格') or [])}", f"起订{r.get('起订量')}", flush=True)
for x in q:
    sellers, wws = [], []
    for p in x['商品']:
        f = B / 'pages' / f"{p['offerId']}.json"
        if f.exists():
            d = json.loads(f.read_text())
            for k, lst in (('卖家公司', sellers), ('旺旺名', wws)):
                if d.get(k) and d[k] not in lst:
                    lst.append(d[k])
    if sellers:
        x['页面卖家'] = '；'.join(sellers)
    if wws:
        x['旺旺名'] = '；'.join(wws)
save_queue(B, q)
print('完成')
