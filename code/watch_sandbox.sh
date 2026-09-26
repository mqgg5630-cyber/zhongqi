#!/usr/bin/env bash
# watch_sandbox.sh - sandbox-side resident watchdog (keeps this clone talking to GitHub)
# rounds: fetch -> fast-forward if clean -> push if ahead -> heartbeat log
REPO="/home/user/zhongqi"
BRANCH="arena/01a0a949-zhongqi"
LOG="$REPO/results/sync/sandbox_watch.log"
INTERVAL="${1:-60}"
mkdir -p "$(dirname "$LOG")"
cd "$REPO" || exit 1
round=0
echo "[$(TZ=Asia/Shanghai date '+%F %T') CST] watch_sandbox start branch=$BRANCH interval=${INTERVAL}s" >> "$LOG"
while true; do
  round=$((round+1))
  ts="$(TZ=Asia/Shanghai date '+%F %T')"
  out=""
  git fetch origin "$BRANCH" >/dev/null 2>&1
  local_head="$(git rev-parse HEAD)"
  remote_head="$(git rev-parse FETCH_HEAD 2>/dev/null)"
  dirty="$(git status --porcelain | wc -l)"
  if [ "$local_head" != "$remote_head" ] && [ "$dirty" = "0" ]; then
    git merge --ff-only FETCH_HEAD >/dev/null 2>&1 && out="$out pulled->$(git rev-parse --short HEAD)"
  elif [ "$local_head" != "$remote_head" ]; then
    out="$out remote=${remote_head:0:7} local-dirty(${dirty} files) skip-pull"
  fi
  if [ "$dirty" = "0" ]; then
    ahead="$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo 0)"
    up="$(git rev-list --count FETCH_HEAD..HEAD 2>/dev/null || echo 0)"
    if [ "${up:-0}" -gt 0 ]; then
      if git push origin HEAD:"$BRANCH" >/dev/null 2>&1; then out="$out pushed-${up}-commits"; else out="$out push-failed"; fi
    fi
  fi
  echo "[$ts CST] round $round head=$(git rev-parse --short HEAD) branch=$BRANCH$out" >> "$LOG"
  tail -c 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  sleep "$INTERVAL"
done
