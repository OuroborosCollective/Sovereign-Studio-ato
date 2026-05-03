import { useState, useEffect, useCallback } from 'react';

export interface GeminiHookOptions {
  model?: string;
  offlineFallback?: string;
}

export interface GeminiHookResult {
  generateContent: (prompt: string) => Promise<string>;
  isLoading: boolean;
  error: string | null;
  isOnline: boolean;
}

export function useGemini(options: GeminiHookOptions = {}): GeminiHookResult {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof window !== 'undefined' ? window.navigator.onLine : true
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleStatusChange = () => {
      setIsOnline(window.navigator.onLine);
    };

    window.addEventListener('online', handleStatusChange);
    window.addEventListener('offline', handleStatusChange);

    return () => {
      window.removeEventListener('online', handleStatusChange);
      window.removeEventListener('offline', handleStatusChange);
    };
  }, []);

  const generateContent = useCallback(async (prompt: string): Promise<string> => {
    if (!isOnline) {
      return options.offlineFallback || "Sie sind derzeit offline. Die KI-Anfrage kann nicht verarbeitet werden.";
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/ai/gemini', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt,
          model: options.model || 'gemini-1.5-flash',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Kommunikationsfehler mit der Gemini API');
      }

      const result = await response.json();
      return result.content || '';
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Ein unbekannter Fehler ist aufgetreten';
      setError(errorMessage);
      return options.offlineFallback || `Fehler bei der Inhaltsgenerierung: ${errorMessage}`;
    } finally {
      setIsLoading(false);
    }
  }, [isOnline, options.model, options.offlineFallback]);

  return {
    generateContent,
    isLoading,
    error,
    isOnline,
  };
}