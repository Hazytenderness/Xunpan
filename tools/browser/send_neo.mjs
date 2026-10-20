// 未通过发送实测前保持禁用；三项核对、只用粘贴和发送按钮。
const chat=await pageFor('send');
const out={ww:job.ww,offerId:job.offerId,operation_id:job.operation_id,阶段:'准备'};
const stage=async name=>{out.阶段=name;if(job.operation_id)await fs.writeFile(path.join(C,'send.progress.json'),JSON.stringify(out));};
const stop=why=>done({...out,结果:'停止:'+why});
const inHours=()=>{const h=(new Date().getUTCHours()+8)%24;return h>=9&&h<18;};
const windowEnd=()=>done({...out,结果:'暂缓:已到18点',时段结束:true});
await chat.goto(chatUrl(job.ww,job.offerId));
if(await blocked(chat))await stop('出现验证或掉登录');
try{await chat.waitForFunction(()=>[...document.querySelectorAll('iframe')].some(f=>{try{const d=f.contentDocument,h=d.querySelector('.conversation-header .go-shop-container');return !!d.querySelector('pre[contenteditable=true]')&&!!h&&[...h.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());}catch{return false;}}),undefined,{timeout:60000});}
catch{if(await blocked(chat))await stop('出现验证或掉登录');await done({...out,结果:'停止:聊天输入框暂未加载',可重试:true});}
if(await blocked(chat))await stop('出现验证或掉登录');
const state=()=>chat.evaluate(ww=>{
  for(const f of document.querySelectorAll('iframe')){try{
    const d=f.contentDocument,ed=d.querySelector('pre[contenteditable=true]');if(!ed)continue;
    const header=d.querySelector('.conversation-header .go-shop-container');
    const hd=header?[...header.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim():'';
    if(/若长时间未加载/.test(d.body.innerText))return {blocked:true};
    const mine=[...d.querySelectorAll('.message-item.self')].map(m=>({t:m.querySelector('.time')?.textContent.trim(),text:(m.querySelector('pre.edit')?.innerText||m.querySelector('.content')?.innerText||'').trim()}));
    const history=[...d.querySelectorAll('.message-item')].map(m=>({
      self:m.classList.contains('self'),text:(m.querySelector('pre.edit')?.innerText??m.querySelector('.content')?.innerText??'').trim(),
      images:[...m.querySelectorAll('img.imui-msg-img')].map(i=>i.src),videos:[...m.querySelectorAll('video')].map(v=>v.src||v.currentSrc).filter(Boolean)
    })).slice(-8);
    return {ok:!!hd&&hd===ww,hd,mine,history,box:ed.innerText};
  }catch{}}return null;
},job.ww);
const s0=await state();if(!s0||s0.blocked)await done({...out,结果:'停止:聊天暂未加载',可重试:true});
if(!s0.ok)await done({...out,结果:'停止:收件人对不上',实际页头:s0.hd});
const norm=x=>(x||'').replace(/\r/g,'').trim();
const historyKey=h=>JSON.stringify(h?.map(m=>[m.self,norm(m.text),m.images||[],m.videos||[]]));
// 恢复只读聊天，永远不进入粘贴/发图/发送分支。只接受绝对时间的正面证据。
if(job.recover_only){
  const matches=s0.mine.filter(m=>norm(m.text)===norm(job.text));
  const proven=matches.map(m=>({...m,stamp:/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(m.t||'')?Date.parse(m.t.replace(' ','T')+'+08:00')/1000:0}))
    .filter(m=>job.intent_time>0&&m.stamp>=Math.floor(job.intent_time)&&m.stamp<=Date.now()/1000);
  if(proven.length===1)await done({...out,结果:'成功',回执恢复:true,sent_at:proven[0].stamp,
    核对:{收件人:true,内容一致:true,未误发:true},聊天证据:proven[0]});
  await done({...out,结果:'停止:未取得唯一且有绝对时间的发送证据'});
}
if(s0.mine.some(m=>norm(m.text)===norm(job.text)))await done({...out,结果:'跳过:最新聊天已有相同内容',聊天证据:s0.mine.filter(m=>norm(m.text)===norm(job.text))});
if(job.expected_history&&historyKey(s0.history)!==historyKey(job.expected_history))
  await done({...out,结果:'跳过:最新聊天已变化，重新读取分析',需重读:true,最新聊天:s0.history,原分析聊天:job.expected_history});
const draft=norm(s0.box)===norm(job.text);
if(s0.box.trim()&&!draft){
  if(!job.dry&&job.owned_draft&&norm(s0.box)===norm(job.owned_draft)&&chat.clearDraft){
    await chat.clearDraft(job.owned_draft);
    s0.box='';
  }else await done({...out,结果:'暂缓:输入框有未确认归属的草稿',草稿冲突:true,已点击发送:false});
}
if(job.dry){
  const editor=chat.nativeNode?await chat.nativeNode('pre[contenteditable=true]'):null;
  const image=chat.nativeNode?await chat.nativeNode("input[type=file][accept='image/*']"):null;
  await done({...out,结果:'演练通过',编辑器:editor?.name,图片控件:image?.name});
}
// 发前按网站实时成本再次核对：食品接触、不做、倍数≤2、已经补齐的都不再询盘。
if(!job.seqs?.length)await stop('没有对应产品编号');
const site=await pageFor('site');await site.goto('https://ataous.com/#review');
await site.waitForFunction(()=>{
  const sync=document.getElementById('syncStatus');
  if(sync?.dataset.state==='error')throw Error('网站同步门禁失败：'+sync.textContent.slice(0,200));
  return !!window.jp云?.能写不()&&!!window.ReviewCore&&window.SelectionCore?.sourcesReady()&&sync?.dataset.state==='ok';
},undefined,{timeout:25000});
const current=await site.evaluate(sitePolicy,{apply:false,readOnly:true});
if(current.采纳失败.length)await stop('网站采纳有失败项，先处理数据');
if(current.变更款.length){
  try{await site.waitForFunction(()=>{
    const sync=document.getElementById('syncStatus');
    if(sync?.dataset.state==='error')throw Error('网站同步门禁失败：'+sync.textContent.slice(0,200));
    return sync?.dataset.state==='ok';
  },undefined,{timeout:25000});}
  catch(error){await done({...out,结果:'暂缓:网站同步待确认',同步待确认:true,错误:'网站修改已留在草稿，保留标签等待验收：'+String(error.message||error).slice(0,200)});}
}
const permitted=new Set(current.可询盘.map(x=>x.序));
if(job.seqs.some(n=>!permitted.has(+n)))await done({...out,结果:'跳过:网站最新筛选排除或资料已齐'});
for(const target of job.targets||[]){
  const latest=current.可询盘.find(p=>p.序===+target.seq);
  if(latest.asin!==target.asin)await done({...out,结果:'跳过:网站代表ASIN已变更，需重新核页'});
  if(latest.候选ID&&!latest.候选ID.includes(String(job.offerId)))await done({...out,结果:'跳过:供应商已不在网站当前候选，需重新核页'});
}
for(const seq of job.seqs){
  const latest=current.可询盘.find(p=>p.序===+seq);
  if(!latest.可询盘候选ID?.includes(String(job.offerId)))await done({...out,结果:'跳过:当前候选尚未通过核页核SKU，暂不询盘'});
}
out.打开时={页头:s0.hd,我方条数:s0.mine.length};
const refs=(snap,pattern)=>snap.split('\n').filter(l=>pattern.test(l)).map(l=>l.match(/\[ref=(e\d+)\]/)?.[1]).filter(Boolean);
if(job.img&&!draft){
  if(!inHours())await windowEnd();
  await stage('图片上传前');
  await chat.uploadImage([job.img]);
  await chat.waitForFunction(n=>[...document.querySelectorAll('iframe')].some(f=>{try{const m=[...f.contentDocument.querySelectorAll('.message-item.self')];return m.length===n+1&&!!m[n].querySelector('.content img');}catch{return false;}}),s0.mine.length,{timeout:20000});
  const si=await state();out.图已发=si?.mine.length===s0.mine.length+1;
  if(out.图已发)await fs.writeFile(path.join(C,'send.progress.json'),JSON.stringify({...out,图已发:true}));
  if(!out.图已发)await stop('图片新增条数不等于1');s0.mine=si.mine;s0.history=si.history;
}
if(!draft){
  await stage('粘贴前');
  if(chat.focusEditor)await chat.focusEditor();
  else{const editors=refs(await chat.snapshot(),/textbox|请输入消息|contenteditable/i);if(editors.length!==1)await stop('无法唯一定位聊天输入框');await chat.click(editors[0]);}
  await chat.insertText(job.text);
}
const s1=await state();out.核对={收件人:!!s1?.ok,内容一致:norm(s1?.box)===norm(job.text),未误发:s1?.mine.length===s0.mine.length};
if(historyKey(s1?.history)!==historyKey(s0.history))
  await done({...out,结果:'暂缓:准备发送期间聊天已变化，保留草稿重新分析',需重读:true,已点击发送:false,
    自有草稿:norm(s1?.box)===norm(job.text)?job.text:null});
if(!Object.values(out.核对).every(Boolean))await stop('发送前三项核对不通过');
if(await blocked(chat))await stop('发送前出现验证或掉登录');
const buttons=refs(await chat.snapshot(),/button.*发送/);
if(buttons.length!==1)await stop('发送按钮不是唯一');
if(!inHours())await windowEnd();
await stage('发送点击前');out.已点击发送=true;
await chat.click(buttons[0]);
await chat.waitForFunction(n=>[...document.querySelectorAll('iframe')].some(f=>{try{return f.contentDocument.querySelectorAll('.message-item.self').length>n;}catch{return false;}}),s1.mine.length,{timeout:10000});
const s2=await state(),added=s2?.mine.slice(s1.mine.length)||[];
out.发后新增条数=added.length;out.发送时间=added[0]?.t||null;
out.结果=added.length===1&&norm(added[0].text)===norm(job.text)&&!norm(s2.box)?'成功':'异常';
if(out.结果==='成功')out.sent_at=Date.now()/1000;
await done(out);
