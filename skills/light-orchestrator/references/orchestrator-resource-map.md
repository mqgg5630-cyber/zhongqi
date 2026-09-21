# Orchestrator resource map

Use this map for a multi-stage project, a resumed project, a failed checkpoint,
or final delivery. The canonical orchestration state is
`.light/passport.yaml`; memory-pm owns the surrounding project card, decisions,
version history and handoff archive. Do not let two files both claim to be the
pipeline state authority.

## 1. Intake before action

Run `scripts/lifecycle.py intake --root <project>`. It classifies exactly one
primary state:

| State | Meaning | Next action |
|---|---|---|
| `new` | no passport or no stage records | propose a cropped pipeline; ask before strategic choices |
| `resume` | an active/rework stage exists and evidence is not stale | continue the recorded `next_action` |
| `partial` | some stages are delivered but no active stage is recorded | identify the next dependency-ready stage |
| `dirty` | Git has tracked/untracked user work | preserve it; do not overwrite or reorganize |
| `failed` | schema/checkpoint/evidence failed | stop; inspect blocking findings and suggest reroute |
| `stale` | upstream content hash changed | reverify only the propagated downstream closure |
| `delivered` | selected pipeline is delivered | verify delivery package and ask what happens next |

An existing file is not proof of completion. Delivery requires a valid
passport, current hashes, required checkpoint evidence, no unresolved critical
finding, and an explicit user delivery decision.

## 2. Canonical state and migration

- Current schema: `light.passport.v3`.
- Machine schema: `passport.schema.json`.
- Starter only: `../templates/passport.v3.yaml`; `passport.py init` replaces
  the zero hash with a real SHA-256.
- Run `passport.py migrate` as a dry run first. Use `--write` only after the
  user authorizes migration of the project ledger.
- `state_hash` is computed from canonical JSON excluding `state_hash`.
  `inputs_fingerprint` hashes file contents, not mtime alone.
- A v1/v2 back-edge without an authorization record migrates as
  `authorization_id=UNKNOWN` and remains a warning, never fabricated proof.

## 3. Roles

- Pipeline: stages 1–13 only.
- Resident overlays: memory-pm, project-structure, consistency,
  research-ethics and file-reading. They are never stage numbers.
- Off-DAG engineering/IP handoff: frontend-design, system-design,
  patent-disclosure and software-copyright. They may be invoked beside a
  research/software project, but never enter `STAGE_GATES`, `ROUTES` or
  scientific findings.
- project-structure and file-reading are off-DAG overlays. Only consistency
  and research-ethics produce normal cross-stage content findings; memory-pm
  produces an on-demand ledger audit.

Read `integration-contract.json` for the exact 23-skill mapping. Rebuild and
audit the human inventory with:

```bash
python scripts/integration_audit.py --root ../.. --markdown
```

## 4. Checkpoint and reroute

1. Run the actual producer and retain its `light.findings.v1`.
2. Run `run_checkpoint.py` without `--write`; inspect exit code and report.
3. If critical, run `reroute.py`. It only recommends:
   - `back_edge`: an actual earlier scientific stage;
   - `admission_hold`: 2⊣3, which blocks entry to idea generation and never
     writes a back-edge;
   - `known_limitation` or `manual`.
4. Stop and ask the user. Only after a specific choice, call
   `passport.py add-back-edge` with `--authorization-id`.
5. A real back-edge must satisfy `to < from`, increments the target's durable
   `revision_rounds`, and cannot exceed two rounds.

Before choosing any multi-task mode, run `scripts/execution_mode.py`. It must
return `UNRESOLVED` for remote execution, paid resources, external writes,
publish/submit, delete/overwrite, irreversible actions, high-risk work,
private/legal/ethics-sensitive scope, or positive cost unless a passing
`light.decision_checkpoint.v1` with an authorization ID is attached to the
task profile. `user_decision_needed=false` is not an override.

For multi-task/parallel/HITL execution, run
`scripts/workflow_ledger.py --input templates/workflow-ledger.example.json`.
The ledger is read-only and checks dependency closure, task owner/context,
completion evidence with real `sha256:<64hex>`, a non-owner verification
package bound to the exact current artifact hashes, bounded retries, decision
question/options/expiry, parallel joins and resume snapshot compatibility. It
does not execute, authorize or replace the passport. A `WAITING_USER` task is
valid only when the user-facing question and at least two consequence-bearing
options are recorded; otherwise the orchestrator is merely pretending to ask.
A changed workflow definition invalidates an old resume snapshot. An owner
cannot self-certify `SUCCEEDED`; a changed evidence hash invalidates its old
verification package.

## 5. Evidence discipline

Use only `VERIFIED`, `PLANNED`, `UNKNOWN`, `UNAVAILABLE`, or `FAILED`.

- `VERIFIED`: command/result/hash/timestamp are present and current.
- `PLANNED`: authorized intent without execution evidence.
- `UNKNOWN`: fact was not supplied or established.
- `UNAVAILABLE`: an identified tool/source could not be accessed.
- `FAILED`: an attempted check or checkpoint failed.

Never collapse `UNKNOWN` into an empty list, `UNAVAILABLE` into absence, or a
plan into a completed result.

## 6. Access tiers

1. Local/free core: passport, findings, Git, Python stdlib, project files.
2. Public/no-login: authoritative web pages and public APIs.
3. Login or institution: optional coverage; record `UNAVAILABLE` when absent.
4. Paid/closed: optional only; never required for the core lifecycle.

## 7. Resident budget and harness boundary

Claude Code can inject a deterministic SessionStart report. Codex and
OpenCode run the same memory-pm resume implementation through their instruction
file; the trigger is model-read, not harness-enforced. Keep resident context
under 9,800 characters, prioritize red lines + state + next action, and degrade
to a short pointer when the resume report is unavailable or oversized.

## 8. Handoff and recovery

Run `lifecycle.py handoff` to emit a hash-bound handoff. On resume, run
`lifecycle.py verify-handoff`; a changed passport hash makes it stale. The
verifier also checks the project root, timezone-bearing `generated_at`, and
the live intake snapshot (`intake_state`, `next_action`, blockers,
`need_reverify`, known limitations and evidence state). This catches stale
artifacts or dirty user work that appear without changing the passport hash.
The handoff records classification, blockers, known limitations and exactly
one next action. It is a recovery pointer, not a second state authority.

Final delivery uses `passport.py authorize-delivery --authorization-id ...`.
It checks every selected stage, evidence state and stale propagation before
writing `DELIVERED`; known limitations travel with the authorization.
