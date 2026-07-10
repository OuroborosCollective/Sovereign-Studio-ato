import { describe, expect, it } from 'vitest';
import {
  classifySovereignAgentResult,
  gateSovereignAgentResult,
  filterSovereignAgentEventsForUI,
  buildPatternIntakeFromSovereignAgent,
  shouldLearnFromSovereignAgent,
  summarizeSovereignAgentChatStatus,
  type SovereignAgentPatternIntakeInput,
} from './sovereignAgentPatternGatewayBridge';
import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';

function idleSnapshot(): SovereignAgentJobSnapshot {
  return { status: 'idle', changedFiles: [], events: [] };
}

function runningSnapshot(): SovereignAgentJobSnapshot {
  return { status: 'running', changedFiles: ['src/App.tsx'], events: [] };
}

function successSnapshot(): SovereignAgentJobSnapshot {
  return {
    status: 'completed',
    changedFiles: ['src/App.tsx', 'src/main.tsx'],
    draftPrUrl: 'https://github.com/test/pull/1',
    events: [],
  };
}

function blockerSnapshot(reason = 'Guard red'): SovereignAgentJobSnapshot {
  return { status: 'blocked', changedFiles: [], lastError: reason, events: [] };
}

function emptySnapshot(): SovereignAgentJobSnapshot {
  return { status: 'completed', changedFiles: [], events: [] };
}

function planOnlySnapshot(): SovereignAgentJobSnapshot {
  return {
    status: 'completed',
    changedFiles: ['README.md', 'docs/changes.txt', 'package.json'],
    events: [],
  };
}

