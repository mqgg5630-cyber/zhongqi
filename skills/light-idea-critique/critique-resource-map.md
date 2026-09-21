# 审 idea：真实审稿人工作流 + 资源地图（真实用户视角 · Round 2 R2）

> **真实顶会审稿人 / 资深研究者审一个 idea 不是"打个分鼓励一下"**——是**复盘 target → 多视角找非重叠致命缺陷 →
> 带检索证据查撞车 → 反谄媚 + 拒稿预演两面对抗 → 一票否决裁决**的工作流：先复述这 idea 解决的"新问题"和用的背景，
> 再以五视角(对标/可行/新颖/工程/统计) + Devil's Advocate 挑非重叠 fatal flaw，每个"撞车/不新"主张都回检索证据核，
> 反复反驳时不被顺从放行，最后以目标会审稿人身份预演 top-3 拒稿理由。本文件把这套**真实审稿工作方式内化进本技能**：
> 每一步**接进本技能既有脚本/门的闭环**，不是方法论罗列。
>
> **与既有文件不重叠声明**(范本 search-resource-map.md / idea-resource-map.md 同款)：
> - [`docs/competitors/idea-critique.md`](../../docs/competitors/idea-critique.md) = **对标判据 SSOT**(13 真同类
>   审稿/评审/查新 skill 拆表 + 机制锚 + 超越点 + 诚实边界)；"谁强在哪、我借什么"看那里。
> - [`references.md`](references.md) + [`references/{rubric,protocol,contract}.md`](references/) = **逐个工具/API/rubric
>   的硬信息**(NeurIPS 评审表字段 / OpenReview API 端点 / S2 检索 / 八维 rubric / 反谄媚协议)；"某项具体怎么调/打几分"
>   看那里。
> - 本文件 = **审稿人视角的"审 idea 该去哪取证、按什么顺序、怎么接进脚本/门"导航地图**；"这一步该去哪、接哪个脚本"
>   看这里。三层互补，不复写判据/端点/rubric。
>
> **零本地库铁律**：本技能**不直连任何数据源**——撞车/查新检索一律经上游 `literature-search` 已验证脚本
> (`domain_map`/`snowball`/`cross_domain_search`)，本技能只消费其结果 + 产 critical findings。下表是**资源地图
> (哪类需求去哪)+ 工作流(按什么顺序)**；star/access 均 **2026-06-27 一手核**，外部可变，引用前当天核，查不到标
> unknown，**绝不编**。
>
> **诚实重述(防做偏 · figure scipilot 教训)**：多视角对抗审稿、Devil's Advocate 挑刺、撞车带证据、反谄媚、拒稿预演——
> 是**真实审稿人 + 同类 skill(paperjury 两面庭审 / imbad0202 5-role / K-Dense council / ARIS cross-model 查新)的强
> 共识**，Light **不是"唯一想到严审"**。Light 真增量 = **把这套工作流落成确定性否决闸门(一票否决/反谄媚 concession-rate
> /密度先验机检化) + 产机读 critical findings 被总控确定性阻断 + 跨技能反哺(top-3 喂 paper-writing/review-rebuttal) +
> 全程零 key/零 MCP**(对标见 competitors §0.C/§2；K-Dense 需 OPENROUTER_API_KEY、ARIS 需 Codex MCP+OpenAI key)。

---

## §A 审 idea 工作流（五步闭环 · 可执行非口号 · 每步接脚本/门）

> 前置：严线松紧 / 批量送审范围已在 [SKILL「ASK 决策点」] 用 AskUserQuestion 拍板。下面是"定了严线后怎么审"。
> （借 paperjury 洞察：AskUserQuestion **只在 loop 前有效、loop 内是死的** → 决策点都摆在严审开跑前。）

**Step 1 · 复盘 claim + target（不是先打分；借 GraphMind/paperjury 两遍穿透）**
- 先用自己的话复述这 idea **解决的"新问题"(target)** + **用什么领域/数据(background)**，再列候选 fatal flaw——
  顺序是 paperjury "fatal-flaw 诊断 → forensic interrogation"、imbad0202 Sprint Contract "看正文前先承诺
  failure_conditions"的纪律：**先立标准再看内容，别被作者叙事带跑**。
