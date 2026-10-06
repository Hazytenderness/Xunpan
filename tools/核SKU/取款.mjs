// 取「货源核实·待核对」且有 1688 候选的款，写 <工作目录>/products.json。
// 用法（在 ataous-site 目录运行）：node <本文件> <工作目录>，工作目录里要先放线上 purchase.json
//   CLOUDFLARE_ACCOUNT_ID=f451a19a9c22c7472e8c23bd4ca272d5 npx wrangler r2 object get "ataous-data/jp/宠物/purchase.json" --remote --file <工作目录>/purchase.json
import fs from 'node:fs'; import vm from 'node:vm';
const S = process.argv[2], js = f => 'build/js/' + f;
const ctx = vm.createContext({ URL, console }); ctx.window = ctx;
for (const f of ['products.js', 'products-sources.js', 'selection-core.js', 'review-core.js']) if (fs.existsSync(js(f))) vm.runInContext(fs.readFileSync(js(f), 'utf8'), ctx);
const { DECK, DECK_SOURCES, SelectionCore: C } = ctx;
for (const x of DECK) if (!x.货源候选 && DECK_SOURCES?.[x.序]) x.货源候选 = DECK_SOURCES[x.序];
const rows = JSON.parse(fs.readFileSync(S + '/purchase.json', 'utf8')).行;
const todo = DECK.filter(x => !x.历史目录 && C.reviewState(x, rows[x.序] || {}, []) === '待核对');
const out = todo.filter(x => (x.货源候选 || []).length);
fs.writeFileSync(S + '/products.json', JSON.stringify(out));
console.log('待核对', todo.length, '有候选', out.length);
