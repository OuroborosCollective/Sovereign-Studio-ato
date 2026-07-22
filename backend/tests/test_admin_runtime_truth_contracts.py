from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "sovereign-backend"
CANONICAL_APP = DEPLOY / "app.py"
ADMIN_CLIENT = ROOT / "src" / "features" / "admin" / "api" / "adminApiClient.ts"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_write_queries_preserve_returning_evidence_in_canonical_backend() -> None:
    for path in (CANONICAL_APP,):
        source = read(path)
        assert "elif cur.description is not None:" in source
        assert "if write:\n                conn.commit()\n            return result" in source
        assert "if write:\n                conn.commit()\n                return None" not in source


def test_credit_package_price_contract_is_camel_case_across_backend_and_react_client() -> None:
    source = read(CANONICAL_APP)
    client = read(ADMIN_CLIENT)
    assert 'price_eur::float AS "priceEur"' in source
    assert 'body["priceEur"] = round(float(body["priceEur"]), 2)' in source
    assert '"persisted": True' in source
    assert "priceEur: number;" in client
    assert "'priceEur'" in client
    assert "price_eur" not in client


def test_admin_loads_are_bounded_while_long_provider_operations_get_explicit_limits() -> None:
    client = read(ADMIN_CLIENT)
    assert "timeoutMs = 15_000" in client
    assert "const controller = new AbortController();" in client
    assert "controller.abort()" in client
    assert "Backend-Zeitüberschreitung nach ${Math.ceil(timeoutMs / 1000)} Sekunden." in client
    assert "discoverFreeRevolverProvider" in client
    assert client.count("}, 180_000);") >= 2
    assert "credentials: 'omit'" in client
    assert "cache: 'no-store'" in client


def test_admin_knowledge_and_pdf_live_path_is_registered_in_canonical_backend() -> None:
    source = read(DEPLOY / "knowledge_library.py")
    app = read(CANONICAL_APP)
    assert "def register_admin_knowledge_routes(" in source
    assert '"/api/admin/knowledge/sources/upload"' in source
    assert 'filename = uploaded.filename or "upload.txt"' in source
    assert "payload = uploaded.stream.read(_upload_limit_bytes(filename) + 1)" in source
    assert "document = upload_document(filename, payload)" in source
    assert '"/api/admin/knowledge/search"' in source
    assert '"/api/admin/knowledge/repair"' in source
    assert "repair_missing_knowledge_embeddings" in source
    assert "max_batches = max(1, min" in source
    assert "register_admin_knowledge_routes(" in app


def test_transaction_schema_matches_admin_reader_and_writer() -> None:
    migration = read(DEPLOY / "migrations/010_admin_billing_runtime_contracts.sql")
    assert "CREATE TABLE IF NOT EXISTS transactions" in migration
    assert "ADD COLUMN IF NOT EXISTS user_email" in migration
    assert "ALTER COLUMN user_email SET NOT NULL" in migration
    assert "transactions_user_id_fkey" in migration
    for path in (CANONICAL_APP,):
        source = read(path)
        assert 'user_email AS "userEmail"' in source
        assert "INSERT INTO transactions" in source


def test_credit_package_list_errors_are_not_false_empty_successes() -> None:
    for path in (CANONICAL_APP,):
        source = read(path)
        assert '"runtimeState": "failed"}), 500' in source


def test_backend_release_is_validation_only_and_queue_bound() -> None:
    workflow = read(ROOT / ".github/workflows/sovereign-agent-backend.yml")
    assert "Queue-only Release Policy" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "Validation-only boundary verified" in workflow
    assert "production release requires the Sovereign host-command queue" in workflow
    assert "capture_stdout: true" not in workflow
    for forbidden in ("apple" + "boy/", "ssh-" + "action", "scp-" + "action", "docker " + "build", "docker " + "run"):
        assert forbidden not in workflow
