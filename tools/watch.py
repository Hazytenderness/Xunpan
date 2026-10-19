"""盯回复开关：每 N 秒扫一次消息列表，询盘名单里的店最后一条有变化就输出一行，到点自动停。
用法：python3 tools/watch.py [分钟=10] [间隔秒=60]
只报对方的新内容：过滤我方发过的话和平台提示；首次运行只记底，有未读才报。"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import browser, entries, sent_texts, CACHE
from resilience import RetryLater,atomic_json
from port import file_lock

SYSTEM = re.compile(r'商家长时间没有回复|平台已通知|欢迎光临|欢迎来到|优惠券|库存不多|不要错过|抓紧下单|等你等得')
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
every = float(sys.argv[2]) if len(sys.argv) > 2 else 60
E = entries(include_unsent=False)
state_f = CACHE / 'watch_state.json'
state = json.loads(state_f.read_text(encoding='utf-8')) if state_f.exists() else {}
end = time.time() + minutes * 60
print(f'开始盯回复 {minutes:g} 分钟，每 {every:g} 秒一次，已发询盘的店 {len(E)} 家', flush=True)
while True:
    mine = sent_texts()
    try:r = browser('chat_list.mjs', timeout=120)
    except RetryLater as error:print('暂缓：'+str(error),flush=True);break
    if not r or '错误' in r:
        print('停止：' + (r or {}).get('错误','浏览器无结果'), flush=True); break
    news={}
    for it in (r or {}).get('会话', []):
        name = it['名']
        if name not in E:
            continue
        last = it['最后']
        changed = (name not in state and it['未读'] > 0) or (name in state and state[name] != last)
        ours = any(last.startswith(t) for t in mine)
        if changed and not ours and not SYSTEM.search(last):
            key=E[name][1]['id'];line=f"新回复|{key}|{name}|未读{it['未读']}|{last[:50]}"
            news[key]=line;print(line,flush=True)
        state[name] = last
    # 先持久化待处理，再推进扫描游标；父程序中断也不会丢新回复。
    with file_lock(CACHE/'pending_replies.lock'):
        target=CACHE/'pending_replies.json'
        pending=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        pending.update(news);atomic_json(target,pending)
    atomic_json(state_f,state)
    if time.time() + every > end:
        break
    time.sleep(every)
print('盯回复结束', flush=True)
