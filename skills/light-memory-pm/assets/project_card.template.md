---
project_name: <PROJECT_NAME>
created: <CREATED_DATE>
---
# 项目卡：<PROJECT_NAME>

> 项目记忆总览。每次重要进展**立即更新**对应字段（联动 memory-pm 更新纪律）。
> 相对日期一律转绝对日期。`current_stage` 取下列 11 阶段枚举之一。
> 会话开头先读 `next_actions`（“上次做到哪、下一步是什么”）。

```yaml
project_name: <PROJECT_NAME>
goal:                  # 一句话目标 + 成果形态(论文/竞赛/系统)
current_stage: 资料调研  # 资料调研|idea 构思|方案确认|数据准备|实验实现|结果分析|论文写作|图表制作|投稿准备|答辩展示|成果转化
confirmed_idea:        # idea-critique 通过的 idea(一句话) + 创新点
data_status:           # 数据来源/规模/质量结论(链 data-engineering)
method_status:         # 选定方法/baseline
experiment_status:     # 已跑/待跑实验(链实验矩阵)
paper_status:          # 各章节进度 + 当前版本
ppt_status:            # PPT 版本与场景
code_status:           # 代码进度 + 仓库/分支
risk_list:             # 风险点 + 应对
next_actions:          # 下一步(会话开始先读这里)
decision_log: 见 decision_log.md
version_history: 见 version_history.md
# archived: YYYY-MM-DD # 可选,仅项目完结(录用/结题/用户声明)后加;会话开头扫描跳过已归档项目
```

## 配套文件（同在 `.light/`）
- `passport.yaml` — DAG 科研台账(passport.py 引擎管:阶段/状态/回边/门)。
- `terminology.md` — 术语/指标/创新点标准措辞(受控事实源,供 consistency 跨材料统一)。
- `decision_log.md` — 决策时间线(ADR 式,只追加)。
- `version_history.md` — 论文/PPT/图/代码各版本记录(与 git tag 对齐)。
- `memory_items.json` — 可选的结构化项目记忆条目(scope/敏感级别/保留期/来源/替代链/删除)，不是数据库。
- `consistency/*.yaml` — 机读受控 schema(严格校验时用;空模板见 light-consistency/assets/)。
- `handoff/S<NN>-*.md` — 跨会话交接卡(链式,可追到任意上级会话)。
