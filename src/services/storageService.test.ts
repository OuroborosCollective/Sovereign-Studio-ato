import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { authRepository, AuthTokens } from './storageService';

describe('authRepository', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe('isTokenExpired', () => {
    it('should return true if no tokens are stored', async () => {
      vi.spyOn(authRepository, 'get').mockResolvedValue(null);

      const result = await authRepository.isTokenExpired();

      expect(result).toBe(true);
      expect(authRepository.get).toHaveBeenCalledTimes(1);
    });

    it('should return true if the token is exactly at expiration time', async () => {
      const currentTime = 1000000;
      vi.setSystemTime(currentTime);

      const mockTokens: AuthTokens = {
        accessToken: 'mock-access',
        refreshToken: 'mock-refresh',
        tokenType: 'Bearer',
        expiresAt: currentTime,
      };

      vi.spyOn(authRepository, 'get').mockResolvedValue(mockTokens);

      const result = await authRepository.isTokenExpired();

      expect(result).toBe(true);
    });

    it('should return true if the token is past expiration time', async () => {
      const currentTime = 1000000;
      vi.setSystemTime(currentTime);

      const mockTokens: AuthTokens = {
        accessToken: 'mock-access',
        refreshToken: 'mock-refresh',
        tokenType: 'Bearer',
        expiresAt: currentTime - 1000, // Expired 1 second ago
      };

      vi.spyOn(authRepository, 'get').mockResolvedValue(mockTokens);

      const result = await authRepository.isTokenExpired();

      expect(result).toBe(true);
    });

    it('should return false if the token has not yet expired', async () => {
      const currentTime = 1000000;
      vi.setSystemTime(currentTime);

      const mockTokens: AuthTokens = {
        accessToken: 'mock-access',
        refreshToken: 'mock-refresh',
        tokenType: 'Bearer',
        expiresAt: currentTime + 1000, // Expires in 1 second
      };

      vi.spyOn(authRepository, 'get').mockResolvedValue(mockTokens);

      const result = await authRepository.isTokenExpired();

      expect(result).toBe(false);
    });
  });
});
