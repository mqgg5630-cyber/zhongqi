# 研究方案：{{项目/课题名称}}

> 本文件 = **上游研究设计文档**，描述"要做什么、为什么、如何验证"。
> 落地任务级清单（建目录、写脚本、跑实验的 to-do）走 **project-structure** 的脚手架生成，**勿在此重复**。
> 本文件只承载研究设计与判定标准；实验明细见同目录 `experiment_matrix.md`。

- 关联 idea / idea-critique 放行记录：{{链接或编号}}
- 负责人：{{姓名}}　起止：{{开始}} → {{deadline}}
- 数据就绪(data-engineering)：{{是/否}}　方法就绪：{{是/否}}

---

## 0. idea-critique must-fix 承接
> 若 idea-critique 给出「有条件通过」，其 Revision Roadmap 的每条 must-fix 必须在此逐条落到本方案的假设/实验/成功标准，
> 避免整改项悬空。无条件通过则注明「无 must-fix」。

| must-fix 条目（来自 idea-critique） | 落到方案哪一处（假设 H? / 实验 EXP·ABL·ROB·GEN·SEN-? / 成功标准） | 如何验证整改到位 |
|---|---|---|
| {{条目1}} | {{对应位置}} | {{验证方式}} |

---

## 1. 研究问题、estimand 与核心假设（★ 可证伪是 critical）
- 总目标：{{一句话}}
- **目标人群/对象与外推边界**：{{population}}
- **统计单位 / 随机化单位 / 分析单位**：{{分别写；不同则解释}}
- **Comparison**：{{A vs B，在何条件}}
- **Outcome**：{{variable + computation + aggregation + timepoint}}
- **Estimand**：{{要估计的 contrast/effect + summary measure}}
- **可证伪假设 + 反证条件**（每条假设必须能被推翻——`plan_gate` falsifiable 门：缺反证条件=critical）：

| 假设 | 陈述 | 主指标 | 反证条件（什么结果能推翻 H，可量化） |
|---|---|---|---|
| H1 | {{假设陈述}} | {{主指标}} | {{如 top-1 提升<2% 或 p≥0.05 则 H1 被推翻}} |
| H2 | {{假设陈述}} | {{主指标}} | {{如 消融掉点<1% 则"组件Y有贡献"被推翻}} |

- **成功 / 失败 / 无结论**：{{H1/H2… 的支持门槛 / 反证门槛 / precision 不足或 CI 跨界时的 inconclusive}}
- **验证方式**：{{用哪个实验/指标回答每条假设}}
- **失败树/claim 动作**（同步 `failure-tree.json`，最终跑 `failure_tree_gate.py`）：

| 假设 | success 条件与动作 | failure 条件与动作 | inconclusive 条件与动作 | claim impact |
|---|---|---|---|---|
| H1 | {{F1 提升≥3pp 且 q<0.05 → PROCEED_CONFIRMATORY}} | {{提升<1pp 或 q≥0.05 → REPLAN/STOP_NO_GO}} | {{CI 跨 SESOI → REPORT_INCONCLUSIVE/COLLECT_MORE_DATA}} | {{允许/禁止/降级哪些宣称}} |

## 2. 技术路线
- 整体框架图（交 figure）：{{图链接或占位}}
- 关键模块：{{模块A / 模块B …，各自职责}}
- 数据流：{{输入 → 处理 → 模型 → 输出}}
- **成功标准**：{{端到端 smoke test 通过}}　**验证方式**：{{各模块接口对齐确认}}

## 3. 数据
- 来源：{{数据集名 / data-engineering 数据卡条目}}
- 处理流程（引 data-engineering 流水线）：{{步骤}}　划分方式：{{train/val/test 比例与策略}}
- 统计：{{规模 / 类别分布 / 缺失}}；lineage：{{source URL + revision + raw/clean hash + cleaning commit}}
- **派生评测集清单**（主流水线之外、需回 data-engineering 构建的加噪/缺失/跨域/扫参集；明细规格见 `experiment_matrix.md` §5）：
  - 加噪/缺失集：{{基础集 → 噪声σ / 缺失率%+机制 → 服务 ROB-xx}}
  - 跨域/跨数据集：{{源域 → 目标域 → 服务 GEN-xx}}　扫参集：{{超参网格 → 服务 SEN-xx}}
- **成功标准**：{{划分无泄漏（data-engineering split_leakage 过）、分布达标；派生集按规格构建 + 数据卡齐}}
- **验证方式**：{{校验脚本；派生需求回 data-engineering 构建并登记数据卡}}

