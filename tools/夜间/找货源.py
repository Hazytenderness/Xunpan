"""夜间找货源（ataous 供应商匹配工作流的机械部分，判断部分交给 AI 审图）。从 06_VibeCoding/ataous/供应商匹配/20261007_遨虾智能选商 的一次性脚本通用化。
批次目录 B 里先放 任务清单.json：[{序, asin, 父ASIN, 图, 名, 类, 排除offer:[旧的款不对/下架候选ID]}]
  找货源.py search B     遨虾智能选商主图搜，raw/<序>.json，calls.jsonl；已有的跳过，失败不重试
  找货源.py screen B     机械筛（价格>0、服务分≥3.5、同商家去重、去掉排除offer；优质全留，无资质留前 5）→ pool.json、sheets/、review/task_<k>.md
  找货源.py need-kw B    列出审图后保留不足 3 家的款（给 AI 写中文搜索词，写进 词搜词.json {序: 词}）
  找货源.py kw B         文字补搜 raw_kw/ → pool_kw.json、sheets_kw/、review_kw/task_<k>.md
  找货源.py rank B       合并审图结论 review*/batch_<k>.json → 100 分排序 → seeds.json（import-suppliers.mjs 格式）、汇总.json
审图结论格式：{"<序>": {"<offerId>": {"结论": "保留|排除", "理由": "…"}}}，规则见 ataous-site/供应商匹配工作流.md 第 3 节。
"""
import json, math, os, sys, time, datetime, urllib.request, concurrent.futures as cf
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path.home() / 'ClaudeP/04_工具/aoxia'))

QUAL = {'SUPER_FACTORY': '超级工厂', 'POWER_FACTORY': '实力商家'}
PLAIN_KEEP, TASK_SIZE = 5, 12
NEAR = ('上海', '江苏', '安徽', '江西', '福建')
cmd, B = sys.argv[1], Path(sys.argv[2])
DATE = datetime.date.today().isoformat()
L = {str(x['序']): x for x in json.loads((B / '任务清单.json').read_text())}


def jload(name, default=None):
    f = B / name
    return json.loads(f.read_text()) if f.exists() else default


def num(v):
    try:
        return float(str(v).rstrip('%'))
    except Exception:
        return None


def lab(lst, label):
    for s in lst or []:
        if s.get('label') == label:
            return s.get('originValue') if s.get('originValue') is not None else s.get('value')


def offers_of(f):
    return ((json.loads(f.read_text()).get('result') or {}).get('result') or {}).get('offerInfo', {}).get('offerList') or []


def cand(o, i, total, kw=None):
    p = o.get('providerInfo') or {}
    tags = p.get('providerTags') or []
    fwf = num(lab(o.get('providerServices'), '综合服务分'))
    return {'原排名': i + 1, '原始条数': total, 'offerId': str(o['itemId']), '标题': o.get('title'), '价格': num(o.get('itemPrice')),
            '图片': o.get('imageUrl'), '公司': p.get('companyName'), 'memberId': p.get('memberId'), '旺旺': p.get('loginId'),
            '资质标签': [t['tagName'] for t in tags if t.get('tagCode') in QUAL or t.get('tagStyle') in QUAL],
            '近一年销量': num(lab(o.get('salesInfos'), '近一年销量')), '服务分': fwf or None,
            '回头率': num(lab(o.get('providerServices'), '90天回头率')), '店铺30天订单': num(lab(o.get('providerServices'), '30天订单')),
            '发货地': lab(o.get('shipInfos'), '发货地'), '起批量': lab(o.get('purchaseInfos'), '起批量'),
            '1688类别': next((a.get('value') for a in o.get('coreAttributes') or [] if a.get('label') == '类别'), None),
            **({'搜索关键词': kw} if kw else {})}


