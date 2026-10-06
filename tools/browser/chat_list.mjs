// 读消息列表最上面的会话：名字、最后一条、未读数
const p = await pageFor(st.readPage || "p2"); if (!st.readPage) { st.readPage = p.label; await fs.writeFile(path.join(C, "state.json"), JSON.stringify(st)); }
const home = "https://air.1688.com/app/ocms-fusion-components-1688/def_cbu_web_im/index.html";
await p.goto(home, { timeout: 30000 }).catch(() => {});
try { await p.waitForFunction(() => [...document.querySelectorAll("iframe")].some(f => { try { return f.contentDocument.querySelector(".conversation-item"); } catch { return false; } }), undefined, { timeout: 20000 }); } catch {}
await p.waitForTimeout(1500);
if (await blocked(p)) await done({ 错误: "出现验证或风控提示" });
const items = await p.evaluate(() => {
  for (const f of document.querySelectorAll("iframe")) { try {
    const items = [...f.contentDocument.querySelectorAll(".conversation-item")]; if (!items.length) continue;
    return items.slice(0, 40).map(i => ({ 名: i.querySelector(".name")?.innerText.trim(), 最后: i.querySelector(".desc")?.innerText.trim() || "", 未读: +(i.innerText.match(/^(\d+)\n/)?.[1] || 0) }));
  } catch (e) {} }
  return null;
});
await done(items ? { 会话: items } : { 错误: "读不到消息列表" });
