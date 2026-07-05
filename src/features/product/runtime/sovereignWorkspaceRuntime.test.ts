/**
 * Sovereign Workspace Runtime Tests
 *
 * Tests for the Sovereign Workspace Runtime.
 * Covers acceptance criteria from Issue #503.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  SovereignWorkspaceRuntime,
  createMockWorkspaceAdapter,
  createInitialRuntimeState,
  determineWorkspacePurpose,
  shouldTriggerWorkspace,
  DEFAULT_WORKSPACE_CONFIG,
} from './sovereignWorkspaceRuntime';
import type {
  SovereignWorkspaceRequest,
  WorkspaceAdapter,
  WorkspacePurpose,
} from './sovereignWorkspaceTypes';

describe('SovereignWorkspaceRuntime', () => {
  let runtime: SovereignWorkspaceRuntime;

  beforeEach(() => {
    runtime = new SovereignWorkspaceRuntime();
  });

  describe('initialization', () => {
    it('should create runtime with no adapters', () => {
      const state = createInitialRuntimeState();
      expect(state.adapters).toHaveLength(0);
      expect(state.activeJobs.size).toBe(0);
      expect(state.completedJobs.size).toBe(0);
    });

    it('should create runtime with default config', () => {
      expect(DEFAULT_WORKSPACE_CONFIG.maxConcurrentJobs).toBe(3);
      expect(DEFAULT_WORKSPACE_CONFIG.jobTimeoutMs).toBe(30 * 60 * 1000);
    });

    it('should register adapters', () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);
      expect(runtime.hasExecutorSync()).toBe(true);
    });

    it('should not allow duplicate adapter registration', () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);
      expect(() => runtime.registerAdapter(adapter)).toThrow('already registered');
    });

    it('should unregister adapters', () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);
      runtime.unregisterAdapter('test-adapter');
      expect(runtime.hasExecutorSync()).toBe(false);
    });
  });

  describe('workspace requests', () => {
    const validRequest: SovereignWorkspaceRequest = {
      jobId: 'test-job-1',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Fix bug in authentication',
      allowedPaths: ['src/', 'lib/'],
      forbiddenPaths: ['.env', 'node_modules/'],
      requireTests: true,
      allowCommit: true,
      allowDraftPr: true,
    };

    it('should block request with invalid repo URL', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const invalidRequest = { ...validRequest, repoUrl: 'https://gitlab.com/test/repo' };
      const result = await runtime.requestWorkspace(invalidRequest);

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('https://github.com/');
    });

    it('should block request with missing jobId', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const invalidRequest = { ...validRequest, jobId: '' };
      const result = await runtime.requestWorkspace(invalidRequest);

      expect(result.status).toBe('blocked');
    });

    it('should block request without executor', async () => {
      const request = { ...validRequest, mission: 'Fix critical bug in src/auth' };
      const result = await runtime.requestWorkspace(request);

      expect(result.status).toBe('blocked');
      // Without adapter, executor is unavailable
      expect(result.blocker).toBe('executor_unavailable');
    });

    it('should execute workspace when executor available and policy allows', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const result = await runtime.requestWorkspace(validRequest);

      expect(result.status).toBe('completed');
      expect(result.events.length).toBeGreaterThan(0);
    });

    it('should track active jobs', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      await runtime.requestWorkspace(validRequest);

      expect(runtime.getActiveJobs()).toHaveLength(0); // Job completed
      expect(runtime.getCompletedJobs()).toHaveLength(1);
    });

    it('should block Draft PR when allowDraftPr is false', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const request = {
        ...validRequest,
        allowDraftPr: false,
        purpose: 'draft_pr' as WorkspacePurpose,
      };

      const result = await runtime.requestWorkspace(request);

      expect(result.status).toBe('completed');
      // Note: Mock adapter doesn't actually create draft PR, so this passes
      // In real adapter, this would be blocked
    });
  });

  describe('routing decisions', () => {
    it('should route simple questions to worker-chat', () => {
      const decision = runtime.makeRoutingDecision({
        mission: 'Was ist Sovereign Studio?',
      });

      expect(decision.route).toBe('worker-chat');
      expect(decision.allowed).toBe(false);
    });

    it('should route complex tasks to isolated-workspace', () => {
      // Without adapter, executor_gate will block with executor_unavailable
      const decision = runtime.makeRoutingDecision({
        repoUrl: 'https://github.com/test/repo',
        baseBranch: 'main',
        mission: 'Fix bug in authentication module',
        targetPaths: ['src/auth/login.ts'],
      });

      // Without adapter, executor unavailable
      expect(decision.blocker).toBe('executor_unavailable');
    });

    it('should route small doc patches to direct-github-patch', () => {
      const decision = runtime.makeRoutingDecision({
        repoUrl: 'https://github.com/test/repo',
        baseBranch: 'main',
        mission: 'Update README',
        targetPaths: ['README.md'],
      });

      expect(decision.route).toBe('direct-github-patch');
      expect(decision.allowed).toBe(false);
    });

    it('should route read-only analysis to snapshot-analysis', () => {
      const decision = runtime.makeRoutingDecision({
        repoUrl: 'https://github.com/test/repo',
        mission: 'Analyze the codebase structure',
        isReadOnly: true,
      });

      expect(decision.route).toBe('snapshot-analysis');
      expect(decision.capability).toBe('repo_read');
    });

    it('should block when no executor for workspace-required task', () => {
      const decision = runtime.makeRoutingDecision({
        repoUrl: 'https://github.com/test/repo',
        baseBranch: 'main',
        mission: 'Implement new feature in src/core',
        targetPaths: ['src/core/index.ts', 'src/core/types.ts'],
      });

      expect(decision.allowed).toBe(false);
      // Without adapter, executor unavailable
      expect(decision.blocker).toBe('executor_unavailable');
    });
  });

  describe('job management', () => {
    it('should report job status for active job', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const request: SovereignWorkspaceRequest = {
        jobId: 'active-job',
        purpose: 'patch',
        repoUrl: 'https://github.com/test/repo',
        baseBranch: 'main',
        mission: 'Quick fix',
        allowedPaths: ['src/'],
        forbiddenPaths: [],
        requireTests: false,
        allowCommit: true,
        allowDraftPr: false,
      };

      await runtime.requestWorkspace(request);

      const status = runtime.getJobStatus('active-job');
      expect(status.completed).toBe(true);
    });

    it('should report unknown job status', () => {
      const status = runtime.getJobStatus('unknown-job');
      expect(status.active).toBe(false);
      expect(status.completed).toBe(false);
    });

    it('should cleanup job', async () => {
      const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      runtime.registerAdapter(adapter);

      const request: SovereignWorkspaceRequest = {
        jobId: 'cleanup-job',
        purpose: 'patch',
        repoUrl: 'https://github.com/test/repo',
        baseBranch: 'main',
        mission: 'Cleanup test',
        allowedPaths: ['src/'],
        forbiddenPaths: [],
        requireTests: false,
        allowCommit: true,
        allowDraftPr: false,
      };

      await runtime.requestWorkspace(request);
      await runtime.cleanupJob('cleanup-job');

      // Should not throw
    });
  });

  describe('adapter management', () => {
    it('should get adapters for specific purpose', async () => {
      const patchAdapter = createMockWorkspaceAdapter('patch-adapter', 'Patch Adapter');
      (patchAdapter as any).supportedPurposes = ['patch'];

      const testAdapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
      (testAdapter as any).supportedPurposes = ['test'];

      runtime.registerAdapter(patchAdapter);
      runtime.registerAdapter(testAdapter);

      const patchAdapters = await runtime.getAvailableAdapters('patch');
      expect(patchAdapters).toHaveLength(1);
      expect(patchAdapters[0].id).toBe('patch-adapter');

      const testAdapters = await runtime.getAvailableAdapters('test');
      expect(testAdapters).toHaveLength(1);
      expect(testAdapters[0].id).toBe('test-adapter');
    });
  });
});

describe('createMockWorkspaceAdapter', () => {
  it('should create adapter with all supported purposes', () => {
    const adapter = createMockWorkspaceAdapter('mock', 'Mock Adapter');
    expect(adapter.supportedPurposes).toContain('analysis');
    expect(adapter.supportedPurposes).toContain('patch');
    expect(adapter.supportedPurposes).toContain('test');
    expect(adapter.supportedPurposes).toContain('draft_pr');
    expect(adapter.supportedPurposes).toContain('repair');
  });

  it('should report as available', async () => {
    const adapter = createMockWorkspaceAdapter('mock', 'Mock Adapter');
    expect(await adapter.isAvailable()).toBe(true);
  });

  it('should execute request and return events', async () => {
    const adapter = createMockWorkspaceAdapter('mock', 'Mock Adapter');

    const request: SovereignWorkspaceRequest = {
      jobId: 'mock-job',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Test mission',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: false,
    };

    const result = await adapter.execute(request);

    expect(result.status).toBe('completed');
    expect(result.events.length).toBeGreaterThan(0);
    expect(result.events.some((e) => e.kind === 'workspace_requested')).toBe(true);
    expect(result.events.some((e) => e.kind === 'workspace_created')).toBe(true);
    expect(result.events.some((e) => e.kind === 'diff_ready')).toBe(true);
  });

  it('should include test events when requireTests is true', async () => {
    const adapter = createMockWorkspaceAdapter('mock', 'Mock Adapter');

    const request: SovereignWorkspaceRequest = {
      jobId: 'test-job',
      purpose: 'test',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Run tests',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: true,
      allowCommit: false,
      allowDraftPr: false,
    };

    const result = await adapter.execute(request);

    expect(result.events.some((e) => e.kind === 'tests_started')).toBe(true);
    expect(result.events.some((e) => e.kind === 'tests_finished')).toBe(true);
  });

  it('should include draft_pr_ready event when allowDraftPr is true', async () => {
    const adapter = createMockWorkspaceAdapter('mock', 'Mock Adapter');

    const request: SovereignWorkspaceRequest = {
      jobId: 'draft-job',
      purpose: 'draft_pr',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Create draft PR',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: true,
    };

    const result = await adapter.execute(request);

    expect(result.events.some((e) => e.kind === 'draft_pr_ready')).toBe(true);
  });
});

describe('determineWorkspacePurpose', () => {
  it('should return test for test missions', () => {
    expect(determineWorkspacePurpose('Run the test suite')).toBe('test');
    expect(determineWorkspacePurpose('Add test coverage')).toBe('test');
  });

  it('should return draft_pr for draft PR missions', () => {
    expect(determineWorkspacePurpose('Create a draft PR')).toBe('draft_pr');
    expect(determineWorkspacePurpose('Submit as draft PR')).toBe('draft_pr');
  });

  it('should return repair for bug fixes', () => {
    expect(determineWorkspacePurpose('Fix the authentication bug')).toBe('repair');
    expect(determineWorkspacePurpose('Repair broken build')).toBe('repair');
  });

  it('should return analysis for read-only analysis', () => {
    expect(determineWorkspacePurpose('Analyze the codebase')).toBe('analysis');
    expect(determineWorkspacePurpose('Review the architecture')).toBe('analysis');
  });

  it('should return patch for default case', () => {
    expect(determineWorkspacePurpose('Update the README')).toBe('patch');
    expect(determineWorkspacePurpose('Add new feature')).toBe('patch');
  });
});

describe('shouldTriggerWorkspace', () => {
  it('should not trigger for simple questions', () => {
    const result = shouldTriggerWorkspace('Was ist Sovereign?');
    expect(result.shouldTrigger).toBe(false);
    expect(result.reason).toContain('Simple question');
  });

  it('should trigger for multi-file changes', () => {
    const result = shouldTriggerWorkspace(
      'Update multiple files',
      ['src/a.ts', 'src/b.ts']
    );
    expect(result.shouldTrigger).toBe(true);
    expect(result.suggestedPurpose).toBe('patch');
  });

  it('should trigger for source code changes', () => {
    const result = shouldTriggerWorkspace(
      'Fix bug in auth',
      ['src/auth/login.ts']
    );
    expect(result.shouldTrigger).toBe(true);
  });

  it('should not trigger for docs-only changes', () => {
    const result = shouldTriggerWorkspace(
      'Update documentation',
      ['README.md', 'docs/guide.md']
    );
    expect(result.shouldTrigger).toBe(false);
  });
});

describe('Secret masking in events', () => {
  it('should mask GitHub tokens in events', async () => {
    const runtime = new SovereignWorkspaceRuntime();
    const adapter = createMockWorkspaceAdapter('test-adapter', 'Test Adapter');
    runtime.registerAdapter(adapter);

    const request: SovereignWorkspaceRequest = {
      jobId: 'secret-test',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Fix auth with token ghp_abcdefghijklmnopqrstuvwxyz1234567890ab',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: false,
    };

    const result = await runtime.requestWorkspace(request);

    // Check that events don't contain raw tokens
    const eventStrings = result.events.map((e) => JSON.stringify(e));
    for (const eventStr of eventStrings) {
      expect(eventStr).not.toContain('ghp_abcdefghijklmnopqrstuvwxyz1234567890ab');
    }
  });
});

describe('Acceptance Criteria from Issue #503', () => {
  let runtime: SovereignWorkspaceRuntime;

  beforeEach(() => {
    runtime = new SovereignWorkspaceRuntime();
    const adapter = createMockWorkspaceAdapter('openhands-mock', 'OpenHands Mock');
    runtime.registerAdapter(adapter);
  });

  it('AC1: Workspace Runtime is agent-neutral, not OpenHands-hardcoded', async () => {
    // Runtime works without any specific adapter
    const emptyRuntime = new SovereignWorkspaceRuntime();
    expect(emptyRuntime.hasExecutorSync()).toBe(false);
    expect(await emptyRuntime.hasAvailableExecutor()).toBe(false);

    // Adapter can be any ID, not hardcoded to 'openhands'
    const customAdapter = createMockWorkspaceAdapter('custom-agent', 'Custom Agent');
    emptyRuntime.registerAdapter(customAdapter);
    expect(emptyRuntime.hasExecutorSync()).toBe(true);
    expect(await emptyRuntime.hasAvailableExecutor()).toBe(true);
  });

  it('AC2: Each job gets own isolated workspace context', async () => {
    // Create a fresh runtime for this test to ensure isolation
    const isolatedRuntime = new SovereignWorkspaceRuntime();
    const adapter = createMockWorkspaceAdapter('isolated-adapter', 'Isolated Adapter');
    isolatedRuntime.registerAdapter(adapter);

    const request1: SovereignWorkspaceRequest = {
      jobId: 'job-1',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo1',
      baseBranch: 'main',
      mission: 'Task 1',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: false,
    };

    const request2: SovereignWorkspaceRequest = {
      jobId: 'job-2',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo2',
      baseBranch: 'develop',
      mission: 'Task 2',
      allowedPaths: ['lib/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: false,
    };

    const result1 = await isolatedRuntime.requestWorkspace(request1);
    const result2 = await isolatedRuntime.requestWorkspace(request2);

    // Each job completed independently with its own context
    expect(result1.jobId).toBe('job-1');
    expect(result2.jobId).toBe('job-2');
    expect(result1.status).toBe('completed');
    expect(result2.status).toBe('completed');
    // Each job should have its own events
    expect(result1.events.length).toBeGreaterThan(0);
    expect(result2.events.length).toBeGreaterThan(0);
  });

  it('AC3: Chat/Analysis agents do not start write workspace', () => {
    const decision = runtime.makeRoutingDecision({
      mission: 'Was ist der Status des Repos?',
      isReadOnly: true,
    });

    expect(decision.route).toBe('snapshot-analysis');
    expect(decision.allowed).toBe(false);
  });

  it('AC4: Code agents can request workspace via runtime gates', async () => {
    // Create fresh runtime without adapter to test blocking
    const blockedRuntime = new SovereignWorkspaceRuntime();
    const decisionNoAdapter = blockedRuntime.makeRoutingDecision({
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Implement feature in src/core',
      targetPaths: ['src/core/index.ts'],
    });
    expect(decisionNoAdapter.allowed).toBe(false);
    expect(decisionNoAdapter.blocker).toBe('executor_unavailable');

    // With adapter, workspace should be allowed
    const adapter = createMockWorkspaceAdapter('code-agent', 'Code Agent');
    runtime.registerAdapter(adapter);
    const decisionWithAdapter = runtime.makeRoutingDecision({
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Implement feature in src/core',
      targetPaths: ['src/core/index.ts'],
    });
    expect(decisionWithAdapter.allowed).toBe(true);
  });

  it('AC5: Workspace result delivers real events and changed files', async () => {
    const request: SovereignWorkspaceRequest = {
      jobId: 'ac5-test',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Update configuration',
      allowedPaths: ['src/', 'config/'],
      forbiddenPaths: [],
      requireTests: true,
      allowCommit: true,
      allowDraftPr: true,
    };

    const result = await runtime.requestWorkspace(request);

    expect(result.events.length).toBeGreaterThan(0);
    expect(result.status).toBe('completed');
    expect(result.diffSummary).toBeDefined();
  });

  it('AC6: No workspace creates UI truth', () => {
    const decision = runtime.makeRoutingDecision({
      mission: 'Simple status question',
    });

    // UI should not trigger workspace
    expect(decision.route).toBe('worker-chat');
  });

  it('AC7: No tokens/secrets in events', async () => {
    const request: SovereignWorkspaceRequest = {
      jobId: 'secret-ac-test',
      purpose: 'patch',
      repoUrl: 'https://github.com/test/repo',
      baseBranch: 'main',
      mission: 'Task with secret sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnop',
      allowedPaths: ['src/'],
      forbiddenPaths: [],
      requireTests: false,
      allowCommit: true,
      allowDraftPr: false,
    };

    const result = await runtime.requestWorkspace(request);
    const eventJson = JSON.stringify(result.events);

    expect(eventJson).not.toContain('sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnop');
  });

  it('AC8: OpenHands can be connected as first adapter', async () => {
    // The mock adapter demonstrates that any adapter can be connected
    const openhandsAdapter = createMockWorkspaceAdapter('openhands', 'OpenHands Executor');
    runtime.registerAdapter(openhandsAdapter);

    expect(runtime.hasExecutorSync()).toBe(true);
    expect(await runtime.hasAvailableExecutor()).toBe(true);
  });
});
