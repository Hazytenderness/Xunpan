#!/usr/bin/env python3
"""多账号询盘调度：输入 json -> 输出 json。规则见 AGENT.md 第 10、11 节，数字只读 rules.json 的「调度」，名单读 账号.json。"""
import hashlib, json, os, sys
from datetime import datetime, timedelta, timezone

D = os.path.dirname(os.path.abspath(__file__))
USAGE = """用法：
  python3 调度.py                 不带参数＝只打印用法
  python3 调度.py <输入.json>     打印输出 json
  python3 调度.py --selftest      跑 调度用例.json，逐条打 过/不过，有不过退出码 1"""
BJ = timezone(timedelta(hours=8))
FMT = "%Y-%m-%dT%H:%M:%S+08:00"
类型们 = ("询盘", "回复")


class 时间错(ValueError):
    pass


def bj(s):
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    t = datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise 时间错("时间必须带时区：%s" % s)
    return t.astimezone(BJ).replace(microsecond=0)


def secs(s):  # "HH:MM" -> 当天第几秒；"24:00"＝86400＝当天结束
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def can(t, typ, C):
    """t 能不能发 typ 类型：星期、时段（含头不含尾）、暂停段；跨午夜按 t 自己那天算"""
    if t.isoweekday() not in C["工作日"]:
        return False
    x = t.hour * 3600 + t.minute * 60 + t.second
    if any(secs(a) <= x < secs(b) for a, b in C["暂停"]):
        return False
    return any(secs(a) <= x < secs(b) for a, b in C[typ + "时段"])


def kinds(t, C):
    return [k for k in 类型们 if can(t, k, C)]


def judge(inp, R):
    C = R["调度"]
    now = bj(inp["现在"])
    if "账号名单" in inp:
        names = inp["账号名单"]
    else:
        names = json.load(open(os.path.join(D, "账号.json"), encoding="utf-8"))["账号"]
    st = inp.get("账号状态") or {}
    queue = inp.get("队列") or []
    out = {"版本": R["版本"], "现在": now.strftime(FMT), "可发送": True, "原因": "", "计划": [],
           "新绑定": [], "等待": [], "停的号": [], "要你做": []}

    # 3 停的号（不在时间内也照出）
    ok = []
    for n in names:
        c = n["代号"]
        why = None
        if n.get("状态") != "正常":
            why = "账号.json 标暂停" + ("：" + n["备注"] if n.get("备注") else "")
        elif (st.get(c) or {}).get("风控"):
            why = "风控：" + st[c]["风控"]
        if why:
            out["停的号"].append({"账号": c, "原因": why})
            out["要你做"].append("%s 被拦（%s），去验证后把 账号.json 里的状态改成正常" % (c, why))
        else:
            ok.append(c)
    stopped = {s["账号"] for s in out["停的号"]}

    # 1、2 时间窗
    start = now
    end = now + timedelta(minutes=C["窗口分钟"])
    # 时段边界都落在整分钟，所以只看 现在 和窗口内每个整分钟点
    probe = [now] + [now.replace(second=0) + timedelta(minutes=i) for i in range(1, C["窗口分钟"] + 1)]
    if not any(kinds(t, C) for t in probe if t < end):
        out.update(可发送=False, 原因="不在发送时间")
        return out

    # 6 队列整理
    seen, qs = set(), []
    for q in queue:
        if q["供应商"] not in seen:
            seen.add(q["供应商"])
            qs.append(q)
    qs.sort(key=lambda q: (q.get("倍数") is None, -(q.get("倍数") or 0)))

    allnames = {n["代号"] for n in names}

    # 全停
    if not ok:
        out.update(可发送=False, 原因="全部 %d 个号都停了" % len(names) if names else "账号名单为空")
        for q in qs:
            b = q.get("绑定账号")
            if not names or not b:
                why = "没有可用的号"
            elif b in allnames:
                why = "%s暂停" % b
            else:
                why = "绑定账号不在名单"
            out["等待"].append({"供应商": q["供应商"], "原因": why})
        return out

    # 4 间隔
    lo, hi = C["间隔最短秒"], C["间隔最长秒"]

    def gap(c, t):
        h = hashlib.sha256(("%s|%s" % (c, t.strftime(FMT))).encode("utf-8")).hexdigest()
        return timedelta(seconds=lo + int(h, 16) % (hi - lo + 1))

    # 5 每个号的时刻
    slots = []
    for c in ok:
        last = (st.get(c) or {}).get("最后发送")
        t = start if not last else max(start, bj(last) + gap(c, bj(last)))
        done = (st.get(c) or {}).get("今日已发") or 0
        while t < end:
            ks = kinds(t, C)
            if ks:  # 哪种类型都不能发的时刻跳过，链照样往后推
                slots.append((t, done, c, ks))
            t = t + gap(c, t)

    # 7 等待（先出）
    left = []
    for q in qs:
        b = q.get("绑定账号")
        if b and b in stopped:
            out["等待"].append({"供应商": q["供应商"], "原因": "%s暂停" % b})
        elif b and b not in allnames:
            out["等待"].append({"供应商": q["供应商"], "原因": "绑定账号不在名单"})
        else:
            left.append(q)

    # 8 填时刻
    kind = lambda q: q.get("类型") if q.get("类型") in 类型们 else "回复"  # 缺省按回复：窗口更窄，宁可少发
    for t, _, c, ks in sorted(slots, key=lambda s: (s[0], s[1], s[2])):
        pick = next((q for q in left if q.get("绑定账号") == c and kind(q) in ks), None)
        if pick is None:
            pick = next((q for q in left if not q.get("绑定账号") and kind(q) in ks), None)
            if pick is not None:
                out["新绑定"].append({"供应商": pick["供应商"], "账号": c})
        if pick is None:
            continue
        left.remove(pick)
        out["计划"].append({"时间": t.strftime(FMT), "账号": c, "供应商": pick["供应商"], "类型": kind(pick),
                          "候选": pick["候选"], "下一句": pick["下一句"]})

    # 9 剩下的
    for q in left:
        k = kind(q)
        why = "本轮排不下" if any(k in ks for _, _, _, ks in slots) else "不在%s时段" % k
        out["等待"].append({"供应商": q["供应商"], "原因": why})
    out["计划"].sort(key=lambda p: (p["时间"], p["账号"]))
    return out


