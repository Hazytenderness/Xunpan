"""网站报价同步的持久化队列。服务端按字段去重，重发仅用于幂等同步。"""
import json
import subprocess
import time
from pathlib import Path
from resilience import atomic_json, fingerprint, RetryLater
from port import HIDDEN, require


def enqueue(cache, feed):
    identity={k:v for k,v in feed.items() if k!='生成时间'}
    ident=fingerprint(identity)+'.json'
    target=Path(cache)/'review_outbox'/ident
    if not target.exists():atomic_json(target,{'status':'pending','payload':feed,'created':time.time(),'attempts':0})
    return ident


def transport(feed, station):
    require('review_push')
    token=(Path.home()/'.config/xunpan/ataous_review_token').read_text(encoding='utf-8').strip()
    if '\n' in token or '\r' in token:raise ValueError('报价同步凭据格式无效')
    # 仅stdin传入凭据，不能进入命令行或诊断输出。
    config='header = '+json.dumps('Authorization: Bearer '+token)+'\n'
    config+='header = "Content-Type: application/json"\n'
    config+='data-binary = '+json.dumps(json.dumps(feed,ensure_ascii=False),ensure_ascii=False)+'\n'
    command=['curl.exe' if __import__('os').name=='nt' else 'curl','--config','-',
             '--silent','--show-error','--connect-timeout','10','--max-time','35',
             '--user-agent','xunpan-review-sync','--write-out','\n%{http_code}',
             f'https://ataous.com/api/{station}/review-feed']
    try:
        result=subprocess.run(command,input=config,capture_output=True,text=True,encoding='utf-8',
                              timeout=40,creationflags=HIDDEN)
    except (OSError,subprocess.TimeoutExpired) as error:
        raise RetryLater('网站同步连接暂不可用') from error
    if result.returncode:raise RetryLater(f'网站同步网络暂不可用（curl {result.returncode}）')
    body,_,status=result.stdout.rpartition('\n')
    if not status.isdigit():raise RetryLater('网站同步响应不完整')
    status=int(status)
    if status in (408,425,429) or status>=500:raise RetryLater(f'网站同步HTTP {status}，稍后补同步')
    if status!=200:raise ValueError(f'网站同步HTTP {status}，需核对权限或接口')
    try:receipt=json.loads(body)
    except json.JSONDecodeError as error:raise RetryLater('网站同步回执不完整') from error
    if not isinstance(receipt,dict) or '新增' not in receipt or '未导入' not in receipt:
        raise RetryLater('网站同步缺有效业务回执')
    return receipt


def flush(cache, transport=transport, attempts=3):
    result={'新增':0,'未导入':[],'待同步':0,'需处理':[]}
    folder=Path(cache)/'review_outbox'
    queue=sorted(folder.glob('*.json'),key=lambda p:json.loads(p.read_text(encoding='utf-8')).get('created',0))
    offline=False
    for target in queue:
        if offline:break
        state=json.loads(target.read_text(encoding='utf-8'))
        if state['status']=='done':continue
        if state['status']=='blocked':
            result['待同步']+=1;result['需处理'].append(state.get('error','同步待人工处理'));continue
        for number in range(attempts):
            state['attempts']=state.get('attempts',0)+1
            try:
                station=state['payload'].get('站','jp')
                if station not in ('jp','au'):raise ValueError('同步站点无效')
                receipt=transport(state['payload'],station)
                if receipt.get('未导入'):
                    state['receipt']=receipt;result['未导入'].extend(receipt['未导入'])
                    result['新增']+=receipt.get('新增',0)
                    raise ValueError('网站报价存在未导入项，需核对候选或字段')
                state.update(status='done',receipt=receipt,finished=time.time())
                atomic_json(target,state);result['新增']+=receipt.get('新增',0)
                break
            except RetryLater as error:
                state.update(status='pending',error=str(error));atomic_json(target,state)
                if number+1<attempts:time.sleep(2*(number+1));continue
                offline=True;result['待同步']+=1
            except ValueError as error:
                state.update(status='blocked',error=str(error));atomic_json(target,state)
                result['待同步']+=1;result['需处理'].append(str(error));break
    result['待同步']=sum(json.loads(p.read_text(encoding='utf-8'))['status']!='done' for p in queue)
    result['同步待重试']=result['待同步']>0
    return result
