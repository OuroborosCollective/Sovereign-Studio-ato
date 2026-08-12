"""Cross-language PatchMon readback parity - golden vector (issue #1169).

Acceptance criterion #6: "PatchMon bestätigt die wirklich geladene
Config-Projektion; TS und Python müssen byteidentische Fail-Closed-Readback-
Entscheidungen treffen." The existing parity test locks the assembled receipt
hash; this module guards the **readback audit** that consumes that receipt.

It loads a single shared golden fixture
(``fixtures/config_provenance_readback_parity.v1.json``), runs the full
``resolve_config_sources -> materialize_receipt`` live path to build a real
``ConfigReceipt``, asserts the materialized receipt hash equals the frozen
golden (cross-language lock, same value as the receipt-hash parity fixture),
then feeds each frozen PatchMon observation to ``verify_config_readback`` and
asserts the frozen audit outcome (``accepted`` / ``blocker`` /
``contradicted``).

The same fixture is consumed by the TypeScript test
``configReadbackParity.test.ts``, so any divergence in the readback audit reason
codes between Python and TypeScript breaks the gate on the offending side. No
production logic is copied here; the live ``verify_config_readback``
implementation is exercised directly.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigReadbackObservation,
    ConfigSourceContract,
    ResolveOptions,
    materialize_receipt,
    resolve_config_sources,
)
from agent_runtime.configuration.receipt import (  # noqa: E402
    ConfigReceipt,
    verify_config_readback,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "config_provenance_readback_parity.v1.json"
)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text("utf-8"))


def _build_sources(fixture: dict[str, Any]) -> list[ConfigSourceContract]:
    return [
        ConfigSourceContract(
            id=s["id"],
            kind=s["kind"],
            revision=s["revision"],
            content_hash=s["content_hash"],
            schema_hash=s["schema_hash"],
            priority=s["priority"],
            values=s["values"],
        )
        for s in fixture["sources"]
    ]


def _materialize_golden_receipt(fixture: dict[str, Any]) -> ConfigReceipt:
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=fixture["options"]["schemaFields"]),
    )
    return materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )


def test_materializes_golden_receipt_hash_before_readback() -> None:
    fixture = _load_fixture()
    receipt = _materialize_golden_receipt(fixture)
    assert receipt.status == fixture["expected"]["status"]
    assert receipt.resolved_hash == fixture["expected"]["resolved_hash"]
    assert receipt.receipt_hash == fixture["expected"]["receipt_hash"]


def _scenarios() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    fixture = _load_fixture()
    return [
        (s["name"], s["observation"], s["expected"]) for s in fixture["scenarios"]
    ]


@pytest.mark.parametrize(
    "observation, expected",
    [(obs, exp) for _name, obs, exp in _scenarios()],
    ids=[name for name, _obs, _exp in _scenarios()],
)
def test_readback_audit_matches_golden_vector(
    observation: dict[str, Any], expected: dict[str, Any]
) -> None:
    fixture = _load_fixture()
    receipt = _materialize_golden_receipt(fixture)
    # Cross-language lock: the audit must run against the frozen receipt.
    assert receipt.receipt_hash == fixture["expected"]["receipt_hash"]

    audit = verify_config_readback(
        receipt,
        ConfigReadbackObservation(
            revision=observation["revision"],
            image_digest=observation["imageDigest"],
            schema_hash=observation["schemaHash"],
            resolved_hash=observation["resolvedHash"],
            receipt_hash=observation["receiptHash"],
        ),
    )
    assert audit.accepted is expected["accepted"]
    assert audit.blocker == expected["blocker"]
    assert audit.contradicted is expected["contradicted"]
