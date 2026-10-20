import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export function validateSendJob(job){
  const validator=fileURLToPath(new URL('../lib/send_policy.py',import.meta.url));
  const command=process.env.XUNPAN_PYTHON||(process.platform==='win32'?'python':'python3');
  const result=spawnSync(command,['-X','utf8',validator],{input:JSON.stringify(job),encoding:'utf8',windowsHide:true});
  if(result.error||result.status!==0)throw Error('话术校验未通过：'+(result.error?.message||result.stderr?.trim()||'校验器未运行'));
}
