# result-analysis 工具一手核查笔记（真实命令 / 机制 / 已知坑 / 版本敏感）

> **2026-06-19 上网一手核实**（非凭记忆，铁律 2）。环境实测:numpy 2.0 · scipy 1.14.1 · statsmodels 0.14.5 ·
> sklearn 1.5.2 · pandas 2.2.3 · pingouin 0.6.1 · matplotlib 3.9.4 · shap 0.46.0(全可用)。
> 原则:**效应量/CI/多重比较校正优先 statsmodels/scipy/pingouin,别重造**;自写只留 evidence_contract 接线 + DeLong(库里没有)。

## 多重比较校正(stat_validity 门的核心)

- **statsmodels** `from statsmodels.stats.multitest import multipletests`:`multipletests(pvals, alpha=0.05, method="fdr_bh")`
  返回 `(rejected_bool, pvals_corrected_q, _, _)`;method 还有 `"bonferroni"`/`"holm"`/`"fdr_by"`;`is_sorted=False` 默认按原序返回。
  **BH-FDR**(Benjamini-Hochberg)控 **FDR**(假发现率,功效高);**Bonferroni** 控 **FWER**(族错误率,保守)。**显著性一律看校正后 q。**
- v2 `stat_rigor_gate` 用港来 `significance_test.benjamini_hochberg`(numpy,`__main__` 已对齐 statsmodels 数值一致),缺 numpy →
  纯 stdlib BH 兜底(同款公式,确定性);statsmodels 是正确性锚。**裸 p<.05 经 BH 后掉到 q≥.05 = 假阳性 → critical。**

## 检验选择(analyze_results 自动派发,scipy.stats)

- `scipy.stats`:`ttest_ind(a,b,equal_var=False)`(Welch,**不假设等方差,默认首选**)、`mannwhitneyu`(非参 2 组)、`f_oneway`(ANOVA)、
  `kruskal`(非参多组)、`levene(center="median")`(方差齐性)、`shapiro`(正态性)、`ttest_rel`/`wilcoxon`(配对)。
- 派发逻辑(analyze_results):2 组正态→Welch t / 非正态→Mann-Whitney;≥3 组正态→Levene 齐→ANOVA+Tukey、不齐→Welch-ANOVA / 非正态→Kruskal。
  **配对设计**(共享 seed/fold)→`--paired-by` 走配对 t/Wilcoxon(扣单元间方差,功效更高,误当独立会低估显著性)。
- **小样本坑**:Shapiro 在 n<10 功效低,「判正态」不可靠 → analyze_results 自动标 small_n_warning,提示改非参/预设检验。

## 效应量(evidence_strength 分档的输入)

- **Cohen's d**(`significance_test.cohens_d(a,b,correction=True)` 带 **Hedges' g** 小样本校正 J=1−3/(4(na+nb)−9)):适正态/齐方差;
  量级惯例 0.2 small / 0.5 medium / 0.8 large(**惯例非真理,跨领域不同**)。
- **Cliff's δ**(非参,随机优势 P(X1>X2)−P(X1<X2),范围[−1,1]):**序数/非正态/有离群更稳**,无正态假设。**诚实落后项:v1/v2 当前只算
  Cohen's d,Cliff δ 待补**——非参检验(MWU/Kruskal)宜配 Cliff δ 而非 d。pingouin `compute_effsize(...,eftype="cles")` 可补。
- **配对效应量** d_z = mean(diff)/sd(diff)(analyze_results 配对路径已算)。

## 置信区间 / bootstrap

- `significance_test.mean_diff_ci(a,b,equal_var=False)`(Welch df,自测 == scipy `ttest_ind().confidence_interval`)、
  `bootstrap_ci(x,stat,n_boot,seed)`(percentile bootstrap)。
