from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def test_repository_execution_has_no_sovereign_github_oauth_or_clone_authority() -> None:
    routes = source("backend/agent_runtime/routes.py")
    runtime = source("backend/agent_runtime/repository_execution.py")
    a2a = source("backend/agent_runtime/agent_zero_a2a.py")

    repo_route = section(
        routes,
        'def user_start_repository_execution():',
        '@app.route("/api/user/agent/jobs", methods=["POST"])',
    )
    assert "_github_access_token_for_session" not in repo_route
    assert "GITHUB_CREDENTIAL_FORBIDDEN_ON_EXECUTION" in repo_route
    assert "github_access_token=" not in repo_route

    start_runtime = section(
        runtime,
        "def start_repository_execution(",
        "def _submit_pending_repository_job(",
    )
    assert "github_access_token" not in start_runtime
    assert "clone_repo=False" in start_runtime
    assert "agent_zero_repository_access_delegated" in start_runtime
    assert "clone_repo=True" not in start_runtime

    assert "repository_url: str" in a2a
    assert "branch: str" in a2a
    assert "Agent Zero's own configured GitHub/repository capability" in a2a
    assert "Never request, read, accept, or use a Sovereign" in a2a
    assert "GitHub Coding Agent" in a2a
    assert "Jules task" in a2a


def test_legacy_swarm_and_controller_cannot_execute_repositories() -> None:
    swarm = source("backend/agent_runtime/cognitive_swarm_routes.py")
    controller = source("scripts/sovereign-backend/controller_board.py")

    assert "REPOSITORY_EXECUTION_REQUIRES_AGENT_ZERO_A2A_ROUTE" in swarm
    assert "create_sovereign_agent_job(" not in swarm
    assert "clone_repo=True" not in swarm
    assert "resolve_request_github_token" not in swarm

    assert "start_repository_execution(" in controller
    assert "create_sovereign_agent_job(" not in controller
    assert "clone_repo=True" not in controller
    assert "resolve_request_github_token(" not in controller
    assert '"billingRouteUsed": False' in controller
    assert '"githubOAuthUsed": False' in controller


def test_frontend_execution_payload_cannot_carry_github_token() -> None:
    client = source("src/features/product/runtime/sovereignAgentClient.ts")
    builder = source("src/features/product/containers/BuilderContainer.tsx")
    release = source("src/features/release/PlayReleaseChat.tsx")

    repo_input = section(
        client,
        "export interface SovereignRepositoryExecutionInput",
        "export interface SovereignDesktopFrameObservation",
    )
    assert "githubAccessToken" not in repo_input

    repo_start = section(
        client,
        "async startRepositoryExecution(",
        "async listJobs(",
    )
    assert "githubAccessToken" not in repo_start
    assert "'/api/user/agent/repository/run'" in repo_start

    builder_start = section(
        builder,
        "const startAgentFromText",
        "const publishConfirmedDraftPr",
    )
    assert "githubAccessToken: githubTokenRef.current" not in builder_start
    assert "hasCurrentGitHubWriteEvidence()" not in builder_start

    release_execution = section(
        release,
        "const executeRepositoryAction",
        "const confirmPendingRepositoryAction",
    )
    assert "githubAccessToken" not in release_execution

    publication = section(
        release,
        "const publishDraftForJob",
        "const executeRepositoryAction",
    )
    assert "createDraftPr(snapshot.jobId, githubAccessToken)" in publication


def test_shipping_backend_is_byte_equal_to_canonical_execution_boundary() -> None:
    for canonical, shipping in (
        ("backend/agent_runtime/routes.py", "scripts/sovereign-backend/agent_runtime/routes.py"),
        ("backend/agent_runtime/repository_execution.py", "scripts/sovereign-backend/agent_runtime/repository_execution.py"),
        ("backend/agent_runtime/agent_zero_a2a.py", "scripts/sovereign-backend/agent_runtime/agent_zero_a2a.py"),
        ("backend/agent_runtime/cognitive_swarm_routes.py", "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py"),
    ):
        assert source(canonical) == source(shipping)
