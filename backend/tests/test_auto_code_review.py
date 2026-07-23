import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime import auto_code_review as review


def free_route(route_id: str = "free-1") -> dict:
    return {
        "id": route_id,
        "runtime_kind": "freellm",
        "provider": "freellm",
        "model_id": "free/model",
        "base_url": "http://freellmapi:3001/v1",
        "config": {"transport": "freellm", "executionProfile": "free_single_agent", "direct": True},
    }


def paid_route(route_id: str = "paid-1") -> dict:
    return {
        "id": route_id,
        "runtime_kind": "openrouter",
        "provider": "openrouter",
        "model_id": "openai/gpt-mini",
        "base_url": "https://openrouter.ai/api/v1",
        "config": {"transport": "openrouter", "executionProfile": "paid_swarm_6"},
    }


def resolution(primary: dict, *candidates: dict):
    return SimpleNamespace(
        primary_route=primary,
        candidate_routes=tuple(candidates or (primary,)),
        requested_mode="auto",
    )


def test_truncate_keeps_short_diff():
    assert review._truncate_diff("abc", 300) == "abc"


def test_truncate_keeps_both_diff_edges():
    value = "a" * 400 + "z" * 400
    result = review._truncate_diff(value, 300)
    assert result.startswith("a") and result.endswith("z")
    assert "diff truncated" in result


def test_review_prompt_contains_actual_diff():
    prompt = review._build_review_prompt(review.AutoCodeReviewInput(diff_text="+secure", mission="fix", changed_files=("a.py",)))
    assert "Actual git diff" in prompt and "+secure" in prompt and "a.py" in prompt


def test_extract_accepts_plain_json_array():
    payload, valid = review._extract_findings_payload("[]")
    assert valid is True and payload == []


def test_extract_accepts_json_array_inside_text():
    payload, valid = review._extract_findings_payload('result: [{"severity":"LOW"}] done')
    assert valid is True and isinstance(payload, list)


def test_extract_rejects_object_payload():
    payload, valid = review._extract_findings_payload('{}')
    assert valid is False and payload is None


def test_extract_rejects_invalid_text():
    payload, valid = review._extract_findings_payload('not-json')
    assert valid is False and payload is None


def test_parse_normalizes_unknown_severity_and_category():
    findings = review._parse_findings('[{"severity":"CRITICAL","category":"other","file":"a","description":"x"}]')
    assert findings[0].severity == "LOW"
    assert findings[0].category == "quality"


def test_parse_drops_empty_description():
    assert review._parse_findings('[{"severity":"HIGH","description":""}]') == ()


def test_parse_bounds_findings_to_fifty():
    raw = str([{"severity": "LOW", "category": "style", "file": "a", "description": str(i)} for i in range(70)]).replace("'", '"')
    assert len(review._parse_findings(raw)) == 50


def test_count_by_severity():
    findings = (
        review.AutoCodeReviewFinding("HIGH", "security", "a", "1", "h"),
        review.AutoCodeReviewFinding("MEDIUM", "quality", "b", "2", "m"),
        review.AutoCodeReviewFinding("LOW", "style", "c", "3", "l"),
    )
    assert review._count_by_severity(findings) == (1, 1, 1)


def test_candidates_keep_one_paid_then_free_revolver():
    candidates = review._candidate_routes(resolution(paid_route(), paid_route(), free_route("f1"), free_route("f2")))
    assert [route["id"] for route in candidates] == ["paid-1", "f1", "f2"]


def test_candidates_deduplicate_route_ids():
    candidates = review._candidate_routes(resolution(free_route("f1"), free_route("f1"), free_route("f2")))
    assert [route["id"] for route in candidates] == ["f1", "f2"]


def test_empty_diff_blocks_without_route_lookup(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: pytest.fail("must not resolve"))
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text=""), get_connection=lambda: None, user_id="u")
    assert result.decision == "blocked_unavailable" and result.passed is False


def test_missing_user_blocks_without_route_lookup(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: pytest.fail("must not resolve"))
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="")
    assert result.error == "authenticated user id is required"


def test_no_resolution_blocks(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: None)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.error == "NO_VERIFIED_REVIEW_ROUTE_READY"


def test_resolution_error_is_secret_safe(monkeypatch):
    def fail(*args, **kwargs):
        raise review.ExecutionResolutionError("no_route", "not ready", status_code=503)
    monkeypatch.setattr(review, "load_execution_resolution", fail)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.error == "ExecutionResolutionError"


def test_free_route_passes_without_openrouter_billing(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route()))
    async def run_route(**kwargs):
        assert kwargs["stage_billing"] is None
        return "[]"
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.passed is True and result.resolved_transport == "freellm"


