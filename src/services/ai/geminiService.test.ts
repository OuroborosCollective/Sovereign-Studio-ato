import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { GeminiService } from './geminiService';
import type { GenerateOptions } from './geminiService';

const mocks = vi.hoisted(() => {
  const generateContentMock = vi.fn();
  const getGenerativeModelMock = vi.fn();

  return {
    generateContentMock,
    getGenerativeModelMock,
  };
});

vi.mock('@google/generative-ai', () => {
  return {
    GoogleGenerativeAI: vi.fn().mockImplementation(() => ({
      getGenerativeModel: mocks.getGenerativeModelMock,
    })),
  };
});

describe('GeminiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.generateContentMock.mockResolvedValue({
      response: {
        text: () => 'Mocked response content',
      },
    });

    mocks.getGenerativeModelMock.mockReturnValue({
      generateContent: mocks.generateContentMock,
    });
  });

  it('creates the GoogleGenerativeAI client', () => {
    expect(GoogleGenerativeAI).toHaveBeenCalledWith(expect.any(String));
  });

  it('generates content with the default model', async () => {
    const result = await GeminiService.generateContent('Hello Gemini');

    expect(result).toBe('Mocked response content');

    expect(mocks.getGenerativeModelMock).toHaveBeenCalledWith({
      model: 'gemini-1.5-flash',
    });

    expect(mocks.generateContentMock).toHaveBeenCalledWith({
      contents: [
        {
          role: 'user',
          parts: [{ text: 'Hello Gemini' }],
        },
      ],
      generationConfig: {
        temperature: 0.7,
        topP: 0.95,
        topK: 40,
        maxOutputTokens: 8192,
      },
    });
  });

  it('generates content with a custom model', async () => {
    const options: GenerateOptions = {
      model: 'gemini-1.5-pro',
    };

    const result = await GeminiService.generateContent('Use custom model', options);

    expect(result).toBe('Mocked response content');

    expect(mocks.getGenerativeModelMock).toHaveBeenCalledWith({
      model: 'gemini-1.5-pro',
    });
  });

  it('supports legacy string systemInstruction argument', async () => {
    const result = await GeminiService.generateContent(
      'Explain the world lore',
      'You are a fantasy MMORPG oracle.'
    );

    expect(result).toBe('Mocked response content');

    expect(mocks.getGenerativeModelMock).toHaveBeenCalledWith({
      model: 'gemini-1.5-flash',
      systemInstruction: {
        role: 'system',
        parts: [{ text: 'You are a fantasy MMORPG oracle.' }],
      },
    });
  });

  it('supports systemInstruction inside GenerateOptions', async () => {
    const options: GenerateOptions = {
      model: 'gemini-1.5-flash',
      systemInstruction: 'You are an NPC quest writer.',
    };

    const result = await GeminiService.generateContent('Create a quest', options);

    expect(result).toBe('Mocked response content');

    expect(mocks.getGenerativeModelMock).toHaveBeenCalledWith({
      model: 'gemini-1.5-flash',
      systemInstruction: {
        role: 'system',
        parts: [{ text: 'You are an NPC quest writer.' }],
      },
    });
  });

  it('merges custom generationConfig with defaults', async () => {
    const options: GenerateOptions = {
      model: 'gemini-1.5-flash',
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 1024,
      },
    };

    const result = await GeminiService.generateContent('Low creativity answer', options);

    expect(result).toBe('Mocked response content');

    expect(mocks.generateContentMock).toHaveBeenCalledWith({
      contents: [
        {
          role: 'user',
          parts: [{ text: 'Low creativity answer' }],
        },
      ],
      generationConfig: {
        temperature: 0.2,
        topP: 0.95,
        topK: 40,
        maxOutputTokens: 1024,
      },
    });
  });

  it('propagates generateContent errors', async () => {
    mocks.generateContentMock.mockRejectedValueOnce(new Error('Gemini failed'));

    const options: GenerateOptions = {
      model: 'gemini-1.5-flash',
    };

    await expect(
      GeminiService.generateContent('Trigger failure', options)
    ).rejects.toThrow('Gemini failed');
  });
});
