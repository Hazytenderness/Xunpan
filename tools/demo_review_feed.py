"""生成演示用的「询盘回复」复核资料，批次名以「演示」开头，网站上会标出，可整批撤回。

用法：python3 tools/demo_review_feed.py [--site 站点目录]
撤回：POST /api/jp/review-feed  {"撤回批次": "演示·询盘回复"}
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from review_triage import triage, SITE

ap = argparse.ArgumentParser()
ap.add_argument('--site', default=str(SITE))
args = ap.parse_args()

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / 'batches/2026-10-05-洗衣'
queue = {x['id']: x for x in json.loads((B / 'queue.json').read_text())}
match = {(m['id'], m['序'], m['offerId']): m for m in json.loads((B / '核页规格匹配.json').read_text())}
BATCH = '演示·询盘回复'

replies = [
    ('L28', 2359, '2026-10-05T12:20:00+08:00', '灰色长毛洗鞋袋有现货，库存3000多个，500个3.1一个，1000个2.9，中性包装OPP袋单个装没问题，起订200个',
     {'采购单价': 3.1, '现货': '有现货，约 3000 个', '中性包装': '可以，OPP 袋单个装', '起订量': 200}),
    ('L01', 200, '2026-10-05T13:05:00+08:00', '支架款两个装我们可以配一起装，500套9.2元一套，起订300套，交期7天左右，开票加6个点',
     {'采购单价': 9.2, '起订量': 300, '交期': '约 7 天', '开票': '加 6 个点'}),
    ('L41', 244, '2026-10-05T14:40:00+08:00', '单人床笠90*200白色有现货，夹棉防水一体的，500个28块一个，起订500，交期10天',
     {'采购单价': 28, '现货': '90×200 白色有现货', '起订量': 500, '交期': '约 10 天'}),
    ('L20', 1339, '2026-10-05T15:10:00+08:00', '胡桃色宽肩44.5cm有现货，肩厚5.5cm，500个8.5元，印logo的话起订1000个',
     {'采购单价': 8.5, '现货': '胡桃色 44.5cm 有现货', '定制': '印 logo 起订 1000 个'}),
    ('L38', 214, '2026-10-05T16:25:00+08:00', '150×210我们可以做，白色全棉，需要定做，500条32一条，起订300条，打样3天，样品费50',
     {'采购单价': 32, '现货': '需定做', '起订量': 300, '打样': '3 天，样品费 50 元'}),
]


def pieces(spec):
    m = re.search(r'(\d+)\s*个装', spec)
    return int(m.group(1)) if m else 1


items = []
for qid, 序, when, said, values in replies:
    x = queue[qid]
    p = x['商品'][0]
    k = next(k for k in x['对应款'] if k['序'] == 序)
    m = match.get((qid, 序, p['offerId'])) or {}
    page = round(m['price'] * pieces(k['规格']) / int(m.get('unit_count') or 1), 2) if m.get('price') else None
    for field, value in values.items():
        item = {'序': 序, '候选ID': p['offerId'], '供应商': x.get('页面卖家') or '', '字段': field, '新值': value,
                '依据': said, '证据': p['商品链接'], '来源': '询盘回复', '采集时间': when}
        if field == '采购单价' and page:
            item['_页面价'] = page
        if field == '起订量':
            item['_首批'] = k.get('数量') or 500
        items.append(item)

items = triage(items, Path(args.site))
out = ROOT / 'demo/review_feed_demo.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'批次': BATCH, '来源': '询盘回复', '生成时间': max(i['采集时间'] for i in items), '条目': items},
                          ensure_ascii=False, indent=1))
for i in items:
    print(i['序'], i['字段'], i['新值'], '|', i['建议'])
print(out)
