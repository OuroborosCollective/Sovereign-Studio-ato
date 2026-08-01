"""Environment-Bound MCP Execution with Credential, Identity and Egress Receipts.

Every MCP, tool, agent, provider, database or deployment call must be bound to
a concrete environment, a server-side-resolved principal, an authorised
credential identity, an egress policy decision and a revision-bound run.

A dev/test/ephemeral run must never reach production credentials or targets
solely because of a URL, tool ID, client header or prompt assertion.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Client-supplied IDs are candidates only — never the proof.
- Secrets, tokens and raw credential material are never stored in receipts.
- The pure layer produces a pre-connection decision receipt; persistence and
  effect ordering must be proven by the caller's storage/readback boundary.
- OBO tokens are validated for scope, audience and owner before use.
- Cross-environment promotion requires explicit approval receipt.
- No Arelorian WASD or N+1 personality integration in this ATO module.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, FrozenSet, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION: Final[str] = "sovereign.environment-mcp-execution.v1"

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
_MAX_SCOPES: Final[int] = 64
_MAX_TOOL_ID_LEN: Final[int] = 256
_MAX_PRINCIPAL_ID_LEN: Final[int] = 256
_MAX_AUDIENCE_LEN: Final[int] = 2048
_MAX_IDENTIFIER_LEN: Final[int] = 256
_MAX_HOST_LEN: Final[int] = 253
_MAX_PROTOCOL_LEN: Final[int] = 24

# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_OWNER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{0,127}$")
_ENVIRONMENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9\-]{0,119}(?:/[a-z][a-z0-9\-]{0,119})?$"
)

# ---------------------------------------------------------------------------
# Blocked network ranges (egress policy)
# ---------------------------------------------------------------------------
_BLOCKED_NETWORKS: Final[Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = (
    ipaddress.ip_network("127.0.0.0/8"),        # loopback
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918 private
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918 private
    ipaddress.ip_network("100.64.0.0/10"),      # shared address space
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
)

# Cloud metadata endpoints explicitly blocked by hostname
_BLOCKED_HOSTNAMES: Final[FrozenSet[str]] = frozenset({
    "169.254.169.254",        # AWS/GCP/Azure IMDS
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",
})


class EnvironmentContractError(ValueError):
    """An input violated an environment execution invariant."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EnvironmentKind(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"
    EPHEMERAL = "ephemeral"


class CredentialMode(str, Enum):
    DIRECT = "direct"              # credential resolved directly for this principal
    ON_BEHALF_OF = "on_behalf_of"  # OBO: acting in name of authenticated user
    SERVICE_ACCOUNT = "service_account"  # shared service account (must be explicit)
    ANONYMOUS = "anonymous"        # no credential; read-only public paths only


class EgressDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


class EgressBlockReason(str, Enum):
    LOOPBACK = "loopback"
    METADATA_IP = "metadata_ip"
    PRIVATE_NETWORK = "private_network"
    BLOCKED_HOSTNAME = "blocked_hostname"
    ENVIRONMENT_POLICY = "environment_policy"
    UNKNOWN_IP_CLASS = "unknown_ip_class"
    PROTOCOL_NOT_ALLOWED = "protocol_not_allowed"
    DNS_EVIDENCE_REQUIRED = "dns_evidence_required"
    PRODUCTION_TARGET_FROM_NONPROD = "production_target_from_nonprod"


class ResolutionMethod(str, Enum):
    SERVER_JWT = "server_jwt"          # server-side JWT validation
    SESSION_COOKIE = "session_cookie"  # server-side session lookup
    API_KEY_HASH = "api_key_hash"      # server-side API key resolution
    SERVICE_ACCOUNT = "service_account"  # pre-configured service account
    ANONYMOUS = "anonymous"            # no auth; read-only scope only


# ---------------------------------------------------------------------------
# Production-targeting environments
# ---------------------------------------------------------------------------
_PRODUCTION_ENVIRONMENTS: Final[FrozenSet[EnvironmentKind]] = frozenset({
    EnvironmentKind.PRODUCTION,
})
_NONPROD_ENVIRONMENTS: Final[FrozenSet[EnvironmentKind]] = frozenset({
    EnvironmentKind.DEVELOPMENT,
    EnvironmentKind.TEST,
    EnvironmentKind.STAGING,
    EnvironmentKind.EPHEMERAL,
})


# ---------------------------------------------------------------------------
# Canonical hash helpers
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    s = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()


def _content_addressed_id(kind: str, payload: object) -> str:
    """Return a deterministic identity for canonical non-secret receipt data."""
    return f"{kind}:{_canonical_sha256(payload)}"


def _validate_bounded_text(
    value: Optional[str],
    *,
    field: str,
    max_length: int = _MAX_IDENTIFIER_LEN,
    required: bool = True,
) -> Optional[str]:
    if value is None:
        if required:
            raise EnvironmentContractError(f"'{field}' must not be empty.")
        return None
    if not isinstance(value, str) or not value.strip():
        raise EnvironmentContractError(f"'{field}' must not be empty.")
    if len(value) > max_length or "\x00" in value:
        raise EnvironmentContractError(f"'{field}' is invalid or exceeds its length limit.")
    return value


