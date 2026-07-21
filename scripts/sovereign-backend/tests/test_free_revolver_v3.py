from __future__ import annotations

import json
import time
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from free_revolver_v3 import Revolver, RevolverProfile, plan_routes, validate_schema


def route(route_id: str, priority: int = 10) -> dict:
    return {
        "id": route_id,
        "model_id": f"alias-{route_id}",
        "provider": "litellm",
        "disabled": False,
        "priority": priority,
        "config": {
            "billingCategory": "free",
            "pricingVerified": True,
            "capabilities": ["chat", "structured_output"],
        },
    }


def test_weighted_plan_is_deterministic_for_same_request_and_revision() -> None:
    routes = [route("a"), route("b"), route("c")]
    profile = RevolverProfile(
        mode="weighted",
        route_weights_ppm={"a": 100_000, "b": 300_000, "c": 600_000},
        revision=7,
    )
    first = [item["id"] for item in plan_routes(routes, profile, "11111111-1111-1111-1111-111111111111")]
    second = [item["id"] for item in plan_routes(routes, profile, "11111111-1111-1111-1111-111111111111")]
    assert first == second
    assert sorted(first) == ["a", "b", "c"]


def test_race_returns_before_slow_loser_finishes() -> None:
    def call(selected: dict, payload: dict, timeout: float):
        if selected["id"] == "slow":
            time.sleep(0.4)
        else:
            time.sleep(0.03)
        return ({"choices": [{"message": {"content": "ok"}}]}, {"model": selected["id"]}, "")

    revolver = Revolver(call)
    started = time.monotonic()
    result = revolver.chat(
        [{"role": "user", "content": "hello"}],
        [route("slow", 1), route("fast", 2)],
        RevolverProfile(mode="race", race_n=2, timeout_ms=1000),
        request_id="22222222-2222-2222-2222-222222222222",
    )
    elapsed = time.monotonic() - started
    assert result.selected_route["id"] == "fast"
    assert elapsed < 0.2


def test_structured_schema_validation_is_fail_closed() -> None:
    schema = {
        "type": "object",
        "required": ["status", "count"],
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": ["ok"]},
            "count": {"type": "integer"},
        },
    }
    assert validate_schema({"status": "ok", "count": 2}, schema) == []
    errors = validate_schema({"status": "bad", "extra": True}, schema)
    assert "$.count: required" in errors
    assert "$.status: enum mismatch" in errors
    assert "$.extra: additional property" in errors


def test_chat_rejects_invalid_structured_winner_and_rotates() -> None:
    def call(selected: dict, payload: dict, timeout: float):
        content = json.dumps({"status": "bad"}) if selected["id"] == "a" else json.dumps({"status": "ok"})
        return ({"choices": [{"message": {"content": content}}]}, {}, "")

    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"type": "string", "enum": ["ok"]}},
    }
    result = Revolver(call).chat(
        [{"role": "user", "content": "json"}],
        [route("a", 1), route("b", 2)],
        RevolverProfile(mode="sequential", required_capabilities=("chat", "structured_output")),
        request_id="33333333-3333-3333-3333-333333333333",
        schema=schema,
    )
    assert result.selected_route["id"] == "b"
    assert [attempt.outcome for attempt in result.attempts] == ["schema_invalid", "success"]
