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
  ...overrides,
});

describe('ChatIntentRouter', () => {
  describe('routeChatIntent', () => {
    describe('load-repo intent', () => {
      it('detects load-repo when repo is not ready', () => {
        const result = routeChatIntent(makeInput({ message: 'load repository', repoReady: false, hasToken: true }));
        expect(result.intent).toBe('load-repo');
        expect(result.allowed).toBe(true);
      });

      it('requires token for load-repo', () => {
        const result = routeChatIntent(makeInput({ message: 'load repository', repoReady: false, hasToken: false }));
        expect(result.intent).toBe('load-repo');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('token');
      });
    });

    describe('explain-status intent', () => {
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
    });

    describe('generate-package intent', () => {
      it('requires repo ready and no blockers', () => {
        const result = routeChatIntent(makeInput({
          message: 'generate package',
          repoReady: true,
          repoFileCount: 10,
          activeBlockers: [],
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(true);
      });

      it('blocked when repo is not ready', () => {
        const result = routeChatIntent(makeInput({
          message: 'generate package',
          repoReady: false,
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('not ready');
      });

      it('blocked when blockers are active', () => {
        const result = routeChatIntent(makeInput({
          message: 'generate package',
          repoReady: true,
          repoFileCount: 10,
          activeBlockers: ['missing-token'],
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('blocker');
      });

      it('blocked when repo has no files', () => {
        const result = routeChatIntent(makeInput({
          message: 'generate package',
          repoReady: true,
          repoFileCount: 0,
        }));
        expect(result.intent).toBe('generate-package');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('files');
      });
    });

    describe('create-draft-pr intent', () => {
      it('requires repo, token, package, and no draft', () => {
        const result = routeChatIntent(makeInput({
          message: 'create draft pr',
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
        const result = routeChatIntent(makeInput({
          message: 'create draft pr',
          repoReady: true,
          hasToken: true,
          hasPackage: false,
        }));
        expect(result.intent).toBe('create-draft-pr');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('No package');
      });

      it('blocked when draft already exists', () => {
        const result = routeChatIntent(makeInput({
          message: 'create draft pr',
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
    });

    describe('show-diff intent', () => {
      it('allowed when repo ready and has package', () => {
        const result = routeChatIntent(makeInput({
          message: 'show diff',
          repoReady: true,
          hasPackage: true,
          repoFileCount: 10,
        }));
        expect(result.intent).toBe('show-diff');
        expect(result.allowed).toBe(true);
      });

      it('blocked when no package', () => {
        const result = routeChatIntent(makeInput({
          message: 'show diff',
          repoReady: true,
          hasPackage: false,
        }));
        expect(result.intent).toBe('show-diff');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('No package');
      });
    });

    describe('watch-workflow intent', () => {
      it('requires existing draft PR', () => {
        const result = routeChatIntent(makeInput({
          message: 'watch workflow',
          repoReady: true,
          hasToken: true,
          hasDraft: true,
        }));
        expect(result.intent).toBe('watch-workflow');
        expect(result.allowed).toBe(true);
      });

      it('blocked when no draft exists', () => {
        const result = routeChatIntent(makeInput({
          message: 'watch workflow',
          repoReady: true,
          hasToken: true,
          hasDraft: false,
        }));
        expect(result.intent).toBe('watch-workflow');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('draft');
      });
    });

    describe('repair-workflow intent', () => {
      it('requires existing draft PR', () => {
        const result = routeChatIntent(makeInput({
          message: 'repair workflow',
          repoReady: true,
          hasToken: true,
          hasDraft: true,
        }));
        expect(result.intent).toBe('repair-workflow');
        expect(result.allowed).toBe(true);
      });
    });

    describe('search-patterns intent', () => {
      it('requires at least 10 files', () => {
        const result = routeChatIntent(makeInput({
          message: 'search patterns',
          repoReady: true,
          repoFileCount: 15,
        }));
        expect(result.intent).toBe('search-patterns');
        expect(result.allowed).toBe(true);
      });

      it('blocked when file count too low', () => {
        const result = routeChatIntent(makeInput({
          message: 'search patterns',
          repoReady: true,
          repoFileCount: 5,
        }));
        expect(result.intent).toBe('search-patterns');
        expect(result.allowed).toBe(false);
        expect(result.blockedReason).toContain('at least 10');
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
      it('returns correct target tab for each intent', () => {
        expect(routeChatIntent(makeInput({ message: 'load repo', repoReady: false, hasToken: true })).targetTab).toBe('repo');
        expect(routeChatIntent(makeInput({ message: 'generate package', repoReady: true, repoFileCount: 10 })).targetTab).toBe('builder');
        expect(routeChatIntent(makeInput({ message: 'draft pr', repoReady: true, hasToken: true, hasPackage: true })).targetTab).toBe('files');
        expect(routeChatIntent(makeInput({ message: 'show diff', repoReady: true, hasPackage: true })).targetTab).toBe('diff');
        expect(routeChatIntent(makeInput({ message: 'watch workflow', repoReady: true, hasToken: true, hasDraft: true })).targetTab).toBe('workflow');
        expect(routeChatIntent(makeInput({ message: 'repair workflow', repoReady: true, hasToken: true, hasDraft: true })).targetTab).toBe('repair');
      });

      it('returns undefined for explain-status', () => {
        const result = routeChatIntent(makeInput({ message: 'status' }));
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

    it('returns explain-status and load-repo when no repo loaded but has token', () => {
      const available = getAvailableIntents({
        repoReady: false,
        hasToken: true, // token available - can load repo
        hasPackage: false,
        hasDraft: false,
        repoFileCount: 0,
        activeBlockers: [],
      });

      expect(available).toContain('explain-status');
      expect(available).toContain('load-repo');
    });
  });
});