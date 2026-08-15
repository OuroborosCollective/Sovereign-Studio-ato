"""Tests for the NocoDB operator projection command gateway (Issue #1174).

Covers the strict schema/owner/receipt/base-hash binding and the fail-closed
security posture. The gateway never executes; it only produces a server-bound
``GatewayCommand`` receipt for the canonical lane chain.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from agent_runtime.operator_projection.command_gateway import (  # noqa: E402
    CANONICAL_LANE_CHAIN,
    CommandRejected,
    GatewayCommand,
    SecretRejected,
    BoundPrincipal,
    gateway_accept,
    load_schema,
    parse_request,
)


_REV = "sha256:" + "a" * 64
_HASH = "sha256:" + "b" * 64
_BASE = "sha256:" + "c" * 64


def _good_payload(effect: str = "INSPECT") -> dict:
    return {
        "schemaVersion": "operator-command-request.v1",
        "operatorProjectionRevision": _REV,
        "sourceReceiptHashes": [_HASH],
        "requestedCapabilityId": "cap.inspect.runtime",
        "targetResourceId": "runtime-node-1",
        "expectedBaseHash": _BASE,
        "normalizedParameters": {"scope": "incidents", "limit": 5},
        "requestedEffectClass": effect,
        "reasonCode": "operator wants an inspect projection",
    }


def _principal() -> BoundPrincipal:
    return BoundPrincipal(principal="operator@sovereign", owner="OuroborosCollective")


def test_schema_contract_is_strict_and_loads():
    schema = load_schema()
    assert schema["title"] == "OperatorCommandRequestV1"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schemaVersion"]["const"] == "operator-command-request.v1"
    assert "BOUNDED_MUTATION" in schema["properties"]["requestedEffectClass"]["enum"]


def test_gateway_accepts_valid_inspect_request():
    cmd = gateway_accept(_good_payload("INSPECT"), _principal())
    assert isinstance(cmd, GatewayCommand)
    assert cmd.requestedEffectClass == "INSPECT"
    assert cmd.boundPrincipal.principal == "operator@sovereign"
    assert cmd.boundPrincipal.owner == "OuroborosCollective"
    assert cmd.commandHash.startswith("sha256:")
    assert cmd.routedTo == CANONICAL_LANE_CHAIN
    # Gateway performs no execution; it advertises the lane chain only.
    assert "permission-workflow" in cmd.routedTo


def test_command_hash_is_deterministic_and_bound_to_principal():
    cmd_a = gateway_accept(_good_payload(), _principal())
    cmd_b = gateway_accept(_good_payload(), _principal())
    assert cmd_a.commandHash == cmd_b.commandHash
    other = BoundPrincipal(principal="operator2@sovereign", owner="OuroborosCollective")
    cmd_c = gateway_accept(_good_payload(), other)
    assert cmd_c.commandHash != cmd_a.commandHash


def test_unknown_schema_version_rejected():
    payload = _good_payload()
    payload["schemaVersion"] = "operator-command-request.v2"
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_unknown_fields_rejected():
    payload = _good_payload()
    payload["clientSuppliedOwner"] = "attacker"
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_invalid_effect_class_rejected():
    payload = _good_payload("DEPLOY")  # not allowed
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_malformed_hashes_rejected():
    payload = _good_payload()
    payload["operatorProjectionRevision"] = "not-a-hash"
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_empty_receipt_hashes_rejected():
    payload = _good_payload()
    payload["sourceReceiptHashes"] = []
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_unsafe_token_rejected():
    payload = _good_payload()
    payload["requestedCapabilityId"] = "cap with spaces!"
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_parameters_must_be_primitives():
    payload = _good_payload()
    payload["normalizedParameters"] = {"nested": {"deep": "object"}}
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_parameters_too_many_keys_rejected():
    payload = _good_payload()
    payload["normalizedParameters"] = {f"k{i}": i for i in range(65)}
    with pytest.raises(CommandRejected):
        parse_request(payload)


def test_secret_in_reason_rejected():
    payload = _good_payload()
    payload["reasonCode"] = "leaked sk-1234567890abcdefghijklmnopqrstuvwxyz key"
    with pytest.raises(SecretRejected):
        parse_request(payload)


def test_secret_in_parameter_value_rejected():
    payload = _good_payload()
    payload["normalizedParameters"] = {"api_key": "ghp_1234567890abcdefghijklmnopqrstuvwxyz"}
    with pytest.raises(SecretRejected):
        parse_request(payload)


def test_secret_in_capability_id_rejected():
    payload = _good_payload()
    payload["requestedCapabilityId"] = "cap.ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    with pytest.raises(SecretRejected):
        parse_request(payload)


def test_bound_principal_must_be_nonempty():
    with pytest.raises(Exception):
        BoundPrincipal(principal="", owner="owner")


def test_bound_principal_rejects_secret_shaped_owner():
    with pytest.raises(Exception):
        BoundPrincipal(principal="op", owner="ghp_1234567890abcdefghijklmnopqrstuvwxyz")


def test_to_dict_roundtrip_is_serializable():
    import json

    cmd = gateway_accept(_good_payload("BOUNDED_MUTATION"), _principal())
    data = cmd.to_dict()
    json.dumps(data)  # must serialize
    assert data["boundOwner"] == "OuroborosCollective"
    assert data["requestedEffectClass"] == "BOUNDED_MUTATION"


def test_bounded_mutation_requires_base_hash():
    payload = _good_payload("BOUNDED_MUTATION")
    payload["expectedBaseHash"] = ""
    with pytest.raises(CommandRejected):
        parse_request(payload)