## 4. 模型 / 方法
- 算法流程 / 关键公式 / 复杂度：{{步骤或伪代码}}
- **成功标准**：{{方法实现正确性判据}}　**验证方式**：{{单元测试 / 金标准用例（关键函数用 Hypothesis property-based 测）}}

## 5. 实验设计（★ 对照公平是 critical；明细见 `experiment_matrix.md`）
- 主实验：{{任务 / 数据集 / 指标}}
- design：{{randomized / observational / repeated / cluster / offline benchmark}}；
  blocking/stratification：{{}}；negative control：{{}}
- **对照公平性声明**（`plan_gate` fair_baseline 门：放水=critical）：

| baseline | 公平性档（ok/warn/unfair:说明） |
|---|---|
| {{最强可得 baseline}} | {{ok: 同数据同划分 + 等量调参预算 + 取当前 SOTA 实现}} |

- 消融实验：{{逐个移除的创新组件 + 固定项 + 负对照；联合移除不归因单组件}}
- 对比实验：{{对比 SOTA + 公平设置}}
- 参数敏感性：{{超参网格，Hydra multirun / W&B Sweeps}}
- 泛化测试：{{跨数据集 / 跨域 / 跨规模}}　鲁棒性：{{噪声 / 对抗 / 缺失 / 漂移}}
- outcome registry：{{primary / secondary / exploratory + variable/metric/aggregation/timepoint}}
- comparison family：{{成员 K + 校正法}}；排除/缺失/outlier/transform/covariates：{{预先锁定 + if-then fallback}}
- 功效/敏感性：{{独立单位 + SESOI/效应范围 + 来源/收缩 + 匹配 design 的方法 + N 或固定N下MDE}}
- 重复/种子：{{用于估计算法随机性；与独立样本 n 分开报告}}
- stopping / guardrail / kill（同步 `failure-tree.json`）：{{fixed N 或合法 sequential；counter-metric 阈值；kill action；资源耗尽与 inconclusive 默认动作}}
- 防泄漏：{{预处理封入 Pipeline（data-engineering safe_split）}}
- **成功标准**：{{每类实验判定假设成立的结果门槛}}　**验证方式**：{{结果如何回答对应假设}}

## 6. 可视化方案
- 要出的图表（交 figure）：{{图1 / 图2 …}}　**成功标准**：{{图支撑哪条结论}}　**验证方式**：{{数据到图的核对}}

## 7. 时间安排
- 里程碑 + 甘特（对齐 deadline）：{{M1:日期 / M2:日期 …}}　**成功标准**：{{各里程碑交付物}}　**验证方式**：{{进度核对（登记 memory-pm）}}

## 8. 风险点 & 备选方案
- 风险1：{{描述}} → plan B：{{备选}}　**成功标准**：{{风险触发时的可接受退路}}　**验证方式**：{{触发条件监测}}

## 9. 预注册与 provenance
- 模板：{{`templates/preregistration.md` 完成路径}}
- confirmatory / exploratory 分轨：{{}}
- frozen at（含时区）/ plan version / git commit / SHA256：{{}}
- registry / status / ID / URL / PDF hash：{{OSF / AsPredicted / 适用 registry；未提交写 DRAFT/UNAVAILABLE}}
- amendments/deviations：{{只追加不覆盖；看过 outcome 的受影响项转 exploratory}}

## 10. 算力 / 成本预算（方案定型前算账）
- 逐实验估 GPU 时数 × 卡数 × 单价（现查 + 记日期），汇总对照预算上限；扫参×多种子是放大器，超支砍范围（记功效损失）。明细表见 `experiment_matrix.md` §7。

## 11. 预期成果
- 层次：{{论文 / 竞赛 / 专利 / 软著}}　**成功标准**：{{成果达成判据}}　**验证方式**：{{投稿 / 提交 / 评审记录}}

---
## 衔接
方案 + 预注册冻结包交 experiment-coding 实现 → project-structure 建目录 → memory-pm 登记里程碑 → 实验跑完交 result-analysis。
**派生/评测数据需求回 data-engineering 构建**（`experiment_matrix.md` §5 → `derive_eval_set.py`）。方案变更回写 `.light/decision_log`。
**回炉**：result-analysis 判结果不支撑假设 → 回边 **7→5** 重规划；拒稿·实验质疑 → **13→5**。
