import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lib'))
import resilience as r
import inquiry_workflow as w


class RecoveryTests(unittest.TestCase):
    def test_recent_measurement_request_waits_when_supplier_has_no_data(self):
        now=datetime.now(timezone.utc)
        history=[{'发送方':'我方','内容':'请仓库量尺、称重，给单个包装长宽高和重量。','时间':(now-timedelta(minutes=45)).isoformat()},
                 {'发送方':'对方','内容':'没有具体数据','时间':now.isoformat()}]
        flow=w.response_step({'对应款':[{'规格':'灰色地毯'}]}, {}, [], history)
        self.assertEqual(flow['阶段'],'等商家测量')
        self.assertEqual(flow['话术'],'')
        self.assertGreater(datetime.fromisoformat(flow['下次核查时间']),now)
        history[0]['时间']=(now-timedelta(hours=25)).isoformat()
        self.assertIn('尺',w.response_step({'对应款':[{'规格':'灰色地毯'}]}, {}, [], history)['话术'])

    def test_new_tax_question_is_not_hidden_by_measurement_wait(self):
        history=[{'发送方':'我方','内容':'请量尺称重，单个包装长宽高和重量。','时间':datetime.now(timezone.utc).isoformat()},
                 {'发送方':'对方','内容':'没有具体数据，含税还是不含税'}]
        self.assertIn('不含税',w.response_step({'对应款':[{'规格':'灰色'}]}, {}, [], history)['话术'])

    def test_missing_measurement_time_requires_receipt_check_not_endless_wait(self):
        history=[{'发送方':'我方','内容':'请量尺称重，给单个包装数据。'}, {'发送方':'对方','内容':'没有具体数据'}]
        flow=w.response_step({'对应款':[{'规格':'灰色'}]}, {}, [], history)
        self.assertEqual(flow['阶段'],'待核发送时间')
        self.assertIn('发送日志',flow['原因'])
        sent=[{'结果':'成功','文本':history[0]['内容'],'时间':datetime.now(timezone.utc).isoformat()}]
        flow=w.response_step({'对应款':[{'规格':'灰色'}]}, {}, sent, history)
        self.assertEqual(flow['阶段'],'等商家测量')
        self.assertIsNotNone(flow['下次核查时间'])

    def test_missing_time_remains_in_backlog_for_fresh_chat_recovery(self):
        from workflow_backlog import snapshot
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);batch=root/'batches/b';batch.mkdir(parents=True);cache=root/'cache';cache.mkdir()
            entry={'id':'X1','站':'jp','状态':'已回','对应款':[{'规格':'灰色','序':1}],'商品':[{'offerId':'1'}]}
            r.atomic_json(batch/'queue.json',[entry])
            (batch/'sent_log.jsonl').write_text(json.dumps({'id':'X1','结果':'成功','文本':'更早的问题','时间':datetime.now(timezone.utc).isoformat()})+'\n',encoding='utf-8')
            r.atomic_json(batch/'chats/1.json',{'消息':[{'发送方':'我方','内容':'请量尺称重，给单个包装数据。'}, {'发送方':'对方','内容':'没有具体数据'}]})
            plan=snapshot(root,cache,datetime.now(timezone.utc))
            self.assertEqual(plan['条目'][0]['阶段'],'待核发送时间')
            self.assertIn('X1',plan['可续接'])

    def test_positive_receipt_restores_only_matching_sender_failure(self):
        row={'旺旺名':'A','商品':[{'offerId':'1'}],'对应款':[{'序':24}],
             '状态':'待人工核实','回复暂停':{'原因':'发送连接中断，结果待核实'}}
        job={'ww':'A','offerId':'1','seqs':[24],'text':'问题'}
        self.assertFalse(r.restore_queue_entry(row,{**job,'offerId':'2'},{},'op'))
        proof={'结果':'成功','核对':{'收件人':True,'内容一致':True,'未误发':True}}
        self.assertTrue(r.restore_queue_entry(row,job,proof,'op'))
        self.assertEqual(row['状态'],'已回');self.assertNotIn('回复暂停',row)
        self.assertEqual(row['发送恢复记录'][0]['operation_id'],'op')
        row['回复暂停']={'原因':'人工指定暂停：发送连接中断，结果待核实'}
        self.assertFalse(r.restore_queue_entry(row,job,{},'op'))
    def test_new_facts_require_analysis_not_cached_quotes(self):
        for message in ('有的，带包装20×15×5cm，100g','没有一样的花形','这个有','只有蓝色'):
            self.assertTrue(w.requires_fact_analysis([{'发送方':'对方','内容':message}]))
        self.assertFalse(w.requires_fact_analysis([{'发送方':'对方','内容':'你好'},{'发送方':'对方','内容':'含税运吗？'}]))

    def test_chat_changed_before_click_is_deferred_not_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder)
            result=r.send_once(cache,{'ww':'A','offerId':'1','text':'问题'},lambda _:{
                '结果':'暂缓:聊天变化','需重读':True,'已点击发送':False,'图已发':True})
            self.assertTrue(result['需重读'])
            state=json.loads(next((cache/'send_ops').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(state['status'],'deferred')
            self.assertTrue(state['image_sent'])

    def test_deferred_owned_draft_is_passed_to_new_analysis_text(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);job={'ww':'A','offerId':'1','text':'旧问题'}
            r.send_once(cache,job,lambda _:{'结果':'暂缓','需重读':True,'已点击发送':False,'自有草稿':'旧问题'})
            calls=[]
            r.send_once(cache,{**job,'text':'新问题'},lambda j:(calls.append(j) or {'结果':'成功'}))
            self.assertEqual(calls[0]['owned_draft'],'旧问题')

    def test_matching_enum_object_still_requires_real_supplier_evidence(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from analyze_replies import validate_quote
        q={'field':'匹配确认','value_json':'{"匹配":"不匹配","原话":"没有一样的花形"}',
           'source_indexes':[0],'image_files':[],'image_quote':'','conversion':''}
        record={'历史':[{'发送方':'对方','内容':'没有一样的花形','文件':[],'时间':'2026-10-20T14:30:06+08:00'}]}
        self.assertEqual(validate_quote(q,record,Path('.'))[0],'不匹配')
        q['source_indexes']=[]
        with self.assertRaises(ValueError):validate_quote(q,record,Path('.'))
    def test_legacy_global_unknown_pause_scopes_but_risk_pause_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder)
            r.atomic_json(cache/'send_ops/a.json',{'status':'uncertain','job':{'ww':'A'},'time':1})
            r.atomic_json(cache/'send_paused.json',{'原因':'存在未核实发送意图，不自动重发'})
            self.assertFalse(r.global_send_pause(cache))
            r.atomic_json(cache/'send_ops/a.json',{'status':'success'})
            self.assertFalse(r.global_send_pause(cache))
            r.atomic_json(cache/'send_paused.json',{'原因':'收件人不匹配'})
            self.assertTrue(r.global_send_pause(cache))

    def test_failed_recovery_keeps_original_unknown_and_never_sends(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);job={'ww':'A','offerId':'1','text':'问题'}
            with self.assertRaises(r.UnsafeOperation):
                r.send_once(cache,job,lambda _:(_ for _ in ()).throw(RuntimeError()))
            target=next((cache/'send_ops').glob('*.json'));before=target.read_bytes()
            with self.assertRaises(r.UnsafeOperation):
                r.send_once(cache,job,lambda _:self.fail('不得发'),recover=lambda _:{'结果':'未找到'})
            self.assertEqual(target.read_bytes(),before)

    def test_unresolved_receipt_blocks_same_supplier_but_not_other_suppliers(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            old = {'ww': 'A', 'offerId': '1', 'text': '旧问题'}
            with self.assertRaises(r.UnsafeOperation):
                r.send_once(cache, old, lambda _: (_ for _ in ()).throw(RuntimeError()))
            r.latest_send_times(cache)
            with self.assertRaises(r.UnsafeOperation):
                r.send_once(cache, {**old, 'text': '新问题'}, lambda _: self.fail('不能绕开未知回执'))
            self.assertEqual(r.send_once(cache, {**old, 'ww': 'B'}, lambda _: {'结果': '成功'})['结果'], '成功')

    def test_positive_live_receipt_recovers_without_new_send(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            job = {'ww': 'A', 'offerId': '1', 'text': '问题'}
            with self.assertRaises(r.UnsafeOperation):
                r.send_once(cache, job, lambda _: (_ for _ in ()).throw(RuntimeError()))
            def recover(probe):
                self.assertTrue(probe['recover_only'])
                return {'结果': '成功', '回执恢复': True, 'operation_id': probe['operation_id'],
                        '核对': {'收件人': True, '内容一致': True, '未误发': True},
                        'sent_at': probe['intent_time'] + 1}
            result = r.send_once(cache, job, lambda _: self.fail('恢复不得重发'), recover=recover)
            self.assertTrue(result['回执恢复'])
            state = json.loads(next((cache/'send_ops').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(state['job']['ww'], 'A')
            self.assertEqual(state['previous']['status'], 'uncertain')

    def test_packaging_is_complete_without_extras(self):
        entry = {'对应款': [{'规格': '白色2个装'}]}
        q = {'匹配确认': {'值': '完全匹配'}, '包装尺寸毛重': {'值': {'长': 10, '宽': 20, '高': 3, '重量克': 80}}}
        self.assertEqual(w.next_step(entry, q)['阶段'], '资料收集完成')

    def test_two_questions_do_not_permanently_stop_packaging(self):
        entry = {'对应款': [{'规格': '白色2个装'}]}
        q = {'匹配确认': {'值': '完全匹配'}}
        sent = [{'文本': '2个装的一套包装尺寸多少？重量多少？'}] * 2
        self.assertEqual(w.next_step(entry, q, sent)['阶段'], '补包装')

    def test_measurement_reply_and_tax_question_are_actionable(self):
        entry = {'对应款': [{'规格': '白色2个装'}]}
        q = {'匹配确认': {'值': '完全匹配'}}
        history = [{'发送方': '对方', '内容': '没测量过'}]
        self.assertIn('尺', w.response_step(entry, q, [], history)['话术'])
        history = [{'发送方': '对方', '内容': '含税吗发哪里'}, {'发送方': '系统', '内容': '商品卡片'}]
        self.assertIn('义乌', w.response_step(entry, q, [], history)['话术'])
        self.assertIn('不含税', w.response_step(entry, q, [], history)['话术'])

    def test_supplier_wait_does_not_trigger_immediate_followup(self):
        entry = {'对应款': [{'规格': '白色'}]}
        flow = w.response_step(entry, {'匹配确认': {'值': '完全匹配'}}, [], [{'发送方': '对方', '内容': '稍等我量一下'}])
        self.assertEqual(flow['话术'], '')
        self.assertEqual(flow['阶段'], '等商家测量')

    def test_old_wait_is_resumed_once_and_latest_outbound_then_waits(self):
        entry={'对应款':[{'规格':'白色'}]}
        history=[{'发送方':'对方','内容':'稍等','时间':'2026-01-01T10:00:00+08:00'}]
        flow=w.response_step(entry,{},[],history)
        self.assertIn('称重',flow['话术'])
        history.append({'发送方':'我方','内容':flow['话术']})
        self.assertEqual(w.response_step(entry,{},[],history)['话术'],'')
