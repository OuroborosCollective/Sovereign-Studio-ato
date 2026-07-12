from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_COPIES = (
    REPO_ROOT / "scripts" / "sovereign-backend" / "app.py",
    REPO_ROOT / "backend" / "app.py",
)


def _backend_sources() -> tuple[str, str]:
    return tuple(path.read_text(encoding="utf-8") for path in BACKEND_COPIES)


def test_backend_copies_fail_closed_without_default_jwt_secret() -> None:
    for source in _backend_sources():
        assert 'JWT_SECRET = os.getenv("JWT_SECRET", "").strip()' in source
        assert 'supersecretkey-change-me' not in source
        assert 'raise RuntimeError("JWT_SECRET ist nicht konfiguriert")' in source


def test_github_oauth_requires_state_pkce_and_real_callback() -> None:
    for source in _backend_sources():
        assert 'https://chat.arelorian.de/auth/github/callback.html' in source
        assert 'if not state or not code_verifier:' in source
        assert 'GitHub OAuth benötigt State und PKCE-Verifier' in source
        assert 'if not _validate_pkce(code_verifier, stored_challenge):' in source


def test_admin_browser_session_does_not_persist_admin_key() -> None:
    for source in _backend_sources():
        assert "sessionStorage.getItem('sov_admin_key')" not in source
        assert "sessionStorage.setItem('sov_admin_key'" not in source
        assert "sessionStorage.removeItem('sov_admin_key')" not in source
        assert "const r = await fetch(BASE+'/api/admin/ping'" in source
        assert "data.ok!==true || !data.id" in source


def test_payment_webhooks_require_verification_and_replay_guards() -> None:
    for source in _backend_sources():
        assert "def _verify_paypal_webhook_signature" in source
        assert 'Ungültige PayPal Webhook-Signatur' in source
        assert 'PayPal Betrag oder Währung stimmt nicht mit dem Paket überein' in source
        assert 'SKRILL_VERIFICATION_NOT_CONFIGURED' in source
        assert 'hmac.compare_digest(expected_sig, received_sig)' in source
        assert 'CREATE TABLE IF NOT EXISTS credit_receipts' not in source
        assert 'INSERT INTO credit_receipts' in source
        assert 'WHERE provider = %s AND provider_tx_id = %s' in source
        assert 'token_fingerprint = hashlib.sha256(purchase_token.encode()).hexdigest()' in source


def test_credit_grant_and_transaction_log_share_one_database_transaction() -> None:
    for source in _backend_sources():
        helper_start = source.index("def _apply_credit_delta")
        helper_end = source.index("def _add_credits_and_log", helper_start)
        helper = source[helper_start:helper_end]
        assert "pool = get_pool()" in helper
        assert "conn.commit()" in helper
        assert "conn.rollback()" in helper
        assert "FOR UPDATE" in helper
        assert "INSERT INTO credit_ledger" in helper
        assert "UPDATE admin_users SET credits = %s" in helper
        assert "INSERT INTO transactions" in helper


def test_backend_error_states_are_not_empty_http_200_successes() -> None:
    for source in _backend_sources():
        assert '"paymentMethods": [], "error": str(exc), "runtimeState": "failed"}), 500' in source
        assert '"methods": [], "error": str(exc), "runtimeState": "failed"}), 500' in source
        assert 'return jsonify({"error": str(exc), "runtimeState": "failed"}), 500' in source
        assert 'return jsonify({"credits": 0, "error": str(exc)' not in source
        assert '"ok": health_status == "healthy"' in source
