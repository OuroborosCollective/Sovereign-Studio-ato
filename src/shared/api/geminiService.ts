import { GoogleGenerativeAI, GenerationConfig, Content, Part } from "@google/generative-ai";

const API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY || "";
const genAI = new GoogleGenerativeAI(API_KEY);

const ANTIGRAVITY_SYSTEM_PROMPT = `Du bist der Antigravity-Assistent. Deine Aufgabe ist es, präzise, technisch fundierte und dennoch kreative Antworten im Kontext von Physik, Engineering und zukunftsweisenden Technologien zu geben. 
Formatiere deine Antworten immer als valides JSON, wenn Datenstrukturen angefragt werden, oder in klarem Markdown für erklärende Texte. 
Vermeide ausschweifende Einleitungen. Komm direkt zum Punkt.`;

export interface GeminiChatOptions {
  model?: string;
  temperature?: number;
  topP?: number;
  topK?: number;
  maxOutputTokens?: number;
  systemInstruction?: string;
}

export interface GeminiResponse {
  text: string;
  usage?: any;
}

export const geminiService = {
  /**
   * Bereinigt die Response von Markdown-Code-Blöcken ohne verbotene Regex-Syntax.
   */
  cleanResponse(text: string): string {
    let cleaned = text.trim();
    if (cleaned.startsWith("json")) {
      cleaned = cleaned.split("json").join("");
    }
    if (cleaned.startsWith("")) {
      cleaned = cleaned.split("").join("");
    }
    return cleaned.trim();
  },

  /**
   * Generiert eine einfache Textantwort basierend auf einem Prompt.
   */
  async generateText(prompt: string, options: GeminiChatOptions = {}): Promise<string> {
    if (!API_KEY) {
      throw new Error("Gemini API Key ist nicht konfiguriert.");
    }

    try {
      const model = genAI.getGenerativeModel({
        model: options.model || "gemini-1.5-flash",
        systemInstruction: options.systemInstruction,
      });

      const generationConfig: GenerationConfig = {
        temperature: options.temperature ?? 0.7,
        topP: options.topP ?? 0.95,
        topK: options.topK ?? 40,
        maxOutputTokens: options.maxOutputTokens ?? 8192,
      };

      const result = await model.generateContent({
        contents: [{ role: "user", parts: [{ text: prompt } as Part] }],
        generationConfig,
      });

      const response = await result.response;
      const text = response.text();
      
      if (!text) {
        throw new Error("Keine Antwort von Gemini erhalten.");
      }

      return text;
    } catch (error) {
      console.error("Gemini API generateText Error:", error);
      throw error;
    }
  },

  /**
   * Spezifische Antigravity-Logik zur Generierung von Content.
   */
  async generateAntigravityContent(prompt: string, options: GeminiChatOptions = {}): Promise<string> {
    const enrichedOptions: GeminiChatOptions = {
      ...options,
      systemInstruction: options.systemInstruction || ANTIGRAVITY_SYSTEM_PROMPT,
      temperature: options.temperature ?? 0.9,
    };

    const rawResponse = await this.generateText(prompt, enrichedOptions);
    return this.cleanResponse(rawResponse);
  },

  /**
   * Startet oder führt einen Chat-Verlauf fort.
   */
  async chat(history: Content[], message: string, options: GeminiChatOptions = {}): Promise<string> {
    if (!API_KEY) {
      throw new Error("Gemini API Key ist nicht konfiguriert.");
    }

    try {
      const model = genAI.getGenerativeModel({
        model: options.model || "gemini-1.5-flash",
        systemInstruction: options.systemInstruction || ANTIGRAVITY_SYSTEM_PROMPT,
      });

      const chatSession = model.startChat({
        history: history,
        generationConfig: {
          temperature: options.temperature ?? 0.7,
          maxOutputTokens: options.maxOutputTokens ?? 8192,
        },
      });

      const result = await chatSession.sendMessage(message);
      const response = await result.response;
      return this.cleanResponse(response.text());
    } catch (error) {
      console.error("Gemini API Chat Error:", error);
      throw error;
    }
  },

  /**
   * Hilfsmethode zur Validierung des API-Keys
   */
  hasValidConfig(): boolean {
    return !!API_KEY && API_KEY.length > 0;
  }
};