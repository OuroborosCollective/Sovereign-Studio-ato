from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

MAX_EVIDENCE_BYTES = 32_000
MAX_AUTOMATIC_REPAIR_ATTEMPTS = 2

_TRANSACTION_CONTROL = re.compile(
    r"(?im)^\s*(BEGIN(?:\s+(?:WORK|TRANSACTION))?|START\s+TRANSACTION|COMMIT(?:\s+WORK)?|ROLLBACK(?:\s+WORK)?)\b"
)
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


@dataclass(frozen=True)
class FailurePolicy:
    family: str
    signatures: tuple[str, ...]
    repair_action: str
    auto_repairable: bool
    mutation_scope: str
    requires_confirmation: bool
    required_post_checks: tuple[str, ...]
    blocked_capabilities: tuple[str, ...] = (
        "generic_shell",
        "generic_sql",
        "direct_main_write",
        "auto_merge",
        "secret_readout",
    )


_FAILURE_POLICIES = (
    FailurePolicy(
        family="host_command_queue_contract",
        signatures=(
            "inbound_mutation_forbidden",
            "host_command_queue_timeout",
            "host_command_still_running",
            "host_command_outcome_unknown",
            "host_command_outcome_uncertain_after_worker_restart",
        ),
        repair_action="read_existing_job_status_and_inspect_host_worker_without_resubmitting",
        auto_repairable=False,
        mutation_scope="host_runtime_recovery",
        requires_confirmation=False,
        required_post_checks=(
            "host_command_worker_active",
            "queue_canary_roundtrip",
            "direct_socket_mutation_blocked",
            "target_state_verified_before_retry",
        ),
    ),
    FailurePolicy(
        family="broker_socket_namespace_visibility",
        signatures=(
            "broker_socket_path_absent",
            "broker-socket ist in diesem runtime-namespace nicht vorhanden",
            "host-broker-socket fehlt",
        ),
        repair_action="compare_host_and_container_socket_then_recreate_only_stale_mount",
        auto_repairable=False,
        mutation_scope="host_runtime_recovery",
        requires_confirmation=True,
        required_post_checks=(
            "host_socket_is_unix_socket",
            "container_socket_is_unix_socket",
            "broker_health_rpc",
            "mcp_initialize_handshake",
        ),
    ),
    FailurePolicy(
        family="broker_socket_permission_contract",
        signatures=(
            "broker_socket_permission_denied",
            "broker-socket ist sichtbar, aber für den mcp-prozess nicht zugreifbar",
        ),
        repair_action="align_host_group_gid_and_container_supplementary_group",
        auto_repairable=False,
        mutation_scope="host_runtime_recovery",
        requires_confirmation=True,
        required_post_checks=("socket_owner_group_mode", "container_group_membership", "broker_health_rpc"),
    ),
    FailurePolicy(
        family="broker_rpc_liveness",
        signatures=(
            "broker_socket_connection_refused",
            "broker_rpc_timeout",
            "broker_rpc_unavailable",
            "broker_rpc_empty_response",
            "broker_rpc_invalid_response",
            "broker_rpc_request_mismatch",
            "broker_rpc_result_missing",
            "kein broker nimmt verbindungen an",
        ),
        repair_action="restart_broker_without_recreating_runtime_directory_then_probe_health",
        auto_repairable=False,
        mutation_scope="host_runtime_recovery",
        requires_confirmation=True,
        required_post_checks=("broker_service_active", "broker_health_rpc", "mcp_initialize_handshake"),
    ),
    FailurePolicy(
        family="mcp_streamable_http_request_contract",
        signatures=(
            "post /mcp http/1.1\" 400 bad request",
            "terminating session: none",
        ),
        repair_action="identify_calling_client_then_replace_malformed_probe_without_touching_node_or_broker",
        auto_repairable=False,
        mutation_scope="host_runtime_recovery",
        requires_confirmation=True,
        required_post_checks=(
            "calling_process_identified",
            "valid_initialize_handshake",
            "no_repeated_400_window",
            "tunnel_service_active",
        ),
    ),
    FailurePolicy(
        family="tunnel_mcp_initialize_contract",
        signatures=(
            "mcp initialize returned http 400",
            "execstartpre-prüfung",
            "tunnel-healthcheck",
        ),
        repair_action="use_shared_python_jsonrpc_initialize_probe_without_shell_json",
        auto_repairable=False,
        mutation_scope="host_installer",
        requires_confirmation=True,
        required_post_checks=("mcp_initialize_handshake", "tunnel_service_active"),
    ),
    FailurePolicy(
        family="dependency_install_process_killed",
        signatures=(
            "exit_code\": -9",
            "returncode -9",
            "terminated by signal 9",
        ),
        repair_action="reduce_install_concurrency_and_memory_then_retry_once",
        auto_repairable=False,
        mutation_scope="isolated_workspace",
        requires_confirmation=False,
        required_post_checks=("lockfile_install_exit_zero", "dependency_resolver_canary"),
    ),
    FailurePolicy(
        family="dependency_resolution_incomplete",
        signatures=(
            "cannot find module 'typescript/bin/tsc'",
            "cannot find module \"typescript/bin/tsc\"",
            "status=resolution_failed",
        ),
        repair_action="verify_lockfile_install_completion_then_resolve_required_executables",
        auto_repairable=False,
        mutation_scope="isolated_workspace",
        requires_confirmation=False,
        required_post_checks=("typescript_resolves", "vite_resolves", "vitest_resolves", "capacitor_cli_resolves"),
    ),
    FailurePolicy(
        family="migration_preview_transaction_wrapper",
        signatures=(
            "migration enthält verschachtelte transaktionssteuerung",
            "nested transaction",
            "transaction already in progress",
        ),
        repair_action="normalize_one_outer_transaction_for_preview",
        auto_repairable=True,
        mutation_scope="preview_only",
        requires_confirmation=False,
        required_post_checks=("preview_rollback", "source_sha256_unchanged"),
    ),
    FailurePolicy(
        family="workspace_runtime_contract",
        signatures=("no workspace path", "permission denied", "workspace"),
        repair_action="reinstall_workspace_ownership_contract",
        auto_repairable=False,
        mutation_scope="host_installer",
        requires_confirmation=True,
        required_post_checks=("workspace_write_canary", "isolated_clone_canary"),
    ),
    FailurePolicy(
        family="repository_clone_contract",
        signatures=("clone failed", "file not found: readme.md"),
        repair_action="recreate_isolated_workspace_then_clone",
        auto_repairable=False,
        mutation_scope="isolated_workspace",
        requires_confirmation=False,
        required_post_checks=("git_head", "git_status", "readme_exists"),
    ),
    FailurePolicy(
        family="event_mapping_contract",
        signatures=(
            "toolevent' object has no attribute 'get'",
            "sovereignagentevent' object has no attribute 'get'",
        ),
        repair_action="patch_event_mapping_in_isolated_workspace",
        auto_repairable=False,
        mutation_scope="draft_pr_only",
        requires_confirmation=False,
        required_post_checks=("targeted_pytest", "backend_compile", "draft_pr"),
    ),
    FailurePolicy(
        family="backend_image_missing",
        signatures=("manifest unknown", "image not found", "kein auflösbares image"),
        repair_action="publish_exact_main_revision_image",
        auto_repairable=False,
        mutation_scope="github_actions_then_verified_deploy",
        requires_confirmation=True,
        required_post_checks=("oci_revision_label", "immutable_digest", "candidate_health"),
    ),
    FailurePolicy(
        family="stale_backend_runtime",
        signatures=("nicht neu deployter container", "alte runtime", "stale backend revision"),
        repair_action="resolve_and_deploy_verified_revision",
        auto_repairable=False,
        mutation_scope="verified_deploy",
        requires_confirmation=True,
        required_post_checks=("container_revision", "health", "post_start_log_canary"),
    ),
    FailurePolicy(
        family="postgres_authentication",
        signatures=("password authentication failed", "postgresql-authentifizierung"),
        repair_action="rerun_guarded_database_bootstrap",
        auto_repairable=False,
        mutation_scope="host_installer",
        requires_confirmation=True,
        required_post_checks=("reader_select_1", "preview_ddl_rollback"),
    ),
    FailurePolicy(
        family="vector_schema_missing",
        signatures=("vector_columns: []", "vektorspalten []"),
        repair_action="create_hash_confirmed_vector_schema_migration",
        auto_repairable=False,
        mutation_scope="migration_preview_then_confirmed_apply",
        requires_confirmation=True,
        required_post_checks=("pgvector_extension", "vector_columns", "vector_index"),
    ),
)


