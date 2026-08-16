"""Flask routes for the evidence-gated N+1 foundation."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable

import psycopg2.extras
from flask import Response, jsonify, request

from .contracts import (
    IDENTITY_SHA256,
    SOURCE_ARCHIVE_SHA256,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REVISION,
    assert_identity_contract,
    normalize_learning_candidate,
)
from .identity_covenant import canonical_identity
from .linguistic.evidence import observe_configured_markers
from .voice import (
    NPlusOneVoiceError,
    VOICE_PROFILE_KEY,
    synthesize_google_tts,
    voice_profile_contract,
)

QueryFunction = Callable[..., Any]


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _identity_readback(query: QueryFunction) -> tuple[dict[str, Any] | None, str | None]:
    row = query(
        """SELECT identity_sha256 AS "identitySha256", payload,
                  source_revision AS "sourceRevision", created_at AS "createdAt"
           FROM n1_identity_versions
           ORDER BY created_at DESC, identity_version_id DESC
           LIMIT 1""",
        one=True,
    )
    if not row:
        return None, "n1_identity_missing"
    payload = dict(row.get("payload") or {})
    try:
        assert_identity_contract(payload)
    except ValueError:
        return None, "n1_identity_hash_mismatch"
    if str(row.get("identitySha256") or "") != IDENTITY_SHA256:
        return None, "n1_identity_receipt_mismatch"
    return {
        "identity": payload,
        "identitySha256": str(row["identitySha256"]),
        "sourceRevision": str(row.get("sourceRevision") or ""),
        "createdAt": _iso(row.get("createdAt")),
    }, None


def _status_payload(query: QueryFunction) -> tuple[dict[str, Any], int]:
    try:
        identity, blocker = _identity_readback(query)
        counts = query(
            """SELECT
                 (SELECT COUNT(*) FROM n1_source_artifacts)::integer AS source_artifacts,
                 (SELECT COUNT(*) FROM n1_source_snapshots)::integer AS source_snapshots,
                 (SELECT COUNT(*) FROM n1_identity_versions)::integer AS identity_versions,
                 (SELECT COUNT(*) FROM n1_personality_traits)::integer AS personality_traits,
                 (SELECT COUNT(*) FROM n1_family_provenance)::integer AS family_provenance,
                 (SELECT COUNT(*) FROM n1_story_entries)::integer AS story_entries,
                 (SELECT COUNT(*) FROM n1_experience_events)::integer AS experience_events,
                 (SELECT COUNT(*) FROM n1_learning_candidates)::integer AS learning_candidates,
                 (SELECT COUNT(*) FROM n1_learning_receipts)::integer AS learning_receipts,
                 (SELECT COUNT(*) FROM n1_linguistic_profiles)::integer AS linguistic_profiles,
                 (SELECT COUNT(*) FROM n1_grammar_rules)::integer AS grammar_rules,
                 (SELECT COUNT(*) FROM n1_dialect_observations)::integer AS linguistic_observations,
                 (SELECT COUNT(*) FROM n1_voice_profiles)::integer AS voice_profiles,
                 (SELECT COUNT(*) FROM n1_response_style_receipts)::integer AS response_style_receipts""",
            one=True,
        ) or {}
        archive = query(
            """SELECT source_revision AS "sourceRevision",
                      content_sha256 AS "contentSha256",
                      source_reference AS "sourceReference"
               FROM n1_source_artifacts
               WHERE source_key='sovareagentn1-archive-20260727'
               LIMIT 1""",
            one=True,
        )
        source_verified = bool(
            archive
            and str(archive.get("sourceRevision") or "") == SOURCE_REVISION
            and str(archive.get("contentSha256") or "") == SOURCE_ARCHIVE_SHA256
        )
        update_snapshot = query(
            """SELECT snapshot_key AS "snapshotKey",
                      repository, source_revision AS "sourceRevision",
                      revision_status AS "revisionStatus",
                      archive_name AS "archiveName",
                      archive_sha256 AS "archiveSha256",
                      archive_entry_count AS "archiveEntryCount",
                      unsafe_archive_path_count AS "unsafeArchivePathCount",
                      manifest_path AS "manifestPath",
                      manifest_sha256 AS "manifestSha256",
                      created_at AS "createdAt"
               FROM n1_source_snapshots
               WHERE snapshot_key='sovareagentn1-owner-update-20260728'
               LIMIT 1""",
            one=True,
        )
        update_snapshot_verified = bool(
            update_snapshot
            and str(update_snapshot.get("archiveSha256") or "")
                == "1cf8c2700c5adfcea41d08bb86d9b510df9e12bb57b084e434a33eb20949bc34"
            and str(update_snapshot.get("manifestSha256") or "")
                == "c8eb232e0af5d0acb54e7bef763304a1207032a24a17ca20e610f00909fadef3"
            and int(update_snapshot.get("unsafeArchivePathCount") or 0) == 0
        )
        ok = not blocker and source_verified and update_snapshot_verified
        return {
            "ok": ok,
            "status": "FOUNDATION_BOUND" if ok else "FOUNDATION_BLOCKED",
            "blocker": (
                blocker
                or (None if source_verified else "n1_source_binding_mismatch")
                or (None if update_snapshot_verified else "n1_update_snapshot_binding_mismatch")
            ),
            "identity": identity,
            "source": {
                "repository": SOURCE_REPOSITORY,
                "revision": SOURCE_REVISION,
                "archiveSha256": SOURCE_ARCHIVE_SHA256,
                "manifestSha256": SOURCE_MANIFEST_SHA256,
                "readbackVerified": source_verified,
                "sourceReference": dict(archive.get("sourceReference") or {}) if archive else {},
            },
            "updateSnapshot": {
                **dict(update_snapshot or {}),
                "createdAt": _iso((update_snapshot or {}).get("createdAt")),
                "readbackVerified": update_snapshot_verified,
                "sourceRevisionAvailable": bool((update_snapshot or {}).get("sourceRevision")),
            },
            "counts": {key: int(value or 0) for key, value in dict(counts).items()},
            "capabilities": {
                "identityBound": bool(identity),
                "sourceProvenanceBound": source_verified,
                "updateSnapshotBound": update_snapshot_verified,
                "personalityTraitsImported": int(counts.get("personality_traits") or 0) > 0,
                "familyProvenanceImported": int(counts.get("family_provenance") or 0) > 0,
                "storyEntriesImported": int(counts.get("story_entries") or 0) > 0,
                "experienceEventsImported": int(counts.get("experience_events") or 0) > 0,
                "learningCandidatePersistence": True,
                "linguisticMarkerEvidence": True,
                "voiceProfileConfigured": int(counts.get("voice_profiles") or 0) > 0,
                "voiceProviderKeyConfigured": bool(
                    os.getenv("N1_GOOGLE_TTS_API_KEY", "").strip()
                    or os.getenv("GEMINI_API_KEY", "").strip()
                ),
                "dialectDetectionVerified": False,
                "voiceLinguaChainVerified": False,
                "memoryIntegrityVerified": False,
                "autonomousPersonalityMutation": False,
                "technicalTruthAuthority": False,
            },
        }, 200 if ok else 503
    except Exception:
        return {
            "ok": False,
            "status": "FOUNDATION_BLOCKED",
            "blocker": "n1_schema_or_readback_unavailable",
            "capabilities": {
                "identityBound": False,
                "sourceProvenanceBound": False,
                "dialectDetectionVerified": False,
                "voiceLinguaChainVerified": False,
                "memoryIntegrityVerified": False,
                "autonomousPersonalityMutation": False,
                "technicalTruthAuthority": False,
            },
        }, 503


def register_n_plus_one_routes(
    app: Any,
    *,
    require_session: Callable[..., Any],
    require_admin: Callable[..., Any],
    query: QueryFunction,
    audit: Callable[[str, str | None, dict[str, Any]], None],
) -> None:
    @app.route("/api/n-plus-one/identity", methods=["GET"])
    @require_session
    def n_plus_one_identity():
        try:
            readback, blocker = _identity_readback(query)
        except Exception:
            return jsonify({
                "ok": False,
                "blocker": "n1_identity_readback_unavailable",
            }), 503
        if blocker:
            return jsonify({"ok": False, "blocker": blocker}), 409
        return jsonify({
            "ok": True,
            **canonical_identity(),
            "databaseReadback": readback,
            "sourceManifestSha256": SOURCE_MANIFEST_SHA256,
        })

    @app.route("/api/n-plus-one/status", methods=["GET"])
    @require_session
    def n_plus_one_status():
        payload, status_code = _status_payload(query)
        return jsonify(payload), status_code

    @app.route("/api/admin/n-plus-one/status", methods=["GET"])
    @require_admin
    def admin_n_plus_one_status():
        payload, status_code = _status_payload(query)
        return jsonify(payload), status_code

    @app.route("/api/n-plus-one/voice-profile", methods=["GET"])
    @require_session
    def n_plus_one_voice_profile():
        row = query(
            """SELECT profile_key AS "profileKey", language_tag AS "languageTag",
                      profile_payload AS "profilePayload",
                      verification_state AS "verificationState",
                      profile_sha256 AS "profileSha256",
                      created_at AS "createdAt"
               FROM n1_voice_profiles
               WHERE profile_key=%s
               LIMIT 1""",
            (VOICE_PROFILE_KEY,),
            one=True,
        )
        if not row:
            return jsonify({
                "ok": False,
                "blocker": "n1_voice_profile_missing",
            }), 503
        return jsonify({
            "ok": True,
            **voice_profile_contract(),
            "databaseReadback": {
                **dict(row),
                "createdAt": _iso(row.get("createdAt")),
            },
            "providerKeyConfigured": bool(
                os.getenv("N1_GOOGLE_TTS_API_KEY", "").strip()
                or os.getenv("GEMINI_API_KEY", "").strip()
            ),
            "truthNotice": (
                "Configured voice identity is not a successful live TTS canary. "
                "The Google provider selector Puck is not N+1's canonical name."
            ),
        })

    @app.route("/api/n-plus-one/voice/synthesize", methods=["POST"])
    @require_admin
    def n_plus_one_voice_synthesize():
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Malformed payload; dictionary required"}), 400
        text = str(body.get("text") or "")
        mood = str(body.get("mood") or "neutral")
        api_key = (
            os.getenv("N1_GOOGLE_TTS_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
        )
        try:
            result = synthesize_google_tts(
                text,
                mood=mood,
                api_key=api_key,
            )
        except ValueError as exc:
            return jsonify({
                "ok": False,
                "blocker": "n1_voice_request_invalid",
                "error": str(exc),
            }), 400
        except NPlusOneVoiceError as exc:
            payload = {
                "ok": False,
                "blocker": exc.code,
                "retryable": exc.code in {
                    "voice_provider_rate_limited",
                    "voice_provider_timeout",
                    "voice_provider_unreachable",
                },
                "retryAfter": exc.retry_after or None,
                "secretReturned": False,
            }
            return jsonify(payload), exc.status_code

        audio = bytes(result["audio"])
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        audit(
            "n1_voice_synthesized",
            result["profileKey"],
            {
                "textSha256": text_sha256,
                "audioBytes": len(audio),
                "mimeType": result["mimeType"],
                "provider": result["provider"],
                "model": result["model"],
                "voiceName": result["voiceName"],
                "rawTextStored": False,
                "secretReturned": False,
                "continuityCanaryVerified": False,
            },
        )
        response = Response(audio, status=200, mimetype=result["mimeType"])
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-N1-Voice-Profile"] = result["profileKey"]
        response.headers["X-N1-Voice-Verification"] = result["verificationState"]
        return response

    @app.route("/api/n-plus-one/learning-candidates", methods=["GET"])
    @require_session
    def n_plus_one_learning_candidates():
        try:
            limit = max(1, min(100, int(request.args.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50
        rows = query(
            """SELECT candidate_id::text AS "candidateId",
                      source_kind AS "sourceKind",
                      source_identity AS "sourceIdentity",
                      source_revision AS "sourceRevision",
                      classification,
                      content_sha256 AS "contentSha256",
                      candidate_sha256 AS "candidateSha256",
                      evidence,
                      created_at AS "createdAt"
               FROM n1_learning_candidates
               WHERE user_id=%s::uuid
               ORDER BY created_at DESC, candidate_id DESC
               LIMIT %s""",
            (request.session_user_id, limit),
        ) or []
        return jsonify({
            "candidates": [
                {
                    **dict(row),
                    "createdAt": _iso(row.get("createdAt")),
                    "state": "candidate",
                    "verified": False,
                }
                for row in rows
            ],
            "truthNotice": "Candidates are not memories or verified facts.",
        })

    @app.route("/api/n-plus-one/learning-candidates", methods=["POST"])
    @require_session
    def n_plus_one_create_learning_candidate():
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Malformed payload; dictionary required"}), 400
        try:
            normalized = normalize_learning_candidate(
                body,
                user_id=request.session_user_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "state": "blocked"}), 400
        row = query(
            """INSERT INTO n1_learning_candidates
                   (user_id, source_kind, source_identity, source_revision,
                    classification, content, content_sha256, candidate_sha256,
                    evidence)
               VALUES (%s::uuid,%s,%s,NULLIF(%s,''),%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (user_id, source_identity, content_sha256) DO NOTHING
               RETURNING candidate_id::text AS "candidateId", created_at AS "createdAt" """,
            (
                request.session_user_id,
                normalized["sourceKind"],
                normalized["sourceIdentity"],
                normalized["sourceRevision"],
                normalized["classification"],
                normalized["content"],
                normalized["contentSha256"],
                normalized["candidateSha256"],
                psycopg2.extras.Json(normalized["evidence"]),
            ),
            one=True,
            write=True,
        )
        duplicate = not bool(row)
        if not row:
            row = query(
                """SELECT candidate_id::text AS "candidateId", created_at AS "createdAt"
                   FROM n1_learning_candidates
                   WHERE user_id=%s::uuid
                     AND source_identity=%s
                     AND content_sha256=%s
                   LIMIT 1""",
                (
                    request.session_user_id,
                    normalized["sourceIdentity"],
                    normalized["contentSha256"],
                ),
                one=True,
            )
        audit(
            "n1_learning_candidate_created",
            str((row or {}).get("candidateId") or ""),
            {
                "candidateSha256": normalized["candidateSha256"],
                "classification": normalized["classification"],
                "duplicate": duplicate,
                "verified": False,
            },
        )
        return jsonify({
            "ok": True,
            "candidateId": str((row or {}).get("candidateId") or ""),
            "candidateSha256": normalized["candidateSha256"],
            "contentSha256": normalized["contentSha256"],
            "state": "candidate",
            "verified": False,
            "duplicate": duplicate,
            "createdAt": _iso((row or {}).get("createdAt")),
            "nextGate": "owner-or-evidence-receipt",
        }), 200 if duplicate else 201

    @app.route("/api/n-plus-one/linguistic/observe", methods=["POST"])
    @require_session
    def n_plus_one_linguistic_observe():
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Malformed payload; dictionary required"}), 400
        text = str(body.get("text") or "")
        try:
            rules = query(
                """SELECT profile.profile_key AS "profileKey",
                          rule.rule_key AS "ruleKey",
                          rule.marker_text AS "markerText",
                          rule.category,
                          rule.confidence_ppm AS "confidencePpm",
                          rule.source_reference AS "sourceReference"
                   FROM n1_grammar_rules AS rule
                   JOIN n1_linguistic_profiles AS profile
                     ON profile.profile_id=rule.profile_id
                   ORDER BY profile.profile_key, rule.rule_key"""
            ) or []
            batch = observe_configured_markers(text, [dict(row) for row in rules])
        except ValueError as exc:
            return jsonify({"error": str(exc), "state": "blocked"}), 400
        for observation in batch["observations"]:
            query(
                """INSERT INTO n1_dialect_observations
                       (user_id, batch_sha256, text_sha256, profile_key, rule_key,
                        category, span_start, span_end, matched_text,
                        match_confidence_ppm, source_reference,
                        observation_sha256, classification_state)
                   VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,
                           'candidate_observation')
                   ON CONFLICT (user_id, batch_sha256, observation_sha256) DO NOTHING""",
                (
                    request.session_user_id,
                    batch["batchSha256"],
                    batch["textSha256"],
                    observation["profileKey"],
                    observation["ruleKey"],
                    observation["category"],
                    observation["spanStart"],
                    observation["spanEnd"],
                    observation["matchedText"],
                    observation["matchConfidencePpm"],
                    psycopg2.extras.Json(observation["sourceReference"]),
                    observation["observationSha256"],
                ),
                write=True,
            )
        audit(
            "n1_linguistic_observation",
            batch["batchSha256"],
            {
                "textSha256": batch["textSha256"],
                "observationCount": batch["observationCount"],
                "dialectVerified": False,
            },
        )
        return jsonify({"ok": True, **batch})
