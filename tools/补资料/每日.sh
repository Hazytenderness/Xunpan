#!/bin/zsh
# 补资料定时任务入口（launchd 调用）。本机在美东，launchd 在冬夏令时两个可能的本地钟点都唤醒，这里按北京时间放行。
#   每日.sh send 9      北京 9 点：建当天队列 → run.py 先发其他批次没发完的、再发补资料，到 18:00 或遇错停
#   每日.sh read 9,…,18 北京 9:00–18:00 每 10 分钟：扫消息列表，有新回复才 claude -p 读、记报价、回商家、推网站；18 点那轮只发日报
# 跑完把结果推给用户（微信，失败走飞书）。日志：~/Library/Logs/xunpan-buziliao.log
set -u
export PATH=/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin
X=$HOME/ClaudeP/Xunpan; C=$HOME/.cache/xunpan; cd $X || exit 1
mode=$1; hours=$2
H=$(TZ=Asia/Shanghai date +%-H); D=$(TZ=Asia/Shanghai date +%F)
[[ ",$hours," == *",$H,"* ]] || exit 0
[[ $mode == send ]] && { stamp=$C/buziliao_send_${D}_$H; [[ -e $stamp ]] && exit 0; touch $stamp; }
echo "=== $(TZ=Asia/Shanghai date '+%F %T') 北京 $mode"

notify() { python3 -c "import sys;sys.path.insert(0,'$HOME/ClaudeP/04_工具/comp_common');from notify import push;push(sys.stdin.read(),chat='oc_a22f9557a1e54f584b81ced44430abcf')" <<< "$1"; }  # 发到飞书「ai协同」群（用户定·10/8）

if [[ $mode == send ]]; then
  git pull -q --rebase --autostash || echo "git pull 失败，接着用本地"
  git -C $HOME/ClaudeP/06_VibeCoding/ataous/ataous-site-night pull -q --rebase || echo "网站夜间副本 pull 失败，接着用本地"
  plan=$(python3 tools/补资料/建队列.py 2>&1) || { notify "补资料：建队列失败 $plan"; exit 1; }
  echo $plan
  # 建完就提交队列，发送中途停了也不留未提交改动（10-09 发送一开始就停，队列没提交，挡了 12:02 的复核导出）
  git add batches/补资料 && git commit -q -m "补资料 $D 建队列" -- batches/补资料 && git push -q
  # 其他批次没发完的待发R1（建队列已把对应款不缺资料的改成不用发）先发，再发补资料；任何一批停了就都停
  out=""; rc=0
  for b in $(python3 -c "import sys;sys.path.insert(0,'tools/lib');from base import batch_dirs,load_queue;print(' '.join(str(b) for b in batch_dirs() if b.name!='补资料' and any(x['状态']=='待发R1' and x.get('旺旺名') for x in load_queue(b))))") batches/补资料; do
    o=$(python3 tools/run.py $b 2>&1); rc=$?; out+=$'\n'"$o"; echo $o
    [[ $rc != 0 ]] && break
  done
  # 正常收工不发群（数字进 18 点后的日报）；停了才推一句【用户定·10/9】
  if [[ $rc == 3 ]]; then
    why=$(grep '停止：' <<< "$out" | tail -1 | python3 -c "import sys,json;s=sys.stdin.read();d=json.loads(s[s.index('{'):]) if '{' in s else {};print((d.get('结果') or d.get('错误') or '原因见日志').replace('停止:',''))")
    notify "⚠ 发询盘停了（$(TZ=Asia/Shanghai date +%H:%M)）：$why。今天已发 $(grep -c " 成功$" <<< "$out") 家，需要你看一下 1688"
  fi
elif [[ $mode == read ]]; then
  # 每 10 分钟由 launchd 唤醒：先纯脚本扫一次消息列表，有新回复才启动 AI；上一轮还没跑完就跳过
  mkdir $C/buziliao_read.lock 2>/dev/null || exit 0
  trap 'rmdir $C/buziliao_read.lock' EXIT
  # 北京 18 点那一轮只发当天日报（一天一次），不再扫描
  if [[ $H == 18 ]]; then
    [[ -e $C/buziliao_daily_$D ]] || { touch $C/buziliao_daily_$D; notify "$(python3 tools/补资料/日报.py daily)"; }
    exit 0
  fi
  scan=$(python3 tools/watch.py 0.01 2>&1)
  if grep -q "停止" <<< "$scan"; then
    [[ -e $C/buziliao_scanstop_$D ]] || { touch $C/buziliao_scanstop_$D; notify "⚠ 读回复扫消息列表停了，需要你看一下 1688：$(grep 停止 <<< "$scan" | tail -1)"; }
  elif grep -q "^新回复|" <<< "$scan"; then
    echo $scan
    git -C $HOME/ClaudeP/06_VibeCoding/ataous/ataous-site-night pull -q --rebase 2>/dev/null
    # launchd 下读不到钥匙串登录态，用长期令牌（仓库外文件，不进 git）
    export CLAUDE_CODE_OAUTH_TOKEN=$(<$HOME/.config/xunpan/claude_token)
    # ⛔不要 2>&1：claude -p 的警告走 stderr，混进来会顶掉汇报
    claude -p "$(cat tools/补资料/读回复提示词.md)

本次扫到的新回复：
$(grep '^新回复|' <<< "$scan")

今天已经报过的「要你定」（不要再报）：
$(python3 tools/补资料/日报.py asked)" \
      --allowedTools "Bash(python3:*)" "Bash(TZ=Asia/Shanghai date:*)" "Read" \
      < /dev/null > $C/buziliao_read.out 2> $C/buziliao_read.err
    rc=$?; cat $C/buziliao_read.out; [[ -s $C/buziliao_read.err ]] && tail -5 $C/buziliao_read.err
    # 提交这次有回复的条目所在批次（只提交这些目录，别的会话没提交的批次不碰）
    dirs=($(python3 -c "import sys;sys.path.insert(0,'tools/lib');from base import find;print(' '.join(sorted({str(find(l.split('|')[1])[0].relative_to('$X')) for l in sys.stdin if l.startswith('新回复|')})))" <<< "$scan"))
    (( ${#dirs} )) && git add $dirs && git commit -q -m "补资料读回复 $(TZ=Asia/Shanghai date '+%F %H:%M')" -- $dirs && { git pull -q --rebase --autostash; git push -q; }
    if [[ $rc != 0 || ! -s $C/buziliao_read.out ]]; then notify "⚠ 读回复没跑成（$(TZ=Asia/Shanghai date +%H:%M)），原因在日志 xunpan-buziliao.log"
    else
      # 累加当天统计；只把「停了」和新出现的「要你定」当场推，其余进 18 点日报
      now=$(python3 tools/补资料/日报.py round $C/buziliao_read.out)
      [[ -n $now ]] && notify "$now"
    fi
  fi
fi
