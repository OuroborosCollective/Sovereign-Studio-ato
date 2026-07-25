from __future__ import annotations

import pytest

from litellm_stack import LiteLLMStackRuntime


def test_legacy_litellm_runtime_is_permanently_fail_closed() -> None:
    assert LiteLLMStackRuntime.RETIRED is True
    assert LiteLLMStackRuntime.RETIREMENT_BLOCKER == "legacy_litellm_runtime_retired"
    assert LiteLLMStackRuntime.REPLACEMENT == "direct-openrouter-paid-and-direct-freellm-free"

    with pytest.raises(RuntimeError, match="legacy_litellm_runtime_retired"):
        LiteLLMStackRuntime()
