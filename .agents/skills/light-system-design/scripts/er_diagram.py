#!/usr/bin/env python3
"""Validate a schema spec and render deterministic Mermaid erDiagram text.

JSON works with the standard library. YAML requires PyYAML and rejects duplicate
mapping keys. Rendering is a structural view, not a database-schema parser.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

CARD = {
    "one-to-one": "||--||",
    "one-to-many": "||--o{",
    "many-to-one": "}o--||",
    "many-to-many": "}o--o{",
    "zero-or-one": "||--o|",
    "zero-or-many": "|o--o{",
}
KEYS = {"PK", "FK", "UK"}


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_yaml_no_duplicates(text: str) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("YAML input requires PyYAML; JSON remains available") from exc

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict:
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError(f"duplicate YAML key: {key!r}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    return yaml.load(text, Loader=UniqueKeyLoader)


def load_spec(text: str, fmt: str = "auto") -> dict[str, Any]:
    if not text.strip():
        raise ValueError("input is empty")
    fmt = fmt.lower()
    if fmt not in {"auto", "json", "yaml"}:
        raise ValueError(f"unknown format: {fmt}")
    if fmt == "json":
        value = json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    elif fmt == "yaml":
        value = _load_yaml_no_duplicates(text)
    else:
        try:
            value = json.loads(text, object_pairs_hook=_pairs_no_duplicates)
        except json.JSONDecodeError:
            value = _load_yaml_no_duplicates(text)
    if not isinstance(value, dict):
        raise ValueError("spec top level must be an object")
    return value


def _identifier(raw: Any) -> str:
    text = str(raw)
    value = re.sub(r"[^A-Za-z0-9_]", "_", text)
    value = re.sub(r"_+", "_", value).strip("_") or "entity"
    if value[0].isdigit():
        value = "E_" + value
    return value


def _label(raw: Any) -> str:
    text = re.sub(r"\s+", " ", str(raw)).strip()
    return html.escape(text, quote=True).replace("&#x27;", "'")


def _key_tokens(raw: Any) -> list[str]:
    tokens = []
    for token in str(raw or "").replace("/", ",").split(","):
        token = token.strip().upper()
        if token:
            if token not in KEYS:
                raise ValueError(f"unknown column key {token!r}; use PK/FK/UK")
            if token not in tokens:
                tokens.append(token)
    return tokens


def _validate_spec(spec: dict[str, Any], strict: bool) -> tuple[dict, list]:
    entities = spec.get("entities")
    relationships = spec.get("relationships", [])
    if not isinstance(entities, dict) or not entities:
        raise ValueError("spec.entities must be a non-empty object")
    if not isinstance(relationships, list):
        raise ValueError("spec.relationships must be an array")

    identifier_owner: dict[str, str] = {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_entity in entities.items():
        name = str(raw_name)
        identifier = _identifier(name)
        if identifier in identifier_owner and identifier_owner[identifier] != name:
            raise ValueError(
                f"entity names collide after Mermaid normalization: "
                f"{identifier_owner[identifier]!r} and {name!r} -> {identifier!r}"
            )
        identifier_owner[identifier] = name
        if raw_entity is None:
            raw_entity = {}
        if not isinstance(raw_entity, dict):
            raise ValueError(f"entity {name!r} must be an object")
        columns = raw_entity.get("columns", [])
        if not isinstance(columns, list):
            raise ValueError(f"entity {name!r}.columns must be an array")
        seen_columns: set[str] = set()
        normalized_columns = []
        normalized_column_ids: set[str] = set()
        for index, raw_column in enumerate(columns):
            if not isinstance(raw_column, dict):
                raise ValueError(f"entity {name!r} column {index} must be an object")
            column = dict(raw_column)
            column_name = str(column.get("name", "")).strip()
            if not column_name:
                raise ValueError(f"entity {name!r} column {index} has no name")
            if column_name in seen_columns:
                raise ValueError(f"entity {name!r} has duplicate column {column_name!r}")
            seen_columns.add(column_name)
            column_id = _identifier(column_name)
            if column_id in normalized_column_ids:
                raise ValueError(
                    f"entity {name!r} columns collide after normalization: {column_id!r}"
                )
            normalized_column_ids.add(column_id)
            column["_id"] = column_id
            column["_keys"] = _key_tokens(column.get("key"))
            normalized_columns.append(column)
        normalized[name] = {
            "_id": identifier,
            "columns": normalized_columns,
        }

    normalized_rels = []
    for index, raw_rel in enumerate(relationships):
        if not isinstance(raw_rel, dict):
            raise ValueError(f"relationship {index} must be an object")
        if "from" not in raw_rel or "to" not in raw_rel:
            raise ValueError(f"relationship {index} requires from and to")
        source = str(raw_rel["from"])
        target = str(raw_rel["to"])
        missing = [name for name in (source, target) if name not in normalized]
        if missing and strict:
            raise ValueError(
                f"relationship {index} references undefined entities: {missing}"
            )
        cardinality = str(raw_rel.get("type", "one-to-many")).lower()
        if cardinality not in CARD:
            raise ValueError(
                f"relationship {index} has unknown type {cardinality!r}; "
                f"choose from {sorted(CARD)}"
            )
        normalized_rels.append(
            {
                "from": normalized.get(source, {"_id": _identifier(source)})["_id"],
                "to": normalized.get(target, {"_id": _identifier(target)})["_id"],
                "type": cardinality,
                "label": _label(raw_rel.get("label", "relates to")),
            }
        )
    return normalized, normalized_rels


def build_mermaid(spec: dict[str, Any], strict: bool = False) -> str:
    entities, relationships = _validate_spec(spec, strict)
    lines = ["erDiagram"]
    for raw_name, entity in entities.items():
        if raw_name != entity["_id"]:
            lines.append(
                f'    %% entity-map: {entity["_id"]} = "{_label(raw_name)}"'
            )
    for rel in relationships:
        lines.append(
            f'    {rel["from"]} {CARD[rel["type"]]} {rel["to"]} : '
            f'"{rel["label"]}"'
        )
    for raw_name, entity in entities.items():
        lines.append(f'    {entity["_id"]} {{')
        for column in entity["columns"]:
            data_type = _identifier(column.get("type", "string"))
            parts = [f"        {data_type} {column['_id']}"]
            if column["_keys"]:
                parts.append(",".join(column["_keys"]))
            comment_parts = []
            if column.get("comment"):
                comment_parts.append(str(column["comment"]))
            if str(column["name"]) != column["_id"]:
                comment_parts.append(f"source-name={column['name']}")
            line = " ".join(parts)
            if comment_parts:
                line += f' "{_label("; ".join(comment_parts))}"'
            lines.append(line)
        lines.append("    }")
    return "\n".join(lines) + "\n"


def _format_from_path(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "json"
    if path.suffix.lower() in {".yaml", ".yml"}:
        return "yaml"
    return "auto"


def _selftest() -> int:
    spec = {
        "entities": {
            "Research Run": {
                "columns": [
                    {"name": "run id", "type": "integer", "key": "PK"},
                    {
                        "name": "tenant_id",
                        "type": "integer",
                        "key": "FK",
                        "comment": 'owner "tenant"',
                    },
                ]
            },
            "Tenant": {
                "columns": [{"name": "id", "type": "integer", "key": "PK"}]
            },
        },
        "relationships": [
            {
                "from": "Tenant",
                "to": "Research Run",
                "type": "one-to-many",
                "label": 'owns "runs"',
            }
        ],
    }
    output = build_mermaid(spec, strict=True)
    assert output == build_mermaid(spec, strict=True)
    assert 'entity-map: Research_Run = "Research Run"' in output
    assert "Tenant ||--o{ Research_Run" in output
    assert "&quot;runs&quot;" in output
    assert 'source-name=run id' in output

    parsed_json = load_spec(json.dumps(spec), "json")
    assert build_mermaid(parsed_json, strict=True) == output

    try:
        load_spec('{"entities":{"A":{},"A":{}}}', "json")
        raise AssertionError("duplicate JSON entity key must fail")
    except ValueError:
        pass
    try:
        load_spec("entities:\n  A: {}\n  A: {}\n", "yaml")
        raise AssertionError("duplicate YAML entity key must fail")
    except (ValueError, RuntimeError):
        pass
    try:
        build_mermaid(
            {
                "entities": {"A-B": {}, "A B": {}},
                "relationships": [],
            },
            strict=True,
        )
        raise AssertionError("normalized entity collision must fail")
    except ValueError:
        pass
    try:
        build_mermaid(
            {
                "entities": {"A": {"columns": [{"name": "id"}, {"name": "id"}]}},
                "relationships": [],
            },
            strict=True,
        )
        raise AssertionError("duplicate columns must fail")
    except ValueError:
        pass
    try:
        build_mermaid(
            {
                "entities": {"A": {}},
                "relationships": [{"from": "A", "to": "Missing"}],
            },
            strict=True,
        )
        raise AssertionError("strict dangling endpoint must fail")
    except ValueError:
        pass
    for bad in ("", "[]", "{}"):
        try:
            build_mermaid(load_spec(bad), strict=True)
            raise AssertionError(f"bad input must fail: {bad!r}")
        except (ValueError, json.JSONDecodeError):
            pass

    repo_root = Path(__file__).resolve()
    while repo_root != repo_root.parent and not (
        repo_root / "skills" / "light-system-design"
    ).exists():
        repo_root = repo_root.parent
    e2e_root = repo_root / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="light-er-diagram-", dir=e2e_root))
    try:
        nested = base / "windows style folder"
        nested.mkdir()
        input_path = nested / "schema.json"
        output_path = nested / "diagram.mmd"
        input_path.write_text(json.dumps(spec), encoding="utf-8")
        rendered = build_mermaid(
            load_spec(input_path.read_text(encoding="utf-8"), "json"), strict=True
        )
        output_path.write_text(rendered, encoding="utf-8")
        first = output_path.read_bytes()
        output_path.write_text(rendered, encoding="utf-8")
        assert output_path.read_bytes() == first
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print("[selftest] PASS er_diagram")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate YAML/JSON schema spec and render Mermaid erDiagram"
    )
    parser.add_argument("--in", dest="infile")
    parser.add_argument("--out", dest="outfile")
    parser.add_argument("--format", choices=("auto", "json", "yaml"), default="auto")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.infile:
        parser.error("provide --in or --selftest")
    try:
        source = Path(args.infile).expanduser().resolve()
        fmt = args.format if args.format != "auto" else _format_from_path(source)
        spec = load_spec(source.read_text(encoding="utf-8"), fmt)
        rendered = build_mermaid(spec, strict=args.strict)
        if args.outfile:
            target = Path(args.outfile).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            print(f"wrote {target}")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
