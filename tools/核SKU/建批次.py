"""用 products.json 建核页批次：一家 1688 商品一条，跳过线上已有复核记录或旧批次推过的「款×商品」，复用旧批次已核的页。
用法：XUNPAN_WORK=<工作目录> python3 tools/核SKU/建批次.py batches/<日期>-<名>"""
import json, glob, os, shutil, sys
from pathlib import Path
S = Path(os.environ['XUNPAN_WORK']); B = Path(sys.argv[1]); (B / 'pages').mkdir(parents=True, exist_ok=True)
P = json.load(open(S / 'products.json'))
done = set()
for f in glob.glob('batches/*/review_feed.json'):
    for i in json.load(open(f))['条目']:
        done.add((int(i['序']), str(i['候选ID'])))
for k, r in json.load(open(S / 'purchase.json'))['行'].items():
    for e in (r.get('复核') or {}).values():
        if e.get('候选ID'):
            done.add((int(k), str(e['候选ID'])))
by = {}
for x in P:
    for c in x['货源候选']:
        o = str(c['候选ID'])
        if (x['序'], o) in done:
            continue
        e = by.setdefault(o, {'商品': [{'offerId': o, '商品链接': c['商品链接'], '商品标题': c.get('商品标题'), '参考价': c.get('参考价')}],
                              '供应商_站点记录': c.get('供应商'), '对应款': []})
        e['对应款'].append({'序': x['序'], 'asin': x['asin'], '日文名': x['名'], '细类': x.get('细类'), '规格': '', '数量': None,
                          '候选排名': (c.get('推荐') or {}).get('排名')})
q = [{'id': f'H{n:04d}', '类目': e['对应款'][0]['细类'], '组': None, **e, 'r1_text': None, 'r2_text': None, '状态': '待核页', '备注': ''}
     for n, (o, e) in enumerate(by.items(), 1)]
(B / 'queue.json').write_text(json.dumps(q, ensure_ascii=False, indent=1))
reuse = 0
for f in glob.glob('batches/*/pages/*.json'):
    o = Path(f).stem
    if o in by and not (B / 'pages' / f'{o}.json').exists():
        shutil.copy(f, B / 'pages' / f'{o}.json'); reuse += 1
print('商品页', len(q), '款×商品', sum(len(e['对应款']) for e in q), '款', len({k['序'] for e in q for k in e['对应款']}), '复用页', reuse)
