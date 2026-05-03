import { GoogleGenerativeAI } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || '');

export class GeminiService {
  static async generateContent(prompt: string): Promise<string> {
    const model = genAI.getGenerativeModel({
      model: 'gemini-1.5-flash'
    });

    const chatSession = model.startChat({
      generationConfig: {
        temperature: 0.7,
        topP: 0.9,
      },
      history: [],
    });

    const result = await chatSession.sendMessage(prompt);
    const response = await result.response;
    return response.text();
  }
}