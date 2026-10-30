#!/usr/bin/env python3
"""采购agent：一批款 -> 每款分类 + 重跑请求 + 排班。规则见 AGENT.md 第 12、13 节，数字只读 rules.json 的「分类」。
逐家判调 inquiry.judge，排班调 调度.judge，这里不复制它们的逻辑。"""
import copy, json, os, re, sys, tempfile
from datetime import datetime, timedelta

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import inquiry
import 调度

USAGE = """用法：
  python3 采购agent.py                                   不带参数＝只打印用法
  python3 采购agent.py <数据目录> <现在> [<账号状态.json>]  打印本轮 json；现在必须带时区
  python3 采购agent.py --selftest                         跑 采购agent用例.json，再把 模拟数据/ 跑两遍比对相同"""


def sim_map(k, errs):
    """人工.类似款 -> 只留 接受／不接受；null 当 {}，别的值当没表态并记一条错误"""
    m = (k.get("人工") or {}).get("类似款")
    if not isinstance(m, dict):
        return {}
    for oid, v in m.items():
        if v not in ("接受", "不接受"):
            errs.append("%s 类似款 %s 写了「%s」，只认 接受／不接受" % (k.get("编号"), oid, v))
    return {oid: v for oid, v in m.items() if v in ("接受", "不接受")}


def batch_of(k, errs):
    """款的批次＝入池日期 YYYY-MM-DD（AGENT.md 10.4）；没写或写错都归「未知批次」，写错记一条错误"""
    b = k.get("批次")
    if b is None:
        return "未知批次"
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", b):
            raise ValueError
        datetime.strptime(b, "%Y-%m-%d")
        return b
    except (ValueError, TypeError):
        errs.append("%s 批次 读不了：%r，要 YYYY-MM-DD" % (k.get("编号"), b))
        return "未知批次"


def judge_home(k, home, now_s, R, sim):
    ex = copy.deepcopy(home["询盘"].get("抽取") or {})
    for f in ("事实", "无法提供", "商家反问", "待决策"):
        ex.setdefault(f, [])
    ex.setdefault("候选", home["offerId"])
    if sim.get(home["offerId"]) == "接受":
        for f in ex["事实"]:
            if f.get("项") == "匹配确认" and f.get("值") == "类似款":
                f["值"] = "完全匹配"
    inq = home["询盘"]
    return inquiry.judge({
        "现在": now_s,
        "候选": {"offerId": home["offerId"], "关键规格": k.get("关键规格"), "销售单位": k["销售单位"]},
        "抽取": ex, "已问次数": inq.get("已问次数") or {}, "最后发送": inq.get("最后发送"),
        "最新消息方": inq.get("最新消息方", "对方"), "人工": inq.get("人工") or {}}, R)


