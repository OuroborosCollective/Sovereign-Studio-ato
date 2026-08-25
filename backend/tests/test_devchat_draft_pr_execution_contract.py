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


def test_swarm_route_forwards_repository_execution_identity() -> None:
    source = CANONICAL.read_text("utf-8")

    assert 'repository_url=str(body.get("repositoryUrl") or body.get("repoUrl") or "") or None' in source
    assert 'repository_branch=str(body.get("repositoryBranch") or body.get("branch") or "main")' in source
    assert 'expected_head_sha=str(body.get("expectedHeadSha") or "") or None' in source
    assert 'payload, status_code = _start_run_with_session_github_token(' in source
    assert 'if "githubAccessToken" in body' in source
    assert "start_run=_start_run_with_session_github_token" in source


def test_paid_repository_execution_uses_requested_repo_branch_and_exact_head() -> None:
    source = CANONICAL.read_text("utf-8")

    assert "selected_repository_url = (" in source
    assert '"repoUrl": selected_repository_url' in source
    assert '"branch": normalized_repository_branch' in source
    assert 'job_payload["expectedHeadSha"] = normalized_expected_head_sha' in source
    assert "github_access_token=normalized_github_access_token" in source
    assert 'job_payload["githubAccessToken"]' not in source
    assert "clone_repo=True" in source


def test_deployment_mirror_matches_canonical_swarm_route() -> None:
    assert MIRROR.read_bytes() == CANONICAL.read_bytes()


def test_deployment_registers_server_held_github_credential_for_swarm_starts() -> None:
    source = BACKEND_APP.read_text("utf-8")

    registration = source.split("register_cognitive_swarm_routes(", 1)[1].split(")", 1)[0]
    assert "get_session_github_token=_session_github_token_for_user" in registration


def test_devchat_uses_executable_repository_runtime_and_restores_jobs() -> None:
    app = APP.read_text("utf-8")
    client = CLIENT.read_text("utf-8")
    boundary = ENGINE_BOUNDARY.read_text("utf-8")

    assert "agentClient.startRepositoryExecution(" not in app
    assert "agentClient.createDraftPr(" not in app
    assert "await transport.startRepositoryExecution(command.payload.input)" in boundary
    assert "await transport.listJobs()" in boundary
    assert "await transport.createDraftPr(command.payload.jobId, command.payload.githubAccessToken)" in boundary
    assert "'/api/user/agent/swarm/run'" in client
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
    assert "githubAccessToken: githubTokenRef.current || undefined" in builder
    assert "!rescueOpen && (" in app
    assert "['blocked', 'failed'].includes(canonicalAgentJob.status)" in app
