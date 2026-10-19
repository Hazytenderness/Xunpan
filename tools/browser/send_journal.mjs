// 只重试本地进度替换；调用方的浏览器动作不在重试范围内。
import fs from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

export async function writeSendProgress(filename,data,options,{fsOps=fs,platform=process.platform,sleep=delay}={}){
  const pending=filename+'.'+process.pid+'.'+randomUUID()+'.pending';
  await fsOps.writeFile(pending,data,options);
  const waits=[50,100,200,400,800];
  for(let attempt=0;;attempt++){
    try{await fsOps.rename(pending,filename);return;}
    catch(error){
      if(platform!=='win32'||!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt===waits.length){
        error.progressPendingPath=pending;
        throw error;
      }
      await sleep(waits[attempt]);
    }
  }
}
