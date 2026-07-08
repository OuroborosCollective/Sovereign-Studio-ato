import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  DEV_CHAT_WORKER_FALLBACK_MODEL,
  DEV_CHAT_WORKER_MODELS,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_HEALTH,
  SOVEREIGN_WORKER_KV,
  devChatGithubUrlToRepoRequest,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  normalizeDevChatWorkerModel,
  parseDevChatGithubUrl,
  streamDevChatWorkerReply,
  summarizeDevChatRepoSnapshot,
  isWorkerTimeoutError,
  createWorkerTimeoutDiagnostic,
  WORKER_REPLY_TIMEOUT_MS,
} from './devChatWorkerBridge';

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('devChatWorkerBridge', () => {
  it('keeps the approved worker routes and model aliases', () => {
    expect(SOVEREIGN_WORKER_CHAT).toContain('/v1/chat/completions');
    expect(SOVEREIGN_WORKER_KV).toContain('/kv');
    expect(SOVEREIGN_WORKER_HEALTH).toContain('/health');
    // Models updated 2026-07-02: cerebras routes removed (no Worker route),
    // llama-3-8b deprecated. Active: deepseek-r1, mistral-7b, llama-3.1-8b.
    expect(DEV_CHAT_WORKER_DEFAULT_MODEL).toBe('deepseek-r1');
    expect(DEV_CHAT_WORKER_FALLBACK_MODEL).toBe('llama-3.1-8b');
    expect(DEV_CHAT_WORKER_MODELS).toHaveLength(3);
    // Legacy aliases (dead models) normalise to the new default
    expect(normalizeDevChatWorkerModel('llama-3-8b')).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
    expect(normalizeDevChatWorkerModel('cerebras/gpt-oss-120b')).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
    expect(normalizeDevChatWorkerModel('cerebras/zai-glm-4.7')).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
  });

  it('parses GitHub URLs typed into the chat', () => {
    const repoUrl = ['https://github.com', 'OuroborosCollective', 'Sovereign-Studio-ato', 'tree', 'main', 'src'].join('/');
    const parsed = parseDevChatGithubUrl(`Bitte lade ${repoUrl}`);

    expect(parsed?.owner).toBe('OuroborosCollective');
    expect(parsed?.repo).toBe('Sovereign-Studio-ato');
    expect(parsed?.branch).toBe('main');
    expect(parsed?.path).toBe('src');
  });

  it('converts chat GitHub URLs into repo load requests', () => {
    const repoUrl = ['https://github.com', 'acme', 'tool', 'tree', 'dev'].join('/');
    expect(devChatGithubUrlToRepoRequest(repoUrl)).toEqual({ repoUrl: 'https://github.com/acme/tool', repoBranch: 'dev' });
    expect(devChatGithubUrlToRepoRequest('nothing')).toBeNull();
  });

  it('summarizes real repo snapshots without inventing extra data', () => {
    expect(summarizeDevChatRepoSnapshot({
      owner: 'acme', repo: 'tool', branch: 'main', name: 'tool', repoUrl: 'repo', fileCount: 3, files: [], dirs: ['src'], truncated: false,
    })).toBe('acme/tool geladen · main · 3 files');
  });

  it('calls the worker chat route and validates response content', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'Antwort aus Worker.' } }] }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDevChatWorkerReply({ model: 'llama-3-8b', messages: [{ role: 'user', content: 'Hallo' }] });

    expect(result).toMatchObject({ ok: true, content: 'Antwort aus Worker.', route: SOVEREIGN_WORKER_CHAT });
    expect(fetchMock).toHaveBeenCalledWith(SOVEREIGN_WORKER_CHAT, expect.objectContaining({ method: 'POST' }));
  });

  it('returns a diagnostic blocker for HTTP 500 responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: { message: 'Gateway exploded', type: 'server_error' } }, 500)));

    const result = await fetchDevChatWorkerReply({ model: 'llama-3-8b', messages: [{ role: 'user', content: 'Hallo' }] });

    expect(result.ok).toBe(false);
    expect(result.error).toBe('Gateway exploded');
    expect(result.diagnostic?.status).toBe(500);
    expect(result.diagnostic?.scope).toMatch(/worker_runtime|worker_config/);
    expect(result.diagnostic?.canClientFix).toBe(false);
  });

  it('reads the hosted worker health endpoint without secrets', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ok: true, provider: 'bridge', gateway: 'gatter', model: DEV_CHAT_WORKER_DEFAULT_MODEL, upstreamConfigured: true, secretConfigured: true })));

    const result = await fetchDevChatWorkerHealth();

    expect(result.ok).toBe(true);
    expect(result.route).toBe(SOVEREIGN_WORKER_HEALTH);
    expect(result.secretConfigured).toBe(true);
    expect(result.model).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
  });

  it('returns a real blocker when the worker response has no usable content', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [] })));

    const result = await fetchDevChatWorkerReply({ model: 'llama-3-8b', messages: [{ role: 'user', content: 'Hallo' }] });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('keine auswertbare Antwort');
    expect(result.route).toBe(SOVEREIGN_WORKER_CHAT);
  });
});

