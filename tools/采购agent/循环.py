#!/usr/bin/env python3
"""采购agent 的 loop：读款 -> 采购agent.run（分类＋排班）-> 写本轮结果、记录和状态.json，18:00 后出当天日报。规则见 AGENT.md 10.4、10.5。
同一个「现在」跑几遍＝跑一遍；不装定时任务，不连 1688。"""
import json, os, shutil, subprocess, sys, tempfile
from datetime import date, datetime, timedelta

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import 采购agent
import 调度

USAGE = """用法：
  python3 循环.py                                                   不带参数＝只打印用法
  python3 循环.py <数据目录> <记录目录> [--现在 ISO] [--账号状态 文件]  跑一轮；不给 --现在 用本机当前北京时间
  python3 循环.py --selftest                                        跑 循环用例.json，再把 模拟数据/ 同一现在跑两遍比对"""
日报时 = 18


def batch_key(b):
    """批次（入池日期）-> (排序键, 标签)：ISO 周，标签「第 N 周（周一 MM-DD）」；未知批次排最后"""
    if b == "未知批次":
        return (1, ""), b
    d = date.fromisoformat(b)
    mon = d - timedelta(days=d.weekday())
    return (0, mon.isoformat()), "第 %d 周（%s）" % (d.isocalendar()[1], mon.strftime("%m-%d"))


