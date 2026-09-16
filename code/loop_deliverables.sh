#!/usr/bin/env bash
# loop_deliverables.sh —— 自循环任务：生成 docx / pptx → 推到分支 → 请本机核验 →
# 读本机推回来的结论 → 修 → 再来一轮，直到"结果没问题"。
#
# 用法（在仓库根目录）：
#   bash code/loop_deliverables.sh                       # 最多 5 轮，等本机值守回传结论
#   bash code/loop_deliverables.sh --max-rounds 3
#   bash code/loop_deliverables.sh --agent-only          # 只跑 agent 侧（本机还没连通时用）
#   bash code/loop_deliverables.sh --request "verify: 中期 docx + H 版 PPT"
#   bash code/loop_deliverables.sh --status              # 只看当前握手状态与最近一次本机结论
#   bash code/loop_deliverables.sh --interval 20         # 轮询远端握手的间隔（秒）
#
# 一轮做的事：
#   1. python code/build_deliverables.py
#      重生成 scope=loop 的 docx / pptx（复用仓库既有生成脚本）→ 逐个断言
#      （页数 / 段落数 / 封面信息 / 术语）→ 与 HEAD 比内容指纹（一致就还原原字节，
#      避免无意义的二进制 churn）→ 跑闸门 code/check_all.sh →
#      写 results/status/agent_manifest.json（含每个文件的 sha256）
#      并把 code/deliverables.tsv 编译成 results/status/success_criteria.json
#   2. bash skills/git-sync/scripts/agent-handsfree.sh \
#          --sync "<本轮提交信息>" --request "<本机要核验什么>" --timeout auto
#      = 提交推送 → 把 handshake 置为 awaiting_check → 轮询等本机值守
#        （本机自动 pull → 跑 code/local_check.ps1 → 把 passed/failed 推回分支）
#        → 再用 success_criteria.json 复核 → 都过就 accept，闭环
#   3. 按退出码决定下一步：
#        0 本机核验通过 + 验收标准通过 + 已 accept  → 收工（exit 0）
#        2 本机判失败                              → 打印失败详情，下一轮（修完再来）
#        3 本机值守不在线 / 超时                    → 停：把本机那段 PowerShell 再贴给用户
#      agent 侧生成就失败                          → 停（exit 1），先修生成
#
# 退出码：0 闭环完成；1 agent 侧生成/闸门失败；2 本机判失败且轮次用尽；3 本机未连通。
set -u -o pipefail
cd "$(dirname "$0")/.."

MAX_ROUNDS=5
INTERVAL=15
TIMEOUT=auto
AGENT_ONLY=0
STATUS_ONLY=0
REQUEST="verify: 本轮 docx / pptx 已回到本机（sha256 与 agent 清单一致、包结构完好、闸门通过）"
SYNC_PREFIX="feat(loop): 重生成 docx + pptx 并自检"

while [ $# -gt 0 ]; do
  case "$1" in
    --max-rounds) MAX_ROUNDS="$2"; shift 2 ;;
    --interval)   INTERVAL="$2"; shift 2 ;;
    --timeout)    TIMEOUT="$2"; shift 2 ;;
    --request)    REQUEST="$2"; shift 2 ;;
    --sync)       SYNC_PREFIX="$2"; shift 2 ;;
    --agent-only) AGENT_ONLY=1; shift ;;
    --status)     STATUS_ONLY=1; shift ;;
    -h|--help)    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

HS="results/status/handshake.json"
HF="skills/git-sync/scripts/agent-handsfree.sh"
BUILD="code/build_deliverables.py"
PY=""; command -v python3 >/dev/null 2>&1 && PY="python3"
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY="python"

cur_round() {
  [ -f "$HS" ] || { echo 0; return; }
  [ -z "$PY" ] && { echo 0; return; }
  $PY -c "import json;print(int(json.load(open('$HS',encoding='utf-8-sig')).get('round') or 0))" 2>/dev/null || echo 0
}

show_latest_local_log() {  # $1 = round
  local r="$1" f
  f="$(ls -1 results/status/check_r${r}_*.txt 2>/dev/null | sort | tail -1)"
  if [ -z "$f" ]; then
    # 本机推回来的日志可能还没进本地工作区，从远端取
    local br
    br="$($PY -c "import json;print(json.load(open('skills/git-sync/sync.config.json',encoding='utf-8')).get('branch',''))" 2>/dev/null)"
    f="$(git ls-tree --name-only "origin/$br" results/status/ 2>/dev/null | grep "check_r${r}_" | sort | tail -1)"
    if [ -n "$f" ]; then
      echo "== 本机结论（远端 $f，末 40 行）"
      git show "origin/$br:$f" 2>/dev/null | tail -40
      return
    fi
  fi
  if [ -n "$f" ] && [ -f "$f" ]; then
    echo "== 本机结论（$f，末 40 行）"
    tail -40 "$f"
  else
    echo "== 本机这一轮还没有推回检查日志（results/status/check_r${r}_*.txt）"
  fi
}

