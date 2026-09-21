# 提 idea：真实研究者工作流 + 资源地图（真实用户视角 · Round 2 R2）

> **真实研究者提 idea 不是"丢个方向求点子"**——是**沿 related-work 找 gap + 跨域类比迁移 + 提出时就撞车前置查 +
> 分层下注**的工作流:吃文献领域地图的未解问题 → 系统过 5 型 gap → 跨域把别处前沿迁过来 → 每个候选当场查最像前作 →
> 收敛成 moonshot/solid/safe 分层送审。本文件把这套**真实工作方式内化进本技能**:每一步**接进本技能既有脚本/门的
> 闭环**,不是方法论罗列。
>
> **与既有文件不重叠声明**(范本 search-resource-map.md / resource-map.md 同款):
> - [`docs/competitors/idea-generation.md`](../../docs/competitors/idea-generation.md) = **对标判据 SSOT**(9 真同类
>   ideation skill 拆表 + 机制锚 + 超越点 + 诚实边界);"谁强在哪、我借什么"看那里。
> - [`references.md`](references.md) = **逐个工具/论文/API 的硬信息**(ResearchAgent/AI-Scientist/ScholarEval/OpenAlex
>   端点逐条研究);"某个工具/论文具体怎么做"看那里。
> - 本文件 = **研究者视角的"提 idea 该去哪找、按什么顺序、怎么接进脚本/门"导航地图**;"这一步该去哪、接哪个脚本"
>   看这里。三层互补,不复写判据/端点。
>
> **零本地库铁律**:本技能**不直连任何数据源**——撞车/gap 检索一律经上游 `literature-search` 已验证脚本(`domain_map`/
>   `cross_domain_search`/`snowball`),本技能只消费其领域地图 + 产 findings。下表是**资源地图(哪类需求去哪)+ 工作流
>   (按什么顺序)**;star/access 均 **2026-06-26 一手核**,外部可变,引用前当天核,查不到标 unknown,**绝不编**。
>
> **诚实重述(防做偏 · figure scipilot 教训)**:"沿 related-work 找 gap + 跨域类比 + 撞车前置查 + 分层"是**真实研究者 +
>   同类 skill(Galaxy-Dawn 5 型 gap / K-Dense 4 技法 / lingzhi227·ARIS 查新 / lyndonkl diverge-converge)的强共识**,
>   Light **不是"唯一想到找 gap/查撞车"**。Light 真增量 = **把这套工作流落成确定性脚本编排(provocation 机检覆盖门 +
>   candidate_dedup 防伪多样)+ 产机读 findings 被下游门消费 + 生成端不自评 novel(按 Si et al)+ 全程零 key/零本地库 +
>   离线降级**(对标见 competitors §0.C)。

---

## §A 提 idea 工作流（5 步闭环 · 可执行非口号 · 每步接脚本/门）

> 前置:输入分级已在 [SKILL「ASK 决策点」] 用 AskUserQuestion 拍板——**Level 1**(已有明确 idea→细化/差异化/可行性
> 核验)还是 **Level 2**(只有方向/数据→走完整发散漏斗)。下面是"定级后怎么提"。

**Step 1 · 定锚:吃上游领域地图,idea 从 gap 长出(不是空想)**
- 先让 `literature-search` 出领域地图:`domain_map.py "<方向>" --method "<方法轴>" --current-year 2026 --json-out dmap.json`
  ——出**研究脉络 / 方法谱系 / 未解问题**三件套 + 撞车基线 + ★年代偏斜 advisory。**idea 从地图的"未解问题层"长出来**,
  不是凭"这个方向挺火"拍脑袋(NEVER 第 4/6:不臆造"没人做过")。
- **守硬约束**:gap 必须来自**真实 related-work**(lit-search 在线取数),不直接采信记忆/SaaS 页面;查不到写 `unknown`。

