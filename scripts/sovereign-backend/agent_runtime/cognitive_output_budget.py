"""Secret-safe output-budget diagnostics for routed Agents SDK responses.

The runtime must distinguish provider unavailability from a request that executed
but exhausted its bounded visible-output budget.  This module only inspects
bounded metadata (finish reason and token counters); it never persists raw model
output or provider error text.
"""

from __future__ import annotations

from typing import Any, Final

# One bounded ceiling shared by SDK requests, diagnostics and paid reservations.
# Reasoning tokens consume the same completion budget as the visible JSON.
AGENT_OUTPUT_TOKEN_LIMIT: Final[int] = 8_192

_LENGTH_REASONS: Final[frozenset[str]] = frozenset(
    {"length", "max_tokens", "max_output_tokens", "max_completion_tokens"}
)


def _value(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _candidate_objects(value: Any) -> list[Any]:
    candidates: list[Any] = [value]
    response = _value(value, "response")
    if response is not None and response is not value:
        candidates.append(response)
    raw_responses = _value(value, "raw_responses")
    if isinstance(raw_responses, (list, tuple)):
        candidates.extend(reversed(raw_responses))
    return [candidate for candidate in candidates if candidate is not None]


def _finish_reason(value: Any) -> str:
    for candidate in _candidate_objects(value):
        direct = _value(candidate, "finish_reason") or _value(candidate, "finishReason")
        if direct:
            return str(direct).strip().casefold()[:80]
        choices = _value(candidate, "choices")
        if isinstance(choices, (list, tuple)):
            for choice in reversed(choices):
                direct = _value(choice, "finish_reason") or _value(choice, "finishReason")
                if direct:
                    return str(direct).strip().casefold()[:80]
        status = str(_value(candidate, "status") or "").strip().casefold()
        incomplete = _value(candidate, "incomplete_details") or _value(
            candidate, "incompleteDetails"
        )
        reason = _value(incomplete, "reason")
        if status == "incomplete" and reason:
            return str(reason).strip().casefold()[:80]
    return ""


def _usage_candidates(value: Any) -> list[Any]:
    usages: list[Any] = []
    context = _value(value, "context_wrapper")
    context_usage = _value(context, "usage")
    if context_usage is not None:
        usages.append(context_usage)
    direct_usage = _value(value, "usage")
    if direct_usage is not None:
        usages.append(direct_usage)
    for candidate in _candidate_objects(value):
        usage = _value(candidate, "usage")
        if usage is not None:
            usages.append(usage)
    return usages


def _token_evidence(value: Any) -> tuple[int, int]:
    completion_tokens = 0
    reasoning_tokens = 0
    for usage in _usage_candidates(value):
        completion_tokens = max(
            completion_tokens,
            _nonnegative_int(_value(usage, "output_tokens")),
            _nonnegative_int(_value(usage, "completion_tokens")),
        )
        for details_name in ("output_tokens_details", "completion_tokens_details"):
            details = _value(usage, details_name)
            reasoning_tokens = max(
                reasoning_tokens,
                _nonnegative_int(_value(details, "reasoning_tokens")),
            )
    return completion_tokens, reasoning_tokens


def assess_output_budget_evidence(
    value: Any,
    *,
    output_token_limit: int,
) -> dict[str, object]:
    """Return bounded evidence that a completed request exhausted its output budget.

    `budgetExhausted` is deliberately diagnostic rather than a model-quality or
    provider-health verdict.  It becomes true when the provider reports an
    explicit length/max-output finish, or when a reasoning-bearing response uses
    the full configured output limit.  Callers should use it only while handling
    an invalid/partial result or provider exception, never to reject a result that
    already satisfies its output contract.
    """

    limit = max(0, int(output_token_limit or 0))
    finish_reason = _finish_reason(value)
    completion_tokens, reasoning_tokens = _token_evidence(value)
    explicit_length = finish_reason in _LENGTH_REASONS
    full_reasoning_budget = bool(
        limit > 0
        and completion_tokens >= limit
        and reasoning_tokens > 0
    )
    return {
        "schemaVersion": "sovereign.output-budget-diagnostic.v1",
        "budgetExhausted": bool(explicit_length or full_reasoning_budget),
        "finishReason": finish_reason or None,
        "completionTokens": completion_tokens,
        "reasoningTokens": reasoning_tokens,
        "outputTokenLimit": limit,
        "explicitLengthFinish": explicit_length,
        "fullReasoningBudgetObserved": full_reasoning_budget,
        "rawOutputPersisted": False,
        "truthVerdict": "NOT_ASSERTED",
    }
