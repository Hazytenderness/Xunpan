import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/lib'))
import inquiry_workflow as workflow


class SendPolicyTests(unittest.TestCase):
    def setUp(self):
        self.entry = {'id': 'T1', '旺旺名': 'supplier', '商品': [{'offerId': '123'}],
                      '对应款': [{'规格': '剑麻鱼，2个装', '序': 1, 'asin': 'A'}]}

    def test_screenshot_style_is_rejected_even_with_human_opinion(self):
        self.entry['人工处理意见'] = {'state': 'queued', 'action': 'continue', 'text': '补包装资料'}
        self.assertIsNone(workflow.allowed_reply(self.entry, '您好，询问链接123的剑麻鱼，普通OPP袋即可，仅作询价。'))

    def test_only_exact_first_message_is_allowed_for_first_round(self):
        from send_policy import validate_job
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root = Path(folder); batch = root/'batches/test'; batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([self.entry]), encoding='utf-8')
            job = {'ww': 'supplier', 'offerId': '123', 'kind': 'R1', 'text': workflow.first_message(self.entry)}
            self.assertEqual(validate_job(root, job), self.entry['id'])
            for text in ['您好，' + job['text'], '能帮忙贴标吗？']:
                with self.assertRaises(ValueError): validate_job(root, {**job, 'text': text})

    def test_missing_identity_and_unapproved_free_text_stop_before_browser(self):
        from send_policy import validate_job
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root = Path(folder); batch = root/'batches/test'; batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([self.entry]), encoding='utf-8')
            for job in [{'ww':'other','offerId':'123','text':'能帮忙贴标吗？'},
                        {'ww':'supplier','offerId':'123','text':'普通OPP袋即可，仅作询价。'}]:
                with self.assertRaises(ValueError): validate_job(root, job)

    def test_current_missing_fields_and_approved_clarifications_pass(self):
        from send_policy import validate_job
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder); batch=root/'batches/test'; batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([self.entry]),encoding='utf-8')
            for text in ['图上这款有吗？', '发义乌。']:
                self.assertEqual(validate_job(root,{'ww':'supplier','offerId':'123','text':text}),'T1')
            with self.assertRaises(ValueError):
                validate_job(root,{'ww':'supplier','offerId':'123','text':'能帮忙贴标吗？'})

    def test_legacy_wording_can_only_be_reconciled_without_sending(self):
        from send_policy import validate_job
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch=root/'batches/test';batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([self.entry]),encoding='utf-8')
            job={'ww':'supplier','offerId':'123','text':'旧版未确认文案'}
            with self.assertRaises(ValueError):validate_job(root,job)
            self.assertEqual(validate_job(root,{**job,'recover_only':True}),'T1')
