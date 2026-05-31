// Core types for Sovereign Studio React Native App

export type FileItem = {
  path: string;
  icon: string;
};

export type Card = {
  id: string;
  title: string;
  body: string;
};

export type WorkView = 'editor' | 'pipeline';

export type PipelineState = 'idle' | 'publishing' | 'validating' | 'failed' | 'patching' | 'green';

export type ProjectSettings = {
  repoMode: 'single' | 'monorepo';
  packageManager: 'auto' | 'npm' | 'pnpm' | 'yarn' | 'bun';
  installStrategy: 'safe' | 'workspace' | 'frozen';
  linter: 'auto' | 'eslint' | 'biome' | 'prettier-eslint';
  specialization: string;
  maxFixLoops: number;
};

// Provider Types
export type ProviderType = 'mlvoca' | 'groq' | 'huggingface' | 'together' | 'openrouter' | 'gemini';

export interface ProviderConfig {
  type: ProviderType;
  apiKey?: string;
  baseURL: string;
  model: string;
  supportsStreaming?: boolean;
  maxTokens?: number;
  priority: number;
}

export interface ProviderResponse {
  text: string;
  provider: ProviderType;
  model: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };
}

export interface ProviderError {
  provider: ProviderType;
  error: string;
  statusCode?: number;
  isRetryable: boolean;
}

// GitHub Types
export interface RepoFile {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
}

export interface ParsedRepo {
  owner: string;
  repo: string;
}

// Awareness Sync Types
export interface AwarenessSyncResult {
  summary: string;
  technologies: string[];
  structure: string;
  suggestions: string[];
  rawText: string;
}

// Canvas Types
export type CanvasObjectType = 'rect' | 'ai-text';

export interface CanvasObject {
  id: string;
  type: CanvasObjectType;
  x: number;
  y: number;
  width: number;
  height: number;
  data: Record<string, unknown>;
}

// Chat Types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  provider?: ProviderType;
}

// Config Types
export type AppConfig = {
  canvas: {
    resolutionScale: number;
    showStats: boolean;
  };
  gemini: {
    model: 'gemini-1.5-pro' | 'gemini-1.5-flash';
    temperature: number;
  };
};