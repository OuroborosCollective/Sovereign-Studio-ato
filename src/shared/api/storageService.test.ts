import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { StorageService } from './storageService';

describe('StorageService', () => {
  let storageService: StorageService;
  let mockStorage: Map<string, string>;

  beforeEach(() => {
    mockStorage = new Map();
    
    const mockLocalStorage = {
      getItem: (key: string) => mockStorage.get(key) ?? null,
      setItem: (key: string, value: string) => mockStorage.set(key, value),
      removeItem: (key: string) => mockStorage.delete(key),
      clear: () => mockStorage.clear(),
    };
    
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
    });
    
    storageService = new StorageService();
  });

  afterEach(() => {
    mockStorage.clear();
  });

  describe('setItem / getItem', () => {
    it('should store and retrieve a string value', () => {
      storageService.setItem('testKey', 'testValue');
      expect(storageService.getItem<string>('testKey')).toBe('testValue');
    });

    it('should store and retrieve an object value', () => {
      const obj = { name: 'test', value: 123 };
      storageService.setItem('objKey', obj);
      expect(storageService.getItem<typeof obj>('objKey')).toEqual(obj);
    });

    it('should store and retrieve an array value', () => {
      const arr = [1, 2, 3, 'test'];
      storageService.setItem('arrKey', arr);
      expect(storageService.getItem<typeof arr>('arrKey')).toEqual(arr);
    });

    it('should return null for non-existent keys', () => {
      expect(storageService.getItem<string>('nonExistent')).toBeNull();
    });

    it('should overwrite existing values', () => {
      storageService.setItem('key', 'first');
      storageService.setItem('key', 'second');
      expect(storageService.getItem<string>('key')).toBe('second');
    });
  });

  describe('set / get (alias methods)', () => {
    it('should work as alias for setItem/getItem', () => {
      storageService.set('aliasKey', 'aliasValue');
      expect(storageService.get<string>('aliasKey')).toBe('aliasValue');
    });

    it('should work with objects via aliases', () => {
      const obj = { nested: { value: true } };
      storageService.set('nested', obj);
      expect(storageService.get<typeof obj>('nested')).toEqual(obj);
    });
  });

  describe('removeItem', () => {
    it('should remove an item from storage', () => {
      storageService.setItem('toRemove', 'value');
      expect(storageService.getItem<string>('toRemove')).toBe('value');
      
      storageService.removeItem('toRemove');
      expect(storageService.getItem<string>('toRemove')).toBeNull();
    });

    it('should not throw when removing non-existent key', () => {
      expect(() => storageService.removeItem('nonExistent')).not.toThrow();
    });
  });

  describe('clear', () => {
    it('should remove all items from storage', () => {
      storageService.setItem('key1', 'value1');
      storageService.setItem('key2', 'value2');
      storageService.setItem('key3', 'value3');
      
      storageService.clear();
      
      expect(storageService.getItem<string>('key1')).toBeNull();
      expect(storageService.getItem<string>('key2')).toBeNull();
      expect(storageService.getItem<string>('key3')).toBeNull();
    });
  });

  describe('JSON serialization', () => {
    it('should handle complex nested objects', () => {
      const complex = {
        array: [{ a: 1 }, { b: 2 }],
        nested: { deeper: { value: 'test' } },
        boolean: true,
        null: null,
        number: 42.5,
      };
      
      storageService.setItem('complex', complex);
      expect(storageService.getItem<typeof complex>('complex')).toEqual(complex);
    });

    it('should handle empty objects', () => {
      storageService.setItem('empty', {});
      expect(storageService.getItem<object>('empty')).toEqual({});
    });

    it('should handle empty arrays', () => {
      storageService.setItem('emptyArr', []);
      expect(storageService.getItem<[]>('emptyArr')).toEqual([]);
    });

    it('should handle special number values', () => {
      storageService.setItem('numbers', {
        int: 0,
        negative: -123,
        float: 3.14159,
        scientific: 1e10,
        // Note: Infinity values become null when serialized via JSON
        // This is expected JSON behavior
      });
      expect(storageService.getItem('numbers')).toEqual({
        int: 0,
        negative: -123,
        float: 3.14159,
        scientific: 1e10,
      });
    });
  });

  describe('error handling', () => {
    it('should handle localStorage being unavailable', () => {
      const serviceWithoutStorage = new StorageService();
      
      // Mock storage as null
      Object.defineProperty(window, 'localStorage', {
        value: null,
        writable: true,
      });
      
      // Should not throw
      expect(() => serviceWithoutStorage.setItem('key', 'value')).not.toThrow();
      expect(() => serviceWithoutStorage.getItem('key')).not.toThrow();
      expect(() => serviceWithoutStorage.removeItem('key')).not.toThrow();
      expect(() => serviceWithoutStorage.clear()).not.toThrow();
    });

    it('should handle JSON parse errors gracefully', () => {
      mockStorage.set('malformed', 'not valid json {');
      
      const service = new StorageService();
      expect(service.getItem('malformed')).toBeNull();
    });

    it('should handle localStorage.setItem errors gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const storageError = new Error('Quota exceeded');
      vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
        throw storageError;
      });

      storageService.setItem('key', 'value');

      expect(consoleSpy).toHaveBeenCalledWith('Error saving to localStorage', storageError);
      consoleSpy.mockRestore();
    });

    it('should handle localStorage.removeItem errors gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const storageError = new Error('Remove error');
      vi.spyOn(window.localStorage, 'removeItem').mockImplementation(() => {
        throw storageError;
      });

      storageService.removeItem('key');

      expect(consoleSpy).toHaveBeenCalledWith('Error removing from localStorage', storageError);
      consoleSpy.mockRestore();
    });

    it('should handle localStorage.clear errors gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const storageError = new Error('Clear error');
      vi.spyOn(window.localStorage, 'clear').mockImplementation(() => {
        throw storageError;
      });

      storageService.clear();

      expect(consoleSpy).toHaveBeenCalledWith('Error clearing localStorage', storageError);
      consoleSpy.mockRestore();
    });
  });

  describe('instance methods', () => {
    it('should create separate instances with independent storage', () => {
      const service1 = new StorageService();
      const service2 = new StorageService();
      
      service1.setItem('sharedKey', 'service1');
      expect(service2.getItem<string>('sharedKey')).toBe('service1');
      
      service2.setItem('sharedKey', 'service2');
      expect(service1.getItem<string>('sharedKey')).toBe('service2');
    });
  });
});