def _canonical_protocol(value: str) -> str:
    protocol = str(value).strip().lower()
    if not protocol or len(protocol) > _MAX_PROTOCOL_LEN or not re.fullmatch(r"[a-z][a-z0-9+.-]*", protocol):
        raise EnvironmentContractError("protocol is invalid.")
    return protocol


def _canonical_host(value: str) -> str:
    host = str(value).strip().lower().rstrip(".")
    if not host or len(host) > _MAX_HOST_LEN or any(ch in host for ch in "/\\@?#\x00"):
        raise EnvironmentContractError("target_host is invalid.")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        try:
            host.encode("ascii")
        except UnicodeEncodeError as exc:
            raise EnvironmentContractError("target_host must be canonical ASCII/IDNA form.") from exc
        labels = host.split(".")
        if any(
            not label
            or len(label) > 63
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise EnvironmentContractError("target_host is not a canonical hostname.")
        return host


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_owner(value: str, *, field: str) -> str:
    if not value or not value.strip():
        raise EnvironmentContractError(f"'{field}' must not be empty.")
    if ".." in value or "\x00" in value:
        raise EnvironmentContractError(f"'{field}' contains forbidden sequence.")
    if not _OWNER_PATTERN.fullmatch(value):
        raise EnvironmentContractError(f"'{field}' has invalid characters (got {value!r}).")
    return value


def _validate_revision(value: Optional[str], *, field: str) -> Optional[str]:
    if value is None:
        return None
    if not _SHA40.fullmatch(value):
        raise EnvironmentContractError(f"'{field}' must be 40-char hex SHA.")
    return value


def _validate_environment_id(value: str) -> str:
    if not value or not value.strip():
        raise EnvironmentContractError("environment_id must not be empty.")
    if not _ENVIRONMENT_ID_PATTERN.fullmatch(value):
        raise EnvironmentContractError(
            f"environment_id must match [a-z][a-z0-9-]{{0,119}}[/...] (got {value!r})."
        )
    return value


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnvironmentManifest:
    """Canonical, hash-committed description of an execution environment.

    Contains no credentials or secrets. Binds all policy, network and
    identity contracts for a single execution scope.
    """
    environment_id: str          # e.g. "production", "development", "ephemeral/run-123"
    kind: EnvironmentKind
    schema_version: str
    repo_owner: str
    repo_name: str
    revision: str                # mandatory 40-char hex SHA
    network_policy_hash: str     # SHA-256 of the network policy (computed externally)
    credential_scope_hash: str   # SHA-256 of the allowed credential scope set
    allowed_protocols: Tuple[str, ...]   # e.g. ("https",)
    allowed_egress_hosts: Tuple[str, ...]  # allowlist of external hosts (not IPs)
    is_production: bool
    manifest_hash: str           # SHA-256 of all above fields


@dataclass(frozen=True)
class PrincipalResolutionReceipt:
    """Server-side principal resolution result.

    Client-supplied IDs are candidates; this receipt commits to the
    server-resolved identity after authentication.
    """
    receipt_id: str              # deterministic content-addressed identity
    schema_version: str
    environment_id: str
    principal_id: str            # server-resolved; NOT client-supplied raw value
    owner_id: str
    resolution_method: ResolutionMethod
    is_server_resolved: bool     # always True in production; False only in test stubs
    run_id: Optional[str]
    revision: Optional[str]
    client_supplied_candidate: Optional[str]  # stored for audit; never used as proof
    receipt_hash: str


@dataclass(frozen=True)
class CredentialResolutionReceipt:
    """Resolution receipt for a credential identity.

    No secret material is ever stored. The receipt commits to the
    credential's identity (ID, owner, scope fingerprint, mode) but
    not to the actual key, token or password.
    """
    receipt_id: str              # deterministic content-addressed identity
    schema_version: str
    environment_id: str
    credential_id: str           # stable, non-secret credential identifier
    owner_id: str
    mode: CredentialMode
    provider: str                # e.g. "openrouter", "github", "postgres"
    scope_hash: str              # SHA-256 of sorted scope set; no raw scopes stored
    audience: Optional[str]      # OBO / OIDC audience
    executed_as_principal_id: str  # server-resolved principal
    refresh_version: int         # monotonic; rotation invalidates previous sessions
    is_expired: bool
    receipt_hash: str


@dataclass(frozen=True)
class EgressDecisionReceipt:
    """Pure pre-connection policy decision.

    The caller must persist and read back this receipt before opening the
    target connection; this pure module does not claim that side effect.
    """
    receipt_id: str              # deterministic content-addressed identity
    schema_version: str
    environment_id: str
    environment_kind: EnvironmentKind
    target_host: str             # canonicalised hostname or IP string
    resolved_ip: Optional[str]    # canonical DNS/IP evidence committed to decision
    target_port: Optional[int]
    protocol: str                # "https", "http", "tcp", etc.
    decision: EgressDecision
    block_reason: Optional[EgressBlockReason]
    receipt_hash: str


@dataclass(frozen=True)
class McpInstallationBinding:
    """Exact, registry-revision-bound MCP tool/server/installation reference.

    Prevents tool confusion attacks where a different installation with the
    same tool name is silently substituted.
    """
    binding_id: str              # deterministic content-addressed identity
    tool_id: str                 # canonical tool identifier
    server_id: str               # canonical server identifier
    installation_id: str         # exact installation on this host
    registry_revision: str       # 40-char hex SHA of tool registry at bind time
    verified_at_revision: Optional[str]  # repo revision at bind time
    binding_hash: str


@dataclass(frozen=True)
class ExecutionIdentityReceipt:
    """Composite receipt binding all execution identity facts for one run.

    This is the canonical audit record proving who ran what, where, under
    which credential and subject to which egress decision.
    """
    receipt_id: str              # deterministic content-addressed identity
    schema_version: str
    run_id: str
    revision: str
    environment_manifest_hash: str
    principal_receipt_id: str
    credential_receipt_id: str
    egress_receipt_id: str
    installation_binding_id: str
    tool_id: str
    environment_kind: EnvironmentKind
    is_mutation: bool
    receipt_hash: str


# ---------------------------------------------------------------------------
# EnvironmentManifestCompiler (pure)
# ---------------------------------------------------------------------------

class EnvironmentManifestCompiler:
    """Compile and validate EnvironmentManifest instances."""

    @classmethod
    def compile(
        cls,
        *,
        environment_id: str,
        kind: EnvironmentKind,
        repo_owner: str,
        repo_name: str,
        revision: Optional[str] = None,
        network_policy_descriptor: object,    # arbitrary JSON-serialisable
        credential_scope_descriptor: object,  # arbitrary JSON-serialisable
        allowed_protocols: Sequence[str] = ("https",),
        allowed_egress_hosts: Sequence[str] = (),
    ) -> EnvironmentManifest:
        environment_id = _validate_environment_id(environment_id)
        repo_owner = _validate_owner(repo_owner, field="repo_owner")
        repo_name = _validate_owner(repo_name, field="repo_name")
        revision = _validate_revision(revision, field="revision")
        if revision is None:
            raise EnvironmentContractError("revision is required for an execution environment.")

        if not allowed_protocols:
            raise EnvironmentContractError("allowed_protocols must not be empty.")

        protocols = tuple(sorted({_canonical_protocol(value) for value in allowed_protocols}))
        hosts = tuple(sorted({_canonical_host(value) for value in allowed_egress_hosts}))
        network_policy_hash = _canonical_sha256(network_policy_descriptor)
        credential_scope_hash = _canonical_sha256(credential_scope_descriptor)
        is_production = kind == EnvironmentKind.PRODUCTION

        manifest_hash = _canonical_sha256({
            "environment_id": environment_id,
            "kind": kind.value,
            "schema_version": SCHEMA_VERSION,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "revision": revision,
            "network_policy_hash": network_policy_hash,
            "credential_scope_hash": credential_scope_hash,
            "allowed_protocols": list(protocols),
            "allowed_egress_hosts": list(hosts),
            "is_production": is_production,
        })

        return EnvironmentManifest(
            environment_id=environment_id,
            kind=kind,
            schema_version=SCHEMA_VERSION,
            repo_owner=repo_owner,
            repo_name=repo_name,
            revision=revision,
            network_policy_hash=network_policy_hash,
            credential_scope_hash=credential_scope_hash,
            allowed_protocols=protocols,
            allowed_egress_hosts=hosts,
            is_production=is_production,
            manifest_hash=manifest_hash,
        )

    @staticmethod
    def verify(manifest: EnvironmentManifest) -> bool:
        if manifest.schema_version != SCHEMA_VERSION:
            return False
        if not _SHA40.fullmatch(manifest.revision):
            return False
        if manifest.is_production != (manifest.kind == EnvironmentKind.PRODUCTION):
            return False
        try:
            protocols = tuple(sorted({_canonical_protocol(value) for value in manifest.allowed_protocols}))
            hosts = tuple(sorted({_canonical_host(value) for value in manifest.allowed_egress_hosts}))
        except EnvironmentContractError:
            return False
        if protocols != manifest.allowed_protocols or hosts != manifest.allowed_egress_hosts:
            return False
        expected = _canonical_sha256({
            "environment_id": manifest.environment_id,
            "kind": manifest.kind.value,
            "schema_version": manifest.schema_version,
            "repo_owner": manifest.repo_owner,
            "repo_name": manifest.repo_name,
            "revision": manifest.revision,
            "network_policy_hash": manifest.network_policy_hash,
            "credential_scope_hash": manifest.credential_scope_hash,
            "allowed_protocols": list(protocols),
            "allowed_egress_hosts": list(hosts),
            "is_production": manifest.is_production,
        })
        return manifest.manifest_hash == expected


# ---------------------------------------------------------------------------
# PrincipalResolver (pure)
# ---------------------------------------------------------------------------

class PrincipalResolver:
    """Produce PrincipalResolutionReceipt from server-verified identity data."""

    @classmethod
    def resolve(
        cls,
        *,
        environment_id: str,
        server_resolved_principal_id: str,
        owner_id: str,
        resolution_method: ResolutionMethod,
        run_id: Optional[str] = None,
        revision: Optional[str] = None,
        client_supplied_candidate: Optional[str] = None,
    ) -> PrincipalResolutionReceipt:
        """Create a server-side principal receipt.

        server_resolved_principal_id must be determined server-side.
        client_supplied_candidate (if any) is stored for audit only.
        """
        environment_id = _validate_environment_id(environment_id)
        principal_id = _validate_bounded_text(
            server_resolved_principal_id,
            field="server_resolved_principal_id",
            max_length=_MAX_PRINCIPAL_ID_LEN,
        )
        owner_id = _validate_owner(owner_id, field="owner_id")
        run_id = _validate_bounded_text(run_id, field="run_id")
        revision = _validate_revision(revision, field="revision")
        if revision is None:
            raise EnvironmentContractError("revision is required for principal resolution.")
        client_supplied_candidate = _validate_bounded_text(
            client_supplied_candidate,
            field="client_supplied_candidate",
            required=False,
        )
        assert principal_id is not None and run_id is not None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "environment_id": environment_id,
            "principal_id": principal_id,
            "owner_id": owner_id,
            "resolution_method": resolution_method.value,
            "is_server_resolved": True,
            "run_id": run_id,
            "revision": revision,
            "client_supplied_candidate": client_supplied_candidate,
        }
        receipt_id = _content_addressed_id("principal", payload)
        receipt_hash = _canonical_sha256({"receipt_id": receipt_id, **payload})
        return PrincipalResolutionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=environment_id,
            principal_id=principal_id,
            owner_id=owner_id,
            resolution_method=resolution_method,
            is_server_resolved=True,
            run_id=run_id,
            revision=revision,
            client_supplied_candidate=client_supplied_candidate,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def verify(receipt: PrincipalResolutionReceipt) -> bool:
        if receipt.schema_version != SCHEMA_VERSION or not receipt.is_server_resolved:
            return False
        try:
            _validate_environment_id(receipt.environment_id)
            _validate_owner(receipt.owner_id, field="owner_id")
            _validate_bounded_text(receipt.principal_id, field="principal_id")
            _validate_bounded_text(receipt.run_id, field="run_id")
            if _validate_revision(receipt.revision, field="revision") is None:
                return False
            _validate_bounded_text(
                receipt.client_supplied_candidate,
                field="client_supplied_candidate",
                required=False,
            )
        except EnvironmentContractError:
            return False
        payload = {
            "schema_version": receipt.schema_version,
            "environment_id": receipt.environment_id,
            "principal_id": receipt.principal_id,
            "owner_id": receipt.owner_id,
            "resolution_method": receipt.resolution_method.value,
            "is_server_resolved": receipt.is_server_resolved,
            "run_id": receipt.run_id,
            "revision": receipt.revision,
            "client_supplied_candidate": receipt.client_supplied_candidate,
        }
        expected_id = _content_addressed_id("principal", payload)
        return (
            receipt.receipt_id == expected_id
            and receipt.receipt_hash == _canonical_sha256({"receipt_id": expected_id, **payload})
        )


