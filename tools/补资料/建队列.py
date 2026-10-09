"""每天把 ataous 货源核实里还没核对完的款排进「补资料」批次，问供应商要单品包装尺寸和单价。
用法：python3 tools/补资料/建队列.py [--purchase 本地purchase.json] [--dry]
规则【用户定·10/8】：
  - 只问匹配度为完全匹配 / 部分匹配、没下架的家；已经给过单价又给过尺寸的家不问（那款早该进已完成）。
  - 每款同时最多 2 家在问（还没发，或发出不满 72 小时）；问满 72 小时没补齐就换下一家，同一家同一款只问一次。
  - 一家店同一时间只排一条；其他批次里已发过或待发的店不排（那边的会话接着跟）。
  - 旺旺名和中文规格从各批次核页结果里取，没核过页的家不排。
  - 款已经不在待核对（已完成、不做等）的，还没发的条目改成「不用发」。
  - 也排「重新跑」还没跑完的款；其他批次没发出去的待发R1（如 10/6 家居扩展停在滑块的 81 条）每日.sh 一起发，
    其中对应款都已不缺资料的改「不用发」【用户定·10/8】。
话术原话（用户定·10/8，只替换 {产品}）：{产品}单品包装尺寸多少（长宽高）、重量多少，500 个什么价？
"""
import argparse, json, re, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import ROOT, BATCHES, CACHE, batch_dirs, load_queue, save_queue, now_bj

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night'  # 夜间任务的网站副本，货源候选和匹配度最新
B = BATCHES / '补资料'
TEXT = '{产品}单品包装尺寸多少（长宽高）、重量多少，500 个什么价？'
PER_PRODUCT, ACTIVE_HOURS = 2, 72
ELSEWHERE = {'待发R1', '已发R1', '已回', '已发R2', '已催', '拒绝', '无货'}

ap = argparse.ArgumentParser()
ap.add_argument('--purchase')
ap.add_argument('--dry', action='store_true')
a = ap.parse_args()

purchase = Path(a.purchase) if a.purchase else CACHE / 'purchase.json'
if not a.purchase:
    # 10-09 起网站把选品记录分 16 片存，旧的整份 purchase.json 不再更新：用 拉记录.py 拼回整份
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / '拉记录.py'), 'jp', str(purchase)],
                       cwd=SITE, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode or not purchase.exists() or purchase.stat().st_size < 1000:
        sys.exit('读线上选品记录失败：' + (r.stderr or r.stdout)[-300:])
todo = json.loads(subprocess.run(['node', str(Path(__file__).parent / '待补款.mjs'), str(SITE), str(purchase)],
                                 check=True, capture_output=True, text=True).stdout)


def short(spec):
    """中文规格只留品名和第一项参数，聊天里好读：「不锈钢猫咪饮水机（2L，鹅颈…）」→「不锈钢猫咪饮水机（2L）」，
    「双面桑蚕丝枕套，22姆米，43×63cm」→「双面桑蚕丝枕套（22姆米）」"""
    parts = [s.strip() for s in re.split(r'[（()），,]', spec) if s.strip()]
    pack = re.search(r'\d+\s*[个条支只片双套枚本张卷]装', spec)  # 装数影响报价口径，必须留
    keep = [p for p in parts[1:2] if not (pack and pack.group() in p)] + ([pack.group()] if pack and pack.group() not in parts[0] else [])
    return f"{parts[0]}（{'，'.join(keep)}）" if keep else parts[0] if parts else spec.strip()


# 各批次核页结果：(序, offerId) → 旺旺名、卖家、规格；其他批次在跟的店
info, busy, others = {}, set(), {}
for b in batch_dirs():
    if b == B:
        continue
    others[b] = load_queue(b)
    for x in others[b]:
        if x.get('旺旺名') and x['状态'] in ELSEWHERE:
            busy.add(x['旺旺名'])
        if not x.get('旺旺名') or x['状态'] in ('款不对', '下架', '已合并', '待核页'):
            continue
        for p in x['商品']:
            for k in x['对应款']:
                if k.get('规格'):
                    info[(k['序'], str(p['offerId']))] = {'旺旺名': x['旺旺名'], '页面卖家': x.get('页面卖家') or '', '规格': k['规格'], '商品': p, '类目': x.get('类目') or ''}

q = load_queue(B) if (B / 'queue.json').exists() else []
sent = {}
if (B / 'sent_log.jsonl').exists():
    for line in (B / 'sent_log.jsonl').read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            sent[r['id']] = datetime.fromisoformat(r['时间'])
