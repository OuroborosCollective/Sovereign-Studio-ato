import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  adminApiClient,
  clearAdminKey,
  getAdminKey,
  setAdminKey,
} from './adminApiClient';

afterEach(() => {
  clearAdminKey();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('adminApiClient protected owner-input endpoint', () => {
  it('binds one protected value to the exact request and clears the encoded buffer after use', async () => {
    let requestBodyReference: Uint8Array | undefined;
    let observedBodyCopy: Uint8Array | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(
        'https://sovereign-backend.arelorian.de/api/admin/owner-input/requests/request-1/resolve?decision=yes',
      );
      expect(init).toMatchObject({
        method: 'POST',
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
      });
      expect(init?.headers).toEqual(expect.objectContaining({
        Accept: 'application/json',
        'Content-Type': 'application/octet-stream',
      }));
      expect(init?.body).toBeInstanceOf(Uint8Array);
      requestBodyReference = init?.body as Uint8Array;
      observedBodyCopy = new Uint8Array(requestBodyReference);
      return new Response(JSON.stringify({
        ok: true,
        status: 'consumed',
        targetId: 'freellm-provider-key',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    setAdminKey('test-admin-authority');

    const result = await adminApiClient.resolveFreeRevolverOwnerInput(
      'request-1',
      'bounded-owner-input',
    );

    expect(result).toEqual({
      ok: true,
      status: 'consumed',
      targetId: 'freellm-provider-key',
    });
    expect(new TextDecoder().decode(observedBodyCopy)).toBe('bounded-owner-input');
    expect(Array.from(requestBodyReference ?? [])).toEqual(
      Array.from({ length: 'bounded-owner-input'.length }, () => 0),
    );
  });

  it('fails closed and clears the in-memory admin authority on an unauthorized readback', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: 'owner input request is no longer authorized',
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })));
    setAdminKey('test-admin-authority');

    await expect(adminApiClient.resolveFreeRevolverOwnerInput(
      'request-expired',
      'bounded-owner-input',
    )).rejects.toThrow('no longer authorized');

    expect(getAdminKey()).toBe('');
  });
});
