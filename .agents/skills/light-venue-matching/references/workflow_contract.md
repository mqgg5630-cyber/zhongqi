# Stage-12 venue artifact contract

## Input

`light.venue_input.v2` points to one delivered
`light.typesetting_venue_handoff.v1`, a manuscript profile, author constraints,
source records, and candidate evidence. Paths resolve relative to the input
JSON. The workflow verifies the PDF path/hash plus handoff/compliance status,
then consumes the recorded pages, page size, profile/source, compliance report,
and upstream provenance. It does not compile or inspect the PDF again.

`manuscript_profile.claims_delivery` is required. It binds the paper-writing
claim/profile artifact by safe relative path, schema, and SHA-256. The workflow
hashes that artifact before preparing a decision packet; if the file is absent,
absolute/escaping, schema-mismatched, or edited after the hash was recorded,
prepare fails closed. Venue matching may consume the claim/evidence profile for
fit explanation, but it must not rewrite or strengthen claims to satisfy a
venue.

Each source has `source_id`, URL/query/locator/path, check time, access tier,
authority, status, and failure reason. `status=AVAILABLE` without an auditable
locator, `checked_at`, `access_tier`, or `authority` is downgraded before any
field can use it. Each candidate field is an envelope:

```json
{
  "status": "AVAILABLE|UNKNOWN|UNAVAILABLE|STALE",
  "value": null,
  "source_ids": ["official-guidelines"],
  "checked_at": "YYYY-MM-DD",
  "reason": "why available or why not"
}
```

`AVAILABLE` needs a value and an available source. Acceptance rate, review
time, APC/OA, indexing/quartile, and CFP/submission deadlines must be checked on
the run date; otherwise the workflow rewrites them to `STALE` with a null
value. Official rules, article type, page limits, APC/OA and deadlines require
official/publisher/venue authority; indexing/quartile require index or registry
authority. A 403/429/5xx, missing key/login/subscription, or source outage is
`UNAVAILABLE`, never “not indexed,” “not in DOAJ,” free of charge, or risky.
The evidence gate requires a timezone-aware `as_of`; any `retrieved_at` later
than `as_of` is future evidence and blocks the decision packet.

## Prepare outputs

`venue_workflow.py prepare` writes:

- `candidate-registry.json` (`light.venue_candidate_registry.v2`);
- `source-evidence.json` (`light.venue_source_evidence.v1`);
- `fit-risk-report.json` (`light.venue_fit_risk.v2`);
- `unknowns.json` (`light.venue_unknowns.v1`);
- `decision-packet.json` (`light.venue_decision_packet.v2`);
- `delivery.json` (`light.venue_delivery.v2`).

The decision packet is always `AWAITING_USER_DECISION`,
`decision_point=true`, `chosen=null`. It includes reach/match/safety/excluded
groups and a transfer order with `because` and evidence IDs. Scope,
article-type, method/data, real page facts, APC/OA, timing, indexing, risk, and
author constraints remain separately explainable. Fit is not acceptance
probability.

Soft risk signals stay warnings. The workflow may objectively exclude an
official article-type/page mismatch or an explicit author hard constraint. It
does not auto-condemn a venue as predatory/hijacked; that needs current,
multi-source evidence and a human verdict.

The packet binds `candidate-registry.json`, `source-evidence.json`,
`fit-risk-report.json`, and `unknowns.json` by relative path, schema, and
SHA-256. `delivery.json` records the decision packet SHA-256. These bindings
are decision evidence, not optional metadata.

## User selection and downstream handoff

`venue_workflow.py choose` refuses an unprompted agent choice. It requires a
separate `light.venue_user_selection.v1`: use `actor=user` for a direct choice;
for explicit delegation use `actor=agent_with_user_authorization`,
`decision_authority=user`, and preserve the user's authorization verbatim.
The selection must also include timezone-aware `selected_at` and `because`
recording the user's stated trade-off, plus `decision_sha256` copied from the
reviewed delivery. `selected_at` cannot predate the decision packet's
`generated_at`. The candidate ID must come from a non-excluded tier. Before
writing a handoff, `choose` re-hashes the decision and all four bound artifacts,
checks their schemas, and requires them to remain beside the decision packet.
Any mutation or path drift fails closed. Only then it writes:

- `selected-venue-handoff.json` (`light.selected_venue_handoff.v1`);
- `author-submission-plan.json` (`light.author_submission_plan.v1`);
- `review-rebuttal-context.json`
  (`light.review_rebuttal_venue_context.v1`).

The selected handoff preserves candidate field evidence, source IDs, author
constraints, manuscript profile including the bound paper-writing claims
artifact, and the stage-11 PDF facts/provenance.
Downstream work may use those current rules; it must recheck unknowns and
volatile fields before submission. Selection never performs submission.

## Stage contract

Stage 12 is a user decision point, not a confirmation gate.
`STAGE_GATES` has no key 12 and `ROUTES` has no key 12. The canonical workflow
does not create critical findings or a fake back-edge. The legacy
`venue_risk_gate.py` remains a warn-only adapter for projects that aggregate
risk findings; it is not required by the canonical prepare/choose path.
