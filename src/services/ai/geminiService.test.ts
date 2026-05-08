import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { geminiService } from '../../features/ai/geminiService';
import { GoogleGenerativeAI } from '@google/generative-ai';

vi.mock('@google/generative-ai');

describe('GeminiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('should successfully return text when generateText is called', async () => {
    const mockResponseText = 'This is a generated response';
    
    const mockGenerateContent = vi.fn().mockResolvedValue({
      response: {
        text: () => mockResponseText,
      },
    });

    const mockGetGenerativeModel = vi.fn().mockReturnValue({
      generateContent: mockGenerateContent,
    });

    (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
      getGenerativeModel: mockGetGenerativeModel,
    }));

    // Re-import to re-evaluate after mock
    const { geminiService: localGeminiService } = await import('../../features/ai/geminiService');

    const result = await localGeminiService.generateText('Hello Gemini');

    expect(result).toBe(mockResponseText);
    expect(mockGetGenerativeModel).toHaveBeenCalledWith({ model: 'gemini-1.5-flash', generationConfig: { temperature: 0.7, topK: undefined, topP: undefined, maxOutputTokens: undefined, stopSequences: undefined } });
    expect(mockGenerateContent).toHaveBeenCalledWith('Hello Gemini');
  });

  it('should throw an error if generateText fails', async () => {
    const mockError = new Error('API Error');
    
    const mockGenerateContent = vi.fn().mockRejectedValue(mockError);

    const mockGetGenerativeModel = vi.fn().mockReturnValue({
      generateContent: mockGenerateContent,
    });

    (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
      getGenerativeModel: mockGetGenerativeModel,
    }));

    vi.resetModules();
    const { geminiService: localGeminiService } = await import('../../features/ai/geminiService');

    await expect(localGeminiService.generateText('Hello Gemini')).rejects.toThrow('API Error');
  });
});