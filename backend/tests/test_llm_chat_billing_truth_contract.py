from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# Single source of truth: the live sovereign backend. backend/app.py was
# deliberately removed; contracts must pin the production implementation only.
PRODUCTION_APP = ROOT / "scripts" / "sovereign-backend" / "app.py"
APP_SOURCES = (PRODUCTION_APP,)
HELPERS = {
    "_llm_usage_credit_cost",
    "_estimate_llm_input_token_upper_bound",
    "_estimate_llm_request_tokens",
    "_resolve_enabled_llm_route",
}


def _load_helpers(
    path: Path,
    *,
    routes: tuple = (),
    selectable=lambda route: True,
    policy_error_model_ids: frozenset = frozenset(),
):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in HELPERS
    ]
    assert {node.name for node in selected} == HELPERS

    calls: list[tuple[str, tuple | None]] = []
    reconciles: list[bool] = []

    def query(sql: str, params=None, *, one=False, write=False):
        normalized = " ".join(sql.split())
        calls.append((normalized, params))
        assert write is False
        if "FROM llm_routes" in normalized and "disabled=false" in normalized:
            return [dict(route) for route in routes]
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def reconcile():
        reconciles.append(True)
        return (1, "")

    class BillingPolicyError(Exception):
        pass

    def route_billing_policy(route):
        if str(route.get("model_id") or "") in policy_error_model_ids:
            raise BillingPolicyError("route billing policy invalid")
        return {"billingCategory": "standard", "markupMultiplier": 1}

    namespace = {
        "_json": json,
        "query": query,
        "_reconcile_worker_routes_if_empty": reconcile,
        "_is_runtime_selectable_llm_route": selectable,
        "route_billing_policy": route_billing_policy,
        "BillingPolicyError": BillingPolicyError,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace, calls, reconciles, source


def _function_ast(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def _function_source(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    next_route = source.find("\n@app.route", start + 1)
    next_def = source.find("\ndef ", start + 1)
    candidates = [idx for idx in (next_route, next_def) if idx != -1]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_credit_cost_and_request_estimate_are_deterministic():
    messages = [{"role": "user", "content": "Hallo Runtime"}]
    for path in APP_SOURCES:
        namespace, _calls, _reconciles, _source = _load_helpers(path)
        cost = namespace["_llm_usage_credit_cost"]
        estimate = namespace["_estimate_llm_request_tokens"]
        upper_bound = namespace["_estimate_llm_input_token_upper_bound"]

        assert cost(0.001, 1024) == 1
        assert cost(1.0, 1001) == 2
        assert cost(-5, 1000) == 1

        # New truth: fail-closed byte-length upper bound plus framing and the
        # requested output budget (no longer the optimistic chars/4 estimate).
        serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        expected_input = max(1, len(serialized.encode("utf-8")) + 2048)
        assert upper_bound(messages) == expected_input
        assert estimate(messages, 250) == expected_input + 250

        # Byte semantics must stay fail-closed for multibyte content: the
        # bound counts UTF-8 bytes, not characters.
        multibyte = [{"role": "user", "content": "Hällö Wörld"}]
        multi_serialized = json.dumps(
            multibyte, ensure_ascii=False, separators=(",", ":")
        )
        char_len = len(multi_serialized)
        byte_len = len(multi_serialized.encode("utf-8"))
        assert byte_len > char_len
        assert upper_bound(multibyte) == max(1, byte_len + 2048)
        assert estimate(multibyte, 1) >= byte_len + 2048 + 1


def test_direct_chat_cannot_resolve_unlisted_or_disabled_model():
    listed_route = {
        "id": "route-1",
        "model_id": "@cf/meta/model",
        "provider": "openrouter",
        "credits_per_unit": 0.001,
    }
    for path in APP_SOURCES:
        # Unlisted model: the catalog returns nothing, resolution stays None.
        namespace, calls, reconciles, _source = _load_helpers(path)
        assert namespace["_resolve_enabled_llm_route"]("@cf/unlisted/model") is None
        assert reconciles == []
        route_query = calls[0][0]
        assert (
            "WHERE disabled=false AND lower(COALESCE(runtime_kind, provider)) "
            "IN ('openrouter', 'freellm') AND (model_id=%s OR id::text=%s)"
        ) in route_query

        # A route the direct runtime cannot select (disabled/unverified) is
        # skipped even when the catalog row matches the requested model.
        namespace, calls, reconciles, _source = _load_helpers(
            path, routes=(listed_route,), selectable=lambda route: False
        )
        assert namespace["_resolve_enabled_llm_route"]("@cf/meta/model") is None
        assert reconciles == []

        # A route whose billing policy is invalid is skipped fail-closed.
        namespace, calls, reconciles, _source = _load_helpers(
            path,
            routes=(listed_route,),
            policy_error_model_ids=frozenset({"@cf/meta/model"}),
        )
        assert namespace["_resolve_enabled_llm_route"]("@cf/meta/model") is None
        assert reconciles == []

        # A listed, runtime-selectable, policy-valid route resolves.
        namespace, calls, reconciles, _source = _load_helpers(
            path, routes=(listed_route,)
        )
        resolved = namespace["_resolve_enabled_llm_route"]("@cf/meta/model")
        assert resolved is not None
        assert resolved["model_id"] == "@cf/meta/model"
        assert reconciles == []


def test_empty_catalog_resolve_returns_none_without_implicit_reconcile():
    # New truth: _resolve_enabled_llm_route never reconciles implicitly. An
    # empty catalog resolves to None and the caller must block explicitly.
    for path in APP_SOURCES:
        namespace, calls, reconciles, _source = _load_helpers(path, routes=())
        route = namespace["_resolve_enabled_llm_route"]("@cf/meta/model")

        assert route is None
        assert reconciles == []
        assert len(calls) == 1
        assert "disabled=false" in calls[0][0]

        resolve_source = _function_source(
            path.read_text(encoding="utf-8"), "_resolve_enabled_llm_route"
        )
        assert "_reconcile_worker_routes_if_empty" not in resolve_source


def test_chat_reserves_credits_before_provider_and_refunds_failures():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        start = source.index("def public_llm_chat():")
        end = source.index('\n\nif __name__ == "__main__":', start)
        route_source = source[start:end]

        # Route gate stays fail-closed before any money moves.
        assert "route = _resolve_enabled_llm_route(model)" in route_source
        assert '"blocker": "llm_route_not_enabled"' in route_source
        assert '"blocker": "llm_billing_policy_invalid"' in route_source
        assert '"blocker": "free_route_revolver_exhausted"' in route_source
        assert "consume_step_up_approval(" in route_source

        # New settlement-based order: settlement row first, then the
        # provider-funded reservation, and only then the provider call.
        assert "_create_llm_usage_settlement(" in route_source
        assert '"blocker": "duplicate_llm_request_id"' in route_source
        assert "_reserve_provider_funded_llm_credits(" in route_source
        assert "fetch_direct_llm(" in route_source
        assert route_source.index("consume_step_up_approval(") < route_source.index(
            "_create_llm_usage_settlement("
        )
        assert route_source.index(
            "_create_llm_usage_settlement("
        ) < route_source.index("_reserve_provider_funded_llm_credits(")
        assert route_source.index(
            "_reserve_provider_funded_llm_credits("
        ) < route_source.index("fetch_direct_llm(")

        # The settlement is marked reserved before the provider is touched.
        assert 'status="reserved"' in route_source
        assert route_source.index('status="reserved"') < route_source.index(
            "fetch_direct_llm("
        )

        # Reservation failures are explicit blockers, never silent charges.
        assert '"blocker": "reservation_failed"' in route_source
        assert '_mark_llm_settlement_failed(request_id, "reservation_failed")' in route_source

        # Every post-reservation failure runs the refund path, and a failed
        # refund is itself an explicit blocker (never a fake success).
        assert "_refund_reserved_llm_credits(" in route_source
        assert route_source.count("refund_failed_run(") >= 3
        assert '"blocker": "refund_failed"' in route_source
        assert '_mark_llm_settlement_failed(request_id, "refund_failed")' in route_source
        assert '"blocker": "settlement_failed"' in route_source

        # Final billing is settlement-based on provider-reported evidence.
        assert "_settle_llm_usage(" in route_source
        assert route_source.index("fetch_direct_llm(") < route_source.index(
            "_settle_llm_usage("
        )

        # The reservation and refund helpers stay idempotent per request id.
        reserve_source = _function_source(source, "_reserve_provider_funded_llm_credits")
        assert "_apply_credit_delta(" in reserve_source
        assert 'provider_tx_id=f"{request_id}:reservation"' in reserve_source
        refund_source = _function_source(source, "_refund_reserved_llm_credits")
        assert "_apply_credit_delta(" in refund_source
        assert 'provider_tx_id=f"{request_id}:refund"' in refund_source

        # Settlement pins charge basis to verified provider evidence only.
        settle_source = _function_source(source, "_settle_llm_usage")
        assert '"chargeBasis": charge_basis' in settle_source
        assert 'charge_basis = "direct_provider_reported_cost"' in settle_source
        assert 'charge_basis = "verified_usage_and_route_prices"' in settle_source


def test_separate_deduct_endpoint_rejects_client_reported_llm_tokens():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        deduct_source = _function_source(source, "user_billing_deduct")

        # New truth: the deduct endpoint must never convert client-reported
        # LLM token counts into credits; LLM usage is settlement-only.
        assert "_llm_usage_credit_cost(" not in deduct_source
        assert '"blocker": "llm_usage_requires_provider_settlement"' in deduct_source
        assert '"requiredEndpoint": "/api/llm/chat"' in deduct_source

        # Fixed non-LLM tool costs remain deterministic and server-side.
        assert '"tool_vps_exec": 5' in deduct_source
        assert '"tool_github_pr": 10' in deduct_source
        assert '"tool_repo_load": 3' in deduct_source
        assert "amount = fixed_costs[cost_id]" in deduct_source
        assert '"error": "unknown_cost_id"' in deduct_source
        assert "consume_step_up_approval(" in deduct_source
        assert "_apply_credit_delta(" in deduct_source


def test_billing_helpers_exist_in_single_production_source():
    # Single source of truth: the removed backend/app.py must stay absent and
    # every billing helper must live in the production backend.
    assert not (ROOT / "backend" / "app.py").exists()
    names = HELPERS | {
        "_refund_reserved_llm_credits",
        "_reserve_provider_funded_llm_credits",
        "_create_llm_usage_settlement",
        "_settle_llm_usage",
        "public_llm_chat",
    }
    for name in names:
        assert _function_ast(PRODUCTION_APP, name)
