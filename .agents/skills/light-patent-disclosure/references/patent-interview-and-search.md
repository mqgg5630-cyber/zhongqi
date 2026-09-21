# Patent interview, search and claim-ladder workflow

Use this reference when a task involves patent-point mining, invention disclosure drafting, prior-art context, claim support, or attorney handoff. This is procedural support for preparing evidence-backed materials, not legal advice.

## 1. Intake risk triage

Record four risk records before writing a polished disclosure:

1. `public_disclosure`: papers, posters, talks, thesis defense, GitHub releases, product demos, sales, offers for sale, standards submissions, public datasets and dates.
2. `ownership_inventorship`: applicant/owner, inventors, contributors, employer, sponsor, commissioned/cooperative/inherited constraints.
3. `foreign_filing_or_secrecy`: intended route, secrecy/export review, foreign filing strategy, deadline.
4. `trade_secret_redaction`: what must be removed or summarized before outside review.

Allowed status values are `VERIFIED`, `PLANNED`, `UNKNOWN`, `UNAVAILABLE`. `PLANNED` or `UNKNOWN` needs a `next_check`. Do not infer legal facts from source code.

## 2. Inventor interview prompts

Ask only the questions needed for the current evidence gap:

- What problem were you trying to solve technically?
- What existing approaches did you try or reject, and why?
- What is the key insight that made the final approach work?
- Which edge cases, constraints, latency/resource limits, data limits or failure modes shaped the design?
- Which files, design docs, notebooks, issues, experiments or diagrams prove the implementation?
- Who contributed to the inventive concept, and what did each person contribute?
- Has the idea, product, paper, demo or code been publicly disclosed, sold or offered for sale?
- When was the idea conceived and when was it reduced to practice?
- What prior papers, products, patents or internal baselines were already known to the team?

Separate “inventor-known prior art” from “agent-run public search results”.

## 3. Evidence packet

Every technical feature needs an artifact id, relative path, SHA-256 and support note. Acceptable evidence includes repository files, design docs, lab notes, experiment logs, issue discussions, notebooks, public papers, user-supplied records and vector/programmatic diagrams. Chat history alone is not evidence.

## 4. Search coverage log

For public search, record `searched_sources`:

- `source_name`: e.g. CNIPA patent publication system, Google Patents, USPTO, EPO Espacenet, Google Scholar, arXiv, publisher page.
- `source_type`: use `patent_database`, `non_patent_literature`, `product_documentation`, or `other_public_source`.
- `query`, `checked_at`, optional `filters`, `result_count`, `failure`.

If search is verified, include at least one patent database. If non-patent literature is not searched, record `npl_not_searched_reason`. Do not call the search complete unless it actually is; write the limitation plainly.

## 5. Problem-solution-effect analysis

For each candidate patent point, write:

- technical problem, not business desire;
- technical means: algorithm, architecture, data structure, protocol, control loop, model pipeline, device arrangement or UI interaction rule;
- technical effect: measurable or observable improvement;
- nearest known approach and distinguishing technical feature;
- artifact support and open evidence gaps.

After search, revise the objective problem and difference table if the nearest result changes the story.

## 6. Claim ladder

Prepare a claim strategy before calling the packet ready:

1. `broadest_defensible_point`: the widest technical point still supported by artifacts and embodiments.
2. `fallback_positions`: narrower fallbacks, each with why it is narrower and artifact support.
3. `enablement_support_summary`: how the disclosure teaches the invention: embodiments, variants, parameter ranges, edge cases, failure handling and alternatives.

Do not keep a broad claim element if no artifact or embodiment supports it. Either narrow it, mark it as a counsel question, or lower delivery status.

## 7. QC before attorney handoff

Before `READY_FOR_ATTORNEY_REVIEW`, set all five QC flags true:

- `support_map_complete`: every distinguishing feature and claim element has artifact support.
- `terms_consistent`: title, description, figures and draft claims use consistent terms.
- `figures_auditable`: figures are Mermaid/Graphviz/PlantUML/SVG/manual vector/programmatic sources with hashes; no AI bitmap drawings.
- `overclaim_removed`: grant/filing/novelty/FTO guarantees and unsupported breadth are removed.
- `counsel_questions_listed`: open legal/prosecution questions are visible.

If any QC item fails, deliver `DRAFT` or `NEEDS_USER_INPUT` with the repair plan.
