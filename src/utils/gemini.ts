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

  public static async generateContent(prompt: string, apiKey?: string): Promise<string> {
    return GeminiService.getInstance(apiKey).generateResponse(prompt);
  }

  public static async generateText(prompt: string, apiKey?: string): Promise<string> {
    return GeminiService.getInstance(apiKey).generateResponse(prompt);
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
      
      if (!data.candidates || data.candidates.length === 0) {
        throw new Error("No candidates returned from Gemini API");
      }

      return data.candidates[0].content.parts[0].text;
    } catch (error) {
      console.error("Gemini API Error:", error);
      throw error;
    }
  }

  async *streamResponse(prompt: string): AsyncGenerator<string> {
    if (!this.apiKey) {
      throw new Error("Gemini API Key is missing");
    }

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:streamGenerateContent?key=${this.apiKey}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
      }),
    });

    if (!response.body) {
      throw new Error("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      let startBracket = buffer.indexOf('{"candidates"');
      while (startBracket !== -1) {
        let bracketCount = 0;
        let endBracket = -1;
        
        for (let i = startBracket; i < buffer.length; i++) {
          if (buffer[i] === '{') bracketCount++;
          else if (buffer[i] === '}') bracketCount--;
          
          if (bracketCount === 0) {
            endBracket = i;
            break;
          }
        }

        if (endBracket !== -1) {
          const jsonStr = buffer.substring(startBracket, endBracket + 1);
          try {
            const data = JSON.parse(jsonStr);
            const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
            if (text) yield text;
          } catch (e) {
            console.error("Error parsing stream chunk", e);
          }
          buffer = buffer.substring(endBracket + 1);
          startBracket = buffer.indexOf('{"candidates"');
        } else {
          break;
        }
      }
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