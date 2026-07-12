from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEPLOY = ROOT / "scripts" / "sovereign-backend"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_write_queries_preserve_returning_evidence_in_both_backend_mirrors() -> None:
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert "elif cur.description is not None:" in source
        assert "if write:\n                conn.commit()\n            return result" in source
        assert "if write:\n                conn.commit()\n                return None" not in source


def test_credit_package_price_contract_is_camel_case_and_reload_verified() -> None:
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert 'price_eur::float AS "priceEur"' in source
        assert 'body["priceEur"] = round(float(body["priceEur"]), 2)' in source
        assert '"persisted": True' in source
        assert "priceEur: parseFloat(document.getElementById('pp_'+id).value)" in source
        assert "Reload-Verifikation fehlgeschlagen" in source
        assert "parseFloat(p.price_eur)" not in source
        assert "price_eur: parseFloat(document.getElementById('pp_'+id).value)" not in source


def test_admin_loads_are_bounded_while_long_knowledge_jobs_keep_runtime_truth() -> None:
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert "boundedFetch(path, options={}, timeoutMs=15000)" in source
        assert "timeoutMs>0?setTimeout(()=>controller.abort(),timeoutMs):null" in source
        assert "Backend-Zeitüberschreitung nach '+Math.ceil(timeoutMs/1000)+' Sekunden." in source
        assert "boundedFetch('/api/admin/users" in source
        assert "boundedFetch(url.replace(BASE,''),{headers:hdr()})" in source
        assert "Erneut laden" in source
        assert "Quelle wird geladen, geparst, gechunkt und eingebettet" in source
        assert "Datei wird geladen, geparst, gechunkt und eingebettet" in source
        assert "knowledge/sources/url',{method:'POST',headers:hdr(),body:JSON.stringify({url})},0" in source
        assert "knowledge/sources/upload',{method:'POST',headers:formHdr(),body:form},0" in source
        assert "knowledge/search',{method:'POST',headers:hdr(),body:JSON.stringify({query,limit:8})},120000" in source


def test_admin_knowledge_and_pdf_live_path_is_registered_and_visible() -> None:
    for path in (BACKEND / "knowledge_library.py", DEPLOY / "knowledge_library.py"):
        source = read(path)
        assert "def register_admin_knowledge_routes(" in source
        assert '"/api/admin/knowledge/sources/upload"' in source
        assert "upload_document(uploaded.filename" in source
        assert '"/api/admin/knowledge/search"' in source
        assert '"/api/admin/knowledge/repair"' in source
        assert "repair_missing_knowledge_embeddings" in source
        assert "max_batches = max(1, min" in source
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert "register_admin_knowledge_routes(" in source
        assert "Wissensdatenbank & PDF-Einspeisung" in source
        assert "uploadKnowledgeFileAdmin" in source
        assert "repairKnowledgeEmbeddingsAdmin" in source
        assert "Fehlende Vektoren reparieren" in source
        assert "'/api/admin/knowledge/repair'" in source
        assert "formHdr()" in source


def test_transaction_schema_matches_admin_reader_and_writer() -> None:
    migration = read(DEPLOY / "migrations/010_admin_billing_runtime_contracts.sql")
    assert "CREATE TABLE IF NOT EXISTS transactions" in migration
    assert "ADD COLUMN IF NOT EXISTS user_email" in migration
    assert "ALTER COLUMN user_email SET NOT NULL" in migration
    assert "transactions_user_id_fkey" in migration
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert 'user_email AS "userEmail"' in source
        assert "INSERT INTO transactions" in source


def test_credit_package_list_errors_are_not_false_empty_successes() -> None:
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert '"runtimeState": "failed"}), 500' in source


def test_backend_deploy_remote_shell_is_posix_safe() -> None:
    workflow = read(ROOT / ".github/workflows/sovereign-agent-backend.yml")
    assert "capture_stdout: true" not in workflow
    assert "set -euo pipefail\n            RELEASE_DIR=" not in workflow
    assert workflow.count("script: |\n            set -eu") >= 3
