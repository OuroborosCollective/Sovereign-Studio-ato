import { Preferences } from '@capacitor/preferences';
import { Capacitor } from '@capacitor/core';

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  tokenType: string;
}

interface IStorageProvider {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  clear(): Promise<void>;
}

class WebStorageProvider implements IStorageProvider {
  async getItem(key: string): Promise<string | null> {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(key);
  }
  async setItem(key: string, value: string): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.setItem(key, value);
    }
  }
  async removeItem(key: string): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(key);
    }
  }
  async clear(): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.clear();
    }
  }
}

class NativeStorageProvider implements IStorageProvider {
  async getItem(key: string): Promise<string | null> {
    const { value } = await Preferences.get({ key });
    return value;
  }
  async setItem(key: string, value: string): Promise<void> {
    await Preferences.set({ key, value });
  }
  async removeItem(key: string): Promise<void> {
    await Preferences.remove({ key });
  }
  async clear(): Promise<void> {
    await Preferences.clear();
  }
}

const provider: IStorageProvider = Capacitor.isNativePlatform() 
  ? new NativeStorageProvider() 
  : new WebStorageProvider();

export class BaseRepository<T> {
  constructor(
    protected readonly key: string,
    protected readonly storage: IStorageProvider
  ) {}

  async get(): Promise<T | null> {
    const value = await this.storage.getItem(this.key);
    if (!value) return null;
    try {
      return JSON.parse(value) as T;
    } catch (error) {
      console.error(`Error parsing storage key: ${this.key}`, error);
      return null;
    }
  }

  async set(value: T): Promise<void> {
    const serialized = JSON.stringify(value);
    await this.storage.setItem(this.key, serialized);
  }

  async remove(): Promise<void> {
    await this.storage.removeItem(this.key);
  }
}

class AuthTokenRepository extends BaseRepository<AuthTokens> {
  constructor(storage: IStorageProvider) {
    super('auth_tokens', storage);
  }

  async getAccessToken(): Promise<string | null> {
    const tokens = await this.get();
    if (!tokens || this.isExpired(tokens)) {
      return null;
    }
    return tokens.accessToken;
  }

  async isTokenExpired(): Promise<boolean> {
    const tokens = await this.get();
    if (!tokens) return true;
    return this.isExpired(tokens);
  }

  private isExpired(tokens: AuthTokens): boolean {
    return Date.now() >= tokens.expiresAt;
  }
}

export const authRepository = new AuthTokenRepository(provider);

export const storageService = {
  // Exposure of raw provider for generic use cases
  async get(key: string): Promise<string | null> {
    return provider.getItem(key);
  },

  async set(key: string, value: string): Promise<void> {
    await provider.setItem(key, value);
  },

  async remove(key: string): Promise<void> {
    await provider.removeItem(key);
  },

  // Facade for AuthTokens (Maintains backward compatibility with improved logic)
  async setTokens(tokens: AuthTokens): Promise<void> {
    await authRepository.set(tokens);
  },

  async getTokens(): Promise<AuthTokens | null> {
    return authRepository.get();
  },

  async clearTokens(): Promise<void> {
    await authRepository.remove();
  },

  async getAccessToken(): Promise<string | null> {
    return authRepository.getAccessToken();
  },

  async isTokenExpired(): Promise<boolean> {
    return authRepository.isTokenExpired();
  },

  async clearAll(): Promise<void> {
    await provider.clear();
  }
};