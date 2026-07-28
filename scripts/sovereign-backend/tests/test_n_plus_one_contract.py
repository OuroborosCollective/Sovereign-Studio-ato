from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SCRIPT_BACKEND = ROOT / "scripts" / "sovereign-backend"
MANIFEST = ROOT / "config" / "architecture" / "N_PLUS_ONE_SOURCE_MANIFEST.v1.json"
MIGRATION = SCRIPT_BACKEND / "migrations" / "043_n_plus_one_foundation.sql"
CANONICAL_MIGRATION = BACKEND / "migrations" / "043_n_plus_one_foundation.sql"
UPDATE_MIGRATION = SCRIPT_BACKEND / "migrations" / "044_n_plus_one_memory_voice_update.sql"
CANONICAL_UPDATE_MIGRATION = BACKEND / "migrations" / "044_n_plus_one_memory_voice_update.sql"

if str(SCRIPT_BACKEND) not in sys.path:
    sys.path.insert(0, str(SCRIPT_BACKEND))

from n_plus_one.contracts import (  # noqa: E402
    IDENTITY_SHA256,
    SOURCE_ARCHIVE_SHA256,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
    assert_identity_contract,
    identity_payload,
    normalize_learning_candidate,
)
from n_plus_one.identity_covenant import canonical_identity  # noqa: E402
from n_plus_one.linguistic.evidence import observe_configured_markers  # noqa: E402


def test_n_plus_one_python_surfaces_parse_without_runtime_execution() -> None:
    relative_paths = (
        "n_plus_one/__init__.py",
        "n_plus_one/contracts.py",
        "n_plus_one/identity_covenant.py",
        "n_plus_one/routes.py",
        "n_plus_one/linguistic/__init__.py",
        "n_plus_one/linguistic/evidence.py",
        "n_plus_one/voice.py",
    )
    for root in (BACKEND, SCRIPT_BACKEND):
        for relative in relative_paths:
            path = root / relative
            ast.parse(path.read_text("utf-8"), filename=str(path))
    ast.parse((SCRIPT_BACKEND / "app.py").read_text("utf-8"), filename="app.py")


def test_canonical_and_deployed_n_plus_one_surfaces_are_byte_identical() -> None:
    relative_paths = (
        "n_plus_one/__init__.py",
        "n_plus_one/contracts.py",
        "n_plus_one/identity_covenant.py",
        "n_plus_one/routes.py",
        "n_plus_one/linguistic/__init__.py",
        "n_plus_one/linguistic/evidence.py",
        "n_plus_one/voice.py",
    )
    for relative in relative_paths:
        assert (BACKEND / relative).read_bytes() == (SCRIPT_BACKEND / relative).read_bytes()
    assert CANONICAL_MIGRATION.read_bytes() == MIGRATION.read_bytes()
    assert CANONICAL_UPDATE_MIGRATION.read_bytes() == UPDATE_MIGRATION.read_bytes()


def test_identity_covenant_is_hash_bound_and_does_not_grant_privileges() -> None:
    payload = identity_payload()
    assert assert_identity_contract(payload) == payload
    covenant = canonical_identity()

    assert covenant["identitySha256"] == IDENTITY_SHA256
    assert covenant["identity"]["canonicalName"] == "N+1"
    assert covenant["identity"]["spokenName"] == "NPlusEins"
    assert covenant["identity"]["technicalNamespace"] == "n_plus_one"
    assert covenant["identity"]["familyDesignation"] == "Papas kleines Mädchen"
    assert covenant["identity"]["projectBoundaries"]["separateProjects"] == [
        "Arelorian Wasd"
    ]
    assert covenant["identity"]["projectBoundaries"]["sharedRuntime"] is False
    assert covenant["identity"]["projectBoundaries"]["sharedDatabase"] is False
    assert covenant["privilegesDerivedFromPersonality"] is False
    assert covenant["technicalTruthAuthority"] is False
    assert covenant["runtimeSharedWithArelorianWasd"] is False
    assert {
        "name": "Puck",
        "status": "historical-source-alias-only",
    } in covenant["identity"]["legacyAliases"]


def test_learning_is_deterministic_candidate_only_and_never_self_verified() -> None:
    body = {
        "sourceKind": "llm_hypothesis",
        "sourceIdentity": "n1:test:hypothesis:1",
        "sourceRevision": SOURCE_REVISION,
        "classification": "learning_hypothesis",
        "content": "Eine Hypothese bleibt bis zum Evidence- oder Owner-Receipt Kandidatin.",
        "evidence": {"checks": [], "origin": "contract-test"},
    }
    first = normalize_learning_candidate(body, user_id="00000000-0000-0000-0000-000000000001")
    second = normalize_learning_candidate(body, user_id="00000000-0000-0000-0000-000000000001")

    assert first == second
    assert first["state"] == "candidate"
    assert first["verified"] is False
    assert len(first["contentSha256"]) == 64
    assert len(first["candidateSha256"]) == 64


