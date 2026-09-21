# 科研伦理真实资源工作流

> 这是执行地图，不是法规百科。`docs/competitors/research-ethics.md` 是对标判据 SSOT；`SKILL.md` 管红线与脚本；
> `decision_trees.md` 管高利害分支；`cn_compliance.md` 管中国法域入口。本页只回答：真实研究者在项目生命周期中先查什么、
> 用什么工件承接、何时停下找机构，以及怎样把结果交给 Light 既有门。

## 五步闭环

### 1. 分诊：法域 × 对象 × 数据 × 阶段

先建 `authority packet`，至少记录：

```text
project / activity:
jurisdiction + institution:
participants: none | human | animal | both
data: public | anonymous | pseudonymous | identifiable | sensitive
intervention / recording / biological sample:
stage: plan | approval | collect | analyze | publish | post-publication
authoritative form/SOP URL or local path:
owner + checked_at:
unresolved:
```

按优先级取规则：

1. 研究所在机构当前伦理委员会/IRB/HREC/IACUC 的表单、SOP、批准函与 amendment 规则；
2. 研究所在地现行法律法规与主管部门原文；
3. 目标 venue/funder 当前政策与 reporting guideline；
4. 国际原则与行业流程（Helsinki、COPE、ICMJE、ARRIVE、CRediT）；
5. 博客、论坛、第三方模板只能帮助发现问题，不能覆盖前四层。

若法域、机构或活动性质不清，停止填表并 ASK。不要用美国 Exempt/Expedited/Full Board 词汇硬套中国、欧盟或机构自有路径。

### 2. 设计与批准：在采集/干预前锁定

真实工作顺序：

1. 用机构表单描述科学问题、参与者、招募、活动、时长、记录、数据字段、分享与保留；
2. 逐风险登记 `受影响者 | harm | likelihood | severity | mitigation | residual risk | owner`；
3. 将 consent **过程**与 consent **文件**分开：谁在何时怎样解释、如何确认理解、如何退出、数据退出边界是什么；
4. 对录音录像、二次使用、公开分享、可识别引文分别取 consent，必要时 layered/ongoing consent；
5. 由机构做 exempt/免审/简易/快速/full-board 等决定；研究者和 Light 不自行宣布；
6. 批准函/备案/豁免认定未取得前，不开始需批准的招募、采集或干预。

把 consent 范围单独落成 `light.consent_scope_packet.v1`，再运行
`scripts/consent_scope_gate.py`。该门不判断 waiver/exempt 是否成立，只核录音、公开引文、二次使用、共享、repository release、
跨境传输、模型训练与退出后数据处理是否有 exact consent/authority locator；“有一份同意书”不能自动覆盖所有用途。

至少交付：

- protocol/application；
- participant information / consent / assent；
- recruitment material；
- data management / security / access plan；
- risk register；
- approval、waiver 或 institution determination 的真实 locator。

`assets/ethics_review_template.md` 记录当前状态与缺口，不代替这些原始工件。

### 3. 实施与变更：批准不是一次性文件

每次出现以下事件，重新打开 authority packet 与批准条件：

- 增加人群、地点、合作方、数据字段、录音/影像、二次用途或跨境传输；
- 风险上升、出现 adverse event / breach / participant complaint；
- consent 文本、招募方式、补偿或退出方案改变；
- 原 protocol 中没有的新分析、公开共享或模型训练用途；
- 研究暂停、提前终止、PI/owner 变化。

动作：

1. 对照机构 amendment / incident reporting / continuing review / closure 路径；
2. 未获必要批准前暂停受影响活动；
3. 记录 `change → risk delta → authority consulted → decision → effective date`；
4. 对 ongoing consent 重新告知受影响参与者，并重跑 `consent_scope_gate.py` 覆盖新的用途/数据/共享范围；
5. resume 长周期项目时重核批准状态与到期/continuing-review 条件。

先将上述状态写入 `assets/authority-packet.example.json` 的本地副本，再运行
`scripts/authority_lifecycle_gate.py`。它只核真实来源/locator、批准范围集合差异、变更是否先审、
事件是否按已声明义务报告；不会自行决定某活动是否 exempt/waived，也不会把 PASS 写成法律意见。

### 4. 分析与写作：让每个主张只用自己的证据

先跑确定性门，再做人判：

