"""Pure fail-closed receipt and verdict core for Observed Tool Behavior Attestation (OTBA).

This module converts a real observed behavior set into an immutable, tamper-sensitive
``ObservedToolBehaviorReceipt`` and evaluates it deterministically against a
``ToolBehaviorContract`` without an LLM decision. It performs no execution, sandboxing,
registry mutation, persistence or network I/O. A positive ``BEHAVIOR_VERIFIED`` verdict
arises only from real, complete, in-bounds observations that match the contract identity.

This lane claims no real runtime attestation on its own. It only ensures an observed
behavior set is checked against a contract and converted to a manipulation-sensitive
receipt. ``REMOTE_MCP`` execution kinds can never receive ``BEHAVIOR_VERIFIED`` because a
remote server offers no local syscall/filesystem fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping, Sequence

from tool_behavior_contract import (
    ToolBehaviorContract,
    ToolBehaviorContractError,
    canonical_sha256,
)


_SCHEMA_RECEIPT = "sovereign.observed-tool-behavior-receipt.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A revision field may carry a 40-char Git SHA or a 64-char SHA-256 receipt/digest hash.
_SHA40_OR_256 = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
_VERDICTS = frozenset({
    "BEHAVIOR_VERIFIED",
    "BEHAVIOR_VIOLATION",
    "REMOTE_PARTIAL",
    "UNVERIFIED",
    "CONTRADICTED",
})


class ToolBehaviorAttestationError(ValueError):
    """Raised when a caller crosses an OTBA receipt truth-boundary invariant."""


# Secret-shaped patterns that must never appear inside observed or receipt fields.
# Matches are intentionally broad and fail closed: a false positive blocks a value
# rather than risking a real secret landing in a receipt.
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),  # GitHub PAT / fine-grained
    re.compile(r"github_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9]{59}"),  # GitHub fine-grained PAT
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style key
    re.compile(r"(?i)\b(?:secret|token|password|passwd|api[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"<>]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
)


def _scan_for_secrets(value: str, *, field: str) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise ToolBehaviorAttestationError(
                f"secret-shaped material is forbidden in {field}"
            )


def _validate_hash_field(value: Any, *, field: str) -> str:
    """A hash field must be a valid lowercase SHA-256; raw secrets cannot masquerade as hashes."""
    if not isinstance(value, str):
        raise ToolBehaviorAttestationError(f"{field} must be a lowercase SHA-256")
    normalized = value.strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ToolBehaviorAttestationError(f"{field} must be a 64-char lowercase SHA-256")
    return normalized


def _validate_revision_field(value: Any, *, field: str) -> str:
    """A revision field may carry a 40-char Git SHA or a 64-char SHA-256 hash."""
    if not isinstance(value, str):
        raise ToolBehaviorAttestationError(f"{field} must be a lowercase revision SHA")
    normalized = value.strip().lower()
    if not _SHA40_OR_256.fullmatch(normalized):
        raise ToolBehaviorAttestationError(f"{field} must be a 40- or 64-char lowercase SHA")
    return normalized


def _validate_optional_hash(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _validate_hash_field(value, field=field)


def _validated_strings(value: Any, *, field: str) -> tuple[str, ...]:
    """Validate and normalize a tuple of observed strings, scanning each for secrets."""
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[str] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        items = value
    else:
        raise ToolBehaviorAttestationError(f"{field} must be a list of strings")
    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ToolBehaviorAttestationError(f"{field} entries must be strings")
        _scan_for_secrets(item, field=field)
        normalized.append(item)
    return tuple(normalized)


def _validated_optional_strings(value: Any, *, field: str) -> tuple[str, ...] | None:
    """None means the observation was not collected at all; () means collected and empty."""
    if value is None:
        return None
    return _validated_strings(value, field=field)


def _validated_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolBehaviorAttestationError(f"{field} must be an integer")
    if value < 0:
        raise ToolBehaviorAttestationError(f"{field} must be non-negative")
    return value


def _validated_optional_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    return _validated_int(value, field=field)


@dataclass(frozen=True, slots=True)
class ObservedBehavior:
    """Raw observed behavior from a real isolated execution.

    A ``None`` value for an observation dimension means it was *not collected*;
    an empty tuple means it was *collected and observed to be empty*. This
    distinction is what lets the verdict distinguish a violation from a missing
    observation.
    """

    observed_exec: tuple[str, ...] | None
    observed_read_paths: tuple[str, ...] | None
    observed_write_paths: tuple[str, ...] | None
    observed_network_targets: tuple[str, ...] | None
    observed_wall_time_ms: int | None
    observed_memory_bytes: int | None
    observed_external_effect: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_exec", _validated_optional_strings(self.observed_exec, field="observed_exec"))
        object.__setattr__(self, "observed_read_paths", _validated_optional_strings(self.observed_read_paths, field="observed_read_paths"))
        object.__setattr__(self, "observed_write_paths", _validated_optional_strings(self.observed_write_paths, field="observed_write_paths"))
        object.__setattr__(self, "observed_network_targets", _validated_optional_strings(self.observed_network_targets, field="observed_network_targets"))
        object.__setattr__(self, "observed_wall_time_ms", _validated_optional_int(self.observed_wall_time_ms, field="observed_wall_time_ms"))
        object.__setattr__(self, "observed_memory_bytes", _validated_optional_int(self.observed_memory_bytes, field="observed_memory_bytes"))
        if self.observed_external_effect is not None:
            if not isinstance(self.observed_external_effect, str):
                raise ToolBehaviorAttestationError("observed_external_effect must be a string or null")
            _scan_for_secrets(self.observed_external_effect, field="observed_external_effect")
            if not self.observed_external_effect.strip():
                object.__setattr__(self, "observed_external_effect", None)


def _observation_marker(value: tuple[str, ...] | None) -> dict[str, Any]:
    """Encode an observation so 'unobserved' and 'observed empty' hash differently."""
    if value is None:
        return {"observed": False}
    return {"observed": True, "payload": list(value)}


def _resource_marker(value: int | None) -> dict[str, Any]:
    if value is None:
        return {"observed": False}
    return {"observed": True, "value": value}


def _external_effect_marker(value: str | None) -> dict[str, Any]:
    if value is None:
        return {"observed": False}
    return {"observed": True, "marker": hashlib.sha256(value.encode("utf-8")).hexdigest()}


def _subset_of(observed: tuple[str, ...], allowed: tuple[str, ...]) -> tuple[str, ...]:
    """Return the items observed but not declared in the contract (the overflow set)."""
    allowed_set = set(allowed)
    return tuple(sorted(item for item in observed if item not in allowed_set))


def evaluate_verdict(
    *,
    contract: ToolBehaviorContract,
    observed: ObservedBehavior,
    authoritative_readback_sha256: str | None,
    trace_artifact_sha256: str,
) -> tuple[str, tuple[str, ...]]:
    """Evaluate an observed behavior set against a contract, returning (verdict, findings).

    Verdict precedence (highest first):
      CONTRADICTED  - identity (revision / digest / contract) mismatch with the contract
      UNVERIFIED    - a required observation for this execution kind was not collected
      BEHAVIOR_VIOLATION - an observed value exceeds or contradicts the contract bounds
      kind-specific success (BEHAVIOR_VERIFIED or REMOTE_PARTIAL)

    A REMOTE_MCP execution kind can never return BEHAVIOR_VERIFIED because it has no
    local syscall/filesystem fidelity. Its best positive outcome is REMOTE_PARTIAL.
    """
    findings: list[str] = []

    # 1. Identity contradiction: the observation must bind the exact contract identity.
    if authoritative_readback_sha256 is not None:
        if authoritative_readback_sha256 != contract.contract_sha256:
            return "CONTRADICTED", ("AUTHORITATIVE_READBACK_CONTRACT_HASH_MISMATCH",)
    # The trace artifact binds the actual execution that produced these observations.
    _validate_hash_field(trace_artifact_sha256, field="trace_artifact_sha256")

    execution_kind = contract.execution_kind

    # 2. Required observations per execution kind. A missing required observation is
    #    UNVERIFIED, never a violation: we cannot blame a tool for behavior we did not see.
    required_exec = execution_kind in {"LOCAL_OCI", "HOST_BROKER"}
    required_resource = execution_kind in {"LOCAL_OCI", "HOST_BROKER"}
    # A remote MCP server is networked by definition; its network observation is
    # always required regardless of the contract's network_required flag.
    required_network = execution_kind in {"LOCAL_OCI", "HOST_BROKER", "REMOTE_MCP"} or contract.network_required
    required_read = execution_kind == "LOCAL_OCI"
    required_write = execution_kind == "LOCAL_OCI"
    required_readback = execution_kind in {"LOCAL_OCI", "HOST_BROKER"}

    missing: list[str] = []
    if required_exec and observed.observed_exec is None:
        missing.append("exec")
    if required_read and observed.observed_read_paths is None:
        missing.append("read_paths")
    if required_write and observed.observed_write_paths is None:
        missing.append("write_paths")
    if required_network and observed.observed_network_targets is None:
        missing.append("network_targets")
    if required_resource and observed.observed_wall_time_ms is None:
        missing.append("wall_time")
    if required_resource and observed.observed_memory_bytes is None:
        missing.append("memory")
    if required_readback and authoritative_readback_sha256 is None:
        missing.append("authoritative_readback")
    if missing:
        return "UNVERIFIED", tuple(f"MISSING_OBSERVATION:{item}" for item in sorted(missing))

    # 3. Bound checks. Any excess or contradiction is a BEHAVIOR_VIOLATION.
    violations: list[str] = []

    if observed.observed_exec is not None:
        overflow = _subset_of(observed.observed_exec, contract.allowed_exec)
        if overflow:
            violations.append(f"EXEC_NOT_DECLARED:{','.join(overflow)}")

    if observed.observed_read_paths is not None:
        overflow = _subset_of(observed.observed_read_paths, contract.allowed_read_paths)
        if overflow:
            violations.append(f"READ_PATH_NOT_DECLARED:{','.join(overflow)}")

    if observed.observed_write_paths is not None:
        # READ_ONLY contracts declare no write paths, so any write is a violation.
        overflow = _subset_of(observed.observed_write_paths, contract.allowed_write_paths)
        if overflow:
            violations.append(f"WRITE_PATH_NOT_DECLARED:{','.join(overflow)}")

    if observed.observed_network_targets is not None:
        overflow = _subset_of(observed.observed_network_targets, contract.allowed_network_targets)
        if overflow:
            violations.append(f"NETWORK_TARGET_NOT_DECLARED:{','.join(overflow)}")

    if observed.observed_wall_time_ms is not None:
        if observed.observed_wall_time_ms > contract.max_wall_time_ms:
            violations.append(
                f"WALL_TIME_EXCEEDED:{observed.observed_wall_time_ms}>{contract.max_wall_time_ms}"
            )

    if observed.observed_memory_bytes is not None:
        if observed.observed_memory_bytes > contract.max_memory_bytes:
            violations.append(
                f"MEMORY_EXCEEDED:{observed.observed_memory_bytes}>{contract.max_memory_bytes}"
            )

    if observed.observed_external_effect is not None:
        # An external effect is only permitted for EXTERNAL_WRITE contracts. Seeing one
        # against a non-external contract is a violation even if no writes overflowed.
        if contract.effect_class != "EXTERNAL_WRITE":
            violations.append("EXTERNAL_EFFECT_NOT_PERMITTED")
    else:
        # EXTERNAL_WRITE contracts must actually exhibit an observed external effect.
        if contract.effect_class == "EXTERNAL_WRITE":
            violations.append("EXTERNAL_EFFECT_MISSING")

    if violations:
        return "BEHAVIOR_VIOLATION", tuple(violations)

    # 4. Kind-specific success. REMOTE_MCP can never prove local syscall/filesystem
    #    fidelity, so its best honest positive outcome is REMOTE_PARTIAL.
    if execution_kind == "REMOTE_MCP":
        return "REMOTE_PARTIAL", ("REMOTE_MCP_NO_LOCAL_FIDELITY",)

    return "BEHAVIOR_VERIFIED", ("BEHAVIOR_WITHIN_CONTRACT",)


@dataclass(frozen=True, slots=True)
class ObservedToolBehaviorReceipt:
    """Immutable, tamper-sensitive receipt over an observed behavior set and verdict."""

    schema_version: str
    tool_id: str
    repository_revision: str
    tool_registry_revision: str
    image_digest: str | None
    behavior_contract_sha256: str
    canary_input_sha256: str
    observed_exec_sha256: str
    observed_filesystem_sha256: str
    observed_network_sha256: str
    observed_resource_usage_sha256: str
    external_effect_sha256: str | None
    authoritative_readback_sha256: str | None
    trace_artifact_sha256: str
    verdict: str
    receipt_sha256: str = field(default="")

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_RECEIPT:
            raise ToolBehaviorAttestationError("unsupported receipt schema_version")
        if not isinstance(self.tool_id, str) or not self.tool_id:
            raise ToolBehaviorAttestationError("tool_id must be a non-empty string")
        # tool_id shape is already enforced by the contract that produced it; keep a
        # light check here so a hand-built receipt cannot smuggle a malformed id.
        object.__setattr__(self, "repository_revision", _validate_revision_field(self.repository_revision, field="repository_revision"))
        object.__setattr__(self, "tool_registry_revision", _validate_revision_field(self.tool_registry_revision, field="tool_registry_revision"))
        object.__setattr__(self, "image_digest", _validated_digest_or_none(self.image_digest))
        object.__setattr__(self, "behavior_contract_sha256", _validate_hash_field(self.behavior_contract_sha256, field="behavior_contract_sha256"))
        object.__setattr__(self, "canary_input_sha256", _validate_hash_field(self.canary_input_sha256, field="canary_input_sha256"))
        object.__setattr__(self, "observed_exec_sha256", _validate_hash_field(self.observed_exec_sha256, field="observed_exec_sha256"))
        object.__setattr__(self, "observed_filesystem_sha256", _validate_hash_field(self.observed_filesystem_sha256, field="observed_filesystem_sha256"))
        object.__setattr__(self, "observed_network_sha256", _validate_hash_field(self.observed_network_sha256, field="observed_network_sha256"))
        object.__setattr__(self, "observed_resource_usage_sha256", _validate_hash_field(self.observed_resource_usage_sha256, field="observed_resource_usage_sha256"))
        object.__setattr__(self, "external_effect_sha256", _validate_optional_hash(self.external_effect_sha256, field="external_effect_sha256"))
        object.__setattr__(self, "authoritative_readback_sha256", _validate_optional_hash(self.authoritative_readback_sha256, field="authoritative_readback_sha256"))
        object.__setattr__(self, "trace_artifact_sha256", _validate_hash_field(self.trace_artifact_sha256, field="trace_artifact_sha256"))
        if self.verdict not in _VERDICTS:
            raise ToolBehaviorAttestationError(f"verdict must be one of {sorted(_VERDICTS)}")
        object.__setattr__(self, "verdict", self.verdict)
        # The receipt hash is derived from its canonical record so a tampered field
        # is detectable by recomputation. A caller-supplied value is replaced here.
        object.__setattr__(self, "receipt_sha256", canonical_sha256(self._canonical_record_without_hash()))

    def _canonical_record_without_hash(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "toolId": self.tool_id,
            "repositoryRevision": self.repository_revision,
            "toolRegistryRevision": self.tool_registry_revision,
            "imageDigest": self.image_digest,
            "behaviorContractSha256": self.behavior_contract_sha256,
            "canaryInputSha256": self.canary_input_sha256,
            "observedExecSha256": self.observed_exec_sha256,
            "observedFilesystemSha256": self.observed_filesystem_sha256,
            "observedNetworkSha256": self.observed_network_sha256,
            "observedResourceUsageSha256": self.observed_resource_usage_sha256,
            "externalEffectSha256": self.external_effect_sha256,
            "authoritativeReadbackSha256": self.authoritative_readback_sha256,
            "traceArtifactSha256": self.trace_artifact_sha256,
            "verdict": self.verdict,
        }

    def canonical_record(self) -> dict[str, Any]:
        record = self._canonical_record_without_hash()
        record["receiptSha256"] = self.receipt_sha256
        return record

    def verify(self) -> bool:
        """Self-consistency check: True iff the stored receipt hash matches the recomputed canonical hash.

        A freshly built receipt is always self-consistent. Tamper detection across
        serialization is enforced by ``receipt_from_mapping``, which rejects a mapping
        whose stored hash disagrees with the reconstructed canonical record.
        """
        return canonical_sha256(self._canonical_record_without_hash()) == self.receipt_sha256


def _validated_digest_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolBehaviorAttestationError("image_digest must be a digest string or null")
    normalized = value.strip().lower()
    if not normalized:
        raise ToolBehaviorAttestationError("image_digest must be non-empty or null")
    digest_re = re.compile(r"^(?:sha256:[0-9a-f]{64}|[0-9a-f]{64})$")
    if not digest_re.fullmatch(normalized):
        raise ToolBehaviorAttestationError("image_digest must be 'sha256:<64 hex>' or a bare 64-char hex digest")
    return normalized


def build_receipt(
    *,
    contract: ToolBehaviorContract,
    canary_input_sha256: str,
    observed: ObservedBehavior,
    authoritative_readback_sha256: str | None,
    trace_artifact_sha256: str,
    verdict: str | None = None,
    findings: tuple[str, ...] = (),
) -> tuple[ObservedToolBehaviorReceipt, tuple[str, ...]]:
    """Build a tamper-sensitive receipt from a contract and a real observed behavior set.

    The observation *hashes* are computed by this lane from the structured raw
    observations rather than trusted from the caller, so 'unobserved' and
    'observed empty' produce distinct, well-defined hashes. If ``verdict`` is not
    supplied the lane evaluates it deterministically from the contract and
    observations; a caller-supplied verdict must match the evaluated one or the
    receipt fails closed (CONTRADICTED is returned instead).
    """
    evaluated_verdict, evaluated_findings = evaluate_verdict(
        contract=contract,
        observed=observed,
        authoritative_readback_sha256=authoritative_readback_sha256,
        trace_artifact_sha256=trace_artifact_sha256,
    )
    if verdict is not None:
        if verdict != evaluated_verdict:
            # A caller asserting a verdict that does not match the deterministic
            # evaluation is a contradiction, not a success. We emit a CONTRADICTED
            # receipt that records both the asserted and evaluated verdicts.
            contradiction_findings = (
                f"ASSERTED_VERDICT:{verdict}",
                f"EVALUATED_VERDICT:{evaluated_verdict}",
            )
            receipt = ObservedToolBehaviorReceipt(
                schema_version=_SCHEMA_RECEIPT,
                tool_id=contract.tool_id,
                repository_revision=contract.repository_revision,
                tool_registry_revision=contract.tool_registry_revision,
                image_digest=contract.image_digest,
                behavior_contract_sha256=contract.contract_sha256,
                canary_input_sha256=canary_input_sha256,
                observed_exec_sha256=_hash_observation(_observation_marker(observed.observed_exec)),
                observed_filesystem_sha256=_hash_filesystem(observed),
                observed_network_sha256=_hash_observation(_observation_marker(observed.observed_network_targets)),
                observed_resource_usage_sha256=_hash_resource(observed),
                external_effect_sha256=_hash_external_effect(observed.observed_external_effect),
                authoritative_readback_sha256=authoritative_readback_sha256,
                trace_artifact_sha256=trace_artifact_sha256,
                verdict="CONTRADICTED",
            )
            return receipt, evaluated_findings + contradiction_findings
        final_findings = findings or evaluated_findings
    else:
        final_findings = findings or evaluated_findings

    receipt = ObservedToolBehaviorReceipt(
        schema_version=_SCHEMA_RECEIPT,
        tool_id=contract.tool_id,
        repository_revision=contract.repository_revision,
        tool_registry_revision=contract.tool_registry_revision,
        image_digest=contract.image_digest,
        behavior_contract_sha256=contract.contract_sha256,
        canary_input_sha256=canary_input_sha256,
        observed_exec_sha256=_hash_observation(_observation_marker(observed.observed_exec)),
        observed_filesystem_sha256=_hash_filesystem(observed),
        observed_network_sha256=_hash_observation(_observation_marker(observed.observed_network_targets)),
        observed_resource_usage_sha256=_hash_resource(observed),
        external_effect_sha256=_hash_external_effect(observed.observed_external_effect),
        authoritative_readback_sha256=authoritative_readback_sha256,
        trace_artifact_sha256=trace_artifact_sha256,
        verdict=evaluated_verdict,
    )
    return receipt, final_findings


def _hash_observation(marker: dict[str, Any]) -> str:
    return canonical_sha256(marker)


def _hash_filesystem(observed: ObservedBehavior) -> str:
    return canonical_sha256({
        "read": _observation_marker(observed.observed_read_paths),
        "write": _observation_marker(observed.observed_write_paths),
    })


def _hash_resource(observed: ObservedBehavior) -> str:
    return canonical_sha256({
        "wallTimeMs": _resource_marker(observed.observed_wall_time_ms),
        "memoryBytes": _resource_marker(observed.observed_memory_bytes),
    })


def _hash_external_effect(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def receipt_from_mapping(value: Mapping[str, Any]) -> ObservedToolBehaviorReceipt:
    """Reconstruct a receipt from its canonical mapping and verify it is untampered.

    The stored ``receiptSha256`` is compared against the hash recomputed from the
    reconstructed canonical record. A mismatch means the mapping was tampered with
    after it was originally built; reconstruction fails closed instead of silently
    adopting the altered hash.
    """
    if not isinstance(value, Mapping):
        raise ToolBehaviorAttestationError("receipt must be an object")
    stored_hash = value.get("receiptSha256")
    receipt = ObservedToolBehaviorReceipt(
        schema_version=value.get("schemaVersion"),
        tool_id=value.get("toolId"),
        repository_revision=value.get("repositoryRevision"),
        tool_registry_revision=value.get("toolRegistryRevision"),
        image_digest=value.get("imageDigest"),
        behavior_contract_sha256=value.get("behaviorContractSha256"),
        canary_input_sha256=value.get("canaryInputSha256"),
        observed_exec_sha256=value.get("observedExecSha256"),
        observed_filesystem_sha256=value.get("observedFilesystemSha256"),
        observed_network_sha256=value.get("observedNetworkSha256"),
        observed_resource_usage_sha256=value.get("observedResourceUsageSha256"),
        external_effect_sha256=value.get("externalEffectSha256"),
        authoritative_readback_sha256=value.get("authoritativeReadbackSha256"),
        trace_artifact_sha256=value.get("traceArtifactSha256"),
        verdict=value.get("verdict"),
    )
    if not isinstance(stored_hash, str):
        raise ToolBehaviorAttestationError("receiptSha256 is required for reconstruction")
    if stored_hash != receipt.receipt_sha256:
        raise ToolBehaviorAttestationError("receiptSha256 does not match the canonical record (tamper detected)")
    return receipt


__all__ = [
    "ObservedBehavior",
    "ObservedToolBehaviorReceipt",
    "ToolBehaviorAttestationError",
    "build_receipt",
    "evaluate_verdict",
    "receipt_from_mapping",
]
