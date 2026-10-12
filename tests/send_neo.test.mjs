import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
const source=await fs.readFile(new URL('../tools/browser/send_neo.mjs',import.meta.url),'utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function simulate(states, {dry=false,blocked=false,snapshots=[],text='原话'}={}){
  const actions=[];let result;
  const page={goto:async()=>{},evaluate:async()=>states.shift(),snapshot:async()=>snapshots.shift()||'',
    click:async ref=>actions.push(['click',ref]),insertText:async t=>actions.push(['paste',t]),
    waitForFunction:async()=>true};
  try{await new AsyncFunction('pageFor','job','done','blocked','chatUrl',source)(async()=>page,
    {ww:'supplier',offerId:'123',text,dry},async r=>{result=r;throw {done:true};},async()=>blocked,()=> 'fixture');}
  catch(e){if(!e.done)throw e;}
  return {result,actions};
}
test('wrong recipient stops without typing or clicking',async()=>{
  const r=await simulate([{ok:false,hd:'other',mine:[],box:''}]);
  assert.match(r.result.结果,/收件人对不上/);assert.deepEqual(r.actions,[]);
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
