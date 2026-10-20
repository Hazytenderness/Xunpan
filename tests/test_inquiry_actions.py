import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/lib'))
sys.path.insert(0,str(ROOT/'tools'))


class InquiryActionTests(unittest.TestCase):
    def fixture(self,root):
        batch=root/'batches/补资料';batch.mkdir(parents=True)
        entry={'id':'BZ0383','站':'jp','对应款':[{'序':2060,'asin':'B0H6L8NFWD','规格':'灰色针梳'}],'商品':[{'offerId':'743844801853','商品链接':'https://detail.1688.com/offer/743844801853.html'}],'页面卖家':'供应商','旺旺名':'seller','待决策':'包装选择','状态':'已回'}
        (batch/'queue.json').write_text(json.dumps([entry],ensure_ascii=False),encoding='utf-8')
        return batch,entry

    def test_decision_is_applied_once_and_existing_uncertain_pause_survives(self):
        import inquiry_actions as actions
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch,e=self.fixture(root);e['回复暂停']={'原因':'未知发送'};(batch/'queue.json').write_text(json.dumps([e]),encoding='utf-8');cache=root/'cache';cache.mkdir()
            task={'id':'jp-BZ0383-2060-743844801853','inquiryId':'BZ0383','product':{'cw':'CW2060','asin':'B0H6L8NFWD'},'supplier':{'offerId':'743844801853'},'sourceFingerprint':'x','decision':{'id':'opinion-1','action':'clarify','text':'先补两种包装尺寸','actor':'operator','sourceFingerprint':'x'}}
            calls=[]
            def api(method,path,data=None):
                if method=='GET':return {'tasks':[task]}
                calls.append(data);return {'好':True}
            with patch.object(actions,'api_request',side_effect=api):
                actions.consume_decisions(root,cache);actions.consume_decisions(root,cache)
            row=json.loads((batch/'queue.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(row['回复暂停'],{'原因':'未知发送'})
            self.assertEqual(row['人工处理意见']['id'],'opinion-1')
            self.assertEqual(json.loads((cache/'pending_replies.json').read_text(encoding='utf-8')).keys(),{'BZ0383'})
            self.assertEqual(len(calls),1)

    def test_changed_supplier_identity_does_not_apply_opinion(self):
        import inquiry_actions as actions
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch,_=self.fixture(root);cache=root/'cache';cache.mkdir()
            task={'id':'task','inquiryId':'BZ0383','product':{'cw':'CW2060','asin':'B0H6L8NFWD'},'supplier':{'offerId':'999'},'decision':{'id':'d','text':'意见','action':'clarify'}}
            with patch.object(actions,'api_request',return_value={'tasks':[task]}):actions.consume_decisions(root,cache)
            self.assertNotIn('人工处理意见',json.loads((batch/'queue.json').read_text(encoding='utf-8'))[0])

    def test_human_opinion_does_not_allow_unapproved_freeform_copy(self):
        from inquiry_workflow import allowed_reply
        entry={'对应款':[{'规格':'饲养箱'}],'人工处理意见':{'state':'queued','action':'continue','text':'需要金属网盖'}}
        self.assertFalse(allowed_reply(entry,'我们需要金属网盖，请确认能否提供。'))
        self.assertFalse(allowed_reply(entry,'我们同意下单，请发付款账号。'))
        self.assertFalse(allowed_reply(entry,'请分别报两个方案，先补资料，暂不确认方案或下单。'))
        self.assertEqual(allowed_reply(entry,'我们要的是饲养箱。'),'我们要的是饲养箱。')
        self.assertFalse(allowed_reply(entry,'暂不下单。请发付款账号。'))
        self.assertFalse(allowed_reply({'对应款':[{'规格':'饲养箱'}],'人工处理意见':{'state':'done','action':'continue'}},'我们需要金属网盖。'))

    def test_context_includes_human_opinion_for_cache_and_model(self):
        import analyze_replies as analyzer
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch,e=self.fixture(root);e['人工处理意见']={'id':'d','text':'先补资料','action':'clarify','state':'queued'};(batch/'chats').mkdir();(batch/'chats/743844801853.json').write_text('{"消息":[]}',encoding='utf-8')
            with patch.object(analyzer,'find',return_value=(batch,e)):
                records,_=analyzer.context(['BZ0383'])
            self.assertEqual(records[0]['人工处理意见']['id'],'d')

    def test_followup_chat_still_publishes_after_opinion_consumed(self):
        import inquiry_actions as actions
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch,e=self.fixture(root);cache=root/'cache';cache.mkdir()
            ident=actions.task_id(e,e['对应款'][0]);question=e.pop('待决策');e['人工处理意见']={'taskId':ident,'state':'done'}
            (batch/'queue.json').write_text(json.dumps([e]),encoding='utf-8');(batch/'chats').mkdir()
            (batch/'chats/743844801853.json').write_text(json.dumps({'消息':[{'发送方':'对方','内容':'新回复','时间':'now'}]}),encoding='utf-8')
            (cache/'inquiry_cloud_state.json').write_text(json.dumps({'tasks':[{'id':ident,'question':question}]}),encoding='utf-8')
            tasks=actions.build_tasks(root,cache,{'BZ0383'})
            self.assertEqual(tasks[0]['question'],question);self.assertEqual(tasks[0]['messages'][0]['text'],'新回复')

    def test_uncertain_send_gets_viewable_task_without_clearing_pause(self):
        import inquiry_actions as actions
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch,e=self.fixture(root);cache=root/'cache';cache.mkdir()
            e.pop('待决策');e['回复暂停']={'原因':'存在未核实发送意图'}
            (batch/'queue.json').write_text(json.dumps([e]),encoding='utf-8');(batch/'chats').mkdir();(batch/'chats/743844801853.json').write_text('{"消息":[]}',encoding='utf-8')
            tasks=actions.build_tasks(root,cache,{'BZ0383'})
            self.assertIn('请勿直接重发',tasks[0]['question']);self.assertEqual(json.loads((batch/'queue.json').read_text(encoding='utf-8'))[0]['回复暂停'],e['回复暂停'])


if __name__=='__main__':unittest.main()
