from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

import freemium_product_architect_tools as tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: list[tuple[str, object, str]] = []

    def tool(self, *, annotations):
        def decorator(function):
            self.tools.append((function.__name__, annotations, function.__doc__ or ""))
            return function

        return decorator


@pytest.fixture(autouse=True)
def reset_registration(monkeypatch) -> None:
    monkeypatch.setattr(tools, "_REGISTERED", False)


def _evidence(publisher: str, categories: list[str], suffix: str) -> tools.MarketEvidence:
    return tools.MarketEvidence(
        claim=f"Quantitative market claim {suffix}",
        metric=f"cost and manual gap {suffix}",
        value="42 percent",
        publisher=publisher,
        source_url=f"https://evidence.example/{suffix}",
        source_type="primary",
        published_at="2026-06-01",
        accessed_at="2026-07-19",
        geography="global",
        method="published dataset",
        categories=categories,
    )


def _candidate(candidate_id: str, score_offset: int = 0, *, gated: bool = True) -> tools.MarketCandidate:
    evidence = []
    if gated:
        evidence = [
            _evidence("Publisher A", ["demand", "economic"], f"{candidate_id}-a"),
            _evidence("Publisher B", ["supply-gap"], f"{candidate_id}-b"),
        ]
    return tools.MarketCandidate(
        id=candidate_id,
        name=f"Candidate {candidate_id}",
        scores=tools.MarketScores(
            demand=20 + score_offset,
            pain=16,
            willingness_to_pay=15,
            supply_gap=10,
            agent_fit=13,
            friction_penalty=-6,
        ),
        evidence=evidence,
        invalidation_test="Reject when ten buyer interviews show no paid urgency.",
    )


def _good_contract():
    offer = tools.freemium_offer_contract_build(
        "chatgpt-mcp-app",
        "Evidence Operator",
        "evidence-operator",
        "ai-governance",
        "Calm evidence-first system operator",
        ["Gap analysis"],
        ["Persisted evidence pack"],
        "Persist or export verified results.",
    )
    product_tools = [tools.ProductToolContract.model_validate(item) for item in offer.tools]
    endpoints = [
        tools.EndpointContract(role="free-analysis", method="POST", path="/api/v1/analyze-free", auth="none", mutates=False),
        tools.EndpointContract(role="checkout-create", method="POST", path="/api/v1/payments/checkout", auth="oauth2", mutates=True),
        tools.EndpointContract(role="payment-webhook", method="POST", path="/api/v1/webhooks/payment", auth="webhook-signature", mutates=True),
        tools.EndpointContract(role="entitlement-read", method="GET", path="/api/v1/entitlements/current", auth="oauth2", mutates=False),
        tools.EndpointContract(role="paid-execution", method="POST", path="/api/v1/executions", auth="oauth2", mutates=True),
        tools.EndpointContract(role="run-status", method="GET", path="/api/v1/runs/{run_id}", auth="oauth2", mutates=False),
        tools.EndpointContract(role="artifact-manifest", method="GET", path="/api/v1/runs/{run_id}/artifacts", auth="oauth2", mutates=False),
        tools.EndpointContract(role="oauth-protected-resource", method="GET", path="/.well-known/oauth-protected-resource", auth="none", mutates=False),
        tools.EndpointContract(role="oauth-authorization-metadata", method="GET", path="/.well-known/oauth-authorization-server", auth="none", mutates=False),
    ]
    auth = tools.AuthContract(
        mode="oauth2.1-pkce",
        token_transport="authorization-header-context",
        server_side_entitlement=True,
        token_as_tool_argument=False,
        pkce_s256=True,
        resource_audience_bound=True,
    )
    payment = tools.PaymentContract(
        provider="external checkout",
        external_checkout=True,
        webhook_signature_verified=True,
        idempotency_keys=True,
        raw_card_data_accepted_by_tool=False,
        entitlement_source="persisted server-side entitlement",
    )
    return product_tools, endpoints, auth, payment


