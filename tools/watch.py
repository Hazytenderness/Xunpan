"""盯回复开关：每 N 秒扫一次消息列表，询盘名单里的店最后一条有变化就输出一行，到点自动停。
用法：python3 tools/watch.py [分钟=10] [间隔秒=60]
只报对方的新内容：过滤我方发过的话和平台提示；首次运行只记底，有未读才报。"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from base import browser, entries, sent_texts, CACHE

SYSTEM = re.compile(r'商家长时间没有回复|平台已通知|欢迎光临|欢迎来到|优惠券|库存不多|不要错过|抓紧下单|等你等得')
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
every = float(sys.argv[2]) if len(sys.argv) > 2 else 60
E = entries(include_unsent=False)
state_f = CACHE / 'watch_state.json'
state = json.loads(state_f.read_text()) if state_f.exists() else {}
end = time.time() + minutes * 60
print(f'开始盯回复 {minutes:g} 分钟，每 {every:g} 秒一次，已发询盘的店 {len(E)} 家', flush=True)
while True:
    mine = sent_texts()
    r = browser('chat_list.mjs', timeout=120)
    if r and '错误' in r and '验证' in r['错误']:
        print('停止：' + r['错误'], flush=True); break
    for it in (r or {}).get('会话', []):
        name = it['名']
        if name not in E:
            continue
        last = it['最后']
        changed = (name not in state and it['未读'] > 0) or (name in state and state[name] != last)
        ours = any(last.startswith(t) for t in mine)
        if changed and not ours and not SYSTEM.search(last):
            print(f"新回复|{E[name][1]['id']}|{name}|未读{it['未读']}|{last[:50]}", flush=True)
        state[name] = last
    state_f.write_text(json.dumps(state, ensure_ascii=False))
    if time.time() + every > end:
        break
    time.sleep(every)
print('盯回复结束', flush=True)
