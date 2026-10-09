#!/bin/zsh
# 夜间上游任务（launchd 在本地 6 点、7 点唤醒，按北京 19 点放行）【用户定·10/8】：
#   1 找货源：货源核实「待跑·缺货源」→ 遨虾主图搜 → 机械筛 → AI 审图 → 不足 3 家的 AI 写中文词文字补搜 → 再审图 → 排序 → 导入 → 保护核对
#   2 核页核 SKU：「待跑·待核页」（含第 1 步刚找到的）→ 建批次 → 核页 → 分块 AI 判同款 → 合并 → 推复核 → 匹配度写进目录
#   3 上线：测试 → 提交 → 推 GitHub 自动部署 → 核对构建成功（用户 10/8 长期授权每晚自动上线）
# 用网站夜间专用副本 ataous-site-night，不碰别人的工作副本；另一个会话 36 小时内在跑的款跳过。日志 ~/Library/Logs/xunpan-night.log
set -u
export PATH=/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin
X=$HOME/ClaudeP/Xunpan; SITE=$HOME/ClaudeP/06_VibeCoding/ataous/ataous-site-night; C=$HOME/.cache/xunpan
T=$X/tools/夜间; ACCOUNT=f451a19a9c22c7472e8c23bd4ca272d5
H=$(TZ=Asia/Shanghai date +%-H); D=$(TZ=Asia/Shanghai date +%F)
[[ ${1:-} == now || $H == 19 ]] || exit 0
[[ -e $C/night_$D ]] && exit 0
mkdir $C/night.lock 2>/dev/null || exit 0
trap 'rmdir $C/night.lock' EXIT
touch $C/night_$D
W=$C/night/$D; mkdir -p $W; R=$W/汇报.txt; : > $R
echo "=== $(TZ=Asia/Shanghai date '+%F %T') 北京 夜间开始"
say() { echo "$1"; echo "$1" >> $R; }   # 只用于 ⚠ 要人处理的事
SRC="今晚没有缺货源的款要找"; CHK="今晚没有要核的款"; PUSH=""; LIVE="网站没有变化，不用上线"; SKIP=0
# 飞书汇报【用户定·10/8：别发 JSON 和程序原始输出】
report() { printf '夜间任务 %s\n【找货源】%s\n【核同款】%s%s\n【上线】%s\n【要你处理】%s\n（另有 %s 款别的会话在处理，今晚跳过）' "$D" "$SRC" "$CHK" "${PUSH:+；$PUSH}" "$LIVE" "$( [[ -s $R ]] && cat $R || echo 无)" "$SKIP"; }
notify() { python3 -c "import sys;sys.path.insert(0,'$HOME/ClaudeP/04_工具/comp_common');from notify import push;push(sys.stdin.read(),chat='oc_a22f9557a1e54f584b81ced44430abcf')" <<< "$1"; }  # 发到飞书「ai协同」群（用户定·10/8）
export CLAUDE_CODE_OAUTH_TOKEN=$(<$HOME/.config/xunpan/claude_token)
# ⛔不要 2>&1：claude -p 的警告走 stderr，混进来会顶掉回报
ai() { claude -p "$1" --allowedTools "Read" "Write" "Bash(python3:*)" "Bash(curl:*)" < /dev/null 2>> $W/ai.err | tail -3; }

git -C $SITE pull -q --rebase || { notify "⚠ 夜间任务没跑：网站夜间副本 git pull 失败"; exit 1; }
git -C $X pull -q --rebase --autostash || echo "询盘仓库 pull 失败，接着用本地"
(cd $SITE && CLOUDFLARE_ACCOUNT_ID=$ACCOUNT npx wrangler r2 object get "ataous-data/jp/宠物/purchase.json" --remote --file $W/purchase.json >/dev/null 2>&1)
[[ -s $W/purchase.json ]] || { notify "⚠ 夜间任务没跑：读不到线上 purchase.json"; exit 1; }

# 另一个会话在跑的款：询盘仓库里非夜间、非补资料、36 小时内改过的批次，和供应商匹配里 36 小时内改过的非夜间批次
busy() { python3 - "$1" <<'EOF'
import json, sys, time, glob, os
from pathlib import Path
cut, s = time.time() - 36 * 3600, set()
for q in glob.glob(os.path.expanduser('~/ClaudeP/Xunpan/batches/*/queue.json')):
    n = Path(q).parent.name
    if n == '补资料' or n.endswith('夜间核页') or os.path.getmtime(q) < cut: continue
    s |= {k['序'] for x in json.load(open(q)) for k in x['对应款']}
for d in glob.glob(os.path.expanduser('~/ClaudeP/06_VibeCoding/ataous/供应商匹配/*/')):
    if d.rstrip('/').endswith('_夜间') or os.path.getmtime(d) < cut: continue
    for f in glob.glob(d + '任务清单*.json'):
        s |= {int(x['序']) for x in json.load(open(f))}
json.dump(sorted(s), open(sys.argv[1], 'w'))
print(len(s))
EOF
}
SKIP=$(busy $W/skip.json)

