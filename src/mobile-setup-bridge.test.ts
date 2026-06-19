import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createMobileRepoSetupDetail, dispatchMobileRepoSetup, MOBILE_REPO_SETUP_EVENT, parseMobileRepoSetupDetail } from './mobile-setup-bridge';

describe('mobile repo setup bridge', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sanitizes setup detail and requires repo url', () => {
    const detail = createMobileRepoSetupDetail({ repoUrl: ' https://github.com/owner/repo ', accessValue: ' value ', autoLoad: true });
    expect(detail.repoUrl).toBe('https://github.com/owner/repo');
    expect(detail.accessValue).toBe('value');
    expect(detail.autoLoad).toBe(true);
    expect(parseMobileRepoSetupDetail({ repoUrl: '', accessValue: 'x' })).toBeNull();
  });

  it('dispatches a typed setup event', () => {
    const listener = vi.fn();
    window.addEventListener(MOBILE_REPO_SETUP_EVENT, listener);
    const detail = createMobileRepoSetupDetail({ repoUrl: 'https://github.com/owner/repo', accessValue: 'value' });
    expect(dispatchMobileRepoSetup(detail)).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(MOBILE_REPO_SETUP_EVENT, listener);
  });
});
