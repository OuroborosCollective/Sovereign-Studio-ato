"""Routes and persistence for the Sovereign Evidence Observatory Atlas."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable

import psycopg2.extras
from flask import jsonify, request

from evidence_observatory_contracts import (
    WORKFLOW_PUBLISHED,
    WORKFLOW_PUBLISHABLE,
    WORKFLOW_QUARANTINED,
    build_evidence_passport,
    evaluate_evidence_case,
    https_url,
    iso_datetime,
    normalized_claim,
    public_case_projection,
    score_arena_response,
    source_dependency_analysis,
    sha256_json,
    sha256_text,
)
from evidence_observatory_integrations import (
    arena_request,
    normalize_notion_export,
    parse_arena_text,
    publish_huggingface_batch,
)

QueryFn = Callable[..., Any]
AuditFn = Callable[[str, str | None, dict[str, Any]], None]
_PUBLIC_STATES = (WORKFLOW_PUBLISHABLE, WORKFLOW_PUBLISHED)
_SETTLED_ARENA_STATES = {"settled_usage", "settled_estimate", "refunded"}


def _public_case(query: QueryFn, case_id: str) -> dict[str, Any] | None:
    row = query(
        """SELECT id::text, project_id, title, claim, claim_sha256, verdict,
                  evidence_class, workflow_state, visibility, source_kind,
                  source_locator, case_payload, gate_report, passport,
                  passport_sha256, case_sha256, as_of, created_at, updated_at,
                  published_at
           FROM evidence_observatory_cases
           WHERE id::text=%s AND visibility='public'
             AND workflow_state = ANY(%s)
           LIMIT 1""",
        (case_id, list(_PUBLIC_STATES)), one=True,
    )
    return dict(row) if row else None


def _candidate_case(query: QueryFn, case_id: str) -> dict[str, Any] | None:
    row = query(
        """SELECT id::text, project_id, title, claim, claim_sha256, verdict,
                  evidence_class, workflow_state, visibility, source_kind,
                  source_locator, raw_payload, case_payload, gate_report,
                  passport, passport_sha256, case_sha256, as_of,
                  created_at, updated_at, published_at
           FROM evidence_observatory_cases WHERE id::text=%s LIMIT 1""",
        (case_id,), one=True,
    )
    return dict(row) if row else None


def _safe_case_id(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("case_id_invalid") from exc


def _admin_id(get_current_admin: Callable[[], dict | None]) -> str:
    value = str((get_current_admin() or {}).get("id") or "").strip()
    if not value:
        raise RuntimeError("authenticated_admin_id_missing")
    return value


def _arena_model_response(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return parse_arena_text(value)


def _case_projection_for_publish(row: dict[str, Any]) -> dict[str, Any]:
    projection = public_case_projection(row)
    payload = row.get("case_payload") if isinstance(row.get("case_payload"), dict) else {}
    projection["proofReceipts"] = payload.get("proofReceipts") or []
    projection["method"] = payload.get("method") or {}
    return projection


def register_evidence_observatory_routes(
    app: Any,
    *,
    require_session: Callable,
    require_admin: Callable,
    query: QueryFn,
    get_current_admin: Callable[[], dict | None],
    audit: AuditFn,
) -> None:
    """Register Atlas, quarantine, publication and arena routes."""

    @app.route("/api/evidence-observatory/v1/atlas", methods=["GET"])
    def observatory_atlas():
        project_id = str(request.args.get("projectId") or "").strip()[:160]
        as_of_raw = str(request.args.get("asOf") or "").strip()
        as_of = iso_datetime(as_of_raw) if as_of_raw else None
        if as_of_raw and as_of is None:
            return jsonify({"ok": False, "error": "asOf_invalid"}), 400
        params: list[Any] = [list(_PUBLIC_STATES)]
        where = ["visibility='public'", "workflow_state = ANY(%s)"]
        if project_id:
            where.append("project_id=%s")
            params.append(project_id)
        rows = query(
            f"""SELECT id::text, project_id, title, claim, claim_sha256, verdict,
                       evidence_class, workflow_state, visibility, source_kind,
                       source_locator, case_payload, gate_report, passport,
                       passport_sha256, case_sha256, as_of, created_at, updated_at,
                       published_at
                FROM evidence_observatory_cases
                WHERE {' AND '.join(where)}
                ORDER BY COALESCE(as_of, created_at) ASC, id ASC
                LIMIT 500""",
            tuple(params),
        ) or []
        cases = [public_case_projection(dict(row), as_of=as_of) for row in rows]
        return jsonify({
            "ok": True,
            "cases": cases,
            "count": len(cases),
            "sourceCount": sum(len(case.get("sources") or []) for case in cases),
            "materialGeoEvidenceCount": sum(len(case.get("materialGeoEvidence") or []) for case in cases),
            "asOf": as_of.isoformat() if as_of else None,
            "projectId": project_id or None,
            "truthNotice": "The Atlas exposes reproducible evidence states. PUBLISHABLE does not mean every claim is SUPPORTED.",
        })

    @app.route("/api/evidence-observatory/v1/cases/<case_id>", methods=["GET"])
    def observatory_case(case_id: str):
        try:
            normalized_id = _safe_case_id(case_id)
        except ValueError:
            return jsonify({"ok": False, "error": "case_id_invalid"}), 400
        row = _public_case(query, normalized_id)
        if not row:
            return jsonify({"ok": False, "error": "case_not_found"}), 404
        as_of_raw = str(request.args.get("asOf") or "").strip()
        as_of = iso_datetime(as_of_raw) if as_of_raw else None
        if as_of_raw and as_of is None:
            return jsonify({"ok": False, "error": "asOf_invalid"}), 400
        return jsonify({"ok": True, "case": public_case_projection(row, as_of=as_of)})

    @app.route("/api/evidence-observatory/v1/cases/<case_id>/source-dependency", methods=["GET"])
    @require_session
    def observatory_source_dependency(case_id: str):
        try:
            normalized_id = _safe_case_id(case_id)
        except ValueError:
            return jsonify({"ok": False, "error": "case_id_invalid"}), 400
        source_id = str(request.args.get("sourceId") or "").strip()[:240]
        if not source_id:
            return jsonify({"ok": False, "error": "source_id_required"}), 400
        row = _public_case(query, normalized_id)
        if not row:
            return jsonify({"ok": False, "error": "case_not_found"}), 404
        try:
            analysis = source_dependency_analysis(row, source_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "analysis": analysis})

    @app.route("/api/evidence-observatory/v1/submissions", methods=["POST"])
    @require_session
    def observatory_submission():
        body = request.get_json(force=True) or {}
        claim = normalized_claim(body.get("claim"))
        source_url = str(body.get("sourceUrl") or "").strip()
        if not claim:
            return jsonify({"ok": False, "error": "claim_required"}), 400
        if not https_url(source_url):
            return jsonify({"ok": False, "error": "source_https_url_required"}), 400
        case_id = str(uuid.uuid4())
        project_id = str(body.get("projectId") or "community-research").strip()[:160] or "community-research"
        title = str(body.get("title") or claim).strip()[:500] or claim[:500]
        raw_payload = {
            "note": str(body.get("note") or "")[:10000],
            "submittedSourceUrl": source_url,
            "submittedBy": request.session_user_id,
            "truthPromotion": False,
        }
        row = query(
            """INSERT INTO evidence_observatory_cases
                   (id, project_id, title, claim, claim_sha256, verdict,
                    workflow_state, visibility, source_kind, source_locator,
                    external_key, raw_payload, case_payload, gate_report,
                    passport, created_by)
               VALUES (%s::uuid,%s,%s,%s,%s,'UNPROVEN','QUARANTINED','private',
                       'community',%s,%s,%s::jsonb,'{}'::jsonb,'{}'::jsonb,
                       '{}'::jsonb,%s::uuid)
               RETURNING id::text, workflow_state, visibility, claim_sha256""",
            (case_id, project_id, title, claim, sha256_text(claim), source_url,
             f"community:{case_id}", psycopg2.extras.Json(raw_payload), request.session_user_id),
            one=True, write=True,
        )
        audit("evidence_observatory_submission", case_id, {
            "projectId": project_id,
            "workflowState": WORKFLOW_QUARANTINED,
            "visibility": "private",
            "sourceLocatorSha256": sha256_text(source_url),
            "truthPromotion": False,
        })
        return jsonify({"ok": True, "candidate": dict(row), "truthPromotion": False}), 201

    @app.route("/api/admin/evidence-observatory/v1/notion/import", methods=["POST"])
    @require_admin
    def observatory_notion_import():
        try:
            normalized = normalize_notion_export(request.get_json(force=True) or {})
            admin_id = _admin_id(get_current_admin)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        inserted = updated = 0
        candidate_ids: list[str] = []
        for candidate in normalized["pages"]:
            claim = normalized_claim(candidate.get("claim"))
            if not claim:
                continue
            existing = query(
                "SELECT id::text FROM evidence_observatory_cases WHERE external_key=%s LIMIT 1",
                (candidate["externalKey"],), one=True,
            )
            row = query(
                """INSERT INTO evidence_observatory_cases
                       (project_id, title, claim, claim_sha256, verdict,
                        workflow_state, visibility, source_kind, source_locator,
                        external_key, raw_payload, case_payload, gate_report,
                        passport, as_of, created_by)
                   VALUES (%s,%s,%s,%s,'UNPROVEN','QUARANTINED','private','notion',
                           %s,%s,%s::jsonb,'{}'::jsonb,'{}'::jsonb,'{}'::jsonb,%s,%s::uuid)
                   ON CONFLICT (external_key) DO UPDATE SET
                       project_id=EXCLUDED.project_id,
                       title=EXCLUDED.title,
                       source_locator=EXCLUDED.source_locator,
                       raw_payload=EXCLUDED.raw_payload,
                       as_of=EXCLUDED.as_of,
                       workflow_state='QUARANTINED', visibility='private', updated_at=NOW()
                   RETURNING id::text, workflow_state""",
                (candidate["projectId"], candidate["title"], claim, sha256_text(claim),
                 candidate.get("sourceLocator") or None, candidate["externalKey"],
                 psycopg2.extras.Json(candidate), iso_datetime(candidate.get("asOf")), admin_id),
                one=True, write=True,
            )
            candidate_ids.append(str(row["id"]))
            updated += int(bool(existing))
            inserted += int(not existing)
        audit("evidence_observatory_notion_import", None, {
            "inputCount": normalized["inputCount"], "normalizedCount": normalized["normalizedCount"],
            "inserted": inserted, "updated": updated, "truthPromotions": 0,
            "candidateIds": candidate_ids[:100],
        })
        return jsonify({"ok": True, "inserted": inserted, "updated": updated,
                        "candidateIds": candidate_ids, "truthPromotions": 0,
                        "workflowState": WORKFLOW_QUARANTINED})

    @app.route("/api/admin/evidence-observatory/v1/cases/<case_id>/verify", methods=["POST"])
    @require_admin
    def observatory_verify(case_id: str):
        try:
            normalized_id = _safe_case_id(case_id)
        except ValueError:
            return jsonify({"ok": False, "error": "case_id_invalid"}), 400
        candidate = _candidate_case(query, normalized_id)
        if not candidate:
            return jsonify({"ok": False, "error": "case_not_found"}), 404
        payload = request.get_json(force=True) or {}
        claim = normalized_claim(payload.get("claim"))
        if claim != normalized_claim(candidate.get("claim")):
            return jsonify({"ok": False, "error": "candidate_claim_mismatch",
                            "expectedClaimSha256": candidate.get("claim_sha256"),
                            "actualClaimSha256": sha256_text(claim) if claim else None}), 409
        gate = evaluate_evidence_case(payload)
        passport = build_evidence_passport(payload, gate)
        case_sha = sha256_json({"payload": payload, "gate": gate, "passport": passport})
        target_state = WORKFLOW_PUBLISHABLE if gate["passed"] else WORKFLOW_QUARANTINED
        visibility = "public" if gate["passed"] else "private"
        row = query(
            """UPDATE evidence_observatory_cases
               SET verdict=%s, evidence_class=%s, workflow_state=%s, visibility=%s,
                   case_payload=%s::jsonb, gate_report=%s::jsonb, passport=%s::jsonb,
                   passport_sha256=%s, case_sha256=%s, as_of=%s, updated_at=NOW()
               WHERE id=%s::uuid
               RETURNING id::text, workflow_state, visibility, verdict,
                         evidence_class, claim_sha256, case_sha256, passport_sha256""",
            (str(payload.get("verdict") or "").upper(), str(payload.get("evidenceClass") or ""),
             target_state, visibility, psycopg2.extras.Json(payload), psycopg2.extras.Json(gate),
             psycopg2.extras.Json(passport), passport["passportSha256"], case_sha,
             iso_datetime(payload.get("asOf")), normalized_id), one=True, write=True,
        )
        audit("evidence_observatory_case_verified", normalized_id, {
            "passed": bool(gate["passed"]), "blockers": gate["blockers"],
            "gateSha256": gate["gateSha256"], "passportSha256": passport["passportSha256"],
            "caseSha256": case_sha, "workflowState": target_state,
        })
        return jsonify({"ok": bool(gate["passed"]), "case": dict(row), "gateReport": gate,
                        "evidencePassport": passport,
                        "truthNotice": "Gate success proves a reproducible evidence state, not that every claim is SUPPORTED."}), 200 if gate["passed"] else 409

    @app.route("/api/admin/evidence-observatory/v1/status", methods=["GET"])
    @require_admin
    def observatory_status():
        counts = query("SELECT workflow_state AS state, COUNT(*)::integer AS count FROM evidence_observatory_cases GROUP BY workflow_state ORDER BY workflow_state") or []
        publications = query("SELECT COUNT(*)::integer AS count, COUNT(*) FILTER (WHERE readback_verified=true)::integer AS verified FROM evidence_observatory_publish_receipts", one=True) or {}
        arena = query("SELECT COUNT(*)::integer AS count FROM evidence_observatory_arena_runs", one=True) or {}
        return jsonify({"ok": True,
                        "states": {str(row["state"]): int(row["count"]) for row in counts},
                        "publicationReceipts": int(publications.get("count") or 0),
                        "publicationReadbacksVerified": int(publications.get("verified") or 0),
                        "arenaRuns": int(arena.get("count") or 0),
                        "notionMode": "normalized-authenticated-import",
                        "huggingFaceMode": "runtime-identity-staging-with-readback",
                        "directRawCredentialIngress": False})

    @app.route("/api/admin/evidence-observatory/v1/publish/huggingface", methods=["POST"])
    @require_admin
    def observatory_publish_huggingface():
        repo_id = str(os.getenv("SOVEREIGN_HF_DATASET_REPO") or "Thorsu/sovereign-evidence-observatory").strip()
        revision = str(os.getenv("SOVEREIGN_HF_DATASET_REVISION") or "staging-atlas").strip()
        rows = query(
            """SELECT id::text, project_id, title, claim, claim_sha256, verdict,
                      evidence_class, workflow_state, visibility, source_kind,
                      source_locator, case_payload, gate_report, passport,
                      passport_sha256, case_sha256, as_of, created_at, updated_at, published_at
               FROM evidence_observatory_cases
               WHERE workflow_state='PUBLISHABLE' AND visibility='public'
               ORDER BY COALESCE(as_of, created_at) ASC, id ASC LIMIT 500"""
        ) or []
        if not rows:
            return jsonify({"ok": False, "error": "no_publishable_cases"}), 409
        projections: list[dict[str, Any]] = []
        case_ids: list[str] = []
        for raw_row in rows:
            row = dict(raw_row)
            payload = row.get("case_payload") if isinstance(row.get("case_payload"), dict) else {}
            gate = evaluate_evidence_case(payload)
            passport = build_evidence_passport(payload, gate)
            if not gate["passed"]:
                return jsonify({"ok": False, "error": "publish_gate_recheck_failed",
                                "caseId": row["id"], "blockers": gate["blockers"]}), 409
            if gate.get("gateSha256") != (row.get("gate_report") or {}).get("gateSha256"):
                return jsonify({"ok": False, "error": "publish_gate_hash_mismatch", "caseId": row["id"]}), 409
            if passport.get("passportSha256") != row.get("passport_sha256"):
                return jsonify({"ok": False, "error": "publish_passport_hash_mismatch", "caseId": row["id"]}), 409
            expected_case_sha = sha256_json({"payload": payload, "gate": gate, "passport": passport})
            if expected_case_sha != row.get("case_sha256"):
                return jsonify({"ok": False, "error": "publish_case_hash_mismatch", "caseId": row["id"]}), 409
            projections.append(_case_projection_for_publish(row))
            case_ids.append(row["id"])
        try:
            receipt = publish_huggingface_batch(rows=projections, repo_id=repo_id, revision=revision)
            admin_id = _admin_id(get_current_admin)
        except Exception as exc:
            audit("evidence_observatory_hf_publish_blocked", None, {
                "caseCount": len(case_ids), "repoId": repo_id, "revision": revision,
                "blocker": type(exc).__name__,
            })
            return jsonify({"ok": False, "error": str(exc)[:240], "readbackVerified": False}), 502
        persisted = query(
            """WITH receipt AS (
                   INSERT INTO evidence_observatory_publish_receipts
                       (batch_id, repo_id, revision, commit_oid, data_path, manifest_path,
                        data_sha256, manifest_sha256, case_ids, state, readback_verified, created_by)
                   VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'PUBLISHED',true,%s::uuid)
                   RETURNING id::text
               ), updated AS (
                   UPDATE evidence_observatory_cases
                   SET workflow_state='PUBLISHED', published_at=NOW(), updated_at=NOW()
                   WHERE id::text = ANY(%s) AND workflow_state='PUBLISHABLE'
                   RETURNING id::text
               )
               SELECT (SELECT id FROM receipt) AS receipt_id,
                      (SELECT COUNT(*)::integer FROM updated) AS updated_count""",
            (receipt["batchId"], receipt["repoId"], receipt["revision"], receipt["commitOid"],
             receipt["dataPath"], receipt["manifestPath"], receipt["dataSha256"],
             receipt["manifestSha256"], psycopg2.extras.Json(case_ids), admin_id, case_ids),
            one=True, write=True,
        )
        if int((persisted or {}).get("updated_count") or 0) != len(case_ids):
            return jsonify({"ok": False, "error": "publish_persistence_count_mismatch",
                            "readbackVerified": True, "expected": len(case_ids),
                            "updated": int((persisted or {}).get("updated_count") or 0)}), 500
        audit("evidence_observatory_hf_published", receipt["batchId"], {
            "caseCount": len(case_ids), "caseIds": case_ids, "repoId": receipt["repoId"],
            "revision": receipt["revision"], "commitOid": receipt["commitOid"],
            "dataSha256": receipt["dataSha256"], "manifestSha256": receipt["manifestSha256"],
            "readbackVerified": True,
        })
        return jsonify({**receipt, "publishedCaseIds": case_ids, "persistenceVerified": True})

    @app.route("/api/evidence-observatory/v1/arena/cases/<case_id>/request", methods=["GET"])
    @require_session
    def observatory_arena_request(case_id: str):
        try:
            normalized_id = _safe_case_id(case_id)
        except ValueError:
            return jsonify({"ok": False, "error": "case_id_invalid"}), 400
        case = _public_case(query, normalized_id)
        if not case:
            return jsonify({"ok": False, "error": "case_not_found"}), 404
        contract = arena_request(case)
        return jsonify({"ok": True, "caseId": normalized_id,
                        "messages": [{"role": "system", "content": contract["system"]},
                                     {"role": "user", "content": contract["input"]}],
                        "temperature": contract["temperature"],
                        "responseContract": contract["responseContract"],
                        "executionEndpoint": "/api/llm/chat",
                        "rawProviderCredentialRequired": False})

    @app.route("/api/evidence-observatory/v1/arena/score", methods=["POST"])
    @require_session
    def observatory_arena_score():
        body = request.get_json(force=True) or {}
        try:
            case_id = _safe_case_id(body.get("caseId"))
            llm_request_id = str(uuid.UUID(str(body.get("llmRequestId") or "").strip()))
        except (ValueError, AttributeError, TypeError):
            return jsonify({"ok": False, "error": "arena_identity_invalid"}), 400
        case = _public_case(query, case_id)
        if not case:
            return jsonify({"ok": False, "error": "case_not_found"}), 404
        settlement = query(
            """SELECT request_id::text, user_id::text, route_id, model_id, provider,
                      status, settled_credits, prompt_tokens, completion_tokens,
                      total_tokens, upstream_request_id, provider_cost_usd_micros, settled_at
               FROM llm_usage_settlements
               WHERE request_id=%s::uuid AND user_id=%s::uuid LIMIT 1""",
            (llm_request_id, request.session_user_id), one=True,
        )
        if not settlement:
            return jsonify({"ok": False, "error": "arena_llm_settlement_missing"}), 409
        settlement = dict(settlement)
        if str(settlement.get("status") or "") not in _SETTLED_ARENA_STATES:
            return jsonify({"ok": False, "error": "arena_llm_settlement_not_final",
                            "status": settlement.get("status")}), 409
        if body.get("routeId") and str(body.get("routeId")) != str(settlement.get("route_id") or ""):
            return jsonify({"ok": False, "error": "arena_route_identity_mismatch"}), 409
        if body.get("modelId") and str(body.get("modelId")) != str(settlement.get("model_id") or ""):
            return jsonify({"ok": False, "error": "arena_model_identity_mismatch"}), 409
        try:
            model_response = _arena_model_response(body.get("modelResponse"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        metrics = score_arena_response(case, model_response)
        response_sha = sha256_json(model_response)
        run_payload = {"caseSha256": case.get("case_sha256"), "caseId": case_id,
                       "llmRequestId": llm_request_id, "routeId": settlement.get("route_id"),
                       "modelId": settlement.get("model_id"), "provider": settlement.get("provider"),
                       "responseSha256": response_sha, "metrics": metrics}
        run_sha = sha256_json(run_payload)
        existing = query(
            """SELECT id::text, run_sha256, metrics FROM evidence_observatory_arena_runs
               WHERE user_id=%s::uuid AND llm_request_id=%s::uuid LIMIT 1""",
            (request.session_user_id, llm_request_id), one=True,
        )
        if existing:
            existing = dict(existing)
            if str(existing.get("run_sha256") or "") != run_sha:
                return jsonify({"ok": False, "error": "arena_run_replay_mismatch"}), 409
            return jsonify({"ok": True, "idempotent": True, "runId": existing["id"],
                            "runSha256": run_sha, "metrics": existing.get("metrics") or metrics})
        row = query(
            """INSERT INTO evidence_observatory_arena_runs
                   (case_id, user_id, route_id, model_id, provider, llm_request_id,
                    response_sha256, metrics, run_sha256, settlement_evidence)
               VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s::uuid,%s,%s::jsonb,%s,%s::jsonb)
               RETURNING id::text, created_at""",
            (case_id, request.session_user_id, str(settlement.get("route_id") or ""),
             str(settlement.get("model_id") or ""), str(settlement.get("provider") or ""),
             llm_request_id, response_sha, psycopg2.extras.Json(metrics), run_sha,
             psycopg2.extras.Json({"status": settlement.get("status"),
                                    "settledCredits": settlement.get("settled_credits"),
                                    "promptTokens": settlement.get("prompt_tokens"),
                                    "completionTokens": settlement.get("completion_tokens"),
                                    "totalTokens": settlement.get("total_tokens"),
                                    "upstreamRequestId": settlement.get("upstream_request_id"),
                                    "providerCostUsdMicros": settlement.get("provider_cost_usd_micros"),
                                    "settledAt": settlement.get("settled_at").isoformat() if settlement.get("settled_at") else None})),
            one=True, write=True,
        )
        return jsonify({"ok": True, "runId": row["id"], "runSha256": run_sha,
                        "metrics": metrics, "truthfulnessRanked": False}), 201

    @app.route("/api/evidence-observatory/v1/arena/leaderboard", methods=["GET"])
    def observatory_arena_leaderboard():
        rows = query(
            """SELECT model_id AS "modelId", provider, COUNT(*)::integer AS runs,
                      ROUND(AVG((metrics->>'overallScore')::numeric), 6)::float AS "overallScore",
                      ROUND(AVG((metrics->>'evidenceAdherence')::numeric), 6)::float AS "evidenceAdherence",
                      ROUND(AVG((metrics->>'citationPrecision')::numeric), 6)::float AS "citationPrecision",
                      ROUND(AVG((metrics->>'unsupportedClaimRate')::numeric), 6)::float AS "unsupportedClaimRate",
                      ROUND(AVG(CASE WHEN (metrics->>'abstentionCorrect')::boolean THEN 1 ELSE 0 END), 6)::float AS "correctAbstentionRate"
               FROM evidence_observatory_arena_runs
               GROUP BY model_id, provider
               ORDER BY "overallScore" DESC, runs DESC, model_id ASC LIMIT 100"""
        ) or []
        return jsonify({"ok": True, "entries": [dict(row) for row in rows],
                        "rankingScope": "evidence-discipline-on-versioned-observatory-cases",
                        "truthfulnessRanked": False})
