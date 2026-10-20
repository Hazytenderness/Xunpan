"""网站询盘待办交接入口；不直接向商家发送。"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'lib'))
from base import ROOT,CACHE
from inquiry_actions import publish_tasks,consume_decisions,api_request

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['publish','consume','status'])
    parser.add_argument('--ids-file',type=Path)
    args=parser.parse_args()
    if args.action=='publish':
        if not args.ids_file:parser.error('publish 必须提供已核对的 --ids-file')
        rows=json.loads(args.ids_file.read_text(encoding='utf-8'))
        result=publish_tasks(ROOT,CACHE,{r['询盘号'] if isinstance(r,dict) else r for r in rows})
    elif args.action=='consume':result=consume_decisions(ROOT,CACHE)
    else:result=api_request('GET','/api/jp/inquiry')
    print(json.dumps(result,ensure_ascii=False,indent=2))
