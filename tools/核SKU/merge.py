"""把各块 match.json 并进批次：核页规格匹配.json、queue.json 的 对应款.规格/数量 和 状态。可重复运行。"""
import os, json, glob, re, html
from pathlib import Path
S = Path(os.environ['XUNPAN_WORK']); B = Path(os.environ['XUNPAN_BATCH'])
q = json.load(open(B / 'queue.json'))
spec, pairs, bad = {}, {}, []
for f in sorted(glob.glob(str(S / 'chunks/*/match.json'))):
    for k in json.load(open(f))['款']:
        n = int(k.get('装数') or 1); s = k['规格']
        if n > 1 and not re.search(rf'{n}\s*个装', s): s += f'（{n}个装）'
        spec[k['序']] = s
        for c in k['候选']:
            pairs[(c['条目'], k['序'], str(c['offerId']))] = c
match = []
for e in q:
    o = e['商品'][0]['offerId']; res = []
    for k in e['对应款']:
        c = pairs.get((e['id'], k['序'], o))
        if k['序'] in spec: k['规格'] = spec[k['序']]; k['数量'] = 500
        if not c:
            if k['序'] in spec: bad.append((e['id'], k['序']))
            continue
        res.append(c['结论'])
        if c.get('price') is not None and float(c['price']) < 0.3:
            c = {**c, 'confidence': '低', 'note': f"页面价 {c['price']} 元疑似引流价，需询价确认；" + (c.get('note') or '')}
        match.append({'id': e['id'], '序': k['序'], 'offerId': o, 'sku_index': c.get('sku_index'), 'sku': html.unescape(c['sku']) if c.get('sku') else c.get('sku'),
                      'price': c.get('price'), 'unit_count': c.get('unit_count') or 1, 'pack': c.get('pack'),
                      'confidence': '低' if c['结论'] == '近似' or '装数待确认' in (c.get('note') or '') else c.get('confidence'),
                      'note': ('近似款，' if c['结论'] == '近似' else '') + (c.get('note') or ''), '结论': c['结论']})
    if res:
        e['状态'] = '已核页' if any(r in ('同款', '近似') for r in res) else ('下架' if all(r in ('下架', '未抓到') for r in res) else '款不对')
        e['备注'] = '；'.join(f"{pairs[(e['id'], k['序'], o)]['结论']}：{pairs[(e['id'], k['序'], o)].get('note') or ''}" for k in e['对应款'] if (e['id'], k['序'], o) in pairs)
(B / '核页规格匹配.json').write_text(json.dumps(match, ensure_ascii=False, indent=1))
(B / 'queue.json').write_text(json.dumps(q, ensure_ascii=False, indent=1))
from collections import Counter
print('款', len(spec), '家', len(match), Counter(m['结论'] for m in match), Counter(e['状态'] for e in q), '漏', bad[:10])