**Step 2 · 找 gap(研究者提 idea 的主真实入口,系统过 5 型 gap)**
- 借 **Galaxy-Dawn research-ideation 的 5 型 gap** 系统过一遍,别只盯"性能差一点":
  **literature**(没人研究的题)/ **methodological**(现方法的局限)/ **application**(理论→实践迁移)/
  **interdisciplinary**(学科交叉口)/ **temporal**(时代变化带来的新需求)。
- 接 `provocation_gen.py --seed "<核心实体>"` 的 **gap-driven / problem-reframe / theory-gap** 三角度——机械逼出每型 gap
  的候选提问(脚手架,洞察靠你 + 地图)。
- 接 `gap_evidence_gate.py` 把"这个 gap 从哪里来"做成机读门：`SUPPORTED` gap 必须链接到 literature-search/domain-map
  来源；声称"无前作/无等价工作"必须有 query×corpus×checked_at 的 negative search；查不到写 `UNKNOWN`，不能把
  空白直觉包装成 supported gap。`checked_at` 必须已发生；source locator 不能是模板、本机私有路径、UNC/根路径或
  `../` 越界路径。
- **资源**:domain_map 未解问题层(主力)+ arXiv listing 看某方向"vitamins"(最新预印本流,趋势)+ Papers with Code SOTA
  排行看"现最好还差什么"。**Elicit/Consensus 是 gap-finding 付费 SaaS → 不依赖**(其 PRISMA/claim 聚合方法已提炼进
  lit-search 门),免费走 domain_map gap 层 + WebSearch。

**Step 3 · 跨域类比迁移(突破口的真实来源,不是"在 X 上加模块")**
- 借 **K-Dense 4 技法**(跨域类比/假设反转/尺度切换/约束增删)+ **SciMuse 冷门概念对**(低 degree/PageRank 的概念对 =
  "有趣度"信号)→ `provocation_gen` 的 **method-transfer / combination** 角度(实体两两跨域强配,答 1+1>2 机理非堆叠)。
- 接 `literature-search` 的 `cross_domain_search.py --application <你的领域> --method <要迁移的前沿技术>`(应用轴×方法轴
  **正交不拼词**)找迁移源前作。
- **资源**:arXiv 跨类目看别领域 SOTA(把别处成熟方法迁过来)+ Connected Papers 引用链看某方法的扩散边界。

**Step 4 · 撞车前置自查(提出时就查最像前作,不等 idea-critique 才发现)**
- `idea_selfcheck.py --in candidates.json --domain-map dmap.json --report findings.json`——对每候选用 `semantic_sim` 找
  **最像前作** + 沿 application_domain/purpose/mechanism/evaluation 四 facet 留槽 → 产 `light.findings.v1`(warn)。
- `candidate_dedup.py --in candidates.json` 防伪多样(批内 mean+1σ 标"疑似换皮变体对",治 Si et al 实测的多样性塌缩)。
- **守硬约束**:**撞车只产 warn 信号,novel/无创新的 critical 判决归 idea-critique**(NEVER 第 1;Si et al:LLM 不能可靠
  自评 idea)。Google/百度学术被引只当**发现入口**,命中后回 OpenAlex/Crossref 按 DOI 核(经 lit-search),不直接采信其页面。

**Step 5 · 收敛分层下注 + 交总控(入口宽 ≥15 → 出口窄 3-6)**
- `gap_evidence_gate.py --input idea-gap-evidence.json --report gap_evidence_findings.json --as-of 2026-07-05`——先确认候选从可审计 gap
  证据长出，而不是从空想长出；此门可产 `light.findings.v1` 供总控聚合。
- `idea_genealogy.py --input idea-genealogy.json --report genealogy_findings.json --as-of 2026-07-05`——再确认候选谱系、机制 delta、
  信息增益、资源账和最小判别实验闭合。Round 3 后，`VERIFIED` source evidence 必须有可交接 locator、SHA-256 和非未来
  `checked_at`；`AVAILABLE` 资源必须有 `evidence_locator + checked_at`。本机私有路径、UNC/根路径、`../` 越界、`file:` URL
  或"我应该能拿到"一律不能支撑送审。
