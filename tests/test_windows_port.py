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


if __name__=='__main__': unittest.main()
