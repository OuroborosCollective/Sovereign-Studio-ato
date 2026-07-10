import { describe, expect, it } from 'vitest';
import type { AgentWorkspaceResult } from './agentWorkspaceRuntime';
import {
  classifyWorkspaceError,
  getWorkspaceErrorNextAction,
  safeWorkspaceStatusTransition,
} from './workspaceErrorPolicy';

describe('workspaceErrorPolicy', () => {
  describe('classifyWorkspaceError', () => {
    it('classifies invalid repo URL errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Workspace requires a valid HTTPS GitHub repository URL.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('invalid-repo');
      expect(error.severity).toBe('blocked');
      expect(error.retryable).toBe(false);
    });

    it('classifies secret detection errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Workspace request contains a secret-like value.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('secret-detected');
      expect(error.severity).toBe('fatal');
      expect(error.retryable).toBe(false);
    });

    it('classifies executor not ready errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Workspace executor is not ready.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('executor-not-ready');
      expect(error.severity).toBe('blocked');
      expect(error.retryable).toBe(true);
    });

    it('classifies backend unavailable errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Sovereign Agent backend is not ready.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('backend-unavailable');
      expect(error.retryable).toBe(true);
    });

    it('classifies timeout errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Workspace execution timeout exceeded.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('timeout');
      expect(error.retryable).toBe(true);
    });

    it('classifies network errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Network connection failed.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('network-error');
      expect(error.retryable).toBe(true);
    });

    it('classifies cleanup failed errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Workspace cleanup failed.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('cleanup-failed');
      expect(error.retryable).toBe(false);
    });

    it('classifies workspace occupied errors', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Workspace already running.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('workspace-occupied');
      expect(error.retryable).toBe(false);
    });

    it('classifies blocked- prefixed workspace IDs as validation failures', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'blocked-12345',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'Request validation failed.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('validation-failed');
    });

    it('returns unknown for unrecognized blockers', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'Something unexpected happened.',
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('unknown');
      expect(error.severity).toBe('warning');
    });

    it('returns info severity for blocked status with no blocker', () => {
      const result: AgentWorkspaceResult = {
        workspaceId: 'test-1',
        status: 'blocked',
        events: [],
        changedFiles: [],
      };
      const error = classifyWorkspaceError(result);
      expect(error.kind).toBe('unknown');
      expect(error.severity).toBe('info');
    });
  });

  describe('getWorkspaceErrorNextAction', () => {
    it('returns fix-input for secret detection', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'secret detected',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('fix-input');
      expect(action.blocked).toBe(true);
    });

    it('returns fix-input for invalid repo', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'invalid github url',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('fix-input');
    });

    it('returns cleanup for workspace occupied', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'already running',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('cleanup');
    });

    it('returns contact-admin for executor not ready', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'blocked',
        events: [],
        changedFiles: [],
        blocker: 'executor not ready',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('contact-admin');
    });

    it('returns retry for timeout errors', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'timeout',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('retry');
      expect(action.blocked).toBe(false);
    });

    it('returns retry for network errors', () => {
      const error = classifyWorkspaceError({
        workspaceId: 'test',
        status: 'failed',
        events: [],
        changedFiles: [],
        blocker: 'network error',
      });
      const action = getWorkspaceErrorNextAction(error);
      expect(action.action).toBe('retry');
    });
  });

  describe('safeWorkspaceStatusTransition', () => {
    it('allows idle → queued', () => {
      const result = safeWorkspaceStatusTransition('idle', 'queued');
      expect(result.valid).toBe(true);
      expect(result.safeNext).toBe('queued');
    });

    it('allows queued → running', () => {
      const result = safeWorkspaceStatusTransition('queued', 'running');
      expect(result.valid).toBe(true);
    });

    it('allows running → completed', () => {
      const result = safeWorkspaceStatusTransition('running', 'completed');
      expect(result.valid).toBe(true);
    });

    it('allows running → failed', () => {
      const result = safeWorkspaceStatusTransition('running', 'failed');
      expect(result.valid).toBe(true);
    });

    it('allows completed → cleaned', () => {
      const result = safeWorkspaceStatusTransition('completed', 'cleaned');
      expect(result.valid).toBe(true);
    });

    it('allows failed → cleaned', () => {
      const result = safeWorkspaceStatusTransition('failed', 'cleaned');
      expect(result.valid).toBe(true);
    });

    it('allows failed → queued (retry)', () => {
      const result = safeWorkspaceStatusTransition('failed', 'queued');
      expect(result.valid).toBe(true);
    });

    it('allows blocked → queued (retry)', () => {
      const result = safeWorkspaceStatusTransition('blocked', 'queued');
      expect(result.valid).toBe(true);
    });

    it('allows cleaned → queued (new workspace)', () => {
      const result = safeWorkspaceStatusTransition('cleaned', 'queued');
      expect(result.valid).toBe(true);
    });

    it('blocks idle → running (skip queued)', () => {
      const result = safeWorkspaceStatusTransition('idle', 'running');
      expect(result.valid).toBe(false);
      expect(result.safeNext).toBe('idle'); // falls back to current
    });

    it('blocks running → idle', () => {
      const result = safeWorkspaceStatusTransition('running', 'idle');
      expect(result.valid).toBe(false);
    });

    it('blocks completed → running', () => {
      const result = safeWorkspaceStatusTransition('completed', 'running');
      expect(result.valid).toBe(false);
    });

    it('logs warning for invalid transitions', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      safeWorkspaceStatusTransition('running', 'idle');
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Invalid status transition'),
      );
      consoleSpy.mockRestore();
    });
  });
});
