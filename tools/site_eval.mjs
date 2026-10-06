// 用 ATAO 运营台同一套公式评估复核条目：当前值、采纳前后的单价成本、利润率和计费重。
// 用法：node tools/site_eval.mjs <站点目录> < 条目.json > 结果.json
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';

const site = process.argv[2];
const ctx = vm.createContext({ URL, console });
ctx.window = ctx;
const js = f => path.join(site, 'build/js', f);
vm.runInContext(fs.readFileSync(js('products.js'), 'utf8'), ctx);
if (fs.existsSync(js('products-sources.js'))) {
  vm.runInContext(fs.readFileSync(js('products-sources.js'), 'utf8'), ctx);
  for (const x of ctx.DECK) if (!x.货源候选 && ctx.DECK_SOURCES?.[x.序]) x.货源候选 = ctx.DECK_SOURCES[x.序];
}
for (const f of ['selection-core.js', 'review-core.js']) vm.runInContext(fs.readFileSync(js(f), 'utf8'), ctx);
const { SelectionCore: core, ReviewCore: R, DECK } = ctx;
const products = new Map(DECK.map(x => [x.序, x]));
const kg = v => v ? Math.max(v.长 && v.宽 && v.高 ? v.长 * v.宽 * v.高 / core.rules.体积除数 : 0, (v.重量克 || 0) / 1000) : null;
const items = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = items.map(item => {
  const product = products.get(+item.序);
  if (!product) return { 找到: false };
  const before = core.metrics(product, {});
  const row = item.字段 === '采购单价' ? { 核价: { 单价: +item.新值 } } : item.字段 === '单品包装' ? { 包装: item.新值 } : {};
  const after = core.metrics(product, row);
  const current = R.current(product, {}, { 字段: item.字段, 候选ID: String(item.候选ID || '') });
  return {
    找到: true, 原值: current ?? null, 名: String(product.名 || ''),
    前利润率: before.margin, 后利润率: after.margin, 前成本: before.cost,
    原计费重: item.字段 === '单品包装' ? kg(current) : null, 新计费重: item.字段 === '单品包装' ? kg(item.新值) : null,
  };
});
process.stdout.write(JSON.stringify(out));