- `scipy.stats.bootstrap(data, statistic, method="BCa")`:三法 `percentile`/`basic`/**`BCa`(偏差校正加速,默认,更准)**。**CI 含 0 = 差异方向不定 = 不显著。**

## DeLong 相关 AUROC 比较(港 v1,statsmodels/scipy 没有)

- `significance_test.delong_two_auroc(y_true, score_a, score_b)`:同一测试集两模型 AUROC 差是否显著(**相关样本,方差扣协方差**,
  普通独立检验会错)。纯 numpy,`__main__` 与 sklearn `roc_auc_score` 数值对齐、自比 p=1。医疗/分类评估常用。

## SHAP 可解释性(explain_shap,**非因果**)

- `shap.TreeExplainer`(树模型 RF/GBM/XGB/LGBM 精确快路径)→ 统一 `shap.Explainer`(自动挑 Tree/Linear)→ `KernelExplainer`(模型无关
  兜底,背景集 shap.kmeans/sample ~100 行控成本)。三图:beeswarm(全局方向)/bar(重要性)/waterfall(单样本分解)。
- **三个坑(写进脚本 docstring)**:① 相关特征**稀释**归因(贡献被代理特征分走,配相关矩阵读);② **SHAP 非因果**——「特征推高预测」≠
  「特征导致结果」,**绝不当因果证据**(官方明示);③ KernelExplainer **昂贵**,必采样背景集 + 算 modest 行。shap 缺失优雅降级 exit 0。

## 漂移监控(Evidently,**版本极敏感 — 铁律 2 核出的坑**)

- **Evidently v7.0(2025-04-10)默认换新 API,破坏式变更**:旧 `Report(metrics=[DataDriftPreset()])`(≤0.6.7)迁到 `evidently.future`。
  **用前必先核 Evidently 版本**,旧 API 调用在 v7 直接报错。v1 SKILL 写的就是旧 API——本轮一手核出、如实标注,别照搬旧调用。
- 替代:跨数据集/跨设置一致性也可用 analyze_results 的多数据集复算 + scipy KS 检验,不强依赖 Evidently。

## p-hacking 文献(stat_validity critical 的判据源)

- **Simmons/Nelson/Simonsohn 2011《False-Positive Psychology》**:researcher degrees of freedom → p-hacking 把名义 5% 假阳性最坏抬到 **61%**;
  「探索多种分析、只报成功那个」= 至少一个假阳性概率远超 5%。→ 多重比较未校正/选择性报告 = critical。
- **Gelman & Loken 2013《Garden of Forking Paths》**:即便**单次分析 + 预注册假设**,数据依赖的分析选择 = 隐性多重比较 → 校正必要性比
  显式 fishing 宽。**机器测不全隐性 forking paths**(诚实落后项)。
- **Kerr 1998 HARKing**:把事后假设当 a-priori 报;第三型 = **不报与结果不符的 a-priori 假设** → hypothesis_support 门:假设证否须如实回报、
  回炉 research-plan,**绝不删掉换成功假设重报**。
- **GRADE**(Cochrane):证据确定性四级 high/moderate/low/very-low(对 evidence_contract strong/moderate/weak/none);5 降级域=偏倚/不一致/
  间接/不精确/发表偏倚——evidence_contract **只吃统计强度**(≈不精确+效应量),另四域待 result-analysis 拿多数据集/多种子做「不一致」域降级。

## 与下游/常驻的接口

- **evidence_strength.json**(`light.evidence_strength.v1`)= result-analysis↔paper-writing/research-ethics 的桥:本技能(stage 7)**定证据档**,
  research-ethics(stage 8)`claim_evidence_bind` **查措辞是否超过证据**(消费同一文件),不重叠。
- **run_manifest.md**(上游 experiment-coding)给多种子指标 + 产物路径 → result-analysis 据此做统计 + claim 绑定 + 多种子稳定性(reproducibility 门)。
- **回炉**:reroute `ROUTES[7]` 两条出边 7→5(信号 假设/支撑/效应)/ 7→6(信号 种子/复现);p-hacking critical 无信号 → manual(stage 7 内修)。

## Round 2：计划/设计/provenance 与 R 双路径

- `analysis_plan_audit.py` 只产 warn，不扩大 stage-7 critical 面。它核
  `status/locked_at/results_available_at`、hypothesis/primary metric/unit/exclusion、
  stable `family_id` + planned/reported/correction、expected/observed units，以及输入
  path/hash/owner/time/run manifest/commit。仅声称 `status=frozen` 但缺时间线，或完全没有输入工件，
  都必须显式 warn；Windows PowerShell 产生的 UTF-8 BOM JSON 可直接读取。
- 复杂设计（repeated/hierarchical/cluster/nested CV/repeated holdout/time series）只会被标
  “简单独立/配对检验不可终判”；需 mixed model/GEE/cluster bootstrap/corrected CV 等专门方法，
  当前不假装已实现。
- `r_analysis_crosscheck.R` 不依赖可选包，真算两组 paired t 或 independent Welch t；Python launcher
  依次探 `RSCRIPT`、PATH、Windows Program Files。
- 2026-07-01 本机实测：`Rscript` 不在 PATH；全路径 R 4.6.0 可执行；base R 与 `boot` 可用；
  `ggplot2/broom/effectsize/rstatix/emmeans/lme4` 均不可用。因此只能声称“base-R 关键检验交叉核验”，
  不能声称“高级 R 统计生态均已安装”或“mixed-effects R E2E 已通过”。
