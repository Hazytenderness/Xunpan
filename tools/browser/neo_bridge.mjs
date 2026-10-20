// BrowserOS neo 的 MCP 客户端。保留 job.json → <脚本>.out.json。
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {policyAction as sitePolicy} from '../lib/operating-policy.mjs';
import {evaluateValue,newPage,toolFailure} from './neo_protocol.mjs';
import {writeSendProgress} from './send_journal.mjs';
import {validateSendJob} from './send_policy.mjs';

const C = path.join(os.homedir(), '.cache', 'xunpan');
const dir = path.dirname(fileURLToPath(import.meta.url));
const script = process.argv[2];
if (!['probe.mjs','page.mjs','chat_list.mjs','chat_read.mjs','send.mjs','site_policy.mjs'].includes(script)) throw Error('未知浏览器任务');
const NAME = path.parse(script).name;
const job = JSON.parse(await fs.readFile(path.join(C, 'job.json'), 'utf8'));
if(script==='send.mjs')validateSendJob(job);
if(script==='send.mjs')await fs.unlink(path.join(C,'send.progress.json')).catch(()=>{});
if(script==='send.mjs')await fs.writeFile(path.join(C,'send.progress.json'),JSON.stringify({operation_id:job.operation_id,阶段:'准备'}));
let policy={};try{policy=JSON.parse(await fs.readFile(path.join(C,'windows_permissions.json'),'utf8'));}catch{}
if(script==='send.mjs'&&policy.send!==true)throw Error('发送未授权');
if(script==='site_policy.mjs'&&job.apply&&policy.site_policy!==true)throw Error('网站采纳/排除未授权');
if(script==='chat_list.mjs'&&policy.scan!==true)throw Error('扫描未授权');
if(script==='chat_read.mjs'){
  const eligible=JSON.parse(await fs.readFile(path.join(dir,'../windows_pending_chats.json'),'utf8'));
  if(policy.runtime_chats===true){
    let known=false;const batches=path.join(dir,'../../batches');
    for(const folder of await fs.readdir(batches,{withFileTypes:true})){
      if(!folder.isDirectory())continue;
      const queue=JSON.parse(await fs.readFile(path.join(batches,folder.name,'queue.json'),'utf8').catch(()=>'[]'));
      if(queue.some(x=>x.旺旺名===job.ww))known=true;
    }
    if(!known)throw Error('聊天对象不在本地询盘队列');
  }else if(!policy.chat_read_ww?.includes(job.ww)||!eligible.some(x=>x.ww===job.ww))throw Error('聊天读取未授权或不在交接39家中');
}
const endpoint = process.env.XUNPAN_NEO_URL || 'http://127.0.0.1:9010/mcp';
const endpointUrl = new URL(endpoint);
if (!['127.0.0.1','localhost','[::1]'].includes(endpointUrl.hostname)) throw Error('neo 必须连接本机');
let transportSession, session, requestId = 0;
async function rpc(method, params = {}, notification = false) {
  const body = {jsonrpc:'2.0', method, params, ...(!notification ? {id:++requestId} : {})};
  const response = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json',
    Accept:'application/json, text/event-stream', ...(transportSession ? {'Mcp-Session-Id':transportSession}: {})},
    body:JSON.stringify(body),signal:AbortSignal.timeout(35000)});
  transportSession = response.headers.get('mcp-session-id') || transportSession;
  if (!response.ok) throw Error('neo MCP HTTP ' + response.status);
  const text = await response.text(); if (notification || !text.trim()) return {};
  const packets = text.trim().startsWith('{') ? [JSON.parse(text)] : text.split(/\r?\n/).filter(l=>l.startsWith('data: ')&&l.slice(6).trim()).map(l=>JSON.parse(l.slice(6)));
  const packet = packets.find(p=>p.id===body.id);
  if (!packet || packet.error) throw Error('neo MCP 请求失败');
  return packet.result;
}
async function call(name, args = {}) {
  const result = await rpc('tools/call', {name, arguments:{...args,...(session ? {session}: {})}});
  session = result._meta?.['com.browseros.neo/session'] || session;
  if (result.isError) {
    await fs.writeFile(path.join(C,'neo_tool_error.json'),JSON.stringify({name,time:new Date().toISOString(),content:result.content}));
    throw Error(toolFailure(name,result));
  }
  if (result.structuredContent) return result.structuredContent;
  const text = (result.content || []).filter(x=>x.type==='text').map(x=>x.text).join('\n');
  try { return JSON.parse(text); } catch {
    if(['name_session','tabs'].includes(name))return {text};
    if(name==='evaluate'){
      const saved=text.match(/saved to:\s*(.+)$/m)?.[1]?.trim();
      const full=saved?await fs.readFile(saved,'utf8'):text;
      const clean=full.replace(/^\[UNTRUSTED_PAGE_CONTENT[^\n]*\n/,'').replace(/\n\[END_UNTRUSTED_PAGE_CONTENT[^\]]*\][\s\S]*$/,'').trim();
      try{return {value:JSON.parse(clean)};}catch{}
      await fs.writeFile(path.join(C,'neo_evaluate_protocol.txt'),text);
    }
    throw Error('neo 返回缺少结构化结果：' + name);
  }
}
async function run(code) {
  const result = await call('run', {code,timeout:30000});
  if (!result.ok) throw Error(result.error || 'neo run 失败');
  return result.value;
}
const stFile = path.join(C, 'neo_state.json');
let st = {}; try { st = JSON.parse(await fs.readFile(stFile,'utf8')); } catch {}
await rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'codex',version:'xunpan-windows-port'}});
await rpc('notifications/initialized', {}, true);
await call('name_session',{name:'xunpan port',category:'testing-and-qa',summary:'Windows inquiry workflow migration verification'});
await call('tabs',{action:'list'});
const before=await run("return (await browser.pages.list()).map(p=>({id:p.pageId}));");
// 重连后按独有会话组回收，绝不接管用户或其他任务的标签。
const tab = await call('tabs',{action:'new',url:'about:blank',...(st.groupId ? {groupId:st.groupId}: {})});
// tabs 的结构化形状由下面的 run 以公开 SDK 固定返回形状取得。
const own = await run("return (await browser.pages.list()).filter(p=>p.ownership==='mine').map(p=>({id:p.pageId,url:p.url}));");
const active = newPage(before,own);
let pageId = active.id;
const chatJob=['chat_list.mjs','chat_read.mjs','send.mjs'].includes(script);
let persistentChat=null;
if(chatJob){
  for(const p of own.filter(p=>p.url.startsWith('https://air.1688.com/'))){
    try{await run(`return (await browser.page(${p.id}).snapshot({depth:1})).url;`);persistentChat=p;break;}catch{}
  }
}
if(persistentChat){
  const redundant=own.filter(p=>p.id!==persistentChat.id&&(p.url.startsWith('https://air.1688.com/')||p.id===active.id)).map(p=>p.id);
  await run(`for(const id of ${JSON.stringify(redundant)}){try{await browser.page(id).close();}catch{}}return true;`);
  pageId=persistentChat.id;
}
// 保存 groupId，后续工具重连回到同一任务组。
const inventory = await call('tabs',{action:'list'});
// groupId 仅在 tabs 公开返回中存在时保存，不猜测页面句柄。
const groupId=inventory.groupId||inventory.text?.match(/groupId[=: ]+["']?([^\s"')]+)/)?.[1];
const listedGroup=inventory.text?.match(new RegExp('\\['+pageId+'\\][^\\n]*\\[group ([A-F0-9]+)\\]'))?.[1];
if (listedGroup||groupId) { st.groupId=listedGroup||groupId; await fs.writeFile(stFile,JSON.stringify(st)); }
const done = async value => { await fs.writeFile(path.join(C,NAME+'.out.json'),JSON.stringify(value)); throw {done:true}; };
function pageHandle(id) {
  const execute = code => run(`const p=browser.page(${id}); ${code}`);
  const nativeNode=selector=>execute(`const r=await p.cdp('Runtime.evaluate',JSON.stringify({expression:${JSON.stringify(`(()=>{for(const f of document.querySelectorAll('iframe')){try{const d=f.contentDocument;if(d.querySelector('pre[contenteditable=true]'))return d.querySelector(${JSON.stringify(selector)});}catch{}}return null;})()`)},returnByValue:false}));if(!r.result?.objectId)throw Error('找不到已核实聊天控件');const d=await p.cdp('DOM.describeNode',JSON.stringify({objectId:r.result.objectId}));return {backendNodeId:d.node.backendNodeId,name:d.node.localName,attributes:d.node.attributes};`);
  return {label:'neo-'+id,
    goto: url=>execute(`const current=await p.snapshot();if(current.url.split('#')[0]!==${JSON.stringify(url)}.split('#')[0])await p.goto(${JSON.stringify(url)});return true;`),
    evaluate:async(fn,arg)=>{
      if(fn!==sitePolicy){
        const result=await execute(`return await p.evaluate(${fn.toString()},${JSON.stringify(arg)??'undefined'});`);
        return evaluateValue(result,file=>fs.readFile(file,'utf8'));
      }
      const result=await call('evaluate',{page:id,code:`return await (${fn.toString()})(${JSON.stringify(arg)??'undefined'});`,maxChars:200000});
      if(!Object.hasOwn(result,'page')&&Object.hasOwn(result,'value'))return result.value;
      return evaluateValue(result,file=>fs.readFile(file,'utf8'));
    },
    waitForFunction:async(fn,arg,options={})=>{
      const end=Date.now()+(options.timeout||10000);
      do{
        const duration=Math.max(1,Math.min(20000,end-Date.now()));
        const evaluated=await execute(`return await p.evaluate(async arg=>{const end=Date.now()+${duration};const fn=${fn.toString()};while(Date.now()<end){if(fn(arg))return true;await new Promise(r=>setTimeout(r,250));}return false;},${JSON.stringify(arg)??'undefined'});`);
        const matched=await evaluateValue(evaluated,file=>fs.readFile(file,'utf8'));
        if(matched===true)return true;
        if(matched!==false)throw Error('等待页面返回无效结果');
      }while(Date.now()<end);
      throw Error('等待条件超时');
    },
    waitForTimeout: async ()=>{},
    snapshot:()=>execute('return (await p.snapshot()).text;'),
    click:ref=>execute(`return await p.click(${JSON.stringify(ref)});`),
    insertText:text=>execute(`return await p.insertText(${JSON.stringify(text)});`),
    clearDraft:async expected=>{
      const node=await nativeNode('pre[contenteditable=true]');
      const check=await execute(`return await p.evaluate(()=>[...document.querySelectorAll('iframe')].some(f=>{try{return f.contentDocument.querySelector('pre[contenteditable=true]')?.innerText.trim()===${JSON.stringify(expected.trim())};}catch{return false;}}));`);
      if(await evaluateValue(check,file=>fs.readFile(file,'utf8'))!==true)throw Error('自有草稿已变化');
      return execute(`await p.cdp('DOM.focus',JSON.stringify({backendNodeId:${node.backendNodeId}}));await p.press('Control+A');await p.press('Backspace');return true;`);
    },
    upload:(ref,files)=>execute(`return await p.upload(${JSON.stringify(ref)},${JSON.stringify(files)});`),
    nativeNode,
    focusEditor:async()=>{const node=await nativeNode('pre[contenteditable=true]');if(node.name!=='pre')throw Error('输入框类型错误');return execute(`return await p.cdp('DOM.focus',JSON.stringify({backendNodeId:${node.backendNodeId}}));`);},
    uploadImage:async files=>{const node=await nativeNode("input[type=file][accept='image/*']");if(node.name!=='input')throw Error('上传控件类型错误');return execute(`return await p.cdp('DOM.setFileInputFiles',JSON.stringify({backendNodeId:${node.backendNodeId},files:${JSON.stringify(files)}}));`);},
    url:()=>execute('return (await p.snapshot()).url;')};
}
const jobPages=new Map();
const pageFor = async label=>{
  if(jobPages.has(label))return jobPages.get(label);
  let id=pageId;
  if(jobPages.size)id=await run("const page=await browser.open('about:blank');return page.id;");
  const handle=pageHandle(id);jobPages.set(label,handle);return handle;
};
const blocked = async p=>{
  const detected=await p.evaluate(()=>{
    const visible=element=>{const r=element.getBoundingClientRect(),s=getComputedStyle(element);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
    const docs=[document,...[...document.querySelectorAll('iframe')].filter(visible).map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)];
    // 隐藏的登录 iframe 不代表当前掉登录，聊天原文里提到“验证码”也不当作验证控件。
    return /login\.(1688|taobao)|punish|_____tmd_____/.test(location.href)||docs.some(d=>{
      const text=d.body?.innerText||'';
      return /拖动下方滑块|请完成安全验证|请拖动.*滑块|操作频繁|账号存在风险|请先登录|请登录后/.test(text)||
        [...d.querySelectorAll('#nc_1_wrapper,.nc-container,[id*="captcha"],input[placeholder*="验证码"]')].some(visible);
    });
  });
  if(detected!==true&&detected!==false)throw Error('风险检查没有有效结果，停止');
  if(detected)await fs.writeFile(path.join(C,'neo_paused.json'),JSON.stringify({原因:'出现验证、风险或掉登录；等待用户明确继续',时间:new Date().toISOString()}));
  return detected;
};
const chatUrl=(ww,offerId)=>`https://air.1688.com/app/ocms-fusion-components-1688/def_cbu_web_im/index.html?touid=cnalichn${encodeURIComponent(ww)}&siteid=cnalichn&status=1&offerId=${offerId}`;
try {
  if (script==='probe.mjs') {
    const value=await run(`const p=browser.page(${pageId});const s=await p.snapshot();await p.close();return {provider:'BrowserOS neo',url:s.url,readonly:true};`);
    await done(value);
  }
  const source=await fs.readFile(path.join(dir,script==='send.mjs'?'send_neo.mjs':script),'utf8');
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  const cacheFs={...fs,writeFile:async(filename,...args)=>{
    const target=path.basename(filename)==='state.json'?stFile:filename;
    if(path.basename(target)==='send.progress.json'){
      await writeSendProgress(target,...args);
    }else await fs.writeFile(target,...args);
  }};
  await new AsyncFunction('pageFor','st','fs','path','C','job','done','blocked','chatUrl','sitePolicy',source)(pageFor,st,cacheFs,path,C,job,done,blocked,chatUrl,sitePolicy);
} catch(error) {
  if (!error?.done){
    let progress={};if(script==='send.mjs')progress=JSON.parse(await fs.readFile(path.join(C,'send.progress.json'),'utf8').catch(()=>'{}'));
    const message='BrowserOS neo 停止：'+String(error.message||error).slice(0,200);
    let safe=script!=='send.mjs'||progress.阶段==='准备';
    if(script==='send.mjs'&&safe){
      for(const p of jobPages.values()){
        try{if(await blocked(p)){safe=false;break;}}catch{}
      }
    }
    await fs.writeFile(path.join(C,NAME+'.out.json'),JSON.stringify({...progress,...(error.progressPendingPath?{进度待提交文件:error.progressPendingPath}:{}),错误:message,可重试:safe,...(script==='send.mjs'?{结果:'停止:'+message}:{})}));
  }
} finally {
  if(script!=='probe.mjs'){
    const result=JSON.parse(await fs.readFile(path.join(C,NAME+'.out.json'),'utf8').catch(()=>'{}'));
    if(!result.同步待确认&&((!result.错误&&!String(result.结果||'').startsWith('停止'))||result.可重试)){
      const ids=[...jobPages.values()].map(p=>+p.label.slice(4)).filter(id=>!chatJob||id!==pageId);if(!ids.length&&!chatJob)ids.push(pageId);
      await run(`for(const id of ${JSON.stringify(ids)})await browser.page(id).close();return true;`).catch(()=>{});
    }
  }
}
