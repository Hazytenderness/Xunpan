"""询盘工具的公共底座：路径、浏览器调用（带锁）、节奏、时间、队列与记账。

浏览器脚本（tools/browser/*.mjs）不接收参数：调用前把任务写进 ~/.cache/xunpan/job.json，
脚本把结果写进 ~/.cache/xunpan/<脚本名>.out.json。整个调用过程持有同一把浏览器锁，
发送、读聊天、扫消息列表、核页不会同时操作浏览器。
"""
import os
import copy
import tempfile
from port import file_lock, require, permissions,HIDDEN,captured,ensure_neo
from resilience import RetryLater,UnsafeOperation,atomic_json,atomic_text,send_once,latest_send_times
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCHES = ROOT / 'batches'
BROWSER = ROOT / 'tools' / 'browser'
CACHE = Path.home() / '.cache' / 'xunpan'
CACHE.mkdir(parents=True, exist_ok=True)
LOCK = CACHE / 'browser.lock'
LAST = CACHE / 'last_send.txt'
BJ = timezone(timedelta(hours=8))

GAP_SECONDS = 60          # 任意两条消息之间的最短间隔
WORK_HOURS = (9, 18)      # 北京时间可发消息的时段
_queue_baselines = {}


def now_bj():
    return datetime.now(BJ)


def to_beijing(local_text):
    """1688 页面显示的是本机时间，换成北京时间 ISO 字符串。"""
    try:
        t = datetime.strptime(local_text.strip(), '%Y-%m-%d %H:%M:%S').astimezone()
        return t.astimezone(BJ).isoformat(timespec='seconds')
    except Exception:
        return local_text


def in_work_hours():
    h = now_bj().hour
    return WORK_HOURS[0] <= h < WORK_HOURS[1]


def batch_dirs():
    return sorted(p for p in BATCHES.iterdir() if (p / 'queue.json').exists())


def load_queue(batch):
    key=Path(batch).resolve()
    rows=json.loads((key / 'queue.json').read_text(encoding='utf-8'))
    _queue_baselines[key]=copy.deepcopy(rows)
    return rows


def save_queue(batch, q):
    key=Path(batch).resolve();target=key/'queue.json'
    with file_lock(CACHE/'queue_write.lock'):
        current=json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
        old={x['id']:x for x in _queue_baselines.get(key,[])};by={x['id']:x for x in current};missing=object()
        for wanted in q:
            ident=wanted['id']
            if ident not in old:
                if ident in by and by[ident]!=wanted:raise RuntimeError('询盘队列新增ID冲突，停止')
                if ident not in by:current.append(copy.deepcopy(wanted));by[ident]=current[-1]
                continue
            if ident not in by:raise RuntimeError('询盘条目已被其他操作移除，停止')
            for field in old[ident].keys()|wanted.keys():
                before=old[ident].get(field,missing);after=wanted.get(field,missing)
                if before==after:continue
                actual=by[ident].get(field,missing)
                if actual!=before and actual!=after:raise RuntimeError('询盘队列同字段并发冲突，停止')
                if after is missing:by[ident].pop(field,None)
                else:by[ident][field]=copy.deepcopy(after)
        temp_root=ROOT.parent/'temp';temp_root.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='\n',prefix='xunpan_queue_',suffix='.json',dir=temp_root,delete=False) as f:
            json.dump(current,f,ensure_ascii=False,indent=1);temporary=Path(f.name)
        try:os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
        _queue_baselines[key]=copy.deepcopy(current)


def entries(include_unsent=True):
    """旺旺名 → (批次目录, 队列条目)。款不对、下架、已合并的不算；只核过页没询过盘的（已核页）也不算，免得盖掉真在聊的条目。"""
    out = {}
    for b in batch_dirs():
        for x in load_queue(b):
            if x.get('旺旺名') and x['状态'] not in ('款不对', '下架', '已合并', '待核页', '已核页', '不用发'):
                if include_unsent or x['状态'] != '待发R1':
                    out[x['旺旺名']] = (b, x)
    return out


def find(key):
    """按旺旺名或条目 id 找到 (批次, 条目)。"""
    E = entries()
    if key in E:
        return E[key]
    for b in batch_dirs():
        for x in load_queue(b):
            if x['id'] == key:
                return b, x
    raise SystemExit(f'找不到：{key}')


def append_log(batch, row):
    target=Path(batch)/'sent_log.jsonl'
    with file_lock(CACHE/'sent_log.lock'):
        if target.exists() and row.get('结果')=='成功':
            for line in target.read_text(encoding='utf-8').splitlines():
                old=json.loads(line)
                if old.get('结果')=='成功' and all(old.get(k)==row.get(k) for k in ('id','轮次','文本')):return
        with target.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())


def sent_texts():
    out = set()
    for b in batch_dirs():
        f = b / 'sent_log.jsonl'
        if f.exists():
            for l in f.read_text(encoding='utf-8').splitlines():
                if l.strip():
                    out.add(json.loads(l)['文本'][:20])
    return out


