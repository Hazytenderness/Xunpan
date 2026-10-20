"""网站待办证据与人工意见桥接；原询盘执行机仍是唯一实际发送方。"""
import hashlib
import json
import mimetypes
import re
import subprocess
from pathlib import Path
from port import HIDDEN,require,file_lock
from resilience import atomic_json,fingerprint,RetryLater

BASE='https://ataous.com'


def task_id(entry,product):
    return 'jp-'+entry['id']+'-'+str(product['序'])+'-'+str(entry['商品'][0]['offerId'])


def task_url(entry,product):return BASE+'/inquiry/?task='+task_id(entry,product)


def api_request(method,path,data=None,file=None):
    require('review_push')
    if not re.fullmatch(r'/api/jp/inquiry(?:[-/A-Za-z0-9_?=]*)',path):raise ValueError('询盘接口路径无效')
    token=(Path.home()/'.config/xunpan/ataous_review_token').read_text(encoding='utf-8').strip()
    if '\n' in token or '\r' in token:raise ValueError('询盘凭据格式无效')
    mime=mimetypes.guess_type(str(file))[0] if file else 'application/json'
    if file:
        with Path(file).open('rb') as image:signature=image.read(12)
        if signature.startswith(b'\xff\xd8'):mime='image/jpeg'
        elif signature.startswith(b'\x89PNG'):mime='image/png'
        elif signature.startswith(b'GIF8'):mime='image/gif'
        elif signature.startswith(b'RIFF') and signature[8:12]==b'WEBP':mime='image/webp'
    config='header = '+json.dumps('Authorization: Bearer '+token)+'\nheader = '+json.dumps('Content-Type: '+str(mime))+'\n'
    if file:config+='data-binary = '+json.dumps('@'+str(Path(file).resolve()),ensure_ascii=False)+'\n'
    elif data is not None:config+='data-binary = '+json.dumps(json.dumps(data,ensure_ascii=False),ensure_ascii=False)+'\n'
    try:result=subprocess.run(['curl.exe' if __import__('os').name=='nt' else 'curl','--config','-','--request',method,'--silent','--show-error','--connect-timeout','10','--max-time','35','--write-out','\n%{http_code}',BASE+path],input=config,capture_output=True,text=True,encoding='utf-8',timeout=45,creationflags=HIDDEN)
    except (OSError,subprocess.TimeoutExpired) as error:raise RetryLater('询盘待办连接暂不可用') from error
    if result.returncode:raise RetryLater('询盘待办连接暂不可用（curl '+str(result.returncode)+'）')
    body,_,status=result.stdout.rpartition('\n')
    if not status.isdigit():raise RetryLater('询盘待办响应不完整')
    try:parsed=json.loads(body)
    except ValueError:raise RetryLater('询盘待办未返回有效回执')
    if int(status)!=200:raise RetryLater('询盘待办HTTP '+status+'：'+str(parsed.get('错','请求失败')))
    return parsed


def upload_image(cache,path):
    path=Path(path);ident=hashlib.sha256(path.read_bytes()).hexdigest();ledger=Path(cache)/'inquiry_media_uploaded.json'
    with file_lock(Path(cache)/'inquiry_media.lock',timeout=30):
        known=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
        if ident not in known:
            result=api_request('POST','/api/jp/inquiry-media',file=path)
            if result.get('sha256')!=ident:raise RuntimeError('网站图片哈希不一致')
            known[ident]=result['path'];atomic_json(ledger,known)
        return known[ident]


def identities(root):
    for q in sorted((Path(root)/'batches').glob('*/queue.json')):
        for row in json.loads(q.read_text(encoding='utf-8')):yield q.parent,row


