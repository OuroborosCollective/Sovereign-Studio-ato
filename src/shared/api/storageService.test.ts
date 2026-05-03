import { storageService } from './storageService';

describe('StorageService', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
    
    const mockStorage: Record<string, string> = {};
    
    jest.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => {
      mockStorage[key] = value;
    });
    
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      return mockStorage[key] || null;
    });
    
    jest.spyOn(Storage.prototype, 'removeItem').mockImplementation((key) => {
      delete mockStorage[key];
    });
    
    jest.spyOn(Storage.prototype, 'clear').mockImplementation(() => {
      Object.keys(mockStorage).forEach(key => delete mockStorage[key]);
    });
  });

  it('should save data correctly in localStorage', () => {
    const key = 'user_session';
    const value = { id: 1, name: 'Test User' };
    
    storageService.setItem(key, value);
    
    const storedValue = localStorage.getItem(key);
    expect(storedValue).toBe(JSON.stringify(value));
  });

  it('should retrieve data correctly from localStorage', () => {
    const key = 'user_settings';
    const value = { theme: 'dark', notifications: true };
    localStorage.setItem(key, JSON.stringify(value));
    
    const result = storageService.getItem<typeof value>(key);
    
    expect(result).toEqual(value);
  });

  it('should return null if the key does not exist', () => {
    const result = storageService.getItem('non_existent_key');
    expect(result).toBeNull();
  });

  it('should handle malformed JSON gracefully', () => {
    const key = 'bad_data';
    localStorage.setItem(key, 'invalid-json-{');
    
    const result = storageService.getItem(key);
    expect(result).toBeNull();
  });

  it('should remove a specific item', () => {
    const key = 'temp_data';
    storageService.setItem(key, { test: true });
    storageService.removeItem(key);
    
    expect(localStorage.getItem(key)).toBeNull();
  });

  it('should clear all stored data', () => {
    storageService.setItem('key1', 'val1');
    storageService.setItem('key2', 'val2');
    
    storageService.clear();
    
    expect(localStorage.getItem('key1')).toBeNull();
    expect(localStorage.getItem('key2')).toBeNull();
  });
});