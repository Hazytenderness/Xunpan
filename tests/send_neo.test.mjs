import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
const source=await fs.readFile(new URL('../tools/browser/send_neo.mjs',import.meta.url),'utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function simulate(states, {dry=false,blocked=false,snapshots=[],text='原话',waitFails=false,syncFails=false,track=false,risks=null,clock=null,targets=[],latest=null,jobExtra={}}={}){
  const actions=[];let result,waits=0;
  const policy=()=>{};
  const page={goto:async()=>{},evaluate:async fn=>fn===policy?{采纳失败:[],变更款:syncFails?[24]:[],可询盘:[latest||{序:24,可询盘候选ID:['123']}]}:states.shift(),snapshot:async()=>snapshots.shift()||'',
    click:async ref=>actions.push(['click',ref]),insertText:async t=>actions.push(['paste',t]),
    clearDraft:async text=>actions.push(['clear-owned',text]),
    waitForFunction:async()=>{waits++;if(syncFails&&waits===3)throw Error('fixture quota');if(waitFails)throw Error('fixture loading');return true;}};
  const cacheFs={writeFile:async(name,data)=>actions.push(['journal',JSON.parse(data).阶段])};
  const TaskDate=clock?class extends Date{constructor(){super(clock);}static now(){return new Date(clock).valueOf();}}:class extends Date{constructor(){super('2026-10-14T02:00:00Z');}static now(){return new Date('2026-10-14T02:00:00Z').valueOf();}};
  try{await new AsyncFunction('pageFor','job','done','blocked','chatUrl','sitePolicy','fs','path','C','Date',source)(async()=>page,
    {ww:'supplier',offerId:'123',seqs:[24],targets,text,dry,...jobExtra,...(track?{operation_id:'test'}:{})},async r=>{result=r;throw {done:true};},async()=>risks?risks.shift():blocked,()=> 'fixture',policy,cacheFs,{join:(...p)=>p.join('/')},'cache',TaskDate);}
  catch(e){if(!e.done)throw e;}
  return {result,actions};
}
test('wrong recipient stops without typing or clicking',async()=>{
  const r=await simulate([{ok:false,hd:'other',mine:[],box:''}]);
  assert.match(r.result.结果,/收件人对不上/);assert.deepEqual(r.actions,[]);
});
test('existing exact outbound text never sends twice',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[{text:'原话'}],box:''}]);
  assert.match(r.result.结果,/最新聊天已有相同内容/);assert.deepEqual(r.actions,[]);
});
test('recovery requires unique absolute-time evidence and never touches editor',async()=>{
  for(const t of ['2026-10-14 10:00:00','10:00','2026-10-13 10:00:00']){
    const r=await simulate([{ok:true,hd:'supplier',mine:[{text:'原话',t}],box:''}],
      {jobExtra:{recover_only:true,intent_time:Date.parse('2026-10-14T02:00:00Z')/1000}});
    assert.equal(r.result.回执恢复,t==='2026-10-14 10:00:00'?true:undefined);
    assert.deepEqual(r.actions,[]);
  }
});
test('history comparison ignores transport object-key order',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:'',history:[{images:[],self:false,text:'有',videos:[]}]}],
    {dry:true,jobExtra:{expected_history:[{self:false,text:'有',images:[],videos:[]}]}});
  assert.equal(r.result.结果,'演练通过');
});
test('only a proven owned draft can be replaced after reanalysis',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:'旧问题'},{ok:true,mine:[],box:'原话'},
    {ok:true,mine:[{text:'原话',t:'2026-10-14 10:00:00'}],box:''}],
    {jobExtra:{owned_draft:'旧问题'},snapshots:['textbox [ref=e1] 输入','button [ref=e2] 发送']});
  assert.equal(r.result.结果,'成功');assert.deepEqual(r.actions[0],['clear-owned','旧问题']);
  const blocked=await simulate([{ok:true,hd:'supplier',mine:[],box:'别人的草稿'}],{jobExtra:{owned_draft:'旧问题'}});
  assert.equal(blocked.result.草稿冲突,true);assert.equal(blocked.result.已点击发送,false);assert.deepEqual(blocked.actions,[]);
});
test('incoming message during preparation blocks click',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:'',history:[]},{ok:true,mine:[],box:'原话',history:[{self:false,text:'新答复'}]}],
    {snapshots:['textbox [ref=e1] 请输入消息','button [ref=e2] 发送']});
  assert.match(r.result.结果,/聊天已变化/);assert.ok(!r.actions.some(a=>a[0]==='click'&&a[1]==='e2'));
});

