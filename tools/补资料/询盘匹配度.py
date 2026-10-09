"""把询盘回复里商家确认的款式（quotes.jsonl 的「匹配确认」）整理成网站 scripts/import-match.mjs 认的批次目录。
用法：python3 tools/补资料/询盘匹配度.py <输出上级目录>   → 打印生成的目录（没有确认记录时不打印）
规则【用户定·10/9】：首轮先发主图问「图上这款有吗」，说有再追问图上看不出的关键规格；确认了＝完全匹配，没有这款或关键规格不是＝不匹配。
只认值为「完全匹配」「不匹配」的记录；同一家多次确认以 quotes.jsonl 里最后写的为准。"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import batch_dirs, load_queue, now_bj

VERDICT = {'完全匹配': '同款', '不匹配': '款不对'}
out, queue = [], []
for b in batch_dirs():
    f = b / 'quotes.jsonl'
    if not f.exists():
        continue
    got = {r['id']: r['匹配确认'] for r in map(json.loads, filter(str.strip, f.read_text().splitlines()))
           if (r.get('匹配确认') or {}).get('值') in VERDICT}
    for x in load_queue(b):
        if x['id'] in got:
            c = got[x['id']]
            queue.append(x)
            out += [{'id': x['id'], '序': k['序'], 'offerId': x['商品'][0]['offerId'], '结论': VERDICT[c['值']], 'unit_count': 1,
                     'note': f"询盘确认（{str(c.get('时间', ''))[:10]}）：{c.get('原话', '')}"} for k in x['对应款']]
if out:
    d = Path(sys.argv[1]) / f'{now_bj():%Y-%m-%d}-询盘确认'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'queue.json').write_text(json.dumps(queue, ensure_ascii=False))
    (d / '核页规格匹配.json').write_text(json.dumps(out, ensure_ascii=False))
    print(d)
