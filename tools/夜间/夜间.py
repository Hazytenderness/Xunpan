"""Windows 夜间入口。默认计划预览；外部动作分别由仓库外授权门控制。"""
import argparse
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from base import ROOT, CACHE, now_bj, batch_dirs, load_queue
from port import run, executable, file_lock, require, codex, notify, commit_paths

SITE = Path.home() / 'ClaudeP/06_VibeCoding/ataous/ataous-site-night'
T = ROOT / 'tools/夜间'
SUPPLIERS = Path.home() / 'ClaudeP/06_VibeCoding/ataous/供应商匹配'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--now', action='store_true')
    ap.add_argument('--publish', action='store_true', help='另外经用户批准后才能发布')
    args = ap.parse_args()
    now = now_bj(); day = now.date().isoformat()
    plan = {'入口': 'Python', '北京时间': now.isoformat(), '放行小时': 19, '自动运行': False,
            '步骤': ['读取选品记录', '跳过其他会话正在处理的款', '遨虾主图搜与审图',
                     '不足3家才文字补搜', '追加候选与保护核对', '核页核SKU', '推复核',
                     '写匹配度与新旧候选合并', '检查并等待发布批准'],
            '需要单独授权': ['automatic', 'paid_search', 'ai_workflow', 'review_push', 'github_push', 'deploy', 'notify']}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False)); return
    require('automatic')
    for action in ('paid_search', 'ai_workflow', 'review_push', 'notify'):
        require(action)
    if args.publish:
        require('github_push'); require('deploy')
    if not args.now and now.hour != 19: return
    stamp = CACHE / f'night_{day}'
    if stamp.exists(): return
    # 干净专用副本是保护前提；失败时保留证据，不checkout覆盖文件。
    if run(['git', '-C', SITE, 'status', '--porcelain']).strip():
        raise RuntimeError('网站夜间副本有未提交工作，停止')
    with file_lock(CACHE / 'night_windows.lock', blocking=False):
        stamp.touch()
        W = CACHE / 'night' / day; W.mkdir(parents=True, exist_ok=True)
        FB = SUPPLIERS / (day.replace('-', '') + '_夜间'); FB.mkdir(parents=True, exist_ok=True)
        HB = ROOT / 'batches' / (day + '-夜间核页')
        env = {'XUNPAN_WORK': str(W), 'XUNPAN_BATCH': str(HB)}
        def py(file, *a): return run([sys.executable, ROOT / 'tools' / file, *a], cwd=ROOT, env=env)
        def node(file, *a, cwd=ROOT): return run(['node', file, *a], cwd=cwd, env=env)
        def save(name, data): (W / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        def output(name, text): (W / name).write_text(text, encoding='utf-8'); return text
        def protect(stage, ids, fields, operation):
            snap = W / f'before_{stage}.json'
            node(T / '保护核对.mjs', 'snap', SITE, snap)
            result = operation()
            output(f'protect_{stage}.txt', node(T / '保护核对.mjs', 'diff', SITE, snap, ids, fields))
            return result
        def ai(promptfile, extra, result):
            text = Path(promptfile).read_text(encoding='utf-8').replace('python3 ', 'python ')
            # 图像作为附件传入，不能靠命令行文本冒充审图。
            import re
            pictures = [Path(p) for p in re.findall(r'(?m)(?:^|[\s(])([^\n()]+\.(?:png|jpg|jpeg))', extra)
                        if Path(p).is_file()]
            return codex(text + '\n' + extra, W / result, ROOT, write=True, images=pictures)
        run(['git', '-C', SITE, 'pull', '--ff-only'])
        output('purchase.out', run([sys.executable, ROOT / 'tools/拉记录.py', 'jp', W / 'purchase.json'], cwd=SITE))
        busy = set()
        for b in batch_dirs():
            if b.name == '补资料' or b.name.endswith('夜间核页'): continue
            q = load_queue(b)
            if any(x.get('状态') == '待核页' for x in q): busy.update(k['序'] for x in q for k in x['对应款'])
        for d in SUPPLIERS.iterdir():
            if not d.is_dir() or d.name.endswith('_夜间'): continue
            files = [f for f in d.rglob('*') if f.is_file()]
            if max((f.stat().st_mtime for f in files), default=0) < time.time()-6*3600: continue
            for f in d.glob('任务清单*.json'): busy.update(int(x['序']) for x in json.loads(f.read_text(encoding='utf-8')))
        save('skip.json', sorted(busy))
        source = json.loads(node(T / '清单.mjs', SITE, W / 'purchase.json', 'source', W / 'skip.json'))
        ledgerfile = T / '找货源台账.json'
        ledger = json.loads(ledgerfile.read_text(encoding='utf-8')) if ledgerfile.exists() else {}
        cut = (now.date()-timedelta(days=14)).isoformat()
        todo = [x for x in source if ledger.get(str(x['序']), '') < cut]
        (FB / '任务清单.json').write_text(json.dumps(todo, ensure_ascii=False), encoding='utf-8')
        appended = W / 'appended.json'; save('appended.json', [])
        if todo:
            output('search.out', py('夜间/找货源.py', 'search', FB))
            output('screen.out', py('夜间/找货源.py', 'screen', FB))
            for task in sorted((FB / 'review').glob('task_*.md')):
                ai(T / '审图提示词.md', task.read_text(encoding='utf-8')+'\n任务文件：'+str(task), task.stem+'.out')
            needed = output('need-kw.txt', py('夜间/找货源.py', 'need-kw', FB))
            if needed.strip():
                ai(T / '搜索词提示词.md', '词搜词.json 路径：'+str(FB / '词搜词.json')+'\n'+needed, 'keywords.out')
                output('kw.out', py('夜间/找货源.py', 'kw', FB))
                for task in sorted((FB / 'review_kw').glob('task_*.md')):
                    ai(T / '审图提示词.md', task.read_text(encoding='utf-8')+'\n任务文件：'+str(task), 'kw-'+task.stem+'.out')
            output('rank.out', py('夜间/找货源.py', 'rank', FB))
            save('source_ids.json', [x['序'] for x in todo])
            protect('source', W / 'source_ids.json', '参考成本,参考成本说明,货源候选,图搜记录',
                    lambda: output('append.out', node(SITE / 'scripts/night-candidates.mjs', 'append', FB / 'seeds.json', appended, cwd=SITE)))
            seeds = json.loads((FB / 'seeds.json').read_text(encoding='utf-8'))
            for x in todo: ledger[str(x['序'])] = '跳过' if seeds.get(x['asin'], {}).get('图搜无结果') else day
            ledgerfile.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding='utf-8')
        products = json.loads(node(T / '清单.mjs', SITE, W / 'purchase.json', 'check', W / 'skip.json'))
        save('products.json', products)
        if products:
            output('batch.out', py('核SKU/建批次.py', HB))
            # hepage任何失败即停止整轮，不继续核、推、发布。
            output('hepage.out', py('hepage.py', HB))
            chunk = 0
            while True:
                lines = py('核SKU/ready.py', '10').splitlines()
                ids = lines[-1] if len(lines)>1 else ''
                if not ids.strip(): break
                chunk += 1
                output(f'prep_{chunk}.out', py('核SKU/prep.py', f'n{chunk}', ids))
                c = W / 'chunks' / f'n{chunk}'
                ai(ROOT / 'tools/核SKU/匹配说明.md', '块目录 '+str(c)+'；输入 input.json，输出 match.json。\n'+
                   '\n'.join(str(p) for p in (c / 'img').glob('sheet_*.jpg')), f'match_{chunk}.out')
            output('merge.out', py('核SKU/merge.py'))
            output('feed.out', py('build_review_feed.py', HB, '--site', SITE))
            pushed = output('push.out', py('push_review_feed.py', HB))
            if json.loads(pushed.splitlines()[-1]).get('未导入'): raise RuntimeError('复核有未导入项，停止发布')
            save('check_ids.json', sorted({k['序'] for x in load_queue(HB) for k in x['对应款']}))
            protect('check', W / 'check_ids.json', '货源候选',
                    lambda: output('match.out', node(SITE / 'scripts/import-match.mjs', HB, '--apply', cwd=SITE)))
        if json.loads(appended.read_text(encoding='utf-8')):
            protect('trim', appended, '参考成本,参考成本说明,货源候选',
                    lambda: output('trim.out', node(SITE / 'scripts/night-candidates.mjs', 'trim', appended, cwd=SITE)))
        confirmed = py('补资料/询盘匹配度.py', W).strip()
        if confirmed:
            qd = Path(confirmed)
            save('confirm_ids.json', sorted({x['序'] for x in json.loads((qd / '核页规格匹配.json').read_text(encoding='utf-8'))}))
            protect('confirmed', W / 'confirm_ids.json', '货源候选',
                    lambda: node(SITE / 'scripts/import-match.mjs', qd, '--apply', cwd=SITE))
        output('test.out', run([executable('npm'), 'test'], cwd=SITE))
        output('check.out', run([executable('npm'), 'run', 'check'], cwd=SITE))
        run(['git', '-C', SITE, 'diff', '--check'])
        xunpan_paths=[ledgerfile]+([HB] if HB.exists() else [])
        commit_paths(ROOT,xunpan_paths,f'夜间核页与找货源台账 {day}',push=args.publish)
        live = '尚未发布，等待用户审查并批准'
        if args.publish and run(['git','-C',SITE,'diff','--','build/js']).strip():
            require('deploy'); require('github_push')
            if run(['git','-C',SITE,'branch','--show-current']).strip()!='main':
                raise RuntimeError('夜间网站副本分支不是main，停止发布')
            run(['git','-C',SITE,'add','build/js/products.js','build/js/products-sources.js'])
            run(['git','-C',SITE,'commit','-m',f'夜间任务 {day}：已核验货源与SKU'])
            run(['git','-C',SITE,'pull','--rebase'])
            # 变基后重跑检查，再推送。
            run([executable('npm'),'test'],cwd=SITE);run([executable('npm'),'run','check'],cwd=SITE)
            run(['git','-C',SITE,'diff','--check'])
            sha=run(['git','-C',SITE,'rev-parse','HEAD']).strip()
            run(['git','-C',SITE,'push','origin','main'])
            # 没有gh时保留推送证据，绝不能把推送成功当作构建成功。
            import shutil
            if shutil.which('gh'):
                for attempt in range(40):
                    checks=json.loads(run(['gh','api',f'repos/Hazytenderness/ataous-site/commits/{sha}/check-runs']))
                    checks=[x for x in checks.get('check_runs',[]) if 'ataous' in x['name'].lower()]
                    if checks and all(x['status']=='completed' for x in checks):
                        live='构建成功，待线上验收' if all(x['conclusion']=='success' for x in checks) else '构建失败'
                        break
                    time.sleep(15)
                else:live='已推送，构建未确认'
            else:live='已推送，未安装gh，构建未确认'
        report = {'日期':day,'找货源款':len(todo),'待核页款':len(products),'跳过':len(busy),
                  '上线':live,'工作目录':str(W)}
        save('结果.json',report)
        notify(f"夜间任务 {day}\n找货源 {len(todo)} 款，核页 {len(products)} 款，跳过 {len(busy)} 款。\n上线：{live}")
        print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    main()
