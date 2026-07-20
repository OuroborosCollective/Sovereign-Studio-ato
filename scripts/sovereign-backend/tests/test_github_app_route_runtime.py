from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import types

flask_stub = types.ModuleType("flask")
flask_stub.jsonify = lambda payload: payload
flask_stub.request = types.SimpleNamespace(headers={}, args={}, get_data=lambda: b"", get_json=lambda: {})
flask_stub.Response = object
sys.modules.setdefault("flask", flask_stub)

jwt_stub = types.ModuleType("jwt")
jwt_stub.encode = lambda *_args, **_kwargs: "stub-jwt"
sys.modules.setdefault("jwt", jwt_stub)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import github_app


class FakeApp:
    def __init__(self):
        self.rules: set[str] = set()
        self.handlers: dict[str, object] = {}

    def route(self, rule, **_kwargs):
        def decorator(function):
            self.rules.add(rule)
            self.handlers[rule] = function
            return function
        return decorator


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows) if isinstance(rows, list) else [rows]
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()):
        self.executed.append((" ".join(statement.split()), tuple(params)))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class Connection:
    def __init__(self, rows):
        self.cursor_instance = Cursor(rows)
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_app_injects_real_pooled_connection_factory() -> None:
    source = (BACKEND_ROOT / "app.py").read_text("utf-8")
    registration = source.split("register_github_app_routes(", 1)[1].split(")", 1)[0]

    assert "get_connection=get_agent_runtime_connection" in registration
    assert "get_connection=get_connection" not in registration
    assert 'raise RuntimeError("GitHub App route registration failed")' in source
    assert "GitHub App routes registration failed" not in source


def test_routes_register_without_database_access() -> None:
    app = FakeApp()

    def require_admin(function):
        return function

    github_app.register_github_app_routes(
        app,
        require_admin=require_admin,
        get_connection=lambda: Connection(None),
    )

    assert "/api/webhooks/github-app" in app.rules
    assert "/api/github-app/installations" in app.rules
    assert "/api/github-app/installations/<int:installation_id>/credits" in app.rules


def test_callback_never_claims_unperformed_oauth_exchange() -> None:
    app = FakeApp()
    github_app.register_github_app_routes(
        app,
        require_admin=lambda function: function,
        get_connection=lambda: Connection(None),
    )
    callback = app.handlers["/api/auth/github-app/callback"]

    github_app.request.args = {"code": "unexchanged-code"}
    payload, status = callback()
    assert status == 501
    assert payload["ok"] is False
    assert payload["blocker"] == "github_app_oauth_exchange_unavailable"
    assert payload["authenticationEstablished"] is False

    github_app.request.args = {"setup_action": "install", "installation_id": "42"}
    payload = callback()
    assert payload["status"] == "installation_redirect_received"
    assert payload["installation_id"] == 42
    assert payload["authenticationEstablished"] is False


def test_credit_readback_supports_real_dict_rows_and_closes_transaction() -> None:
    updated_at = datetime(2026, 7, 21, tzinfo=timezone.utc)
    connection = Connection({
        "installation_id": 42,
        "account_login": "OuroborosCollective",
        "credits": 17,
        "plan": "pro",
        "status": "active",
        "updated_at": updated_at,
    })

    result = github_app.get_installation_credits(42, lambda: connection)

    assert result is not None
    assert result.installation_id == 42
    assert result.account_login == "OuroborosCollective"
    assert result.credits == 17
    assert result.plan == "pro"
    assert result.status == "active"
    assert result.updated_at == updated_at
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_insufficient_credit_path_rolls_back_mapping_cursor_transaction() -> None:
    connection = Connection([None, {"credits": 2}])

    result = github_app.deduct_credits(
        installation_id=42,
        amount=3,
        action="analysis",
        idempotency_key="11111111-1111-4111-8111-111111111111",
        get_connection=lambda: connection,
    )

    assert result == {"ok": False, "duplicate": False, "remainingCredits": 2}
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_credit_deduction_is_idempotent_and_mapping_safe() -> None:
    first = Connection([None, {"credits": 5, "status": "active"}])
    request_id = "22222222-2222-4222-8222-222222222222"

    created = github_app.deduct_credits(
        installation_id=42,
        amount=3,
        action="analysis",
        idempotency_key=request_id,
        get_connection=lambda: first,
    )

    assert created == {"ok": True, "duplicate": False, "remainingCredits": 2}
    assert "pg_advisory_xact_lock" in first.cursor_instance.executed[0][0]
    assert first.cursor_instance.executed[0][1] == (
        f"github-app-credit:{request_id}",
    )
    assert first.commits == 1
    assert first.rollbacks == 0
    assert first.closed == 1

    duplicate = Connection([{
        "installation_id": 42,
        "amount": -3,
        "action": "analysis",
    }])
    replayed = github_app.deduct_credits(
        installation_id=42,
        amount=3,
        action="analysis",
        idempotency_key=request_id,
        get_connection=lambda: duplicate,
    )

    assert replayed == {"ok": True, "duplicate": True, "remainingCredits": None}
    assert duplicate.commits == 0
    assert duplicate.rollbacks == 1
    assert duplicate.closed == 1


def test_marketplace_event_never_invents_an_installation_id() -> None:
    connection = Connection([None])

    result = github_app.handle_marketplace_purchase(
        action="purchased",
        marketplace_purchase={
            "account": {"id": 9001, "login": "OuroborosCollective"},
            "plan": {"name": "pro"},
            "unit_count": 1,
        },
        get_connection=lambda: connection,
    )

    assert result["ok"] is False
    assert result["action"] == "installation_required"
    assert result["account_id"] == 9001
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_github_app_credit_schema_is_versioned_and_idempotent() -> None:
    migration = (
        BACKEND_ROOT / "migrations" / "029_github_app_credit_runtime.sql"
    ).read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS github_app_credits" in migration
    assert "account_id BIGINT" in migration
    assert "status TEXT NOT NULL DEFAULT 'active'" in migration
    assert "CREATE TABLE IF NOT EXISTS github_app_credit_transactions" in migration
    assert "idempotency_key UUID NOT NULL UNIQUE" in migration
    assert "REFERENCES github_app_credits(installation_id) ON DELETE CASCADE" in migration


def test_suspension_is_persisted_and_blocks_credit_use() -> None:
    suspended = Connection([{"installation_id": 42}])
    result = github_app.handle_installation_event(
        action="suspended",
        installation={"id": 42, "account": {"id": 9001, "login": "OuroborosCollective"}},
        get_connection=lambda: suspended,
    )
    assert result["ok"] is True
    assert result["status"] == "suspended"
    assert suspended.commits == 1
    assert suspended.closed == 1

    blocked = Connection([None, {"credits": 10, "status": "suspended"}])
    deduction = github_app.deduct_credits(
        installation_id=42,
        amount=1,
        action="analysis",
        idempotency_key="33333333-3333-4333-8333-333333333333",
        get_connection=lambda: blocked,
    )
    assert deduction == {"ok": False, "duplicate": False, "remainingCredits": 10}
    assert blocked.commits == 0
    assert blocked.rollbacks == 1


def test_configured_status_requires_all_secret_families() -> None:
    app = FakeApp()
    github_app.register_github_app_routes(
        app,
        require_admin=lambda function: function,
        get_connection=lambda: Connection(None),
    )
    payload = app.handlers["/api/github-app/configured"]()
    assert payload["configured"] is False
    assert payload["apiConfigured"] is False
    assert payload["oauthConfigured"] is False
    assert payload["webhookConfigured"] is False
