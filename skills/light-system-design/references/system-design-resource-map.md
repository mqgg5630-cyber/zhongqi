# System design resource map

## Contents

- [Boundary and resource roles](#boundary-and-resource-roles)
- [Lifecycle](#lifecycle)
- [Artifact contract](#artifact-contract)
- [Decision and mutation authorization](#decision-and-mutation-authorization)
- [Evidence states](#evidence-states)
- [Access tiers](#access-tiers)
- [Cross-skill ownership](#cross-skill-ownership)

## Boundary and resource roles

Use this map for greenfield design, existing-system inventory, architecture
options, contracts, operational schema, system migration, ADRs, and delivery
evidence.

- `SKILL.md` chooses the lifecycle phase, enforces stop points, and defines
  ownership.
- This resource map defines artifacts, state transitions, access tiers, and
  authorization.
- `references.md` contains version-sensitive primary-source pointers and branch
  questions. It is not an embedded product/version database.
- `templates/` contains small intake, decision, package, and dialect-labeled
  examples. Select one only after context and user choice.
- `scripts/architecture_lifecycle.py` performs read-only inventory and verifies
  evidence-state integrity.
- `scripts/schema_lint.py` emits dialect/context-scoped heuristic SQL risks.
- `scripts/er_diagram.py` validates schema-spec structure and renders stable
  Mermaid text.
- `scripts/contract_validate.py` validates an OpenAPI document when a real
  validator is installed and separately checks declared examples.

No resource proves production readiness by existing.

## Lifecycle

1. **Protect.** Resolve the selected root, Git/repository context, dirty work,
   artifact locators, and evidence output. Keep evidence outside the source
   root. Inventory is read-only.
2. **Profile requirements.** Record users, goals, core use cases, data classes,
   load range, latency/availability/durability/consistency targets, team/ops
   capability, budget, environment, compliance, and migration window. Missing
   facts remain `UNKNOWN`.
3. **Inventory current state.** Record components, boundaries, interfaces,
   stores, owners, dependencies, write paths, trust boundaries, failure modes,
   versions, source locators, confidence, and freshness.
4. **Model scenarios.** Convert quality attributes into observable scenarios.
   Record synchronous/asynchronous flows and reliability behavior.
5. **Compare options.** Provide a recommendation, viable alternative, rejection
   conditions, tradeoffs, cost/complexity, migration/compatibility/rollback,
   operations, exit criteria, and decision-reversing unknowns. Applicable
   migrations bind consumer/interface inventory and dated usage evidence,
   structured telemetry, phased rollout, rollback verification, and
   compatibility removal conditions; prose placeholders fail readiness.
6. **Stop for decision.** Ask the user to select an option and exact action IDs.
   Do not generate or apply selected artifacts before this response.
7. **Build the authorized package.** Create only the approved schema, contracts,
   migration, ADR, controls, and verification plan.
8. **Rehearse.** Use a disposable database/filesystem. Capture before/after
   hashes, commands, return codes, data-preservation checks, compatibility,
   rollback, and reapply.
9. **Deliver.** Separate verified facts from plans, unknowns, and unavailable
   checks. Hand specialist decisions outward.

## Artifact contract

`architecture_lifecycle.py intake` emits:

| Artifact | Required content |
|---|---|
| `system-profile.json` | system mode and all requirement fields, including `UNKNOWN` |
| `source-inventory.json` | locator, SHA-256, bytes, artifact-kind signal |
| `current-state-inventory.json` | declared components/interfaces/stores/dependencies/deployments with evidence |
| `risk-unknown-report.json` | unknowns, stale facts, trust/PII/tenant/migration risks |
| `intake-integrity.json` | resolved roots and before/after snapshot equality |
| `delivery.md` | concise read-only result and next decision request |

After a choice, the architecture package contains:

| Artifact | Minimum content |
|---|---|
| `context-quality.md` | users, goals, constraints, quality-attribute scenarios |
| `current-state.md` | evidence-backed inventory and unknowns |
| `options.md` | recommendation, alternative, rejected conditions, tradeoffs |
| `component-data-flow.md` | boundaries, ownership, flows, failures |
| API/event contract | versioning, auth, errors, idempotency, compatibility |
| schema/change plan | dialect/version, current/target, diff tool or limitation |
| `migration-plan.md` | expand/backfill/cutover/contract, rollback, stop signals |
| `adr/*.md` | context, options, decision, consequences, status |
| `risk-unknown.md` | security/privacy controls and specialist-review items |
| `package-manifest.json` | package-local authorization binding, source-intake binding, implemented action IDs, artifact hashes, and verification entries |
| `delivery.md` | status summary and limitations |

## Decision and mutation authorization

The option packet must have a SHA-256 and stable action IDs.
`design_readiness.py` computes the canonical digest from requirements,
state model, fitness functions, and the option itself. Authorization must
name:

- authorization ID and absolute authorization date;
- option ID and option-packet SHA-256;
- approved action IDs;
- disposable target root/database;
- explicit `disposable_confirmed=true`;
- compatibility and rollback choice;
- user-supplied authorizer identifier.

Do not include blocked or production actions. Reject changed option digests,
path escape, unknown targets, missing before evidence, or an authorization that
attempts to waive rollback. The authorized walking skeleton may reference only
approved action IDs.

The scripts intentionally do not provide a generic “apply arbitrary SQL” path.
Database engines and migration runners have different semantics; use the
selected real engine in the disposable target and preserve its exact evidence.
The final package manifest must copy the authorization file into the package
directory and bind it by locator/SHA-256, option ID, option-packet SHA-256, and
approved action IDs. It must also declare `implemented_action_ids` as a subset
of approved actions; every verification entry must carry action IDs inside that
implemented scope.

## Evidence states

Use exactly:

- `VERIFIED`: a check ran successfully; include command, cwd, return code,
  locator, SHA-256, and timestamp.
- `PLANNED`: a concrete check exists but was not run.
- `UNKNOWN`: required fact or outcome is not known.
- `UNAVAILABLE`: a named tool/resource was attempted or probed and is not
  available; include the probe/error.
- `FAILED`: a check ran and failed; include evidence and do not deliver as pass.

`architecture_lifecycle.py verify-package` rejects a package missing
authorization binding, missing implemented action IDs, action IDs outside the
approved scope, missing verification coverage for an implemented action, a
stale authorization hash, or a stale source-intake binding. It also rejects a
`VERIFIED` entry missing evidence or whose artifact hash no longer matches. It
cannot establish that the recorded command itself was truthful; preserve raw
logs for high-risk work. Artifact and verification locators are resolved
relative to the manifest's directory and must remain inside that package
directory, so a package does not silently verify a file from the caller's
current working directory or from a parent/outside path.

## Access tiers

| Tier | Examples | Core dependency? |
|---|---|---|
| Local free | Python stdlib, SQLite, local source, supplied DB tools | Yes |
| Public free | official specs/docs, public GitHub source | Research only |
| Free login/key | higher-rate APIs, hosted schema registry | No |
| Institution/cloud restricted | private repo, staging DB, cloud logs | Optional |
| Paid/closed | commercial architecture/schema platforms | No |

The core intake, evidence verification, SQL heuristic, JSON parsing, and
Mermaid text generation run locally. YAML needs PyYAML and full OpenAPI
validation needs `openapi-spec-validator`; absence becomes `UNAVAILABLE`, not a
false pass.

## Cross-skill ownership

- `system-design`: system/runtime boundaries, interfaces, operational stores,
  system migration, reliability choices, ADRs.
- `project-structure`: visible tree and authorized file moves only. Its
  read-only/authorization/hash/rollback discipline is reused; schema and API
  migration remain here.
- `data-engineering`: research-data quality, lineage, transformations, split,
  and release. This skill may state service data flow but does not absorb that
  scientific-data lifecycle.
- `frontend-design`: interaction and UI implementation. API consumer needs are
  inputs here; interface visuals are not.
- `research-ethics`: final privacy/ethics review. This skill records controls
  and pending-review items without declaring ethical clearance.
- `orchestrator`: may consume delivery status. System design remains off-DAG
  with no findings, checkpoint, stage, route, or back-edge.
