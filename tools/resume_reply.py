"""单款恢复入口：重读聊天→确定性响应→实时核对→发送→保存回执。不会启动批量或群通知。"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent/'lib'))
from base import ROOT, CACHE, find, load_queue, save_queue, now_bj
from inquiry_workflow import response_step, routine_clarification, requires_fact_analysis
from resilience import atomic_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('id')
    parser.add_argument('--dry',action='store_true')
    args=parser.parse_args()
    batch,entry=find(args.id)
    run=subprocess.run([sys.executable,str(ROOT/'tools/chat.py'),args.id],capture_output=True,text=True,encoding='utf-8')
    if run.returncode or '错误' in run.stdout or '可重试' in run.stdout:
        raise RuntimeError('最新聊天未读取成功：'+run.stdout+run.stderr)
    offer=str(entry['商品'][0]['offerId'])
    chat=json.loads((batch/'chats'/f'{offer}.json').read_text(encoding='utf-8'))
    if requires_fact_analysis(chat['消息'],entry.get('询盘流程',{}).get('版本')):
        command=[sys.executable,str(ROOT/'tools/analyze_replies.py'),args.id]+(['--dry'] if args.dry else [])
        analyzed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        report={'id':args.id,'产品':[k['序'] for k in entry['对应款']],'时间':now_bj().isoformat(),
                '读取时间':chat['读取时间'],'dry':args.dry,'入口':'最新事实转字段分析与同步','分析结果':analyzed.stdout,
                '退出码':analyzed.returncode,'错误':analyzed.stderr if analyzed.returncode else ''}
        atomic_json(CACHE/'resume_receipts'/f"{args.id}_{now_bj().strftime('%Y%m%d_%H%M%S')}.json",report)
        print(json.dumps(report,ensure_ascii=False))
        return
    def lines(path):
        return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []
    quotes=next((q for q in lines(batch/'quotes.jsonl') if q['id']==args.id),{})
    sent=[m for m in lines(batch/'sent_log.jsonl') if m['id']==args.id]
    flow=response_step(entry,quotes,sent,chat['消息'])
    report={'id':args.id,'产品':[k['序'] for k in entry['对应款']],'时间':now_bj().isoformat(),
            '读取时间':chat['读取时间'],'流程':flow,'dry':args.dry}
    if flow['话术'] and not args.dry:
        run=subprocess.run([sys.executable,str(ROOT/'tools/reply.py'),args.id,flow['话术']],capture_output=True,text=True,encoding='utf-8')
        if run.returncode:report['错误']=run.stdout+run.stderr
        else:report['回执']=json.loads(run.stdout)
    if not args.dry:
        queue=load_queue(batch)
        for row in queue:
            if row['id']==args.id:
                row['询盘流程']={k:v for k,v in flow.items() if k!='话术'}
                if routine_clarification(row.get('待决策')) and report.get('回执',{}).get('结果')=='成功':
                    row.setdefault('已处理澄清',[]).append({'原待决策':row.pop('待决策'),'时间':report['时间'],'回复':flow['话术']})
        save_queue(batch,queue)
    atomic_json(CACHE/'resume_receipts'/f"{args.id}_{now_bj().strftime('%Y%m%d_%H%M%S')}.json",report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
