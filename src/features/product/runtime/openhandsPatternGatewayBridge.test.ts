import { describe, expect, it } from 'vitest';
import {
  classifyOpenHandsResult,
  gateOpenHandsResult,
  filterOpenHandsEventsForUI,
  buildPatternIntakeFromOpenHands,
  shouldLearnFromOpenHands,
  summarizeOpenHandsChatStatus,
  type OpenHandsPatternIntakeInput,
} from './openhandsPatternGatewayBridge';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

function idleSnapshot(): OpenHandsJobSnapshot {
  return { status: 'idle', changedFiles: [], events: [] };
}

function runningSnapshot(): OpenHandsJobSnapshot {
  return { status: 'running', changedFiles: ['src/App.tsx'], events: [] };
}

function successSnapshot(): OpenHandsJobSnapshot {
  return {
    status: 'completed',
    changedFiles: ['src/App.tsx', 'src/main.tsx'],
    draftPrUrl: 'https://github.com/test/pull/1',
    events: [],
  };
}

function blockerSnapshot(reason = 'Guard red'): OpenHandsJobSnapshot {
  return { status: 'blocked', changedFiles: [], lastError: reason, events: [] };
}

function emptySnapshot(): OpenHandsJobSnapshot {
  return { status: 'completed', changedFiles: [], events: [] };
}

function planOnlySnapshot(): OpenHandsJobSnapshot {
  return {
    status: 'completed',
    changedFiles: ['README.md', 'docs/changes.txt', 'package.json'],
    events: [],
  };
}

