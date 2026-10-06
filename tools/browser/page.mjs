// 核页：只读抓一个 1688 商品详情页。job = {url}
const page = await pageFor("p1");
try { await page.goto(job.url, { timeout: 30000 }); } catch {}
try { await page.waitForFunction(() => (window.context?.result?.data?.Root && window.context?.result?.global?.globalData?.model?.buyerModel) || /验证|登录|下架|不存在/.test(document.body?.innerText || ""), undefined, { timeout: 20000 }); } catch {}
await page.waitForTimeout(2000);
const r = await page.evaluate(() => {
  const txt = document.body?.innerText || "", c = window.context?.result;
  const block = /login\.(1688|taobao)|punish|_____tmd_____/.test(location.href) || !c?.data?.Root && /滑动|拖动.*验证|请完成安全验证|验证码|请登录/.test(txt.slice(0, 1500));
  if (!c?.data?.Root) return { block, noContext: true, textHead: txt.slice(0, 200) };
  const g = c.global.globalData.model, dj = c.data.Root.fields.dataJson, pm = c.data.mainPrice?.fields?.priceModel || {}, fp = c.data.mainPrice?.fields?.finalPriceModel || {}, sk = dj.skuModel || {}, op = dj.orderParamModel?.orderParam || {};
  return { block,
    卖家公司: g.sellerModel?.companyName ?? null, 旺旺名: g.sellerModel?.loginId ?? null, 标题: g.offerDetail?.subject ?? null, 状态: g.offerDetail?.status ?? null, 类目: g.offerDetail?.leafCategoryName ?? null,
    已登录: !!g.buyerModel?.buyerLevel || /新人价|老客价|会员价/.test(txt),
    规格属性: (sk.skuProps || []).map(x => ({ 属性: x.prop, 值: (x.value || []).map(v => v.name) })),
    规格价格: Object.entries(sk.skuInfoMap || {}).map(([name, v]) => ({ 规格: name, 价格: v.discountPrice || v.price || null, 库存: v.canBookCount ?? null })),
    规格图: (sk.skuProps || []).flatMap(x => (x.value || []).filter(v => v.imageUrl).map(v => [v.name, v.imageUrl])),
    价格展示: pm.priceDisplayType ?? null, 价格区间: pm.originalPriceDisplay ?? null, 阶梯价_登录后: pm.currentPrices ?? null,
    到手价: fp.onHandPrice ? { 价: fp.onHandPrice, 说明: fp.onHandPriceTypeText, 件数: fp.onHandPriceNum } : null,
    起订量: op.beginNum ?? null, 单位: c.data.shippingServices?.fields?.unit ?? null, 可售总量: op.canBookedAmount ?? null, 已售: op.saledCount ?? null,
    主图: (g.offerDetail?.mainImageList || g.offerDetail?.imageList || []).map(i => i.fullPathImageURI || i).slice(0, 10),
    商品属性: (g.offerDetail?.featureAttributes || []).map(a => `${a.name}:${(a.values || [a.value]).join("/")}`),
    包装信息: c.data.productPackInfo?.fields?.pieceWeightScale?.pieceWeightScaleInfo ?? null };
});
if (r.block || r.已登录 === false) await done({ 错误: r.block ? "出现验证或掉登录" : "未登录" });
await done({ ...r, url: await page.url(), 核页时间: new Date().toISOString(), ...(r.noContext ? { 备注: "页面无商品数据，可能下架或打不开" } : {}) });
