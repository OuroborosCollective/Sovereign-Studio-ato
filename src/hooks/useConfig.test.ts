import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useConfig } from './useConfig';
import { storageService } from '../shared/api/storageService';

// Mock the storage service
vi.mock('../shared/api/storageService', () => ({
  storageService: {
    get: vi.fn(),
    set: vi.fn(),
  },
}));

describe('useConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('initial state', () => {
    it('should return default config when no saved config exists', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      expect(result.current.config).toEqual({
        canvas: {
          resolutionScale: 1,
          fpsLimit: 60,
          showStats: false,
          bloomEnabled: true,
        },
        gemini: {
          temperature: 0.7,
          topP: 1,
          maxTokens: 2000,
          model: 'gemini-1.5-flash',
        },
      });
    });

    it('should be not loaded initially', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      expect(result.current.isLoaded).toBe(false);

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });
    });

    it('should merge saved config with defaults', async () => {
      const savedConfig = {
        canvas: {
          resolutionScale: 2,
          fpsLimit: 30,
          showStats: true,
          bloomEnabled: false,
        },
        gemini: {
          temperature: 0.5,
          topP: 0.9,
          maxTokens: 1000,
          model: 'gemini-1.5-flash' as const,
        },
      };

      vi.mocked(storageService.get).mockResolvedValue(JSON.stringify(savedConfig));

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      expect(result.current.config.canvas.resolutionScale).toBe(2);
      expect(result.current.config.canvas.fpsLimit).toBe(30);
      expect(result.current.config.canvas.showStats).toBe(true);
      expect(result.current.config.canvas.bloomEnabled).toBe(false);
      expect(result.current.config.gemini.temperature).toBe(0.5);
    });

    it('should handle partial saved config', async () => {
      const partialConfig = {
        canvas: {
          resolutionScale: 3,
          fpsLimit: 120,
          showStats: true,
          bloomEnabled: true,
        },
        gemini: {
          temperature: 0.9,
          topP: 0.95,
          maxTokens: 5000,
          model: 'gemini-1.5-pro' as const,
        },
      };

      vi.mocked(storageService.get).mockResolvedValue(JSON.stringify(partialConfig));

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      expect(result.current.config).toEqual(partialConfig);
    });

    it('should handle storage errors gracefully', async () => {
      vi.mocked(storageService.get).mockRejectedValue(new Error('Storage error'));

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      // Should still have default config
      expect(result.current.config.gemini.model).toBe('gemini-1.5-flash');
    });

    it('should handle non-string saved config (already parsed)', async () => {
      const parsedConfig = {
        canvas: {
          resolutionScale: 1.5,
          fpsLimit: 60,
          showStats: false,
          bloomEnabled: true,
        },
        gemini: {
          temperature: 0.7,
          topP: 1,
          maxTokens: 2000,
          model: 'gemini-1.5-flash' as const,
        },
      };

      vi.mocked(storageService.get).mockResolvedValue(parsedConfig);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      expect(result.current.config.canvas.resolutionScale).toBe(1.5);
    });
  });

  describe('updateConfig', () => {
    it('should update config and persist to storage', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        result.current.updateConfig({
          canvas: { resolutionScale: 2 },
        });
      });

      expect(result.current.config.canvas.resolutionScale).toBe(2);
      expect(storageService.set).toHaveBeenCalledWith(
        'app_settings_v1',
        expect.stringContaining('"resolutionScale":2')
      );
    });

    it('should merge partial updates at top level', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        result.current.updateConfig({
          gemini: { temperature: 0.9, topP: 0.5, maxTokens: 1000, model: 'gemini-1.5-flash' },
        });
      });

      expect(result.current.config.gemini.temperature).toBe(0.9);
      expect(result.current.config.gemini.model).toBe('gemini-1.5-flash');
      expect(result.current.config.canvas.resolutionScale).toBe(1); // canvas unchanged
    });

    it('should handle updateConfig errors gracefully', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);
      vi.mocked(storageService.set).mockImplementation(() => {
        throw new Error('Storage error');
      });

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        // Should not throw
        expect(() => result.current.updateConfig({ canvas: { resolutionScale: 2 } })).not.toThrow();
      });
      
      // Config should still be updated in memory
      expect(result.current.config.canvas.resolutionScale).toBe(2);
    });

    it('should support updating deep nested properties', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        result.current.updateConfig({
          gemini: {
            model: 'gemini-1.5-pro',
            temperature: 1.0,
          },
        });
      });

      expect(result.current.config.gemini.model).toBe('gemini-1.5-pro');
      expect(result.current.config.gemini.temperature).toBe(1.0);
    });
  });

  describe('resetToDefaults', () => {
    it('should reset config to default values', async () => {
      const savedConfig = {
        canvas: { resolutionScale: 5, fpsLimit: 10, showStats: true, bloomEnabled: false },
        gemini: { temperature: 0.1, topP: 0.5, maxTokens: 100, model: 'gemini-1.5-pro' as const },
      };

      vi.mocked(storageService.get).mockResolvedValue(JSON.stringify(savedConfig));

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      expect(result.current.config.canvas.resolutionScale).toBe(5);

      act(() => {
        result.current.resetToDefaults();
      });

      expect(result.current.config.canvas.resolutionScale).toBe(1);
      expect(result.current.config.canvas.fpsLimit).toBe(60);
      expect(result.current.config.gemini.temperature).toBe(0.7);
      expect(result.current.config.gemini.model).toBe('gemini-1.5-flash');
    });

    it('should persist reset config to storage', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        result.current.resetToDefaults();
      });

      expect(storageService.set).toHaveBeenCalledWith(
        'app_settings_v1',
        expect.stringContaining('"resolutionScale":1')
      );
    });

    it('should handle resetToDefaults errors gracefully', async () => {
      vi.mocked(storageService.get).mockResolvedValue(null);
      vi.mocked(storageService.set).mockImplementation(() => {
        throw new Error('Storage error');
      });

      const { result } = renderHook(() => useConfig());

      await waitFor(() => {
        expect(result.current.isLoaded).toBe(true);
      });

      act(() => {
        // Should not throw
        expect(() => result.current.resetToDefaults()).not.toThrow();
      });
      
      // Config should still be reset in memory
      expect(result.current.config.canvas.resolutionScale).toBe(1);
    });
  });
});
