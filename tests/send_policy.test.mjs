import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSendJob} from '../tools/browser/send_policy.mjs';

test('direct browser bridge refuses screenshot-style unregistered messages',()=>{
  assert.throws(()=>validateSendJob({ww:'unregistered-policy-test',offerId:'123',text:'您好，询问链接123，普通OPP袋即可，仅作询价。'}),/话术校验未通过/);
});
test('recipient-only dry runs remain available without sending text',()=>{
  assert.doesNotThrow(()=>validateSendJob({dry:true}));
});
