import { useState, useEffect, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { addVectors } from '@/store/slices/canvasSlice';

/**
 * Interface für Canvas-Vektorelemente
 */
export interface CanvasVector {
  id: string;
  type: 'path' | 'rect' | 'circle' | 'text';
  data: any;
  style: {
    stroke?: string;
    fill?: string;
    strokeWidth?: number;
  };
}

export interface GeminiHookOptions {
  model?: string;
  offlineFallback?: string;
  onVectorGenerated?: (vectors: CanvasVector[]) => void;
  autoDispatch?: boolean;
}

export interface GeminiHookResult {
  generateContent: (prompt: string) => Promise<string>;
  generateCanvasVectors: (prompt: string) => Promise<CanvasVector[]>;
  isLoading: boolean;
  error: string | null;
  isOnline: boolean;
}

/**
 * Middleware zur Extraktion von JSON-Vektoren aus KI-Antworten
 */
const extractVectors = (text: string): CanvasVector[] => {
  try {
    const jsonMatch = text.match(/\[\s*{[\s\S]*}\s*\]/);
    if (!jsonMatch) return [];
    
    const parsed = JSON.parse(jsonMatch[0]);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    console.error("Fehler bei der Vektor-Transformation:", err);
    return [];
  }
};

export function useGemini(options: GeminiHookOptions = {}): GeminiHookResult {
  const dispatch = useDispatch();
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
      return options.offlineFallback || "Offline-Modus aktiv.";
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/ai/gemini', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          model: options.model || 'gemini-1.5-flash',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'API Fehler');
      }

      const result = await response.json();
      return result.content || '';
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler';
      setError(errorMessage);
      return options.offlineFallback || `Fehler: ${errorMessage}`;
    } finally {
      setIsLoading(false);
    }
  }, [isOnline, options.model, options.offlineFallback]);

  /**
   * Erzeugt Canvas-kompatible Datenstrukturen und streamt diese in den Redux Store
   */
  const generateCanvasVectors = useCallback(async (prompt: string): Promise<CanvasVector[]> => {
    const systemInstruction = "Antworte ausschließlich im JSON-Format als Array von CanvasVector-Objekten. " +
      "Struktur: { id, type, data: { points: [] }, style: { stroke, strokeWidth } }";
    
    const enhancedPrompt = `${systemInstruction}\n\nUser Request: ${prompt}`;
    
    const rawContent = await generateContent(enhancedPrompt);
    const vectors = extractVectors(rawContent);
    
    if (vectors.length > 0) {
      // Stream an Redux Store
      dispatch(addVectors(vectors));
      
      if (options.onVectorGenerated) {
        options.onVectorGenerated(vectors);
      }
    }
    
    return vectors;
  }, [generateContent, options, dispatch]);

  return {
    generateContent,
    generateCanvasVectors,
    isLoading,
    error,
    isOnline,
  };
}