# ---------- 1 找货源 ----------
FB=$HOME/ClaudeP/06_VibeCoding/ataous/供应商匹配/${D//-/}_夜间; mkdir -p $FB
LEDGER=$T/找货源台账.json; [[ -e $LEDGER ]] || echo '{}' > $LEDGER
node $T/清单.mjs $SITE $W/purchase.json source $W/skip.json > $W/source.json
python3 - $W/source.json $LEDGER $FB/任务清单.json <<'EOF'
import json, sys, datetime
todo, led = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
cut = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
json.dump([x for x in todo if led.get(str(x['序']), '') < cut], open(sys.argv[3], 'w'), ensure_ascii=False)
EOF
NS=$(python3 -c "import json;print(len(json.load(open('$FB/任务清单.json'))))")
NALL=$(python3 -c "import json;print(len(json.load(open('$W/source.json'))))"); (( NS < NALL )) && SRC="缺货源 $NALL 款，14 天内找过的 $((NALL-NS)) 款跳过；" || SRC=""
if [[ $NS -gt 0 ]]; then
  python3 $T/找货源.py search $FB > $W/search.out 2>&1 || say "⚠ 遨虾搜索中断：$(tail -1 $W/search.out)"
  python3 $T/找货源.py screen $FB | tail -1
  for t in $FB/review/task_*.md(N); do ai "$(cat $T/审图提示词.md)

任务文件：$t"; done
  python3 $T/找货源.py need-kw $FB > $W/need-kw.txt
  if [[ -s $W/need-kw.txt ]]; then
    ai "$(cat $T/搜索词提示词.md)

词搜词.json 路径：$FB/词搜词.json
$(cat $W/need-kw.txt)"
    python3 $T/找货源.py kw $FB > $W/kw.out 2>&1 || say "⚠ 遨虾文字补搜中断：$(tail -1 $W/kw.out)"
    for t in $FB/review_kw/task_*.md(N); do ai "$(cat $T/审图提示词.md)

任务文件：$t"; done
  fi
  rank=$(python3 $T/找货源.py rank $FB | tail -1); echo "$rank" > $W/rank.out
  SRC+=$(python3 -c "import json,sys;r=json.loads(sys.argv[1]);print(f\"找了 {r['款']} 款，找到 {r['找到']} 款（其中选出的 3 家里有同款的 {r.get('入选有同款的款',0)} 款），没找到 {r['无结果']} 款\")" "$rank")
  python3 -c "import json;L=json.load(open('$FB/任务清单.json'));json.dump([x['序'] for x in L],open('$W/source_ids.json','w'))"
  node $T/保护核对.mjs snap $SITE $W/before_src.json >/dev/null
  # 已有候选的款不整组替换，新候选先追加、核完 SKU 再挑 3 家【用户定·10/8】
  if (cd $SITE && node scripts/night-candidates.mjs append $FB/seeds.json $W/appended.json > $W/append.out) && node $T/保护核对.mjs diff $SITE $W/before_src.json $W/source_ids.json 参考成本,参考成本说明,货源候选,图搜记录 > $W/protect1.txt; then
    python3 - $LEDGER $FB <<'EOF'
# 找到的记日期（14 天内不重找）；主图和文字都搜不到的记「跳过」，以后不再找【用户定·10/9】（「跳过」排在任何日期之后，取款时自然被筛掉）
import json, sys, datetime
from pathlib import Path
led, B = json.load(open(sys.argv[1])), Path(sys.argv[2])
none = {a for a, v in json.loads((B / 'seeds.json').read_text()).items() if v.get('图搜无结果')}
for x in json.loads((B / '任务清单.json').read_text()):
    led[str(x['序'])] = '跳过' if x['asin'] in none else datetime.date.today().isoformat()
json.dump(led, open(sys.argv[1], 'w'), ensure_ascii=False, indent=0)
EOF
  else
    echo "[]" > $W/appended.json; git -C $SITE checkout -- build/js; say "⚠ 找货源导入没通过保护核对，已撤回：$(head -3 $W/protect1.txt 2>/dev/null)"
  fi
fi

# ---------- 2 核页核 SKU ----------
HB=$X/batches/${D}-夜间核页
node $T/清单.mjs $SITE $W/purchase.json check $W/skip.json > $W/products.json
NC=$(python3 -c "import json;print(len(json.load(open('$W/products.json'))))")

if [[ $NC -gt 0 ]]; then
  export XUNPAN_WORK=$W XUNPAN_BATCH=$HB
  cd $X
  python3 tools/核SKU/建批次.py $HB | tail -1
  python3 tools/hepage.py $HB > $W/hepage.out 2>&1; [[ $? == 3 ]] && { say "⚠ 核页停了（多半是 1688 验证），只判已核到的页：$(grep 停止 $W/hepage.out | tail -1)"; notify "⚠ 夜间核页停了，需要你看一下 1688：$(grep 停止 $W/hepage.out | tail -1)"; }
  k=0
  while true; do
    ids=$(python3 tools/核SKU/ready.py 10 | tail -1); [[ -z $ids || $ids == *可分* ]] && break
    k=$((k+1)); python3 tools/核SKU/prep.py n$k $ids | tail -1
    ai "按 $X/tools/核SKU/匹配说明.md 处理块目录 $W/chunks/n$k （先 Read 那份说明，输入在块目录 input.json，结果写块目录 match.json）。"
  done
  python3 tools/核SKU/merge.py > $W/merge.out 2>&1
  [[ -s $HB/核页规格匹配.json ]] && CHK=$(python3 -c "import json,sys,collections;m=json.load(open(sys.argv[1]));c=collections.Counter(x['结论'] for x in m);print(f\"核了 {len({x['序'] for x in m})} 款 {len(m)} 家：完全匹配 {c['同款']}、部分匹配 {c['近似']}、不匹配 {c['款不对']}\"+(f\"、已下架 {c['下架']}\" if c['下架'] else ''))" $HB/核页规格匹配.json)
  if [[ -s $HB/核页规格匹配.json ]] && python3 tools/build_review_feed.py $HB --site $SITE > $W/feed.out 2>&1; then
    python3 tools/push_review_feed.py $HB > $W/push.out 2>&1
    PUSH=$(python3 -c "import json,sys;r=json.loads(sys.argv[1]);print(f\"报价推上网站 {r['新增']} 条（自动采纳 {r['自动采纳']} 条）\"+(f\"，{len(r['未导入'])} 条没导入\" if r['未导入'] else ''))" "$(tail -1 $W/push.out)" 2>/dev/null) || say "⚠ 报价推送失败：$(tail -1 $W/push.out)"
    python3 -c "import json;json.dump(sorted({k['序'] for x in json.load(open('$HB/queue.json')) for k in x['对应款']}),open('$W/check_ids.json','w'))"
    node $T/保护核对.mjs snap $SITE $W/before_chk.json >/dev/null
    if (cd $SITE && node scripts/import-match.mjs $HB --apply > $W/match.out) && node $T/保护核对.mjs diff $SITE $W/before_chk.json $W/check_ids.json 货源候选 > $W/protect2.txt; then :
    else git -C $SITE checkout -- build/js; say "⚠ 匹配度导入没通过保护核对，已撤回：$(head -3 $W/protect2.txt 2>/dev/null)"; fi
  fi
  git add $HB && git commit -q -m "夜间核页核 SKU $D" -- $HB && git pull -q --rebase --autostash && git push -q
fi
git -C $X add tools/夜间/找货源台账.json && git -C $X commit -q -m "夜间找货源台账 $D" -- tools/夜间/找货源台账.json && git -C $X push -q

# ---------- 2b 新旧合并：追加过新候选的款，按匹配度挑 3 家（没核成的排在部分匹配和不匹配之间）【用户定·10/8】----------
if [[ -s $W/appended.json && $(<$W/appended.json) != "[]" ]]; then
  node $T/保护核对.mjs snap $SITE $W/before_trim.json >/dev/null
  if (cd $SITE && node scripts/night-candidates.mjs trim $W/appended.json > $W/trim.out) && node $T/保护核对.mjs diff $SITE $W/before_trim.json $W/appended.json 参考成本,参考成本说明,货源候选 > $W/protect3.txt; then
    SRC+="；已有候选的$(cat $W/trim.out)"
  else git -C $SITE checkout -- build/js; say "⚠ 新旧合并没通过保护核对，今晚网站改动全部撤回：$(head -3 $W/protect3.txt 2>/dev/null)"; fi
fi

# ---------- 3 上线 ----------
cd $SITE
if git diff --quiet build/js; then :
elif npm test > $W/test.out 2>&1 && npm run check > $W/check.out 2>&1 && git diff --check; then
  git add build/js/products.js build/js/products-sources.js
  git commit -q -m "夜间任务 $D：找货源与核 SKU 匹配度写入（自动，用户 10/8 授权）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  # 提交或推送失败要如实报没上线，不能拿上一次提交的构建结果冒充（10-08 夜间副本缺提交身份，提交失败却报了「已上线」）
  if [[ $(git rev-parse HEAD) == $(git rev-parse @{u}) ]] || ! { git pull -q --rebase && git push -q origin main; }; then
    LIVE="没上线"; say "⚠ 提交或推送失败，今晚没上线：$(git status -sb | head -1)"; notify "$(report)"; exit 1
  fi
  sha=$(git rev-parse --short HEAD); st=""
  for i in {1..40}; do st=$(gh api repos/Hazytenderness/ataous-site/commits/$sha/check-runs --jq '.check_runs[]|select(.name|test("ataous"))|.status+" "+(.conclusion//"")' 2>/dev/null); [[ $st == completed* ]] && break; sleep 15; done
  [[ $st == "completed success" ]] && LIVE="已上线（$(TZ=Asia/Shanghai date +%H:%M)，版本 $sha）" || { LIVE="没确认成功"; say "⚠ 上线没确认成功（$sha：${st:-查不到构建状态}）"; }
else
  git checkout -- build/js; LIVE="测试没过，今晚不上线"; say "⚠ 测试没过，今晚不上线：$(grep -E '^# fail|not ok' $W/test.out | head -2)"
fi
echo "=== $(TZ=Asia/Shanghai date '+%F %T') 北京 夜间结束"
notify "$(report)"
