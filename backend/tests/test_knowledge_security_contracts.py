from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEPLOY = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

# The isolated repository test host intentionally has no Flask/PostgreSQL runtime
# dependencies. Stub only import surfaces; tests below never execute HTTP or DB I/O.
flask_stub = ModuleType("flask")
flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
flask_stub.make_response = lambda value=None, *args, **kwargs: value
flask_stub.request = SimpleNamespace()
sys.modules.setdefault("flask", flask_stub)
psycopg2_stub = ModuleType("psycopg2")
psycopg2_extras_stub = ModuleType("psycopg2.extras")
psycopg2_stub.extras = psycopg2_extras_stub
sys.modules.setdefault("psycopg2", psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

import knowledge_library
import security_runtime
import vector_embedding

pattern_spec = importlib.util.spec_from_file_location(
    "pattern_vector_memory_contract",
    BACKEND / "agent_runtime" / "pattern_vector_memory.py",
)
assert pattern_spec and pattern_spec.loader
pattern_vector_memory = importlib.util.module_from_spec(pattern_spec)
pattern_spec.loader.exec_module(pattern_vector_memory)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backend_live_modules_are_exact_mirrors() -> None:
    for relative in (
        "vector_embedding.py",
        "knowledge_library.py",
        "are_inference.py",
        "security_runtime.py",
        "agent_runtime/pattern_vector_memory.py",
        "agent_runtime/pattern_gateway.py",
        "agent_runtime/routes.py",
    ):
        assert read(BACKEND / relative) == read(DEPLOY / relative), relative


def test_embedding_adapter_rejects_wrong_dimensions() -> None:
    payload = {"data": [{"embedding": [0.1, 0.2]}]}
    with pytest.raises(vector_embedding.EmbeddingUnavailable, match="expected 768"):
        vector_embedding._extract_vectors(payload)


def test_embedding_adapter_accepts_cloudflare_and_openai_shapes() -> None:
    vector = [0.001] * vector_embedding.EMBEDDING_DIMENSIONS
    cloudflare = vector_embedding._extract_vectors({"result": {"data": [vector]}})
    openai = vector_embedding._extract_vectors({"data": [{"embedding": vector}]})
    assert cloudflare == openai
    assert len(cloudflare[0]) == 768
    assert vector_embedding.vector_literal(cloudflare[0]).startswith("[")


def test_embedding_adapter_fails_closed_without_route(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "KNOWLEDGE_EMBEDDING_BASE_URL",
        "WORKER_AI_PROXY_URL",
        "WORKER_AI_PROXY_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(vector_embedding.EmbeddingUnavailable, match="no embedding route configured"):
        vector_embedding.embed_texts(["real vector required"])


def test_knowledge_chunking_is_stable_and_hash_deduplicable() -> None:
    text = "# C++ pointers\n\n" + ("Pointers store addresses. " * 260)
    first = knowledge_library.chunk_document(text)
    second = knowledge_library.chunk_document(text)
    assert len(first) >= 2
    assert [item.content_sha256 for item in first] == [item.content_sha256 for item in second]
    assert len({item.content_sha256 for item in first}) == len(first)
    assert all(len(item.content_sha256) == 64 for item in first)


def test_knowledge_url_allowlist_blocks_ssrf_and_plain_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        knowledge_library.fetch_url_document("http://127.0.0.1:8088/secret")
    with pytest.raises(ValueError, match="Allowed knowledge URL hosts"):
        knowledge_library.fetch_url_document("https://example.com/private")


def test_source_upload_classifies_code_without_executing_it() -> None:
    doc = knowledge_library.upload_document("example.cpp", b"int main(){ return 0; }")
    assert doc.source_type == "code"
    assert "int main" in doc.text


def test_security_context_hash_is_canonical_and_action_bound() -> None:
    left = security_runtime.canonical_context_hash(
        "credit_purchase", {"credits": 500, "priceEur": 2, "packageId": "a"}
    )
    reordered = security_runtime.canonical_context_hash(
        "credit_purchase", {"packageId": "a", "priceEur": 2, "credits": 500}
    )
    other_action = security_runtime.canonical_context_hash(
        "expensive_llm_route", {"packageId": "a", "priceEur": 2, "credits": 500}
    )
    assert left == reordered
    assert left != other_action
    assert len(left) == 64


def test_capacitor_passkeys_require_explicit_origin_and_rp_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPACITOR_PASSKEY_ORIGIN", "https://localhost")
    monkeypatch.delenv("CAPACITOR_PASSKEY_RP_ID", raising=False)
    with pytest.raises(security_runtime.SecurityRuntimeUnavailable, match="CAPACITOR_PASSKEY_RP_ID"):
        security_runtime._rp_id_for_origin("https://localhost")
    monkeypatch.setenv("CAPACITOR_PASSKEY_RP_ID", "localhost")
    assert security_runtime._rp_id_for_origin("https://localhost") == "localhost"
    assert security_runtime._rp_id_for_origin("https://chat.arelorian.de") == security_runtime.PASSKEY_RP_ID


def test_account_key_hash_requires_server_pepper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCOUNT_KEY_PEPPER", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(security_runtime.SecurityRuntimeUnavailable):
        security_runtime._secret_hash("svk_example")
    monkeypatch.setenv("ACCOUNT_KEY_PEPPER", "test-only-pepper")
    assert security_runtime._secret_hash("svk_example") != "svk_example"
    assert len(security_runtime._secret_hash("svk_example")) == 64


def test_experience_vector_text_contains_evidence_not_raw_secrets() -> None:
    result = SimpleNamespace(payload={
        "kind": "solution",
        "mission": "Fix compiler error",
        "changedFiles": ["src/main.cpp"],
        "diffSummary": "Use std::unique_ptr",
        "testSummary": "ctest passed",
        "blocker": "",
    })
    text = pattern_vector_memory.pattern_text(result)
    assert "Fix compiler error" in text
    assert "ctest passed" in text


def test_migration_and_image_build_contain_live_contracts() -> None:
    migration = read(DEPLOY / "migrations/008_knowledge_memory_passkeys_stepup.sql")
    are_migration = read(DEPLOY / "migrations/009_are_inference_quarantine.sql")
    dockerfile = read(DEPLOY / "Dockerfile")
    requirements = read(DEPLOY / "requirements.txt")
    workflow = read(ROOT / ".github/workflows/sovereign-backend-image.yml")
    ci_workflow = read(ROOT / ".github/workflows/ci.yml")

    assert "knowledge_blocks" in migration
    assert "embedding vector(768)" in migration
    assert "user_passkeys" in migration
    assert "step_up_approvals" in migration
    assert "USING hnsw" in migration
    assert "are_learning_quarantine" in are_migration
    assert "UNIQUE (user_id, content_sha256)" in are_migration
    assert "COPY security_runtime.py" in dockerfile
    assert "COPY knowledge_library.py" in dockerfile
    assert "COPY are_inference.py" in dockerfile
    assert "webauthn>=2.7.0,<3" in requirements
    assert "pypdf>=5.0.0,<6" in requirements
    assert "requests>=2.31.0" in requirements
    assert "security_runtime.py" in workflow
    assert "are_inference.py" in workflow
    assert "python -m pip install -r scripts/sovereign-backend/requirements.txt pytest -q" in ci_workflow


def test_pnpm_action_setup_uses_package_manager_as_single_version_source() -> None:
    workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    duplicate_version = re.compile(
        r"uses:\s*pnpm/action-setup@v4\s*\n\s+with:\s*\n(?:\s+[^\n]+\n)*?\s+version:",
        re.MULTILINE,
    )
    for workflow_path in workflows:
        source = read(workflow_path)
        assert "PNPM_VERSION: 10" not in source, workflow_path.name
        assert "PNPM_VERSION: \"10\"" not in source, workflow_path.name
        assert not duplicate_version.search(source), workflow_path.name


def test_payment_and_credit_security_are_server_authoritative() -> None:
    for path in (BACKEND / "app.py", DEPLOY / "app.py"):
        source = read(path)
        assert '@app.route("/api/billing/purchase/google-play/validate", methods=["POST"])\n@require_session\ndef google_play_validate' in source
        assert "user_id        = request.session_user_id" in source
        assert "_authorize_credit_purchase" in source
        assert '"error": "Account mismatch"' in source
        assert '"error": "unknown_cost_id"' in source
        assert "SELECT credits FROM admin_users" in source
        assert "X-Step-Up-Token" in source


def test_frontend_surfaces_and_runtime_consumption_exist() -> None:
    profile = read(ROOT / "src/features/user/components/UserProfile.tsx")
    builder = read(ROOT / "src/features/product/containers/BuilderContainer.tsx")
    billing = read(ROOT / "src/features/billing/billingSlice.ts")
    guard = read(ROOT / "src/features/billing/useCreditGuard.ts")
    login = read(ROOT / "src/features/user/components/LoginModal.tsx")

    assert "KnowledgeLibraryPanel" in profile
    assert "SecuritySettingsPanel" in profile
    assert "evaluateAreInference" in builder
    assert "referenceKnowledgeContext = areInferenceResult.knowledgeContext" in builder
    assert "experiencePatternContext = areInferenceResult.experienceContext" in builder
    assert "quarantineOnlineAnswer" in builder
    assert "const workerHealthForInference = await fetchDevChatWorkerHealth()" in builder
    assert "repositoryRevision: chatRepoSnapshot?.treeSha" in builder
    assert "files: chatRepoSnapshot?.files ?? []" in builder
    assert "const _canProceed = await chargeCredits(d.modelId" in builder
    assert "if (fullText && !streamError && !streamDiagnostic)" in builder
    assert "await quarantineOnlineAnswer" in builder
    assert "Der Auftrag wurde vor Credit-Abzug und Online-Call gestoppt" in builder
    assert "fetchWithStepUp" in billing
    assert "fetchWithStepUp" in guard
    assert "Mit Passkey anmelden" in login
    assert "Mit Account Key anmelden" in login
