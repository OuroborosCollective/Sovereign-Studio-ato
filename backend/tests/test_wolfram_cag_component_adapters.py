from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIRROR_ROOT = ROOT / "scripts" / "sovereign-backend"

_PACKAGE = "_sovereign_cag_1459"
sys.modules.setdefault(
    _PACKAGE, types.ModuleType(_PACKAGE)
)
sys.modules[_PACKAGE].__path__ = [str(ROOT / "backend" / "agent_runtime")]
sys.modules.setdefault(f"{_PACKAGE}.adapters", types.ModuleType(f"{_PACKAGE}.adapters"))
sys.modules[f"{_PACKAGE}.adapters"].__path__ = [
    str(ROOT / "backend" / "agent_runtime" / "adapters")
]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wolfram_module = _load_module(
    f"{_PACKAGE}.adapters.wolfram_agenttools",
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_agenttools.py",
)

WOLFRAM_CAG_COMPONENT_MAP = wolfram_module.WOLFRAM_CAG_COMPONENT_MAP
WolframCagComponent = wolfram_module.WolframCagComponent
WolframCagCredential = wolfram_module.WolframCagCredential
WolframCagError = wolfram_module.WolframCagError
WolframCagErrorFamily = wolfram_module.WolframCagErrorFamily
WolframCagReceipt = wolfram_module.WolframCagReceipt
WolframCagRequest = wolfram_module.WolframCagRequest
WolframCagRetryDecision = wolfram_module.WolframCagRetryDecision
WolframCagStatus = wolfram_module.WolframCagStatus
CagHttpOutcome = wolfram_module.CagHttpOutcome
cag_retry_decision = wolfram_module.cag_retry_decision
classify_cag_status = wolfram_module.classify_cag_status
execute_cag_request = wolfram_module.execute_cag_request
is_wolfram_capability = wolfram_module.is_wolfram_capability
provision_cag_component = wolfram_module.provision_cag_component
resolve_cag_credentials = wolfram_module.resolve_cag_credentials
WOLFRAM_CAPABILITY_MAP = wolfram_module.WOLFRAM_CAPABILITY_MAP

HASH = "a" * 64
SECRET_VALUE = "super-secret-app-id-DO-NOT-LOG"


def _request(**overrides):
    values = {
        "capability_id": "wolfram.cag.hints",
        "body_hash": HASH,
        "response_schema_hash": HASH,
        "idempotency_key": "cag-1:hints",
    }
    values.update(overrides)
    return WolframCagRequest(**values)


def _credential(entitled: bool = True) -> WolframCagCredential:
    return WolframCagCredential(
        credential_hash=HASH,
        entitled=entitled,
        provider="wolfram",
    )


def _json_schema_validator():
    def validator(body: bytes, content_type: str, component: WolframCagComponent) -> bool:
        if component.expected_content_type == "application/json":
            import json
            try:
                data = json.loads(body)
            except Exception:
                return False
            return isinstance(data, dict) and "result" in data
        if component.expected_content_type == "application/xml":
            return b"<queryresult" in body
        return True
    return validator


def _outcome(
    *,
    status: int = 200,
    content_type: str = "application/json",
    body: bytes = b'{"result": "ok"}',
    response_uuid: str = "uuid-123",
    request_id: str = "req-456",
    timed_out: bool = False,
    rate_limit_remaining: str = "100",
    quota_remaining: str = "unlimited",
) -> CagHttpOutcome:
    return CagHttpOutcome(
        status=status,
        content_type=content_type,
        body=body,
        response_uuid=response_uuid,
        request_id=request_id,
        timed_out=timed_out,
        rate_limit_remaining=rate_limit_remaining,
        quota_remaining=quota_remaining,
    )


def test_cag_component_map_covers_four_components_and_is_read_only():
    expected = {"wolfram.cag.hints", "wolfram.cag.compute", "wolfram.cag.results", "wolfram.cag.context"}
    assert set(WOLFRAM_CAG_COMPONENT_MAP) == expected
    for component in WOLFRAM_CAG_COMPONENT_MAP.values():
        assert component.mutates is False
        assert component.base_url.startswith("https://")
        assert component.timeout_seconds > 0
        assert component.max_output_bytes > 0
        assert component.max_request_bytes > 0
        assert component.max_retries >= 0
    # The Component APIs map to the named components from the issue.
    names = {c.component for c in WOLFRAM_CAG_COMPONENT_MAP.values()}
    assert names == {
        "WolframLanguageHints",
        "WolframLanguageComputation",
        "WolframAlphaResults",
        "WolframAlphaContext",
    }


