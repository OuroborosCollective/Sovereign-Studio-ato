export type FileItem = { path: string; icon: string };
export type RepoFile = { path: string; type: 'blob' | 'tree'; size?: number };
export type Card = { id: string; title: string; body: string };
export type WorkView = 'editor' | 'pipeline';
export type PipelineState = 'idle' | 'planning' | 'generating' | 'validating' | 'failed' | 'fixing' | 'revalidating' | 'green' | 'blocked';
export type MobilePane = 'auftrag' | 'live' | 'log';
export type WorkMode = 'manual' | 'assisted' | 'autonomous';
export type ProjectSettings = {
  repoMode: 'single' | 'monorepo';
  packageManager: 'auto' | 'npm' | 'pnpm' | 'yarn' | 'bun';
  installStrategy: 'safe' | 'workspace' | 'frozen';
  linter: 'auto' | 'eslint' | 'biome' | 'prettier-eslint';
  specialization: string;
  maxFixLoops: number;
  workMode?: WorkMode;
};

export interface AgentStep {
  id: string;
  label: string;
  state: 'pending' | 'running' | 'done' | 'failed';
  message: string;
}

// Chat types
export type ChatRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: number;
}

export type SuggestionType = 'feature' | 'error' | 'improvement';

export interface Suggestion {
  id: string;
  type: SuggestionType;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  accepted?: boolean;
}

export interface ArchitectureAnalysis {
  summary: string;
  components: string[];
  potentialIssues: string[];
  suggestedFeatures: string[];
  integrations: string[];
}
