"""用 products.json 建核页批次：一家 1688 商品一条，跳过线上已有复核记录或旧批次推过的「款×商品」，复用旧批次已核的页。
用法：XUNPAN_WORK=<工作目录> python3 tools/核SKU/建批次.py batches/<日期>-<名>"""
import json, glob, os, shutil, sys
from pathlib import Path
S = Path(os.environ['XUNPAN_WORK']); B = Path(sys.argv[1])
if (B / 'queue.json').exists():
    sys.exit('批次已存在：保留原queue/pages/match断点，直接续接；新身份请建独立新批次')
(B / 'pages').mkdir(parents=True, exist_ok=True)
P = json.load(open(S / 'products.json', encoding='utf-8'))
站 = 'au' if any(x.get('站') == 'au' for x in P) else 'jp'  # 取款.mjs 带 au 时商品带 站:'au'
# 复核/报价上传不能证明核SKU已完成；以当前同身份候选的匹配度为准。
done = {(x['序'],str(c['候选ID'])) for x in P for c in x['货源候选']
        if isinstance(c.get('匹配度'),dict) and c['匹配度'].get('等级') in ('完全匹配','部分匹配','不匹配','已下架')}
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
q = [{'id': f'H{n:04d}', '站': 站, '类目': e['对应款'][0]['细类'], '组': None, **e, 'r1_text': None, 'r2_text': None, '状态': '待核页', '备注': ''}
     for n, (o, e) in enumerate(by.items(), 1)]
(B / 'queue.json').write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding='utf-8')
reuse = 0
for f in glob.glob('batches/*/pages/*.json'):
    o = Path(f).stem
    if o in by and not (B / 'pages' / f'{o}.json').exists():
        page=json.loads(Path(f).read_text(encoding='utf-8'))
        if str(page.get('offerId'))!=o or page.get('错误') or page.get('block') or page.get('已登录') is False:
            continue
        shutil.copy(f, B / 'pages' / f'{o}.json'); reuse += 1
print('站点', 站, '商品页', len(q), '款×商品', sum(len(e['对应款']) for e in q), '款', len({k['序'] for e in q for k in e['对应款']}), '复用页', reuse)
