import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/lib'))


class InquiryReportingTests(unittest.TestCase):
    def test_empty_feed_does_not_create_a_permanent_sync_failure(self):
        from review_sync import enqueue
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder)
            self.assertIsNone(enqueue(cache,{'批次':'empty','站':'jp','条目':[]}))
            self.assertEqual(list((cache/'review_outbox').glob('*.json')),[])

    def test_repeated_stop_is_quiet_but_new_problem_still_notifies(self):
        from inquiry_reporting import notify_once
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);send=Mock()
            self.assertTrue(notify_once(cache,'补资料 17:22\n⚠ 跟进暂停：BZ0001：存在未核实发送意图',send))
            self.assertTrue(notify_once(cache,'补资料 17:32\n⚠ 跟进暂停：BZ0001：存在未核实发送意图',send))
            self.assertEqual(send.call_count,1)
            notify_once(cache,'补资料 17:42\n⚠ 跟进暂停：BZ0002：存在未核实发送意图',send)
            self.assertEqual(send.call_count,2)

    def test_unsent_notice_is_not_marked_delivered(self):
        from inquiry_reporting import notify_once
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder)
            with self.assertRaises(RuntimeError):notify_once(cache,'⚠ 同步故障',Mock(side_effect=RuntimeError('offline')))
            send=Mock();notify_once(cache,'⚠ 同步故障',send);send.assert_called_once()

    def test_legacy_sync_warning_is_adopted_without_repeat(self):
        from inquiry_reporting import notify_once
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            cache=Path(folder);(cache/'review_sync_attention.json').write_text('["old issue"]',encoding='utf-8')
            send=Mock();notify_once(cache,'⚠ 网站报价同步有权限或业务拒绝项，需要核对本机日志；其他采集继续。',send)
            send.assert_not_called()

    def test_identifies_each_supplier_with_website_cw_and_asin(self):
        from inquiry_reporting import humanize_line, identity_index
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch=root/'batches/补资料';batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([{'id':'BZ0606','页面卖家':'供应商甲','商品':[{'offerId':'1','商品链接':'https://detail.1688.com/offer/1.html'}],'对应款':[{'序':2345,'asin':'B012345678','规格':'五档花洒带软管'}]}],ensure_ascii=False),encoding='utf-8')
            line=humanize_line('要你定：BZ0606：报价含义不明',identity_index(root))
            for text in ['CW2345','B012345678','五档花洒带软管','供应商甲','BZ0606']:self.assertIn(text,line)
            self.assertEqual(humanize_line('系统同步问题',{}),'系统同步问题')

    def test_media_positive_text_resolves_only_same_message_image(self):
        from review_evidence import media_values
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            batch=Path(folder);(batch/'chats').mkdir()
            chat={'消息':[{'发送方':'我方','时间':'2026-10-20T10:00:00+08:00','图片':['https://img.example/target.jpg']},{'发送方':'对方','时间':'2026-10-20T10:01:00+08:00','图片':['https://img.example/other.jpg']},{'发送方':'对方','时间':'2026-10-20T10:02:00+08:00','图片':['https://img.example/real.jpg']}]}
            (batch/'chats/123.json').write_text(json.dumps(chat),encoding='utf-8')
            fact={'值':'已提供','时间':'2026-10-20T10:02:00+08:00','原话':'见图 media\\123\\20261020T100200_0.jpg'}
            self.assertEqual(media_values(fact,batch,'123','实拍图'),['https://img.example/real.jpg'])
            self.assertEqual(media_values({'值':{'有':True},'原话':'有'},batch,'123','实拍图'),[])
            self.assertEqual(media_values({'值':'无'},batch,'123','实拍图'),['无'])

    def test_media_archive_and_url_lists_are_not_stringified(self):
        from review_evidence import media_values
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            batch=Path(folder);(batch/'media/123').mkdir(parents=True);(batch/'media/123/a.jpg').write_bytes(b'fixture')
            self.assertEqual(media_values({'值':['media\\123\\a.jpg']},batch,'123','实拍图'),['media/123/a.jpg'])
            self.assertEqual(media_values({'值':'https://user:secret@invalid.example/a.jpg'},batch,'123','实拍图'),[])


if __name__=='__main__':unittest.main()
