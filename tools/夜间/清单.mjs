// 夜间任务取款：货源核实「待跑」里按 SelectionCore.sourceFlow 分出的 缺货源 / 待核页 款。规则住网站，⛔别在这里另写一份。
// 用法：node 清单.mjs <网站目录> <purchase.json> <source|check> <跳过的序 JSON 文件> [上限]
//   source → 找货源 任务清单.json 格式：[{序, asin, 父ASIN, 图, 名, 类, 排除offer}]（排除offer＝现有候选，都已款不对/下架）
//   check  → 核 SKU 建批次.py 用的 products.json 格式（商品对象带 货源候选，只留还没核匹配度的候选）
import fs from 'node:fs';import vm from 'node:vm';
const [site,purchase,mode,skipFile,cap]=process.argv.slice(2);
globalThis.window=globalThis;
for(const f of ['products.js','products-sources.js','selection-core.js'])vm.runInThisContext(fs.readFileSync(site+'/build/js/'+f,'utf8'),{filename:f});
const core=globalThis.SelectionCore,src=globalThis.DECK_SOURCES||{},rows=JSON.parse(fs.readFileSync(purchase,'utf8')).行||{};
const skip=new Set(JSON.parse(fs.readFileSync(skipFile,'utf8')).map(Number));
const out=[];
for(const p of globalThis.DECK){
 if(p.历史目录||skip.has(p.序))continue;
 if(src[p.序])p.货源候选=src[p.序];
 const row=rows[p.序]||{},rs=core.reviewState(p,row,[]);
 if(rs==='已放弃'||rs==='不进流程')continue;
 // 「待跑」与货源核实页同口径：重新跑没跑完的，或待核对里从没拉过 / 拉失败的
 const wait=core.rerunPending(row)||(rs==='待核对'&&['待拉','拉失败'].includes(core.pullStatus(p,row).状态));
 if(!wait||core.sourceFlow(p,row)!==mode)continue;
 if(mode==='source')out.push({序:p.序,asin:p.asin,父ASIN:p.父ASIN,图:p.图,名:p.名,类:p.类||'',排除offer:(p.货源候选||[]).map(q=>String(q.候选ID))});
 else out.push({...p,货源候选:(p.货源候选||[]).filter(q=>!q.历史报价&&!q.匹配度)});
}
process.stdout.write(JSON.stringify(cap?out.slice(0,+cap):out));