def build_tasks(root,cache,only=None):
    tasks=[]
    catalog_file=Path(cache)/'inquiry_product_catalog.json'
    catalog=json.loads(catalog_file.read_text(encoding='utf-8')) if catalog_file.exists() else {}
    cloud_file=Path(cache)/'inquiry_cloud_state.json'
    cloud={t['id']:t for t in json.loads(cloud_file.read_text(encoding='utf-8')).get('tasks',[])} if cloud_file.exists() else {}
    for batch,e in identities(root):
        previous=cloud.get(e.get('人工处理意见',{}).get('taskId'),{})
        paused=e.get('回复暂停') or {}
        question=e.get('待决策') or ('发送结果待核实：'+str(paused.get('原因','请核对实际聊天及发送回执'))[:200]+'。已保留防重复保护，请勿直接重发。' if paused else previous.get('question'))
        if e.get('站','jp')!='jp' or not question or (only is not None and e['id'] not in only):continue
        offer=str(e['商品'][0]['offerId']);chat=batch/'chats'/f'{offer}.json'
        if not chat.exists():continue
        raw=json.loads(chat.read_text(encoding='utf-8'));messages=[]
        for m in raw.get('消息',[]):
            pictures=[]
            for name in m.get('文件',[]):
                f=(batch/name).resolve()
                if f.is_relative_to((batch/'media').resolve()) and f.is_file() and f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp'):pictures.append(upload_image(cache,f))
            if not pictures:pictures=[u for u in m.get('图片',[]) if isinstance(u,str) and u.startswith('https://')]
            videos=[u for u in m.get('视频',[]) if isinstance(u,str) and u.startswith('https://')]
            messages.append({'time':m.get('时间',''),'sender':m.get('发送方','系统'),'text':str(m.get('内容',''))[:8000],'images':pictures,'videos':videos})
        for p in e['对应款']:
            source=fingerprint({'inquiry':e['id'],'cw':p['序'],'asin':p['asin'],'offer':offer,'question':question})
            tasks.append({'id':task_id(e,p),'inquiryId':e['id'],'product':{'cw':'CW'+str(p['序']),'asin':p['asin'],'name':p.get('规格',p.get('日文名',''))[:55],'spec':p.get('规格','')},'supplier':{'name':e.get('页面卖家') or e.get('旺旺名') or '待核','ww':e.get('旺旺名',''),'offerId':offer,'url':e['商品'][0]['商品链接']},'question':question,'messages':messages,'sourceFingerprint':source})
            image=catalog.get(str(p['序']),{})
            if image.get('asin')==p['asin'] and image.get('image'):tasks[-1]['product']['image']=image['image']
    return tasks


def publish_tasks(root,cache,only=None):
    retry_file=Path(cache)/'inquiry_publish_pending.json'
    retry=set(json.loads(retry_file.read_text(encoding='utf-8'))) if retry_file.exists() else set()
    if only is not None:only=set(only)|retry;atomic_json(retry_file,sorted(only))
    tasks=build_tasks(root,cache,only);path=Path(cache)/'inquiry_tasks_published.json'
    ledger=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {};changed=[(t,fingerprint(t)) for t in tasks if ledger.get(t['id'])!=fingerprint(t)]
    for start in range(0,len(changed),5):
        batch=changed[start:start+5];response=api_request('POST','/api/jp/inquiry/import',{'tasks':[t for t,_ in batch]})
        if response.get('条数')!=len(batch):raise RuntimeError('询盘待办导入回执数量不符')
        for t,stamp in batch:ledger[t['id']]=stamp
        atomic_json(path,ledger)
    if only is not None:atomic_json(retry_file,[])
    return {'current_tasks':len(tasks),'published':len(changed)}


def progress(task,status,result):
    return api_request('POST','/api/jp/inquiry/'+task['id']+'/progress',{'decisionId':task['decision']['id'],'status':status,'result':result})


