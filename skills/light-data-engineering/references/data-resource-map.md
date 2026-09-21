# 数据从哪里来、能不能用：真实研究者资源地图 + intake 闭环（Round 2 R2）

> 本文件回答“真实研究者为一个 idea 找数据时，去哪里、按什么顺序、怎样接回 Light 的门”。
> 它与根目录 [`references.md`](../references.md) **互补不重复**：`references.md` 是 pandas/OpenML/HF/
> Kaggle 等工具的调用细节；本文件是 **需求 → 发现 → 下载前审计 → 抽样 → 获取与血缘 → 泄漏/可行性门 →
> 发布** 的用户工作流。竞品判据仍以
> [`docs/competitors/data-engineering.md`](../../../docs/competitors/data-engineering.md) 为 SSOT。
>
> **零本地库铁律**：本地图只保存资源类别、access 与复核方法，不把数据条目/大小/许可做成易腐目录。
> 候选的 license、gating、版本、大小与可达性必须在使用当天重核；查不到写 `unknown`。

---

## A. 六步闭环（每步都接现有脚本/门）

### Step 1 · 先写数据需求卡，别从下载开始

从 idea-generation 的数据字段冻结以下内容：

- **科学对象**：观察单位是什么（患者/用户/牧场/图像/时间窗）？目标人群与时间范围是什么？
- **任务与 target**：分类/回归/检测/时序；label 如何定义、在预测时点是否真实可得？
- **最小规模**：总样本、最小类/正例、特征数、group 数；这里只是筛候选，正式功效仍归 power analysis。
- **split 约束**：按实体、地点、设备、中心、时间还是随机；哪些 ID 绝不能跨 train/test？
- **资源预算**：允许的格式、最大下载量、算力/存储、必须免 key/免登录还是可接受 gated。
- **权利边界**：允许的 license、是否要再分发、是否涉人/医疗/敏感属性。

**反例**：“找一个乳腺癌数据集，下载量最高的就行。”
**正例**：“二分类、患者级观察单位、至少 500 人、患者不得跨 split、需可公开论文结果、原始数据最大 2 GB；
license 与来源必须可核。”

### Step 2 · 多源找候选，不把任何单站当真相

1. **机器学习通用**：Hugging Face Hub、OpenML、UCI。
2. **论文/benchmark 线索**：论文 supplement、作者项目页、OpenML benchmark、历史 Papers with Code 快照。
3. **综合科研仓储**：Zenodo、Figshare、Dataverse；优先 DOI/版本化 record。
4. **竞赛/社区**：Kaggle（登录/token/条款）；只作为候选源，不把 votes/usability 当科学质量。
5. **领域权威库**：如医疗/基因/遥感/政府统计的官方 repository；机构/法域规则优先于通用门户。

Hugging Face 公开候选先跑：

```powershell
python scripts/dataset_intake.py --query "breast cancer" --limit 10 --sort downloads `
  --report data_candidates.json