def test_cag_component_rejects_mutation_contract():
    with pytest.raises(WolframCagError, match="read-only"):
        WolframCagComponent(
            capability_id="x",
            component="X",
            base_url="https://example.invalid",
            endpoint_id="x",
            method="POST",
            expected_content_type="application/json",
            timeout_seconds=1,
            max_output_bytes=1,
            max_request_bytes=1,
            max_retries=0,
            mutates=True,
        )


def test_cag_capabilities_project_into_existing_namespace_not_new_registry():
    for cid in WOLFRAM_CAG_COMPONENT_MAP:
        assert is_wolfram_capability(cid) is True
    assert is_wolfram_capability("wolfram.context.search") is True
    assert is_wolfram_capability("github.pull.read") is False
    # The CAG map is the same object/namespace as the existing Wolfram module,
    # not a separate registry file.
    assert WOLFRAM_CAG_COMPONENT_MAP is wolfram_module.WOLFRAM_CAG_COMPONENT_MAP
    assert WOLFRAM_CAPABILITY_MAP is wolfram_module.WOLFRAM_CAPABILITY_MAP


def test_request_contract_is_typed_and_validates_size_and_forbidden_keys():
    request = _request()
    component = request.validate()
    assert component.capability_id == "wolfram.cag.hints"
    assert len(request.request_hash) == 64

    with pytest.raises(WolframCagError, match="unknown CAG capability"):
        _request(capability_id="wolfram.cag.bogus").validate()
    with pytest.raises(WolframCagError, match="SHA-256"):
        _request(body_hash="short").validate()
    with pytest.raises(WolframCagError, match="output exceeds"):
        _request(requested_output_bytes=10 * 1024 * 1024).validate()
    with pytest.raises(WolframCagError, match="forbidden"):
        _request(idempotency_key="apikey").validate()


def test_credentials_resolved_server_side_and_secret_never_returned_or_logged(monkeypatch):
    monkeypatch.setenv("WOLFRAM_CAG_APP_ID", SECRET_VALUE)
    credential = resolve_cag_credentials(capability_id="wolfram.cag.hints")
    assert credential is not None
    assert credential.entitled is True
    # Only a hash leaves the resolver; the raw secret is never on the object.
    assert not hasattr(credential, "secret")
    assert credential.credential_hash == "b" * 0 or len(credential.credential_hash) == 64
    assert SECRET_VALUE not in repr(credential)
    assert SECRET_VALUE not in str(dataclasses.asdict(credential))

    def resolver(capability_id):
        return (SECRET_VALUE, "wolfram-custom")

    cred2 = resolve_cag_credentials(
        capability_id="wolfram.cag.compute",
        credential_resolver=resolver,
    )
    assert cred2.provider == "wolfram-custom"
    assert SECRET_VALUE not in repr(cred2)

    # Not provisioned -> honest UNAVAILABLE.
    monkeypatch.delenv("WOLFRAM_CAG_APP_ID", raising=False)
    assert resolve_cag_credentials(capability_id="wolfram.cag.hints") is None


def test_provision_is_honest_unavailable_and_not_entitled():
    assert provision_cag_component(
        capability_id="wolfram.cag.hints",
        credential=None,
    ) is WolframCagStatus.UNAVAILABLE
    assert provision_cag_component(
        capability_id="wolfram.cag.hints",
        credential=_credential(entitled=False),
    ) is WolframCagStatus.NOT_ENTITLED
    assert provision_cag_component(
        capability_id="wolfram.cag.hints",
        credential=_credential(entitled=True),
    ) is WolframCagStatus.AVAILABLE
    assert provision_cag_component(
        capability_id="wolfram.cag.bogus",
        credential=_credential(),
    ) is WolframCagStatus.BLOCKED


