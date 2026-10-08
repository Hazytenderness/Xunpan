"""连发首轮询盘：把批次里「待发R1」按 A/B 交替发出，直到发完或到北京 18:00。
用法：python3 tools/run.py batches/<批次> [--ids L01,L02] [--no-push]
每条走 tools/browser/send.mjs 的全套核对；两条之间随机 2–4 分钟（且不少于全局间隔 60 秒）；
任何一条结果不是「成功」立刻停。每发 10 条和结束时提交推送。"""
import argparse, json, random, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import ROOT, browser, load_queue, save_queue, append_log, to_beijing, in_work_hours, now_bj

ap = argparse.ArgumentParser()
ap.add_argument('batch')
ap.add_argument('--ids')
ap.add_argument('--no-push', action='store_true')
a = ap.parse_args()
B = Path(a.batch)
BRANCH = 'main'


def push(msg):
    if a.no_push:
        return
    subprocess.run(['git', '-C', str(ROOT), 'add', str(B)])
    subprocess.run(['git', '-C', str(ROOT), 'commit', '-q', '-m', msg])
    subprocess.run(['git', '-C', str(ROOT), 'pull', '-q', '--rebase'])
    subprocess.run(['git', '-C', str(ROOT), 'push', '-q'])


q = load_queue(B)
pending = [x for x in q if x['状态'] == '待发R1' and x.get('旺旺名')]
if a.ids:
    order = [i for i in a.ids.split(',') if any(x['id'] == i for x in pending)]
else:
    A_ = [x['id'] for x in pending if x['组'] == 'A']
    B_ = [x['id'] for x in pending if x['组'] != 'A']
    order = []
    for i in range(max(len(A_), len(B_))):
        order += A_[i:i + 1] + B_[i:i + 1]
sent = 0
for n, lid in enumerate(order):
    if not in_work_hours():
        print(f'{now_bj():%H:%M} 不在北京 9:00–18:00，停', flush=True)
        break
    if n:
        time.sleep(random.uniform(120, 240))
    q = load_queue(B)
    x = next(i for i in q if i['id'] == lid)
    if x['状态'] != '待发R1':
        continue
    r = browser('send.mjs', {'ww': x['旺旺名'], 'offerId': x['商品'][0]['offerId'], 'text': x['r1_text']}, sending=True) or {'结果': '无结果'}
    print(f"{now_bj():%H:%M:%S} {lid} {x['组']} {x['旺旺名']} {r.get('结果')}", flush=True)
    if r.get('结果') != '成功':
        print('停止：' + json.dumps(r, ensure_ascii=False), flush=True)
        push(f'R1 发送停止于 {lid}（{B.name}）')
        sys.exit(3)
    append_log(B, {'id': lid, '组': x['组'], '轮次': 'R1', '旺旺名': x['旺旺名'], 'offerId': x['商品'][0]['offerId'],
                   '时间': to_beijing(r.get('发送时间') or ''), '文本': x['r1_text'], '核对': r.get('核对'),
                   '发后新增条数': r.get('发后新增条数'), '结果': '成功', '打开时我方已有': r.get('打开时', {}).get('我方条数')})
    x['状态'] = '已发R1'
    save_queue(B, q)
    sent += 1
    if sent % 10 == 0:
        push(f'R1 发送 {sent} 条（{B.name}）')
push(f'R1 发送 {sent} 条（{B.name}，本轮结束）')
print('本轮结束', sent, flush=True)
