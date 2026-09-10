from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_routes(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '_INTENT_MODES = frozenset({"auto", "conversation", "read_only_analysis", "repository_execution"})\n',
        '_INTENT_MODES = frozenset({"auto", "conversation", "read_only_analysis", "repository_execution"})\n_AGENT_MODES = frozenset({"auto", "single", "swarm"})\n',
        label=f"{path}: agent mode constants",
    )

    helper_anchor = "\n\ndef _explicit_mission_intent(intent_mode: str, mission: str) -> MissionIntent | None:\n"
    helper = '''\n\ndef _normalize_agent_mode(value: str) -> str:\n    selected = str(value or "auto").strip().casefold().replace("-", "_").replace(" ", "_")\n    if selected not in _AGENT_MODES:\n        raise ValueError("agentMode must be auto, single or swarm")\n    return selected\n\n\ndef _single_agent_resolution(resolution: ExecutionResolution) -> ExecutionResolution:\n    """Project a free swarm-capable resolution onto one foreground agent.\n\n    Candidate routes stay intact so the existing FreeLLM revolver may fail over\n    between independent quota scopes. Only the execution shape changes.\n    """\n    if resolution.profile_id != FREE_SWARM_PROFILE:\n        return resolution\n    return ExecutionResolution(\n        profile_id=FREE_SINGLE_AGENT_PROFILE,\n        primary_route=resolution.primary_route,\n        agent_route=resolution.primary_route,\n        candidate_routes=resolution.candidate_routes,\n        max_foreground_agents=1,\n        max_background_agents=0,\n        repository_execution_allowed=resolution.repository_execution_allowed,\n        paid_purchase_verified=resolution.paid_purchase_verified,\n        paid_entitlement_verified=resolution.paid_entitlement_verified,\n        paid_entitlement_source=resolution.paid_entitlement_source,\n        provider_funded_credits=resolution.provider_funded_credits,\n        requested_mode=resolution.requested_mode,\n        reason="explicit_single_agent_feature_selected",\n        fallback_from_transport=resolution.fallback_from_transport,\n    )\n'''
    text = replace_once(text, helper_anchor, helper + helper_anchor, label=f"{path}: helpers")

    start_at = text.index("def start_cognitive_swarm_run(")
    resume_at = text.index("def resume_cognitive_swarm_run(")
    before = text[:start_at]
    segment = text[start_at:resume_at]
    after = text[resume_at:]

    segment = replace_once(
        segment,
        '    mode: str = "auto",\n    intent_mode: str = "auto",\n    run_id: str | None = None,\n',
        '    mode: str = "auto",\n    intent_mode: str = "auto",\n    agent_mode: str = "auto",\n    run_id: str | None = None,\n',
        label=f"{path}: start signature",
    )
    segment = replace_once(
        segment,
        '    normalized_mode = str(mode or "auto").strip().lower()\n    normalized_repository_url = str(repository_url or "").strip()\n',
        '    normalized_mode = str(mode or "auto").strip().lower()\n    try:\n        normalized_agent_mode = _normalize_agent_mode(agent_mode)\n    except ValueError as exc:\n        return {"error": str(exc)}, 400\n    normalized_repository_url = str(repository_url or "").strip()\n',
        label=f"{path}: normalize agent mode",
    )
    segment = replace_once(
        segment,
        '    resolver_mode = "free" if _force_free_profile else normalized_mode\n',
        '    resolver_mode = (\n        "free"\n        if _force_free_profile or normalized_agent_mode == "single"\n        else normalized_mode\n    )\n',
        label=f"{path}: resolver mode",
    )

    recursive_pattern = re.compile(
        r'(?m)^(?P<indent>\s+)mode=(?P<value>[^\n]+),\n(?P=indent)intent_mode=normalized_intent_mode,'
    )
    segment, recursive_count = recursive_pattern.subn(
        lambda match: (
            f'{match.group("indent")}mode={match.group("value")},\n'
            f'{match.group("indent")}intent_mode=normalized_intent_mode,\n'
            f'{match.group("indent")}agent_mode=normalized_agent_mode,'
        ),
        segment,
    )
    if recursive_count < 1:
        raise RuntimeError(f"{path}: no recursive start calls received agent_mode")

    validation_anchor = '    try:\n        _validate_execution_resolution_snapshot(execution_resolution)\n'
    validation_index = segment.find(validation_anchor)
    if validation_index < 0:
        raise RuntimeError(f"{path}: validation anchor missing")
    agent_gate = '''    if normalized_agent_mode == "single":\n        execution_resolution = _single_agent_resolution(execution_resolution)\n    elif (\n        normalized_agent_mode == "swarm"\n        and execution_resolution.profile_id not in {FREE_SWARM_PROFILE, PAID_SWARM_PROFILE}\n    ):\n        state = _persist_execution_resolution_blocker(\n            get_connection,\n            user_id=user_id,\n            run_id=resolved_run_id,\n            trace_id=resolved_trace_id,\n            status="BLOCKED",\n            blocker="SWARM_CAPACITY_NOT_READY",\n            reason=(\n                "Swarm mode is an explicit feature and requires a verified multi-agent "\n                "execution profile. Normal single-agent FreeLLM work remains available."\n            ),\n            next_action="USE_SINGLE_AGENT_OR_RETRY_SWARM_WHEN_CAPACITY_READY",\n        )\n        return {\n            "ok": False,\n            "runtime": "openai-agents-sdk",\n            "runId": resolved_run_id,\n            "traceId": resolved_trace_id,\n            "status": state["status"],\n            "source": state["source"],\n            "evidenceId": state["evidenceId"],\n            "receivedEvidenceId": received_state["evidenceId"],\n            "blocker": "SWARM_CAPACITY_NOT_READY",\n            "reason": state["reason"],\n            "nextAction": state["nextAction"],\n            "requestedAgentMode": normalized_agent_mode,\n            "singleAgentAvailable": True,\n            "secretValuesReturned": False,\n        }, 409\n\n'''
    segment = segment[:validation_index] + agent_gate + segment[validation_index:]
    text = before + segment + after

    text = replace_once(
        text,
        '            "executionModes": ["auto", "paid", "free"],\n            "allowedModels": [],\n',
        '            "executionModes": ["auto", "paid", "free"],\n            "agentModes": ["single", "swarm"],\n            "defaultAgentMode": "single",\n            "singleAgentTransport": "freellm",\n            "swarmRequiresExplicitOptIn": True,\n            "allowedModels": [],\n',
        label=f"{path}: manifest agent modes",
    )
    text = replace_once(
        text,
        '            mode=str(body.get("mode") or "auto"),\n            intent_mode=str(body.get("intentMode") or "auto"),\n            repository_url=str(body.get("repositoryUrl") or body.get("repoUrl") or "") or None,\n',
        '            mode=str(body.get("mode") or "auto"),\n            intent_mode=str(body.get("intentMode") or "auto"),\n            agent_mode=str(body.get("agentMode") or "auto"),\n            repository_url=str(body.get("repositoryUrl") or body.get("repoUrl") or "") or None,\n',
        label=f"{path}: user route agent mode",
    )
    path.write_text(text, encoding="utf-8")


