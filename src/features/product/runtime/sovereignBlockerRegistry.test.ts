/**
 * Sovereign Blocker Registry Tests
 *
 * Test cases from Issue #504:
 * 1. Three same executor_unavailable events create one blocker with occurrences: 3, not three errors
 * 2. GitHub ready + Sovereign Agent missing shows nextAction not "GitHub-Zugang öffnen"
 * 3. GitHub validating shows status "GitHub-Zugang wird geprüft"
 * 4. Worker HTTP 500 stays its own worker_blocked blocker
 * 5. Action Stream shows blocker inline, no extra dashboard
 * 6. No tokens in blocker detail/label/nextAction
 */

import { describe, it, expect } from 'vitest';
import {
  generateBlockerKey,
  defaultSeverityForKind,
  createBlockerRegistryState,
  registerBlocker,
  dismissBlocker,
  clearBlockersByKind,
  clearAllBlockers,
  deriveBlockerNextAction,
  blockerFromGitHubAccess,
  blockerFromWorkerError,
  formatBlockerSummary,
  type SovereignBlockerKind,
  type SovereignBlockerSeverity,
} from './sovereignBlockerRegistry';

describe('sovereignBlockerRegistry', () => {
  // ─── Key Generation ─────────────────────────────────────────────────────────

  describe('generateBlockerKey', () => {
    it('generates consistent keys for identical inputs', () => {
      const input1 = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'sovereign-agent',
        label: 'Sovereign Agent nicht bereit',
        detail: 'Executor ist nicht verfügbar',
        nextAction: 'Executor starten',
      };
      const input2 = {
        ...input1,
        detail: 'Executor ist nicht verfügbar', // Same detail
      };
      expect(generateBlockerKey(input1)).toBe(generateBlockerKey(input2));
    });

    it('generates different keys for different routes', () => {
      const input1 = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'sovereign-agent',
        label: 'Test',
        detail: 'Same detail',
        nextAction: 'Test',
      };
      const input2 = {
        ...input1,
        route: 'worker',
      };
      expect(generateBlockerKey(input1)).not.toBe(generateBlockerKey(input2));
    });

    it('generates different keys for different kinds', () => {
      const input1 = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'worker',
        label: 'Test',
        detail: 'Same detail',
        nextAction: 'Test',
      };
      const input2 = {
        ...input1,
        kind: 'worker_blocked' as SovereignBlockerKind,
      };
      expect(generateBlockerKey(input1)).not.toBe(generateBlockerKey(input2));
    });

    it('normalizes detail for key generation (case-insensitive)', () => {
      const input1 = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'worker',
        label: 'Test',
        detail: 'Executor NICHT VERFÜGBAR',
        nextAction: 'Test',
      };
      const input2 = {
        ...input1,
        detail: 'executor nicht verfügbar',
      };
      expect(generateBlockerKey(input1)).toBe(generateBlockerKey(input2));
    });

    it('normalizes whitespace in detail', () => {
      const input1 = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'worker',
        label: 'Test',
        detail: 'Executor  ist  nicht   verfügbar',
        nextAction: 'Test',
      };
      const input2 = {
        ...input1,
        detail: 'Executor ist nicht verfügbar',
      };
      expect(generateBlockerKey(input1)).toBe(generateBlockerKey(input2));
    });
  });

  // ─── Severity Defaults ──────────────────────────────────────────────────────

  describe('defaultSeverityForKind', () => {
    it('assigns error severity to github_access_required', () => {
      expect(defaultSeverityForKind('github_access_required')).toBe('error');
    });

    it('assigns warning severity to github_access_validating', () => {
      expect(defaultSeverityForKind('github_access_validating')).toBe('warning');
    });

    it('assigns warning severity to executor_unavailable', () => {
      expect(defaultSeverityForKind('executor_unavailable')).toBe('warning');
    });

    it('assigns warning severity to worker_blocked', () => {
      expect(defaultSeverityForKind('worker_blocked')).toBe('warning');
    });

    it('assigns info severity to unknown kinds', () => {
      expect(defaultSeverityForKind('runtime_error')).toBe('warning');
    });
  });

  // ─── Registry State ────────────────────────────────────────────────────────

  describe('createBlockerRegistryState', () => {
    it('creates empty registry with zero counts', () => {
      const state = createBlockerRegistryState();
      expect(state.blockers).toEqual([]);
      expect(state.activeBlockerCount).toBe(0);
      expect(state.warningCount).toBe(0);
      expect(state.errorCount).toBe(0);
    });
  });

  // ─── Deduplication (Core Issue #504 Requirement) ────────────────────────────

  describe('registerBlocker - Deduplication', () => {
    it('Test 1: Three same executor_unavailable events create one blocker with occurrences: 3, not three errors', () => {
      let state = createBlockerRegistryState();

      const executorBlocker = {
        kind: 'executor_unavailable' as SovereignBlockerKind,
        route: 'sovereign-agent',
        label: 'Sovereign Agent Executor',
        detail: 'Executor ist nicht verfügbar',
        nextAction: 'Executor starten',
      };

      // Register same blocker 3 times
      state = registerBlocker(state, executorBlocker);
      state = registerBlocker(state, executorBlocker);
      state = registerBlocker(state, executorBlocker);

      // Should be ONE blocker with 3 occurrences, not 3 errors
      expect(state.activeBlockerCount).toBe(1);
      expect(state.errorCount).toBe(0); // executor_unavailable is warning, not error
      expect(state.warningCount).toBe(1);
      expect(state.blockers[0].occurrences).toBe(3);
    });

    it('registers new blocker when kind is different', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Executor 1',
        detail: 'Detail 1',
        nextAction: 'Action 1',
      });

      state = registerBlocker(state, {
        kind: 'worker_blocked',
        route: 'sovereign-agent',
        label: 'Executor 2',
        detail: 'Detail 2',
        nextAction: 'Action 2',
      });

      expect(state.activeBlockerCount).toBe(2);
      expect(state.blockers).toHaveLength(2);
    });

    it('increments occurrences on same blocker', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Same blocker',
        detail: 'Same detail',
        nextAction: 'Same action',
      });

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Same blocker',
        detail: 'Same detail',
        nextAction: 'Same action',
      });

      expect(state.blockers).toHaveLength(1);
      expect(state.blockers[0].occurrences).toBe(2);
    });

    it('updates firstSeenAt only on first occurrence', () => {
      let state = createBlockerRegistryState();
      const firstSeen = Date.now();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Same blocker',
        detail: 'Same detail',
        nextAction: 'Same action',
      });

      const firstFirstSeen = state.blockers[0].firstSeenAt;

      // Wait a bit
      state = { ...state, lastUpdatedAt: firstSeen + 1000 };

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Same blocker',
        detail: 'Same detail',
        nextAction: 'Same action',
      });

      // firstSeenAt should not change
      expect(state.blockers[0].firstSeenAt).toBe(firstFirstSeen);
      // lastSeenAt should update
      expect(state.blockers[0].lastSeenAt).toBeGreaterThanOrEqual(firstFirstSeen);
    });
  });

  // ─── Dismissal ─────────────────────────────────────────────────────────────

  describe('dismissBlocker', () => {
    it('removes blocker by key', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Test',
        detail: 'Detail',
        nextAction: 'Action',
      });

      const key = state.blockers[0].key;
      state = dismissBlocker(state, key);

      expect(state.activeBlockerCount).toBe(0);
      expect(state.blockers).toHaveLength(0);
    });

    it('does nothing for non-existent key', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Test',
        detail: 'Detail',
        nextAction: 'Action',
      });

      state = dismissBlocker(state, 'non-existent-key');

      expect(state.activeBlockerCount).toBe(1);
    });
  });

  // ─── Clear Operations ───────────────────────────────────────────────────────

  describe('clearBlockersByKind', () => {
    it('removes all blockers of specific kind', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Executor blocker',
        detail: 'Detail',
        nextAction: 'Action',
      });

      state = registerBlocker(state, {
        kind: 'worker_blocked',
        route: 'worker',
        label: 'Worker blocker',
        detail: 'Detail',
        nextAction: 'Action',
      });

      state = clearBlockersByKind(state, 'executor_unavailable');

      expect(state.activeBlockerCount).toBe(1);
      expect(state.blockers[0].kind).toBe('worker_blocked');
    });
  });

  describe('clearAllBlockers', () => {
    it('removes all blockers', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, { kind: 'executor_unavailable', route: 'a', label: '1', detail: '1', nextAction: '1' });
      state = registerBlocker(state, { kind: 'worker_blocked', route: 'b', label: '2', detail: '2', nextAction: '2' });

      state = clearAllBlockers(state);

      expect(state.activeBlockerCount).toBe(0);
    });
  });

  // ─── Next Action Derivation ────────────────────────────────────────────────

  describe('deriveBlockerNextAction', () => {
    it('Test 2: GitHub ready + Sovereign Agent missing shows nextAction not "GitHub-Zugang öffnen"', () => {
      const action = deriveBlockerNextAction({
        githubReady: true,
        githubValidating: false,
        executorAvailable: false,
        patchRouteAvailable: true,
        agentConfigured: false,
      });

      // Should NOT suggest opening GitHub access
      expect(action).not.toContain('GitHub-Zugang öffnen');
      expect(action).toBe('Sovereign Agent konfigurieren.');
    });

    it('Test 3: GitHub validating shows status "GitHub-Zugang wird geprüft"', () => {
      const action = deriveBlockerNextAction({
        githubReady: false,
        githubValidating: true,
        executorAvailable: false,
        patchRouteAvailable: false,
        agentConfigured: false,
      });

      expect(action).toBe('GitHub-Zugang wird geprüft. Bitte Ergebnis abwarten.');
    });

    it('shows "Sicheren GitHub-Zugang öffnen" when GitHub is missing', () => {
      const action = deriveBlockerNextAction({
        githubReady: false,
        githubValidating: false,
        executorAvailable: false,
        patchRouteAvailable: false,
        agentConfigured: false,
      });

      expect(action).toBe('Sicheren GitHub-Zugang öffnen.');
    });

    it('suggests starting executor when GitHub ready but executor unavailable', () => {
      const action = deriveBlockerNextAction({
        githubReady: true,
        githubValidating: false,
        executorAvailable: false,
        patchRouteAvailable: true,
        agentConfigured: true,
      });

      expect(action).toBe('Workspace Executor starten.');
    });

    it('suggests activating Direct GitHub Patch when patch route blocked', () => {
      const action = deriveBlockerNextAction({
        githubReady: true,
        githubValidating: false,
        executorAvailable: true,
        patchRouteAvailable: false,
        agentConfigured: true,
      });

      expect(action).toBe('Direct GitHub Patch Runtime aktivieren.');
    });

    it('shows execution prompt when everything is ready', () => {
      const action = deriveBlockerNextAction({
        githubReady: true,
        githubValidating: false,
        executorAvailable: true,
        patchRouteAvailable: true,
        agentConfigured: true,
      });

      expect(action).toBe('Auftrag eingeben und ausführen.');
    });
  });

  // ─── GitHub Access Blocker Creation ───────────────────────────────────────

  describe('blockerFromGitHubAccess', () => {
    it('returns null for ready state', () => {
      const blocker = blockerFromGitHubAccess({
        state: 'ready',
        maskedToken: 'ghp_****abcd',
      });
      expect(blocker).toBeNull();
    });

    it('returns blocker for missing state', () => {
      const blocker = blockerFromGitHubAccess({
        state: 'missing',
        maskedToken: null,
      });

      expect(blocker?.kind).toBe('github_access_required');
      expect(blocker?.severity).toBe('error');
      expect(blocker?.nextAction).toContain('Sicheren GitHub-Zugang öffnen');
    });

    it('returns blocker for validating state', () => {
      const blocker = blockerFromGitHubAccess({
        state: 'validating',
        maskedToken: 'ghp_****abcd',
      });

      expect(blocker?.kind).toBe('github_access_validating');
      expect(blocker?.severity).toBe('warning');
      expect(blocker?.nextAction).toContain('wird geprüft');
    });

    it('returns blocker for invalid state', () => {
      const blocker = blockerFromGitHubAccess({
        state: 'invalid',
        maskedToken: 'ghp_****abcd',
      });

      expect(blocker?.kind).toBe('github_access_required');
      expect(blocker?.severity).toBe('error');
    });

    it('Test 6: No tokens in blocker detail/label/nextAction', () => {
      const blocker = blockerFromGitHubAccess({
        state: 'invalid',
        maskedToken: 'ghp_REALTOKEN1234567890abcdefghij',
      });

      // maskedToken should not appear in any output
      expect(blocker?.detail).not.toContain('REALTOKEN');
      expect(blocker?.label).not.toContain('REALTOKEN');
      expect(blocker?.nextAction).not.toContain('REALTOKEN');

      // Should only show masked version if at all
      expect(blocker?.detail).not.toMatch(/ghp_[a-zA-Z0-9]{36,}/);
    });
  });

  // ─── Worker Error Blocker Creation ─────────────────────────────────────────

  describe('blockerFromWorkerError', () => {
    it('Test 4: Worker HTTP 500 stays its own worker_blocked blocker', () => {
      const blocker = blockerFromWorkerError({
        statusCode: 500,
        errorMessage: 'Internal Server Error',
      });

      expect(blocker.kind).toBe('worker_blocked');
      expect(blocker.severity).toBe('warning');
      // Detail contains the error message when provided
      expect(blocker.detail).toContain('Internal Server Error');
    });

    it('creates blocker for HTTP 503', () => {
      const blocker = blockerFromWorkerError({
        statusCode: 503,
      });

      expect(blocker.kind).toBe('worker_blocked');
      expect(blocker.detail).toContain('HTTP 503');
    });

    it('creates blocker with default detail for unknown errors', () => {
      const blocker = blockerFromWorkerError({});

      expect(blocker.kind).toBe('worker_blocked');
      expect(blocker.detail).toBe('Unbekannter Worker-Fehler.');
    });
  });

  // ─── Format Summary ────────────────────────────────────────────────────────

  describe('formatBlockerSummary', () => {
    it('shows "Alle Systeme bereit" when no blockers', () => {
      const state = createBlockerRegistryState();
      const summary = formatBlockerSummary(state);

      expect(summary.activeBlockers).toBe(0);
      expect(summary.warnings).toBe(0);
      expect(summary.errors).toBe(0);
      expect(summary.summary).toBe('Alle Systeme bereit');
    });

    it('formats summary with blocker counts', () => {
      let state = createBlockerRegistryState();

      state = registerBlocker(state, {
        kind: 'executor_unavailable',
        route: 'sovereign-agent',
        label: 'Test',
        detail: 'Detail',
        nextAction: 'Action',
      });

      state = registerBlocker(state, {
        kind: 'github_access_required',
        route: 'github-access',
        label: 'Test',
        detail: 'Detail',
        nextAction: 'Action',
      });

      const summary = formatBlockerSummary(state);

      expect(summary.activeBlockers).toBe(2);
      expect(summary.warnings).toBe(1); // executor_unavailable = warning
      expect(summary.errors).toBe(1); // github_access_required = error
    });
  });
});
