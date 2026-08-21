from __future__ import annotations

import dataclasses
import importlib
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
execute_live_cag_request = wolfram_module.execute_live_cag_request
is_wolfram_capability = wolfram_module.is_wolfram_capability
provision_cag_component = wolfram_module.provision_cag_component
read_cag_secret_file = wolfram_module.read_cag_secret_file
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
        if component.expected_content_type == "text/plain":
            try:
                return bool(body.decode("utf-8").strip())
            except UnicodeDecodeError:
                return False
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
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.hints"].base_url == "https://services.wolfram.com/api/cag/v1/WolframLanguageHints"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.compute"].base_url == "https://services.wolfram.com/api/cag/v1/WolframLanguageCompute"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.results"].base_url == "https://services.wolfram.com/api/cag/v1/WolframAlphaResult"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.context"].base_url == "https://services.wolfram.com/api/cag/v1/WolframAlphaContext"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.results"].expected_content_type == "text/plain"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.results"].method == "GET"
    assert WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.context"].method == "POST"
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
    # Request payload size is enforced against the component contract, not
    # merely declared.
    with pytest.raises(WolframCagError, match="request size must be non-negative"):
        _request(request_size_bytes=-1).validate()
    with pytest.raises(WolframCagError, match="request payload exceeds component limit"):
        _request(request_size_bytes=component.max_request_bytes + 1).validate()
    # A request at exactly the limit is accepted.
    _request(request_size_bytes=component.max_request_bytes).validate()


def test_request_size_limit_is_testable_per_component_and_bound_into_hash():
    # Each component declares a distinct, finite request limit that is
    # individually enforceable, satisfying #1459's "Requestlimits sind testbar".
    for capability_id, component in WOLFRAM_CAG_COMPONENT_MAP.items():
        assert component.max_request_bytes > 0
        at_limit = _request(
            capability_id=capability_id,
            request_size_bytes=component.max_request_bytes,
        )
        assert at_limit.validate().capability_id == capability_id
        over_limit = _request(
            capability_id=capability_id,
            request_size_bytes=component.max_request_bytes + 1,
        )
        with pytest.raises(WolframCagError, match="request payload exceeds component limit") as exc:
            over_limit.validate()
        assert exc.value.family is WolframCagErrorFamily.SCHEMA
    # The declared request size is part of the deterministic receipt identity,
    # so two equal requests with different sizes produce different hashes.
    base = _request(request_size_bytes=0)
    sized = _request(request_size_bytes=1024)
    assert base.request_hash != sized.request_hash


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


def test_owner_managed_credential_file_is_preferred_and_permission_bounded(monkeypatch, tmp_path):
    secret_path = tmp_path / "wolfram_cag_api_key.txt"
    secret_path.write_text(SECRET_VALUE + "\n", encoding="utf-8")
    secret_path.chmod(0o600)
    monkeypatch.setattr(wolfram_module, "DEFAULT_WOLFRAM_CAG_API_KEY_FILE", str(secret_path))
    monkeypatch.setenv("WOLFRAM_CAG_API_KEY_FILE", str(secret_path))
    monkeypatch.setenv("WOLFRAM_CAG_APP_ID", "legacy-must-not-win")

    assert read_cag_secret_file(str(secret_path)) == SECRET_VALUE
    credential = resolve_cag_credentials(capability_id="wolfram.cag.hints")
    assert credential is not None
    assert credential.provider == "wolfram-owner-file"
    assert SECRET_VALUE not in repr(credential)

    secret_path.chmod(0o644)
    with pytest.raises(WolframCagError, match="permissions are too broad") as exc:
        read_cag_secret_file(str(secret_path))
    assert exc.value.family is WolframCagErrorFamily.AUTH

    secret_path.chmod(0o600)
    secret_path.write_bytes(b"x" * (wolfram_module.MAX_WOLFRAM_CAG_API_KEY_BYTES + 1))
    with pytest.raises(WolframCagError, match="size is invalid") as exc:
        read_cag_secret_file(str(secret_path))
    assert exc.value.family is WolframCagErrorFamily.AUTH


def test_non_allowlisted_cag_secret_path_is_rejected_before_open(monkeypatch, tmp_path):
    canonical = tmp_path / "canonical.txt"
    canonical.write_text(SECRET_VALUE, encoding="utf-8")
    canonical.chmod(0o600)
    monkeypatch.setattr(wolfram_module, "DEFAULT_WOLFRAM_CAG_API_KEY_FILE", str(canonical))
    with pytest.raises(WolframCagError, match="path is not allowlisted") as exc:
        read_cag_secret_file(str(tmp_path / "other.txt"))
    assert exc.value.family is WolframCagErrorFamily.AUTH


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


class _LiveResponse:
    def __init__(self, status_code: int, content_type: str, body: bytes, *, headers=None) -> None:
        self.status_code = status_code
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size=16384):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start:start + chunk_size]

    def close(self):
        self.closed = True


class _LiveSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected live CAG request")
        return self.responses.pop(0)


def _live_json(uuid_value: str) -> bytes:
    return (
        '{"result":"ok","code":0,"success":true,"uuid":"' + uuid_value + '"}'
    ).encode("utf-8")


