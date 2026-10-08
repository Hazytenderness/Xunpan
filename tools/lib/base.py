"""询盘工具的公共底座：路径、浏览器调用（带锁）、节奏、时间、队列与记账。

浏览器脚本（tools/browser/*.mjs）不接收参数：调用前把任务写进 ~/.cache/xunpan/job.json，
脚本把结果写进 ~/.cache/xunpan/<脚本名>.out.json。整个调用过程持有同一把浏览器锁，
发送、读聊天、扫消息列表、核页不会同时操作浏览器。
"""
import fcntl
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCHES = ROOT / 'batches'
BROWSER = ROOT / 'tools' / 'browser'
CACHE = Path.home() / '.cache' / 'xunpan'
CACHE.mkdir(parents=True, exist_ok=True)
LOCK = CACHE / 'browser.lock'
LAST = CACHE / 'last_send.txt'
BJ = timezone(timedelta(hours=8))

GAP_SECONDS = 60          # 任意两条消息之间的最短间隔
WORK_HOURS = (9, 18)      # 北京时间可发消息的时段


def now_bj():
    return datetime.now(BJ)


def to_beijing(local_text):
    """1688 页面显示的是本机时间，换成北京时间 ISO 字符串。"""
    try:
        t = datetime.strptime(local_text.strip(), '%Y-%m-%d %H:%M:%S').astimezone()
        return t.astimezone(BJ).isoformat(timespec='seconds')
    except Exception:
        return local_text


def in_work_hours():
    h = now_bj().hour
    return WORK_HOURS[0] <= h < WORK_HOURS[1]


def batch_dirs():
    return sorted(p for p in BATCHES.iterdir() if (p / 'queue.json').exists())


def load_queue(batch):
    return json.loads((Path(batch) / 'queue.json').read_text())


def save_queue(batch, q):
    (Path(batch) / 'queue.json').write_text(json.dumps(q, ensure_ascii=False, indent=1))


def entries(include_unsent=True):
    """旺旺名 → (批次目录, 队列条目)。款不对、下架、已合并的不算；只核过页没询过盘的（已核页）也不算，免得盖掉真在聊的条目。"""
    out = {}
    for b in batch_dirs():
        for x in load_queue(b):
            if x.get('旺旺名') and x['状态'] not in ('款不对', '下架', '已合并', '待核页', '已核页', '不用发'):
                if include_unsent or x['状态'] != '待发R1':
                    out[x['旺旺名']] = (b, x)
    return out


def find(key):
    """按旺旺名或条目 id 找到 (批次, 条目)。"""
    E = entries()
    if key in E:
        return E[key]
    for b in batch_dirs():
        for x in load_queue(b):
            if x['id'] == key:
                return b, x
    raise SystemExit(f'找不到：{key}')


def append_log(batch, row):
    with open(Path(batch) / 'sent_log.jsonl', 'a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def sent_texts():
    out = set()
    for b in batch_dirs():
        f = b / 'sent_log.jsonl'
        if f.exists():
            for l in f.read_text().splitlines():
                if l.strip():
                    out.add(json.loads(l)['文本'][:20])
    return out


def wait_gap():
    if LAST.exists():
        left = GAP_SECONDS - (time.time() - float(LAST.read_text() or 0))
        if left > 0:
            time.sleep(left)


def mark_sent():
    LAST.write_text(str(time.time()))


def browser(script, job=None, timeout=300, sending=False):
    """在浏览器锁内运行 tools/browser/<script>，返回脚本写出的 JSON；失败返回 None。"""
    out = CACHE / (Path(script).stem + '.out.json')
    with open(LOCK, 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if sending:
            wait_gap()
        (CACHE / 'job.json').write_text(json.dumps(job or {}, ensure_ascii=False))
        out.unlink(missing_ok=True)
        code = f'const NAME = {json.dumps(Path(script).stem)};\n' + (BROWSER / '_prelude.txt').read_text() + '\n' + (BROWSER / script).read_text()
        r = subprocess.run(['ego-browser', 'nodejs', '-e', code],
                           capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        if sending:
            mark_sent()
    if out.exists():
        return json.loads(out.read_text())
    (CACHE / 'last_error.txt').write_text(r.stdout[-3000:] + '\n' + r.stderr[-3000:])
    return None
