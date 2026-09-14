#!/usr/bin/env bash
# check_all.sh - 一次跑完全部自检（文档格式 / 口径 / PPT 版式）
set -u
cd "$(dirname "$0")/.."
rc=0

CELLS="22:0:3 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0"
BLANK=""; for r in 11 12 13 14 15 16; do BLANK="$BLANK 22:$r:2 22:$r:4 22:$r:5 22:$r:6"; done
INS="22:8:0@22:7:0:1:0"
TCSKIP="22:0:1 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0 22:8:0"
TCCELLS=""; for r in 11 12 13 14 15 16; do
  TCSKIP="$TCSKIP 22:$r:2 22:$r:3 22:$r:4 22:$r:5"; TCCELLS="$TCCELLS 22:$r:1"
done
SDT="13:0:0 13:1:0 13:2:0 13:3:0 13:4:0 13:5:0 13:6:0"

for f in "deliverable/中期.docx" "deliverable/中期新.docx" "中间版/中期.docx"; do
  echo "=== $f"
  python code/verify_docx.py --base sources/中期.docx --filled "$f" \
    --cells $CELLS --blank-cells $BLANK --insert-cells $INS \
    --tc-skip $TCSKIP --tc-cells $TCCELLS --sdt-cells $SDT \
    --row-insert 22:15:1 | tail -1 || rc=1
done

echo "=== 口径核对"
python code/check_consistency.py | tail -1 || rc=1

echo "=== PPT 版式"
for f in deliverable/中期答辩_*.pptx 中间版/*.pptx; do
  printf "%-46s " "$f"; python code/check_ppt.py "$f" | tail -1
done

echo "=== PowerPoint 脚本 ASCII 检查"
python code/check_ps1.py | tail -2

echo "(rc=$rc)"
exit $rc
