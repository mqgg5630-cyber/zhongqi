-- EXAMPLE ONLY; not a one-shot production migration.
-- Dialect/context: PostgreSQL 18, existing experiment table.
-- Each phase is a separately deployed action with verification and rollback.

-- ACTION PG-EXPAND-001: additive nullable column.
ALTER TABLE experiment ADD COLUMN title text;

-- Application phase: deploy dual-write for public_name and title.
-- Backfill phase: run bounded batches from an application job; do not place an
-- unbounded UPDATE here and pretend its runtime/lock impact is known.

-- ACTION PG-CONSTRAINT-002: after backfill, prevent new nulls without validating
-- all old rows in the same step.
ALTER TABLE experiment
  ADD CONSTRAINT experiment_title_nn CHECK (title IS NOT NULL) NOT VALID;

-- ACTION PG-VALIDATE-003: rehearse on the target version/data shape.
ALTER TABLE experiment VALIDATE CONSTRAINT experiment_title_nn;

-- ACTION PG-CONTRACT-004: may skip the scan when the validated CHECK proves
-- non-null, but still requires the target-version lock/rehearsal decision.
ALTER TABLE experiment ALTER COLUMN title SET NOT NULL;

-- Destructive removal/rename of public_name is intentionally omitted. Add it
-- only after every client has crossed the compatibility window and the user
-- authorizes a separately reversible/backup-backed contract action.
