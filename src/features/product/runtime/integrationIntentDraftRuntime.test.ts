import { describe, expect, it, beforeEach } from 'vitest';
import {
  createIntegrationIntentDraft,
  formatIntegrationIntentDraft,
  canConfirmIntegrationIntentDraft,
  reduceIntegrationIntentDraftAction,
  buildDraftCreatedEvent,
  buildDraftConfirmedEvent,
  buildDraftRejectedEvent,
  buildRouteStartedEvent,
  buildRouteBlockedEvent,
  createInitialDraftState,
  isConfirmedDraft,
  hasPendingDraft,
  getCurrentDraft,
  type IntegrationIntentDraftState,
} from './integrationIntentDraftRuntime';
import type { RepoFile } from '../../github/types';

describe('integrationIntentDraftRuntime', () => {
  // ─────────────────────────────────────────────────────────────
  // createIntegrationIntentDraft
  // ─────────────────────────────────────────────────────────────

  describe('createIntegrationIntentDraft', () => {
    it('creates draft from normal implementation text', () => {
      const input = 'Der Bot soll jede Eingabe als Integrationsauftrag verstehen';
      const draft = createIntegrationIntentDraft(input, undefined, { now: 1700000000000, idSeed: 'test1' });

      expect(draft).not.toBeNull();
      expect(draft?.title).toBe('Der Bot soll jede Eingabe als Integrationsauftrag verstehen');
      expect(draft?.goal).toBeTruthy();
      expect(draft?.originalText).toBe(input);
      expect(draft?.id).toBe('draft_test1');
      expect(draft?.createdAt).toBe(1700000000000);
    });

    it('returns null for questions ending with ?', () => {
      const input = 'Wie sollte die Oberfläche besser werden?';
      const draft = createIntegrationIntentDraft(input);
      expect(draft).toBeNull();
    });

    it('returns null for very short inputs', () => {
      expect(createIntegrationIntentDraft('Hi')).toBeNull();
      expect(createIntegrationIntentDraft('ok')).toBeNull();
      expect(createIntegrationIntentDraft('ab')).toBeNull();
    });

    it('returns null for slash commands', () => {
      const input = '/repo owner/name';
      const draft = createIntegrationIntentDraft(input);
      expect(draft).toBeNull();
    });

    it('returns null for GitHub URLs', () => {
      const input = 'https://github.com/owner/repo';
      const draft = createIntegrationIntentDraft(input);
      expect(draft).toBeNull();
    });

    it('returns null for greetings', () => {
      expect(createIntegrationIntentDraft('Hallo')).toBeNull();
      expect(createIntegrationIntentDraft('Hello world')).toBeNull();
      expect(createIntegrationIntentDraft('Danke für die Hilfe')).toBeNull();
    });

    // ── Issue #522: P2 Fix 2 & 4 - Status/Retry Intents and Placeholder Missions

    it('returns null for status queries (P2 Fix 2)', () => {
      expect(createIntegrationIntentDraft('Was ist der Status?')).toBeNull();
      expect(createIntegrationIntentDraft('Wie ist der Stand?')).toBeNull();
      expect(createIntegrationIntentDraft('Status')).toBeNull();
      expect(createIntegrationIntentDraft('Fortschritt?')).toBeNull();
      expect(createIntegrationIntentDraft('Was läuft gerade?')).toBeNull();
    });

    it('returns null for retry intents (P2 Fix 2)', () => {
      expect(createIntegrationIntentDraft('Nochmal')).toBeNull();
      expect(createIntegrationIntentDraft('Noch ein Versuch')).toBeNull();
      expect(createIntegrationIntentDraft('Versuch es nochmal')).toBeNull();
      expect(createIntegrationIntentDraft('Es klappt nicht')).toBeNull();
      expect(createIntegrationIntentDraft('Funktioniert nicht')).toBeNull();
    });

    it('returns null for placeholder missions (P2 Fix 4)', () => {
      // Basic placeholders
      expect(createIntegrationIntentDraft('Fehler')).toBeNull();
      expect(createIntegrationIntentDraft('Idee')).toBeNull();
      expect(createIntegrationIntentDraft('Ideen')).toBeNull();
      expect(createIntegrationIntentDraft('Plan')).toBeNull();
      expect(createIntegrationIntentDraft('Workflow')).toBeNull();
      expect(createIntegrationIntentDraft('Mach weiter')).toBeNull();
      
      // Issue #522 P2 Fix 4: Extended vague placeholders
      expect(createIntegrationIntentDraft('Weiter')).toBeNull();
      expect(createIntegrationIntentDraft('Mach was')).toBeNull();
      expect(createIntegrationIntentDraft('Mach etwas')).toBeNull();
      expect(createIntegrationIntentDraft('Fix me')).toBeNull();
      
      // Single-word short vague commands
      expect(createIntegrationIntentDraft('Hilf')).toBeNull();
      expect(createIntegrationIntentDraft('Hilfe')).toBeNull();
    });

    it('extracts correct goal for fix intent', () => {
      const input = 'Fix den Bug im Chat';
      const draft = createIntegrationIntentDraft(input);
      expect(draft?.goal).toBe('Fehler beheben');
    });

    it('extracts correct scope for UI-related input', () => {
      const input = 'Die UI soll verbessert werden';
      const draft = createIntegrationIntentDraft(input);
      expect(draft?.scope).toContain('UI/Komponenten');
    });

    it('extracts affected files from repo context', () => {
      const repoFiles: RepoFile[] = [
        { path: 'src/components/Chat.tsx', type: 'blob' },
        { path: 'src/runtime/router.ts', type: 'blob' },
        { path: 'docs/readme.md', type: 'blob' },
      ];
      const input = 'Verbesser den Chat';
      const draft = createIntegrationIntentDraft(input, repoFiles, { now: 1700000000000, idSeed: 'files-test' });
      expect(draft?.affectedFiles).toContain('src/components/Chat.tsx');
    });

    it('draft contains no tokens in sensitive fields', () => {
      const input = 'Test input without secrets';
      const draft = createIntegrationIntentDraft(input, undefined, { now: 1700000000000, idSeed: 'tokens-test' });

      expect(draft?.title).not.toContain('sk-');
      expect(draft?.title).not.toContain('ghp_');
      expect(draft?.goal).not.toContain('sk-');
      expect(draft?.originalText).not.toContain('sk-');
    });

    it('limits affected files to 5 suggestions', () => {
      const repoFiles: RepoFile[] = Array.from({ length: 10 }, (_, i) => ({
        path: `src/components/Component${i}.tsx`,
        type: 'blob' as const,
      }));
      const input = 'Verbesser die UI Komponenten';
      const draft = createIntegrationIntentDraft(input, repoFiles, { now: 1700000000000, idSeed: 'limit-test' });
      expect(draft?.affectedFiles.length).toBeLessThanOrEqual(5);
    });
  });

  // ─────────────────────────────────────────────────────────────
  // formatIntegrationIntentDraft
  // ─────────────────────────────────────────────────────────────

  describe('formatIntegrationIntentDraft', () => {
    it('formats draft with all fields', () => {
      const draft = createIntegrationIntentDraft('Implementiere einen neuen Button', undefined, { now: 1700000000000, idSeed: 'format-test' });
      if (!draft) throw new Error('Draft should not be null');

      const formatted = formatIntegrationIntentDraft(draft);

      expect(formatted.title).toBe('Implementiere einen neuen Button');
      expect(formatted.goal).toBeTruthy();
      expect(Array.isArray(formatted.scope)).toBe(true);
      expect(Array.isArray(formatted.affectedFiles)).toBe(true);
    });
  });

  // ─────────────────────────────────────────────────────────────
  // canConfirmIntegrationIntentDraft
  // ─────────────────────────────────────────────────────────────

  describe('canConfirmIntegrationIntentDraft', () => {
    it('allows confirm when repo is ready', () => {
      const draft = createIntegrationIntentDraft('Test input', undefined, { now: 1700000000000, idSeed: 'confirm-seed' });
      if (!draft) throw new Error('Draft should not be null');

      const result = canConfirmIntegrationIntentDraft(draft, {
        repoReady: true,
        githubWriteReady: true,
        directPatchReady: false,
        agentReady: false,
      });

      expect(result.canConfirm).toBe(true);
    });

    it('blocks confirm when repo is not ready', () => {
      const draft = createIntegrationIntentDraft('Test input', undefined, { now: 1700000000000, idSeed: 'confirm-seed' });
      if (!draft) throw new Error('Draft should not be null');

      const result = canConfirmIntegrationIntentDraft(draft, {
        repoReady: false,
        githubWriteReady: true,
        directPatchReady: false,
        agentReady: false,
      });

      expect(result.canConfirm).toBe(false);
      expect(result.blocker).toContain('Repository nicht geladen');
    });

    it('blocks confirm when sovereign-agent is ready but github is missing', () => {
      // P1 Fix: Sovereign Agent without GitHub write should be blocked
      const draft = createIntegrationIntentDraft('Test input', undefined, { now: 1700000000000, idSeed: 'confirm-seed' });
      if (!draft) throw new Error('Draft should not be null');

      const result = canConfirmIntegrationIntentDraft(draft, {
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: true,
      });

      expect(result.canConfirm).toBe(false);
      expect(result.blocker).toContain('GitHub-Zugang erforderlich');
    });

    it('allows confirm when direct patch is ready', () => {
      const draft = createIntegrationIntentDraft('Test input', undefined, { now: 1700000000000, idSeed: 'confirm-seed' });
      if (!draft) throw new Error('Draft should not be null');

      const result = canConfirmIntegrationIntentDraft(draft, {
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: true,
        agentReady: false,
      });

      expect(result.canConfirm).toBe(true);
    });

    it('blocks confirm when no execution path is available', () => {
      const draft = createIntegrationIntentDraft('Test input', undefined, { now: 1700000000000, idSeed: 'confirm-seed' });
      if (!draft) throw new Error('Draft should not be null');

      const result = canConfirmIntegrationIntentDraft(draft, {
        repoReady: true,
        githubWriteReady: false,
        directPatchReady: false,
        agentReady: false,
      });

      expect(result.canConfirm).toBe(false);
      expect(result.blocker).toContain('Kein Ausführungspfad');
    });
  });

  // ─────────────────────────────────────────────────────────────
  // reduceIntegrationIntentDraftAction
  // ─────────────────────────────────────────────────────────────

  describe('reduceIntegrationIntentDraftAction', () => {
    let initialState: IntegrationIntentDraftState;

    beforeEach(() => {
      initialState = createInitialDraftState();
    });

    it('creates draft on CREATE_DRAFT', () => {
      const newState = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: 'Test integration task',
      });

      expect(hasPendingDraft(newState)).toBe(true);
      if (hasPendingDraft(newState)) {
        expect(newState.draft.originalText).toBe('Test integration task');
      }
    });

    it('returns idle when CREATE_DRAFT with invalid input', () => {
      const newState = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: '?',
      });

      expect(newState.status).toBe('idle');
    });

    it('confirms pending draft on CONFIRM_DRAFT', () => {
      let state = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: 'Test task',
      });
      state = reduceIntegrationIntentDraftAction(state, { type: 'CONFIRM_DRAFT' });

      expect(isConfirmedDraft(state)).toBe(true);
    });

    it('rejects pending draft on REJECT_DRAFT', () => {
      let state = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: 'Test task',
      });
      state = reduceIntegrationIntentDraftAction(state, { type: 'REJECT_DRAFT' });

      expect(state.status).toBe('rejected');
    });

    it('rephrases pending draft on REPHRASE_DRAFT', () => {
      let state = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: 'Test task',
      });
      state = reduceIntegrationIntentDraftAction(state, { type: 'REPHRASE_DRAFT' });

      expect(state.status).toBe('rephrased');
      if (state.status === 'rephrased') {
        expect(state.rephrasedText).toBeTruthy();
      }
    });

    it('clears draft on CLEAR_DRAFT', () => {
      let state = reduceIntegrationIntentDraftAction(initialState, {
        type: 'CREATE_DRAFT',
        input: 'Test task',
      });
      state = reduceIntegrationIntentDraftAction(state, { type: 'CLEAR_DRAFT' });

      expect(state.status).toBe('idle');
    });

    it('does nothing when confirming idle state', () => {
      const state = reduceIntegrationIntentDraftAction(initialState, { type: 'CONFIRM_DRAFT' });
      expect(state.status).toBe('idle');
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Query helpers
  // ─────────────────────────────────────────────────────────────

  describe('query helpers', () => {
    it('isConfirmedDraft returns true only for confirmed state', () => {
      const idle: IntegrationIntentDraftState = { status: 'idle' };
      expect(isConfirmedDraft(idle)).toBe(false);

      const pending: IntegrationIntentDraftState = {
        status: 'pending',
        draft: createIntegrationIntentDraft('test', undefined, { now: 1700000000000, idSeed: 'query-test' })!,
      };
      expect(isConfirmedDraft(pending)).toBe(false);

      const confirmed: IntegrationIntentDraftState = {
        status: 'confirmed',
        draft: createIntegrationIntentDraft('test', undefined, { now: 1700000000000, idSeed: 'query-test' })!,
      };
      expect(isConfirmedDraft(confirmed)).toBe(true);
    });

    it('hasPendingDraft returns true only for pending state', () => {
      const idle: IntegrationIntentDraftState = { status: 'idle' };
      expect(hasPendingDraft(idle)).toBe(false);

      const pending: IntegrationIntentDraftState = {
        status: 'pending',
        draft: createIntegrationIntentDraft('test', undefined, { now: 1700000000000, idSeed: 'query-test' })!,
      };
      expect(hasPendingDraft(pending)).toBe(true);
    });

    it('getCurrentDraft returns draft only when present', () => {
      const idle: IntegrationIntentDraftState = { status: 'idle' };
      expect(getCurrentDraft(idle)).toBeNull();

      const pending: IntegrationIntentDraftState = {
        status: 'pending',
        draft: createIntegrationIntentDraft('test', undefined, { now: 1700000000000, idSeed: 'query-test' })!,
      };
      expect(getCurrentDraft(pending)).not.toBeNull();
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Action event builders
  // ─────────────────────────────────────────────────────────────

  describe('action event builders', () => {
    it('buildDraftCreatedEvent creates valid event', () => {
      const draft = createIntegrationIntentDraft('Test task', undefined, { now: 1700000000000, idSeed: 'event-test' });
      if (!draft) throw new Error('Draft should not be null');

      const event = buildDraftCreatedEvent(draft);

      expect(event.kind).toBe('intent_detected');
      expect(event.route).toBe('runtime');
      expect(event.state).toBe('done');
      expect(event.detail).toBe(draft.title);
    });

    it('buildDraftConfirmedEvent creates valid event', () => {
      const draft = createIntegrationIntentDraft('Test task', undefined, { now: 1700000000000, idSeed: 'event-test' });
      if (!draft) throw new Error('Draft should not be null');

      const event = buildDraftConfirmedEvent(draft);

      expect(event.kind).toBe('route_selected');
      expect(event.state).toBe('done');
    });

    it('buildDraftRejectedEvent creates blocked event', () => {
      const event = buildDraftRejectedEvent();

      expect(event.kind).toBe('blocked');
      expect(event.state).toBe('blocked');
    });

    it('buildRouteStartedEvent stays queued until runtime start evidence exists', () => {
      const event = buildRouteStartedEvent('sovereign-agent');

      expect(event.kind).toBe('route_selected');
      expect(event.state).toBe('queued');
      expect(event.detail).toContain('Runtime-Start-Evidence');
    });

    it('buildRouteBlockedEvent creates blocked event', () => {
      const event = buildRouteBlockedEvent('No executor available');

      expect(event.kind).toBe('blocked');
      expect(event.state).toBe('blocked');
      expect(event.detail).toBe('No executor available');
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Edge cases
  // ─────────────────────────────────────────────────────────────

  describe('edge cases', () => {
    it('handles empty scope gracefully', () => {
      const input = 'Baue etwas';
      const draft = createIntegrationIntentDraft(input);

      // "Baue etwas" contains "baue" which is a goal keyword, not scope
      // The scope should be derived from actual patterns
      expect(draft?.scope).toBeTruthy();
    });

    it('handles rephrased text when already imperative', () => {
      const input = 'Baue einen neuen Button';
      const draft = createIntegrationIntentDraft(input);

      // Already starts with action verb, rephrased should match original
      expect(draft?.rephrasedText).toBeTruthy();
    });

    it('caps title length at 80 characters', () => {
      const longInput = 'A'.repeat(100);
      const draft = createIntegrationIntentDraft(longInput);

      expect(draft?.title.length).toBeLessThanOrEqual(80);
    });

    it('generates deterministic IDs when seed provided', () => {
      const draft1 = createIntegrationIntentDraft('Task 1', undefined, { now: 1700000000000, idSeed: 'det-1' });
      const draft2 = createIntegrationIntentDraft('Task 2', undefined, { now: 1700000000000, idSeed: 'det-2' });

      if (!draft1 || !draft2) throw new Error('Drafts should not be null');
      expect(draft1.id).toBe('draft_det-1');
      expect(draft2.id).toBe('draft_det-2');
      expect(draft1.id).not.toBe(draft2.id);
    });
  });
});
