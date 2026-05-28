import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useDispatch } from 'react-redux';
import { useGemini } from './useGemini';
import { addVectors } from '../../canvas/canvasSlice';

// Mock react-redux
vi.mock('react-redux', () => ({
  useDispatch: vi.fn(),
}));

// Mock Redux action
vi.mock('../../canvas/canvasSlice', async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    addVectors: vi.fn((payload) => ({ type: 'canvas/addVectors', payload })),
  };
});

describe('useGemini hook', () => {
  const mockDispatch = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useDispatch as any).mockReturnValue(mockDispatch);

    // Mock global fetch
    global.fetch = vi.fn();

    // Default online status
    Object.defineProperty(window.navigator, 'onLine', {
      value: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should initialize with correct default state', () => {
    const { result } = renderHook(() => useGemini());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBe(null);
    expect(result.current.isOnline).toBe(true);
  });

  it('should update isOnline status based on window events', () => {
    const { result } = renderHook(() => useGemini());

    expect(result.current.isOnline).toBe(true);

    act(() => {
      Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true });
      window.dispatchEvent(new Event('offline'));
    });

    expect(result.current.isOnline).toBe(false);

    act(() => {
      Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true });
      window.dispatchEvent(new Event('online'));
    });

    expect(result.current.isOnline).toBe(true);
  });

  describe('generateContent', () => {
    it('should return content on successful API call', async () => {
      const mockResponse = { content: 'Generated AI response' };
      (global.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useGemini());

      let content;
      await act(async () => {
        content = await result.current.generateContent('Hello');
      });

      expect(content).toBe('Generated AI response');
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBe(null);
      expect(global.fetch).toHaveBeenCalledWith('/api/ai/gemini', expect.any(Object));
    });

    it('should handle API errors and set error state', async () => {
      const errorMessage = 'API Error';
      (global.fetch as any).mockResolvedValue({
        ok: false,
        json: async () => ({ message: errorMessage }),
      });

      const { result } = renderHook(() => useGemini({ offlineFallback: 'Fallback text' }));

      let content;
      await act(async () => {
        content = await result.current.generateContent('Hello');
      });

      expect(content).toBe('Fallback text');
      expect(result.current.error).toBe(errorMessage);
      expect(result.current.isLoading).toBe(false);
    });

    it('should return default fallback if offline', async () => {
      Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true });
      const { result } = renderHook(() => useGemini());

      let content;
      await act(async () => {
        content = await result.current.generateContent('Hello');
      });

      expect(content).toBe('Offline-Modus aktiv.');
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  describe('generateCanvasVectors', () => {
    it('should generate vectors and dispatch addVectors to Redux', async () => {
      const mockJson = JSON.stringify([
        { id: 'vec1', type: 'rect', data: { x: 10, y: 20, width: 50, height: 50 }, style: { fill: 'red' } }
      ]);
      const mockResponse = { content: `Here are the vectors: ${mockJson}` };

      (global.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      });

      const onVectorGenerated = vi.fn();
      const { result } = renderHook(() => useGemini({ onVectorGenerated }));

      let vectors;
      await act(async () => {
        vectors = await result.current.generateCanvasVectors('Draw a red square');
      });

      expect(vectors).toHaveLength(1);
      expect(vectors[0].id).toBe('vec1');

      // Verify Redux dispatch
      expect(mockDispatch).toHaveBeenCalled();
      const dispatchedAction = mockDispatch.mock.calls[0][0];
      expect(dispatchedAction.type).toBe('canvas/addVectors');
      expect(dispatchedAction.payload[0].id).toBe('vec1');
      expect(dispatchedAction.payload[0].aiGenerated).toBe(true);
      expect(dispatchedAction.payload[0].fill).toBe('red');

      // Verify callback
      expect(onVectorGenerated).toHaveBeenCalledWith(vectors);
    });

    it('should handle responses without valid JSON vectors', async () => {
      const mockResponse = { content: 'I cannot draw that for you.' };
      (global.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useGemini());

      let vectors;
      await act(async () => {
        vectors = await result.current.generateCanvasVectors('Impossible request');
      });

      expect(vectors).toEqual([]);
      expect(mockDispatch).not.toHaveBeenCalled();
    });
  });
});
