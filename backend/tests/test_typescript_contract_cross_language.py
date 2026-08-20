"""Cross-language parity for the isolated TypeScript contract pilot.

This test deliberately consumes the generated TypeScript artifact instead of a
second manually maintained Python schema. It validates the shared fixture and
negative cases using only the JSON Schema semantics the pilot publishes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "contracts" / "typescript" / "artifacts" / "contracts.json"
FIXTURE = ROOT / "contracts" / "typescript" / "fixtures" / "permission-receipt-input.json"


def _resolve(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str):
        return schema
    prefix = "#/components/schemas/"
    assert reference.startswith(prefix), f"unexpected schema reference: {reference}"
    return document["components"]["schemas"][reference.removeprefix(prefix)]


def _validate(document: dict[str, Any], schema: dict[str, Any], value: Any, path: str = "$") -> None:
    schema = _resolve(document, schema)
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: enum mismatch"
    schema_type = schema.get("type")
    if schema_type == "object":
        assert isinstance(value, dict), f"{path}: expected object"
        required = schema.get("required", [])
        for key in required:
            assert key in value, f"{path}: missing {key}"
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(schema.get("properties", {})), f"{path}: unknown field"
        for key, child in value.items():
            _validate(document, schema["properties"][key], child, f"{path}.{key}")
    elif schema_type == "string":
        assert isinstance(value, str), f"{path}: expected string"
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{path}: string too short"
        if "maxLength" in schema:
            assert len(value) <= schema["maxLength"], f"{path}: string too long"
        if "pattern" in schema:
            assert re.fullmatch(schema["pattern"], value), f"{path}: pattern mismatch"
    elif schema_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), f"{path}: expected integer"
    elif schema_type == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{path}: expected number"


def _permission_schema(document: dict[str, Any]) -> dict[str, Any]:
    return document["components"]["schemas"]["PermissionReceiptInput"]


def test_typescript_generated_schema_accepts_shared_permission_fixture() -> None:
    assert ARTIFACT.exists(), "run the isolated TypeScript contract build before Python cross-language tests"
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _validate(document, _permission_schema(document), fixture)


def test_typescript_generated_schema_rejects_unknown_and_coerced_shared_payloads() -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid_unknown = {**fixture, "unexpected": True}
    invalid_coerced = {**fixture, "requestedAt": "1735689600000"}
    for candidate in (invalid_unknown, invalid_coerced):
        try:
            _validate(document, _permission_schema(document), candidate)
        except AssertionError:
            continue
        raise AssertionError("schema-invalid payload unexpectedly crossed the Python parity boundary")
