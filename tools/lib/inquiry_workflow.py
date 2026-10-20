"""2026-10-19 用户确认的话术与资料优先级；仅判断下一步，不发送消息。"""
import re
from datetime import datetime, timezone, timedelta

VERSION = '2026-10-20-unified-copy-1'

def routine_clarification(text):
    return bool(re.search(r'税运|含税|运费|开票|联系方式|包装选择|选择包装|没测量|允许澄清',text or '')) and not re.search(r'付款|下单|接受替代|定制承诺',text or '')

def requires_fact_analysis(history):
    """单款快恢复只处理纯澄清；数字、图片、确认/否认同款等都回到字段分析器。"""
    boundary=max((i for i,m in enumerate(history) if m.get('发送方')=='我方'),default=-1)
    for m in history[boundary+1:]:
        if m.get('发送方')!='对方':continue
        text=m.get('内容','')
        if m.get('图片') or m.get('视频') or m.get('文件') or re.search(r'\d',text):return True
        if re.fullmatch(r'[\s你好您好亲！!，,。.?？]*',text):continue
        if not re.fullmatch(r'[\s你好您好亲！!，,。.?？]*(?:稍等(?:一下)?|您稍等(?:一下)?|等一下|没(?:有)?测量过|没(?:有)?量过|含税运吗|含税运价格|您需要配送到哪里呢)[\s。.?？!！]*',text):
            return True
    return False

def value(quotes, field):
    return (quotes.get(field) or {}).get('值')


def sales_unit(entry):
    spec = entry['对应款'][0].get('规格', '')
    match = re.search(r'(\d+)\s*(个|条|支|片|件|枚|本|双|只|张|根|颗|块)\s*(?:装|套|一[套盒包组袋])', spec)
    if match and int(match[1]) > 1:
        return f'{match[1]}{match[2]}装的一套', '套'
    return '单个', '个'


def clarification_messages(entry):
    unit,_=sales_unit(entry)
    spec=entry['对应款'][0].get('规格','')
    return ['发义乌。','先按500件了解，麻烦报下价。',f'我们要的是{spec}。',
            f'哪款和图上这个一样？我们要的是{spec}。',
            '这个是产品本身的数据，还是带包装的？我们要带包装的。',
            f'这个是单个的，还是{unit}的？','尺寸是厘米吗？重量是克还是千克？',
            f'这个价是单个的，还是{unit}的？','我们先在这里聊，资料发这里就行。']


def allowed_reply(entry, text):
    clean=lambda x:re.sub(r'[。！？?！\s]+$','',x.strip())
    return next((t for t in clarification_messages(entry) if clean(t)==clean(text)),None)


def first_message(entry):
    spec = entry['对应款'][0].get('规格', '').strip().rstrip('。')
    if not spec:
        raise ValueError('缺目标关键规格，不能编写询盘')
    unit, _ = sales_unit(entry)
    return f'图上这款有吗？我们要的是{spec}。{unit}包装尺寸多少？重量多少？订500件多少钱'


def next_step(entry, quotes, sent=()):
    unit, count = sales_unit(entry)
    label = value(quotes, '贴标')
    result = {'版本': VERSION, '贴标': label if label in ('能贴', '不能贴') else '未确认', '包装已完成': False}

    def step(stage, text='', reason=''):
        # 同一缺项最多提问两次；不把供应商“不能贴标”作为自动不做理由。
        asks = [x.get('文本', '') for x in sent if x.get('结果', '成功') == '成功']
        repeated = sum(text == t for t in asks) if text else 0
        if stage == '确认同款':
            repeated = sum('图上这款有吗？' in t for t in asks)
        if stage=='补包装':
            counts=[]
            if '尺寸' in text:counts.append(sum(bool(re.search(r'包装.*(?:尺寸|长宽高|多大)',t)) for t in asks))
            if '重量' in text:counts.append(sum('包装' in t and bool(re.search(r'重量|多重',t)) for t in asks))
            repeated=max(counts,default=0)
        if stage=='补贴标等资料':
            counts=[sum(word in t for t in asks) for word in ('中性包装','贴标','一箱') if word in text]
            repeated=max(counts,default=0)
        if stage=='补图片视频报价':
            counts=[sum(word in t for t in asks) for word in ('实拍图','视频','多少钱') if word in text]
            repeated=max(counts,default=0)
        if text and repeated >= 2:
            stage, text, reason = '待核实', '', '同一问题已问两次，未得到明确答复'
        return {**result, '阶段': stage, '话术': text, '原因': reason}

    match = value(quotes, '匹配确认')
    if match == '不匹配' or value(quotes, '现货') == '无货':
        return step('不匹配结束', reason='供应商明确没有目标款或无货')
    if match != '完全匹配':
        return step('确认同款', '图上这款有吗？')
    pack = value(quotes, '包装尺寸毛重') or {}
    basis = (quotes.get('包装尺寸毛重') or {}).get('原话', '')
    dimensions = isinstance(pack, dict) and all(isinstance(pack.get(k), (int, float)) and pack[k] > 0 for k in ('长', '宽', '高'))
    weight = isinstance(pack, dict) and isinstance(pack.get('重量克'), (int, float)) and pack['重量克'] > 0
    if re.search(r'非包装|不是包装|裸(?:产品|重|尺寸)|未(?:明确|确认).*包装', basis):
        dimensions = weight = False
    if not dimensions or not weight:
        text = f'{unit}包装尺寸多少？重量多少？' if not dimensions and not weight else f'{unit}包装尺寸多少？' if not dimensions else f'{unit}带包装重量多少？'
        return step('补包装', text)
    result['包装已完成'] = True
    second = []
    if value(quotes, '中性包装') in (None, ''):
        second.append('这款能发中性包装吗？')
    if label not in ('能贴', '不能贴'):
        second.append('能帮忙贴标吗？')
    box = value(quotes, '每箱数量')
    if box in (None, ''):
        second.append(f'一箱装多少{count}？')
    if second:
        return step('补贴标等资料', ''.join(second))
    photos, video, price = (value(quotes, k) for k in ('实拍图', '视频', '阶梯价'))
    third = []
    if photos in (None, '') and video in (None, ''):
        third.append('这款实拍图和视频发下，')
    elif photos in (None, ''):
        third.append('这款实拍图发下，')
    elif video in (None, ''):
        third.append('这款视频发下，')
    if price in (None, ''):
        third.append('订500件多少钱？')
    if third:
        return step('补图片视频报价', ''.join(third).rstrip('，') + ('。' if third[-1].endswith('，') else ''))
    return step('资料收集完成')


