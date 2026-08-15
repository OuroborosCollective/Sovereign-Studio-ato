from __future__ import annotations

import hashlib

import pytest

from tool_behavior_contract import (
    ToolBehaviorContract,
    ToolBehaviorContractError,
    canonical_json,
    canonical_sha256,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA256_A = "a" * 64
DIGEST_A = "sha256:" + "a" * 64


def _local_oci_contract(**overrides) -> ToolBehaviorContract:
    base = dict(
        schema_version="sovereign.tool-behavior-contract.v1",
        tool_id="tool.canary.local",
        execution_kind="LOCAL_OCI",
        repository_revision=SHA_A,
        tool_registry_revision=SHA_A,
        image_digest=DIGEST_A,
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


def test_identical_contract_produces_identical_hash() -> None:
    first = _local_oci_contract()
    second = _local_oci_contract()
    assert first.contract_sha256 == second.contract_sha256
    assert len(first.contract_sha256) == 64


def test_changing_image_digest_changes_hash() -> None:
    base = _local_oci_contract()
    changed = _local_oci_contract(image_digest="sha256:" + "b" * 64)
    assert base.contract_sha256 != changed.contract_sha256


def test_changing_network_target_changes_hash() -> None:
    base = _local_oci_contract()
    changed = _local_oci_contract(allowed_network_targets=("registry.other.invalid",))
    assert base.contract_sha256 != changed.contract_sha256


def test_changing_exec_path_changes_hash() -> None:
    base = _local_oci_contract()
    changed = _local_oci_contract(allowed_exec=("/usr/bin/false",))
    assert base.contract_sha256 != changed.contract_sha256


def test_changing_write_path_changes_hash() -> None:
    base = _local_oci_contract()
    changed = _local_oci_contract(allowed_write_paths=("/workspace/repo/other",))
    assert base.contract_sha256 != changed.contract_sha256


def test_field_order_does_not_change_hash() -> None:
    record_a = {
        "a": "1",
        "b": ["2", "1"],
        "c": {"z": "9", "a": "0"},
    }
    record_b = {
        "c": {"a": "0", "z": "9"},
        "b": ["2", "1"],
        "a": "1",
    }
    assert canonical_sha256(record_a) == canonical_sha256(record_b)


def test_unsorted_input_is_normalized_into_sorted_tuple() -> None:
    c1 = _local_oci_contract(allowed_exec=("/usr/bin/true", "/usr/bin/zcat", "/usr/bin/awk"))
    c2 = _local_oci_contract(allowed_exec=("/usr/bin/awk", "/usr/bin/zcat", "/usr/bin/true"))
    assert c1.allowed_exec == c2.allowed_exec
    assert c1.contract_sha256 == c2.contract_sha256


def test_invalid_sha_in_repository_revision_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="repository_revision"):
        _local_oci_contract(repository_revision="not-a-sha")


def test_invalid_image_digest_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="image_digest"):
        _local_oci_contract(image_digest="sha256:zzz")


def test_invalid_bare_digest_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="image_digest"):
        _local_oci_contract(image_digest="zz" * 32)


def test_negative_resource_limits_are_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="max_wall_time_ms"):
        _local_oci_contract(max_wall_time_ms=-1)
    with pytest.raises(ToolBehaviorContractError, match="max_memory_bytes"):
        _local_oci_contract(max_memory_bytes=-5)


def test_bool_resource_limits_are_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="max_wall_time_ms"):
        _local_oci_contract(max_wall_time_ms=True)


def test_unknown_execution_kind_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="execution_kind"):
        _local_oci_contract(execution_kind="VM")


def test_unknown_effect_class_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="effect_class"):
        _local_oci_contract(effect_class="ROOT")


def test_read_only_contract_must_not_declare_write_paths() -> None:
    with pytest.raises(ToolBehaviorContractError, match="READ_ONLY"):
        _local_oci_contract(
            effect_class="READ_ONLY",
            allowed_write_paths=("/workspace/repo/out",),
        )


def test_read_only_contract_with_no_write_paths_is_allowed() -> None:
    c = _local_oci_contract(effect_class="READ_ONLY", allowed_write_paths=())
    assert c.effect_class == "READ_ONLY"
    assert c.allowed_write_paths == ()


def test_local_oci_requires_image_digest() -> None:
    with pytest.raises(ToolBehaviorContractError, match="LOCAL_OCI"):
        _local_oci_contract(image_digest=None)


def test_remote_mcp_must_not_bind_image_digest() -> None:
    with pytest.raises(ToolBehaviorContractError, match="REMOTE_MCP"):
        ToolBehaviorContract(
            schema_version="sovereign.tool-behavior-contract.v1",
            tool_id="tool.remote",
            execution_kind="REMOTE_MCP",
            repository_revision=SHA_A,
            tool_registry_revision=SHA_A,
            image_digest=DIGEST_A,
            effect_class="READ_ONLY",
            allowed_exec=("/usr/bin/true",),
            allowed_read_paths=(),
            allowed_write_paths=(),
            allowed_network_targets=(),
            network_required=False,
            max_wall_time_ms=5000,
            max_memory_bytes=256 * 1024 * 1024,
        )


def test_external_write_requires_network() -> None:
    with pytest.raises(ToolBehaviorContractError, match="EXTERNAL_WRITE"):
        _local_oci_contract(effect_class="EXTERNAL_WRITE", network_required=False)


def test_network_required_without_targets_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="network_required"):
        _local_oci_contract(network_required=True, allowed_network_targets=())


def test_path_traversal_in_write_paths_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="write"):
        _local_oci_contract(allowed_write_paths=("/workspace/repo/../etc",))


def test_backslash_path_separator_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="backslash"):
        _local_oci_contract(allowed_read_paths=("C:\\workspace",))


def test_interior_empty_path_segments_are_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="empty path segments"):
        _local_oci_contract(allowed_read_paths=("/workspace//repo",))


def test_absolute_path_with_leading_slash_is_allowed() -> None:
    c = _local_oci_contract(allowed_read_paths=("/workspace/repo",))
    assert c.allowed_read_paths == ("/workspace/repo",)


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(ToolBehaviorContractError, match="schema_version"):
        _local_oci_contract(schema_version="sovereign.tool-behavior-contract.v0")


def test_contract_hash_is_recomputed_after_revision_rebind() -> None:
    original = _local_oci_contract()
    rebound = original.with_revision(repository_revision=SHA_B, tool_registry_revision=SHA_B)
    assert rebound.contract_sha256 != original.contract_sha256
    assert rebound.repository_revision == SHA_B


def test_from_mapping_round_trip_preserves_hash() -> None:
    contract = _local_oci_contract()
    record = contract.canonical_record()
    rebuilt = ToolBehaviorContract.from_mapping(record)
    assert rebuilt.contract_sha256 == contract.contract_sha256
    assert rebuilt.canonical_record() == record


def test_canonical_json_rejects_floats() -> None:
    with pytest.raises(ToolBehaviorContractError, match="floating-point"):
        canonical_json({"a": 1.5})


def test_canonical_json_rejects_non_string_keys() -> None:
    with pytest.raises(ToolBehaviorContractError, match="non-string key"):
        canonical_json({1: "a"})


def test_digest_value_can_be_bare_sha256() -> None:
    c = _local_oci_contract(image_digest="a" * 64)
    assert c.image_digest == "a" * 64
