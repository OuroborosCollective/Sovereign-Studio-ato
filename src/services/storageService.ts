import { Preferences } from '@capacitor/preferences';

export const storageService = {
  async get(key: string): Promise<string | null> {
    const { value } = await Preferences.get({ key });
    if (value !== null) return value;
    // Fallback to localStorage just in case
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
  }
};
