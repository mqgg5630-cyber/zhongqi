# Patent disclosure resource map

Last checked: 2026-07-05. Dynamic legal and filing facts must be rechecked
against official sources on the day of use.

## Peer skills and what Light borrowed

| Source | Observed signal | Useful mechanism | Light boundary |
|---|---:|---|---|
| [`handsomestWei/patent-disclosure-skill`](https://github.com/handsomestWei/patent-disclosure-skill) | ~3.5k stars, MIT, HEAD `c4b843e2037376ce65a63f8db09b0cf635002b8f` | Project scan, patent-point mining, CNIPA-first prior-art notes, editable disclosure drafts, Mermaid figures, self-check and iteration log | Do not require Playwright/Node/Mermaid CLI as baseline; do not imply automated CNIPA search always succeeds; add Light hash/evidence gate |
| [`trilogy-group/cc-skill-patent-disclosure`](https://github.com/trilogy-group/cc-skill-patent-disclosure) | Low-star but strong workflow, HEAD `b109a13d295abed32296fb8fa3eed9c9038c9d10` | Candidate triage, user interview, sectioned disclosure, multi-angle QC | Excluded Google Docs/OAuth/gogcli publishing path; Light remains local and zero-key |
| [`RobThePCGuy/Claude-Patent-Creator`](https://github.com/RobThePCGuy/Claude-Patent-Creator) | ~148 stars, MIT, HEAD `afee446` | Phase model: discovery, claims, specification, diagrams, abstract/front matter, compliance | Its MCP/BigQuery/EPO/USPTO API stack is not portable here; Light must not say “USPTO-ready” unless formal current requirements and professional review are actually satisfied |
| [`jaccen/AI-Copyright-Skill`](https://github.com/jaccen/AI-Copyright-Skill) | Adjacent combined patent/soft-copyright skill, HEAD `20908b7` | Combined IP material framing and patent-prior-art prompts | Treat as adjacent inspiration; avoid copying AI-specialized assumptions into general research/software projects |

Deep read record: [`../../../docs/learning/ip/patent-deep-read-report.md`](../../../docs/learning/ip/patent-deep-read-report.md).

## Official and high-trust anchors

- CNIPA `专利申请受理和审批办事指南`:
  <https://www.cnipa.gov.cn/attach/0/0caf8492459846d98f3859ab05225df7.pdf>.
  It anchors core China application materials: request, claims, description,
  abstract and drawings when necessary for invention; utility model includes
  drawings; written/electronic routes and formal document constraints.
- CNIPA Q&A `专利申请书`:
  <https://www.cnipa.gov.cn/jact/front/mailpubdetail.do?sysid=6&transactId=446578>.
  Use only as quick material-list confirmation; prefer the current official
  guide for detailed requirements.
- WIPO Patent Drafting Manual, second edition, 2023:
  <https://www.wipo.int/publications/en/details.jsp?id=4706>.
  Use as drafting craft: claims and description must support each other; include
  variants/embodiments early because later narrowing needs support.
- USPTO nonprovisional utility guide:
  <https://www.uspto.gov/patents/basics/apply/utility-patent>.
  Use only for US route awareness; it requires current English/application
  materials and DOCX surcharge rules that change over time.
- USPTO provisional guide:
  <https://www.uspto.gov/patents/basics/apply/provisional-application>.
  Use only for US provisional awareness; provisional applications are not
  examined and do not need formal claims, oath/declaration or IDS.
- USPTO MPEP 2163 / 2164:
  <https://www.uspto.gov/web/offices/pac/mpep/s2163.html> and
  <https://www.uspto.gov/web/offices/pac/mpep/s2164.html>.
  Use for written-description and enablement awareness; Light records support
  and implementation evidence but does not issue a legal opinion.
- EPO Guidelines, objective technical problem:
  <https://www.epo.org/en/legal/guidelines-epc/2026/g_vii_5_2.html>.
  Use to reframe the technical problem after closest-prior-art search.

## Light disclosure packet contract

A credible packet has:

1. source artifacts with relative paths and SHA-256;
2. problem-solution-effect statement;
3. distinguishing features, each with evidence support;
4. prior-art status and nearest-result notes;
5. draft claims or patent points with element-level support;
6. programmatic/vector figure sources;
7. open attorney questions and explicit non-legal-advice status.
8. risk triage, inventor-known prior art, search-source coverage, claim ladder
   and QC review flags.

The machine gate is [`../scripts/disclosure_gate.py`](../scripts/disclosure_gate.py).
It intentionally blocks:

- grant or filing guarantees;
- `READY_TO_FILE` language;
- AI-generated patent drawing sources;
- unsupported claim elements;
- missing or mismatched evidence hashes;
- unverified prior-art claims disguised as certainty.

## Prompting stance

The useful expert posture is not “write me a patent.” It is:

> “Here is the actual technical contribution, here is every artifact that proves
> it, here are the closest known approaches, here is the widest plausible claim
> language and the fallback narrower embodiments, and here are the questions
> counsel must decide.”

If a task lacks evidence, write an evidence request instead of a disclosure.
