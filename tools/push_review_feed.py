"""把 review_feed.json 推到 ATAO 运营台的「询盘复核」。

用法：python3 tools/push_review_feed.py batches/2026-10-05-洗衣
密钥文件：~/.config/xunpan/ataous_review_token（不进仓库）
重复推送安全：网站按「产品+供应商+字段+新值」去重。
"""
import json
import sys
import urllib.request
from pathlib import Path

feed = Path(sys.argv[1]) / 'review_feed.json'
token = (Path.home() / '.config/xunpan/ataous_review_token').read_text().strip()
req = urllib.request.Request('https://ataous.com/api/jp/review-feed', data=feed.read_bytes(), method='POST',
                             headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                                      'User-Agent': 'xunpan-review-sync'})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(json.dumps(json.loads(r.read()), ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode('utf-8', 'replace'))
    sys.exit(1)