describe('openhandsPatternGatewayBridge', () => {
  describe('classifyOpenHandsResult', () => {
    it('classifies idle as running', () => {
      expect(classifyOpenHandsResult(idleSnapshot())).toBe('running');
    });

    it('classifies running as running', () => {
      expect(classifyOpenHandsResult(runningSnapshot())).toBe('running');
    });

    it('classifies blocked as blocker', () => {
      expect(classifyOpenHandsResult(blockerSnapshot())).toBe('blocker');
    });

    it('classifies failed as blocker', () => {
      expect(classifyOpenHandsResult({ status: 'failed', changedFiles: [], events: [] })).toBe('blocker');
    });

    it('classifies success with changed files as success', () => {
      expect(classifyOpenHandsResult(successSnapshot())).toBe('success');
    });

    it('classifies empty result as empty', () => {
      expect(classifyOpenHandsResult(emptySnapshot())).toBe('empty');
    });

    it('classifies docs-only changes as plan-only', () => {
      expect(classifyOpenHandsResult(planOnlySnapshot())).toBe('plan-only');
    });

    it('classifies partial docs with some code as success', () => {
      const snapshot: OpenHandsJobSnapshot = {
        status: 'completed',
        changedFiles: ['README.md', 'src/App.tsx'],
        events: [],
      };
      expect(classifyOpenHandsResult(snapshot)).toBe('success');
    });
  });

  describe('gateOpenHandsResult', () => {
    it('blocks running jobs', () => {
      const gate = gateOpenHandsResult(runningSnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('running');
    });

    it('allows blocker results with reason', () => {
      const gate = gateOpenHandsResult(blockerSnapshot('Guard red'));
      expect(gate.allowed).toBe(true);
      expect(gate.type).toBe('blocker');
      expect(gate.blockerReason).toBe('Guard red');
    });

    it('allows success results with real changes', () => {
      const gate = gateOpenHandsResult(successSnapshot());
      expect(gate.allowed).toBe(true);
      expect(gate.type).toBe('success');
      expect(gate.changedFiles).toHaveLength(2);
      expect(gate.draftPrUrl).toBe('https://github.com/test/pull/1');
    });

    it('blocks empty results', () => {
      const gate = gateOpenHandsResult(emptySnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('empty');
    });

    it('blocks plan-only results', () => {
      const gate = gateOpenHandsResult(planOnlySnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('plan-only');
      expect(gate.summary).toContain('documentation');
    });
  });

  describe('filterOpenHandsEventsForUI', () => {
    it('returns empty array for undefined events', () => {
      expect(filterOpenHandsEventsForUI(undefined)).toEqual([]);
    });

    it('passes through events without secrets', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'Running step 1' }];
      const filtered = filterOpenHandsEventsForUI(events);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].message).toBe('Running step 1');
    });

    it('redacts tokens in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'Token: abc123xyz' }];
      const filtered = filterOpenHandsEventsForUI(events);
      expect(filtered[0].message).not.toContain('abc123xyz');
      expect(filtered[0].safe).toBe(false);
    });

    it('redacts passwords in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'password=secret123' }];
      const filtered = filterOpenHandsEventsForUI(events);
      expect(filtered[0].message).not.toContain('secret123');
    });

    it('redacts API keys in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'api_key: sk-1234567890' }];
      const filtered = filterOpenHandsEventsForUI(events);
      expect(filtered[0].message).not.toContain('sk-1234567890');
    });
  });

  describe('buildPatternIntakeFromOpenHands', () => {
    it('returns null for running results', () => {
      const input: OpenHandsPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: runningSnapshot(),
      };
      expect(buildPatternIntakeFromOpenHands(input)).toBeNull();
    });

    it('returns null for empty results', () => {
      const input: OpenHandsPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: emptySnapshot(),
      };
      expect(buildPatternIntakeFromOpenHands(input)).toBeNull();
    });

    it('returns null for plan-only results', () => {
      const input: OpenHandsPatternIntakeInput = {
        mission: 'Update docs',
        snapshot: planOnlySnapshot(),
      };
      expect(buildPatternIntakeFromOpenHands(input)).toBeNull();
    });

    it('builds valid pattern input for success results', () => {
      const input: OpenHandsPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: successSnapshot(),
        providerId: 'openhands',
      };
      const pattern = buildPatternIntakeFromOpenHands(input);
      expect(pattern).not.toBeNull();
      expect(pattern!.intakeNode).toBe('openhands-runtime');
      expect(pattern!.confidence).toBe('completed');
      expect(pattern!.fix.changedFiles).toHaveLength(2);
    });

    it('builds blocker pattern with inferred confidence', () => {
      const input: OpenHandsPatternIntakeInput = {
        mission: 'Test mission',
        snapshot: blockerSnapshot('Test blocker'),
      };
      const pattern = buildPatternIntakeFromOpenHands(input);
      expect(pattern).not.toBeNull();
      expect(pattern!.confidence).toBe('inferred');
      expect(pattern!.problem.severity).toBe('high');
      expect(pattern!.fix.summary).toBe('Test blocker');
    });
  });

  describe('shouldLearnFromOpenHands', () => {
    it('returns false for running jobs', () => {
      expect(shouldLearnFromOpenHands(runningSnapshot())).toBe(false);
    });

    it('returns false for empty results', () => {
      expect(shouldLearnFromOpenHands(emptySnapshot())).toBe(false);
    });

    it('returns false for plan-only results', () => {
      expect(shouldLearnFromOpenHands(planOnlySnapshot())).toBe(false);
    });

    it('returns true for blocker results', () => {
      expect(shouldLearnFromOpenHands(blockerSnapshot())).toBe(true);
    });

    it('returns true for success results', () => {
      expect(shouldLearnFromOpenHands(successSnapshot())).toBe(true);
    });
  });

  describe('summarizeOpenHandsChatStatus', () => {
    it('shows running status for active jobs', () => {
      expect(summarizeOpenHandsChatStatus(runningSnapshot())).toContain('arbeitet');
    });

    it('shows success summary with file count', () => {
      const summary = summarizeOpenHandsChatStatus(successSnapshot());
      expect(summary).toContain('fertig');
      expect(summary).toContain('2 Datei');
    });

    it('shows blocker status', () => {
      expect(summarizeOpenHandsChatStatus(blockerSnapshot())).toBe('Sovereign Agent blockiert.');
    });

    it('shows empty result status', () => {
      expect(summarizeOpenHandsChatStatus(emptySnapshot())).toContain('Kein greifbares Ergebnis');
    });

    it('shows plan-only rejection', () => {
      expect(summarizeOpenHandsChatStatus(planOnlySnapshot())).toContain('Dokumentation');
    });
  });
});
