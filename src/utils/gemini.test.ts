import { GoogleGenerativeAI } from '@google/generative-ai';
import type { GenerationConfig } from '@google/generative-ai';

export type GeminiModelName =
  | 'gemini-1.5-flash'
  | 'gemini-1.5-pro'
  | 'gemini-pro'
  | string;

export interface GeminiGenerateOptions {
  model?: GeminiModelName;
  systemInstruction?: string;
  generationConfig?: Partial<GenerationConfig>;
}

const apiKey =
  (import.meta.env.VITE_GEMINI_API_KEY as string | undefined) || 'test-api-key';

const genAI = new GoogleGenerativeAI(apiKey);

const DEFAULT_MODEL = 'gemini-1.5-flash';

export class GeminiService {
  static async generateContent(
    prompt: string,
    optionsOrSystemInstruction: GeminiGenerateOptions | string = {}
  ): Promise<string> {
    const options: GeminiGenerateOptions =
      typeof optionsOrSystemInstruction === 'string'
        ? { systemInstruction: optionsOrSystemInstruction }
        : optionsOrSystemInstruction;

    const generationConfig: GenerationConfig = {
      temperature: 0.7,
      topP: 0.95,
      topK: 40,
      maxOutputTokens: 8192,
      ...options.generationConfig,
    };

    const model = genAI.getGenerativeModel({
      model: options.model ?? DEFAULT_MODEL,
      systemInstruction: options.systemInstruction
        ? {
            role: 'system',
            parts: [{ text: options.systemInstruction }],
          }
        : undefined,
    });

    const result = await model.generateContent({
      contents: [
        {
          role: 'user',
          parts: [{ text: prompt }],
        },
      ],
      generationConfig,
    });

    const response = await result.response;
    return response.text();
  }
}