test('website change awaiting sync keeps draft and defers before supplier effects',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''}],{syncFails:true});
  assert.equal(r.result.同步待确认,true);assert.notEqual(r.result.可重试,true);
  assert.match(r.result.错误,/quota/);assert.deepEqual(r.actions,[]);
});
test('page not loaded before effects is safely deferred',async()=>{
  const r=await simulate([],{waitFails:true});
  assert.equal(r.result.可重试,true);assert.deepEqual(r.actions,[]);
});
test('late verification during editor wait cannot be retried',async()=>{
  const r=await simulate([],{waitFails:true,risks:[false,true]});
  assert.match(r.result.结果,/验证/);assert.notEqual(r.result.可重试,true);assert.deepEqual(r.actions,[]);
});
test('text click is blocked after Beijing 18:00',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''},{ok:true,mine:[],box:'原话'}],
    {clock:'2026-10-14T10:00:00Z',snapshots:['textbox [ref=e1] 请输入消息','button [ref=e2] 发送']});
  assert.equal(r.result.时段结束,true);assert.ok(!r.actions.some(a=>a[0]==='click'&&a[1]==='e2'));
});
test('updated ASIN or removed candidate skips without sending',async()=>{
  for(const latest of [{序:24,asin:'new',候选ID:['123']},{序:24,asin:'original',候选ID:['999']}]){
    const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''}],{targets:[{seq:24,asin:'original'}],latest});
    assert.match(r.result.结果,/^跳过:/);assert.deepEqual(r.actions,[]);
  }
});
test('new candidate without checked SKU cannot be sent from an old queue',async()=>{
  const latest={序:24,asin:'original',候选ID:['123'],可询盘候选ID:[]};
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''}],{targets:[{seq:24,asin:'original'}],latest});
  assert.match(r.result.结果,/^跳过:.*核页/);assert.deepEqual(r.actions,[]);
});
test('send intent is journaled before the actual click',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''},{ok:true,mine:[],box:'原话'},
    {ok:true,mine:[{text:'原话',t:'2026-10-14 10:00:00'}],box:''}],
    {track:true,snapshots:['textbox [ref=e1] 请输入消息','button [ref=e2] 发送']});
  const click=r.actions.findIndex(a=>a[0]==='click'&&a[1]==='e2');
  assert.ok(click>0);assert.deepEqual(r.actions[click-1],['journal','发送点击前']);
});
test('verification stops before reading or sending',async()=>{
  const r=await simulate([],{blocked:true});assert.match(r.result.结果,/验证/);assert.deepEqual(r.actions,[]);
});
test('dry run never pastes or sends',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''}],{dry:true});
  assert.equal(r.result.结果,'演练通过');assert.deepEqual(r.actions,[]);
});
test('content mismatch stops before send button',async()=>{
  const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''},{ok:true,mine:[],box:'changed'}],
    {snapshots:['textbox [ref=e1] 请输入消息']});
  assert.match(r.result.结果,/三项核对/);assert.deepEqual(r.actions,[['click','e1'],['paste','原话']]);
});
test('one exact added message succeeds; two messages fail',async()=>{
  for(const count of [1,2]){
    const r=await simulate([{ok:true,hd:'supplier',mine:[],box:''},{ok:true,mine:[],box:'原话'},
      {ok:true,mine:Array.from({length:count},()=>({text:'原话',t:'2026-10-13 10:00:00'})),box:''}],
      {snapshots:['textbox [ref=e1] 请输入消息','button [ref=e2] 发送']});
    assert.equal(r.result.结果,count===1?'成功':'异常');
    assert.deepEqual(r.actions,[['click','e1'],['paste','原话'],['click','e2']]);
  }
});
