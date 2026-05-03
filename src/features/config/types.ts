export type Theme = 'light' | 'dark' | 'system';

export type Language = 'en' | 'de' | 'es' | 'fr';

export interface ConfigState {
  theme: Theme;
  language: Language;
  sidebarOpen: boolean;
  notificationsEnabled: boolean;
  lastSync: string | null;
  version: string;
}

export interface ConfigUpdatePayload {
  theme?: Theme;
  language?: Language;
  sidebarOpen?: boolean;
  notificationsEnabled?: boolean;
}

export interface ConfigOption<T> {
  label: string;
  value: T;
  icon?: string;
}

export type ThemeOption = ConfigOption<Theme>;
export type LanguageOption = ConfigOption<Language>;

export interface AppConfig {
  theme: string;
  autoSave: boolean;
  apiEndpoint: string;
  maxRetries: number;
  debugMode: boolean;
  canvas: any;
  gemini: any;
}