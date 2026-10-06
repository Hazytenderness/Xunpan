"""把一个批次的核页结果和询盘报价整理成 ATAO 运营台「询盘复核」可导入的文件。

用法：
  python3 tools/build_review_feed.py batches/2026-10-05-洗衣
输出：<批次目录>/review_feed.json

只保留属于该款货源候选的店（候选从 ataous 站点 products.js 读取，也可用 --candidates 指定 JSON）。
数据来源：
  pages/<offerId>.json      核页抓到的卖家、在售、起订量
  核页规格匹配.json          每组「条目×款×商品」对应的页面规格、价格和包装
  quotes.jsonl（可选）       询盘回复抽出的报价，每个字段 {值, 原话, 时间}
"""
import argparse
import sys
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('batch')
ap.add_argument('--candidates', help='缺省时直接读 ataous 站点的 products.js')
ap.add_argument('--site', default=str(Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site'), help='ataous 站点目录，用它的公式做 AI 预判')
args = ap.parse_args()

B = Path(args.batch)
queue = json.loads((B / 'queue.json').read_text())
if args.candidates:
    raw = json.loads(Path(args.candidates).read_text())
else:
    import subprocess
    site = Path(args.site) / 'build/js/products.js'
    js = "globalThis.window=globalThis;require(process.argv[1]);const fs=require('fs'),src=process.argv[1].replace(/products\\.js$/,'products-sources.js');if(fs.existsSync(src))require(src);const o={};for(const x of DECK){const c=x.货源候选||(globalThis.DECK_SOURCES||{})[x.序];if(c)o[x.序]=c.map(c=>({候选ID:String(c.候选ID)}));}process.stdout.write(JSON.stringify(o))"
    raw = json.loads(subprocess.run(['node', '-e', js, str(site)], check=True, capture_output=True, text=True).stdout)
candidates = {int(k): {c['候选ID'] for c in v} for k, v in raw.items()}
match = {(m['id'], m['序'], m['offerId']): m for m in json.loads((B / '核页规格匹配.json').read_text())}
quotes = {}
if (B / 'quotes.jsonl').exists():
    for line in (B / 'quotes.jsonl').read_text().splitlines():
        if line.strip():
            q = json.loads(line)
            quotes[q['id']] = q

batch_name = B.name
items = []


def pieces(spec):
    m = re.search(r'(\d+)\s*个装', spec)
    return int(m.group(1)) if m else 1


seen = set()
page_price = {}


def add(序, offer, seller, field, value, basis, link, when, source, **extra):
    key = json.dumps([序, offer, field, value], ensure_ascii=False, sort_keys=True)
    if key in seen:
        return
    seen.add(key)
    items.append({'序': 序, '候选ID': offer, '供应商': seller, '字段': field, '新值': value,
                  '依据': basis, '证据': link, '来源': source, '采集时间': when,
                  **{'_' + k: v for k, v in extra.items() if v is not None}})


for x in queue:
    for k in x['对应款']:
        序 = k['序']
        for p in x['商品']:
            offer = p['offerId']
            if offer not in candidates.get(序, set()):
                continue
            f = B / 'pages' / f'{offer}.json'
            if not f.exists():
                continue
            page = json.loads(f.read_text())
            seller = page.get('卖家公司') or x.get('页面卖家') or ''
            when = page.get('核页时间') or ''
            link = p['商品链接']
            if seller:
                add(序, offer, seller, '页面卖家', seller, f"1688 商品页卖家：{seller}，旺旺：{page.get('旺旺名') or '未显示'}", link, when, '1688 核页')
            if page.get('状态') == 'PUBLISHED':
                add(序, offer, seller, '在售状态', '在售', f"商品页在售，标题「{page.get('标题', '')[:40]}」", link, when, '1688 核页')
            elif page.get('状态'):
                add(序, offer, seller, '在售状态', '已下架', f"商品页状态 {page['状态']}，不在售", link, when, '1688 核页')
            elif page.get('noContext'):
                add(序, offer, seller or x.get('供应商_站点记录') or '', '在售状态', '已下架', '商品页显示已下架' if '已下架' in (page.get('textHead') or '') else '商品页打不开，跳转到 1688 搜索页', link, when, '1688 核页')
            m = match.get((x['id'], 序, offer))
            if page.get('起订量') and not (m and m.get('结论') == '款不对'):
                add(序, offer, seller, '起订量', int(page['起订量']), f"页面起批量 {page['起订量']} {page.get('单位') or '件'}", link, when, '1688 核页', 首批=k.get('数量'))
            if not m or m.get('sku_index') is None or not m.get('price'):
                continue
            need, have = pieces(k['规格']), int(m.get('unit_count') or 1)
            price = round(m['price'] * need / have, 2)
            basis = f"页面规格「{m['sku']}」{m['price']:.2f} 元"
            if need != have:
                basis += f"，页面{'单个售卖' if have == 1 else f'{have} 个一份'}，按 {need} 个装折算 {price:.2f} 元"
            if m.get('note'):
                basis += f"。{m['note']}"
            add(序, offer, seller, '采购单价', price, basis, link, when, '1688 核页', 置信度=m.get('confidence'), 说明=m.get('note'))
            page_price[(序, offer)] = price
            if m.get('pack') and need == have:
                pk = m['pack']
                add(序, offer, seller, '单品包装', pk, f"页面包装信息：规格「{m['sku']}」{pk['长']}×{pk['宽']}×{pk['高']} cm，{pk['重量克']} g", link, when, '1688 核页', 置信度=m.get('confidence'))
    q = quotes.get(x['id'])
    if not q:
        continue
    offer = x['商品'][0]['offerId']
    seller = x.get('页面卖家') or ''
    link = x['商品'][0]['商品链接']
    for 序 in [k['序'] for k in x['对应款'] if offer in candidates.get(k['序'], set())]:
        def said(field):
            v = q.get(field)
            return v if isinstance(v, dict) and v.get('值') not in (None, '') else None
        ladder = said('阶梯价')
        if ladder and isinstance(ladder['值'], dict):
            price = ladder['值'].get('500') or next((v for v in ladder['值'].values() if v), None)
            if price:
                add(序, offer, seller, '采购单价', price, ladder['原话'], link, ladder.get('时间', ''), '询盘回复', 页面价=page_price.get((序, offer)))
        for field, target in [('起订量', '起订量'), ('现货', '现货'), ('箱规', '箱规'), ('中性包装', '中性包装'),
                              ('交期', '交期'), ('打样', '打样'), ('开票点数', '开票'), ('定制', '定制')]:
            v = said(field)
            if v:
                value = v['值'] if target == '起订量' and str(v['值']).isdigit() else str(v['值'])
                add(序, offer, seller, target, int(value) if target == '起订量' else value, v['原话'], link, v.get('时间', ''), '询盘回复')
        pack = said('包装尺寸毛重')
        if pack and isinstance(pack['值'], dict):
            add(序, offer, seller, '单品包装', pack['值'], pack['原话'], link, pack.get('时间', ''), '询盘回复')

sys.path.insert(0, str(Path(__file__).parent))
from review_triage import triage
items = triage(items, Path(args.site))
feed = {'批次': batch_name, '来源': '询盘与核页', '生成时间': max((i['采集时间'] for i in items), default=''), '条目': items}
out = B / 'review_feed.json'
out.write_text(json.dumps(feed, ensure_ascii=False, indent=1))
from collections import Counter
print(out, len(items), dict(Counter(i['字段'] for i in items)), '产品', len({i['序'] for i in items}))
