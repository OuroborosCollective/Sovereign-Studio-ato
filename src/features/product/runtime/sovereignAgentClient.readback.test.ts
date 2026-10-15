import { createServer, type ServerResponse } from 'node:http';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSovereignAgentClient } from './sovereignAgentClient';

const nativeTimer = globalThis.setTimeout.bind(globalThis);
const nativeFetch = globalThis.fetch.bind(globalThis);
const responses = new Set<ServerResponse>();
let status = 200, stall = false, origin = '';
const server = createServer((request, response) => {
  response.writeHead(status, { 'Content-Type': 'application/json' });
  if (stall) {
    responses.add(response);
    response.on('close', () => responses.delete(response));
    response.write('{');
  } else response.end(JSON.stringify({ job: { jobId: 'agent-socket', status: 'running', events: [], changedFiles: [] } }));
});
beforeAll(async () => {
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Loopback HTTP server unavailable');
  origin = `http://127.0.0.1:${address.port}`;
});
beforeEach(() => {
  status = 200; stall = false;
  // Only elapsed deadline time is shortened. Network/body/abort are real.
  vi.spyOn(globalThis, 'setTimeout').mockImplementation(((fn, ms, ...args) =>
    nativeTimer(fn, ms === 15_000 ? 150 : ms, ...args)) as typeof setTimeout);
});
afterEach(() => {
  responses.forEach(response => response.destroy()); responses.clear(); vi.restoreAllMocks();
});
afterAll(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); });
const client = () => createSovereignAgentClient({ fetcher: nativeFetch, config: {
  enabled: true, deploymentMode: 'sovereign-agent-backend', agentApiUrl: origin, ready: true, reason: 'ready',
} });
async function bounded(pending: Promise<unknown>) {
  let guard: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([pending, new Promise((_, reject) => { guard = nativeTimer(() => reject(new Error('Readback remained pending')), 1000); })]);
  } finally { clearTimeout(guard); }
}

describe('real runtime readback HTTP body deadline', () => {
  it('reads a complete job response', async () => {
    await expect(bounded(client().getJob('agent-socket'))).resolves.toMatchObject({ jobId: 'agent-socket' });
  });
  it.each([200, 503])('bounds a stalled %s body after headers', async code => {
    status = code; stall = true;
    await expect(bounded(client().getJob('agent-socket'))).rejects.toThrow(/readback timed out/i);
  });
  it('also bounds evidence anchor bodies so they cannot freeze the whole monitor poll', async () => {
    stall = true;
    await expect(bounded(client().getEvidenceAnchors('agent-socket'))).rejects.toThrow(/readback timed out/i);
  });
});
