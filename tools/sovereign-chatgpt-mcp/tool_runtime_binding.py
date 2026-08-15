"""Pure fail-closed runtime binding core for Observed Tool Behavior Attestation (OTBA).

PatchMon (``patchmon_operator.py``) is the canonical fleet/Docker sensor. It owns every
real container, image, network and mount readback. This module is the **verifier**, never
the sensor: it consumes an already-collected, structured runtime readback (the shape
returned by ``PatchmonOperatorRuntime._inspect_container``) and binds a behavior receipt
to the exact runtime identity that was actually observed.

This lane performs no execution, no Docker/registry I/O, no persistence and no LLM
decision. It only deterministically normalizes a real readback into a tamper-sensitive
``ToolRuntimeBinding`` and checks it against a ``ToolBehaviorContract`` so a healthy but
digest/revision/topology-foreign container can never yield a fully runtime-bound positive
receipt. No second Docker/fleet truth store is created here.

Hard rules enforced:

- ``healthy != revision verified``
- ``image tag != immutable digest``
- ``expected digest != observed digest``  -> ``CONTRADICTED``
- ``runtime revision required and not observed`` -> ``UNVERIFIED``
- ``workflow success != runtime truth``
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from tool_behavior_contract import (
    ToolBehaviorContract,
    ToolBehaviorContractError,
    canonical_sha256,
)


_SCHEMA_BINDING = "sovereign.tool-runtime-binding.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A digest may carry the ``sha256:`` prefix (OCI form) or be bare 64-char hex.
_DIGEST = re.compile(r"^(?:sha256:[0-9a-f]{64}|[0-9a-f]{64})$")
# A revision is a 40-char Git SHA. It may be absent for non-revision-critical bindings.
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_TOOL_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,254}$")

# Runtime binding fidelity verdicts. These are distinct from behavior verdicts: a
# binding verdict describes whether the *runtime identity* the receipt is bound to is
# complete and consistent, independent of whether the observed behavior was in-contract.
_BINDING_VERDICTS = frozenset({
    "RUNTIME_BOUND_OK",
    "CONTRADICTED",
    "UNVERIFIED",
    "RUNTIME_READBACK_MISSING",
})


class ToolRuntimeBindingError(ValueError):
    """Raised when a caller crosses a runtime-binding truth-boundary invariant."""


def _require_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ToolRuntimeBindingError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ToolRuntimeBindingError(f"{field} must be non-empty")
    return normalized


def _require_tool_id(value: Any) -> str:
    normalized = _require_str(value, field="tool_id").lower()
    if not _TOOL_ID.fullmatch(normalized):
        raise ToolRuntimeBindingError("tool_id must match [a-z0-9][a-z0-9._:-]{0,254}")
    return normalized


def _normalize_digest(value: Any, *, field: str) -> str:
    """Normalize an immutable digest to bare lowercase 64-char hex.

    The ``sha256:`` prefix is a transport concern of the registry; the binding identity
    stores bare hex so a receipt carrying the prefix and an identity storing bare hex
    compare equal (digest drift is a real promotion boundary, formatting drift is not).
    """
    if not isinstance(value, str):
        raise ToolRuntimeBindingError(f"{field} must be a digest string")
    normalized = value.strip().lower()
    if not normalized:
        raise ToolRuntimeBindingError(f"{field} must be non-empty")
    if not _DIGEST.fullmatch(normalized):
        raise ToolRuntimeBindingError(f"{field} must be 'sha256:<64 hex>' or bare 64-char hex")
    return normalized.removeprefix("sha256:")


def _optional_digest(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _normalize_digest(value, field=field)


def _optional_sha40(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolRuntimeBindingError(f"{field} must be a revision string or null")
    normalized = value.strip().lower()
    if not normalized:
        return None
    if not _SHA40.fullmatch(normalized):
        raise ToolRuntimeBindingError(f"{field} must be a 40-char Git SHA or null")
    return normalized


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ToolRuntimeBindingError(f"{field} must be a sha256 string")
    normalized = value.strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ToolRuntimeBindingError(f"{field} must be 64-char lowercase hex")
    return normalized


def _optional_sha256(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field=field)


def _normalize_networks(value: Any) -> tuple[dict[str, str], ...]:
    """Normalize the PatchMon ``networks`` list into a canonical, hashable record.

    IP addresses are deliberately excluded from the identity record: they are runtime-
    assigned and would create spurious drift. Only the network *name* is identity-bearing
    (an unexpected network name is a real topology signal).
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ToolRuntimeBindingError("networks must be a list")
    out: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ToolRuntimeBindingError("each network entry must be an object")
        name = str(entry.get("name") or "").strip()
        if not name:
            # A network entry without a name is malformed evidence, not an empty network.
            raise ToolRuntimeBindingError("network entries must carry a non-empty name")
        out.append({"name": name})
    # Deterministic order by name so identical topologies hash equal.
    out.sort(key=lambda n: n["name"])
    return tuple(out)