- `card_gate.py --in idea_candidates.md`——完整性 + 反敷衍 + **★可证伪/可测量阈值 advisory**(借 K-Dense testability +
  Galaxy-Dawn falsification:「最小验证实验」「失效条件」缺可测量阈值 → warn,顶会 desk-reject 视角,不阻断)。
- `rank_ideas.py`(moonshot/solid/safe 分层 round-robin,突破口不被性价比压杀)+ `swiss_rank.py`(ELO 两两配对,压自报分,
  Si 实证 pairwise>绝对自评)。
- 交总控 `run_checkpoint.py --stage 3 --findings findings.json` 聚合 → **强制送 idea-critique(stage 4)**;被毙带根因
  回炉重发散(3⇄4 回环),**不是微调旧 idea**。

> **一句话**:同类工具帮你**生成几个 idea**;Light 帮你把"吃地图找 gap→跨域迁移→撞车前置查→分层下注"这套真实研究者
> 工作流**落成确定性脚本 + 机读 findings**,每步可复验、可喂下游、生成端不自评 novel、可离线降级。

---

## §B 资源地图（按"要什么"分 · access 诚实分级 · 引用前当天核）

### B1 · 找 gap / 趋势源（经 lit-search 取数 · 本技能不直连 · 找 idea 主力）

| 资源 | 要什么时用 | 接哪个脚本/层 | access |
|---|---|---|---|
| **OpenAlex 领域地图**(未解问题层) | 主力:从真实 related-work 的 gap 长 idea | lit-search `domain_map.py` 三件套 + 年代偏斜 advisory | ⚠ OpenAlex 2026 起称需免费 key,匿名+mailto 灰度仍 200(详 lit-search references) |
| **arXiv listing / 某方向 vitamins** | 看某方向最新预印本流(趋势/新方法) | lit-search `arxiv_search`(近三年前沿层) | ✓ 真免 key(须 https,间隔≥3s) |
| **Papers with Code SOTA** | 看"现最好还差什么"=方法 gap | 当 SOTA 线索,回学术源核 | ✓ 免费(无稳定 API,当线索) |
| **Connected Papers 引用链** | 看某方法的扩散边界/还没迁到哪 | 文献耦合从 OpenAlex `referenced_works` 零额外 API 算(lit-search) | ✓ 免费看(每月限额);⚠ 无 API,不依赖其站 |
| **cross_domain_search(应用×方法轴)** | 跨域把别处前沿迁过来 | lit-search `cross_domain_search.py` 正交不拼词 | ✓ 经 lit-search 免 key 源 |

### B2 · gap-finding / novelty SaaS（看思路 · 受限/付费**不依赖**;方法已提炼进门）

| 资源 | 是什么 | 本技能怎么拿到等价信号 | access |
|---|---|---|---|
| **Elicit** | PRISMA 可审计筛选 + 找 gap | 其筛选方法已进 lit-search `prisma_flow`;gap 走 domain_map 未解问题层 | ⚠ 付费 SaaS → 不依赖,诚实标 unavailable |
| **Consensus** | claim 级证据方向聚合(support/oppose) | 借"已定论 vs 争议"作 gap 信号;不做 claim 共识表 | ⚠ 付费 → 不依赖 |
| **undermind / scite** | 多轮 triage 召回估计 / 引用情感 | 召回估计→覆盖度 caveat;争议识别→theory-gap 角度 | ⚠ 付费 → 不依赖 |
| **Connected Papers / ResearchRabbit** | 力导向图共被引+文献耦合 | OpenAlex `referenced_works` 零额外 API 算(经 lit-search) | ✓ 免费(ResearchRabbit 需登录)→ 不依赖其站 |

