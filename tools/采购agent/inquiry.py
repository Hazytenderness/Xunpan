#!/usr/bin/env python3
"""日本站询价补资料：输入 json -> 输出 json。规则见 AGENT.md 第 4、5 节，数字和问句只读 rules.json。"""
import json, os, sys
from datetime import datetime, timedelta

D = os.path.dirname(os.path.abspath(__file__))
USAGE = """用法：
  python3 inquiry.py <输入.json>     打印输出 json
  python3 inquiry.py --selftest      跑 用例.json，逐条打 过/不过，有不过退出码 1"""


def judge(inp, R):
    cand, sell = inp["候选"], inp["候选"]["销售单位"]
    oid, ex = cand["offerId"], inp["抽取"]
    人工 = inp.get("人工") or {}
    ask_n = inp.get("已问次数") or {}
    q = R["问句"]
    # 1 事实：只留当前候选；人工已填整条替换同项（同项后者覆盖前者）
    filled = {f["项"] for f in 人工.get("已填", [])}
    facts = {}
    for f in [f for f in ex["事实"] if f["候选"] == oid and f["项"] not in filled] + 人工.get("已填", []):
        facts[f["项"]] = f
    val = lambda k: (facts.get(k) or {}).get("值")
    gone = set(ex["无法提供"])
    手 = []
    out = {"版本": R["版本"], "候选": oid, "资料状态": "待补资料", "动作": "", "下一句": "",
           "这次问": [], "核心缺项": [], "辅助缺项": [], "交人工": 手,
           "采用价格": {"原价": None, "计价单位": None, "折算单价": None, "折算": False}, "包装已完成": False, "原因": "",
           "匹配确认": val("匹配确认")}
    lian = R["单件量词"]

    def same_unit(u):  # 数量单位能否对上销售单位的计数
        return u == sell["计数"] or u == sell["叫法"] or (sell["计数"] == "个" and u in lian)

    # 2 核心缺项：(项, 问句键)
    core = []
    m = val("匹配确认")
    if m == "不匹配":
        out.update(资料状态="不匹配结束", 动作="完成", 原因="商家说不匹配")
        return out
    if m == "类似款":
        手.append("只有类似款，接不接受替代你定")
    elif m != "完全匹配":
        core.append(("匹配确认", "匹配确认"))
    # 定制款：普通起订量不判，只按定制起订量判（>上限记起订量缺、键 类似现货）
    custom = val("定制款") is True
    if custom:
        n, u = val("定制起订量"), (facts.get("定制起订量") or {}).get("单位", "不明")
        if n is None:
            core.append(("起订量", "定制起订量"))
        elif not same_unit(u):
            core.append(("起订量", "定制起订量.单位不明"))
        elif n > R["定制起订上限"]:
            core.append(("起订量", "类似现货"))
    # 先后见 AGENT.md 4.4：同款 → 定制起订 → 包装尺寸重量、贴标 → 价格和起订量 → 包装方式
    b = facts.get("包装")
    if not b or b.get("口径") == "产品":
        core += [("包装尺寸", "包装尺寸"), ("带包装重量", "带包装重量")]
    else:
        bad = None
        if b.get("口径") == "不明":
            bad = "包装尺寸.口径不明"
        elif b.get("对应单位") == "不明" or (b.get("对应单位") == "单个" and sell["计数"] == "套"):
            bad = "包装尺寸.对应不明"
        elif b.get("单位明确") is False:
            bad = "包装尺寸.单位不明"
        if bad:
            core += [("包装尺寸", bad), ("带包装重量", bad)]
        else:
            if not all((b.get(k) or 0) > 0 for k in "长宽高"):
                core.append(("包装尺寸", "包装尺寸"))
            if not (b.get("重量克") or 0) > 0:
                core.append(("带包装重量", "带包装重量"))
    t = val("贴标")
    if t not in ("能贴", "不能贴"):
        core.append(("贴标", "贴标"))
    elif t == "不能贴":
        手.append("不能贴标")
    p = facts.get("采购单价")
    if not p or p.get("值") is None:
        core.append(("采购单价", "采购单价"))
    else:
        u, pr, ap = p.get("单位", "不明"), p["值"], out["采用价格"]
        ap.update(原价=pr, 计价单位=u)
        n = sell.get("件数")
        if u == sell["计数"] or (sell["计数"] == "个" and u in lian):
            ap["折算单价"] = pr
        elif u in lian and sell["计数"] == "套" and isinstance(n, int) and not isinstance(n, bool) and n > 0:
            ap.update(折算单价=round(pr * n, 6), 折算=True)
        else:
            core.append(("采购单价", "采购单价.单位不明"))
    if not custom:
        s = facts.get("起订量")
        if not s or s.get("值") is None:
            core.append(("起订量", "起订量"))
        elif not (s.get("单位") == sell["计数"] or (sell["计数"] == "个" and s.get("单位") in lian)):
            core.append(("起订量", "起订量.单位不明"))
    if not val("包装方式"):
        core.append(("包装方式", "包装方式"))
    # 辅助项：无法提供也算有
    aux = []
    for k in R["辅助项"]:
        v = val(k)
        ok = (v > 0 if k == "每箱数量" and isinstance(v, (int, float)) else
              v in (("能", "不能") if k == "中性包装" else ("已发", "不能提供"))
              if k in ("中性包装", "实拍图", "视频") else False)
        if not ok and k not in gone:
            aux.append((k, k))
    out["包装已完成"] = not {"包装尺寸", "带包装重量"} & {i for i, _ in core}
    uniq = lambda xs: list(dict.fromkeys(xs))
    out["核心缺项"], out["辅助缺项"] = uniq(i for i, _ in core), [i for i, _ in aux]
    if not core:
        out["资料状态"] = "核心资料齐全"
    # 3 能问
    askable = lambda k: k.split(".")[0] not in gone and ask_n.get(k.split(".")[0], 0) < R["每项最多问次数"]
    fill = lambda s: (s.replace("{销售单位}", sell["叫法"]).replace("{计数}", sell["计数"])
                      .replace("{关键规格}", cand.get("关键规格") or ""))
    # 4 待决策
    手 += ex["待决策"]
    看不懂 = ex.get("看不懂") or []  # 缺当 []；程序不猜，原话原样交人工（AGENT.md 3.10、5.6）
    手 += ["看不懂：" + x["原话"] for x in 看不懂]
    n = sell.get("件数")
    装数不明 = not (isinstance(n, int) and not isinstance(n, bool) and n > 0) or sell["计数"] not in ("个", "套")
    if 装数不明:
        手.append("销售单位装数不明")
    pending = bool(手) and ("只有类似款，接不接受替代你定" in 手 or ex["待决策"] or 看不懂 or 装数不明)
    def stop(act, why):
        out.update(动作=act, 原因=why)
        return out
    # 5 先后拦截
    if 人工.get("暂停"):
        return stop("人工暂停", "人工暂停")
    if (inp.get("最后发送") or {}).get("结果") == "未知":
        return stop("核回执", "最后一次发送结果未知")
    if pending:
        return stop("待你决策", "有事要你定")
    now = datetime.fromisoformat(inp["现在"])
    last = inp.get("最后发送")
    # 反问回答，拼在问句前
    pre = "".join(fill(R["反问回答"][r]) for r in ex["商家反问"])
    def send(sentence, keys, why):
        out.update(动作="发送", 下一句=pre + sentence, 这次问=uniq(k.split(".")[0] for k in keys), 原因=why)
        return out
    # 6 我方最后说话
    if inp.get("最新消息方") == "我方":
        # 收口只在催回发完之后：24 小时催一次，催回发出后再等 24 小时（AGENT.md 4.10）
        if (core and last and last["结果"] == "成功"
                and ask_n.get("催回", 0) >= R["最多催回次数"]
                and now - datetime.fromisoformat(last["时间"]) >= timedelta(hours=R["无回复收口小时"])):
            out["资料状态"] = "资料未齐已收口"
            return stop("完成", "发送后超时没回复")
        # 催回键不是资料项：不进 askable 和辅助项，次数单独按 最多催回次数 判
        if (last and last["结果"] == "成功"
                and now - datetime.fromisoformat(last["时间"]) >= timedelta(hours=R["催回小时"])
                and ask_n.get("催回", 0) < R["最多催回次数"]):
            return send(q["催回"], ["催回"], "催回")
        return stop("等商家回复", "等对方回")
    # 7 首轮
    if inp.get("最新消息方") == "无" and not ask_n:
        if not cand.get("关键规格"):
            sys.exit("错误：首轮需要候选.关键规格")
        return send(fill(q["首轮"]), ["匹配确认", "包装尺寸", "带包装重量"], "首轮")

    def pick(items):  # 8/9 取前 N 个能问的；只有 包装尺寸+带包装重量 这组算 1 问，其他合并组按键数算（AGENT.md 4.3）
        cs = uniq(k for _, k in items if askable(k))
        ks, parts, i, n = [], [], 0, 0
        while i < len(cs) and n < R["每条最多问题数"]:
            g = next((g for g in R["合并问句"] if "包装尺寸" in g["项"] and cs[i:i + len(g["项"])] and set(cs[i:i + len(g["项"])]) == set(g["项"])
                      and not any("." in k for k in cs[i:i + len(g["项"])])), None)
            if g:
                ks += cs[i:i + len(g["项"])]; parts.append(fill(g["问句"])); i += len(g["项"])
            else:
                ks.append(cs[i]); parts.append(fill(q[cs[i]])); i += 1
            n += 1
        # 非包装的成对合并（价格+起订量、实拍图+视频）：取到的正好是一整组才合并
        if len(parts) == len(ks):
            for g in R["合并问句"]:
                if set(g["项"]) == set(ks) and len(ks) == len(g["项"]) and not any("." in k for k in ks):
                    return ks, fill(g["问句"])
        return ks, "".join(parts)
    def end(why):
        if pre:
            return send("", [], why)
        return stop("完成", why)
    # 8 核心
    if core:
        if core[0][0] == "匹配确认":
            ks, s = pick(core[:1])
        else:
            ks, s = pick(core)
        if not ks:
            out["资料状态"] = "资料未齐已收口"
            return end("缺项都问不了了")
        return send(s, ks, "补核心项")
    # 9 辅助
    ks, s = pick(aux)
    if not ks:
        return end("资料够了")
    return send(s, ks, "补辅助项")