def dur(sec):
    h = int(sec // 3600)
    return "%d 小时" % h if h < 48 else "%d 天 %d 小时" % (h // 24, h % 24)


def update_state(rec, out):
    """状态.json：{编号: {分类, 进入时间}}。分类变了才更新进入时间；同一现在再跑不变"""
    p = os.path.join(rec, "状态.json")
    old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    if not isinstance(old, dict):
        raise ValueError("状态.json 顶层不是对象：%s" % p)
    st = dict(old)
    for e in out["款"]:
        if (st.get(e["编号"]) or {}).get("分类") != e["分类"]:
            st[e["编号"]] = {"分类": e["分类"], "进入时间": out["现在"]}
    if st != old or not os.path.exists(p):
        os.makedirs(rec, exist_ok=True)
        open(p + ".tmp", "w", encoding="utf-8").write(json.dumps(st, ensure_ascii=False, indent=1))
        os.replace(p + ".tmp", p)
    return st


def stuck_rows(out, ks, st, R):
    """卡点明细：[(卡点序号, 款条目, 卡了几秒, 谁来动)]；时限读 rules.json「日报」，催回已发出本身就是超时"""
    now = 调度.bj(out["现在"])
    kmap = {k["编号"]: k for k in ks}
    lim = R["日报"]
    shops = {w["供应商"] for w in out["等待"] if w["原因"].endswith("暂停")}
    rows = []
    for e in out["款"]:
        k = kmap[e["编号"]]
        age = (now - 调度.bj(st[e["编号"]]["进入时间"])).total_seconds()
        home = next((h for r in k["轮次"] for h in r["候选"] if h["offerId"] == e["当前候选"]), None)
        q = (home or {}).get("询盘") or {}
        if (e["分类"] == "询盘中" and (q.get("已问次数") or {}).get("催回", 0) >= 1
                and q.get("最新消息方") == "我方" and q.get("最后发送")):
            rows.append((0, e, (now - 调度.bj(q["最后发送"]["时间"])).total_seconds(), "采购agent"))
        if e["分类"] == "待人工核实" and age > lim["待人工核实没人看小时"] * 3600:
            rows.append((1, e, age, "你"))
        if e["分类"] == "重跑供应商" and age > lim["重跑等找货小时"] * 3600:
            rows.append((2, e, age, "找货程序"))
        if e["编号"] in out["悬着"]:
            rows.append((3, e, (now - 调度.bj(k["开始询盘"])).total_seconds(), "你"))
        if home and home["店铺"] in shops:
            rows.append((4, e, age, "你"))
    return rows


def today_work(rec, out):
    """当天（北京时间）各轮计划里的询盘、回复条数，同一条（店、候选、句子都一样）只算一次；只看不晚于这一轮的"""
    day = out["现在"][:10].replace("-", "")
    cur = 调度.bj(out["现在"]).strftime("%Y%m%d-%H%M%S")
    seen = {"询盘": set(), "回复": set()}
    d = os.path.join(rec, "轮")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.startswith(day) or f[:-5] > cur:
            continue
        try:
            plan = json.load(open(os.path.join(d, f), encoding="utf-8")).get("计划") or []
        except (OSError, ValueError, AttributeError):
            continue
        for p in plan:
            seen[p["类型"]].add((p["供应商"], p["候选"], p["下一句"]))
    return len(seen["询盘"]), len(seen["回复"])


def report(out, ks, st, rec, R):
    day = out["现在"][:10]
    days = R["分类"]["悬着天数"]
    names = ["等商家回复已催过", "待人工核实没人看", "重跑等夜里找货", "满 %d 天没结局" % days, "号被拦"]
    bk = {e["批次"]: batch_key(e["批次"]) for e in out["款"]}
    order = sorted(set(bk.values()))
    # 一、每批进度
    t1 = ["| 批次 | 总款 | 完成 | 待人工核实（包装已有） | 询盘中 | 重跑 | 找不到 | 不做 | 完成率 |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label in order:
        es = [e for e in out["款"] if bk[e["批次"]] == (key, label)]
        n = lambda f: sum(1 for e in es if f(e))
        c, lost, skip = n(lambda e: e["结局"] == "完成"), n(lambda e: e["分类"] == "找不到货源"), n(lambda e: e["分类"] == "不做")
        den = len(es) - lost - skip
        t1.append("| %s | %d | %d | %d（%d） | %d | %d | %d | %d | %s |" % (
            label, len(es), c, n(lambda e: e["分类"] == "待人工核实"), n(lambda e: e.get("包装") == "已有"),
            n(lambda e: e["分类"] == "询盘中"), n(lambda e: e["分类"] == "重跑供应商"), lost, skip,
            "%.1f%%" % (100.0 * c / den) if den > 0 else "无"))
    # 二、卡在哪
    groups = {}
    for no, e, sec, who in stuck_rows(out, ks, st, R):
        g = groups.setdefault((no, bk[e["批次"]]), {"编号": [], "秒": 0, "谁": who})
        g["编号"].append(e["编号"])
        g["秒"] = max(g["秒"], sec)
    stop = "、".join(s["账号"] for s in out["停的号"])
    t2 = ["| 卡点 | 哪批 | 款数 | 最久卡了多久 | 谁来动 |", "|---|---|---|---|---|"]
    for no, name in enumerate(names):
        if no == 4 and stop:
            name += "（%s）" % stop
        gs = sorted(x for x in groups if x[0] == no)
        if not gs:
            t2.append("| %s | %s | %s | - | %s |" % (name, "无", "0" if no == 4 and stop else "-", "你" if no == 4 and stop else "-"))
        for x in gs:
            g = groups[x]
            cnt = "%d（%s）" % (len(g["编号"]), "、".join(sorted(g["编号"]))) if no == 3 else str(len(g["编号"]))
            t2.append("| %s | %s | %s | %s | %s |" % (name, x[1][1], cnt, dur(g["秒"]), g["谁"]))
    top = min(groups, key=lambda x: (-len(groups[x]["编号"]), x[0], x[1]), default=None)  # 并列取卡点序靠前、批次靠前
    # 三、今天做了什么
    ask, reply = today_work(rec, out)
    new = [e for e in out["款"] if e["分类"] == "待人工核实" and st[e["编号"]]["进入时间"][:10] == day]
    done = sum(1 for e in new if e["结局"] == "完成")
    head = "今天完成 %d 款；%s。" % (done, "卡得最多的是%s的「%s」，%d 款" % (
        top[1][1], names[top[0]], len(groups[top]["编号"])) if top else "没有卡住的款")
    return "\n".join(["# 日报 %s" % day, head, "", "## 一、每批进度"] + t1 + ["", "## 二、卡在哪（只列超过时限的）"] + t2 + [
        "", "## 三、今天做了什么", "- 排了 %d 条询盘、%d 条回复" % (ask, reply), "- 今天新进待人工核实 %d 款" % len(new)]) + "\n"


def seen_times(jl):
    ts = set()
    if os.path.exists(jl):
        for x in open(jl, encoding="utf-8").read().splitlines():
            try:
                ts.add(json.loads(x).get("现在"))
            except (ValueError, AttributeError):
                pass
    return ts


def run_once(data, rec, now, R, state=None, names=None):
    """跑一轮。返回 {轮文件, 日报: 写了|已有|未到时间, 新增记录}；坏时间、坏状态.json 抛 ValueError，数据目录不存在抛 NotADirectoryError"""
    t = 调度.bj(now)
    if not os.path.isdir(data):
        raise NotADirectoryError("数据目录不存在或不是目录：%s" % data)
    ks, le = 采购agent.load_dir(data)
    out = 采购agent.run(ks, now, R, names, state, le)
    st = update_state(rec, out)
    os.makedirs(os.path.join(rec, "轮"), exist_ok=True)
    f = os.path.join(rec, "轮", t.strftime("%Y%m%d-%H%M%S") + ".json")
    open(f, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    jl = os.path.join(rec, "记录.jsonl")
    fresh = out["现在"] not in seen_times(jl)
    if fresh:  # 记录里已有同一现在＝这一轮记过了，跑几遍＝跑一遍（不看轮文件在不在）
        line = {"现在": out["现在"], "统计": out["统计"], "结局统计": out["结局统计"], "完成率": out["完成率"],
                "计划条数": len(out["计划"]), "错误条数": len(out["错误"])}
        with open(jl, "a", encoding="utf-8") as g:
            g.write(json.dumps(line, ensure_ascii=False) + "\n")
    done = "未到时间"
    if t.hour >= 日报时:
        p = os.path.join(rec, "日报", t.strftime("%Y-%m-%d") + ".md")
        if os.path.exists(p):
            done = "已有"  # 已存在⛔不覆盖：人可能手改过
        else:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(report(out, ks, st, rec, R))
            done = "写了"
    return {"轮文件": f, "日报": done, "新增记录": fresh}


def lines(p):
    return len(open(p, encoding="utf-8").read().splitlines()) if os.path.exists(p) else 0


def run_case(c, R):
    bad = []
    with tempfile.TemporaryDirectory() as td:
        data, rec = os.path.join(td, "数据"), os.path.join(td, "记录")
        if c.get("仅追加"):
            os.makedirs(data)
        else:
            shutil.copytree(os.path.join(D, "模拟数据"), data)
        for j, k in enumerate(c.get("追加款") or []):
            json.dump(k, open(os.path.join(data, "9%d_追加.json" % j), "w", encoding="utf-8"), ensure_ascii=False)
        if "命令行" in c:
            args = [a.replace("{数据}", data).replace("{记录}", rec) for a in c["命令行"]]
            p = subprocess.run([sys.executable, os.path.join(D, "循环.py")] + args, capture_output=True, text=True)
            if p.returncode != c["退出码"]:
                bad.append("退出码 期望 %r 实得 %r" % (c["退出码"], p.returncode))
            if c.get("输出含") and c["输出含"] not in p.stdout + p.stderr:
                bad.append("输出里没有 %r：%r" % (c["输出含"], p.stdout + p.stderr))
            if os.path.exists(rec):
                bad.append("出错时不该写记录目录")
            return bad
        prev = prevst = None
        for i, s in enumerate(c["步骤"], 1):
            if s.get("删轮文件"):
                shutil.rmtree(os.path.join(rec, "轮"), ignore_errors=True)
            if "预置状态" in s:
                os.makedirs(rec, exist_ok=True)
                json.dump(s["预置状态"], open(os.path.join(rec, "状态.json"), "w", encoding="utf-8"), ensure_ascii=False)
            for w in s.get("写款") or []:
                json.dump(w["款"], open(os.path.join(data, w["文件"]), "w", encoding="utf-8"), ensure_ascii=False)
            if "改日报" in s:
                p = os.path.join(rec, "日报", s["改日报"]["文件"])
                open(p, "w", encoding="utf-8").write(s["改日报"]["内容"])
            r = run_once(data, rec, s["现在"], R, None, c.get("账号名单"))
            body = open(r["轮文件"], "rb").read()
            if "日报" in s and r["日报"] != s["日报"]:
                bad.append("步骤 %d 日报 期望 %r 实得 %r" % (i, s["日报"], r["日报"]))
            if "轮文件名" in s and os.path.basename(r["轮文件"]) != s["轮文件名"]:
                bad.append("步骤 %d 轮文件名 期望 %r 实得 %r" % (i, s["轮文件名"], os.path.basename(r["轮文件"])))
            if s.get("轮文件同上一步") and body != prev:
                bad.append("步骤 %d 轮文件和上一步不同" % i)
            prev = body
            stf = os.path.join(rec, "状态.json")
            stbody = open(stf, "rb").read()
            if s.get("状态同上一步") and stbody != prevst:
                bad.append("步骤 %d 状态.json 和上一步不同" % i)
            prevst = stbody
            got = json.loads(stbody)
            for no, want in (s.get("状态") or {}).items():
                if got.get(no) != want:
                    bad.append("步骤 %d 状态.json[%s] 期望 %r 实得 %r" % (i, no, want, got.get(no)))
        e = c.get("最终") or {}
        names = lambda sub: sorted(os.listdir(os.path.join(rec, sub))) if os.path.isdir(os.path.join(rec, sub)) else []
        if "轮文件数" in e and len(names("轮")) != e["轮文件数"]:
            bad.append("轮文件数 期望 %r 实得 %r" % (e["轮文件数"], len(names("轮"))))
        if "记录行数" in e and lines(os.path.join(rec, "记录.jsonl")) != e["记录行数"]:
            bad.append("记录行数 期望 %r 实得 %r" % (e["记录行数"], lines(os.path.join(rec, "记录.jsonl"))))
        if "日报文件" in e and names("日报") != e["日报文件"]:
            bad.append("日报文件 期望 %r 实得 %r" % (e["日报文件"], names("日报")))
        for fn, want in (e.get("日报内容") or {}).items():
            got = open(os.path.join(rec, "日报", fn), encoding="utf-8").read()
            if got != want:
                bad.append("日报 %s 被改了：%r" % (fn, got))
        for fn, subs in (e.get("日报含") or {}).items():
            got = open(os.path.join(rec, "日报", fn), encoding="utf-8").read()
            bad += ["日报 %s 里没有 %r" % (fn, x) for x in subs if x not in got]
        for fn, subs in (e.get("日报不含") or {}).items():
            got = open(os.path.join(rec, "日报", fn), encoding="utf-8").read()
            bad += ["日报 %s 里不该有 %r" % (fn, x) for x in subs if x in got]
        if "记录首行含键" in e:
            first = json.loads(open(os.path.join(rec, "记录.jsonl"), encoding="utf-8").readline())
            bad += ["记录首行没有键 %s" % k for k in e["记录首行含键"] if k not in first]
    return bad


def selftest(R):
    cases = json.load(open(os.path.join(D, "循环用例.json"), encoding="utf-8"))
    fails = 0
    for c in cases:
        bad = run_case(c, R)
        fails += bool(bad)
        print("%s %s %s" % ("不过" if bad else "过", c["编号"], c["名"]))
        for b in bad:
            print("    " + b)
    # 全新两个记录目录、同一现在：轮文件逐字相同
    with tempfile.TemporaryDirectory() as td:
        t, outs = "2026-11-02T18:05:00+08:00", []
        for n in ("甲", "乙"):
            r = run_once(os.path.join(D, "模拟数据"), os.path.join(td, n), t, R, None, cases[0].get("账号名单"))
            outs.append(open(r["轮文件"], "rb").read())
        bad = [] if outs[0] == outs[1] else ["同一现在跑两遍，轮文件不同"]
    fails += bool(bad)
    print("%s 模拟数据同一现在两遍相同" % ("不过" if bad else "过"))
    for x in bad:
        print("    " + x)
    print("共 %d 条，不过 %d" % (len(cases) + 1, fails))
    return 1 if fails else 0


def main():
    a = sys.argv[1:]
    if not a:
        print(USAGE)
        return 0
    R = json.load(open(os.path.join(D, "rules.json"), encoding="utf-8"))
    if a == ["--selftest"]:
        return selftest(R)
    pos, opt, i = [], {}, 0
    while i < len(a):
        if a[i] in ("--现在", "--账号状态"):
            if i + 1 >= len(a):
                print("错误：%s 后面缺值" % a[i], file=sys.stderr)
                return 2
            opt[a[i]] = a[i + 1]
            i += 2
        else:
            pos.append(a[i])
            i += 1
    if len(pos) != 2:
        print(USAGE)
        return 2
    try:
        now = opt["--现在"] if "--现在" in opt else datetime.now(调度.BJ).strftime(调度.FMT)
        state = None
        if "--账号状态" in opt:
            if not os.path.isfile(opt["--账号状态"]):
                raise FileNotFoundError("账号状态文件不存在：%s" % opt["--账号状态"])
            state = json.load(open(opt["--账号状态"], encoding="utf-8"))
        r = run_once(pos[0], pos[1], now, R, state)
    except (ValueError, OSError) as e:  # 时间错、坏 json、目录不存在
        print("错误：%s" % (str(e).splitlines()[0] if str(e) else type(e).__name__), file=sys.stderr)
        return 2
    print("写了 %s；日报：%s" % (r["轮文件"], r["日报"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
