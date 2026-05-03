import { GoogleGenerativeAI, GenerationConfig } from '@google/generative-ai';
import { vi } from 'vitest';

vi.mock('@google/generative-ai', () => {
  const generateContentMock = vi.fn().mockResolvedValue({
    response: {
      text: () => 'Mocked response content',
    },
  });

  const getGenerativeModelMock = vi.fn().mockImplementation(() => {
    return {
      generateContent: generateContentMock,
    };
  });

  return {
    GoogleGenerativeAI: vi.fn().mockImplementation(() => ({
      getGenerativeModel: getGenerativeModelMock,
    })),
  };
});

const genAI = new GoogleGenerativeAI((import.meta.env.VITE_GEMINI_API_KEY as string) || 'test-api-key');

export class GeminiService {
  static async generateContent(prompt: string, systemInstruction?: string): Promise<string> {
    const generationConfig: GenerationConfig = {
      temperature: 0.7,
      topP: 0.95,
      topK: 40,
      maxOutputTokens: 8192,
    };

    const model = genAI.getGenerativeModel({
      model: 'gemini-1.5-flash',
      systemInstruction: systemInstruction,
    });

    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig,
    });

    const response = await result.response;
    return response.text();
  }
}