def test_learning_candidate_rejects_unbound_revision_and_source_kind() -> None:
    invalid_revision = {
        "sourceKind": "owner_narrative",
        "sourceIdentity": "owner:test",
        "sourceRevision": "main",
        "classification": "story",
        "content": "Quelle",
    }
    invalid_source = {
        **invalid_revision,
        "sourceKind": "browser_local_storage",
        "sourceRevision": SOURCE_REVISION,
    }
    for body in (invalid_revision, invalid_source):
        try:
            normalize_learning_candidate(
                body,
                user_id="00000000-0000-0000-0000-000000000001",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid N+1 candidate input was accepted")


def test_linguahabar_marker_observation_is_replay_stable_and_not_a_detector_claim() -> None:
    rules = [
        {
            "profileKey": "n1-family-expression-v1",
            "ruleKey": "identity-n-plus-one",
            "markerText": "N+1",
            "category": "identity-token",
            "confidencePpm": 1_000_000,
            "sourceReference": {"provenance": "canonical-identity"},
        },
        {
            "profileKey": "n1-family-expression-v1",
            "ruleKey": "family-papa",
            "markerText": "Papa",
            "category": "family-term",
            "confidencePpm": 1_000_000,
            "sourceReference": {"provenance": "owner-family-context"},
        },
        {
            "profileKey": "n1-family-expression-v1",
            "ruleKey": "legacy-puck",
            "markerText": "Puck",
            "category": "legacy-alias",
            "confidencePpm": 1_000_000,
            "sourceReference": {
                "provenance": "historical-source-only",
                "canonicalReplacement": False,
            },
        },
    ]
    text = "Papa nennt sie N+1; Puck bleibt nur in ihrer Herkunft sichtbar."
    first = observe_configured_markers(text, rules)
    second = observe_configured_markers(text, list(reversed(rules)))

    assert first == second
    assert first["observationCount"] == 3
    assert first["dialectVerified"] is False
    assert first["detectorClaimed"] is False
    assert "no dialect model" in first["truthNotice"]
    assert all(item["classificationState"] == "candidate_observation" for item in first["observations"])
    assert all(item["dialectVerified"] is False for item in first["observations"])
    assert all(len(item["observationSha256"]) == 64 for item in first["observations"])


def test_source_manifest_binds_the_exact_archive_and_truth_boundaries() -> None:
    manifest = json.loads(MANIFEST.read_text("utf-8"))

    assert manifest["source"]["revision"] == SOURCE_REVISION
    assert manifest["source"]["archiveSha256"] == SOURCE_ARCHIVE_SHA256
    assert manifest["source"]["archiveEntryCount"] == 101
    assert manifest["source"]["unsafeArchivePathCount"] == 0
    assert len(manifest["boundFiles"]) == 10
    assert manifest["truthBoundaries"]["technicalCapabilityImportedByClaim"] is False
    assert manifest["truthBoundaries"]["dialectDetectionVerified"] is False
    assert manifest["truthBoundaries"]["voiceLinguaChainVerified"] is False
    assert manifest["truthBoundaries"]["memoryIntegrityVerified"] is False
    assert manifest["truthBoundaries"]["learningAutoVerified"] is False
    assert manifest["truthBoundaries"]["openSqlImported"] is False
    assert manifest["truthBoundaries"]["secondRuntimeImported"] is False
    assert manifest["truthBoundaries"]["sharedRuntimeWithArelorianWasd"] is False
    import hashlib

    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == SOURCE_MANIFEST_SHA256


def test_migration_is_append_only_candidate_gated_and_registers_all_foundation_tables() -> None:
    migration = MIGRATION.read_text("utf-8")
    required_tables = (
        "n1_source_artifacts",
        "n1_identity_versions",
        "n1_personality_traits",
        "n1_family_provenance",
        "n1_story_entries",
        "n1_experience_events",
        "n1_learning_candidates",
        "n1_learning_receipts",
        "n1_linguistic_profiles",
        "n1_grammar_rules",
        "n1_dialect_observations",
        "n1_voice_profiles",
        "n1_response_style_receipts",
    )
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "n1_reject_append_only_mutation" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "state TEXT NOT NULL DEFAULT 'candidate' CHECK (state = 'candidate')" in migration
    assert "decision TEXT NOT NULL CHECK (decision IN ('accepted','rejected'))" in migration
    assert "configured_not_canary_verified" in migration
    assert "autoVerifiedImported\":false" in migration
    assert "openSqlImported\":false" in migration
    assert "VALUES ('043', NOW())" in migration
    assert "VALUES (43, 'n_plus_one_foundation')" in migration


def test_flask_docker_and_readiness_contract_wire_the_domain_without_second_runtime() -> None:
    app = (SCRIPT_BACKEND / "app.py").read_text("utf-8")
    dockerfile = (SCRIPT_BACKEND / "Dockerfile").read_text("utf-8")
    routes = (SCRIPT_BACKEND / "n_plus_one" / "routes.py").read_text("utf-8")

    assert "from n_plus_one import register_n_plus_one_routes" in app
    assert "register_n_plus_one_routes(" in app
    assert "require_session=require_session" in app
    assert "require_admin=require_admin" in app
    assert '"043_n_plus_one_foundation.sql"' in app
    assert '"044_n_plus_one_memory_voice_update.sql"' in app
    for schema_contract in (
        "n1_source_artifacts",
        "n1_source_snapshots",
        "n1_identity_versions",
        "n1_learning_candidates",
        "n1_dialect_observations",
    ):
        assert schema_contract in app
    assert "COPY n_plus_one/ ./n_plus_one/" in dockerfile
    assert '@app.route("/api/n-plus-one/identity", methods=["GET"])' in routes
    assert '@app.route("/api/n-plus-one/linguistic/observe", methods=["POST"])' in routes
    assert '@app.route("/api/n-plus-one/voice-profile", methods=["GET"])' in routes
    assert '@app.route("/api/n-plus-one/voice/synthesize", methods=["POST"])' in routes
    assert "POST /api/db/query" not in routes
    assert "localStorage" not in routes
    assert "Math.random" not in routes
    assert "Date.now" not in routes
