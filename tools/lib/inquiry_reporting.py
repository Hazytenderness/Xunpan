"""询盘通知去重与网站可搜索身份；不执行发送或改变询盘业务状态。"""
import hashlib
import json
import re
from pathlib import Path
from resilience import atomic_json
from port import file_lock


def identity_index(root):
    result={}
    for file in sorted((Path(root)/'batches').glob('*/queue.json')):
        for entry in json.loads(file.read_text(encoding='utf-8')):
            result[entry['id']]=entry
    return result


def humanize_line(line, index):
    match=re.search(r'\b(?:BZ|L)\d+\b',line)
    if not match or match[0] not in index:return line
    entry=index[match[0]];parts=[]
    for product in entry.get('对应款',[]):
        prefix='AU' if entry.get('站','jp')=='au' else 'CW'
        parts.append(prefix+str(product['序'])+' '+str(product.get('规格') or product.get('日文名') or '产品名称待核')[:55]+' · '+str(product.get('asin') or 'ASIN待核'))
    seller=entry.get('页面卖家') or entry.get('旺旺名') or '供应商待核'
    label=' / '.join(parts)+'（'+seller+'；询盘 '+match[0]+'）'
    readable=line[:match.start()]+label+line[match.end():]
    from base import CACHE
    from inquiry_actions import task_id,task_url
    ledger=Path(CACHE)/'inquiry_tasks_published.json'
    published=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
    links=[task_url(entry,p) for p in entry.get('对应款',[]) if entry.get('商品') and task_id(entry,p) in published]
    return readable+(' · 查看聊天并处理：'+' '.join(links) if links else '')


def notice_key(line):
    if '网站报价同步有权限或业务拒绝项' in line:return 'review-sync-blocked'
    return hashlib.sha256(line.strip().encode('utf-8')).hexdigest()


def notify_once(cache, message, sender):
    with file_lock(Path(cache)/'inquiry_notice.lock',timeout=30):
        return _notify_once(cache,message,sender)


def _notify_once(cache, message, sender):
    cache=Path(cache);target=cache/'inquiry_notice_state.json'
    state=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'delivered':{}}
    delivered=state.setdefault('delivered',{})
    lines=message.strip().splitlines()
    if not lines:return True
    # 日报每日期一份；瞬时提醒按内容去重，忽略“补资料 HH:MM”外壳。
    if lines[0].startswith('补资料日报'):
        key='daily:'+lines[0]
        if key in delivered:return True
        sender(message);delivered[key]=True;atomic_json(target,state);return True
    header=lines.pop(0) if re.fullmatch(r'补资料 \d\d:\d\d',lines[0]) else ''
    fresh=[];keys=[]
    for line in dict.fromkeys(lines):
        key=notice_key(line)
        if key in delivered:continue
        old_sync=cache/'review_sync_attention.json'
        if key=='review-sync-blocked' and old_sync.exists() and json.loads(old_sync.read_text(encoding='utf-8')):
            delivered[key]=True;continue
        fresh.append(line);keys.append(key)
    if fresh:
        sender('\n'.join(([header] if header else [])+fresh))
        delivered.update({key:True for key in keys})
    atomic_json(target,state)
    return True
