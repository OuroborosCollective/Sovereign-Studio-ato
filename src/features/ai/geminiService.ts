import { GoogleGenerativeAI, Part, GenerationConfig } from "@google/generative-ai";

const API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY || "";
const genAI = new GoogleGenerativeAI(API_KEY);

export interface GeminiRequestOptions {
  model?: string;
  temperature?: number;
  topK?: number;
  topP?: number;
  maxOutputTokens?: number;
  stopSequences?: string[];
}

export const geminiService = {
  async generateText(prompt: string, options: GeminiRequestOptions = {}) {
    try {
      const config: GenerationConfig = {
        temperature: options.temperature ?? 0.7,
        topK: options.topK,
        topP: options.topP,
        maxOutputTokens: options.maxOutputTokens,
        stopSequences: options.stopSequences,
      };

      const model = genAI.getGenerativeModel({
        model: options.model || "gemini-1.5-flash",
        generationConfig: config,
      });

      const result = await model.generateContent(prompt);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("Gemini Service Error (Text):", error);
      throw error;
    }
  },

  async generateFromMedia(prompt: string, parts: Part[], options: GeminiRequestOptions = {}) {
    try {
      const model = genAI.getGenerativeModel({
        model: options.model || "gemini-1.5-flash",
      });

      const result = await model.generateContent([prompt, ...parts]);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("Gemini Service Error (Media):", error);
      throw error;
    }
  },

  async *streamText(prompt: string, options: GeminiRequestOptions = {}) {
    try {
      const model = genAI.getGenerativeModel({
        model: options.model || "gemini-1.5-flash",
      });

      const result = await model.generateContentStream(prompt);
      for await (const chunk of result.stream) {
        const chunkText = chunk.text();
        yield chunkText;
      }
    } catch (error) {
      console.error("Gemini Service Error (Stream):", error);
      throw error;
    }
  }
};