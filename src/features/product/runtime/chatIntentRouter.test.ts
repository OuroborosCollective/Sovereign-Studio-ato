import { describe, it, expect } from 'vitest';
import { routeChatIntent, getIntentPreconditions, getAvailableIntents } from './chatIntentRouter';
import type { ChatIntentRouterInput } from './chatIntentRouter';

const makeInput = (overrides: Partial<ChatIntentRouterInput> = {}): ChatIntentRouterInput => ({
  message: '',
  repoReady: false,
  repoFileCount: 0,
  hasToken: false,
  hasPackage: false,
  hasDraft: false,
  activeBlockers: [],
  hasConcreteMission: undefined,
  selfReviewAccepted: undefined,
  hasDraftCommit: undefined,
  hasWorkflowReport: undefined,
  ...overrides,
});

/**
 * Helper: constructs input with LLM-declared intent.
 * After removing keyword-based detectIntent, callers must pass intent explicitly.
 */
const withIntent = (intent: Parameters<typeof makeInput>[0]['intent'], overrides: Partial<ChatIntentRouterInput> = {}): ChatIntentRouterInput =>
  makeInput({ ...overrides, intent });

describe('ChatIntentRouter', () => {
  describe('routeChatIntent', () => {
    describe('load-repo intent', () => {
      it('accepts LLM-declared load-repo intent when repo is not ready (public repo without token)', () => {
        const result = routeChatIntent(withIntent('load-repo', { repoReady: false, hasToken: false }));
        expect(result.intent).toBe('load-repo');
        expect(result.allowed).toBe(true);
      });

      it('detects GitHub URL via structural pattern — the only permitted local detection', () => {
        const result = routeChatIntent(makeInput({ message: 'https://github.com/owner/repo' }));
        expect(result.intent).toBe('load-repo');
        expect(result.allowed).toBe(true);
      });

      it('does NOT detect load-repo from natural-language keywords — LLM must declare intent', () => {
        // Without explicit intent or GitHub URL, the router returns unknown.
        // Keyword detection ("load repository") is the LLM's responsibility.
        const result = routeChatIntent(makeInput({ message: 'load repository', repoReady: false }));
        expect(result.intent).toBe('unknown');
      });

      it('public repo loads do not require token', () => {
        const result = routeChatIntent(withIntent('load-repo', { repoReady: false, hasToken: false }));
        expect(result.allowed).toBe(true);
      });
    });

    describe('explain-status intent', () => {
      it('always allowed regardless of state when LLM declares intent', () => {
        const result = routeChatIntent(withIntent('explain-status'));
        expect(result.intent).toBe('explain-status');
        expect(result.allowed).toBe(true);
      });

      it('allowed even when draft exists (read-only action)', () => {
        const result = routeChatIntent(withIntent('explain-status', { hasDraft: true }));
        expect(result.intent).toBe('explain-status');
        expect(result.allowed).toBe(true);
      });

      it('does NOT detect explain-status from keywords — LLM must declare intent', () => {
        const result = routeChatIntent(makeInput({ message: 'what is the status' }));
        expect(result.intent).toBe('unknown');
      });
    });

    describe('generate-package intent', () => {
      it('requires repo ready and no blockers', () => {
        const result = routeChatIntent(withIntent('generate-package', {
          repoReady: true,
          repoFileCount: 10,
          activeBlockers: [],
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(true);
      });

      it('blocked when repo is not ready', () => {
        const result = routeChatIntent(withIntent('generate-package', { repoReady: false }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('not ready');
      });

      it('blocked when blockers are active', () => {
        const result = routeChatIntent(withIntent('generate-package', {
          repoReady: true,
          repoFileCount: 10,
          activeBlockers: ['missing-token'],
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('blocker');
      });

      it('blocked when repo has no files', () => {
        const result = routeChatIntent(withIntent('generate-package', {
          repoReady: true,
          repoFileCount: 0,
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('files');
      });

      it('blocked without concrete mission', () => {
        const result = routeChatIntent(withIntent('generate-package', {
          repoReady: true,
          repoFileCount: 10,
          activeBlockers: [],
          hasConcreteMission: false,
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('concrete mission');
      });
    });

    describe('create-draft-pr intent', () => {
      it('requires repo, token, package, and no draft', () => {
        const result = routeChatIntent(withIntent('create-draft-pr', {
          repoReady: true,
          hasToken: true,
          hasPackage: true,
          hasDraft: false,
          repoFileCount: 10,
          activeBlockers: [],
        }));
        expect(result.intent).toBe('create-draft-pr');
        expect(result.allowed).toBe(true);
      });

      it('blocked when no package generated', () => {
        const result = routeChatIntent(withIntent('create-draft-pr', {
          repoReady: true,
          hasToken: true,
          hasPackage: false,
        }));
        expect(result.intent).toBe('create-draft-pr');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('No package');
      });

      it('blocked when draft already exists', () => {
        const result = routeChatIntent(withIntent('create-draft-pr', {
          repoReady: true,
          hasToken: true,
          hasPackage: true,
          hasDraft: true,
          repoFileCount: 10,
        }));
        expect(result.intent).toBe('create-draft-pr');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('draft');
      });

      it('blocked when self-review not accepted', () => {
        const result = routeChatIntent(withIntent('create-draft-pr', {
          repoReady: true,
          hasToken: true,
          hasPackage: true,
          hasDraft: false,
          repoFileCount: 10,
          selfReviewAccepted: false,
        }));
        expect(result.intent).toBe('create-draft-pr');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('review');
      });
    });

    describe('show-diff intent', () => {
      it('allowed when repo ready and has package', () => {
        const result = routeChatIntent(withIntent('show-diff', {
          repoReady: true,
          hasPackage: true,
          repoFileCount: 10,
        }));
        expect(result.intent).toBe('show-diff');
        expect(result.allowed).toBe(true);
      });

      it('blocked when no package', () => {
        const result = routeChatIntent(withIntent('show-diff', {
          repoReady: true,
          hasPackage: false,
        }));
        expect(result.intent).toBe('show-diff');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('No package');
      });

      it('allowed even when draft exists (read-only action)', () => {
        const result = routeChatIntent(withIntent('show-diff', {
          repoReady: true,
          hasPackage: true,
          hasDraft: true,
          repoFileCount: 10,
        }));
        expect(result.intent).toBe('show-diff');
        expect(result.allowed).toBe(true);
      });
    });

    describe('watch-workflow intent', () => {
      it('requires existing draft PR', () => {
        const result = routeChatIntent(withIntent('watch-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: true,
        }));
        expect(result.intent).toBe('watch-workflow');
        expect(result.allowed).toBe(true);
      });

      it('blocked when no draft exists', () => {
        const result = routeChatIntent(withIntent('watch-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: false,
        }));
        expect(result.intent).toBe('watch-workflow');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('draft');
      });

      it('blocked without commit SHA', () => {
        const result = routeChatIntent(withIntent('watch-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: true,
          hasDraftCommit: false,
        }));
        expect(result.intent).toBe('watch-workflow');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('commit');
      });
    });

    describe('repair-workflow intent', () => {
      it('requires existing draft PR', () => {
        const result = routeChatIntent(withIntent('repair-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: true,
        }));
        expect(result.intent).toBe('repair-workflow');
        expect(result.allowed).toBe(true);
      });

      it('blocked without workflow report', () => {
        const result = routeChatIntent(withIntent('repair-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: true,
          hasWorkflowReport: false,
        }));
        expect(result.intent).toBe('repair-workflow');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('Watch the workflow first');
      });
    });

    describe('search-patterns intent', () => {
      it('allowed with any non-empty repo', () => {
        const result = routeChatIntent(withIntent('search-patterns', {
          repoReady: true,
          repoFileCount: 5,
        }));
        expect(result.intent).toBe('search-patterns');
        expect(result.allowed).toBe(true);
      });

      it('blocked when repo is empty', () => {
        const result = routeChatIntent(withIntent('search-patterns', {
          repoReady: true,
          repoFileCount: 0,
        }));
        expect(result.intent).toBe('search-patterns');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('at least 1');
      });
    });

    describe('LLM-declared intent takes precedence over message content', () => {
      it('uses LLM-declared intent regardless of message wording', () => {
        // The message says nothing specific, but LLM declared 'watch-workflow'
        const result = routeChatIntent(withIntent('watch-workflow', {
          repoReady: true,
          hasToken: true,
          hasDraft: true,
          message: 'how is the CI going?',
        }));
        expect(result.intent).toBe('watch-workflow');
      });

      it('without LLM-declared intent and no GitHub URL, result is unknown', () => {
        const result = routeChatIntent(makeInput({ message: 'fix workflow' }));
        expect(result.intent).toBe('unknown');
      });

      it('without LLM-declared intent and no GitHub URL, generic bug fix is unknown', () => {
        const result = routeChatIntent(makeInput({ message: 'repair broken login' }));
        expect(result.intent).toBe('unknown');
      });
    });

    describe('unknown intent', () => {
      it('returns unknown when no intent declared and message is not a GitHub URL', () => {
        const result = routeChatIntent(makeInput({ message: 'xyz123 nonsense' }));
        expect(result.intent).toBe('unknown');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('Enter a clear mission');
      });
    });

    describe('targetTab mapping', () => {
      it('returns correct target tab for each LLM-declared intent', () => {
        expect(routeChatIntent(withIntent('load-repo')).targetTab).toBe('repo');
        expect(routeChatIntent(withIntent('generate-package', { repoReady: true, repoFileCount: 10 })).targetTab).toBe('builder');
        expect(routeChatIntent(withIntent('create-draft-pr', { repoReady: true, hasToken: true, hasPackage: true })).targetTab).toBe('files');
        expect(routeChatIntent(withIntent('show-diff', { repoReady: true, hasPackage: true })).targetTab).toBe('diff');
        expect(routeChatIntent(withIntent('watch-workflow', { repoReady: true, hasToken: true, hasDraft: true })).targetTab).toBe('workflow');
        expect(routeChatIntent(withIntent('repair-workflow', { repoReady: true, hasToken: true, hasDraft: true })).targetTab).toBe('repair');
      });

      it('returns undefined for explain-status', () => {
        const result = routeChatIntent(withIntent('explain-status'));
        expect(result.targetTab).toBeUndefined();
      });
    });
  });

  describe('getIntentPreconditions', () => {
    it('returns preconditions for valid intent', () => {
      const preconditions = getIntentPreconditions('generate-package');
      expect(preconditions.requiredRepoReady).toBe(true);
      expect(preconditions.requiredHasPackage).toBe(false);
    });

    it('load-repo allows public repos without token', () => {
      const preconditions = getIntentPreconditions('load-repo');
      expect(preconditions.requiredHasToken).toBe(false);
    });
  });

  describe('getAvailableIntents', () => {
    it('returns intents that are allowed with given state', () => {
      const available = getAvailableIntents({
        repoReady: true,
        hasToken: true,
        hasPackage: true,
        hasDraft: false,
        repoFileCount: 20,
        activeBlockers: [],
      });

      expect(available).toContain('generate-package');
      expect(available).toContain('create-draft-pr');
      expect(available).toContain('show-diff');
    });

    it('returns explain-status and load-repo when no repo loaded', () => {
      const available = getAvailableIntents({
        repoReady: false,
        hasToken: true,
        hasPackage: false,
        hasDraft: false,
        repoFileCount: 0,
        activeBlockers: [],
      });

      expect(available).toContain('explain-status');
      expect(available).toContain('load-repo');
    });

    it('read-only intents remain available when draft exists', () => {
      const available = getAvailableIntents({
        repoReady: true,
        hasToken: true,
        hasPackage: true,
        hasDraft: true,
        repoFileCount: 10,
        activeBlockers: [],
      });

      expect(available).toContain('explain-status');
      expect(available).toContain('show-diff');
      expect(available).toContain('watch-workflow');
      expect(available).toContain('search-patterns');
      expect(available).not.toContain('create-draft-pr');
    });
  });
});
