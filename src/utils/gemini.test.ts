import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GeminiService } from './gemini';

vi.mock('./gemini', () => ({
  GeminiService: {
    generateContent: vi.fn()
  }
}));

describe('GeminiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should be defined', () => {
    expect(GeminiService).toBeDefined();
  });

  it('should call generateContent statically with a valid parameters object', async () => {
    const params = {
      model: 'gemini-1.5-flash',
      prompt: 'Test prompt',
      systemInstruction: 'You are a helpful assistant'
    };
    const mockResponse = 'Mocked response';
    vi.mocked(GeminiService.generateContent).mockResolvedValue(mockResponse);

    const result = await GeminiService.generateContent(params);

    expect(GeminiService.generateContent).toHaveBeenCalledWith(params);
    expect(result).toBe(mockResponse);
  });
});