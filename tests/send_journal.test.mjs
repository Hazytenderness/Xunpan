import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=path.join(root,'..','temp','询盘工作流优化_20261019');
const bridge=await fs.readFile(path.join(root,'tools/browser/neo_bridge.mjs'),'utf8');
const cacheSource=bridge.slice(bridge.indexOf('  const cacheFs='),bridge.indexOf('  await new AsyncFunction('));
async function fixture(t,overrides={},platform='win32'){
  await fs.mkdir(temp,{recursive:true});
  const dir=await fs.mkdtemp(path.join(temp,'journal-test-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const target=path.join(dir,'send.progress.json');
  await fs.writeFile(target,'{"operation_id":"old","阶段":"粘贴前"}');
  const ops={...fs,...overrides};
  const writeSendProgress=async(filename,data,options)=>{
    const helper=await import('../tools/browser/send_journal.mjs');
    return helper.writeSendProgress(filename,data,options,{fsOps:ops,platform,sleep:async()=>{}});
  };
  const cacheFs=new Function('fs','path','stFile','writeSendProgress',cacheSource+'return cacheFs;')(ops,path,path.join(dir,'state.json'),writeSendProgress);
  return {dir,target,cacheFs};
}

test('temporary Windows rename denial preserves the old journal until an atomic replacement succeeds',async t=>{
  let count=0,targetPath;
  const {target,cacheFs}=await fixture(t,{rename:async(from,to)=>{
    count++;
    if(count<=2){assert.equal(await fs.readFile(to,'utf8'),'{"operation_id":"old","阶段":"粘贴前"}');throw Object.assign(Error('file held'),{code:'EPERM'});}
    targetPath=to;return fs.rename(from,to);
  }});
  await cacheFs.writeFile(target,'{"operation_id":"new","阶段":"发送点击前"}');
  assert.equal(targetPath,target);
  assert.deepEqual(JSON.parse(await fs.readFile(target,'utf8')),{operation_id:'new',阶段:'发送点击前'});
});

test('persistent Windows denial is bounded and retains both committed and pending evidence',async t=>{
  let renames=0;
  const {target,cacheFs}=await fixture(t,{rename:async()=>{renames++;throw Object.assign(Error('held'),{code:'EBUSY'});}});
  await assert.rejects(cacheFs.writeFile(target,'{"operation_id":"new","图已发":true,"阶段":"发送点击前"}'),asyncError=>{
    assert.equal(asyncError.code,'EBUSY');assert.match(asyncError.progressPendingPath,/\.pending$/);return true;
  });
  assert.equal(renames,6);
  assert.equal(await fs.readFile(target,'utf8'),'{"operation_id":"old","阶段":"粘贴前"}');
  const pending=(await fs.readdir(path.dirname(target))).filter(x=>x.endsWith('.pending'));
  assert.equal(pending.length,1);
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(path.dirname(target),pending[0]),'utf8')),{operation_id:'new',图已发:true,阶段:'发送点击前'});
});

test('separate progress writes never share a temporary filename or alter legacy pending evidence',async t=>{
  const paths=[];
  const {target,cacheFs}=await fixture(t,{rename:async(from,to)=>{paths.push(from);return fs.rename(from,to);}});
  await fs.writeFile(target+'.pending','legacy evidence');
  await Promise.all([cacheFs.writeFile(target,'{"operation_id":"first"}'),cacheFs.writeFile(target,'{"operation_id":"second"}')]);
  assert.equal(new Set(paths).size,2);
  assert.ok(!paths.includes(target+'.pending'));
  assert.equal(await fs.readFile(target+'.pending','utf8'),'legacy evidence');
  assert.ok(['first','second'].includes(JSON.parse(await fs.readFile(target,'utf8')).operation_id));
});

test('nontransient errors and non-Windows permission errors are not retried',async t=>{
  for(const [platform,code] of [['win32','ENOSPC'],['linux','EPERM']]){
    let renames=0;
    const {target,cacheFs}=await fixture(t,{rename:async()=>{renames++;throw Object.assign(Error('permanent'),{code});}},platform);
    await assert.rejects(cacheFs.writeFile(target,'{}'),{code});
    assert.equal(renames,1);
    assert.equal(await fs.readFile(target,'utf8'),'{"operation_id":"old","阶段":"粘贴前"}');
  }
});

test('write failure stops immediately without attempting a rename',async t=>{
  let renames=0;
  const {target,cacheFs}=await fixture(t,{writeFile:async()=>{throw Object.assign(Error('full'),{code:'ENOSPC'});},rename:async()=>{renames++;}});
  await assert.rejects(cacheFs.writeFile(target,'{}'),{code:'ENOSPC'});
  assert.equal(renames,0);
  assert.equal(await fs.readFile(target,'utf8'),'{"operation_id":"old","阶段":"粘贴前"}');
});

