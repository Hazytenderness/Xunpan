"""Windows 每日入口。默认只显示计划；未授权时 --execute 立即退出。"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import ROOT, CACHE, batch_dirs, load_queue, find, now_bj, browser
from port import file_lock, run, require, notify, commit_paths, permissions

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night'


def current_policy():
    result=browser('site_policy.mjs',{'apply':True,'includeRows':True},timeout=180)
    if not result or result.get('错误') or result.get('采纳失败'):
        raise RuntimeError('网站实时采纳/筛选未完成，停止询盘')
    rows=result.pop('行')
    (CACHE/'current_purchase.json').write_text(json.dumps({'行':rows},ensure_ascii=False),encoding='utf-8')
    (CACHE/'current_policy.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['send', 'read'])
    ap.add_argument('hours', nargs='?', default='9,10,11,12,13,14,15,16,17,18')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--resume', action='store_true',help='在工作时段从已保存的发送队列继续，不重发成功项')
    a = ap.parse_args()
    now = now_bj(); day = now.date().isoformat()
    plan = {'模式': a.mode, '北京时间': now.isoformat(), '允许小时': a.hours,
            '自动运行': False, '入口': 'Python', 'AI': 'Codex',
            '步骤': ['建队列', '发送其他批次', '发送补资料'] if a.mode == 'send' else
                    ['扫描消息列表', '有新回复才调用Codex', '整理报价', '生成日报'],
            '断点': '已授权处理聊天；BZ0097核实仅缺文字，实时筛选通过后只补文字'}
    if not a.execute:
        print(json.dumps(plan, ensure_ascii=False)); return
    require('automatic')
    if now.hour not in {int(h) for h in a.hours.split(',')}:
        return
    def py(file, *args):
        return run([sys.executable, ROOT / 'tools' / file, *args], cwd=ROOT,timeout=12*3600 if file=='run.py' else 3600)
    try:
        with file_lock(CACHE / f'buziliao_{a.mode}_windows.lock', blocking=False):
            if a.mode == 'send':
                require('send')
                stamp = CACHE / f'buziliao_send_{day}_{now.hour}'
                if stamp.exists() and not a.resume: return
                # 仅允许已经只读核实过的断点补字，不重复发图。
                for b in batch_dirs():
                    if any(x['id'] == 'BZ0097' and x['状态'] == '待发R1' and not x.get('断点核实',{}).get('允许补文字') for x in load_queue(b)):
                        raise RuntimeError('BZ0097 尚未人工核实，发送保持停止')
                notify(f'Windows发询盘任务已启动（{now:%Y-%m-%d %H:%M} 北京时间）。仅处理日本站非食品接触、最新倍数>2且缺资料的款。')
                policy=current_policy()
                stamp.touch()
                print(py('补资料/建队列.py','--purchase',CACHE/'current_purchase.json','--policy',CACHE/'current_policy.json'),flush=True)
                commit_paths(ROOT, [ROOT/'batches/补资料'], f'补资料 {day} 建队列', push=permissions().get('github_push') is True)
                batches = [b for b in batch_dirs() if b.name != '补资料' and
                           any(x['状态'] == '待发R1' and x.get('旺旺名') for x in load_queue(b))]
                for b in batches + [ROOT / 'batches/补资料']:
                    log=CACHE/'logs'/f'{day}_R1_{b.name}.log';log.parent.mkdir(exist_ok=True)
                    with log.open('a',encoding='utf-8') as output:
                        child=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/run.py'),str(b),'--no-push'],cwd=ROOT,
                            env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1'},stdout=output,stderr=output,stdin=subprocess.DEVNULL)
                    commit_paths(ROOT,[b],f'R1 发送记录 {day}',push=permissions().get('github_push') is True)
                    if child.returncode:raise RuntimeError(f'发送在{b.name}停止，退出码{child.returncode}')
                notify(f'Windows发询盘任务本轮结束（{now_bj():%H:%M}）。发送记录已保存，18点会汇总。')
            elif now.hour == 18:
                stamp = CACHE / f'buziliao_daily_{day}'
                if not stamp.exists():
                    require('notify')
                    notify(py('补资料/日报.py', 'daily')); stamp.touch()
            else:
                require('scan')
                started=CACHE/f'read_started_{day}'
                if not started.exists():
                    notify(f'Windows扫描回复任务已启动（{now:%Y-%m-%d %H:%M}）。每10分钟扫描，有新回复就整理报价并同步日本站；18点汇总。');started.touch()
                policy=current_policy()
                scan = py('watch.py', '0.01')
                if '停止' in scan:
                    raise RuntimeError('浏览器扫描停止，不重试')
                pending_file=CACHE/'pending_replies.json'
                pending=json.loads(pending_file.read_text(encoding='utf-8')) if pending_file.exists() else {}
                recovered=CACHE/'recovered_39_seeded'
                if not recovered.exists():
                    for item in json.loads((ROOT/'tools/windows_pending_chats.json').read_text(encoding='utf-8')):
                        pending.setdefault(item['id'],f"新回复|{item['id']}|{item['ww']}|交接未处理回复")
                    recovered.touch()
                for line in scan.splitlines():
                    if line.startswith('新回复|'):pending[line.split('|')[1]]=line
                pending_file.write_text(json.dumps(pending,ensure_ascii=False),encoding='utf-8')
                permitted={x['序'] for x in policy['可询盘']}
                active=[]
                for key in list(pending):
                    b,x=find(key)
                    if any(k['序'] in permitted for k in x['对应款']):active.append(key)
                    else:pending.pop(key)
                keys=active[:5]
                pending_file.write_text(json.dumps(pending,ensure_ascii=False),encoding='utf-8')
                if not keys:return
                news=[pending[key] for key in keys]
                # 先由已验收的工具取证，AI只读缓存和图片，避免漏读或二次扫描丢消息。
                for key in keys:
                    text=py('chat.py',key);print(text,flush=True)
                    if '"错误"' in text:raise RuntimeError('读聊天失败，保留待处理列表')
                # Codex只输出结构化分析，工具执行由父程序控制，不依赖CLI的Shell权限。
                text = py('analyze_replies.py',*keys)
                (CACHE/'buziliao_read.out').write_text(text,encoding='utf-8')
                print(text)
                completed=re.search(r'^完成ID[：:]\s*(.*)$',text,re.M)
                if completed:
                    for key in re.findall(r'[A-Z]+\d+',completed.group(1)):
                        if key in keys:pending.pop(key,None)
                pending_file.write_text(json.dumps(pending,ensure_ascii=False),encoding='utf-8')
                report = py('补资料/日报.py', 'round', CACHE / 'buziliao_read.out')
                if report.strip(): notify(report)
                dirs=sorted({find(line.split('|')[1])[0] for line in news})
                commit_paths(ROOT,dirs,f'补资料读回复 {now:%Y-%m-%d %H:%M}',push=permissions().get('github_push') is True)
                current_policy()
    except BlockingIOError:
        print('上一轮仍在运行，跳过')


if __name__ == '__main__':
    main()
