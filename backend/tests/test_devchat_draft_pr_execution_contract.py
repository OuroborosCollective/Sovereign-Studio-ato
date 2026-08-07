from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "backend" / "agent_runtime" / "cognitive_swarm_routes.py"
MIRROR = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "cognitive_swarm_routes.py"
APP = ROOT / "src" / "App.tsx"
BUILDER = ROOT / "src" / "features" / "product" / "containers" / "BuilderContainer.tsx"
CLIENT = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentClient.ts"
RUNTIME = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentRuntime.ts"
REPO_BRIDGE = ROOT / "src" / "features" / "product" / "runtime" / "devChatWorkerBridge.ts"


def test_swarm_route_forwards_repository_execution_identity() -> None:
    source = CANONICAL.read_text("utf-8")

    assert 'repository_url=str(body.get("repositoryUrl") or body.get("repoUrl") or "") or None' in source
    assert 'repository_branch=str(body.get("repositoryBranch") or body.get("branch") or "main")' in source
    assert 'expected_head_sha=str(body.get("expectedHeadSha") or "") or None' in source
    assert 'github_access_token=str(body.get("githubAccessToken") or "") or None' in source


def test_paid_repository_execution_uses_requested_repo_branch_and_exact_head() -> None:
    source = CANONICAL.read_text("utf-8")

    assert "selected_repository_url = (" in source
    assert '"repoUrl": selected_repository_url' in source
    assert '"branch": normalized_repository_branch' in source
    assert 'job_payload["expectedHeadSha"] = normalized_expected_head_sha' in source
    assert "clone_repo=True" in source


def test_deployment_mirror_matches_canonical_swarm_route() -> None:
    assert MIRROR.read_bytes() == CANONICAL.read_bytes()


def test_devchat_uses_executable_repository_runtime_and_restores_jobs() -> None:
    app = APP.read_text("utf-8")
    client = CLIENT.read_text("utf-8")

    assert "agentClient.startRepositoryExecution({" in app
    assert "agentClient.listJobs()" in app
    assert "agentClient.createDraftPr(jobId, input?.githubAccessToken)" in app
    assert "'/api/user/agent/swarm/run'" in client
    assert "async listJobs(): Promise<SovereignAgentJobSnapshot[]>" in client


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
    assert "!rescueOpen && ['blocked', 'failed'].includes(agentJob.status)" in app
