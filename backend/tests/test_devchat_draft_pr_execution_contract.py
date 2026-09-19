from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "backend" / "agent_runtime" / "cognitive_swarm_routes.py"
MIRROR = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "cognitive_swarm_routes.py"
APP = ROOT / "src" / "App.tsx"
DRAFT_FLOW_TEST = ROOT / "src" / "App.draftPrFlow.test.tsx"
BUILDER = ROOT / "src" / "features" / "product" / "containers" / "BuilderContainer.tsx"
CLIENT = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentClient.ts"
RUNTIME = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentRuntime.ts"
REPO_BRIDGE = ROOT / "src" / "features" / "product" / "runtime" / "devChatWorkerBridge.ts"
ENGINE_BOUNDARY = ROOT / "src" / "features" / "product" / "runtime" / "sovereignEngineBoundary.ts"
BACKEND_APP = ROOT / "scripts" / "sovereign-backend" / "app.py"


def test_swarm_route_rejects_repository_execution_and_github_credentials() -> None:
    source = CANONICAL.read_text("utf-8")

    assert "REPOSITORY_EXECUTION_REQUIRES_AGENT_ZERO_A2A_ROUTE" in source
    assert "USE_AGENT_ZERO_REPOSITORY_EXECUTION_ROUTE" in source
    assert "_start_run_without_github_authority" in source
    assert "_start_run_with_session_github_token" not in source
    assert "resolve_request_github_token" not in source
    assert "create_sovereign_agent_job(" not in source
    assert "clone_repo=True" not in source


def test_repository_execution_is_owned_by_canonical_agent_zero_route() -> None:
    runtime = (ROOT / "backend" / "agent_runtime" / "repository_execution.py").read_text("utf-8")
    a2a = (ROOT / "backend" / "agent_runtime" / "agent_zero_a2a.py").read_text("utf-8")

    assert "clone_repo=False" in runtime
    assert "agent_zero_repository_access_delegated" in runtime
    assert "github_access_token" not in runtime.split("def start_repository_execution(", 1)[1].split("def _submit_pending_repository_job(", 1)[0]
    assert "Agent Zero's own configured GitHub/repository capability" in a2a
    assert "GitHub Coding Agent" in a2a
    assert "githubAccessToken" in a2a


def test_deployment_mirror_matches_canonical_swarm_route() -> None:
    assert MIRROR.read_bytes() == CANONICAL.read_bytes()


def test_deployment_does_not_wire_github_credential_into_swarm_starts() -> None:
    source = BACKEND_APP.read_text("utf-8")

    registration = source.split("register_cognitive_swarm_routes(", 1)[1].split(")", 1)[0]
    assert "get_session_github_token=_session_github_token_for_user" not in registration


def test_devchat_uses_executable_repository_runtime_and_restores_jobs() -> None:
    app = APP.read_text("utf-8")
    client = CLIENT.read_text("utf-8")
    boundary = ENGINE_BOUNDARY.read_text("utf-8")

    assert "agentClient.startRepositoryExecution(" not in app
    assert "agentClient.createDraftPr(" not in app
    assert "await transport.startRepositoryExecution(command.payload.input)" in boundary
    assert "await transport.listJobs()" in boundary
    assert "await transport.createDraftPr(command.payload.jobId, command.payload.githubAccessToken)" in boundary
    assert "'/api/user/agent/swarm/run'" not in client
    assert "async listJobs(): Promise<SovereignAgentJobSnapshot[]>" in client


def test_draft_pr_resume_tests_use_optional_transient_token_signature() -> None:
    source = DRAFT_FLOW_TEST.read_text("utf-8")

    assert "toHaveBeenCalledWith('job-1', undefined)" in source
    assert "toHaveBeenCalledWith('job-staged', undefined)" in source


def test_reviewable_presets_bypass_are_for_direct_and_resumed_execution() -> None:
    builder = BUILDER.read_text("utf-8")

    assert "await startAgentFromText(submitted, 'code_execution')" in builder
    assert "submittedText.includes('Risiko: reviewable_patch')" in builder
    assert "Vorgemerktes Review-Preset wird direkt über den Repository-Executor wiederaufgenommen" in builder


def test_repository_execution_is_same_origin_revision_bound_and_rescue_is_conditional() -> None:
    app = APP.read_text("utf-8")
    builder = BUILDER.read_text("utf-8")
    runtime = RUNTIME.read_text("utf-8")
    bridge = REPO_BRIDGE.read_text("utf-8")

    assert "readSameOriginBackendUrl()" in runtime
    assert "/commits/${encodeURIComponent(parsed.branch)}" in bridge
    assert "headSha: typeof commit.sha === 'string' ? commit.sha : undefined" in bridge
    assert "expectedHeadSha: chatRepoSnapshot.headSha" in builder
    start_section = builder.split("const startAgentFromText", 1)[1].split("const publishConfirmedDraftPr", 1)[0]
    assert "githubAccessToken: githubTokenRef.current || undefined" not in start_section
    assert "!rescueOpen && (" in app
    assert "['blocked', 'failed'].includes(canonicalAgentJob.status)" in app
