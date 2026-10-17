"""运行状态与发送回执；只有无副作用的阶段允许重试。"""
import hashlib
import json
import os
import tempfile
import time
import random
from pathlib import Path


class RetryLater(RuntimeError):
    pass


class UnsafeOperation(RuntimeError):
    pass


def atomic_text(path, text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,suffix='.pending',delete=False) as handle:
            name=Path(handle.name)
            handle.write(text)
            handle.flush();os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if name:name.unlink(missing_ok=True)


def atomic_json(path,value):
    atomic_text(path,json.dumps(value,ensure_ascii=False,indent=1))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def merge_pending(cache,before,after):
    from port import file_lock
    target=Path(cache)/'pending_replies.json'
    with file_lock(Path(cache)/'pending_replies.lock'):
        current=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        for key,value in before.items():
            if key not in after and current.get(key)==value:current.pop(key,None)
        for key,value in after.items():
            if key not in current or current.get(key)==before.get(key):
                current.pop(key,None);current[key]=value
        atomic_json(target,current)
        return current


def send_once(cache, job, attempt, attempts=3):
    # 图片有无不加入键：先图后字的断点也属于同一文字询盘。
    ident=fingerprint({k:job.get(k) for k in ('ww','offerId','text')})
    target=Path(cache)/'send_ops'/f'{ident}.json'
    previous=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    image_sent=bool(previous.get('image_sent') or previous.get('receipt',{}).get('图已发'))
    def complete(result):
        stamp=result.get('sent_at') or time.time()
        result={**result,'operation_id':ident,'sent_at':stamp,
                'not_before':result.get('not_before') or stamp+(random.uniform(120,240) if job.get('kind')=='R1' else 60)}
        atomic_json(target,{'status':'success','receipt':result,'image_sent':image_sent or result.get('图已发',False),'time':time.time()})
        return result
    if previous.get('status')=='success':return {**complete(previous['receipt']),'回执恢复':True}
    if previous.get('status') in ('inflight','uncertain'):
        output=Path(cache)/'send.out.json'
        receipt=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
        checks=receipt.get('核对',{})
        if receipt.get('operation_id')==ident and receipt.get('结果')=='成功' and receipt.get('发后新增条数')==1 and all(checks.get(k) is True for k in ('收件人','内容一致','未误发')):
            return {**complete(receipt),'回执恢复':True}
        raise UnsafeOperation('存在未核实发送意图，不自动重发')
    operation={**job,'operation_id':ident}
    if image_sent:operation.pop('img',None)
    for number in range(attempts):
        atomic_json(target,{'status':'inflight','job':operation,'image_sent':image_sent,'time':time.time()})
        try:
            result=attempt(operation)
        except Exception as error:
            atomic_json(target,{'status':'uncertain','job':operation,'image_sent':image_sent,'time':time.time()})
            raise UnsafeOperation('发送连接中断，结果待核实') from error
        result={**(result or {}),'operation_id':ident}
        known_image=image_sent
        image_sent=image_sent or bool(result.get('图已发'))
        if result.get('结果')=='成功':
            return complete(result)
        if result.get('时段结束'):
            atomic_json(target,{'status':'deferred','job':operation,'receipt':result,'image_sent':image_sent,'time':time.time()})
            raise RetryLater('已到18点，保留图片与文字断点，明日继续')
        if result.get('同步待确认') and result.get('阶段')=='准备' and not result.get('图已发') and not result.get('已点击发送'):
            atomic_json(target,{'status':'deferred','job':operation,'receipt':result,'image_sent':image_sent,'time':time.time()})
            raise RetryLater(str(result.get('错误') or '网站同步待确认，保留草稿和待发，下轮恢复'))
        if str(result.get('结果','')).startswith('跳过:'):
            atomic_json(target,{'status':'skipped','receipt':result,'time':time.time()})
            return result
        if result.get('可重试') is True and (not result.get('图已发') or known_image) and not result.get('已点击发送'):
            atomic_json(target,{'status':'deferred','job':operation,'receipt':result,'image_sent':image_sent,'time':time.time()})
            if number+1<attempts:time.sleep(2*(number+1));continue
            raise RetryLater('发送准备暂不可用，保留待发，下轮恢复')
        atomic_json(target,{'status':'uncertain','job':operation,'receipt':result,'image_sent':image_sent,'time':time.time()})
        raise UnsafeOperation(result.get('结果') or '发送结果不确定，待核实')
    raise RetryLater('发送准备暂不可用')


def latest_send_times(cache):
    sent=next_time=0
    for target in (Path(cache)/'send_ops').glob('*.json'):
        state=json.loads(target.read_text(encoding='utf-8'))
        if state.get('status') in ('inflight','uncertain'):
            receipt=send_once(cache,state['job'],lambda _:(_ for _ in ()).throw(UnsafeOperation('不允许重发未核实操作')))
        elif state.get('status')=='success':receipt=state['receipt']
        else:continue
        sent=max(sent,receipt.get('sent_at',0));next_time=max(next_time,receipt.get('not_before',0))
    return sent,next_time