```powershell
# 统计报告值重算 / GRIM 信号
python scripts/extract_stats.py paper.txt --json
python scripts/stat_consistency.py grim --n <N> --mean <MEAN>

# 每条论文 claim 绑定自己的 evidence IDs；strong A 不得兜底 B
python scripts/claim_evidence_bind.py `
  --draft draft.md `
  --evidence evidence_strength.json `
  --claim-map claim_plan.json `
  --json

# 仅比对用户提供的旧作语料，不宣称全库“查重率”
python scripts/text_overlap.py paper.txt "prior-work/*.txt" --min-run 40 --exclude-refs

# tortured phrase 是 paper-mill 筛查信号，不是定罪
python scripts/tortured_phrase_scan.py draft.txt --refs references.txt
```

同时人工核：

- planned 与 post-hoc 是否区分；
- null/negative/contradictory results 是否保留；
- 因果、外推、机制、SOTA 与 novelty 措辞是否超过设计与证据；
- 小社区、可搜索原话、影像/声音、交叉表连接是否造成 deductive disclosure；
- 申请表、consent、DMP 与实际分析/分享是否一致。

发现 claim 无证据或超档：BLOCK，回 8→7/6 或弱化；发现伦理范围变化：回步骤 2/3 找机构，不靠写 limitations 静默补票。

### 5. 提交、发布与出版后：收口仍可回炉

投稿/发布前：

0. 先运行 `scripts/ethics_evidence_gate.py --input <ethics-evidence-packet.json>`，
   核 `ethics_evidence.v1`、`ai_use_ledger.v1`、`contribution_record.v1` 与
   `untrusted_content_boundary.v1`；UNKNOWN 证据、AI 政策未核、贡献/署名不闭合、
   外部内容未隔离或风险信号写成定罪时，不进入交付。
0.5. 涉人/参与者数据项目再运行 `scripts/consent_scope_gate.py --input <consent-scope-packet.json>`，
   核实际用途与 consent/waiver/authority 范围、退出边界和跨附件一致性；UNKNOWN 只可停在早期计划，不可进入采集、分析或发布。
1. 用目标 venue/funder 当天的 author instructions、AI policy、data/code policy 与 reporting checklist；
2. 用 ICMJE qualification 与 CRediT contribution 分开核署名；CRediT 角色不自动等于作者资格；
3. 核对 AI 使用披露位置与措辞；AI 不能列作者；
4. DOI 经 `check_retractions.py` 查 Crossref production schema；RETRACTED/FLAGGED/UNRESOLVED 分开；
5. 动物研究用 ARRIVE 2.0，医学人体研究用当前 Helsinki/相关 reporting guideline，但这些都不替代审批；
6. 数据/代码发布前复核 consent scope、许可、PII、访问等级与撤回约束；
7. 将所有 BLOCK/WARN 的 locator 与 owner 写入 `ethics_review_template.md`，再交总控 checkpoint。

出版后：

- 发现错误、投诉、撤稿/关注声明或新再识别风险时，保全证据并按机构/COPE/venue 路径升级；
- 不公开指控个人，不让脚本信号替代调查；
- 更正、撤稿、数据撤回、参与者通知由有权限主体决定并留下版本记录。

## 资源访问分级

### A. 本地 / 无 key（默认先用）

- 本技能 `scripts/`、`assets/`、`decision_trees.md`、`cn_compliance.md`；
- 项目自己的 protocol、approval、consent、DMP、risk register、claim plan、evidence artifacts；
- 本技能的 `assets/consent-scope-packet.example.json` 与本地项目副本；
- git/run/config/hash/owner/date 等 provenance；
- 机构表单的版本化本地副本（保留官方 URL、取得日期、版本）。

本地文件是项目事实源，不是法规真相源。审批号、同意范围、作者贡献、数据路径不得由模型补造。

### B. 公开权威 / 无 key

