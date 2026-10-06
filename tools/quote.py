"""把商家给的信息合并进 quotes.jsonl（每个字段 {值, 原话, 时间}）。
用法：python3 tools/quote.py <条目id> '{"阶梯价": [{"单价": 4.5}, "4.5元一个", "2026-10-06T14:43:00+08:00"]}'
字段名见 schema/queue.schema.md；价格要折算成我们的销售单位（如 2 个装），原话里写清折算。"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import find

qid, add = sys.argv[1], json.loads(sys.argv[2])
b, _ = find(qid)
f = b / 'quotes.jsonl'
rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
row = next((r for r in rows if r['id'] == qid), None)
if not row:
    row = {'id': qid, '状态': '已回'}
    rows.append(row)
for k, (v, said, t) in add.items():
    row[k] = {'值': v, '原话': said, '时间': t}
f.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
print(b.name, qid, list(add))
