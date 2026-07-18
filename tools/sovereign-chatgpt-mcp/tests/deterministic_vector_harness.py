from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from deterministic_contract import (
    canonical_bytes,
    canonical_decimal_to_units,
    canonical_sha256,
    divide_fixed,
    multiply_fixed,
    replay_verify,
    state_sha256,
    transition_preview,
    trunc_div_toward_zero,
)


FIXTURE = Path(__file__).parent / "fixtures" / "deterministic_contract_vectors.json"


def materialize_tagged_integers(value: Any) -> Any:
    if isinstance(value, list):
        return [materialize_tagged_integers(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$integer"} and isinstance(value["$integer"], str):
            raw = value["$integer"]
            parsed = int(raw)
            if raw == "-0" or str(parsed) != raw:
                raise ValueError("tagged integer must be canonical")
            return parsed
        return {
            key: materialize_tagged_integers(item)
            for key, item in value.items()
        }
    return value


def tag_integers(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, float)):
        return value
    if isinstance(value, int):
        return {"$integer": str(value)}
    if isinstance(value, list):
        return [tag_integers(item) for item in value]
    if isinstance(value, dict):
        return {key: tag_integers(item) for key, item in value.items()}
    raise TypeError(f"unsupported parity result type: {type(value).__name__}")


def build_python_results(document: dict[str, Any]) -> dict[str, Any]:
    decimals = [
        {
            "name": vector["name"],
            "units": str(canonical_decimal_to_units(
                vector["value"],
                signed=vector.get("signed", True),
            )),
        }
        for vector in document["decimalVectors"]
    ]

    arithmetic = []
    for vector in document["arithmeticVectors"]:
        left = materialize_tagged_integers(vector["left"])
        right = materialize_tagged_integers(vector["right"])
        operation = vector["operation"]
        if operation == "truncDiv":
            result = trunc_div_toward_zero(left, right)
        elif operation == "multiplyFixed":
            result = multiply_fixed(left, right)
        elif operation == "divideFixed":
            result = divide_fixed(left, right)
        else:
            raise ValueError(f"unknown arithmetic operation: {operation}")
        arithmetic.append({"name": vector["name"], "result": str(result)})

    canonical = []
    for vector in document["canonicalVectors"]:
        value = materialize_tagged_integers(vector["value"])
        canonical.append({
            "name": vector["name"],
            "canonicalUtf8Hex": canonical_bytes(value).hex(),
            "sha256": canonical_sha256(value),
        })

    rejections = []
    for vector in document["rejectionVectors"]:
        rejected = False
        try:
            if vector["operation"] == "canonical":
                canonical_sha256(materialize_tagged_integers(vector["value"]))
            else:
                canonical_decimal_to_units(str(vector["value"]), signed=False)
        except (TypeError, ValueError, ZeroDivisionError):
            rejected = True
        rejections.append({"name": vector["name"], "rejected": rejected})

    states = [
        {
            "name": vector["name"],
            "stateSha256": state_sha256(
                materialize_tagged_integers(vector["state"])
            ),
        }
        for vector in document["stateVectors"]
    ]

    transitions = []
    for vector in document["transitionVectors"]:
        expected_version = vector.get("expectedVersion")
        if expected_version is not None:
            expected_version = materialize_tagged_integers(expected_version)
        result = transition_preview(
            materialize_tagged_integers(vector["currentState"]),
            materialize_tagged_integers(vector["action"]),
            materialize_tagged_integers(vector["transitionTable"]),
            expected_version=expected_version,
            expected_state_hash=vector.get("expectedStateHash", ""),
            engine_version=vector.get("engineVersion", "are-v1"),
        )
        result.pop("truthNotice", None)
        transitions.append({"name": vector["name"], "result": tag_integers(result)})

    replays = []
    for vector in document["replayVectors"]:
        result = replay_verify(
            materialize_tagged_integers(vector["initialState"]),
            materialize_tagged_integers(vector["actions"]),
            materialize_tagged_integers(vector["transitionTable"]),
            expected_final_state_hash=vector.get("expectedFinalStateHash", ""),
            engine_version=vector.get("engineVersion", "are-v1"),
        )
        result.pop("truthNotice", None)
        replays.append({"name": vector["name"], "result": tag_integers(result)})

    return {
        "schemaVersion": "sovereign.deterministic-cross-runtime-results.v1",
        "sourceSchemaVersion": document["schemaVersion"],
        "decimalVectors": decimals,
        "arithmeticVectors": arithmetic,
        "canonicalVectors": canonical,
        "rejectionVectors": rejections,
        "stateVectors": states,
        "transitionVectors": transitions,
        "replayVectors": replays,
    }


def load_document(path: Path = FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE
    results = build_python_results(load_document(path))
    sys.stdout.write(json.dumps(results, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
