import { GoogleGenerativeAI, GenerationConfig, ModelParams } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI((import.meta.env.VITE_GEMINI_API_KEY as string) || '');

export class GeminiService {
  static async generateContent(prompt: string, systemInstruction?: string): Promise<string> {
    const generationConfig: GenerationConfig = {
      temperature: 0.7,
      topP: 0.95,
      topK: 40,
      maxOutputTokens: 8192,
    };

    const modelParams: ModelParams = {
      model: 'gemini-1.5-flash',
      generationConfig,
    };

    if (systemInstruction) {
      modelParams.systemInstruction = systemInstruction;
    }

    const model = genAI.getGenerativeModel(modelParams);

    const result = await model.generateContent(prompt);
    const response = await result.response;
    return response.text();
  }
}