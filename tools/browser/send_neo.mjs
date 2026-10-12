// 未通过发送实测前保持禁用；三项核对、只用粘贴和发送按钮。
const chat=await pageFor('send');
const out={ww:job.ww,offerId:job.offerId};
const stop=why=>done({...out,结果:'停止:'+why});
await chat.goto(chatUrl(job.ww,job.offerId));
if(await blocked(chat))await stop('出现验证或掉登录');
const state=()=>chat.evaluate(ww=>{
  for(const f of document.querySelectorAll('iframe')){try{
    const d=f.contentDocument,ed=d.querySelector('pre[contenteditable=true]');if(!ed)continue;
    const hd=d.querySelector('.conversation-header')?.textContent.trim()||'';
    if(/若长时间未加载/.test(d.body.innerText))return {blocked:true};
    const mine=[...d.querySelectorAll('.message-item.self')].map(m=>({t:m.querySelector('.time')?.textContent.trim(),text:(m.querySelector('pre.edit')?.innerText||m.querySelector('.content')?.innerText||'').trim()}));
    return {ok:!!hd&&hd.startsWith(ww),hd,mine,box:ed.innerText};
  }catch{}}return null;
},job.ww);
const s0=await state();if(!s0||s0.blocked)await stop('聊天未加载或断线，不重试');
if(!s0.ok)await stop('收件人对不上');
const norm=x=>(x||'').replace(/\r/g,'').trim();
const draft=norm(s0.box)===norm(job.text);
if(s0.box.trim()&&!draft)await stop('输入框原本有内容');
if(job.dry)await done({...out,结果:'演练通过'});
out.打开时={页头:s0.hd,我方条数:s0.mine.length};
const refs=(snap,pattern)=>snap.split('\n').filter(l=>pattern.test(l)).map(l=>l.match(/\[ref=(e\d+)\]/)?.[1]).filter(Boolean);
if(job.img&&!draft){
  const files=refs(await chat.snapshot(),/file|上传图片|选择图片/i);
  if(files.length!==1)await stop('无法唯一定位图片上传入口');
  await chat.upload(files[0],[job.img]);
  await chat.waitForFunction(n=>[...document.querySelectorAll('iframe')].some(f=>{try{const m=[...f.contentDocument.querySelectorAll('.message-item.self')];return m.length===n+1&&!!m[n].querySelector('.content img');}catch{return false;}}),s0.mine.length,{timeout:20000});
  const si=await state();out.图已发=si?.mine.length===s0.mine.length+1;
  if(!out.图已发)await stop('图片新增条数不等于1');s0.mine=si.mine;
}
if(!draft){
  const editors=refs(await chat.snapshot(),/textbox|请输入消息|contenteditable/i);
  if(editors.length!==1)await stop('无法唯一定位聊天输入框');
  await chat.click(editors[0]);await chat.insertText(job.text);
}
const s1=await state();out.核对={收件人:!!s1?.ok,内容一致:norm(s1?.box)===norm(job.text),未误发:s1?.mine.length===s0.mine.length};
if(!Object.values(out.核对).every(Boolean))await stop('发送前三项核对不通过');
if(await blocked(chat))await stop('发送前出现验证或掉登录');
const buttons=refs(await chat.snapshot(),/button.*发送/);
if(buttons.length!==1)await stop('发送按钮不是唯一');
await chat.click(buttons[0]);
await chat.waitForFunction(n=>[...document.querySelectorAll('iframe')].some(f=>{try{return f.contentDocument.querySelectorAll('.message-item.self').length>n;}catch{return false;}}),s1.mine.length,{timeout:10000});
const s2=await state(),added=s2?.mine.slice(s1.mine.length)||[];
out.发后新增条数=added.length;out.发送时间=added[0]?.t||null;
out.结果=added.length===1&&norm(added[0].text)===norm(job.text)&&!norm(s2.box)?'成功':'异常';
await done(out);
