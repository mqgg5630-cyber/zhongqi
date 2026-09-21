#!/usr/bin/env python3
"""Validate OpenAPI with a real validator and check request/response examples.

YAML parsing or a few structural checks are never reported as full contract
validation. If openapi-spec-validator is unavailable, status is STRUCTURE_ONLY
and the command exits 2.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from er_diagram import load_spec  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _pointer(root: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref is supported for example checks: {ref}")
    value = root
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise ValueError(f"unresolved local $ref: {ref}")
        value = value[token]
    return value


def _expand_schema(
    schema: Any, root: dict[str, Any], stack: tuple[str, ...] = ()
) -> Any:
    if isinstance(schema, list):
        return [_expand_schema(item, root, stack) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in stack:
            return {"$ref": ref}
        target = _expand_schema(_pointer(root, ref), root, stack + (ref,))
        if not isinstance(target, dict):
            raise ValueError(f"schema $ref is not an object: {ref}")
        merged = dict(target)
        for key, value in schema.items():
            if key != "$ref":
                merged[key] = _expand_schema(value, root, stack)
        return merged
    return {key: _expand_schema(value, root, stack) for key, value in schema.items()}


def _media_examples(
    media: dict[str, Any], location: str
) -> Iterator[tuple[str, Any, Any]]:
    schema = media.get("schema")
    if not isinstance(schema, dict):
        return
    if "example" in media:
        yield f"{location}.example", schema, media["example"]
    examples = media.get("examples", {})
    if isinstance(examples, dict):
        for name, raw in examples.items():
            if isinstance(raw, dict) and "$ref" not in raw and "value" in raw:
                yield f"{location}.examples.{name}", schema, raw["value"]


def _inline_examples(
    spec: dict[str, Any]
) -> Iterator[tuple[str, Any, Any]]:
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return
    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {
                "get",
                "put",
                "post",
                "delete",
                "options",
                "head",
                "patch",
                "trace",
                "query",
            } or not isinstance(operation, dict):
                continue
            request = operation.get("requestBody", {})
            if isinstance(request, dict):
                content = request.get("content", {})
                if isinstance(content, dict):
                    for media_type, media in content.items():
                        if isinstance(media, dict):
                            yield from _media_examples(
                                media, f"paths.{path_name}.{method}.request.{media_type}"
                            )
            responses = operation.get("responses", {})
            if isinstance(responses, dict):
                for status, response in responses.items():
                    if not isinstance(response, dict):
                        continue
                    if "$ref" in response:
                        response = _pointer(spec, str(response["$ref"]))
                        if not isinstance(response, dict):
                            raise ValueError(
                                f"response $ref is not an object: "
                                f"{operation['responses'][status]['$ref']}"
                            )
                    content = response.get("content", {})
                    if isinstance(content, dict):
                        for media_type, media in content.items():
                            if isinstance(media, dict):
                                yield from _media_examples(
                                    media,
                                    f"paths.{path_name}.{method}.responses.{status}.{media_type}",
                                )


def _external_examples(
    path: Path | None,
) -> Iterator[tuple[str, str, Any]]:
    if path is None:
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("examples file must be an object with cases[]")
    for index, case in enumerate(data["cases"]):
        if not isinstance(case, dict):
            raise ValueError(f"examples.cases[{index}] must be an object")
        if not case.get("schema_ref") or "instance" not in case:
            raise ValueError(
                f"examples.cases[{index}] requires schema_ref and instance"
            )
        yield (
            str(case.get("name", f"case-{index}")),
            str(case["schema_ref"]),
            case["instance"],
        )


def _basic_structure(spec: dict[str, Any]) -> list[str]:
    errors = []
    if not isinstance(spec.get("openapi"), str):
        errors.append("openapi version string is required")
    info = spec.get("info")
    if not isinstance(info, dict) or not info.get("title") or not info.get("version"):
        errors.append("info.title and info.version are required")
    if not isinstance(spec.get("paths"), dict):
        errors.append("paths must be an object")
    return errors


def validate_contract(
    spec: dict[str, Any], examples_path: Path | None = None
) -> dict[str, Any]:
    errors = _basic_structure(spec)
    validator_available = False
    validator_version = "UNAVAILABLE"
    try:
        from openapi_spec_validator import validate  # type: ignore

        validator_available = True
        validator_version = importlib.metadata.version("openapi-spec-validator")
        try:
            validate(spec)
        except Exception as exc:  # validator exposes several exception classes
            errors.append(f"OpenAPI validator: {type(exc).__name__}: {exc}")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        pass

    example_results = []
    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    all_examples: list[tuple[str, Any, Any]] = list(_inline_examples(spec))
    for name, ref, instance in _external_examples(examples_path):
        all_examples.append((name, {"$ref": ref}, instance))

    if all_examples and jsonschema is None:
        errors.append("jsonschema is unavailable; examples were not checked")
    elif jsonschema is not None:
        for name, schema, instance in all_examples:
            try:
                expanded = _expand_schema(schema, spec)
                jsonschema.Draft202012Validator(expanded).validate(instance)
                example_results.append({"name": name, "state": "VERIFIED"})
            except Exception as exc:
                example_results.append(
                    {
                        "name": name,
                        "state": "FAILED",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                errors.append(f"example {name}: {type(exc).__name__}: {exc}")

    if errors:
        status = "FAILED"
    elif not validator_available:
        status = "STRUCTURE_ONLY"
    else:
        status = "VALIDATED"
    return {
        "schema": "light.system-design.v2.contract-validation",
        "status": status,
        "openapi": spec.get("openapi", "UNKNOWN"),
        "validator": "openapi-spec-validator",
        "validator_version": validator_version,
        "example_count": len(all_examples),
        "example_results": example_results,
        "errors": errors,
        "limitation": (
            "OpenAPI validation and JSON Schema example checks do not prove "
            "implementation behavior, authorization, performance, or compatibility."
        ),
    }


def _selftest() -> int:
    valid = {
        "openapi": "3.1.0",
        "info": {"title": "selftest", "version": "1"},
        "paths": {
            "/runs": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/RunCreate"
                                },
                                "examples": {
                                    "ok": {"value": {"title": "baseline"}}
                                },
                            }
                        }
                    },
                    "responses": {
                        "204": {"$ref": "#/components/responses/NoContent"}
                    },
                }
            }
        },
        "components": {
            "responses": {
                "NoContent": {
                    "description": "ok",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Ack"
                            },
                            "examples": {"ok": {"value": {"ok": True}}},
                        }
                    },
                }
            },
            "schemas": {
                "Ack": {
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
                "RunCreate": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title"],
                    "properties": {"title": {"type": "string", "minLength": 1}},
                }
            }
        },
    }
    report = validate_contract(valid)
    assert report["status"] in {"VALIDATED", "STRUCTURE_ONLY"}, report
    assert report["example_count"] == 2
    assert all(
        item["state"] == "VERIFIED" for item in report["example_results"]
    )

    broken = json.loads(json.dumps(valid))
    broken["paths"]["/runs"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]["bad"] = {"value": {"title": ""}}
    failed = validate_contract(broken)
    assert failed["status"] == "FAILED"
    assert any(item["state"] == "FAILED" for item in failed["example_results"])
    print("[selftest] PASS contract_validate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate OpenAPI and declared request/response examples"
    )
    parser.add_argument("--spec")
    parser.add_argument("--examples")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.spec:
        parser.error("provide --spec or --selftest")
    try:
        path = Path(args.spec).expanduser().resolve()
        fmt = "json" if path.suffix.lower() == ".json" else "yaml"
        spec = load_spec(path.read_text(encoding="utf-8"), fmt)
        examples = Path(args.examples).expanduser().resolve() if args.examples else None
        report = validate_contract(spec, examples)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(
                f"{report['status']} OpenAPI {report['openapi']} "
                f"validator={report['validator_version']} "
                f"examples={report['example_count']}"
            )
            for error in report["errors"]:
                print(f"- {error}")
            print(report["limitation"])
        if report["status"] == "VALIDATED":
            return 0
        if report["status"] == "STRUCTURE_ONLY":
            return 2
        return 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
