import { Preferences } from '@capacitor/preferences';

type SavedListener = (key: string) => void;
const savedListeners = new Set<SavedListener>();

/**
 * Subscribe to successful key-persist events. The listener fires whenever a
 * non-empty value is persisted via `set()` (web localStorage or Capacitor
 * Preferences). Returns an unsubscribe function.
 */
function onSaved(listener: SavedListener): () => void {
  savedListeners.add(listener);
  return () => {
    savedListeners.delete(listener);
  };
}

function notifySaved(key: string): void {
  savedListeners.forEach((listener) => {
    try {
      listener(key);
    } catch {
      // ignore listener errors so persistence is never affected
    }
  });
}

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
  const hasValue = !!value.trim();
  try {
    if (hasValue) {
      await Preferences.set({ key, value: value.trim() });
      localStorage.setItem(key, value.trim());
    } else {
      await Preferences.remove({ key });
      localStorage.removeItem(key);
    }
    if (hasValue) notifySaved(key);
  } catch {
    try {
      if (hasValue) {
        localStorage.setItem(key, value.trim());
        notifySaved(key);
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

export const keyStorage = { get, set, remove, onSaved };
