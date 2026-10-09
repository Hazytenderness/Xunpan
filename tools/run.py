"""连发首轮询盘：把批次里「待发R1」按 A/B 交替发出，直到发完或到北京 18:00。
用法：python3 tools/run.py batches/<批次> [--ids L01,L02] [--no-push]
每条先发对应款的日本站主图、再发文字（用户定·10/9），走 tools/browser/send.mjs 的全套核对；两条之间随机 2–4 分钟（且不少于全局间隔 60 秒）；
任何一条结果不是「成功」立刻停。每发 10 条和结束时提交推送。"""
import argparse, json, random, re, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import ROOT, CACHE, browser, load_queue, save_queue, append_log, to_beijing, in_work_hours, now_bj

ap = argparse.ArgumentParser()
ap.add_argument('batch')
ap.add_argument('--ids')
ap.add_argument('--no-push', action='store_true')
a = ap.parse_args()
B = Path(a.batch)
BRANCH = 'main'
ASK = '图上这款有吗？'
SITE_JS = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night/build/js'  # 网站夜间副本，每款都存了亚马逊主图


def main_image(asin):
    """对应款的亚马逊主图下到本地缓存，返回路径；网站数据里没有这款返回 None。"""
    f = CACHE / 'img' / f'{asin}.jpg'
    if not f.exists():
        url = next((u for js in ('products.js', 'products-au.js')
                    for u in re.findall(r'"asin":"%s"[^{}]*?"图":"([^"]+)"' % asin, (SITE_JS / js).read_text())), None)
        if not url:
            return None
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(urllib.request.urlopen(re.sub(r'\._[^/]*_\.jpg$', '.jpg', url), timeout=30).read())  # 去掉尺寸后缀取原图（加 SL1000 有的图会变成小图）
    return str(f)


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
    job = {'ww': x['旺旺名'], 'offerId': x['商品'][0]['offerId'], 'text': x['r1_text']}
    if not x['r1_text'].startswith(ASK):  # 先问图上这款有没有，再问价和包装【用户定·10/9】
        x['r1_text'] = job['text'] = ASK + x['r1_text']
        save_queue(B, q)
    if not x.get('图已发'):
        job['img'] = main_image(x['对应款'][0]['asin'])
        if not job['img']:
            print(f"{now_bj():%H:%M:%S} {lid} 网站数据里找不到 {x['对应款'][0]['asin']} 的主图，跳过", flush=True)
            continue
    r = browser('send.mjs', job, sending=True) or {'结果': '无结果'}
    # 1688 聊天临时断线（点此重连）不算风控：等 5、10、15 分钟各重试一次，还断才停【用户定·10/9】
    for k in (1, 2, 3):
        if '聊天连接断开' not in str(r.get('结果')) or not in_work_hours():
            break
        print(f'{now_bj():%H:%M:%S} {lid} 聊天断线，{5 * k} 分钟后重试', flush=True)
        time.sleep(300 * k)
        r = browser('send.mjs', job, sending=True) or {'结果': '无结果'}
    print(f"{now_bj():%H:%M:%S} {lid} {x['组']} {x['旺旺名']} {r.get('结果')}", flush=True)
    if r.get('图已发') and r.get('结果') != '成功':  # 图发出去了、字没发成：下次只补发字，不重复发图
        x['图已发'] = True
        save_queue(B, q)
    if r.get('结果') != '成功':
        print('停止：' + json.dumps(r, ensure_ascii=False), flush=True)
        push(f'R1 发送停止于 {lid}（{B.name}）')
        sys.exit(3)
    append_log(B, {'id': lid, '组': x['组'], '轮次': 'R1', '旺旺名': x['旺旺名'], 'offerId': x['商品'][0]['offerId'],
                   '时间': to_beijing(r.get('发送时间') or ''), '文本': x['r1_text'], '图片': job.get('img'), '核对': r.get('核对'),
                   '发后新增条数': r.get('发后新增条数'), '结果': '成功', '打开时我方已有': r.get('打开时', {}).get('我方条数')})
    x['状态'] = '已发R1'
    save_queue(B, q)
    sent += 1
    if sent % 10 == 0:
        push(f'R1 发送 {sent} 条（{B.name}）')
push(f'R1 发送 {sent} 条（{B.name}，本轮结束）')
print('本轮结束', sent, flush=True)
