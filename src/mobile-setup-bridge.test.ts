import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  createMobileRepoSetupDetail,
  createMobileRepoSetupState,
  dispatchMobileRepoSetup,
  MOBILE_REPO_SETUP_EVENT,
  parseMobileRepoSetupDetail,
  readMobileRepoSetupState,
  validateMobileRepoSetupDetail,
  validateMobileRepoSetupState,
  writeMobileRepoSetupState,
} from './mobile-setup-bridge';

describe('mobile repo setup bridge', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('sanitizes setup detail and requires repo url', () => {
    const detail = createMobileRepoSetupDetail({ repoUrl: ' https://github.com/owner/repo ', accessValue: ' value ', autoLoad: true });
    expect(detail.repoUrl).toBe('https://github.com/owner/repo');
    expect(detail.accessValue).toBe('value');
    expect(detail.autoLoad).toBe(true);
    expect(validateMobileRepoSetupDetail(detail).valid).toBe(true);
    expect(parseMobileRepoSetupDetail({ repoUrl: '', accessValue: 'x' })).toBeNull();
  });

  it('dispatches a typed setup event and persists dispatched state', () => {
    const listener = vi.fn();
    window.addEventListener(MOBILE_REPO_SETUP_EVENT, listener);
    const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'value' });
    expect(dispatchMobileRepoSetup(detail)).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(readMobileRepoSetupState()?.stage).toBe('dispatched');
    window.removeEventListener(MOBILE_REPO_SETUP_EVENT, listener);
  });

  it('validates and stores handoff state across stages', () => {
    const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'value', requestId: 'req-1' });
    const state = createMobileRepoSetupState(detail, 'loading', 'load started');
    expect(validateMobileRepoSetupState(state).valid).toBe(true);
    expect(writeMobileRepoSetupState(state)).toBe(true);
    expect(readMobileRepoSetupState()).toMatchObject({ requestId: 'req-1', stage: 'loading', repoUrl: 'https://github.com/owner/repo' });
  });

  describe('no premature repo load', () => {
    it('autoLoad defaults to true unless explicitly set to false', () => {
      const detailWithDefault = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'ghp_xxx' });
      expect(detailWithDefault.autoLoad).toBe(true);
      
      const detailWithFalse = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'ghp_xxx', autoLoad: false });
      expect(detailWithFalse.autoLoad).toBe(false);
    });

    it('validates complete detail with all required fields', () => {
      const detail = createMobileRepoSetupDetail({ 
        repoUrl: 'https://github.com/owner/repo', 
        accessValue: 'token',
        requestId: 'test-req'
      });
      const report = validateMobileRepoSetupDetail(detail);
      expect(report.valid).toBe(true);
    });

    it('warns about non-GitHub URL format', () => {
      const detail = createMobileRepoSetupDetail({ 
        repoUrl: 'https://gitlab.com/owner/repo', 
        accessValue: 'token' 
      });
      const report = validateMobileRepoSetupDetail(detail);
      expect(report.warnings.some(w => w.includes('does not look like'))).toBe(true);
    });

    it('persists setup state only after explicit dispatch', () => {
      expect(readMobileRepoSetupState()).toBeNull();
      
      const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'token' });
      dispatchMobileRepoSetup(detail);
      
      expect(readMobileRepoSetupState()?.stage).toBe('dispatched');
    });
  });

  describe('setup state stages', () => {
    it('tracks dispatched stage', () => {
      const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'token' });
      const state = createMobileRepoSetupState(detail, 'dispatched', 'Setup dispatched');
      expect(state.stage).toBe('dispatched');
    });

    it('tracks loading stage', () => {
      const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'token' });
      const state = createMobileRepoSetupState(detail, 'loading', 'Loading repository');
      expect(state.stage).toBe('loading');
    });

    it('tracks ready stage', () => {
      const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'token' });
      const state = createMobileRepoSetupState(detail, 'loaded', 'Repository loaded');
      expect(state.stage).toBe('loaded');
    });

    it('tracks failed stage', () => {
      const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'token' });
      const state = createMobileRepoSetupState(detail, 'failed', 'Failed to load');
      expect(state.stage).toBe('failed');
    });
  });
});
