"""Bounded routing of agent / ToolChain / teaching intent onto Wolfram CAG.

Issue #1461 (parent epic #1457): bind the existing Wolfram CAG transport,
evidence and health lanes into the Sovereign agent / ToolChain / teaching
surfaces so that a model can *request* a compute / knowledge step without
escalating to secrets, repository, runtime, deployment or database mutation.

What this module is
-------------------

A **read-only, pure-stdlib routing layer** that sits between an incoming
mission/claim and the existing CAG adapter lane
(:mod:`adapters.wolfram_agenttools`). It owns no second registry, no truth
authority and no execution path. Every routing verdict is a *projection*
derived from machine-checkable evidence:

- the CAG component contract map (what is even a CAG capability),
- provisioning state (``AVAILABLE`` only when a real entitled credential is
  present),
- the skill ``EffectClass`` (CAG is always ``read_only``), and
- an intent classifier with explicit triggers and anti-triggers.

What this module is *not*
-------------------------

- It does **not** execute a CAG request. Execution remains the adapter's job
  and still produces its own honest receipt (#1459 / #1460).
- It does **not** authorize a mutation. CAG components are read-only by
  design (``WolframCagComponent.__post_init__`` enforces this). A routing
  ``SELECT`` never releases a workspace/external write.
- It does **not** route repository, runtime, deployment, database, container
  or secret-shaped intent to CAG. Those intents are classified as
  ``NOT_CAG`` with an explicit escape-hatch route family so the caller can
  hand them to the authoritative readback lane instead.
- It does **not** fabricate provider receipts. The teaching helpers can only
  *assess* and *simulate* against real CAG contracts; without real
  provisioning they honestly report ``NOT_ENTITLED`` / ``UNAVAILABLE``.

Truth class
-----------

``IMPLEMENTED_IN_REPOSITORY``. A route verdict becomes
``RUNTIME_VERIFIED`` only after real provider + readback, which is deferred
to #1458 / #1462 runtime work. Until then every CAG capability is honestly
``UNAVAILABLE`` unless an entitled credential is supplied.

Design rule (Prime Directive): the UI / agent may only *request* a CAG step
through this router; the router never invents success, never escalates
effect, and never opens an open-world compute path on ambiguity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

# The adapter lane owns the single CAG contract map, capability identity and
# provisioning helper. We import and reuse it; this module adds no second map.
from .adapters.wolfram_agenttools import (
    WOLFRAM_CAG_COMPONENT_MAP,
    WolframCagComponent,
    WolframCagCredential,
    WolframCagStatus,
    is_wolfram_capability,
    provision_cag_component,
)
from .skills.manifest import EffectClass


# ---------------------------------------------------------------------------
# Capability projection
# ---------------------------------------------------------------------------

#: The single, non-mutating effect CAG capabilities are allowed to expose in
#: the skill-manifest vocabulary. This is a hard constant, not a configurable:
#: a CAG capability can never be staged as a workspace or external mutation.
#: Raising it would silently turn a read-only knowledge step into a write path.
CAG_EFFECT_CLASS = EffectClass.READ_ONLY

#: The effect vocabulary used by the ``mcp_toolchain_*`` IR
#: (``"read"`` / ``"workspace-write"`` / ``"external-write"``). CAG nodes are
#: only ever permitted to declare ``"read"``. This is kept separate from
#: :data:`CAG_EFFECT_CLASS` because the skill-manifest and ToolChain IR use
#: different effect vocabularies; the router translates between them rather
#: than collapsing them.
CAG_TOOLCHAIN_EFFECT = "read"

#: Capabilities that must never be routed to CAG. They belong to the
#: authoritative readback / mutation lanes (GitHub, DB, Docker, secrets,
#: runtime, deployment). Listing them here lets the router classify their
#: intents as ``NOT_CAG`` and return the correct escape route instead of
#: silently swallowing them into a knowledge step.
_NON_CAG_ROUTE_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "github": ("github.", "pull request", "pull-request", "merge", "branch", "commit", "issue", "workflow", "actions"),
    "database": ("database", "sql", "postgres", "migration", "table", "query the db", "db query"),
    "container": ("docker", "container", "podman", "kubernetes", "deploy", "deployment", "registry image", "image digest"),
    "runtime": ("runtime state", "runtime readback", "container readback", "patchmon", "live process", "restart the server"),
    "secrets": ("api key", "api-key", "token", "secret", "password", "credential", "private key", "app id", "appid"),
}


@dataclass(frozen=True, slots=True)
class CagCapabilityProjection:
    """A secret-free, read-only projection of one CAG capability.

    This is the shape the agent / ToolChain registry consumes. It carries no
    credential material, no URLs that could be confused with write targets,
    and a hard ``read_only`` effect.
    """

    capability_id: str
    component: str
    endpoint_id: str
    effect_class: EffectClass
    mutates: bool

    def to_public_dict(self) -> dict[str, str]:
        return {
            "capabilityId": self.capability_id,
            "component": self.component,
            "endpointId": self.endpoint_id,
            "effectClass": self.effect_class.value,
            "mutates": "true" if self.mutates else "false",
        }


def cag_capability_registry() -> tuple[CagCapabilityProjection, ...]:
    """Project the canonical CAG capabilities as read-only registry entries.

    There is exactly one source of truth for CAG capabilities
    (:data:`WOLFRAM_CAG_COMPONENT_MAP`). This function only *projects* it
    into the read-only shape the ToolChain IR consumes; it never edits it.
    """
    projections: list[CagCapabilityProjection] = []
    for capability_id, component in WOLFRAM_CAG_COMPONENT_MAP.items():
        # Defensive: the adapter enforces mutates=False at construction. We
        # re-assert here so a future contract edit can never silently turn a
        # CAG capability into a mutation through the registry projection.
        if component.mutates:
            raise RuntimeError(f"CAG capability {capability_id} declares a mutation; refusing to project")
        projections.append(
            CagCapabilityProjection(
                capability_id=capability_id,
                component=component.component,
                endpoint_id=component.endpoint_id,
                effect_class=CAG_EFFECT_CLASS,
                mutates=False,
            )
        )
    return tuple(projections)


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


class CagRouteVerdict(str, Enum):
    """What the router decided for one mission/claim."""

    #: A CAG capability is the strongest read-only candidate.
    SELECT_CAG = "SELECT_CAG"
    #: The intent is a CAG-shaped knowledge/compute question but no single
    #: capability is a clear winner; the caller must disambiguate. Ambiguity
    #: never auto-releases a compute / open-world path.
    AMBIGUOUS_CAG = "AMBIGUOUS_CAG"
    #: The intent looks like CAG but no entitled credential is provisioned.
    #: This is honest degraded state, never a silent success.
    CAG_NOT_PROVISIONED = "CAG_NOT_PROVISIONED"
    #: The intent belongs to a non-CAG lane (GitHub/DB/Docker/secrets/...).
    NOT_CAG = "NOT_CAG"
    #: The intent is not a CAG question and not a known non-CAG escape route.
    NO_MATCH = "NO_MATCH"


#: Triggers (lowercased substring match) that map an intent to a CAG capability.
#: Order matters only for determinism; each capability is scored independently.
_CAG_TRIGGERS: Mapping[str, tuple[str, ...]] = {
    "wolfram.cag.hints": (
        "wolfram language hint",
        "wl hint",
        "wolfram language function",
        "which wolfram function",
        "symbol suggestion",
        "wolfram syntax",
    ),
    "wolfram.cag.compute": (
        "compute",
        "evaluate",
        "solve equation",
        "solve the equation",
        "exact arithmetic",
        "big integer",
        "symbolic algebra",
        "derivative",
        "integral",
        "simplify expression",
        "factor polynomial",
    ),
    "wolfram.cag.results": (
        "unit conversion",
        "convert unit",
        "wolfram alpha result",
        "facts about",
        "physical constant",
        "wolframalpha",
        "structured fact",
    ),
    "wolfram.cag.context": (
        "contextualize",
        "context window",
        "knowledge context",
        "background knowledge",
        "wolfram alpha context",
        "context for",
    ),
}


@dataclass(frozen=True, slots=True)
class CagIntentClassification:
    """One classified mission/claim."""

    verdict: CagRouteVerdict
    matched_capabilities: tuple[str, ...]
    matched_triggers: tuple[str, ...]
    escape_route_family: str
    reasons: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "matchedCapabilities": list(self.matched_capabilities),
            "matchedTriggers": list(self.matched_triggers),
            "escapeRouteFamily": self.escape_route_family,
            "reasons": list(self.reasons),
        }


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_.:/+-]+", text.casefold()))


def _matched_cag(normalized: str) -> dict[str, list[str]]:
    """Return ``{capability_id: [matched triggers...]}`` for CAG triggers."""
    matched: dict[str, list[str]] = {}
    for capability_id, triggers in _CAG_TRIGGERS.items():
        hits = [trigger for trigger in triggers if trigger in normalized]
        if hits:
            matched[capability_id] = hits
    return matched


def _escape_route_family(normalized: str) -> str:
    """Return the non-CAG lane family whose triggers matched, or ``""``."""
    for family, triggers in _NON_CAG_ROUTE_FAMILIES.items():
        if any(trigger in normalized for trigger in triggers):
            return family
    return ""


def classify_cag_intent(mission: str) -> CagIntentClassification:
    """Classify a mission/claim without authorizing any effect or request.

    The classifier is deterministic and substring-based over normalized text.
    It never calls a model and never reads credentials.

    Precedence (honest, never silent):

    1. ``NOT_CAG`` wins over CAG: if the intent mentions a GitHub / DB /
       Docker / secret / runtime keyword, it is handed to that escape route,
       even if it also contains a CAG-shaped word. This prevents a request
       like "compute the database migration hash" from being routed to CAG.
    2. CAG triggers are then scored. Zero hits -> ``NO_MATCH``.
    3. More than one CAG capability with the *same* top score -> ``AMBIGUOUS_CAG``.
    4. Exactly one winner -> ``SELECT_CAG`` (provisioning is checked later;
       the classifier itself stays read-only and credential-free).
    """
    if not isinstance(mission, str) or not mission.strip():
        return CagIntentClassification(
            CagRouteVerdict.NO_MATCH,
            (),
            (),
            "",
            ("empty mission",),
        )
    normalized = _normalize(mission)

    escape = _escape_route_family(normalized)
    if escape:
        return CagIntentClassification(
            CagRouteVerdict.NOT_CAG,
            (),
            (),
            escape,
            (f"intent matches non-CAG route family: {escape}",),
        )

    matched = _matched_cag(normalized)
    if not matched:
        return CagIntentClassification(
            CagRouteVerdict.NO_MATCH,
            (),
            (),
            "",
            ("no CAG trigger matched and no non-CAG escape route matched",),
        )

    # Score = number of distinct matched triggers per capability.
    scored = sorted(matched.items(), key=lambda item: (-len(item[1]), item[0]))
    top_score = len(scored[0][1])
    winners = [cap for cap, hits in scored if len(hits) == top_score]
    all_triggers = tuple(sorted({trigger for hits in matched.values() for trigger in hits}))

    if len(winners) > 1:
        return CagIntentClassification(
            CagRouteVerdict.AMBIGUOUS_CAG,
            tuple(sorted(winners)),
            all_triggers,
            "",
            ("multiple CAG capabilities tie for the top score; disambiguate before requesting compute",),
        )
    return CagIntentClassification(
        CagRouteVerdict.SELECT_CAG,
        tuple(winners),
        all_triggers,
        "",
        ("single CAG capability is the strongest read-only candidate",),
    )


# ---------------------------------------------------------------------------
# Bounded router
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CagRouteDecision:
    """The router's final, evidence-bound decision for one mission/claim.

    ``selected_capability`` is non-empty only when a single CAG capability is
    the strongest candidate *and* it is provisioned (``AVAILABLE``). In every
    other state it is empty and ``provision_status`` carries the honest reason.
    """

    verdict: CagRouteVerdict
    selected_capability: str
    effect_class: EffectClass
    provision_status: WolframCagStatus
    escape_route_family: str
    reasons: tuple[str, ...]

    @property
    def releases_compute(self) -> bool:
        """True only when a real, entitled CAG step may be requested.

        Ambiguity, missing provisioning and non-CAG intents never release a
        compute / open-world path.
        """
        return (
            self.verdict is CagRouteVerdict.SELECT_CAG
            and bool(self.selected_capability)
            and self.provision_status is WolframCagStatus.AVAILABLE
            and self.effect_class is CAG_EFFECT_CLASS
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "selectedCapability": self.selected_capability,
            "effectClass": self.effect_class.value,
            "provisionStatus": self.provision_status.value,
            "escapeRouteFamily": self.escape_route_family,
            "releasesCompute": self.releases_compute,
            "reasons": list(self.reasons),
        }


def route_cag_intent(
    mission: str,
    *,
    credentials: Mapping[str, WolframCagCredential | None] | None = None,
) -> CagRouteDecision:
    """Route a mission/claim to a bounded CAG decision.

    ``credentials`` maps ``capability_id -> credential`` for the capabilities
    the runtime has actually resolved. It is the caller's job to resolve
    credentials server-side (see :func:`resolve_cag_credentials`); this router
    only consumes the resulting secret-free projections. When a capability has
    no entry (or maps to ``None``) it is honestly ``UNAVAILABLE``.
    """
    classification = classify_cag_intent(mission)

    if classification.verdict is CagRouteVerdict.NOT_CAG:
        return CagRouteDecision(
            classification.verdict,
            "",
            CAG_EFFECT_CLASS,
            WolframCagStatus.BLOCKED,
            classification.escape_route_family,
            classification.reasons,
        )
    if classification.verdict is CagRouteVerdict.NO_MATCH:
        return CagRouteDecision(
            classification.verdict,
            "",
            CAG_EFFECT_CLASS,
            WolframCagStatus.BLOCKED,
            "",
            classification.reasons,
        )
    if classification.verdict is CagRouteVerdict.AMBIGUOUS_CAG:
        return CagRouteDecision(
            classification.verdict,
            "",
            CAG_EFFECT_CLASS,
            WolframCagStatus.BLOCKED,
            "",
            classification.reasons,
        )

    # SELECT_CAG: exactly one candidate. Check provisioning honestly.
    capability_id = classification.matched_capabilities[0]
    credential = (credentials or {}).get(capability_id)
    provision = provision_cag_component(capability_id=capability_id, credential=credential)

    if provision is not WolframCagStatus.AVAILABLE:
        return CagRouteDecision(
            CagRouteVerdict.CAG_NOT_PROVISIONED,
            capability_id,
            CAG_EFFECT_CLASS,
            provision,
            "",
            (
                f"CAG candidate {capability_id} is {provision.value}; "
                "compute is not released without real entitled provisioning",
            ),
        )
    return CagRouteDecision(
        CagRouteVerdict.SELECT_CAG,
        capability_id,
        CAG_EFFECT_CLASS,
        provision,
        "",
        (f"CAG candidate {capability_id} is AVAILABLE; read-only compute may be requested",),
    )


# ---------------------------------------------------------------------------
# ToolChain node validation (mcp_toolchain_* IR companion)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CagToolchainNode:
    """A non-executing ToolChain node that wants to call a CAG capability."""

    node_id: str
    capability_id: str
    effect: str
    contract_sha256: str
    output_schema_present: bool
    dependencies: tuple[str, ...] = ()

    def validate_contract(self) -> WolframCagComponent:
        """Return the bound component or raise if the node is not a CAG node."""
        if self.effect != CAG_TOOLCHAIN_EFFECT:
            raise ValueError(
                f"CAG ToolChain node {self.node_id} declares effect {self.effect!r}; "
                f"only {CAG_TOOLCHAIN_EFFECT!r} is permitted for CAG"
            )
        component = WOLFRAM_CAG_COMPONENT_MAP.get(self.capability_id)
        if component is None:
            raise ValueError(
                f"CAG ToolChain node {self.node_id} references unknown capability {self.capability_id!r}"
            )
        return component


@dataclass(frozen=True, slots=True)
class CagToolchainValidation:
    node_id: str
    ok: bool
    provision_status: WolframCagStatus
    findings: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "nodeId": self.node_id,
            "ok": self.ok,
            "provisionStatus": self.provision_status.value,
            "findings": list(self.findings),
        }


def validate_cag_toolchain_node(
    node: CagToolchainNode,
    *,
    credentials: Mapping[str, WolframCagCredential | None] | None = None,
) -> CagToolchainValidation:
    """Validate a single CAG ToolChain node without executing it.

    Mirrors the ``mcp_toolchain_validate`` contract: a node is acceptable only
    when it (a) references a real CAG contract, (b) declares the read-only
    effect, (c) carries an output schema, and (d) is provisioned. Missing
    provisioning is an honest ``UNAVAILABLE`` finding, never a silent pass.
    """
    findings: list[str] = []

    if node.effect != CAG_TOOLCHAIN_EFFECT:
        findings.append(
            f"effect must be {CAG_TOOLCHAIN_EFFECT!r}; got {node.effect!r}"
        )
    if not node.output_schema_present:
        findings.append("output schema is required for CAG toolchain nodes")
    if not node.contract_sha256 or not _SHA256.fullmatch(node.contract_sha256):
        findings.append("contractSha256 must be a bound sha256 contract hash")

    component = WOLFRAM_CAG_COMPONENT_MAP.get(node.capability_id)
    if component is None:
        findings.append(f"unknown CAG capability {node.capability_id!r}")
        return CagToolchainValidation(node.node_id, False, WolframCagStatus.BLOCKED, tuple(findings))

    # Assert the bound contract hash matches the canonical component contract.
    expected = _component_contract_sha256(component)
    if node.contract_sha256 != expected:
        findings.append(
            f"contractSha256 does not match canonical CAG contract for {node.capability_id!r}"
        )

    credential = (credentials or {}).get(node.capability_id)
    provision = provision_cag_component(capability_id=node.capability_id, credential=credential)
    if provision is not WolframCagStatus.AVAILABLE:
        findings.append(f"capability is {provision.value}; not provisioned for execution")

    return CagToolchainValidation(node.node_id, not findings, provision, tuple(findings))


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _component_contract_sha256(component: WolframCagComponent) -> str:
    """Deterministic contract hash for a CAG component (secret-free)."""
    payload = {
        "capabilityId": component.capability_id,
        "component": component.component,
        "endpointId": component.endpoint_id,
        "method": component.method,
        "expectedContentType": component.expected_content_type,
        "timeoutSeconds": component.timeout_seconds,
        "maxOutputBytes": component.max_output_bytes,
        "maxRequestBytes": component.max_request_bytes,
        "maxRetries": component.max_retries,
        "mutates": component.mutates,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def cag_contract_inventory() -> dict[str, object]:
    """Public, secret-free inventory of CAG contracts for the ToolChain IR.

    Companion to ``mcp_toolchain_contract_inventory``: lets a planner see the
    bounded CAG nodes (capabilities, effects, contract hashes) without any
    credential material and without executing anything.
    """
    nodes = []
    for projection, component in zip(cag_capability_registry(), WOLFRAM_CAG_COMPONENT_MAP.values()):
        nodes.append(
            {
                **projection.to_public_dict(),
                "contractSha256": _component_contract_sha256(component),
                "method": component.method,
                "timeoutSeconds": component.timeout_seconds,
                "maxRetries": component.max_retries,
            }
        )
    return {
        "schemaVersion": "sovereign.wolfram-cag-routing-inventory.v1",
        "ok": True,
        "status": "CAG_ROUTING_INVENTORY_READY",
        "effectClass": CAG_EFFECT_CLASS.value,
        "nodes": nodes,
        "mutationPerformed": False,
        "runtimeVerified": False,
        "secretValuesReturned": False,
        "truthNotice": (
            "Inventory is a read-only projection of bound CAG contracts. "
            "runtimeVerified becomes true only after real provider + readback (#1458/#1462)."
        ),
    }


# ---------------------------------------------------------------------------
# Teaching (assess / simulate) bound to real CAG contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CagTeachingAssessment:
    """Assessment of a teaching package against real CAG contracts.

    Teaching can only describe and verify against the *real* contract map. It
    cannot fake a provider receipt: without provisioning, the assessment is
    honestly ``NOT_ENTITLED`` / ``UNAVAILABLE``.
    """

    package_id: str
    ok: bool
    assessed_capabilities: tuple[str, ...]
    unknown_capabilities: tuple[str, ...]
    provision_status: WolframCagStatus
    findings: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "packageId": self.package_id,
            "ok": self.ok,
            "assessedCapabilities": list(self.assessed_capabilities),
            "unknownCapabilities": list(self.unknown_capabilities),
            "provisionStatus": self.provision_status.value,
            "findings": list(self.findings),
        }


def teaching_package_assess(
    package_id: str,
    declared_capabilities: Sequence[str],
    *,
    credentials: Mapping[str, WolframCagCredential | None] | None = None,
) -> CagTeachingAssessment:
    """Assess a CAG teaching package against the real contract map.

    A capability is "assessed" only when it is a real CAG capability.
    Anything else is reported as unknown. Provisioning is checked per
    capability but never faked: the worst provision status across assessed
    capabilities is surfaced honestly.
    """
    findings: list[str] = []
    assessed: list[str] = []
    unknown: list[str] = []
    statuses: list[WolframCagStatus] = []

    if not isinstance(package_id, str) or not package_id.strip():
        findings.append("packageId is required")
    if not declared_capabilities:
        findings.append("at least one declared capability is required")

    for capability_id in declared_capabilities:
        if not is_wolfram_capability(capability_id) or capability_id not in WOLFRAM_CAG_COMPONENT_MAP:
            unknown.append(capability_id)
            findings.append(f"capability {capability_id!r} is not a known CAG capability")
            continue
        assessed.append(capability_id)
        credential = (credentials or {}).get(capability_id)
        provision = provision_cag_component(capability_id=capability_id, credential=credential)
        statuses.append(provision)
        if provision is not WolframCagStatus.AVAILABLE:
            findings.append(f"capability {capability_id!r} is {provision.value}")

    # Worst-case honest provision status across assessed capabilities.
    if statuses:
        if WolframCagStatus.UNAVAILABLE in statuses:
            worst = WolframCagStatus.UNAVAILABLE
        elif WolframCagStatus.NOT_ENTITLED in statuses:
            worst = WolframCagStatus.NOT_ENTITLED
        elif WolframCagStatus.BLOCKED in statuses:
            worst = WolframCagStatus.BLOCKED
        else:
            worst = WolframCagStatus.AVAILABLE
    else:
        worst = WolframCagStatus.BLOCKED

    ok = bool(assessed) and not unknown and worst is WolframCagStatus.AVAILABLE and not findings
    return CagTeachingAssessment(
        package_id=package_id or "",
        ok=ok,
        assessed_capabilities=tuple(sorted(set(assessed))),
        unknown_capabilities=tuple(sorted(set(unknown))),
        provision_status=worst,
        findings=tuple(findings),
    )


@dataclass(frozen=True, slots=True)
class CagTeachingSimulation:
    """A non-executing lesson simulation against a real CAG contract.

    The simulation never calls the provider. It verifies that the lesson's
    requested capability is a real CAG contract and that, *if* it were
    provisioned, the lesson would request a read-only step. A real provider
    receipt is never fabricated; ``provider_receipt`` stays empty unless the
    caller supplies a real one.
    """

    lesson_id: str
    capability_id: str
    ok: bool
    provision_status: WolframCagStatus
    provider_receipt: str
    findings: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "lessonId": self.lesson_id,
            "capabilityId": self.capability_id,
            "ok": self.ok,
            "provisionStatus": self.provision_status.value,
            "providerReceipt": self.provider_receipt,
            "findings": list(self.findings),
        }


def teaching_lesson_simulate(
    lesson_id: str,
    capability_id: str,
    *,
    credentials: Mapping[str, WolframCagCredential | None] | None = None,
    real_provider_receipt: str | None = None,
) -> CagTeachingSimulation:
    """Simulate a CAG teaching lesson without executing or faking a receipt.

    ``real_provider_receipt`` may be supplied only by an owner-approved
    runtime step that actually obtained a provider receipt. Without it the
    simulation is honest: the lesson is structurally valid against a real
    contract, but ``provider_receipt`` is empty and ``ok`` reflects that no
    real provider evidence exists.
    """
    findings: list[str] = []
    if not isinstance(lesson_id, str) or not lesson_id.strip():
        findings.append("lessonId is required")

    component = WOLFRAM_CAG_COMPONENT_MAP.get(capability_id)
    if component is None:
        findings.append(f"capability {capability_id!r} is not a known CAG capability")
        return CagTeachingSimulation(
            lesson_id=lesson_id or "",
            capability_id=capability_id,
            ok=False,
            provision_status=WolframCagStatus.BLOCKED,
            provider_receipt="",
            findings=tuple(findings),
        )

    credential = (credentials or {}).get(capability_id)
    provision = provision_cag_component(capability_id=capability_id, credential=credential)
    if provision is not WolframCagStatus.AVAILABLE:
        findings.append(f"capability is {provision.value}; no real provider step is possible")

    receipt = ""
    if real_provider_receipt is not None:
        if not isinstance(real_provider_receipt, str) or not real_provider_receipt.strip():
            findings.append("real_provider_receipt must be a non-empty string when supplied")
        else:
            receipt = real_provider_receipt.strip()

    # ok requires a real contract, real provisioning, AND a real provider receipt.
    ok = (
        not findings
        and provision is WolframCagStatus.AVAILABLE
        and bool(receipt)
    )
    if not receipt and not findings:
        findings.append("no real provider receipt supplied; simulation is structural only")
    return CagTeachingSimulation(
        lesson_id=lesson_id or "",
        capability_id=capability_id,
        ok=ok,
        provision_status=provision,
        provider_receipt=receipt,
        findings=tuple(findings),
    )
