"""把 review_feed.json 推到 ATAO 运营台的「询盘复核」。

用法：python3 tools/push_review_feed.py batches/2026-10-05-洗衣
密钥文件：~/.config/xunpan/ataous_review_token（不进仓库）
重复推送安全：网站按「产品+供应商+字段+新值」去重。
按文件里的「站」推到 /api/jp/ 或 /api/au/（澳洲批次由 build_review_feed.py 写 站:au；没写的是日本站）。
"""
import json
import sys
import urllib.request
import os
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from port import require,HIDDEN
require('review_push')

feed = Path(sys.argv[1]) / 'review_feed.json'
token = (Path.home() / '.config/xunpan/ataous_review_token').read_text(encoding='utf-8').strip()
站 = json.loads(feed.read_text(encoding='utf-8')).get('站', 'jp')
assert 站 in ('jp', 'au'), 站
print('推送到', 站, '站')
if os.name=='nt':
    # 密钥仅通过stdin传给curl，不进入命令行、临时配置文件或日志。
    assert '\n' not in token and '\r' not in token
    config='header = '+json.dumps('Authorization: Bearer '+token)+'\n'
    response=subprocess.run(['curl.exe','--config','-','--fail','--location','--max-time','60',
        '--header','Content-Type: application/json','--user-agent','xunpan-review-sync',
        '--data-binary','@'+str(feed.resolve()),f'https://ataous.com/api/{站}/review-feed'],
        input=config,capture_output=True,text=True,encoding='utf-8',creationflags=HIDDEN)
    if response.returncode:raise RuntimeError('XUNPAN_REVIEW_SYNC_NETWORK: 网站报价同步连接失败，保留本地资料')
    print(json.dumps(json.loads(response.stdout),ensure_ascii=False))
    sys.exit(0)
req = urllib.request.Request(f'https://ataous.com/api/{站}/review-feed', data=feed.read_bytes(), method='POST',
                             headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                                      'User-Agent': 'xunpan-review-sync'})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(json.dumps(json.loads(r.read()), ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode('utf-8', 'replace'))
    sys.exit(1)
