# 从真实证据到跨材料一致：资源地图 + 可执行闭环（Round 2 R2）

> 真实研究者做一致性维护，不是“最后统一润色一遍”，而是：
> **从原始证据提候选 → 人确认权威源 → 定义材料清单与检查面 → 全量回扫 →
> 人裁定改材料还是改权威源 → 重扫并交 checkpoint**。

本文件与现有资料互补、不重叠：

- [`docs/competitors/consistency.md`](../../../docs/competitors/consistency.md)：
  **R1 对标判据 SSOT**，回答“同行 skill / 工具有什么机制、证据在哪”；
- [`../SKILL.md`](../SKILL.md)：**执行契约**，回答“何时 ACT / ASK / NEVER、如何产 findings”；
- [`../assets/`](../assets/)：**事实源 schema 模板**，回答“canonical 数据机器怎么存”；
- file-reading / result-analysis / paper-writing / citation 等技能自己的 references：
  **领域方法**，本文件不重造解析、统计、写作或引文核验。

本文件只回答：**一个真实研究者会去哪些资源，怎样把它们接成可追溯、可复扫、可阻断的闭环。**

---

## §A 五步闭环

### Step 1 · 建权威源：先 harvest 候选，后由人确认 canonical

#### 1.1 先确定“谁有资格定义”

按事实类型找第一权威：

| 事实类型 | 首选权威 | 可用辅证 | 不能单独当项目真值 |
|---|---|---|---|
| 方法 / 模块名 | 论文题名、方法定义段、作者确认 | 代码类名、README | 外部 style guide、搜索摘要 |
| 数据集名 / 划分 | 数据卡、实验协议、最终配置 | 论文 Method | 二手博客、文件名猜测 |
| 指标定义 | 实验协议、指标实现、投稿规范 | 论文 Metrics 段 | “行业通常这样算” |
| 指标值 | 最终统计输出 / 冻结实验表 | 论文 Results 表 | PPT、临时 notebook 输出 |
| claim 与证据档 | result-analysis 的 claim-evidence 表 | 论文 Results / Discussion | 摘要宣传句 |
| accepted wording | 作者已确认的论文措辞 / 决策日志 | reviewer response | 裸模型偏好 |

#### 1.2 用 file-reading 留下候选证据

先按 [`light-file-reading`](../../light-file-reading/SKILL.md) 做 triage、parse-once、navigate-first，
再把每个候选写成：

```yaml
schema: light.consistency.harvest_candidates.v1
candidates:
  - candidate_id: metric.main.f1
    kind: metric_record
    proposed_value: 87.6
    unit: "%"
    source:
      path: paper.pdf
      locator: "p.7 §4.2 / Table 2 / row Ours / column F1"
      coverage: "p.1, p.3-8, Appendix A；未读 References"
      extraction_confidence: high
    status: proposed
```

候选可以来自真实语料，但**仍不是 canonical**。它必须保持 `status: proposed`，放在工作记录或临时
handoff 中；不得直接塞进 `.light/consistency/*.yaml` 参与阻断。

#### 1.3 人确认后由 memory-pm 写入 `.light/`

consistency 给用户：

```text
现状：Table 2 的 Ours/F1=87.6，locator=p.7 Table 2。
推荐：把它确认为 DCA-Net × CrowdScene-2k 的 F1 canonical record。
备选：若最终统计表另有冻结版本，请以冻结表为准并给路径/cell。
```

用户确认后，**memory-pm** 才写 registry。每条 canonical / record / claim 至少带：

```yaml
authority:
  owner: memory-pm
  updated_at: "2026-07-01"

provenance:
  status: confirmed
  source: "paper.pdf"
  locator: "p.7 §4.2 / Table 2 / row Ours / column F1"
```

`AUTHORITY_COVERAGE` 会把缺 registry、缺 owner/date、缺 confirmed source+locator 报为 **warn-only**。
它检查“链条字段是否齐”，不证明来源内容本身正确。

#### 1.4 语义对象层：同名不等于同一事实

