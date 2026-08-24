// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../security/securityApi', () => ({
  loginWithAccountKey: vi.fn(),
  loginWithPasskey: vi.fn(),
}));

import { useUserStore } from './useUserStore';

const verifiedUser = {
  id: 'user-session',
  email: 'verified@example.test',
  displayName: 'Verified Session',
  role: 'user',
  credits: 500,
  subscriptionStatus: 'free',
  isBanned: false,
  createdAt: 1,
};

afterEach(() => {
  useUserStore.setState({ user: null, isLoading: false, error: null });
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('OAuth session effect readback', () => {
  it('accepts Google exchange only after /api/auth/me confirms the cookie session', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'untrusted-post-body', email: 'post@example.test' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(verifiedUser), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    await useUserStore.getState().loginWithGoogle('id-token');

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/auth/google');
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/auth/me');
    expect(useUserStore.getState().user?.id).toBe('user-session');
  });

  it('rejects Google POST success when the session cookie cannot be read back', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await useUserStore.getState().loginWithGoogle('id-token');

    expect(useUserStore.getState().user).toBeNull();
    expect(useUserStore.getState().error).toContain('Session nicht bestätigt');
  });

  it('sends GitHub code/state/verifier then requires /api/auth/me', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...verifiedUser, githubId: '123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    await useUserStore.getState().loginWithGitHub({
      code: 'code',
      state: 'state',
      codeVerifier: 'verifier',
    });

    const request = fetchMock.mock.calls[0];
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      code: 'code',
      state: 'state',
      code_verifier: 'verifier',
    });
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/auth/me');
    expect(useUserStore.getState().user?.githubId).toBe('123');
  });

  it('rejects GitHub POST success when the backend session is absent', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await useUserStore.getState().loginWithGitHub({ code: 'code', state: 'state', codeVerifier: 'verifier' });

    expect(useUserStore.getState().user).toBeNull();
    expect(useUserStore.getState().error).toContain('Session nicht bestätigt');
  });
});
