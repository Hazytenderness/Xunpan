// SDK evaluate 的内联/文件返回，以及本轮新建标签的识别。
export function toolFailure(name,result){
  const text=(result.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');
  return text.match(/网站(?:同步门禁|草稿保存)失败：[^\r\n]*/)?.[0]?.slice(0,240)||'neo 工具失败：'+name;
}

export async function evaluateValue(result,readText){
  if(result&&typeof result==='object'){
    if(result.error||result.exceptionDetails)throw Error(typeof result.error==='string'?result.error:'页面执行失败');
    if(result.writtenToFile||result.file){
      const filename=result.path||result.file;
      if(!filename||!readText)throw Error('页面结果已写入文件，但没有可读文件路径');
      const text=await readText(filename);
      const clean=text.replace(/^\[UNTRUSTED_PAGE_CONTENT[^\n]*\r?\n/,'')
        .replace(/\r?\n\[END_UNTRUSTED_PAGE_CONTENT[^\]]*\]\s*$/,'').trim();
      return JSON.parse(clean);
    }
    if(Object.hasOwn(result,'page'))return Object.hasOwn(result,'value')?result.value:null;
  }
  if(result===undefined)throw Error('页面执行没有返回结果');
  return result;
}

export function newPage(before,after){
  const known=new Set(before.map(p=>p.id));
  const fresh=after.filter(p=>!known.has(p.id)&&p.url==='about:blank');
  if(fresh.length!==1)throw Error('无法唯一识别本轮新建的neo标签');
  return fresh[0];
}
