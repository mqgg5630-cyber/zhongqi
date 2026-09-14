# 中间版（提交给老师）

> 完整版在 `deliverable/`，**一个字节都没动**。本文件夹放的是同一套内容的压缩稿，
> 供中期材料提交给老师用；文件名与完整版一致，方便替换。

## 里面有什么

| 文件 | 页数 / 段落 | 与完整版的关系 |
|---|---|---|
| `中期.docx` | 正文 29 段 / 完整版 60 段（**48%**），字数 51% | 同一份学校模板、同样就地填写，Ⅱ.导师指导情况与检查小组成员都在，格式校验 `RESULT: template format fully preserved` |
| `中期答辩_H_nature风.pptx` | **8 页** / 完整版 16 页 | 与 H 版同一套版式、配色、参考线、最小 15 pt，含 8 页演讲备注 |

## 砍掉的是什么

- **docx**：按"主线"保留 —— 抗菌肽作为切入点、研究现状与本研究的切入点、研究目标、
  研究内容 1/3/4/5/7、技术路线、进度 1/3/5/6/7 与完成结构；阶段性成果里的数据流程、预测结果、
  差异与去重、机制关联方案、阶段性结论；投稿计划；机制关联内容与方案、抑菌实验内容与方案、
  结果整理与投稿、问题 1/3 及对策、后续安排。
  去掉的是对同一件事的重复展开（现状的三条不足、研究内容的第 2/6/8 条、实时进度的第 2/4/8 条、
  技术路线的实施要点细节等）。
- **PPT**：16 页 → 8 页，每张"图 + 图注"合并为一页：

  | 中间版 | 完整版对应页 |
  |---|---|
  | 1 封面 | 1 封面 |
  | 2 背景与切入点 | 2 背景 + 3 思路总览（旁栏） |
  | 3 研究思路与完成进度 | 3 思路总览 + 5 思路总览图 |
  | 4 队列分阶段 + 三模型共识预测 | 4 阶段队列 + 6 三模型 |
  | 5 分阶段差异 + 宏蛋白组二次去重 | 7 分阶段差异 + 8 二次去重 |
  | 6 机制关联与抑菌实验验证 | 9 机制关联 + 10 抑菌实验 |
  | 7 进度与开题计划对照（原生表格 4 行） | 12 对照表 5 行（合并"模型方案"，4 行） |
  | 8 后续安排与总结 | 14 后续安排 + 16 总结 |

## 怎么重新生成

```bash
python code/make_mid_content.py        # 完整版草稿 -> docs/中间版_填写内容.md（保留清单在脚本里）
python code/build_ops.py --in docs/中间版_填写内容.md --out build/ops_中期_中间版.json
python code/fill_docx.py --ops build/ops_中期_中间版.json --out 中间版/中期.docx

python code/make_ppt_mid.py            # 出 8 页 PPT
python code/make_ppt_mid.py --audit    # 顺带跑 nature-skills 的审计脚本

bash code/check_all.sh                 # 三份 docx 格式 + 九份 PPT 版式 + 口径核对，一次跑完
```

## 自检结果

- `code/verify_docx.py`：`RESULT: template format fully preserved`
- `code/check_ppt.py`：`RESULT: OK (0 soft warning(s))`（8 页，最小字号 15 pt）
- nature-skills `audit_pptx_quality.py`：`high=0, medium=0, low=0`（`results/qa/中期版_audit.{md,json}`）
- `code/check_consistency.py`：完整版与中间版 docx、九份 PPT 口径一致（含禁用表述：按导师意见 / 极简 等）
- 预览图：`results/ppt_preview/中间版_第1页起.png`、`中间版_第5页起.png`
