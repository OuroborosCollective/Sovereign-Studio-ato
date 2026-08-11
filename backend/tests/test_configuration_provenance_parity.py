"""Cross-language configuration provenance parity - end-to-end golden vector.

Issue #1169 acceptance criterion: "gleicher Input erzeugt bytegleichen
Public-Receipt-Hash". The existing parity tests in
``test_configuration_provenance.py`` lock the primitive serializers
(``canonical_json`` / ``hash_value``) against TS reference values. This module
guards the **assembled** contract: it loads a single shared golden fixture
(``fixtures/config_provenance_parity.v1.json``), runs the full
``resolve_config_sources -> materialize_receipt`` pipeline against it, and
asserts that the Python implementation produces the byte-identical
``resolved_hash`` and ``receipt_hash`` frozen in that fixture.

The same fixture is consumed by the TypeScript test
``configProvenanceParity.test.ts``, so any serialization divergence on either
side breaks both gates. The fixture is the single source of truth; both
language tests read the same inputs and the same expected hashes from it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    ResolveOptions,
    materialize_receipt,
    resolve_config_sources,
)

FIXTURE = Path(__file__).parent / "fixtures" / "config_provenance_parity.v1.json"

# The golden resolved_hash / receipt_hash are hard regression guards. The
# float-parity fix (#1339) is already on main and this rescue applies the
# Unicode/raw-UTF-8 parity fix from #1344, so no expected failure remains.


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text("utf-8"))


def _build_sources(fixture: dict) -> list[ConfigSourceContract]:
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


def test_resolved_hash_matches_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    assert contract.status == fixture["expected"]["status"]
    assert contract.resolved_hash == fixture["expected"]["resolved_hash"]


def test_receipt_hash_matches_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    receipt = materialize_receipt(
        contract,
        {
            "revision": fixture["options"]["revision"],
            "image_digest": fixture["options"]["imageDigest"],
        },
    )
    assert receipt.receipt_hash == fixture["expected"]["receipt_hash"]


def test_resolved_values_match_golden_vector() -> None:
    fixture = _load_fixture()
    schema_fields = fixture["options"]["schemaFields"]
    contract = resolve_config_sources(
        _build_sources(fixture),
        ResolveOptions(schema_fields=schema_fields),
    )
    assert contract.resolved == fixture["expected"]["resolved"]


def test_fixture_self_documents_verified_parity() -> None:
    """Guard against a stale fixture: the embedded parity proof must hold."""
    fixture = _load_fixture()
    proof = fixture["parity_verified"]
    assert proof["identical"] is True
    assert proof["python_resolved_hash"] == proof["typescript_resolved_hash"]
    assert proof["python_receipt_hash"] == proof["typescript_receipt_hash"]
    assert proof["python_resolved_hash"] == fixture["expected"]["resolved_hash"]
    assert proof["python_receipt_hash"] == fixture["expected"]["receipt_hash"]
