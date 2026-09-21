# System design technical references

Use this file only after selecting the relevant dialect/protocol branch. It is
an index of constraints and primary sources, not a frozen technology catalog.
Recheck version-sensitive claims on the day they are used.

## PostgreSQL migration facts

- PostgreSQL 11 introduced the optimization that avoids rewriting every row
  when adding a column with a non-null **constant** default. Volatile defaults
  still require per-row evaluation. Check the target major version and the
  expression volatility before classifying risk.
- `CREATE INDEX CONCURRENTLY` avoids blocking ordinary writes but performs more
  work, has failure/invalid-index caveats, and cannot run inside a transaction
  block. It is not a universal “safe index” switch.
- `NOT VALID` applies to PostgreSQL `CHECK` and foreign-key constraints, not to
  every constraint type. `VALIDATE CONSTRAINT` still scans existing rows and
  acquires a documented lock.
- A validated `CHECK (col IS NOT NULL)` can let `SET NOT NULL` skip the table
  scan. This does not mean “no lock” or “zero downtime.”
- RLS without an applicable policy is default-deny for ordinary access, while
  superusers, `BYPASSRLS`, and normally table owners have bypass behavior.
  Test with the actual runtime role; file presence proves neither isolation nor
  performance.

Primary sources, checked 2026-07-03:

- <https://www.postgresql.org/docs/11/release-11.html>
- <https://www.postgresql.org/docs/18/ddl-alter.html>
- <https://www.postgresql.org/docs/18/sql-altertable.html>
- <https://www.postgresql.org/docs/18/sql-createindex.html>
- <https://www.postgresql.org/docs/18/ddl-rowsecurity.html>

## SQLite migration facts

SQLite has its own ALTER TABLE surface and version history. As of the official
page updated 2026-06-03, direct operations include rename table/column, add
column, drop column, and (from SQLite 3.53.0) limited ALTER COLUMN nullability.
Other changes commonly require create-copy-drop-rename inside a tested
transaction plus foreign-key and integrity checks.

Do not apply PostgreSQL `CONCURRENTLY`, `NOT VALID`, RLS, lock, or volatility
rules to SQLite.

Primary sources, checked 2026-07-03:

- <https://sqlite.org/lang_altertable.html>
- <https://sqlite.org/lang_transaction.html>

## OpenAPI contract facts

The latest published OpenAPI version is 3.2.0 (2025-09-19). A project may still
choose 3.0.x or 3.1.x because validator/generator support is part of the actual
constraint set. YAML parsing proves only syntax. Even the official schemas do
not guarantee detection of every specification violation; preserve the exact
validator and version used.

Primary sources, checked 2026-07-03:

- <https://spec.openapis.org/oas/latest.html>
- <https://spec.openapis.org/oas/>
- <https://github.com/python-openapi/openapi-spec-validator>

## Reliability questions

For each asynchronous edge, record:

- producer/consumer owners and contract version;
- delivery semantics actually provided by the transport;
- idempotency key, deduplication store, and retention window;
- transaction/outbox or compensation boundary;
- ordering scope and what happens outside it;
- timeout, retry budget, jitter, circuit breaker, and dead-letter handling;
- backpressure signal and overload behavior;
- replay, poison-message, partial-failure, and observability plan.

Do not label a flow exactly-once unless the claim is scoped to a named boundary
and proven by the selected system. Prefer describing observable duplicate and
recovery behavior.

## Security and privacy boundary

Record threat surfaces, trust boundaries, secret handling, PII classification,
tenant isolation, authorization checks, audit requirements, and deletion/
retention behavior. System design can propose controls and test plans. Route
final security, legal, privacy, and research-ethics judgments to the relevant
specialist/authority.
