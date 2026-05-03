import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { GeminiService } from '../../shared/api/geminiService';
import { GoogleGenerativeAI } from '@google/generative-ai';

vi.mock('@google/generative-ai');

describe('GeminiService', () => {
  let service: GeminiService;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new GeminiService();
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

    const result = await service.generateText('Hello Gemini');

    expect(result).toBe(mockResponseText);
    expect(mockGetGenerativeModel).toHaveBeenCalledWith({ model: 'gemini-pro' });
    expect(mockGenerateContent).toHaveBeenCalledWith('Hello Gemini');
  });

  it('should throw an error if generateText fails', async () => {
    const mockError = new Error('API Error');
    
    const mockGenerateContent = vi.fn().mockRejectedValue(mockError);

    (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
      getGenerativeModel: vi.fn().mockReturnValue({
        generateContent: mockGenerateContent,
      }),
    }));

    await expect(service.generateText('Hello Gemini')).rejects.toThrow('API Error');
  });
});