"""Windows 每日入口。默认只显示计划；未授权时 --execute 立即退出。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import ROOT, CACHE, batch_dirs, load_queue, find, now_bj
from port import file_lock, run, require, codex, notify, commit_paths, permissions

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['send', 'read'])
    ap.add_argument('hours', nargs='?', default='9,10,11,12,13,14,15,16,17,18')
    ap.add_argument('--execute', action='store_true')
    a = ap.parse_args()
    now = now_bj(); day = now.date().isoformat()
    plan = {'模式': a.mode, '北京时间': now.isoformat(), '允许小时': a.hours,
            '自动运行': False, '入口': 'Python', 'AI': 'Codex',
            '步骤': ['建队列', '发送其他批次', '发送补资料'] if a.mode == 'send' else
                    ['扫描消息列表', '有新回复才调用Codex', '整理报价', '生成日报'],
            '断点': '39家须经用户授权读取；BZ0097禁止自动补发'}
    if not a.execute:
        print(json.dumps(plan, ensure_ascii=False)); return
    require('automatic')
    if now.hour not in {int(h) for h in a.hours.split(',')}:
        return
    def py(file, *args):
        return run([sys.executable, ROOT / 'tools' / file, *args], cwd=ROOT)
    try:
        with file_lock(CACHE / f'buziliao_{a.mode}_windows.lock', blocking=False):
            if a.mode == 'send':
                require('send')
                stamp = CACHE / f'buziliao_send_{day}_{now.hour}'
                if stamp.exists(): return
                # 不让部分发送的 BZ0097 混进自动批次。
                for b in batch_dirs():
                    if any(x['id'] == 'BZ0097' and x['状态'] == '待发R1' for x in load_queue(b)):
                        raise RuntimeError('BZ0097 尚未人工核实，发送保持停止')
                stamp.touch()
                print(py('补资料/建队列.py'))
                commit_paths(ROOT, [ROOT/'batches/补资料'], f'补资料 {day} 建队列', push=permissions().get('github_push') is True)
                batches = [b for b in batch_dirs() if b.name != '补资料' and
                           any(x['状态'] == '待发R1' and x.get('旺旺名') for x in load_queue(b))]
                for b in batches + [ROOT / 'batches/补资料']:
                    print(py('run.py', b, '--no-push'))
                    commit_paths(ROOT,[b],f'R1 发送记录 {day}',push=permissions().get('github_push') is True)
            elif now.hour == 18:
                stamp = CACHE / f'buziliao_daily_{day}'
                if not stamp.exists():
                    require('notify')
                    notify(py('补资料/日报.py', 'daily')); stamp.touch()
            else:
                require('scan')
                scan = py('watch.py', '0.01')
                if '停止' in scan:
                    raise RuntimeError('浏览器扫描停止，不重试')
                news = [line for line in scan.splitlines() if line.startswith('新回复|')]
                if not news: return
                prompt = (ROOT / 'tools/补资料/读回复提示词.md').read_text(encoding='utf-8').replace('python3 ', 'python ')
                prompt += '\n本次新回复：\n' + '\n'.join(news)
                prompt += '\n今天已报：\n' + py('补资料/日报.py', 'asked')
                text = codex(prompt, CACHE / 'buziliao_read.out', ROOT, write=True)
                print(text)
                report = py('补资料/日报.py', 'round', CACHE / 'buziliao_read.out')
                if report.strip(): notify(report)
                dirs=sorted({find(line.split('|')[1])[0] for line in news})
                commit_paths(ROOT,dirs,f'补资料读回复 {now:%Y-%m-%d %H:%M}',push=permissions().get('github_push') is True)
    except BlockingIOError:
        print('上一轮仍在运行，跳过')


if __name__ == '__main__':
    main()
