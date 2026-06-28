import { describe, it, expect } from 'vitest';
import { routeChatIntent, getAvailableIntents } from './chatIntentRouter';
import type { ChatIntentRouterInput } from './chatIntentRouter';

const makeInput = (overrides: Partial<ChatIntentRouterInput> = {}): ChatIntentRouterInput => ({
  message: '', repoReady: false, repoFileCount: 0, hasToken: false, hasPackage: false, hasDraft: false,
  activeBlockers: [], hasConcreteMission: undefined, selfReviewAccepted: undefined,
  hasDraftCommit: undefined, hasWorkflowReport: undefined, workflowFailed: undefined, ...overrides,
});

describe('ChatIntentRouter', () => {
  describe('load-repo', () => {
    it('detects load-repo for public repo without token', () => {
      const result = routeChatIntent(makeInput({ message: 'load repository', repoReady: false, hasToken: false }));
      expect(result.intent).toBe('load-repo');
      expect(result.allowed).toBe(true);
    });
    it('accepts GitHub URL as load-repo intent', () => {
      const result = routeChatIntent(makeInput({ message: 'https://github.com/owner/repo' }));
      expect(result.intent).toBe('load-repo');
      expect(result.allowed).toBe(true);
    });
  });

  describe('explain-status', () => {
    it('always allowed regardless of state', () => {
      const result = routeChatIntent(makeInput({ message: 'what is the status' }));
      expect(result.intent).toBe('explain-status');
      expect(result.allowed).toBe(true);
    });
    it('detects German status requests', () => {
      const result = routeChatIntent(makeInput({ message: 'was ist der status' }));
      expect(result.intent).toBe('explain-status');
      expect(result.allowed).toBe(true);
    });
    it('allowed even when draft exists (read-only)', () => {
      const result = routeChatIntent(makeInput({ message: 'status', hasDraft: true }));
      expect(result.intent).toBe('explain-status');
      expect(result.allowed).toBe(true);
    });
  });

  describe('generate-package', () => {
    it('requires repo ready, no blockers, and concrete mission', () => {
      const result = routeChatIntent(makeInput({ message: 'generate package', repoReady: true, repoFileCount: 10, activeBlockers: [], hasConcreteMission: true }));
      expect(result.intent).toBe('generate-package');
      expect(result.allowed).toBe(true);
    });
    it('blocked when repo is not ready', () => {
      const result = routeChatIntent(makeInput({ message: 'generate package', repoReady: false, hasConcreteMission: true }));
      expect(result.intent).toBe('generate-package');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('not ready');
    });
    it('blocked without concrete mission (undefined)', () => {
      const result = routeChatIntent(makeInput({ message: 'generate package', repoReady: true, repoFileCount: 10, activeBlockers: [] }));
      expect(result.intent).toBe('generate-package');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('concrete mission');
    });
    it('blocked when concrete mission is false', () => {
      const result = routeChatIntent(makeInput({ message: 'generate package', repoReady: true, repoFileCount: 10, activeBlockers: [], hasConcreteMission: false }));
      expect(result.intent).toBe('generate-package');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('concrete mission');
    });
  });

  describe('create-draft-pr', () => {
    it('requires repo, token, package, self-review, and no draft', () => {
      const result = routeChatIntent(makeInput({ message: 'create draft pr', repoReady: true, hasToken: true, hasPackage: true, hasDraft: false, repoFileCount: 10, selfReviewAccepted: true }));
      expect(result.intent).toBe('create-draft-pr');
      expect(result.allowed).toBe(true);
    });
    it('blocked when no package generated', () => {
      const result = routeChatIntent(makeInput({ message: 'create draft pr', repoReady: true, hasToken: true, hasPackage: false, selfReviewAccepted: true }));
      expect(result.intent).toBe('create-draft-pr');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('No package');
    });
    it('blocked when self-review not evaluated (undefined)', () => {
      const result = routeChatIntent(makeInput({ message: 'create draft pr', repoReady: true, hasToken: true, hasPackage: true, hasDraft: false, repoFileCount: 10 }));
      expect(result.intent).toBe('create-draft-pr');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('review');
    });
  });

  describe('watch-workflow', () => {
    it('requires existing draft PR and commit SHA', () => {
      const result = routeChatIntent(makeInput({ message: 'watch workflow', repoReady: true, hasToken: true, hasDraft: true, hasDraftCommit: true }));
      expect(result.intent).toBe('watch-workflow');
      expect(result.allowed).toBe(true);
    });
    it('blocked when no draft exists', () => {
      const result = routeChatIntent(makeInput({ message: 'watch workflow', repoReady: true, hasToken: true, hasDraft: false }));
      expect(result.intent).toBe('watch-workflow');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('draft');
    });
    it('blocked without commit SHA (undefined)', () => {
      const result = routeChatIntent(makeInput({ message: 'watch workflow', repoReady: true, hasToken: true, hasDraft: true }));
      expect(result.intent).toBe('watch-workflow');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('commit');
    });
  });

  describe('repair-workflow', () => {
    it('requires existing draft PR, workflow report, and failed workflow', () => {
      const result = routeChatIntent(makeInput({ message: 'fix workflow', repoReady: true, hasToken: true, hasDraft: true, hasWorkflowReport: true, workflowFailed: true }));
      expect(result.intent).toBe('repair-workflow');
      expect(result.allowed).toBe(true);
    });
    it('blocked without workflow report', () => {
      const result = routeChatIntent(makeInput({ message: 'fix workflow', repoReady: true, hasToken: true, hasDraft: true, workflowFailed: true }));
      expect(result.intent).toBe('repair-workflow');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('Watch the workflow first');
    });
    it('blocked without workflow failure', () => {
      const result = routeChatIntent(makeInput({ message: 'fix workflow', repoReady: true, hasToken: true, hasDraft: true, hasWorkflowReport: true, workflowFailed: false }));
      expect(result.intent).toBe('repair-workflow');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('must have failed');
    });
    it('detects fix failed workflow', () => {
      const result = routeChatIntent(makeInput({ message: 'fix failed workflow' }));
      expect(result.intent).toBe('repair-workflow');
    });
    it('detects fix ci', () => {
      const result = routeChatIntent(makeInput({ message: 'fix ci' }));
      expect(result.intent).toBe('repair-workflow');
    });
  });

  describe('intent detection priority', () => {
    it('workflow signals take priority over generic status', () => {
      const result = routeChatIntent(makeInput({ message: 'ci status' }));
      expect(result.intent).toBe('watch-workflow');
    });
    it('repair signals take priority over watch', () => {
      const result = routeChatIntent(makeInput({ message: 'fix workflow' }));
      expect(result.intent).toBe('repair-workflow');
    });
    it('pull request status routes to status', () => {
      const result = routeChatIntent(makeInput({ message: 'pull request status' }));
      expect(result.intent).toBe('explain-status');
    });
    it('URL without action routes to load-repo', () => {
      const result = routeChatIntent(makeInput({ message: 'https://github.com/owner/repo' }));
      expect(result.intent).toBe('load-repo');
    });
    it('URL with action routes to that action', () => {
      const result = routeChatIntent(makeInput({ message: 'show diff https://github.com/owner/repo' }));
      expect(result.intent).toBe('show-diff');
    });
  });

  describe('unknown intent', () => {
    it('returns unknown for unrecognized messages', () => {
      const result = routeChatIntent(makeInput({ message: 'xyz123 nonsense' }));
      expect(result.intent).toBe('unknown');
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('Enter a clear mission');
    });
  });

  describe('targetTab mapping', () => {
    it('returns correct target tabs', () => {
      expect(routeChatIntent(makeInput({ message: 'load repo' })).targetTab).toBe('repo');
      expect(routeChatIntent(makeInput({ message: 'generate package', repoReady: true, repoFileCount: 10 })).targetTab).toBe('builder');
      expect(routeChatIntent(makeInput({ message: 'watch workflow', repoReady: true, hasToken: true, hasDraft: true, hasDraftCommit: true })).targetTab).toBe('workflow');
    });
  });

  describe('getAvailableIntents', () => {
    it('returns intents that are allowed with given state', () => {
      const available = getAvailableIntents({ repoReady: true, hasToken: true, hasPackage: true, hasDraft: false, repoFileCount: 20, activeBlockers: [], hasConcreteMission: true, selfReviewAccepted: true });
      expect(available).toContain('generate-package');
      expect(available).toContain('create-draft-pr');
      expect(available).toContain('show-diff');
    });
    it('read-only intents remain available when draft exists', () => {
      const available = getAvailableIntents({ repoReady: true, hasToken: true, hasPackage: true, hasDraft: true, repoFileCount: 10, activeBlockers: [], hasConcreteMission: true, selfReviewAccepted: true, hasDraftCommit: true, hasWorkflowReport: true, workflowFailed: false });
      expect(available).toContain('explain-status');
      expect(available).toContain('show-diff');
      expect(available).toContain('search-patterns');
      expect(available).not.toContain('create-draft-pr');
    });
  });
});