| 任务 | 首选资源 | 怎样接入闭环 |
|---|---|---|
| 美国涉人分诊 | OHRP 45 CFR 46、2018 decision charts | 步骤 1/2；记录适用条件与机构 Terms of Assurance |
| 方案变更与事件 | OHRP 当前 IRB written procedures、机构 amendment/incident SOP | 步骤 3；变更实施前核决定，事件按机构路径及时升级 |
| 美国科研失信程序 | ORI 42 CFR Part 93 current rule/guidance | allegation date 决定版本；只做升级路径，不自行定罪 |
| 出版伦理 | COPE Core Practices + flowcharts | 步骤 5；选 misconduct/authorship/COI/correction 对应路径 |
| 作者与 AI | ICMJE 2026 Recommendations | qualification、责任、AI 披露；再叠目标刊政策 |
| 贡献角色 | CRediT ANSI/NISO Z39.104-2022 | 登记 14 角色；不代替 authorship criteria |
| 医学人体研究原则 | WMA Helsinki 2024 | 原则层；只引用 2024 current version |
| 动物报告 | ARRIVE 2.0 Essential 10 + Recommended Set | 设计与论文收口；不代替 IACUC |
| 撤稿/更正状态 | Crossref REST production + RW CSV | `check_retractions.py`；Labs 已过时，不再用 |
| 中国涉人伦理 | 国家卫健委 2023《涉及人的生命科学和医学研究伦理审查办法》 | 步骤 1/2；再叠机构伦理委员会 SOP |
| 中国广义科技伦理 | 科技部 2023《科技伦理审查办法（试行）》 | 人/动物/可能影响生命健康、生态、公共秩序的活动 |
| 中国科研失信 | 科技部等 22 部门 2022《科研失信行为调查处理规则》 | 认定/调查归单位与主管部门；技能只报信号 |
| 健康数据去标识 | HHS HIPAA de-identification guidance | Safe Harbor / Expert Determination 分路；去标识风险非零 |
| 数据管理共享 | NIH DMS / funder current policy | DMP、repository、访问与 consent scope 对齐 |
| 人体数据二次使用 | NIH/OHSRP secondary research guidance + 本机构 IRB | 原 consent 限制与新用途/分享逐项比对；冲突时停下找机构 |

访问失败时：记录 `URL + checked_at + HTTP/错误 + 未核字段`，改用官方镜像/公报/PDF；仍失败则标 UNRESOLVED 并 ASK
用户提供机构文件。搜索摘要可定位原文，不可当最终法律依据。

### C. 机构 / 登录

- IRB/HREC/IACUC portal、Infonetica 等提交系统；
- institution-approved storage、DPO/privacy office、research integrity office、legal/tech-transfer；
- CITI 或本机构 training 记录；
- 医院 EHR/受控数据环境。

这些资源通常最权威，也最敏感。Light 不尝试登录、代签、代提交或上传参与者数据；用户在授权系统内完成动作，并只回传必要状态
与 locator。

### D. 付费 / 闭源（可选，不得成为完成前提）

Proofig/ImageTwin、iThenticate/Turnitin、商业合规平台可列为专业复核选项。没有账号时必须诚实标能力缺口：

- 无图像取证 → 人工/机构/专业工具；
- 无全库查重 → 只报自给语料 overlap；
- 无法律顾问 → 不给法律结论；
- 无受限数据库 → UNRESOLVED，不写 CLEAN。

## 与既有 reference 的互补边界

- 本页：资源、访问级别、生命周期顺序、工件与 Light 门的接线。
- `decision_trees.md`：FFP/机构升级、涉人、撤稿、涉动物的高利害分支。
- `cn_compliance.md`：中国现行官方入口与已核范围。
- `assets/risk_checklist.md`：逐项红旗；不是资源导航。
- `docs/competitors/research-ethics.md`：R1 对标证据；不是用户执行指南。

## 收口检查

- [ ] authority packet 有法域、机构、对象、数据、阶段、owner、checked_at。
- [ ] 需要机构决定的路径没有被 Light 自行判 exempt/clean/approved。
- [ ] protocol、consent、recruitment、DMP、实际执行与发布范围一致。
- [ ] consent scope packet 已覆盖录音/公开引文/二次使用/共享/发布/跨境/模型训练与退出边界。
- [ ] 变更、incident、resume 已触发状态重核。
- [ ] 每条 strong claim 只绑定自己的 evidence IDs 与 source locators。
- [ ] 撤稿状态区分 RETRACTED / FLAGGED / CLEAN / UNRESOLVED。
- [ ] 付费/登录/受限资源不可用时已显式降级，没有伪造“已查”。
- [ ] BLOCK/WARN 有 locator、owner、下一步与第三方权威。
- [ ] 交付证据包通过 ethics_evidence_gate；AI、贡献、外部内容边界和信号语言未靠口头承诺放行。

## 续补规则：checked_at 不得来自未来

`checked_at` 必须是实际核验/检索日期，不能预填未来日期。若 ethics
document、AI policy、authority packet 或 authority source 的 `checked_at`
晚于当前 `as_of`/运行日，机器门会阻断，因为这不是已完成核验。
