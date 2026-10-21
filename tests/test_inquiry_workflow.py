import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lib'))
import inquiry_workflow as w


def fact(value):
    return {'值': value, '原话': '商家原话'}


class InquiryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.entry = {'id': 'X1', '对应款': [{'规格': '白色18cm宽四层带轮推车', 'asin': 'A', '序': 1}]}

    def test_first_message_preserves_user_exact_copy_and_full_specs(self):
        self.assertEqual(w.first_message(self.entry), '图上这款有吗？我们要的是白色18cm宽四层带轮推车。单个包装尺寸多少？重量多少？订500件多少钱')

    def test_supplier_yes_is_sufficient_no_repeated_spec_question(self):
        q = {'匹配确认': fact('完全匹配')}
        p = w.next_step(self.entry, q)
        self.assertEqual(p['阶段'], '补包装')
        self.assertEqual(p['话术'], '单个包装尺寸多少？重量多少？')

    def test_priority_two_continues_even_if_price_was_already_obtained(self):
        q = {'匹配确认': fact('完全匹配'), '包装尺寸毛重': fact({'长': 10, '宽': 20, '高': 30, '重量克': 500}), '阶梯价': fact({'单价': 8})}
        p = w.next_step(self.entry, q)
        self.assertEqual(p['阶段'], '补贴标等资料')
        self.assertEqual(p['话术'], '怎么包装的？这款能发中性包装吗？能帮忙贴标吗？一箱装多少个？')

    def test_cannot_label_does_not_drop_or_stop_collecting(self):
        q = {'匹配确认': fact('完全匹配'), '包装尺寸毛重': fact({'长': 10, '宽': 20, '高': 30, '重量克': 500}), '贴标': fact('不能贴')}
        p = w.next_step(self.entry, q)
        self.assertEqual(p['贴标'], '不能贴')
        self.assertIn('中性包装', p['话术'])
        self.assertNotIn('贴标', p['话术'])
        self.assertNotIn('不做', p.values())

    def test_third_priority_no_label_detail_question(self):
        q = {'匹配确认': fact('完全匹配'), '包装尺寸毛重': fact({'长': 10, '宽': 20, '高': 30, '重量克': 500}), '贴标': fact('能贴'), '中性包装': fact('不能提供'), '每箱数量': fact(12)}
        q['包装方式'] = fact('袋装')
        p = w.next_step(self.entry, q)
        self.assertEqual(p['话术'], '这款实拍图和视频发下，订500件多少钱？')

    def test_product_size_cannot_satisfy_packaging_requirement(self):
        q = {'匹配确认': fact('完全匹配'), '包装尺寸毛重': {'值': {'长': 10, '宽': 20, '高': 30, '重量克': 500}, '原话': '产品尺寸，非包装'}}
        self.assertEqual(w.next_step(self.entry, q)['阶段'], '补包装')

    def test_repeated_question_closes_to_verification_instead_of_endless_resend(self):
        p = w.next_step(self.entry, {}, sent=[{'文本': '图上这款有吗？'}, {'文本': '图上这款有吗？'}])
        self.assertEqual(p['阶段'], '待核实')
        self.assertEqual(p['话术'], '')

    def test_complete_does_not_require_positive_label_answer(self):
        q = {'匹配确认': fact('完全匹配'), '包装尺寸毛重': fact({'长': 10, '宽': 20, '高': 30, '重量克': 500}), '贴标': fact('不能贴'), '中性包装': fact('可以'), '每箱数量': fact(12), '实拍图': fact('无'), '视频': fact('无'), '阶梯价': fact({'单价': 8})}
        q['包装方式'] = fact('袋装')
        p = w.next_step(self.entry, q)
        self.assertEqual(p['阶段'], '资料收集完成')
        self.assertEqual(p['话术'], '')

    def test_explicit_no_matching_product_closes(self):
        self.assertEqual(w.next_step(self.entry, {'匹配确认': fact('不匹配')})['阶段'], '不匹配结束')

    def test_pack_quantity_is_not_silently_discarded(self):
        self.entry['对应款'][0]['规格'] = '浴巾110×50cm，炭灰色，2条装'
        self.assertIn('2条装的一套包装尺寸多少？重量多少？订500件多少钱', w.first_message(self.entry))

    def test_explicit_set_and_other_pack_units(self):
        for spec,expected in [('蓝色2件套','2件装的一套'),('2只装','2只装的一套'),('10张装','10张装的一套')]:
            self.entry['对应款'][0]['规格']=spec
            self.assertIn(expected,w.first_message(self.entry))

    def test_first_message_and_split_question_share_the_same_missing_field_limit(self):
        q={'匹配确认':fact('完全匹配')}
        sent=[{'文本':w.first_message(self.entry)},{'文本':'单个包装尺寸多少？重量多少？'}]
        self.assertEqual(w.next_step(self.entry,q,sent)['阶段'],'待核实')

    def test_shipping_answer_punctuation_and_unit_clarification_are_allowed(self):
        self.assertEqual(w.allowed_reply(self.entry,'发义乌。'),'发义乌。')
        self.assertEqual(w.allowed_reply(self.entry,'这个价是单个的，还是单个的？'),'这个价是单个的，还是单个的？')
        self.assertIsNone(w.allowed_reply(self.entry,'好的，500件就这样下单了'))

    def test_packaging_method_can_follow_dimensions_before_weight(self):
        q={'匹配确认':fact('完全匹配'),'包装尺寸毛重':fact({'长':10,'宽':20,'高':30})}
        self.assertEqual(w.next_step(self.entry,q)['话术'],'单个带包装重量多少？怎么包装的？')

    def test_volunteered_packaging_method_is_not_asked_again(self):
        q={'匹配确认':fact('完全匹配'),'包装尺寸毛重':fact({'长':10,'宽':20,'高':30,'重量克':500}),
           '包装方式':fact('单个OPP袋装')}
        p=w.next_step(self.entry,q)
        self.assertNotIn('怎么包装的',p['话术'])
        self.assertIn('中性包装',p['话术'])

    def test_packaging_method_respects_two_question_limit(self):
        q={'匹配确认':fact('完全匹配'),'包装尺寸毛重':fact({'长':10,'宽':20,'高':30,'重量克':500})}
        p=w.next_step(self.entry,q,[{'文本':'怎么包装的？'},{'文本':'怎么包装的？能帮忙贴标吗？'}])
        self.assertEqual(p['阶段'],'待核实')

    def test_custom_target_asks_moq_even_when_no_stock(self):
        q={'定制款':fact(True),'现货':fact('无货')}
        self.assertEqual(w.next_step(self.entry,q)['话术'],'定制款的起订量是多少？')

    def test_custom_moq_at_most_fifty_can_continue_without_stock(self):
        for quantity in (49,50):
            with self.subTest(quantity=quantity):
                q={'定制款':fact(True),'定制起订量':fact({'数量':quantity,'单位':'件'}),
                   '现货':fact('无货'),'匹配确认':fact('完全匹配')}
                p=w.next_step(self.entry,q)
                self.assertEqual(p['阶段'],'补包装')
                self.assertIs(p['定制可继续'],True)

    def test_custom_moq_above_fifty_asks_similar_stock(self):
        q={'定制款':fact(True),'定制起订量':fact({'数量':51,'单位':'件'})}
        self.assertEqual(w.next_step(self.entry,q)['话术'],'有没有类似款，有现货的？')

    def test_custom_moq_cartons_or_bundle_scope_needs_clarification(self):
        q={'定制款':fact(True),'定制起订量':fact({'数量':10,'单位':'箱'})}
        self.assertEqual(w.next_step(self.entry,q)['话术'],'这个起订量是按单个算的吗？')
        self.entry['对应款'][0]['规格']='白色毛巾2条装'
        q['定制起订量']=fact({'数量':50,'单位':'条'})
        self.assertEqual(w.next_step(self.entry,q)['话术'],'这个起订量是按2条装的一套算的吗？')

    def test_optional_customization_does_not_trigger_custom_target_branch(self):
        q={'定制':fact('支持尺寸定制'),'匹配确认':fact('完全匹配')}
        self.assertEqual(w.next_step(self.entry,q)['阶段'],'补包装')

    def test_similar_stock_reply_is_reviewed_instead_of_reasked_or_accepted(self):
        q={'定制款':fact(True),'定制起订量':fact({'数量':100,'单位':'件'})}
        history=[{'发送方':'我方','内容':'有没有类似款，有现货的？'},
                 {'发送方':'对方','内容':'有，看看这款'}]
        p=w.response_step(self.entry,q,[],history)
        self.assertEqual(p['阶段'],'待核实')
        self.assertEqual(p['话术'],'')

    def test_old_saved_rules_require_reanalysis_even_with_only_a_new_greeting(self):
        history=[{'发送方':'对方','内容':'OPP袋装'}, {'发送方':'我方','内容':'谢谢'}, {'发送方':'对方','内容':'你好'}]
        self.assertTrue(w.requires_fact_analysis(history,'2026-10-20-unified-copy-1'))
        self.assertFalse(w.requires_fact_analysis(history,w.VERSION))
