import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
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
    vi.resetModules();
    const { geminiService } = await import('./geminiService');

    const result = await geminiService.generateText('Hello Gemini');

    expect(result).toBe(mockResponseText);
    expect(mockGetGenerativeModel).toHaveBeenCalledWith({
      model: 'gemini-1.5-flash',
      generationConfig: {
        temperature: 0.7,
        topK: undefined,
        topP: undefined,
        maxOutputTokens: undefined,
        stopSequences: undefined
      }
    });
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
    const { geminiService } = await import('./geminiService');

    await expect(geminiService.generateText('Hello Gemini')).rejects.toThrow('API Error');
  });

  describe('generateFromMedia', () => {
    it('should successfully return text when generateFromMedia is called', async () => {
      const mockResponseText = 'This is a media response';
      const mockParts = [{ inlineData: { data: 'base64data', mimeType: 'image/png' } }];

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

      vi.resetModules();
      const { geminiService } = await import('./geminiService');

      const result = await geminiService.generateFromMedia('Describe this image', mockParts);

      expect(result).toBe(mockResponseText);
      expect(mockGetGenerativeModel).toHaveBeenCalledWith({ model: 'gemini-1.5-flash' });
      expect(mockGenerateContent).toHaveBeenCalledWith(['Describe this image', ...mockParts]);
    });

    it('should throw an error if generateFromMedia fails', async () => {
      const mockError = new Error('Media API Error');

      const mockGenerateContent = vi.fn().mockRejectedValue(mockError);

      const mockGetGenerativeModel = vi.fn().mockReturnValue({
        generateContent: mockGenerateContent,
      });

      (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
        getGenerativeModel: mockGetGenerativeModel,
      }));

      vi.resetModules();
      const { geminiService } = await import('./geminiService');

      await expect(geminiService.generateFromMedia('Describe this image', [])).rejects.toThrow('Media API Error');
    });
  });

  describe('streamText', () => {
    it('should successfully stream text when streamText is called', async () => {
      const mockChunks = ['chunk1', 'chunk2'];
      const mockStream = (async function* () {
        for (const chunk of mockChunks) {
          yield { text: () => chunk };
        }
      })();

      const mockGenerateContentStream = vi.fn().mockResolvedValue({
        stream: mockStream,
      });

      const mockGetGenerativeModel = vi.fn().mockReturnValue({
        generateContentStream: mockGenerateContentStream,
      });

      (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
        getGenerativeModel: mockGetGenerativeModel,
      }));

      vi.resetModules();
      const { geminiService } = await import('./geminiService');

      const resultStream = geminiService.streamText('Stream this');
      const results = [];
      for await (const chunk of resultStream) {
        results.push(chunk);
      }

      expect(results).toEqual(mockChunks);
      expect(mockGetGenerativeModel).toHaveBeenCalledWith({ model: 'gemini-1.5-flash' });
      expect(mockGenerateContentStream).toHaveBeenCalledWith('Stream this');
    });

    it('should throw an error if streamText fails', async () => {
      const mockError = new Error('Stream API Error');

      const mockGenerateContentStream = vi.fn().mockRejectedValue(mockError);

      const mockGetGenerativeModel = vi.fn().mockReturnValue({
        generateContentStream: mockGenerateContentStream,
      });

      (GoogleGenerativeAI as unknown as Mock).mockImplementation(() => ({
        getGenerativeModel: mockGetGenerativeModel,
      }));

      vi.resetModules();
      const { geminiService } = await import('./geminiService');

      const resultStream = geminiService.streamText('Stream this');
      await expect(async () => {
        for await (const _ of resultStream) {
          // do nothing
        }
      }).rejects.toThrow('Stream API Error');
    });
  });
});
