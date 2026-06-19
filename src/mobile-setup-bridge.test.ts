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
});