def patch_frontend() -> None:
    domain = ROOT / "src/features/control-surface-vnext/types/domain.ts"
    text = domain.read_text(encoding="utf-8")
    text = replace_once(text, "export type JobPhase =\n", "export type AgentMode = 'single' | 'swarm';\n\nexport type JobPhase =\n", label="domain AgentMode")
    domain.write_text(text, encoding="utf-8")

    interface = ROOT / "src/features/control-surface-vnext/adapter/interface.ts"
    text = interface.read_text(encoding="utf-8")
    text = replace_once(text, "  DraftPR,\n", "  AgentMode,\n  DraftPR,\n", label="adapter interface import")
    text = replace_once(
        text,
        "  runSwarm(prompt: string, toolchains: string[], activeSkillIds?: string[]): Promise<{ jobId: string }>;\n",
        "  runSwarm(prompt: string, toolchains: string[], activeSkillIds?: string[], agentMode?: AgentMode): Promise<{ jobId: string }>;\n",
        label="adapter interface runSwarm",
    )
    interface.write_text(text, encoding="utf-8")

    hook = ROOT / "src/features/control-surface-vnext/hooks/useSwarmRun.ts"
    text = hook.read_text(encoding="utf-8")
    text = replace_once(text, "import { useSovereignAdapter } from '../adapter/context';\n", "import { useSovereignAdapter } from '../adapter/context';\nimport type { AgentMode } from '../types/domain';\n", label="hook AgentMode import")
    text = replace_once(
        text,
        "export interface SwarmRunParams { prompt?: string; objective?: string; toolchains?: string[]; toolchainId?: string; activeSkillIds?: string[]; }\n",
        "export interface SwarmRunParams { prompt?: string; objective?: string; toolchains?: string[]; toolchainId?: string; activeSkillIds?: string[]; agentMode?: AgentMode; }\n",
        label="hook params",
    )
    text = replace_once(
        text,
        "      return adapter.runSwarm(prompt, toolchains, params.activeSkillIds ?? []);\n",
        "      return adapter.runSwarm(prompt, toolchains, params.activeSkillIds ?? [], params.agentMode ?? 'single');\n",
        label="hook dispatch",
    )
    hook.write_text(text, encoding="utf-8")

    adapter = ROOT / "src/features/control-surface-vnext/adapter/production-adapter.ts"
    text = adapter.read_text(encoding="utf-8")
    text = replace_once(text, "  DraftPR,\n", "  AgentMode,\n  DraftPR,\n", label="production adapter AgentMode import")
    build_anchor = "\nfunction parseRun(value: unknown): PersistedRun {\n"
    builder = '''\nexport function buildRunRequest(mission: string, agentMode: AgentMode = 'single'): JsonRecord {\n  const repositoryUrl = extractGitHubRepositoryUrl(mission);\n  const base = { mission, mode: 'free', agentMode };\n  return repositoryUrl ? {\n    ...base,\n    intentMode: 'repository_execution',\n    repositoryUrl,\n    repositoryBranch: 'main',\n  } : {\n    ...base,\n    intentMode: 'auto',\n  };\n}\n'''
    text = replace_once(text, build_anchor, builder + build_anchor, label="production adapter request builder")
    method_pattern = re.compile(
        r"  async runSwarm\(prompt: string, _toolchains: string\[\], _activeSkillIds: string\[\] = \[\]\): Promise<\{ jobId: string \}> \{.*?\n  \}\n\n  private async getRun",
        re.S,
    )
    replacement = '''  async runSwarm(\n    prompt: string,\n    _toolchains: string[],\n    _activeSkillIds: string[] = [],\n    agentMode: AgentMode = 'single',\n  ): Promise<{ jobId: string }> {\n    const mission = prompt.trim();\n    if (!mission) throw new Error('Mission text is required.');\n    const result = await this.requestObject('/api/user/agent/swarm/run', {\n      method: 'POST',\n      body: JSON.stringify(buildRunRequest(mission, agentMode)),\n    });\n    const runId = stringValue(result.body.runId);\n    if (runId) return { jobId: runId };\n    const reason = stringValue(result.body.reason) || stringValue(result.body.error) || stringValue(result.body.blocker);\n    throw new Error(reason || `Sovereign swarm start failed with HTTP ${result.status}.`);\n  }\n\n  private async getRun'''
    text, count = method_pattern.subn(replacement, text)
    if count != 1:
        raise RuntimeError(f"production adapter runSwarm: expected 1 replacement, got {count}")
    adapter.write_text(text, encoding="utf-8")

    app = ROOT / "src/features/control-surface-vnext/App.tsx"
    text = app.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import type { ChatMessage, OwnerInteractionResponse } from './types/domain';\n",
        "import type { AgentMode, ChatMessage, OwnerInteractionResponse } from './types/domain';\n",
        label="App AgentMode import",
    )
    text = replace_once(
        text,
        "  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');\n",
        "  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');\n  const [agentMode, setAgentMode] = useState<AgentMode>('single');\n",
        label="App agent state",
    )
    text = replace_once(
        text,
        "      const accepted = await swarmRun.mutateAsync({ prompt: mission, toolchains: selectedToolchain ? [selectedToolchain.id] : [], activeSkillIds });\n",
        "      const accepted = await swarmRun.mutateAsync({ prompt: mission, toolchains: selectedToolchain ? [selectedToolchain.id] : [], activeSkillIds, agentMode });\n",
        label="App agent dispatch",
    )
    text = replace_once(
        text,
        "      activeIntegrationsCount={(integrations.data ?? []).length}\n    />\n",
        "      activeIntegrationsCount={(integrations.data ?? []).length}\n      agentMode={agentMode}\n      onAgentModeChange={setAgentMode}\n    />\n",
        label="App ChatSurface agent props",
    )
    app.write_text(text, encoding="utf-8")

    chat = ROOT / "src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx"
    text = chat.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import type { ChatMessage, JobPhase, SovereignJob } from '../../types/domain';\n",
        "import type { AgentMode, ChatMessage, JobPhase, SovereignJob } from '../../types/domain';\n",
        label="ChatSurface AgentMode import",
    )
    text = replace_once(
        text,
        "  activeIntegrationsCount?: number;\n}\n",
        "  activeIntegrationsCount?: number;\n  agentMode?: AgentMode;\n  onAgentModeChange?: (mode: AgentMode) => void;\n}\n",
        label="ChatSurface props",
    )
    text = replace_once(
        text,
        "export function ChatSurface({ messages, onSubmitOrder, onSendMessage, jobPhase = 'IDLE', activeJob, onOpenToolchain, onOpenSkills, onOpenIntegrations, onAbortJob, onTypingStateChange, activeToolchainName, activeSkillsCount = 0, activeIntegrationsCount = 0 }: Props) {\n",
        "export function ChatSurface({ messages, onSubmitOrder, onSendMessage, jobPhase = 'IDLE', activeJob, onOpenToolchain, onOpenSkills, onOpenIntegrations, onAbortJob, onTypingStateChange, activeToolchainName, activeSkillsCount = 0, activeIntegrationsCount = 0, agentMode = 'single', onAgentModeChange }: Props) {\n",
        label="ChatSurface destructure",
    )
    text = text.replace("<BrainCircuit size={10} /> SWARM", "<BrainCircuit size={10} /> AGENTS", 1)
    selector_anchor = '        <div className="theme-diamond-cut rounded-xl border border-[rgba(255,30,56,0.28)] bg-[var(--carbon-deep)] p-2 shadow-[0_0_24px_rgba(255,30,56,0.08)]">\n'
    selector = '''        <div data-testid="agent-mode-selector" className="mb-2 flex items-center gap-1.5 rounded-lg border border-white/5 bg-[var(--carbon-deep)] p-1.5 font-mono">\n          <span className="px-1 text-[8px] text-[var(--text-dim)]">EXECUTION</span>\n          <button type="button" data-testid="agent-mode-single" aria-pressed={agentMode === 'single'} disabled={executing} onClick={() => { playKeystrokeChirp(); onAgentModeChange?.('single'); }} className={`min-h-8 flex-1 rounded border px-2 text-[8.5px] font-black ${agentMode === 'single' ? 'border-[var(--emerald-seal)] bg-[rgba(16,185,129,0.12)] text-[var(--emerald-seal)]' : 'border-white/5 bg-[var(--carbon-surface)] text-[var(--text-muted)]'} disabled:opacity-50`}>1 AGENT · FREELLM</button>\n          <button type="button" data-testid="agent-mode-swarm" aria-pressed={agentMode === 'swarm'} disabled={executing} onClick={() => { playKeystrokeChirp(); onAgentModeChange?.('swarm'); }} className={`min-h-8 flex-1 rounded border px-2 text-[8.5px] font-black ${agentMode === 'swarm' ? 'border-[var(--red-laser)] bg-[rgba(255,30,56,0.12)] text-[var(--red-laser)]' : 'border-white/5 bg-[var(--carbon-surface)] text-[var(--text-muted)]'} disabled:opacity-50`}>SWARM · OPT-IN</button>\n          <span className="hidden sm:inline px-1 text-[8px] text-[var(--text-dim)]">SERVER-GATED</span>\n        </div>\n\n'''
    text = replace_once(text, selector_anchor, selector + selector_anchor, label="ChatSurface selector")
    chat.write_text(text, encoding="utf-8")

    live = ROOT / "tests/e2e/five-draft-pr-paths.spec.ts"
    text = live.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "  await composer.fill(text);\n  await page.getByTestId('builder__start-task').click();\n",
        "  await composer.fill(text);\n  await expect(page.getByTestId('agent-mode-single')).toHaveAttribute('aria-pressed', 'true');\n  await page.getByTestId('builder__start-task').click();\n",
        label="live five single-agent default",
    )
    live.write_text(text, encoding="utf-8")


