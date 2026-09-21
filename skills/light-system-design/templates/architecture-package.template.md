# Architecture package: <system>

## Status

- Option selected by:
- Authorization locator/hash:
- Option packet SHA-256:
- Approved action IDs:
- Implemented action IDs:
- Source intake integrity locator/hash or not-applicable reason:
- Package state: PROPOSED | AUTHORIZED | VERIFIED | PARTIAL

## Context and quality attributes

| Scenario | Stimulus/environment | Response | Measure | State/evidence |
|---|---|---|---|---|

## Current state

| Component/interface/store | Owner | Dependencies/write path | Failure/trust boundary | Source/freshness |
|---|---|---|---|---|

## Options and decision

| Option | Benefits | Costs/complexity | Migration/compatibility | Reject when | Exit criteria |
|---|---|---|---|---|---|

## Component and data flow

Record sync/async edges, transaction/outbox boundaries, delivery semantics,
idempotency/deduplication, ordering, backpressure, timeout/retry, and failure
handling.

## Contracts and schema

Record dialect/protocol/version, current and target locators, validator/diff
tool, compatibility window, deprecation, auth/error/pagination/idempotency.

## Migration and rollback

List stable action IDs. For each action include precondition, mutation,
verification, rollback, stop signal, owner, and expected observability.

## ADR

Record context, decision drivers, considered options with pros/cons, selected
decision, consequences, status, and supersession links.

## Risk, unknown, and specialist review

Separate system controls from pending security/privacy/research-ethics review.

## Verification evidence

Each verification entry must bind to action IDs that are both implemented and
approved.

| Check | Action IDs | State | Command/cwd | Return code | Locator/SHA-256 | Timestamp |
|---|---|---|---|---|---|---|

## Delivery limitations

State what the package does not prove.
