import { describe, expect, it } from 'vitest';
import type { RepoFile } from '../../github/types';
import {
  createInitialRepoAccessState,
  computeRepoAccessState,
  isRepoReady,
  getBlockingError,
  computeAutomationReadiness,
  buildAutomationRunKey,
  computeBotStatus,
  type RepoAccessState,
} from './repoAccessState';

const mockRepoFiles: RepoFile[] = [
  { path: 'README.md', type: 'blob' },
  { path: 'package.json', type: 'blob' },
  { path: 'src/index.ts', type: 'blob' },
];

describe('repoAccessState', () => {
  describe('createInitialRepoAccessState', () => {
    it('creates empty state', () => {
      const state = createInitialRepoAccessState();
      
      expect(state.repoUrl).toBe('');
      expect(state.repoBranch).toBe('main');
      expect(state.githubTokenPresent).toBe(false);
      expect(state.repoFiles).toEqual([]);
      expect(state.repoSnapshotStatus.ready).toBe(false);
      expect(state.lastRepoLoadAt).toBeNull();
      expect(state.lastRepoLoadError).toBeNull();
    });
  });

  describe('isRepoReady', () => {
    it('returns true when repo has files and is ready', () => {
      const state: RepoAccessState = {
        repoUrl: 'https://github.com/owner/repo',
        repoBranch: 'main',
        githubTokenPresent: true,
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
        lastRepoLoadAt: 1,
        lastRepoLoadError: null,
      };
      
      expect(isRepoReady(state)).toBe(true);
    });

    it('returns false when no files', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: [],
        repoSnapshotStatus: { ready: false, fileCount: 0, reason: 'No files' },
      };
      
      expect(isRepoReady(state)).toBe(false);
    });

    it('returns false when snapshot not ready', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: false, fileCount: 0, reason: 'Loading...' },
      };
      
      expect(isRepoReady(state)).toBe(false);
    });
  });

  describe('getBlockingError', () => {
    it('returns load error if present', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
        lastRepoLoadError: 'Failed to fetch repo',
      };
      
      expect(getBlockingError(state)).toBe('Failed to fetch repo');
    });

    it('returns no repo URL error if missing', () => {
      const state = createInitialRepoAccessState();
      
      expect(getBlockingError(state)).toBe('No repository URL configured');
    });

    it('returns null when ready', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      expect(getBlockingError(state)).toBeNull();
    });
  });

  describe('computeBotStatus', () => {
    it('returns RED when blocking error exists', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        lastRepoLoadError: 'Failed to load',
      };
      
      const status = computeBotStatus(state, 'fix bug', null, false, false, false, false, false);
      
      expect(status.color).toBe('red');
      expect(status.message).toBe('Failed to load');
      expect(status.isActiveWork).toBe(false);
    });

    it('returns YELLOW when repo not ready', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: [],
        repoSnapshotStatus: { ready: false, fileCount: 0, reason: 'Loading...' },
      };
      
      const status = computeBotStatus(state, 'fix bug', null, false, false, false, false, false);
      
      expect(status.color).toBe('yellow');
      expect(status.message).toBe('Repository needs to be loaded');
    });

    it('returns YELLOW when mission missing', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const status = computeBotStatus(state, '', null, false, false, false, false, false);
      
      expect(status.color).toBe('yellow');
      expect(status.message).toBe('No mission/auftrag provided');
    });

    it('returns GREEN when active step running', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const status = computeBotStatus(state, 'fix bug', 'package-build', false, false, false, false, false);
      
      expect(status.color).toBe('green');
      expect(status.message).toBe('Working: package-build');
      expect(status.isActiveWork).toBe(true);
    });

    it('returns GREEN when result ready', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const status = computeBotStatus(state, 'fix bug', null, true, false, false, false, false);
      
      expect(status.color).toBe('green');
      expect(status.message).toBe('Result ready for review');
    });

    it('returns NEUTRAL when ready for mission', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const status = computeBotStatus(state, 'fix bug', null, false, false, false, false, false);
      
      expect(status.color).toBe('neutral');
      expect(status.message).toBe('Ready');
    });

    it('shows publishing status when isPublishing is true', () => {
      const state = createInitialRepoAccessState();
      
      const status = computeBotStatus(state, 'fix bug', null, false, false, true, false, false);
      
      expect(status.color).toBe('green');
      expect(status.message).toBe('Publishing...');
    });

    it('shows workflow watch status when isWatchingWorkflow is true', () => {
      const state = createInitialRepoAccessState();
      
      const status = computeBotStatus(state, 'fix bug', null, false, false, false, true, false);
      
      expect(status.color).toBe('green');
      expect(status.message).toBe('Watching workflow...');
    });
  });

  describe('buildAutomationRunKey', () => {
    it('includes all required fields in key', () => {
      const state: RepoAccessState = {
        repoUrl: 'https://github.com/owner/repo',
        repoBranch: 'main',
        githubTokenPresent: true,
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
        lastRepoLoadAt: 1,
        lastRepoLoadError: null,
      };
      
      const key = buildAutomationRunKey(state, 'fix bug', 'v1.0.0', null);
      
      // Key is pipe-separated string containing all required parts
      expect(key).toContain('https://github.com/owner/repo');
      expect(key).toContain('main');
      expect(key).toContain('has-token');
      expect(key).toContain('ready');
      expect(key).toContain('3'); // file count
      expect(key).toContain('fix bug');
      expect(key).toContain('v1.0.0');
    });

    it('produces different keys for different states', () => {
      const state1: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const state2: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/other/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const key1 = buildAutomationRunKey(state1, 'fix bug', null, null);
      const key2 = buildAutomationRunKey(state2, 'fix bug', null, null);
      
      expect(key1).not.toBe(key2);
    });

    it('invalidates when error hash changes', () => {
      const state = createInitialRepoAccessState();
      
      const key1 = buildAutomationRunKey(state, 'fix bug', null, 'abc123');
      const key2 = buildAutomationRunKey(state, 'fix bug', null, 'def456');
      
      expect(key1).not.toBe(key2);
    });

    it('produces same key for same state', () => {
      const state: RepoAccessState = {
        ...createInitialRepoAccessState(),
        repoUrl: 'https://github.com/owner/repo',
        repoFiles: mockRepoFiles,
        repoSnapshotStatus: { ready: true, fileCount: 3, reason: 'ok' },
      };
      
      const key1 = buildAutomationRunKey(state, 'fix bug', 'v1', null);
      const key2 = buildAutomationRunKey(state, 'fix bug', 'v1', null);
      
      expect(key1).toBe(key2);
    });
  });
});

