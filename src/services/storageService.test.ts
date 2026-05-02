import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { storageService, authRepository } from './storageService';

describe('storageService.isTokenExpired', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('should return true if no tokens exist', async () => {
    vi.spyOn(authRepository, 'get').mockResolvedValue(null);
    const result = await storageService.isTokenExpired();
    expect(result).toBe(true);
  });

  it('should return true if token is expired', async () => {
    const now = 1000000000000;
    vi.setSystemTime(now);

    vi.spyOn(authRepository, 'get').mockResolvedValue({
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresAt: now - 1000, // 1 second ago
      tokenType: 'Bearer',
    });

    const result = await storageService.isTokenExpired();
    expect(result).toBe(true);
  });

  it('should return true if token expires exactly now', async () => {
    const now = 1000000000000;
    vi.setSystemTime(now);

    vi.spyOn(authRepository, 'get').mockResolvedValue({
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresAt: now,
      tokenType: 'Bearer',
    });

    const result = await storageService.isTokenExpired();
    expect(result).toBe(true);
  });

  it('should return false if token expires in the future', async () => {
    const now = 1000000000000;
    vi.setSystemTime(now);

    vi.spyOn(authRepository, 'get').mockResolvedValue({
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresAt: now + 1000, // 1 second from now
      tokenType: 'Bearer',
    });

    const result = await storageService.isTokenExpired();
    expect(result).toBe(false);
  });
});