python scripts/dataset_intake.py --inspect scikit-learn/breast-cancer-wisconsin
```

`metadata-ready` 仅代表下载前字段较齐；报告会保存 `raw_response_sha256` 与
`candidate_manifest_sha256` 以便复查当天 API 结果。`review` 代表缺
license/revision/last_modified/size/split/file tree/card、license 只来自 tag、命中
医疗/隐私/人类等敏感标签或受限，**两者都不是“科学上可用”判决**。

### Step 3 · 下载前 preflight：先卡许可、版本、大小、split

每个 shortlist 候选逐项登记：

| 面 | 必须拿到 | 缺失时怎么办 |
|---|---|---|
| 身份 | provider id + 官方 URL + DOI（若有） | `unknown`，不拿二手转载页代替 |
| 版本 | revision/version + last_checked | 不能锁版本则不可声称可复现 |
| 权利 | license 原文 locator、gating、用途/再分发限制 | unknown 不等于允许；回官方条款 |
| 成本 | bytes/size category、文件树、格式 | 大小未知不整库下载 |
| 科学适配 | 观察单位、目标人群、采集期、label 定义 | card 没写就找原论文/作者说明 |
| split | 官方 split 生成法、group/time/seed | 不明则只视为原始 pool，自行设计 |
| 风险 | PII、偏差、重复、目标泄漏、撤回/勘误 | 交 research-ethics 与领域专家 |

**NON-NEGOTIABLE**：没有明确 license locator，绝不把“网页可下载”写成“可公开使用/再分发”。

### Step 4 · 先看 card/schema/sample，再决定整库获取

顺序固定为：

1. 读 dataset card / paper / file tree；
2. 只取一个文件、一个 split 或 500–2,000 条代表性样本；
3. 记录 sample URL、revision 与 SHA256；
4. 跑 `data_doctor.py` 与必要的 `quality_gate.py`；
5. 样本暴露出 task/label/格式/许可不匹配时，淘汰候选，不为沉没成本硬用。

超大数据优先用 streaming、range/subset、DuckDB `hf://`、HF `--include` 或 sparse checkout；
只有 shortlist 通过 preflight 才拉全量。Kaggle/HF skill 的“先 metadata/file tree，再单文件，再整库”是节流共识。

### Step 5 · 获取后锁血缘，再过科学门

原始数据必须 immutable，至少记录：

```text
provider/id + source_url + revision/version + retrieved_at
raw_sha256 + raw_bytes + file list
cleaning_script + git commit + cleaned_sha256
removed/changed row mapping + split scheme/seed/group/time
```

`data_identity_fitness.py` 的 `as_of`、`dataset.snapshot_at`、split `created_at`
与 `fitness.staleness.data_valid_at` 必须是已经发生的真实核验/冻结时间。未来时间视为预填证据，
会阻断交付；若数据尚未获取、split 尚未创建或有效性尚未核验，就保持 `UNKNOWN/NOT_FIT`。

`decision=NOT_FIT/UNKNOWN` 是阻断性裁定，不是“可继续但提醒一下”；只有 `FIT`
或限制已写入 `fitness.limitations` 的 `FIT_WITH_LIMITATIONS` 才能向下游交接。

然后按顺序执行：

```powershell
python scripts/data_doctor.py --csv data.csv --target y --out data_health.md
python scripts/safe_split.py --csv data.csv --target y --task group --group-col patient_id --group-clf
python scripts/split_leakage.py --train train.csv --test test.csv --group-col patient_id --target y `
  --out leakage.md --findings leak_findings.json
