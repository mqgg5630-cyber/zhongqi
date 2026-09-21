# Citation 真实作者资源地图

这不是网址清单，而是从作者材料到 stage-10 交付物的可执行闭环。
`docs/competitors/citation.md` 记录 R1 同类与机制证据；`SKILL.md` 给执行
指令和红线；本页决定先读什么、跑什么、产什么；`references/*` 解释
schema 与人工复核；`templates/*` 约束输入；`scripts/*` 执行。

## 八步闭环

### 1. 建 inventory，保留作者 provenance

输入 paper-writing 的 `light.paper_claims.v1`、稿件、表图说明、补充材料和
参考文献清单。运行：

```bash
python scripts/citation_registry.py \
  --claim-map claim_plan.json --draft paper.tex \
  --figure figures/notes.md --supplement supplement.md \
  --refs-spec citation_input.json --out-dir citation-delivery
```

每个 inventory row 保留 `source_kind/path/locator/claim_id/claim_locator/
claim_text/claim_text_sha256/citekey/identifier/captured_at`。paper-writing 的
`citation_candidates` 只是候选，不能直接变成“已核”。

### 2. 规范标识符并聚合版本

规范 DOI、arXiv、PMID、ISBN、URL；citekey 只作项目内别名。相同 DOI
去重；同一 row 同时给 DOI+arXiv 时，在一个 work 下保留两个版本标识，
不把预印本和正式版静默压成一条。无法证明同一 work 时保持分开。

### 3. 多源字段核验

```bash
python scripts/verify_refs.py --spec citation_input.json --out verify.json
```

注册源（Crossref 或 DataCite）提供 canonical 字段；PubMed、Semantic
Scholar 或带免费 key 的 OpenAlex提供第二独立字段源。逐源保留
title/authors/year/venue/identifier、endpoint、HTTP、时间与 outcome。
字段冲突只报警，不用 fuzzy match 覆盖原引用。

### 4. 走诚实四态

- `CONFIRMED`：注册源 + 第二独立字段源；
- `CONFIRMED-MISSING`：DOI RA 明确不存在且 Crossref/DataCite 都 404；
- `UNAVAILABLE`：超时、429、5xx、认证/资源不可用；
- `UNRESOLVED`：部分查到或第二源未完成。

只有 `CONFIRMED-MISSING` 与嵌合引用进入 citation critical。网络失败、
安全限制和索引覆盖不足不冒充“查无此文”。

### 5. 查嵌合与出版后更新

把原引用 title/authors/year 与注册源逐字段比；多核心字段冲突或“标题
对、凭空新增作者”标 chimeric。Crossref 对被更新原文读 `updated-by`；
通知的 `update-to` 是反向指回原文，不能把通知判成被撤。citation 只记
通知 DOI、类型、关系方向和来源；诚信终判/措辞交 research-ethics。

### 6. 做 claim↔citation 语义复核

元数据命中不证明命题。按 `references/locator_audit.md` 和
`templates/claim_citation_review.json` 记录 source locator、excerpt、
`reviewed_claim_sha256`、方向、范围、群体、指标及 verdict。当前
`claim_text_sha256` 与 `reviewed_claim_sha256` 不一致时，说明 citation
support 审查绑定的是旧 claim，必须重审。`related_only` 必须报警：主题相近但
不能支持 claim 时，改 claim、换引用或删引用。

### 7. 生成 canonical 交付物

`citation_registry.py --online` 生成 registry、BibTeX、CSL JSON、逐源
evidence、失败件、claim review 与 citekey audit。只有
`CONFIRMED` 且非 chimeric 的 work 进入 `.bib`/CSL；失败项不静默掉。

### 8. stage 10 与 typesetting

```bash
python scripts/citation_verify_gate.py \
  --registry citation-delivery/citation-registry.json \
  --tex paper.tex --bib citation-delivery/references.bib \
  --report citation_findings.json
python ../light-orchestrator/scripts/run_checkpoint.py \
  --file .light/passport.yaml --stage 10 \
  --findings citation_findings.json --write --ts <ISO-8601>
```

critical 在 stage 10 内修；`ROUTES` 没有 key 10，不造 back-edge。通过后
把 `delivery.json`、`references.bib`、`citekey-audit.json` 交
typesetting；typesetting 真实消费 citekey/BibTeX 并负责编译，不重验
文献真伪。

## 资源分层

| 层级 | 资源 | 用法与不可用处理 |
|---|---|---|
| 本地免费 | 本技能 scripts/templates/references、稿件、claim map、PDF | 核心路径；无网络仍可建 inventory，但状态是 UNRESOLVED |
| 免费公开/免 key | DOI RA、Crossref、DataCite、PubMed E-utilities、DOI 内容协商、OpenCitations | 核心在线路径；429/5xx → UNAVAILABLE |
| 免费登录/key | OpenAlex、Semantic Scholar key（匿名通道可能限流） | 只增强覆盖；没 key 明记 UNAVAILABLE，不阻断本地流程 |
| 机构受限 | Web of Science、Scopus、机构订阅全文 | 可人工补证；不可假装已查 |
| 付费闭源 | EndNote、Paperpile、商业核验/插件 | 可选互导；绝不作为核心完成条件 |

## 分工

- literature-search 提供检索 provenance/候选；citation 重新核作者最终采用项。
- paper-writing 提供 per-claim map/source locator 与 citation candidate。
- research-ethics 接 publication update 事实，终判撤稿/更正/EoC 的诚信处理。
- typesetting 消费 `.bib`/citekey audit，负责真实编译。
- orchestrator 只按 `STAGE_GATES[10]=[citation_verify]` 聚合；`ROUTES`
  无 10，citation 不伪造出边。
