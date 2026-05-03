import { describe, it, expect, vi, beforeEach } from 'vitest';
import { geminiService } from './geminiService';
import { GoogleGenerativeAI } from '@google/generative-ai';

const generateContentMock = vi.fn();
const getGenerativeModelMock = vi.fn(() => ({
  generateContent: generateContentMock,
}));

vi.mock('@google/generative-ai', () => {
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
  const TEST_MODEL = 'gemini-1.5-pro';

  beforeEach(() => {
    vi.clearAllMocks();
    generateContentMock.mockResolvedValue(mockResponse);
  });

  it('should call generateContent with the correct parameters', async () => {
    const prompt = 'Hello, AI!';
    const result = await geminiService.generateText(prompt, TEST_MODEL);

    expect(result).toBe('Mocked AI response');
    expect(getGenerativeModelMock).toHaveBeenCalledWith(
      expect.objectContaining({ model: TEST_MODEL })
    );
    expect(generateContentMock).toHaveBeenCalledWith(prompt);
  });

  it('should handle API errors gracefully', async () => {
    generateContentMock.mockRejectedValueOnce(new Error('API Error'));

    await expect(geminiService.generateText('Fail', TEST_MODEL)).rejects.toThrow('API Error');
  });

  it('should pass system instructions if provided', async () => {
    const prompt = 'Explain quantum physics';
    const systemPrompt = 'Speak like a pirate';
    
    await geminiService.generateText(prompt, TEST_MODEL, { 
      systemInstruction: systemPrompt 
    });

    expect(getGenerativeModelMock).toHaveBeenCalledWith(
      expect.objectContaining({
        model: TEST_MODEL,
        systemInstruction: systemPrompt
      })
    );
  });

  it('should utilize the correct model version', async () => {
    const specificModel = 'gemini-1.5-flash';
    
    await geminiService.generateText('test', specificModel);
    
    expect(getGenerativeModelMock).toHaveBeenCalledWith(
      expect.objectContaining({
        model: specificModel
      })
    );
  });

  it('should accept optional temperature and topP parameters', async () => {
    await geminiService.generateText('test', TEST_MODEL, { 
      temperature: 0.7,
      topP: 0.9
    });

    expect(getGenerativeModelMock).toHaveBeenCalledWith(
      expect.objectContaining({
        model: TEST_MODEL,
        generationConfig: expect.objectContaining({
          temperature: 0.7,
          topP: 0.9
        })
      })
    );
  });
});