def _mask_range(masked: list[str], start: int, end: int) -> None:
    for index in range(start, min(end, len(masked))):
        if masked[index] not in {"\n", "\r"}:
            masked[index] = " "


def _mask_sql_noncode(sql: str) -> str:
    """Mask SQL comments, strings and dollar-quoted bodies while preserving offsets."""

    masked = list(sql)
    index = 0
    length = len(sql)

    while index < length:
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            end = length if end < 0 else end
            _mask_range(masked, index, end)
            index = end
            continue

        if sql.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if sql.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif sql.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            _mask_range(masked, index, cursor)
            index = cursor
            continue

        if sql[index] == "'":
            cursor = index + 1
            while cursor < length:
                if sql[cursor] == "'":
                    if cursor + 1 < length and sql[cursor + 1] == "'":
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            _mask_range(masked, index, cursor)
            index = cursor
            continue

        if sql[index] == '"':
            cursor = index + 1
            while cursor < length:
                if sql[cursor] == '"':
                    if cursor + 1 < length and sql[cursor + 1] == '"':
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            _mask_range(masked, index, cursor)
            index = cursor
            continue

        if sql[index] == "$":
            tag_match = _DOLLAR_TAG.match(sql, index)
            if tag_match:
                tag = tag_match.group(0)
                end = sql.find(tag, tag_match.end())
                if end >= 0:
                    end += len(tag)
                    _mask_range(masked, index, end)
                    index = end
                    continue

        index += 1

    return "".join(masked)


