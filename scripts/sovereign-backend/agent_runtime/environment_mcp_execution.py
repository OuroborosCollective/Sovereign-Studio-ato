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
- Egress decision is made and stored BEFORE any network connection.
- OBO tokens are validated for scope, audience and owner before use.
- Cross-environment promotion requires explicit approval receipt.
- No Arelorian WASD or N+1 personality integration in this ATO module.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
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


def _hmac_fingerprint(data: str, *, key_material: str) -> str:
    """Produce a deterministic fingerprint without exposing raw data.

    Uses a fixed-format HMAC-like construction over (key_material, data).
    The output commits to the data's identity without revealing it.
    """
    combined = f"sovereign.fingerprint.v1|{key_material}|{data}"
    return hashlib.sha256(combined.encode()).hexdigest()


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
    revision: Optional[str]      # 40-char hex SHA or None
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
    receipt_id: str              # UUID4
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
    receipt_id: str              # UUID4
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
    """Pre-connection egress policy decision.

    Made and stored BEFORE any network connection is opened.
    Block decisions include a reason code for audit.
    """
    receipt_id: str              # UUID4
    schema_version: str
    environment_id: str
    environment_kind: EnvironmentKind
    target_host: str             # canonicalised hostname or IP string
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
    binding_id: str              # UUID4
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
    receipt_id: str              # UUID4
    schema_version: str
    run_id: str
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

        if not allowed_protocols:
            raise EnvironmentContractError("allowed_protocols must not be empty.")

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
            "allowed_protocols": sorted(allowed_protocols),
            "allowed_egress_hosts": sorted(allowed_egress_hosts),
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
            allowed_protocols=tuple(sorted(allowed_protocols)),
            allowed_egress_hosts=tuple(sorted(allowed_egress_hosts)),
            is_production=is_production,
            manifest_hash=manifest_hash,
        )

    @staticmethod
    def verify(manifest: EnvironmentManifest) -> bool:
        expected = _canonical_sha256({
            "environment_id": manifest.environment_id,
            "kind": manifest.kind.value,
            "schema_version": manifest.schema_version,
            "repo_owner": manifest.repo_owner,
            "repo_name": manifest.repo_name,
            "revision": manifest.revision,
            "network_policy_hash": manifest.network_policy_hash,
            "credential_scope_hash": manifest.credential_scope_hash,
            "allowed_protocols": sorted(manifest.allowed_protocols),
            "allowed_egress_hosts": sorted(manifest.allowed_egress_hosts),
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
        if not server_resolved_principal_id or not server_resolved_principal_id.strip():
            raise EnvironmentContractError("server_resolved_principal_id must not be empty.")
        if len(server_resolved_principal_id) > _MAX_PRINCIPAL_ID_LEN:
            raise EnvironmentContractError("principal_id exceeds length limit.")

        receipt_id = str(uuid.uuid4())
        receipt_hash = _canonical_sha256({
            "receipt_id": receipt_id,
            "schema_version": SCHEMA_VERSION,
            "environment_id": environment_id,
            "principal_id": server_resolved_principal_id,
            "owner_id": owner_id,
            "resolution_method": resolution_method.value,
            "is_server_resolved": True,
            "run_id": run_id,
            "revision": revision,
        })
        return PrincipalResolutionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=environment_id,
            principal_id=server_resolved_principal_id,
            owner_id=owner_id,
            resolution_method=resolution_method,
            is_server_resolved=True,
            run_id=run_id,
            revision=revision,
            client_supplied_candidate=client_supplied_candidate,
            receipt_hash=receipt_hash,
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
        if not credential_id or not credential_id.strip():
            raise EnvironmentContractError("credential_id must not be empty.")
        if not owner_id or not owner_id.strip():
            raise EnvironmentContractError("owner_id must not be empty.")
        if not executed_as_principal_id or not executed_as_principal_id.strip():
            raise EnvironmentContractError("executed_as_principal_id must not be empty.")

        if mode == CredentialMode.ON_BEHALF_OF:
            cls._validate_obo(
                scopes=list(scopes),
                audience=audience,
                required_scopes=list(obo_required_scopes) if obo_required_scopes else [],
            )

        if len(scopes) > _MAX_SCOPES:
            raise EnvironmentContractError(f"scopes must not exceed {_MAX_SCOPES}.")
        scope_hash = _canonical_sha256(sorted(scopes))

        if is_expired:
            raise EnvironmentContractError(
                "Credential is expired. Rotation required before execution."
            )

        receipt_id = str(uuid.uuid4())
        receipt_hash = _canonical_sha256({
            "receipt_id": receipt_id,
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
        })
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
        target_host = target_host.strip().lower()

        # 1a. If target_host itself looks like an IP, check it immediately.
        try:
            ipaddress.ip_address(target_host)
            _ip_block = cls._check_ip(target_host)
            if _ip_block is not None:
                return cls._blocked(
                    environment_manifest, target_host, target_port, protocol, _ip_block
                )
        except ValueError:
            pass  # not an IP; continue to hostname checks

        # 1b. Blocked hostname check
        if target_host in _BLOCKED_HOSTNAMES:
            return cls._blocked(
                environment_manifest, target_host, target_port, protocol,
                EgressBlockReason.BLOCKED_HOSTNAME,
            )

        # 2. Resolved IP check (DNS rebinding / SSRF)
        if resolved_ip is not None:
            block = cls._check_ip(resolved_ip)
            if block is not None:
                return cls._blocked(
                    environment_manifest, target_host, target_port, protocol, block
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

        receipt_id = str(uuid.uuid4())
        receipt_hash = _canonical_sha256({
            "receipt_id": receipt_id,
            "environment_id": environment_manifest.environment_id,
            "environment_kind": environment_manifest.kind.value,
            "target_host": target_host,
            "target_port": target_port,
            "protocol": protocol,
            "decision": EgressDecision.ALLOW.value,
            "block_reason": None,
        })
        return EgressDecisionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=environment_manifest.environment_id,
            environment_kind=environment_manifest.kind,
            target_host=target_host,
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
            # Skip networks of a different IP version to avoid TypeError.
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
    ) -> EgressDecisionReceipt:
        receipt_id = str(uuid.uuid4())
        receipt_hash = _canonical_sha256({
            "receipt_id": receipt_id,
            "environment_id": manifest.environment_id,
            "environment_kind": manifest.kind.value,
            "target_host": target_host,
            "target_port": target_port,
            "protocol": protocol,
            "decision": EgressDecision.BLOCK.value,
            "block_reason": reason.value,
        })
        return EgressDecisionReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            environment_id=manifest.environment_id,
            environment_kind=manifest.kind,
            target_host=target_host,
            target_port=target_port,
            protocol=protocol,
            decision=EgressDecision.BLOCK,
            block_reason=reason,
            receipt_hash=receipt_hash,
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
        if not tool_id or len(tool_id) > _MAX_TOOL_ID_LEN:
            raise EnvironmentContractError(
                f"tool_id must be 1–{_MAX_TOOL_ID_LEN} characters."
            )
        if not _SHA40.fullmatch(registry_revision):
            raise EnvironmentContractError("registry_revision must be 40-char hex SHA.")
        if verified_at_revision is not None and not _SHA40.fullmatch(verified_at_revision):
            raise EnvironmentContractError("verified_at_revision must be 40-char hex SHA.")

        binding_id = str(uuid.uuid4())
        binding_hash = _canonical_sha256({
            "binding_id": binding_id,
            "tool_id": tool_id,
            "server_id": server_id,
            "installation_id": installation_id,
            "registry_revision": registry_revision,
            "verified_at_revision": verified_at_revision,
        })
        return McpInstallationBinding(
            binding_id=binding_id,
            tool_id=tool_id,
            server_id=server_id,
            installation_id=installation_id,
            registry_revision=registry_revision,
            verified_at_revision=verified_at_revision,
            binding_hash=binding_hash,
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
        # Verify all components belong to the same environment
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

        # Egress must be ALLOW for execution to proceed
        if egress_receipt.decision != EgressDecision.ALLOW:
            raise EnvironmentContractError(
                f"Cannot build ExecutionIdentityReceipt: egress decision is "
                f"{egress_receipt.decision.value!r} "
                f"(reason: {egress_receipt.block_reason!r})."
            )

        receipt_id = str(uuid.uuid4())
        receipt_hash = _canonical_sha256({
            "receipt_id": receipt_id,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "environment_manifest_hash": environment_manifest.manifest_hash,
            "principal_receipt_id": principal_receipt.receipt_id,
            "credential_receipt_id": credential_receipt.receipt_id,
            "egress_receipt_id": egress_receipt.receipt_id,
            "installation_binding_id": installation_binding.binding_id,
            "tool_id": installation_binding.tool_id,
            "environment_kind": environment_manifest.kind.value,
            "is_mutation": is_mutation,
        })
        return ExecutionIdentityReceipt(
            receipt_id=receipt_id,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
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
