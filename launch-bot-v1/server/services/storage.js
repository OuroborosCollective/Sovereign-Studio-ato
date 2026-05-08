import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');
const STORAGE_FILE = path.join(DATA_DIR, 'user_data.json');

class StorageService {
  constructor() {
    this.initialized = false;
  }

  /**
   * Initialisiert das Speicherverzeichnis und die JSON-Datei, falls nicht vorhanden.
   */
  async ensureStorage() {
    if (this.initialized) return;
    try {
      await fs.mkdir(DATA_DIR, { recursive: true });
      try {
        await fs.access(STORAGE_FILE);
      } catch {
        await fs.writeFile(STORAGE_FILE, JSON.stringify({ users: {} }, null, 2), 'utf-8');
      }
      this.initialized = true;
    } catch (error) {
      console.error('[StorageService] Initialization Error:', error);
      throw error;
    }
  }

  /**
   * Lädt den kompletten Datensatz aus der JSON-Datei.
   */
  async load() {
    await this.ensureStorage();
    const content = await fs.readFile(STORAGE_FILE, 'utf-8');
    return JSON.parse(content);
  }

  /**
   * Speichert den Datensatz persistent ab.
   */
  async save(data) {
    await this.ensureStorage();
    await fs.writeFile(STORAGE_FILE, JSON.stringify(data, null, 2), 'utf-8');
  }

  /**
   * Ruft Daten für einen spezifischen Nutzer ab.
   */
  async getUser(userId) {
    const data = await this.load();
    return data.users[userId] || null;
  }

  /**
   * Aktualisiert oder erstellt Nutzerdaten.
   */
  async updateUser(userId, payload) {
    const data = await this.load();
    const timestamp = new Date().toISOString();

    data.users[userId] = {
      ...data.users[userId],
      ...payload,
      id: userId,
      lastModified: timestamp
    };

    if (!data.users[userId].createdAt) {
      data.users[userId].createdAt = timestamp;
    }

    await this.save(data);
    return data.users[userId];
  }

  /**
   * Löscht einen Nutzer aus dem permanenten Speicher.
   */
  async deleteUser(userId) {
    const data = await this.load();
    if (data.users[userId]) {
      delete data.users[userId];
      await this.save(data);
      return true;
    }
    return false;
  }

  /**
   * Listet alle registrierten Nutzer auf.
   */
  async listUsers() {
    const data = await this.load();
    return Object.values(data.users);
  }
}

export const storage = new StorageService();