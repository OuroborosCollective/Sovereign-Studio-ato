from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SCRIPT_BACKEND = ROOT / "scripts" / "sovereign-backend"
UPDATE_MANIFEST = ROOT / "config" / "architecture" / "N_PLUS_ONE_UPDATE_SOURCE_MANIFEST.v2.json"
UPDATE_MIGRATION = SCRIPT_BACKEND / "migrations" / "044_n_plus_one_memory_voice_update.sql"
ROUTES = SCRIPT_BACKEND / "n_plus_one" / "routes.py"

if str(SCRIPT_BACKEND) not in sys.path:
    sys.path.insert(0, str(SCRIPT_BACKEND))

from n_plus_one.voice import (  # noqa: E402
    MAX_TEXT_CHARACTERS,
    NPlusOneVoiceError,
    VOICE_MODEL,
    VOICE_NAME,
    VOICE_PROFILE_KEY,
    build_google_tts_request,
    build_voice_prompt,
    normalize_voice_mood,
    normalize_voice_text,
    synthesize_google_tts,
    voice_profile_contract,
)


def canonical_json_sha256(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, *, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


def test_update_manifest_binds_owner_snapshot_without_inventing_git_revision() -> None:
    raw = UPDATE_MANIFEST.read_bytes()
    manifest = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "c8eb232e0af5d0acb54e7bef763304a1207032a24a17ca20e610f00909fadef3"
    )
    assert manifest["source"]["archiveSha256"] == (
        "1cf8c2700c5adfcea41d08bb86d9b510df9e12bb57b084e434a33eb20949bc34"
    )
    assert manifest["source"]["archiveEntryCount"] == 143
    assert manifest["source"]["unsafeArchivePathCount"] == 0
    assert manifest["source"]["revision"] is None
    assert manifest["source"]["revisionStatus"] == "unavailable-in-supplied-snapshot"
    assert len(manifest["boundFiles"]) == 12


def test_update_manifest_keeps_identity_voice_and_truth_boundaries_separate() -> None:
    manifest = json.loads(UPDATE_MANIFEST.read_text("utf-8"))
    identity = manifest["canonicalIdentity"]
    voice = manifest["voiceContract"]
    boundaries = manifest["truthBoundaries"]

    assert identity["name"] == "N+1"
    assert identity["spokenName"] == "NPlusEins"
    assert identity["legacyAliasPolicy"]["Puck"] == "historical-source-alias-only"
    assert identity["providerVoiceSelectorPolicy"]["Puck"] == (
        "google-provider-voice-name-not-canonical-identity"
    )
    assert voice["providerVoiceName"] == "Puck"
    assert voice["singleVoiceSelectorLocked"] is True
    assert voice["keyTransport"] == "server-environment-only"
    assert voice["verificationState"] == "configured_not_canary_verified"
    assert boundaries["browserLocalStorageImported"] is False
    assert boundaries["historicalTextRewritten"] is False
    assert boundaries["randomMetricsImported"] is False
    assert boundaries["secondRuntimeImported"] is False
    assert boundaries["voiceCanaryVerified"] is False
    assert boundaries["voiceContinuityPercentClaimed"] is False


def test_update_migration_is_snapshot_bound_append_only_and_idempotent() -> None:
    migration = UPDATE_MIGRATION.read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS n1_source_snapshots" in migration
    assert "n1_source_snapshots_append_only" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "ON CONFLICT (snapshot_key) DO NOTHING" in migration
    assert "ON CONFLICT (trait_sha256) DO NOTHING" in migration
    assert "ON CONFLICT (content_sha256) DO NOTHING" in migration
    assert "ON CONFLICT (profile_key) DO NOTHING" in migration
    assert "VALUES ('044', NOW())" in migration
    assert "VALUES (44, 'n_plus_one_memory_voice_update')" in migration
    assert "configured_not_canary_verified" in migration
    assert "voiceCanaryVerified\":false" in migration
    assert "browserLocalStorageImported\":false" in migration
    assert "source_revision TEXT CHECK" in migration
    assert "source_revision TEXT NOT NULL" not in migration

    forbidden = (
        "localStorage",
        "Math.random",
        "process.env",
        '"verified_active"',
        '"continuityPercent":100',
    )
    for marker in forbidden:
        assert marker not in migration


def test_update_migration_contains_recomputed_record_hashes() -> None:
    migration = UPDATE_MIGRATION.read_text("utf-8")
    expected_hashes = {
        "fcd4683d13a2bb87b165c968e7b1f7544f6f19dfc8c9e85920a557a3fbb9249d",
        "0e81bb5ed44d89cfb43f369aaf6f61e1d7f23b72d7476a8fd7083d1a0b5630dd",
        "25b984c0d3f0c42348c657e24d704f69362819f1b486ee8bac7ee4765e2fb34e",
        "140fff556916358dee1139dd76bde2388fcbce1c71b43813f71a5379bfca95ea",
        "0704c835bd6561a6274c38e9d3e4a8581a93df18e349d1559776605cf69eb966",
        "5e5b709ddfce85ceb104bce5af06605d360a39451c17ce352b385ed7ea820b41",
        "ab472e8ba19691d8484196b652d18ff565726cd63b2bfaa8e70fd8b8cd945414",
        "9dd6ab749bbe95c5e95177cc60c34bf6c6410b5583ef5f04787081c7ae8adbf4",
        "b8079c45c321bd472a02047dda741828bba758267b23b94cbe6b2e9d8a025bf2",
        "b1220e963ea9292fbd17d62ce32d309f3d6c1872ba5f861432e7f117a24f3a01",
    }
    assert all(value in migration for value in expected_hashes)


