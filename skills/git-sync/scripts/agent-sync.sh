#!/usr/bin/env bash
# agent-sync.sh - the assistant-side "commit + push" for one round of work.
#
# Usage (from the repo root or anywhere inside it):
#     bash skills/git-sync/scripts/agent-sync.sh "feat: ..."            # commit + push
#     bash skills/git-sync/scripts/agent-sync.sh "feat: ..." --no-gate  # skip the checks
#     bash skills/git-sync/scripts/agent-sync.sh --status               # just report
#
# What it does, in order:
#   1. branch guard   - refuses to run on main/master and refuses to touch any
#                       branch other than the one in sync.config.json
#   2. fetch          - always refresh refs/remotes/origin/* first
#   3. sanity check   - if HEAD is not a descendant of origin/<branch> (the
#                       sandbox .git silently resetting to the baseline commit
#                       does exactly this), run agent-recover.sh logic inline so
#                       the worktree is kept and history is restored
#   4. gate           - run the "gate" command from sync.config.json
#                       (default: bash code/check_all.sh), abort on failure
#   5. commit + push  - git add -A, commit with the given message, push to the
#                       configured branch only
#
# Exit codes: 0 ok, 1 usage/guard error, 2 gate failed, 3 git error.

set -u -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

CFG="skills/git-sync/sync.config.json"
BRANCH=""; REMOTE="origin"; GATE="bash code/check_all.sh"
if [ -f "$CFG" ]; then
  BRANCH="$(python3 -c "import json;print(json.load(open('$CFG',encoding='utf-8')).get('branch',''))" 2>/dev/null || true)"
  REMOTE="$(python3 -c "import json;print(json.load(open('$CFG',encoding='utf-8')).get('remote','origin'))" 2>/dev/null || true)"
  GATE_CFG="$(python3 -c "import json;print(json.load(open('$CFG',encoding='utf-8')).get('gate',''))" 2>/dev/null || true)"
  [ -n "$GATE_CFG" ] && GATE="$GATE_CFG"
fi
[ -z "$BRANCH" ] && BRANCH="$(git rev-parse --abbrev-ref HEAD)"

MSG=""; RUN_GATE=1
for arg in "$@"; do
  case "$arg" in
    --no-gate) RUN_GATE=0 ;;
    --status)  MSG="__status__" ;;
    -*)        echo "unknown option: $arg" >&2; exit 1 ;;
    *)         MSG="$arg" ;;
  esac
done

echo "== repo  : $REPO_ROOT"
echo "== branch: $BRANCH (remote $REMOTE)"
echo "== gate  : $([ "$RUN_GATE" = 1 ] && echo "$GATE" || echo '(skipped)')"

# ---------------------------------------------------------------- 1. guard
case "$BRANCH" in
  main|master) echo "[REFUSED] never work on $BRANCH - set branch in $CFG" >&2; exit 1 ;;
esac
CURRENT="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT" != "$BRANCH" ]; then
  echo "[REFUSED] HEAD is on $CURRENT, expected $BRANCH" >&2
  echo "          this session must stay on its own branch" >&2
  exit 1
fi

# ---------------------------------------------------------------- 2. fetch
if ! git fetch "$REMOTE" 2>&1 | tail -2; then
  echo "[ERROR] git fetch failed" >&2; exit 3
fi
ORIGIN="$REMOTE/$BRANCH"

status_report() {
  echo "-- HEAD        : $(git log -1 --oneline)"
  echo "-- $ORIGIN : $(git log -1 --oneline "$ORIGIN" 2>/dev/null || echo '(not fetched yet)')"
  echo "-- uncommitted : $(git status --porcelain | wc -l) file(s)"
  echo "-- stash       : $(git stash list | wc -l) entr(y|ies)"
}

if [ "${MSG:-}" = "__status__" ]; then
  status_report
  exit 0
fi

# ------------------------------------------------- 3. divergence / recovery
if git rev-parse --verify --quiet "$ORIGIN" >/dev/null; then
  if ! git merge-base --is-ancestor HEAD "$ORIGIN" 2>/dev/null \
     && ! git merge-base --is-ancestor "$ORIGIN" HEAD 2>/dev/null; then
    echo "!! HEAD and $ORIGIN have diverged (the sandbox .git reset to the baseline commit does this)."
    echo "   keeping the worktree, moving HEAD onto $ORIGIN ..."
    git reset --mixed "$ORIGIN" || { echo "[ERROR] recovery failed" >&2; exit 3; }
  elif git merge-base --is-ancestor HEAD "$ORIGIN" 2>/dev/null; then
    BEHIND="$(git rev-list --count "HEAD..$ORIGIN")"
    if [ "$BEHIND" != "0" ]; then
      echo "!! $BEHIND commit(s) behind $ORIGIN - fast-forwarding"
      git reset --mixed "$ORIGIN" || { echo "[ERROR] fast-forward failed" >&2; exit 3; }
    fi
  fi
fi

# ---------------------------------------------------------------- 4. gate
if [ "$RUN_GATE" = 1 ] && [ -n "$GATE" ]; then
  echo "== gate: $GATE"
  if ! bash -c "$GATE"; then
    echo "[GATE FAILED] nothing was committed. Fix the checks first." >&2
    exit 2
  fi
fi

# --------------------------------------------------------- 5. commit + push
git add -A
if [ -z "$(git status --porcelain)" ]; then
  echo "== nothing new to commit"
else
  [ -z "${MSG:-}" ] && MSG="sync: agent update $(date '+%Y-%m-%d %H:%M')"
  git -c user.name="Arena Agent" -c user.email="agent@arena.ai" commit -q -m "$MSG"
  echo "== committed: $(git log -1 --oneline)"
fi

if ! git push "$REMOTE" "$BRANCH" 2>&1 | tail -3; then
  echo "[ERROR] push failed" >&2
  status_report
  exit 3
fi

echo ""
echo "== done: $(git log -1 --oneline --decorate)"
echo "== user side: .\\sync.ps1   (then .\\download.ps1 -Set final to copy the deliverables out)"
