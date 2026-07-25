// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

const nativeRuntime = vi.hoisted(() => ({
  native: false,
  handler: null as null | ((event: { url: string }) => void),
  remove: vi.fn(async () => undefined),
  open: vi.fn(async () => undefined),
  close: vi.fn(async () => undefined),
}));

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => nativeRuntime.native },
}));
vi.mock('@capacitor/app', () => ({
  App: {
    addListener: vi.fn(async (_event: string, handler: (event: { url: string }) => void) => {
      nativeRuntime.handler = handler;
      return { remove: nativeRuntime.remove };
    }),
  },
}));
vi.mock('@capacitor/browser', () => ({
  Browser: { open: nativeRuntime.open, close: nativeRuntime.close },
}));

import { initiateGitHubOAuth } from './githubOAuthLogin';

interface PopupDouble {
  closed: boolean;
  close: ReturnType<typeof vi.fn>;
}

function initPayload() {
  return {
    authUrl: 'https://github.com/login/oauth/authorize?state=state_test',
    state: 'state_test',
    codeVerifier: 'verifier_test',
    callbackOrigin: 'https://chat.arelorian.de',
    openerOrigin: window.location.origin,
  };
}

function dispatchOAuthMessage(
  popup: PopupDouble,
  origin: string,
  data: Record<string, unknown>,
) {
  window.dispatchEvent(new MessageEvent('message', {
    origin,
    source: popup as unknown as Window,
    data,
  }));
}

afterEach(() => {
  nativeRuntime.native = false;
  nativeRuntime.handler = null;
  nativeRuntime.remove.mockClear();
  nativeRuntime.open.mockClear();
  nativeRuntime.close.mockClear();
  vi.restoreAllMocks();
});

describe('GitHub OAuth verified return channel', () => {
  it('sends the opener origin and accepts only the backend-confirmed callback origin', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify(initPayload()),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const popup: PopupDouble = { closed: false, close: vi.fn(() => { popup.closed = true; }) };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);

    const pending = initiateGitHubOAuth(undefined, 2_000);
    await vi.waitFor(() => expect(window.open).toHaveBeenCalledTimes(1));

    const request = fetchMock.mock.calls[0];
    const body = JSON.parse(String(request[1]?.body || '{}')) as Record<string, unknown>;
    expect(body.opener_origin).toBe(window.location.origin);
    expect(body.redirect_uri).toBeUndefined();

    dispatchOAuthMessage(popup, 'https://evil.example', {
      type: 'GITHUB_OAUTH_SUCCESS',
      code: 'evil_code',
      state: 'state_test',
    });
    dispatchOAuthMessage(popup, 'https://chat.arelorian.de', {
      type: 'GITHUB_OAUTH_SUCCESS',
      code: 'verified_code',
      state: 'state_test',
    });

    await expect(pending).resolves.toEqual({
      success: true,
      code: 'verified_code',
      state: 'state_test',
      codeVerifier: 'verifier_test',
    });
    expect(popup.close).toHaveBeenCalledTimes(1);
  });

  it('returns from the Android browser through the app-specific deep link', async () => {
    nativeRuntime.native = true;
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify(initPayload()),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const popupSpy = vi.spyOn(window, 'open');

    const pending = initiateGitHubOAuth(undefined, 2_000);
    await vi.waitFor(() => expect(nativeRuntime.open).toHaveBeenCalledWith({
      url: initPayload().authUrl,
    }));
    nativeRuntime.handler?.({
      url: 'com.arestudio.nocode.aab://auth/github/callback?code=native_code&state=state_test',
    });

    await expect(pending).resolves.toEqual({
      success: true,
      code: 'native_code',
      state: 'state_test',
      codeVerifier: 'verifier_test',
    });
    expect(popupSpy).not.toHaveBeenCalled();
    expect(nativeRuntime.remove).toHaveBeenCalledTimes(1);
    expect(nativeRuntime.close).toHaveBeenCalledTimes(1);
  });

  it('rejects a callback with the wrong one-time state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify(initPayload()),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const popup: PopupDouble = { closed: false, close: vi.fn(() => { popup.closed = true; }) };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);

    const pending = initiateGitHubOAuth(undefined, 2_000);
    await vi.waitFor(() => expect(window.open).toHaveBeenCalledTimes(1));
    dispatchOAuthMessage(popup, 'https://chat.arelorian.de', {
      type: 'GITHUB_OAUTH_SUCCESS',
      code: 'code_test',
      state: 'tampered_state',
    });

    const result = await pending;
    expect(result.success).toBe(false);
    expect(result.error).toContain('State stimmt nicht');
  });
});
