import { useState, useCallback, useEffect, useRef } from 'react';
import { GeminiService } from '../services/ai/geminiService';

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
  const abortControllerRef = useRef<AbortController | null>(null);

  const generate = useCallback(async (prompt: string): Promise<string | null> => {
    if (!prompt.trim()) {
      return null;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    setData(null);

    try {
      const result = await GeminiService.generateContent(prompt, {
        signal: controller.signal
      });

      setData(result);
      return result;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return null;
      }

      const errorMessage =
        err instanceof Error
          ? err.message
          : 'Ein unerwarteter Fehler ist aufgetreten';

      setError(errorMessage);
      return null;
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
        setIsLoading(false);
      }
    }
  }, []);

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setIsLoading(false);
    setError(null);
    setData(null);
  }, []);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  return {
    isLoading,
    error,
    data,
    generate,
    reset
  };
};
