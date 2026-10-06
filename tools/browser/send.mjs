// 发一条消息：job = {ww, offerId, text, dry}
// 打开聊天 → 核对收件人 → 粘贴 → 核对内容一字不差、没有误发 → 点「发送」→ 核对我方只多 1 条
const chat = await pageFor("p1");
const out = { ww: job.ww, offerId: job.offerId };
const stop = (why) => done({ ...out, 结果: "停止:" + why });
await chat.goto(chatUrl(job.ww, job.offerId), { timeout: 30000 }).catch(() => {});
try {
  await chat.waitForFunction((ww) => [...document.querySelectorAll("iframe")].some(f => { try {
    const d = f.contentDocument; if (!d.querySelector("pre[contenteditable=true]")) return false;
    const hd = (d.querySelector(".conversation-header")?.textContent.trim() || ""), nicks = [...new Set([...d.querySelectorAll(".message-item:not(.self) .nick")].map(n => n.textContent.trim()))];
    return hd ? hd.startsWith(ww) : nicks.length ? nicks.every(n => n.startsWith(ww)) : decodeURIComponent(location.href).includes("cnalichn" + ww + "&");
  } catch { return false; } }), job.ww, { timeout: 25000 });
} catch {}
await chat.waitForTimeout(3000);
if (await blocked(chat)) await stop("出现验证或风控提示");
const state = () => chat.evaluate((ww) => {
  for (const f of document.querySelectorAll("iframe")) { try {
    const d = f.contentDocument, ed = d.querySelector("pre[contenteditable=true]"); if (!ed) continue;
    const hd = (d.querySelector(".conversation-header")?.textContent.trim() || ""), nicks = [...new Set([...d.querySelectorAll(".message-item:not(.self) .nick")].map(n => n.textContent.trim()))];
    const ok = hd ? hd.startsWith(ww) : nicks.length ? nicks.every(n => n.startsWith(ww)) : decodeURIComponent(location.href).includes("cnalichn" + ww + "&");
    const mine = [...d.querySelectorAll(".message-item.self")].map(m => ({ t: m.querySelector(".time")?.textContent.trim(), text: (m.querySelector("pre.edit")?.innerText || m.querySelector(".content")?.innerText || "").trim() }));
    return { ok, hd, nicks, mine, box: ed.innerText };
  } catch (e) {} }
  return null;
}, job.ww);
const s0 = await state();
if (!s0) await stop("找不到聊天输入框");
out.打开时 = { 页头: s0.hd, 对方昵称: s0.nicks, 我方条数: s0.mine.length };
if (!s0.ok) await stop("收件人对不上");
if (s0.box.trim()) await stop("输入框原本有内容");
if (job.dry) await done({ ...out, 结果: "演练通过" });
const snap0 = await chat.snapshot();
const ed = snap0.match(/text "请输入消息[^"]*"\s*\n\s*container \[ref=(\d+)\]/);
if (!ed) await stop("找不到输入框位置");
await chat.click("@" + ed[1], { label: "点击输入框" });
await chat.keyboard.paste(job.text);
await chat.waitForTimeout(1000);
const s1 = await state();
const norm = (x) => (x || "").replace(/\r/g, "").trim();
out.核对 = { 收件人: s1.ok, 内容一致: norm(s1.box) === norm(job.text), 未误发: s1.mine.length === s0.mine.length };
if (!out.核对.收件人 || !out.核对.内容一致 || !out.核对.未误发) await stop("发送前核对不通过");
const snap = await chat.snapshot();
const btns = [...snap.matchAll(/button \[ref=(\d+)\]\s*\n\s*text "发送"\n/g)];
if (btns.length !== 1) await stop("发送按钮个数=" + btns.length);
await chat.click("@" + btns[0][1], { label: "点击发送" });
await chat.waitForTimeout(3000);
const s2 = await state();
const added = s2.mine.slice(s1.mine.length);
out.发后新增条数 = added.length;
out.发送时间 = added[0]?.t || null;
out.结果 = added.length === 1 && norm(added[0].text) === norm(job.text.split("\n")[0]) && !norm(s2.box) ? "成功" : "异常";
await done(out);
