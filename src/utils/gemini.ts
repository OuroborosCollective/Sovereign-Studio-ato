import { GoogleGenerativeAI } from "@google/generative-ai";

export class GeminiService {
  private static instance: GeminiService;
  private genAI: GoogleGenerativeAI | null = null;
  private apiKey: string | undefined;

  constructor(apiKey?: string) {
    this.apiKey = apiKey || process.env.NEXT_PUBLIC_GEMINI_API_KEY;
    if (this.apiKey) {
      this.genAI = new GoogleGenerativeAI(this.apiKey);
    }
  }

  public static getInstance(apiKey?: string): GeminiService {
    if (!GeminiService.instance) {
      GeminiService.instance = new GeminiService(apiKey);
    }
    return GeminiService.instance;
  }

  public static async generateContent(prompt: string, apiKey?: string): Promise<string> {
    const service = GeminiService.getInstance(apiKey);
    return service.generateResponse(prompt);
  }

  async generateResponse(prompt: string, systemInstruction?: string): Promise<string> {
    if (!this.apiKey || !this.genAI) {
      throw new Error("Gemini API Key is missing");
    }

    try {
      const model = this.genAI.getGenerativeModel({ 
        model: "gemini-pro",
        systemInstruction: systemInstruction,
        generationConfig: {
          temperature: 0.7,
          topP: 0.95,
          topK: 40,
          maxOutputTokens: 2048,
        }
      });
      
      const result = await model.generateContent(prompt);
      const response = await result.response;
      return response.text();
    } catch (error) {
      console.error("Gemini API Error:", error);
      throw error;
    }
  }

  async *streamResponse(prompt: string, systemInstruction?: string): AsyncGenerator<string> {
    if (!this.apiKey || !this.genAI) {
      throw new Error("Gemini API Key is missing");
    }

    try {
      const model = this.genAI.getGenerativeModel({ 
        model: "gemini-pro",
        systemInstruction: systemInstruction,
        generationConfig: {
          temperature: 0.7,
          topP: 0.95,
          topK: 40,
          maxOutputTokens: 2048,
        }
      });

      const result = await model.generateContentStream(prompt);

      for await (const chunk of result.stream) {
        const chunkText = chunk.text();
        if (chunkText) {
          yield chunkText;
        }
      }
    } catch (error) {
      console.error("Gemini Stream Error:", error);
      throw error;
    }
  }
}

export const generateContent = async (prompt: string, apiKey?: string): Promise<string> => {
  return GeminiService.generateContent(prompt, apiKey);
};

export const streamContent = async function* (prompt: string, apiKey?: string): AsyncGenerator<string> {
  const service = GeminiService.getInstance(apiKey);
  yield* service.streamResponse(prompt);
};