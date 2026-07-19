import { describe, expect, it } from 'vitest';
import {
  classifyOfflineSovereignExecutorIntent,
  decideSovereignExecutorRoute,
} from './sovereignExecutorRuntime';
import { buildSovereignToolCapabilityRegistry } from './sovereignToolCapabilityRuntime';
import { createSovereignWorkspaceScope } from './sovereignWorkspaceScopeRuntime';

function capabilities(overrides: Partial<Parameters<typeof buildSovereignToolCapabilityRegistry>[0]> = {}) {
  return buildSovereignToolCapabilityRegistry({
    repoReady: true,
    githubAccessState: 'ready',
    githubTokenPresent: true,
    directPatchSupported: true,
    agentConfigured: true,
    workerAvailable: true,
    workspaceConfigured: true,
    draftPrSupported: true,
    activeExecutorStatus: 'idle',
    ...overrides,
  });
}

function workspaceScope(overrides: Partial<Parameters<typeof createSovereignWorkspaceScope>[0]> = {}) {
  return createSovereignWorkspaceScope({
    repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
    branch: 'main',
    allowedPaths: ['src/features/product/runtime/', 'README.md'],
    forbiddenPaths: ['src/secrets/'],
    draftPrOnly: true,
    githubWriteValidated: true,
    maxAction: 'draft_pr',
    ...overrides,
  });
}

describe('sovereignExecutorRuntime', () => {
  it('accepts only explicit offline commands and never interprets free language', () => {
    expect(classifyOfflineSovereignExecutorIntent('/status')).toBe('status');
    expect(classifyOfflineSovereignExecutorIntent('/direct-patch README Titel ändern')).toBe('direct_patch');
    expect(classifyOfflineSovereignExecutorIntent('/code Tests in src/foo.test.ts')).toBe('code_execution');
    expect(classifyOfflineSovereignExecutorIntent('/agent Runtime reparieren')).toBe('code_execution');
    expect(classifyOfflineSovereignExecutorIntent('/draft-pr')).toBe('draft_pr');
    expect(classifyOfflineSovereignExecutorIntent('/question Warum ist das so?')).toBe('question');
    expect(classifyOfflineSovereignExecutorIntent('Was ist der Status?')).toBe('unknown');
    expect(classifyOfflineSovereignExecutorIntent('Bitte README Titel ändern')).toBe('unknown');
    expect(classifyOfflineSovereignExecutorIntent('Implementiere Tests in src/foo.test.ts')).toBe('unknown');
    expect(classifyOfflineSovereignExecutorIntent('Erstelle einen Draft PR')).toBe('unknown');
  });

  it('routes status questions locally and terminally', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'status',
      capabilities: capabilities(),
    });

    expect(decision.route).toBe('local_status');
    expect(decision.state).toBe('allowed');
    expect(decision.terminal).toBe(true);
    expect(decision.event.route).toBe('runtime');
  });

  it('blocks write intents before repo is loaded', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'code_execution',
      capabilities: capabilities({ repoReady: false }),
    });

    expect(decision.state).toBe('blocked');
    expect(decision.blocker).toBe('repo_missing');
    expect(decision.nextAllowedAction).toBe('load_repo');
  });

  it('opens GitHub access route before Sovereign Agent when write access is missing', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'code_execution',
      capabilities: capabilities({
        githubAccessState: 'missing',
        githubTokenPresent: false,
        agentConfigured: true,
      }),
      workspaceScope: workspaceScope({ githubWriteValidated: false }),
    });

    expect(decision.route).toBe('github_access');
    expect(decision.state).toBe('blocked');
    expect(decision.requiredCapability).toBe('github_write');
    expect(decision.event.kind).toBe('github_access_required');
    expect(decision.nextAllowedAction).toBe('request_github_access');
  });

  it('selects Direct Patch for small documentation work when ready', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'direct_patch',
      capabilities: capabilities(),
      workspaceScope: workspaceScope(),
      candidatePath: 'README.md',
    });

    expect(decision.route).toBe('direct_patch');
    expect(decision.state).toBe('allowed');
    expect(decision.nextAllowedAction).toBe('run_direct_patch');
    expect(decision.event.route).toBe('direct-github-patch');
  });

  it('selects Sovereign Agent for complex code work only when GitHub write is ready', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'code_execution',
      capabilities: capabilities({ directPatchSupported: false }),
      workspaceScope: workspaceScope(),
      candidatePath: 'src/features/product/runtime/foo.ts',
    });

    expect(decision.route).toBe('sovereign-agent');
    expect(decision.state).toBe('allowed');
    expect(decision.requiredCapability).toBe('sovereign-agent');
    expect(decision.nextAllowedAction).toBe('start_agent');
  });

  it('blocks code work outside workspace scope', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'code_execution',
      capabilities: capabilities({ directPatchSupported: false }),
      workspaceScope: workspaceScope(),
      candidatePath: 'src/secrets/token.ts',
    });

    expect(decision.route).toBe('workspace');
    expect(decision.state).toBe('blocked');
    expect(decision.blocker).toBe('workspace_scope_blocked');
    expect(decision.reason).toContain('forbidden');
  });

  it('keeps unclear input on Worker Chat instead of starting write executors', () => {
    const decision = decideSovereignExecutorRoute({
      intent: 'unknown',
      capabilities: capabilities(),
    });

    expect(decision.route).toBe('worker_chat');
    expect(decision.nextAllowedAction).toBe('start_worker_chat');
  });
});