- 接：填 `critique_input.json` 的 `most_similar[].{target_equivalent, stance}` facet 决策(吃 gen `idea_selfcheck`
  留空的槽)。**守硬约束**：撞车判定必须 **target/background 可追溯分解**，只共享 background ≠ 撞车(NEVER#2)。

**Step 2 · 五视角对抗严审（找非重叠 fatal flaw；借 imbad0202 5-role / K-Dense council）**
- 以**非重叠**五视角 + Devil's Advocate 各挑最脆弱点：对标派(撞车/新颖)、可行派、新颖派、工程派、统计派——
  "选会产生建设性冲突的视角，一致没价值"(K-Dense consciousness-council)；Devil's Advocate 专找 Foundation
  Collapse / Logic Chain Break(相关≠因果) / Evidence Gaps / Stronger Counter-Narrative(imbad0202 四类 CRITICAL)。
- 接 `score_aggregate.py` 八维加权 + **确定性否决闸门**。**守硬约束**：**一票否决**——一个 fatal flaw 不被其他高维度
  平均救回(NEVER#1；scholar-evaluation 纯打分能被高均值救回=放水，Light 否决项优先于加权分)。

**Step 3 · 撞车/查新带证据复核（≥2 库、target 层、非"感觉像"；经 lit-search 取数）**
- 经上游 `literature-search`：`domain_map.py`/`snowball.py` 取**最像前作** + DOI/HTTP 码留痕；`fatal_flaw_gate.py`
  **直接消费 `_shared/semantic_sim`** 复核 idea↔最像前作(不只信 gen 自报)→ `novelty_audit.py` 四阶段查新留痕 +
  target/background 分解；`novelty_density.py` 给 LLM 自评之外的独立密度新颖先验(抓"嘴上高创新但扎密集簇")。
- **守硬约束**：判"新"必有**检索证否留痕(≥2 库、HTTP 码、最像前作)**，无证据的 novelty 一律封顶标 evidence-missing
  (NEVER#2/#7；obra verification-before-completion 同款"无新鲜证据不下断言"铁律)。查新 run 的 `retrieved_at`
  必须已发生，run/collision/judge/human/Pareto/fatal/decision locator 必须是真实公开定位符；human/Pareto/fatal/decision
  evidence 必须带 SHA-256（human 还要非未来 captured_at），模板占位、本机绝对路径或 `../` 越界路径不能冒充证据。
  **绝不编造前作/DOI 压新 idea，也不让专家判断/最终 GO 的证据事后漂移。**

**Step 4 · 反谄媚 + 拒稿预演两面对抗（★Round 2 借 paperjury two-sided trial）**
- 有作者反驳应答 → `sycophancy_guard.py` 算 concession-rate：**让步必须挂新证据否则强制降 3、禁连续无证据让步**
  (对抗 OpenReviewer 实证的通用 LLM 谄媚)。
- ★以目标会审稿人身份列 **top-3 拒稿理由**，逐条预演作者反驳能否站住 → `critique_self_audit.py` 的 `rehearsal_audit`
  检**预演完整性**(top-3 是否齐 / 每条 `rebuttable` 填没填 / 预演不出反驳的拒稿点是否浮出)，**warn-only advisory**
  (借 paperjury 每个 issue 经两面庭审才能 close 的纪律)。**守硬约束**：预演不出有效反驳的拒稿点 = 未化解，停下走
  Step 5 回炉决策，**不当通过**(NEVER#4；advisory 只提示完整性，不替你判反驳是否有效)。

**Step 5 · 一票否决裁决 + 回炉决策（不替用户拍）**
- `fatal_flaw_gate.py` 把撞车(critical)+无创新(critical)+反谄媚(warn)编排成 `light.findings.v1` → 总控
  `run_checkpoint.py --stage 4` 聚合(**critical fail → exit 1 确定性阻断**)→ `reroute.py` 建议回边 **4→3**
  带"**具体缺口 + 最像前作**"(对齐 paperjury ledger 的 `close_criterion`)。
- `critique_self_audit.build_critique_corpus` 把 top-3 拒稿理由下沉喂 **paper-writing**(正文预反驳)/**review-rebuttal**
  (拼 rebuttal 底稿)。**守硬约束**：critical fail 的 idea **停下用 ASK 问用户**回炉/带病推进/转已知局限——押数月方向，
  **不替用户拍**(决策点，非自作主张回炉/放行)。

> **一句话**：同类工具帮你**扮审稿人挑刺打分**；Light 帮你把"复盘 target→五视角找致命缺陷→带证据查撞车→反谄媚+拒稿
> 预演→一票否决回炉"这套真实审稿工作流**落成确定性否决闸门 + 机读 critical findings**，每步可复验、可确定性阻断、
> 可喂下游、可离线降级。

---

## §B 资源地图（按"要什么"分 · access 诚实分级 · 引用前当天核）

### B1 · 审稿真相源 / rubric 锚（免费 · 严审标准与真实审稿范例的根）

| 资源 | 要什么时用 | 接哪个脚本/层 | access |
|---|---|---|---|
| **NeurIPS / ICLR Reviewer Guidelines + 评审表** | 八维 rubric 锚到顶会官方维度(Originality/Quality/Clarity/Significance + Soundness/Presentation/Contribution + Overall 1-10)，不自创 | `references/rubric.md` + `score_aggregate` 八维 | ✓ 免费公开(neurips.cc/iclr.cc Reviewer Guidelines) |
| **OpenReview API**(api2.openreview.net) | 拉**真实顶会 review/rebuttal/meta-review 范例**：审稿人真怎么挑刺、rebuttal 怎么应对、anchoring 长什么样 | `references.md` §2 端点；校准刻薄度 + `build_critique_corpus` 的 reviewer_corpus_refs | ✓ 免 key 拉已 release 的公开评审(`openreview-py`，venue/invitation 每年变) |
| **顶会公开 proceedings Review.html** | 看真实 review 行文结构(Summary→Strengths→Weaknesses→Relation to Prior Work→评分→post-rebuttal) | `references/protocol.md` 严审 Step 行文 | ✓ 免费(proceedings.neurips.cc) |

### B2 · 撞车/查新取数（经 lit-search · 本技能不直连 · 判"撞车/新"的证据底）

| 资源 | 要什么时用 | 接哪个脚本/层 | access |
|---|---|---|---|
| **OpenAlex 领域地图 / 引用链** | 取最像前作 + target 层撞车证据 + 被引/referenced_works | lit-search `domain_map`/`snowball` → 本技能 `novelty_audit` | ⚠ OpenAlex 2026 起称需免费 key，匿名+mailto 灰度仍 200(详 lit-search references) |
| **Crossref / arXiv / Europe PMC** | DOI 去重真相源 + 近三年前沿 + 生医免 key | lit-search 免 key 骨架 → 本技能复核 | ✓ 真免 key(arXiv 须 https、间隔≥3s) |
| **Semantic Scholar(S2AG)** | SPECTER2 嵌入 + influentialCitationCount，强化撞车复核 | lit-search `snowball`；嵌入档可注入 `_shared/semantic_sim` 强化 | ✓ 匿名可用(限速严 429)；免费 key 提配额 |
| **Connected Papers** | 看某方法扩散边界/最像前作的引用邻域 | OpenAlex `referenced_works` 零额外 API 算(经 lit-search) | ✓ 免费看(每月限额)；⚠ 无 API，不依赖其站 |

### B3 · 审稿 SaaS / 同类 skill（看思路 · 受限/付费**不依赖**；方法已提炼进门）

| 资源 | 是什么 | 本技能怎么拿到等价信号 | access |
|---|---|---|---|
| **paperjury / imbad0202 academic-paper-reviewer / K-Dense peer-review** | 同类审稿 skill(courtroom / 5-role / checklist) | 其多视角/Devil's Advocate/两面庭审/报告规范**方法已提炼进** score_aggregate/fatal_flaw_gate/critique_self_audit(对标见 competitors §0.A) | ✓ 开源可读(K-Dense peer-review **需 OPENROUTER_API_KEY**→不依赖其 LLM 步骤) |
| **ARIS novelty-check** | cross-model(gpt-5.5 via Codex MCP)查新下 binary novel | 借 claim 抽取 + multi-source 思路；**不要异模型/不在生成端下 binary**(Si et al)→归 critique 端可计算闸门 | ⚠ 需 Codex MCP + OpenAI key→**违硬约束不依赖** |
| **Elicit / scite / Consensus / Paperpal** | 付费 SaaS(可审计筛选 / 引用情感 / claim 共识 / 投前审稿) | PRISMA 筛选/争议识别方法已进 lit-search 门；引用情感(scite)本技能只 count-based 提请人工 | ⚠ 付费→不依赖，诚实标 unavailable，走免费骨架 + WebSearch |
| **poldrack/ai-peer-review** | 真·多模型去标识 meta-review | 借"去标识 + 共识/个别分离"思路；我单模型扮多视角(伪多样，诚实落后项#2) | ✓ 开源可读；要多家 API key→不依赖 |

---

## §C 守硬约束三原则（把"真实审稿工作流"落地的判据）

1. **撞车/新颖靠证据不靠"感觉"**：判"撞车"必须 **target/background 可追溯分解**(只共享背景不算撞车)；判"新"必须有
   **检索证否留痕**(≥2 库、HTTP 码、最像前作)，无证据的 novelty 封顶 evidence-missing。撞车/新颖是 **AI 易错判断**——
   拿不准就**降级"建议核实"问用户**，不自下定论(NEVER#2)。检索统一交 lit-search，**不手拼 API URL**；查不到写
   `unknown`，**宁缺毋造**——既不编"不存在的前作"压新 idea，也不假装"查全了没撞车"放行(NEVER#7)。
2. **可计算闸门是先验非真值，judge 不裸自评**：八维权重/pass_line/否决线是**经验默认、可调超参**(非标注集反推，Light
   无公开标注集)；新颖性终判靠 semantic_sim(离线档跨语言弱)+ 检索 + 人/宿主(Si et al 实证 LLM 自评 idea 弱)。审稿人
   质疑阈值 → 诚实答"经验值，可调，跑 weight_sensitivity 看稳健"(NEVER#6)。**反谄媚阈值留脚本不暴露给作者**(防针对刷)。
3. **付费/登录站诚实标 unavailable，全程零 key/零 MCP**：Elicit/scite/Consensus/Paperpal/ARIS Codex MCP/K-Dense
   OPENROUTER 任一受限 → **不假装拿到了料**，其方法论已提炼进本技能门 + lit-search 门；撞车/查新走免费骨架(OpenAlex
   灰度 + Crossref/arXiv/Europe PMC)+ WebSearch 摘要。**零 MCP、零付费、零强制注册、零本地库**(守硬约束)。

---

## 取数端点 + 当天复核（零本地库——本技能经 lit-search，可达性当天核，标 last_checked）

```bash
# 本技能不直连数据源：撞车/查新检索经 lit-search 脚本(端点真相源见 lit-search references.md)。
# 同类审稿/查新 skill star 当天核(对标判据更新时复核)：
gh api repos/u7079256/paperjury --jq .stargazers_count                       # paperjury(courtroom 审稿引擎)
gh api repos/imbad0202/academic-research-skills --jq .stargazers_count        # academic-paper-reviewer 5-role
gh api repos/K-Dense-AI/scientific-agent-skills --jq .stargazers_count        # peer-review/scholar-evaluation/council
gh api repos/wanshuiyin/auto-claude-code-research-in-sleep --jq .stargazers_count  # ARIS novelty-check(cross-model)
# 审稿真相源连通性(引用前核，绝不信内嵌快照)：
curl -sI "https://api2.openreview.net/notes?limit=1" | head -1               # OpenReview API 2
```

- 对标判据 SSOT：[`docs/competitors/idea-critique.md`](../../docs/competitors/idea-critique.md)(本文件不复写，只给指针)
- 工具/API/rubric SSOT：[`references.md`](references.md)(NeurIPS 评审表 / OpenReview API / S2)+ [`references/{rubric,protocol,contract}.md`](references/)
- 撞车/查新端点：经 lit-search `references.md`(本技能零本地库，不直连)
- 受限(不依赖)：Elicit/scite/Consensus/Paperpal(付费)· ARIS Codex MCP / K-Dense OPENROUTER(需 key)· Google/百度学术(无 API)→ 诚实标 unavailable

> **唯一真相源声明**：对标判据 SSOT = `competitors/idea-critique.md`；工具/API/rubric SSOT = `references.md` +
> `references/`；本文件是它们的**审稿人视角"审 idea 工作流"落地导航**。access/star 随时间变，引用前当天复检；
> 查不到标 unknown，绝不编。
