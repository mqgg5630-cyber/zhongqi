#!/usr/bin/env python3
"""Dialect/context-scoped heuristic review for schema specs and migration SQL.

The SQL path includes a lexical scanner for comments, strings, dollar-quoted
bodies, quoted identifiers, and multiple statements. It is still not a SQL
parser, catalog diff, query planner, lock simulator, or zero-downtime proof.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from er_diagram import load_spec
except Exception:
    load_spec = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SEVERITIES = ("critical", "major", "review", "minor")
VOLATILE_FUNCTIONS = (
    "random",
    "clock_timestamp",
    "timeofday",
    "gen_random_uuid",
    "uuid_generate_v1",
    "uuid_generate_v4",
    "nextval",
)


@dataclass
class Statement:
    raw: str
    code: str
    line: int

    @property
    def flat(self) -> str:
        return re.sub(r"\s+", " ", self.code).strip()

    @property
    def upper(self) -> str:
        return self.flat.upper()


def _mask_range(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = " "


def scan_statements(sql: str) -> tuple[list[Statement], list[dict[str, Any]]]:
    """Split only on semicolons in normal lexical state and mask non-code text."""
    masked = list(sql)
    issues: list[dict[str, Any]] = []
    boundaries: list[tuple[int, int, int]] = []
    index = 0
    start = 0
    line = 1
    start_line = 1
    length = len(sql)

    while index < length:
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            end = length if end < 0 else end
            _mask_range(masked, index, end)
            index = end
            continue
        if sql.startswith("/*", index):
            block_start = index
            depth = 1
            index += 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    if sql[index] == "\n":
                        line += 1
                    index += 1
            _mask_range(masked, block_start, index)
            if depth:
                issues.append(
                    {
                        "line": start_line,
                        "code": "LEX-UNCLOSED-BLOCK-COMMENT",
                        "severity": "major",
                        "message": "Unclosed block comment; later lint results are unreliable.",
                    }
                )
            continue
        char = sql[index]
        if char == "'":
            token_start = index
            index += 1
            closed = False
            while index < length:
                if sql[index] == "\n":
                    line += 1
                if sql[index] == "'":
                    if index + 1 < length and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    closed = True
                    break
                index += 1
            _mask_range(masked, token_start, index)
            if not closed:
                issues.append(
                    {
                        "line": start_line,
                        "code": "LEX-UNCLOSED-STRING",
                        "severity": "major",
                        "message": "Unclosed SQL string; later lint results are unreliable.",
                    }
                )
            continue
        if char == '"':
            token_start = index
            index += 1
            closed = False
            while index < length:
                if sql[index] == "\n":
                    line += 1
                if sql[index] == '"':
                    if index + 1 < length and sql[index + 1] == '"':
                        index += 2
                        continue
                    index += 1
                    closed = True
                    break
                index += 1
            _mask_range(masked, token_start, index)
            if not closed:
                issues.append(
                    {
                        "line": start_line,
                        "code": "LEX-UNCLOSED-QUOTED-IDENTIFIER",
                        "severity": "major",
                        "message": "Unclosed quoted identifier.",
                    }
                )
            continue
        if char == "`":
            token_start = index
            index += 1
            closed = False
            while index < length:
                if sql[index] == "\n":
                    line += 1
                if sql[index] == "`":
                    if index + 1 < length and sql[index + 1] == "`":
                        index += 2
                        continue
                    index += 1
                    closed = True
                    break
                index += 1
            _mask_range(masked, token_start, index)
            if not closed:
                issues.append(
                    {
                        "line": sql.count("\n", 0, token_start) + 1,
                        "code": "LEX-UNCLOSED-BACKTICK-IDENTIFIER",
                        "severity": "major",
                        "message": "Unclosed backtick-quoted identifier.",
                    }
                )
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if match:
                delimiter = match.group(0)
                token_start = index
                body_start = index + len(delimiter)
                end = sql.find(delimiter, body_start)
                if end < 0:
                    index = length
                    issues.append(
                        {
                            "line": start_line,
                            "code": "LEX-UNCLOSED-DOLLAR-QUOTE",
                            "severity": "major",
                            "message": "Unclosed dollar-quoted body.",
                        }
                    )
                else:
                    segment = sql[index : end + len(delimiter)]
                    line += segment.count("\n")
                    index = end + len(delimiter)
                _mask_range(masked, token_start, index)
                continue
        if char == ";":
            boundaries.append((start, index, start_line))
            index += 1
            start = index
            start_line = line
            continue
        if char == "\n":
            line += 1
        index += 1

    if start < length:
        boundaries.append((start, length, start_line))
    statements = []
    masked_text = "".join(masked)
    for begin, end, _statement_line in boundaries:
        code = masked_text[begin:end]
        if code.strip():
            first_code = next(
                offset for offset, value in enumerate(code) if not value.isspace()
            )
            statement_line = sql.count("\n", 0, begin + first_code) + 1
            statements.append(Statement(sql[begin:end].strip(), code, statement_line))
    return statements, issues


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:3]) if parts else None


def _online_risk(context: dict[str, Any]) -> bool | None:
    required = context.get("write_availability_required", "UNKNOWN")
    rows = context.get("table_rows", "UNKNOWN")
    if required is True:
        return True
    if isinstance(rows, int) and rows >= 100_000:
        return True
    if required is False and isinstance(rows, int):
        return False
    return None


def _issue(
    statement: Statement | None,
    code: str,
    severity: str,
    message: str,
    dialect: str,
    premise: str,
) -> dict[str, Any]:
    return {
        "line": statement.line if statement else 1,
        "loc": statement.raw[:100].replace("\n", " ") if statement else "input",
        "code": code,
        "severity": severity,
        "message": message,
        "dialect": dialect,
        "premise": premise,
    }


def _risk_severity(context: dict[str, Any]) -> str:
    risk = _online_risk(context)
    return "major" if risk is True else "review"


def lint_ddl(
    sql: str,
    dialect: str = "generic",
    server_version: str | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = dict(context or {})
    dialect = dialect.lower()
    if dialect not in {"generic", "postgresql", "sqlite", "mysql"}:
        raise ValueError(f"unsupported dialect: {dialect}")
    version = _version_tuple(server_version)
    statements, lexical = scan_statements(sql)
    issues = [
        _issue(
            None,
            item["code"],
            item["severity"],
            item["message"],
            dialect,
            "lexical scan",
        )
        for item in lexical
    ]
    explicit_transaction = False
    context_transaction = context.get("transaction_mode", "UNKNOWN")

    for statement in statements:
        upper = statement.upper
        if re.match(r"^(BEGIN|START TRANSACTION)\b", upper):
            explicit_transaction = True
            continue
        if re.match(r"^(COMMIT|ROLLBACK)\b", upper):
            explicit_transaction = False
            continue

        if re.search(r"\bDROP\s+TABLE\b", upper):
            issues.append(
                _issue(
                    statement,
                    "DROP-TABLE",
                    "critical",
                    "DROP TABLE is destructive. Require dependency inventory, "
                    "backup/retention evidence, compatibility closure, and explicit authorization.",
                    dialect,
                    "data and dependent objects may be removed",
                )
            )
        if re.search(r"\bDROP\s+COLUMN\b", upper):
            detail = (
                "SQLite rewrites stored rows for DROP COLUMN."
                if dialect == "sqlite"
                else "Column data and old-client compatibility can be lost."
            )
            issues.append(
                _issue(
                    statement,
                    "DROP-COLUMN",
                    "critical",
                    f"DROP COLUMN is destructive. {detail} Use an authorized contract "
                    "phase only after compatibility and rollback evidence.",
                    dialect,
                    "destructive change",
                )
            )
        if re.search(r"\bRENAME\s+COLUMN\b", upper):
            issues.append(
                _issue(
                    statement,
                    "RENAME-COLUMN-COMPAT",
                    "major",
                    "A metadata rename can still break old clients, queries, views, or "
                    "generated code. Inventory consumers and use a compatibility phase.",
                    dialect,
                    "existing consumers are possible",
                )
            )
        if re.search(r"\bALTER\s+TABLE\b.*\bRENAME\s+TO\b", upper):
            issues.append(
                _issue(
                    statement,
                    "RENAME-TABLE-COMPAT",
                    "major",
                    "A table rename can break consumers and dependent objects; verify "
                    "dialect/version propagation and compatibility.",
                    dialect,
                    "existing consumers are possible",
                )
            )
        if re.search(r"\bDROP\s+NOT\s+NULL\b", upper):
            issues.append(
                _issue(
                    statement,
                    "DROP-NOT-NULL-COMPAT",
                    "minor",
                    "Downstream readers may rely on non-null values; review compatibility.",
                    dialect,
                    "contract may rely on non-null",
                )
            )

        if re.match(
            r"^(DO|EXECUTE|CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE))\b",
            upper,
        ) or re.search(
            r"\bEXECUTE\s*$", upper
        ):
            issues.append(
                _issue(
                    statement,
                    "DYNAMIC-SQL-UNINSPECTED",
                    "review",
                    "Dynamic or procedural SQL body was lexically masked and not inspected.",
                    dialect,
                    "heuristic scanner does not parse generated SQL",
                )
            )

        if dialect == "postgresql":
            in_transaction = explicit_transaction or context_transaction == "always"
            if re.match(r"^CREATE\s+(UNIQUE\s+)?INDEX\b", upper):
                concurrent = bool(re.match(
                    r"^CREATE\s+(UNIQUE\s+)?INDEX\s+CONCURRENTLY\b", upper
                ))
                if concurrent and in_transaction:
                    issues.append(
                        _issue(
                            statement,
                            "CONCURRENT-INDEX-IN-TRANSACTION",
                            "major",
                            "PostgreSQL CREATE INDEX CONCURRENTLY cannot run inside "
                            "a transaction block; this migration will fail.",
                            dialect,
                            "explicit BEGIN or context.transaction_mode=always",
                        )
                    )
                elif concurrent and context_transaction == "UNKNOWN":
                    issues.append(
                        _issue(
                            statement,
                            "CONCURRENT-INDEX-TXN-UNKNOWN",
                            "review",
                            "Confirm the migration runner does not wrap this command in a transaction.",
                            dialect,
                            "transaction_mode is UNKNOWN",
                        )
                    )
                elif not concurrent:
                    severity = _risk_severity(context)
                    issues.append(
                        _issue(
                            statement,
                            "INDEX-WRITE-BLOCK-REVIEW",
                            severity,
                            "A regular PostgreSQL index build blocks writes. Choose "
                            "CONCURRENTLY only after considering its extra work, failure "
                            "caveats, partitioning, and transaction restrictions.",
                            dialect,
                            "online/size context determines impact",
                        )
                    )

            add_column = bool(
                re.search(
                    r"\bADD\s+(?:COLUMN\s+)?"
                    r"(?!(?:CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK|EXCLUDE)\b)",
                    upper,
                )
            )
            has_default = bool(re.search(r"\bDEFAULT\b", upper))
            if add_column and has_default:
                volatile = [
                    function
                    for function in VOLATILE_FUNCTIONS
                    if re.search(rf"\b{re.escape(function)}\s*\(", statement.code, re.I)
                ]
                if volatile:
                    issues.append(
                        _issue(
                            statement,
                            "ADD-COLUMN-VOLATILE-DEFAULT",
                            _risk_severity(context),
                            "Volatile default expression is evaluated for existing rows and "
                            f"may rewrite the table: {volatile}. Rehearse on target data/version.",
                            dialect,
                            "function volatility list is conservative and incomplete",
                        )
                    )
                elif version is None:
                    issues.append(
                        _issue(
                            statement,
                            "ADD-COLUMN-DEFAULT-VERSION-UNKNOWN",
                            "review",
                            "Target PostgreSQL version is UNKNOWN. The constant-default "
                            "no-rewrite optimization starts in PostgreSQL 11.",
                            dialect,
                            "server_version not supplied",
                        )
                    )
                elif version < (11,):
                    issues.append(
                        _issue(
                            statement,
                            "ADD-COLUMN-DEFAULT-PRE11",
                            _risk_severity(context),
                            "Before PostgreSQL 11, adding a non-null default can rewrite "
                            "the table. Rehearse with target size and lock budget.",
                            dialect,
                            f"server_version={server_version}",
                        )
                    )

            if (
                add_column
                and re.search(r"\bNOT\s+NULL\b", upper)
                and not has_default
            ):
                issues.append(
                    _issue(
                        statement,
                        "ADD-COLUMN-NOT-NULL-NO-DEFAULT",
                        "major",
                        "Existing rows cannot satisfy a new NOT NULL column without a "
                        "value/backfill. Use an additive nullable phase first.",
                        dialect,
                        "existing table may contain rows",
                    )
                )

            if re.search(r"\bADD\s+CONSTRAINT\b", upper) and re.search(
                r"\b(FOREIGN\s+KEY|CHECK)\b", upper
            ) and "NOT VALID" not in upper:
                issues.append(
                    _issue(
                        statement,
                        "CONSTRAINT-VALIDATION-REVIEW",
                        _risk_severity(context),
                        "PostgreSQL will validate existing rows while adding this CHECK/FK. "
                        "Consider NOT VALID then VALIDATE, with measured lock/scan impact.",
                        dialect,
                        "NOT VALID is available only for CHECK/FK",
                    )
                )
            if re.search(r"\bVALIDATE\s+CONSTRAINT\b", upper):
                issues.append(
                    _issue(
                        statement,
                        "VALIDATE-CONSTRAINT-REHEARSE",
                        "review",
                        "VALIDATE scans existing rows and acquires documented locks; "
                        "schedule and measure it rather than calling it lock-free.",
                        dialect,
                        "target table size and concurrency are not simulated",
                    )
                )
            if re.search(r"\bSET\s+NOT\s+NULL\b", upper):
                proven = context.get("validated_not_null_check", "UNKNOWN")
                severity = (
                    "review"
                    if proven is True
                    else _risk_severity(context)
                )
                issues.append(
                    _issue(
                        statement,
                        "SET-NOT-NULL-REHEARSE",
                        severity,
                        "A valid CHECK proving non-null can skip the scan, but SET NOT NULL "
                        "still needs target-version lock/rehearsal evidence.",
                        dialect,
                        f"validated_not_null_check={proven}",
                    )
                )
            if re.search(
                r"\bALTER\s+(COLUMN\s+)?[A-Z0-9_]*\s+(SET\s+DATA\s+)?TYPE\b",
                upper,
            ):
                issues.append(
                    _issue(
                        statement,
                        "ALTER-TYPE-REHEARSE",
                        _risk_severity(context),
                        "ALTER TYPE behavior depends on source/target types, USING "
                        "expression, indexes, and version. A regex cannot decide rewrite/lock safety.",
                        dialect,
                        "type coercion/catalog context unavailable",
                    )
                )

        elif dialect == "sqlite":
            if "CONCURRENTLY" in upper:
                issues.append(
                    _issue(
                        statement,
                        "SQLITE-UNSUPPORTED-CONCURRENTLY",
                        "major",
                        "SQLite does not support CREATE INDEX CONCURRENTLY.",
                        dialect,
                        "SQLite grammar",
                    )
                )
            if re.search(r"\bALTER\s+(COLUMN\s+)?", upper) and re.search(
                r"\b(SET|DROP)\s+NOT\s+NULL\b", upper
            ):
                if version is None or version < (3, 53, 0):
                    issues.append(
                        _issue(
                            statement,
                            "SQLITE-ALTER-COLUMN-VERSION",
                            "major",
                            "SQLite ALTER COLUMN nullability requires SQLite 3.53.0+; "
                            "older versions need a tested create-copy-drop-rename procedure.",
                            dialect,
                            f"server_version={server_version or 'UNKNOWN'}",
                        )
                    )

    return issues


def _has_key(column: dict[str, Any], target: str) -> bool:
    tokens = str(column.get("key", "")).replace("/", ",").split(",")
    return target in {token.strip().upper() for token in tokens}


def lint_spec(
    spec: dict[str, Any], dialect: str = "generic"
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    entities = spec.get("entities", {})
    if not isinstance(entities, dict):
        raise ValueError("spec.entities must be an object")
    for name, raw_entity in entities.items():
        entity = raw_entity or {}
        columns = entity.get("columns", [])
        names = [column.get("name") for column in columns]
        indexes = set(entity.get("indexes", []) or [])
        primary = {column.get("name") for column in columns if _has_key(column, "PK")}
        if not primary:
            severity = "major" if entity.get("requires_row_identity") is True else "review"
            issues.append(
                {
                    "line": 1,
                    "loc": f"entity:{name}",
                    "code": "ROW-IDENTITY-REVIEW",
                    "severity": severity,
                    "message": "No primary key is declared. Confirm whether stable row "
                    "identity is required; append-only/event tables may be intentional exceptions.",
                    "dialect": dialect,
                    "premise": f"requires_row_identity={entity.get('requires_row_identity', 'UNKNOWN')}",
                }
            )
        for column in columns:
            if (_has_key(column, "FK") or column.get("fk_to")) and column.get(
                "name"
            ) not in indexes | primary:
                issues.append(
                    {
                        "line": 1,
                        "loc": f"{name}.{column.get('name')}",
                        "code": "FK-INDEX-ACCESS-PATH-REVIEW",
                        "severity": "review",
                        "message": "No index is declared for this FK column. Map it to "
                        "actual joins, parent updates/deletes, and write cost before adding one.",
                        "dialect": dialect,
                        "premise": "index need depends on real access paths",
                    }
                )
        if entity.get("requires_audit") is True:
            missing = [
                column for column in ("created_at", "updated_at") if column not in names
            ]
            if missing:
                issues.append(
                    {
                        "line": 1,
                        "loc": f"entity:{name}",
                        "code": "AUDIT-FIELDS-REQUIRED",
                        "severity": "major",
                        "message": f"Declared audit requirement lacks fields: {missing}.",
                        "dialect": dialect,
                        "premise": "requires_audit=true",
                    }
                )
        policies = entity.get("policies", []) or []
        if dialect == "postgresql" and entity.get("rls") is True and not policies:
            issues.append(
                {
                    "line": 1,
                    "loc": f"entity:{name}",
                    "code": "RLS-NO-POLICY",
                    "severity": "major",
                    "message": "PostgreSQL RLS is enabled with no declared policy, so "
                    "ordinary access is default-deny. Owners/BYPASSRLS behavior still "
                    "requires actual-role testing.",
                    "dialect": dialect,
                    "premise": "rls=true and policies empty",
                }
            )
        for policy in policies:
            for column in policy.get("on_columns", []) or []:
                if column not in indexes | primary:
                    issues.append(
                        {
                            "line": 1,
                            "loc": f"{name}.policy:{policy.get('name', 'UNKNOWN')}",
                            "code": "POLICY-ACCESS-PATH-REVIEW",
                            "severity": "review",
                            "message": f"Policy column {column!r} has no declared index. "
                            "Benchmark the real predicate/role/data distribution.",
                            "dialect": dialect,
                            "premise": "no universal performance number is assumed",
                        }
                    )
        sensitive = [
            column.get("name")
            for column in columns
            if str(column.get("sensitive", "")).lower() in {"pii", "phi"}
        ]
        if sensitive and not entity.get("access_control"):
            issues.append(
                {
                    "line": 1,
                    "loc": f"entity:{name}",
                    "code": "SENSITIVE-ACCESS-CONTROL-UNKNOWN",
                    "severity": "review",
                    "message": f"Sensitive fields {sensitive} have no declared access-control "
                    "design. This is a pending design/specialist review, not an ethics verdict.",
                    "dialect": dialect,
                    "premise": "access_control absent",
                }
            )
    return issues


def aggregate(
    issues: list[dict[str, Any]],
    target: str,
    dialect: str,
    server_version: str | None,
) -> dict[str, Any]:
    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        counts[issue["severity"]] += 1
    return {
        "schema": "light.system-design.v2.schema-lint",
        "target": target,
        "dialect": dialect,
        "server_version": server_version or "UNKNOWN",
        "issue_count": len(issues),
        "by_severity": counts,
        "issues": issues,
        "limitation": (
            "Lexical/regex heuristic only; not a SQL parser, catalog diff, "
            "query planner, lock simulator, execution test, or zero-downtime proof."
        ),
    }


def to_markdown(report: dict[str, Any]) -> str:
    counts = report["by_severity"]
    lines = [
        f"# Schema/migration heuristic: {report['target']}",
        "",
        f"- Dialect: `{report['dialect']}`",
        f"- Server version: `{report['server_version']}`",
        "- Issues: "
        + ", ".join(f"{key}={counts[key]}" for key in SEVERITIES),
        "",
    ]
    for issue in report["issues"]:
        lines.append(
            f"- [{issue['severity']}] {issue['code']} line {issue['line']}: "
            f"{issue['message']} Premise: {issue['premise']}"
        )
    if not report["issues"]:
        lines.append("- No configured heuristic matched.")
    lines.extend(["", f"> {report['limitation']}"])
    return "\n".join(lines)


def _selftest() -> int:
    noise = r"""
    -- DROP TABLE not_real;
    /* nested /* DROP COLUMN x */ comment */
    SELECT 'ALTER TABLE t DROP COLUMN x';
    SELECT "DROP TABLE";
    WITH x AS (SELECT 'CREATE INDEX idx ON t(c)') SELECT * FROM x;
    DO $$ BEGIN EXECUTE 'DROP TABLE dynamic_name'; END $$;
    """
    issues = lint_ddl(noise, "postgresql", "18", {})
    codes = [issue["code"] for issue in issues]
    assert "DROP-TABLE" not in codes and "DROP-COLUMN" not in codes, codes
    assert codes == ["DYNAMIC-SQL-UNINSPECTED"], codes

    quoted = "SELECT * FROM `DROP TABLE`; ALTER TABLE t DROP COLUMN `RENAME COLUMN`;"
    quoted_issues = lint_ddl(quoted, "mysql")
    assert [item["code"] for item in quoted_issues] == ["DROP-COLUMN"], quoted_issues
    quoted_statements, _ = scan_statements("\n\nSELECT 1;\n\nDROP TABLE t;")
    assert [item.line for item in quoted_statements] == [3, 5]

    function_issues = lint_ddl(
        "CREATE FUNCTION f() RETURNS void AS $$ BEGIN EXECUTE 'DROP TABLE t'; "
        "END $$ LANGUAGE plpgsql;",
        "postgresql",
        "18",
    )
    assert "DYNAMIC-SQL-UNINSPECTED" in {
        item["code"] for item in function_issues
    }

    destructive = """
    DROP TABLE legacy;
    ALTER TABLE runs DROP COLUMN secret;
    ALTER TABLE runs RENAME COLUMN name TO title;
    """
    codes = {item["code"] for item in lint_ddl(destructive, "generic")}
    assert {"DROP-TABLE", "DROP-COLUMN", "RENAME-COLUMN-COMPAT"} <= codes

    pg = """
    BEGIN;
    CREATE INDEX CONCURRENTLY runs_tenant_idx ON runs(tenant_id);
    COMMIT;
    ALTER TABLE runs ADD COLUMN token uuid DEFAULT gen_random_uuid();
    ALTER TABLE runs ADD COLUMN created_at timestamptz DEFAULT now();
    ALTER TABLE runs ADD CONSTRAINT runs_fk FOREIGN KEY(tenant_id)
      REFERENCES tenant(id) NOT VALID;
    ALTER TABLE runs VALIDATE CONSTRAINT runs_fk;
    ALTER TABLE runs ALTER COLUMN title SET NOT NULL;
    """
    pg_issues = lint_ddl(
        pg,
        "postgresql",
        "18",
        {
            "write_availability_required": True,
            "table_rows": 500_000,
            "transaction_mode": "explicit",
        },
    )
    pg_codes = {item["code"] for item in pg_issues}
    assert "CONCURRENT-INDEX-IN-TRANSACTION" in pg_codes
    assert "ADD-COLUMN-VOLATILE-DEFAULT" in pg_codes
    assert "ADD-COLUMN-DEFAULT-PRE11" not in pg_codes
    assert "CONSTRAINT-VALIDATION-REVIEW" not in pg_codes
    assert "VALIDATE-CONSTRAINT-REHEARSE" in pg_codes
    assert "SET-NOT-NULL-REHEARSE" in pg_codes
    assert not any(
        item["code"] == "ADD-COLUMN-VOLATILE-DEFAULT"
        and "created_at" in item["loc"]
        for item in pg_issues
    ), pg_issues

    pre11 = lint_ddl(
        "ALTER TABLE t ADD COLUMN c integer DEFAULT 0;",
        "postgresql",
        "10",
        {"table_rows": 1_000_000},
    )
    assert "ADD-COLUMN-DEFAULT-PRE11" in {item["code"] for item in pre11}

    sqlite_issues = lint_ddl(
        "CREATE INDEX CONCURRENTLY i ON t(c); "
        "ALTER TABLE t ALTER COLUMN c SET NOT NULL;",
        "sqlite",
        "3.45.3",
    )
    sqlite_codes = {item["code"] for item in sqlite_issues}
    assert "SQLITE-UNSUPPORTED-CONCURRENTLY" in sqlite_codes
    assert "SQLITE-ALTER-COLUMN-VERSION" in sqlite_codes

    spec = {
        "entities": {
            "run": {
                "requires_row_identity": True,
                "requires_audit": True,
                "rls": True,
                "columns": [
                    {"name": "tenant_id", "key": "FK", "sensitive": "pii"}
                ],
            }
        }
    }
    spec_codes = {
        item["code"] for item in lint_spec(spec, dialect="postgresql")
    }
    assert {
        "ROW-IDENTITY-REVIEW",
        "FK-INDEX-ACCESS-PATH-REVIEW",
        "AUDIT-FIELDS-REQUIRED",
        "RLS-NO-POLICY",
        "SENSITIVE-ACCESS-CONTROL-UNKNOWN",
    } <= spec_codes

    report = aggregate(pg_issues, "selftest.sql", "postgresql", "18")
    assert report["by_severity"]["major"] > 0
    assert "not a SQL parser" in report["limitation"]
    print("[selftest] PASS schema_lint")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dialect/context-scoped schema and migration heuristic"
    )
    parser.add_argument("--spec")
    parser.add_argument("--ddl")
    parser.add_argument(
        "--dialect",
        choices=("generic", "postgresql", "sqlite", "mysql"),
        default="generic",
    )
    parser.add_argument("--server-version")
    parser.add_argument("--context", help="JSON object with table/transaction context")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest or (not args.spec and not args.ddl):
        return _selftest()
    try:
        context = {}
        if args.context:
            context = json.loads(Path(args.context).read_text(encoding="utf-8"))
            if not isinstance(context, dict):
                raise ValueError("--context must contain a JSON object")
        issues: list[dict[str, Any]] = []
        targets = []
        if args.spec:
            if load_spec is None:
                raise RuntimeError("er_diagram.load_spec is unavailable")
            path = Path(args.spec).expanduser().resolve()
            fmt = "json" if path.suffix.lower() == ".json" else "yaml"
            spec = load_spec(path.read_text(encoding="utf-8"), fmt)
            issues.extend(lint_spec(spec, args.dialect))
            targets.append(str(path))
        if args.ddl:
            path = Path(args.ddl).expanduser().resolve()
            issues.extend(
                lint_ddl(
                    path.read_text(encoding="utf-8"),
                    args.dialect,
                    args.server_version,
                    context,
                )
            )
            targets.append(str(path))
        report = aggregate(
            issues, "+".join(targets), args.dialect, args.server_version
        )
        print(
            json.dumps(report, ensure_ascii=False, indent=2)
            if args.json
            else to_markdown(report)
        )
        return (
            1
            if report["by_severity"]["critical"]
            or report["by_severity"]["major"]
            else 0
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