def _semicolon_after(masked: str, start: int) -> int:
    semicolon = masked.find(";", start)
    if semicolon < 0:
        raise ValueError("Transaktionssteuerung ohne Semikolon ist nicht erlaubt")
    return semicolon + 1


class PolicyGuardedRepairEngine:
    def diagnose(self, evidence: str) -> dict[str, Any]:
        encoded = str(evidence or "").encode("utf-8", errors="replace")[:MAX_EVIDENCE_BYTES]
        normalized = encoded.decode("utf-8", errors="replace").lower()

        for policy in _FAILURE_POLICIES:
            if policy.family == "workspace_runtime_contract":
                matched = "workspace" in normalized and any(
                    signature in normalized for signature in ("permission denied", "no workspace path")
                )
            else:
                matched = any(signature in normalized for signature in policy.signatures)
            if matched:
                return {
                    "ok": True,
                    "status": "DETECTED",
                    "policy": asdict(policy),
                    "max_automatic_attempts": MAX_AUTOMATIC_REPAIR_ATTEMPTS,
                    "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
                }

        return {
            "ok": False,
            "status": "UNKNOWN",
            "policy": {
                "family": "unknown",
                "repair_action": "collect_bounded_runtime_evidence_then_create_draft_pr",
                "auto_repairable": False,
                "mutation_scope": "draft_pr_only",
                "requires_confirmation": False,
                "required_post_checks": ["targeted_test", "runtime_canary"],
                "blocked_capabilities": list(FailurePolicy.__dataclass_fields__["blocked_capabilities"].default),
            },
            "max_automatic_attempts": 0,
            "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def normalize_migration_preview(self, sql: str) -> dict[str, Any]:
        """Normalize one outer transaction without touching PL/pgSQL or string contents."""

        source = str(sql)
        text = source.strip()
        masked = _mask_sql_noncode(text)

        open_match = re.match(
            r"\A\s*(?P<open>BEGIN(?:\s+(?:WORK|TRANSACTION))?|START\s+TRANSACTION)\s*;",
            masked,
            re.IGNORECASE,
        )
        close_match = re.search(
            r"(?P<close>COMMIT(?:\s+WORK)?)\s*;\s*\Z",
            masked,
            re.IGNORECASE,
        )

        repaired = bool(open_match and close_match and close_match.start("close") >= open_match.end("open"))
        if repaired:
            open_end = _semicolon_after(masked, open_match.end("open"))
            close_end = _semicolon_after(masked, close_match.end("close"))
            text = f"{text[:open_match.start('open')]}{text[open_end:close_match.start('close')]}{text[close_end:]}".strip()

        remaining_control = _TRANSACTION_CONTROL.search(_mask_sql_noncode(text))
        if remaining_control:
            raise ValueError("Migration enthält verschachtelte Top-Level-Transaktionssteuerung")

        return {
            "sql": text,
            "repair": {
                "family": "migration_preview_transaction_wrapper",
                "status": "APPLIED" if repaired else "NOT_NEEDED",
                "action": "normalize_one_outer_transaction_for_preview",
                "scope": "preview_only",
                "attempts": 1 if repaired else 0,
                "max_attempts": MAX_AUTOMATIC_REPAIR_ATTEMPTS,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "preview_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source_unchanged": True,
                "production_write_performed": False,
                "required_post_checks": ["preview_rollback", "source_sha256_unchanged"],
            },
        }


REPAIR_ENGINE = PolicyGuardedRepairEngine()