def screen_offers(s, offers, kw=None, used_members=(), used_ids=()):
    bad = set(map(str, L[s].get('排除offer') or [])) | set(used_ids)
    seen, good, plain = set(used_members), [], []
    for i, o in enumerate(offers):
        c = cand(o, i, len(offers), kw)
        m = c['memberId'] or c['公司']
        if c['offerId'] in bad or not (c['价格'] and c['价格'] > 0) or (c['服务分'] is not None and c['服务分'] < 3.5) or m in seen:
            continue
        seen.add(m)
        (good if c['资质标签'] else plain).append(c)
    return good + plain[:PLAIN_KEEP]


def get(url, path):
    if path.exists():
        return path
    try:
        path.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20).read())
        return path
    except Exception:
        return None


def sheets(pool, folder):
    (B / folder).mkdir(exist_ok=True); (B / 'thumbs').mkdir(exist_ok=True)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', 18)
    except Exception:
        font = None

    def one(s):
        cs = pool[s]['候选']
        if not cs:
            return
        ims = [get(L[s]['图'], B / 'thumbs' / f'amz_{s}.jpg')] + [
            get(c['图片'] + '_220x220.jpg' if c['图片'] and 'alicdn' in c['图片'] else c['图片'], B / 'thumbs' / f"{c['offerId']}.jpg") for c in cs]
        W = 240; cols = min(5, len(ims)); rows = math.ceil(len(ims) / cols)
        cv = Image.new('RGB', (cols * W, rows * (W + 22)), 'white'); d = ImageDraw.Draw(cv)
        for k, p in enumerate(ims):
            r, cn = divmod(k, cols); x0, y0 = cn * W, r * (W + 22)
            try:
                im = Image.open(p).convert('RGB'); im.thumbnail((W - 10, W - 10)); cv.paste(im, (x0 + 5, y0 + 22))
            except Exception:
                d.text((x0 + 10, y0 + 100), '图片取不到', fill='red', font=font)
            d.text((x0 + 5, y0), 'AMZ' if k == 0 else f'#{k}', fill='red' if k == 0 else 'black', font=font)
        cv.save(B / folder / f'{s}.jpg', quality=80)
    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(one, list(pool)))


def tasks(pool, folder, sheet_folder):
    (B / folder).mkdir(exist_ok=True)
    items = [(s, v) for s, v in pool.items() if v['候选']]
    for k in range(math.ceil(len(items) / TASK_SIZE)):
        lines = []
        for s, v in items[k * TASK_SIZE:(k + 1) * TASK_SIZE]:
            lines.append(f"## 序 {s}\n亚马逊商品：{L[s]['名']}\n亚马逊类目：{L[s]['类']}\n对照图：{B / sheet_folder / (s + '.jpg')}（左上 AMZ=亚马逊原品，#n=下列候选）")
            lines += [f"- #{i} offerId={c['offerId']} ¥{c['价格']} 1688类别={c['1688类别']} 标题：{c['标题']}" for i, c in enumerate(v['候选'], 1)]
            lines.append('')
        (B / folder / f'task_{k + 1}.md').write_text('\n'.join(lines))
    print(folder, '款', len(items), '候选', sum(len(v['候选']) for _, v in items), '任务包', math.ceil(len(items) / TASK_SIZE))


def reviews():
    rev = {}
    for f in sorted(B.glob('review*/batch_*.json')):
        for s, d in json.loads(f.read_text()).items():
            rev.setdefault(str(s), {}).update(d)
    return rev


def kept(s, pools, rev):
    return [c for p in pools for c in (p.get(s, {}).get('候选') or []) if (rev.get(s, {}).get(c['offerId']) or {}).get('结论') == '保留']


