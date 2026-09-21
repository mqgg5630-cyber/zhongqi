# Venue-matching 真实作者资源闭环

> 本页是执行地图。`SKILL.md` 定流程和红线；
> `references/workflow_contract.md` 定 JSON 工件；
> `references.md` 定来源权限与证据用途；`templates/` 只给空白输入/选择骨架；
> `scripts/` 负责可重复执行；`docs/competitors/venue-matching.md` 只保存 R1
> 对标证据，不是运行说明。

## Round 3 source/selection guard

`venue_workflow.py` treats `AVAILABLE` as an auditable claim, not a label.
Available sources must have a locator (`url`, `query`, `locator`, or `path`),
`checked_at`, `access_tier`, and `authority`; unavailable sources keep their
failure reason. Official venue rules, fees, deadlines, article type and page
limits must use official/publisher/venue authority, while indexing/quartile
must use index/registry authority. Evidence packets require timezone-aware
`as_of`; future `retrieved_at` is invalid evidence. User selection must have
`decision_authority=user`, timezone-aware `selected_at` not earlier than the
decision packet `generated_at`, and a recorded `because`; otherwise no selected
handoff is emitted.
`manuscript_profile.claims_delivery` must also bind the current paper-writing
claim/profile artifact by safe relative path, schema and SHA-256; otherwise
the manuscript profile is treated as hand-typed and cannot drive venue fit.

## 八步闭环

### 1. 锁定 stage-11 事实

读取 typesetting `venue-handoff.json`，校验 PDF 路径/SHA-256、
`DELIVERED`、2 类状态、页数、page size、profile/source、
compliance report 与 `critical_count=0`。读取同目录 build manifest 时只复制
paper/figure/citation/typesetting provenance。禁止重编、改版或把
`UNAVAILABLE` 当通过。

### 2. 建作者约束卡

从 paper-writing 稿件画像与 claims 复制研究方向、文章类型、方法、数据规模、
证据强度，并用 `claims_delivery.path + sha256 + schema` 绑定当前 claim/profile
工件；向作者收阶段/地区/索引/OA/APC/deadline/审稿速度/冲稳保偏好/
不可接受项。区分 hard constraint 与 soft preference。未知保持空。

### 3. 候选发现

未公开稿件先在本地把标题、摘要、独有方法/数据集名和结果句登记为私密签名，再由作者确认宽泛领域/
方法族术语；任何 public/authenticated 外部查询先跑 `query_privacy_gate.py`。报告只留 query hash 与
命中类别，不回显原文。PASS 仅表示未命中已登记片段，不证明不可重识别。

优先收作者/导师候选、关键参考文献常见 venue、官方 CFP、跨出版社 finder。
用 `venue_discovery.py` 从 Crossref 相似 work 的 container metadata 扩 recall。
每条保存 query、endpoint、时间、权限与 example DOI；频次只作发现，不作排名。

### 4. 逐字段取证

逐 venue 打开官方 Aims & Scope、article types、author instructions、fees/OA、
metrics、deadline/CFP。身份用 ISSN/Crossref 交叉核；OA 白名单用 DOAJ；OpenAlex
可补 works/topics，但 free key 缺失标 `UNAVAILABLE`。JCR/Scopus/Cabells 等无
合法访问就空着，绝不由第三方摘要代填。

### 5. 稿件事实对照

把真实 PDF 页数/page size/profile 与 page/length/template 规则对照；把真实
article type、method/data、claims strength 与 scope/type/design expectation
对照。citation/figure/paper-writing 的科学事实不在本阶段改；若 claim/profile
工件变化，stage 12 必须重新 prepare 和重新让用户选择。

### 6. fit/risk/unknown 分离

每候选分别输出 scope、type、method/data、paper strength、format、APC/OA、
timing、index、risk、author constraint 的 because/evidence。网络/权限失败进
unknowns；软 risk 进 warning；官方 type/page 不匹配与作者 hard constraint
才可客观 exclude。掠夺/劫持终判留人。

### 7. 冲稳保与决策暂停

生成 registry/evidence/fit-risk/unknown/decision/delivery 六件套。
`decision_point=true`、`chosen=null`；给 reach/match/safety 与 transfer order，
然后真实停下问作者。stage 12 没有 checkpoint、critical gate 或 route 出边。

### 8. 选择后交接

只接受 `actor=user` 的 selection artifact。选择后才生成 selected handoff、
review-rebuttal context 与 author submission plan；下游按相同 evidence IDs
消费规则/未知/provenance。`selected_at` 不得早于 decision packet `generated_at`。
投稿日重核易腐字段，再次停在 portal submit 前。

## 资源访问分层

| 层级 | 核心资源 | 用法与边界 |
|---|---|---|
| 本地免费 | Python stdlib、真实 stage-11 工件、`venue_workflow.py`、`venue_discovery.py` | 核心路径；不依赖浏览器插件/npm |
| 免费公开 | Crossref、DOAJ、ISSN Portal 网页、官方 venue/publisher author instructions、官方 CFP、Think.Check.Submit、Retraction Watch hijacked checker | 发现、身份、OA、规则、风险人工核；失败为 unavailable |
| 免费登录/key | OpenAlex free key、部分 publisher finder/portal、Scopus limited API key | 可选增强；缺 key/login 不阻塞核心 |
| 机构受限 | JCR、Scopus 完整源、学校认可目录/政策、部分 WoS/CCF/中科院字段 | 用户合法访问或提供导出；记录版本/日期 |
| 付费闭源 | Cabells、商业选刊/编辑服务、付费指标库 | 只列可选；不得成为核心依赖或由代理绕过 |

## 工件与旧资源分工

- `references.md` 不保存 venue 数值，只保存“去哪取、能证明什么、不能证明什么”。
- `templates/venue_input.json` 是空白证据 envelope；示例值不得当事实。
- `templates/venue_compare_table.md` 是 decision packet 的人读视图，不是数据库。
- `venue_signal.py` 是可选信号采集器；它不能替代官方 scope/rules。
- `venue_fit_rank.py` 与 `venue_risk_gate.py` 保留旧项目兼容；新闭环以
  `venue_workflow.py` 为 canonical。
- `docs/competitors/venue-matching.md` 的 star/commit/行号用于开发审计，不在
  运行时加载。

核心路径不依赖 Cabells/JCR/Scopus 订阅、私有 API key、浏览器插件或 npm
重依赖。