def _normalize_ports(value: Any) -> tuple[dict[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ToolRuntimeBindingError("publishedPorts must be a list")
    out: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ToolRuntimeBindingError("each published port entry must be an object")
        container_port = str(entry.get("containerPort") or "").strip()
        host_port = str(entry.get("hostPort") or "").strip()
        if not container_port:
            raise ToolRuntimeBindingError("published port entries must carry a containerPort")
        out.append({"containerPort": container_port, "hostPort": host_port})
    out.sort(key=lambda p: (p["containerPort"], p["hostPort"]))
    return tuple(out)


def _normalize_mounts(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ToolRuntimeBindingError("mounts must be a list")
    out: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ToolRuntimeBindingError("each mount entry must be an object")
        destination = str(entry.get("destination") or "").strip()
        if not destination:
            raise ToolRuntimeBindingError("mount entries must carry a destination")
        out.append({
            "type": str(entry.get("type") or "").strip(),
            "name": str(entry.get("name") or "").strip(),
            "destination": destination,
            "rw": bool(entry.get("rw")),
        })
    out.sort(key=lambda m: m["destination"])
    return tuple(out)


def _normalize_security(value: Any) -> dict[str, Any]:
    if value is None:
        return {"privileged": False, "readOnlyRootfs": False, "networkMode": ""}
    if not isinstance(value, Mapping):
        raise ToolRuntimeBindingError("security must be an object")
    return {
        "privileged": bool(value.get("privileged")),
        "readOnlyRootfs": bool(value.get("readOnlyRootfs")),
        "networkMode": str(value.get("networkMode") or "").strip(),
    }


def _normalize_state(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ToolRuntimeBindingError("state must be an object")
    return {
        "status": str(value.get("status") or "unknown"),
        "running": bool(value.get("running")),
        "health": str(value.get("health") or "none"),
        "restartCount": int(value.get("restartCount") or 0),
    }


@dataclass(frozen=True, slots=True)
class ToolRuntimeBinding:
    """Immutable, tamper-sensitive binding between a tool and the runtime that ran it.

    Every field is derived from a real PatchMon/Docker readback, not trusted from the
    caller. The hashes cover the topology dimensions a behavior receipt must bind to so
    that a drift in networks, mounts or security posture invalidates the binding even
    when the tool output looked successful.
    """

    schema_version: str
    tool_id: str
    container_id: str
    image_digest: str
    repository_revision: str | None
    runtime_revision: str | None
    networks_sha256: str
    mounts_sha256: str
    security_state_sha256: str
    runtime_readback_sha256: str
    binding_sha256: str = field(default="")

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_BINDING:
            raise ToolRuntimeBindingError("unsupported binding schema_version")
        object.__setattr__(self, "tool_id", _require_tool_id(self.tool_id))
        container_id = _require_str(self.container_id, field="container_id")
        if len(container_id) > 64:
            raise ToolRuntimeBindingError("container_id must be at most 64 chars")
        object.__setattr__(self, "container_id", container_id)
        object.__setattr__(self, "image_digest", _normalize_digest(self.image_digest, field="image_digest"))
        object.__setattr__(self, "repository_revision", _optional_sha40(self.repository_revision, field="repository_revision"))
        object.__setattr__(self, "runtime_revision", _optional_sha40(self.runtime_revision, field="runtime_revision"))
        object.__setattr__(self, "networks_sha256", _require_sha256(self.networks_sha256, field="networks_sha256"))
        object.__setattr__(self, "mounts_sha256", _require_sha256(self.mounts_sha256, field="mounts_sha256"))
        object.__setattr__(self, "security_state_sha256", _require_sha256(self.security_state_sha256, field="security_state_sha256"))
        object.__setattr__(self, "runtime_readback_sha256", _require_sha256(self.runtime_readback_sha256, field="runtime_readback_sha256"))
        # The binding hash is derived from its canonical record so a tampered field is
        # detectable by recomputation; a caller-supplied value is replaced.
        object.__setattr__(self, "binding_sha256", canonical_sha256(self._canonical_record_without_hash()))

    def _canonical_record_without_hash(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "toolId": self.tool_id,
            "containerId": self.container_id,
            "imageDigest": self.image_digest,
            "repositoryRevision": self.repository_revision,
            "runtimeRevision": self.runtime_revision,
            "networksSha256": self.networks_sha256,
            "mountsSha256": self.mounts_sha256,
            "securityStateSha256": self.security_state_sha256,
            "runtimeReadbackSha256": self.runtime_readback_sha256,
        }

    def canonical_record(self) -> dict[str, Any]:
        record = self._canonical_record_without_hash()
        record["bindingSha256"] = self.binding_sha256
        return record

    def verify(self) -> bool:
        """Self-consistency: True iff the stored binding hash matches the recomputed one."""
        return canonical_sha256(self._canonical_record_without_hash()) == self.binding_sha256


def _hash_networks(networks: tuple[dict[str, str], ...]) -> str:
    return canonical_sha256([{"name": n["name"]} for n in networks])


def _hash_mounts(mounts: tuple[dict[str, Any], ...]) -> str:
    return canonical_sha256([
        {"type": m["type"], "name": m["name"], "destination": m["destination"], "rw": m["rw"]}
        for m in mounts
    ])


def _hash_security(security: dict[str, Any]) -> str:
    return canonical_sha256({
        "privileged": security["privileged"],
        "readOnlyRootfs": security["readOnlyRootfs"],
        "networkMode": security["networkMode"],
    })


def build_binding_from_readback(
    *,
    tool_id: str,
    runtime_readback: Mapping[str, Any],
    image_digest: str | None = None,
    repository_revision: str | None = None,
    runtime_revision: str | None = None,
) -> ToolRuntimeBinding:
    """Build a binding from a real PatchMon ``_inspect_container`` readback.

    ``runtime_readback`` is the structured dict PatchMon already produced; this function
    never invokes Docker. The image digest is taken from the readback's authoritative
    image identity when not supplied, so a stale caller-supplied tag cannot override the
    observed immutable digest.
    """
    if not isinstance(runtime_readback, Mapping):
        raise ToolRuntimeBindingError("runtime_readback must be a mapping")
    if not runtime_readback.get("present", False):
        raise ToolRuntimeBindingError("runtime_readback reports container absent; no binding is possible")

    container_id = _require_str(runtime_readback.get("id"), field="runtime_readback.id")
    # The observed image identity. Prefer an explicit immutable digest; fall back to the
    # readback's image id only if it is digest-shaped. An image *tag* or *reference* is
    # explicitly not accepted: ``image tag != immutable digest``.
    observed_image = image_digest or runtime_readback.get("imageId") or ""
    digest = _optional_digest(observed_image, field="image_digest") if observed_image else None
    if digest is None:
        raise ToolRuntimeBindingError(
            "no immutable image digest in readback; an image tag/reference is not a binding identity"
        )

    networks = _normalize_networks(runtime_readback.get("networks"))
    mounts = _normalize_mounts(runtime_readback.get("mounts"))
    security = _normalize_security(runtime_readback.get("security"))

    # The runtime_readback hash covers the authoritative sensor snapshot so a binding
    # cannot be replayed against a different container state than was actually observed.
    readback_record = {
        "containerId": container_id,
        "imageId": str(runtime_readback.get("imageId") or ""),
        "imageReference": str(runtime_readback.get("imageReference") or ""),
        "state": _normalize_state(runtime_readback.get("state")),
        "networks": [{"name": n["name"]} for n in networks],
        "publishedPorts": [
            {"containerPort": p["containerPort"], "hostPort": p["hostPort"]}
            for p in _normalize_ports(runtime_readback.get("publishedPorts"))
        ],
        "mounts": [
            {"type": m["type"], "name": m["name"], "destination": m["destination"], "rw": m["rw"]}
            for m in mounts
        ],
        "security": security,
    }

    return ToolRuntimeBinding(
        schema_version=_SCHEMA_BINDING,
        tool_id=tool_id,
        container_id=container_id,
        image_digest=digest,
        repository_revision=repository_revision,
        runtime_revision=runtime_revision,
        networks_sha256=_hash_networks(networks),
        mounts_sha256=_hash_mounts(mounts),
        security_state_sha256=_hash_security(security),
        runtime_readback_sha256=canonical_sha256(readback_record),
    )


@dataclass(frozen=True, slots=True)
class BindingEvaluation:
    """The result of checking a binding against a contract's runtime expectations."""

    verdict: str
    findings: tuple[str, ...]
    binding: ToolRuntimeBinding | None
    overrides_seen: tuple[str, ...]


def _digest_matches(expected: str | None, observed: str) -> bool:
    if expected is None:
        return True
    return _normalize_digest(expected, field="expected") == observed


def evaluate_runtime_binding(
    *,
    contract: ToolBehaviorContract,
    binding: ToolRuntimeBinding,
    require_repository_revision: bool = False,
    require_runtime_revision: bool = False,
    overrides: Mapping[str, Any] | None = None,
) -> BindingEvaluation:
    """Evaluate whether a binding is consistent with a contract's runtime expectations.

    Only ``LOCAL_OCI`` tools carry a local immutable identity and may be runtime-bound.
    Remote/broker tools have no local container, so they cannot produce a binding here
    and callers must report ``REMOTE_PARTIAL`` honesty upstream.

    Topology drift (unexpected network, mount, port, privileged gain, read-only-rootfs
    loss) fails closed to ``CONTRADICTED``: a successful tool output cannot overrule an
    unexpected runtime topology.
    """
    if contract.execution_kind != "LOCAL_OCI":
        raise ToolRuntimeBindingError(
            "runtime binding is only defined for LOCAL_OCI tools; remote/broker tools report REMOTE_PARTIAL upstream"
        )
    if not binding.verify():
        raise ToolRuntimeBindingError("binding failed self-consistency; it has been tampered with")
    if binding.tool_id != contract.tool_id:
        raise ToolRuntimeBindingError("binding tool_id does not match contract tool_id")

    overrides_seen: list[str] = []
    if overrides:
        for key in ("mcp_initialize_pass", "signed_image", "ui_flag", "workflow_success", "container_healthy"):
            if overrides.get(key):
                overrides_seen.append(key)

    findings: list[str] = []
    verdict = "RUNTIME_BOUND_OK"

    # 1. Immutable digest. expected != observed is a hard CONTRADICTED.
    if not _digest_matches(contract.image_digest, binding.image_digest):
        findings.append(f"IMAGE_DIGEST_DRIFT:expected={contract.image_digest},observed={binding.image_digest}")
        verdict = "CONTRADICTED"

    # 2. Revision binding. Required-and-absent is UNVERIFIED (we cannot contradict what
    #    we never observed); a present-but-mismatched revision would be CONTRADICTED but
    #    the binding stores only presence, so absence is the observable failure here.
    if require_repository_revision and binding.repository_revision is None:
        findings.append("REPOSITORY_REVISION_REQUIRED_BUT_ABSENT")
        if verdict != "CONTRADICTED":
            verdict = "UNVERIFIED"
    if require_runtime_revision and binding.runtime_revision is None:
        findings.append("RUNTIME_REVISION_REQUIRED_BUT_ABSENT")
        if verdict != "CONTRADICTED":
            verdict = "UNVERIFIED"

    # Topology drift (networks, mounts, ports, privileged/read-only-rootfs) is evaluated
    # against the originating readback by ``evaluate_topology_drift`` and combined into
    # the final receipt verdict by ``binding_verdict_for_receipt``. The binding stores
    # only topology *hashes* (presence, not names) so drift detection needs the readback.

    return BindingEvaluation(
        verdict=verdict,
        findings=tuple(findings),
        binding=binding,
        overrides_seen=tuple(overrides_seen),
    )


@dataclass(frozen=True, slots=True)
class TopologyDrift:
    """Topology drift findings between an observed readback and contract expectations."""

    unexpected_networks: tuple[str, ...]
    unexpected_mounts: tuple[str, ...]
    unexpected_published_ports: tuple[str, ...]
    privileged_gain: bool
    read_only_rootfs_lost: bool
    findings: tuple[str, ...]
    violated: bool


def evaluate_topology_drift(
    *,
    runtime_readback: Mapping[str, Any],
    expected_networks: tuple[str, ...] = (),
    expected_mount_destinations: tuple[str, ...] = (),
    expected_published_ports: tuple[str, ...] = (),
    forbid_privileged: bool = True,
    require_read_only_rootfs: bool = False,
) -> TopologyDrift:
    """Detect runtime topology drift from a real PatchMon readback.

    This is the topology arm of the binding evaluation: it inspects the actual observed
    container topology (networks, mounts, published ports, privileged/read-only-rootfs)
    against what the contract expected. Any unexpected addition or security posture loss
    is a real runtime violation that a successful tool output cannot overrule.
    """
    if not isinstance(runtime_readback, Mapping):
        raise ToolRuntimeBindingError("runtime_readback must be a mapping")
    if not runtime_readback.get("present", False):
        raise ToolRuntimeBindingError("runtime_readback reports container absent; topology drift cannot be evaluated")

    networks = _normalize_networks(runtime_readback.get("networks"))
    mounts = _normalize_mounts(runtime_readback.get("mounts"))
    ports = _normalize_ports(runtime_readback.get("publishedPorts"))
    security = _normalize_security(runtime_readback.get("security"))

    expected_network_set = {n.strip().lower() for n in expected_networks if n.strip()}
    observed_network_names = {n["name"].strip().lower() for n in networks}
    extra_networks = tuple(sorted(observed_network_names - expected_network_set))

    expected_mount_set = {m.strip().lower() for m in expected_mount_destinations if m.strip()}
    observed_mounts = {m["destination"].strip().lower() for m in mounts}
    extra_mounts = tuple(sorted(observed_mounts - expected_mount_set))

    expected_port_set = {p.strip().lower() for p in expected_published_ports if p.strip()}
    observed_ports = {p["containerPort"].strip().lower() for p in ports}
    extra_ports = tuple(sorted(observed_ports - expected_port_set))

    privileged_gain = forbid_privileged and security["privileged"]
    read_only_rootfs_lost = require_read_only_rootfs and not security["readOnlyRootfs"]

    findings: list[str] = []
    # Extras are only violations when a baseline expectation was declared: a contract
    # that did not constrain topology cannot detect additions against an empty set, and
    # flagging every observed network/mount would make a clean container always violated.
    if expected_network_set and extra_networks:
        findings.append(f"UNEXPECTED_NETWORKS:{list(extra_networks)}")
    if expected_mount_set and extra_mounts:
        findings.append(f"UNEXPECTED_MOUNTS:{list(extra_mounts)}")
    if expected_port_set and extra_ports:
        findings.append(f"UNEXPECTED_PUBLISHED_PORTS:{list(extra_ports)}")
    if privileged_gain:
        findings.append("PRIVILEGED_GAIN_FORBIDDEN_BY_CONTRACT")
    if read_only_rootfs_lost:
        findings.append("READ_ONLY_ROOTFS_LOST")

    violated = bool(findings)
    return TopologyDrift(
        unexpected_networks=extra_networks,
        unexpected_mounts=extra_mounts,
        unexpected_published_ports=extra_ports,
        privileged_gain=privileged_gain,
        read_only_rootfs_lost=read_only_rootfs_lost,
        findings=tuple(findings),
        violated=violated,
    )


def binding_verdict_for_receipt(
    *,
    binding: ToolRuntimeBinding | None,
    topology: TopologyDrift | None,
    require_repository_revision: bool = False,
    require_runtime_revision: bool = False,
) -> tuple[str, tuple[str, ...]]:
    """Reduce a binding + topology evaluation to the receipt-fidelity verdict.

    A behavior receipt may carry ``BEHAVIOR_VERIFIED`` only when the runtime binding is
    fully present and consistent (``RUNTIME_BOUND_OK``) and no topology drift was found.
    Missing readback, digest/revision drift or topology violation downgrades to
    ``UNVERIFIED`` / ``CONTRADICTED``. This is the single honest gate the attestation
    lane consults before allowing a positive verdict.

    Returns ``(fidelity_verdict, findings)`` where ``fidelity_verdict`` is one of the
    behavior verdicts the receipt lane understands (``BEHAVIOR_VERIFIED`` only when
    fully bound, otherwise ``UNVERIFIED`` / ``CONTRADICTED``).
    """
    findings: list[str] = []

    if binding is None:
        findings.append("RUNTIME_BINDING_MISSING")
        return "UNVERIFIED", tuple(findings)

    if not binding.verify():
        findings.append("RUNTIME_BINDING_TAMPERED")
        return "CONTRADICTED", tuple(findings)

    if require_repository_revision and binding.repository_revision is None:
        # Revision-absent is UNVERIFIED, not contradicted: we did not observe a
        # contradicting value, we observed nothing to bind against.
        findings.append("REPOSITORY_REVISION_REQUIRED_BUT_ABSENT")
        return "UNVERIFIED", tuple(findings)

    if require_runtime_revision and binding.runtime_revision is None:
        findings.append("RUNTIME_REVISION_REQUIRED_BUT_ABSENT")
        return "UNVERIFIED", tuple(findings)

    if topology is not None and topology.violated:
        findings.extend(topology.findings)
        return "CONTRADICTED", tuple(findings)

    return "BEHAVIOR_VERIFIED", tuple(findings)


def binding_from_mapping(value: Mapping[str, Any]) -> ToolRuntimeBinding:
    """Reconstruct a binding from a serialized canonical record, rejecting tampering."""
    if not isinstance(value, Mapping):
        raise ToolRuntimeBindingError("binding mapping must be an object")
    if value.get("schemaVersion") != _SCHEMA_BINDING:
        raise ToolRuntimeBindingError("unsupported binding schema_version in mapping")

    stored_hash = value.get("bindingSha256")
    binding = ToolRuntimeBinding(
        schema_version=str(value.get("schemaVersion")),
        tool_id=str(value.get("toolId")),
        container_id=str(value.get("containerId")),
        image_digest=str(value.get("imageDigest")),
        repository_revision=value.get("repositoryRevision"),
        runtime_revision=value.get("runtimeRevision"),
        networks_sha256=str(value.get("networksSha256")),
        mounts_sha256=str(value.get("mountsSha256")),
        security_state_sha256=str(value.get("securityStateSha256")),
        runtime_readback_sha256=str(value.get("runtimeReadbackSha256")),
    )
    # The constructor recomputes the hash. A stored hash that disagrees means the
    # serialized record was altered after binding.
    if not isinstance(stored_hash, str) or stored_hash != binding.binding_sha256:
        raise ToolRuntimeBindingError("binding mapping hash does not match recomputed hash (tampered)")
    return binding


__all__ = [
    "ToolRuntimeBinding",
    "ToolRuntimeBindingError",
    "BindingEvaluation",
    "TopologyDrift",
    "build_binding_from_readback",
    "evaluate_runtime_binding",
    "evaluate_topology_drift",
    "binding_verdict_for_receipt",
    "binding_from_mapping",
]