# ---------------------------------------------------------------------------
# CredentialResolver (pure)
# ---------------------------------------------------------------------------

class CredentialResolver:
    """Produce CredentialResolutionReceipt. No secret material stored."""

    @classmethod
    def resolve(
        cls,
        *,
        environment_id: str,
        credential_id: str,         # stable non-secret ID, e.g. "openrouter-prod-key-v3"
        owner_id: str,
        mode: CredentialMode,
        provider: str,
        scopes: Sequence[str],      # sorted and hashed; not stored raw
        audience: Optional[str] = None,
        executed_as_principal_id: str,
        refresh_version: int = 1,
        is_expired: bool = False,
        obo_required_scopes: Optional[Sequence[str]] = None,
    ) -> CredentialResolutionReceipt:
        environment_id = _validate_environment_id(environment_id)
        credential_id = _validate_bounded_text(credential_id, field="credential_id")
        owner_id = _validate_owner(owner_id, field="owner_id")
        provider = _validate_bounded_text(provider, field="provider")
        executed_as_principal_id = _validate_bounded_text(
            executed_as_principal_id,
            field="executed_as_principal_id",
            max_length=_MAX_PRINCIPAL_ID_LEN,
        )
        audience = _validate_bounded_text(
            audience,
            field="audience",
            max_length=_MAX_AUDIENCE_LEN,
            required=False,
        )
        if isinstance(scopes, (str, bytes)) or len(scopes) > _MAX_SCOPES:
            raise EnvironmentContractError(f"scopes must be a sequence of at most {_MAX_SCOPES} items.")
        normalized_scopes = tuple(sorted({
            str(scope).strip() for scope in scopes
            if isinstance(scope, str) and scope.strip()
        }))
        if len(normalized_scopes) != len(scopes):
            raise EnvironmentContractError("scopes must be unique non-empty strings.")
        if isinstance(refresh_version, bool) or refresh_version < 1:
            raise EnvironmentContractError("refresh_version must be a positive integer.")

        if mode == CredentialMode.ON_BEHALF_OF:
            cls._validate_obo(
                scopes=normalized_scopes,
                audience=audience,
                required_scopes=list(obo_required_scopes) if obo_required_scopes else [],
            )

        scope_hash = _canonical_sha256(list(normalized_scopes))
        if is_expired:
            raise EnvironmentContractError(
                "Credential is expired. Rotation required before execution."
            )
        assert credential_id is not None and provider is not None and executed_as_principal_id is not None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "environment_id": environment_id,
            "credential_id": credential_id,
            "owner_id": owner_id,
            "mode": mode.value,
            "provider": provider,
            "scope_hash": scope_hash,
            "audience": audience,
            "executed_as_principal_id": executed_as_principal_id,
            "refresh_version": refresh_version,
            "is_expired": False,
        }
        receipt_id = _content_addressed_id("credential", payload)
        receipt_hash = _canonical_sha256({"receipt_id": receipt_id, **payload})
        return CredentialResolutionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=environment_id,
            credential_id=credential_id,
            owner_id=owner_id,
            mode=mode,
            provider=provider,
            scope_hash=scope_hash,
            audience=audience,
            executed_as_principal_id=executed_as_principal_id,
            refresh_version=refresh_version,
            is_expired=False,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def verify(receipt: CredentialResolutionReceipt) -> bool:
        if receipt.schema_version != SCHEMA_VERSION or receipt.is_expired:
            return False
        if not _SHA64.fullmatch(receipt.scope_hash):
            return False
        try:
            _validate_environment_id(receipt.environment_id)
            _validate_owner(receipt.owner_id, field="owner_id")
            _validate_bounded_text(receipt.credential_id, field="credential_id")
            _validate_bounded_text(receipt.provider, field="provider")
            _validate_bounded_text(receipt.executed_as_principal_id, field="executed_as_principal_id")
            _validate_bounded_text(
                receipt.audience,
                field="audience",
                max_length=_MAX_AUDIENCE_LEN,
                required=False,
            )
            if isinstance(receipt.refresh_version, bool) or receipt.refresh_version < 1:
                return False
        except EnvironmentContractError:
            return False
        payload = {
            "schema_version": receipt.schema_version,
            "environment_id": receipt.environment_id,
            "credential_id": receipt.credential_id,
            "owner_id": receipt.owner_id,
            "mode": receipt.mode.value,
            "provider": receipt.provider,
            "scope_hash": receipt.scope_hash,
            "audience": receipt.audience,
            "executed_as_principal_id": receipt.executed_as_principal_id,
            "refresh_version": receipt.refresh_version,
            "is_expired": receipt.is_expired,
        }
        expected_id = _content_addressed_id("credential", payload)
        return (
            receipt.receipt_id == expected_id
            and receipt.receipt_hash == _canonical_sha256({"receipt_id": expected_id, **payload})
        )

    @staticmethod
    def _validate_obo(
        *,
        scopes: Sequence[str],
        audience: Optional[str],
        required_scopes: Sequence[str],
    ) -> None:
        if not audience:
            raise EnvironmentContractError(
                "OBO credential requires a non-empty audience."
            )
        if len(audience) > _MAX_AUDIENCE_LEN:
            raise EnvironmentContractError("OBO audience exceeds length limit.")
        if required_scopes:
            missing = set(required_scopes) - set(scopes)
            if missing:
                raise EnvironmentContractError(
                    f"OBO_SCOPE_INSUFFICIENT: missing scopes {sorted(missing)}."
                )


