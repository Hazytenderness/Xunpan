"""由现有台账生成下一步和集中决策清单，不改采购决定或远程数据。"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from inquiry_workflow import VERSION, next_step, response_step, routine_clarification
from resilience import atomic_json


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def snapshot(root, cache, now):
    items=[];decisions=defaultdict(list);resume=[]
    legacy={}
    for day in sorted(cache.glob('buziliao_day_*.json')):
        for note in json.loads(day.read_text(encoding='utf-8')).get('要你定',[]):
            m=re.match(r'要你定：([A-Z]+\d+)：(.+)',note)
            if m:legacy[m[1]]=m[2]
    policy=cache/'current_policy.json'
    permitted={x['序'] for x in json.loads(policy.read_text(encoding='utf-8')).get('可询盘',[])} if policy.exists() else None
    for batch in sorted((root/'batches').iterdir()):
        if not (batch/'queue.json').exists():continue
        quotes={q['id']:q for q in lines(batch/'quotes.jsonl')}
        sent=defaultdict(list)
        for message in lines(batch/'sent_log.jsonl'):
            if message.get('结果')=='成功':sent[message['id']].append(message)
        for entry in json.loads((batch/'queue.json').read_text(encoding='utf-8')):
            if entry.get('人工暂缓'):continue
            if entry.get('站','jp')!='jp':continue
            state=entry.get('状态')
            if state in ('不用发','款不对','下架','已合并'):continue
            ident=entry['id'];history=sent[ident]
            if not history and state not in ('待发R1','待人工核实','待补主图'):continue
            chat=batch/'chats'/f"{entry['商品'][0]['offerId']}.json"
            messages=json.loads(chat.read_text(encoding='utf-8')).get('消息',[]) if chat.exists() else []
            flow=response_step(entry,quotes.get(ident,{}),history,messages)
            receipt_pause='未核实发送意图' in entry.get('回复暂停',{}).get('原因','')
            if (entry.get('回复暂停') or state=='待人工核实') and not receipt_pause:flow.update(阶段='待核实',话术='',原因='有发送风险或既有人工待核实断点')
            if state=='待补主图':flow.update(阶段='待补主图',话术='',原因='移交核页补目标主图')
            if state=='待发R1':flow.update(阶段='待发送')
            current=entry.get('待决策')
            historical=legacy.get(ident) if entry.get('询盘流程',{}).get('版本')!=VERSION and flow['阶段'] not in ('资料收集完成','不匹配结束') and (permitted is None or any(k.get('序') in permitted for k in entry.get('对应款',[]))) else None
            if current or historical:
                text=current or historical;category=next((k for k,words in [('包装选择',('包装','袋装','盒装')),('规格选择',('规格','尺寸','颜色','材质','克重')),('定制与起订',('定制','起订','数量')),('样品与采购',('样品','下单','付款')),('税运口径',('含税','含运')),('联系方式',('联系','微信','电话'))] if any(word in text for word in words)),'其他决策')
                decisions[category].append({'批次':batch.name,'id':ident,'问题':text,'状态':'当前待决策' if current else '历史待确认，待按新规则复核'})
                if current and not routine_clarification(current):flow.update(阶段='待你决策',话术='',原因=text)
            age=None
            if history:
                try:age=round((now-datetime.fromisoformat(history[-1]['时间'])).total_seconds()/3600,1)
                except (ValueError,TypeError):pass
            next_action={'确认同款':'等回复/核实目标款','确认定制起订量':'核对目标定制起订数量与单位','询问类似现货':'起订量超过50，询问类似现货','补包装':'补单品包装尺寸重量','补贴标等资料':'补包装方式、中性包装、贴标、每箱数','补图片视频':'补实拍图、视频','待补主图':'核页补图','待你决策':'集中决策','不匹配结束':'结束本供应商，回供应商匹配','资料收集完成':'资料已齐，交业务判断','待核实':'核对原文或发送回执','待发送':'按发送计划处理'}.get(flow['阶段'],'核对')
            if age is not None and age>=72 and flow['话术']:
                next_action='超72小时：检查催回/关闭本供应商，回匹配补候选'
            item={'批次':batch.name,'id':ident,'供应商':entry.get('旺旺名'),'产品':[k.get('asin') for k in entry.get('对应款',[])],**flow,'距上次发送小时':age,'下一步':next_action}
            items.append(item)
            # 只续接尚未问过的新资料阶段。沉默商家不每10分钟重发。
            asked=any(m.get('文本')==flow['话术'] for m in history)
            chat=batch/'chats'/f"{entry['商品'][0]['offerId']}.json"
            old_evidence=False
            if history and chat.exists() and entry.get('询盘流程',{}).get('版本')!=VERSION:
                old_evidence=any(m.get('发送方')=='对方' for m in json.loads(chat.read_text(encoding='utf-8')).get('消息',[]))
            if history and chat.exists() and flow['阶段'] not in ('待你决策','待核实','待补主图','不匹配结束','资料收集完成') and (receipt_pause or old_evidence or flow['阶段']=='待核发送时间' or flow['话术'] and not asked):resume.append(ident)
    result={'版本':VERSION,'时间':now.isoformat(),'统计':dict(Counter(x['阶段'] for x in items)),'超72小时':sum((x['距上次发送小时'] or 0)>=72 and x['阶段'] not in ('资料收集完成','不匹配结束') for x in items),'条目':items,'可续接':resume}
    atomic_json(cache/'workflow_backlog.json',result)
    atomic_json(cache/'workflow_decisions.json',{'时间':now.isoformat(),'分类':dict(decisions)})
    return result