def response_step(entry, quotes, sent, history):
    """根据最后一次我方消息之后的整段商家回复续接；卡片不遮蔽前面的反问。"""
    flow = next_step(entry, quotes, sent)
    if flow['阶段'] in ('资料收集完成', '不匹配结束'):
        return flow
    boundary = max((i for i,m in enumerate(history) if m.get('发送方')=='我方'), default=-1)
    recent = [m for m in history[boundary+1:] if m.get('发送方')=='对方']
    if boundary>=0 and not recent:
        return {**flow,'阶段':'等商家回复','话术':'','原因':'最新消息仍是我方，先等回复；超24小时核查，不每小时重复追问'}
    text = '\n'.join(m.get('内容','') for m in recent)
    no_data=bool(re.search(r'没(?:有)?测|没(?:有)?量|不知道|不清楚|没(?:有)?(?:具体)?数据',text))
    previous=history[boundary] if boundary>=0 else {}
    requested=bool(re.search(r'量尺|尺.*量|称重|秤.*读数',previous.get('内容',''))) and '包装' in previous.get('内容','')
    if no_data and requested and not re.search(r'[?？]|吗|呢|哪|什么|还是|是否|要不要|需不需要',text):
        try:
            asked_at=datetime.fromisoformat(previous['时间'])
            if asked_at.tzinfo is None:raise ValueError('发送时间无时区')
            due=asked_at+timedelta(hours=24)
        except (KeyError,TypeError,ValueError):
            due=None
            for message in reversed(sent):
                if message.get('结果')!='成功' or message.get('文本')!=previous.get('内容'):continue
                try:
                    stamp=datetime.fromisoformat(message['时间'])
                    if stamp.tzinfo is not None:due=stamp+timedelta(hours=24);break
                except (KeyError,TypeError,ValueError):continue
        if due is None:
            return {**flow,'阶段':'待核发送时间','话术':'','原因':'测量已问但聊天时间缺失；先从发送日志或原始聊天核回执时间，不重复发送',
                    '下次核查时间':datetime.now(timezone.utc).isoformat()}
        if datetime.now(timezone.utc)<due:
            return {**flow,'阶段':'等商家测量','话术':'','原因':'已明确请求包装量尺称重，商家仍无数据；避免短时间换词重复追问',
                    '下次核查时间':due.isoformat() if due else None}
    if re.search(r'稍等|等一下|晚点|明天|量好.*发|正在.*量', text) and not re.search(r'[?？]|哪|什么', text):
        try:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(recent[-1]['时间'])).total_seconds()/3600
        except (KeyError,ValueError,TypeError):elapsed=0
        if elapsed<24:
            return {**flow,'阶段':'等商家测量','话术':'','原因':'商家承诺补数据，等待新回复；24小时后核查'}
    if re.search(r'发哪|哪里|地址|发货地|含税运|含运',text):
        return {**flow,'话术':'发义乌。','响应类型':'上下文澄清'}
    if re.search(r'微信|电话|加我|联系方式',text):
        return {**flow,'话术':'我们先在这里聊，资料发这里就行。','响应类型':'上下文澄清'}
    return flow
