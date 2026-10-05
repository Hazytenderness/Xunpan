"""复核条目的 AI 预判：给每条加上 原值 和 建议{动作, 理由}。

动作：自动采纳（事实类、影响小且可信）/ 建议采纳 / 建议驳回 / 需判断。
条目可带以下私有键（以 _ 开头，输出前删除）：
  _置信度  规格匹配置信度 高/中/低
  _说明    规格匹配说明
  _首批    首批数量，起订量超过它要人判断
  _页面价  同一供应商核页价，用来对比商家报价
"""
import json
import re
import subprocess
from pathlib import Path

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site'
MARGIN_FLOOR = 0.15
SMALL_SWING = 0.03
FACTS = {'页面卖家', '在售状态', '现货', '箱规', '中性包装', '交期', '打样', '开票', '定制'}


def pts(v):
    return f'{v * 100:.1f}%' if v is not None else '—'


def evaluate(items, site):
    payload = json.dumps([{k: v for k, v in i.items() if not k.startswith('_')} for i in items], ensure_ascii=False)
    res = subprocess.run(['node', str(Path(__file__).with_name('site_eval.mjs')), str(site)], input=payload,
                         capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def judge(item, ev):
    field, conf, note = item['字段'], item.get('_置信度'), item.get('_说明') or ''
    before, after = ev.get('前利润率'), ev.get('后利润率')
    if field in FACTS:
        return '自动采纳', '商家原话' if item.get('来源') == '询盘回复' else '页面事实'
    if field == '起订量':
        first = item.get('_首批') or 500
        if item['新值'] <= first:
            return '自动采纳', f"起订 {item['新值']} ≤ 首批 {first}"
        return '需判断', f"起订 {item['新值']} 超过首批 {first} 件"
    if field == '单品包装':
        old, new = ev.get('原计费重'), ev.get('新计费重')
        if conf == '低':
            return '需判断', '规格未确认，包装可能不是同款'
        if old and new and not (0.4 <= new / old <= 2.5):
            return '建议驳回', f'计费重 {new:.2f} kg，与对标包裹 {old:.2f} kg 差距过大'
        return '自动采纳', f"计费重 {new:.2f} kg" if new else '页面包装信息'
    if field == '采购单价':
        page = item.get('_页面价')
        if page and abs(item['新值'] - page) / page > 0.2:
            return '需判断', f"报价 ¥{item['新值']} 与页面价 ¥{page} 相差 {abs(item['新值'] - page) / page * 100:.0f}%"
        if conf == '低':
            parts = [c.strip() for c in re.split('[；，;,]', note) if c.strip()]
            parts = [re.sub(r'（[^）]*）', '', c) for c in parts]
            first = next((c for c in parts if any(w in c for w in ('看不出', '确认', '是否', '需', '不是', '没有'))), parts[0] if parts else '')[:30]
            return '需判断', '规格未确认' + (f"：{first}" if first else '')
        if after is not None and after < MARGIN_FLOOR:
            return '需判断', f"采纳后利润率 {pts(after)}，低于 {pts(MARGIN_FLOOR)}"
        if before is None or after is None or abs(after - before) <= SMALL_SWING:
            return '自动采纳', f"利润率 {pts(before)} → {pts(after)}"
        old = ev.get('原值')
        why = f"利润率 {pts(before)} → {pts(after)}"
        if old and item['新值'] > old * 1.5:
            why = f"参考价 ¥{old} 对应的不是同款规格，核实价折算后{why}"
        return '建议采纳', why
    return '需判断', ''


def triage(items, site=SITE):
    evs = evaluate(items, site)
    out = []
    for item, ev in zip(items, evs):
        action, reason = judge(item, ev)
        clean = {k: v for k, v in item.items() if not k.startswith('_')}
        if ev.get('找到') and ev.get('原值') is not None:
            clean['原值'] = ev['原值']
        clean['建议'] = {'动作': action, '理由': reason}
        out.append(clean)
    return out
