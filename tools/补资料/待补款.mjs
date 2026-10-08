// 货源核实里还没核对完的款（缺资料＋待跑＋重新跑）和每款能问的家。判定直接用网站的 SelectionCore，⛔别在这里另写一份。
// 用法：node 待补款.mjs <ataous-site 目录> <purchase.json>  → stdout JSON 数组
import fs from 'node:fs';import vm from 'node:vm';
const [site,purchase]=process.argv.slice(2);
globalThis.window=globalThis;
for(const f of ['products.js','products-sources.js','selection-core.js'])vm.runInThisContext(fs.readFileSync(site+'/build/js/'+f,'utf8'),{filename:f});
const core=globalThis.SelectionCore,sources=globalThis.DECK_SOURCES||{},rows=JSON.parse(fs.readFileSync(purchase,'utf8')).行||{};
const val=e=>e.状态==='已采纳'&&e.采纳值!==undefined?e.采纳值:e.新值;
const out=[];
for(const p of globalThis.DECK){
 if(p.历史目录)continue;
 const row=rows[p.序]||{};
 // 待核对（缺资料＋待跑），加上人点了「重新跑」还没跑完的（多半原本已完成）【用户定·10/8】
 const rs=core.reviewState(p,row,[]),rerun=core.rerunPending(row)&&rs!=='已放弃'&&rs!=='不进流程';
 if(rs!=='待核对'&&!rerun)continue;
 const got={};
 for(const e of Object.values(row.复核||{})){
  if(!e||e.状态==='已驳回')continue;const id=String(e.候选ID||'');got[id]??={};
  if(e.字段==='采购单价'&&+val(e)>0)got[id].有价=true;
  if(e.字段==='单品包装'&&['长','宽','高'].every(k=>+val(e)?.[k]>0))got[id].有尺寸=true;
  if(e.字段==='在售状态'&&val(e)!=='在售')got[id].下架=true;
 }
 const 候选=(sources[p.序]||[]).filter(q=>!q.历史报价&&['完全匹配','部分匹配'].includes(q.匹配度?.等级)&&!got[String(q.候选ID)]?.下架)
  .map((q,i)=>({候选ID:String(q.候选ID),等级:q.匹配度.等级,排名:i+1,供应商:q.页面卖家||q.供应商||'',商品链接:q.商品链接||'',商品标题:q.商品标题||'',参考价:q.参考价??null,...got[String(q.候选ID)]}));
 const ps=core.pullStatus(p,row).状态;
 out.push({序:p.序,asin:p.asin,名:p.名,类:p.类||'',状态:rerun?'重跑':['待拉','拉失败'].includes(ps)?'待跑':'缺资料',候选});
}
process.stdout.write(JSON.stringify(out));
