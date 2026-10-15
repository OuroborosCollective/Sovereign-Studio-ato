import { createServer, type Server, type ServerResponse } from 'node:http';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminApiClient, clearAdminKey, getAdminKey, setAdminKey } from './adminApiClient';
import { useAdminUsers } from '../hooks/useAdminApi';

// Exercise the real client and hooks against actual HTTP response streams.
// Only the external destination and elapsed deadline are adapted for the test.
const transportFetch = globalThis.fetch.bind(globalThis);
const windowSetTimeout = window.setTimeout.bind(window);
let server: Server;
let origin: string;
let status = 200;
let body = '';
let stall = false;
let responseHeadersReceived: Promise<void>;
let reportHeaders: () => void;
let requestSignal: AbortSignal | undefined;
const responses = new Set<ServerResponse>();

beforeAll(async () => {
  server = createServer((request, response) => {
    expect(request.url).toMatch(/^\/api\/admin\//);
    response.writeHead(status, { 'Content-Type': 'application/json' });
    if (stall) {
      responses.add(response);
      response.on('close', () => responses.delete(response));
      response.write('{');
    } else {
      response.end(body);
    }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Loopback server unavailable');
  origin = `http://127.0.0.1:${address.port}`;
});

beforeEach(() => {
  status = 200;
  body = JSON.stringify({ users: [], total: 0 });
  stall = false;
  requestSignal = undefined;
  responseHeadersReceived = new Promise(resolve => { reportHeaders = resolve; });
  setAdminKey('test-admin-authority');
  vi.spyOn(window, 'setTimeout').mockImplementation((handler, timeout, ...args) => (
    windowSetTimeout(handler, timeout === 15_000 ? 300 : timeout, ...args)
  ));
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    requestSignal = init?.signal ?? undefined;
    const response = await transportFetch(`${origin}${new URL(String(input), origin).pathname}`, init);
    reportHeaders();
    return response;
  });
});

afterEach(() => {
  for (const response of responses) response.destroy();
  responses.clear();
  clearAdminKey();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

afterAll(async () => {
  server.closeAllConnections();
  await new Promise<void>(resolve => server.close(() => resolve()));
});

async function boundedResult(promise: Promise<unknown>) {
  return Promise.race([
    promise.then(value => ({ value, error: undefined }), error => ({ value: undefined, error })),
    new Promise<never>((_, reject) => windowSetTimeout(
      () => reject(new Error('Admin request stayed pending after its deadline')), 1_500,
    )),
  ]);
}

describe('admin request body loading deadline', () => {
  it('reads complete data and clears the deadline after the body', async () => {
    body = JSON.stringify({ users: [{ id: 'user-1' }], total: 1 });
    await expect(adminApiClient.getUsers()).resolves.toMatchObject({ total: 1 });
    await new Promise(resolve => windowSetTimeout(resolve, 350));
    expect(requestSignal?.aborted).toBe(false);
    expect(getAdminKey()).toBe('test-admin-authority');
  });

  it('times out a success body that stalls after response headers', async () => {
    stall = true;
    const pending = boundedResult(adminApiClient.getUsers());
    await responseHeadersReceived;
    expect(requestSignal?.aborted).toBe(false);
    const result = await pending;
    expect(result.error).toBeInstanceOf(Error);
    expect(result.error.message).toContain('Backend-Zeitüberschreitung nach 15 Sekunden');
    expect(requestSignal?.aborted).toBe(true);
    expect(getAdminKey()).toBe('test-admin-authority');
  });

  it('ends the actual users hook loading state when the body stalls', async () => {
    stall = true;
    const { result, unmount } = renderHook(() => useAdminUsers());
    try {
      await act(async () => { await responseHeadersReceived; });
      expect(result.current.loading).toBe(true);
      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 1_500 });
      expect(result.current.error).toContain('Backend-Zeitüberschreitung');
      expect(result.current.users).toEqual([]);
    } finally {
      unmount();
    }
  });

  it('keeps the deadline while reading a stalled HTTP error body', async () => {
    status = 503;
    stall = true;
    const result = await boundedResult(adminApiClient.getUsers());
    expect(result.error.message).toContain('Backend-Zeitüberschreitung');
    expect(requestSignal?.aborted).toBe(true);
  });

  it('revokes unauthorized authority even if the error body stalls', async () => {
    status = 401;
    stall = true;
    const result = await boundedResult(adminApiClient.getUsers());
    expect(result.error.message).toContain('Backend-Zeitüberschreitung');
    expect(getAdminKey()).toBe('');
  });

  it('preserves complete bounded backend error details', async () => {
    status = 503;
    body = JSON.stringify({ blocker: 'database_unavailable', error: { message: 'Database unavailable' } });
    await expect(adminApiClient.getUsers()).rejects.toThrow(
      'database_unavailable · HTTP 503 · Database unavailable',
    );
  });

  it('rejects malformed success data and ends loading instead of fabricating data', async () => {
    body = 'not-json';
    const { result, unmount } = renderHook(() => useAdminUsers());
    try {
      await waitFor(() => expect(result.current.error).not.toBeNull());
      expect(result.current.loading).toBe(false);
      expect(result.current.users).toEqual([]);
    } finally {
      unmount();
    }
  });
});