describe('sovereignAgentPatternGatewayBridge', () => {
  describe('classifySovereignAgentResult', () => {
    it('classifies idle as running', () => {
      expect(classifySovereignAgentResult(idleSnapshot())).toBe('running');
    });

    it('classifies running as running', () => {
      expect(classifySovereignAgentResult(runningSnapshot())).toBe('running');
    });

    it('classifies blocked as blocker', () => {
      expect(classifySovereignAgentResult(blockerSnapshot())).toBe('blocker');
    });

    it('classifies failed as blocker', () => {
      expect(classifySovereignAgentResult({ status: 'failed', changedFiles: [], events: [] })).toBe('blocker');
    });

    it('classifies success with changed files as success', () => {
      expect(classifySovereignAgentResult(successSnapshot())).toBe('success');
    });

    it('classifies empty result as empty', () => {
      expect(classifySovereignAgentResult(emptySnapshot())).toBe('empty');
    });

    it('classifies docs-only changes as plan-only', () => {
      expect(classifySovereignAgentResult(planOnlySnapshot())).toBe('plan-only');
    });

    it('classifies partial docs with some code as success', () => {
      const snapshot: SovereignAgentJobSnapshot = {
        status: 'completed',
        changedFiles: ['README.md', 'src/App.tsx'],
        events: [],
      };
      expect(classifySovereignAgentResult(snapshot)).toBe('success');
    });
  });

  describe('gateSovereignAgentResult', () => {
    it('blocks running jobs', () => {
      const gate = gateSovereignAgentResult(runningSnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('running');
    });

    it('allows blocker results with reason', () => {
      const gate = gateSovereignAgentResult(blockerSnapshot('Guard red'));
      expect(gate.allowed).toBe(true);
      expect(gate.type).toBe('blocker');
      expect(gate.blockerReason).toBe('Guard red');
    });

    it('allows success results with real changes', () => {
      const gate = gateSovereignAgentResult(successSnapshot());
      expect(gate.allowed).toBe(true);
      expect(gate.type).toBe('success');
      expect(gate.changedFiles).toHaveLength(2);
      expect(gate.draftPrUrl).toBe('https://github.com/test/pull/1');
    });

    it('blocks empty results', () => {
      const gate = gateSovereignAgentResult(emptySnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('empty');
    });

    it('blocks plan-only results', () => {
      const gate = gateSovereignAgentResult(planOnlySnapshot());
      expect(gate.allowed).toBe(false);
      expect(gate.type).toBe('plan-only');
      expect(gate.summary).toContain('documentation');
    });
  });

  describe('filterSovereignAgentEventsForUI', () => {
    it('returns empty array for undefined events', () => {
      expect(filterSovereignAgentEventsForUI(undefined)).toEqual([]);
    });

    it('passes through events without secrets', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'Running step 1' }];
      const filtered = filterSovereignAgentEventsForUI(events);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].message).toBe('Running step 1');
    });

    it('redacts tokens in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'Token: abc123xyz' }];
      const filtered = filterSovereignAgentEventsForUI(events);
      expect(filtered[0].message).not.toContain('abc123xyz');
      expect(filtered[0].safe).toBe(false);
    });

    it('redacts passwords in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'password=secret123' }];
      const filtered = filterSovereignAgentEventsForUI(events);
      expect(filtered[0].message).not.toContain('secret123');
    });

    it('redacts API keys in event messages', () => {
      const events = [{ at: 1000, level: 'info' as const, stage: 'test', message: 'api_key: sk-1234567890' }];
      const filtered = filterSovereignAgentEventsForUI(events);
      expect(filtered[0].message).not.toContain('sk-1234567890');
    });
  });

  describe('buildPatternIntakeFromSovereignAgent', () => {
    it('returns null for running results', () => {
      const input: SovereignAgentPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: runningSnapshot(),
      };
      expect(buildPatternIntakeFromSovereignAgent(input)).toBeNull();
    });

    it('returns null for empty results', () => {
      const input: SovereignAgentPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: emptySnapshot(),
      };
      expect(buildPatternIntakeFromSovereignAgent(input)).toBeNull();
    });

    it('returns null for plan-only results', () => {
      const input: SovereignAgentPatternIntakeInput = {
        mission: 'Update docs',
        snapshot: planOnlySnapshot(),
      };
      expect(buildPatternIntakeFromSovereignAgent(input)).toBeNull();
    });

    it('builds valid pattern input for success results', () => {
      const input: SovereignAgentPatternIntakeInput = {
        mission: 'Fix bug',
        snapshot: successSnapshot(),
        providerId: 'sovereign-agent',
      };
      const pattern = buildPatternIntakeFromSovereignAgent(input);
      expect(pattern).not.toBeNull();
      expect(pattern!.intakeNode).toBe('sovereign-agent-runtime');
      expect(pattern!.confidence).toBe('completed');
      expect(pattern!.fix.changedFiles).toHaveLength(2);
    });

    it('builds blocker pattern with inferred confidence', () => {
      const input: SovereignAgentPatternIntakeInput = {
        mission: 'Test mission',
        snapshot: blockerSnapshot('Test blocker'),
      };
      const pattern = buildPatternIntakeFromSovereignAgent(input);
      expect(pattern).not.toBeNull();
      expect(pattern!.confidence).toBe('inferred');
      expect(pattern!.problem.severity).toBe('high');
      expect(pattern!.fix.summary).toBe('Test blocker');
    });
  });

  describe('shouldLearnFromSovereignAgent', () => {
    it('returns false for running jobs', () => {
      expect(shouldLearnFromSovereignAgent(runningSnapshot())).toBe(false);
    });

    it('returns false for empty results', () => {
      expect(shouldLearnFromSovereignAgent(emptySnapshot())).toBe(false);
    });

    it('returns false for plan-only results', () => {
      expect(shouldLearnFromSovereignAgent(planOnlySnapshot())).toBe(false);
    });

    it('returns true for blocker results', () => {
      expect(shouldLearnFromSovereignAgent(blockerSnapshot())).toBe(true);
    });

    it('returns true for success results', () => {
      expect(shouldLearnFromSovereignAgent(successSnapshot())).toBe(true);
    });
  });

  describe('summarizeSovereignAgentChatStatus', () => {
    it('shows running status for active jobs', () => {
      expect(summarizeSovereignAgentChatStatus(runningSnapshot())).toContain('arbeitet');
    });

    it('shows success summary with file count', () => {
      const summary = summarizeSovereignAgentChatStatus(successSnapshot());
      expect(summary).toContain('fertig');
      expect(summary).toContain('2 Datei');
    });

    it('shows blocker status', () => {
      expect(summarizeSovereignAgentChatStatus(blockerSnapshot())).toBe('Sovereign Agent blockiert.');
    });

    it('shows empty result status', () => {
      expect(summarizeSovereignAgentChatStatus(emptySnapshot())).toContain('Kein greifbares Ergebnis');
    });

    it('shows plan-only rejection', () => {
      expect(summarizeSovereignAgentChatStatus(planOnlySnapshot())).toContain('Dokumentation');
    });
  });
});
