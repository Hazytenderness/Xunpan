import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class SkuHandoffTests(unittest.TestCase):
 def fixture(self,root):
  work=root/'work';batch=root/'batches/new';work.mkdir();batch.parent.mkdir()
  p={'序':1,'asin':'B011111111','名':'测试','细类':'测试','货源候选':[{'候选ID':'11','商品链接':'https://detail.1688.com/offer/11.html'}]}
  (work/'products.json').write_text(json.dumps([p]),encoding='utf-8');(work/'purchase.json').write_text(json.dumps({'行':{}}),encoding='utf-8')
  return work,batch,p
 def run_script(self,name,root,work,batch):
  return subprocess.run([sys.executable,str(ROOT/'tools/核SKU'/name),str(batch)],cwd=root,env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','XUNPAN_WORK':str(work),'XUNPAN_BATCH':str(batch)},capture_output=True,text=True,encoding='utf-8')
 def test_previous_review_feed_and_cloud_review_do_not_mean_sku_verified(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);work,batch,p=self.fixture(root);old=root/'batches/old';old.mkdir();(old/'review_feed.json').write_text(json.dumps({'条目':[{'序':1,'候选ID':'11'}]}));(work/'purchase.json').write_text(json.dumps({'行':{'1':{'复核':{'old':{'候选ID':'11'}}}}}))
   r=self.run_script('建批次.py',root,work,batch);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(json.loads((batch/'queue.json').read_text(encoding='utf-8'))),1)
 def test_current_terminal_match_skips_candidate(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);work,batch,p=self.fixture(root);p['货源候选'][0]['匹配度']={'等级':'完全匹配'};(work/'products.json').write_text(json.dumps([p]))
   r=self.run_script('建批次.py',root,work,batch);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads((batch/'queue.json').read_text(encoding='utf-8')),[])
 def test_existing_batch_is_never_overwritten_on_restart(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);work,batch,p=self.fixture(root);batch.mkdir();q=batch/'queue.json';q.write_text('[{"id":"H0099","状态":"已核页"}]',encoding='utf-8');before=q.read_bytes()
   r=self.run_script('建批次.py',root,work,batch);self.assertNotEqual(r.returncode,0);self.assertEqual(q.read_bytes(),before)
 def test_mismatched_cached_page_is_not_reused(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);work,batch,p=self.fixture(root);old=root/'batches/old/pages';old.mkdir(parents=True);(old/'11.json').write_text(json.dumps({'offerId':'999','标题':'错误身份'}))
   r=self.run_script('建批次.py',root,work,batch);self.assertEqual(r.returncode,0,r.stderr);self.assertFalse((batch/'pages/11.json').exists())
 def test_missing_page_never_becomes_delisted(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);work,batch,p=self.fixture(root);batch.mkdir();(batch/'queue.json').write_text(json.dumps([{'id':'H0001','商品':[{'offerId':'11'}],'对应款':[{'序':1}],'状态':'待核页'}]));chunk=work/'chunks/a';chunk.mkdir(parents=True);(chunk/'match.json').write_text(json.dumps({'款':[{'序':1,'规格':'测试','候选':[{'条目':'H0001','offerId':'11','结论':'未抓到','note':'保留待核'}]}]}))
   r=self.run_script('merge.py',root,work,batch);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads((batch/'queue.json').read_text(encoding='utf-8'))[0]['状态'],'待核页')
if __name__=='__main__':unittest.main()
