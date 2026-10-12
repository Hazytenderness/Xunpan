// BrowserOS neo 的 MCP 客户端。保留 job.json → <脚本>.out.json。
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const C = path.join(os.homedir(), '.cache', 'xunpan');
const dir = path.dirname(fileURLToPath(import.meta.url));
const script = process.argv[2];
if (!['probe.mjs','page.mjs','chat_list.mjs','chat_read.mjs','send.mjs'].includes(script)) throw Error('未知浏览器任务');
const NAME = path.parse(script).name;
const job = JSON.parse(await fs.readFile(path.join(C, 'job.json'), 'utf8'));
let policy={};try{policy=JSON.parse(await fs.readFile(path.join(C,'windows_permissions.json'),'utf8'));}catch{}
if(script==='send.mjs'&&policy.send!==true)throw Error('发送未授权');
if(script==='chat_list.mjs'&&policy.scan!==true)throw Error('扫描未授权');
if(script==='chat_read.mjs'){
  const eligible=JSON.parse(await fs.readFile(path.join(dir,'../windows_pending_chats.json'),'utf8'));
  if(!policy.chat_read_ww?.includes(job.ww)||!eligible.some(x=>x.ww===job.ww))throw Error('聊天读取未授权或不在交接39家中');
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
  if (result.isError) throw Error('neo 工具失败：' + name);
  if (result.structuredContent) return result.structuredContent;
  const text = (result.content || []).filter(x=>x.type==='text').map(x=>x.text).join('\n');
  try { return JSON.parse(text); } catch { if(['name_session','tabs'].includes(name))return {text};throw Error('neo 返回缺少结构化结果：' + name); }
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
// 重连后按独有会话组回收，绝不接管用户或其他任务的标签。
const tab = await call('tabs',{action:'new',url:'about:blank',...(st.groupId ? {groupId:st.groupId}: {})});
// tabs 的结构化形状由下面的 run 以公开 SDK 固定返回形状取得。
const own = await run("return (await browser.pages.list()).filter(p=>p.ownership==='mine').map(p=>({id:p.pageId,url:p.url}));");
const active = own.find(p=>p.url==='about:blank');
if (!active) throw Error('找不到本次新建的 neo 标签');
let pageId = active.id;
// 保存 groupId，后续工具重连回到同一任务组。
const inventory = await call('tabs',{action:'list'});
// groupId 仅在 tabs 公开返回中存在时保存，不猜测页面句柄。
const groupId=inventory.groupId||inventory.text?.match(/groupId[=: ]+["']?([^\s"')]+)/)?.[1];
const listedGroup=inventory.text?.match(new RegExp('\\['+pageId+'\\][^\\n]*\\[group ([A-F0-9]+)\\]'))?.[1];
if (listedGroup||groupId) { st.groupId=listedGroup||groupId; await fs.writeFile(stFile,JSON.stringify(st)); }
const done = async value => { await fs.writeFile(path.join(C,NAME+'.out.json'),JSON.stringify(value)); throw {done:true}; };
function pageHandle(id) {
  const execute = code => run(`const p=browser.page(${id}); ${code}`);
  return {label:'neo-'+id,
    goto: url=>execute(`await p.goto(${JSON.stringify(url)}); return true;`),
    evaluate:(fn,arg)=>execute(`return await p.evaluate(${fn.toString()},${JSON.stringify(arg)??'undefined'});`),
    waitForFunction:(fn,arg,options={})=>execute(`return await p.evaluate(async arg=>{const end=Date.now()+${Math.min(options.timeout||10000,25000)};const fn=${fn.toString()};while(Date.now()<end){if(fn(arg))return true;await new Promise(r=>setTimeout(r,250));}throw Error('等待条件超时');},${JSON.stringify(arg)??'undefined'});`),
    waitForTimeout: async ()=>{},
    snapshot:()=>execute('return (await p.snapshot()).text;'),
    click:ref=>execute(`return await p.click(${JSON.stringify(ref)});`),
    insertText:text=>execute(`return await p.insertText(${JSON.stringify(text)});`),
    upload:(ref,files)=>execute(`return await p.upload(${JSON.stringify(ref)},${JSON.stringify(files)});`),
    url:()=>execute('return (await p.snapshot()).url;')};
}
const pageFor = async ()=>pageHandle(pageId);
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
  const cacheFs={...fs,writeFile:(filename,...args)=>fs.writeFile(path.basename(filename)==='state.json'?stFile:filename,...args)};
  await new AsyncFunction('pageFor','st','fs','path','C','job','done','blocked','chatUrl',source)(pageFor,st,cacheFs,path,C,job,done,blocked,chatUrl);
} catch(error) {
  if (!error?.done) await fs.writeFile(path.join(C,NAME+'.out.json'),JSON.stringify({错误:'BrowserOS neo 停止：'+String(error.message||error).slice(0,200)}));
} finally {
  if(script!=='probe.mjs'){
    const result=JSON.parse(await fs.readFile(path.join(C,NAME+'.out.json'),'utf8').catch(()=>'{}'));
    if(!result.错误&&!String(result.结果||'').startsWith('停止'))await run(`await browser.page(${pageId}).close();return true;`).catch(()=>{});
  }
}
