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

  it('should call generateContent statically with model and prompt parameters', async () => {
    const model = 'gemini-1.5-flash';
    const prompt = 'Test prompt';
    const mockResponse = 'Mocked response';
    vi.mocked(GeminiService.generateContent).mockResolvedValue(mockResponse);

    const result = await GeminiService.generateContent(model, prompt);

    expect(GeminiService.generateContent).toHaveBeenCalledWith(model, prompt);
    expect(result).toBe(mockResponse);
  });
});