test('Windows access-denied replacement recovers with the exact pending payload',async t=>{
  let attempts=0;
  const {target,cacheFs}=await fixture(t,{rename:async(from,to)=>{
    if(++attempts===1)throw Object.assign(Error('held'),{code:'EACCES'});
    return fs.rename(from,to);
  }});
  await cacheFs.writeFile(target,'{"operation_id":"new","图已发":true}');
  assert.deepEqual(JSON.parse(await fs.readFile(target,'utf8')),{operation_id:'new',图已发:true});
});

test('real Windows file handle denial recovers after the handle is released',{skip:process.platform!=='win32'},async t=>{
  const {spawn}=await import('node:child_process');
  const {writeSendProgress}=await import('../tools/browser/send_journal.mjs');
  const {target}=await fixture(t);
  const probe=target+'.lock-probe';await fs.writeFile(probe,'probe');
  const quote=p=>"'"+p.replaceAll("'","''")+"'";
  const holder=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',
    `$h=[IO.File]::Open(${quote(target)},[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite); Write-Output 'LOCKED'; Start-Sleep -Milliseconds 650; $h.Dispose()`],{windowsHide:true});
  t.after(()=>holder.kill());
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('lock holder timeout')),10000);
    holder.on('error',error=>{clearTimeout(timer);reject(error);});
    holder.on('exit',code=>{clearTimeout(timer);if(code)reject(Error('lock holder exited: '+code));});
    holder.stdout.on('data',data=>{if(data.toString().includes('LOCKED')){clearTimeout(timer);resolve();}});
  });
  await assert.rejects(fs.rename(probe,target),error=>['EPERM','EACCES','EBUSY'].includes(error.code));
  await writeSendProgress(target,'{"operation_id":"after-lock","阶段":"发送点击前"}');
  assert.deepEqual(JSON.parse(await fs.readFile(target,'utf8')),{operation_id:'after-lock',阶段:'发送点击前'});
});

async function runSend(cacheFs,target,{clickFails=false}={}){
  const actions=[];
  const states=[{ok:true,hd:'supplier',mine:[],box:''},{ok:true,mine:[],box:'原话'},{ok:true,mine:[{text:'原话',t:'10:00'}],box:''}];
  const sitePolicy=()=>{};
  const page={goto:async()=>{},waitForFunction:async()=>true,focusEditor:async()=>{},
    insertText:async()=>actions.push('paste'),snapshot:async()=> 'button [ref=e1] 发送',
    evaluate:async fn=>fn===sitePolicy?{采纳失败:[],变更款:[],可询盘:[{序:24,可询盘候选ID:['123']}]}:states.shift(),
    click:async()=>{actions.push('click');if(clickFails)throw Error('uncertain click result');}};
  const source=await fs.readFile(path.join(root,'tools/browser/send_neo.mjs'),'utf8');
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  const TaskDate=class extends Date{constructor(){super('2026-10-19T02:00:00Z');}static now(){return 1792375200000;}};
  let result,error;
  try{
    await new AsyncFunction('pageFor','job','done','blocked','chatUrl','sitePolicy','fs','path','C','Date',source)(
      async()=>page,{ww:'supplier',offerId:'123',operation_id:'send-test',seqs:[24],text:'原话'},
      async value=>{result=value;throw {done:true};},async()=>false,()=> 'fixture',sitePolicy,cacheFs,path,path.dirname(target),TaskDate);
  }catch(caught){if(!caught.done)error=caught;}
  return {actions,result,error};
}

test('retrying persistence before send never repeats the send click',async t=>{
  let denials=0;
  const {target,cacheFs}=await fixture(t,{rename:async(from,to)=>{
    if(JSON.parse(await fs.readFile(from,'utf8')).阶段==='发送点击前'&&denials++<2)throw Object.assign(Error('held'),{code:'EPERM'});
    return fs.rename(from,to);
  }});
  const {actions,result,error}=await runSend(cacheFs,target);
  assert.equal(error,undefined);assert.equal(result.结果,'成功');assert.deepEqual(actions,['paste','click']);
});

test('permanent persistence failure stops before send and retains the attempted stage',async t=>{
  const {target,cacheFs}=await fixture(t,{rename:async(from,to)=>{
    if(JSON.parse(await fs.readFile(from,'utf8')).阶段==='发送点击前')throw Object.assign(Error('held'),{code:'EPERM'});
    return fs.rename(from,to);
  }});
  const {actions,result,error}=await runSend(cacheFs,target);
  assert.equal(result,undefined);assert.equal(error.code,'EPERM');assert.deepEqual(actions,['paste']);
  assert.equal(JSON.parse(await fs.readFile(target,'utf8')).阶段,'粘贴前');
  assert.equal(JSON.parse(await fs.readFile(error.progressPendingPath,'utf8')).阶段,'发送点击前');
});

test('an uncertain send click is never retried even when journal retry is enabled',async t=>{
  const {target,cacheFs}=await fixture(t);
  const {actions,result,error}=await runSend(cacheFs,target,{clickFails:true});
  assert.equal(result,undefined);assert.match(error.message,/uncertain click/);assert.deepEqual(actions,['paste','click']);
  assert.equal(JSON.parse(await fs.readFile(target,'utf8')).阶段,'发送点击前');
});
