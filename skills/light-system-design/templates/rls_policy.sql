-- EXAMPLE ONLY; PostgreSQL 18 syntax, not a security verdict.
-- Assumption: the application sets app.tenant_id with SET LOCAL inside each
-- transaction and runtime roles do not have BYPASSRLS or table ownership.
-- Test with the actual runtime role before claiming tenant isolation.

ALTER TABLE experiment ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiment FORCE ROW LEVEL SECURITY;

CREATE POLICY experiment_tenant_select ON experiment
  FOR SELECT TO app_runtime
  USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::bigint
  );

CREATE POLICY experiment_tenant_write ON experiment
  FOR ALL TO app_runtime
  USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::bigint
  )
  WITH CHECK (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::bigint
  );

-- The example assumes experiment_tenant_idx exists. It does not benchmark the
-- policy, validate connection-pool session hygiene, or replace security review.
