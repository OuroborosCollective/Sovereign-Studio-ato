from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlparse

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field


LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

Surface = Literal["custom-gpt-action", "chatgpt-mcp-app", "docker-mcp-agent"]
Tier = Literal["free", "conversion", "paid"]
ToolAuth = Literal["none", "oauth2", "private-gateway"]
EndpointAuth = Literal["none", "oauth2", "private-gateway", "webhook-signature"]
EvidenceCategory = Literal["demand", "economic", "supply-gap", "competition", "agent-fit"]
ProductName = Annotated[str, Field(min_length=3, max_length=120)]
ProductSlug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")]
NicheId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")]
BoundedText = Annotated[str, Field(min_length=3, max_length=800)]
HttpsUrl = Annotated[str, Field(pattern=r"^https://[^\s]+$")]

_REGISTERED = False
_SECRET_INPUT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:access.?token|refresh.?token|api.?key|client.?secret|webhook.?secret|password|passwd|"
    r"card.?number|\bcvv\b|\bcvc\b|private.?key)",
    re.I,
)
_TOOL_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_REQUIRED_ENDPOINT_ROLES: Final[frozenset[str]] = frozenset({
    "free-analysis",
    "checkout-create",
    "payment-webhook",
    "entitlement-read",
    "paid-execution",
    "run-status",
    "artifact-manifest",
})
_MCP_OAUTH_ENDPOINT_ROLES: Final[frozenset[str]] = frozenset({
    "oauth-protected-resource",
    "oauth-authorization-metadata",
})
_ENDPOINT_BEHAVIOR: Final[dict[str, tuple[str, bool]]] = {
    "free-analysis": ("POST", False),
    "checkout-create": ("POST", True),
    "payment-webhook": ("POST", True),
    "entitlement-read": ("GET", False),
    "paid-execution": ("POST", True),
    "run-status": ("GET", False),
    "artifact-manifest": ("GET", False),
    "oauth-protected-resource": ("GET", False),
    "oauth-authorization-metadata": ("GET", False),
}
_PROTECTED_ENDPOINT_ROLES: Final[frozenset[str]] = frozenset({
    "checkout-create",
    "entitlement-read",
    "paid-execution",
    "run-status",
    "artifact-manifest",
})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketEvidence(StrictModel):
    claim: Annotated[str, Field(min_length=8, max_length=800)]
    metric: Annotated[str, Field(min_length=2, max_length=160)]
    value: Annotated[str, Field(min_length=1, max_length=160)]
    publisher: Annotated[str, Field(min_length=2, max_length=160)]
    source_url: HttpsUrl
    source_type: Literal["government", "regulator", "standards", "primary", "audited-filing", "industry-research"]
    published_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    accessed_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    geography: Annotated[str, Field(min_length=2, max_length=120)]
    method: Annotated[str, Field(min_length=2, max_length=300)]
    categories: Annotated[list[EvidenceCategory], Field(min_length=1, max_length=5)]


class MarketScores(StrictModel):
    demand: Annotated[int, Field(ge=0, le=25)]
    pain: Annotated[int, Field(ge=0, le=20)]
    willingness_to_pay: Annotated[int, Field(ge=0, le=20)]
    supply_gap: Annotated[int, Field(ge=0, le=15)]
    agent_fit: Annotated[int, Field(ge=0, le=15)]
    friction_penalty: Annotated[int, Field(ge=-15, le=0)]


class MarketCandidate(StrictModel):
    id: NicheId
    name: Annotated[str, Field(min_length=3, max_length=160)]
    scores: MarketScores
    evidence: Annotated[list[MarketEvidence], Field(max_length=12)]
    invalidation_test: Annotated[str, Field(min_length=8, max_length=500)]


class ToolHints(StrictModel):
    readOnlyHint: bool
    destructiveHint: bool
    openWorldHint: bool
    idempotentHint: bool = True


