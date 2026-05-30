import { GoogleGenerativeAI, Part, GenerationConfig } from "@google/generative-ai";

// Default model - updated to gemini-2.0-flash
const DEFAULT_MODEL = "gemini-2.0-flash";

export interface GeminiRequestOptions {
  model?: string;
  temperature?: number;
  topK?: number;
  topP?: number;
  maxOutputTokens?: number;
  stopSequences?: string[];
}

function createClient(apiKey: string) {
  if (!apiKey || !apiKey.trim()) {
    throw new Error("Kein Gemini API-Key angegeben. Bitte einen gültigen Key in den Einstellungen eintragen.");
  }
  return new GoogleGenerativeAI(apiKey.trim());
}

async function withRetry<T>(fn: () => Promise<T>, retries = 2, delayMs = 2000): Promise<T> {
  try {
    return await fn();
  } catch (error: any) {
    const is429 = error?.status === 429 || error?.message?.includes("429") || error?.message?.includes("quota") || error?.message?.includes("RESOURCE_EXHAUSTED");
    if (is429 && retries > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      return withRetry(fn, retries - 1, delayMs * 2);
    }
    throw error;
  }
}

export const geminiService = {
  async generateText(apiKey: string, prompt: string, options: GeminiRequestOptions = {}) {
    const genAI = createClient(apiKey);
    const config: GenerationConfig = {
      temperature: options.temperature ?? 0.7,
      topK: options.topK,
      topP: options.topP,
      maxOutputTokens: options.maxOutputTokens ?? 2048,
      stopSequences: options.stopSequences,
    };
    const model = genAI.getGenerativeModel({
      model: options.model || DEFAULT_MODEL,
      generationConfig: config,
    });
    return withRetry(async () => {
      const result = await model.generateContent(prompt);
      const response = await result.response;
      return response.text();
    });
  },

  async generateFromMedia(apiKey: string, prompt: string, parts: Part[], options: GeminiRequestOptions = {}) {
    const genAI = createClient(apiKey);
    const model = genAI.getGenerativeModel({
      model: options.model || DEFAULT_MODEL,
    });
    return withRetry(async () => {
      const result = await model.generateContent([prompt, ...parts]);
      const response = await result.response;
      return response.text();
    });
  },

  async *streamText(apiKey: string, prompt: string, options: GeminiRequestOptions = {}) {
    const genAI = createClient(apiKey);
    const model = genAI.getGenerativeModel({
      model: options.model || DEFAULT_MODEL,
    });
    const result = await model.generateContentStream(prompt);
    for await (const chunk of result.stream) {
      yield chunk.text();
    }
  },
};
