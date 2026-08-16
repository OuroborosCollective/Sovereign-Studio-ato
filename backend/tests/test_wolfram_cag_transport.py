"""Tests for the canonical, fail-closed Wolfram CAG Component transport (#1459).

These tests exercise the real live-path adapter module under
``backend/agent_runtime/adapters/wolfram_cag_transport.py`` via the same
dynamic module-loader pattern used by the rest of the agent-runtime suite.

The transport is intentionally fail-closed: without real provisioning
evidence from issue #1458, every component resolves to ``NOT_ENTITLED`` and no
live HTTP is performed. These tests therefore assert the honest fail-closed
behaviour, secret-safety, strict schema validation, and normalized error
families without mocking the Wolfram API.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIRROR_ROOT = ROOT / "scripts" / "sovereign-backend"

_PACKAGE = "_sovereign_issue_1459"


def _install_package(name: str, path: Path) -> None:
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_install_package(_PACKAGE, ROOT / "backend" / "agent_runtime")
_install_package(f"{_PACKAGE}.adapters", ROOT / "backend" / "agent_runtime" / "adapters")

cag = _load_module(
    f"{_PACKAGE}.adapters.wolfram_cag_transport",
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_cag_transport.py",
)

CagRequestV1 = cag.CagRequestV1
CagEntitlementVerdict = cag.CagEntitlementVerdict
CagEntitlementState = cag.CagEntitlementState
CagComponentStatus = cag.CagComponentStatus
CagVerdict = cag.CagVerdict
CagErrorFamily = cag.CagErrorFamily
CagTransportError = cag.CagTransportError
CAG_CAPABILITY_MAP = cag.CAG_CAPABILITY_MAP
CAG_CAPABILITY_IDS = cag.CAG_CAPABILITY_IDS
CAG_CONTRACT_VERSION = cag.CAG_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Capability projection
# ---------------------------------------------------------------------------

def test_four_cag_capabilities_projected_with_fixed_ids():
    assert set(CAG_CAPABILITY_IDS) == {
        "wolfram.cag.hints",
        "wolfram.cag.compute",
        "wolfram.cag.results",
        "wolfram.cag.context",
    }
    for cid, contract in CAG_CAPABILITY_MAP.items():
        assert contract.capability_id == cid
        assert contract.component_id == cid
        assert contract.read_only is True, f"{cid} must be read-only"
        assert contract.allows_free_execution is False, f"{cid} must not allow free execution"
        assert contract.base_host.startswith("https://"), f"{cid} must use https"


def test_no_free_model_url_or_endpoint_override():
    # Fixed endpoint identities only; no capability exposes a free URL param.
    for contract in CAG_CAPABILITY_MAP.values():
        assert contract.endpoint_id.startswith("cag.")
        assert contract.method in ("GET", "POST")


# ---------------------------------------------------------------------------
# Fail-closed without entitlement evidence (#1459 DoD)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("capability_id", CAG_CAPABILITY_IDS)
def test_component_not_entitled_without_evidence(capability_id):
    request = CagRequestV1(capability_id=capability_id, input_text="2+2")
    status = cag.resolve_component_status(capability_id, None)
    assert status is CagComponentStatus.NOT_ENTITLED
    # authorize must fail closed
    with pytest.raises(CagTransportError) as exc:
        cag.authorize_cag_call(request, None)
    assert exc.value.family is CagErrorFamily.ENTITLEMENT


@pytest.mark.parametrize("capability_id", CAG_CAPABILITY_IDS)
def test_not_entitled_receipt_is_honest(capability_id):
    request = CagRequestV1(capability_id=capability_id, input_text="derivative of x^2")
    receipt = cag.not_entitled_receipt(request)
    assert receipt.component_status is CagComponentStatus.NOT_ENTITLED
    assert receipt.verdict is CagVerdict.UNAVAILABLE
    assert receipt.error_family is CagErrorFamily.ENTITLEMENT
    assert receipt.response_status == 0
    # receipt must be self-consistent and valid
    receipt.validate()
    # truth boundary notice must be present and forbid runtime truth claims
    assert "repository" in receipt.truth_notice or "runtime" in receipt.truth_notice


def test_entitled_without_auth_evidence_hash_is_not_usable():
    # ENTITLED state without secret-free auth evidence hash is rejected
    verdict = CagEntitlementVerdict(
        component_id="wolfram.cag.compute",
        state=CagEntitlementState.ENTITLED,
        auth_evidence_hash="",
    )
    with pytest.raises(CagTransportError) as exc:
        verdict.validate()
    assert exc.value.family is CagErrorFamily.ENTITLEMENT
    assert verdict.is_usable() is False


def test_entitlement_wrong_component_does_not_authorize_other_component():
    verdict = CagEntitlementVerdict(
        component_id="wolfram.cag.hints",
        state=CagEntitlementState.ENTITLED,
        auth_evidence_hash="a" * 64,
    )
    request = CagRequestV1(capability_id="wolfram.cag.compute", input_text="x")
    status = cag.resolve_component_status("wolfram.cag.compute", verdict)
    assert status is CagComponentStatus.NOT_ENTITLED
    with pytest.raises(CagTransportError):
        cag.authorize_cag_call(request, verdict)


def test_entitled_with_valid_evidence_authorizes_bounded_call():
    verdict = CagEntitlementVerdict(
        component_id="wolfram.cag.compute",
        state=CagEntitlementState.ENTITLED,
        auth_evidence_hash="a" * 64,
        terms_version_date="2026-01-01",
    )
    assert verdict.is_usable() is True
    request = CagRequestV1(capability_id="wolfram.cag.compute", input_text="2+2")
    contract = cag.authorize_cag_call(request, verdict)
    assert contract.endpoint_id == "cag.compute.evaluate"
    assert contract.read_only is True


# ---------------------------------------------------------------------------
# Request validation / input bounding
# ---------------------------------------------------------------------------

def test_unknown_capability_rejected():
    request = CagRequestV1(capability_id="wolfram.cag.evil", input_text="x")
    with pytest.raises(CagTransportError):
        request.validate()


def test_empty_input_rejected():
    with pytest.raises(CagTransportError):
        CagRequestV1(capability_id="wolfram.cag.hints", input_text="   ").validate()


def test_oversized_input_rejected():
    big = "x" * (cag.DEFAULT_MAX_REQUEST_BYTES + 1)
    request = CagRequestV1(capability_id="wolfram.cag.hints", input_text=big)
    with pytest.raises(CagTransportError):
        request.validate()


def test_invalid_timeout_rejected():
    for bad in (0, -1, 61, 100):
        request = CagRequestV1(
            capability_id="wolfram.cag.hints", input_text="x", timeout_seconds=bad
        )
        with pytest.raises(CagTransportError):
            request.validate()


def test_input_hash_is_stable_and_secret_free():
    r1 = CagRequestV1(capability_id="wolfram.cag.compute", input_text="2+2")
    r2 = CagRequestV1(capability_id="wolfram.cag.compute", input_text="2+2")
    assert r1.input_hash == r2.input_hash
    assert len(r1.input_hash) == 64
    r3 = CagRequestV1(capability_id="wolfram.cag.compute", input_text="3+3")
    assert r3.input_hash != r1.input_hash


# ---------------------------------------------------------------------------
# Strict response validation: 2xx without schema is NOT success
# ---------------------------------------------------------------------------

def test_2xx_without_required_field_is_not_success():
    for cap, required in (
        ("wolfram.cag.results", "success"),
        ("wolfram.cag.context", "success"),
        ("wolfram.cag.hints", "result"),
        ("wolfram.cag.compute", "result"),
    ):
        with pytest.raises(CagTransportError) as exc:
            cag.validate_response_schema(cap, 200, "application/json", {"unrelated": True})
        assert exc.value.family is CagErrorFamily.SCHEMA


def test_2xx_valid_schema_passes():
    cag.validate_response_schema("wolfram.cag.results", 200, "application/json", {"success": True})
    cag.validate_response_schema("wolfram.cag.compute", 200, "application/json", {"result": "4"})


def test_non_json_content_type_rejected():
    with pytest.raises(CagTransportError) as exc:
        cag.validate_response_schema("wolfram.cag.compute", 200, "text/html", {"result": "4"})
    assert exc.value.family is CagErrorFamily.SCHEMA


def test_non_2xx_rejected():
    with pytest.raises(CagTransportError):
        cag.validate_response_schema("wolfram.cag.compute", 500, "application/json", {})


# ---------------------------------------------------------------------------
# Normalized error families (DoD: distinct failure families)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status, family",
    [
        (401, CagErrorFamily.AUTH),
        (403, CagErrorFamily.AUTH),
        (402, CagErrorFamily.QUOTA),
        (404, CagErrorFamily.RESULT_UNAVAILABLE),
        (429, CagErrorFamily.RATE_LIMIT),
        (500, CagErrorFamily.UPSTREAM),
        (503, CagErrorFamily.UPSTREAM),
    ],
)
def test_http_status_classifies_to_distinct_families(status, family):
    assert cag.classify_http_status(status) is family


def test_quota_and_auth_are_distinct_from_timeout_and_schema():
    assert cag.classify_http_status(402) is not cag.classify_http_status(401)
    assert CagErrorFamily.QUOTA is not CagErrorFamily.AUTH
    assert CagErrorFamily.TIMEOUT is not CagErrorFamily.RATE_LIMIT
    assert CagErrorFamily.SCHEMA is not CagErrorFamily.UPSTREAM


# ---------------------------------------------------------------------------
# Receipt secret-safety and truth boundary
# ---------------------------------------------------------------------------

def test_receipt_strips_credentials_from_response_hash():
    request = CagRequestV1(capability_id="wolfram.cag.compute", input_text="2+2")
    body_with_secret = {"result": "4", "appid": "SK-SECRET-VALUE", "token": "bearer-xyz"}
    body_without = {"result": "4"}
    r_with = cag.build_receipt(
        request, response_status=200, response_body=body_with_secret,
        response_uuid="u1", component_status=CagComponentStatus.READY,
        verdict=CagVerdict.SUPPORTED, latency_ms=42, quota_class="paid",
        bounded_summary="4",
    )
    r_without = cag.build_receipt(
        request, response_status=200, response_body=body_without,
        response_uuid="u1", component_status=CagComponentStatus.READY,
        verdict=CagVerdict.SUPPORTED, latency_ms=42, quota_class="paid",
        bounded_summary="4",
    )
    # Credentials are stripped before hashing -> identical response hashes.
    assert r_with.response_hash == r_without.response_hash
    # And no secret leaks into any receipt field.
    import json
    from dataclasses import asdict
    blob = json.dumps(asdict(r_with))
    assert "SK-SECRET" not in blob
    assert "bearer-xyz" not in blob


def test_supported_verdict_requires_ready_status():
    request = CagRequestV1(capability_id="wolfram.cag.compute", input_text="2+2")
    with pytest.raises(CagTransportError):
        cag.build_receipt(
            request, response_status=200, response_body={"result": "4"},
            response_uuid="u1", component_status=CagComponentStatus.UNAVAILABLE,
            verdict=CagVerdict.SUPPORTED, latency_ms=42, quota_class="paid",
        )


def test_receipt_cannot_self_assert_verified():
    # CagVerdict has no VERIFIED member at all; that truth class is reserved
    # for the Sovereign Evidence/Judge lane (#1460).
    assert not hasattr(CagVerdict, "VERIFIED")
    assert CagVerdict.SUPPORTED is not None  # bounded verdicts exist


def test_receipt_truth_notice_present():
    request = CagRequestV1(capability_id="wolfram.cag.hints", input_text="x")
    receipt = cag.not_entitled_receipt(request)
    assert receipt.truth_notice
    assert "supplemental" in receipt.truth_notice.lower()


# ---------------------------------------------------------------------------
# Mirror parity (canonical == deployment mirror)
# ---------------------------------------------------------------------------

def test_canonical_and_mirror_cag_transport_are_byte_equal():
    canonical = (ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_cag_transport.py").read_bytes()
    mirror = (MIRROR_ROOT / "agent_runtime" / "adapters" / "wolfram_cag_transport.py").read_bytes()
    assert canonical == mirror


def test_canonical_and_mirror_adapters_init_are_byte_equal():
    canonical = (ROOT / "backend" / "agent_runtime" / "adapters" / "__init__.py").read_bytes()
    mirror = (MIRROR_ROOT / "agent_runtime" / "adapters" / "__init__.py").read_bytes()
    assert canonical == mirror
