// 生成「多件装折算」校准推送：已生效的单件价按装数折算后自动采纳；待定且建议采纳的单件价另附折算条目、原条目改为建议驳回；
// 单件包装的重量按装数估算整套重量，作为需判断条目由人确认。
import fs from 'node:fs';import vm from 'node:vm';
const S=process.argv[2],NOW=new Date().toISOString();
const ctx=vm.createContext({URL,window:{}});vm.runInContext(fs.readFileSync('build/js/review-core.js','utf8'),ctx);const R=ctx.ReviewCore;
const rows=JSON.parse(fs.readFileSync(S+'/purchase-now.json','utf8')).行;
const N={598:2,882:20,1116:3,1317:50,1339:6,1502:20,1504:10,2359:2,2532:20,2627:10,2878:20};
const PEND={277:[2,'高阳县艾枝毛巾厂'],598:[2,'潮州市亿嘉科技有限公司'],1362:[2,'高阳县棉巾纺织品制造有限公司']};
const items=[],base=(序,e)=>({序:+序,候选ID:e.候选ID,供应商:e.供应商,字段:e.字段,证据:e.证据||undefined});
for(const [序,n] of Object.entries(N)){
 const row=rows[序],force=R.inForce(row);
 // 原计入成本那家排最后，折算后同价时不换家（包装跟着计入成本那家）
 const order=Object.entries(row.复核).sort(([,x],[,y])=>(x.候选ID===row.核价?.候选ID)-(y.候选ID===row.核价?.候选ID));
 for(const [id,e] of order)if(e.字段==='采购单价'&&force.has(id)){
  const v=+(e.采纳值*n).toFixed(2);
  items.push({...base(序,e),新值:v,原值:e.采纳值,依据:'对标 '+n+' 件装，原采纳价 ¥'+e.采纳值+' 为单件价（'+e.依据.slice(0,80)+'），按 ×'+n+' 折算为每套 ¥'+v,来源:'多件装折算',建议:{动作:'自动采纳',理由:'单件价按对标 '+n+' 件装折算'}});
 }
 const box=row.包装,pick=row.核价?.候选ID;
 if(box?.重量克&&pick){const sup=Object.values(row.复核).find(e=>e.候选ID===pick)?.供应商||'';
  items.push({序:+序,候选ID:pick,供应商:sup,字段:'单品包装',新值:{长:box.长,宽:box.宽,高:box.高,重量克:box.重量克*n},原值:{长:box.长,宽:box.宽,高:box.高,重量克:box.重量克},依据:'现有包装是单件的（'+box.重量克+'g），对标 '+n+' 件装，按单件重量 ×'+n+' 估算整套重量；整套尺寸未知，运费为估算下限',来源:'多件装折算',建议:{动作:'需判断',理由:'整套重量按单件 ×'+n+' 估算，尺寸未知，确认后计入运费'}});}
}
const stale=[];
for(const [序,[n,sup]] of Object.entries(PEND)){
 for(const [id,e] of Object.entries(rows[序].复核)){
  if(e.字段!=='采购单价'||e.状态!=='待复核'||e.供应商!==sup||e.建议?.动作!=='建议采纳')continue;
  const v=+(e.新值*n).toFixed(2);
  items.push({...base(序,e),新值:v,原值:e.新值,依据:'对标 '+n+' 件装，页面价 ¥'+e.新值+' 为单件价（'+e.依据.slice(0,80)+'），按 ×'+n+' 折算为每套 ¥'+v,来源:'多件装折算',建议:{动作:'建议采纳',理由:'单件价按对标 '+n+' 件装折算'}});
  const old={...base(序,e),新值:e.新值,建议:{动作:'建议驳回',理由:'单件价，已另附按 '+n+' 件装折算的报价'}};
  if(R.idOf(old)!==id)throw new Error('id 对不上 CW'+序);stale.push(old);items.push(old);
 }
}
const feed={批次:'校准·多件装折算',来源:'多件装折算',生成时间:NOW,条目:items};
fs.writeFileSync(S+'/calib-feed.json',JSON.stringify(feed,null,1));
console.log('条目',items.length,'| 价格折算',items.filter(i=>i.来源&&i.字段==='采购单价'&&i.建议.动作==='自动采纳').length,'| 包装估算',items.filter(i=>i.字段==='单品包装').length,'| 待定折算',items.filter(i=>i.建议.动作==='建议采纳').length,'| 原条目改驳回',stale.length);
