"""Live PostgreSQL control and evidence surface for Sovereign Free Revolver v3."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable, Mapping

from flask import jsonify, request

from free_revolver_v3 import RevolverProfile, eligible_free_routes, plan_routes
from llm_cost_policy import BillingPolicyError, route_billing_policy

FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS = max(
    1,
    min(int(os.getenv("FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS", "24")), 168),
)


def _load_profile(query: Callable[..., Any], tenant_id: str | None, profile_key: str) -> RevolverProfile:
    row = query(
        """SELECT profile_key, mode, race_n, timeout_ms, token_budget,
                  required_capabilities, preferred_route_ids, route_weights,
                  structured_repair_attempts, semantic_cache_enabled, revision
           FROM llm_revolver_profiles
           WHERE enabled=true AND profile_key=%s
             AND (tenant_id=%s::uuid OR tenant_id IS NULL)
           ORDER BY tenant_id NULLS LAST
           LIMIT 1""",
        (profile_key, tenant_id),
        one=True,
    )
    if not row:
        return RevolverProfile(profile_key=profile_key)
    return RevolverProfile.from_mapping({
        "profileKey": row.get("profile_key"),
        "mode": row.get("mode"),
        "raceN": row.get("race_n"),
        "timeoutMs": row.get("timeout_ms"),
        "tokenBudget": row.get("token_budget"),
        "requiredCapabilities": row.get("required_capabilities"),
        "preferredRouteIds": row.get("preferred_route_ids"),
        "routeWeights": row.get("route_weights"),
        "structuredRepairAttempts": row.get("structured_repair_attempts"),
        "semanticCacheEnabled": row.get("semantic_cache_enabled"),
        "revision": row.get("revision"),
    })


def resolve_free_revolver_plan(
    query: Callable[..., Any],
    *,
    tenant_id: str | None,
    request_id: str,
    profile_key: str = "default-free",
    capabilities: tuple[str, ...] = ("chat",),
) -> tuple[RevolverProfile, list[dict[str, Any]]]:
    profile = _load_profile(query, tenant_id, profile_key)
    if capabilities:
        profile = RevolverProfile(
            profile_key=profile.profile_key,
            mode=profile.mode,
            race_n=profile.race_n,
            timeout_ms=profile.timeout_ms,
            token_budget=profile.token_budget,
            required_capabilities=capabilities,
            preferred_route_ids=profile.preferred_route_ids,
            route_weights_ppm=profile.route_weights_ppm,
            structured_repair_attempts=profile.structured_repair_attempts,
            semantic_cache_enabled=profile.semantic_cache_enabled,
            revision=profile.revision,
        )
    rows = query(
        """SELECT route.id::text, route.model_id, route.model_name,
                  route.provider, route.disabled, route.priority, route.config
           FROM llm_routes AS route
           LEFT JOIN llm_revolver_provider_models AS provider_model
             ON provider_model.litellm_alias=route.model_id
           LEFT JOIN llm_revolver_provider_sources AS provider_source
             ON provider_source.id=provider_model.source_id
           WHERE route.disabled=false AND lower(route.provider)='litellm'
             AND (
               COALESCE(route.config->>'routingOwner','') <> 'free-revolver-v3'
               OR (
                 provider_model.free_verified=true
                 AND provider_model.enabled=true
                 AND provider_model.status='ready'
                 AND provider_model.pricing_verified_at >=
                     NOW() - (%s * INTERVAL '1 hour')
                 AND provider_source.enabled=true
                 AND provider_source.status IN ('healthy','degraded')
               )
             )
           ORDER BY route.priority ASC, route.model_name ASC
           LIMIT 100""",
        (FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS,),
    ) or []
    verified: list[dict[str, Any]] = []
    for source in rows:
        route = dict(source)
        try:
            policy = route_billing_policy(route)
        except BillingPolicyError:
            continue
        if policy["billingCategory"] == "free":
            verified.append(route)
    return profile, plan_routes(verified, profile, request_id)


def register_free_revolver_runtime(
    app: Any,
    *,
    require_admin: Callable[..., Any],
    query: Callable[..., Any],
    audit: Callable[..., Any],
) -> None:
    @app.route("/api/admin/llm/revolver-v3", methods=["GET"])
    @require_admin
    def admin_free_revolver_v3():
        profile_key = str(request.args.get("profileKey") or "default-free")[:120]
        request_id = str(uuid.uuid4())
        profile, routes = resolve_free_revolver_plan(
            query,
            tenant_id=None,
            request_id=request_id,
            profile_key=profile_key,
        )
        stats = query(
            """SELECT COUNT(*)::integer AS attempts,
                      COUNT(*) FILTER (WHERE outcome='success')::integer AS successes,
                      (SELECT COUNT(*)::integer
                         FROM llm_revolver_structured_evidence
                        WHERE valid=false AND observed_at >= NOW() - INTERVAL '24 hours') AS schema_invalid,
                      COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at-started_at))*1000),0)::float AS avg_latency_ms
               FROM llm_route_attempts
               WHERE completed_at >= NOW() - INTERVAL '24 hours'""",
            one=True,
        ) or {}
        recommendations = query(
            """SELECT profile_key AS "profileKey", route_id AS "routeId",
                      recommended_weight_ppm AS "recommendedWeightPpm",
                      evidence, created_at AS "createdAt"
               FROM llm_revolver_bandit_recommendations
               WHERE approved=false
               ORDER BY created_at DESC LIMIT 50"""
        ) or []
        return jsonify({
            "ok": True,
            "schemaVersion": "sovereign.free-revolver-v3.admin.v1",
            "requestId": request_id,
            "truthOwner": "postgresql-litellm-runtime-evidence",
            "profile": {
                "profileKey": profile.profile_key,
                "mode": profile.mode,
                "raceN": profile.race_n,
                "timeoutMs": profile.timeout_ms,
                "tokenBudget": profile.token_budget,
                "requiredCapabilities": list(profile.required_capabilities),
                "preferredRouteIds": list(profile.preferred_route_ids),
                "routeWeightsPpm": dict(profile.route_weights_ppm),
                "structuredRepairAttempts": profile.structured_repair_attempts,
                "semanticCacheEnabled": profile.semantic_cache_enabled,
                "revision": profile.revision,
            },
            "plannedRoutes": [{
                "id": str(route.get("id") or ""),
                "modelId": str(route.get("model_id") or ""),
                "modelName": str(route.get("model_name") or ""),
                "priority": int(route.get("priority") or 0),
                "quotaScope": str((route.get("config") or {}).get("quotaScope") or ""),
            } for route in routes],
            "stats24h": {
                "attempts": int(stats.get("attempts") or 0),
                "successes": int(stats.get("successes") or 0),
                "schemaInvalid": int(stats.get("schema_invalid") or 0),
                "averageLatencyMs": float(stats.get("avg_latency_ms") or 0),
            },
            "banditRecommendations": [dict(item) for item in recommendations],
            "semanticCachePolicy": "disabled-unless-cache_safe-capability-and-tenant-scope",
            "pricingEvidenceTtlHours": FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS,
            "kubernetesSidecar": False,
        })

    @app.route("/api/admin/llm/revolver-v3/profiles/<profile_key>", methods=["PATCH"])
    @require_admin
    def admin_update_free_revolver_profile(profile_key: str):
        body = request.get_json(force=True) or {}
        mode = str(body.get("mode") or "sequential").lower()
        if mode == "race":
            return jsonify({
                "error": "race is implemented and tested but not enabled on the billed live path",
                "blocker": "race_cost_settlement_not_enabled",
            }), 409
        if mode not in {"sequential", "weighted"}:
            return jsonify({"error": "mode must be sequential or weighted"}), 400
        race_n = max(1, min(int(body.get("raceN") or 3), 8))
        timeout_ms = max(1000, min(int(body.get("timeoutMs") or 30000), 120000))
        token_budget = max(128, min(int(body.get("tokenBudget") or 32000), 256000))
        required = body.get("requiredCapabilities") or ["chat"]
        preferred = body.get("preferredRouteIds") or []
        weights = body.get("routeWeightsPpm") or {}
        repairs = max(0, min(int(body.get("structuredRepairAttempts") or 1), 3))
        semantic = bool(body.get("semanticCacheEnabled", False))
        if semantic and "cache_safe" not in required:
            return jsonify({
                "error": "semantic cache requires cache_safe capability",
                "blocker": "semantic_cache_capability_required",
            }), 409
        row = query(
            """INSERT INTO llm_revolver_profiles
                   (tenant_id, profile_key, mode, race_n, timeout_ms, token_budget,
                    required_capabilities, preferred_route_ids, route_weights,
                    structured_repair_attempts, semantic_cache_enabled, revision)
               VALUES (NULL,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,1)
               ON CONFLICT (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), profile_key)
               DO UPDATE SET mode=EXCLUDED.mode, race_n=EXCLUDED.race_n,
                   timeout_ms=EXCLUDED.timeout_ms, token_budget=EXCLUDED.token_budget,
                   required_capabilities=EXCLUDED.required_capabilities,
                   preferred_route_ids=EXCLUDED.preferred_route_ids,
                   route_weights=EXCLUDED.route_weights,
                   structured_repair_attempts=EXCLUDED.structured_repair_attempts,
                   semantic_cache_enabled=EXCLUDED.semantic_cache_enabled,
                   revision=llm_revolver_profiles.revision+1, updated_at=NOW()
               RETURNING id::text, revision""",
            (profile_key[:120], mode, race_n, timeout_ms, token_budget,
             json.dumps(required), json.dumps(preferred), json.dumps(weights), repairs, semantic),
            one=True,
            write=True,
        )
        audit("admin_update_free_revolver_v3_profile", str(row.get("id") or ""), {
            "profileKey": profile_key[:120], "mode": mode, "revision": int(row.get("revision") or 1)
        })
        return jsonify({"ok": True, "profileKey": profile_key[:120], "revision": int(row.get("revision") or 1)})