def test_free_revolver_advances_after_first_failure(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route("f1"), free_route("f1"), free_route("f2")))
    attempts = []
    async def run_route(**kwargs):
        attempts.append(kwargs["route"]["id"])
        if kwargs["route"]["id"] == "f1":
            raise RuntimeError("quota")
        return "[]"
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert attempts == ["f1", "f2"] and result.fallback_used is True and result.passed is True


def test_paid_route_uses_billing(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(paid_route()))
    created = []
    class Billing:
        def __init__(self, **kwargs):
            created.append(kwargs)
    monkeypatch.setattr(review, "AgentStageBilling", Billing)
    async def run_route(**kwargs):
        assert isinstance(kwargs["stage_billing"], Billing)
        return "[]"
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x", job_id="j"), get_connection=lambda: None, user_id="u")
    assert result.passed is True and created and result.resolved_transport == "openrouter"


def test_high_finding_blocks_draft_pr(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route()))
    async def run_route(**kwargs):
        return '[{"severity":"HIGH","category":"security","file":"a.py","line_hint":"1","description":"secret exposure"}]'
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.decision == "blocked_high" and result.high_count == 1 and result.passed is False


def test_medium_and_low_findings_do_not_block(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route()))
    async def run_route(**kwargs):
        return '[{"severity":"MEDIUM","category":"quality","file":"a.py","line_hint":"2","description":"risk"},{"severity":"LOW","category":"style","file":"a.py","line_hint":"3","description":"style"}]'
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.passed is True and result.medium_count == 1 and result.low_count == 1


def test_invalid_model_output_advances_to_next_free_route(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route("f1"), free_route("f1"), free_route("f2")))
    outputs = iter(["invalid", "[]"])
    async def run_route(**kwargs):
        return next(outputs)
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.passed is True and result.attempted_route_count == 2


def test_all_routes_failed_blocks(monkeypatch):
    monkeypatch.setattr(review, "load_execution_resolution", lambda *args, **kwargs: resolution(free_route("f1"), free_route("f1"), free_route("f2")))
    async def run_route(**kwargs):
        raise RuntimeError("down")
    monkeypatch.setattr(review, "_run_review_route", run_route)
    result = review.auto_code_review(review.AutoCodeReviewInput(diff_text="+x"), get_connection=lambda: None, user_id="u")
    assert result.decision == "blocked_unavailable" and result.attempted_route_count == 2


def test_signal_contains_no_secret_fields():
    result = review.AutoCodeReviewResult("passed", True, "ok", (), 0, 0, 0, "model", "freellm", "route", False, 1, "")
    signal = review.auto_code_review_signal(result)
    assert signal["secretValuesReturned"] is False
    assert "apiKey" not in signal and "token" not in signal


def test_review_prompt_redacts_generated_github_credential():
    credential = "_".join(("github", "pat", "x" * 40))
    prompt = review._build_review_prompt(review.AutoCodeReviewInput(diff_text=f"+token={credential}"))
    assert credential not in prompt
    assert "[REDACTED_SECRET]" in prompt


def test_review_prompt_redacts_generated_bearer_credential():
    credential = "".join(("Bear", "er ", "a" * 40))
    prompt = review._build_review_prompt(review.AutoCodeReviewInput(diff_text=f"+header={credential}"))
    assert credential not in prompt
    assert "[REDACTED_SECRET]" in prompt


def test_model_findings_are_redacted_before_api_projection():
    credential = "_".join(("github", "pat", "y" * 40))
    raw = json.dumps([{
        "severity": "HIGH",
        "category": "security",
        "file": "a.py",
        "line_hint": "1",
        "description": f"exposed {credential}",
    }])
    findings = review._parse_findings(raw)
    assert credential not in findings[0].description
    assert "[REDACTED_SECRET]" in findings[0].description


def test_backend_and_deployment_reviewer_are_exact_mirrors():
    canonical = (ROOT / "backend" / "agent_runtime" / "auto_code_review.py").read_text(encoding="utf-8")
    deployed = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "auto_code_review.py").read_text(encoding="utf-8")
    assert canonical == deployed


def test_backend_and_deployment_routes_are_exact_mirrors():
    canonical = (ROOT / "backend" / "agent_runtime" / "routes.py").read_text(encoding="utf-8")
    deployed = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "routes.py").read_text(encoding="utf-8")
    assert canonical == deployed


def test_draft_pr_prepare_is_guarded_by_real_auto_review_route():
    routes = (ROOT / "backend" / "agent_runtime" / "routes.py").read_text(encoding="utf-8")
    assert '/api/user/agent/jobs/<job_id>/review' in routes
    assert 'review = _review_job_diff(job, user_id)' in routes
    assert 'if not review.passed:' in routes
    assert '"autoCodeReview": review_signal' in routes


def test_new_reviewer_contains_no_litellm_transport_path():
    source = (ROOT / "backend" / "agent_runtime" / "auto_code_review.py").read_text(encoding="utf-8").lower()
    assert "litellm" not in source
    assert "openrouter" in source
    assert "freellm" in source
