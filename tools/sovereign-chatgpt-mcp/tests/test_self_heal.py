from __future__ import annotations

import pytest

from self_heal import REPAIR_ENGINE


def test_preview_normalization_accepts_plpgsql_begin_inside_dollar_quote() -> None:
    sql = """-- additive migration
BEGIN;
CREATE TABLE IF NOT EXISTS llm_routes(id integer, model_id text, model text);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE column_name = 'model') THEN
        EXECUTE 'UPDATE llm_routes SET model_id = COALESCE(model_id, model) WHERE model_id IS NULL';
    END IF;
END $$;
COMMIT;
"""

    result = REPAIR_ENGINE.normalize_migration_preview(sql)

    assert result["repair"]["status"] == "APPLIED"
    assert result["repair"]["scope"] == "preview_only"
    assert result["repair"]["source_unchanged"] is True
    assert result["repair"]["production_write_performed"] is False
    assert "DO $$" in result["sql"]
    assert "END $$;" in result["sql"]
    assert not result["sql"].lstrip().upper().startswith("BEGIN;")
    assert not result["sql"].rstrip().upper().endswith("COMMIT;")


def test_preview_normalization_ignores_transaction_words_in_strings_and_comments() -> None:
    sql = """BEGIN;
-- BEGIN; COMMIT;
SELECT 'BEGIN; COMMIT;' AS example;
DO $body$
BEGIN
    RAISE NOTICE 'ROLLBACK;';
END
$body$;
COMMIT;
"""

    result = REPAIR_ENGINE.normalize_migration_preview(sql)

    assert result["repair"]["status"] == "APPLIED"
    assert "RAISE NOTICE" in result["sql"]


def test_preview_normalization_blocks_real_nested_top_level_transaction() -> None:
    sql = """BEGIN;
CREATE TABLE first_table(id integer);
COMMIT;
BEGIN;
CREATE TABLE second_table(id integer);
COMMIT;
"""

    with pytest.raises(ValueError, match="Top-Level-Transaktionssteuerung"):
        REPAIR_ENGINE.normalize_migration_preview(sql)


def test_failure_diagnosis_routes_event_contract_to_draft_pr_only() -> None:
    result = REPAIR_ENGINE.diagnose("SovereignAgentEvent' object has no attribute 'get'")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "event_mapping_contract"
    assert result["policy"]["auto_repairable"] is False
    assert result["policy"]["mutation_scope"] == "draft_pr_only"
    assert "direct_main_write" in result["policy"]["blocked_capabilities"]
    assert "auto_merge" in result["policy"]["blocked_capabilities"]


def test_failure_diagnosis_allows_only_preview_scoped_transaction_repair() -> None:
    result = REPAIR_ENGINE.diagnose("Migration enthält verschachtelte Transaktionssteuerung")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "migration_preview_transaction_wrapper"
    assert result["policy"]["auto_repairable"] is True
    assert result["policy"]["mutation_scope"] == "preview_only"
    assert result["max_automatic_attempts"] == 2


def test_failure_diagnosis_routes_queue_timeout_to_status_without_resubmit() -> None:
    result = REPAIR_ENGINE.diagnose("failure_family=HOST_COMMAND_STILL_RUNNING")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "host_command_queue_contract"
    assert result["policy"]["repair_action"] == (
        "read_existing_job_status_and_inspect_host_worker_without_resubmitting"
    )
    assert "target_state_verified_before_retry" in result["policy"]["required_post_checks"]


def test_failure_diagnosis_distinguishes_broker_namespace_visibility() -> None:
    result = REPAIR_ENGINE.diagnose(
        "failure_family=BROKER_SOCKET_PATH_ABSENT Broker-Socket ist in diesem Runtime-Namespace nicht vorhanden"
    )

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "broker_socket_namespace_visibility"
    assert result["policy"]["repair_action"] == "compare_host_and_container_socket_then_recreate_only_stale_mount"
    assert "container_socket_is_unix_socket" in result["policy"]["required_post_checks"]


def test_failure_diagnosis_routes_local_node_work_to_github_actions() -> None:
    result = REPAIR_ENGINE.diagnose("status=REMOTE_CI_REQUIRED failure_family=LOCAL_DEPENDENCY_INSTALL_FORBIDDEN")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "external_node_build_boundary"
    assert result["policy"]["mutation_scope"] == "github_actions_only"
    assert result["policy"]["repair_action"] == (
        "publish_remote_ref_and_use_github_actions_without_local_retry"
    )


def test_failure_diagnosis_distinguishes_dependency_process_kill() -> None:
    result = REPAIR_ENGINE.diagnose(
        'pnpm install --frozen-lockfile returned {"exit_code": -9}; Cannot find module typescript/bin/tsc'
    )

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "dependency_install_process_killed"
    assert result["policy"]["mutation_scope"] == "isolated_workspace"


def test_failure_diagnosis_distinguishes_incomplete_dependency_resolution() -> None:
    result = REPAIR_ENGINE.diagnose("Cannot find module 'typescript/bin/tsc'")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "dependency_resolution_incomplete"
    assert result["policy"]["repair_action"] == "verify_lockfile_install_completion_then_resolve_required_executables"


def test_failure_diagnosis_routes_exact_repeated_mcp_400_logs_without_node_repair() -> None:
    result = REPAIR_ENGINE.diagnose(
        'INFO: 172.16.1.1:50424 - "POST /mcp HTTP/1.1" 400 Bad Request\nTerminating session: None'
    )

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "mcp_streamable_http_request_contract"
    assert result["policy"]["repair_action"] == (
        "identify_calling_client_then_replace_malformed_probe_without_touching_node_or_broker"
    )
    assert "no_repeated_400_window" in result["policy"]["required_post_checks"]


def test_failure_diagnosis_routes_tunnel_400_to_protocol_probe_repair() -> None:
    result = REPAIR_ENGINE.diagnose("MCP initialize returned HTTP 400 during tunnel-healthcheck")

    assert result["status"] == "DETECTED"
    assert result["policy"]["family"] == "tunnel_mcp_initialize_contract"
    assert "mcp_initialize_handshake" in result["policy"]["required_post_checks"]


def test_unknown_failure_remains_fail_closed() -> None:
    result = REPAIR_ENGINE.diagnose("completely new failure signature")

    assert result["status"] == "UNKNOWN"
    assert result["policy"]["auto_repairable"] is False
    assert result["max_automatic_attempts"] == 0
