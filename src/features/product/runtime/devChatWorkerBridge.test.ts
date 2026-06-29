import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  DEV_CHAT_WORKER_MODELS,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_HEALTH,
  SOVEREIGN_WORKER_KV,
  devChatGithubUrlToRepoRequest,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  normalizeDevChatWorkerModel,
  parseDevChatGithubUrl,
  summarizeDevChatRepoSnapshot,
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
  it('keeps the approved Cloudflare worker routes', () => {
    expect(SOVEREIGN_WORKER_CHAT).toContain('sovereign-llm-proxy.projectouroboroscollective.workers.dev/v1/chat/completions');
    expect(SOVEREIGN_WORKER_KV).toContain('sovereign-llm-proxy.projectouroboroscollective.workers.dev/kv');
    expect(SOVEREIGN_WORKER_HEALTH).toContain('sovereign-llm-proxy.projectouroboroscollective.workers.dev/health');
    expect(DEV_CHAT_WORKER_MODELS).toEqual([
      expect.objectContaining({ id: DEV_CHAT_WORKER_DEFAULT_MODEL, thinking: true }),
    ]);
    expect(normalizeDevChatWorkerModel('llama-3-8b')).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
  });

  it('parses GitHub URLs typed into the chat', () => {
    const parsed = parseDevChatGithubUrl('Bitte lade https://github.com/OuroborosCollective/Sovereign-Studio-ato/tree/main/src');

    expect(parsed?.owner).toBe('OuroborosCollective');
    expect(parsed?.repo).toBe('Sovereign-Studio-ato');
    expect(parsed?.branch).toBe('main');
    expect(parsed?.path).toBe('src');
    expect(parsed?.repoUrl).toBe('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
  });

  it('converts chat GitHub URLs into repo load requests', () => {
    expect(devChatGithubUrlToRepoRequest('https://github.com/acme/tool/tree/dev')).toEqual({
      repoUrl: 'https://github.com/acme/tool',
      repoBranch: 'dev',
    });
    expect(devChatGithubUrlToRepoRequest('nothing')).toBeNull();
  });

  it('summarizes real repo snapshots without inventing extra data', () => {
    expect(summarizeDevChatRepoSnapshot({
      owner: 'acme',
      repo: 'tool',
      branch: 'main',
      name: 'tool',
      repoUrl: 'https://github.com/acme/tool',
      fileCount: 3,
      files: [],
      dirs: ['src'],
      truncated: false,
    })).toBe('acme/tool geladen · main · 3 files');
  });

  it('calls the Cloudflare worker chat route and validates the response content', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      choices: [{ message: { content: 'Antwort aus Worker.' } }],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDevChatWorkerReply({
      model: 'llama-3-8b',
      messages: [{ role: 'user', content: 'Hallo' }],
    });

    expect(result).toEqual({
      ok: true,
      content: 'Antwort aus Worker.',
      route: SOVEREIGN_WORKER_CHAT,
    });
    expect(fetchMock).toHaveBeenCalledWith(SOVEREIGN_WORKER_CHAT, expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining(DEV_CHAT_WORKER_DEFAULT_MODEL),
    }));
  });

  it('returns a diagnostic blocker for HTTP 500 responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { message: 'Gateway exploded', type: 'server_error' },
    }, 500)));

    const result = await fetchDevChatWorkerReply({
      model: 'llama-3-8b',
      messages: [{ role: 'user', content: 'Hallo' }],
    });

    expect(result.ok).toBe(false);
    expect(result.error).toBe('Gateway exploded');
    expect(result.diagnostic?.status).toBe(500);
    expect(result.diagnostic?.scope).toMatch(/worker_runtime|worker_config/);
    expect(result.diagnostic?.canClientFix).toBe(false);
  });

  it('reads the hosted worker health endpoint without secrets', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      ok: true,
      provider: 'sovereign-llm-bridge',
      gateway: 'gatter',
      model: DEV_CHAT_WORKER_DEFAULT_MODEL,
      upstreamConfigured: true,
      secretConfigured: true,
    })));

    const result = await fetchDevChatWorkerHealth();

    expect(result.ok).toBe(true);
    expect(result.route).toBe(SOVEREIGN_WORKER_HEALTH);
    expect(result.secretConfigured).toBe(true);
    expect(result.model).toBe(DEV_CHAT_WORKER_DEFAULT_MODEL);
  });

  it('returns a real blocker when the worker response has no usable content', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [] })));

    const result = await fetchDevChatWorkerReply({
      model: 'llama-3-8b',
      messages: [{ role: 'user', content: 'Hallo' }],
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('keine auswertbare Antwort');
    expect(result.route).toBe(SOVEREIGN_WORKER_CHAT);
  });
});