def search(field, value, raw, logname, items):
    from aoxia_api import post
    (B / raw).mkdir(exist_ok=True)
    log = open(B / logname, 'a')
    for s, v in items:
        f = B / raw / f'{s}.json'
        if f.exists():
            continue
        t0 = datetime.datetime.now().isoformat(timespec='seconds')
        r = post('/ai.select.provider.search/1.0', {'intention': 'SEARCH_OFFER', field: v, 'language': 'zh'})
        n = len((((r.get('result') or {}).get('result') or {}).get('offerInfo') or {}).get('offerList') or [])
        log.write(json.dumps({'序': s, '输入': v, '开始': t0, '完成': datetime.datetime.now().isoformat(timespec='seconds'),
                              'resultCode': r.get('resultCode'), '条数': n, '错误': r.get('_http') and r.get('_body')}, ensure_ascii=False) + '\n'); log.flush()
        if r.get('resultCode') == 'SUCCESS':
            f.write_text(json.dumps(r, ensure_ascii=False))
        print(s, r.get('resultCode'), n, flush=True)
        if r.get('resultCode') in ('FAIL_ACCOUNT_POINT_NOT_ENOUGH', 'FAIL_ACCOUNT_ERROR'):
            sys.exit('遨虾账户：' + r.get('resultCode'))
        time.sleep(1)


if cmd == 'search':
    search('searchImageUrl', None, 'raw', 'calls.jsonl', [(s, x['图']) for s, x in L.items() if x.get('图')])