class ProductToolContract(StrictModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    description: Annotated[str, Field(min_length=12, max_length=500)]
    tier: Tier
    auth: ToolAuth
    input_fields: Annotated[list[str], Field(max_length=32)]
    output_fields: Annotated[list[str], Field(min_length=1, max_length=32)]
    annotations: ToolHints


class EndpointContract(StrictModel):
    role: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")]
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: Annotated[str, Field(pattern=r"^/[A-Za-z0-9_{}./-]{1,255}$")]
    auth: EndpointAuth
    mutates: bool


class AuthContract(StrictModel):
    mode: Literal["oauth2.1-pkce", "custom-gpt-oauth", "private-gateway"]
    token_transport: Literal["authorization-header-context"]
    server_side_entitlement: Literal[True]
    token_as_tool_argument: Literal[False]
    pkce_s256: bool
    resource_audience_bound: bool


class PaymentContract(StrictModel):
    provider: Annotated[str, Field(min_length=2, max_length=120)]
    external_checkout: Literal[True]
    webhook_signature_verified: Literal[True]
    idempotency_keys: Literal[True]
    raw_card_data_accepted_by_tool: Literal[False]
    entitlement_source: Annotated[str, Field(min_length=8, max_length=240)]


@dataclass(frozen=True)
class ToolInventoryResult:
    schemaVersion: str
    ok: bool
    status: str
    tools: list[dict[str, Any]]
    boundaries: dict[str, Any]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


@dataclass(frozen=True)
class MarketScoreResult:
    schemaVersion: str
    ok: bool
    status: str
    asOf: str
    geography: str
    candidates: list[dict[str, Any]]
    selectedCandidateId: str
    selectedScore: int
    externallyVerified: bool
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


@dataclass(frozen=True)
class OfferContractResult:
    schemaVersion: str
    ok: bool
    status: str
    product: dict[str, Any]
    offer: dict[str, Any]
    tools: list[dict[str, Any]]
    endpointRoles: list[str]
    authBoundary: dict[str, Any]
    mutationPerformed: bool
    runtimeVerified: bool
    paymentVerified: bool
    secretValuesReturned: bool
    truthNotice: str


@dataclass(frozen=True)
class ContractValidationResult:
    schemaVersion: str
    ok: bool
    status: str
    contractSha256: str
    errors: list[str]
    warnings: list[str]
    requiredEndpointRoles: list[str]
    mutationPerformed: bool
    runtimeVerified: bool
    paymentVerified: bool
    secretValuesReturned: bool


@dataclass(frozen=True)
class BundleManifestResult:
    schemaVersion: str
    ok: bool
    status: str
    surface: str
    productSlug: str
    files: list[dict[str, Any]]
    requiredEnvironmentVariables: list[str]
    validationGates: list[str]
    manifestSha256: str
    archiveWritten: bool
    mutationPerformed: bool
    runtimeVerified: bool
    deploymentVerified: bool
    secretValuesReturned: bool


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _model_dict(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _valid_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def freemium_product_tool_inventory() -> ToolInventoryResult:
    """Use this when you need the exact deterministic Freemium MCP architect tool surface and its truth boundaries."""
    return ToolInventoryResult(
        schemaVersion="sovereign.freemium-product-architect-inventory.v1",
        ok=True,
        status="FREEMIUM_PRODUCT_ARCHITECT_TOOLS_READY",
        tools=[
            {"name": "freemium_market_opportunity_score", "purpose": "Score exactly three evidence records without browsing", "mutates": False},
            {"name": "freemium_offer_contract_build", "purpose": "Build a free/paid offer and tool contract", "mutates": False},
            {"name": "freemium_product_contract_validate", "purpose": "Fail closed on auth, payment, endpoint, and tool-schema defects", "mutates": False},
            {"name": "freemium_product_bundle_manifest", "purpose": "Plan a surface-specific contract bundle without writing it", "mutates": False},
        ],
        boundaries={
            "webResearchPerformed": False,
            "inputEvidenceExternallyVerified": False,
            "checkoutCreated": False,
            "paymentVerified": False,
            "entitlementGranted": False,
            "archiveWritten": False,
            "runtimeSuccessClaimed": False,
            "tokensAcceptedAsToolArguments": False,
        },
        mutationPerformed=False,
        runtimeVerified=False,
        secretValuesReturned=False,
    )


def freemium_market_opportunity_score(
    candidates: Annotated[list[MarketCandidate], Field(min_length=3, max_length=3)],
    as_of: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    geography: Annotated[str, Field(min_length=2, max_length=160)],
) -> MarketScoreResult:
    """Use this when three current niche candidates and their cited evidence need deterministic scoring without a false external-validation claim."""
    if not _valid_iso_date(as_of):
        raise ValueError("as_of must be a real ISO date")
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        scores = candidate.scores
        total = (
            scores.demand
            + scores.pain
            + scores.willingness_to_pay
            + scores.supply_gap
            + scores.agent_fit
            + scores.friction_penalty
        )
        publishers = {item.publisher.strip().casefold() for item in candidate.evidence}
        categories = {category for item in candidate.evidence for category in item.categories}
        dates_valid = all(_valid_iso_date(item.published_at) and _valid_iso_date(item.accessed_at) for item in candidate.evidence)
        urls_valid = all(_valid_https_url(item.source_url) for item in candidate.evidence)
        gate = (
            len(publishers) >= 2
            and {"demand", "economic", "supply-gap"}.issubset(categories)
            and dates_valid
            and urls_valid
        )
        scored.append({
            "id": candidate.id,
            "name": candidate.name,
            "score": total,
            "evidenceRecords": len(candidate.evidence),
            "independentPublishers": len(publishers),
            "evidenceGate": "INPUT_EVIDENCE_GATE_MET" if gate else "HYPOTHESIS_INSUFFICIENT_EVIDENCE",
            "invalidationTest": candidate.invalidation_test,
            "sourceUrls": sorted({item.source_url for item in candidate.evidence}),
        })
    scored.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    gated = all(item["evidenceGate"] == "INPUT_EVIDENCE_GATE_MET" for item in scored)
    selected = scored[0]
    return MarketScoreResult(
        schemaVersion="sovereign.freemium-market-score.v1",
        ok=True,
        status="INPUT_MARKET_EVIDENCE_GATED" if gated else "RESEARCH_HYPOTHESIS",
        asOf=as_of,
        geography=geography,
        candidates=scored,
        selectedCandidateId=str(selected["id"]),
        selectedScore=int(selected["score"]),
        externallyVerified=False,
        mutationPerformed=False,
        runtimeVerified=False,
        secretValuesReturned=False,
        truthNotice="The tool validates and scores supplied evidence only; it does not browse or independently verify publishers, metrics, market truth, or willingness to pay.",
    )


def _planned_tool(
    name: str,
    description: str,
    tier: Tier,
    auth: ToolAuth,
    input_fields: list[str],
    output_fields: list[str],
    *,
    read_only: bool,
) -> dict[str, Any]:
    return _model_dict(ProductToolContract(
        name=name,
        description=description,
        tier=tier,
        auth=auth,
        input_fields=input_fields,
        output_fields=output_fields,
        annotations=ToolHints(
            readOnlyHint=read_only,
            destructiveHint=False,
            openWorldHint=False,
            idempotentHint=True,
        ),
    ))


def freemium_offer_contract_build(
    surface: Surface,
    product_name: ProductName,
    product_slug: ProductSlug,
    selected_niche_id: NicheId,
    persona: Annotated[str, Field(min_length=8, max_length=500)],
    free_deliverables: Annotated[list[BoundedText], Field(min_length=1, max_length=12)],
    paid_executions: Annotated[list[BoundedText], Field(min_length=1, max_length=12)],
    paywall_trigger: BoundedText,
) -> OfferContractResult:
    """Use this when a selected niche needs one honest free-value contract and one server-enforced paid-execution boundary."""
    protected_auth: ToolAuth = "private-gateway" if surface == "docker-mcp-agent" else "oauth2"
    tools = [
        _planned_tool(
            "analyze_free",
            "Use this when the user needs a bounded free preview or evidence-gap analysis.",
            "free",
            "none",
            ["profile"],
            ["status", "preview", "evidenceGaps", "nextActions"],
            read_only=True,
        ),
        _planned_tool(
            "create_checkout",
            "Use this when the user explicitly chooses a priced plan and needs an external merchant checkout URL.",
            "conversion",
            protected_auth,
            ["plan", "idempotencyKey"],
            ["status", "checkoutUrl", "checkoutSessionId"],
            read_only=False,
        ),
        _planned_tool(
            "read_entitlement",
            "Use this when current server-side access must be read for the authenticated principal.",
            "conversion",
            protected_auth,
            [],
            ["status", "plan", "scopes", "expiresAt"],
            read_only=True,
        ),
        _planned_tool(
            "execute_paid",
            "Use this when an authenticated principal with a current entitlement requests bounded paid execution.",
            "paid",
            protected_auth,
            ["executionSpec", "idempotencyKey"],
            ["status", "runId"],
            read_only=False,
        ),
        _planned_tool(
            "get_run_status",
            "Use this when the authenticated owner needs current persisted state for a previously accepted paid run.",
            "paid",
            protected_auth,
            ["runId"],
            ["status", "runId", "failure", "nextAction"],
            read_only=True,
        ),
        _planned_tool(
            "get_artifact_manifest",
            "Use this when a successful paid run needs its authorized artifact metadata and integrity digests.",
            "paid",
            protected_auth,
            ["runId"],
            ["status", "artifacts"],
            read_only=True,
        ),
    ]
    endpoint_roles = sorted(_REQUIRED_ENDPOINT_ROLES)
    if surface == "chatgpt-mcp-app":
        endpoint_roles.extend(sorted(_MCP_OAUTH_ENDPOINT_ROLES))
    return OfferContractResult(
        schemaVersion="sovereign.freemium-offer-contract.v1",
        ok=True,
        status="OFFER_CONTRACT_PLANNED_NOT_IMPLEMENTED",
        product={
            "name": product_name,
            "slug": product_slug,
            "selectedNicheId": selected_niche_id,
            "persona": persona,
            "surface": surface,
        },
        offer={
            "freeDeliverables": list(free_deliverables),
            "paidExecutions": list(paid_executions),
            "paywallTrigger": paywall_trigger,
        },
        tools=tools,
        endpointRoles=endpoint_roles,
        authBoundary={
            "principalSource": "verified-request-context",
            "serverSideEntitlementRequired": True,
            "tokenAsToolArgument": False,
            "rawCardDataAccepted": False,
            "customGptAndMcpCombinedInOneConfiguration": False,
        },
        mutationPerformed=False,
        runtimeVerified=False,
        paymentVerified=False,
        secretValuesReturned=False,
        truthNotice="This output is a planned offer and contract. No tool, checkout, entitlement, executor, artifact, or deployment was created.",
    )


def freemium_product_contract_validate(
    surface: Surface,
    tools: Annotated[list[ProductToolContract], Field(min_length=2, max_length=40)],
    endpoints: Annotated[list[EndpointContract], Field(min_length=7, max_length=40)],
    auth: AuthContract,
    payment: PaymentContract,
) -> ContractValidationResult:
    """Use this when a freemium product contract must fail closed on tool, endpoint, OAuth, entitlement, or payment-boundary defects."""
    errors: list[str] = []
    warnings: list[str] = []
    names: set[str] = set()
    tiers: set[str] = set()
    for tool in tools:
        tiers.add(tool.tier)
        if tool.name in names:
            errors.append(f"DUPLICATE_TOOL:{tool.name}")
        names.add(tool.name)
        if not _TOOL_NAME_RE.fullmatch(tool.name):
            errors.append(f"INVALID_TOOL_NAME:{tool.name}")
        if not tool.description.startswith("Use this when"):
            errors.append(f"TOOL_DESCRIPTION_TRIGGER_MISSING:{tool.name}")
        if tool.tier == "paid" and tool.auth == "none":
            errors.append(f"PAID_TOOL_UNAUTHENTICATED:{tool.name}")
        for field in tool.input_fields:
            if _SECRET_INPUT_RE.search(field):
                errors.append(f"MODEL_VISIBLE_SECRET_INPUT:{tool.name}:{field}")
        mutating_name = any(token in tool.name for token in ("create", "execute", "start", "submit", "push", "export"))
        if mutating_name and tool.annotations.readOnlyHint:
            errors.append(f"MUTATING_TOOL_MARKED_READ_ONLY:{tool.name}")
        if tool.annotations.readOnlyHint and tool.annotations.destructiveHint:
            errors.append(f"READ_ONLY_TOOL_MARKED_DESTRUCTIVE:{tool.name}")
    if "free" not in tiers or "paid" not in tiers:
        errors.append("FREE_AND_PAID_TOOL_TIERS_REQUIRED")

    endpoint_roles = {endpoint.role for endpoint in endpoints}
    role_counts: dict[str, int] = {}
    expected_protected_auth: EndpointAuth = "private-gateway" if surface == "docker-mcp-agent" else "oauth2"
    for endpoint in endpoints:
        role_counts[endpoint.role] = role_counts.get(endpoint.role, 0) + 1
        expected_behavior = _ENDPOINT_BEHAVIOR.get(endpoint.role)
        if expected_behavior is not None:
            expected_method, expected_mutates = expected_behavior
            if endpoint.method != expected_method:
                errors.append(f"ENDPOINT_METHOD_INVALID:{endpoint.role}:{endpoint.method}")
            if endpoint.mutates is not expected_mutates:
                errors.append(f"ENDPOINT_MUTATION_INVALID:{endpoint.role}")
        if endpoint.role == "free-analysis" and endpoint.auth != "none":
            errors.append("FREE_ANALYSIS_MUST_NOT_REQUIRE_AUTH")
        if endpoint.role in _PROTECTED_ENDPOINT_ROLES and endpoint.auth != expected_protected_auth:
            errors.append(f"PROTECTED_ENDPOINT_AUTH_INVALID:{endpoint.role}:{endpoint.auth}")
        if endpoint.role == "payment-webhook" and endpoint.auth != "webhook-signature":
            errors.append("PAYMENT_WEBHOOK_SIGNATURE_AUTH_REQUIRED")
        if endpoint.role in _MCP_OAUTH_ENDPOINT_ROLES and endpoint.auth != "none":
            errors.append(f"OAUTH_METADATA_ENDPOINT_AUTH_INVALID:{endpoint.role}")
    for role, count in sorted(role_counts.items()):
        if count > 1:
            errors.append(f"DUPLICATE_ENDPOINT_ROLE:{role}")
    for role in sorted(_REQUIRED_ENDPOINT_ROLES - endpoint_roles):
        errors.append(f"ENDPOINT_ROLE_MISSING:{role}")
    if surface == "chatgpt-mcp-app":
        for role in sorted(_MCP_OAUTH_ENDPOINT_ROLES - endpoint_roles):
            errors.append(f"MCP_OAUTH_ENDPOINT_ROLE_MISSING:{role}")
        if auth.mode != "oauth2.1-pkce":
            errors.append("MCP_AUTH_MODE_MUST_BE_OAUTH2_1_PKCE")
        if not auth.pkce_s256:
            errors.append("MCP_PKCE_S256_REQUIRED")
        if not auth.resource_audience_bound:
            errors.append("MCP_RESOURCE_AUDIENCE_BINDING_REQUIRED")
    if surface == "custom-gpt-action" and auth.mode != "custom-gpt-oauth":
        errors.append("CUSTOM_GPT_ACTION_AUTH_MODE_MUST_BE_CUSTOM_GPT_OAUTH")
    if surface == "docker-mcp-agent" and auth.mode != "private-gateway":
        errors.append("DOCKER_MCP_AUTH_MODE_MUST_BE_PRIVATE_GATEWAY")

    contract = {
        "surface": surface,
        "tools": [_model_dict(tool) for tool in tools],
        "endpoints": [_model_dict(endpoint) for endpoint in endpoints],
        "auth": _model_dict(auth),
        "payment": _model_dict(payment),
    }
    return ContractValidationResult(
        schemaVersion="sovereign.freemium-contract-validation.v1",
        ok=not errors,
        status="STATIC_CONTRACT_VALIDATED" if not errors else "CONTRACT_BLOCKED",
        contractSha256=_sha256(contract),
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        requiredEndpointRoles=sorted(_REQUIRED_ENDPOINT_ROLES | (_MCP_OAUTH_ENDPOINT_ROLES if surface == "chatgpt-mcp-app" else frozenset())),
        mutationPerformed=False,
        runtimeVerified=False,
        paymentVerified=False,
        secretValuesReturned=False,
    )


def freemium_product_bundle_manifest(
    surface: Surface,
    product_slug: ProductSlug,
    public_base_url: HttpsUrl,
    oauth_issuer: HttpsUrl,
) -> BundleManifestResult:
    """Use this when a validated product needs an exact surface-specific file and environment manifest before any archive is written."""
    if not _valid_https_url(public_base_url) or not _valid_https_url(oauth_issuer):
        raise ValueError("public_base_url and oauth_issuer must be HTTPS URLs")
    common_files = [
        "blueprint.json",
        "validation.json",
        "evidence-ledger.json",
        "instructions.md",
        "openapi.json",
        "mcp-tool-schema.json",
        ".env.example",
        "docker-compose.yml",
        "MANIFEST.json",
    ]
    surface_files = {
        "custom-gpt-action": ["custom-gpt/action-openapi.json", "custom-gpt/editor-auth-contract.json"],
        "chatgpt-mcp-app": ["mcp/server.py", "mcp/oauth-protected-resource.json", "mcp/authorization-server-metadata.json"],
        "docker-mcp-agent": ["mcp/server.py", "mcp/private-gateway-contract.json", "Dockerfile.mcp"],
    }[surface]
    paths = sorted(common_files + surface_files)
    files = [{"path": path, "status": "REQUIRED_NOT_WRITTEN"} for path in paths]
    environment = [
        "ENTITLEMENT_DATABASE_URL",
        "MCP_RESOURCE_URL",
        "OAUTH_ISSUER",
        "PAID_EXECUTOR_URL",
        "PAYMENT_PROVIDER_SECRET",
        "PAYMENT_WEBHOOK_SECRET",
        "PUBLIC_BASE_URL",
    ]
    manifest_payload = {
        "surface": surface,
        "productSlug": product_slug,
        "publicBaseUrl": public_base_url,
        "oauthIssuer": oauth_issuer,
        "files": paths,
        "environment": environment,
    }
    return BundleManifestResult(
        schemaVersion="sovereign.freemium-product-bundle-manifest.v1",
        ok=True,
        status="PRODUCT_KIT_MANIFEST_READY_NOT_WRITTEN",
        surface=surface,
        productSlug=product_slug,
        files=files,
        requiredEnvironmentVariables=environment,
        validationGates=[
            "market evidence independently reviewed",
            "tool input/output schemas and annotations inspected",
            "OAuth discovery, PKCE, audience and scope tests",
            "signed webhook and replay tests",
            "sandbox checkout-to-entitlement-to-execution canary",
            "archive SHA-256 manifest verification",
            "immutable image revision/digest and MCP protocol readback",
        ],
        manifestSha256=_sha256(manifest_payload),
        archiveWritten=False,
        mutationPerformed=False,
        runtimeVerified=False,
        deploymentVerified=False,
        secretValuesReturned=False,
    )


def register(mcp: Any) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    for tool in (
        freemium_product_tool_inventory,
        freemium_market_opportunity_score,
        freemium_offer_contract_build,
        freemium_product_contract_validate,
        freemium_product_bundle_manifest,
    ):
        mcp.tool(annotations=LOCAL_READ_ONLY)(tool)
    _REGISTERED = True
