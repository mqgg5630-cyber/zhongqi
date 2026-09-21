# 量化诚信门（Integrity Gate）

把"诚实第一"从口号变成可执行配额。两道门：**初稿门**（写作中持续抽样）、**终稿门**（提交前全量）。
对接 `self_review_checklist.md` 的 M2/M3，对接 `[MATERIAL GAP]` / `[RESULT GAP]` 标记，
机检入口 `scripts/draft_lint.py`（GAP/声明）+ `scripts/claim_evidence_gate.py`（claim 无证据/过度宣称）。

> **职责分工**：本诚信门管 **claim ↔ 证据**（paper-writing 写作自检）。**引用真实性核验**（DOI/题录存在性、
> 字段一致、CNKI 无 DOI 中文条目比对）是 **citation 阶段（stage 10）** 的硬门——本门只登记"该引用核了没"，
> 不重造 citation 的核验协议。措辞超档的**交付红线**在 research-ethics（横切复核），本门是写作时自检。

---

## 1. Claim 核查抽样配额

把正文中的**事实性 claim**（任何"是/有/达到/优于/导致"的可证伪陈述）登记到
`templates/claim_argument_plan.json`（canonical 机读契约）；`claim_passport.md` 可作人读视图。

| 阶段 | 抽样比例 | 下限 | 范围 |
|---|---|---|---|
| 初稿（写作中） | **≥30%** | 至少 10 条（少于 10 条则全查） | 全文事实性 claim 随机抽样，优先抽数字类与引用类 |
| 终稿（提交前） | **100%** | 全部 | 每条 claim + 每条引用都过一遍 |

抽样不是放过其余 70%——是分摊到各模块滚动抽，终稿必须收口到 100%。
高危类**不抽样、永远全查**：所有带数字的结果句、所有他人方法的性能数字、所有"first/SOTA/outperform/显著优于"措辞。

---

## 2. 每条 claim 的核查动作清单（逐条勾）

对抽中的每条 claim：

- [ ] **分类**：是 ① 本文实验结果 / ② 引用的他人结论 / ③ 公认背景 / ④ 推断？
- [ ] **①实验结果** → 指向实际运行产物（日志/表格/脚本）？有 std/CI？**在 result-analysis 的 `evidence_strength.json` 里有对应证据档**？单次结果不得写成定论。否则改 `[RESULT GAP]`。
- [ ] **②引用结论** → 登记到 claim 台账，标"待 citation 核"；citation 阶段做存在性 + 字段一致 + 支撑关系核验。
- [ ] **③背景** → 是否真"公认"？存疑则补 1 条可核引用，否则降级措辞。
- [ ] **④推断** → 是否被标为推断（"we hypothesize/suggest/可能"）而非事实？硬写成事实即触发改写。
- [ ] **措辞↔证据**：该 claim 的措辞强度是否不超过它的证据档（`claim_evidence_gate` 机检）？超档→降级或补证据。
- [ ] **溯源状态登记**：已验证 / 待核 / GAP（写进 claim_passport）。

---

## 3. claim 无证据 = 诚信门 critical（机检 + 回炉）

`claim_evidence_gate.py` 把"每个 claim 都有证据吗"落成机读门（producer=paper-writing）：

- **claim 无证据（诚信门）= critical**：草稿做强断言（SOTA/demonstrate/证明/显著优于…），但该句未登记、未绑定自己的
  `evidence_claim_ids`、绑定 ID 不存在或只绑定 `none` → 阻断 → `run_checkpoint --stage 8` exit 1。另一条 strong evidence 不得兜底。
- **回炉**：`reroute --stage 8` 建议 **8→7**（回 result-analysis 补/强化证据）；若该结论**实验根本没产出** → 改 **8→6**（回 experiment-coding 补实验）。**停下问用户**后 `passport add-back-edge` 落账。
- **过度宣称（warn）**：有证据档但措辞强于该档 → 软化提示（交付前 research-ethics 硬门复核）。

> 机检有边界：canonical 门以当前 `draft_sha256` + 精确 `text` span + evidence claim ID 校验绑定；旧稿 claim map 会 fail closed，但过宽 span、同义改写和 claim 边界仍会失真。
> 它仍只抓"强断言无证据档 / 措辞超档"的形态；**逻辑、创新与论证终判仍需人/审稿人**。

---

## 4. 过门判据

- **初稿门**：抽样覆盖率达标 + 抽中 claim 无 M2/M3 未处理项 + 所有未核内容都已标 GAP + `claim_evidence_gate` 无 claim-无证据 critical（或已记回炉）。
- **终稿门**：100% claim 已分类核查 + 每条数值 claim 在 `evidence_strength.json` 有证据档且措辞不超档 + 0 个遗留 `[MATERIAL GAP]`/`[RESULT GAP]` + 引用已交 citation 阶段核（无遗留"待核"）+ 必备声明齐全（见 `mandatory_inclusions.md`）。
- 任一不达标 → 不得标记"可提交"。机检用 `draft_lint.py`（GAP/声明）+ `claim_evidence_gate.py`（claim↔证据），**人判覆盖机检**。
