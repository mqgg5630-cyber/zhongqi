# 投稿前引用体检清单

配合 `citation_registry.py`、`verify_refs.py`、`citation_verify_gate.py`、
`citekey_audit.py` 与 `references/locator_audit.md` 使用。

## Inventory 与 provenance

- [ ] paper claim map、文稿、表图说明、补充材料、refs spec 中的引用都进 inventory。
- [ ] 每个 occurrence 保留 path/locator/claim_id/citekey/raw identifier。
- [ ] DOI/arXiv/PMID/ISBN/URL 已规范化；预印本/正式版等版本没有静默压平。

## 真实性与元数据

- [ ] 每个进入 `.bib` 的 work 都是 `CONFIRMED`：注册源 + 第二独立字段源。
- [ ] 没有 `CONFIRMED-MISSING` 或 chimeric work。
- [ ] `UNAVAILABLE/UNRESOLVED` 已重试或明确留失败件，没有冒充通过。
- [ ] title/authors/year/venue/identifier 的逐源值仍在 `source_evidence`。
- [ ] `field_conflicts` 已人工裁决；没有 fuzzy 自动覆盖原引用。
- [ ] DataCite DOI 没因 Crossref 404 被误判不存在。

## Claim↔citation

- [ ] 每条核心 claim 有精确 claim locator 与 source locator。
- [ ] `SUPPORTS` 由原文复核得出，不是 metadata hit 或摘要关键词相似。
- [ ] `claim_text_sha256` 与 `reviewed_claim_sha256` 一致；正文 claim 改写后已重做引用支持复核。
- [ ] `PARTIAL` 已收窄 claim 或补源。
- [ ] `RELATED_ONLY`/`UNSUPPORTED` 已换引用、改 claim 或删除。
- [ ] A→B 引用边只用来证明引用关系，不冒充 B 支持当前命题。

## 出版后更新

- [ ] 受影响原文读 Crossref `updated-by`；通知反向 `update-to` 未被误判。
- [ ] retraction/correction/expression-of-concern 的 notice DOI、类型、来源、方向已留痕。
- [ ] publication update 事实已交 research-ethics 终判与定措辞。

## 格式与交付

- [ ] registry 是 SSOT；BibTeX/CSL 是从 confirmed work 派生。
- [ ] `\cite`/Pandoc keys 与 `references.bib` 无缺失/重复。
- [ ] venue 样式、条目类型、姓名、日期、页码和 DOI 已人工抽查。
- [ ] citation gate exit 0；stage-10 checkpoint `delivered`。
- [ ] typesetting 已真实消费 `references.bib` 与 citekey audit。
