"""连发首轮询盘：把批次里「待发R1」按 A/B 交替发出，直到发完或到北京 18:00。
用法：python3 tools/run.py batches/<批次> [--ids L01,L02] [--no-push]
每条先发对应款的日本站主图、再发文字（用户定·10/9），走 tools/browser/send.mjs 的全套核对；两条之间随机 2–4 分钟（且不少于全局间隔 60 秒）；
任何一条结果不是「成功」立刻停。每发 10 条和结束时提交推送。"""
import argparse, json, random, re, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import ROOT, CACHE, browser, load_queue, save_queue, append_log, to_beijing, in_work_hours, now_bj
from port import require,site_root
from resilience import RetryLater
from images import download_image
from inquiry_workflow import first_message,VERSION
require('send')

ap = argparse.ArgumentParser()
ap.add_argument('batch')
ap.add_argument('--ids')
ap.add_argument('--no-push', action='store_true')
a = ap.parse_args()
B = Path(a.batch)
BRANCH = 'main'
ASK = '图上这款有吗？'
SITE_JS = site_root()/'build/js'


def main_image(asin):
    """对应款的亚马逊主图下到本地缓存，返回路径；网站数据里没有这款返回 None。"""
    f = CACHE / 'img' / f'{asin}.jpg'
    if not f.exists():
        url = next((u for js in ('products.js', 'products-au.js')
                    for u in re.findall(r'"asin":"%s"[^{}]*?"图":"([^"]+)"' % asin, (SITE_JS / js).read_text(encoding='utf-8'))), None)
        if not url:
            return None
        f.parent.mkdir(exist_ok=True)
        download_image(url,f)
    return str(f)


def push(msg):
    if a.no_push:
        return
    require('github_push')
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
        if not in_work_hours():break
    q = load_queue(B)
    x = next(i for i in q if i['id'] == lid)
    if x['状态'] != '待发R1':
        continue
    job = {'ww': x['旺旺名'], 'offerId': x['商品'][0]['offerId'], 'text': x['r1_text'], 'seqs':[k['序'] for k in x['对应款']],
           'targets':[{'seq':k['序'],'asin':k['asin']} for k in x['对应款']],'kind':'R1'}
    if x.get('话术版本')!=VERSION:
        x['r1_text'] = job['text'] = first_message(x)
        x['话术版本']=VERSION
        save_queue(B, q)
    if not x.get('图已发'):
        try:job['img'] = main_image(x['对应款'][0]['asin'])
        except RuntimeError:
            print(f'{lid} 商品主图下载失败，保持待发并跳过本条',flush=True)
            continue
        if not job['img']:
            x['发送阻塞']={'原因':'缺目标主图','ASIN':x['对应款'][0]['asin'],'时间':now_bj().isoformat()}
            x['状态']='待补主图';save_queue(B,q)
            print(f"{now_bj():%H:%M:%S} {lid} 缺目标主图，移交核页，停止反复重试", flush=True)
            continue
    try:r = browser('send.mjs', job, sending=True) or {'结果': '无结果'}
    except RetryLater as error:
        print('XUNPAN_RETRY_LATER: '+str(error),file=sys.stderr,flush=True);sys.exit(75)
    # Windows 接管：断线、验证、收件人异常立即停，不自动重试。
    if str(r.get('结果','')).startswith('跳过:'):
        if r.get('需重读'):
            print(lid,r['结果'],flush=True);continue
        if '最新聊天已有相同内容' in r['结果']:
            x['状态']='已发R1';x['发送核对']=r;save_queue(B,q)
            print(lid,'聊天已有首询，继续读回复',flush=True);continue
        x['状态']='不用发';x['备注']=(x.get('备注') or '')+'；'+r['结果'];save_queue(B,q)
        print(lid,r['结果'],flush=True);continue
    if r.get('需重读'):
        print(lid,r['结果'],flush=True);continue
    print(f"{now_bj():%H:%M:%S} {lid} {x['组']} {x['旺旺名']} {r.get('结果')}", flush=True)
    if r.get('图已发') and r.get('结果') != '成功':  # 图发出去了、字没发成：下次只补发字，不重复发图
        x['图已发'] = True
        save_queue(B, q)
    if r.get('结果') != '成功':
        x['状态']='待人工核实';x['回复暂停']={'时间':now_bj().isoformat(),'原因':r.get('结果','无结果')};save_queue(B,q)
        if '未核实发送意图' in r.get('结果','') and not (CACHE/'neo_paused.json').exists():
            print('仅暂停本商家，保留发送意图等待回执核实',flush=True)
            continue
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
