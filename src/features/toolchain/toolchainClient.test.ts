import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SOVEREIGN_TOOLCHAIN_ENDPOINTS,
  ToolchainRequestError,
  toolchainClient,
} from './toolchainClient';

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('toolchainClient Android/backend boundary', () => {
  it('uses the absolute Sovereign backend contract with the authenticated session', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ name: 'embedded', tools: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(toolchainClient.manifest()).resolves.toMatchObject({ tools: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      SOVEREIGN_TOOLCHAIN_ENDPOINTS.manifest,
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({ Accept: 'application/json' }),
      }),
    );
    expect(SOVEREIGN_TOOLCHAIN_ENDPOINTS.manifest).not.toContain('https://localhost');
  });

  it('classifies an HTML fallback as an invalid response instead of a network outage', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      '<!DOCTYPE html><html><body>Not Found</body></html>',
      { status: 404, headers: { 'Content-Type': 'text/html' } },
    )));

    await expect(toolchainClient.manifest()).rejects.toMatchObject({
      name: 'ToolchainRequestError',
      kind: 'invalid_response',
      status: 404,
    });
  });

  it.each([
    [401, 'authentication'],
    [403, 'permission'],
    [404, 'not_found'],
    [503, 'server'],
  ] as const)('classifies HTTP %s as %s', async (status, kind) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: `failure-${status}` }, status)));

    let thrown: unknown;
    try {
      await toolchainClient.manifest();
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(ToolchainRequestError);
    expect(thrown).toMatchObject({ kind, status, message: `failure-${status}` });
  });

  it('classifies a rejected fetch as a real network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    }));

    await expect(toolchainClient.manifest()).rejects.toMatchObject({
      kind: 'network',
      message: 'Failed to fetch',
    });
  });
});
