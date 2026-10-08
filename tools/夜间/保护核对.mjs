// 导入保护核对（供应商匹配工作流第 5 节第 3 步，从 20261007 批次 audit.mjs 通用化）
//   node 保护核对.mjs snap <网站目录> <快照.json>
//   node 保护核对.mjs diff <网站目录> <快照.json> <目标序 JSON 数组文件> <允许字段,逗号分隔>
// diff：款数、其他商品、目标款的其他字段有任何变化就退出码 1
import fs from 'node:fs';
const [cmd,site,snap,targetsFile,allow]=process.argv.slice(2);
function load(){
 const S=site+'/build/js/';
 const deck=JSON.parse(fs.readFileSync(S+'products.js','utf8').match(/window\.DECK=(\[.*?\]);?\s*$/s)[1]);
 const src=JSON.parse(fs.readFileSync(S+'products-sources.js','utf8').match(/window\.DECK_SOURCES=(\{.*\});?\s*$/s)[1]);
 for(const x of deck)if(src[x.序])x.货源候选=src[x.序];return deck;
}
if(cmd==='snap'){const d=load();fs.writeFileSync(snap,JSON.stringify(d));console.log('快照',d.length,'款');process.exit(0);}
const before=JSON.parse(fs.readFileSync(snap,'utf8')),after=load();
const targets=new Set(JSON.parse(fs.readFileSync(targetsFile,'utf8')).map(Number)),ALLOW=new Set(allow.split(','));
const am=new Map(after.map(x=>[x.序,x])),bad=[];let changed=0;
if(before.length!==after.length)bad.push(`款数 ${before.length}→${after.length}`);
for(const b of before){const a=am.get(b.序);if(!a){bad.push('缺 '+b.序);continue;}
 for(const f of new Set([...Object.keys(b),...Object.keys(a)])){
  if(JSON.stringify(b[f])===JSON.stringify(a[f]))continue;
  if(targets.has(b.序)&&ALLOW.has(f)){changed++;continue;}
  bad.push(`序${b.序} 字段「${f}」被改`);}}
console.log('目标款字段变化',changed,'处；违规',bad.length,'处');bad.slice(0,20).forEach(x=>console.log(' ',x));
process.exit(bad.length?1:0);
