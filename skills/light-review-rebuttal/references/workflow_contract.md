# Stage-13 review workflow contract

## Invariants

1. Source text is immutable. `raw_text` and `raw_span` are evidence;
   interpretation, classification, strategy and draft prose are derived layers.
   `review_atom.v2` additionally carries source ID, start/end offsets, exact
   span text and SHA-256; addressable reviewer units reconstruct to a declared
   hash so omissions and duplicate mappings are visible. `review_workflow.py`
   records `raw_sha256` for every available review source, verifies any supplied
   `raw_sha256`, and rejects missing/naive/future `captured_at`.
2. Venue rules keep their source envelope and
   `AVAILABLE|UNKNOWN|UNAVAILABLE|STALE` state.
   `light.selected_venue_handoff.v1` is not trusted by filename alone: the
   consumer must verify user/delegated selection audit fields, chosen candidate,
   fit/risk row, source-evidence artifact, context envelope and delivered PDF
   facts before drafting a response. `selected_at` must be timezone-aware and
   not in the future at consumption time.
3. `PLANNED|IN_PROGRESS|DONE|DECLINED|NOT_APPLICABLE` describes actual action
   state. DONE requires a change locator; scientific DONE requires run
   provenance with a matching SHA-256. A path that merely exists on this machine
   is not enough. `response_action.v2` also declares evidence kind and policy/
   ethics/user-authorization state before a new result is promised.
4. Only `rejection_driving=true` plus complete `rejection_evidence` can create
   stage-13 critical.
5. Gate/reroute output is advisory. Passport mutation requires a later user
   decision.

## Input

`light.review_rebuttal_input.v2` is represented by
`templates/review_input.json`.

Each review source records:

- `source_id`, `source_kind`, `source_url`, `captured_at`;
- `access_status`, `access_reason`;
- `round`, `reviewer_id`, `decision`, `meta_review`, `attachments`;
- verbatim `raw_text`, `raw_sha256`, and timezone-aware `captured_at`;
- derived `atoms[]`.

Each atom records:

- stable `issue_id`;
- exact contiguous `source_span` with start/end/text/SHA-256;
- addressable unit IDs and reconstruction hash coverage;
- `issue_type`: request, claim, question, misunderstanding or editorial;
- root cause and severity;
- optional explicit rejection-driving evidence;
- claim/evidence bindings;
- strategy, action kind, owner, state, locator, artifact/run/citation
  provenance and author-supplied response text.

## Outputs

| Artifact | Schema | Meaning |
|---|---|---|
| `review-registry.json` | `light.review_registry.v1` | canonical raw reviews/decisions/meta-review and source metadata |
| `issue-matrix.json` | `light.review_issue_matrix.v1` | atoms, root causes, rejection evidence and action bindings |
| `revision-plan.json` | `light.revision_plan.v1` | owner/state/location checklist |
| `evidence-change-map.json` | `light.evidence_change_map.v1` | issue↔claim↔evidence↔change↔citation/run provenance |
| `response-draft.md` | human-readable | verbatim concern plus supplied draft/status/locator |
| `commitment-ledger.json` | `light.commitment_ledger.v1` | atomic promises and actual states |
| `unknowns.json` | `light.review_unknowns.v1` | venue/source/rule unknown, unavailable and stale items |
| `failure.json` | `light.review_failure.v1` | structural/provenance/truth failures |
| `delivery.json` | `light.review_rebuttal_delivery.v1` | artifact index, verified venue/PDF facts and boundaries |

`light.review_response_contract.v1` is the stricter pre-draft gate for
`review_atom.v2`, `response_action.v2`, reviewer competence/conflict cards, and
`domain|method|statistics|ethics|cold_reader` self-review. Run
`scripts/review_response_contract.py --input <contract.json>`; exit code 1
means the package is not ready.

`DRAFT_READY` means structural checks passed; it does not mean the venue accepts
the response or the science is adequate. `BLOCKED` means `failure.json` must be
repaired.

## Rejection evidence

A critical candidate needs:

```json
{
  "rejection_driving": true,
  "rejection_evidence": {
    "kind": "decision | meta_review | reviewer_explicit",
    "value": "verbatim or faithful source value",
    "locator": "source artifact locator"
  }
}
```

An overall Reject/Major decision can establish the round context, but does not
make every major comment rejection-driving. Explicitly bind the decision or
meta-review statement to the root-cause issue.

## Change evidence

- Prose DONE: concrete section/page/line/anchor plus actual revised artifact.
- Experiment/analysis DONE: locator, run artifact path, matching hash, and
  producer provenance.
- New citation: canonical citation `work_id` with `CONFIRMED`; semantic support
  still follows citation's claim-edge review.
- No manuscript change: `NOT_APPLICABLE` with clarification/rebuttal evidence,
  or `DECLINED` with rationale.

## Exit codes

| Script | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `review_workflow.py` | draft ready | blocked delivery | input/runtime error | — |
| `review_response_contract.py` | pass/warn | critical atom/action contract gap | input/runtime error | — |
| `fetch_openreview.py` | available capture | — | argument/runtime error | source unavailable |
| `rebuttal_budget.py` | pass or explicit unknown/stale | over current limit | input/runtime error | source unavailable |
| `check_commitments.py` | pass/warn | critical truth/coverage gap | input/runtime error | — |
| `reviewer_classify.py` | no critical | evidenced critical | input/runtime error | — |
