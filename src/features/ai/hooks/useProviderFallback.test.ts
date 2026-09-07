import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useProviderFallback } from './useProviderFallback';
import { providerManager } from '../providerManager';
import { geminiService } from '../geminiService';

vi.mock('../providerManager', async () => {
  const actual = await vi.importActual('../providerManager');
  return {
    ...actual,
    providerManager: {
      setApiKey: vi.fn(),
      getConfiguredProviders: vi.fn(() => []),
      generateWithFallback: vi.fn(),
    }
  };
});

vi.mock('../geminiService', () => ({
  geminiService: {
    generateText: vi.fn(),
  }
}));

describe('useProviderFallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('should initialize with gemini and no errors', () => {
    const { result } = renderHook(() => useProviderFallback());
    expect(result.current.currentProvider).toBe('gemini');
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('should set API keys from localStorage on mount', () => {
    localStorage.setItem('sovereign_groq_api_key', 'test-groq-key');
    renderHook(() => useProviderFallback());
    expect(providerManager.setApiKey).toHaveBeenCalledWith('groq', 'test-groq-key');
  });

  it('should update localStorage when setProviderApiKey is called', () => {
    const { result } = renderHook(() => useProviderFallback());
    act(() => {
      result.current.setProviderApiKey('groq', 'new-key');
    });
    expect(providerManager.setApiKey).toHaveBeenCalledWith('groq', 'new-key');
    expect(localStorage.getItem('sovereign_groq_api_key')).toBe('new-key');
  });

  it('should remove from localStorage when setProviderApiKey is called with empty string', () => {
    localStorage.setItem('sovereign_groq_api_key', 'old-key');
    const { result } = renderHook(() => useProviderFallback());
    act(() => {
      result.current.setProviderApiKey('groq', '');
    });
    expect(localStorage.getItem('sovereign_groq_api_key')).toBeNull();
  });

  it('should call geminiService first if gemini API key is provided', async () => {
    (geminiService.generateText as any).mockResolvedValue('gemini response');
    const { result } = renderHook(() => useProviderFallback());

    let res;
    await act(async () => {
      res = await result.current.generateContent('test prompt', 'gemini-key');
    });

    expect(geminiService.generateText).toHaveBeenCalledWith('gemini-key', 'test prompt', expect.any(Object));
    expect(res).toEqual({ text: 'gemini response', provider: 'gemini', model: 'gemini-1.5-flash' });
  });

  it('should fallback to providerManager on gemini 429 error', async () => {
    const error = new Error('429 Too Many Requests');
    (geminiService.generateText as any).mockRejectedValue(error);
    (providerManager.generateWithFallback as any).mockResolvedValue({
      text: 'fallback response',
      provider: 'pollinations',
      model: 'openai'
    });

    const onFallback = vi.fn();
    const { result } = renderHook(() => useProviderFallback({ onFallback }));

    let res;
    await act(async () => {
      res = await result.current.generateContent('test prompt', 'gemini-key');
    });

    expect(onFallback).toHaveBeenCalledWith('gemini', 'groq', expect.stringContaining('429 Too Many Requests'));
    expect(providerManager.generateWithFallback).toHaveBeenCalled();
    expect(res).toEqual({ text: 'fallback response', provider: 'pollinations', model: 'openai' });
    expect(result.current.currentProvider).toBe('pollinations');
  });
});