def classify(k, now_s, R, errs):
    """返回 (款条目, 重跑请求或None, 队列项或None, 要你做或None)"""
    C = R["分类"]
    rounds = k.get("轮次") or []
    last = rounds[-1] if rounds else {"轮": 0, "候选": []}
    e = {"编号": k["编号"], "批次": batch_of(k, errs), "分类": "", "原因": "", "结局": "进行中", "当前候选": "", "第几轮": last["轮"], "不能贴标": False}
    if (k.get("人工") or {}).get("不做"):  # 优先于「没有轮次」
        e.update(分类="不做", 原因="你标了不做", 结局="不做")
        return e, None, None, None
    if not rounds:
        errs.append("%s 没有轮次" % k.get("编号"))
        return None, None, None, None
    sim = sim_map(k, errs)
    res = [[(h, judge_home(k, h, now_s, R, sim)) for h in r["候选"]] for r in rounds]
    cur = None  # (home, out)
    # 3 有货：任一轮任一家（类似款你接受的已在 judge_home 里当完全匹配；不接受的不算）
    for r in res:
        for h, o in r:
            if cur is None and o["匹配确认"] == "完全匹配" and sim.get(h["offerId"]) != "不接受":
                cur = (h, o)
    if cur:
        e.update(分类="待人工核实", 原因=C["原因"]["有货"], 结局="完成")
    else:
        # 4 最后一轮找当前家
        for h, o in res[-1]:
            if (o["资料状态"] in ("资料未齐已收口", "不匹配结束")
                    or sim.get(h["offerId"]) == "不接受"):
                continue
            cur = (h, o)
            break
        if cur:
            h, o = cur
            if o["匹配确认"] == "类似款":  # 你还没表态；12.3 里排在别的待人看之前
                e.update(分类="待人工核实", 原因=C["原因"]["类似款"], 结局="完成")
            elif o["动作"] == "待你决策":
                e.update(分类="待人工核实", 原因="；".join(o["交人工"]))
            elif o["动作"] == "人工暂停":
                e.update(分类="待人工核实", 原因="人工暂停")
            else:
                e.update(分类="询盘中", 原因="核心缺：" + "、".join(o["核心缺项"]) if o["核心缺项"] else o["动作"])
        elif len(rounds) < C["最多轮数"]:  # 5 重跑
            e.update(分类="重跑供应商", 原因="这一轮 %d 家都问完了" % len(last["候选"]))
            names = [h["商家品名"] for h in rounds[0]["候选"] if h.get("商家品名")]
            req = {"编号": k["编号"], "第几轮": len(rounds) + 1,
                   "排除店铺": list(dict.fromkeys(h["店铺"] for r in rounds for h in r["候选"])),
                   "排除offer": [h["offerId"] for r in rounds for h in r["候选"]],
                   "图": C["重跑搜索"]["图"] if k.get("有副图") else C["重跑搜索"]["没副图"],
                   "关键词": list(dict.fromkeys([k["关键规格"]] + names)), "最多家数": C["每轮最多家数"]}
            return e, req, None, None
        else:
            e.update(分类="找不到货源", 原因=C["原因"]["找不到"], 结局="找不到货源")
            return e, None, None, None
    h, o = cur
    e["当前候选"] = h["offerId"]
    e["不能贴标"] = "不能贴标" in o["交人工"]
    if e["分类"] == "待人工核实":  # 12.4 小筛选：当前候选的包装尺寸和带包装重量都不缺才算已有
        e["包装"] = "待定" if {"包装尺寸", "带包装重量"} & set(o["核心缺项"]) else "已有"
    q = None
    if o["动作"] == "发送":  # 有货之后没给的项照样问（12.4）
        q = {"供应商": h["店铺"], "候选": h["offerId"], "下一句": o["下一句"], "类型": "询盘" if o["原因"] == "首轮" else "回复",
             "倍数": k.get("倍数"), "绑定账号": h.get("绑定账号")}
    todo = "%s 待人工核实：%s" % (k["编号"], e["原因"]) if e["分类"] == "待人工核实" else None
    return e, None, q, todo


def run(ks, now, R, names=None, state=None, load_errs=()):
    now_s = 调度.bj(now).strftime(调度.FMT)
    out = {"版本": R["版本"], "现在": now_s, "款": [], "统计": {c: 0 for c in ("待人工核实", "询盘中", "重跑供应商", "找不到货源", "不做")},
           "包装统计": {"已有": 0, "待定": 0},
           "结局统计": {c: 0 for c in ("完成", "找不到货源", "不做", "进行中")}, "完成率": None, "悬着": [],
           "重跑请求": [], "待发": [], "计划": [], "新绑定": [], "等待": [], "停的号": [], "要你做": [], "错误": list(load_errs)}
    todos = []
    for k in ks:
        e, req, q, todo = classify(k, now_s, R, out["错误"])
        if e is None:
            continue
        out["款"].append(e)
        out["统计"][e["分类"]] += 1
        if e.get("包装"):
            out["包装统计"][e["包装"]] += 1
        out["结局统计"][e["结局"]] += 1
        if e["结局"] == "进行中" and k.get("开始询盘"):
            try:
                if 调度.bj(now) - 调度.bj(k["开始询盘"]) >= timedelta(days=R["分类"]["悬着天数"]):
                    out["悬着"].append(e["编号"])
            except (ValueError, TypeError, AttributeError) as x:  # 不是字符串也只记错误，不崩
                out["错误"].append("%s 开始询盘 读不了：%s" % (e["编号"], x))
        if req:
            out["重跑请求"].append(req)
        if q:
            out["待发"].append(q)
        if todo:
            todos.append(todo)
    n = len(out["款"]) - out["结局统计"]["找不到货源"] - out["结局统计"]["不做"]
    if n > 0:
        out["完成率"] = round(out["结局统计"]["完成"] / n, 4)
    out["悬着"].sort()
    inp = {"现在": now_s, "账号状态": state or {}, "队列": out["待发"]}
    if names is not None:
        inp["账号名单"] = names
    s = 调度.judge(inp, R)
    for f in ("计划", "新绑定", "等待", "停的号"):
        out[f] = s[f]
    out["要你做"] = s["要你做"] + todos
    return out


