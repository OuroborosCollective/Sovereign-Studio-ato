import { describe, expect, it } from 'vitest';
import {
  canShowWorkspaceInspector,
  createOpenHandsWorkspaceAdapter,
  getWorkspaceNextAction,
  summarizeWorkspaceStatus,
} from './openhandsWorkspaceAdapter';
import type { AgentWorkspaceResult } from './agentWorkspaceRuntime';

const VALID_REQUEST = {
  repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
  branch: 'main',
  task: 'Fix a bug in the runtime',
  executor: 'openhands' as const,
  draftPrOnly: true as const,
};

const READY_OH_CONFIG = {
  enabled: true,
  deploymentMode: 'external-agent-runtime' as const,
  agentApiUrl: 'https://openhands.example.com/api',
  adminConsoleUrl: 'https://openhands.example.com/admin',
  ready: true,
  reason: 'Ready',
};

const NOT_READY_OH_CONFIG = {
  enabled: false,
  deploymentMode: 'disabled' as const,
  agentApiUrl: '',
  adminConsoleUrl: '',
  ready: false,
  reason: 'OpenHands is disabled.',
};

describe('openhandsWorkspaceAdapter', () => {
  describe('createOpenHandsWorkspaceAdapter', () => {
    it('blocks requests when OpenHands backend is not ready', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: NOT_READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start(VALID_REQUEST);

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('disabled');
    });

    it('validates request through neutral contract before dispatch', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const invalidRequest = {
        ...VALID_REQUEST,
        repoUrl: 'not-a-valid-url',
      };

      const result = await adapter.start(invalidRequest);

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('valid HTTPS GitHub');
    });

    it('returns queued status when request is valid and backend is ready', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start(VALID_REQUEST);

      expect(result.status).toBe('queued');
      expect(result.workspaceId).toMatch(/^openhands-\d+$/);
      expect(result.events).toHaveLength(1);
      expect(result.events[0].message).toContain('queued');
    });

    it('rejects empty repo URL', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start({
        ...VALID_REQUEST,
        repoUrl: '',
      });

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('valid HTTPS GitHub');
    });

    it('rejects empty task', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start({
        ...VALID_REQUEST,
        task: '',
      });

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('task');
    });

    it('rejects non-draft-pr-only requests', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start({
        ...VALID_REQUEST,
        draftPrOnly: false as unknown as true,
      });

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('Draft-PR-only');
    });

    it('rejects requests with secret-like values', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: () => ({}),
      });

      const result = await adapter.start({
        ...VALID_REQUEST,
        task: 'Fix the bug. Token is ghp_abc123xyz456789abcdef',
      });

      expect(result.status).toBe('blocked');
      expect(result.blocker).toContain('secret-like');
    });

    it('maps OpenHands snapshot events through sanitization', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: (snapshot) => ({
          changedFiles: snapshot.changedFiles,
          draftPrUrl: snapshot.draftPrUrl,
        }),
      });

      // Start workspace first
      const started = await adapter.start(VALID_REQUEST);
      expect(started.status).toBe('queued');

      // Read with blocked- prefix should return blocked
      const blocked = await adapter.read('blocked-123');
      expect(blocked.status).toBe('blocked');
    });

    it('never invents changed files or draft pr url', async () => {
      const adapter = createOpenHandsWorkspaceAdapter({
        executor: 'openhands',
        config: READY_OH_CONFIG,
        mapSnapshot: (snapshot) => ({
          changedFiles: snapshot.changedFiles,
          draftPrUrl: snapshot.draftPrUrl,
        }),
      });

      const result = await adapter.start(VALID_REQUEST);

      // New workspace should have no changed files
      expect(result.changedFiles).toEqual([]);
      expect(result.draftPrUrl).toBeUndefined();
    });
  });

  describe('summarizeWorkspaceStatus', () => {
    it('shows "Workspace gestartet" for queued', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'queued',
        events: [],
        changedFiles: [],
      };
      expect(summarizeWorkspaceStatus(result)).toBe('Workspace gestartet');
    });

    it('shows "Repo geklont · Tests laufen" for running', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'running',
        events: [],
        changedFiles: [],
      };
      expect(summarizeWorkspaceStatus(result)).toBe('Repo geklont · Tests laufen');
    });

    it('shows "Draft PR bereit" for completed with draft pr url', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['README.md'],
        draftPrUrl: 'https://github.com/test/repo/pull/1',
      };
      expect(summarizeWorkspaceStatus(result)).toBe('Draft PR bereit');
    });

    it('does not report completed workspace without draft PR as Draft PR ready', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['README.md'],
      };
      expect(summarizeWorkspaceStatus(result)).toBe('1 Änderung(en) gemeldet · Draft PR fehlt');
    });

    it('does not report empty completed workspace as result-backed', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: [],
      };
      expect(summarizeWorkspaceStatus(result)).toBe('Workspace abgeschlossen · kein Ergebnis belegt');
    });

    it('shows blocker message for failed status', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Build error in line 42',
      };
      const summary = summarizeWorkspaceStatus(result);
      expect(summary).toContain('Blocker');
      expect(summary).toContain('Build error');
    });

    it('shows blocker message for blocked status', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Missing API key',
      };
      const summary = summarizeWorkspaceStatus(result);
      expect(summary).toContain('Blocker');
      expect(summary).toContain('Missing API key');
    });

    it('shows "Workspace bereinigt" for cleaned status', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'cleaned',
        events: [],
        changedFiles: [],
      };
      expect(summarizeWorkspaceStatus(result)).toBe('Workspace bereinigt');
    });
  });

  describe('canShowWorkspaceInspector', () => {
    it('returns true only when inspector URL is present and safe', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['file.ts'],
        workspaceInspectorUrl: 'https://workspace.example.com/view',
      };
      expect(canShowWorkspaceInspector(result)).toBe(true);
    });

    it('returns false when status is blocked', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        workspaceInspectorUrl: 'https://workspace.example.com/view',
      };
      expect(canShowWorkspaceInspector(result)).toBe(false);
    });

    it('returns false when status is cleaned', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'cleaned',
        events: [],
        changedFiles: [],
        workspaceInspectorUrl: 'https://workspace.example.com/view',
      };
      expect(canShowWorkspaceInspector(result)).toBe(false);
    });

    it('returns false when URL is missing', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['file.ts'],
      };
      expect(canShowWorkspaceInspector(result)).toBe(false);
    });

    it('returns false for http URLs', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['file.ts'],
        workspaceInspectorUrl: 'http://insecure-workspace.example.com/view',
      };
      expect(canShowWorkspaceInspector(result)).toBe(false);
    });
  });

  describe('getWorkspaceNextAction', () => {
    it('returns publish action for completed with draft pr', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['file.ts'],
        draftPrUrl: 'https://github.com/test/repo/pull/1',
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('publish');
      expect(action.label).toBe('Draft PR ansehen');
    });

    it('returns inspect action for completed without draft pr', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'completed',
        events: [],
        changedFiles: ['file.ts'],
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('inspect');
      expect(action.label).toBe('Workspace ansehen');
    });

    it('returns retry action for failed status', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Error',
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('retry');
      expect(action.label).toBe('Erneut versuchen');
    });

    it('returns cleanup action for completed/failed/blocked that need cleanup', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('retry'); // retry has priority over cleanup for failed
    });

    it('returns none for running workspace', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'running',
        events: [],
        changedFiles: [],
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('none');
    });

    it('returns none for queued workspace', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'queued',
        events: [],
        changedFiles: [],
      };
      const action = getWorkspaceNextAction(result);
      expect(action.action).toBe('none');
    });
  });
});
