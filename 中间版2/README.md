# 中间版 2（提交给老师：内容减半 + 进度减半）

> 与 `中间版/` 平行的一版：**篇幅砍一半，进度口径也砍一半**。
> 完整版（`deliverable/`）与中间版 1（`中间版/`）都不动。

## 里面有什么

| 文件 | 页数 / 段落 | 与完整版的关系 |
|---|---|---|
| `中期.docx` | 正文 31 段 / 完整版 60 段（**52%**），字数 51% | 同一份学校模板、同样就地填写；含 Ⅱ.导师指导情况（按半程进度写的短版）与检查小组成员 6 人；格式校验 `RESULT: template format fully preserved` |
| `中期答辩_H_nature风.pptx` | **8 页** / 完整版 16 页 | 与 H 版同一套版式、配色、参考线、最小 15 pt，含 8 页演讲备注 |

## 进度口径（与完整版、中间版 1 的区别）

| 环节 | 完整版 / 中间版 1 | **中间版 2** |
|---|---|---|
| 宏基因组数据处理与参考集 | 已完成 | **已完成** |
| 短肽库（sORF 预测与去冗余） | 已完成 | **已完成** |
| 三模型共识预测 | 已完成 | **已完成**（候选名单已产出） |
| 分阶段差异分析 | 已完成 | **下一阶段**（已进入实施） |
| 宏蛋白组二次去重与特有抗菌肽筛选 | 已完成 | **下一阶段**（已进入实施） |
| 机制关联分析 | 进行中 | **下一阶段**（方案已确定） |
| 抑菌实验验证 | 进行中 | **下一阶段**（方案与材料已确定） |
| 结果整理与论文撰写 | 进行中 | **随分析进度同步推进** |

PPT 第 3 页用的是专用图 `results/figures/figA_研究思路总览_半程.png`（4/8 已完成、4/8 下一阶段），
第 5、6 页标题以"下一阶段："开头，第 7 页对照表把差异分析、机制与验证两行写为"下一阶段开展"。
docx 的"工作进度与完成情况"只列 1—3 项为已完成，第 4 项写明其余各项为下一阶段工作。

## 怎么重新生成

```bash
python code/make_mid2_content.py                                    # -> docs/中间版2_填写内容.md
python code/build_ops.py --in docs/中间版2_填写内容.md --out build/ops_中期_中间版2.json
python code/fill_docx.py --ops build/ops_中期_中间版2.json --out 中间版2/中期.docx

python code/make_mid2_figures.py      # 半程进度图 figA_研究思路总览_半程.png
python code/make_ppt_mid.py --half    # 8 页 PPT（进度减半）

bash code/check_all.sh                # 四份 docx 格式 + 十份 PPT 版式 + 口径核对
```

## 自检结果

- `code/verify_docx.py`：`RESULT: template format fully preserved`
- `code/check_ppt.py`：`RESULT: OK (0 soft warning(s))`
- nature-skills `audit_pptx_quality.py`：`high=0, medium=0, low=0`（`results/qa/中期版2_audit.{md,json}`）
- `code/check_consistency.py`：三份 docx 与十份 PPT 口径一致
- 预览图：`results/ppt_preview/中间版2_第1页起.png`、`中间版2_第5页起.png`
