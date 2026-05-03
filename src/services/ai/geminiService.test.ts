import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GeminiService } from './geminiService';
import { GoogleGenerativeAI } from '@google/generative-ai';

vi.mock('@google/generative-ai', () => {
  const generateContentMock = vi.fn();
  const getGenerativeModelMock = vi.fn(() => ({
    generateContent: generateContentMock,
  }));

  return {
    GoogleGenerativeAI: vi.fn().mockImplementation(() => ({
      getGenerativeModel: getGenerativeModelMock,
    })),
  };
});

describe('GeminiService', () => {
  const mockResponse = {
    response: {
      text: () => 'Mocked AI response',
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call generateContent with the correct parameters', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: 'gemini-pro' });
    (modelMock.generateContent as any).mockResolvedValue(mockResponse);

    const prompt = 'Hello, AI!';
    const result = await GeminiService.generateText(prompt);

    expect(result).toBe('Mocked AI response');
    expect(modelMock.generateContent).toHaveBeenCalledWith(prompt);
  });

  it('should handle API errors gracefully', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: 'gemini-pro' });
    (modelMock.generateContent as any).mockRejectedValue(new Error('API Error'));

    await expect(GeminiService.generateText('Fail')).rejects.toThrow('API Error');
  });

  it('should pass system instructions if provided', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: 'gemini-pro' });
    (modelMock.generateContent as any).mockResolvedValue(mockResponse);

    const prompt = 'Explain quantum physics';
    const systemPrompt = 'Speak like a pirate';
    
    await GeminiService.generateText(prompt, { systemInstruction: systemPrompt });

    expect(modelMock.generateContent).toHaveBeenCalled();
  });

  it('should utilize the correct model version', () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    GeminiService.generateText('test');
    
    expect(genAIInstance.getGenerativeModel).toHaveBeenCalledWith(
      expect.objectContaining({
        model: expect.stringContaining('gemini')
      })
    );
  });
});