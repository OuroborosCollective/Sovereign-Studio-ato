"""Configuration Provenance - backend contract tests.

Covers deterministic merge semantics (object/array/null/missing/deleted),
fail-closed for unknown sources & bare remote URLs, remote-binding
enforcement, drift invalidation, byte-identical receipt hashing, secret
redaction, and PatchMon readback fields. Mirrors the TypeScript tests in
``src/runtime/config/configProvenance.test.ts``.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

import pytest

# Make agent_runtime importable whether pytest runs from the repo root
# (sovereign-agent-backend.yml PR gate) or from backend/ (ci.yml push gate).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration import (  # noqa: E402
    ConfigSourceContract,
    ConfigDriftRecord,
    RemoteBinding,
    ResolveOptions,
    default_priority_for,
    canonical_source_order,
    compute_receipt_hash,
    is_safe_to_advance,
    materialize_receipt,
    resolve_config_sources,
    verify_receipt,
)
from agent_runtime.configuration.config_canonicalize import (
    canonical_json,
    hash_value,
    is_redacted_secret,
    merge_values,
    schema_hash_from_fields,
)


def _src(
    id: str,
    kind: str,
    values: dict[str, Any],
    *,
    revision: str = "rev-1",
    content_hash: str | None = None,
    schema_hash: str = "sch-default",
    priority: int | None = None,
    remote: RemoteBinding | None = None,
) -> ConfigSourceContract:
    if priority is None:
        try:
            priority = default_priority_for(kind)  # type: ignore[arg-type]
        except KeyError:
            priority = 999
    return ConfigSourceContract(
        id=id,
        kind=kind,  # type: ignore[arg-type]
        revision=revision,
        content_hash=content_hash or f"ch-{id}",
        schema_hash=schema_hash,
        priority=priority,
        values=values,
        remote=remote,
    )


BASE_SOURCES = [
    _src("defaults", "compiled-defaults", {"a": 1, "b": {"x": 1}, "arr": [1, 2]}),
    _src("deploy", "deployment-config", {"b": {"y": 2}, "c": 3}),
]


def test_canonical_source_order_ascending():
    order = canonical_source_order()
    assert order == [
        "compiled-defaults",
        "image-manifest",
        "deployment-config",
        "environment-projection",
        "approved-runtime-overlay",
    ]


def test_priorities_monotonic():
    assert default_priority_for("compiled-defaults") < default_priority_for("image-manifest")
    assert default_priority_for("image-manifest") < default_priority_for("deployment-config")
    assert default_priority_for("deployment-config") < default_priority_for("environment-projection")
    assert default_priority_for("environment-projection") < default_priority_for("approved-runtime-overlay")


def test_canonical_json_key_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_merge_deep_objects():
    assert merge_values({"b": {"x": 1}}, {"b": {"y": 2}}) == {"b": {"x": 1, "y": 2}}


def test_merge_replaces_arrays():
    assert merge_values({"arr": [1, 2]}, {"arr": [3]}) == {"arr": [3]}


def test_merge_null_deletes_key():
    merged = merge_values({"a": 1, "b": 2}, {"a": None})
    assert merged == {"b": 2}
    assert "a" not in merged


def test_redacted_secret_detection():
    assert is_redacted_secret({"kind": "secret", "redactedId": "r-1"})
    assert not is_redacted_secret({"kind": "secret"})


def test_schema_hash_order_independent():
    a = schema_hash_from_fields([{"name": "a", "kind": "num"}, {"name": "b", "kind": "str"}])
    b = schema_hash_from_fields([{"name": "b", "kind": "str"}, {"name": "a", "kind": "num"}])
    assert a == b


def test_resolve_success_merge():
    res = resolve_config_sources(BASE_SOURCES)
    assert res.status == "RESOLVED"
    assert res.resolved == {"a": 1, "b": {"x": 1, "y": 2}, "arr": [1, 2], "c": 3}
    assert len(res.source_hashes) == 2
    assert res.errors == ()
    assert res.source_order == ("compiled-defaults", "deployment-config")


def test_resolve_returns_hashes():
    res = resolve_config_sources(BASE_SOURCES)
    assert res.schema_hash == "sch-default"
    assert len(res.resolved_hash) == 64
    rec = res.source_hashes[0]
    assert rec.id == "defaults"
    assert rec.kind == "compiled-defaults"
    assert rec.revision == "rev-1"
    assert rec.content_hash == "ch-defaults"
    assert rec.remote_origin is None


def test_resolve_deterministic_regardless_of_input_order():
    r1 = resolve_config_sources(list(reversed(BASE_SOURCES)))
    r2 = resolve_config_sources(BASE_SOURCES)
    assert r1.resolved_hash == r2.resolved_hash
    assert canonical_json(r1.resolved) == canonical_json(r2.resolved)


def test_compute_receipt_hash_matches_resolver():
    res = resolve_config_sources(BASE_SOURCES)
    direct = compute_receipt_hash(BASE_SOURCES)
    assert direct == res.resolved_hash


def test_reject_unknown_source_kind():
    res = resolve_config_sources([_src("bad", "unknown-origin", {})])
    assert res.status == "BLOCKED"
    assert "unknown source kind" in res.errors[0]
    assert res.resolved == {}
    assert res.resolved_hash == ""


def test_reject_missing_revision():
    res = resolve_config_sources([_src("x", "compiled-defaults", {}, revision="")])
    assert res.status == "BLOCKED"
    assert "missing revision" in "|".join(res.errors)


def test_reject_remote_origin_not_pre_bound():
    res = resolve_config_sources(
        [
            _src(
                "remote",
                "approved-runtime-overlay",
                {"a": 9},
                remote=RemoteBinding(
                    origin="https://untrusted.example/cfg",
                    digest="d-1",
                    signature_hash="s-1",
                ),
            )
        ]
    )
    assert res.status == "BLOCKED"
    assert "remote origin not pre-bound/allowed" in "|".join(res.errors)


def test_reject_remote_missing_digest():
    opts = ResolveOptions(
        allowed_remote_origins=frozenset({"https://trusted.example/cfg"})
    )
    res = resolve_config_sources(
        [
            _src(
                "remote",
                "approved-runtime-overlay",
                {"a": 9},
                remote=RemoteBinding(
                    origin="https://trusted.example/cfg",
                    digest="",
                    signature_hash="s-1",
                ),
            )
        ],
        opts,
    )
    assert res.status == "BLOCKED"
    assert "without digest" in "|".join(res.errors)


# ---------------------------------------------------------------------------
# Prototype-pollution hardening parity.
#
# merge_values must reject property names that would hijack an object or global
# prototype (`__proto__`, `constructor`, `prototype`). Python dicts do not
# expose prototype pollution the way JS objects do, but the *rejection
# behavior* must be byte-identical to the TypeScript implementation so that a
# remote/user-provided source is canonicalized the same way on both runtimes.
# These tests exercise the real merge_values path and assert the dangerous
# keys are dropped (never stored) symmetrically with the TS implementation.
# ---------------------------------------------------------------------------
def test_merge_rejects_proto_key():
    import json as _json

    overlay = _json.loads('{"__proto__": {"polluted": true}}')
    merged = merge_values({"a": 1}, overlay)
    assert merged == {"a": 1}
    assert "__proto__" not in merged
    assert "polluted" not in merged


def test_merge_rejects_constructor_and_prototype_keys():
    import json as _json

    overlay = _json.loads(
        '{"constructor": {"prototype": {"polluted": "yes"}}, "prototype": {"x": 9}}'
    )
    merged = merge_values({"a": 1}, overlay)
    assert merged == {"a": 1}
    assert "constructor" not in merged
    assert "prototype" not in merged
    assert "polluted" not in merged


def test_merge_rejects_dangerous_keys_at_nested_depth():
    import json as _json

    overlay = _json.loads('{"b": {"__proto__": {"deep": true}}}')
    merged = merge_values({"b": {"x": 1}}, overlay)
    assert merged == {"b": {"x": 1}}
    assert "deep" not in merged


def test_merge_still_allows_safe_lookalike_keys():
    # A normal field name is unaffected by the sanitizer.
    merged = merge_values({"a": 1}, {"protoSafe": 2})
    assert merged == {"a": 1, "protoSafe": 2}


def test_accept_remote_when_pre_bound():
    opts = ResolveOptions(
        allowed_remote_origins=frozenset({"https://trusted.example/cfg"})
    )
    res = resolve_config_sources(
        [
            _src("defaults", "compiled-defaults", {"a": 1}),
            _src(
                "remote",
                "approved-runtime-overlay",
                {"a": 9},
                remote=RemoteBinding(
                    origin="https://trusted.example/cfg",
                    digest="d-1",
                    signature_hash="s-1",
                ),
            ),
        ],
        opts,
    )
    assert res.status == "RESOLVED"
    assert res.resolved == {"a": 9}
    assert res.source_hashes[1].remote_origin == "https://trusted.example/cfg"
    assert res.source_hashes[1].remote_digest == "d-1"


def test_content_drift_contradicted():
    res = resolve_config_sources(
        BASE_SOURCES, ResolveOptions(expected_receipt_hash="deadbeef")
    )
    assert res.status == "CONTRADICTED"
    assert res.drift is not None
    assert res.drift.kind == "content-drift"
    assert res.drift.expected_hash == "deadbeef"
    assert res.drift.actual_hash == res.resolved_hash
    assert res.resolved == {}
    assert not is_safe_to_advance(res)


def test_no_drift_when_expected_matches():
    baseline = resolve_config_sources(BASE_SOURCES)
    res = resolve_config_sources(
        BASE_SOURCES,
        ResolveOptions(expected_receipt_hash=baseline.resolved_hash),
    )
    assert res.status == "RESOLVED"
    assert res.drift is None
    assert is_safe_to_advance(res)


def test_schema_disagreement_blocked():
    res = resolve_config_sources(
        [
            _src("a", "compiled-defaults", {"a": 1}, schema_hash="sch-1"),
            _src("b", "deployment-config", {"b": 2}, schema_hash="sch-2"),
        ]
    )
    assert res.status == "BLOCKED"
    assert res.drift is not None
    assert res.drift.kind == "schema-drift"
    assert "schemaHash" in "|".join(res.errors)


def test_expected_schema_fields_mismatch():
    res = resolve_config_sources(
        [_src("a", "compiled-defaults", {"a": 1}, schema_hash="sch-default")],
        ResolveOptions(schema_fields=[{"name": "zzz", "kind": "num"}]),
    )
    assert res.status == "BLOCKED"
    assert res.drift is not None
    assert res.drift.kind == "schema-drift"


def test_receipt_deterministic_for_identical_input():
    res = resolve_config_sources(BASE_SOURCES)
    r1 = materialize_receipt(res, {"revision": "rev-1", "image_digest": "img-1"})  # type: ignore[arg-type]
    r2 = materialize_receipt(res, {"revision": "rev-1", "image_digest": "img-1"})  # type: ignore[arg-type]
    assert r1.receipt_hash == r2.receipt_hash
    assert len(r1.receipt_hash) == 64


def test_receipt_differs_when_revision_differs():
    res = resolve_config_sources(BASE_SOURCES)
    r1 = materialize_receipt(res, {"revision": "rev-1", "image_digest": "img-1"})  # type: ignore[arg-type]
    r2 = materialize_receipt(res, {"revision": "rev-2", "image_digest": "img-1"})  # type: ignore[arg-type]
    assert r1.receipt_hash != r2.receipt_hash


def test_verify_receipt_integrity():
    res = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(res, {"revision": "rev-1"})  # type: ignore[arg-type]
    assert verify_receipt(receipt) is True


def test_tampered_receipt_fails_verification():
    res = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(res, {"revision": "rev-1"})  # type: ignore[arg-type]
    tampered = ConfigSourceContract(  # reuse frozen dataclass shape for tamper
        id=receipt.revision or "",
        kind="compiled-defaults",
        revision="rev-tampered",
        content_hash="x",
        schema_hash="x",
        priority=0,
        values={},
    )
    # Construct a tampered receipt by replacing revision only.
    import dataclasses

    tampered_receipt = dataclasses.replace(receipt, revision="rev-tampered")
    assert verify_receipt(tampered_receipt) is False


def test_patchmon_readback_fields_present():
    res = resolve_config_sources(BASE_SOURCES)
    receipt = materialize_receipt(
        res, {"revision": "rev-1", "image_digest": "sha256:img-1"}  # type: ignore[arg-type]
    )
    assert receipt.revision == "rev-1"
    assert receipt.image_digest == "sha256:img-1"
    assert receipt.schema_hash == res.schema_hash
    assert receipt.resolved_hash == res.resolved_hash


def test_secret_redaction_never_leaks_raw_material():
    secret = "super-secret-value-do-not-leak"
    redacted_id = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    sources = [
        _src(
            "env",
            "environment-projection",
            {"apiKey": {"kind": "secret", "redactedId": redacted_id}, "public": "visible"},
        )
    ]
    res = resolve_config_sources(sources)
    assert res.status == "RESOLVED"
    body = canonical_json(res.resolved)
    assert secret not in body
    assert "redactedId" in body
    receipt = materialize_receipt(res, {"revision": "rev-1"})  # type: ignore[arg-type]
    assert secret not in canonical_json(receipt.resolved)


def test_null_override_deletes_lower_priority_value():
    res = resolve_config_sources(
        [
            _src("defaults", "compiled-defaults", {"secret": "x"}),
            _src("overlay", "approved-runtime-overlay", {"secret": None}),
        ]
    )
    assert res.status == "RESOLVED"
    assert "secret" not in res.resolved


def test_bare_url_value_is_not_a_remote_truth_path():
    res = resolve_config_sources(
        [_src("defaults", "compiled-defaults", {"url": "https://evil.example/cfg"})]
    )
    assert res.status == "RESOLVED"
    assert res.resolved["url"] == "https://evil.example/cfg"
    assert res.source_hashes[0].remote_origin is None


# ---------------------------------------------------------------------------
# Cross-language float canonicalization parity.
#
# The TypeScript canonicalizer uses JS ``Number.prototype.toString`` (via
# ``String(value)``). Python ``str(float)`` diverges for some floats (whole
# floats, exponential threshold), which would break provenance hash parity.
# These values were chosen to exercise the divergent formatting boundaries and
# are asserted byte-for-byte against the JS reference output. If either side
# changes float serialization, these tests fail.
# ---------------------------------------------------------------------------

_JS_FLOAT_REFERENCE = [
    # (input, expected canonical JS string, expected sha256 of that string).
    # Expected values were produced by the TypeScript canonicalizer (the
    # declared-canonical implementation) and re-confirmed byte-identical by the
    # fixed Python implementation. Do NOT edit these by hand - regenerate from
    # both runtimes if float serialization changes.
    (1.0, "1", "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"),
    (-0.0, "0", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    (0.1, "0.1", "14be4b45f18e0d8c67b4f719b5144eee88497e413709d11d85b096d8e2346310"),
    (-0.1, "-0.1", "ffe616e28103a848cc8a18531f5ba096e153b50c6d597297ad5cb69e39496f6a"),
    (100.25, "100.25", "276e984dd04dbd73c7d99e14cf02cff9fe8d1b467a04929a3770f8c7c7f0ace2"),
    (1e16, "10000000000000000", "139eb393675707818651f879828a526159209ca3ad3b2f94f9f8ec8c4fb5e610"),
    (1e20, "100000000000000000000", "c344e9487bfbd5c4e03c9fb90d62a5dde5e00b54d55c46e9f4a803aea162b80c"),
    (1e21, "1e+21", "241c4643fa70b1dcde1205b71be4e3bebb17e9f880c8e1a33d0ead6c27271d3c"),
    (1e-7, "1e-7", "5b33e02f2c5103a05d32f6ba9cb058294452bfbf393967f68bb30c1bdcbbab22"),
    (5e-7, "5e-7", "1dbb0eeaf281e991374e0969e04ccffc84d2c820f69c056f105256cf4cc2bba0"),
    (5e-324, "5e-324", "c46e7ca1be4c8734f373a56530787288fa2058d73d07855e9247e949f811a42a"),
    (1.7976931348623157e308, "1.7976931348623157e+308", "c2784e1abd6317452708f3fbf9641c16b959561bc621a1d408c23a20aa2cb585"),
    (1234567.89, "1234567.89", "3b1ff895d2562d2fd5af9c6868370fb954997d8d863abd0e28bdd981b3ba6cd2"),
    (1234567890123456.0, "1234567890123456", "7a51d064a1a216a692f753fcdab276e4ff201a01d8b66f56d50d4d719fd0dc87"),
]


@pytest.mark.parametrize("value,expected_str,expected_hash", _JS_FLOAT_REFERENCE)
def test_float_canonicalization_matches_js(value, expected_str, expected_hash):
    assert canonical_json(value) == expected_str
    assert hash_value(value) == expected_hash


def test_float_nested_canonicalization_matches_js():
    # A nested structure mixing floats, ints, strings and arrays must serialize
    # byte-identically to the JS canonicalizer. The expected string was produced
    # from the TypeScript implementation.
    value = {"a": 1.0, "b": [1e20, 2.5, 3], "c": {"d": 0.1, "e": 1e-7}}
    expected = '{"a":1,"b":[100000000000000000000,2.5,3],"c":{"d":0.1,"e":1e-7}}'
    assert canonical_json(value) == expected
