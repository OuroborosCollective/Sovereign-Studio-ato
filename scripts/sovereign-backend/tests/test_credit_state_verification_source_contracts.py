from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_SOURCE = REPO_ROOT / "scripts" / "sovereign-backend" / "app.py"
MIGRATION = (
    REPO_ROOT
    / "scripts"
    / "sovereign-backend"
    / "migrations"
    / "011_credit_state_verification.sql"
)


def _source() -> str:
    return BACKEND_SOURCE.read_text(encoding="utf-8")


def test_user_creation_persists_signup_credit_evidence_atomically() -> None:
    source = _source()
    assert "def _create_user_with_initial_credits" in source
    assert source.count("_create_user_with_initial_credits(") >= 4
    helper = source[source.index("def _create_user_with_initial_credits"):]
    assert "'signup_bonus'" in helper
    assert 'f"account-create:{user_id}"' in helper
    assert "conn.commit()" in helper
    assert "conn.rollback()" in helper


def test_credit_transition_verifies_ledger_cache_before_mutation() -> None:
    source = _source()
    start = source.index("def _apply_credit_delta")
    end = source.index("def _add_credits_and_log", start)
    helper = source[start:end]
    assert "FOR UPDATE" in helper
    assert "COALESCE(SUM(amount), 0)::integer AS balance" in helper
    assert "ledger_balance != cached_balance" in helper
    assert "CreditStateConflict" in helper
    assert "INSERT INTO credit_ledger" in helper
    assert "UPDATE admin_users" in helper
    assert "SET credits = %s" in helper
    assert "conn.commit()" in helper
    assert "conn.rollback()" in helper


def test_provider_receipt_is_unique_evidence_for_confirmed_purchase() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS credit_receipts" in migration
    assert "PRIMARY KEY (provider, provider_tx_id)" in migration
    source = _source()
    assert "INSERT INTO credit_receipts" in source
    assert "WHERE provider = %s AND provider_tx_id = %s" in source
    assert 'provider="crypto"' in source
    assert '"paypal",\n            capture_id,' in source
    assert '"skrill",\n            transaction_id,' in source
    assert '"google_play",\n            token_fingerprint,' in source


def test_usage_deduction_has_no_best_effort_log_after_cache_write() -> None:
    source = _source()
    assert "INSERT INTO credit_usage" not in source
    route_start = source.index("def user_billing_deduct")
    route_end = source.index("# ═", route_start)
    route = source[route_start:route_end]
    assert "_apply_credit_delta(" in route
    assert "-amount" in route
    assert 'ledger_type="usage"' in route
    assert '"ledgerType": "usage"' in route
    assert "credit_state_verification_failed" in route


def test_existing_cache_is_reconciled_to_append_only_ledger_once() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "COALESCE(SUM(amount), 0)::INTEGER AS balance" in migration
    assert "account.credits - COALESCE(ledger.balance, 0) AS delta" in migration
    assert "'balance_reconciliation'" in migration
    assert "WHERE delta <> 0" in migration


def test_admin_adjustment_audit_shares_credit_transaction() -> None:
    source = _source()
    assert 'audit_action="admin_credit_adjustment"' in source
    helper_start = source.index("def _apply_credit_delta")
    helper_end = source.index("def _add_credits_and_log", helper_start)
    helper = source[helper_start:helper_end]
    assert "INSERT INTO audit_log" in helper
    assert '"newBalance": new_balance' in helper


def test_credit_reads_verify_cache_and_ledger_in_one_query() -> None:
    source = _source()
    start = source.index("def _read_verified_credit_balance")
    end = source.index("class CreditStateConflict", start)
    helper = source[start:end]
    assert "LEFT JOIN credit_ledger" in helper
    assert "cached_balance" in helper
    assert "ledger_balance" in helper
    assert "cached_balance != ledger_balance" in helper
    assert "return 0" not in helper


def test_user_and_billing_responses_require_verified_credit_state() -> None:
    source = _source()
    user_start = source.index("def _user_row_to_dict")
    user_end = source.index("def _set_session_cookie", user_start)
    user_contract = source[user_start:user_end]
    assert "_read_verified_credit_balance(user_id)" in user_contract
    assert '"creditStateVerified": True' in user_contract

    route_start = source.index("def user_billing_credits")
    route_end = source.index("@app.route(\"/api/billing/deduct\"", route_start)
    route = source[route_start:route_end]
    assert "_read_verified_credit_balance(user_id)" in route
    assert '"creditStateVerified": False' in route
    assert '"blocker": "credit_state_verification_failed"' in route


def test_llm_route_selection_uses_verified_credit_state_when_present() -> None:
    source = _source()
    route_start = source.index("def public_llm_auto_route")
    route_end = source.index("def public_llm_chat", route_start)
    route = source[route_start:route_end]
    assert "user_id = request.session_user_id" in route
    assert "_read_verified_credit_balance(user_id)" in route
    assert '"blocker": "credit_state_verification_failed"' in route
    assert "SELECT id, credits FROM admin_users" not in route
