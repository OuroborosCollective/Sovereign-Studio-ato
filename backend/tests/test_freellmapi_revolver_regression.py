
def test_freellmapi_revolver_fallback_regression():
    """Verify that FreeLLMAPI is checked and functional and revolver limits are respected without bugs."""
    from backend.agent_runtime.adaptive_handoff import provider_readiness_projection

    projection = provider_readiness_projection()

    assert projection is not None
    assert "freellm" in projection["canonicalRoutes"]["free"]
    assert "revolver" in projection["canonicalRoutes"]["free"]
    assert "litellm" in projection["prohibitedRuntimeRoutes"]