def consume_decisions(root,cache):
    cache=Path(cache)
    for saved in sorted((cache/'inquiry_progress_outbox').glob('*.json')):
        note=json.loads(saved.read_text(encoding='utf-8'))
        if note.get('delivery')!='pending':continue
        try:
            api_request('POST','/api/jp/inquiry/'+note['taskId']+'/progress',{k:note[k] for k in ('decisionId','status','result')});note['delivery']='done'
        except RetryLater as error:
            if 'HTTP 409' not in str(error):raise
            note['delivery']='superseded'
        atomic_json(saved,note)
    cloud=api_request('GET','/api/jp/inquiry');atomic_json(cache/'inquiry_cloud_state.json',cloud)
    tasks=[t for t in cloud.get('tasks',[]) if t.get('status','answered') in ('answered','queued','working','waiting_send')]
    ledger=cache/'inquiry_decisions_applied.json';applied=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {};count=0
    # 只在落盘时持队列锁，不阻塞日常询盘等待网络。
    entries={e['id']:(b,e) for b,e in identities(root)}
    for task in tasks:
        d=task.get('decision') or {};ident=d.get('id')
        if not ident or task['inquiryId'] not in entries:continue
        batch,e=entries[task['inquiryId']]
        if not any('CW'+str(p['序'])==task['product']['cw'] and p['asin']==task['product']['asin'] for p in e['对应款']) or str(e['商品'][0]['offerId'])!=task['supplier']['offerId']:continue
        if d.get('sourceFingerprint') and d['sourceFingerprint']!=task.get('sourceFingerprint'):
            if applied.get(ident)!='stale':progress(task,'needs_human','商家问题或产品要求已更新，请重新核对后提交意见');applied[ident]='stale';atomic_json(ledger,applied)
            continue
        if e.get('人工处理意见',{}).get('id')!=ident:
            opinion={**d,'taskId':task['id'],'state':'queued'}
            with file_lock(cache/'queue_write.lock',timeout=30):
                fresh=json.loads((batch/'queue.json').read_text(encoding='utf-8'))
                for row in fresh:
                    if row['id']==e['id']:
                        if str(row['商品'][0]['offerId'])!=task['supplier']['offerId'] or not any('CW'+str(p['序'])==task['product']['cw'] and p['asin']==task['product']['asin'] for p in row['对应款']):raise RetryLater('本地产品身份已更新，意见暂不应用')
                        row['人工处理意见']=opinion;row.pop('待决策',None)
                        if d['action']=='hold':row['人工暂缓']=True
                        else:row.pop('人工暂缓',None)
                atomic_json(batch/'queue.json',fresh)
            e['人工处理意见']=opinion
        with file_lock(cache/'pending_replies.lock',timeout=30):
            pending_file=cache/'pending_replies.json';pending=json.loads(pending_file.read_text(encoding='utf-8')) if pending_file.exists() else {}
            pending.setdefault(e['id'],'人工处理|'+e['id']+'|'+e.get('旺旺名','')+'|已收到网站处理意见');atomic_json(pending_file,pending)
        if ident not in applied:
            progress(task,'queued','执行机已读取意见并保存断点，将按原询盘时段和安全门槛处理');applied[ident]='queued';atomic_json(ledger,applied);count+=1
    return {'received':count}


def manual_is_current(entry):
    opinion=entry.get('人工处理意见')
    if not opinion:return True
    task=api_request('GET','/api/jp/inquiry/'+opinion['taskId'])['task']
    return task.get('decision',{}).get('id')==opinion['id'] and task.get('sourceFingerprint')==opinion.get('sourceFingerprint')


def report_outcome(root,cache,key,status,result):
    pair=next(((b,e) for b,e in identities(root) if e['id']==key),None)
    if not pair:return
    batch,e=pair;d=e.get('人工处理意见')
    if not d or d.get('state') not in ('queued','working','waiting_send'):return
    receipt=Path(cache)/'inquiry_progress_outbox'/(d['id']+'.json')
    note={'taskId':d['taskId'],'decisionId':d['id'],'status':status,'result':result,'delivery':'pending'}
    atomic_json(receipt,note)
    with file_lock(Path(cache)/'queue_write.lock',timeout=30):
        q=json.loads((batch/'queue.json').read_text(encoding='utf-8'))
        for row in q:
            if row['id']==key and row.get('人工处理意见',{}).get('id')==d['id']:row['人工处理意见'].update(state=status,result=result)
        atomic_json(batch/'queue.json',q)
    try:
        progress({'id':d['taskId'],'decision':d},status,result);note['delivery']='done';atomic_json(receipt,note)
    except RetryLater:print('网站处理结果暂待同步，本地执行回执已保存，不重复向商家发送',flush=True)
