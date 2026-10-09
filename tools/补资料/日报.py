"""补资料群消息【用户定·10/9：群里只放「要你定 / 停了」和每天一条日报，要短、有重点】
  日报.py asked           打印今天已推过的「要你定」（给读回复 AI，别重复报）
  日报.py round <输出文件>  解析一轮读回复的固定格式输出，累加当天统计；打印要立刻推的话（没有就不打印）
  日报.py daily           打印当天日报（发询盘数从各批次 sent_log 数）
读回复输出格式（读回复提示词.md 末尾定）：
  统计 新回复=3 回了=2 单价=1 尺寸=1 推网站=4
  要你定：<品名>：<一句话>
  ⚠ 停了：<原因>
  细节：……（只进日志）
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import CACHE, batch_dirs, now_bj

D = now_bj().strftime('%Y-%m-%d')
F = CACHE / f'buziliao_day_{D}.json'
KEYS = ['新回复', '回了', '单价', '尺寸', '推网站']
st = json.loads(F.read_text()) if F.exists() else {'轮': 0, **{k: 0 for k in KEYS}, '要你定': []}
cmd = sys.argv[1]

if cmd == 'asked':
    print('\n'.join(st['要你定']) or '（今天还没有）')
elif cmd == 'round':
    text = Path(sys.argv[2]).read_text()
    st['轮'] += 1
    m = re.search(r'^统计\s+(.*)$', text, re.M)
    for k, v in re.findall(r'(\S+?)=(\d+)', m.group(1) if m else ''):
        if k in st:
            st[k] += int(v)
    new = [l.strip() for l in text.splitlines() if l.strip().startswith('要你定：') and l.strip() not in st['要你定']]
    st['要你定'] += new
    stop = [l.strip() for l in text.splitlines() if l.strip().startswith('⚠')]
    F.write_text(json.dumps(st, ensure_ascii=False))
    hm = now_bj().strftime('%H:%M')
    out = stop[:1] + new
    if out:
        print(f'补资料 {hm}\n' + '\n'.join(out))
elif cmd == 'daily':
    r1 = rp = 0
    for b in batch_dirs():
        f = b / 'sent_log.jsonl'
        if f.exists():
            for l in f.read_text().splitlines():
                x = json.loads(l) if l.strip() else {}
                if str(x.get('时间', '')).startswith(D) and x.get('结果') == '成功':
                    r1 += x.get('轮次') == 'R1'
                    rp += x.get('轮次') != 'R1'
    left = sum(1 for x in json.loads((Path(__file__).resolve().parents[2] / 'batches/补资料/queue.json').read_text()) if x['状态'] == '待发R1')
    lines = [f'补资料日报 {D[5:]}',
             f'发询盘 {r1} 家，跟进回复 {rp} 条；队列还剩 {left} 家',
             f"收到回复 {st['新回复']} 家，记到单价 {st['单价']} 家、包装尺寸 {st['尺寸']} 家，推到网站 {st['推网站']} 条"]
    asks = [a.replace('要你定：', '', 1) for a in st['要你定']]
    lines += [f'今天要你定的 {len(asks)} 件：'] + [f'{i}. {a}' for i, a in enumerate(asks, 1)] if asks else ['今天没有要你定的事']
    print('\n'.join(lines))
