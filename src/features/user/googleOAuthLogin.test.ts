// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

const runtime = vi.hoisted(() => ({
  native: true,
  initialize: vi.fn(async () => undefined),
  signIn: vi.fn(async () => ({ authentication: { idToken: 'google-id-token' } })),
}));

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => runtime.native },
}));

vi.mock('@codetrix-studio/capacitor-google-auth', () => ({
  GoogleAuth: {
    initialize: runtime.initialize,
    signIn: runtime.signIn,
  },
}));

import { googleOAuthErrorMessage, initiateGoogleOAuth } from './googleOAuthLogin';

function installCrypto(byte = 0x11) {
  vi.stubGlobal('crypto', {
    subtle: {
      digest: vi.fn(async () => new Uint8Array(32).fill(byte).buffer),
    },
  });
}

function mockConfiguredBackend(fingerprint = '11'.repeat(32)) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    configured: true,
    clientIdFingerprint: fingerprint,
    audienceVerificationRequired: true,
    issuerVerificationRequired: true,
    emailVerificationRequired: true,
    rawCredentialReturned: false,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
}

afterEach(() => {
  runtime.native = true;
  runtime.initialize.mockClear();
  runtime.signIn.mockClear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Google OAuth platform-safe initialization', () => {
  it('does not override androidClientId with the Web client ID on native Android', async () => {
    installCrypto();
    mockConfiguredBackend();

    await expect(initiateGoogleOAuth()).resolves.toBe('google-id-token');

    expect(runtime.initialize).toHaveBeenCalledWith({
      scopes: ['profile', 'email'],
      grantOfflineAccess: false,
    });
    expect(runtime.initialize.mock.calls[0]?.[0]).not.toHaveProperty('clientId');
    expect(runtime.signIn).toHaveBeenCalledTimes(1);
  });

  it('uses the Web/Server audience when running in a browser', async () => {
    runtime.native = false;
    installCrypto();
    mockConfiguredBackend();

    await initiateGoogleOAuth();

    expect(runtime.initialize).toHaveBeenCalledWith(expect.objectContaining({
      clientId: '511695074775-s08le2ju1k4nl2vv3i150i6tn084b682.apps.googleusercontent.com',
      grantOfflineAccess: false,
    }));
  });

  it('fails closed before opening Google when backend and build audiences differ', async () => {
    installCrypto();
    mockConfiguredBackend('22'.repeat(32));

    await expect(initiateGoogleOAuth()).rejects.toThrow('nicht dieselbe sichere Audience');
    expect(runtime.initialize).not.toHaveBeenCalled();
    expect(runtime.signIn).not.toHaveBeenCalled();
  });

  it('maps Android developer error 10 to an actionable bounded message', () => {
    expect(googleOAuthErrorMessage({ code: 10, message: 'Something went wrong' })).toContain('Android-Builds');
  });
});
