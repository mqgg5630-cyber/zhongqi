# QA 报告 —— H 版（nature 风 / 论文汇报风）PPT

> 生成脚本：`code/make_ppt_nature.py`　交付文件：`deliverable/中期答辩_H_nature风.pptx`
> 方法来源：[mqgg5630-cyber/nature-skills](https://github.com/mqgg5630-cyber/nature-skills) → `skills/nature-paper2ppt`（Apache-2.0）
> 报告按该 skill 的 `static/core/output-and-quality.md` 要求填写。

## 1. 生成状态

| 项目 | 结果 |
|---|---|
| PPTX 是否生成 | ✅ 已生成（16:9，16 页） |
| 幻灯片页数 | 16 |
| 插入图 | 7 张（figA—figG，全部来自 `results/figures/`，未做裁切，原图标注完整） |
| 原生可编辑对象 | ✅ 全部为文本框 / 形状 / 原生表格（第 12 页为 6 行 × 3 列原生表格，可直接改数） |
| 演讲备注 | ✅ 16/16 页 |
| 缺图或占位图 | 无 |

## 2. 路由与叙事（skill Step 1—3）

- `paper_type` 判定：**resource**（数据 / 组学 / 流程类成果）→ 采用 **workflow-to-validation** 叙事弧：
  为什么需要 → 队列与数据设计 → 生成与质量控制 → 主结果 → 验证与可复现 → 复用与边界 → 总结。
  实现映射：第 2 页（背景与空白）→ 第 4 页（队列分阶段）→ 第 5 页（技术路线，full-width 流程）→
  第 6—8 页（三模型 / 差异 / 去重结果）→ 第 9—10 页（机制关联与抑菌验证）→ 第 14—15 页（安排与边界）→ 第 16 页（总结）。
- 术语账本：见 `docs/术语表.md`；同一概念全篇同一写法（三模型 = Attention / LSTM / BERT；特有抗菌肽 = 健康人群特有与各阶段特有）。
- 未使用禁用套话（`一句话总结` / `不是…而是…` / `具有重要意义` 等），由 skill 的审计脚本核对（0 命中）。

## 3. 自检与修正（skill Step 8）

| 严重度 | 缺陷 | 页 | 处理 |
|---|---|---|---|
| high | 无 | — | — |
| medium | 无 | — | — |
| low | 说明带文字与色块紧贴、上下边仅差 5.8 pt（近对齐） | 7、10 | 已修正：文字框改为与色块同顶、垂直居中，重出后审计 0 条 |

三重校验结果：

1. `code/check_ppt.py` → `RESULT: OK (0 soft warning(s))`（最小字号 15.0 pt、无越界、无文字压图）；
2. nature-paper2ppt 自带审计 `scripts/audit_pptx_quality.py` → **findings 0**（16 页，无 high/medium/low）；
   该脚本同时对 **八版** PPT 全部跑过一遍，结果见 `results/qa/中期答辩_*_audit.md`：A 0 条、B 5 条、
   C 4 条、D 19 条、E 17 条、F 35 条、G 50 条、**H 0 条**（其余均为 `alignment_near_miss` 的 low 级提示，
   属于装饰性色块/线条的 2—8 pt 近对齐，不影响阅读；H 版已逐条消除）；
3. 目视核对预览图 `results/ppt_preview/H版_第1页起.png` … `H版_第13页起.png`。

## 4. 与其它版本的口径一致性

`code/check_consistency.py`（本轮新增）以 **docx 中期检查表为准**，逐条核对 8 份 PPT：

```
OK 论文题目 / 封面·姓名 / 封面·学号 / 封面·培养单位 / 封面·指导教师
OK 阶段划分（NC / SCS / SCD / MCI / AD）
OK 机制·Aβ / 机制·AChE / 成果·投稿 / 完成度口径 / 后续环节
OK 禁用表述：极简、最小工作量、最小可行性、最小化验证
RESULT: docx 与全部 PPT 口径一致
```

本轮为保证一致，对 docx 正文做了 4 处措辞统一（格式未动，`verify_docx.py` 仍为 `RESULT: template format fully preserved`）：
AChE 首次出现补英文全称、后文统一用缩写；阶段划分首次写明 NC / SCS / SCD / MCI / AD 五阶段；Aβ 写法统一。

## 5. 边界与待确认

- 图内文字（figA—figG）是我方自制示意图，非实验原始数据图；若后续有真实结果图，直接替换 `results/figures/` 同名文件即可重出。
- 第 4 页的阶段定义为队列既有诊断标签（NC / SCS / SCD / MCI / AD）；若实际标签不同，改 `code/make_ppt_nature.py` 中 `metrics_slide(...)` 的 `stages` 列表。
- 第 12 页表格的"现阶段结果"来自 `docs/ppt_outline.json` / `deliverable/中期检查表_填写内容.md`，未引入新数字。
