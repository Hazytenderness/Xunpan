import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/lib'))
from resilience import atomic_json, send_once, RetryLater, UnsafeOperation
from review_sync import enqueue, flush
from port import file_lock
from analysis_cache import analyze_cached


class ResilienceTests(unittest.TestCase):
    def test_site_sync_draft_defers_without_resend_or_uncertain_marker(self):
        from unittest.mock import Mock
        job={'ww':'fixture','offerId':'123','text':'原话'}
        call=Mock(return_value={'阶段':'准备','同步待确认':True,'错误':'网站同步待确认：quota','结果':'暂缓:网站同步待确认'})
        with self.assertRaisesRegex(RetryLater,'quota'):send_once(self.cache,job,call)
        self.assertEqual(call.call_count,1)
        records=list((self.cache/'send_ops').glob('*.json'))
        self.assertEqual(json.loads(records[0].read_text(encoding='utf-8'))['status'],'deferred')

    def test_site_sync_marker_cannot_hide_uncertain_supplier_effects(self):
        for effect in ({'阶段':'发送点击前','已点击发送':True},{'阶段':'准备','图已发':True}):
            with self.subTest(effect=effect):
                job={'ww':'fixture','offerId':str(len(list(self.cache.glob('send_ops/*.json')))),'text':'原话'}
                with self.assertRaises(UnsafeOperation):
                    send_once(self.cache,job,lambda _:{'同步待确认':True,'结果':'暂缓',**effect})

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=ROOT.parent/'temp')
        self.cache=Path(self.folder.name)
    def tearDown(self):
        self.folder.cleanup()

    def test_send_preparation_retries_but_receipt_survives_restart(self):
        calls=[]
        def attempt(job):
            calls.append(job)
            return {'结果':'停止:页面未加载','可重试':True} if len(calls)==1 else {'结果':'成功','发后新增条数':1}
        job={'ww':'fixture','offerId':'123','text':'原话'}
        with patch('resilience.time.sleep'):
            result=send_once(self.cache,job,attempt)
        self.assertEqual(result['结果'],'成功')
        self.assertEqual(len(calls),2)
        self.assertEqual(send_once(self.cache,job,lambda _:self.fail('不得二次发送'))['结果'],'成功')

    def test_uncertain_send_never_replays_after_process_crash(self):
        job={'ww':'fixture','offerId':'123','text':'原话'}
        def crash(_):raise RuntimeError('连接中断')
        with self.assertRaises(UnsafeOperation):send_once(self.cache,job,crash)
        with self.assertRaises(UnsafeOperation):send_once(self.cache,job,lambda _:self.fail('不得重发'))

    def test_matching_browser_success_receipt_recovers_without_resending(self):
        from resilience import fingerprint
        job={'ww':'fixture','offerId':'123','text':'原话','kind':'R1'}
        ident=fingerprint({k:job[k] for k in ('ww','offerId','text')})
        atomic_json(self.cache/'send_ops'/f'{ident}.json',{'status':'inflight','job':job})
        atomic_json(self.cache/'send.out.json',{'operation_id':ident,'结果':'成功','发后新增条数':1,
                                               '核对':{'收件人':True,'内容一致':True,'未误发':True}})
        result=send_once(self.cache,job,lambda _:self.fail('已有浏览器成功回执不得再发'))
        self.assertEqual(result['结果'],'成功')
        self.assertGreaterEqual(result['not_before']-result['sent_at'],120)
        self.assertLessEqual(result['not_before']-result['sent_at'],240)

    def test_invalid_model_shape_is_not_permanently_cached(self):
        records=[{'id':'X1','历史':['原话']}];calls=[]
        def invalid(rows):calls.append(rows);return {'items':[{'id':'X1','quotes':[],'reply':'x'*121,'needs_user':''}]}
        with self.assertRaises(ValueError):analyze_cached(self.cache,records,[],invalid)
        with self.assertRaises(ValueError):analyze_cached(self.cache,records,[],invalid)
        self.assertEqual(len(calls),2)

    def test_pending_merge_preserves_reply_added_by_another_scanner(self):
        from resilience import merge_pending
        before={'X1':'旧回复'}
        atomic_json(self.cache/'pending_replies.json',{'X1':'新增回复','X2':'另一扫描新发现'})
        self.assertEqual(merge_pending(self.cache,before,{}),{'X1':'新增回复','X2':'另一扫描新发现'})

    def test_image_checkpoint_survives_a_preparation_failure_next_day(self):
        job={'ww':'fixture','offerId':'123','text':'原话','img':'original.jpg'}
        with self.assertRaises(RetryLater):send_once(self.cache,job,lambda _:{'结果':'暂缓','图已发':True,'时段结束':True})
        seen=[]
        def temporary(operation):seen.append(operation);return {'结果':'暂缓','可重试':True}
        with self.assertRaises(RetryLater):send_once(self.cache,job,temporary,attempts=1)
        send_once(self.cache,job,lambda operation:(seen.append(operation) or {'结果':'成功'}))
        self.assertTrue(all('img' not in x for x in seen))

    def test_any_next_sender_recovers_previous_receipt_clock(self):
        from resilience import latest_send_times
        job={'ww':'fixture','offerId':'123','text':'原话','kind':'R1'}
        result=send_once(self.cache,job,lambda _:{'结果':'成功'})
        self.assertEqual(latest_send_times(self.cache),(result['sent_at'],result['not_before']))

    def test_risk_or_wrong_recipient_is_never_retried(self):
        calls=[]
        with self.assertRaises(UnsafeOperation):
            send_once(self.cache,{'ww':'fixture','offerId':'123','text':'原话'},
                      lambda job:(calls.append(job) or {'结果':'停止:收件人对不上'}))
        self.assertEqual(len(calls),1)

    def test_outbox_keeps_original_snapshot_and_retries_after_restart(self):
        feed={'站':'jp','批次':'fixture','条目':[{'字段':'采购单价','新值':51}]}
        ident=enqueue(self.cache,feed)
        feed['条目'][0]['新值']=99
        calls=[]
        def offline(body,station):
            calls.append(body)
            raise RetryLater('测试断网')
        result=flush(self.cache,transport=offline,attempts=1)
        self.assertEqual(result['待同步'],1)
        self.assertEqual(calls[0]['条目'][0]['新值'],51)
        done=flush(self.cache,transport=lambda body,station:{'新增':1,'未导入':[]},attempts=1)
        self.assertEqual(done['待同步'],0)
        self.assertEqual(done['新增'],1)
        self.assertTrue((self.cache/'review_outbox'/ident).exists())
        self.assertEqual(flush(self.cache,transport=lambda *_:self.fail('已完成不再推送'))['新增'],0)

    def test_business_rejection_is_retained_and_not_success(self):
        enqueue(self.cache,{'站':'jp','批次':'fixture','条目':[{}]})
        result=flush(self.cache,transport=lambda *_:{'新增':0,'未导入':[{'原因':'候选不匹配'}]},attempts=1)
        self.assertEqual(result['待同步'],1)
        self.assertTrue(result['需处理'])

    def test_atomic_write_preserves_previous_json_on_replace_failure(self):
        target=self.cache/'state.json'
        atomic_json(target,{'old':True})
        with patch('resilience.os.replace',side_effect=OSError('占用')):
            with self.assertRaises(OSError):atomic_json(target,{'new':True})
        self.assertEqual(json.loads(target.read_text()),{'old':True})
        self.assertEqual([p.name for p in self.cache.iterdir()],['state.json'])

    def test_lock_wait_is_bounded_and_next_attempt_can_acquire(self):
        import subprocess
        lock=self.cache/'busy.lock'
        code="import sys;sys.path.insert(0,sys.argv[1]);from port import file_lock;from resilience import RetryLater\ntry:\n with file_lock(sys.argv[2],timeout=.1):print('acquired')\nexcept RetryLater:print('deferred')"
        def child():return subprocess.check_output([sys.executable,'-c',code,str(ROOT/'tools/lib'),str(lock)],text=True).strip()
        with file_lock(lock):self.assertEqual(child(),'deferred')
        self.assertEqual(child(),'acquired')

    def test_ai_cached_until_supplier_text_or_image_changes(self):
        records=[{'id':'X1','历史':['商家报价51元']}];calls=[]
        image=self.cache/'image.jpg';image.write_bytes(b'original')
        def compute(rows):calls.append(rows);return {'items':[{'id':r['id'],'quotes':[],'reply':'','needs_user':''} for r in rows]}
        analyze_cached(self.cache,records,[image],compute)
        analyze_cached(self.cache,records,[image],compute)
        self.assertEqual(len(calls),1)
        image.write_bytes(b'updated')
        analyze_cached(self.cache,records,[image],compute)
        self.assertEqual(len(calls),2)
        records[0]['历史'].append('包装255克')
        analyze_cached(self.cache,records,[image],compute)
        self.assertEqual(len(calls),3)

    def test_temporary_failures_alert_once_after_threshold_and_recovery_once(self):
        sys.path.insert(0,str(ROOT/'tools'))
        from scheduled import report_health
        alerts=[]
        for _ in range(5):report_health(self.cache,'read','deferred','网络暂不可用',alerts.append)
        self.assertEqual(len(alerts),1)
        report_health(self.cache,'read','ok','',alerts.append)
        report_health(self.cache,'read','ok','',alerts.append)
        self.assertEqual(len(alerts),2)

    def test_child_timeout_is_recoverable_and_releases_process(self):
        from port import captured
        with self.assertRaises(RetryLater):
            captured([sys.executable,'-c','import time;time.sleep(30)'],text=True,encoding='utf8',timeout=.1)

if __name__=='__main__':unittest.main()