def load_dir(d):
    """返回 (款列表, 错误列表)；坏文件跳过并记错误，其余照跑"""
    ks, errs = [], []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        try:
            x = json.load(open(os.path.join(d, f), encoding="utf-8"))
            if not isinstance(x, dict):
                raise ValueError("顶层不是对象")
            ks.append(x)
        except (OSError, ValueError) as e:  # UnicodeDecodeError、JSONDecodeError 都是 ValueError
            errs.append("%s 读不了：%s" % (f, str(e).splitlines()[0] if str(e) else type(e).__name__))
    return ks, errs


def selftest(R):
    cases = json.load(open(os.path.join(D, "采购agent用例.json"), encoding="utf-8"))
    fails = 0
    for c in cases:
        bad = 调度.check(run(c["款"], c["现在"], R, c.get("账号名单"), c.get("账号状态")), c["期望"])
        fails += bool(bad)
        print("%s %s %s" % ("不过" if bad else "过", c["编号"], c["名"]))
        for b in bad:
            print("    " + b)
    sim, le = load_dir(os.path.join(D, "模拟数据"))
    t = "2026-11-02T10:01:00+08:00"
    a, b = run(sim, t, R, load_errs=le), run(sim, t, R, load_errs=le)
    bad = [] if a == b else ["模拟数据两遍输出不同"]
    bad += ["统计 %s 为 0" % c for c, n in a["统计"].items() if n == 0]
    bad += ["结局统计 %s 为 0" % c for c, n in a["结局统计"].items() if n == 0 and c != "不做"]
    bad += ["包装统计 %s 为 0" % c for c, n in a["包装统计"].items() if n == 0]
    bs = {e["批次"] for e in a["款"]}
    if "未知批次" not in bs or len(bs - {"未知批次"}) < 2:
        bad.append("模拟数据的批次要有 未知批次 和至少两个日期：%r" % sorted(bs))
    fails += bool(bad)
    print("%s 模拟数据两遍相同且四类统计、三种结局、包装已有／待定、批次都不为 0" % ("不过" if bad else "过"))
    for x in bad:
        print("    " + x)
    # 坏文件：1 好款 + 坏 json + 非对象 + 名字带 .json 的子目录，好款照出、三个坏的各报一条
    with tempfile.TemporaryDirectory() as td:
        good = next(c for c in cases if c["编号"] == "6")
        json.dump(good["款"][0], open(os.path.join(td, "1_好.json"), "w", encoding="utf-8"), ensure_ascii=False)
        open(os.path.join(td, "2_bad.json"), "w", encoding="utf-8").write("{bad")
        open(os.path.join(td, "3_list.json"), "w", encoding="utf-8").write("[]")
        os.mkdir(os.path.join(td, "4_dir.json"))
        ks, le = load_dir(td)
        o = run(ks, good["现在"], R, good.get("账号名单"), load_errs=le)
    bad = []
    if [x["编号"] for x in o["款"]] != ["CW1"]:
        bad.append("好款没照常出：%r" % o["款"])
    for f in ("2_bad.json", "3_list.json", "4_dir.json"):
        if not any(x.startswith(f + " 读不了：") for x in o["错误"]):
            bad.append("错误里没有 %s 读不了：%r" % (f, o["错误"]))
    fails += bool(bad)
    print("%s 26 坏文件" % ("不过" if bad else "过"))
    for x in bad:
        print("    " + x)
    print("共 %d 条，不过 %d" % (len(cases) + 2, fails))
    return 1 if fails else 0


def main():
    a = sys.argv[1:]
    if not a:
        print(USAGE)
        return 0
    R = json.load(open(os.path.join(D, "rules.json"), encoding="utf-8"))
    if a == ["--selftest"]:
        return selftest(R)
    if a[0] == "--selftest":
        print("--selftest 后面不能带参数", file=sys.stderr)
        return 2
    if len(a) not in (2, 3):
        print(USAGE)
        return 2
    if not os.path.isdir(a[0]):
        print("数据目录不存在或不是目录：%s" % a[0], file=sys.stderr)
        return 2
    if len(a) == 3 and not os.path.isfile(a[2]):
        print("账号状态文件不存在：%s" % a[2], file=sys.stderr)
        return 2
    try:
        state = json.load(open(a[2], encoding="utf-8")) if len(a) == 3 else None
        ks, le = load_dir(a[0])
        print(json.dumps(run(ks, a[1], R, None, state, le), ensure_ascii=False, indent=1))
    except 调度.时间错 as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
