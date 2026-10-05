"""每天把 ATAO 运营台「询盘复核」的处理结果导出存进本仓库，有变化才提交推送。

用法：python3 tools/export_review_result.py [--no-push]
输出：batches/<批次>/review_result.json（按复核记录里的批次分组）
密钥文件：~/.config/xunpan/ataous_review_token（不进仓库）
"""
import json
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = 'claude/claude-github-connection-mtu9fd'
token = (Path.home() / '.config/xunpan/ataous_review_token').read_text().strip()
req = urllib.request.Request('https://ataous.com/api/jp/review-feed',
                             headers={'Authorization': f'Bearer {token}', 'User-Agent': 'xunpan-review-export'})
with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read())


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, text=True).stdout


push = '--no-push' not in sys.argv
if push:
    git('pull', '-q', '--rebase', 'origin', BRANCH)

keep = ['id', '序', '候选ID', '供应商', '字段', '状态', '原值', '新值', '采纳值', '依据', '证据', '来源', '采集时间',
        '导入时间', '处理人', '处理时间']
groups = defaultdict(list)
for e in data['条目']:
    groups[e.get('批次') or '未分批'].append({k: e.get(k) for k in keep if e.get(k) is not None})

changed = []
for batch, rows in groups.items():
    folder = ROOT / 'batches' / batch
    if not folder.is_dir():
        folder = ROOT / 'batches' / '_未分批'
        folder.mkdir(parents=True, exist_ok=True)
    out = folder / 'review_result.json'
    body = {'批次': batch, '网站更新时间': data.get('更新时间'), '统计': dict(Counter(r['状态'] for r in rows)),
            '条数': len(rows), '条目': rows}
    text = json.dumps(body, ensure_ascii=False, indent=1) + '\n'
    if not out.exists() or out.read_text() != text:
        out.write_text(text)
        changed.append(str(out.relative_to(ROOT)))

today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
print(today, '复核记录', data['条数'], '条', '有变化' if changed else '无变化', changed)
if changed and push:
    git('add', *changed)
    git('commit', '-q', '-m', f'复核结果导出 {today}（北京时间）')
    git('push', '-q', 'origin', BRANCH)
    print('已提交推送')
