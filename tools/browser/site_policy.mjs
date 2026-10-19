// 网站当前采纳与询盘门槛：只改日本站业务数据，不部署代码。
const page=await pageFor('site');
await page.goto('https://ataous.com/#review');
await page.waitForFunction(()=>{
  const sync=document.getElementById('syncStatus');
  if(sync?.dataset.state==='error')throw Error('网站同步门禁失败：'+sync.textContent.slice(0,200));
  return !!window.jp云?.能写不()&&!!window.ReviewCore&&window.SelectionCore?.sourcesReady()&&sync?.dataset.state==='ok';
},undefined,{timeout:25000});
const result=await page.evaluate(sitePolicy,{apply:!!job.apply,includeRows:!!job.includeRows});
if(job.apply&&result.变更款.length){
  try{await page.waitForFunction(()=>{
    const sync=document.getElementById('syncStatus');
    if(sync?.dataset.state==='error')throw Error('网站同步门禁失败：'+sync.textContent.slice(0,200));
    return sync?.dataset.state==='ok';
  },undefined,{timeout:25000});}
  catch(error){await done({...result,同步待确认:true,错误:'网站修改已留在草稿，云端同步尚未确认；保留标签等待验收：'+String(error.message||error).slice(0,200)});}
}
await done(result);