写入 `.light/consistency/` 前，先把关键事实登记成 `light.consistency_registry.v1`：

```text
canonical object = type + name + value + unit + population + analysis_set
                 + denominator + numerator + method + dataset + split role
```

然后运行：

```powershell
python skills/light-consistency/scripts/consistency_registry_gate.py `
  --input .light/consistency/consistency-registry.json
```

典型阻断：

- 同名 F1 但 denominator 分别是 test instances 与 validation instances；
- 87.6 同值却一个是 `%`、一个是 `fraction`，且没有 unit_conversion 证据；
- 论文说 test split，代码/config 写 validation split；
- semantic/record/visual checker coverage 未声明；
- canonical 变更未产生 impact graph、stale marks 与 broadcast；
- 冲突被“最像/最近/相似度最高”自动解决，而没有 owner decision locator。

---

### Step 2 · 定义材料清单与检查面：先说“查哪些”，再谈“是否一致”

建立本次 scan set。至少写：

| material | 类型 | 预期检查面 | 来源 / 版本 | 读取覆盖 | 风险 |
|---|---|---|---|---|---|
| `paper.md` | 论文 | 术语、方法名、指标名值、claim、贡献 | accepted draft / commit | 全文 | LaTeX 命令需排除 |
| `abstract.md` | 项目摘要 | 主方法、主指标、claim 强度 | 官网 / 申报版 | 全文 | 字数压缩可合理省略 |
| `README.md` | 项目说明 | 方法名、数据集、主结果 | main@SHA | 全文 | 可能滞后 |
| `slides.txt` | PPT 抽文 | 术语、指标值、claim 强度 | deck v3 | slide 1–18 | 图中文字可能漏抽 |
| `results.csv` | 冻结结果 | 指标值 | final run | `Results!A1:F20` | 单位 / 百分数 |
| `submission-form.txt` | 投稿表单 | 题名、摘要、作者、claim | draft | 已填字段 | 登录页未填字段 |

原则：

1. **未在 scan set 里 ≠ 已一致**；
2. **解析失败 / 未读 / 低置信 ≠ 无冲突**；
3. 材料可有不同检查面：短摘要未出现次要术语不应自动报错；
4. 定义变更时 scan set 应升级为全部受影响产物，而不是只扫当前编辑文件。

当前脚本用显式 `--materials` 接收 scan set；材料完整率由执行记录 + file-reading coverage 保证。
若项目经常漏文件，后续优先增加 material manifest，不要让脚本猜整个仓库哪些文件算交付物。

---

### Step 3 · 全量回扫：产带位置 findings，并诚实报告覆盖

```powershell
$env:PYTHONUTF8 = "1"
python skills/light-consistency/scripts/consistency_audit.py `
  --source .light/consistency `
  --materials paper.md abstract.md README.md slides.txt submission-form.txt `
  --report .light/reports/consistency.findings.json `
  --report-target "paper+abstract+README+slides+submission"
```

检查输出时分三层：

1. **hard conflict**：SUBSTITUTION / METRIC_VALUE / GROSS_MISMATCH /
   CLAIM_STRENGTH_DRIFT → critical；
2. **review signal**：VARIANT / METRIC_NAME / CONTRIBUTION_DRIFT /
   ABBREV / STALE / COVERAGE → warn/info；
3. **audit coverage**：AUTHORITY_COVERAGE → warn-only，说明权威链或检查面不完整。

不要用“finding=0”单独宣布一致。交付句应同时写：

```text
已扫描：5/6 份预期材料。
未扫描：poster.pdf（图中文字抽取失败）。
权威覆盖：四份 registry 齐；2 条 metric record 缺 confirmed locator。
结论：已读材料中无硬冲突；整体仍为部分覆盖，不宣称全项目一致。
```

---

### Step 4 · 人裁权威 + 真修：决定改材料，还是更新权威源

每条硬冲突都给三件：

```text
现状：
  paper.md:42       F1=87.6
  slides.txt:18     F1=81.0
  authority         87.6
  provenance        paper.pdf p.7 Table 2 row Ours

