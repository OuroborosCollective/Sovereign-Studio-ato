import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as providerManager from './providerManager';

describe('ProviderManager API calls', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('callGroq should use callOpenAICompatible pattern', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        choices: [{ message: { content: 'Groq response' } }],
        usage: { totalTokens: 10 }
      })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callGroq('key', 'model', 'prompt', {});

    expect(result.text).toBe('Groq response');
    expect(result.provider).toBe('groq');
    expect(fetch).toHaveBeenCalledWith(
      'https://api.groq.com/openai/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer key',
          'Content-Type': 'application/json'
        })
      })
    );
  });

  it('callPollinations should use callOpenAICompatible with correct default tokens', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        choices: [{ message: { content: 'Pollinations response' } }]
      })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callPollinations('model', 'prompt', {});

    expect(result.text).toBe('Pollinations response');
    expect(result.provider).toBe('pollinations');

    const body = JSON.parse((fetch as any).mock.calls[0][1].body);
    expect(body.max_tokens).toBe(4096);
  });

  it('should handle errors using fetchWithProviderError logic', async () => {
    const mockResponse = {
      ok: false,
      status: 429,
      json: () => Promise.resolve({ error: { message: 'Rate limited' } })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    await expect(providerManager.callTogether('key', 'model', 'prompt', {}))
      .rejects.toMatchObject({
        provider: 'together',
        error: 'Rate limited',
        statusCode: 429,
        isRetryable: true
      });
  });

  it('callMlvoCa should use fetchWithProviderError pattern', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        response: 'MLVoca response'
      })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callMlvoCa('model', 'prompt', {});

    expect(result.text).toBe('MLVoca response');
    expect(result.provider).toBe('mlvoca');
    expect(fetch).toHaveBeenCalledWith(
      'https://mlvoca.com/api/generate',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json'
        })
      })
    );
  });
  it('callTogether should use callOpenAICompatible pattern', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        choices: [{ message: { content: 'Together response' } }],
      })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callTogether('key', 'model', 'prompt', {});

    expect(result.text).toBe('Together response');
    expect(result.provider).toBe('together');
    expect(fetch).toHaveBeenCalledWith(
      'https://api.together.xyz/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer key',
          'Content-Type': 'application/json'
        })
      })
    );
  });

  it('callOpenRouter should use callOpenAICompatible pattern', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        choices: [{ message: { content: 'OpenRouter response' } }],
      })
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callOpenRouter('key', 'model', 'prompt', {});

    expect(result.text).toBe('OpenRouter response');
    expect(result.provider).toBe('openrouter');
    expect(fetch).toHaveBeenCalledWith(
      'https://openrouter.ai/api/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer key',
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://sovereign-studio.app',
          'X-Title': 'Sovereign Studio'
        })
      })
    );
  });

  it('callHuggingFace should use correct API pattern', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve([{
        generated_text: 'HuggingFace response'
      }])
    };
    (fetch as any).mockResolvedValue(mockResponse);

    const result = await providerManager.callHuggingFace('key', 'meta-llama/Llama-3.2-1B-Instruct', 'prompt', {});

    expect(result.text).toBe('HuggingFace response');
    expect(result.provider).toBe('huggingface');
    expect(fetch).toHaveBeenCalledWith(
      'https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-1B-Instruct',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer key',
          'Content-Type': 'application/json'
        })
      })
    );
  });

});