缺 = object()  # 字段不存在，和值为 null 区分开


def dig(o, path):
    for seg in path.split("."):
        if o is 缺:
            return 缺
        if isinstance(o, list) and not seg.isdigit():
            o = [x.get(seg, 缺) if isinstance(x, dict) else 缺 for x in o]
            if 缺 in o:
                return 缺
        elif isinstance(o, list):
            o = o[int(seg)] if int(seg) < len(o) else 缺
        elif isinstance(o, dict):
            o = o.get(seg, 缺)
        else:
            return 缺
    return o


def sub(got, want):  # want 的每个字段 got 里都一样
    return all(got.get(k) == v for k, v in want.items())


def check(got, exp):
    bad = []
    for k, v in exp.items():
        base = k
        for suf in ("不含", "包含", "含", "最大小于", "长度"):
            if k.endswith(suf):
                base = k[:-len(suf)]
                break
        else:
            suf = ""
        g = dig(got, base.rstrip("."))
        if g is 缺:
            bad.append("%s 期望 %r 实得 字段不存在" % (k, v))
            continue
        if suf == "不含":
            ok = isinstance(g, list) and bool(g) and not set(v) & set(g)
        elif suf == "含":
            ok = isinstance(g, list) and all(any(isinstance(x, dict) and sub(x, w) or x == w for x in g) for w in v)
        elif suf == "最大小于":
            ok = isinstance(g, list) and bool(g) and max(g) < v
        elif suf == "长度":
            ok = g is not None and len(g) == v
        elif suf == "包含":
            ok = (isinstance(g, str) and v in g) or (isinstance(g, list) and isinstance(v, list) and all(w in g for w in v))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            ok = isinstance(g, list) and len(g) == len(v) and all(sub(a, b) for a, b in zip(g, v))
        else:
            ok = g == v
        if not ok:
            bad.append("%s 期望 %r 实得 %r" % (k, v, g))
    return bad


def gaps_bad(out):
    bad, last = [], {}
    for p in out["计划"]:
        t = bj(p["时间"])
        if p["账号"] in last:
            d = (t - last[p["账号"]]).total_seconds()
            if not 120 <= d <= 240:
                bad.append("%s 相邻间隔 %d 秒不在 120–240" % (p["账号"], d))
        last[p["账号"]] = t
    return bad


def main():
    a = sys.argv[1:]
    if not a:
        print(USAGE)
        return 0
    R = json.load(open(os.path.join(D, "rules.json"), encoding="utf-8"))
    if a[0] != "--selftest":
        try:
            print(json.dumps(judge(json.load(open(a[0], encoding="utf-8")), R), ensure_ascii=False, indent=1))
        except 时间错 as e:
            print(e, file=sys.stderr)
            return 2
        return 0
    cases = json.load(open(os.path.join(D, "调度用例.json"), encoding="utf-8"))
    fails = 0
    for c in cases:
        try:
            out = judge(c["输入"], R)
        except 时间错:
            out = None
        if "报错" in c["期望"]:
            bad = [] if out is None and c["期望"]["报错"] == 2 else ["期望退出码 2 的报错，实际没报错"]
        elif out is None:
            bad = ["意外报错：时间必须带时区"]
        else:
            bad = check(out, c["期望"]) + gaps_bad(out)
            if c["编号"] == "3" and judge(c["输入"], R) != out:
                bad.append("同输入跑两遍输出不同")
        fails += bool(bad)
        print("%s %s %s" % ("不过" if bad else "过", c["编号"], c["名"]))
        for b in bad:
            print("    " + b)
    print("共 %d 条，不过 %d" % (len(cases), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
