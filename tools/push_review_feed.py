"""把 review_feed.json 推到 ATAO 运营台的「询盘复核」。

用法：python3 tools/push_review_feed.py batches/2026-10-05-洗衣
密钥文件：~/.config/xunpan/ataous_review_token（不进仓库）
重复推送安全：网站按「产品+供应商+字段+新值」去重。
按文件里的「站」推到 /api/jp/ 或 /api/au/（澳洲批次由 build_review_feed.py 写 站:au；没写的是日本站）。
"""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from port import require,CACHE,file_lock
from review_sync import enqueue,flush


def main():
    ap=argparse.ArgumentParser();ap.add_argument('batch',nargs='?');ap.add_argument('--pending',action='store_true')
    args=ap.parse_args();require('review_push')
    if not args.batch and not args.pending:ap.error('需提供批次或--pending')
    with file_lock(CACHE/'review_sync.lock',timeout=90):
        if args.batch:
            feed=json.loads((Path(args.batch)/'review_feed.json').read_text(encoding='utf-8'))
            if feed.get('站','jp') not in ('jp','au'):raise ValueError('站点无效')
            enqueue(CACHE,feed)
        receipt=flush(CACHE)
    print(json.dumps(receipt,ensure_ascii=False))
    return 0


if __name__=='__main__':sys.exit(main())
