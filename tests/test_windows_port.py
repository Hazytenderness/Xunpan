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
                 patch.object(daily,'notify'),patch.object(daily,'commit_paths'),\
                 patch.object(daily,'find',return_value=(cache,{'对应款':[{'序':1}]})),\
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
                 patch.object(analyze_replies,'find',return_value=(cache,{})),patch.object(analyze_replies,'run',side_effect=child),\
                 patch.object(analyze_replies,'load_queue',return_value=queue),patch.object(analyze_replies,'save_queue'),\
                 patch.object(analyze_replies,'in_work_hours',return_value=True):
                analyze_replies.main()
            self.assertLess(commands.index('push_review_feed.py'),commands.index('reply.py'))
            self.assertEqual(queue[0]['状态'],'待人工核实')
            self.assertIn('回复暂停',queue[0])


if __name__=='__main__': unittest.main()
