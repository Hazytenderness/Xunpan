"""读一家或几家店的聊天并落盘 chats/<offerId>.json，图片存 media/<offerId>/。
用法：python3 tools/chat.py <旺旺名或条目id> [...]
输出每家「我方倒数第二条之后」的对话（系统消息不显示），用来决定怎么回。"""
import json, re, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import browser, find, to_beijing, now_bj

SYSTEM = re.compile(r'商家长时间没有回复|平台已通知|欢迎光临|欢迎来到|优惠券|满\d+可用|去逛逛|评价|自动回复|库存不多|不要错过|抓紧下单|等你等得')
for key in sys.argv[1:]:
    b, x = find(key)
    ww, offer = x['旺旺名'], x['商品'][0]['offerId']
    r = browser('chat_read.mjs', {'ww': ww, 'offerId': offer}, timeout=180)
    if not r or '错误' in r:
        print(json.dumps({'id': x['id'], '旺旺名': ww, '错误': (r or {}).get('错误', '浏览器无结果')}, ensure_ascii=False)); continue
    msgs = []
    for m in r['消息']:
        who = '我方' if m['我方'] else ('系统' if m['模板'] or SYSTEM.search(m['内容'] or '') else '对方')
        kind = '图片' if m['图片'] and not (m['内容'] or '').strip('预览 ') else '卡片' if m['模板'] else '文本'
        msgs.append({'时间': to_beijing(m['时间'] or ''), '发送方': who, '类型': kind, '内容': m['内容'], '图片': m['图片'], '视频': m['视频']})
    media = b / 'media' / offer
    for m in msgs:
        files = []
        for j, u in enumerate(m['图片']):
            f = media / f"{m['时间'][:19].replace(':', '').replace('-', '')}_{j}.jpg"
            if not f.exists():
                try:
                    media.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://air.1688.com/'}), timeout=20).read())
                except Exception:
                    continue
            files.append(str(f.relative_to(b)))
        m['文件'] = files
    (b / 'chats').mkdir(exist_ok=True)
    (b / 'chats' / f'{offer}.json').write_text(json.dumps({'offerId': offer, '旺旺名': ww, '条目': x['id'], '批次': b.name,
                                                            '读取时间': now_bj().isoformat(timespec='seconds'), '消息': msgs}, ensure_ascii=False, indent=1))
    mine = [i for i, m in enumerate(msgs) if m['发送方'] == '我方']
    start = mine[-2] if len(mine) >= 2 else (mine[-1] if mine else 0)
    print(f"## {x['id']} {ww} | 询：{' / '.join(k['规格'] for k in x['对应款'])} | 我方共 {len(mine)} 条")
    for m in msgs[start:]:
        if m['发送方'] != '系统':
            print(f"   {m['时间'][11:16]} {m['发送方']} {(m['内容'] or '').replace(chr(10), ' ')[:120]} {'[图 ' + ' '.join(m['文件']) + ']' if m['文件'] else ''}")
    sys.stdout.flush()
