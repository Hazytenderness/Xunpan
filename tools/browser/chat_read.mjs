// 读一家店的完整聊天：job = {ww, offerId}；先确认打开的是这家店再读
const p = await pageFor(st.readPage || "p2"); if (!st.readPage) { st.readPage = p.label; await fs.writeFile(path.join(C, "state.json"), JSON.stringify(st)); }
await p.goto(chatUrl(job.ww, job.offerId), { timeout: 30000 }).catch(() => {});
let ok = false;
try {
  await p.waitForFunction((ww) => [...document.querySelectorAll("iframe")].some(f => { try {
    const d = f.contentDocument; if (!d.querySelector(".message-item")) return false;
    const hd = (d.querySelector(".conversation-header")?.textContent.trim() || ""), nicks = [...new Set([...d.querySelectorAll(".message-item:not(.self) .nick")].map(n => n.textContent.trim()))];
    return hd ? hd.startsWith(ww) : nicks.length ? nicks.every(n => n.startsWith(ww)) : decodeURIComponent(location.href).includes("cnalichn" + ww + "&");
  } catch { return false; } }), job.ww, { timeout: 25000 }); ok = true;
} catch {}
await p.waitForTimeout(2500);
if (await blocked(p)) await done({ 错误: "出现验证或风控提示" });
if (!ok) await done({ 错误: "打开的不是这家店的聊天" });
const msgs = await p.evaluate(() => {
  for (const f of document.querySelectorAll("iframe")) { try {
    const d = f.contentDocument; if (!d.querySelector("pre[contenteditable=true]")) continue;
    return [...d.querySelectorAll(".message-item")].map(m => ({
      昵称: m.querySelector(".nick")?.innerText.trim(), 时间: m.querySelector(".time")?.innerText.trim(), 我方: m.classList.contains("self"), 模板: !!m.querySelector(".im-template-msg"),
      内容: (m.querySelector("pre.edit")?.innerText ?? m.querySelector(".content")?.innerText ?? "").trim(),
      图片: [...m.querySelectorAll("img.imui-msg-img")].map(i => i.src), 视频: [...m.querySelectorAll("video")].map(v => v.src || v.currentSrc).filter(Boolean) }));
  } catch (e) {} }
  return null;
});
await done(msgs ? { 消息: msgs } : { 错误: "读不到消息" });