def write_tests() -> None:
    (ROOT / "src/features/control-surface-vnext/adapter/production-adapter.agent-mode.test.ts").write_text(
        '''import { describe, expect, it } from 'vitest';\nimport { buildRunRequest } from './production-adapter';\n\ndescribe('SovereignProductionAdapter agent mode contract', () => {\n  it('defaults normal repository work to one FreeLLM agent', () => {\n    expect(buildRunRequest('Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato\\nÄndere README.md.')).toEqual({\n      mission: 'Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato\\nÄndere README.md.',\n      mode: 'free',\n      agentMode: 'single',\n      intentMode: 'repository_execution',\n      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',\n      repositoryBranch: 'main',\n    });\n  });\n\n  it('makes the multi-agent swarm an explicit FreeLLM opt-in', () => {\n    const payload = buildRunRequest('Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato', 'swarm');\n    expect(payload.mode).toBe('free');\n    expect(payload.agentMode).toBe('swarm');\n    expect(payload.intentMode).toBe('repository_execution');\n  });\n\n  it('keeps ordinary non-repository missions single-agent by default', () => {\n    expect(buildRunRequest('Fasse den Status zusammen.')).toEqual({\n      mission: 'Fasse den Status zusammen.',\n      mode: 'free',\n      agentMode: 'single',\n      intentMode: 'auto',\n    });\n  });\n});\n''',
        encoding="utf-8",
    )

    (ROOT / "backend/tests/test_agent_mode_contract.py").write_text(
        '''from pathlib import Path\n\nimport pytest\n\nfrom agent_runtime import cognitive_swarm_routes as routes\nfrom llm_execution_resolver import ExecutionResolution, FREE_SINGLE_AGENT_PROFILE, FREE_SWARM_PROFILE\n\n\ndef _free_swarm_resolution() -> ExecutionResolution:\n    routes_list = tuple({"id": f"free-{index}"} for index in range(7))\n    return ExecutionResolution(\n        profile_id=FREE_SWARM_PROFILE,\n        primary_route=routes_list[0],\n        agent_route=routes_list[1],\n        candidate_routes=routes_list,\n        max_foreground_agents=1,\n        max_background_agents=6,\n        repository_execution_allowed=True,\n        paid_purchase_verified=False,\n        paid_entitlement_verified=True,\n        paid_entitlement_source="existing_credit_balance",\n        provider_funded_credits=0,\n        requested_mode="free",\n        reason="free_swarm_ready_with_seven_independent_verified_quota_scopes",\n    )\n\n\ndef test_agent_mode_normalization_is_bounded():\n    assert routes._normalize_agent_mode("single") == "single"\n    assert routes._normalize_agent_mode("SWARM") == "swarm"\n    assert routes._normalize_agent_mode("") == "auto"\n    with pytest.raises(ValueError, match="agentMode must be auto, single or swarm"):\n        routes._normalize_agent_mode("background-chaos")\n\n\ndef test_explicit_single_agent_projects_free_swarm_capacity_to_one_agent():\n    projected = routes._single_agent_resolution(_free_swarm_resolution())\n    assert projected.profile_id == FREE_SINGLE_AGENT_PROFILE\n    assert projected.primary_route["id"] == "free-0"\n    assert projected.agent_route["id"] == "free-0"\n    assert projected.max_foreground_agents == 1\n    assert projected.max_background_agents == 0\n    assert [route["id"] for route in projected.candidate_routes] == [f"free-{index}" for index in range(7)]\n\n\ndef test_user_route_exposes_single_default_and_explicit_swarm_feature():\n    source = Path(routes.__file__).read_text(encoding="utf-8")\n    assert '"agentModes": ["single", "swarm"]' in source\n    assert '"defaultAgentMode": "single"' in source\n    assert '"swarmRequiresExplicitOptIn": True' in source\n    assert 'agent_mode=str(body.get("agentMode") or "auto")' in source\n    assert 'blocker="SWARM_CAPACITY_NOT_READY"' in source\n    assert 'next_action="USE_SINGLE_AGENT_OR_RETRY_SWARM_WHEN_CAPACITY_READY"' in source\n''',
        encoding="utf-8",
    )


def main() -> None:
    patch_routes(ROOT / "backend/agent_runtime/cognitive_swarm_routes.py")
    patch_routes(ROOT / "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py")
    patch_frontend()
    write_tests()
    backend = (ROOT / "backend/agent_runtime/cognitive_swarm_routes.py").read_bytes()
    mirror = (ROOT / "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py").read_bytes()
    if backend != mirror:
        raise RuntimeError("backend/script cognitive_swarm_routes mirror parity failed")
    print("single-agent/swarm feature patch applied with backend mirror parity")


if __name__ == "__main__":
    main()