def test_execute_succeeds_with_strict_schema_and_binds_request_ids():
    calls = {"n": 0}

    def transport(request, component, credential, credential_secret):
        calls["n"] += 1
        assert credential_secret is None
        return _outcome()

    receipt = execute_cag_request(
        _request(),
        credential=_credential(),
        transport=transport,
        schema_validator=_json_schema_validator(),
    )
    assert calls["n"] == 1
    assert receipt.status is WolframCagStatus.SUCCEEDED_UNVERIFIED
    assert receipt.response_status == 200
    assert receipt.response_uuid == "uuid-123"
    assert receipt.request_id == "req-456"
    assert receipt.rate_limit_remaining == "100"
    assert receipt.quota_remaining == "unlimited"
    assert len(receipt.response_hash) == 64
    assert "cannot mutate" in receipt.truth_notice


def test_two_xx_without_valid_schema_is_not_accepted_as_success():
    def transport(request, component, credential, credential_secret):
        return _outcome(body=b"not json at all")

    with pytest.raises(WolframCagError, match="schema validation") as exc:
        execute_cag_request(
            _request(),
            credential=_credential(),
            transport=transport,
            schema_validator=_json_schema_validator(),
        )
    assert exc.value.family is WolframCagErrorFamily.SCHEMA


def test_two_xx_with_wrong_content_type_is_rejected():
    def transport(request, component, credential, credential_secret):
        return _outcome(content_type="text/html", body=b"<html></html>")

    with pytest.raises(WolframCagError, match="content-type") as exc:
        execute_cag_request(
            _request(),
            credential=_credential(),
            transport=transport,
            schema_validator=lambda body, ct, comp: True,
        )
    assert exc.value.family is WolframCagErrorFamily.SCHEMA