# ---------------------------------------------------------------------------
# EgressPolicyEngine (pure)
# ---------------------------------------------------------------------------

class EgressPolicyEngine:
    """Deterministic egress policy decisions made BEFORE network connections.

    Evaluates target_host against blocked networks, metadata endpoints,
    environment-level allowlists, and cross-environment production targeting.
    """

    @classmethod
    def decide(
        cls,
        *,
        environment_manifest: EnvironmentManifest,
        target_host: str,
        target_port: Optional[int] = None,
        protocol: str = "https",
        resolved_ip: Optional[str] = None,  # caller provides after DNS resolution
    ) -> EgressDecisionReceipt:
        """Produce an egress decision receipt.

        The decision is committed to a receipt BEFORE any connection attempt.
        If resolved_ip is provided, it is checked against blocked networks
        (DNS-rebinding / SSRF protection).
        """
        if not EnvironmentManifestCompiler.verify(environment_manifest):
            raise EnvironmentContractError("environment_manifest failed canonical verification.")
        target_host = _canonical_host(target_host)
        protocol = _canonical_protocol(protocol)
        if target_port is not None and (
            isinstance(target_port, bool) or not 1 <= target_port <= 65535
        ):
            raise EnvironmentContractError("target_port must be between 1 and 65535.")
        if target_host in _BLOCKED_HOSTNAMES:
            return cls._blocked(
                environment_manifest,
                target_host,
                target_port,
                protocol,
                EgressBlockReason.BLOCKED_HOSTNAME,
            )
        if protocol not in environment_manifest.allowed_protocols:
            return cls._blocked(
                environment_manifest,
                target_host,
                target_port,
                protocol,
                EgressBlockReason.PROTOCOL_NOT_ALLOWED,
            )
        if (
            environment_manifest.kind in _NONPROD_ENVIRONMENTS
            and cls._looks_like_production_host(target_host)
        ):
            return cls._blocked(
                environment_manifest,
                target_host,
                target_port,
                protocol,
                EgressBlockReason.PRODUCTION_TARGET_FROM_NONPROD,
            )
        if environment_manifest.allowed_egress_hosts and not any(
            target_host == host or target_host.endswith(f".{host}")
            for host in environment_manifest.allowed_egress_hosts
        ):
            return cls._blocked(
                environment_manifest,
                target_host,
                target_port,
                protocol,
                EgressBlockReason.ENVIRONMENT_POLICY,
            )

        host_is_ip = True
        try:
            ipaddress.ip_address(target_host)
        except ValueError:
            host_is_ip = False

        canonical_resolved_ip: Optional[str] = None
        if resolved_ip is not None:
            try:
                canonical_resolved_ip = str(ipaddress.ip_address(resolved_ip.strip()))
            except (ValueError, AttributeError):
                return cls._blocked(
                    environment_manifest,
                    target_host,
                    target_port,
                    protocol,
                    EgressBlockReason.UNKNOWN_IP_CLASS,
                    resolved_ip=None,
                )
        elif not host_is_ip:
            return cls._blocked(
                environment_manifest,
                target_host,
                target_port,
                protocol,
                EgressBlockReason.DNS_EVIDENCE_REQUIRED,
                resolved_ip=None,
            )
        else:
            canonical_resolved_ip = target_host

        # 1a. If target_host itself is an IP, check it immediately.
        if host_is_ip:
            _ip_block = cls._check_ip(target_host)
            if _ip_block is not None:
                return cls._blocked(
                    environment_manifest,
                    target_host,
                    target_port,
                    protocol,
                    _ip_block,
                    resolved_ip=canonical_resolved_ip,
                )

        # 1b. Blocked hostname check
        if target_host in _BLOCKED_HOSTNAMES:
            return cls._blocked(
                environment_manifest, target_host, target_port, protocol,
                EgressBlockReason.BLOCKED_HOSTNAME,
            )

        # 2. Resolved IP check (DNS rebinding / SSRF)
        if canonical_resolved_ip is not None:
            block = cls._check_ip(canonical_resolved_ip)
            if block is not None:
                return cls._blocked(
                    environment_manifest,
                    target_host,
                    target_port,
                    protocol,
                    block,
                    resolved_ip=canonical_resolved_ip,
                )

        # 3. Protocol check
        if protocol not in environment_manifest.allowed_protocols:
            return cls._blocked(
                environment_manifest, target_host, target_port, protocol,
                EgressBlockReason.PROTOCOL_NOT_ALLOWED,
            )

        # 4. Cross-environment production targeting check
        # Non-production environments must not reach hosts listed only in production
        if environment_manifest.kind in _NONPROD_ENVIRONMENTS:
            if cls._looks_like_production_host(target_host):
                return cls._blocked(
                    environment_manifest, target_host, target_port, protocol,
                    EgressBlockReason.PRODUCTION_TARGET_FROM_NONPROD,
                )

        # 5. Host allowlist (if manifest defines one)
        if environment_manifest.allowed_egress_hosts:
            if not any(
                target_host == h or target_host.endswith(f".{h}")
                for h in environment_manifest.allowed_egress_hosts
            ):
                return cls._blocked(
                    environment_manifest, target_host, target_port, protocol,
                    EgressBlockReason.ENVIRONMENT_POLICY,
                )

        payload = {
            "schema_version": SCHEMA_VERSION,
            "environment_id": environment_manifest.environment_id,
            "environment_kind": environment_manifest.kind.value,
            "target_host": target_host,
            "resolved_ip": canonical_resolved_ip,
            "target_port": target_port,
            "protocol": protocol,
            "decision": EgressDecision.ALLOW.value,
            "block_reason": None,
        }
        receipt_id = _content_addressed_id("egress", payload)
        receipt_hash = _canonical_sha256({"receipt_id": receipt_id, **payload})
        return EgressDecisionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=environment_manifest.environment_id,
            environment_kind=environment_manifest.kind,
            target_host=target_host,
            resolved_ip=canonical_resolved_ip,
            target_port=target_port,
            protocol=protocol,
            decision=EgressDecision.ALLOW,
            block_reason=None,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def _check_ip(ip_str: str) -> Optional[EgressBlockReason]:
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return EgressBlockReason.UNKNOWN_IP_CLASS
        for network in _BLOCKED_NETWORKS:
            if addr.version != network.version:
                continue
            if addr in network:
                if addr.is_loopback:
                    return EgressBlockReason.LOOPBACK
                if isinstance(addr, ipaddress.IPv4Address) and str(addr).startswith("169.254."):
                    return EgressBlockReason.METADATA_IP
                if isinstance(addr, ipaddress.IPv6Address) and addr.is_link_local:
                    return EgressBlockReason.METADATA_IP
                return EgressBlockReason.PRIVATE_NETWORK
        if not addr.is_global:
            return EgressBlockReason.UNKNOWN_IP_CLASS
        return None

    @staticmethod
    def _looks_like_production_host(host: str) -> bool:
        """Heuristic to detect production-domain hosts from non-production code.

        This is a conservative blocklist; the caller's manifest allowlist is
        the authoritative gate. This heuristic provides defence-in-depth.
        """
        prod_indicators = (".prod.", "-prod.", ".production.", "-production.", "prod-")
        return any(ind in host for ind in prod_indicators)

    @classmethod
    def _blocked(
        cls,
        manifest: EnvironmentManifest,
        target_host: str,
        target_port: Optional[int],
        protocol: str,
        reason: EgressBlockReason,
        *,
        resolved_ip: Optional[str] = None,
    ) -> EgressDecisionReceipt:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "environment_id": manifest.environment_id,
            "environment_kind": manifest.kind.value,
            "target_host": target_host,
            "resolved_ip": resolved_ip,
            "target_port": target_port,
            "protocol": protocol,
            "decision": EgressDecision.BLOCK.value,
            "block_reason": reason.value,
        }
        receipt_id = _content_addressed_id("egress", payload)
        receipt_hash = _canonical_sha256({"receipt_id": receipt_id, **payload})
        return EgressDecisionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=manifest.environment_id,
            environment_kind=manifest.kind,
            target_host=target_host,
            resolved_ip=resolved_ip,
            target_port=target_port,
            protocol=protocol,
            decision=EgressDecision.BLOCK,
            block_reason=reason,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def verify(receipt: EgressDecisionReceipt) -> bool:
        if receipt.schema_version != SCHEMA_VERSION:
            return False
        if receipt.decision == EgressDecision.ALLOW and receipt.block_reason is not None:
            return False
        if receipt.decision == EgressDecision.BLOCK and receipt.block_reason is None:
            return False
        try:
            host = _canonical_host(receipt.target_host)
            protocol = _canonical_protocol(receipt.protocol)
            resolved_ip = (
                str(ipaddress.ip_address(receipt.resolved_ip))
                if receipt.resolved_ip is not None else None
            )
        except (EnvironmentContractError, ValueError):
            return False
        if host != receipt.target_host or protocol != receipt.protocol:
            return False
        payload = {
            "schema_version": receipt.schema_version,
            "environment_id": receipt.environment_id,
            "environment_kind": receipt.environment_kind.value,
            "target_host": receipt.target_host,
            "resolved_ip": resolved_ip,
            "target_port": receipt.target_port,
            "protocol": receipt.protocol,
            "decision": receipt.decision.value,
            "block_reason": receipt.block_reason.value if receipt.block_reason else None,
        }
        expected_id = _content_addressed_id("egress", payload)
        return (
            receipt.receipt_id == expected_id
            and receipt.receipt_hash == _canonical_sha256({"receipt_id": expected_id, **payload})
        )


