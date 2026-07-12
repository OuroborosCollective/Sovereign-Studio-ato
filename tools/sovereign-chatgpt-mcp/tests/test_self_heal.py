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


def test_unknown_failure_remains_fail_closed() -> None:
    result = REPAIR_ENGINE.diagnose("completely new failure signature")

    assert result["status"] == "UNKNOWN"
    assert result["policy"]["auto_repairable"] is False
    assert result["max_automatic_attempts"] == 0
