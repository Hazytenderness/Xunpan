import test from 'node:test';
import assert from 'node:assert/strict';
import {policyAction} from '../tools/lib/operating-policy.mjs';

test('latest multiples, food contact, exact cutoff and purchase protection',()=>{
  globalThis.DECK=[
    {序:1,类:'水切りカゴ',名:'沥水篮'},
    {序:2,类:'ランチバッグ',名:'便当袋'},
    {序:3,类:'ラック',名:'厨房收纳架'},
    {序:4,类:'清洁刷',名:'清洁刷'},
    {序:5,类:'清洁刷',名:'清洁刷'},
    {序:6,类:'弁当箱',名:'便当盒'},
    {序:7,类:'清洁刷',名:'清洁刷'},
    {序:2687,类:'排水口',名:'排水口滤篮'},
    {序:8,类:'米びつ',名:'米桶'},
    {序:9,类:'水切りマット',名:'硅胶沥水垫'},
    {序:10,类:'水切りマット',名:'ソープトレー 石鹸置き'},
    {序:11,类:'ペット用品:小動物:給水器・ウォーターボトル',名:'饮水器'},
    {序:12,类:'調理器具:包丁立て',名:'刀架'},
    {序:13,类:'調理器具:カトラリーケース',名:'餐具收纳盒'},
    {序:14,类:'水切りマット',名:'人工采购台的沥水垫'}
  ];
  const rows={1:{倍数:5},2:{倍数:3},3:{倍数:3},4:{倍数:1.9},5:{倍数:2},6:{倍数:4,确:true},
    7:{倍数:1,复核:{r:{状态:'待复核',字段:'采购单价'}}},2687:{倍数:10},8:{倍数:3},9:{倍数:4},10:{倍数:4},11:{倍数:3},
    12:{倍数:3},13:{倍数:3},14:{倍数:1,选品:{采购台保留:true,负责人:'测试采购员',阶段:'核价中'}}};
  globalThis.SelectionCore={metrics:(p,r)=>({cost:1,m:r.倍数}),multiple:m=>m.m,round:()=>'',reviewState:()=> '待核对',rerunPending:()=>false};
  globalThis.ReviewCore={accept:(p,r)=>({...r,倍数:3,复核:{r:{状态:'已采纳'}}})};
  globalThis.jp订单={读:()=>({})};
  const result=policyAction({rows,includeRows:true});
  assert.deepEqual(result.可询盘.map(x=>x.序),[2,3,7,10,11,12,13]);
  assert.deepEqual(result.排除.map(x=>x.序),[1,4,2687,8,9]);
  assert.equal(result.保护已有采购[0].序,6);
  assert.equal(result.行[1].选品.阶段,'不做');
  assert.equal(result.采纳.length,1);
  assert.equal(result.行[6].确,true);
  assert.deepEqual(result.行[14].选品,rows[14].选品);
  assert.ok(result.保护已有采购.some(x=>x.序===14));
});

test('failed durable save reports quota and cannot report applied policy',()=>{
  globalThis.DECK=[{序:1,类:'清洁刷',名:'清洁刷'}];
  globalThis.jp云={能写不:()=>true};globalThis.ATAO站={conf:()=>({key:'jp'})};
  globalThis.jp谈={读:()=>({1:{倍数:1}}),存:()=>false};
  globalThis.document={getElementById:()=>({textContent:'草稿持久保存失败：quota'})};
  try{assert.throws(()=>policyAction({apply:true}),/网站草稿保存失败.*quota/);}
  finally{delete globalThis.document;}
});
