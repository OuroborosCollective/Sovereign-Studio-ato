import { useState, useEffect, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { addVectors, CanvasObject } from '../../canvas/canvasSlice';
import { maskSecrets } from '../../../shared/utils/crypto';

/**
 * Interface für Canvas-Vektorelemente (KI-Format)
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
    return Array.isArray(parsed) ? (parsed as CanvasVector[]) : [];
  } catch (err) {
    console.error("Fehler bei der Vektor-Transformation:", err);
    return [];
  }
};

/**
 * Transformiert CanvasVector (KI-Format) in CanvasObject (App-Format)
 * Löst TS2345 durch explizite Erfüllung des CanvasObject-Interfaces.
 */
const mapVectorToCanvasObject = (vector: CanvasVector): CanvasObject => {
  return {
    id: vector.id || `ai-${Math.random().toString(36).substr(2, 9)}`,
    type: vector.type === 'text' ? 'ai-text' : vector.type,
    x: vector.data?.x ?? 0,
    y: vector.data?.y ?? 0,
    left: vector.data?.x ?? 0,
    top: vector.data?.y ?? 0,
    width: vector.data?.width ?? 100,
    height: vector.data?.height ?? 100,
    scaleX: 1,
    scaleY: 1,
    angle: 0,
    flipX: false,
    flipY: false,
    opacity: 1,
    visible: true,
    zIndex: 0,
    aiGenerated: true,
    fill: vector.style?.fill || 'transparent',
    stroke: vector.style?.stroke || '#000000',
    strokeWidth: vector.style?.strokeWidth || 1,
    data: vector.data,
    path: vector.type === 'path' ? (vector.data?.points || []) : undefined,
    text: vector.type === 'text' ? (vector.data?.text || '') : undefined,
  };
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
      const errorMessage = maskSecrets(err instanceof Error ? err.message : 'Unbekannter Fehler');
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
      // Transform vectors to CanvasObject structure to satisfy TypeScript and Redux
      // Explicitly typed as CanvasObject[] to ensure compatibility with addVectors action
      const canvasObjects: CanvasObject[] = vectors.map(mapVectorToCanvasObject);
      dispatch(addVectors(canvasObjects));
      
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
