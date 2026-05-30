import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { ProviderType } from './providerManager';

// --- Mocks -----------------------------------------------------------------

// Gemini SDK calls are mocked so we can deterministically force success/failure.
const generateTextMock = vi.fn();
vi.mock('./geminiService', () => ({
  geminiService: {
    generateText: (...args: unknown[]) => generateTextMock(...args),
  },
}));

// Free-provider fallback calls are mocked so each handoff step is reproducible.
const callPuterMock = vi.fn();
const callGroqMock = vi.fn();
const callHuggingFaceMock = vi.fn();
const callTogetherMock = vi.fn();
const callOpenRouterMock = vi.fn();
vi.mock('./providerManager', () => ({
  callPuter: (...args: unknown[]) => callPuterMock(...args),
  callGroq: (...args: unknown[]) => callGroqMock(...args),
  callHuggingFace: (...args: unknown[]) => callHuggingFaceMock(...args),
  callTogether: (...args: unknown[]) => callTogetherMock(...args),
  callOpenRouter: (...args: unknown[]) => callOpenRouterMock(...args),
}));

import { runAwarenessSync, type RepoFile } from './awarenessSync';

// A well-formed model response so section parsing succeeds.
const RAW_RESPONSE = [
  'ZUSAMMENFASSUNG:',
  'Ein Test-Projekt.',
  '',
  'TECHNOLOGIEN:',
  'TypeScript, React, Vite',
  '',
  'STRUKTUR:',
  'Standard src-Ordner.',
  '',
  'VERBESSERUNGSVORSCHLÄGE:',
  '- Mehr Tests',
  '- Bessere Docs',
].join('\n');

const REPO_FILES: RepoFile[] = [
  { path: 'src/index.ts', type: 'blob', size: 100 },
  { path: 'package.json', type: 'blob', size: 50 },
  { path: 'src', type: 'tree' },
];

const REPO_URL = 'https://github.com/acme/widget';

// All five keys present so the entire chain is reachable.
const ALL_KEYS = {
  groqKey: 'gsk_key',
  hfKey: 'hf_key',
  togetherKey: 'together_key',
  openrouterKey: 'sk-or-key',
};

// A retryable Gemini error message that triggers fallback (contains "429").
const RETRYABLE = new Error('429 quota exceeded');

function providerResponse(text = RAW_RESPONSE) {
  return { text, provider: 'puter' as ProviderType, model: 'm' };
}

