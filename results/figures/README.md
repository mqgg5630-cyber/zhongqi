# figures 说明

本目录有两套图，用途不同：

| 文件 | 用途 | 是否用于本次中期材料 |
|---|---|---|
| `figA_研究思路总览.png`、`figB_三模型预测.png`、`figC_分阶段差异分析.png`、`figD_宏蛋白组去重.png`、`figE_机制关联.png`、`figF_抑菌实验方案.png`、`figG_进度甘特.png` | **当前中期答辩 PPT 用图**：只表达研究思路与完成状态，不含技术细节与数值 | ✅ 用于 `deliverable/中期答辩_A—G_*.pptx`（七版共用同一套图） |
| `fig1_技术路线.png` … `fig8_下一步计划.png` | 早期"细节版"图：包含具体样本量、软件参数、P 值等，**留给学位论文与投稿论文使用** | ❌ 中期材料不使用（导师要求不展开细节） |

生成脚本：

```bash
python code/make_figures.py     # fig1—fig8（细节版，供论文用）
python code/make_figures2.py    # figA—figG（思路版，中期用）
```

两套脚本共用 `code/make_figures.py` 里的绘图工具函数（`box` / `arrow` / `save`），
并自带两项自检：**文字是否超出方框**（按坐标轴实际宽度自动折行），
以及**图片缩放到幻灯片后的最小有效字号是否 ≥15 pt**。
