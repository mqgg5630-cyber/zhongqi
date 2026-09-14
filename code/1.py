#!/bin/bash
set -euo pipefail

# ==========================================
# 0. 基础路径配置
# ==========================================
# 脚本运行的主目录 (包含 samples.tsv)
WORKDIR="/mnt/hpc/home/25menglei/25wenshaohua/wsh/ad"
# 所有 476 个样本真正存放的目录 (包含刚修复好的那几个)
MAIN_PROJECT_DIR="/mnt/hpc/home/25menglei/25wenshaohua/wsh/stage/code"

cd "$WORKDIR"

SAMPLES_TSV="temp/qc/samples.tsv"
REPORT_FILE="codenew/Final_Master_Pipeline_Report.md"
FAILED_LOG="codenew/final_failed_samples.list"

echo "---------------------------------------------------"
echo "[INFO] 开始对全队列 476 个样本进行最终成果校验与统计..."
echo "---------------------------------------------------"

TOTAL=0
SUCCESS=0
FAILED=0
TOTAL_MAGS=0
HQ_MAGS=0

> "$FAILED_LOG"

while IFS=$'\t' read -r sample r1 r2 group || [ -n "$sample" ]; do
    [[ -z "$sample" ]] && continue
    TOTAL=$((TOTAL+1))
    
    # 统一从主工程路径检查
    WD="${MAIN_PROJECT_DIR}/work/${sample}"
    
    # 检查 1: Megahit 组装
    if [[ ! -s "${WD}/assembly/${sample}.contigs.fa" ]]; then
        echo -e "${sample}\tAssembly_Failed" >> "$FAILED_LOG"
        FAILED=$((FAILED+1))
        continue
    fi
    
    # 检查 2: Bin_refinement
    if [[ ! -f "${WD}/temp_v2/refine/metawrap_50_10_bins.stats" ]]; then
        echo -e "${sample}\tBin_Refinement_Failed" >> "$FAILED_LOG"
        FAILED=$((FAILED+1))
        continue
    fi
    
    # 检查 3: CheckM 质量评估表
    SUMMARY_FILE="${WD}/result/tables/mag_quality_summary.tsv"
    if [[ ! -f "$SUMMARY_FILE" ]]; then
        echo -e "${sample}\tClassify_Evaluation_Failed" >> "$FAILED_LOG"
        FAILED=$((FAILED+1))
        continue
    fi
    
    # 统计数据
    if [[ -s "$SUMMARY_FILE" ]]; then
        # 提取当前样本的总 MAG 数和高质量数
        mags=$(awk 'END {print NR-1}' "$SUMMARY_FILE")
        [[ "$mags" -gt 0 ]] && TOTAL_MAGS=$((TOTAL_MAGS + mags))
        
        hq=$(awk -F'\t' '$14 == "MIMAG_HQ" {count++} END {print count+0}' "$SUMMARY_FILE")
        HQ_MAGS=$((HQ_MAGS + hq))
    fi

    SUCCESS=$((SUCCESS+1))
done < "$SAMPLES_TSV"

echo "---------------------------------------------------"
echo "检查完毕！总样本数: ${TOTAL} | 成功: ${SUCCESS} | 失败/未完成: ${FAILED}"
echo "全队列共计挖掘出 MAGs: ${TOTAL_MAGS} 个 (包含高质量 MIMAG_HQ: ${HQ_MAGS} 个)"
echo "---------------------------------------------------"

# ==========================================
# 3. 生成最终学术级 Master 报告
# ==========================================
if [ "$FAILED" -eq 0 ] && [ "$TOTAL" -eq 476 ]; then
    echo "[OK] 完美！全队列 476 个样本已全部补齐并通过校验！"
    echo "正在生成最终 Methods 实验记录报告: ${REPORT_FILE}"

    cat <<EOF > "$REPORT_FILE"
# 宏基因组高质量草图基因组 (MAGs) 挖掘标准分析流程报告 (最终版)

**分析完成日期**: $(date +"%Y-%m-%d %H:%M:%S")
**处理规模**: 全队列 476 对双端测序样本 (已处理所有前期异常样本)
**集群配置**: SLURM 高性能计算集群 (48 Threads, 150GB Mem 增强型配置处理复杂样本)

## 1. 核心流程摘要
本研究采用一套高度自动化的流水线，实现了从原始测序数据到高质量基因组 (MAGs) 的深度挖掘。
1. **质控去污染**: fastp + Kneaddata (Bowtie2 vs hg39) 严格剔除人类宿主干扰。
2. **从头组装**: MEGAHIT (de Bruijn graph 算法) 处理复杂微生物群落汇编。
3. **联合分箱与精炼**: 整合 MetaBAT2、MaxBin2 与 CONCOCT 三大主流算法，并通过 metaWRAP bin_refinement 模块进行交叉验证与提纯 (阈值: Completeness ≥ 50%, Contamination ≤ 10%)。
4. **质量评估**: 基于 CheckM 谱系标记基因评估，并辅以 barrnap 与 tRNAscan-SE 进行 MIMAG 标准界定。

## 2. 统计结果 (Result Summary)
- **样本总量**: 476 Samples
- **成功率**: 100%
- **重构 MAGs 总数**: ${TOTAL_MAGS} 个
- **高质量 MAGs (MIMAG_HQ)**: ${HQ_MAGS} 个
  - *注：MIMAG_HQ 定义为完整度 ≥ 90%，污染度 ≤ 5%，且含有完整 5S/16S/23S rRNA 及 18 种以上氨基酸的 tRNA。*

## 3. 下游应用
该非冗余基因组集已完成标准化分类与质量分级，为后续针对 Alzheimer's Disease 患者肠道微生物组的**抗菌肽 (AMPs) 深度学习预测**及功能差异性分析提供了高质量的底层数据库支持。
EOF

    echo "[INFO] 最终报告生成完毕！你可以使用 cat ${REPORT_FILE} 查看。"
else
    echo "[WARNING] 仍有 ${FAILED} 个样本未通过最终校验，请查看 ${FAILED_LOG}。"
fi