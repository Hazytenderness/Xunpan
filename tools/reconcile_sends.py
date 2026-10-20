"""只读聊天恢复本机未知发送回执，绝不发送或删除原始意图。"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'lib'))
from base import CACHE, browser, now_bj, batch_dirs, load_queue, save_queue, append_log, BJ
from datetime import datetime
from resilience import pending_sends, send_once, UnsafeOperation, RetryLater, atomic_json, global_send_pause, restore_queue_entry
from port import file_lock


def reconcile(limit=5):
    rows=[]
    with file_lock(CACHE/'reconcile.lock',blocking=False):
        global_send_pause(CACHE)
        index_path=CACHE/'receipt_reconciliation_index.json'
        index=json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
        pending=list(pending_sends(CACHE))
        for path in (CACHE/'send_ops').glob('*.json'):
            state=json.loads(path.read_text(encoding='utf-8'))
            if state.get('status')=='success' and state.get('previous',{}).get('status') in ('inflight','uncertain') and not state.get('queue_reconciled'):
                pending.append((path,state))
        pending.sort(key=lambda pair:index.get(pair[0].stem,0))
        for path,state in pending[:limit]:
            if (CACHE/'neo_paused.json').exists():break
            try:
                result=send_once(CACHE,state['job'],
                    lambda _:(_ for _ in ()).throw(UnsafeOperation('恢复入口不允许发送')),
                    recover=lambda probe:browser('send.mjs',probe,sending=False))
                job=state['job']
                for batch in batch_dirs():
                    queue=load_queue(batch);changed=False
                    for entry in queue:
                        if restore_queue_entry(entry,job,result,path.stem):
                            changed=True
                            append_log(batch,{'id':entry['id'],'组':entry.get('组'),'轮次':'R1' if job.get('kind')=='R1' else '回复',
                                '旺旺名':job['ww'],'offerId':job['offerId'],'时间':datetime.fromtimestamp(result['sent_at'],BJ).isoformat(),
                                '文本':job['text'],'结果':'成功','回执恢复':True,'operation_id':path.stem,'核对':result['核对']})
                    if changed:save_queue(batch,queue)
                completed=json.loads(path.read_text(encoding='utf-8'))
                completed['queue_reconciled']=time.time()
                atomic_json(path,completed)
                rows.append({'operation':path.stem,'ww':state['job'].get('ww'),'结果':result})
            except (UnsafeOperation,RetryLater) as error:
                rows.append({'operation':path.stem,'ww':state['job'].get('ww'),'仍待核实':str(error)})
            index[path.stem]=time.time()
            atomic_json(index_path,index)
    report={'时间':now_bj().isoformat(),'仅回读':True,'条目':rows}
    atomic_json(CACHE/'receipt_reconciliation.json',report)
    return report


if __name__=='__main__':
    print(json.dumps(reconcile(),ensure_ascii=False))