now = now_bj()


def active(x):
    if x['状态'] == '待发R1':
        return True
    t = sent.get(x['id'])
    return x['状态'] not in ('不用发', '拒绝', '无货') and t is not None and now - t < timedelta(hours=ACTIVE_HOURS)


want = {t['序']: t for t in todo}
dropped = 0
for x in q:
    if x['状态'] == '待发R1' and x['对应款'][0]['序'] not in want:
        x['状态'], dropped = '不用发', dropped + 1
other_drop, other_left = {}, 0
for b, oq in others.items():
    for x in oq:
        if x['状态'] != '待发R1':
            continue
        if any(k['序'] in want for k in x['对应款']):
            other_left += 1
        else:
            x['状态'], x['备注'] = '不用发', (x.get('备注') or '') + f"；{now:%m-%d} 对应款已不缺资料，补资料任务改不用发"
            other_drop[b] = other_drop.get(b, 0) + 1
asked = {(x['对应款'][0]['序'], x['商品'][0]['offerId']) for x in q}
live_ww = {x['旺旺名'] for x in q if active(x)}
n = max([int(x['id'][2:]) for x in q] or [0])
added, skipped = [], {'没有可问的家': 0, '可问的家被别处占着或没旺旺名': 0, '已在问': 0}
for t in todo:
    on = sum(1 for x in q if x['对应款'][0]['序'] == t['序'] and active(x))
    if on >= PER_PRODUCT:
        skipped['已在问'] += 1
        continue
    cands = [c for c in t['候选'] if not (c.get('有价') and c.get('有尺寸'))]
    cands.sort(key=lambda c: (not c.get('有价'), c['等级'] != '完全匹配', c['排名']))
    if not cands:
        skipped['没有可问的家'] += 1
        continue
    picked = 0
    for c in cands:
        if on + picked >= PER_PRODUCT:
            break
        meta = info.get((t['序'], c['候选ID']))
        if not meta or (t['序'], c['候选ID']) in asked or meta['旺旺名'] in live_ww or meta['旺旺名'] in busy:
            continue
        n += 1
        x = {'id': f'BZ{n:04d}', '类目': meta['类目'], '组': 'C', '商品': [meta['商品']],
             '对应款': [{'序': t['序'], 'asin': t['asin'], '日文名': t['名'], '规格': meta['规格'], '数量': 500, '候选排名': c['排名']}],
             '供应商_站点记录': c['供应商'], '页面卖家': meta['页面卖家'], '旺旺名': meta['旺旺名'],
             'r1_text': TEXT.replace('{产品}', short(meta['规格'])), 'r2_text': None, '状态': '待发R1',
             '备注': f"{t['状态']}·{c['等级']}" + ('·已有价缺尺寸' if c.get('有价') else ''), '建于': now.isoformat(timespec='seconds')}
        q.append(x); added.append(x); asked.add((t['序'], c['候选ID'])); live_ww.add(meta['旺旺名']); picked += 1
    if not picked and not on:
        skipped['可问的家被别处占着或没旺旺名'] += 1

summary = {'待核对款': len(todo), '缺资料': sum(t['状态'] == '缺资料' for t in todo), '待跑': sum(t['状态'] == '待跑' for t in todo),
           '重跑': sum(t['状态'] == '重跑' for t in todo), '其他批次待发': other_left, '其他批次改不用发': sum(other_drop.values()),
           '新排': len(added), '新排款': len({x['对应款'][0]['序'] for x in added}), '改不用发': dropped, '待发合计': sum(x['状态'] == '待发R1' for x in q), **skipped}
print(json.dumps(summary, ensure_ascii=False))
for x in added[:5]:
    print(' ', x['id'], x['旺旺名'], x['r1_text'])
if a.dry:
    sys.exit()
B.mkdir(exist_ok=True)
save_queue(B, q)
for b in other_drop:
    save_queue(b, others[b])
if not (B / '核页规格匹配.json').exists():
    (B / '核页规格匹配.json').write_text('[]')
(B / 'batch.json').write_text(json.dumps({'批次': '补资料', '来源': '每天北京 8:50 由 tools/补资料/建队列.py 从 ataous 货源核实待核对款滚动生成',
                                         '最近一次': now.isoformat(timespec='seconds'), '本次': summary}, ensure_ascii=False, indent=1))
