import { Preferences } from '@capacitor/preferences';

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  tokenType: string;
}

const AUTH_TOKENS_KEY = 'auth_tokens';

export const storageService = {
  async get(key: string): Promise<string | null> {
    const { value } = await Preferences.get({ key });
    if (value !== null) return value;
    return typeof window !== 'undefined' ? localStorage.getItem(key) : null;
  },

  async set(key: string, value: string): Promise<void> {
    await Preferences.set({ key, value });
    if (typeof window !== 'undefined') {
      localStorage.setItem(key, value);
    }
  },

  async remove(key: string): Promise<void> {
    await Preferences.remove({ key });
    if (typeof window !== 'undefined') {
      localStorage.removeItem(key);
    }
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
    
    // Check if token is expired
    if (Date.now() >= tokens.expiresAt) {
      return null;
    }
    
    return tokens.accessToken;
  },

  async isTokenExpired(): Promise<boolean> {
    const tokens = await this.getTokens();
    if (!tokens) return true;
    return Date.now() >= tokens.expiresAt;
  }
};