def test_live_transport_uses_current_contract_and_authorization_only_at_http_boundary():
    session = _LiveSession([
        _LiveResponse(200, "application/json", _live_json("uuid-hints")),
        _LiveResponse(200, "application/json; charset=utf-8", _live_json("uuid-compute")),
        _LiveResponse(200, "text/plain; charset=utf-8", b"Query:\n2+2\n\nResult:\n4\n"),
        _LiveResponse(200, "application/json", _live_json("uuid-context")),
    ])

    def resolver(*, capability_id):
        assert capability_id in WOLFRAM_CAG_COMPONENT_MAP
        return SECRET_VALUE, "wolfram-test"

    requests_and_payloads = [
        ("wolfram.cag.hints", {"context": "Draw a pentagram"}),
        ("wolfram.cag.compute", {"code": "Sin[Pi]", "maxChars": 256}),
        ("wolfram.cag.results", {"input": "2+2"}),
        ("wolfram.cag.context", {"context": "speed of a cheetah", "count": 2}),
    ]
    receipts = [
        execute_live_cag_request(
            capability_id=capability_id,
            payload=payload,
            credential_resolver=resolver,
            session=session,
        )
        for capability_id, payload in requests_and_payloads
    ]

    assert [call["method"] for call in session.calls] == ["POST", "POST", "GET", "POST"]
    assert [call["url"] for call in session.calls] == [
        "https://services.wolfram.com/api/cag/v1/WolframLanguageHints",
        "https://services.wolfram.com/api/cag/v1/WolframLanguageCompute",
        "https://services.wolfram.com/api/cag/v1/WolframAlphaResult",
        "https://services.wolfram.com/api/cag/v1/WolframAlphaContext",
    ]
    for call in session.calls:
        assert call["headers"]["Authorization"] == SECRET_VALUE
        assert call["allow_redirects"] is False
        assert "authorization" not in str(call.get("params") or {}).casefold()
        assert SECRET_VALUE not in str(call.get("params") or {})
        assert SECRET_VALUE not in str(call.get("data") or b"")
    assert session.calls[2]["params"] == {"input": "2+2"}
    assert "Content-Type" not in session.calls[2]["headers"]
    assert session.calls[0]["headers"]["Content-Type"] == "application/json"
    assert all(receipt.status is WolframCagStatus.SUCCEEDED_UNVERIFIED for receipt in receipts)
    assert receipts[0].response_uuid == "uuid-hints"
    assert receipts[1].response_uuid == "uuid-compute"
    assert receipts[3].response_uuid == "uuid-context"
    assert all(SECRET_VALUE not in repr(receipt) for receipt in receipts)


def test_live_transport_rejects_credential_payload_and_501_without_retry():
    def resolver(*, capability_id):
        return SECRET_VALUE, "wolfram-test"

    with pytest.raises(WolframCagError, match="credential-shaped") as exc:
        execute_live_cag_request(
            capability_id="wolfram.cag.hints",
            payload={"context": "safe", "authorization": "forbidden"},
            credential_resolver=resolver,
            session=_LiveSession([]),
        )
    assert exc.value.family is WolframCagErrorFamily.SCHEMA

    session = _LiveSession([
        _LiveResponse(501, "text/plain; charset=utf-8", b"No result"),
    ])
    with pytest.raises(WolframCagError) as exc:
        execute_live_cag_request(
            capability_id="wolfram.cag.results",
            payload={"input": "intentionally unavailable"},
            credential_resolver=resolver,
            session=session,
        )
    assert exc.value.family is WolframCagErrorFamily.RESULT_UNAVAILABLE
    assert len(session.calls) == 1


def test_live_transport_fails_closed_if_credential_rotates_between_projection_and_send():
    values = iter(["first-secret", "second-secret"])

    def resolver(*, capability_id):
        return next(values), "wolfram-test"

    session = _LiveSession([])
    with pytest.raises(WolframCagError, match="changed before transport") as exc:
        execute_live_cag_request(
            capability_id="wolfram.cag.hints",
            payload={"context": "safe"},
            credential_resolver=resolver,
            session=session,
        )
    assert exc.value.family is WolframCagErrorFamily.AUTH
    assert session.calls == []


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
    assert classify_cag_status(status=501, timed_out=False) is WolframCagErrorFamily.RESULT_UNAVAILABLE
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


def test_adapters_package_reexports_supplemental_only():
    """Every name in adapters.__all__ must be importable from the package.

    Regression guard: an earlier change extended wolfram_agenttools with CAG
    adapters but dropped ``SUPPLEMENTAL_ONLY`` from the package import block
    while still listing it in ``__all__``, so
    ``from agent_runtime.adapters import SUPPLEMENTAL_ONLY`` raised
    ``ImportError``. The mirror at scripts/sovereign-backend must stay
    byte-equal, so it is exercised through the same path.
    """
    adapters_pkg = _load_module(
        f"{_PACKAGE}.adapters",
        ROOT / "backend" / "agent_runtime" / "adapters" / "__init__.py",
    )
    adapters_pkg.__path__ = [
        str(ROOT / "backend" / "agent_runtime" / "adapters")
    ]
    assert "SUPPLEMENTAL_ONLY" in adapters_pkg.__all__
    # Every advertised public name must resolve through the package re-export.
    for name in adapters_pkg.__all__:
        assert hasattr(adapters_pkg, name), (
            f"adapters.__all__ advertises {name!r} but it is not importable "
            f"from the package; the import block in __init__.py is stale."
        )
    assert adapters_pkg.SUPPLEMENTAL_ONLY == "SUPPLEMENTAL_ONLY"
    assert adapters_pkg.CAG_SUPPLEMENTAL_ONLY == adapters_pkg.SUPPLEMENTAL_ONLY
