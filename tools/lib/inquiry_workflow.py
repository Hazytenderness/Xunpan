"""2026-10-19 用户确认的话术与资料优先级；仅判断下一步，不发送消息。"""
import re
from datetime import datetime, timezone

VERSION = '2026-10-20-executor-1'

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
    result = {'版本': VERSION, '贴标': label if label in ('能贴', '不能贴') else '未确认'}

    def step(stage, text='', reason=''):
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
    unit,_ = sales_unit(entry)
    question = flow['话术']
    if flow['阶段']=='确认同款':
        question=f'图上这款有吗？有的话请补{unit}包装长宽高（厘米）和带包装重量（克）。'
    if re.search(r'稍等|等一下|晚点|明天|量好.*发|正在.*量', text) and not re.search(r'[?？]|哪|什么', text):
        try:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(recent[-1]['时间'])).total_seconds()/3600
        except (KeyError,ValueError,TypeError):elapsed=0
        if elapsed<24:
            return {**flow, '阶段':'等商家测量', '话术':'', '原因':'商家承诺补数据，等待新回复；24小时后核查'}
        return {**flow,'话术':f'之前您说稍等，麻烦帮忙补下{unit}实际发货包装的长宽高（厘米）和带包装重量（克）；还没测的话，请仓库量尺、称重，拍读数也可以。',
                '原因':'商家承诺超过24小时，先核对最新聊天再续接一次'}
    if re.search(r'没(?:有)?测|没(?:有)?量|不知道|不清楚|没(?:有)?数据', text):
        question=f'麻烦拿{unit}现货按实际发货包装，用尺量长宽高、连包装称重量，发厘米和克数；拍尺和秤读数也可以。'
    elif re.search(r'详情|往下翻|页面.*有', text):
        question=f'麻烦把对应{unit}带包装长宽高和毛重的那张参数图发这里，需与这次规格一致；产品尺寸和整箱数据不能代替。'
    elif re.search(r'外箱|整箱|一箱|装箱', text):
        question=f'收到，这是整箱数据。还需要{unit}实际发货包装的长宽高（厘米）和带包装重量（克），麻烦量一下。'
    elif re.search(r'袋装|盒装|OPP|彩盒|纸盒', text, re.I) and re.search(r'哪|还是|选择|[?？]',text):
        question=f'先不定包装，请分别提供现成袋装、盒装对应{unit}的包装长宽高和毛重；我们核算后再确认。'
    prefix=[]
    if re.search(r'含税|开票|发票|不含税', text):prefix.append('先了解不含税、不含运费报价。')
    if re.search(r'发哪|哪里|地址|运费|发货地|含税运|含运', text):prefix.append('发义乌。')
    if re.search(r'微信|电话|加我|联系方式', text):prefix.append('先在这里聊，资料发这里即可。')
    routed=bool(prefix) or question!=flow['话术']
    return {**flow,'话术':(''.join(prefix)+question)[:120],'响应类型':'上下文澄清' if routed else '普通追问'}
