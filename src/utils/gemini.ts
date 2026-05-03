export class GeminiService {
  private static instance: GeminiService;
  private apiKey: string | undefined;

  constructor(apiKey?: string) {
    this.apiKey = apiKey || process.env.NEXT_PUBLIC_GEMINI_API_KEY;
  }

  public static getInstance(apiKey?: string): GeminiService {
    if (!GeminiService.instance) {
      GeminiService.instance = new GeminiService(apiKey);
    }
    return GeminiService.instance;
  }

  async generateResponse(prompt: string): Promise<string> {
    if (!this.apiKey) {
      throw new Error("Gemini API Key is missing");
    }

    try {
      const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=${this.apiKey}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
        }),
      });

      const data = await response.json();
      return data.candidates[0].content.parts[0].text;
    } catch (error) {
      console.error("Gemini API Error:", error);
      throw error;
    }
  }
}