推荐：
  若 p.7 Table 2 是最终结果，修 slides.txt 为 87.6。

备选：
  若 81.0 来自更新后的冻结结果，先由 memory-pm 更新 authority + provenance，
  再广播回扫 paper / abstract / README / slides / submission form。
```

裁定纪律：

- **consistency 不改材料，也不改 registry**；
- 改材料由作者 / 对应上游技能执行；
- 改权威源由 memory-pm 写入，并记录 owner、绝对日期、source、locator；
- 定义变更后必须重跑**全部 impact set**；
- 合理例外要局部登记 reason / scope / owner / expiry，不能全局关掉检查。

---

### Step 5 · 交总控：critical 阻断，warn 留人工签字，修后复跑

```powershell
python skills/light-orchestrator/scripts/run_checkpoint.py `
  --file .light/passport.yaml `
  --stage 8 `
  --findings .light/reports/consistency.findings.json `
  --ts 2026-07-01T16:00
```

- critical → `verdict=fail` → checkpoint **exit 1**；
- warn-only → `verdict=warn` → 不阻断，但必须解释；
- 修复后再跑 audit + `consistency_delta.py --final` + checkpoint，记录 before / decision / fix / after / delta；
- 视觉一致、逻辑叙事、未读材料、低置信 OCR / 表格必须列为人工签字项。

**完成证据不是“我统一了”，而是：**

```text
scan set + coverage
→ canonical source/locator
→ before findings
→ checkpoint exit code
→ 用户裁定
→ 真修
→ after findings
→ delta(FIXED / NEW / PERSISTENT / REGRESSED)
→ checkpoint exit code
```

delta 命令：

```powershell
python skills/light-consistency/scripts/consistency_delta.py `
  --before .light/reports/consistency.before.findings.json `
  --after .light/reports/consistency.after.findings.json `
  --resolved-ledger .light/consistency/resolved_findings.json `
  --decisions .light/consistency/owner_decisions.json `
  --final `
  --json-out .light/reports/consistency.delta.json
