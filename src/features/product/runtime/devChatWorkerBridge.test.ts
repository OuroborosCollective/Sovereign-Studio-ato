import { describe, expect, it } from 'vitest';
import {
  DEV_CHAT_WORKER_MODELS,
  SOVEREIGN_WORKER_CHAT,
  SOVEREIGN_WORKER_KV,
  devChatGithubUrlToRepoRequest,
  parseDevChatGithubUrl,
  summarizeDevChatRepoSnapshot,
} from './devChatWorkerBridge';

describe('devChatWorkerBridge', () => {
  it('keeps the approved Cloudflare worker routes', () => {
    expect(SOVEREIGN_WORKER_CHAT).toContain('sovereign-llm-proxy.projectouroboroscollective.workers.dev/v1/chat/completions');
    expect(SOVEREIGN_WORKER_KV).toContain('sovereign-llm-proxy.projectouroboroscollective.workers.dev/kv');
    expect(DEV_CHAT_WORKER_MODELS.some((model) => model.id === 'deepseek-r1' && model.thinking)).toBe(true);
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
});