def test_registers_five_read_only_tools() -> None:
    mcp = FakeMCP()
    tools.register(mcp)

    assert [name for name, _, _ in mcp.tools] == [
        "freemium_product_tool_inventory",
        "freemium_market_opportunity_score",
        "freemium_offer_contract_build",
        "freemium_product_contract_validate",
        "freemium_product_bundle_manifest",
    ]
    for _, annotations, description in mcp.tools:
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is True
        assert annotations.openWorldHint is False
        assert description.startswith("Use this when")


def test_fastmcp_contract_has_output_schemas_and_bounded_inputs() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("freemium-product-architect-contract-test")
    tools.register(mcp)
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    assert set(registered) == {
        "freemium_product_tool_inventory",
        "freemium_market_opportunity_score",
        "freemium_offer_contract_build",
        "freemium_product_contract_validate",
        "freemium_product_bundle_manifest",
    }
    for tool in registered.values():
        assert tool.output_schema["type"] == "object"
        assert tool.output_schema["required"]
        assert tool.annotations.readOnlyHint is True

    candidate_schema = registered["freemium_market_opportunity_score"].parameters["properties"]["candidates"]
    assert candidate_schema["minItems"] == 3
    assert candidate_schema["maxItems"] == 3
    offer_schema = registered["freemium_offer_contract_build"].parameters["properties"]
    assert offer_schema["free_deliverables"]["minItems"] == 1
    assert offer_schema["free_deliverables"]["maxItems"] == 12


def test_market_score_is_deterministic_but_never_claims_external_verification() -> None:
    result = tools.freemium_market_opportunity_score(
        [_candidate("alpha", 1), _candidate("beta"), _candidate("gamma", -1)],
        "2026-07-19",
        "EU and global",
    )

    assert result.status == "INPUT_MARKET_EVIDENCE_GATED"
    assert result.selectedCandidateId == "alpha"
    assert result.selectedScore == 69
    assert result.externallyVerified is False
    assert result.runtimeVerified is False
    assert result.mutationPerformed is False
    assert all(item["evidenceGate"] == "INPUT_EVIDENCE_GATE_MET" for item in result.candidates)


def test_market_score_marks_missing_evidence_as_hypothesis() -> None:
    result = tools.freemium_market_opportunity_score(
        [_candidate("alpha", gated=False), _candidate("beta", gated=False), _candidate("gamma", gated=False)],
        "2026-07-19",
        "global",
    )

    assert result.status == "RESEARCH_HYPOTHESIS"
    assert all(item["evidenceGate"] == "HYPOTHESIS_INSUFFICIENT_EVIDENCE" for item in result.candidates)


def test_offer_contract_separates_free_paid_and_request_context_auth() -> None:
    result = tools.freemium_offer_contract_build(
        "chatgpt-mcp-app",
        "Evidence Operator",
        "evidence-operator",
        "ai-governance",
        "Calm evidence-first system operator",
        ["Gap analysis"],
        ["Persisted evidence pack"],
        "Persist or export verified results.",
    )

    assert result.status == "OFFER_CONTRACT_PLANNED_NOT_IMPLEMENTED"
    assert result.authBoundary["tokenAsToolArgument"] is False
    assert result.authBoundary["serverSideEntitlementRequired"] is True
    assert {item["tier"] for item in result.tools} >= {"free", "paid"}
    assert "oauth-protected-resource" in result.endpointRoles
    assert result.runtimeVerified is False
    assert result.paymentVerified is False
    assert all(not any("token" in field.casefold() for field in item["input_fields"]) for item in result.tools)


