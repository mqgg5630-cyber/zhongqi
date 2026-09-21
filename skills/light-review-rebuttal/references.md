# Review, decision and venue-rule source policy

Checked on 2026-07-03 (Asia/Shanghai). Recheck volatile rules on every run.

## Source priority

1. Selected venue handoff/context from venue-matching.
2. Author portal export or decision/review files supplied by the user.
3. Current official venue/publisher author and peer-review instructions.
4. Public OpenReview API records for public venues/forums.
5. Research papers/datasets for calibration, never as venue policy.

Do not substitute a general publisher tutorial for a venue-specific rule.
When sources conflict, preserve both and mark the canonical field `UNKNOWN`
pending human resolution.

## Access states

| Observation | State | Meaning |
|---|---|---|
| Current source returns the field/text | `AVAILABLE` | retain value/text, source and capture/check time |
| Source is reachable but field is absent, ambiguous or conflicting | `UNKNOWN` | no usable conclusion |
| 401/403/429/5xx, timeout, network, login, private invitation, key or subscription blocks access | `UNAVAILABLE` | source could not answer |
| Volatile field was not checked for the current run | `STALE` | do not use it for delivery |

## OpenReview

Use `https://api2.openreview.net/notes?forum=<forum-id>&details=directReplies`
for a public discussion tree. Invitation names and content fields vary by
venue/year. Preserve the returned `content`, invitations, signatures, note ID
and timestamps. Public access today does not prove every forum is public.

`fetch_openreview.py` deliberately writes an `UNAVAILABLE` capture on
transport/auth/rate/service failure. Empty results and failed access are not
interchangeable.

When a fixed public PeerRead snapshot is used, pin the raw URL to a repository
commit and label it historical. The capture keeps each original record,
removes only byte-equivalent duplicate review objects from derived counts, and
reports both `source_record_count` and `duplicate_records_removed`. It is not a
substitute for current venue rules.

## JORS selected context

The current official JORS pages describe article types, submission formatting,
peer-review criteria and editorial outcomes. They do not, in the public pages
checked for this run, publish a response-letter word/character/page limit or a
clear new-material rule. Keep those response fields `UNKNOWN`; do not borrow a
conference rebuttal limit.

Official pages:

- https://openresearchsoftware.metajnl.com/about/submissions
- https://openresearchsoftware.metajnl.com/en/about/editorialpolicies
- https://openresearchsoftware.metajnl.com/about

The selected venue context's sourced 4–6-page value applies to the manuscript
article, not automatically to the response letter.

## Separation from other resources

- `review-rebuttal-resource-map.md`: run order and access layers.
- `references/workflow_contract.md`: machine schemas and state semantics.
- `templates/*`: blank input/response/checklist forms.
- `docs/competitors/review-rebuttal.md`: peer-skill, API/tool, rule, paper and
  dataset comparisons with dated evidence.
