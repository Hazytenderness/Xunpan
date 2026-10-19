"""相同原文和实际附图只分析一次；供应商的新回复会自然产生新缓存键。"""
import hashlib
import json
from pathlib import Path
from resilience import atomic_json,fingerprint


def valid_item(item):
    if not isinstance(item,dict) or not isinstance(item.get('quotes'),list):return False
    if not isinstance(item.get('reply'),str) or '\n' in item['reply'] or len(item['reply'])>120:return False
    if not isinstance(item.get('needs_user'),str):return False
    fields=[]
    for q in item['quotes']:
        if not isinstance(q,dict) or not isinstance(q.get('field'),str):return False
        if not all(k in q for k in ('value_json','source_indexes','image_files','image_quote','conversion')):return False
        fields.append(q['field'])
    return len(set(fields))==len(fields)


def analyze_cached(cache, records, images, compute):
    photos=[{'name':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in images]
    paths={r['id']:Path(cache)/'analysis_results'/(fingerprint({'version':2,'record':r,'photos':photos})+'.json') for r in records}
    items={};missing=[]
    for r in records:
        p=paths[r['id']]
        stored=None
        if p.exists():
            try:stored=json.loads(p.read_text(encoding='utf-8'))
            except json.JSONDecodeError:pass
        if stored and valid_item(stored):items[r['id']]=stored
        else:missing.append(r)
    if missing:
        fresh=compute(missing)
        if not isinstance(fresh,dict) or not isinstance(fresh.get('items'),list):raise ValueError('AI结果缺items')
        if {x['id'] for x in fresh['items']}!={r['id'] for r in missing} or len(fresh['items'])!=len(missing):
            raise ValueError('Codex结果ID不完整或重复，保留待处理列表')
        if not all(valid_item(item) for item in fresh['items']):raise ValueError('AI输出结构或追问无效，不缓存，下轮重试')
        for item in fresh['items']:
            atomic_json(paths[item['id']],item);items[item['id']]=item
    return {'items':[items[r['id']] for r in records]}