```

`NEW/PERSISTENT/REGRESSED` 缺 owner/decision/rationale/locator 时，final delta 必须 fail；`FIXED` 只说明旧 finding
在新报告里消失，不证明未扫描材料一致。稳定 fingerprint 使用
`gate + rule + loc`，不把可润色的 issue 文案当身份；重复身份必须细化 locator。
delta 输出还要保存 before/after canonical JSON 的 SHA-256。

---

## §B 资源地图（按 access / 数据去向分级）

### B1 · 本地、零 key（默认主力）

| 资源 | 真实用途 | 怎么接 Light |
|---|---|---|
| **`.light/consistency/*.yaml`** | 项目 canonical 事实源 | memory-pm 维护；consistency 只读 |
| **`consistency_audit.py`** | 十类漂移 + authority coverage | 产 `light.findings.v1` |
| **`consistency_delta.py`** | 修复前后 findings delta | 防止旧问题持久、新问题冒出、已修问题回归 |
| **file-reading 脚本 / 理解笔记** | 解析、locator、coverage、低置信标记 | 只产候选证据，不下 consistency verdict |
| **`rg` / AST / LaTeX grep** | 全仓查术语、宏、常量、标题、caption | 先按 scope 限定，避免 vendor/build 噪声 |
| **Git diff / log / blame** | 找定义何时变化、影响哪些产物 | 形成 impact set 与裁定证据 |
| **Vale** | prose 受控词、markup scope | 可作补充 linter；不替代项目真值 |
| **RedPen / textlint-prh** | 文档 validator / expected term | 可选补充；autofix 默认关闭 |
| **LaTeX glossary / acronym 宏** | 单稿内术语与缩写生成 | 与项目 registry 对齐，不另立真值 |
| **CSV / XLSX 冻结结果** | 指标权威记录 | locator 写 `sheet!cell/range` |

### B2 · 公开规范 / 权威资源（候选定义与交付约束）

| 资源 | 可用于 | 不可用于 |
|---|---|---|
| **ISO 704 / ISO 1087 术语原则** | 概念—术语治理方法 | 决定本项目方法名或实验值 |
| **会议 / 期刊 author guidelines** | 缩写、题名、摘要、格式要求 | 覆盖项目 accepted wording |
| **数据集卡 / benchmark 官方文档** | 数据集与指标正式名称 | 证明本项目跑出的数值 |
| **DTCG / Style Dictionary** | 视觉 token schema 与广播 | 宣称 PPT / 图像素已一致 |
| **开放论文 HTML / PDF / supplement** | 方法、指标、claim 候选及 locator | 不经作者确认直接写 canonical |

外部规范是“怎么表达 / 怎么提交”的权威，不是“本项目事实是什么”的权威。

### B3 · 登录 / 付费 / 闭源（仅备选，不成为完成前提）

| 资源 | 能力 | 使用边界 |
|---|---|---|
| **Trinka** | 全文术语 / 拼写 / 连字符 consistency | 商业 SaaS；未发表稿上传前 ASK |
| **Acrolinx** | 企业 termbase、content governance | 闭源 / 企业部署；只作能力锚 |
| **ApSIC Xbench / Verifika** | 双语 key-term / number QA | 本地化主场；授权与文件敏感性先核 |
| **企业术语库 / CAT termbase** | 团队 accepted terminology | 需用户授权导出；不能替用户改项目真值 |

不可用时继续走本地闭环，并明确能力差异；不得因为没有账号就停摆或伪造结果。

### B4 · 项目内部资源（最重要）

优先级通常是：

1. **冻结实验输出 / 最终统计表**；
2. **作者确认的 accepted wording / 决策日志**；
3. **论文方法定义、Results、supplement**；
4. **协议 / 数据字典 / 投稿表单**；
5. **README / PPT / 海报等派生产物**。

每个内部资源要记：

- owner；
- 版本 / commit / 绝对日期；
- source path；
- page / section / table / figure / sheet-cell locator；
- 已读 coverage 与抽取置信；
- 是否已由人确认。

---

## §C 精确分工

| 技能 | 它负责 | 它不负责 |
|---|---|---|
| **file-reading** | 输入分诊、抽取、locator、coverage、五面理解笔记 | 判断跨材料是否一致 |
| **memory-pm** | 创建 / 更新 `.light/`、owner、日期、provenance、决策历史、变更广播台账 | 替 consistency 扫材料 |
| **consistency** | 只读权威源，定位漂移，给建议，产 findings / checkpoint 输入 | 自动改材料或权威源 |
| **citation** | DOI / 题名 / 作者 / 元数据 / 引文是否真实与是否嵌合 | 项目术语和指标统一 |
| **result-analysis** | 统计重算、效应量、FDR、证据档 | 跨 README / PPT / 论文传播检查 |
| **paper-writing** | 单稿 claim-evidence、结构、措辞 | 全项目多交付物 SSOT |
| **research-ethics** | 统计诚信、夸大、伦理与权属红线 | 日常术语变体治理 |
| **orchestrator** | 聚合 findings、阻断、按根因回炉 | 重写各检测器判断 |

边界句：

> 解析成功 ≠ 来源真实；来源真实 ≠ 项目 canonical；canonical 已登记 ≠ 所有材料已覆盖；
> finding 消失 ≠ 未读材料也一致。

---

## §D 三条硬约束

1. **不把外部 style guide 当项目事实真值**。
2. **不自动把 harvest 候选写成 canonical**；人确认后才由 memory-pm 写。
3. **不因文件未读、解析失败、低置信或 registry 缺失而宣称一致**。

## 复核入口

```powershell
$env:PYTHONUTF8 = "1"
python skills/light-consistency/scripts/consistency_audit.py --selftest
python skills/light-orchestrator/scripts/run_checkpoint.py --selftest
python -m _shared
```
