"""Windows任务计划程序入口：保留逐次日志，异常通过飞书提醒。"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
from base import ROOT,CACHE,now_bj
from port import notify,permissions,HIDDEN
from resilience import atomic_json


def report_health(cache,mode,status,reason,send):
    target=Path(cache)/f'health_{mode}.json'
    old=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    if status=='busy':return
    healthy=status=='ok'
    count=0 if healthy else old.get('count',0)+1
    alerted=old.get('alerted',False)
    message=''
    if healthy and alerted:message=f'Windows询盘{mode}已恢复正常，继续按计划运行。';alerted=False
    elif not healthy and not alerted and (status=='failed' or count>=3):
        message=f'⚠ Windows询盘{mode}'+('需要处理：' if status=='failed' else '暂时未恢复，已保留断点并自动继续检查：')+reason
        alerted=True
    if message:
        try:send(message)
        except Exception:
            print('通知未送达，运行状态已保留',flush=True)
            alerted=old.get('alerted',False)
    atomic_json(target,{'status':status,'count':count,'alerted':alerted,'reason':reason,'time':now_bj().isoformat()})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['send','read']);ap.add_argument('--verify',action='store_true');ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    logs=CACHE/'logs';logs.mkdir(exist_ok=True)
    stamp=now_bj().strftime('%Y%m%d_%H%M%S_%f');out=logs/f'{stamp}_{a.mode}.log';err=logs/f'{stamp}_{a.mode}.err'
    command=[sys.executable,'-X','utf8',str(ROOT/'tools/补资料/每日.py'),a.mode,'9,10,11,12,13,14,15,16,17' if a.mode=='send' else '9,10,11,12,13,14,15,16,17,18']
    if a.resume:
        if a.mode!='send':raise ValueError('--resume只用于询盘断点恢复')
    if a.mode=='send':command.append('--resume')
    if not a.verify:command.append('--execute')
    env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
    env['PATH']=str(Path.home()/'AppData/Roaming/npm')+os.pathsep+r'C:\Program Files\nodejs'+os.pathsep+r'C:\Program Files\Git\cmd'+os.pathsep+env.get('PATH','')
    with out.open('w',encoding='utf-8') as stdout,err.open('w',encoding='utf-8') as stderr:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,creationflags=HIDDEN)
    state=CACHE/f'runtime_{a.mode}.json'
    runtime=json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}
    status='failed' if result.returncode else runtime.get('status','ok')
    if result.returncode==75:status='deferred'
    why=runtime.get('reason','程序异常，请检查本机日志' if status=='failed' else '')
    if result.returncode:
        lines=err.read_text(encoding='utf-8').splitlines()
        known=[x for x in lines if x.startswith(('RuntimeError:','ValueError:','SystemExit:','TimeoutError:','XUNPAN_RETRY_LATER:'))]
        if known:why=known[-1][:160]
    if not a.verify and permissions().get('notify') is True:report_health(CACHE,a.mode,status,why,notify)
    return result.returncode

if __name__=='__main__':sys.exit(main())
