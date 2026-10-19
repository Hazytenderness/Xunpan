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
from port import file_lock, run, require, notify, commit_paths, permissions,HIDDEN
from resilience import RetryLater,atomic_json,merge_pending
from review_sync import flush
from workflow_backlog import snapshot

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night'


def current_policy():
    result=browser('site_policy.mjs',{'apply':True,'includeRows':True},timeout=180)
    if not result or result.get('错误'):raise RetryLater('网站实时筛选暂不可用，保留队列，下轮恢复')
    if result.get('采纳失败'):raise RuntimeError('网站复核有无法采纳项，需要核对数据')
    rows=result.pop('行')
    atomic_json(CACHE/'current_purchase.json',{'行':rows})
    atomic_json(CACHE/'current_policy.json',result)
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
    status={'status':'ok','time':now.isoformat()}
    def alert(message):
        try:notify(message);return True
        except Exception:print('通知暂未送达，保留本地运行日志',flush=True);return False
    def record(paths,message):
        sync_note=CACHE/'git_sync_pending.json'
        try:
            with file_lock(CACHE/'git_record.lock',timeout=30):
                commit_paths(ROOT,paths,message,push=permissions().get('github_push') is True)
            if permissions().get('github_push') is True and sync_note.exists():
                if alert('询盘GitHub同步已恢复，main和执行分支均已更新。'):sync_note.unlink(missing_ok=True)
        except Exception:
            print('GitHub同步暂缓，业务文件已保留；不强推或覆盖其他机器提交',flush=True)
            if permissions().get('github_push') is True and not sync_note.exists():
                delivered=alert('⚠ 询盘GitHub同步暂缓，本地台账已保存；请核对远端提交或网络，禁止其他机器直接接管发送。')
                if delivered:atomic_json(sync_note,{'时间':now_bj().isoformat(),'原因':'Git同步失败，保留本地提交，不强推'})
    try:
        with file_lock(CACHE / f'buziliao_{a.mode}_windows.lock', blocking=False):
            atomic_json(CACHE/f'runtime_{a.mode}.json',{'status':'running','time':now.isoformat()})
            if a.mode == 'send':
                require('send')
                if (CACHE/'send_paused.json').exists() or (CACHE/'neo_paused.json').exists():
                    raise RuntimeError('发送因风险或不确定回执暂停，需核实后恢复')
                stamp = CACHE / f'buziliao_send_{day}_{now.hour}'
                if stamp.exists() and not a.resume: return
                # 仅允许已经只读核实过的断点补字，不重复发图。
                for b in batch_dirs():
                    if any(x['id'] == 'BZ0097' and x['状态'] == '待发R1' and not x.get('断点核实',{}).get('允许补文字') for x in load_queue(b)):
                        raise RuntimeError('BZ0097 尚未人工核实，发送保持停止')
                started=CACHE/f'send_started_{day}'
                if not started.exists() and alert(f'Windows发询盘任务已启动（{now:%Y-%m-%d %H:%M} 北京时间）。仅处理日本站非食品接触、最新倍数>2且缺资料的款。'):started.touch()
                policy=current_policy()
                stamp.touch()
                print(py('补资料/建队列.py','--purchase',CACHE/'current_purchase.json','--policy',CACHE/'current_policy.json'),flush=True)
                record([ROOT/'batches/补资料'],f'补资料 {day} 建队列')
                batches = [b for b in batch_dirs() if b.name != '补资料' and
                           any(x['状态'] == '待发R1' and x.get('旺旺名') for x in load_queue(b))]
                for b in batches + [ROOT / 'batches/补资料']:
                    log=CACHE/'logs'/f'{day}_R1_{b.name}.log';log.parent.mkdir(exist_ok=True)
                    with log.open('a',encoding='utf-8') as output:
                        child=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/run.py'),str(b),'--no-push'],cwd=ROOT,
                            env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1'},stdout=output,stderr=output,stdin=subprocess.DEVNULL,creationflags=HIDDEN)
                    record([b],f'R1 发送记录 {day}')
                    if child.returncode==75:raise RetryLater('发送准备暂不可用，已保存断点，下轮自动继续')
                    if child.returncode:raise RuntimeError(f'发送在{b.name}停止，退出码{child.returncode}')
                print(f'发送本轮结束 {now_bj():%H:%M}；18点汇总',flush=True)
            elif now.hour == 18:
                stamp = CACHE / f'buziliao_daily_{day}'
                if not stamp.exists():
                    require('notify')
                    if alert(py('补资料/日报.py','daily')):stamp.touch()
            else:
                require('scan')
                started=CACHE/f'read_started_{day}'
                if not started.exists():
                    if alert(f'Windows扫描回复任务已启动（{now:%Y-%m-%d %H:%M}）。每10分钟扫描，有新回复就整理报价并同步日本站；18点汇总。'):started.touch()
                # 网络断开不影响扫描与本地落盘；同步队列与AI处理分离。
                with file_lock(CACHE/'review_sync.lock',timeout=90):sync=flush(CACHE)
                if sync['待同步']:print(f"网站待补同步：{sync['待同步']}份",flush=True)
                if sync['需处理']:
                    note=CACHE/'review_sync_attention.json'
                    if not note.exists() or json.loads(note.read_text(encoding='utf-8'))!=sync['需处理']:
                        if alert('⚠ 网站报价同步有权限或业务拒绝项，需要核对本机日志；其他采集继续。'):atomic_json(note,sync['需处理'])
                scan = py('watch.py', '0.01')
                if '停止' in scan:
                    if (CACHE/'neo_paused.json').exists():raise RuntimeError('出现验证或风控，暂停浏览器操作')
                    raise RetryLater('扫描页面暂不可用，保留任务，下轮恢复')
                pending_file=CACHE/'pending_replies.json'
                pending=json.loads(pending_file.read_text(encoding='utf-8')) if pending_file.exists() else {}
                baseline=pending.copy()
                backlog=snapshot(ROOT,CACHE,now_bj())
                for key in backlog['可续接']:pending.setdefault(key,f'续接资料|{key}|已有会话|按最新优先级补资料')
                def persist():
                    nonlocal pending,baseline
                    pending=merge_pending(CACHE,baseline,pending);baseline=pending.copy()
                recovered=CACHE/'recovered_39_seeded'
                if not recovered.exists():
                    for item in json.loads((ROOT/'tools/windows_pending_chats.json').read_text(encoding='utf-8')):
                        pending.setdefault(item['id'],f"新回复|{item['id']}|{item['ww']}|交接未处理回复")
                    recovered.touch()
                for line in scan.splitlines():
                    if line.startswith('新回复|'):pending[line.split('|')[1]]=line
                persist()
                if '暂缓：' in scan:raise RetryLater('扫描连接暂不可用，下轮恢复')
                policy=current_policy()
                permitted={x['序'] for x in policy['可询盘']}
                active=[]
                for key in list(pending):
                    b,x=find(key)
                    if any(k['序'] in permitted for k in x['对应款']):active.append(key)
                    else:pending.pop(key)
                keys=active[:5]
                persist()
                if not keys:return
                readable=[]
                # 先由已验收的工具取证，AI只读缓存和图片，避免漏读或二次扫描丢消息。
                for key in keys:
                    text=py('chat.py',key);print(text,flush=True)
                    if '"错误"' in text:
                        if (CACHE/'neo_paused.json').exists():raise RuntimeError('出现验证或风控，停止读取')
                        pending[key]=pending.pop(key)
                        print(f'会话暂缓|{key}|读取未通过，保留待处理并继续其他会话',flush=True)
                    else:readable.append(key)
                persist()
                keys=readable
                if not keys:return
                news=[pending[key] for key in keys]
                # Codex只输出结构化分析，工具执行由父程序控制，不依赖CLI的Shell权限。
                text = py('analyze_replies.py',*keys)
                (CACHE/'buziliao_read.out').write_text(text,encoding='utf-8')
                print(text)
                completed=re.search(r'^完成ID[：:]\s*(.*)$',text,re.M)
                if completed:
                    finished=re.findall(r'[A-Z]+\d+',completed.group(1))
                    for key in finished:
                        if key in keys:pending.pop(key,None)
                    for key in keys:
                        if key not in finished and key in pending:pending[key]=pending.pop(key)
                persist()
                report = py('补资料/日报.py', 'round', CACHE / 'buziliao_read.out')
                if report.strip():alert(report)
                dirs=sorted({find(line.split('|')[1])[0] for line in news})
                record(dirs,f'补资料读回复 {now:%Y-%m-%d %H:%M}')
                current_policy()
                snapshot(ROOT,CACHE,now_bj())
    except BlockingIOError:
        print('上一轮仍在运行，跳过')
        status['status']='busy'
    except RetryLater as error:
        status.update(status='deferred',reason=str(error));print('暂缓|'+str(error),flush=True)
    except BaseException:
        status['status']='failed';raise
    finally:atomic_json(CACHE/f'runtime_{a.mode}.json',status)


if __name__ == '__main__':
    main()
