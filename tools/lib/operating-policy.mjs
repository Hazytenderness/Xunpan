// 日本站当前运营规则。倍数始终调用网站 SelectionCore，不另建成本公式。
export function policyAction(options={}) {
  const root=globalThis,core=root.SelectionCore,R=root.ReviewCore;
  if(!core||!R)throw Error('网站公式尚未加载');
  if(options.apply&&(!root.jp云?.能写不()||root.ATAO站?.conf().key!=='jp'))throw Error('日本站未登录或无写权限');
  const data=structuredClone(options.rows||root.jp谈.读()),deck=root.DECK||[];
  const products=new Map(deck.map(p=>[p.序,p])),time=new Date().toISOString(),actor='询盘AI（用户授权）';
  const accepted=[],errors=[],excluded=[],protectedRows=[],eligible=[],changed=new Set();
  for(const [number,row] of Object.entries(data)){
    const p=products.get(+number);if(!p)continue;
    for(const [id,e] of Object.entries(row.复核||{})){
      if(e.状态!=='待复核')continue;
      try{data[number]=R.accept(p,data[number],id,undefined,actor,time);accepted.push({序:+number,id,字段:e.字段});changed.add(+number);}
      catch(error){errors.push({序:+number,id,字段:e.字段,原因:error.message});}
    }
  }
  function foodReason(p){
    const kind=typeof root.productKind==='function'?root.productKind(p):'';
    const cat=String(p.类||''),title=String(p.名||'');
    if(String(p.部||'').includes('宠物')||cat.startsWith('ペット用品:'))return '';
    const translated=cat.split(':').map(k=>root.CATEGORY_ZH?.[k]||k).join(':');
    // 用末级用途，不能把“便当箱与水壶”父类下的便当袋、杯套也算直接接触。
    const leaf=cat.split(':').at(-1),type=kind+' '+leaf+' '+(root.CATEGORY_ZH?.[leaf]||'');
    if(+p.序===2687)return '用户明确排除排水口滤篮';
    if(/水切りラック|水切りカゴ|コランダー|沥水篮|沥水架|滤篮/.test(type))return '用户排除沥水/滤篮类';
    // 放餐具或已包装食品的外部收纳件不等于食品接触件。
    if(/ラック|スタンド|収納カート|ワゴン|フック|研ぎ器|食器台|エプロン|食器棚シート|ランチクロス|保温・保冷カバー|ランチバッグ|巾着|ランチベルト/.test(leaf))return '';
    if(/包丁立て|包丁差し|ナイフブロック|カトラリー(?:ケース|トレイ|収納)|箸立て|刀架|餐具收纳架|餐具收纳盒/.test(type+' '+title))return '';
    if(/水切りマット|シンクマット/.test(leaf)&&!/石鹸|ソープ|IHマット|IHカバー/.test(title))return '厨房沥水垫，排除可能直接接触食品的用途';
    if(/米びつ|スライサー|カッター|丼|アイスクリームカップ|かす揚げ|あく取り|ワインストッパー|バキュームポンプ|トレイ・盆|天ぷら敷紙|アイスペール|トング|ピーラー|皮むき器|しゃもじ|飯碗|サラダプレート|整水器交換|水栓一体型用カートリッジ/.test(type))return '食品/饮水直接接触类别：'+leaf;
    const human=/一次性(?:饮料杯|餐具)|食器|カトラリー|調理器具|製菓|保存容器|弁当箱|水筒・マグ|タンブラー|カップ・マグ|包丁|フライパン|鍋|せいろ|スプーン|フォーク|ナイフ|箸|皿|茶碗|湯呑|急須|ボウル|ざる|製氷|計量カップ|(?:水壶与保温杯|餐具|刀叉|筷子|砧板|切菜板|便当盒|饭盒|餐盘|餐碗|马克杯|咖啡杯|茶杯|饮料杯|酒杯|调味|保鲜与储物容器|食品储存|沥水篮|沥水架|滤篮|漏勺|喷油器|菜刀|厨房刀具|蒸笼|烘焙|蛋糕模|制冰|冰格|茶壶|茶具|锅具|煎锅|炒锅|水龙头净水滤芯)/;
    if(human.test(type))return '食品/饮水直接接触类别：'+(kind||translated);
    const named=/まな板|包丁|調理用|料理用|菜刀|食材|食品用|食品保存|食器用|弁当箱|ランチボックス|製菓用|調味料|オイルスプレー|フルーツ.*(?:洗|水切)|果蔬.*(?:清洗|沥水)|水果.*(?:清洗|沥水)/;
    if(named.test(title))return '食品接触用途：'+(title.match(named)||[''])[0];
    return '';
  }
  for(const p of deck){
    if(p.历史目录)continue;
    const row=data[p.序]||{},m=core.metrics(p,row),multiple=core.multiple(m),food=foodReason(p);
    const reason=food||(Number.isFinite(multiple)&&multiple<2?'最新倍数小于2（'+multiple.toFixed(4)+'）':'');
    const orders=root.jp订单?.读()?.[p.序]||[];
    const record={序:p.序,asin:p.asin,名:p.名,类:p.类,倍数:multiple,采购价:m.cost,原因:reason,
      候选ID:(root.DECK_SOURCES?.[p.序]||p.货源候选||[]).map(q=>String(q.候选ID)),
      可询盘候选ID:(typeof core.supplierQuotes==='function'?core.supplierQuotes(p,row):(root.DECK_SOURCES?.[p.序]||p.货源候选||[]))
        .filter(q=>!q.历史报价&&['完全匹配','部分匹配'].includes(q.匹配度?.等级)).map(q=>String(q.候选ID))};
    if(reason){
      const round=core.round(row,orders,p);
      if(row.确||orders.length||row.选品?.采购台保留===true||row.选品?.负责人||row.选品?.已移交||['已下单','已确认','第三轮·采购中'].includes(round)){protectedRows.push(record);continue;}
      excluded.push({...record,已不做:row.选品?.阶段==='不做'});
      if(row.选品?.阶段!=='不做'){
        const selection={...(row.选品||{}),工作流版本:2,阶段:'不做',排除原因:reason,排除时间:time,排除处理人:actor};
        delete selection.负责人;data[p.序]={...row,选品:selection};changed.add(p.序);
      }
    }else if(Number.isFinite(multiple)&&multiple>2&&row.选品?.阶段!=='不做'){
      const state=core.reviewState(p,row,orders),pending=core.rerunPending(row);
      const inquiry=Object.values(row.复核||{}).some(e=>e.来源==='询盘回复'||e.来源==='供应商询盘确认');
      const plans=row.询价方案||[];
      const missing=inquiry&&!orders.length&&!row.确&&!row.选品?.负责人&&!row.选品?.已移交&&plans.some(q=>!q.历史报价&&['贴标','中性包装','每箱数量','实拍图','视频'].some(k=>q[k]===undefined||q[k]===''));
      eligible.push({...record,状态:state,可询盘:state==='待核对'||pending||missing,补充询盘资料:missing,食品接触:false});
    }
  }
  if(options.apply&&changed.size){
    if(!root.jp谈.存(data))throw Error('网站草稿保存失败：'+String(root.document?.getElementById('syncStatus')?.textContent||'未持久保存，停止').slice(0,200));
    root.jp记?.([...changed][0],'AI按用户授权采纳与筛选',accepted.length+'项采纳，'+excluded.filter(x=>!x.已不做).length+'款不做；门槛为最新倍数>2且非食品接触');
    root.jp刷?.();
  }
  return {时间:time,apply:!!options.apply,采纳:accepted,采纳失败:errors,排除:excluded,保护已有采购:protectedRows,
    ...(options.includeRows?{行:data}:{}),
    可询盘:eligible.filter(x=>x.可询盘),倍数大于2:eligible,变更款:[...changed],
    统计:{采纳:accepted.length,采纳失败:errors.length,食品排除:excluded.filter(x=>!x.原因.startsWith('最新倍数')).length,
      倍数排除:excluded.filter(x=>x.原因.startsWith('最新倍数')).length,新增不做:excluded.filter(x=>!x.已不做).length,
      保护已有采购:protectedRows.length,可询盘:eligible.filter(x=>x.可询盘).length,倍数大于2:eligible.length}};
}