python scripts/data_feasibility_gate.py --spec feasibility_spec.json --report feasibility_findings.json
```

- 泄漏 HIGH → critical，先修 split/特征；
- 可行性 insufficient → checkpoint fail，`reroute --stage 2` 建议 **2⊣3**；
- 偏紧/metadata gap → warn/advisory，不冒充 critical；
- 清洗、去重、重标或换 split 后必须**重跑**质量与泄漏门。

### Step 6 · 交总控、写数据卡、发布或降级

1. `run_checkpoint --stage 2` 聚合泄漏与可行性 findings；
2. pass/warn 后补 [`assets/data_card_template.md`](../assets/data_card_template.md)；
3. 需要机器可读发布时跑 `croissant_export.py`；
4. `check_access_level.py` 卡 raw/redacted/verified_only 的下游流向；
5. license/隐私/伦理仍未解决时，状态写 `restricted` / `unresolved`，不发布；
6. 若无候选撑得起 idea，带“缺口 + 已查源 + 淘汰理由”回 idea-generation，而不是换一个下载量高的数据硬做。

---

## B. 资源地图（按 access 分级）

### B1 · 免费公开、读取元数据通常免 key（主力）

| 资源 | 适合找什么 | 怎么接闭环 | access / 诚实边界 |
|---|---|---|---|
| **Hugging Face Hub** | ML/NLP/CV/audio/tabular；dataset card、revision、tags、gating | `dataset_intake.py` 搜公开元数据 → shortlist → card/file tree/sample；大数据用 streaming | 公开 metadata API 免 key但有 rate limit；具体 repo 可 gated/private，不能因搜索可见就说可下载 |
| **OpenML** | 版本化 ML 数据、标准 task/split、规模/特征筛选 | Web/API 按 size/type/format 筛；锁 `data_id+version`；可取 Croissant | 公共发现/下载可免 key；社区上传质量参差，版本/许可/target 仍要核 |
| **UCI ML Repository** | 经典中小型表格数据、DOI/论文关联 | 官方 dataset 页核变量、missing、license、DOI；下载后自己设计 group/time split | 免费网页/下载；不要依赖未承诺稳定的私有 API；用 WebFetch/官方文件 |
| **Zenodo / Figshare / Dataverse** | 论文配套、跨学科版本化数据、DOI | 搜 DOI/作者/项目；锁 record version + file checksum；回论文核语义 | 公开 record 通常可读；单条 record 的 license/embargo/文件权限各异 |
| **领域官方库 / 政府开放数据** | 医疗、基因、遥感、气象、统计等权威数据 | 以官方 data dictionary、版本、法域条款为 authority packet | “官方”不自动等于开放再分发；机构条款与伦理优先 |

### B2 · 免费但需登录、token 或接受条款（可选，不能成为默认依赖）

| 资源 | 用法 | honest access |
|---|---|---|
| **Kaggle Datasets/Competitions** | 搜索→metadata/file tree→单文件→指定版本下载 | 需账号/token；部分竞赛必须先网页接受规则；`kaggle.json` 禁入库 |
| **Hugging Face gated datasets** | card 可见但文件需申请/接受协议 | `dataset_intake` 标 `gated`；未获权限写 `UNAVAILABLE`，不绕过 |
| **Google Dataset Search** | 跨站发现线索 | 浏览器搜索可用但无稳定开放 API；只当线索，最终回原始 host |

### B3 · 受控、付费或机构审批（不依赖；需要时显式停下）

- UK Biobank、临床/基因受控库、ICPSR 受限集合、机构数据仓、商业数据供应商等。
- 需要 DUA、IRB、机构登录、申请、费用或地域限制时，写清 `restricted`、审批人、用途与到期日。
- 用户未提供合法访问权时，**不代登录、不绕过、不用镜像盗链**；转向 B1 公开替代或改 idea。

### B4 · 历史/失效资源

- **Papers with Code 原站已于 2025-07-24 停止服务**；现有 archive 只能用于找历史 dataset/benchmark 线索。
- 任何 archive 条目都要回论文、作者仓库或官方数据主页核版本、许可和下载地址，不能当 live SSOT。

---

## C. 三条守硬约束

1. **资源可见 ≠ 许可可用**：unknown license、二手镜像、未接受 gating 条款，一律不进入“可用”。
2. **下载成功 ≠ 科学可用**：card/schema/sample 只过 intake；质量、泄漏、代表性与功效还要过 Light 的门。
3. **清洗完成 ≠ 可复现**：没有 raw hash、revision、变换脚本/commit、行映射和 split 记录，就不能声称结果可复现。

## 当天复核入口

- HF 官方开放 API：`https://huggingface.co/docs/hub/en/api`
- HF 搜索/CLI：`https://huggingface.co/docs/huggingface_hub/guides/search`
- OpenML 数据发现/加载/Croissant：`https://docs.openml.org/data/use/`
- UCI：`https://archive.ics.uci.edu/datasets`
- Kaggle CLI（官方仓库）：`https://github.com/Kaggle/kaggle-cli`
- Papers with Code 历史快照说明：`https://world-snapshot.github.io/papers-with-code/`

> **使用前当天核**：API、gating、许可、版本、大小与服务状态都可能变化；失败/受限写
> `UNAVAILABLE` / `unknown`，转其他 B1 源，不用旧快照冒充实时结果。