def wait_gap():
    if LAST.exists():
        left = GAP_SECONDS - (time.time() - float(LAST.read_text(encoding='utf-8') or 0))
        if left > 0:
            time.sleep(left)
    next_send=CACHE/'next_send.txt'
    if next_send.exists():
        left=float(next_send.read_text(encoding='utf-8'))-time.time()
        if left>0:time.sleep(left)


def mark_sent(sent_at=None,not_before=None):
    stamp=sent_at or time.time()
    old=float(LAST.read_text(encoding='utf-8') or 0) if LAST.exists() else 0
    atomic_text(LAST,str(max(old,stamp)))
    target=CACHE/'next_send.txt'
    old_next=float(target.read_text(encoding='utf-8') or 0) if target.exists() else 0
    atomic_text(target,str(max(old_next,not_before or stamp+GAP_SECONDS)))


def browser(script, job=None, timeout=300, sending=False):
    """在浏览器锁内运行 tools/browser/<script>，返回脚本写出的 JSON；失败返回 None。"""
    out = CACHE / (Path(script).stem + '.out.json')
    if os.name == 'nt':
        if script != 'probe.mjs' and (CACHE / 'neo_paused.json').exists():
            raise SystemExit('浏览器已暂停：用户处理验证并明确说继续后才能恢复')
        if script == 'send.mjs':
            require('send')
        if script == 'chat_read.mjs':
            allowed = permissions().get('chat_read_ww', [])
            pending = json.loads((ROOT / 'tools/windows_pending_chats.json').read_text(encoding='utf-8'))
            eligible = set(entries()) if permissions().get('runtime_chats') is True else {x['ww'] for x in pending}
            if permissions().get('runtime_chats') is True:
                allowed = eligible
            if not job or job.get('ww') not in allowed or job.get('ww') not in eligible:
                raise SystemExit('聊天读取未授权：会标为已读，必须先经用户确认指定条目')
        if script == 'chat_list.mjs':
            require('scan')
    with file_lock(LOCK):
        if os.name=='nt':ensure_neo()
        if sending:
            if os.name=='nt':
                try:
                    stamp,next_time=latest_send_times(CACHE)
                    if stamp:mark_sent(stamp,next_time)
                except UnsafeOperation as error:
                    atomic_json(CACHE/'send_paused.json',{'原因':str(error),'时间':now_bj().isoformat()})
                    return {'结果':'停止:'+str(error)}
            wait_gap()
            if not in_work_hours():
                raise RetryLater('已到18点，保留待发，明天继续')
        def attempt(payload):
            if sending and not in_work_hours():return {'结果':'暂缓:已到18点','时段结束':True}
            atomic_json(CACHE/'job.json',payload)
            out.unlink(missing_ok=True)
            if os.name=='nt':command=['node',str(BROWSER/'neo_bridge.mjs'),script]
            else:
                code=f'const NAME = {json.dumps(Path(script).stem)};\n'+(BROWSER/'_prelude.txt').read_text(encoding='utf-8')+'\n'+(BROWSER/script).read_text(encoding='utf-8')
                command=['ego-browser','nodejs','-e',code]
            try:
                r=captured(command,capture_output=True,text=True,encoding='utf-8',errors='replace',
                           timeout=timeout,creationflags=HIDDEN)
                if out.exists():return json.loads(out.read_text(encoding='utf-8'))
                (CACHE/'last_error.txt').write_text(r.stdout[-3000:]+'\n'+r.stderr[-3000:],encoding='utf-8')
            except RetryLater:pass
            progress={}
            if script=='send.mjs':
                f=CACHE/'send.progress.json'
                if f.exists():progress=json.loads(f.read_text(encoding='utf-8'))
                if progress.get('operation_id')!=payload.get('operation_id'):progress={}
            safe=script!='send.mjs' or progress.get('阶段')=='准备'
            return {**progress,'错误':'浏览器连接暂不可用','结果':'停止:浏览器连接暂不可用','可重试':safe}
        if os.name=='nt' and script=='send.mjs' and sending:
            if (CACHE/'send_paused.json').exists():return {'结果':'停止:发送暂停，需核实上次异常后恢复'}
            try:result=send_once(CACHE,job or {},attempt)
            except UnsafeOperation as error:
                atomic_json(CACHE/'send_paused.json',{'原因':str(error),'时间':now_bj().isoformat(),'ww':(job or {}).get('ww')})
                mark_sent();return {'结果':'停止:'+str(error)}
            if result.get('结果')=='成功':mark_sent(result.get('sent_at'),result.get('not_before'))
            return result
        for number in range(3 if os.name=='nt' else 1):
            result=attempt(job or {})
            if result and not result.get('错误'):
                if sending:mark_sent()
                return result
            if (CACHE/'neo_paused.json').exists():return result
            if number<2:time.sleep(2*(number+1))
        reason=str((result or {}).get('错误') or '浏览器页面或连接暂不可用')[:240]
        raise RetryLater('保留任务下轮恢复：'+reason)
