#!/usr/bin/env bash
# check_all.sh - 一次跑完全部自检（文档格式 / 口径 / PPT 版式）
set -u
cd "$(dirname "$0")/.."
rc=0

CELLS="22:0:3 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0"
# 中期检查表主体内容单元格
BLANK=""; for r in 11 12 13 14 15 16; do BLANK="$BLANK 22:$r:1 22:$r:2 22:$r:4 22:$r:5 22:$r:6"; done
INS="22:8:0@22:7:0:1:0"
# 封面及正文重建单元格：跳过 raw 检查，段落格式由 --cells 校验
TCSKIP="22:0:1 22:2:0 22:3:0 22:4:0 22:5:0 22:7:0 22:8:0"
# 检查小组成员行：若已删除旧名单（小组更换），则整行留空，raw 结构跳过检查
# 旧名单存在时，这些行会通过 clone_row 扩展，row-insert 需声明
# 现在成员已清空，成员行作为 blank-cells 处理，raw 层全部跳过
TCCELLS=""
for r in 11 12 13 14 15 16; do
  TCSKIP="$TCSKIP 22:$r:1 22:$r:2 22:$r:3 22:$r:4 22:$r:5 22:$r:6"
done
SDT="13:0:0 13:1:0 13:2:0 13:3:0 13:4:0 13:5:0 13:6:0"

for f in "deliverable/中期.docx" "deliverable/中期新.docx" "中间版/中期.docx" "中间版2/中期.docx"; do
  [ -f "$f" ] || continue   # 旧版可能已被有意删除
  echo "=== $f"
  # 成员已清空，不再需要 row-insert 与 tc-cells，全部跳过
  python code/verify_docx.py --base sources/中期.docx --filled "$f" \
    --cells $CELLS --blank-cells $BLANK --insert-cells $INS \
    --tc-skip $TCSKIP --sdt-cells $SDT | tail -1 || rc=1
done

echo "=== 口径核对"
python code/check_consistency.py | tail -1 || rc=1

echo "=== PPT 版式"
for f in deliverable/中期答辩_*.pptx 中间版/*.pptx 中间版2/*.pptx; do
  # 旧版本可能已被有意删除（用户要求只保留最新版），未匹配到的 glob 直接跳过
  [ -f "$f" ] || continue
  printf "%-46s " "$f"; python code/check_ppt.py "$f" | tail -1
done
# 三问·计算版是密集型技术手册式幻灯（表格多），最小字号放宽到 9 pt，仍检查越界与文本溢出
for f in deliverable/三问计算版_*/*.pptx deliverable/候选抗菌肽_AD病理关联解释版_*/*.pptx; do
  [ -f "$f" ] || continue
  printf "%-46s " "$f"; python code/check_ppt.py "$f" --min-pt 9 | tail -1
done

echo "=== PowerPoint 脚本 ASCII 检查"
python code/check_ps1.py | tail -2

echo "(rc=$rc)"
exit $rc