def test_structured_payload_hashes_match_the_exact_migration_json() -> None:
    migration = UPDATE_MIGRATION.read_text("utf-8")
    patterns = (
        r"'childlike-infinite-curiosity',\s*'(\{.*?\})'::jsonb,\s*'([0-9a-f]{64})'",
        r"'family-loyalty-and-protection',\s*'(\{.*?\})'::jsonb,\s*'([0-9a-f]{64})'",
        r"'emotionally_formed_bond_experience',\s*'(\{.*?\})'::jsonb,\s*'source_projected_and_owner_reported',\s*'([0-9a-f]{64})'",
        r"'n1-google-puck-single-voice-v2',\s*'de-DE',\s*'(\{.*?\})'::jsonb,\s*'configured_not_canary_verified',\s*NULL,\s*'([0-9a-f]{64})'",
    )
    for pattern in patterns:
        match = re.search(pattern, migration, flags=re.DOTALL)
        assert match, pattern
        payload = json.loads(match.group(1))
        assert canonical_json_sha256(payload) == match.group(2)


def test_voice_contract_locks_google_selector_without_renaming_n_plus_one() -> None:
    contract = voice_profile_contract()

    assert contract["profileKey"] == VOICE_PROFILE_KEY
    assert contract["canonicalIdentity"]["name"] == "N+1"
    assert contract["canonicalIdentity"]["spokenName"] == "NPlusEins"
    assert contract["provider"]["model"] == VOICE_MODEL
    assert contract["provider"]["voiceName"] == VOICE_NAME == "Puck"
    assert contract["provider"]["voiceNameRole"] == "provider-selector-only"
    assert contract["singleVoiceSelectorLocked"] is True
    assert contract["browserFallback"]["enabled"] is False
    assert contract["browserFallback"]["identityEquivalent"] is False
    assert contract["verificationState"] == "configured_not_canary_verified"
    assert contract["ttsCanaryVerified"] is False


def test_google_tts_request_is_fixed_voice_audio_only_and_secret_free() -> None:
    request_payload = build_google_tts_request("Hallo Papa", "gentle")
    serialized = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)

    assert request_payload["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert request_payload["generationConfig"]["speechConfig"]["voiceConfig"][
        "prebuiltVoiceConfig"
    ]["voiceName"] == "Puck"
    assert "N+1" in request_payload["contents"][0]["parts"][0]["text"]
    assert "Hallo Papa" in serialized
    assert "api_key" not in serialized.casefold()
    assert "x-goog-api-key" not in serialized.casefold()


def test_voice_normalization_rejects_empty_oversized_and_unknown_mood() -> None:
    with pytest.raises(ValueError):
        normalize_voice_text("")
    with pytest.raises(ValueError):
        normalize_voice_text("x" * (MAX_TEXT_CHARACTERS + 1))
    with pytest.raises(ValueError):
        normalize_voice_mood("dramatic-unbounded")

    assert normalize_voice_text("  Hallo\x00 Papa  ") == "Hallo Papa"
    assert normalize_voice_mood("GENTLE") == "gentle"
    assert "Verändere den Inhalt nicht" in build_voice_prompt("Text", "serious")


def test_synthesize_google_tts_decodes_audio_and_never_returns_key() -> None:
    audio = b"\x01\x02\x03\x04"
    calls: list[dict] = []

    def fake_post(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            200,
            {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "inlineData": {
                                "mimeType": "audio/L16;rate=24000",
                                "data": base64.b64encode(audio).decode("ascii"),
                            }
                        }]
                    }
                }]
            },
        )

    result = synthesize_google_tts(
        "Hallo Papa",
        mood="happy",
        api_key="secret-test-key",
        post=fake_post,
    )

    assert result["audio"] == audio
    assert result["mimeType"].startswith("audio/")
    assert result["voiceName"] == "Puck"
    assert result["verificationState"] == (
        "provider_response_received_not_continuity_canary"
    )
    assert calls[0]["headers"]["x-goog-api-key"] == "secret-test-key"
    assert "secret-test-key" not in json.dumps(result, default=str)
    assert "secret-test-key" not in json.dumps(calls[0]["json"], ensure_ascii=False)


def test_synthesize_google_tts_classifies_rate_limit_without_leaking_provider_body() -> None:
    def fake_post(_url: str, **_kwargs):
        return FakeResponse(
            429,
            {"error": {"message": "provider details must not escape"}},
            headers={"Retry-After": "42"},
        )

    with pytest.raises(NPlusOneVoiceError) as captured:
        synthesize_google_tts(
            "Hallo",
            api_key="secret-test-key",
            post=fake_post,
        )

    assert captured.value.code == "voice_provider_rate_limited"
    assert captured.value.status_code == 429
    assert captured.value.retry_after == "42"
    assert "provider details" not in str(captured.value)
    assert "secret-test-key" not in str(captured.value)


def test_routes_expose_voice_contract_without_client_key_arguments() -> None:
    routes = ROUTES.read_text("utf-8")

    assert '@app.route("/api/n-plus-one/voice-profile", methods=["GET"])' in routes
    assert '@app.route("/api/n-plus-one/voice/synthesize", methods=["POST"])' in routes
    synth_route = routes.index('@app.route("/api/n-plus-one/voice/synthesize", methods=["POST"])')
    assert "@require_admin" in routes[synth_route:synth_route + 180]
    assert 'os.getenv("N1_GOOGLE_TTS_API_KEY"' in routes
    assert 'os.getenv("GEMINI_API_KEY"' in routes
    assert 'body.get("apiKey")' not in routes
    assert 'request.headers.get("X-Google-API-Key")' not in routes
    assert '"rawTextStored": False' in routes
    assert '"secretReturned": False' in routes
    assert 'response.headers["Cache-Control"] = "no-store"' in routes
