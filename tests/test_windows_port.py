import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/lib'))
import base
import port
sys.path.insert(0,str(ROOT/'tools'))
import analyze_replies


class WindowsPortTests(unittest.TestCase):
    def test_daily_records_sync_canonical_main_and_work_branch_atomically(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if 'diff' in args:return 'batches/test/queue.json'
            if 'branch' in args:return 'windows-port'
            return ''
        with patch.object(port,'require'),patch.object(port,'run',side_effect=run):
            port.commit_paths(ROOT,[ROOT/'batches/test'],'同步台账',push=True)
        push=next(c for c in calls if 'push' in c)
        self.assertIn('--atomic',push);self.assertIn('HEAD:main',push);self.assertIn('HEAD:windows-port',push)
        self.assertNotIn('--force',push)

    def test_previously_unpushed_commit_is_retried_without_creating_empty_commit(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return 'windows-port' if 'branch' in args else ''
        with patch.object(port,'require'),patch.object(port,'run',side_effect=run):
            port.commit_paths(ROOT,['batches/test'],'续同步',push=True)
        self.assertFalse(any('commit' in c for c in calls));self.assertTrue(any('push' in c for c in calls))

    def test_retry_later_preserves_safe_capacity_reason(self):
        import tempfile
        from resilience import RetryLater
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            with patch.object(port,'CACHE',Path(folder)),patch.object(port,'captured',return_value=subprocess.CompletedProcess([],75,'','XUNPAN_RETRY_LATER: AI分析模型当前满载，资料已保留')):
                with self.assertRaisesRegex(RetryLater,'模型当前满载'):port.run([sys.executable,'analyze.py'])

    def test_codex_capacity_is_reported_without_switching_model(self):
        import tempfile
        from resilience import RetryLater
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            with patch.object(port,'permissions',return_value={}),patch.object(port,'captured',return_value=subprocess.CompletedProcess([],1,'','ERROR: Selected model is at capacity. Please try a different model.')):
                with self.assertRaisesRegex(RetryLater,'模型当前满载'):port.codex('只分析',Path(folder)/'result.json',ROOT,analysis_only=True)

    def test_browser_deferred_keeps_actual_site_gate_error(self):
        import tempfile
        from contextlib import nullcontext
        from resilience import RetryLater
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder)
            def child(*args,**kwargs):
                (cache/'site_policy.out.json').write_text(json.dumps({'错误':'网站同步门禁失败：exceeded the quota','可重试':True}),encoding='utf-8')
            with patch.object(base,'CACHE',cache),patch.object(base,'file_lock',return_value=nullcontext()),\
                 patch.object(base,'ensure_neo'),patch.object(base,'captured',side_effect=child),patch.object(base.time,'sleep'):
                with self.assertRaisesRegex(RetryLater,'exceeded the quota'):
                    base.browser('site_policy.mjs',{'apply':False})

    def test_policy_outage_keeps_new_scan_in_pending_and_defers_without_failure(self):
        import importlib.util,tempfile
        from contextlib import nullcontext
        from datetime import datetime
        from resilience import RetryLater
        spec=importlib.util.spec_from_file_location('daily',ROOT/'tools/补资料/每日.py')
        daily=importlib.util.module_from_spec(spec);spec.loader.exec_module(daily)
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);(cache/'read_started_2026-10-14').touch();(cache/'recovered_39_seeded').touch()
            def child(args,**kwargs):return '新回复|X1|店铺|真实回复' if Path(args[1]).name=='watch.py' else ''
            with patch.object(sys,'argv',['daily','read','17','--execute']),patch.object(daily,'CACHE',cache),\
                 patch.object(daily,'now_bj',return_value=datetime(2026,10,14,17,tzinfo=base.BJ)),\
                 patch.object(daily,'file_lock',return_value=nullcontext()),patch.object(daily,'require'),\
                 patch.object(daily,'notify'),patch.object(daily,'current_policy',side_effect=RetryLater('网站断网')),\
                 patch.object(daily,'consume_decisions',return_value={'received':0}),patch.object(daily,'run',side_effect=child):daily.main()
            self.assertIn('X1',json.loads((cache/'pending_replies.json').read_text(encoding='utf8')))
            self.assertEqual(json.loads((cache/'runtime_read.json').read_text(encoding='utf8'))['status'],'deferred')

    def test_same_reply_analysis_does_not_call_codex_twice(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);(cache/'queue.json').write_text('[]',encoding='utf8')
            record={'id':'X1','历史':[]}
            result={'items':[{'id':'X1','quotes':[],'reply':'','needs_user':''}]}
            def analyze(prompt,output,*args,**kwargs):output.write_text(json.dumps(result),encoding='utf8')
            with patch.object(sys,'argv',['analyze','X1']),patch.object(analyze_replies,'CACHE',cache),\
                 patch.object(analyze_replies,'context',return_value=([record],[])),\
                 patch.object(analyze_replies,'find',return_value=(cache,{'对应款':[{'规格':'目标款'}]})),\
                 patch.object(analyze_replies,'codex',side_effect=analyze) as call,patch.object(analyze_replies,'in_work_hours',return_value=False):
                analyze_replies.main();analyze_replies.main()
            self.assertEqual(call.call_count,1)

    def test_explicit_match_boolean_is_normalized_with_supplier_evidence(self):
        record={'历史':[{'发送方':'对方','内容':'这个花纹的没有哦','文件':[],'时间':'2026-10-14'}]}
        for value,expected in [({'匹配':False,'说明':'没有该花纹'},'不匹配'),
                               ({'匹配':True,'规格':'60片装'},'完全匹配')]:
            record['历史'][0]['内容']='这个花纹的没有哦' if expected=='不匹配' else '图上这款有，60片装'
            quote={'field':'匹配确认','value_json':json.dumps(value),'source_indexes':[0],
                   'image_files':[],'image_quote':'','conversion':''}
            self.assertEqual(analyze_replies.validate_quote(quote,record,ROOT)[0],expected)
            quote['value_json']=expected
            self.assertEqual(analyze_replies.validate_quote(quote,record,ROOT)[0],expected)

    def test_plain_supplier_text_is_accepted_but_numeric_fields_stay_json(self):
        record={'历史':[{'发送方':'对方','内容':'500包有现货，现货没有起订量','文件':[],'时间':'2026-10-14'}]}
        for field,value in [('现货','500包有现货'),('起订量','现货没有起订量')]:
            quote={'field':field,'value_json':value,'source_indexes':[0],
                   'image_files':[],'image_quote':'','conversion':''}
            self.assertEqual(analyze_replies.validate_quote(quote,record,ROOT)[0],value)
        quote['field']='阶梯价'
        with self.assertRaises(ValueError):analyze_replies.validate_quote(quote,record,ROOT)

    def test_structured_moq_keeps_evidence_without_guessing_piece_count(self):
        import runpy, tempfile
        import review_triage
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            batch=Path(folder)
            queue=[{'id':'X1','商品':[{'offerId':'123','商品链接':'https://detail.1688.com/offer/123.html'}],
                    '对应款':[{'序':1}]}]
            quote={'id':'X1','起订量':{'值':{'现货起订量包':1},'原话':'现货一包起订'},
                   '现货':{'值':'有货','原话':'有现货'}}
            for name,value in [('queue.json',queue),('核页规格匹配.json',[]),('candidates.json',{'1':[{'候选ID':'123'}]})]:
                (batch/name).write_text(json.dumps(value),encoding='utf8')
            (batch/'quotes.jsonl').write_text(json.dumps(quote),encoding='utf8')
            with patch.object(sys,'argv',['build_review_feed',str(batch),'--candidates',str(batch/'candidates.json')]), \
                 patch.object(review_triage,'triage',side_effect=lambda items,*args:items):
                runpy.run_path(str(ROOT/'tools/build_review_feed.py'),run_name='__main__')
            items=json.loads((batch/'review_feed.json').read_text(encoding='utf8'))['条目']
            self.assertFalse(any(i['字段']=='起订量' for i in items))
            self.assertTrue(any(i['字段']=='现货' for i in items))
            self.assertEqual(json.loads((batch/'quotes.jsonl').read_text(encoding='utf8')),quote)

    def test_missing_policy_denies_external_actions(self):
        with patch.object(port, 'permissions', return_value={}):
            for action in ('automatic','send','paid_search','review_push','github_push','deploy','notify'):
                with self.subTest(action=action), self.assertRaises(SystemExit):
                    port.require(action)

    def test_browser_send_and_chat_denied_before_subprocess(self):
        with patch.object(base, 'permissions', return_value={}), patch.object(port, 'permissions', return_value={}), \
             patch.object(base.subprocess, 'run') as child:
            for script, job in [('send.mjs',{}),('chat_read.mjs',{'ww':'not-approved'}),('chat_list.mjs',{})]:
                with self.assertRaises(SystemExit): base.browser(script, job)
            child.assert_not_called()

    def test_process_lock_excludes_then_releases(self):
        lock = ROOT.parent / 'temp/Xunpan_Windows适配_20261013/test.lock'
        code = ("import sys;sys.path.insert(0,sys.argv[1]);from port import file_lock;"
                "\ntry:\n with file_lock(sys.argv[2],blocking=False):print('acquired')"
                "\nexcept BlockingIOError:print('busy')")
        def child():
            return subprocess.check_output([sys.executable,'-c',code,str(ROOT/'tools/lib'),str(lock)],text=True).strip()
        with port.file_lock(lock): self.assertEqual(child(),'busy')
        self.assertEqual(child(),'acquired')
        lock.unlink()

    def test_plans_do_not_call_children(self):
        import importlib.util
        for filename,args in [('补资料/每日.py',['send','9']),('夜间/夜间.py',[])]:
            spec=importlib.util.spec_from_file_location('entry',ROOT/'tools'/filename)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with patch.object(sys,'argv',[filename,*args]),patch.object(module,'run') as child:
                module.main(); child.assert_not_called()

    def test_entries_refuse_automatic_run(self):
        import importlib.util
        for filename,args in [('补资料/每日.py',['send','9','--execute']),('夜间/夜间.py',['--execute','--now'])]:
            spec=importlib.util.spec_from_file_location('entry',ROOT/'tools'/filename)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with patch.object(sys,'argv',[filename,*args]),patch.object(port,'permissions',return_value={}), \
                 patch.object(module,'run') as child:
                with self.assertRaises(SystemExit): module.main()
                child.assert_not_called()

    def test_beijing_and_minimum_gap(self):
        self.assertEqual(base.now_bj().utcoffset().total_seconds(),8*3600)
        self.assertEqual(base.GAP_SECONDS,60)

    def test_quote_cannot_cite_our_question_as_supplier_fact(self):
        record={'历史':[{'发送方':'我方','内容':'是500个4元吗？','文件':[],'时间':'2026-10-13'}]}
        quote={'field':'阶梯价','value_json':'{"单价":4}','source_indexes':[0],
               'image_files':[],'image_quote':'','conversion':''}
        with self.assertRaises(ValueError):analyze_replies.validate_quote(quote,record,ROOT)

    def test_root_relative_image_resolves_to_same_supplier_evidence(self):
        batch=ROOT/'batches/补资料'
        photo='media/test/image.jpg'
        record={'历史':[{'发送方':'对方','内容':'见图','文件':[photo],'时间':'2026-10-13'}]}
        quote={'field':'包装尺寸毛重','value_json':'{"重量克":100}','source_indexes':[0],
               'image_files':['batches/补资料/'+photo],'image_quote':'100g','conversion':''}
        value=analyze_replies.validate_quote(quote,record,batch,{(batch/photo).resolve()})
        self.assertEqual(value[0]['重量克'],100)
        self.assertEqual(quote['image_files'],[photo])

    def test_queue_preserves_concurrent_other_field_and_rejects_conflict(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            batch=Path(folder);target=batch/'queue.json'
            target.write_text(json.dumps([{'id':'test','状态':'待发R1','备注':''}]),encoding='utf-8')
            local=base.load_queue(batch);local[0]['状态']='已发R1'
            target.write_text(json.dumps([{'id':'test','状态':'待发R1','备注':'另一进程补记'}]),encoding='utf-8')
            base.save_queue(batch,local)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))[0]['备注'],'另一进程补记')
            local=base.load_queue(batch);local[0]['状态']='已回'
            target.write_text(json.dumps([{'id':'test','状态':'不用发','备注':'另一进程补记'}]),encoding='utf-8')
            with self.assertRaises(RuntimeError):base.save_queue(batch,local)

    def test_unreadable_chat_is_retained_while_other_chats_are_processed(self):
        import importlib.util,tempfile
        from contextlib import nullcontext
        from datetime import datetime
        spec=importlib.util.spec_from_file_location('daily',ROOT/'tools/补资料/每日.py')
        daily=importlib.util.module_from_spec(spec);spec.loader.exec_module(daily)
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);(cache/'recovered_39_seeded').touch()
            pending={f'X{i}':f'新回复|X{i}|店铺' for i in range(1,7)}
            (cache/'pending_replies.json').write_text(json.dumps(pending),encoding='utf8')
            calls=[]
            def child(args,**kwargs):
                name=Path(args[1]).name
                if name=='chat.py':return '{"错误":"聊天页未完成收件人核验"}' if args[2]=='X1' else '聊天读取成功'
                if name=='analyze_replies.py':calls.extend(args[2:]);return '统计 新回复=4\n完成ID：X2,X3,X4,X5'
                return ''
            with patch.object(sys,'argv',['daily','read','15','--execute']),patch.object(daily,'CACHE',cache),\
                 patch.object(daily,'now_bj',return_value=datetime(2026,10,13,15,tzinfo=base.BJ)),\
                 patch.object(daily,'file_lock',return_value=nullcontext()),patch.object(daily,'require'),\
                 patch.object(daily,'notify'),patch.object(daily,'commit_paths'),patch.object(daily,'snapshot',return_value={'可续接':[]}),\
                 patch.object(daily,'find',return_value=(cache,{'对应款':[{'序':1}]})),\
                 patch.object(daily,'consume_decisions',return_value={'received':0}),patch.object(daily,'publish_tasks',return_value={'published':0}),\
                 patch.object(daily,'current_policy',return_value={'可询盘':[{'序':1}]}),patch.object(daily,'run',side_effect=child):
                daily.main()
            self.assertEqual(calls,['X2','X3','X4','X5'])
            self.assertEqual(list(json.loads((cache/'pending_replies.json').read_text())),['X6','X1'])

    def test_quote_upload_precedes_followup_and_failure_is_quarantined(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);commands=[];queue=[{'id':'X1','状态':'已发R1'}]
            record={'id':'X1','历史':[{'发送方':'对方','内容':'13元','文件':[],'时间':'2026-10-13T15:00:00+08:00'}]}
            result={'items':[{'id':'X1','needs_user':'','reply':'包装尺寸多少？','quotes':[{'field':'阶梯价','value_json':'{"单价":13}',
                'source_indexes':[0],'image_files':[],'image_quote':'','conversion':''}]}]}
            def analyze(prompt,output,*args,**kwargs):output.write_text(json.dumps(result),encoding='utf8')
            def child(args,**kwargs):
                name=Path(args[1]).name;commands.append(name)
                if name=='push_review_feed.py':return '{"新增":1}'
                if name=='reply.py':return '{"结果":"停止:未加载"}'
                return ''
            with patch.object(sys,'argv',['analyze','X1']),patch.object(analyze_replies,'CACHE',cache),\
                 patch.object(analyze_replies,'context',return_value=([record],[])),patch.object(analyze_replies,'codex',side_effect=analyze),\
                 patch.object(analyze_replies,'find',return_value=(cache,{'对应款':[{'规格':'目标款'}]})),patch.object(analyze_replies,'run',side_effect=child),\
                 patch.object(analyze_replies,'load_queue',return_value=queue),patch.object(analyze_replies,'save_queue'),\
                 patch.object(analyze_replies,'in_work_hours',return_value=True):
                analyze_replies.main()
            self.assertLess(commands.index('push_review_feed.py'),commands.index('reply.py'))
            self.assertEqual(queue[0]['状态'],'待人工核实')
            self.assertIn('回复暂停',queue[0])


if __name__=='__main__': unittest.main()
