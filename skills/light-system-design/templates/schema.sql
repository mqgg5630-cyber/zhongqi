-- EXAMPLE ONLY; not production-ready.
-- Dialect: PostgreSQL 18. Adapt only after the database decision.
-- Context: minimal shared-table multi-tenant example.
-- Validate against the selected server, access paths, retention, and roles.

CREATE TABLE tenant (
    tenant_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE experiment (
    experiment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id bigint NOT NULL REFERENCES tenant(tenant_id),
    public_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'running', 'complete')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, public_name)
);

CREATE INDEX experiment_tenant_idx ON experiment(tenant_id);

-- This example does not prove that the index serves real query shapes.
-- RLS, retention, PII fields, triggers, and migration history are intentionally
-- absent until the project supplies those requirements.