describe('runAwarenessSync — provider fallback chain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses Gemini and never touches fallback providers when Gemini succeeds', async () => {
    generateTextMock.mockResolvedValue(RAW_RESPONSE);
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-2.0-flash',
      onSwitch
    );

    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(callPuterMock).not.toHaveBeenCalled();
    expect(callGroqMock).not.toHaveBeenCalled();
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).not.toHaveBeenCalled();
    expect(callOpenRouterMock).not.toHaveBeenCalled();
    expect(onSwitch).not.toHaveBeenCalled();

    expect(result.summary).toBe('Ein Test-Projekt.');
    expect(result.technologies).toEqual(['TypeScript', 'React', 'Vite']);
    expect(result.structure).toBe('Standard src-Ordner.');
    expect(result.suggestions).toEqual(['Mehr Tests', 'Bessere Docs']);
    expect(result.rawText).toBe(RAW_RESPONSE);
  });

  it('Gemini 429 → Puter succeeds, and reports the gemini→puter switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callPuterMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-2.0-flash',
      onSwitch
    );

    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(callPuterMock).toHaveBeenCalledTimes(1);
    // Other providers should NOT be called
    expect(callGroqMock).not.toHaveBeenCalled();
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).not.toHaveBeenCalled();
    expect(callOpenRouterMock).not.toHaveBeenCalled();

    // onSwitch called for the fallback
    expect(onSwitch).toHaveBeenCalledTimes(1);
    expect(onSwitch).toHaveBeenCalledWith('gemini', 'puter', expect.stringContaining('429'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('Puter fails → Groq succeeds, and reports the puter→groq switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callPuterMock.mockRejectedValue(new Error('puter down'));
    callGroqMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-2.0-flash',
      onSwitch
    );

    expect(callPuterMock).toHaveBeenCalledTimes(1);
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).not.toHaveBeenCalled();
    expect(callOpenRouterMock).not.toHaveBeenCalled();

    // First fallback is gemini->puter, then puter->groq when puter fails
    expect(onSwitch).toHaveBeenCalledWith('gemini', 'puter', expect.any(String));
    expect(onSwitch).toHaveBeenCalledWith('puter', 'groq', expect.stringContaining('puter down'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('Groq fails → OpenRouter succeeds, and reports the groq→openrouter switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callPuterMock.mockRejectedValue(new Error('puter down'));
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callOpenRouterMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-2.0-flash',
      onSwitch
    );

    expect(callPuterMock).toHaveBeenCalledTimes(1);
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).not.toHaveBeenCalled();

    // Verify groq->openrouter fallback
    expect(onSwitch).toHaveBeenCalledWith('groq', 'openrouter', expect.stringContaining('groq down'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('walks every provider in order when each one before the last fails', async () => {
    const callOrder: string[] = [];
    generateTextMock.mockImplementation(async () => {
      callOrder.push('gemini');
      throw RETRYABLE;
    });
    callPuterMock.mockImplementation(async () => {
      callOrder.push('puter');
      throw new Error('puter down');
    });
    callGroqMock.mockImplementation(async () => {
      callOrder.push('groq');
      throw new Error('groq down');
    });
    callOpenRouterMock.mockImplementation(async () => {
      callOrder.push('openrouter');
      throw new Error('openrouter down');
    });
    callHuggingFaceMock.mockImplementation(async () => {
      callOrder.push('huggingface');
      throw new Error('hf down');
    });
    callTogetherMock.mockImplementation(async () => {
      callOrder.push('together');
      return providerResponse();
    });

    await runAwarenessSync('AIza-key', REPO_FILES, REPO_URL, ALL_KEYS);

    // Provider order: puter -> groq -> openrouter -> huggingface -> together
    expect(callOrder).toEqual(['gemini', 'puter', 'groq', 'openrouter', 'huggingface', 'together']);
  });

  it('starts at Puter (reports gemini→puter) when no Gemini key is supplied', async () => {
    callPuterMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync('', REPO_FILES, REPO_URL, ALL_KEYS, 'gemini-2.0-flash', onSwitch);

    expect(generateTextMock).not.toHaveBeenCalled();
    expect(callPuterMock).toHaveBeenCalledTimes(1);
    // onSwitch IS called to report the fallback to Puter
    expect(onSwitch).toHaveBeenCalledTimes(1);
    expect(onSwitch).toHaveBeenCalledWith('gemini', 'puter', 'No API key provided');
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('skips providers that have no key and hands off to the next configured one', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callPuterMock.mockRejectedValue(new Error('puter down'));
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callOpenRouterMock.mockRejectedValue(new Error('openrouter down'));
    callTogetherMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    // Only Gemini + Together keys present; Puter, Groq, OpenRouter and HuggingFace will be skipped or fail
    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      { togetherKey: 'together_key' },
      'gemini-2.0-flash',
      onSwitch
    );

    expect(callTogetherMock).toHaveBeenCalledTimes(1);
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('falls back to Puter on ANY Gemini error (including non-retryable)', async () => {
    // With the new logic, ALL errors trigger fallback, not just retryable ones
    generateTextMock.mockRejectedValue(new Error('400 invalid request'));
    callPuterMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-2.0-flash',
      onSwitch
    );

    expect(callPuterMock).toHaveBeenCalledTimes(1);
    expect(onSwitch).toHaveBeenCalledTimes(1);
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('throws the "all providers failed" error when every provider rejects', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callPuterMock.mockRejectedValue(new Error('puter down'));
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callOpenRouterMock.mockRejectedValue(new Error('openrouter down'));
    callHuggingFaceMock.mockRejectedValue(new Error('hf down'));
    callTogetherMock.mockRejectedValue(new Error('together down'));

    await expect(
      runAwarenessSync('AIza-key', REPO_FILES, REPO_URL, ALL_KEYS)
    ).rejects.toThrow(/Alle AI-Provider sind fehlgeschlagen/);

    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(callPuterMock).toHaveBeenCalledTimes(1);
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(callTogetherMock).toHaveBeenCalledTimes(1);
  });

  it('throws the "no key configured" error before any network call when nothing is set', async () => {
    await expect(
      runAwarenessSync('', REPO_FILES, REPO_URL, {})
    ).rejects.toThrow(/Kein API-Key konfiguriert/);

    expect(generateTextMock).not.toHaveBeenCalled();
    expect(callPuterMock).not.toHaveBeenCalled();
  });
});