# ---------------------------------------------------------------------------
# McpInstallationBinder (pure)
# ---------------------------------------------------------------------------

class McpInstallationBinder:
    """Produce exact, registry-revision-bound MCP tool/server/installation references."""

    @classmethod
    def bind(
        cls,
        *,
        tool_id: str,
        server_id: str,
        installation_id: str,
        registry_revision: str,
        verified_at_revision: Optional[str] = None,
    ) -> McpInstallationBinding:
        tool_id = _validate_bounded_text(
            tool_id, field="tool_id", max_length=_MAX_TOOL_ID_LEN
        )
        server_id = _validate_bounded_text(server_id, field="server_id")
        installation_id = _validate_bounded_text(
            installation_id, field="installation_id"
        )
        registry_revision = _validate_revision(
            registry_revision, field="registry_revision"
        )
        verified_at_revision = _validate_revision(
            verified_at_revision, field="verified_at_revision"
        )
        if registry_revision is None or verified_at_revision is None:
            raise EnvironmentContractError(
                "registry_revision and verified_at_revision are required."
            )
        assert tool_id is not None and server_id is not None and installation_id is not None
        payload = {
            "tool_id": tool_id,
            "server_id": server_id,
            "installation_id": installation_id,
            "registry_revision": registry_revision,
            "verified_at_revision": verified_at_revision,
        }
        binding_id = _content_addressed_id("installation", payload)
        binding_hash = _canonical_sha256({"binding_id": binding_id, **payload})
        return McpInstallationBinding(
            binding_id=binding_id,
            tool_id=tool_id,
            server_id=server_id,
            installation_id=installation_id,
            registry_revision=registry_revision,
            verified_at_revision=verified_at_revision,
            binding_hash=binding_hash,
        )

    @staticmethod
    def verify(binding: McpInstallationBinding) -> bool:
        try:
            _validate_bounded_text(binding.tool_id, field="tool_id", max_length=_MAX_TOOL_ID_LEN)
            _validate_bounded_text(binding.server_id, field="server_id")
            _validate_bounded_text(binding.installation_id, field="installation_id")
            if _validate_revision(binding.registry_revision, field="registry_revision") is None:
                return False
            if _validate_revision(binding.verified_at_revision, field="verified_at_revision") is None:
                return False
        except EnvironmentContractError:
            return False
        payload = {
            "tool_id": binding.tool_id,
            "server_id": binding.server_id,
            "installation_id": binding.installation_id,
            "registry_revision": binding.registry_revision,
            "verified_at_revision": binding.verified_at_revision,
        }
        expected_id = _content_addressed_id("installation", payload)
        return (
            binding.binding_id == expected_id
            and binding.binding_hash == _canonical_sha256({"binding_id": expected_id, **payload})
        )


