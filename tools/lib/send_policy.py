"""所有受支持发送入口共用的最终话术校验；不操作浏览器。"""
import json
import sys
from pathlib import Path
from inquiry_workflow import first_message, allowed_reply, response_step


def validate_job(root, job):
    if job.get('dry'):
        return None
    matches=[]
    for queue in (Path(root)/'batches').glob('*/queue.json'):
        for entry in json.loads(queue.read_text(encoding='utf-8')):
            if job.get('inquiryId') and entry.get('id')!=job['inquiryId']:
                continue
            if entry.get('旺旺名')==job.get('ww') and any(str(p.get('offerId'))==str(job.get('offerId')) for p in entry.get('商品',[])):
                matches.append((queue.parent,entry))
    if job.get('recover_only') is True:
        # 恢复只读聊天回执，发送方+offer 已足以定位对话；恢复写回另按序号和暂停原因筛选。
        if not matches:
            raise ValueError('回执核对对象无法定位，保持待核实')
        return job.get('inquiryId') or matches[0][1]['id']
    if len(matches)!=1:
        raise ValueError('发送对象未唯一对应询盘队列，禁止临时绕过')
    batch,entry=matches[0]
    text=job.get('text','')
    if job.get('kind')=='R1':
        approved=first_message(entry)
    else:
        quotes={}; sent=[]
        quote_file=batch/'quotes.jsonl'; log=batch/'sent_log.jsonl'
        if quote_file.exists():
            quotes=next((x for line in quote_file.read_text(encoding='utf-8').splitlines() if line.strip() and (x:=json.loads(line)).get('id')==entry['id']),{})
        if log.exists():
            sent=[x for line in log.read_text(encoding='utf-8').splitlines() if line.strip() and (x:=json.loads(line)).get('id')==entry['id']]
        chat_file=batch/'chats'/f"{job['offerId']}.json"
        history=json.loads(chat_file.read_text(encoding='utf-8')).get('消息',[]) if chat_file.exists() else []
        approved=allowed_reply(entry,text) or response_step(entry,quotes,sent,history)['话术']
    if not approved or text!=approved:
        raise ValueError('发送内容不符合用户确认话术，已阻止发送')
    return entry['id']


if __name__=='__main__':
    try:
        validate_job(Path(__file__).resolve().parents[2],json.load(sys.stdin))
    except (ValueError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(2)
