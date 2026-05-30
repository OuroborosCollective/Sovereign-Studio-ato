import { Preferences } from '@capacitor/preferences';

async function get(key: string, fallback = ''): Promise<string> {
  try {
    const { value } = await Preferences.get({ key });
    if (value !== null && value !== undefined) return value;
    const lsVal = localStorage.getItem(key);
    if (lsVal) {
      await Preferences.set({ key, value: lsVal }).catch(() => {});
      return lsVal;
    }
    return fallback;
  } catch {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  }
}

async function set(key: string, value: string): Promise<void> {
  try {
    if (value.trim()) {
      await Preferences.set({ key, value: value.trim() });
      localStorage.setItem(key, value.trim());
    } else {
      await Preferences.remove({ key });
      localStorage.removeItem(key);
    }
  } catch {
    try {
      if (value.trim()) {
        localStorage.setItem(key, value.trim());
      } else {
        localStorage.removeItem(key);
      }
    } catch {}
  }
}

async function remove(key: string): Promise<void> {
  try {
    await Preferences.remove({ key });
    localStorage.removeItem(key);
  } catch {
    try {
      localStorage.removeItem(key);
    } catch {}
  }
}

export const keyStorage = { get, set, remove };
