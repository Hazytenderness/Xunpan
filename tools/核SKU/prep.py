"""prep.py <块名> <序,序,...>：给子代理整理一块款的核页输入 + 下载亚马逊图和 1688 主图。"""
import os, json, sys, urllib.request, ast
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
S = Path(os.environ['XUNPAN_WORK']); B = Path(os.environ['XUNPAN_BATCH'])
name, ids = sys.argv[1], [int(i) for i in sys.argv[2].split(',')]
P = {x['序']: x for x in json.load(open(S / 'products.json'))}
q = json.load(open(B / 'queue.json'))
out = S / 'chunks' / name; (out / 'img').mkdir(parents=True, exist_ok=True)
lst = lambda v: ast.literal_eval(v) if isinstance(v, str) and v.startswith('[') else (v or [])
jobs, rows = [], []
for 序 in ids:
    x = P[序]; ms = x.get('市场快照') or {}
    item = {'序': 序, 'asin': x['asin'], '亚马逊标题': x['名'], '类目': x.get('类'), **({'站': 'au', '澳元价': ms.get('澳元价'), 'FBA澳元': ms.get('FBA澳元')} if x.get('站') == 'au' else {'日元价': ms.get('日元价'), 'FBA日元': ms.get('FBA日元')}),
            '亚马逊图': f'img/amazon_{序}.jpg', '候选': []}
    if x.get('图'): jobs.append((x['图'], out / 'img' / f'amazon_{序}.jpg'))
    for e in q:
        if not any(k['序'] == 序 for k in e['对应款']): continue
        o = e['商品'][0]['offerId']; f = B / 'pages' / f'{o}.json'
        c = {'条目': e['id'], 'offerId': o, '链接': e['商品'][0]['商品链接']}
        if not f.exists():
            c['核页'] = '未抓到'; item['候选'].append(c); continue
        d = json.loads(f.read_text())
        if d.get('noContext') or not d.get('标题'):
            c['核页'] = '页面无商品数据（可能下架/打不开）'; c['页面开头'] = (d.get('textHead') or '')[:120]; item['候选'].append(c); continue
        mains = lst(d.get('主图'))
        for i, u in enumerate(mains[:2]):
            jobs.append((u, out / 'img' / f'1688_{o}_main{i+1}.jpg'))
        c.update({'状态': d.get('状态'), '标题': d.get('标题'), '1688类目': d.get('类目'), '卖家': d.get('卖家公司'),
                  '规格属性': d.get('规格属性'),
                  '规格价格': [dict(i=i, **s) for i, s in enumerate(d.get('规格价格') or [])],
                  '阶梯价': d.get('阶梯价_登录后'), '起订量': d.get('起订量'), '单位': d.get('单位'),
                  '商品属性': d.get('商品属性'), '包装信息': d.get('包装信息'),
                  '主图': [f'img/1688_{o}_main{i+1}.jpg' for i in range(min(2, len(mains)))],
                  '规格图网址': lst(d.get('规格图'))[:40]})
        item['候选'].append(c)
    rows.append(item)
def get(j):
    u, f = j
    if f.exists(): return
    try:
        f.write_bytes(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read())
    except Exception as ex: print('图下载失败', f.name, ex)
with ThreadPoolExecutor(8) as ex: list(ex.map(get, jobs))
from PIL import Image, ImageDraw
H = 300
for r in rows:
    tiles = [('AMAZON', out / 'img' / f"amazon_{r['序']}.jpg")] + [(c['条目'], out / 'img' / f"1688_{c['offerId']}_main1.jpg") for c in r['候选']]
    ims = []
    for label, f in tiles:
        try:
            im = Image.open(f).convert('RGB'); im = im.resize((max(1, int(im.width * H / im.height)), H))
        except Exception:
            im = Image.new('RGB', (H, H), 'white')
        c = Image.new('RGB', (min(im.width, 400), H + 24), 'white'); c.paste(im.crop((0, 0, min(im.width, 400), H)), (0, 24))
        ImageDraw.Draw(c).text((6, 4), label, fill='red'); ims.append(c)
    sheet = Image.new('RGB', (sum(i.width for i in ims) + 8 * len(ims), H + 24), 'white'); x = 0
    for i in ims: sheet.paste(i, (x, 0)); x += i.width + 8
    sheet.save(out / 'img' / f"sheet_{r['序']}.jpg", quality=80)
    r['对照图'] = f"img/sheet_{r['序']}.jpg"
(out / 'input.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1))
print(name, '款', len(rows), '候选', sum(len(r['候选']) for r in rows), '图', len(jobs))
