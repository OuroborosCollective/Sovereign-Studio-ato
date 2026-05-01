import { Preferences } from '@capacitor/preferences';
import { Capacitor } from '@capacitor/core';

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  tokenType: string;
}

interface StorageProvider {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
  clear(): Promise<void>;
}

const WebProvider: StorageProvider = {
  async get(key: string): Promise<string | null> {
    return typeof window !== 'undefined' ? localStorage.getItem(key) : null;
  },
  async set(key: string, value: string): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.setItem(key, value);
    }
  },
  async remove(key: string): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(key);
    }
  },
  async clear(): Promise<void> {
    if (typeof window !== 'undefined') {
      localStorage.clear();
    }
  }
};

const NativeProvider: StorageProvider = {
  async get(key: string): Promise<string | null> {
    const { value } = await Preferences.get({ key });
    return value;
  },
  async set(key: string, value: string): Promise<void> {
    await Preferences.set({ key, value });
  },
  async remove(key: string): Promise<void> {
    await Preferences.remove({ key });
  },
  async clear(): Promise<void> {
    await Preferences.clear();
  }
};

const AUTH_TOKENS_KEY = 'auth_tokens';
const provider: StorageProvider = Capacitor.isNativePlatform() ? NativeProvider : WebProvider;

export const storageService = {
  async get(key: string): Promise<string | null> {
    return provider.get(key);
  },

  async set(key: string, value: string): Promise<void> {
    await provider.set(key, value);
  },

  async remove(key: string): Promise<void> {
    await provider.remove(key);
  },

  async setTokens(tokens: AuthTokens): Promise<void> {
    const value = JSON.stringify(tokens);
    await this.set(AUTH_TOKENS_KEY, value);
  },

  async getTokens(): Promise<AuthTokens | null> {
    const value = await this.get(AUTH_TOKENS_KEY);
    if (!value) return null;
    try {
      return JSON.parse(value) as AuthTokens;
    } catch (error) {
      console.error('Error parsing auth tokens', error);
      return null;
    }
  },

  async clearTokens(): Promise<void> {
    await this.remove(AUTH_TOKENS_KEY);
  },

  async getAccessToken(): Promise<string | null> {
    const tokens = await this.getTokens();
    if (!tokens) return null;
    
    if (Date.now() >= tokens.expiresAt) {
      return null;
    }
    
    return tokens.accessToken;
  },

  async isTokenExpired(): Promise<boolean> {
    const tokens = await this.getTokens();
    if (!tokens) return true;
    return Date.now() >= tokens.expiresAt;
  },

  async clearAll(): Promise<void> {
    await provider.clear();
  }
};