def check(got, exp):
    bad = []
    for k, v in exp.items():
        base = k[:-2] if k.endswith("不含") else k[:-1] if k.endswith("含") else k
        if base not in got:  # 字段不存在一律不过，期望 null 也不例外
            bad.append("%s 期望 %r 实得 字段不存在" % (k, v))
            continue
        if k.endswith("不含"):
            ok = not set(v) & set(got[base])
        elif k.endswith("含"):
            ok = set(v) <= set(got[base])
        elif isinstance(v, dict):
            ok = all(a in got[k] and got[k][a] == b for a, b in v.items())
        else:
            ok = got[k] == v
        if not ok:
            bad.append("%s 期望 %r 实得 %r" % (k, v, got.get(k[:-2] if k.endswith("不含") else k[:-1] if k.endswith("含") else k)))
    return bad


def main():
    a = sys.argv[1:]
    if not a:
        print(USAGE)
        return 0
    R = json.load(open(os.path.join(D, "rules.json"), encoding="utf-8"))
    if a[0] != "--selftest":
        print(json.dumps(judge(json.load(open(a[0], encoding="utf-8")), R), ensure_ascii=False, indent=1))
        return 0
    fails = 0
    for c in json.load(open(os.path.join(D, "用例.json"), encoding="utf-8")):
        bad = check(judge(c["输入"], R), c["期望"])
        fails += bool(bad)
        print("%s %s %s" % ("不过" if bad else "过", c["编号"], c["名"]))
        for b in bad:
            print("    " + b)
    print("共 %d 条，不过 %d" % (len(json.load(open(os.path.join(D, "用例.json"), encoding="utf-8"))), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
