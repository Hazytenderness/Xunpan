#!/bin/zsh
# 补资料定时任务入口（launchd 调用）。本机在美东，launchd 在冬夏令时两个可能的本地钟点都唤醒，这里按北京时间放行。
#   每日.sh send 9      北京 9 点：建当天队列 → run.py 连发到 18:00 或遇错停
#   每日.sh read 12,17  北京 12、17 点：claude -p 无人值守读回复、记报价、回商家、推网站
# 跑完把结果推给用户（微信，失败走飞书）。日志：~/Library/Logs/xunpan-buziliao.log
set -u
export PATH=/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin
X=$HOME/ClaudeP/Xunpan; C=$HOME/.cache/xunpan; cd $X || exit 1
mode=$1; hours=$2
H=$(TZ=Asia/Shanghai date +%-H); D=$(TZ=Asia/Shanghai date +%F)
[[ ",$hours," == *",$H,"* ]] || exit 0
stamp=$C/buziliao_${mode}_${D}_$H; [[ -e $stamp ]] && exit 0; touch $stamp
echo "=== $(TZ=Asia/Shanghai date '+%F %T') 北京 $mode"

notify() { python3 -c "import sys;sys.path.insert(0,'$HOME/ClaudeP/04_工具/comp_common');from notify import push;push(sys.stdin.read())" <<< "$1"; }

if [[ $mode == send ]]; then
  git pull -q --rebase --autostash || echo "git pull 失败，接着用本地"
  plan=$(python3 tools/补资料/建队列.py 2>&1) || { notify "补资料：建队列失败 $plan"; exit 1; }
  echo $plan
  out=$(python3 tools/run.py batches/补资料 2>&1); rc=$?
  echo $out
  n=$(grep -c " 成功$" <<< "$out")
  msg="补资料 $D 发询盘 ${n} 家。排队情况：$(head -1 <<< "$plan")"
  [[ $rc == 3 ]] && msg="⚠ 补资料发送停了，需要你看一下 1688（多半是滑块/验证）：$(grep '停止' <<< "$out" | tail -1)
$msg"
  notify "$msg"
elif [[ $mode == read ]]; then
  # launchd 下读不到钥匙串登录态，用长期令牌（仓库外文件，不进 git）
  export CLAUDE_CODE_OAUTH_TOKEN=$(<$HOME/.config/xunpan/claude_token)
  # ⛔不要 2>&1：claude -p 的警告走 stderr，混进来会顶掉汇报
  claude -p "$(cat tools/补资料/读回复提示词.md)" \
    --allowedTools "Bash(python3:*)" "Bash(git add:*)" "Bash(git commit:*)" "Bash(git pull:*)" "Bash(git push:*)" "Bash(git status:*)" "Bash(TZ=Asia/Shanghai date:*)" "Read" \
    < /dev/null > $C/buziliao_read.out 2> $C/buziliao_read.err
  rc=$?; cat $C/buziliao_read.out; [[ -s $C/buziliao_read.err ]] && tail -5 $C/buziliao_read.err
  if [[ $rc != 0 || ! -s $C/buziliao_read.out ]]; then notify "⚠ 补资料读回复没跑成（rc=$rc）：$(tail -c 300 $C/buziliao_read.err)"
  else notify "补资料读回复 $D $H 点：
$(cat $C/buziliao_read.out)"; fi
fi