def test_output_limit_is_enforced_and_testable():
    def transport(request, component, credential, credential_secret):
        return _outcome(body=b"x" * (WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.hints"].max_output_bytes + 1))

    with pytest.raises(WolframCagError, match="output limit") as exc:
        execute_cag_request(
            _request(),
            credential=_credential(),
            transport=transport,
            schema_validator=lambda body, ct, comp: True,
        )
    assert exc.value.family is WolframCagErrorFamily.SCHEMA


def test_error_families_are_distinguishable():
    assert classify_cag_status(status=401, timed_out=False) is WolframCagErrorFamily.AUTH
    assert classify_cag_status(status=403, timed_out=False) is WolframCagErrorFamily.AUTH
    assert classify_cag_status(status=402, timed_out=False) is WolframCagErrorFamily.ENTITLEMENT
    assert classify_cag_status(status=429, timed_out=False) is WolframCagErrorFamily.RATE_LIMIT
    assert classify_cag_status(status=503, timed_out=False) is WolframCagErrorFamily.UPSTREAM
    assert classify_cag_status(status=400, timed_out=False) is WolframCagErrorFamily.SCHEMA
    assert classify_cag_status(status=None, timed_out=True) is WolframCagErrorFamily.TIMEOUT
    assert classify_cag_status(status=None, timed_out=False) is WolframCagErrorFamily.UPSTREAM


def test_timeout_quota_auth_schema_errors_distinguishable_via_execute():
    cases = [
        (401, WolframCagErrorFamily.AUTH),
        (402, WolframCagErrorFamily.ENTITLEMENT),
        (429, WolframCagErrorFamily.RATE_LIMIT),
        (400, WolframCagErrorFamily.SCHEMA),
    ]
    for status, expected in cases:
        def transport(request, component, credential, credential_secret, _status=status):
            return _outcome(status=_status, body=b'{"result": "x"}')

        with pytest.raises(WolframCagError) as exc:
            execute_cag_request(
                _request(),
                credential=_credential(),
                transport=transport,
                schema_validator=_json_schema_validator(),
            )
        assert exc.value.family is expected
        assert exc.value.status == status


def test_unavailable_and_not_entitled_raise_honest_errors():
    def transport(request, component, credential, credential_secret):
        raise AssertionError("transport must not be called when not provisioned")

    with pytest.raises(WolframCagError, match="not provisioned") as exc:
        execute_cag_request(
            _request(),
            credential=None,
            transport=transport,
            schema_validator=lambda body, ct, comp: True,
        )
    assert exc.value.family is WolframCagErrorFamily.RESULT_UNAVAILABLE

    with pytest.raises(WolframCagError, match="not entitled") as exc:
        execute_cag_request(
            _request(),
            credential=_credential(entitled=False),
            transport=transport,
            schema_validator=lambda body, ct, comp: True,
        )
    assert exc.value.family is WolframCagErrorFamily.ENTITLEMENT


def test_bounded_retry_only_for_transient_families():
    assert cag_retry_decision(WolframCagErrorFamily.TIMEOUT, 1, 2) is WolframCagRetryDecision.SAFE_TO_RETRY
    assert cag_retry_decision(WolframCagErrorFamily.RATE_LIMIT, 1, 2) is WolframCagRetryDecision.SAFE_TO_RETRY
    assert cag_retry_decision(WolframCagErrorFamily.UPSTREAM, 1, 2) is WolframCagRetryDecision.SAFE_TO_RETRY
    assert cag_retry_decision(WolframCagErrorFamily.AUTH, 1, 2) is WolframCagRetryDecision.DO_NOT_RETRY
    assert cag_retry_decision(WolframCagErrorFamily.SCHEMA, 1, 2) is WolframCagRetryDecision.DO_NOT_RETRY
    assert cag_retry_decision(WolframCagErrorFamily.TIMEOUT, 3, 2) is WolframCagRetryDecision.DO_NOT_RETRY


def test_retry_exhausts_within_bound_and_does_not_retry_non_transient():
    attempts = {"n": 0}

    def transport(request, component, credential, credential_secret):
        attempts["n"] += 1
        return _outcome(status=500, body=b'{"result": "x"}')

    with pytest.raises(WolframCagError, match="status 500") as exc:
        execute_cag_request(
            _request(),
            credential=_credential(),
            transport=transport,
            schema_validator=_json_schema_validator(),
        )
    assert exc.value.family is WolframCagErrorFamily.UPSTREAM
    # hints has max_retries=2 => initial + 2 retries = 3 attempts total.
    assert attempts["n"] == 3

    attempts["n"] = 0

    def transport_auth(request, component, credential, credential_secret):
        attempts["n"] += 1
        return _outcome(status=401, body=b'{"result": "x"}')

    with pytest.raises(WolframCagError) as exc:
        execute_cag_request(
            _request(),
            credential=_credential(),
            transport=transport_auth,
            schema_validator=_json_schema_validator(),
        )
    assert exc.value.family is WolframCagErrorFamily.AUTH
    # AUTH never retries.
    assert attempts["n"] == 1


def test_cag_receipt_carries_bounded_evidence_and_no_secret_material():
    def transport(request, component, credential, credential_secret):
        return _outcome()

    receipt = execute_cag_request(
        _request(),
        credential=_credential(),
        transport=transport,
        schema_validator=_json_schema_validator(),
    )
    assert len(receipt.credential_hash) == 64
    assert len(receipt.request_hash) == 64
    assert len(receipt.response_hash) == 64
    # No raw secret anywhere in the receipt projection.
    assert SECRET_VALUE not in repr(receipt)
    receipt.validate()


def test_cag_response_cannot_directly_mutate_external_systems():
    def transport(request, component, credential, credential_secret):
        return _outcome()

    receipt = execute_cag_request(
        _request(),
        credential=_credential(),
        transport=transport,
        schema_validator=_json_schema_validator(),
    )
    # The receipt is purely observational: it carries no mutation handle.
    public_keys = set(WolframCagReceipt.__slots__)
    mutating = {"token", "secret", "authorization", "patch", "commit_sha", "deployment_id"}
    assert not (public_keys & mutating)
    assert "cannot mutate" in receipt.truth_notice


def test_error_public_payload_never_exposes_secret():
    err = WolframCagError(
        "boom",
        family=WolframCagErrorFamily.AUTH,
        status=401,
        response_uuid="uuid",
        request_id="req",
    )
    payload = err.public_payload()
    assert payload["family"] == "AUTH"
    assert payload["status"] == "401"
    assert SECRET_VALUE not in str(payload)
    assert "credential" not in payload


def test_canonical_and_mirror_cag_adapters_are_byte_equal():
    relative_paths = (
        "agent_runtime/adapters/__init__.py",
        "agent_runtime/adapters/wolfram_agenttools.py",
    )
    for relative in relative_paths:
        canonical = (ROOT / "backend" / relative).read_bytes()
        mirror = (MIRROR_ROOT / relative).read_bytes()
        assert canonical == mirror
        lowered = canonical.lower()
        assert b"firebase-tools" not in lowered
        assert b"firestore" not in lowered
