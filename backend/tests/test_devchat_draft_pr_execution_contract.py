from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "App.tsx"
BUILDER = ROOT / "src" / "features" / "product" / "containers" / "BuilderContainer.tsx"
CLIENT = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentClient.ts"
RUNTIME = ROOT / "src" / "features" / "product" / "runtime" / "sovereignAgentRuntime.ts"
REPO_BRIDGE = ROOT / "src" / "features" / "product" / "runtime" / "devChatWorkerBridge.ts"
ENGINE_BOUNDARY = ROOT / "src" / "features" / "product" / "runtime" / "sovereignEngineBoundary.ts"
BACKEND_APP = ROOT / "scripts" / "sovereign-backend" / "app.py"
REPOSITORY_EXECUTION = ROOT / "backend" / "agent_runtime" / "repository_execution.py"
REPOSITORY_MIRROR = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "repository_execution.py"


def text(path: Path) -> str:
    return path.read_text("utf-8")


def test_frontend_routes_repository_mutation_through_unified_sovereign_runtime() -> None:
    app = text(APP)
    builder = text(BUILDER)
    client = text(CLIENT)
    boundary = text(ENGINE_BOUNDARY)

    assert "agentClient.startRepositoryExecution(" not in app
    assert "agentClient.createDraftPr(" not in app
    assert "await transport.startRepositoryExecution(command.payload.input)" in boundary
    assert "await transport.listJobs()" in boundary
    assert "startRepositoryExecution" in client
    assert "agent-zero-a2a:" not in client
    assert "Agent Zero A2A" not in client
    assert "startAgentFromText(submitted, 'code_execution')" in builder


def test_repository_execution_is_local_and_revision_bound() -> None:
    runtime = text(REPOSITORY_EXECUTION)
    start = runtime.split("def start_repository_execution(", 1)[1].split(
        "def _submit_pending_repository_job(", 1
    )[0]
    assert "clone_repo=True" in start
    assert "clone_repo=False" not in start
    assert "expectedHeadSha" in runtime
    assert "sovereign-local-runner" in runtime
    assert "AgentZeroA2AClient" not in runtime
    assert "agent-zero-a2a:" not in runtime


def test_repository_executor_registration_keeps_the_unified_runtime_boundary() -> None:
    source = text(BACKEND_APP)
    runtime = text(REPOSITORY_EXECUTION)
    assert "register_cognitive_swarm_routes(" in source
    assert "start_repository_execution(" in runtime
    assert "sovereign-local-runner" in runtime
    assert "AgentZeroA2AClient" not in runtime


def test_frontend_repository_start_carries_no_github_credential() -> None:
    client = text(CLIENT)
    builder = text(BUILDER)

    repo_input = client.split(
        "export interface SovereignRepositoryExecutionInput", 1
    )[1].split(
        "export interface SovereignDesktopFrameObservation", 1
    )[0]
    assert "githubAccessToken" not in repo_input

    builder_start = builder.split("const startAgentFromText", 1)[1].split(
        "const publishConfirmedDraftPr", 1
    )[0]
    assert "githubAccessToken: githubTokenRef.current" not in builder_start


def test_same_origin_backend_and_revision_readback_remain_intact() -> None:
    runtime = text(RUNTIME)
    bridge = text(REPO_BRIDGE)
    builder = text(BUILDER)

    assert "readSameOriginBackendUrl()" in runtime
    assert "/commits/" + "$" + "{encodeURIComponent(parsed.branch)}" in bridge
    assert "headSha: typeof commit.sha === 'string' ? commit.sha : undefined" in bridge
    assert "expectedHeadSha: chatRepoSnapshot.headSha" in builder


def test_repository_execution_shipping_mirror_matches_canonical() -> None:
    assert REPOSITORY_MIRROR.read_bytes() == REPOSITORY_EXECUTION.read_bytes()