# ---------------------------------------------------------------------------
# ExecutionIdentityReceiptBuilder (pure)
# ---------------------------------------------------------------------------

class ExecutionIdentityReceiptBuilder:
    """Compose a final ExecutionIdentityReceipt from all resolved components."""

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        environment_manifest: EnvironmentManifest,
        principal_receipt: PrincipalResolutionReceipt,
        credential_receipt: CredentialResolutionReceipt,
        egress_receipt: EgressDecisionReceipt,
        installation_binding: McpInstallationBinding,
        is_mutation: bool = False,
    ) -> ExecutionIdentityReceipt:
        run_id = _validate_bounded_text(run_id, field="run_id")
        assert run_id is not None
        if not EnvironmentManifestCompiler.verify(environment_manifest):
            raise EnvironmentContractError("environment_manifest failed verification.")
        if not PrincipalResolver.verify(principal_receipt):
            raise EnvironmentContractError("principal_receipt failed verification.")
        if not CredentialResolver.verify(credential_receipt):
            raise EnvironmentContractError("credential_receipt failed verification.")
        if not EgressPolicyEngine.verify(egress_receipt):
            raise EnvironmentContractError("egress_receipt failed verification.")
        if not McpInstallationBinder.verify(installation_binding):
            raise EnvironmentContractError("installation_binding failed verification.")

        env_id = environment_manifest.environment_id
        for name, value in [
            ("principal_receipt", principal_receipt.environment_id),
            ("credential_receipt", credential_receipt.environment_id),
            ("egress_receipt", egress_receipt.environment_id),
        ]:
            if value != env_id:
                raise EnvironmentContractError(
                    f"{name}.environment_id={value!r} does not match "
                    f"manifest.environment_id={env_id!r}."
                )
        if principal_receipt.run_id != run_id:
            raise EnvironmentContractError("principal_receipt.run_id does not match execution run_id.")
        if principal_receipt.revision != environment_manifest.revision:
            raise EnvironmentContractError("principal receipt revision does not match manifest revision.")
        if installation_binding.verified_at_revision != environment_manifest.revision:
            raise EnvironmentContractError("installation binding is not verified at the manifest revision.")
        if principal_receipt.owner_id != environment_manifest.repo_owner:
            raise EnvironmentContractError("principal owner does not match manifest owner.")
        if credential_receipt.owner_id != principal_receipt.owner_id:
            raise EnvironmentContractError("credential owner does not match principal owner.")
        if credential_receipt.executed_as_principal_id != principal_receipt.principal_id:
            raise EnvironmentContractError("credential principal does not match resolved principal.")
        if egress_receipt.environment_kind != environment_manifest.kind:
            raise EnvironmentContractError("egress environment kind does not match manifest kind.")
        if egress_receipt.decision != EgressDecision.ALLOW:
            raise EnvironmentContractError(
                f"Cannot build ExecutionIdentityReceipt: egress decision is "
                f"{egress_receipt.decision.value!r} "
                f"(reason: {egress_receipt.block_reason!r})."
            )
        if is_mutation and credential_receipt.mode == CredentialMode.ANONYMOUS:
            raise EnvironmentContractError("anonymous credentials cannot authorize mutations.")

        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "revision": environment_manifest.revision,
            "environment_manifest_hash": environment_manifest.manifest_hash,
            "principal_receipt_id": principal_receipt.receipt_id,
            "credential_receipt_id": credential_receipt.receipt_id,
            "egress_receipt_id": egress_receipt.receipt_id,
            "installation_binding_id": installation_binding.binding_id,
            "tool_id": installation_binding.tool_id,
            "environment_kind": environment_manifest.kind.value,
            "is_mutation": is_mutation,
        }
        receipt_id = _content_addressed_id("execution", payload)
        receipt_hash = _canonical_sha256({"receipt_id": receipt_id, **payload})
        return ExecutionIdentityReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            revision=environment_manifest.revision,
            environment_manifest_hash=environment_manifest.manifest_hash,
            principal_receipt_id=principal_receipt.receipt_id,
            credential_receipt_id=credential_receipt.receipt_id,
            egress_receipt_id=egress_receipt.receipt_id,
            installation_binding_id=installation_binding.binding_id,
            tool_id=installation_binding.tool_id,
            environment_kind=environment_manifest.kind,
            is_mutation=is_mutation,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def verify(receipt: ExecutionIdentityReceipt) -> bool:
        if receipt.schema_version != SCHEMA_VERSION or not _SHA40.fullmatch(receipt.revision):
            return False
        payload = {
            "schema_version": receipt.schema_version,
            "run_id": receipt.run_id,
            "revision": receipt.revision,
            "environment_manifest_hash": receipt.environment_manifest_hash,
            "principal_receipt_id": receipt.principal_receipt_id,
            "credential_receipt_id": receipt.credential_receipt_id,
            "egress_receipt_id": receipt.egress_receipt_id,
            "installation_binding_id": receipt.installation_binding_id,
            "tool_id": receipt.tool_id,
            "environment_kind": receipt.environment_kind.value,
            "is_mutation": receipt.is_mutation,
        }
        expected_id = _content_addressed_id("execution", payload)
        return (
            receipt.receipt_id == expected_id
            and receipt.receipt_hash == _canonical_sha256({"receipt_id": expected_id, **payload})
        )
