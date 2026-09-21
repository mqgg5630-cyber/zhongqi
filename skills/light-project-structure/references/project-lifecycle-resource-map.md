# Project lifecycle resource map

## Contents

- [Boundary](#boundary)
- [Lifecycle](#lifecycle)
- [Artifact contract](#artifact-contract)
- [Policy decisions](#policy-decisions)
- [Template provenance](#template-provenance)
- [Access levels](#access-levels)
- [Cross-skill ownership](#cross-skill-ownership)

## Boundary

Use this map for the visible project tree, a structure profile, source inventory,
dry-run migration planning, explicitly authorized moves, and rollback. It does
not prove data quality, experiment reproducibility, or paper quality.

`SKILL.md` decides when to use the lifecycle and when to stop. This file defines
the artifact contract. `references/structure-profiles.json` supplies small,
extensible minima. `templates/project-policy.template.json` captures project
facts and file policy. `scripts/scaffold.py` performs deterministic inventory,
move, and rollback mechanics. The remaining legacy templates are optional
examples; they are not a mandatory 23-directory tree.

## Lifecycle

1. **Intake.** Determine greenfield, Git root, Git subroot/monorepo, or non-Git.
   Record branch, tracked/untracked/ignored files, dirty status, submodules,
   symlinks, large files, and sensitive path signals. Inventory is read-only
   with respect to the source root.
2. **Requirements.** Record project type, deliverables, compute environment,
   data volume, remote storage, collaborators, CI, license, and retention.
   Leave missing values as `UNKNOWN`.
3. **Signature evidence.** Detect file/config signals for Python, R, paper,
   data, other code, and monorepo markers. Keep observed signals separate from
   policy declarations; never infer project evidence from the selected profile.
4. **Canonical inventory.** Record locator, SHA-256, size, Git state, owner,
   producer, recomputability, sensitivity, classification, Git policy, target,
   and the policy rule that supplied those fields.
5. **Plan.** Emit moves, duplicates, target conflicts, policy conflicts,
   unknowns, expected diff, and rollback instructions. Existing repositories
   remain dry-run.
6. **Decision.** Present the plan digest and action IDs. A user-created
   authorization must bind a stable authorization ID, concrete user identity,
   non-future authorization date, and exact approved action IDs to that digest.
   Unknown, duplicate, blocked, or placeholder action IDs fail closed.
   `--force` does not exist.
7. **Apply.** Apply only approved, unblocked ordinary-file moves. Reject changed
   source hashes, symlinks, path escape, missing sources, and existing targets.
   Path escape is also a dry-run/governance blocker: `../`, absolute paths,
   Windows drive-letter paths, and UNC paths must not appear as safe action
   IDs. The applied manifest must bind the exact migration-plan file and
   authorization file by locator and raw file SHA-256 in addition to the
   canonical plan digest and authorization digest.
8. **Verify and rollback.** Emit before/after locator and hash evidence. Run
   rollback from the applied manifest, verify restored hashes, then reapply only
   if the same authorization is still intended.

## Artifact contract

`intake --out <dir>` emits:

| Artifact | Required content |
|---|---|
| `project-profile.json` | repo mode, Git evidence, requirement fields |
| `technology-signatures.json` | observed locators, policy declarations, effective artifact types, recommended profile, and limitations |
| `source-inventory.json` | canonical inventory; no inferred fact hidden as known |
| `structure-audit.json` | minimum profile gaps, policy findings, limitations |
| `migration-plan.json` | action IDs, blockers, expected diff, plan digest |
| `conflict-unknown-report.json` | collisions, duplicates, symlinks, large-file review, unknown fields |
| `rollback-plan.json` | pre-apply status and post-apply rollback command |
| `intake-integrity.json` | before/after source snapshot and Git status |
| `environment-doctor.json` | declared Python/R/Quarto/DVC/LaTeX/tool availability; unavailable required tools block readiness |
| `template-residual-scan.json` | placeholder/TODO scan for generated templates; unresolved residuals block delivery |
| `secret-scan.json` | secret locations and redacted fingerprints only; never raw values |
| `governance-report.json` | `structure_governance_gate.py` report tying profile, policy, secrets, env, plan, authorization, and rollback |
| `delivery.md` | concise human handoff and decision request |

`apply` emits `applied-manifest.json`; every applied action has source/target and
before/after SHA-256, and the manifest includes `plan_binding` plus
`authorization_binding` with locator and file SHA-256. `rollback` emits
`rollback-manifest.json`.

## Policy decisions

Do not infer Git suitability from a directory name alone:

- Immutable source data may be tracked when it is small, public, licensed, and
  intentionally versioned, or stored through DVC/object storage.
- Small test fixtures and reviewed golden files commonly belong in Git.
- A DVC pointer belongs in Git; the pointed large object does not.
- Large or sensitive raw data, models, logs, and results normally require DVC,
  object storage, or an institutional repository.
- Final paper figures, release artifacts, and audit evidence may be versioned
  even when they are recomputable. Decide from retention and review needs.

The template policy is an example. Copy it and replace every relevant
`UNKNOWN`; do not treat its globs as universal truth. `git rm --cached`, DVC
initialization, deletion, overwrite, and config rewrites remain separate
decision points and are never performed by `apply`.

## Template provenance

Greenfield `scaffold` records profile source/hash, generator source/hash,
timestamp, and parameters in `.project-structure-provenance.json`. It is a
one-time generator. It does not claim template update or merge support.

After generation, scan for unresolved placeholders such as `{{ cookiecutter.* }}`,
`[[ copier ]]`, `${PROJECT_NAME}`, and `TODO_TEMPLATE`. Passing file existence
tests is not enough; residual placeholders mean the tree is not ready.

Use Copier for stateful template updates and migration tasks. Use Cruft when a
Cookiecutter lineage and drift/update workflow fits. Both still require review
of conflicts and local modifications. Never describe drift detection as a safe
merge guarantee.

Run `structure_governance_gate.py` on the final evidence bundle. It is a local
contract, not a DAG findings gate, and it exists to stop overclaiming: fixed
directory trees, missing environment checks, raw secret values in reports,
unreviewed template residuals, `.light/` moves, root-escaping paths, blocked
actions, applied manifests without plan/auth file binding, and rollback claims
without hash evidence must not be packaged as a finished structure.

## Access levels

| Level | Examples | Core dependency? |
|---|---|---|
| Local free | Python stdlib, Git when installed | Yes |
| Public free | GitHub source, official docs | Research only |
| Free login/key | GitHub API at higher limits | No |
| Institution restricted | private object store, HPC | Optional |
| Paid/closed | commercial template platform | No |

The core lifecycle is local and standard-library only. Git absence produces an
honest `non-git` mode instead of a false pass.

## Cross-skill ownership

- `project-structure`: visible tree, profile, inventory, migration plan, applied
  move evidence, rollback.
- `memory-pm`: every `.light/` content file, passport, project card, decision
  log, and handoff memory. This skill preserves `.light/`.
- `data-engineering`: data quality, lineage, transformations, storage/release
  design. This skill only records the chosen storage policy.
- `experiment-coding`: run manifest, executable code, environment, and
  reproducibility evidence. A tidy tree is not a reproducible run.
- `file-reading`: understand supplied material and repositories; it does not
  move files for this lifecycle.
- `orchestrator`: consume state if useful. Project structure remains an
  off-DAG overlay with no `STAGE_GATES`, `ROUTES`, findings, or back-edge.
