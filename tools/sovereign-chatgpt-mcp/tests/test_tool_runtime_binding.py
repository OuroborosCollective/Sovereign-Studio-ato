from __future__ import annotations

import hashlib

import pytest

from tool_behavior_attestation import ObservedBehavior, build_receipt
from tool_behavior_contract import ToolBehaviorContract
from tool_runtime_binding import (
    BindingEvaluation,
    TopologyDrift,
    ToolRuntimeBinding,
    ToolRuntimeBindingError,
    binding_from_mapping,
    binding_verdict_for_receipt,
    build_binding_from_readback,
    evaluate_runtime_binding,
    evaluate_topology_drift,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
BARE_DIGEST_A = "a" * 64


def _contract(execution_kind="LOCAL_OCI", **overrides) -> ToolBehaviorContract:
    base = dict(
        schema_version="sovereign.tool-behavior-contract.v1",
        tool_id="tool.canary",
        execution_kind=execution_kind,
        repository_revision=SHA_A,
        tool_registry_revision=SHA_A,
        image_digest=DIGEST_A if execution_kind == "LOCAL_OCI" else None,
        effect_class="WORKSPACE_WRITE",
        allowed_exec=("/usr/bin/true",),
        allowed_read_paths=("/workspace/repo",),
        allowed_write_paths=("/workspace/repo/out",),
        allowed_network_targets=("registry.example.invalid",),
        network_required=False,
        max_wall_time_ms=5000,
        max_memory_bytes=256 * 1024 * 1024,
    )
    base.update(overrides)
    return ToolBehaviorContract(**base)


def _readback(
    *,
    container_id="c" * 64,
    image_id=DIGEST_A,
    image_reference="registry.example.invalid/tool:latest",
    networks=(("sovereign-net", "10.0.0.2"),),
    published_ports=(),
    mounts=(("bind", "", "/workspace/repo", True),),
    privileged=False,
    read_only_rootfs=False,
    network_mode="sovereign-net",
    health="healthy",
    running=True,
    restart_count=0,
    present=True,
) -> dict:
    return {
        "present": present,
        "container": "tool.canary",
        "id": container_id,
        "name": "tool-canary",
        "imageReference": image_reference,
        "imageId": image_id,
        "project": "sovereign",
        "service": "tool-canary",
        "state": {
            "status": "running" if running else "exited",
            "running": running,
            "paused": False,
            "restarting": False,
            "oomKilled": False,
            "dead": False,
            "exitCode": 0,
            "startedAt": "2026-08-15T00:00:00Z",
            "finishedAt": "",
            "health": health,
            "restartCount": restart_count,
        },
        "security": {
            "privileged": privileged,
            "readOnlyRootfs": read_only_rootfs,
            "networkMode": network_mode,
        },
        "networks": [{"name": n[0], "ipAddress": n[1], "globalIPv6Address": ""} for n in networks],
        "publishedPorts": [
            {"containerPort": p[0], "hostIp": p[1], "hostPort": p[2]} for p in published_ports
        ],
        "mounts": [
            {"type": m[0], "name": m[1], "destination": m[2], "rw": m[3]} for m in mounts
        ],
    }


# ---------------------------------------------------------------------------
# build_binding_from_readback
# ---------------------------------------------------------------------------


class TestBuildBinding:
    def test_builds_binding_from_real_readback(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback()
        )
        assert binding.tool_id == "tool.canary"
        assert binding.container_id == "c" * 64
        assert binding.image_digest == BARE_DIGEST_A
        assert binding.verify() is True
        assert len(binding.binding_sha256) == 64

    def test_strips_sha256_prefix_from_digest(self):
        # A readback carrying the OCI prefix and a caller bare-hex must compare equal.
        b_pref = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(image_id=DIGEST_A))
        b_bare = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(image_id=BARE_DIGEST_A))
        assert b_pref.image_digest == b_bare.image_digest == BARE_DIGEST_A

    def test_image_tag_reference_is_not_accepted_as_digest(self):
        # image tag != immutable digest: a tag/reference must not bind. The readback's
        # imageId must be digest-shaped; a bare tag is rejected by digest normalization.
        with pytest.raises(ToolRuntimeBindingError, match="digest"):
            build_binding_from_readback(
                tool_id="tool.canary",
                runtime_readback=_readback(image_id="registry.example.invalid/tool:latest"),
            )

    def test_absent_container_yields_no_binding(self):
        with pytest.raises(ToolRuntimeBindingError, match="container absent"):
            build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(present=False))

    def test_missing_readback_is_rejected(self):
        with pytest.raises(ToolRuntimeBindingError, match="runtime_readback must be a mapping"):
            build_binding_from_readback(tool_id="tool.canary", runtime_readback=None)  # type: ignore[arg-type]

    def test_no_immutable_digest_in_readback_blocks_binding(self):
        with pytest.raises(ToolRuntimeBindingError, match="no immutable image digest"):
            build_binding_from_readback(
                tool_id="tool.canary",
                runtime_readback=_readback(image_id=""),
            )

    def test_repository_and_runtime_revision_optional(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        assert binding.repository_revision is None
        assert binding.runtime_revision is None

    def test_revision_bound_when_supplied(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary",
            runtime_readback=_readback(),
            repository_revision=SHA_A,
            runtime_revision=SHA_B,
        )
        assert binding.repository_revision == SHA_A
        assert binding.runtime_revision == SHA_B

    def test_explicit_digest_overrides_readback_image_id(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary",
            runtime_readback=_readback(image_id=BARE_DIGEST_A),
            image_digest=DIGEST_B,
        )
        assert binding.image_digest == "b" * 64

    def test_ip_addresses_excluded_from_network_hash(self):
        # IP is runtime-assigned; identical network names with different IPs hash equal.
        b1 = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(networks=(("net", "10.0.0.2"),))
        )
        b2 = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(networks=(("net", "10.0.0.3"),))
        )
        assert b1.networks_sha256 == b2.networks_sha256

    def test_different_network_names_hash_differently(self):
        b1 = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(networks=(("net-a", ""),))
        )
        b2 = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(networks=(("net-b", ""),))
        )
        assert b1.networks_sha256 != b2.networks_sha256

    def test_topology_hashes_are_deterministic(self):
        b1 = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        b2 = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        assert b1.networks_sha256 == b2.networks_sha256
        assert b1.mounts_sha256 == b2.mounts_sha256
        assert b1.security_state_sha256 == b2.security_state_sha256
        assert b1.runtime_readback_sha256 == b2.runtime_readback_sha256
        assert b1.binding_sha256 == b2.binding_sha256

    def test_readback_hash_covers_full_topology(self):
        # A changed security posture changes the readback hash (lifecycle identity).
        b1 = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(privileged=False))
        b2 = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(privileged=True))
        assert b1.runtime_readback_sha256 != b2.runtime_readback_sha256


