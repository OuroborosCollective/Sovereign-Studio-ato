export type GeminiModel = 'gemini-1.5-flash' | 'gemini-1.5-pro' | 'gemini-1.0-pro';

export interface GenerationConfig {
  temperature?: number;
  topP?: number;
  topK?: number;
  maxOutputTokens?: number;
  stopSequences?: string[];
}

export interface GenerateOptions {
  model?: GeminiModel;
  systemInstruction?: string;
  generationConfig?: Partial<GenerationConfig>;
}

const DEFAULT_MODEL: GeminiModel = 'gemini-1.5-flash';
const API_ENDPOINT = '/api/ai/generate';

export class GeminiService {
  static async generateContent(
    prompt: string,
    optionsOrSystemInstruction: GenerateOptions | string = {}
  ): Promise<string> {
    const options: GenerateOptions =
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

    const payload = {
      model: options.model ?? DEFAULT_MODEL,
      systemInstruction: options.systemInstruction,
      prompt,
      generationConfig,
    };

    try {
      const response = await fetch(API_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to generate content');
      }

      const data = await response.json();
      return data.text;
    } catch (error) {
      console.error('GeminiService Error:', error);
      throw error;
    }
  }
}