elif cmd == 'screen':
    pool = {s: {'候选': screen_offers(s, offers_of(B / 'raw' / f'{s}.json')) if (B / 'raw' / f'{s}.json').exists() else []} for s in L}
    (B / 'pool.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1))
    sheets(pool, 'sheets'); tasks(pool, 'review', 'sheets')
elif cmd == 'need-kw':
    pool, rev = jload('pool.json', {}), reviews()
    for s in L:
        if len(kept(s, [pool], rev)) < 3:
            print(json.dumps({'序': s, '名': L[s]['名'], '类': L[s]['类']}, ensure_ascii=False))
elif cmd == 'kw':
    pool, rev, words = jload('pool.json', {}), reviews(), jload('词搜词.json', {})
    search('query', None, 'raw_kw', 'calls_kw.jsonl', [(s, q) for s, q in words.items() if s in L and q])
    pk = {}
    for s, q in words.items():
        f = B / 'raw_kw' / f'{s}.json'
        if s not in L or not f.exists():
            continue
        prev = pool.get(s, {}).get('候选') or []
        mine = {c['memberId'] or c['公司'] for c in kept(s, [pool], rev)}
        pk[s] = {'候选': screen_offers(s, offers_of(f), q, mine, {c['offerId'] for c in prev})}
    (B / 'pool_kw.json').write_text(json.dumps(pk, ensure_ascii=False, indent=1))
    sheets(pk, 'sheets_kw'); tasks(pk, 'review_kw', 'sheets_kw')
elif cmd == 'rank':
    pool, pk, rev = jload('pool.json', {}), jload('pool_kw.json', {}), reviews()

    def geo(a):
        a = a or ''
        if not a: return None, '未返回'
        if '永康' in a: return 1.0, '永康'
        if '金华' in a or any(k in a for k in ('义乌', '东阳', '武义', '浦江', '兰溪', '磐安')): return 0.9, '金华范围'
        if '浙江' in a: return 0.7, '浙江其余'
        if any(k in a for k in NEAR): return 0.45, '沪苏皖赣闽'
        return 0.2, '其他地区'
    seeds, summary = {}, {}
    for s, x in L.items():
        r, ks = rev.get(s, {}), kept(s, [pool, pk], rev)
        summary[s] = {'CW': s, 'asin': x['asin'], '审图保留': len(ks), '未审': sum(1 for p in (pool, pk) for c in (p.get(s, {}).get('候选') or []) if c['offerId'] not in r)}
        if not ks:
            seeds[x['asin']] = {'图搜无结果': True, '日期': DATE}; continue
        maxs = max((c['近一年销量'] or 0) for c in ks); minp = min(c['价格'] for c in ks)
        for c in ks:
            g, gl = geo(c['发货地'])
            parts = {'销量': (30, (math.log1p(c['近一年销量']) / math.log1p(maxs) if maxs > 0 else 0) if c['近一年销量'] is not None else None),
                     '服务': (12, c['服务分'] / 5 if c['服务分'] else None), '品质': (12, None), '物流': (6, None), '地缘': (20, g),
                     '成本': (10, minp / c['价格']), '回购': (10, c['回头率'] / 100 if c['回头率'] is not None else None)}
            c['得分'] = round(sum(w * min(max(v, 0), 1) for w, v in parts.values() if v is not None), 2)
            c['资料覆盖'] = sum(w for w, v in parts.values() if v is not None); c['地缘档'] = gl
        # 优质供应商（超级工厂/实力商家）排前面，不足 3 家按得分用其他补【用户定·10/7】
        ks.sort(key=lambda c: (not c['资质标签'], -c['得分'], -c['资料覆盖'], c['价格'], c['offerId']))
        rows = []
        for i, c in enumerate(ks[:3]):
            note, kw = (r.get(c['offerId']) or {}).get('理由', ''), c.get('搜索关键词')
            rows.append({'候选ID': c['offerId'], '供应商': c['公司'] or c['标题'], '商品链接': f"https://detail.1688.com/offer/{c['offerId']}.html",
                         '商品图片': c['图片'], '商品标题': c['标题'], '参考价': c['价格'], '计价口径': '搜索计价单位', '采集日期': DATE,
                         '匹配等级': '关键词线索·待人工核验' if kw else '主图相似', '在售状态': '未核验', **({'搜索关键词': kw} if kw else {}),
                         '起订量': c['起批量'], '资质': c['资质标签'],
                         '来源证据': (f"CW{s} 中文品名「{kw}」·遨虾智能选商文字搜第1页原排名{c['原排名']}/{c['原始条数']}；" if kw else f"CW{s} 亚马逊原主图·遨虾智能选商（以品找商）第1页原排名{c['原排名']}/{c['原始条数']}；")
                         + f"商家标签{'/'.join(c['资质标签']) or '无超级工厂/实力商家'}（接口返回，{DATE}）；夜间任务审图保留，{DATE}",
                         '参考说明': '主图相似货源；搜索起价用作采购参考成本。按销量30%、服务/品质/物流30%、地缘20%、成本10%、回购10%排序（遨虾口径：销量为近一年，品质/物流未返回不计分）。',
                         '待核对': '；'.join(filter(None, ['关键词线索：由中文品名搜到，询价前先打开链接核对图片、用途、规格' if kw else '主图同类相似；品牌、尺寸、材质、功能及包装装数以所选SKU为准', note and f'审图：{note}', '近30天单品销量未返回（显示近一年销量）'])),
                         '推荐': {'排名': i + 1, '得分': c['得分'], '资料覆盖': c['资料覆盖'], '近30天销量': None, '近一年销量': c['近一年销量'], '服务评分': c['服务分'],
                                '品质评分': None, '物流评分': None, '发货地': c['发货地'], '地缘': c['地缘档'], '回购率': c['回头率'], '企业名称': c['公司'],
                                '资质': c['资质标签'], '店铺30天订单': c['店铺30天订单'], '指标日期': DATE}})
        seeds[x['asin']] = {'匹配模式': '主图搜索排名', '参考成本': rows[0]['参考价'],
                            '参考成本说明': '采用排名第一的图搜采购参考成本（1688 搜索起价，人民币）；同类相似货源，实际规格与装数按SKU选择；人工报价优先。', '货源候选': rows}
        summary[s]['入选'] = [q['候选ID'] for q in rows]
    (B / 'seeds.json').write_text(json.dumps(seeds, ensure_ascii=False, indent=1))
    (B / '汇总.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    has = sum(1 for v in seeds.values() if not v.get('图搜无结果'))
    print(json.dumps({'款': len(seeds), '找到': has, '无结果': len(seeds) - has, '候选条': sum(len(v.get('货源候选', [])) for v in seeds.values()),
                      '有未审候选的款': sum(1 for v in summary.values() if v['未审'])}, ensure_ascii=False))
else:
    sys.exit(__doc__)