def test_contract_validator_accepts_complete_contract_without_claiming_runtime() -> None:
    product_tools, endpoints, auth, payment = _good_contract()

    result = tools.freemium_product_contract_validate(
        "chatgpt-mcp-app",
        product_tools,
        endpoints,
        auth,
        payment,
    )

    assert result.status == "STATIC_CONTRACT_VALIDATED"
    assert result.ok is True
    assert len(result.contractSha256) == 64
    assert result.runtimeVerified is False
    assert result.paymentVerified is False


def test_contract_validator_rejects_secret_input_unauthenticated_paid_tool_and_missing_oauth() -> None:
    product_tools, endpoints, auth, payment = _good_contract()
    paid = product_tools[3].model_copy(update={
        "auth": "none",
        "input_fields": ["executionSpec", "access_token"],
        "annotations": tools.ToolHints(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    })
    product_tools[3] = paid
    endpoints = [endpoint for endpoint in endpoints if not endpoint.role.startswith("oauth-")]

    result = tools.freemium_product_contract_validate(
        "chatgpt-mcp-app",
        product_tools,
        endpoints,
        auth,
        payment,
    )

    assert result.status == "CONTRACT_BLOCKED"
    assert "PAID_TOOL_UNAUTHENTICATED:execute_paid" in result.errors
    assert "MODEL_VISIBLE_SECRET_INPUT:execute_paid:access_token" in result.errors
    assert "MUTATING_TOOL_MARKED_READ_ONLY:execute_paid" in result.errors
    assert "MCP_OAUTH_ENDPOINT_ROLE_MISSING:oauth-protected-resource" in result.errors


def test_contract_validator_rejects_endpoint_auth_method_and_mutation_drift() -> None:
    product_tools, endpoints, auth, payment = _good_contract()
    endpoints[1] = endpoints[1].model_copy(update={"method": "GET", "auth": "none", "mutates": False})
    endpoints[2] = endpoints[2].model_copy(update={"auth": "none"})

    result = tools.freemium_product_contract_validate(
        "chatgpt-mcp-app",
        product_tools,
        endpoints,
        auth,
        payment,
    )

    assert result.status == "CONTRACT_BLOCKED"
    assert "ENDPOINT_METHOD_INVALID:checkout-create:GET" in result.errors
    assert "ENDPOINT_MUTATION_INVALID:checkout-create" in result.errors
    assert "PROTECTED_ENDPOINT_AUTH_INVALID:checkout-create:none" in result.errors
    assert "PAYMENT_WEBHOOK_SIGNATURE_AUTH_REQUIRED" in result.errors


def test_bundle_manifest_is_secret_free_and_does_not_write_or_claim_deployment() -> None:
    result = tools.freemium_product_bundle_manifest(
        "chatgpt-mcp-app",
        "evidence-operator",
        "https://operator.example",
        "https://auth.operator.example",
    )
    payload = asdict(result)

    assert result.status == "PRODUCT_KIT_MANIFEST_READY_NOT_WRITTEN"
    assert result.archiveWritten is False
    assert result.mutationPerformed is False
    assert result.deploymentVerified is False
    assert all(item["status"] == "REQUIRED_NOT_WRITTEN" for item in result.files)
    assert "PAYMENT_PROVIDER_SECRET" in result.requiredEnvironmentVariables
    assert "secretValuesReturned" in payload and payload["secretValuesReturned"] is False


def test_launcher_image_installer_and_ci_include_freemium_product_module() -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "launcher.py").read_text("utf-8")
    dockerfile = (root / "Dockerfile").read_text("utf-8")
    installer = (root / "deploy" / "install-on-vps.sh").read_text("utf-8")
    workflow = (root.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")

    assert "import freemium_product_architect_tools" in launcher
    assert "freemium_product_architect_tools.register(server.mcp)" in launcher
    assert "freemium_product_architect_tools.py" in dockerfile
    assert "freemium_product_architect_tools.py" in installer
    assert "import freemium_product_architect_tools" in installer
    assert workflow.count("freemium_product_architect_tools.py") >= 3
    assert "import freemium_product_architect_tools" in workflow
