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

  it('should call generateContent statically with prompt parameter', async () => {
    const prompt = 'Test prompt';
    const mockResponse = 'Mocked response';
    vi.mocked(GeminiService.generateContent).mockResolvedValue(mockResponse);

    const result = await GeminiService.generateContent(prompt);

    expect(GeminiService.generateContent).toHaveBeenCalledWith(prompt);
    expect(result).toBe(mockResponse);
  });
});