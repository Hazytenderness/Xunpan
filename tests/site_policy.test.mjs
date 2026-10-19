import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
const source=await fs.readFile(new URL('../tools/browser/site_policy.mjs',import.meta.url),'utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;

async function simulate(syncState,{canWrite=true,afterError=false}={}){
  const previous={window:globalThis.window,document:globalThis.document};
  let calls=0,result;
  const quota="Setting the value of 'jp_deal_宠物' exceeded the quota.";
  globalThis.window={jp云:{能写不:()=>canWrite},ReviewCore:{},SelectionCore:{sourcesReady:()=>true}};
  globalThis.document={getElementById:()=>({dataset:{state:syncState},textContent:quota})};
  const page={goto:async()=>{},waitForFunction:async fn=>{if(!fn())throw Error('fixture timeout');},
    evaluate:async()=>{calls++;if(afterError)syncState='error';return {变更款:afterError?[1]:[],采纳失败:[]};}};
  try{
    await new AsyncFunction('pageFor','job','done','sitePolicy',source)(async()=>page,{apply:true},async r=>{result=r;throw {done:true};},()=>{});
  }catch(error){if(!error.done)throw error;}
  finally{globalThis.window=previous.window;globalThis.document=previous.document;}
  return {calls,result};
}

test('storage quota error is reported before applying website policy',async()=>{
  await assert.rejects(()=>simulate('error',{canWrite:false}),/网站同步门禁失败.*exceeded the quota/);
});
test('pending sync remains closed and healthy sync permits policy evaluation',async()=>{
  await assert.rejects(()=>simulate('pending'),/timeout/);
  await assert.rejects(()=>simulate('ok',{canWrite:false}),/timeout/);
  assert.equal((await simulate('ok')).calls,1);
});
test('sync failure after local change keeps the draft and reports actual error',async()=>{
  const {result}=await simulate('ok',{afterError:true});
  assert.equal(result.同步待确认,true);
  assert.match(result.错误,/exceeded the quota/);
});
