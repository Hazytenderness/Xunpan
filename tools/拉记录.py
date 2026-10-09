"""从线上 R2 读 ataous 选品记录，拼成整份 {"行": {...}} 写到本地文件（只读，不改线上）。
10-09 起网站把 purchase 拆成 16 份存 <站>/宠物/purchase/00.json…15.json；00.json 不存在＝还没迁移，读旧的整份 purchase.json；都没有＝这个站还没有记录。
用法：python3 tools/拉记录.py <jp|au> <输出 purchase.json>
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

站, out = sys.argv[1], Path(sys.argv[2])
assert 站 in ('jp', 'au'), 站
env = {**os.environ, 'CLOUDFLARE_ACCOUNT_ID': 'f451a19a9c22c7472e8c23bd4ca272d5'}  # 本机 wrangler 有两个账户，不指定会报错
tmp = Path(tempfile.mkdtemp())


def get(key):
    f = tmp / key.replace('/', '_')
    r = subprocess.run(['npx', 'wrangler', 'r2', 'object', 'get', f'ataous-data/{key}', '--remote', '--file', str(f)],
                       env=env, capture_output=True, text=True)
    if r.returncode:
        if 'does not exist' in r.stdout + r.stderr:
            return None
        sys.exit(f'读 {key} 失败：' + (r.stderr or r.stdout)[-300:])
    return json.loads(f.read_text())


first = get(f'{站}/宠物/purchase/00.json')
if first is None:
    whole = get(f'{站}/宠物/purchase.json')
    rows, how = (whole or {}).get('行', {}), '旧整份' if whole else '无记录'
else:
    rows, how = dict(first.get('行', {})), '分片'
    for i in range(1, 16):
        part = get(f'{站}/宠物/purchase/{i:02d}.json')
        if part is None:
            sys.exit(f'分片 {i:02d} 缺失，停止（不拿残缺数据冒充整份）')
        rows.update(part.get('行', {}))
out.write_text(json.dumps({'行': rows}, ensure_ascii=False))
print(站, how, '记录', len(rows), '款 →', out)