describe('devChatWorkerBridge timeout gates', () => {
  it('isWorkerTimeoutError detects AbortError DOMException', () => {
    const domEx = new DOMException('The user aborted a request.', 'AbortError');
    expect(isWorkerTimeoutError(domEx)).toBe(true);
  });

  it('isWorkerTimeoutError detects Error with aborted/timeout in message', () => {
    expect(isWorkerTimeoutError(new Error('signal aborted'))).toBe(true);
    expect(isWorkerTimeoutError(new Error('Request timed out'))).toBe(true);
    expect(isWorkerTimeoutError(new Error('signal is aborted without reason'))).toBe(true);
    expect(isWorkerTimeoutError(new Error('Gateway error'))).toBe(false);
    expect(isWorkerTimeoutError(null)).toBe(false);
  });

  it('createWorkerTimeoutDiagnostic has scope=worker_runtime and canClientFix=false', () => {
    const diagnostic = createWorkerTimeoutDiagnostic({ model: 'deepseek-r1', messageCount: 3 });
    expect(diagnostic.scope).toBe('worker_runtime');
    expect(diagnostic.canClientFix).toBe(false);
    expect(diagnostic.route).toBe(SOVEREIGN_WORKER_CHAT);
    expect(diagnostic.model).toBe('deepseek-r1');
    expect(diagnostic.messageCount).toBe(3);
    expect(diagnostic.nextAction).toContain('nicht blind erneut senden');
  });

  it('WORKER_REPLY_TIMEOUT_MS is 30 seconds — not an open-ended wait', () => {
    expect(WORKER_REPLY_TIMEOUT_MS).toBe(30_000);
  });

  it('fetchDevChatWorkerReply returns timeout diagnostic when fetch aborts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('The user aborted a request.', 'AbortError');
    }));

    const result = await fetchDevChatWorkerReply({
      model: DEV_CHAT_WORKER_DEFAULT_MODEL,
      messages: [{ role: 'user', content: 'Hallo' }],
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('Timeout');
    expect(result.diagnostic?.scope).toBe('worker_runtime');
    expect(result.diagnostic?.canClientFix).toBe(false);
    expect(result.diagnostic?.nextAction).toContain('nicht blind erneut senden');
  });

  it('fetchDevChatWorkerHealth returns timeout result when health fetch aborts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('The user aborted a request.', 'AbortError');
    }));

    const result = await fetchDevChatWorkerHealth();

    expect(result.ok).toBe(false);
    expect(result.route).toBe(SOVEREIGN_WORKER_HEALTH);
    expect(result.error).toContain('Timeout');
  });

  it('streamDevChatWorkerReply throws timeout diagnostic when stream fetch aborts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('The user aborted a request.', 'AbortError');
    }));

    let thrown: unknown;
    try {
      for await (const _chunk of streamDevChatWorkerReply({
        model: DEV_CHAT_WORKER_DEFAULT_MODEL,
        messages: [{ role: 'user', content: 'Test' }],
      })) { /* no chunks expected */ }
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toContain('Timeout');
    const diag = (thrown as { diagnostic?: { scope?: string; canClientFix?: boolean; nextAction?: string } }).diagnostic;
    expect(diag?.scope).toBe('worker_runtime');
    expect(diag?.canClientFix).toBe(false);
    expect(diag?.nextAction).toContain('nicht blind erneut senden');
  });
});

describe('streamDevChatWorkerReply', () => {
  function sseResponse(chunks: string[]): Response {
    const body = [...chunks.map(chunk => `data: ${JSON.stringify({ choices: [{ delta: { content: chunk } }] })}`), 'data: [DONE]'].join('\n');
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  }

  it('yields SSE delta chunks as they arrive', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(['Hallo', ' Welt'])));
    const chunks: string[] = [];
    for await (const chunk of streamDevChatWorkerReply({ model: DEV_CHAT_WORKER_DEFAULT_MODEL, messages: [{ role: 'user', content: 'Sag Hallo' }] })) chunks.push(chunk);
    expect(chunks).toEqual(['Hallo', ' Welt']);
  });

  it('terminates cleanly on DONE', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(['Teil 1', 'Teil 2'])));
    const chunks: string[] = [];
    for await (const chunk of streamDevChatWorkerReply({ model: DEV_CHAT_WORKER_DEFAULT_MODEL, messages: [{ role: 'user', content: 'Test' }] })) chunks.push(chunk);
    expect(chunks).toEqual(['Teil 1', 'Teil 2']);
  });

  it('skips invalid JSON lines without crashing', async () => {
    const body = ['data: {"choices":[{"delta":{"content":"Valid"}}]}', 'data: { broken json', 'data: {"choices":[{"delta":{"content":"Auch valid"}}]}', 'data: [DONE]'].join('\n');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })));
    const chunks: string[] = [];
    for await (const chunk of streamDevChatWorkerReply({ model: DEV_CHAT_WORKER_DEFAULT_MODEL, messages: [{ role: 'user', content: 'Test' }] })) chunks.push(chunk);
    expect(chunks).toEqual(['Valid', 'Auch valid']);
  });

  it('reads JSON worker replies when streaming is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'Fallback Antwort' } }] })));
    const chunks: string[] = [];
    for await (const chunk of streamDevChatWorkerReply({ model: DEV_CHAT_WORKER_DEFAULT_MODEL, messages: [{ role: 'user', content: 'Test' }] })) chunks.push(chunk);
    expect(chunks).toEqual(['Fallback Antwort']);
  });

  it('throws a bounded diagnostic on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: 'boom' }, 500)));
    let thrown: unknown;
    try {
      for await (const _chunk of streamDevChatWorkerReply({ model: DEV_CHAT_WORKER_DEFAULT_MODEL, messages: [{ role: 'user', content: 'Test' }] })) {
        // no chunks expected before diagnostic blocker
      }
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as { status?: number }).status).toBe(500);
    expect((thrown as { diagnostic?: { status?: number; scope?: string; canClientFix?: boolean } }).diagnostic).toMatchObject({ status: 500, scope: 'worker_runtime', canClientFix: false });
  });
});
