"""Windows任务计划程序入口：保留逐次日志，异常通过飞书提醒。"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
from base import ROOT,CACHE,now_bj
from port import notify,permissions

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['send','read']);ap.add_argument('--verify',action='store_true');a=ap.parse_args()
    logs=CACHE/'logs';logs.mkdir(exist_ok=True)
    stamp=now_bj().strftime('%Y%m%d_%H%M%S');out=logs/f'{stamp}_{a.mode}.log';err=logs/f'{stamp}_{a.mode}.err'
    command=[sys.executable,'-X','utf8',str(ROOT/'tools/补资料/每日.py'),a.mode,'9' if a.mode=='send' else '9,10,11,12,13,14,15,16,17,18']
    if not a.verify:command.append('--execute')
    env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
    env['PATH']=str(Path.home()/'AppData/Roaming/npm')+os.pathsep+r'C:\Program Files\nodejs'+os.pathsep+r'C:\Program Files\Git\cmd'+os.pathsep+env.get('PATH','')
    with out.open('w',encoding='utf-8') as stdout,err.open('w',encoding='utf-8') as stderr:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL)
    if result.returncode and permissions().get('notify') is True:
        warning=CACHE/f'alert_{a.mode}_{now_bj():%Y%m%d}'
        if not warning.exists():
            why='程序停止，请检查本机日志'
            event=CACHE/('send.out.json' if a.mode=='send' else 'chat_list.out.json')
            if event.exists():
                import json
                data=json.loads(event.read_text(encoding='utf-8'));why=str(data.get('结果') or data.get('错误') or why)[:100]
            notify(f'⚠ Windows询盘{a.mode}任务停止：{why}\n请查看neo或本机日志。');warning.touch()
    return result.returncode

if __name__=='__main__':sys.exit(main())
