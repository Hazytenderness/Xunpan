"""给一家店发一句回复。用法：python3 tools/reply.py <旺旺名或条目id> "<一行回复>" [--dry]
走 send.mjs 的全套核对；记入 sent_log.jsonl（轮次=回复）；成功后状态改为「已回」。
--dry 只核对收件人，不粘贴不发送。"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import browser, find, load_queue, save_queue, append_log, now_bj, in_work_hours

args = [x for x in sys.argv[1:] if x != '--dry']
dry = '--dry' in sys.argv
key, text = args[0], (args[1] if len(args) > 1 else '').strip()
assert dry or (text and '\n' not in text and len(text) <= 120), '回复要一行、120 字以内'
if not dry and not in_work_hours():
    raise SystemExit('不在北京 9:00–18:00，不发')
b, x = find(key)
ww = x['旺旺名']
r = browser('send.mjs', {'ww': ww, 'offerId': x['商品'][0]['offerId'], 'text': text, 'dry': dry}, sending=not dry) or {'结果': '无结果'}
if not dry:
    append_log(b, {'id': x['id'], '组': x['组'], '轮次': '回复', '旺旺名': ww, 'offerId': x['商品'][0]['offerId'],
                   '时间': now_bj().isoformat(timespec='seconds'), '文本': text, '核对': r.get('核对'),
                   '发后新增条数': r.get('发后新增条数'), '结果': r.get('结果')})
    if r.get('结果') == '成功':
        q = load_queue(b)
        for it in q:
            if it['id'] == x['id']:
                it['状态'] = '已回'
        save_queue(b, q)
print(json.dumps({'id': x['id'], '旺旺名': ww, '结果': r.get('结果'), '打开时': r.get('打开时')}, ensure_ascii=False))
