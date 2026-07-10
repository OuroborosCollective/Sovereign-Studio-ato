import { describe, expect, it } from 'vitest';
import {
  mapAgentJobToActionEvent,
  mapAgentPatternToActionEvent,
  mapAgentToolToActionEvents,
} from './sovereignAgentActionStreamBridge';
import {
  appendSovereignActionEvents,
  createSovereignActionStreamState,
} from './sovereignActionStreamRuntime';
import { evaluatePredictiveRuntimePolicy } from './sovereignPredictiveRuntimePolicy';

function predictiveDecision(action: 'create_agent_job' | 'run_agent_tool' | 'validate_agent_result' | 'learn_agent_pattern') {
  return {
    action,
    signal: 'runtime_contract' as const,
    confidence: 'high' as const,
    reason: `Agent runtime next checked action: ${action}`,
    learnedFrom: 1,
    surfaces: ['agent_job', 'agent_workspace', 'agent_tool', 'agent_evidence', 'agent_pattern'] as const,
  };
}

describe('sovereignAgentRuntimeE2E', () => {
  it('proves backend agent state maps into predictive action stream without Sovereign Agent truth', () => {
    const createPolicy = evaluatePredictiveRuntimePolicy({
      capabilityDecision: {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: 'Agent job requested from checked runtime state.',
        blocker: 'workspace_required',
        nextAction: 'create_agent_job',
      },
      prediction: predictiveDecision('create_agent_job'),
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        backendAgentStateReady: true,
      },
    });
    expect(createPolicy.allowed).toBe(true);

    const toolPolicy = evaluatePredictiveRuntimePolicy({
      capabilityDecision: {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: 'Agent tool can run from backend workspace state.',
        blocker: 'workspace_required',
        nextAction: 'run_agent_tool',
      },
      prediction: predictiveDecision('run_agent_tool'),
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        backendAgentStateReady: true,
        agentJobStatus: 'running',
        workspaceReady: true,
      },
    });
    expect(toolPolicy.allowed).toBe(true);

    const evidencePolicy = evaluatePredictiveRuntimePolicy({
      capabilityDecision: {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: 'Agent result has runtime evidence.',
        blocker: 'workspace_required',
        nextAction: 'validate_agent_result',
      },
      prediction: predictiveDecision('validate_agent_result'),
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        backendAgentStateReady: true,
        agentJobStatus: 'running',
        workspaceReady: true,
        hasEvidence: true,
      },
    });
    expect(evidencePolicy.allowed).toBe(true);

    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      mapAgentJobToActionEvent({
        jobId: 'agent-e2e-1',
        status: 'running',
        workspaceId: 'agent-e2e-1',
      }),
      ...mapAgentToolToActionEvents('agent-e2e-1', {
        tool: 'git-status',
        status: 'done',
        changedFiles: ['README.md'],
        evidenceGate: {
          allowed: true,
          canPrepareDraftPr: false,
          summary: 'Changed files collected; diff is next.',
        },
      }),
      ...mapAgentToolToActionEvents('agent-e2e-1', {
        tool: 'diff',
        status: 'done',
        diffSummary: 'README.md | 4 ++++',
        evidenceGate: {
          allowed: true,
          canPrepareDraftPr: false,
          summary: 'Diff collected; tests are next.',
        },
      }),
      ...mapAgentToolToActionEvents('agent-e2e-1', {
        tool: 'test',
        status: 'done',
        testSummary: '1 passed, 0 failed',
        evidenceGate: {
          allowed: true,
          canPrepareDraftPr: true,
          summary: 'Tests passed; Draft PR preparation allowed.',
        },
      }),
      mapAgentPatternToActionEvent('agent-e2e-1', {
        allowed: true,
        kind: 'solution',
        summary: 'Validated solution pattern candidate accepted.',
        remoteMemoryAllowed: true,
      }),
    ]);

    expect(stream.events.map((event) => event.route)).toEqual([
      'agent-job',
      'agent-tool',
      'agent-evidence',
      'agent-tool',
      'agent-evidence',
      'agent-tool',
      'agent-evidence',
      'agent-pattern',
    ]);
    expect(stream.events.map((event) => event.kind)).toContain('agent_result_ready');
    expect(stream.events.map((event) => event.kind)).toContain('agent_pattern_candidate_ready');
    expect(stream.activeRoute).toBeNull();
    expect(JSON.stringify(stream)).not.toContain('Sovereign Agent gestartet');
    expect(JSON.stringify(stream)).not.toContain('github_pat_');
  });

  it('blocks a completed-looking agent result if evidence is missing', () => {
    const policy = evaluatePredictiveRuntimePolicy({
      capabilityDecision: {
        route: 'workspace-executor',
        capability: 'isolated_workspace',
        allowed: false,
        reason: 'Agent result attempted validation without evidence.',
        blocker: 'workspace_required',
        nextAction: 'validate_agent_result',
      },
      prediction: predictiveDecision('validate_agent_result'),
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        backendAgentStateReady: true,
        agentJobStatus: 'completed',
        workspaceReady: true,
        hasEvidence: false,
      },
    });

    expect(policy.allowed).toBe(false);
    expect(policy.violations.map((violation) => violation.code)).toContain('agent_result_requires_evidence');
  });
});
