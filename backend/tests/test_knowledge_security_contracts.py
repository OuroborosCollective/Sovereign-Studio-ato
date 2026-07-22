from __future__ import annotations

import importlib.util
from pathlib import Path
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


def test_embedding_adapter_fails_closed_when_default_route_is_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "KNOWLEDGE_EMBEDDING_BASE_URL",
        "WORKER_AI_PROXY_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WORKER_AI_PROXY_URL", "")
    with pytest.raises(vector_embedding.EmbeddingUnavailable, match="no embedding route configured"):
        vector_embedding.embed_texts(["real vector required"])


def test_embedding_adapter_uses_sovereign_worker_default_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "KNOWLEDGE_EMBEDDING_BASE_URL",
        "WORKER_AI_PROXY_URL",
        "WORKER_AI_PROXY_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    calls: list[dict[str, object]] = []

    class Response:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": [
                    {
                        "embedding": [0.001] * vector_embedding.EMBEDDING_DIMENSIONS,
                    }
                ]
            }

    def post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(vector_embedding.requests, "post", post)
    batch = vector_embedding.embed_texts(["real knowledge"])

    assert batch.provider == "embedding-proxy"
    assert len(batch.vectors) == 1
    assert len(batch.vectors[0]) == 768
    assert calls[0]["url"] == (
        "https://sovereign-llm-proxy.projectouroboroscollective.workers.dev/v1/embeddings"
    )
    assert calls[0]["json"] == {
        "model": "@cf/google/embeddinggemma-300m",
        "input": ["real knowledge"],
    }


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


def test_github_import_failure_returns_auditable_non_secret_correlation() -> None:
    recorded: list[tuple[str, str | None, dict[str, object]]] = []
    source_url = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
    error = knowledge_library.GitHubKnowledgeAccessError(
        "credentials rejected",
        blocker="github_credentials_rejected",
        github_status=403,
        response_status=409,
    )

    correlation_id, audit_recorded = knowledge_library._record_github_import_failure(
        lambda action, target, changes: recorded.append((action, target, changes)),
        source_url,
        error,
    )

    assert str(knowledge_library.uuid.UUID(correlation_id)) == correlation_id
    assert audit_recorded is True
    assert recorded[0][0] == "knowledge:github_import_failed"
    assert recorded[0][1] != source_url
    assert recorded[0][1].startswith("github:")
    assert recorded[0][2]["blocker"] == "github_credentials_rejected"
    assert recorded[0][2]["githubHttpStatus"] == 403
    assert recorded[0][2]["correlationId"] == correlation_id


def test_github_import_failure_marks_missing_audit_without_hiding_blocker() -> None:
    error = knowledge_library.GitHubKnowledgeAccessError(
        "rate limited",
        blocker="github_rate_limit_exhausted",
        github_status=403,
        response_status=429,
    )

    correlation_id, audit_recorded = knowledge_library._record_github_import_failure(
        None,
        "https://github.com/example/private",
        error,
    )

    assert str(knowledge_library.uuid.UUID(correlation_id)) == correlation_id
    assert audit_recorded is False


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


def test_worker_exposes_real_openai_compatible_embedding_contract() -> None:
    worker = read(ROOT / "cloudflare-worker-ai-proxy" / "src" / "index.ts")
    backend_adapter = read(DEPLOY / "vector_embedding.py")

    assert "DEFAULT_WORKER_AI_PROXY_URL" in backend_adapter
    assert "configured_worker = os.getenv(\"WORKER_AI_PROXY_URL\")" in backend_adapter
    assert "DEFAULT_EMBEDDING_MODEL = '@cf/google/embeddinggemma-300m'" in worker
    assert "const EMBEDDING_DIMENSIONS = 768" in worker
    assert "async function handleEmbeddings" in worker
    assert "JSON.stringify({ text: texts })" in worker
    assert "url.pathname === '/v1/embeddings'" in worker
    assert "return handleEmbeddings(request, env)" in worker
    assert "Embedding ${index} did not contain ${EMBEDDING_DIMENSIONS} dimensions" in worker


def test_migration_and_image_build_contain_live_contracts() -> None:
    migration = read(DEPLOY / "migrations/008_knowledge_memory_passkeys_stepup.sql")
    are_migration = read(DEPLOY / "migrations/009_are_inference_quarantine.sql")
    dockerfile = read(DEPLOY / "Dockerfile")
    requirements = read(DEPLOY / "requirements.txt")
    workflow = read(ROOT / ".github/workflows/sovereign-backend-image.yml")
    ci_workflow = read(ROOT / ".github/workflows/ci.yml")
    setup_action = read(ROOT / ".github/actions/setup-backend-python/action.yml")

    assert "knowledge_blocks" in migration
    assert "embedding vector(768)" in migration
    assert "user_passkeys" in migration
    assert "step_up_approvals" in migration
    assert "USING hnsw" in migration
    assert "are_learning_quarantine" in are_migration
    assert "UNIQUE (user_id, content_sha256)" in are_migration
    assert "COPY *.py ./" in dockerfile
    assert "COPY agent_runtime/ ./agent_runtime/" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "webauthn>=2.7.0,<3" in requirements
    assert "pypdf>=5.0.0,<6" in requirements
    assert "requests>=2.31.0" in requirements
    assert "security_runtime.py" in workflow
    assert "are_inference.py" in workflow
    assert "uses: ./.github/actions/setup-backend-python" in ci_workflow
    assert "backend/requirements-test.txt" in read(ROOT / ".github/actions/setup-backend-python/action.yml")


def test_pnpm_action_setup_uses_package_manager_as_single_version_source() -> None:
    workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    for workflow_path in workflows:
        source = read(workflow_path)
        assert "PNPM_VERSION: 10" not in source, workflow_path.name
        assert "PNPM_VERSION: \"10\"" not in source, workflow_path.name
        lines = source.splitlines()
        for index, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped.startswith("- uses: pnpm/action-setup@v4"):
                continue
            step_indent = len(line) - len(stripped)
            for candidate in lines[index + 1:]:
                candidate_stripped = candidate.lstrip()
                candidate_indent = len(candidate) - len(candidate_stripped)
                if candidate_stripped.startswith("- ") and candidate_indent == step_indent:
                    break
                assert not candidate_stripped.startswith("version:"), workflow_path.name


def test_payment_and_credit_security_are_server_authoritative() -> None:
    for path in (DEPLOY / "app.py",):
        source = read(path)
        assert '@app.route("/api/billing/purchase/google-play/validate", methods=["POST"])\n@require_session\ndef google_play_validate' in source
        assert "user_id        = request.session_user_id" in source
        assert "_authorize_credit_purchase" in source
        assert '"error": "Account mismatch"' in source
        assert '"error": "unknown_cost_id"' in source
        assert "FROM admin_users AS account" in source
        assert "LEFT JOIN credit_ledger AS ledger" in source
        assert "cached_balance != ledger_balance" in source
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
