"""对照图：把条目对应的亚马逊图、1688 主图和规格图下载到 ~/.cache/xunpan/img/<id>/，打印路径，供逐张看图判同款。
用法：python3 tools/cmp.py <旺旺|id> [--site 站点目录] [--main 3]
亚马逊图取站点 DECK 的「图」字段（相对路径读本地 build/，网址直接下）；1688 图取 pages/<offerId>.json。"""
import argparse, ast, json, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import CACHE, find

ap = argparse.ArgumentParser()
ap.add_argument('key')
ap.add_argument('--site', default=str(Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site'))
ap.add_argument('--main', type=int, default=3)
a = ap.parse_args()
B, x = find(a.key)
out = CACHE / 'img' / x['id']
out.mkdir(parents=True, exist_ok=True)
js = 'const fs=require("fs"),c={};c.window=c;require("vm").runInNewContext(fs.readFileSync(process.argv[1],"utf8"),c);' \
     'process.stdout.write(JSON.stringify(Object.fromEntries(c.DECK.map(d=>[d.序,d.图||""]))))'
pics = json.loads(subprocess.run(['node', '-e', js, f'{a.site}/build/js/products.js'], capture_output=True, text=True).stdout)


def get(src, name):
    f = out / name
    try:
        if src.startswith('/'):
            f.write_bytes((Path(a.site) / 'build' / src.lstrip('/')).read_bytes())
        else:
            req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
            f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        print(f)
    except Exception as e:
        print(f'下载失败 {name}: {e}')


def lst(v):
    return ast.literal_eval(v) if isinstance(v, str) and v.startswith('[') else (v or [])


for k in x.get('对应款', []):
    if pics.get(str(k['序'])):
        get(pics[str(k['序'])], f"amazon_{k['序']}.jpg")
for p in x['商品']:
    f = B / 'pages' / f"{p['offerId']}.json"
    if not f.exists():
        print(f"没有核页数据 {p['offerId']}，先跑 hepage.py")
        continue
    d = json.loads(f.read_text())
    for i, u in enumerate(lst(d.get('主图'))[:a.main]):
        get(u, f"1688_{p['offerId']}_main{i + 1}.jpg")
    for i, (spec, u) in enumerate(lst(d.get('规格图'))):
        get(u, f"1688_{p['offerId']}_spec{i + 1}_{str(spec)[:20].replace('/', '_')}.jpg")
