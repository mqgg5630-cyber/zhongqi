# Review-rebuttal resource map

Use this map to execute a real review→revision→response round. `SKILL.md` holds
the governing instructions; this page orders resources; `references/*`
defines contracts and source policy; `templates/*` are blank inputs; scripts
validate and emit artifacts.

## 1. Verify the selected venue package

Read venue-matching's `selected-venue-handoff.json` and
`review-rebuttal-context.json`. `review_workflow.py` verifies:

- selected venue identity and user decision authority;
- timezone-bearing `selected_at`, non-empty `selection_basis`,
  `selected_at` not in the future, coherent `selected_by/status`, and
  delegated `user_authorization` when an
  agent selected under user approval;
- chosen candidate ID, fit/risk row and review-context venue type without
  drift;
- rule envelopes and source IDs without filling missing values;
- source evidence schema/path/as-of/source IDs against the source-evidence
  artifact; `AVAILABLE` rule fields must cite available authoritative sources
  with checked dates not after the selection time;
- stage-11 PDF path/SHA-256/pages/page size/profile/source;
- `DELIVERED`, compliance `PASS`, and zero critical findings;
- paper-writing claim IDs and result-analysis evidence IDs.

If JORS is selected, keep its real 2-page PDF facts and sourced 4–6-page
expansion requirement visible. That manuscript-length rule is not a response
letter limit. If no current JORS response-length/new-material rule is found,
record `UNKNOWN`.

## 2. Acquire reviews without losing provenance

Preferred order:

1. User-supplied decision letter, reviews, meta-review and attachments.
2. Public OpenReview API v2 data captured by `fetch_openreview.py`.
3. A commit-pinned public PeerRead/OpenReview snapshot, explicitly labelled as
   historical rather than live, when the API is unavailable.
4. Publisher/conference portal export supplied by the user.

Record source URL/type, timezone-aware capture time, round, reviewer ID,
attachment path/hash where available, access status, and raw-text SHA-256.
Preserve raw text exactly. Store classification and generated prose separately.

## 3. Atomize and classify

Split into `request|claim|question|misunderstanding|editorial`. Assign a root
cause and rejection-driving evidence separately. Novelty, experiment and
writing are not automatically critical; only explicit rejection-driving rows
with a decision/meta-review/reviewer evidence locator can trigger stage 13.
For each addressable reviewer unit, keep source ID, start/end, exact text and
SHA-256, then reconstruct the ordered addressable units to a hash. Run
`scripts/review_response_contract.py` before drafting to catch missing units,
duplicate mappings, duplicate actions, policy-forbidden requests, missing
reviewer competence/conflict cards and incomplete self-review perspectives.

## 4. Bind the work

Bind each atom to paper claim IDs, result evidence IDs, one response strategy,
an owner, an action state, and provenance:

- paper edits → paper-writing;
- experiment/design → research-plan/experiment-coding;
- analysis/evidence strength → result-analysis;
- new references → citation;
- new/changed figures → figure;
- rebuilt PDF/compliance → typesetting.

Use `PLANNED` until the owning skill produces the artifact. A prose promise is
not an artifact.

## 5. Draft and budget

`review_workflow.py` formats author-supplied response text against verbatim
review spans. `rebuttal_budget.py` reads only the selected venue context.
It has no built-in venue presets. Unknown or page-only rules remain explicit
and require current official instructions or a rendered artifact.

## 6. Close commitments

`check_commitments.py` compares:

- `commitment-ledger.json`;
- `issue-matrix.json`;
- `evidence-change-map.json`.

It catches missing issue coverage, `PLANNED_AS_DONE`, DONE without locator,
ledger/change-map drift, declined work without rationale, review raw hash drift,
future/naive review capture time, and completed experiment/analysis without
matching run provenance SHA-256.

## 7. Gate, suggest, pause

`reviewer_classify.py` emits the canonical `reviewer_classify` gate.
`run_checkpoint --stage 13` must fail when a critical root cause exists.
`reroute` may suggest 13→3/5/8. Present the evidence and alternatives, then
stop. Only a subsequent user choice authorizes `passport add-back-edge`.

## Access layers

| Layer | Resources | Role in workflow |
|---|---|---|
| Local free | Skill scripts, templates, manuscript, claims, evidence, citation registry, PDF, user-provided reviews | Core path |
| Free public/no key | OpenReview public API, commit-pinned PeerRead snapshot, venue/publisher author and peer-review pages, Crossref/DataCite via citation | Current or explicitly historical public evidence; 401/403/429/5xx becomes `UNAVAILABLE` |
| Free login/key | Private author portal export, optional OpenReview authenticated/private access, optional scholarly API keys | Enhancement only; user supplies/export data |
| Institution restricted | Scopus/Web of Science/full-text subscriptions, institution publisher portals | Optional evidence; access failure is not a fact |
| Paid closed | Commercial review-management/writing platforms and paid APIs | Never required by the core path |

The core path uses Python standard library and local files. It does not require
a paid review platform, private API key, browser plugin, MCP, or npm package.