if [ "$STATUS_ONLY" = 1 ]; then
  echo "== 当前握手：$(cur_round) 轮"
  bash skills/git-sync/scripts/agent-check.sh --read || true
  exit 0
fi

[ -z "$PY" ] && { echo "[ERROR] 找不到可用的 python" >&2; exit 1; }
[ -f "$BUILD" ] || { echo "[ERROR] 缺 $BUILD" >&2; exit 1; }

start_round=$(cur_round)
echo "################################################################"
echo "# 自循环开始：当前握手轮次 $start_round，本次最多跑 $MAX_ROUNDS 轮"
echo "# 模式：$([ "$AGENT_ONLY" = 1 ] && echo 'agent-only（不请本机核验）' || echo '完整闭环（本机值守回传结论）')"
echo "################################################################"

round=$start_round
for ((i = 1; i <= MAX_ROUNDS; i++)); do
  round=$(( $(cur_round) + 1 ))
  echo ""
  echo "==================== 第 $i/$MAX_ROUNDS 次尝试（将是握手第 $round 轮）===================="

  echo "-- 步骤 1：重生成 + 自检 + 写清单"
  if ! $PY "$BUILD" --round "$round"; then
    echo "[STOP] agent 侧生成或闸门没过 —— 先修这个，别把坏产物推给本机" >&2
    exit 1
  fi

  if [ "$AGENT_ONLY" = 1 ]; then
    echo "-- 步骤 2（--agent-only）：提交推送，不请本机核验"
    bash skills/git-sync/scripts/agent-sync.sh "$SYNC_PREFIX（agent-only 第 $i 次）" || exit 1
    echo ""
    echo "== agent 侧自循环通过：docx / pptx 已重生成、断言与闸门全过、已推到分支"
    echo "== 本机侧要跑起来才有真正的闭环：.\\watch.ps1 -Register（详见 README 第五节）"
    exit 0
  fi

  [ -f "$HF" ] || { echo "[ERROR] 缺 $HF —— git-sync skill 没装好，重跑 agent-install.sh" >&2; exit 1; }

  echo "-- 步骤 2：提交推送 + 请本机核验 + 等结论（timeout=$TIMEOUT interval=${INTERVAL}s）"
  set +e
  bash "$HF" --sync "$SYNC_PREFIX（第 $i 次尝试）" --request "$REQUEST" \
       --timeout "$TIMEOUT" --interval "$INTERVAL"
  rc=$?
  set -e
  echo "-- agent-handsfree 退出码：$rc"

  case "$rc" in
    0)
      echo ""
      echo "################################################################"
      echo "# 闭环完成：本机核验通过 + 验收标准通过 + 已 accept（第 $round 轮）"
      echo "# 产物在分支上，本机 .\\sync.ps1 / 值守 auto_pull 已经拿到；"
      echo "# 要看落地文件：.\\download.ps1 -Set final"
      echo "################################################################"
      exit 0
      ;;
    2)
      echo ""
      echo "-- 本机判失败，诊断如下（修完再跑一次本脚本即进入下一轮）："
      show_latest_local_log "$round"
      if [ "$i" -lt "$MAX_ROUNDS" ]; then
        echo "-- 还有 $((MAX_ROUNDS - i)) 次尝试；重跑生成（若失败原因是产物本身，这一步会修好它）"
        continue
      fi
      echo "[STOP] 轮次用尽仍未通过 —— 把上面的失败项列给用户" >&2
      exit 2
      ;;
    3)
      echo ""
      echo "################################################################"
      echo "# 本机值守不在线（或这一轮超时未回传）—— 循环停在这里，不假装成功"
      echo "#"
      echo "# 需要在你的 Windows 上做一次（只做一次）："
      echo "#   cd E:\\0github\\git-sync"
      echo "#   git clone -b <BRANCH> <ORIGIN_URL> <NEW_FOLDER>"
      echo "#   cd <NEW_FOLDER>"
      echo "#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"
      echo "#   .\\bootstrap.ps1 -Auto"
      echo "#   .\\doctor.ps1"
      echo "#   .\\watch.ps1 -Status"
      echo "#"
      echo "# 值守起来后再跑：bash code/loop_deliverables.sh"
      echo "################################################################"
      BR="$($PY -c "import json;print(json.load(open('skills/git-sync/sync.config.json',encoding='utf-8')).get('branch',''))" 2>/dev/null)"
      URL="$(git remote get-url origin 2>/dev/null)"
      echo "== 本机那段的真值：BRANCH=$BR"
      echo "==                 ORIGIN_URL=$URL"
      exit 3
      ;;
    *)
      echo "[STOP] agent-handsfree 返回意外退出码 $rc" >&2
      exit "$rc"
      ;;
  esac
done

echo "[STOP] 循环结束（未闭环）" >&2
exit 2
