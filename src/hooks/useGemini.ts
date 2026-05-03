import { useState, useCallback } from 'react';
import { geminiService } from '../utils/gemini';

interface UseGeminiReturn {
  isLoading: boolean;
  error: string | null;
  data: string | null;
  generate: (prompt: string) => Promise<string | null>;
  reset: () => void;
}

export const useGemini = (): UseGeminiReturn => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<string | null>(null);

  const generate = useCallback(async (prompt: string): Promise<string | null> => {
    if (!prompt.trim()) {
      return null;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await geminiService.generateResponse(prompt);
      setData(result);
      return result;
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Ein unerwarteter Fehler ist aufgetreten';
      setError(errorMessage);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setIsLoading(false);
    setError(null);
    setData(null);
  }, []);

  return {
    isLoading,
    error,
    data,
    generate,
    reset
  };
};