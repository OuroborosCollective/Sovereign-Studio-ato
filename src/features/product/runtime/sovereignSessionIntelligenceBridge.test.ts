import { describe, expect, it, vi } from 'vitest';
import {
  createSovereignSessionNode,
  createSovereignToolNode,
  createToolLearningSignal,
  createStuckLearningSignal,
  createStrategyChangeLearningSignal,
  sessionStatusToSignalValue,
  observationPhaseToSignalValue,
} from './sovereignSessionIntelligenceBridge';
import * as containerDecisionLearning from './containerDecisionLearning';
import type { SovereignExecutionSession } from './sovereignExecutionSessionRuntime';
import type { SovereignToolObservation } from './sovereignToolObservationRuntime';

// Mock container decision learning
vi.spyOn(containerDecisionLearning, 'createContainerDecisionLearningSignal').mockImplementation(
  (containerId, ruleId, learnTag, action, lamp, score, outcome, reason) => ({
    containerId,
    ruleId,
    learnTag,
    action,
    lamp,
    score,
    outcome,
    reason,
    timestamp: Date.now(),
  })
);

vi.spyOn(containerDecisionLearning, 'applyContainerDecisionOutcome').mockImplementation(() => {});

// Helper to create valid session
function createMockSession(overrides: Partial<SovereignExecutionSession> = {}): SovereignExecutionSession {
  return {
    id: 'test-session',
    request: 'Test request',
    status: 'idle',
    plan: {
      id: 'plan-1',
      title: 'Test Plan',
      steps: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    observations: [],
    currentStepId: null,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    ...overrides,
  };
}

describe('sovereignSessionIntelligenceBridge', () => {
  describe('createSovereignSessionNode', () => {
    it('creates node with running activation', () => {
      const session = createMockSession({ status: 'running', currentStepId: 'step-1' });
      const node = createSovereignSessionNode(session);

      expect(node.id).toBe('session:test-session');
      expect(node.type).toBe('session');
      expect(node.activation).toBe(1);
      expect(node.metadata.sessionId).toBe('test-session');
      expect(node.metadata.status).toBe('running');
    });

    it('creates node with blocked activation', () => {
      const session = createMockSession({
        status: 'blocked',
        blocker: 'missing_token',
        currentStepId: 'step-1',
      });
      const node = createSovereignSessionNode(session);

      expect(node.activation).toBe(0);
      expect(node.metadata.blocker).toBe('missing_token');
    });

    it('creates node with idle activation', () => {
      const session = createMockSession({ status: 'idle', currentStepId: null });
      const node = createSovereignSessionNode(session);

      expect(node.activation).toBe(0.5);
    });
  });

  describe('createSovereignToolNode', () => {
    it('creates node for completed tool', () => {
      const node = createSovereignToolNode('github_access', 'github-access', 'completed');

      expect(node.id).toBe('tool:github_access:github-access');
      expect(node.type).toBe('tool');
      expect(node.activation).toBe(1);
    });

    it('creates node for blocked tool', () => {
      const node = createSovereignToolNode('sovereign-agent', 'sovereign-agent', 'blocked');

      expect(node.activation).toBe(-1);
    });

    it('creates node for selected tool', () => {
      const node = createSovereignToolNode('repo_loader', 'repo', 'selected');

      expect(node.activation).toBe(0.3);
    });
  });

  describe('sessionStatusToSignalValue', () => {
    it('maps finished to 1', () => {
      expect(sessionStatusToSignalValue('finished')).toBe(1);
    });

    it('maps running to 0.7', () => {
      expect(sessionStatusToSignalValue('running')).toBe(0.7);
    });

    it('maps idle to 0.5', () => {
      expect(sessionStatusToSignalValue('idle')).toBe(0.5);
    });

    it('maps blocked to -0.7', () => {
      expect(sessionStatusToSignalValue('blocked')).toBe(-0.7);
    });

    it('maps error to -1', () => {
      expect(sessionStatusToSignalValue('error')).toBe(-1);
    });
  });

  describe('observationPhaseToSignalValue', () => {
    it('maps completed to 1', () => {
      expect(observationPhaseToSignalValue('completed')).toBe(1);
    });

    it('maps observed to 1', () => {
      expect(observationPhaseToSignalValue('observed')).toBe(1);
    });

    it('maps blocked to -1', () => {
      expect(observationPhaseToSignalValue('blocked')).toBe(-1);
    });

    it('maps failed to -0.8', () => {
      expect(observationPhaseToSignalValue('failed')).toBe(-0.8);
    });

    it('maps selected to 0.3', () => {
      expect(observationPhaseToSignalValue('selected')).toBe(0.3);
    });

    it('maps started to 0.5', () => {
      expect(observationPhaseToSignalValue('started')).toBe(0.5);
    });
  });

  describe('createToolLearningSignal', () => {
    it('creates success signal for completed tool', () => {
      const session = createMockSession({ status: 'running' });
      const observation = {
        id: 'obs-1',
        toolName: 'repo_loader',
        route: 'repo' as const,
        phase: 'completed' as const,
        resultSummary: 'Repo loaded',
        createdAt: Date.now(),
        event: {} as any,
      };

      const signal = createToolLearningSignal(session, observation);

      expect(signal).not.toBeNull();
      expect(signal?.outcome).toBe('success');
      expect(signal?.score).toBe(1.0);
      expect(signal?.lamp).toBe('green');
      expect(signal?.action).toBe('continue');
    });

    it('creates failure signal for blocked tool', () => {
      const session = createMockSession({ status: 'blocked' });
      const observation = {
        id: 'obs-2',
        toolName: 'github_access',
        route: 'github-access' as const,
        phase: 'blocked' as const,
        blocker: 'missing_token',
        createdAt: Date.now(),
        event: {} as any,
      };

      const signal = createToolLearningSignal(session, observation);

      expect(signal).not.toBeNull();
      expect(signal?.outcome).toBe('failure');
      expect(signal?.score).toBe(0.0);
      expect(signal?.lamp).toBe('red');
    });

    it('returns null for started phase', () => {
      const session = createMockSession({ status: 'running' });
      const observation = {
        id: 'obs-3',
        toolName: 'sovereign-agent',
        route: 'sovereign-agent' as const,
        phase: 'started' as const,
        createdAt: Date.now(),
        event: {} as any,
      };

      const signal = createToolLearningSignal(session, observation);

      expect(signal).toBeNull();
    });

    it('creates failure signal for failed tool', () => {
      const session = createMockSession({ status: 'error' });
      const observation = {
        id: 'obs-fail',
        toolName: 'github-patch',
        route: 'github-patch' as const,
        phase: 'failed' as const,
        resultSummary: 'Patch failed',
        createdAt: Date.now(),
        event: {} as any,
      };

      const signal = createToolLearningSignal(session, observation);

      expect(signal).not.toBeNull();
      expect(signal?.outcome).toBe('failure');
      expect(signal?.score).toBe(0.0);
    });
  });

  describe('createStuckLearningSignal', () => {
    it('creates failure signal with reason', () => {
      const session = createMockSession({ status: 'blocked' });

      const signal = createStuckLearningSignal(session, 'Repeated blocker detected');

      expect(signal.outcome).toBe('failure');
      expect(signal.score).toBe(0.0);
      expect(signal.reason).toContain('Session stuck');
    });
  });

  describe('createStrategyChangeLearningSignal', () => {
    it('creates rewrite signal for strategy change', () => {
      const session = createMockSession({ status: 'running' });

      const signal = createStrategyChangeLearningSignal(session, 'sovereign-agent', 'direct-patch');

      expect(signal.outcome).toBe('rewrite');
      expect(signal.score).toBe(1.0);
      expect(signal.lamp).toBe('green');
      expect(signal.learnTag).toBe('direct-patch');
    });
  });
});
