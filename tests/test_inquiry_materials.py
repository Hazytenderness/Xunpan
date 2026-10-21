import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import analyze_replies as analyzer
from send_policy import validate_job
from inquiry_workflow import next_step


class InquiryMaterialsTests(unittest.TestCase):
    def quote(self,field,value):
        return {'field':field,'value_json':json.dumps(value,ensure_ascii=False),'source_indexes':[0],
                'image_files':[],'image_quote':'','conversion':''}

    def validate(self,field,value,text):
        record={'历史':[{'发送方':'对方','内容':text,'文件':[],'时间':'2026-10-21T15:00:00+08:00'}]}
        return analyzer.validate_quote(self.quote(field,value),record,ROOT/'batches/test')

    def test_packaging_method_preserves_supplier_evidence(self):
        result=self.validate('包装方式','OPP袋装','单个OPP袋装的')
        self.assertEqual(result[:2],['OPP袋装','单个OPP袋装的'])
        with self.assertRaises(ValueError):self.validate('包装方式','','不知道')

    def test_target_customization_is_a_boolean_not_optional_capability_text(self):
        self.assertIs(self.validate('定制款',True,'这款需要定制')[0],True)
        with self.assertRaises(ValueError):self.validate('定制款','支持颜色定制','支持颜色定制')

    def test_custom_moq_requires_positive_integer_and_explicit_unit(self):
        self.assertEqual(self.validate('定制起订量',{'数量':50,'单位':'件'},'这款定制50件起订')[0],{'数量':50,'单位':'件'})
        for value in ({'数量':True,'单位':'件'},{'数量':0,'单位':'件'},{'数量':50,'单位':''},50):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.validate('定制起订量',value,'定制50件起订')

    def test_analysis_schema_and_runtime_field_allowlist_agree(self):
        schema=json.loads((ROOT/'tools/reply_analysis.schema.json').read_text(encoding='utf-8'))
        fields=schema['properties']['items']['items']['properties']['quotes']['items']['properties']['field']['enum']
        self.assertEqual(set(fields),analyzer.FIELDS)

    def test_new_questions_pass_final_policy_but_redundant_or_wrong_branch_does_not(self):
        entry={'id':'T1','旺旺名':'测试商家','商品':[{'offerId':'1'}],'对应款':[{'序':1,'规格':'白色推车'}]}
        fact=lambda v:{'值':v,'原话':'商家原话'}
        cases=[({'匹配确认':fact('完全匹配'),'包装尺寸毛重':fact({'长':10,'宽':20,'高':30,'重量克':500})},'怎么包装的？'),
               ({'定制款':fact(True)},'定制款的起订量是多少？'),
               ({'定制款':fact(True),'定制起订量':fact({'数量':51,'单位':'件'})},'有没有类似款，有现货的？')]
        with tempfile.TemporaryDirectory(dir=ROOT.parent/'temp') as folder:
            root=Path(folder);batch=root/'batches/test';batch.mkdir(parents=True)
            (batch/'queue.json').write_text(json.dumps([entry]),encoding='utf-8')
            for quotes,phrase in cases:
                with self.subTest(phrase=phrase):
                    (batch/'quotes.jsonl').write_text(json.dumps({'id':'T1',**quotes}),encoding='utf-8')
                    text=next_step(entry,quotes)['话术']
                    self.assertIn(phrase,text)
                    job={'ww':'测试商家','offerId':'1','kind':'回复','text':text}
                    self.assertEqual(validate_job(root,job),'T1')
                    with self.assertRaises(ValueError):validate_job(root,{**job,'text':'好的，就这样下单。'})
            quotes={'匹配确认':fact('完全匹配'),'包装尺寸毛重':fact({'长':10,'宽':20,'高':30,'重量克':500}),'包装方式':fact('OPP袋装')}
            (batch/'quotes.jsonl').write_text(json.dumps({'id':'T1',**quotes}),encoding='utf-8')
            with self.assertRaises(ValueError):validate_job(root,{'ww':'测试商家','offerId':'1','kind':'回复','text':'怎么包装的？'})