### B3 · 跨域类比 / 院士思维素材（看趋势 · 免费为主）

| 资源 | 为何用 | 诚实做法 |
|---|---|---|
| **arXiv 跨类目 listing** | 跨域把别领域 SOTA 方法迁过来(method-transfer) | 经 lit-search `arxiv_search`/`cross_domain_search`,元数据级 |
| **Hugging Face / Papers with Code trending** | 看哪些方法正起飞(技术外推算子) | 当趋势线索,关键结论回学术源核 |
| **Google / 百度学术** | 仅当**发现入口**找最像前作 | **无官方 API + 反爬**;命中后回 OpenAlex/Crossref 按 DOI 核再入撞车表,不直接采信被引(NEVER 第 6) |

---

## §C 守硬约束三原则（把"真实工作流"落地的判据）

1. **idea 从真实 gap 长出,不臆造"没人做过"**:每个候选的"前人没做"主张必须有**阴性证据**(检索了哪些关键词×哪些库
   ×均无命中,经 lit-search 在线取数),不凭记忆/SaaS 页面拍板;查不到写 `unknown`,**宁缺毋造**(NEVER 第 1/6)。
   阴性检索与来源核验日期不得来自未来；locator 必须可公开交接，不能指向作者本机私有路径或模板占位。
2. **撞车只产信号,novel 判决归 idea-critique**(Si et al 实证 LLM 不能可靠自评 idea):生成端只给"最像前作 + facet 待拆
   delta"warn,**绝不在生成端下 novel/无创新的 critical 判决**(那是 stage 4 的一票否决门)。这是 Light 与 lingzhi227/
   AI-Scientist/ARIS(生成端自判 novel)的真分水岭——诚实标"是设计选择,不是独创"。
3. **付费/登录站诚实标 unavailable,转免费骨架 + WebSearch**:Elicit/Consensus/undermind/ResearchRabbit/Scholar 任一
   受限 → **不假装拿到了料**,其方法论已提炼进 lit-search 门 + 本技能 provocation 算子;免费走 domain_map gap 层 +
   cross_domain_search + WebSearch 摘要。**全程零 MCP、零付费、零强制注册、零本地库**(守硬约束)。

---

## 取数端点 + 当天复核（零本地库——本技能经 lit-search,可达性当天核,标 last_checked）

```bash
# 本技能不直连数据源:撞车/gap 检索经 lit-search 脚本(端点真相源见 lit-search references.md)。
# 同类 ideation skill star 当天核(对标判据更新时复核):
gh api repos/lingzhi227/agent-research-skills --jq .stargazers_count   # 同名 idea-generation + novelty_check.py
gh api repos/wanshuiyin/auto-claude-code-research-in-sleep --jq .stargazers_count  # ARIS idea-creator/novelty-check
gh api repos/K-Dense-AI/scientific-agent-skills --jq .stargazers_count  # scientific-brainstorming + hypothesis-generation
gh api repos/Galaxy-Dawn/claude-scholar --jq .stargazers_count          # research-ideation(5 型 gap/falsification)
```

- 对标判据 SSOT:[`docs/competitors/idea-generation.md`](../../docs/competitors/idea-generation.md)(本文件不复写,只给指针)
- 工具/论文/端点 SSOT:[`references.md`](references.md) + 撞车端点经 lit-search references(本技能零本地库,不直连)
- 受限(不依赖):Elicit/Consensus/undermind/scite(付费)· ResearchRabbit(登录)· Google/百度学术(无 API)→ 诚实标 unavailable

> **唯一真相源声明**:对标判据 SSOT = `competitors/idea-generation.md`;工具/端点 SSOT = `references.md`(+ lit-search
> references 撞车端点);本文件是三者的**研究者视角"提 idea 工作流"落地导航**。access/star 随时间变,引用前当天复检;
> 查不到标 unknown,绝不编。
