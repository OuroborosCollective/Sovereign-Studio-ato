import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NativeStorageProvider } from './storageService';
import { Preferences } from '@capacitor/preferences';

// Mock Capacitor Preferences
vi.mock('@capacitor/preferences', () => ({
  Preferences: {
    get: vi.fn(),
    set: vi.fn(),
    remove: vi.fn(),
    clear: vi.fn(),
  },
}));

describe('NativeStorageProvider', () => {
  let provider: NativeStorageProvider;

  beforeEach(() => {
    provider = new NativeStorageProvider();
    vi.clearAllMocks();
  });

  describe('getItem', () => {
    it('should return value when key exists', async () => {
      vi.mocked(Preferences.get).mockResolvedValueOnce({ value: 'test-value' });

      const result = await provider.getItem('test-key');

      expect(Preferences.get).toHaveBeenCalledWith({ key: 'test-key' });
      expect(result).toBe('test-value');
    });

    it('should return null when key does not exist', async () => {
      vi.mocked(Preferences.get).mockResolvedValueOnce({ value: null });

      const result = await provider.getItem('test-key');

      expect(Preferences.get).toHaveBeenCalledWith({ key: 'test-key' });
      expect(result).toBeNull();
    });
  });

  describe('setItem', () => {
    it('should set value for key', async () => {
      await provider.setItem('test-key', 'test-value');

      expect(Preferences.set).toHaveBeenCalledWith({ key: 'test-key', value: 'test-value' });
    });
  });

  describe('removeItem', () => {
    it('should remove value for key', async () => {
      await provider.removeItem('test-key');

      expect(Preferences.remove).toHaveBeenCalledWith({ key: 'test-key' });
    });
  });

  describe('clear', () => {
    it('should clear all preferences', async () => {
      await provider.clear();

      expect(Preferences.clear).toHaveBeenCalled();
    });
  });
});
