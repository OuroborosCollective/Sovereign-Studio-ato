import { GoogleGenerativeAI, GenerativeModel, GenerationConfig, Content, GenerateContentResult } from "@google/generative-ai";

export interface GeminiResponse {
  text: string;
  usage?: any;
}

export interface GenerateOptions {
  prompt: string;
  systemInstruction?: string;
  modelName?: string;
  config?: GenerationConfig;
}

export class GeminiService {
  private genAI: GoogleGenerativeAI;
  private model: GenerativeModel;

  constructor(apiKey: string, modelName: string = "gemini-1.5-flash", systemInstruction?: string) {
    if (!apiKey) {
      throw new Error("Gemini API Key is missing");
    }
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ 
      model: modelName,
      systemInstruction: systemInstruction ? { role: "system", parts: [{ text: systemInstruction }] } : undefined
    });
  }

  /**
   * Statische Methode zur Inhaltsgenerierung
   */
  static async generateContent(
    apiKey: string, 
    options: GenerateOptions
  ): Promise<GenerateContentResult> {
    const { prompt, systemInstruction, modelName = "gemini-1.5-flash", config } = options;
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ 
      model: modelName,
      systemInstruction: systemInstruction ? { role: "system", parts: [{ text: systemInstruction }] } : undefined
    });
    
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
    options: GenerateOptions
  ): Promise<string> {
    try {
      const result = await this.generateContent(apiKey, options);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("GeminiService Static Error (generateText):", error);
      throw error;
    }
  }

  /**
   * Generiert einfachen Text-Content basierend auf Optionen
   */
  async generateText(options: GenerateOptions | string): Promise<string> {
    try {
      let promptText: string;
      let config: GenerationConfig | undefined;
      let activeModel = this.model;

      if (typeof options === "string") {
        promptText = options;
      } else {
        promptText = options.prompt;
        config = options.config;
        
        // Falls spezifische Model-Optionen für diesen Call nötig sind
        if (options.systemInstruction || options.modelName) {
          activeModel = this.genAI.getGenerativeModel({
            model: options.modelName || "gemini-1.5-flash",
            systemInstruction: options.systemInstruction ? { role: "system", parts: [{ text: options.systemInstruction }] } : undefined
          });
        }
      }

      const result = await activeModel.generateContent({
        contents: [{ role: "user", parts: [{ text: promptText }] }],
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
  async generateJSON<T>(options: GenerateOptions | string, schemaConfig?: any): Promise<T> {
    try {
      let promptText: string;
      let config: GenerationConfig | undefined;
      let activeModel = this.model;

      if (typeof options === "string") {
        promptText = options;
      } else {
        promptText = options.prompt;
        config = options.config;
        if (options.systemInstruction || options.modelName) {
          activeModel = this.genAI.getGenerativeModel({
            model: options.modelName || "gemini-1.5-flash",
            systemInstruction: options.systemInstruction ? { role: "system", parts: [{ text: options.systemInstruction }] } : undefined
          });
        }
      }

      const result = await activeModel.generateContent({
        contents: [{ role: "user", parts: [{ text: promptText }] }],
        generationConfig: {
          ...config,
          ...schemaConfig,
          responseMimeType: "application/json",
        },
      });

      const response = await result.response;
      const text = response.text();
      const cleanedText = GeminiService.cleanJsonString(text);
      return JSON.parse(cleanedText) as T;
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
   * Hilfsmethode zum Bereinigen von Markdown-Umgebungen
   */
  public static cleanJsonString(input: string): string {
    let clean = input.trim();
    if (clean.startsWith("")) {
      const lines = clean.split("\n");
      // Entferne die erste Zeile (json oder ) und die letzte Zeile ()
      if (lines.length > 2) {
        clean = lines.slice(1, lines.length - 1).join("\n");
      }
    }
    return clean.trim();
  }
}

export const createGeminiService = (apiKey: string) => new GeminiService(apiKey);

export const geminiService = {
  generateText: GeminiService.generateText,
  generateContent: GeminiService.generateContent,
  cleanJsonString: GeminiService.cleanJsonString
};

export default GeminiService;