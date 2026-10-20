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
from base import ROOT
from inquiry_reporting import identity_index, humanize_line

D = now_bj().strftime('%Y-%m-%d')
F = CACHE / f'buziliao_day_{D}.json'
KEYS = ['新回复', '回了', '单价', '尺寸', '推网站']
st = json.loads(F.read_text(encoding='utf-8')) if F.exists() else {'轮': 0, **{k: 0 for k in KEYS}, '要你定': []}
cmd = sys.argv[1]

if cmd == 'asked':
    print('\n'.join(st['要你定']) or '（今天还没有）')
elif cmd == 'round':
    text = Path(sys.argv[2]).read_text(encoding='utf-8')
    st['轮'] += 1
    m = re.search(r'^统计\s+(.*)$', text, re.M)
    for k, v in re.findall(r'(\S+?)=(\d+)', m.group(1) if m else ''):
        if k in st:
            st[k] += int(v)
    new = list(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip().startswith('要你定：') and l.strip() not in st['要你定']))
    st['要你定'] += new
    stop = [l.strip() for l in text.splitlines() if l.strip().startswith('⚠')]
    F.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    hm = now_bj().strftime('%H:%M')
    out = stop[:1] + new
    if out:
        index=identity_index(ROOT)
        print(f'补资料 {hm}\n' + '\n'.join(humanize_line(line,index) for line in out))
elif cmd == 'daily':
    r1 = rp = 0
    for b in batch_dirs():
        f = b / 'sent_log.jsonl'
        if f.exists():
            for l in f.read_text(encoding='utf-8').splitlines():
                x = json.loads(l) if l.strip() else {}
                if str(x.get('时间', '')).startswith(D) and x.get('结果') == '成功':
                    r1 += x.get('轮次') == 'R1'
                    rp += x.get('轮次') != 'R1'
    left = sum(1 for x in json.loads((Path(__file__).resolve().parents[2] / 'batches/补资料/queue.json').read_text(encoding='utf-8')) if x['状态'] == '待发R1')
    lines = [f'补资料日报 {D[5:]}',
             f'今日新发询盘 {r1} 条，发出跟进 {rp} 条；待首次发送 {left} 条',
             f"今日处理回复/续审 {st['新回复']} 次（含同商家多轮），记录单价 {st['单价']} 次、包装 {st['尺寸']} 次；网站新增复核 {st['推网站']} 条"]
    cloud_file=CACHE/'inquiry_cloud_state.json'
    tasks=json.loads(cloud_file.read_text(encoding='utf-8')).get('tasks',[]) if cloud_file.exists() else []
    needs=[t for t in tasks if t.get('status') in ('needs_human','blocked')]
    pending=[t for t in tasks if t.get('status') in ('answered','queued','working','waiting_send')]
    done=[t for t in tasks if t.get('status')=='done' and str(t.get('updatedAt',''))[:10]==D]
    if tasks:
        lines.append(f'网站当前：待同事处理 {len(needs)} 项，已提交待AI续接 {len(pending)} 项，今日已执行 {len(done)} 项')
        for task in needs[:3]:
            lines.append(task['product']['cw']+' '+task['product']['name']+' · '+task['supplier']['name']+'：'+task['question'][:100]+' · https://ataous.com/inquiry/?task='+task['id'])
    else:lines.append('网站待办状态尚未刷新，请打开待办页查看实时进度。')
    lines.append('查看全部待办、聊天与图片并提交意见：https://ataous.com/inquiry/')
    print('\n'.join(lines))
