export class StorageService {
  private storage: Storage | null = typeof window !== 'undefined' ? window.localStorage : null;

  public setItem<T>(key: string, value: T): void {
    if (!this.storage) return;
    try {
      const serializedValue = JSON.stringify(value);
      this.storage.setItem(key, serializedValue);
    } catch (error) {
      console.error('Error saving to localStorage', error);
    }
  }

  public getItem<T>(key: string): T | null {
    if (!this.storage) return null;
    try {
      const item = this.storage.getItem(key);
      if (item === null) return null;
      return JSON.parse(item) as T;
    } catch (error) {
      console.error('Error reading from localStorage', error);
      return null;
    }
  }

  public set<T>(key: string, value: T): void {
    this.setItem(key, value);
  }

  public get<T>(key: string): T | null {
    return this.getItem(key);
  }

  public removeItem(key: string): void {
    if (!this.storage) return;
    try {
      this.storage.removeItem(key);
    } catch (error) {
      console.error('Error removing from localStorage', error);
    }
  }

  public clear(): void {
    if (!this.storage) return;
    try {
      this.storage.clear();
    } catch (error) {
      console.error('Error clearing localStorage', error);
    }
  }
}

export const storageService = new StorageService();