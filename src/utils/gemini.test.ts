import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GeminiService } from './gemini';
import { GoogleGenerativeAI } from '@google/generative-ai';

vi.mock('@google/generative-ai', () => {
  const generateContentMock = vi.fn().mockResolvedValue({
    response: {
      text: () => 'Mocked response'
    }
  });

  const getGenerativeModelMock = vi.fn().mockReturnValue({
    generateContent: generateContentMock
  });

  return {
    GoogleGenerativeAI: vi.fn().mockImplementation(() => ({
      getGenerativeModel: getGenerativeModelMock
    }))
  };
});

describe('GeminiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should be defined', () => {
    expect(GeminiService).toBeDefined();
  });

  it('should call getGenerativeModel with a single ModelParams object', async () => {
    const prompt = 'Test prompt';
    
    const result = await GeminiService.generateContent(prompt);

    const MockedAI = vi.mocked(GoogleGenerativeAI);
    const aiInstance = MockedAI.mock.results[0].value;

    expect(aiInstance.getGenerativeModel).toHaveBeenCalledWith({
      model: expect.any(String),
      systemInstruction: expect.any(String),
      generationConfig: expect.objectContaining({
        temperature: expect.any(Number),
        topP: expect.any(Number),
        topK: expect.any(Number),
        maxOutputTokens: expect.any(Number),
        responseMimeType: expect.any(String)
      })
    });

    expect(result).toBe('Mocked response');
  });

  it('should handle configuration within the generation call', async () => {
    const prompt = 'Test prompt';
    const result = await GeminiService.generateContent(prompt);
    
    const MockedAI = vi.mocked(GoogleGenerativeAI);
    const aiInstance = MockedAI.mock.results[0].value;
    const modelInstance = aiInstance.getGenerativeModel.mock.results[0].value;

    expect(modelInstance.generateContent).toHaveBeenCalledWith(prompt);
    expect(result).toBe('Mocked response');
  });
});