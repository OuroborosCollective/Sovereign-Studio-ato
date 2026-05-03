import { GoogleGenerativeAI, GenerativeModel, GenerationConfig, Content, GenerateContentResult } from "@google/generative-ai";

export interface GeminiResponse {
  text: string;
  usage?: any;
}

export class GeminiService {
  private genAI: GoogleGenerativeAI;
  private model: GenerativeModel;

  constructor(apiKey: string, modelName: string = "gemini-1.5-flash") {
    if (!apiKey) {
      throw new Error("Gemini API Key is missing");
    }
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: modelName });
  }

  /**
   * Statische Methode zur Inhaltsgenerierung
   */
  static async generateContent(
    apiKey: string, 
    prompt: string, 
    modelName: string = "gemini-1.5-flash", 
    config?: GenerationConfig
  ): Promise<GenerateContentResult> {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: modelName });
    return await model.generateContent({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: config,
    });
  }

  /**
   * Statische Methode zur Textgenerierung
   */
  static async generateText(
    apiKey: string, 
    prompt: string, 
    modelName: string = "gemini-1.5-flash", 
    config?: GenerationConfig
  ): Promise<string> {
    try {
      const result = await this.generateContent(apiKey, prompt, modelName, config);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("GeminiService Static Error (generateText):", error);
      throw error;
    }
  }

  /**
   * Generiert einfachen Text-Content basierend auf einem Prompt
   */
  async generateText(prompt: string, config?: GenerationConfig): Promise<string> {
    try {
      const result = await this.model.generateContent({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: config,
      });
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("GeminiService Error (generateText):", error);
      throw error;
    }
  }

  /**
   * Generiert strukturierten JSON Content
   */
  async generateJSON<T>(prompt: string, schemaConfig?: any): Promise<T> {
    try {
      const result = await this.model.generateContent({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: {
          ...schemaConfig,
          responseMimeType: "application/json",
        },
      });

      const response = await result.response;
      const text = response.text();
      return JSON.parse(this.constructor && (this.constructor as any).cleanJsonString ? (this.constructor as any).cleanJsonString(text) : text) as T;
    } catch (error) {
      console.error("GeminiService Error (generateJSON):", error);
      throw error;
    }
  }

  /**
   * Startet eine Chat-Session
   */
  async startChat(history: Content[] = []) {
    return this.model.startChat({
      history,
      generationConfig: {
        maxOutputTokens: 2048,
      },
    });
  }

  /**
   * Hilfsmethode zum Bereinigen von Markdown-Umgebungen ohne verbotene Regex
   */
  public static cleanJsonString(input: string): string {
    let clean = input;
    if (clean.includes("json")) {
      clean = clean.split("json").join("");
    }
    if (clean.includes("")) {
      clean = clean.split("").join("");
    }
    return clean.trim();
  }
}

export const createGeminiService = (apiKey: string) => new GeminiService(apiKey);