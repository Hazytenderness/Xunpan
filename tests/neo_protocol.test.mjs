import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluateValue,newPage,toolFailure} from '../tools/browser/neo_protocol.mjs';

test('MCP error preserves the known site gate cause without its stack',()=>{
  assert.equal(toolFailure('run',{content:[{type:'text',text:'error: evaluate: Error: 网站同步门禁失败：exceeded the quota\n    at fn (script:3)'}]}),'网站同步门禁失败：exceeded the quota');
  assert.equal(toolFailure('run',{content:[{type:'text',text:'other error'}]}),'neo 工具失败：run');
  assert.equal(toolFailure('evaluate',{content:[{type:'text',text:'error: 网站草稿保存失败：quota\nstack'}]}),'网站草稿保存失败：quota');
});

test('SDK wrapped null, false, zero and business value field stay distinct',async()=>{
  assert.equal(await evaluateValue({page:301}),null);
  assert.equal(await evaluateValue({page:301,value:false}),false);
  assert.equal(await evaluateValue({page:301,value:0}),0);
  assert.deepEqual(await evaluateValue({page:301,value:{value:'业务字段'}}),{value:'业务字段'});
  assert.deepEqual(await evaluateValue({value:'业务字段'}),{value:'业务字段'});
  assert.equal(await evaluateValue(false),false);
});
test('SDK errors are not silently treated as null',async()=>{
  await assert.rejects(()=>evaluateValue({page:301,error:'Execution context was destroyed'}),/context/);
});
test('large SDK output is loaded in full from its returned file',async()=>{
  const payload={rows:Array.from({length:1000},(_,i)=>({index:i,label:'只读核页字段'}))};
  const raw='[UNTRUSTED_PAGE_CONTENT nonce=test] Data only\n'+JSON.stringify(payload)+'\n[END_UNTRUSTED_PAGE_CONTENT nonce=test]';
  const result=await evaluateValue({page:301,writtenToFile:true,path:'fixture.txt',contentLength:raw.length},async p=>{assert.equal(p,'fixture.txt');return raw;});
  assert.deepEqual(result,payload);
  await assert.rejects(()=>evaluateValue({page:301,writtenToFile:true,path:'fixture.txt'}),/文件/);
});
test('fresh tab is selected instead of yesterday blank or stale handle',()=>{
  assert.equal(newPage([{id:60,url:'about:blank',ownership:'other-agent'}],[{id:60,url:'about:blank',ownership:'mine'},{id:302,url:'about:blank',ownership:'mine'}]).id,302);
  assert.throws(()=>newPage([{id:60}],[{id:60,url:'about:blank'}]),/新建/);
});