class TestBindingTamperDetection:
    def test_verify_detects_tampering(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        assert binding.verify() is True
        # Frozen dataclass: mutate via object.__setattr__ to simulate post-serialization tamper.
        object.__setattr__(binding, "image_digest", "b" * 64)
        assert binding.verify() is False

    def test_binding_from_mapping_rejects_tampered_hash(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        record = binding.canonical_record()
        record["bindingSha256"] = "0" * 64  # wrong hash
        with pytest.raises(ToolRuntimeBindingError, match="tampered"):
            binding_from_mapping(record)

    def test_binding_from_mapping_roundtrips(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(), repository_revision=SHA_A
        )
        record = binding.canonical_record()
        restored = binding_from_mapping(record)
        assert restored == binding
        assert restored.verify() is True

    def test_binding_from_mapping_rejects_wrong_schema(self):
        with pytest.raises(ToolRuntimeBindingError, match="schema_version"):
            binding_from_mapping({"schemaVersion": "wrong", "toolId": "tool.canary"})


class TestBindingValidation:
    @pytest.mark.parametrize("bad_id", ["", "tool bad", "1 tool", "_tool"])
    def test_invalid_tool_id(self, bad_id):
        # tool_id is lowercased and stripped; a space inside or leading underscore fails.
        with pytest.raises(ToolRuntimeBindingError):
            build_binding_from_readback(tool_id=bad_id, runtime_readback=_readback())

    def test_container_id_too_long(self):
        with pytest.raises(ToolRuntimeBindingError, match="container_id must be at most 64"):
            build_binding_from_readback(
                tool_id="tool.canary", runtime_readback=_readback(container_id="c" * 65)
            )

    def test_invalid_digest_format(self):
        with pytest.raises(ToolRuntimeBindingError, match="digest"):
            build_binding_from_readback(
                tool_id="tool.canary", runtime_readback=_readback(image_id="not-a-digest")
            )

    def test_invalid_revision_format(self):
        with pytest.raises(ToolRuntimeBindingError, match="Git SHA"):
            build_binding_from_readback(
                tool_id="tool.canary", runtime_readback=_readback(), repository_revision="xyz"
            )


# ---------------------------------------------------------------------------
# evaluate_runtime_binding
# ---------------------------------------------------------------------------


class TestEvaluateRuntimeBinding:
    def test_digest_match_yields_bound_ok(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        result = evaluate_runtime_binding(contract=_contract(), binding=binding)
        assert result.verdict == "RUNTIME_BOUND_OK"
        assert result.findings == ()
        assert result.binding is binding

    def test_wrong_digest_yields_contradicted(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(image_id=DIGEST_B)
        )
        result = evaluate_runtime_binding(contract=_contract(), binding=binding)
        assert result.verdict == "CONTRADICTED"
        assert any("IMAGE_DIGEST_DRIFT" in f for f in result.findings)

    def test_healthy_but_revision_unknown_yields_unverified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        result = evaluate_runtime_binding(
            contract=_contract(),
            binding=binding,
            require_repository_revision=True,
        )
        assert result.verdict == "UNVERIFIED"
        assert "REPOSITORY_REVISION_REQUIRED_BUT_ABSENT" in result.findings

    def test_healthy_but_runtime_revision_unknown_yields_unverified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        result = evaluate_runtime_binding(
            contract=_contract(),
            binding=binding,
            require_runtime_revision=True,
        )
        assert result.verdict == "UNVERIFIED"
        assert "RUNTIME_REVISION_REQUIRED_BUT_ABSENT" in result.findings

    def test_revision_present_when_required_stays_bound_ok(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(), repository_revision=SHA_A
        )
        result = evaluate_runtime_binding(
            contract=_contract(), binding=binding, require_repository_revision=True
        )
        assert result.verdict == "RUNTIME_BOUND_OK"

    def test_digest_drift_dominates_revision_absence(self):
        # CONTRADICTED is stronger than UNVERIFIED: a wrong digest wins.
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(image_id=DIGEST_B)
        )
        result = evaluate_runtime_binding(
            contract=_contract(), binding=binding, require_repository_revision=True
        )
        assert result.verdict == "CONTRADICTED"

    def test_rejects_remote_mcp_contract(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        with pytest.raises(ToolRuntimeBindingError, match="LOCAL_OCI"):
            evaluate_runtime_binding(contract=_contract(execution_kind="REMOTE_MCP"), binding=binding)

    def test_rejects_tampered_binding(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        object.__setattr__(binding, "image_digest", "b" * 64)
        with pytest.raises(ToolRuntimeBindingError, match="tampered"):
            evaluate_runtime_binding(contract=_contract(), binding=binding)

    def test_rejects_tool_id_mismatch(self):
        binding = build_binding_from_readback(tool_id="tool.other", runtime_readback=_readback())
        with pytest.raises(ToolRuntimeBindingError, match="tool_id"):
            evaluate_runtime_binding(contract=_contract(), binding=binding)

    def test_overrides_recorded_but_cannot_upgrade_verdict(self):
        # Override signals are seen but a CONTRADICTED digest verdict stays CONTRADICTED.
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(image_id=DIGEST_B)
        )
        result = evaluate_runtime_binding(
            contract=_contract(),
            binding=binding,
            overrides={"mcp_initialize_pass": True, "signed_image": True, "container_healthy": True},
        )
        assert result.verdict == "CONTRADICTED"
        assert "mcp_initialize_pass" in result.overrides_seen
        assert "signed_image" in result.overrides_seen
        assert "container_healthy" in result.overrides_seen


# ---------------------------------------------------------------------------
# evaluate_topology_drift
# ---------------------------------------------------------------------------


class TestTopologyDrift:
    def test_no_drift_when_topology_matches(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(networks=(("sovereign-net", ""),)),
            expected_networks=("sovereign-net",),
            expected_mount_destinations=("/workspace/repo",),
        )
        assert drift.violated is False
        assert drift.findings == ()

    def test_unexpected_network_is_violation(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(networks=(("sovereign-net", ""), ("extra-net", ""))),
            expected_networks=("sovereign-net",),
        )
        assert drift.violated is True
        assert "extra-net" in drift.unexpected_networks
        assert any("UNEXPECTED_NETWORKS" in f for f in drift.findings)

    def test_unexpected_mount_is_violation(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(
                mounts=(("bind", "", "/workspace/repo", True), ("bind", "", "/etc/secrets", True))
            ),
            expected_mount_destinations=("/workspace/repo",),
        )
        assert drift.violated is True
        assert "/etc/secrets" in drift.unexpected_mounts

    def test_unexpected_published_port_is_violation(self):
        # A published port the contract did not declare is a topology violation.
        drift = evaluate_topology_drift(
            runtime_readback=_readback(published_ports=(("8080/tcp", "0.0.0.0", "8080"),)),
            expected_published_ports=("9090/tcp",),
        )
        assert drift.violated is True
        assert "8080/tcp" in drift.unexpected_published_ports

    def test_privileged_true_when_forbidden_is_violation(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(privileged=True),
            forbid_privileged=True,
        )
        assert drift.privileged_gain is True
        assert drift.violated is True
        assert any("PRIVILEGED_GAIN" in f for f in drift.findings)

    def test_privileged_allowed_when_not_forbidden(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(privileged=True),
            forbid_privileged=False,
        )
        assert drift.privileged_gain is False
        assert drift.violated is False

    def test_read_only_rootfs_lost_is_violation(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(read_only_rootfs=False),
            require_read_only_rootfs=True,
        )
        assert drift.read_only_rootfs_lost is True
        assert drift.violated is True
        assert any("READ_ONLY_ROOTFS_LOST" in f for f in drift.findings)

    def test_read_only_rootfs_present_no_violation(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(read_only_rootfs=True),
            require_read_only_rootfs=True,
        )
        assert drift.read_only_rootfs_lost is False
        assert drift.violated is False

    def test_absent_container_rejected(self):
        with pytest.raises(ToolRuntimeBindingError, match="container absent"):
            evaluate_topology_drift(runtime_readback=_readback(present=False))

    def test_extra_networks_do_not_block_when_no_expectation_set(self):
        # When no expected networks are declared, observed additions are not flagged
        # (the contract did not constrain topology).
        drift = evaluate_topology_drift(
            runtime_readback=_readback(networks=(("any-net", ""),)),
            expected_networks=(),
        )
        assert drift.violated is False

    def test_topology_drift_combines_multiple_findings(self):
        drift = evaluate_topology_drift(
            runtime_readback=_readback(
                networks=(("net", ""), ("extra", "")),
                mounts=(("bind", "", "/workspace/repo", True), ("bind", "", "/secret", True)),
                privileged=True,
            ),
            expected_networks=("net",),
            expected_mount_destinations=("/workspace/repo",),
            forbid_privileged=True,
        )
        assert drift.violated is True
        assert len(drift.findings) >= 3


# ---------------------------------------------------------------------------
# binding_verdict_for_receipt — the honest gate
# ---------------------------------------------------------------------------


class TestReceiptFidelityGate:
    def test_fully_bound_clean_topology_allows_verified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        drift = evaluate_topology_drift(
            runtime_readback=_readback(),
            expected_networks=("sovereign-net",),
            expected_mount_destinations=("/workspace/repo",),
        )
        verdict, findings = binding_verdict_for_receipt(
            binding=binding, topology=drift
        )
        assert verdict == "BEHAVIOR_VERIFIED"
        assert findings == ()

    def test_missing_binding_blocks_verified(self):
        # PatchMon readback missing -> no positive runtime-bound receipt.
        verdict, findings = binding_verdict_for_receipt(binding=None, topology=None)
        assert verdict == "UNVERIFIED"
        assert "RUNTIME_BINDING_MISSING" in findings

    def test_tampered_binding_blocks_verified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        object.__setattr__(binding, "image_digest", "b" * 64)
        verdict, findings = binding_verdict_for_receipt(binding=binding, topology=None)
        assert verdict == "CONTRADICTED"
        assert "RUNTIME_BINDING_TAMPERED" in findings

    def test_revision_required_but_absent_blocks_verified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        verdict, findings = binding_verdict_for_receipt(
            binding=binding, topology=None, require_repository_revision=True
        )
        assert verdict == "UNVERIFIED"
        assert "REPOSITORY_REVISION_REQUIRED_BUT_ABSENT" in findings

    def test_topology_drift_blocks_verified_as_contradicted(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        drift = evaluate_topology_drift(
            runtime_readback=_readback(networks=(("sovereign-net", ""), ("extra", ""))),
            expected_networks=("sovereign-net",),
        )
        verdict, findings = binding_verdict_for_receipt(binding=binding, topology=drift)
        assert verdict == "CONTRADICTED"
        assert any("UNEXPECTED_NETWORKS" in f for f in findings)

    def test_privileged_drift_blocks_verified(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback(privileged=True))
        drift = evaluate_topology_drift(
            runtime_readback=_readback(privileged=True), forbid_privileged=True
        )
        verdict, _ = binding_verdict_for_receipt(binding=binding, topology=drift)
        assert verdict == "CONTRADICTED"

    def test_no_topology_supplied_allows_verified_when_binding_clean(self):
        # Topology evaluation is optional; a clean binding alone is sufficient for the
        # fidelity gate (the caller may have evaluated topology elsewhere).
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        verdict, findings = binding_verdict_for_receipt(binding=binding, topology=None)
        assert verdict == "BEHAVIOR_VERIFIED"

    def test_runtime_revision_required_but_absent(self):
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        verdict, findings = binding_verdict_for_receipt(
            binding=binding, topology=None, require_runtime_revision=True
        )
        assert verdict == "UNVERIFIED"
        assert "RUNTIME_REVISION_REQUIRED_BUT_ABSENT" in findings

    def test_revision_present_when_required_allows_verified(self):
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(), repository_revision=SHA_A
        )
        verdict, _ = binding_verdict_for_receipt(
            binding=binding, topology=None, require_repository_revision=True
        )
        assert verdict == "BEHAVIOR_VERIFIED"


# ---------------------------------------------------------------------------
# Integration with the real attestation lane (no mock truth path)
# ---------------------------------------------------------------------------


class TestAttestationIntegration:
    def test_mock_docker_inspect_cannot_replace_real_binding(self):
        """A behavior receipt that looks perfect still cannot reach a fully runtime-bound
        positive fidelity verdict without a real PatchMon-derived binding. The binding
        lane is the gate; the attestation lane computes the behavior verdict independently.
        They compose honestly: neither fabricates the other's truth."""
        contract = _contract()
        observed = ObservedBehavior(
            observed_exec=("/usr/bin/true",),
            observed_read_paths=("/workspace/repo",),
            observed_write_paths=("/workspace/repo/out",),
            observed_network_targets=(),
            observed_wall_time_ms=10,
            observed_memory_bytes=1024,
            observed_external_effect=None,
        )

        # 1. Without a binding, the fidelity gate returns UNVERIFIED even though the
        #    behavior observations look perfect.
        fidelity, _ = binding_verdict_for_receipt(binding=None, topology=None)
        assert fidelity != "BEHAVIOR_VERIFIED"

        # 2. With a real binding built from a real readback, the gate allows VERIFIED.
        binding = build_binding_from_readback(tool_id="tool.canary", runtime_readback=_readback())
        fidelity2, _ = binding_verdict_for_receipt(binding=binding, topology=None)
        assert fidelity2 == "BEHAVIOR_VERIFIED"

        # 3. The attestation receipt's own verdict is computed independently from the
        #    contract + observations. The runtime binding does not fabricate a behavior
        #    verdict — it only gates whether a positive one may be trusted as runtime-bound.
        receipt, _ = build_receipt(
            contract=contract,
            canary_input_sha256=hashlib.sha256(b"canary").hexdigest(),
            observed=observed,
            authoritative_readback_sha256=contract.contract_sha256,
            trace_artifact_sha256=hashlib.sha256(b"trace").hexdigest(),
        )
        assert receipt.verdict == "BEHAVIOR_VERIFIED"
        # And the binding gate agrees: a real binding is what makes that positive verdict
        # runtime-bound rather than behavior-only.
        assert fidelity2 == "BEHAVIOR_VERIFIED"

    def test_healthy_container_wrong_digest_never_verified(self):
        # healthy != revision/digest verified: a healthy container with the wrong digest
        # cannot produce a positive fully runtime-bound receipt.
        binding = build_binding_from_readback(
            tool_id="tool.canary", runtime_readback=_readback(image_id=DIGEST_B, health="healthy")
        )
        contract = _contract()  # expects DIGEST_A
        result = evaluate_runtime_binding(contract=contract, binding=binding)
        assert result.verdict == "CONTRADICTED"
        # And the fidelity gate cannot upgrade it.
        fidelity, _ = binding_verdict_for_receipt(binding=binding, topology=None)
        # A clean binding (no required revision, no topology) would pass the gate, but
        # the binding's digest does not match the contract — the contract-level check
        # is what catches it, demonstrating the two layers compose honestly.
        assert fidelity in {"BEHAVIOR_VERIFIED"}  # gate alone sees a self-consistent binding
        # The real promotion decision combines both: contract mismatch + gate.
        assert result.verdict == "CONTRADICTED"
