# 结果分析报告 — {项目/实验名}

> 模板用法：每个发现严格按 **现象 → 原因 → 证据 → 对论文的意义** 四段写。
> 区分「已验证」与「推测」（诚实纪律）。所有 p 值配效应量 + CI + FDR 三件套；**显著性看 q 不看 p**。
> 配套脚本：`analyze_results.py`（统计汇总 + `--emit-claim-table` + `--emit-evidence`）、
> `stat_rigor_gate.py`（统计严谨/证据强度 critical 门 → `light.findings.v1`）、
> `significance_test.py`（p+d+CI+FDR+DeLong）、`make_figs.py`（出版图）、
> `leakage_overfit_check.py`（泄漏/过拟合体检）、`explain_shap.py`（SHAP，非因果）。
> **标准机读工件**：`claim_evidence_table.md`（claim↔证据）+ `evidence_strength.json`
> （证据档强/中/弱/无 → 措辞档，交 paper-writing/research-ethics 卡『措辞不强于证据』）。

## 0. 元信息
- 实验：{数据集 / 方法 / baseline 列表}
- 随机种子数：{≥5？}  | 算力/数据是否同设置：{是否公平比较}
- 结果表：`{results.csv}`  | 统计输出：`analysis_out/summary.json` + `summary.md`
- 体检：`leakage_report.json`（verdict: {CLEAN / FLAGS RAISED}）
- 分析计划：{frozen/exploratory/sensitivity；locked_at；results_available_at}
- 统计单位/设计：{unit_of_analysis；independent/paired/repeated/hierarchical/nested CV；paired_by}
- comparison family：{family_id；planned/reported；correction}
- provenance：{raw result SHA-256；run manifest；config/commit；owner；captured_at；coverage}
- R/Python：{R detection；实际走过的 R 路径；关键数值交叉核验或诚实降级}

## 1. 描述层（指标汇总）
| 方法 | 指标 | 均值±std | 95% CI | n(种子) |
|---|---|---|---|---|
| {ours} | {acc} | {0.86±0.02} | {[.., ..]} | {8} |
| {baseline} | {acc} | {0.80±0.03} | {[.., ..]} | {8} |

一句话结论：{ours 相对 baseline 的 gap 与方向}。

## 2. 关键发现（逐条，四段式）

### 发现 1：{标题，如"ours 在 acc 上显著优于 baseline"}
- **现象**：{观察到的数值差异，引用上表}。
- **原因**：{归因到方法的哪个组件；结合消融说明}。
- **证据**：{omnibus 检验=?, p=?, Cohen's d=?(effect), 95% CI=?, BH-FDR 后 q=? 是否仍显著；引用 summary.json 字段}。
- **对论文的意义**：{可写进 contribution / 支撑哪个 claim；不能过度声称之处}。

### 发现 2：{消融自洽性}
- **现象**：{移除组件 X 后性能下降 Y}。
- **原因**：{组件 X 的作用机制}。
- **证据**：{ablation 行的统计；方向是否符合预期；Tukey/pairwise 结果}。
- **对论文的意义**：{证明组件必要性}。

### 发现 3：{跨数据集/设置一致性 或 意外规律}
- **现象**：{}。**原因**：{}。**证据**：{}。**对论文的意义**：{}。

## 3. 亮点清单（可写进 contribution）
- [ ] {亮点 1：哪条规律稳健、效应量大、统计显著 → 主 claim}
- [ ] {亮点 2：意外发现 / 可解释性证据（SHAP/注意力）}
- [ ] {亮点 3：跨设置鲁棒性}

## 4. 问题 / 异常清单（含排查建议）
| # | 异常现象 | 可能原因 | 排查建议 | 严重度 |
|---|---|---|---|---|
| 1 | {train-val gap 过大} | {过拟合} | {正则/早停/增广；看 leakage_report} | 高 |
| 2 | {val-test 落差} | {分布漂移 or 验证集泄漏} | {重切分/检查时间穿越} | 高 |
| 3 | {某特征 |corr|→1} | {标签代理泄漏} | {移除该特征重训} | 高 |
| 4 | {某方法方差异常大} | {种子不稳/数据量小} | {增加种子数} | 中 |

## 5. 待补实验清单（回 research-plan stage 5 / experiment-coding stage 6 补）
- [ ] {补 X 数据集验证泛化}
- [ ] {补组件 Y 的独立消融}
- [ ] {增加种子数到 ≥10 以收紧 CI}
- [ ] {错例分析 / 公平性分组评估}

## 6. 推荐图表（交 figure stage 9 规划 + 绘制）
- {图 a：方法对比柱状图 + 95% CI 误差棒 → grouped_bar_ci}
- {图 b：各种子分布 box+strip → box_strip}
- {图 c：学习曲线 + CI 带 → line_with_band}
- {图 d：归一化混淆矩阵 viridis → heatmap}

## 7. 诚实标注
- 已验证：{列出有统计支撑/可复现的结论}。
- 推测/待验证：{列出尚无充分证据、不能写死的说法}。
- 不能过度声称：{样本量/单数据集/单设置带来的局限}。
- 结果后变更：{old→new / time / reason / exploratory-or-sensitivity；没有则写“无”}。
- 缺失/排除/失败运行：{expected vs observed units；排除理由；对结论的敏感性}。

## 8. 回炉判定（本技能是 7→5 / 7→6 回炉发起方）
- [ ] **结果不支撑假设**（grade=none：q≥.05 / CI 含 0 / 效应量过小）→ 建议回 **research-plan（7→5）**重审假设/设计。
- [ ] **结果不可复现**（多种子 sign-flip / CV 过大 / 复现失败）→ 建议回 **experiment-coding（7→6）**查种子/bug。
- [ ] **p-hacking**（多重比较未校正 / 选择性报告）→ **在 stage 7 内重做分析**（reroute 给 manual，非回上游）。
> 回炉是**决策点**：带证据停下问用户（回哪 / 带病推进并记录 / 转已知局限），绝不静默回。

---
_证据强度（`evidence_strength.json`）交 paper-writing（stage 8）校准措辞、research-ethics 复核夸大；
亮点 → paper-writing 写作支撑；异常/不足 → 回 research-plan 补实验 或 回 idea-generation 提新 idea。_
