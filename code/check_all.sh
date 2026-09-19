#!/usr/bin/env bash
# check_all.sh - 一次跑完全部自检（文档格式 / 口径 / PPT 版式）
set -u
set -o pipefail   # 前面的 python 一失败就让它冒出来（否则 | tail 会把失败吞掉）
cd "$(dirname "$0")/.."
rc=0

# 22:17:0 = “是否同意参加预答辩 / 检查组长签字 / 培养单位盖章”那一格，只往里填了日期
CELLS="22:0:3 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0 22:17:0"
BLANK=""; for r in 11 12 13 14 15 16; do BLANK="$BLANK 22:$r:2 22:$r:4 22:$r:5 22:$r:6"; done
INS="22:8:0@22:7:0:1:0"
TCSKIP="22:0:1 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0 22:8:0"
# r17（是否同意参加预答辩 / 检查组长签字 / 培养单位盖章）只填了日期，属“只改文字”的目标格
TCCELLS_EXTRA="22:17:0"
TCCELLS="$TCCELLS_EXTRA"; for r in 11 12 13 14 15 16; do
  TCSKIP="$TCSKIP 22:$r:2 22:$r:3 22:$r:4 22:$r:5"; TCCELLS="$TCCELLS 22:$r:1"
done
SDT="13:0:0 13:1:0 13:2:0 13:3:0 13:4:0 13:5:0 13:6:0"

for f in "deliverable/中期.docx" "deliverable/中期新.docx" "中间版/中期.docx" "中间版2/中期.docx"; do
  echo "=== $f"
  python code/verify_docx.py --base sources/中期.docx --filled "$f" \
    --cells $CELLS --blank-cells $BLANK --insert-cells $INS \
    --tc-skip $TCSKIP --tc-cells $TCCELLS --sdt-cells $SDT \
    --pbb-rows 22:9 | tail -1 || rc=1
done

echo "=== docx 排版（签字页单独成完整一页）"
for f in "deliverable/中期.docx" "deliverable/中期新.docx" "中间版/中期.docx" "中间版2/中期.docx"; do
  printf "%-32s " "$f"; python code/check_docx_layout.py "$f" --quiet | tail -1 || rc=1
done
printf "%-32s " "deliverable/中期检查表_签字页.docx"
python code/check_docx_layout.py "deliverable/中期检查表_签字页.docx" --sign-page --quiet | tail -1 || rc=1

echo "=== 口径核对"
python code/check_consistency.py | tail -1 || rc=1

echo "=== PPT 版式"
for f in deliverable/中期答辩_*.pptx 中间版/*.pptx 中间版2/*.pptx; do
  printf "%-46s " "$f"; python code/check_ppt.py "$f" | tail -1 || rc=1
done

echo "=== PPT 版面体检（重叠 / 溢出 / 压页脚）"
for f in deliverable/中期答辩_H_nature风.pptx deliverable/中期答辩_最终版.pptx \
         中间版/中期答辩_H_nature风.pptx 中间版2/中期答辩_H_nature风.pptx; do
  printf "%-46s " "$f"; python code/check_layout.py "$f" | tail -1 || rc=1
done

echo "=== 机制图（框内溢出 + 投影字号）"
python code/make_mech_figures.py | tail -1 || rc=1

echo "=== PowerPoint 脚本 ASCII 检查"
python code/check_ps1.py | tail -2 || rc=1

echo "(rc=$rc)"
exit $rc
