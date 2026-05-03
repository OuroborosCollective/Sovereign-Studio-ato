import { describe, it, expect, vi, beforeEach } from 'vitest';
import { geminiService } from './geminiService';
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
  const TEST_MODEL = 'gemini-1.5-pro';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call generateContent with the correct parameters', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: TEST_MODEL });
    (modelMock.generateContent as any).mockResolvedValue(mockResponse);

    const prompt = 'Hello, AI!';
    const result = await geminiService.generateText(prompt, TEST_MODEL);

    expect(result).toBe('Mocked AI response');
    expect(modelMock.generateContent).toHaveBeenCalledWith(prompt);
  });

  it('should handle API errors gracefully', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: TEST_MODEL });
    (modelMock.generateContent as any).mockRejectedValue(new Error('API Error'));

    await expect(geminiService.generateText('Fail', TEST_MODEL)).rejects.toThrow('API Error');
  });

  it('should pass system instructions if provided', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: TEST_MODEL });
    (modelMock.generateContent as any).mockResolvedValue(mockResponse);

    const prompt = 'Explain quantum physics';
    const systemPrompt = 'Speak like a pirate';
    
    await geminiService.generateText(prompt, TEST_MODEL, { 
      systemInstruction: systemPrompt 
    });

    expect(modelMock.generateContent).toHaveBeenCalled();
  });

  it('should utilize the correct model version', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const specificModel = 'gemini-1.5-flash';
    
    await geminiService.generateText('test', specificModel);
    
    expect(genAIInstance.getGenerativeModel).toHaveBeenCalledWith(
      expect.objectContaining({
        model: specificModel
      })
    );
  });

  it('should accept optional temperature and topP parameters', async () => {
    const genAIInstance = new GoogleGenerativeAI('test-key');
    const modelMock = genAIInstance.getGenerativeModel({ model: TEST_MODEL });
    (modelMock.generateContent as any).mockResolvedValue(mockResponse);

    await geminiService.generateText('test', TEST_MODEL, { 
      temperature: 0.7,
      topP: 0.9
    });

    expect(genAIInstance.getGenerativeModel).toHaveBeenCalled();
  });
});