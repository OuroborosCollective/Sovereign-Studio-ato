import { GoogleGenerativeAI } from '@google/generative-ai';

export interface GenerateOptions {
  model?: string;
  temperature?: number;
  maxOutputTokens?: number;
  topK?: number;
  topP?: number;
  signal?: AbortSignal;
}

type GenerateContentSecondArg = string | GenerateOptions | undefined;

const DEFAULT_MODEL = 'gemini-1.5-flash';

function getApiKey(): string {
  const apiKey =
    import.meta.env.VITE_GEMINI_API_KEY ||
    import.meta.env.VITE_GOOGLE_AI_API_KEY ||
    import.meta.env.VITE_GOOGLE_API_KEY;

  if (!apiKey) {
    throw new Error(
      'Gemini API Key fehlt. Bitte VITE_GEMINI_API_KEY in deiner .env Datei setzen.'
    );
  }

  return apiKey;
}

function normalizeGenerateOptions(
  secondArg?: GenerateContentSecondArg
): Required<Pick<GenerateOptions, 'model'>> & Omit<GenerateOptions, 'model'> {
  if (typeof secondArg === 'string') {
    return {
      model: secondArg
    };
  }

  return {
    model: secondArg?.model ?? DEFAULT_MODEL,
    temperature: secondArg?.temperature,
    maxOutputTokens: secondArg?.maxOutputTokens,
    topK: secondArg?.topK,
    topP: secondArg?.topP,
    signal: secondArg?.signal
  };
}

export class GeminiService {
  static async generateContent(
    prompt: string,
    optionsOrModel?: GenerateContentSecondArg
  ): Promise<string> {
    if (!prompt.trim()) {
      throw new Error('Prompt darf nicht leer sein.');
    }

    const options = normalizeGenerateOptions(optionsOrModel);

    if (options.signal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError');
    }

    const apiKey = getApiKey();
    const genAI = new GoogleGenerativeAI(apiKey);

    const model = genAI.getGenerativeModel({
      model: options.model,
      generationConfig: {
        temperature: options.temperature,
        maxOutputTokens: options.maxOutputTokens,
        topK: options.topK,
        topP: options.topP
      }
    });

    const abortPromise = new Promise<never>((_, reject) => {
      options.signal?.addEventListener(
        'abort',
        () => {
          reject(new DOMException('Request aborted', 'AbortError'));
        },
        { once: true }
      );
    });

    const generatePromise = model.generateContent(prompt);

    const result = await Promise.race([generatePromise, abortPromise]);
    const response = result.response;
    const text = response.text();

    if (!text.trim()) {
      throw new Error('Gemini hat keine Antwort zurückgegeben.');
    }

    return text;
  }
}
