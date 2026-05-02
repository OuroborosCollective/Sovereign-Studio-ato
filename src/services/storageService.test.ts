import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { BaseRepository } from './storageService';

describe('BaseRepository', () => {
  let mockStorage: any;
  let repository: BaseRepository<any>;

  beforeEach(() => {
    mockStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };
    repository = new BaseRepository('test_key', mockStorage);

    // Silence console.error for clean test output
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('get', () => {
    it('should return parsed JSON when valid JSON is retrieved', async () => {
      const mockData = { id: 1, name: 'test' };
      mockStorage.getItem.mockResolvedValue(JSON.stringify(mockData));

      const result = await repository.get();

      expect(mockStorage.getItem).toHaveBeenCalledWith('test_key');
      expect(result).toEqual(mockData);
    });

    it('should return null when no value is retrieved', async () => {
      mockStorage.getItem.mockResolvedValue(null);

      const result = await repository.get();

      expect(mockStorage.getItem).toHaveBeenCalledWith('test_key');
      expect(result).toBeNull();
    });

    it('should gracefully return null and log an error when malformed JSON is retrieved', async () => {
      const malformedJson = '{ invalid_json: true, }';
      mockStorage.getItem.mockResolvedValue(malformedJson);

      const result = await repository.get();

      expect(mockStorage.getItem).toHaveBeenCalledWith('test_key');
      expect(result).toBeNull();
      expect(console.error).toHaveBeenCalledWith('Error parsing storage key: test_key', expect.any(Error));
    });
  });
});
