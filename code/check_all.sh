#!/usr/bin/env bash
# check_all.sh —— 提交前闸门（agent-sync.sh 每次 push 前跑；本机值守 local_check.ps1 也跑它）
#
# 三段，从"任何机器都能跑"到"需要依赖才能跑"：
#   A. skill 通用闸门（code/check_gate.sh，上游 v2.7.4 原样）：
#      .ps1 全 ASCII / sync.config.json 分支守卫 / 根目录脚本与 skill 逐字节一致 /
#      $var: 驱动器写法 / watch.ps1 每条退出路径都有收尾行 / .ps1 能被 PowerShell 解析
#   B. 交付物在场 + 体积下限（纯 bash，读 code/deliverables.tsv；不需要 python）
#   C. 文档与 PPT 质量核对（需要 python + python-docx / python-pptx / pillow）：
#      模板格式零改动 / docx 与 PPT 口径一致 / PPT 版式不溢出 / .ps1 引号括号平衡
#      —— 依赖缺失时**大声 SKIP**（本机没装 python 也能把回执推回去，
#         这些检查在 agent 沙箱每次 push 前一定会跑）
#
# 退出码：0 通过，1 失败。
set -u -o pipefail
cd "$(dirname "$0")/.."
fail=0

# Windows/conda 常常只有 python 没有 python3 —— 解析一次，并且证明它真能跑
PY=""
if command -v python3 >/dev/null 2>&1; then PY="python3"
elif command -v python >/dev/null 2>&1; then PY="python"
fi
PY_OK=0
if [ -n "$PY" ] && $PY -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then PY_OK=1; fi

echo "########## A. skill 通用闸门（.ps1 ASCII / 分支守卫 / 脚本一致 / 值守收尾行）"
if [ -f code/check_gate.sh ]; then
    bash code/check_gate.sh || fail=1
else
    echo "[FAIL] code/check_gate.sh 不存在（重装：agent-install.sh --source <git-sync 源>）"
    fail=1
fi

echo ""
echo "########## B. 交付物在场 + 体积下限（code/deliverables.tsv）"
TSV="code/deliverables.tsv"
if [ ! -f "$TSV" ]; then
    echo "[FAIL] $TSV 不存在"
    fail=1
else
    b_ok=0; b_warn=0
    while IFS=$'\t' read -r p kind minb expect scope note; do
        case "$p" in ''|'#'*) continue ;; esac
        case "${minb:-}" in ''|*[!0-9]*) continue ;; esac   # 表头 / 空行 / 写坏的行
        if [ ! -f "$p" ]; then
            if [ "$kind" = "manifest" ]; then
                echo "WARN  缺席（本轮还没跑过 build_deliverables.py）：$p"
                b_warn=$((b_warn + 1))
            else
                echo "[FAIL] 缺席：$p"
                fail=1
            fi
            continue
        fi
        sz=$(wc -c < "$p" | tr -d ' ')
        if [ "$sz" -lt "$minb" ]; then
            echo "[FAIL] 太小：$p（$sz B < $minb B）—— 生成被截断了？"
            fail=1
        else
            b_ok=$((b_ok + 1))
        fi
    done < "$TSV"
    echo "OK: $b_ok 个交付物在场且体积达标（告警 $b_warn 个）"
fi

echo ""
echo "########## C. 文档 / PPT 质量核对"
if [ "$PY_OK" -eq 0 ]; then
    echo "SKIP: 没有可用的 python —— 文档 QA 在本机跳过（agent 沙箱每次 push 前会跑）"
    exit "$fail"
fi
if ! $PY -c 'import docx, pptx' >/dev/null 2>&1; then
    echo "SKIP: 缺 python-docx / python-pptx —— 文档 QA 跳过"
    echo "      装上就有：pip install python-docx python-pptx pillow lxml"
    # .ps1 引号/括号平衡只需要标准库，照跑
    if [ -f code/check_ps1.py ]; then
        echo "=== PowerShell 脚本 ASCII / 引号 / 括号检查"
        $PY code/check_ps1.py | tail -2 || fail=1
    fi
    exit "$fail"
fi

CELLS="22:0:3 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0"
BLANK=""; for r in 11 12 13 14 15 16; do BLANK="$BLANK 22:$r:2 22:$r:4 22:$r:5 22:$r:6"; done
INS="22:8:0@22:7:0:1:0"
TCSKIP="22:0:1 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0 22:8:0"
TCCELLS=""; for r in 11 12 13 14 15 16; do
  TCSKIP="$TCSKIP 22:$r:2 22:$r:3 22:$r:4 22:$r:5"; TCCELLS="$TCCELLS 22:$r:1"
done
SDT="13:0:0 13:1:0 13:2:0 13:3:0 13:4:0 13:5:0 13:6:0"

for f in "deliverable/中期.docx" "deliverable/中期新.docx" "中间版/中期.docx" "中间版2/中期.docx"; do
  echo "=== $f"
  $PY code/verify_docx.py --base sources/中期.docx --filled "$f" \
    --cells $CELLS --blank-cells $BLANK --insert-cells $INS \
    --tc-skip $TCSKIP --tc-cells $TCCELLS --sdt-cells $SDT \
    --row-insert 22:15:1 | tail -1 || fail=1
done

echo "=== 口径核对（docx 为准，核对全部 PPT）"
$PY code/check_consistency.py | tail -1 || fail=1

echo "=== PPT 版式（真实 CJK 字体估算换行高度）"
if $PY -c 'import PIL' >/dev/null 2>&1; then
  for f in deliverable/中期答辩_*.pptx 中间版/*.pptx 中间版2/*.pptx; do
    printf "%-46s " "$f"; $PY code/check_ppt.py "$f" | tail -1 || fail=1
  done
else
  echo "SKIP: 缺 pillow —— PPT 版式复核跳过（pip install pillow）"
fi

echo "=== PowerPoint 脚本 ASCII / 引号 / 括号检查"
$PY code/check_ps1.py | tail -2 || fail=1

echo ""
echo "(rc=$fail)"
exit "$fail"
