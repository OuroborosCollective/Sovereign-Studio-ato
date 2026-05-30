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
const callGroqMock = vi.fn();
const callHuggingFaceMock = vi.fn();
const callTogetherMock = vi.fn();
const callOpenRouterMock = vi.fn();
vi.mock('./providerManager', () => ({
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
  return { text, provider: 'groq' as ProviderType, model: 'm' };
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
      'gemini-1.5-flash',
      onSwitch
    );

    expect(generateTextMock).toHaveBeenCalledTimes(1);
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

  it('Gemini 429 → Groq succeeds, and reports the gemini→groq switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callGroqMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-1.5-flash',
      onSwitch
    );

    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).not.toHaveBeenCalled();
    expect(callOpenRouterMock).not.toHaveBeenCalled();

    expect(onSwitch).toHaveBeenCalledTimes(1);
    expect(onSwitch).toHaveBeenCalledWith('gemini', 'groq', expect.stringContaining('429'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('Groq fails → HuggingFace succeeds, and reports the groq→huggingface switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callHuggingFaceMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-1.5-flash',
      onSwitch
    );

    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(callTogetherMock).not.toHaveBeenCalled();
    expect(callOpenRouterMock).not.toHaveBeenCalled();

    expect(onSwitch).toHaveBeenCalledWith('gemini', 'groq', expect.any(String));
    expect(onSwitch).toHaveBeenCalledWith('groq', 'huggingface', expect.stringContaining('groq down'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('HuggingFace fails → Together succeeds, and reports the huggingface→together switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callHuggingFaceMock.mockRejectedValue(new Error('hf down'));
    callTogetherMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-1.5-flash',
      onSwitch
    );

    expect(callHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(callTogetherMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).not.toHaveBeenCalled();

    expect(onSwitch).toHaveBeenCalledWith('huggingface', 'together', expect.stringContaining('hf down'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('Together fails → OpenRouter succeeds, and reports the together→openrouter switch', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callHuggingFaceMock.mockRejectedValue(new Error('hf down'));
    callTogetherMock.mockRejectedValue(new Error('together down'));
    callOpenRouterMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      ALL_KEYS,
      'gemini-1.5-flash',
      onSwitch
    );

    expect(callTogetherMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).toHaveBeenCalledTimes(1);

    expect(onSwitch).toHaveBeenCalledWith('together', 'openrouter', expect.stringContaining('together down'));
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('walks every provider in order when each one before the last fails', async () => {
    const callOrder: string[] = [];
    generateTextMock.mockImplementation(async () => {
      callOrder.push('gemini');
      throw RETRYABLE;
    });
    callGroqMock.mockImplementation(async () => {
      callOrder.push('groq');
      throw new Error('groq down');
    });
    callHuggingFaceMock.mockImplementation(async () => {
      callOrder.push('huggingface');
      throw new Error('hf down');
    });
    callTogetherMock.mockImplementation(async () => {
      callOrder.push('together');
      throw new Error('together down');
    });
    callOpenRouterMock.mockImplementation(async () => {
      callOrder.push('openrouter');
      return providerResponse();
    });

    await runAwarenessSync('AIza-key', REPO_FILES, REPO_URL, ALL_KEYS);

    expect(callOrder).toEqual(['gemini', 'groq', 'huggingface', 'together', 'openrouter']);
  });

  it('starts at Groq (no gemini→groq report) when no Gemini key is supplied', async () => {
    callGroqMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    const result = await runAwarenessSync('', REPO_FILES, REPO_URL, ALL_KEYS, 'gemini-1.5-flash', onSwitch);

    expect(generateTextMock).not.toHaveBeenCalled();
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(onSwitch).not.toHaveBeenCalled();
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('skips providers that have no key and hands off to the next configured one', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callTogetherMock.mockResolvedValue(providerResponse());
    const onSwitch = vi.fn();

    // Only Gemini + Together keys present; Groq and HuggingFace are skipped.
    const result = await runAwarenessSync(
      'AIza-key',
      REPO_FILES,
      REPO_URL,
      { togetherKey: 'together_key' },
      'gemini-1.5-flash',
      onSwitch
    );

    expect(callGroqMock).not.toHaveBeenCalled();
    expect(callHuggingFaceMock).not.toHaveBeenCalled();
    expect(callTogetherMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).not.toHaveBeenCalled();
    expect(result.summary).toBe('Ein Test-Projekt.');
  });

  it('throws a non-retryable Gemini error without trying any fallback provider', async () => {
    generateTextMock.mockRejectedValue(new Error('400 invalid request'));
    const onSwitch = vi.fn();

    await expect(
      runAwarenessSync('AIza-key', REPO_FILES, REPO_URL, ALL_KEYS, 'gemini-1.5-flash', onSwitch)
    ).rejects.toThrow('400 invalid request');

    expect(callGroqMock).not.toHaveBeenCalled();
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it('throws the "all providers failed" error when every provider rejects', async () => {
    generateTextMock.mockRejectedValue(RETRYABLE);
    callGroqMock.mockRejectedValue(new Error('groq down'));
    callHuggingFaceMock.mockRejectedValue(new Error('hf down'));
    callTogetherMock.mockRejectedValue(new Error('together down'));
    callOpenRouterMock.mockRejectedValue(new Error('openrouter down'));

    await expect(
      runAwarenessSync('AIza-key', REPO_FILES, REPO_URL, ALL_KEYS)
    ).rejects.toThrow(/Alle AI-Provider sind fehlgeschlagen/);

    expect(generateTextMock).toHaveBeenCalledTimes(1);
    expect(callGroqMock).toHaveBeenCalledTimes(1);
    expect(callHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(callTogetherMock).toHaveBeenCalledTimes(1);
    expect(callOpenRouterMock).toHaveBeenCalledTimes(1);
  });

  it('throws the "no key configured" error before any network call when nothing is set', async () => {
    await expect(
      runAwarenessSync('', REPO_FILES, REPO_URL, {})
    ).rejects.toThrow(/Kein API-Key konfiguriert/);

    expect(generateTextMock).not.toHaveBeenCalled();
    expect(callGroqMock).not.toHaveBeenCalled();
  });
});
